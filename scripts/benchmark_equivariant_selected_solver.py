"""Fixed paired study of default and suit-equivariant exact selected CFR+.

All solver calls run in fresh source-frozen child processes. Raw child output is
retained before parsing or independent verification; expected finite-iteration
misses and resource rejections remain visible. No full-deck or production
performance claim follows from these bounded cases.
"""
import argparse
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from math import isfinite
from pathlib import Path
import platform
import subprocess
import sys
import time
import tracemalloc
from unittest.mock import patch

from pokerlab.cards import DECK
from pokerlab.exact_selected_solver import solve_four_street_exact_selected
from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions
from scripts.benchmark_selected_operator import ROOT, _identity, _rss, _write
from scripts.exact_selected_compact_certificate import evaluate_exact
from scripts.preflop_validation import replay_policy

ITERATIONS = {"symmetric": 10, "asymmetric": 10, "original-22": 10,
              "one-world": 1000, "original-22-reject": 1000}
METRICS = ("value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value",
           "sb_gain", "bb_gain", "nash_conv", "exploitability")
REPLAY_TOLERANCE = 1e-10
SCHEDULE = tuple(
    [("symmetric", "default", 0, False), ("symmetric", "suit-equivariant", 0, False),
     ("symmetric", "suit-equivariant", 1, False), ("symmetric", "default", 1, False),
     ("symmetric", "default", 2, False), ("symmetric", "suit-equivariant", 2, False)] +
    [("symmetric", "default", "traced", True),
     ("symmetric", "suit-equivariant", "traced", True)] +
    [("asymmetric", "default", 0, False), ("asymmetric", "suit-equivariant", 0, False)] +
    [("original-22", "default", 0, False), ("original-22", "suit-equivariant", 0, False)] +
    [("one-world", "default", 0, False), ("one-world", "suit-equivariant", 0, False)] +
    [("original-22-reject", "suit-equivariant", 0, False)])


def _base_case():
    return json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text(encoding="utf-8"))["case"]


def case_for(name):
    base = _base_case()
    if name in ("original-22", "original-22-reject"):
        return dict(base, id="original-22-exact-product-study")
    if name == "symmetric":
        return {"id": "suit-exchange-symmetric-v1", "sb_range": "AcAh:1,AdAh:1",
            "bb_range": "KcKh:1,KdKh:1", "config": {"starting_stack": [2, 2],
                "small_blind": .5, "big_blind": 1, "raise_sizes": [.5],
                "max_raises": 1, "include_all_in": False},
            "runouts": ["2c3c4h5s6h", "2d3d4h5s6h"],
            "flop_config": {"bet_sizes": [.5], "raise_sizes": [], "max_raises": 0, "include_all_in": False},
            "turn_config": {"bet_sizes": [.5], "raise_sizes": [], "max_raises": 0, "include_all_in": False},
            "river_config": {"bet_sizes": [.5], "raise_sizes": [], "max_raises": 0, "include_all_in": False}}
    if name == "asymmetric":
        case = case_for("symmetric")
        return dict(case, id="weighted-asymmetric-suit-exchange-v1",
            sb_range="AcAh:0.7,AdAh:0.3", bb_range="KcKh:0.4,KdKh:0.6")
    if name == "one-world":
        return dict(base, id="one-world-t1000-v1", sb_range="AsAd", bb_range="KsKd",
                    runouts=["2c3c4d7h8h"])
    raise ValueError("Unknown fixed equivariant study case")


def request_for(case, iterations):
    return FourStreetSolveRequest(case["sb_range"], case["bb_range"], tuple(case["runouts"]),
        preflop_config=PreflopConfig.from_dict(case["config"]),
        flop_actions=PostflopActions(**case["flop_config"]),
        turn_actions=PostflopActions(**case["turn_config"]),
        river_actions=PostflopActions(**case["river_config"]),
        iterations=iterations, algorithm="cfrplus", traversal="public-batched",
        diagnostics="public-batched", resource_model="public-vector")


def _runtime():
    return {"implementation": platform.python_implementation(), "version": platform.python_version(),
        "sys_version": sys.version, "platform": platform.platform(), "machine": platform.machine()}


def _contains_resource_word(message):
    import re
    return re.search(r"\b(?:admission|limit|exceeds?|exceeded|forecast|cap|capacity)\b",
                     message.lower()) is not None


def child(case_name, reduction, sample, traced=False):
    if reduction not in ("default", "suit-equivariant"):
        raise ValueError("Unknown fixed reduction")
    iterations = ITERATIONS[case_name]
    case = case_for(case_name)
    request = request_for(case, iterations)
    calls = {"default_trainer_calls": 0, "equivariant_trainer_calls": 0,
        "rank_calls": 0, "pair_query_calls": 0, "native_calls": 0,
        "world_producer_calls": 0, "popen_calls": 0}
    from pokerlab import exact_selected_solver as solver
    from pokerlab import exact_selected_kernel as kernel_module
    from pokerlab import equivariant_packed_cfr as equivariant_module
    old_train, rank = solver.train_packed, kernel_module.rank_hand
    new_train = equivariant_module.train_equivariant_packed
    def counted_old(*args, **kwargs):
        calls["default_trainer_calls"] += 1
        return old_train(*args, **kwargs)
    def counted_new(*args, **kwargs):
        calls["equivariant_trainer_calls"] += 1
        return new_train(*args, **kwargs)
    def counted_rank(*args, **kwargs):
        calls["rank_calls"] += 1
        return rank(*args, **kwargs)
    def counted_pair(*args, **kwargs):
        calls["pair_query_calls"] += 1
        raise AssertionError("forbidden pair-probability diagnostic query")
    def forbidden_call(counter, target):
        def reject(*_args, **_kwargs):
            calls[counter] += 1
            raise AssertionError("forbidden production path: " + target)
        return reject
    forbidden = (
        ("world_producer_calls", "pokerlab.preflop_solver._enumerate_physical_worlds"),
        ("world_producer_calls", "pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds"),
        ("world_producer_calls", "pokerlab.preflop_solver._merge_preflop_tree"),
        ("native_calls", "pokerlab.native_selected_operator.train_native_selected"),
        ("native_calls", "pokerlab.native_selected_dag.train_native_selected_dag"),
        ("native_calls", "pokerlab.native_public_cfr.train_native_public"),
        ("popen_calls", "subprocess.Popen"))
    start = None
    seconds = 0.0
    allocation = None
    try:
        with ExitStack() as stack:
            for counter, target in forbidden:
                stack.enter_context(patch(target, new=forbidden_call(counter, target)))
            stack.enter_context(patch.object(solver, "train_packed", new=counted_old))
            stack.enter_context(patch.object(equivariant_module, "train_equivariant_packed", new=counted_new))
            stack.enter_context(patch.object(kernel_module, "rank_hand", new=counted_rank))
            stack.enter_context(patch.object(ExactSelectedRunoutKernel, "pair_probability_exact", new=counted_pair))
            if traced:
                tracemalloc.start()
            start = time.perf_counter()
            try:
                payload = solve_four_street_exact_selected(request, rank_cache_boards=64,
                    pair_diagnostics="compact", exact_arithmetic="dyadic", training_reduction=reduction)
            finally:
                seconds = time.perf_counter() - start
                allocation = tracemalloc.get_traced_memory()[1] if traced else None
                if traced:
                    tracemalloc.stop()
        status, error = "complete", None
    except ValueError as exc:
        allowed = case_name == "original-22-reject" and reduction == "suit-equivariant" and not any(calls.values()) and _contains_resource_word(str(exc))
        if not allowed:
            status, payload = "failed", None
            error = {"type": type(exc).__name__, "message": str(exc)}
        else:
            status, payload = "pretraining-rejected", None
            error = {"type": type(exc).__name__, "message": str(exc)}
    except Exception as exc:
        status, payload = "failed", None
        error = {"type": type(exc).__name__, "message": str(exc)}
    if traced and tracemalloc.is_tracing():
        tracemalloc.stop()
    return {"case": case_name, "reduction": reduction, "sample": sample,
        "iterations": iterations, "traced": traced, "status": status, "error": error,
        "seconds": seconds, "python_peak_allocation_bytes": allocation,
        "process_lifetime_peak_working_set_bytes": _rss(), "actual_calls": calls,
        "payload": payload, "runtime": _runtime()}


def _case_snapshot(case):
    return deepcopy(case)


def _validate_child(raw, expected):
    case_name, reduction, sample, traced = expected
    _need(type(raw) is dict and raw.get("case") == case_name and raw.get("reduction") == reduction and
          raw.get("sample") == sample and raw.get("iterations") == ITERATIONS[case_name] and
          raw.get("traced") is traced and raw.get("runtime") == _runtime(), "child identity/runtime mismatch")
    _need(type(raw.get("seconds")) in (int, float) and isfinite(raw["seconds"]) and raw["seconds"] > 0,
          "child timer missing or invalid")
    _need(type(raw.get("process_lifetime_peak_working_set_bytes")) is int and
          raw["process_lifetime_peak_working_set_bytes"] > 0, "child process peak missing")
    allocation = raw.get("python_peak_allocation_bytes")
    _need((type(allocation) is int and allocation > 0) if traced else allocation is None,
          "tracemalloc measurement mismatch")
    calls = raw.get("actual_calls")
    _need(type(calls) is dict and set(calls) == {"default_trainer_calls", "equivariant_trainer_calls",
          "rank_calls", "pair_query_calls", "native_calls", "world_producer_calls", "popen_calls"} and
          all(type(value) is int and value >= 0 for value in calls.values()) and
          not any(calls[k] for k in ("pair_query_calls", "native_calls", "world_producer_calls", "popen_calls")),
          "forbidden pair/world/native path entered")
    _need(raw.get("status") in ("complete", "pretraining-rejected", "failed"), "unknown child status")
    if raw["status"] == "pretraining-rejected":
        _need(case_name == "original-22-reject" and reduction == "suit-equivariant" and
              type(raw.get("error")) is dict and raw["error"].get("type") == "ValueError" and
              _contains_resource_word(raw["error"].get("message", "")) and
              raw.get("payload") is None and not any(calls.values()), "unexpected/non-early resource rejection")
        return
    _need(raw["status"] == "complete" and raw.get("error") is None and type(raw.get("payload")) is dict,
          "child solve failed: " + str(raw.get("error")))
    _need(calls["default_trainer_calls"] == (reduction == "default") and
          calls["equivariant_trainer_calls"] == (reduction == "suit-equivariant") and calls["rank_calls"] > 0,
          "wrong trainer/rank call count")
    payload = raw["payload"]
    _need(payload.get("chance_contract") == "exact-product-selected-v1" and
          payload.get("conversion_contract") == "exact-product-vectors-binary64-v1" and
          payload.get("training_reduction", "default") == ("suit-equivariant-sorted-chance-binary64-v1" if reduction == "suit-equivariant" else "default") and
          payload.get("pair_diagnostics") == "compact-exact-product-inputs-v1" and
          "private_pair_probabilities" not in payload, "payload contract/reduction mismatch")
    _need(all(type(payload.get(key)) in (int, float) and type(payload.get(key)) is not bool and
              isfinite(payload[key]) for key in METRICS), "payload metrics are missing or nonfinite")
    census = payload.get("operator_census")
    _need(type(census) is dict and census.get("stored_complete_worlds") == 0 and
          census.get("stored_prefix_pair_edges") == 0, "solver retained complete worlds or pair edges")
    admission = census.get("whole_request_admission")
    kernel_stats = census.get("kernel")
    adapter_stats = census.get("float_adapter")
    _need(type(admission) is dict and type(kernel_stats) is dict and type(adapter_stats) is dict,
          "solver omitted whole-request or actual resource receipts")
    kernel_bound = admission["kernel"]["whole_request_upper_work"]
    adapter_bound = admission["adapter"]["whole_request_work_upper"]
    _need(type(kernel_bound) is int and kernel_stats["work_units_cumulative"] <= kernel_bound and
          type(adapter_bound) is int and adapter_stats["modeled_work_entries"] <= adapter_bound and
          admission["combined_modeled_work_upper"] <= admission["whole_request_limit"],
          "actual kernel/adapter or combined work exceeded its admitted upper bound")
    retained = admission["retained_storage"]
    _need(kernel_stats["storage_entries_peak"] <= retained["kernel_peak_upper"] and
          adapter_stats["retained_mapping_entries"] <= retained["adapter_peak_upper"] and
          retained["whole_request_peak_upper"] <= retained["entry_limit"],
          "actual kernel/adapter storage exceeded its admitted upper bound")
    packed_actual = census["packed_layout_actual"]
    packed_upper = census["packed_layout_upper"]
    _need(packed_actual["requested_layout_loop_entries"] <= packed_upper["upper_requested_layout_loop_entries"] and
          packed_actual["action_slots"] <= packed_upper["upper_action_slots"] and
          packed_actual["numeric_buffers"] == 4,
          "actual packed work/action slots exceeded their admitted upper bound")
    if reduction == "suit-equivariant":
        extra = admission["equivariant_additional_admission"]
        layout = census["packed_layout_actual"]["equivariant_additional_admission"]
        _need(extra["modeled_work_upper"] <= extra["whole_request_additional_work_upper"] and
              extra["additional_retained_entries_upper"] <= retained["equivariant_extra_entries_upper"] and
              layout["modeled_work_upper"] <= extra["whole_request_additional_work_upper"] and
              layout["additional_retained_entries_upper"] <= retained["equivariant_extra_entries_upper"],
              "equivariant actual/pre-row work or storage exceeded its whole-request admission")
    dyadic_actual = kernel_stats["integer_arithmetic"]
    dyadic_bound = census["bit_forecast"]["dyadic_integer"]
    _need(dyadic_actual["peak_operand_bits"] <= dyadic_bound["maximum_bits_upper"] and
          dyadic_actual["peak_forecast_bits"] <= dyadic_bound["maximum_bits_upper"] and
          dyadic_actual["peak_integer_payload_bits"] <= dyadic_bound["logical_integer_payload_bits_upper"] and
          dyadic_actual["peak_integer_payload_bits"] <= dyadic_actual["integer_payload_bit_limit"] and
          dyadic_actual["modeled_limb_work_upper"] <= dyadic_bound["whole_request_limb_work_upper"],
          "actual dyadic arithmetic exceeded its admitted bits/payload/work")
    training_calls = census["training"]["calls"]
    _validate_complete_rows(payload, case_for(case_name))
    _need(training_calls == calls["default_trainer_calls"] + calls["equivariant_trainer_calls"] and
          training_calls == 1 and calls["rank_calls"] == kernel_stats["rank_calls"],
          "actual trainer/rank call count differs from solver receipts")


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _validate_complete_rows(payload, case):
    rows = payload.get("strategy")
    _need(type(rows) is list and len(rows) == payload.get("info_sets"), "strategy row count mismatch")
    seen = set()
    for row in rows:
        _need(type(row) is dict and row.get("player") in ("sb", "bb") and
              type(row.get("hand")) is str and type(row.get("history")) is list and
              type(row.get("actions")) is list and row["actions"], "malformed strategy row")
        key = (row["player"], row["hand"], tuple(row["history"]))
        _need(key not in seen, "duplicate complete strategy row")
        seen.add(key)
        _need(all(type(action) is dict and type(action.get("probability")) is float and
                  isfinite(action["probability"]) and 0 <= action["probability"] <= 1
                  for action in row["actions"]), "invalid action probability")
        _need(abs(sum(action["probability"] for action in row["actions"]) - 1.0) <= 1e-12,
              "strategy row does not normalize")
    snapshot = payload.get("chance_input_snapshot", {}).get("ranges")
    _need(type(snapshot) is list and len(snapshot) == 2 and
          [len(side) for side in snapshot] == [len(__import__("pokerlab.cards", fromlist=["expand_range"]).expand_range(case[k]))
                                                   for k in ("sb_range", "bb_range")],
          "compact chance input dimensions mismatch")


def _mapped_key(row):
    swap = {"c": "d", "d": "c", "h": "h", "s": "s"}
    def card(value):
        return value[0] + swap[value[1]]
    history = []
    for token in row["history"]:
        if token.startswith("flop@"):
            flop = [card(token[i:i+2]) for i in (5, 7, 9)]
            flop.sort(key=DECK.index)
            history.append("flop@" + "".join(flop))
        elif token.startswith(("turn@", "river@")):
            history.append(token[:token.index("@") + 1] + card(token[token.index("@") + 1:]))
        else:
            history.append(token)
    holding = "".join(sorted((card(row["hand"][:2]), card(row["hand"][2:]))))
    return row["player"], holding, tuple(history)


def _orbit_check(payload, *, require_equal=False):
    rows = {(row["player"], row["hand"], tuple(row["history"])): row for row in payload["strategy"]}
    diffs = []
    for row in payload["strategy"]:
        partner = rows.get(_mapped_key(row))
        _need(partner is not None, "suit-exchange partner row missing")
        _need([{key: value for key, value in action.items() if key != "probability"} for action in row["actions"]] ==
              [{key: value for key, value in action.items() if key != "probability"} for action in partner["actions"]],
              "suit-exchange legal menu mismatch")
        if require_equal:
            _need([action["probability"].hex() for action in row["actions"]] ==
                  [action["probability"].hex() for action in partner["actions"]],
                  "equivariant policy orbit probabilities differ")
        diffs.append(max(abs(a["probability"] - b["probability"]) for a, b in
                         zip(row["actions"], partner["actions"])))
    return {"orbit_rows_checked": len(diffs), "maximum_probability_difference": max(diffs, default=0.0)}


def _paired_diff(left, right):
    lrows = {(row["player"], row["hand"], tuple(row["history"])): row for row in left["strategy"]}
    rrows = {(row["player"], row["hand"], tuple(row["history"])): row for row in right["strategy"]}
    _need(set(lrows) == set(rrows), "reductions produced different complete row identities")
    row_max = 0.0
    for key in lrows:
        la, ra = lrows[key]["actions"], rrows[key]["actions"]
        _need([{k: v for k, v in x.items() if k != "probability"} for x in la] ==
              [{k: v for k, v in x.items() if k != "probability"} for x in ra], "reduction menu mismatch")
        row_max = max(row_max, *(abs(x["probability"] - y["probability"]) for x, y in zip(la, ra)))
    return {"complete_rows": len(lrows), "maximum_row_probability_difference": row_max,
        "metric_absolute_differences": {key: abs(left[key] - right[key]) for key in METRICS}}


def _verify_payload(case, payload):
    # The independent replay derives physical support and numeric outcomes
    # independently from the request and returned policy.
    replay = replay_policy(payload, case["sb_range"], case["bb_range"], config=case["config"],
        runouts=case["runouts"], flop_config=case["flop_config"],
        turn_config=case["turn_config"], river_config=case["river_config"])
    certificate = evaluate_exact(case, payload)
    replay_metrics = {"value_sb": replay["value_sb"], "value_bb": replay["value_bb"],
        "sb_best_response_value": replay["sb_best_response_value"],
        "bb_best_response_value": replay["bb_best_response_value"],
        "sb_gain": max(0.0, replay["sb_best_response_value"] - replay["value_sb"]),
        "bb_gain": max(0.0, replay["bb_best_response_value"] + replay["value_sb"])}
    replay_metrics["nash_conv"] = replay_metrics["sb_gain"] + replay_metrics["bb_gain"]
    replay_metrics["exploitability"] = replay_metrics["nash_conv"] / 2.0
    gaps = {key: abs(float(payload[key]) - replay_metrics[key]) for key in METRICS}
    _need(replay["checked_information_sets"] == payload["info_sets"],
          "independent numeric replay did not cover every policy row")
    _need(all(isfinite(value) for value in replay_metrics.values()) and
          all(isfinite(value) for value in gaps.values()),
          "independent numeric replay returned nonfinite metrics or gaps")
    return {"numeric_replay": replay, "numeric_replay_metrics": replay_metrics,
        "payload_metric_absolute_differences": gaps,
        "payload_metric_tolerance": REPLAY_TOLERANCE,
        "payload_metrics_within_tolerance": all(value <= REPLAY_TOLERANCE for value in gaps.values()),
        "exact_compact_certificate": certificate}


def _protected_verification(case, payload):
    calls = {"production_solver": 0, "trainer": 0, "kernel_constructor": 0,
        "rank": 0, "pair_query": 0, "world_producer": 0, "native": 0, "popen": 0}
    from pokerlab import exact_selected_solver as solver
    from pokerlab import exact_selected_kernel as kernel_module
    from pokerlab import equivariant_packed_cfr as equivariant_module
    forbidden = (
        ("production_solver", "pokerlab.exact_selected_solver.solve_four_street_exact_selected"),
        ("world_producer", "pokerlab.preflop_solver._enumerate_physical_worlds"),
        ("world_producer", "pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds"),
        ("native", "pokerlab.native_selected_operator.train_native_selected"),
        ("native", "pokerlab.native_selected_dag.train_native_selected_dag"),
        ("native", "pokerlab.native_public_cfr.train_native_public"),
        ("popen", "subprocess.Popen"))
    def reject(counter, label):
        def fail(*_args, **_kwargs):
            calls[counter] += 1
            raise AssertionError("forbidden during independent verification: " + label)
        return fail
    with ExitStack() as stack:
        for counter, target in forbidden:
            stack.enter_context(patch(target, new=reject(counter, target)))
        stack.enter_context(patch.object(solver, "train_packed", new=reject("trainer", "default trainer")))
        stack.enter_context(patch.object(equivariant_module, "train_equivariant_packed",
                                         new=reject("trainer", "equivariant trainer")))
        stack.enter_context(patch.object(kernel_module, "ExactSelectedRunoutKernel",
                                         new=reject("kernel_constructor", "exact kernel constructor")))
        stack.enter_context(patch.object(solver, "ExactSelectedRunoutKernel",
                                         new=reject("kernel_constructor", "solver exact kernel constructor")))
        stack.enter_context(patch.object(kernel_module, "rank_hand", new=reject("rank", "production rank")))
        stack.enter_context(patch.object(ExactSelectedRunoutKernel, "pair_probability_exact",
                                         new=reject("pair_query", "production pair query")))
        result = _verify_payload(case, payload)
    _need(not any(calls.values()), "production path entered during independent verification")
    result["forbidden_production_calls"] = calls
    return result


def _decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _need(key not in result, "duplicate child JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite child JSON token")))


def _label(entry):
    return f"{entry[0]}-{entry[1]}-{entry[2]}"


def run(output):
    output = Path(output).resolve()
    _need(output != ROOT and ROOT not in output.parents and not output.exists(), "Use a new external output directory")
    source = _identity()
    _need(not source["status"], "Commit and clean the complete source closure before the fixed study")
    output.mkdir(parents=True)
    _write(output / "source-before.json", source)
    _write(output / "protocol.json", {"version": "equivariant-selected-cfrplus-fixed-study-v1",
        "source_commit": source["commit"], "source_sha256": source["sha256"],
        "runtime": _runtime(), "schedule": SCHEDULE,
        "cases": {name: _case_snapshot(case_for(name)) for name in ITERATIONS},
        "rank_cache_boards": 64,
        "numeric_replay_metric_tolerance": REPLAY_TOLERANCE,
        "exact_arithmetic": "dyadic", "pair_diagnostics": "compact",
        "retry_policy": "none; preserve raw stdout/stderr and first failure",
        "scope": "Fixed bounded paired comparison of the default CFR+ reduction and a separate suit-equivariant sorted-chance binary64 reference trajectory."})
    samples, certificates, failure = [], {}, None
    for entry in SCHEDULE:
        name, reduction, sample, traced = entry
        label = _label(entry)
        command = [sys.executable, "-B", "-m", "scripts.benchmark_equivariant_selected_solver",
            "--child", name, "--reduction", reduction, "--sample", str(sample), *( ["--traced"] if traced else [])]
        process = None
        try:
            process = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
            (output / (label + ".json")).write_bytes(process.stdout)
            (output / (label + ".stderr.txt")).write_bytes(process.stderr)
            _need(process.returncode == 0, "child exited with status " + str(process.returncode))
            raw = _decode(process.stdout)
            _validate_child(raw, entry)
            samples.append({"artifact": label + ".json", **{k: v for k, v in raw.items() if k != "payload"}})
            if raw["status"] == "complete":
                case = case_for(name)
                _need(_identity() == source,
                      "source closure changed before independent verification")
                verification = _protected_verification(case, raw["payload"])
                _write(output / (label + "-verification.json"), verification)
                _need(verification.get("payload_metrics_within_tolerance") is True,
                      "independent numeric replay metric gap exceeds declared tolerance: " +
                      repr(verification.get("payload_metric_absolute_differences")))
                if reduction == "suit-equivariant" and name == "symmetric":
                    orbit = _orbit_check(raw["payload"], require_equal=True)
                    _write(output / (label + "-orbit.json"), orbit)
                cert = verification["exact_compact_certificate"]
                certificates[label] = {"threshold_met": cert["exact_certificate"]["threshold_met"],
                    "metrics": cert["exact_certificate"]["metrics"],
                    "verification_artifact": label + "-verification.json"}
            print(label, raw["status"], flush=True)
        except Exception as exc:
            failure = {"artifact": label, "type": type(exc).__name__, "message": str(exc),
                "returncode": None if process is None else process.returncode}
            _write(output / (label + "-failure.json"), failure)
            break
    comparisons = {}
    source_after = None
    try:
        source_after = _identity()
        _write(output / "source-after.json", source_after)
        if source_after != source:
            raise ValueError("source closure changed during the paired study")
        if failure is None:
            load = lambda case, reduction, sample: _decode(
                (output / (_label((case, reduction, sample, sample == "traced")) + ".json")).read_bytes())["payload"]
            for case in ("symmetric", "asymmetric", "original-22", "one-world"):
                left, right = load(case, "default", 0), load(case, "suit-equivariant", 0)
                comparisons[case] = _paired_diff(left, right)
            ref_default = load("symmetric", "default", 0)
            comparisons["symmetric"]["default_suit_orbit"] = _orbit_check(ref_default)
            for reduction in ("default", "suit-equivariant"):
                baseline = load("symmetric", reduction, 0)
                checks = [load("symmetric", reduction, index)["strategy"] == baseline["strategy"]
                          for index in (1, 2)]
                checks.append(load("symmetric", reduction, "traced")["strategy"] == baseline["strategy"])
                comparisons["symmetric"][reduction + "_repeat_policies_identical"] = all(checks)
            if not all(comparisons["symmetric"][key] for key in
                       ("default_repeat_policies_identical", "suit-equivariant_repeat_policies_identical")):
                raise ValueError("symmetric repeated policies differ")
    except Exception as exc:
        failure = {"stage": "post-run-comparison-or-source-audit", "type": type(exc).__name__,
                   "message": str(exc), "prior_failure": failure}
        if not (output / "post-run-failure.json").exists():
            _write(output / "post-run-failure.json", failure)
        if not (output / "source-after.json").exists():
            try:
                _write(output / "source-after.json", _identity())
            except Exception:
                _write(output / "source-after.json", None)
    report = {"version": "equivariant-selected-cfrplus-report-v1", "source_commit": source["commit"],
        "runtime": _runtime(), "schedule_planned": len(SCHEDULE), "schedule_attempted": len(samples),
        "samples": samples, "certificates": certificates, "paired_comparisons": comparisons,
        "pretraining_rejection_retained": any(row.get("status") == "pretraining-rejected" for row in samples),
        "finite_iteration_misses_retained": [label for label, row in certificates.items() if not row["threshold_met"]],
        "failure": failure, "scope": "All arithmetic/value differences are descriptive. Exact compact certificates retain bounded oracle caps; no universal accuracy or speed claim."}
    _write(output / "report.json", report)
    manifest = {"source_commit": source["commit"], "sha256": {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.iterdir()) if path.is_file()}}
    _write(output / "manifest.json", manifest)
    digest = hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest()
    return {"outcome": "complete" if failure is None and len(samples) == len(SCHEDULE) else "failed",
        "manifest_sha256": digest, "failure": failure}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", choices=tuple(ITERATIONS))
    parser.add_argument("--reduction", choices=("default", "suit-equivariant"))
    parser.add_argument("--sample", default="0")
    parser.add_argument("--traced", action="store_true")
    args = parser.parse_args()
    if args.child:
        sample = args.sample if args.sample == "traced" else int(args.sample)
        result = child(args.child, args.reduction, sample, args.traced)
    else:
        if args.output is None:
            parser.error("--output is required")
        result = run(args.output)
    print(json.dumps(result, allow_nan=False))
    return 0 if args.child or result["outcome"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
