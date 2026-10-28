"""Fixed paired Fraction/dyadic study for the exact-product selected solver.

This module prepares a 14-call source-frozen study. It is deliberately not run
by tests. The measured children always request compact diagnostics; independent
small-game certificates run in the parent after raw child output is retained.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from math import comb, isfinite
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from unittest.mock import patch

from pokerlab.exact_selected_solver import solve_four_street_exact_selected
from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions
from scripts.benchmark_selected_operator import ROOT, _identity, _rss, _write
from scripts.exact_selected_compact_certificate import evaluate_exact as compact_exact
from scripts import four_street_validation as physical

MODES = ("fraction", "dyadic")
FORMAT = "compact-exact-product-inputs-v1"
METRICS = ("value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value",
           "sb_gain", "bb_gain", "nash_conv", "exploitability")
EXACT_METRICS = frozenset(("value_sb", "value_bb", "sb_best_response_value",
    "bb_best_response_value", "sb_best_response_gain", "bb_best_response_gain",
    "nash_conv", "exploitability", "lower_value_bound", "upper_value_bound"))
RANK_CACHE_BOARDS = 64
FULL_RANGE = "full-range-forced-all-in"


def _runtime_identity():
    """Portable runtime identity without recording an absolute interpreter path."""
    return {"python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(), "python_sys_version": sys.version,
        "os_system": platform.system(), "os_platform": sys.platform,
        "machine": platform.machine()}


def schedule():
    rows = []
    for sample in range(3):
        order = MODES if sample % 2 == 0 else tuple(reversed(MODES))
        rows.extend(("original", 10, mode, sample, False) for mode in order)
    rows.extend(("original", 10, mode, "traced", True) for mode in MODES)
    rows.extend(("original", 100, mode, 0, False) for mode in MODES)
    rows.extend(("one-world", 1000, mode, 0, False) for mode in MODES)
    rows.append(("original", 1000, "dyadic", "resource-control", False))
    rows.append((FULL_RANGE, 10, "dyadic", 0, False))
    return tuple(rows)


def case_for(name):
    base = json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text(encoding="utf-8"))["case"]
    if name == "original":
        return base
    if name == "one-world":
        return dict(base, id="dyadic-selected-one-world-four-street-v1",
                    sb_range="AsAd", bb_range="KsKd", runouts=["2c3c4d7h8h"])
    if name == FULL_RANGE:
        return dict(base, id="dyadic-selected-full-range-forced-all-in-v1",
                    sb_range="random", bb_range="random", runouts=["2c3d4h5s6c"],
                    config=dict(base["config"], starting_stack=[.5, 1]))
    raise ValueError("Unknown fixed dyadic study case")


def request_for(case, iterations):
    return FourStreetSolveRequest(case["sb_range"], case["bb_range"], tuple(case["runouts"]),
        preflop_config=PreflopConfig.from_dict(case["config"]),
        flop_actions=PostflopActions(**case["flop_config"]),
        turn_actions=None if case.get("turn_config") is None else PostflopActions(**case["turn_config"]),
        river_actions=None if case.get("river_config") is None else PostflopActions(**case["river_config"]),
        iterations=iterations, algorithm="cfrplus", traversal="public-batched",
        diagnostics="public-batched", resource_model="public-vector")


def _admission_error(message):
    return any(token in message.lower() for token in ("admission", "limit", "forecast", "cap", "envelope"))


def child(name, iterations, mode, traced=False):
    if name not in ("original", "one-world", FULL_RANGE) or mode not in MODES or type(traced) is not bool:
        raise ValueError("Unsupported fixed dyadic study child")
    from pokerlab import exact_selected_solver as solver
    from pokerlab import exact_selected_kernel as kernel_module
    calls = {"training_calls": 0, "pair_query_calls": 0, "rank_calls": 0, "native_calls": 0}
    train, rank, pair = solver.train_packed, kernel_module.rank_hand, ExactSelectedRunoutKernel.pair_probability_exact

    def counted_train(*args, **kwargs):
        calls["training_calls"] += 1
        return train(*args, **kwargs)

    def counted_rank(*args, **kwargs):
        calls["rank_calls"] += 1
        return rank(*args, **kwargs)

    def forbidden_pair(*args, **kwargs):
        calls["pair_query_calls"] += 1
        raise AssertionError("Compact dyadic study attempted a private-pair query")

    def forbidden_native(*args, **kwargs):
        calls["native_calls"] += 1
        raise AssertionError("Native or subprocess execution is outside this Python study")

    forbidden = ("pokerlab.preflop_solver._enumerate_physical_worlds",
        "pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds",
        "pokerlab.shared_public_topology.compile_shared_public_topology",
        "pokerlab.preflop_solver._merge_preflop_tree")
    native = ("pokerlab.native_selected_operator.train_native_selected",
        "pokerlab.native_selected_dag.train_native_selected_dag",
        "pokerlab.native_public_cfr.train_native_public", "subprocess.Popen")
    request = request_for(case_for(name), iterations)
    payload = None
    error = None
    status = "complete"
    allocation = None
    seconds = None
    with ExitStack() as stack:
        for target in forbidden:
            stack.enter_context(patch(target, side_effect=AssertionError(target)))
        for target in native:
            stack.enter_context(patch(target, new=forbidden_native))
        stack.enter_context(patch.object(solver, "train_packed", new=counted_train))
        stack.enter_context(patch.object(kernel_module, "rank_hand", new=counted_rank))
        stack.enter_context(patch.object(ExactSelectedRunoutKernel, "pair_probability_exact", new=forbidden_pair))
        if traced:
            tracemalloc.start()
        before = time.perf_counter()
        try:
            try:
                payload = solve_four_street_exact_selected(request, rank_cache_boards=RANK_CACHE_BOARDS,
                    pair_diagnostics="compact", exact_arithmetic=mode)
            except ValueError as exc:
                if not (name == "original" and iterations == 1000 and mode == "dyadic" and
                        not any(calls.values()) and _admission_error(str(exc))):
                    raise
                status = "pretraining-rejected"
                error = {"type": type(exc).__name__, "message": str(exc)}
            seconds = time.perf_counter() - before
            allocation = tracemalloc.get_traced_memory()[1] if traced else None
        finally:
            if traced and tracemalloc.is_tracing():
                tracemalloc.stop()
    return {"case": name, "iterations": iterations, "mode": mode, "pair_diagnostics": "compact",
        "output_format": FORMAT, "traced": traced, "rank_cache_boards": RANK_CACHE_BOARDS,
        "runtime": _runtime_identity(),
        "status": status, "error": error, "seconds": seconds,
        "python_allocation_peak_bytes": allocation, "python_process_peak_bytes": _rss(),
        **calls, "payload": payload}


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _object(pairs):
    output = {}
    for key, value in pairs:
        _need(key not in output, "duplicate child JSON key")
        output[key] = value
    return output


def _decode(raw):
    return json.loads(raw, object_pairs_hook=_object,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite child JSON")))


def _validate_child(raw, name, iterations, mode, traced=False):
    _need(type(raw) is dict, "child result must be an object")
    for key, expected in (("case", name), ("iterations", iterations), ("mode", mode),
            ("pair_diagnostics", "compact"), ("output_format", FORMAT),
            ("traced", traced), ("rank_cache_boards", RANK_CACHE_BOARDS)):
        _need(type(raw.get(key)) is type(expected) and raw[key] == expected, "child request/format metadata mismatch")
    _need(type(raw.get("runtime")) is dict and raw["runtime"] == _runtime_identity(),
          "child Python/OS runtime differs from the study parent")
    _need(type(raw.get("seconds")) in (int, float) and isfinite(raw["seconds"]) and raw["seconds"] > 0,
          "invalid child elapsed time")
    _need((type(raw.get("python_allocation_peak_bytes")) is int and raw["python_allocation_peak_bytes"] > 0)
          if traced else raw.get("python_allocation_peak_bytes") is None, "child trace allocation scope mismatch")
    _need(type(raw.get("python_process_peak_bytes")) is int and raw["python_process_peak_bytes"] > 0,
          "invalid child process peak")
    for key in ("training_calls", "pair_query_calls", "rank_calls", "native_calls"):
        _need(type(raw.get(key)) is int and raw[key] >= 0, "invalid child call counter")
    _need(raw["native_calls"] == raw["pair_query_calls"] == 0, "child entered native or private-pair execution")
    if name == "original" and iterations == 1000 and mode == "dyadic":
        error = raw.get("error")
        _need(raw.get("status") == "pretraining-rejected" and raw.get("payload") is None and
            raw["training_calls"] == raw["rank_calls"] == 0 and type(error) is dict and
            error.get("type") == "ValueError" and type(error.get("message")) is str and
            _admission_error(error["message"]), "original T1000 dyadic request did not reject before work")
        return
    payload = raw.get("payload")
    _need(raw.get("status") == "complete" and raw.get("error") is None and type(payload) is dict,
          "expected completed exact-product child")
    _need(payload.get("chance_contract") == "exact-product-selected-v1" and
          payload.get("conversion_contract") == "exact-product-vectors-binary64-v1" and
          payload.get("execution_backend") == "exact-product-selected-direct-packed-python" and
          payload.get("pair_diagnostics") == FORMAT, "child law/arithmetic/compact contract mismatch")
    _need(type(payload.get("strategy")) is list and type(payload.get("info_sets")) is int and
          payload["info_sets"] == len(payload["strategy"],), "policy row coverage mismatch")
    for key in METRICS:
        _need(type(payload.get(key)) in (int, float) and isfinite(payload[key]), "nonfinite/missing diagnostic")
    census = payload.get("operator_census")
    _need(type(census) is dict and census.get("stored_complete_worlds") == 0 and
          census.get("stored_prefix_pair_edges") == 0, "solver stored complete worlds or pair edges")
    admission = census["whole_request_admission"]
    kernel_stats = census["kernel"]
    _need(kernel_stats["rank_calls"] == raw["rank_calls"] and
          census["training"]["calls"] == raw["training_calls"], "spy counts disagree with solver receipt")
    _need((kernel_stats.get("arithmetic") == "exact-dyadic-integer-buckets-v1" and
           type(kernel_stats.get("integer_arithmetic")) is dict) if mode == "dyadic" else
          "integer_arithmetic" not in kernel_stats, "requested exact arithmetic mode differs from kernel receipt")
    _need(kernel_stats["work_units_cumulative"] <= admission["kernel"]["whole_request_upper_work"] <=
          admission["kernel"]["configured_limit"] == 500_000_000 and
          admission["combined_modeled_work_upper"] <= admission["whole_request_limit"] and
          admission["retained_storage"]["whole_request_peak_upper"] <= admission["retained_storage"]["entry_limit"],
          "actual solver exceeded an admitted work/storage envelope")
    adapter = census["float_adapter"]
    adapter_admission = census["adapter_work_admission"]
    _need(type(adapter.get("modeled_work_entries")) is int and
          adapter["modeled_work_entries"] <= adapter_admission["whole_request_work_upper"] <=
          adapter_admission["configured_work_limit"], "actual adapter work exceeded its admitted envelope")
    pair_output = census["exact_pair_output"]
    _need(raw["pair_query_calls"] == payload.get("pair_runout_preflight_checks") == 0 and
          pair_output["candidate_pairs_scanned"] == pair_output["board_scan_work_upper"] ==
          pair_output["output_entry_upper"] == 0 and pair_output["quadratic_diagnostic_stage"] is False,
          "compact solver exposed or scanned private pairs")
    _need("private_pair_probabilities" not in payload and "compatible_private_pairs" not in payload,
          "compact diagnostics leaked pair-table fields")
    snapshot = payload.get("chance_input_snapshot")
    _need(type(snapshot) is dict and set(snapshot) == {"contract", "ranges"} and
          snapshot["contract"] == "exact-product-selected-v1" and type(snapshot["ranges"]) is list and
          len(snapshot["ranges"]) == 2, "compact chance input snapshot has wrong format")
    range_sizes = [len(side) if type(side) is list else -1 for side in snapshot["ranges"]]
    expected_sizes = [1326, 1326] if name == FULL_RANGE else ([1, 1] if name == "one-world" else [2, 2])
    _need(range_sizes == expected_sizes, "compact snapshot range counts do not match the fixed case")
    for side in snapshot["ranges"]:
        _need(all(type(row) is dict and set(row) == {"hand", "weight_hex"} and
                  type(row["hand"]) is str and len(row["hand"]) == 4 and
                  type(row["weight_hex"]) is str and len(row["weight_hex"]) <= 64
                  for row in side), "malformed compact chance snapshot row")
        _need(len({row["hand"] for row in side}) == len(side), "duplicate holdings in compact chance snapshot")
        for row in side:
            try:
                weight = float.fromhex(row["weight_hex"])
            except (ValueError, OverflowError) as exc:
                raise ValueError("invalid compact binary64 snapshot weight") from exc
            _need(isfinite(weight) and weight > 0 and weight.hex() == row["weight_hex"],
                  "compact snapshot weight is not canonical positive binary64")
    expected_hands = {
        "original": ({"AdAs": float(.5).hex(), "QdQs": float(.25).hex()},
                     {"KdKs": float(.75).hex(), "JdJh": float(.25).hex()}),
        "one-world": ({"AdAs": float(1).hex()}, {"KdKs": float(1).hex()}),
    }
    if name in expected_hands:
        observed = tuple({row["hand"]: row["weight_hex"] for row in side} for side in snapshot["ranges"])
        _need(observed == expected_hands[name], "compact snapshot differs from the fixed original/one-world priors")
    if mode == "dyadic":
        actual = kernel_stats["integer_arithmetic"]
        forecast = census["bit_forecast"]["dyadic_integer"]
        _need(forecast.get("logical_integer_payload_bit_limit") == (1 << 30),
              "dyadic logical integer payload cap changed")
        _need(actual["peak_operand_bits"] <= forecast["maximum_bits_upper"] and
              actual["peak_forecast_bits"] <= forecast["maximum_bits_upper"] and
              actual["peak_integer_payload_bits"] <= forecast["logical_integer_payload_bits_upper"] and
              actual["modeled_limb_work_upper"] <= forecast["whole_request_limb_work_upper"],
              "dyadic actual arithmetic counters exceed the admitted whole-request forecast")
    expected_training = 0 if name == FULL_RANGE else 1
    _need(raw["training_calls"] == expected_training, "unexpected training call count")
    if name == "original":
        _need(payload["worlds"] == 22 and payload["info_sets"] == 1200 and raw["rank_calls"] > 0,
              "original fixture identity mismatch")
    elif name == "one-world":
        _need(payload["worlds"] == 1 and payload["info_sets"] > 0 and raw["rank_calls"] > 0,
              "one-world four-street fixture identity mismatch")
    else:
        expected_worlds = comb(47, 2) * comb(45, 2)
        _need(raw["training_calls"] == 0 and payload["worlds"] == expected_worlds and
              payload["info_sets"] == 0 and payload["strategy"] == [] and raw["rank_calls"] == 2 * comb(47, 2),
              "full-range forced-all-in no-choice anchor mismatch")
        for metric in METRICS:
            _need(abs(payload[metric]) <= 1e-12, "full-range identical-prior value/BR/gain symmetry mismatch")
        deck = tuple(rank + suit for rank in "23456789TJQKA" for suit in "cdhs")
        from itertools import combinations
        hand_universe = {"".join(sorted(hand)) for hand in combinations(deck, 2)}
        for side in snapshot["ranges"]:
            _need({row["hand"] for row in side} == hand_universe and
                  all(row["weight_hex"] == float(1).hex() for row in side),
                  "full-range prior is not the complete uniform 1326-hand witness")


def _canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def _certificate(case, payload):
    wrapper = compact_exact(case, payload)
    exact = wrapper["exact_certificate"]
    _need(wrapper["training_calls"] == wrapper["native_calls"] == wrapper["production_pair_rows"] == 0 and
          wrapper["physical_model_builds"] == 3, "compact certificate call accounting mismatch")
    _need(wrapper["compact_input_canonical_sha256"] == _canonical(payload) and
          wrapper["verification_expansion_canonical_sha256"] == exact["input_policy_canonical_sha256"],
          "compact certificate hash binding mismatch")
    _need(type(exact.get("metrics")) is dict and set(exact["metrics"]) == EXACT_METRICS and
          all(type(value) is str and value for value in exact["metrics"].values()), "certificate metric shape mismatch")
    _need(exact.get("source_identity") == "four-street-independent-exact-v3" and
          exact.get("threshold") == "1/1000" and type(exact.get("threshold_met")) is bool,
          "certificate source or unchanged quality target mismatch")
    digest = exact.get("normalized_policy_sha256")
    _need(type(digest) is str and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest),
          "invalid normalized policy hash")
    return exact, wrapper


def _full_range_certificate_rejection(case, payload):
    builds = []

    def forbidden_build(*args, **kwargs):
        builds.append(1)
        raise AssertionError("Full-range verifier entered its capped physical model")

    with patch.object(physical, "build_model", new=forbidden_build):
        try:
            compact_exact(case, payload)
        except ValueError as exc:
            expected = f"each range must contain at most {physical.MAX_HANDS_PER_PLAYER} hands"
            _need(str(exc) == expected, "full-range compact verifier rejected for an unrelated reason")
            _need(not builds, "full-range certificate entered physical model construction")
            return {"status": "rejected-before-physical-model", "error_type": type(exc).__name__,
                "error": str(exc), "unchanged_hand_cap": physical.MAX_HANDS_PER_PLAYER,
                "physical_model_builds": len(builds), "training_calls": 0, "native_calls": 0,
                "production_pair_rows": 0,
                "scope": "Independent compact certificate is intentionally capped; this rejection is not a solver quality failure."}
        raise ValueError("Full-range compact certificate unexpectedly passed the unchanged small-game cap")


def _structural(payload):
    census = payload["operator_census"]
    admission = census["whole_request_admission"]
    integer = census["kernel"].get("integer_arithmetic")
    return {"kernel_actual_work": census["kernel"]["work_units_cumulative"],
        "kernel_requested_work_upper": admission["kernel"]["whole_request_upper_work"],
        "combined_requested_work_upper": admission["combined_modeled_work_upper"],
        "retained_peak_entries_upper": admission["retained_storage"]["whole_request_peak_upper"],
        "integer_arithmetic": integer,
        "dyadic_forecast": census.get("bit_forecast", {}).get("dyadic_integer"),
        "scope": "Logical modeled work/slots and integer-operation receipts; not CPU or Python memory bytes."}


def run(output):
    output = Path(output).resolve()
    _need(output != ROOT and ROOT not in output.parents and not output.exists(), "Use a new external study directory")
    source = _identity()
    _need(not source["status"], "Commit and clean source before measurement")
    output.mkdir(parents=True)
    protocol = {"version": "exact-product-dyadic-selected-paired-study-v1", "source_commit": source["commit"],
        "source_sha256": source["sha256"], "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runtime": _runtime_identity(),
        "schedule": [{"case": n, "iterations": t, "mode": m, "sample": s, "traced": tr}
                     for n, t, m, s, tr in schedule()], "calls": len(schedule()),
        "pair_diagnostics": "compact", "chance_contract": "exact-product-selected-v1",
        "conversion_contract": "exact-product-vectors-binary64-v1", "retry_policy": "none; preserve first failure",
        "quality": "Exact strategy/metric parity is compared within this explicit law; independent v3 certificates retain threshold misses.",
        "timing_scope": "Complete solver call; request construction and spy setup precede timer. Certificates run outside child timer.",
        "memory_scope": "Traced Python allocation and process-lifetime peak are separate observations, not additive or general RAM claims.",
        "scope": "Bounded 22-world weighted choice game, one-world short-stack control, and full-range one-board forced-all-in zero-choice control; no full-deck choice-solving claim."}
    _write(output / "source-before.json", source)
    _write(output / "protocol.json", protocol)
    records, payloads, certificates = [], {}, {}
    full_range_rejection = None
    failure = None
    for name, iterations, mode, sample, traced in schedule():
        label = f"{name}-T{iterations}-{mode}-{sample}"
        process = None
        try:
            command = [sys.executable, "-B", "-m", "scripts.benchmark_dyadic_selected_solver",
                       "--child", name, "--iterations", str(iterations), "--mode", mode]
            if traced:
                command.append("--traced")
            process = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
            (output / (label + ".json")).write_bytes(process.stdout)
            (output / (label + ".stderr.txt")).write_bytes(process.stderr)
            _need(process.returncode == 0, "child exited with status " + str(process.returncode))
            raw = _decode(process.stdout)
            _validate_child(raw, name, iterations, mode, traced)
            records.append({"artifact": label + ".json", "raw_sha256": hashlib.sha256(process.stdout).hexdigest(),
                "sample": sample, **{k: v for k, v in raw.items() if k != "payload"}})
            print(label, raw["status"], f"{raw['seconds']:.6f}", flush=True)
            if raw["status"] == "complete":
                payloads[(name, iterations, mode, sample, traced)] = raw["payload"]
            if name == FULL_RANGE and raw["status"] == "complete":
                _need(_identity() == source, "source changed before bounded full-range certificate control")
                full_range_rejection = _full_range_certificate_rejection(case_for(name), raw["payload"])
                full_range_rejection.update({"raw_artifact": label + ".json",
                    "raw_sha256": hashlib.sha256(process.stdout).hexdigest(),
                    "solver_counters": {key: raw[key] for key in
                        ("training_calls", "rank_calls", "pair_query_calls", "native_calls")}})
                _write(output / "full-range-compact-certificate-rejection.json", full_range_rejection)
            if sample == 0 and name in ("original", "one-world") and iterations in (10, 100, 1000):
                _need(_identity() == source, "source changed before independent exact certificate")
                exact, wrapper = _certificate(case_for(name), raw["payload"])
                artifact = label + "-certificate.json"
                _write(output / artifact, wrapper)
                certificates[(name, iterations, mode)] = {"artifact": artifact, "metrics": exact["metrics"],
                    "threshold": exact["threshold"], "threshold_met": exact["threshold_met"],
                    "normalized_policy_sha256": exact["normalized_policy_sha256"]}
        except Exception as exc:
            failure = {"artifact": label, "error_type": type(exc).__name__, "error": str(exc),
                       "child_returncode": None if process is None else process.returncode}
            _write(output / (label + "-failure.json"), failure)
            break

    source_after = None
    try:
        source_after = _identity()
        if source_after != source:
            failure = {"stage": "source-changed", "prior_failure": failure}
    except Exception as exc:
        failure = {"stage": "source-identity-failed", "error_type": type(exc).__name__,
                   "error": str(exc), "prior_failure": failure}
    _write(output / "source-after.json", source_after)
    comparisons, checks, structures = [], {}, {}
    if failure is None:
        try:
            pairs = [("original", 10, sample, False) for sample in range(3)] + [
                ("original", 10, "traced", True), ("original", 100, 0, False), ("one-world", 1000, 0, False)]
            for name, iterations, sample, traced in pairs:
                left = payloads[(name, iterations, "fraction", sample, traced)]
                right = payloads[(name, iterations, "dyadic", sample, traced)]
                comparisons.append({"case": name, "iterations": iterations, "sample": sample, "traced": traced,
                    "complete_strategy_identical": left["strategy"] == right["strategy"],
                    "all_eight_metrics_identical": all(left[k] == right[k] for k in METRICS),
                    "same_game_counts": all(left[k] == right[k] for k in ("worlds", "public_states", "decisions", "info_sets"))})
            checks["all_paired_strategies_identical"] = all(row["complete_strategy_identical"] for row in comparisons)
            checks["all_paired_eight_metrics_identical"] = all(row["all_eight_metrics_identical"] for row in comparisons)
            checks["all_paired_game_counts_identical"] = all(row["same_game_counts"] for row in comparisons)
            checks["paired_compact_chance_snapshots_identical"] = all(
                payloads[(name, iterations, "fraction", sample, traced)]["chance_input_snapshot"] ==
                payloads[(name, iterations, "dyadic", sample, traced)]["chance_input_snapshot"]
                for name, iterations, sample, traced in pairs)
            t10_reference = payloads[("original", 10, "fraction", 0, False)]
            checks["all_original_T10_policies_match_sample_zero"] = all(
                payloads[("original", 10, mode, sample, traced)]["strategy"] == t10_reference["strategy"]
                for mode, sample, traced in (("fraction", 0, False), ("dyadic", 0, False),
                    ("fraction", 1, False), ("dyadic", 1, False), ("fraction", 2, False),
                    ("dyadic", 2, False), ("fraction", "traced", True), ("dyadic", "traced", True)))
            checks["all_original_T10_metrics_match_sample_zero"] = all(
                all(payloads[("original", 10, mode, sample, traced)][key] == t10_reference[key] for key in METRICS)
                for mode, sample, traced in (("fraction", 0, False), ("dyadic", 0, False),
                    ("fraction", 1, False), ("dyadic", 1, False), ("fraction", 2, False),
                    ("dyadic", 2, False), ("fraction", "traced", True), ("dyadic", "traced", True)))
            for name, iterations in (("original", 10), ("original", 100), ("one-world", 1000)):
                left, right = (certificates[(name, iterations, mode)] for mode in MODES)
                checks[f"{name}_T{iterations}_certificate_metrics_identical"] = left["metrics"] == right["metrics"]
                checks[f"{name}_T{iterations}_normalized_policy_hash_identical"] = left["normalized_policy_sha256"] == right["normalized_policy_sha256"]
                checks[f"{name}_T{iterations}_threshold_and_flag_identical"] = all(left[k] == right[k] for k in ("threshold", "threshold_met"))
            checks["exact_threshold_flags_recorded"] = all(type(c["threshold_met"]) is bool for c in certificates.values())
            checks["full_range_compact_certificate_rejected_before_physical_model"] = (
                full_range_rejection is not None and full_range_rejection["physical_model_builds"] == 0 and
                full_range_rejection["raw_sha256"] == records[-1]["raw_sha256"])
            for mode in MODES:
                structures[f"original_T10_{mode}"] = _structural(payloads[("original", 10, mode, 0, False)])
            structures["one_world_T1000_dyadic"] = _structural(payloads[("one-world", 1000, "dyadic", 0, False)])
            structures["full_range_dyadic"] = _structural(payloads[(FULL_RANGE, 10, "dyadic", 0, False)])
            _need(all(checks.values()), "paired output or independent-certificate comparison failed")
        except Exception as exc:
            failure = {"stage": "paired-acceptance", "error_type": type(exc).__name__, "error": str(exc)}

    medians = {}
    for mode in MODES:
        times = [r["seconds"] for r in records if r["case"] == "original" and r["iterations"] == 10 and
                 r["mode"] == mode and not r["traced"]]
        medians[mode] = statistics.median(times) if times else None
    report = {"outcome": "complete" if failure is None else "failed", "source_commit": source["commit"],
        "protocol": protocol, "samples": records, "paired_comparisons": comparisons, "checks": checks,
        "failure": failure, "certificates": {"|".join(map(str, key)): value for key, value in certificates.items()},
        "structural_comparison": structures, "medians_original_T10_seconds": medians,
        "complete_child_calls": len(records), "training_calls": sum(r["training_calls"] for r in records),
        "pair_query_calls": sum(r["pair_query_calls"] for r in records), "native_calls": sum(r["native_calls"] for r in records),
        "resource_control": {"case": "original-T1000-dyadic", "sample": "resource-control",
            "status": next((row["status"] for row in records if row["case"] == "original" and
                            row["iterations"] == 1000 and row["mode"] == "dyadic"), "not-established"),
            "raw_artifact": next((row["artifact"] for row in records if row["case"] == "original" and
                                   row["iterations"] == 1000 and row["mode"] == "dyadic"), None),
            "raw_sha256": next((row["raw_sha256"] for row in records if row["case"] == "original" and
                                 row["iterations"] == 1000 and row["mode"] == "dyadic"), None),
            "error": next((row["error"] for row in records if row["case"] == "original" and
                           row["iterations"] == 1000 and row["mode"] == "dyadic"), None),
            "training_calls": next((row["training_calls"] for row in records if row["case"] == "original" and
                                    row["iterations"] == 1000 and row["mode"] == "dyadic"), None),
            "rank_calls": next((row["rank_calls"] for row in records if row["case"] == "original" and
                                row["iterations"] == 1000 and row["mode"] == "dyadic"), None),
            "pair_query_calls": next((row["pair_query_calls"] for row in records if row["case"] == "original" and
                                       row["iterations"] == 1000 and row["mode"] == "dyadic"), None),
            "native_calls": next((row["native_calls"] for row in records if row["case"] == "original" and
                                  row["iterations"] == 1000 and row["mode"] == "dyadic"), None)},
        "full_range_certificate_rejection": full_range_rejection,
        "scope": protocol["scope"], "memory_scope": protocol["memory_scope"]}
    _write(output / "report.json", report)
    _write(output / "manifest.json", {"source_commit": source["commit"],
        "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()}})
    return {"outcome": report["outcome"], "manifest_sha256": hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest(),
            "failure": failure}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", choices=("original", "one-world", FULL_RANGE))
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--traced", action="store_true")
    args = parser.parse_args()
    if args.child:
        if args.iterations is None or args.mode is None:
            parser.error("--iterations and --mode are required for a child")
        result = child(args.child, args.iterations, args.mode, args.traced)
    else:
        if args.output is None:
            parser.error("--output is required for a fixed study")
        result = run(args.output)
    print(json.dumps(result, allow_nan=False))
    return 0 if args.child or result["outcome"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
