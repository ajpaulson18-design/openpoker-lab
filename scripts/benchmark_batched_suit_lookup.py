"""Fixed complete-call study of two quotient row-lookup implementations."""
from contextlib import ExitStack
import argparse
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
from scripts.benchmark_suit_quotient_solver import (
    case_for, request_for, _runtime, _protected_verification,
    _policy_metric_certificate_identity, _forbidden,
)
from scripts.benchmark_equivariant_selected_solver import METRICS, _need, _decode

MODES = ("per-row", "per-decision")
SCHEDULE = tuple(("original-22-t10", mode, i, False) for i in range(3)
    for mode in (MODES if i % 2 == 0 else tuple(reversed(MODES)))) + (
    ("original-22-t10", "per-row", "traced", True),
    ("original-22-t10", "per-decision", "traced", True),
    ("payoff-varied-t100", "per-row", 0, False),
    ("payoff-varied-t100", "per-decision", 0, False),
    ("blocker-18", "per-row", 0, False),
    ("blocker-18", "per-decision", 0, False))


def label(entry):
    return "-".join(str(value) for value in entry[:3])


def child(name, mode, sample, traced):
    _need(mode in MODES and name in ("original-22-t10", "payoff-varied-t100", "blocker-18"),
          "Unsupported fixed lookup sample")
    from pokerlab import exact_selected_solver as solver, suit_quotient_cfr as trainer
    from pokerlab import suit_quotient_plan as plan, exact_selected_kernel as kernel
    requested = request_for(case_for(name), 100 if name.endswith("t100") else 10)
    counts = {"trainer": 0, "plan": 0, "rank": 0, "row_route": 0,
              "history_transform": 0, "pair": 0, "world": 0, "native": 0, "popen": 0}
    original_train, original_init, original_rank = trainer.train_suit_quotient, plan.SuitQuotientPlan.__init__, kernel.rank_hand
    original_route, original_history = plan.SuitQuotientPlan._decision_at_history, plan._history
    def count(name, function):
        def counted(*args, **kwargs):
            counts[name] += 1
            return function(*args, **kwargs)
        return counted
    forbidden = (("world", "pokerlab.preflop_solver._enumerate_physical_worlds"),
        ("world", "pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds"),
        ("native", "pokerlab.native_selected_operator.train_native_selected"),
        ("native", "pokerlab.native_selected_dag.train_native_selected_dag"),
        ("native", "pokerlab.native_public_cfr.train_native_public"), ("popen", "subprocess.Popen"))
    with ExitStack() as guards:
        for counter, target in forbidden:
            guards.enter_context(patch(target, new=_forbidden(counter, target, counts)))
        guards.enter_context(patch.object(trainer, "train_suit_quotient", new=count("trainer", original_train)))
        guards.enter_context(patch.object(plan.SuitQuotientPlan, "__init__", new=count("plan", original_init)))
        guards.enter_context(patch.object(kernel, "rank_hand", new=count("rank", original_rank)))
        guards.enter_context(patch.object(plan.SuitQuotientPlan, "_decision_at_history", new=count("row_route", original_route)))
        guards.enter_context(patch.object(plan, "_history", new=count("history_transform", original_history)))
        guards.enter_context(patch.object(kernel.ExactSelectedRunoutKernel, "pair_probability_exact",
            new=_forbidden("pair", "private-pair query", counts)))
        if traced:
            tracemalloc.start()
        start = time.perf_counter()
        try:
            result = solver.solve_four_street_exact_selected(requested, rank_cache_boards=64,
                pair_diagnostics="compact", exact_arithmetic="dyadic",
                training_reduction="suit-equivariant", strategy_storage="suit-quotient", quotient_lookup=mode)
            seconds = time.perf_counter() - start
            allocation = tracemalloc.get_traced_memory()[1] if traced else None
        finally:
            if traced:
                tracemalloc.stop()
    return {"case": name, "lookup": mode, "sample": sample, "traced": traced,
        "runtime": _runtime(), "iterations": requested.iterations, "seconds": seconds,
        "python_allocation_peak_bytes": allocation, "process_peak_bytes": _rss(),
        "counts": counts, "payload": result}


def validate(raw, entry):
    name, mode, sample, traced = entry
    _need(type(raw) is dict and (raw["case"], raw["lookup"], raw["sample"], raw["traced"]) == entry and
          raw["runtime"] == _runtime(), "Sample identity/runtime mismatch")
    _need(type(raw["seconds"]) in (int, float) and 0 < raw["seconds"] < float("inf"), "Invalid elapsed time")
    _need(type(raw["process_peak_bytes"]) is int and raw["process_peak_bytes"] > 0 and
          ((type(raw["python_allocation_peak_bytes"]) is int and raw["python_allocation_peak_bytes"] > 0)
           if traced else raw["python_allocation_peak_bytes"] is None), "Invalid memory observations")
    counts = raw["counts"]
    _need(all(type(value) is int and value >= 0 for value in counts.values()) and
          counts["trainer"] == counts["plan"] == 1 and counts["rank"] > 0 and
          not any(counts[key] for key in ("pair", "world", "native", "popen")), "Forbidden/missing path")
    payload = raw["payload"]
    _need(payload.get("quotient_lookup", "per-row") ==
          ("per-decision-suit-history-transform-v1" if mode == "per-decision" else "per-row"), "Lookup label mismatch")
    _need(payload["strategy_storage"] == "suit-quotient-packed-v1" and
          payload["chance_contract"] == "exact-product-selected-v1" and
          payload["conversion_contract"] == "exact-product-vectors-binary64-v1", "Representation/law mismatch")
    census = payload["operator_census"]; admission = census["whole_request_admission"]
    _need(census["stored_complete_worlds"] == census["stored_prefix_pair_edges"] == 0 and
          admission["combined_modeled_work_upper"] <= admission["whole_request_limit"] and
          admission["retained_storage"]["whole_request_peak_upper"] <= admission["retained_storage"]["entry_limit"] and
          census["kernel"]["work_units_cumulative"] <= admission["kernel"]["whole_request_upper_work"] and
          census["float_adapter"]["modeled_work_entries"] <= admission["adapter"]["whole_request_work_upper"], "Work/storage admission mismatch")
    _need(census["training"]["layout"] == census["packed_layout_actual"] and
          counts["rank"] == census["kernel"]["rank_calls"] and
          census["packed_layout_actual"]["numeric_buffer_bytes"] == 32 * census["suit_quotient_storage"]["quotient_action_slots"],
          "Actual trainer/kernel storage receipt mismatch")


def run(output):
    output = Path(output).resolve()
    _need(output != ROOT and ROOT not in output.parents and not output.exists(), "Use a new external output directory")
    source = _identity()
    _need(not source["status"], "Commit and clean complete source before measurement")
    output.mkdir(parents=True)
    _write(output / "source-before.json", source)
    _write(output / "protocol.json", {"version": "batched-suit-lookup-fixed-study-v1", "source_commit": source["commit"],
        "schedule": SCHEDULE, "runtime": _runtime(), "retry_policy": "none; preserve first failure",
        "cases": {name: case_for(name) for name, *_ in SCHEDULE},
        "scope": "Both modes use Q storage and identical conservative admission. Complete solver timing excludes independent replay and spy installation. Allocation trace and process peak are separate."})
    samples, payloads, verified = [], {}, {}
    failure = None
    comparisons = {}
    for entry in SCHEDULE:
        name, mode, sample, traced = entry
        identifier = label(entry)
        try:
            args = [sys.executable, "-B", "-m", "scripts.benchmark_batched_suit_lookup", "--child", name,
                    "--lookup", mode, "--sample", str(sample)] + (["--traced"] if traced else [])
            process = subprocess.run(args, cwd=ROOT, capture_output=True)
            (output / (identifier + ".json")).write_bytes(process.stdout)
            (output / (identifier + ".stderr.txt")).write_bytes(process.stderr)
            _need(process.returncode == 0, "Child failed: " + str(process.returncode))
            raw = _decode(process.stdout); validate(raw, entry)
            samples.append({"artifact": identifier + ".json", **{key: value for key, value in raw.items() if key != "payload"}})
            _need(_identity() == source, "Source changed before independent replay")
            replay = _protected_verification(case_for(name), raw["payload"])
            _write(output / (identifier + "-verification.json"), replay)
            _need(replay["payload_metrics_within_tolerance"], "Independent replay gap")
            payloads[identifier], verified[identifier] = raw["payload"], replay
            print(identifier, "complete", flush=True)
        except Exception as exc:
            failure = {"sample": identifier, "type": type(exc).__name__, "message": str(exc)}
            _write(output / (identifier + "-failure.json"), failure)
            break
    try:
        if failure is None:
            for name, mode, sample, traced in SCHEDULE:
                if mode != "per-row":
                    continue
                left, right = (label((name, m, sample, traced)) for m in MODES)
                identity = _policy_metric_certificate_identity(payloads[left], payloads[right], verified[left], verified[right])
                _need(payloads[left]["operator_census"]["whole_request_admission"] ==
                      payloads[right]["operator_census"]["whole_request_admission"], "Admission changed across lookup modes")
                comparisons[left + "__vs__" + right] = identity
            for mode in MODES:
                baseline = "original-22-t10-" + mode + "-0"
                for sample in (1, 2, "traced"):
                    other = "original-22-t10-" + mode + "-" + str(sample)
                    _policy_metric_certificate_identity(payloads[baseline], payloads[other], verified[baseline], verified[other])
        after = _identity()
        _write(output / "source-after.json", after)
        _need(after == source, "Source drift after study")
    except Exception as exc:
        failure = {"stage": "post-run", "type": type(exc).__name__, "message": str(exc), "previous": failure}
        _write(output / "post-run-failure.json", failure)
    medians = {mode: statistics.median(row["seconds"] for row in samples if row["case"] == "original-22-t10" and
              row["lookup"] == mode and not row["traced"]) for mode in MODES if any(
              row["case"] == "original-22-t10" and row["lookup"] == mode and not row["traced"] for row in samples)}
    report = {"source_commit": source["commit"], "samples": samples, "comparisons": comparisons,
        "medians_seconds": medians, "failure": failure, "calls_planned": len(SCHEDULE), "calls_completed": len(samples),
        "scope": "Finite fixed games. Same policies, metrics, certificates and conservative admission required. No universal runtime or RAM claim."}
    _write(output / "report.json", report)
    _write(output / "manifest.json", {"source_commit": source["commit"], "sha256": {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(output.iterdir()) if path.is_file()}})
    return {"outcome": "complete" if failure is None and len(samples) == len(SCHEDULE) else "failed", "failure": failure}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", choices=("original-22-t10", "payoff-varied-t100", "blocker-18"))
    parser.add_argument("--lookup", choices=MODES)
    parser.add_argument("--sample", default="0")
    parser.add_argument("--traced", action="store_true")
    args = parser.parse_args()
    if args.child:
        result = child(args.child, args.lookup, args.sample if args.sample == "traced" else int(args.sample), args.traced)
    else:
        if args.output is None:
            parser.error("--output is required")
        result = run(args.output)
    print(json.dumps(result, allow_nan=False))
    return 0 if args.child or result["outcome"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
