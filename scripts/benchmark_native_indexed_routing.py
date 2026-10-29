"""Fixed source-frozen native full-history/indexed-routing study.

This is a new evidence runner. It does not modify or replace the earlier native
four-street study. All solve samples use the same native solver and differ only
in the explicitly selected history-routing mode.
"""
from argparse import ArgumentParser
import base64
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import tracemalloc
from unittest.mock import patch

from scripts.benchmark_selected_operator import ROOT, _identity, _rss, _write
from scripts.benchmark_native_exact_four_street import SCHEDULE as PREVIOUS_SCHEDULE
from scripts.benchmark_suit_quotient_solver import (
    case_for, request_for, _runtime, _protected_verification,
    _policy_metric_certificate_identity,
)
from scripts.benchmark_equivariant_selected_solver import (
    METRICS, _need, _decode, _contains_resource_word,
)
from pokerlab.native_exact_four_street import executable_identity

ROUTINGS = ("full-history", "indexed", "shadow")
OPTIONS = dict(rank_cache_boards=64, pair_diagnostics="compact", exact_arithmetic="dyadic",
    training_reduction="suit-equivariant", strategy_storage="suit-quotient",
    quotient_lookup="per-decision")

# Retain the earlier fixed eighteen-call case/replicate order, mapping its
# Python/reference slot to native full-history and native slot to indexed.
_MAPPED_SCHEDULE = tuple((case, "full-history" if prior == "python" else "indexed", sample, traced)
                         for case, prior, sample, traced in PREVIOUS_SCHEDULE)
SCHEDULE = _MAPPED_SCHEDULE + (
    ("original-22-t10", "shadow", "shadow", False),
    ("mixed-stabilizer", "shadow", "shadow", False),
)
ITERATIONS = {name: 1000 if name.endswith("qreject") else 100 if name.endswith("t100") else 10
              for name, *_ in SCHEDULE}


def label(entry):
    case, routing, sample, traced = entry
    return f"{case}-{routing}-{'traced' if traced else sample}"


def _forbidden(counter, target, counts):
    def reject(*_args, **_kwargs):
        counts[counter] += 1
        raise AssertionError("forbidden path entered: " + target)
    return reject


def child(case_name, routing, sample, traced, executable):
    from pokerlab import exact_selected_solver as solver, native_exact_four_street as native
    from pokerlab import suit_quotient_cfr as trainer, exact_selected_kernel as kernel

    _need(routing in ROUTINGS and case_name in ITERATIONS, "Unsupported fixed native routing sample")
    request = request_for(case_for(case_name), ITERATIONS[case_name])
    counts = {"python_trainer": 0, "native_invoke": 0, "python_rank": 0,
        "rank_before_native": None, "pair": 0, "world": 0, "legacy": 0}
    streams = []
    original_train = trainer.train_suit_quotient
    original_invoke = native._invoke
    original_rank = kernel.rank_hand

    def counted_train(*args, **kwargs):
        counts["python_trainer"] += 1
        return original_train(*args, **kwargs)

    def counted_rank(*args, **kwargs):
        counts["python_rank"] += 1
        return original_rank(*args, **kwargs)

    def counted_invoke(path, raw):
        counts["native_invoke"] += 1
        counts["rank_before_native"] = counts["python_rank"]
        record = {"request": raw, "stdout": b"", "stderr": b"", "returncode": None}
        streams.append(record)
        try:
            record["stdout"] = original_invoke(path, raw)
            record["returncode"] = 0
            return record["stdout"]
        except native.NativeFailure as exc:
            record.update(stdout=exc.stdout, stderr=exc.stderr, returncode=exc.returncode)
            raise

    payload = failure = None
    seconds = 0.0
    allocation = None
    encoded = b""
    with ExitStack() as guards:
        for counter, target in (
            ("world", "pokerlab.preflop_solver._enumerate_physical_worlds"),
            ("world", "pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds"),
            ("legacy", "pokerlab.native_selected_dag.train_native_selected_dag"),
            ("legacy", "pokerlab.native_selected_operator.train_native_selected"),
            ("legacy", "pokerlab.native_public_cfr.train_native_public"),
            ("pair", "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.pair_probability_exact"),
        ):
            guards.enter_context(patch(target, new=_forbidden(counter, target, counts)))
        guards.enter_context(patch.object(trainer, "train_suit_quotient", new=counted_train))
        guards.enter_context(patch.object(native, "_invoke", new=counted_invoke))
        guards.enter_context(patch.object(kernel, "rank_hand", new=counted_rank))
        if traced:
            tracemalloc.start()
        start = time.perf_counter()
        try:
            try:
                payload = solver.solve_four_street_exact_selected(request, native_executable=executable,
                    native_routing=routing, **OPTIONS)
            except Exception as exc:
                failure = {"type": type(exc).__name__, "message": str(exc)}
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
            digest = hashlib.sha256(encoded).hexdigest()
            seconds = time.perf_counter() - start
            allocation = tracemalloc.get_traced_memory()[1] if traced else None
        finally:
            if traced:
                tracemalloc.stop()
    return {"case": case_name, "routing": routing, "sample": sample, "traced": traced,
        "runtime": _runtime(), "iterations": ITERATIONS[case_name], "seconds": seconds,
        "python_allocation_peak_bytes": allocation, "process_peak_bytes": _rss(), "counts": counts,
        "failure": failure, "payload": payload, "payload_sha256": digest, "payload_bytes": len(encoded),
        "native_streams": [{key: base64.b64encode(value).decode("ascii") if type(value) is bytes else value
                            for key, value in record.items()} for record in streams],
        "scope": "Complete native solve plus canonical payload serialization/hash. Instrumentation is installed before timing. Traced memory is Python-only and includes retained native wire bytes; native heap is not included. This is a fixed finite-game comparison, not a universal speed or memory claim."}


def _resource_rejection(raw, case_name):
    return (case_name.endswith("qreject") and raw.get("payload") is None and
        type(raw.get("failure")) is dict and raw["failure"].get("type") == "ValueError" and
        _contains_resource_word(raw["failure"].get("message", "")) and
        not any(raw["counts"].get(key) for key in ("python_trainer", "native_invoke", "python_rank")))


def validate(raw, expected):
    case_name, routing, sample, traced = expected
    _need(type(raw) is dict and (raw.get("case"), raw.get("routing"), raw.get("sample"), raw.get("traced")) == expected and
        raw.get("runtime") == _runtime() and raw.get("iterations") == ITERATIONS[case_name],
        "Native indexed child identity/runtime mismatch")
    _need(type(raw.get("seconds")) in (int, float) and raw["seconds"] > 0 and raw["seconds"] < float("inf") and
        type(raw.get("process_peak_bytes")) is int and raw["process_peak_bytes"] > 0 and
        ((type(raw.get("python_allocation_peak_bytes")) is int and raw["python_allocation_peak_bytes"] > 0)
         if traced else raw.get("python_allocation_peak_bytes") is None), "Invalid timing or memory observation")
    calls = raw.get("counts")
    keys = {"python_trainer", "native_invoke", "python_rank", "rank_before_native", "pair", "world", "legacy"}
    _need(type(calls) is dict and set(calls) == keys and all(type(calls[key]) is int and calls[key] >= 0
        for key in keys - {"rank_before_native"}) and calls["rank_before_native"] in (None, 0) and
        not any(calls[key] for key in ("pair", "world", "legacy", "python_trainer")),
        "Forbidden or malformed Python training path counters")
    if _resource_rejection(raw, case_name):
        _need(raw["failure"]["message"] and not raw["native_streams"],
              "T1000 rejection launched native training")
        return
    _need(raw.get("failure") is None and type(raw.get("payload")) is dict and
        calls["native_invoke"] == 1 and calls["python_rank"] > 0 and calls["rank_before_native"] == 0 and
        len(raw.get("native_streams", ())) == 1,
        "Native training/rank ordering or Python diagnostic rank calls differ")
    payload = raw["payload"]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    _need(hashlib.sha256(encoded).hexdigest() == raw.get("payload_sha256") and
        len(encoded) == raw.get("payload_bytes"), "Canonical complete-payload hash differs")
    _need(payload.get("chance_contract") == "exact-product-selected-v1" and
        payload.get("conversion_contract") == "exact-product-vectors-binary64-v1" and
        payload.get("training_reduction") == "suit-equivariant-sorted-chance-binary64-v1" and
        payload.get("pair_diagnostics") == "compact-exact-product-inputs-v1" and
        "private_pair_probabilities" not in payload and
        payload.get("training_backend") == ("native-exact-four-street-v1" if routing == "full-history"
            else "native-exact-four-street-routed-v2") and
        (payload.get("native_routing") == routing if routing != "full-history" else "native_routing" not in payload),
        "Native backend, law, or routing marker differs")
    _need(all(type(payload.get(key)) in (int, float) and type(payload[key]) is not bool and
        payload[key] == payload[key] and abs(payload[key]) < float("inf") for key in METRICS),
        "Payload metrics are missing or nonfinite")
    census = payload.get("operator_census")
    _need(type(census) is dict and census.get("stored_complete_worlds") == 0 and
        census.get("stored_prefix_pair_edges") == 0 and type(census.get("native_exact")) is dict,
        "Missing native exact census or stored world/pair-edge state")
    receipt = census["native_exact"]
    _need(receipt.get("calls") == 1 and receipt.get("rank_calls", 0) > 0 and
        receipt.get("member_checks") == 2 * raw["iterations"] * payload.get("info_sets", -1) and
        receipt.get("maximum_numeric_workspace_slots") == 4 * receipt.get("quotient_action_slots", -1) and
        receipt.get("final_numeric_workspace_slots") == 0 and
        receipt.get("modeled_work_upper", 500_000_001) <= 500_000_000 and
        receipt.get("retained_entries_upper", 25_000_001) <= 25_000_000,
        "Native counters/resource receipt failed")
    if routing == "full-history":
        _need("indexed_routing" not in receipt, "Full-history result unexpectedly carries routing receipt")
    else:
        routed = receipt.get("indexed_routing")
        direct = census.get("direct_topology")
        _need(type(direct) is dict, "Missing direct topology census for independent route-count validation")
        visits = direct.get("expanded_logical_visits")
        decisions = direct.get("decision_occurrences")
        terminals = direct.get("terminal_occurrences")
        iterations = raw["iterations"]
        _need(all(type(value) is int and value > 0 for value in (visits, decisions, terminals)) and
            type(routed) is dict and
            routed.get("roots") == routed.get("roots_upper") == 3 * iterations and
            routed.get("edges") == routed.get("edges_upper") == 3 * iterations * (visits - 1) and
            routed.get("decisions") == routed.get("decisions_upper") == 3 * iterations * decisions and
            routed.get("prefixes") == routed.get("prefixes_upper") == iterations * (2 * terminals + decisions),
            "Router actual calls differ from the independently checked direct census")
        _need(type(routed) is dict and routed.get("mode") == routing and routed.get("r_lookup_entries") == 0 and
            routed.get("old_q_histories_retained") == 1 and routed.get("final_router_entries") == 0 and
            routed.get("map_entries") == routed.get("map_upper") == routed.get("q_rows") and
            routed.get("combined_work") == receipt["modeled_work_upper"] and
            routed.get("combined_entries") == receipt["retained_entries_upper"],
            "Indexed routing proof omitted bounded map or whole-owner receipt")
        expected_shadow = routing == "shadow"
        _need(routed.get("q_routes") == routed.get("q_routes_upper") == routed.get("q_rows") and
            routed.get("q_tokens") == routed.get("q_tokens_upper") and
            all(type(routed.get(name)) is int and 0 <= routed[name] <= routed[name + "_upper"]
                for name in ("router_work", "index_work", "index_entries", "router_retained")) and
            routed.get("legacy_extensions") == (routed.get("edges") if expected_shadow else 0) and
            routed.get("legacy_rows") == (routed.get("decisions") if expected_shadow else 0) and
            routed.get("legacy_prefixes") == (routed.get("prefixes") if expected_shadow else 0) and
            routed.get("decision_comparisons") == (routed.get("decisions") if expected_shadow else 0) and
            routed.get("prefix_comparisons") == (routed.get("prefixes") if expected_shadow else 0),
            "Indexed routing hot-path legacy-call/comparison proof differs")
    record = raw["native_streams"][0]
    request, output, error = (base64.b64decode(record[key], validate=True)
                              for key in ("request", "stdout", "stderr"))
    _need(record.get("returncode") == 0 and not error and len(request) == receipt["request_bytes"] and
        len(output) == receipt["result_bytes"] and hashlib.sha256(request).hexdigest() == receipt["request_sha256"] and
        hashlib.sha256(output).hexdigest() == receipt["result_sha256"],
        "Raw native request/result stream differs from its receipt")


def _run_child(command):
    return subprocess.run(command, cwd=ROOT, capture_output=True, check=False)


def _verify_pair(left, right, left_verification, right_verification):
    identity = _policy_metric_certificate_identity(left, right, left_verification, right_verification)
    _need(all(type(left.get(key)) in (int, float) and type(right.get(key)) in (int, float) and
        float(left[key]).hex() == float(right[key]).hex() for key in METRICS),
        "Paired reported metric binary64 values differ")
    return {**identity, "left_routing": left.get("native_routing", "full-history"),
        "right_routing": right.get("native_routing", "full-history"),
        "metric_binary64_identical": True}


def run(output, executable):
    output = Path(output).resolve()
    _need(output != ROOT and ROOT not in output.parents and not output.exists(),
          "Use a new external indexed-routing study directory")
    source = _identity()
    build = executable_identity(executable)
    _need(not source["status"], "Commit and clean the complete native source closure before the fixed study")
    output.mkdir(parents=True)
    _write(output / "source-before.json", source)
    _write(output / "build-before.json", build)
    _write(output / "protocol.json", {"version": "native-exact-indexed-routing-fixed-study-v1",
        "source_commit": source["commit"], "source_sha256": source["sha256"], "build": build,
        "runtime": _runtime(), "schedule": SCHEDULE, "cases": {name: case_for(name) for name, *_ in SCHEDULE},
        "iterations": ITERATIONS, "options": OPTIONS, "retry_policy": "none; preserve first stdout/stderr and error",
        "scope": "All solve calls use native exact training. The mapped legacy schedule compares full-history to indexed routing; two additional bounded shadow calls compare legacy behavior while the old path still runs. Pretraining T1000 rejection and finite-game certificate status remain outcomes, not success assumptions. Python traced allocation excludes native heap; no universal time or memory claim."})
    samples, payloads, verifications, pairs = [], {}, {}, {}
    failure = None
    for entry in SCHEDULE:
        case_name, routing, sample, traced = entry
        identifier = label(entry)
        try:
            command = [sys.executable, "-B", "-m", "scripts.benchmark_native_indexed_routing",
                "--child", case_name, "--routing", routing, "--sample", str(sample),
                "--native-executable", str(executable)] + (["--traced"] if traced else [])
            process = _run_child(command)
            (output / (identifier + ".stdout.bin")).write_bytes(process.stdout)
            (output / (identifier + ".stderr.bin")).write_bytes(process.stderr)
            _need(process.returncode == 0, "Native indexed study child process failed: " + str(process.returncode))
            raw = _decode(process.stdout)
            validate(raw, entry)
            samples.append({"artifact": identifier + ".stdout.bin", **{
                key: value for key, value in raw.items() if key not in ("payload", "native_streams")}})
            if raw["payload"] is not None:
                _need(_identity() == source and executable_identity(executable) == build,
                      "Source/build changed before protected verification")
                checked = _protected_verification(case_for(case_name), raw["payload"])
                _write(output / (identifier + "-verification.json"), checked)
                _need(checked["payload_metrics_within_tolerance"], "Independent native policy replay failed")
                payloads[identifier], verifications[identifier] = raw["payload"], checked
            print(identifier, "captured and verified", flush=True)
        except Exception as exc:
            failure = {"sample": identifier, "type": type(exc).__name__, "message": str(exc)}
            _write(output / (identifier + "-failure.json"), failure)
            break
    try:
        if failure is None:
            for case_name, routing, sample, traced in SCHEDULE:
                if case_name.endswith("qreject"):
                    continue
                if routing == "full-history":
                    other_routing = "indexed"
                elif routing == "indexed":
                    other_routing = "full-history"
                else:
                    other_routing = "full-history"
                    sample = 0
                if routing == "shadow":
                    left = label((case_name, "full-history", 0, False))
                    right = label((case_name, "shadow", "shadow", False))
                elif routing == "full-history":
                    left = label((case_name, routing, sample, traced))
                    right = label((case_name, other_routing, sample, traced))
                else:
                    continue
                pairs[left + "__vs__" + right] = _verify_pair(
                    payloads[left], payloads[right], verifications[left], verifications[right])
        after = _identity()
        _write(output / "source-after.json", after)
        build_after = executable_identity(executable)
        _write(output / "build-after.json", build_after)
        _need(after == source and build_after == build, "Native source/build drift after indexed routing study")
    except Exception as exc:
        failure = {"stage": "post-run", "type": type(exc).__name__, "message": str(exc), "previous": failure}
        _write(output / "post-run-failure.json", failure)
    medians = {routing: statistics.median(row["seconds"] for row in samples
        if row["case"] == "original-22-t10" and row["routing"] == routing and not row["traced"])
        for routing in ("full-history", "indexed") if any(row["case"] == "original-22-t10" and
            row["routing"] == routing and not row["traced"] for row in samples)}
    report = {"source_commit": source["commit"], "samples": samples, "paired_identities": pairs,
        "calls_planned": len(SCHEDULE), "calls_completed": len(samples), "medians_seconds": medians,
        "failure": failure, "quality_misses_retained": [key for key, value in verifications.items()
            if not value["exact_compact_certificate"]["exact_certificate"]["threshold_met"]],
        "scope": "Fixed finite four-street selected-runout games. Every quality miss and the original T1000 pretraining rejection is retained. Timing includes complete API output serialization and hash; Python and native memory scopes remain distinct."}
    _write(output / "report.json", report)
    _write(output / "manifest.json", {"source_commit": source["commit"], "sha256": {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.iterdir()) if path.is_file()}})
    return {"outcome": "complete" if failure is None and len(samples) == len(SCHEDULE) else "failed",
        "failure": failure}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--native-executable", type=Path, required=True)
    parser.add_argument("--child", choices=sorted({row[0] for row in SCHEDULE}))
    parser.add_argument("--routing", choices=ROUTINGS)
    parser.add_argument("--sample", default="0")
    parser.add_argument("--traced", action="store_true")
    args = parser.parse_args()
    if args.child:
        sample = args.sample if args.sample == "traced" or args.sample == "shadow" else int(args.sample)
        result = child(args.child, args.routing, sample, args.traced, args.native_executable)
    else:
        if args.output is None:
            parser.error("--output is required")
        result = run(args.output, args.native_executable)
    print(json.dumps(result, allow_nan=False))
    return 0 if args.child or result["outcome"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
