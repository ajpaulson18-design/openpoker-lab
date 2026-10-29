"""Frozen whole-call Python/native exact four-street comparison and saved proof."""
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
from scripts.benchmark_suit_quotient_solver import (
    case_for, request_for, _runtime, _protected_verification,
    _policy_metric_certificate_identity, _forbidden,
)
from scripts.benchmark_equivariant_selected_solver import METRICS, _need, _decode

MODES = ("python", "native")
OPTIONS = dict(rank_cache_boards=64, pair_diagnostics="compact", exact_arithmetic="dyadic",
    training_reduction="suit-equivariant", strategy_storage="suit-quotient", quotient_lookup="per-decision")
SCHEDULE = tuple(("original-22-t10", mode, sample, False) for sample in range(3)
    for mode in (MODES if sample % 2 == 0 else tuple(reversed(MODES)))) + (
    ("original-22-t10", "python", "traced", True), ("original-22-t10", "native", "traced", True),
    ("payoff-varied-t100", "python", 0, False), ("payoff-varied-t100", "native", 0, False),
    ("blocker-18", "python", 0, False), ("blocker-18", "native", 0, False),
    ("asymmetric-weighted", "python", 0, False), ("asymmetric-weighted", "native", 0, False),
    ("mixed-stabilizer", "python", 0, False), ("mixed-stabilizer", "native", 0, False),
    ("original-22-qreject", "python", 0, False), ("original-22-qreject", "native", 0, False))

def label(entry):
    return "-".join(map(str, entry[:3]))

def child(name, mode, sample, traced, executable):
    from pokerlab import exact_selected_solver as solver, native_exact_four_street as native
    from pokerlab import suit_quotient_cfr as trainer, exact_selected_kernel as kernel
    _need(mode in MODES and name in {entry[0] for entry in SCHEDULE}, "Unsupported fixed native sample")
    iterations = 1000 if name.endswith("qreject") else 100 if name.endswith("t100") else 10
    request = request_for(case_for(name), iterations)
    counts = {"python_trainer": 0, "native_invoke": 0, "python_rank": 0, "rank_before_native": None,
        "pair": 0, "world": 0, "legacy": 0}
    streams = []
    original_train, original_invoke, original_rank = trainer.train_suit_quotient, native._invoke, kernel.rank_hand
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
    with ExitStack() as guards:
        for counter, target in (("world", "pokerlab.preflop_solver._enumerate_physical_worlds"),
                ("world", "pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds"),
                ("legacy", "pokerlab.native_selected_dag.train_native_selected_dag"),
                ("legacy", "pokerlab.native_selected_operator.train_native_selected"),
                ("legacy", "pokerlab.native_public_cfr.train_native_public"),
                ("pair", "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.pair_probability_exact")):
            guards.enter_context(patch(target, new=_forbidden(counter, target, counts)))
        guards.enter_context(patch.object(trainer, "train_suit_quotient", new=counted_train))
        guards.enter_context(patch.object(native, "_invoke", new=counted_invoke))
        guards.enter_context(patch.object(kernel, "rank_hand", new=counted_rank))
        if traced:
            tracemalloc.start()
        start = time.perf_counter()
        try:
            try:
                payload = solver.solve_four_street_exact_selected(request, **OPTIONS,
                    **({"native_executable": executable} if mode == "native" else {}))
            except Exception as exc:
                failure = {"type": type(exc).__name__, "message": str(exc)}
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
            digest = hashlib.sha256(encoded).hexdigest()
            seconds = time.perf_counter() - start
            allocation = tracemalloc.get_traced_memory()[1] if traced else None
        finally:
            if traced:
                tracemalloc.stop()
    return {"case": name, "mode": mode, "sample": sample, "traced": traced, "runtime": _runtime(),
        "iterations": iterations, "seconds": seconds, "python_allocation_peak_bytes": allocation,
        "process_peak_bytes": _rss(), "counts": counts, "failure": failure, "payload": payload,
        "payload_sha256": digest, "payload_bytes": len(encoded), "native_streams": [
            {key: base64.b64encode(value).decode("ascii") if type(value) is bytes else value
             for key, value in record.items()} for record in streams],
        "scope": "Complete solve plus canonical result serialization/hash. Instrumentation installed outside timing; raw native request/result bytes are retained by the observer through diagnostics. Traced Python peak includes that retention and excludes the native heap; process peak is Python child lifetime. No whole-machine/RSS or universal performance claim."}

def validate(raw, entry):
    name, mode, sample, traced = entry
    _need(type(raw) is dict and (raw["case"], raw["mode"], raw["sample"], raw["traced"]) == entry and
        raw["runtime"] == _runtime(), "Fixed native sample identity/runtime mismatch")
    _need(type(raw["seconds"]) in (int, float) and 0 < raw["seconds"] < float("inf"), "Invalid elapsed time")
    _need(type(raw["process_peak_bytes"]) is int and raw["process_peak_bytes"] > 0 and
        (type(raw["python_allocation_peak_bytes"]) is int and raw["python_allocation_peak_bytes"] > 0
         if traced else raw["python_allocation_peak_bytes"] is None), "Invalid memory observation")
    counts = raw["counts"]
    _need(not any(counts[key] for key in ("pair", "world", "legacy")), "Forbidden legacy/pair/world path")
    payload = raw["payload"]
    if name.endswith("qreject"):
        _need(payload is None and raw["failure"] is not None and raw["failure"]["type"] == "ValueError" and
            not counts["python_trainer"] and not counts["native_invoke"] and not counts["python_rank"],
            "Original T1000 rejection reached ranking or training")
        return
    _need(payload is not None and raw["failure"] is None and counts["python_rank"] > 0 and
        counts["python_trainer"] == int(mode == "python") and counts["native_invoke"] == int(mode == "native"),
        "Missing or extra native/Python training path")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    _need(hashlib.sha256(encoded).hexdigest() == raw["payload_sha256"] and len(encoded) == raw["payload_bytes"], "Payload byte identity changed")
    census = payload["operator_census"]; admission = census["whole_request_admission"]
    _need(census["stored_complete_worlds"] == census["stored_prefix_pair_edges"] == 0 and
        admission["combined_modeled_work_upper"] <= admission["whole_request_limit"] and
        admission["retained_storage"]["whole_request_peak_upper"] <= admission["retained_storage"]["entry_limit"],
        "Whole-solve admitted resources changed")
    if mode == "native":
        _need(counts["rank_before_native"] == 0 and len(raw["native_streams"]) == 1 and
            payload["training_backend"] == "native-exact-four-street-v1", "Native trained after Python ranking or lost stream")
        record = raw["native_streams"][0]; receipt = census["native_exact"]
        request, output, error = (base64.b64decode(record[key], validate=True) for key in ("request", "stdout", "stderr"))
        _need(record["returncode"] == 0 and not error and
            hashlib.sha256(request).hexdigest() == receipt["request_sha256"] and
            hashlib.sha256(output).hexdigest() == receipt["result_sha256"] and
            len(request) == receipt["request_bytes"] and len(output) == receipt["result_bytes"] and
            receipt["rank_calls"] > 0 and receipt["member_checks"] == 2 * raw["iterations"] * payload["info_sets"] and
            receipt["maximum_numeric_workspace_slots"] == 4 * receipt["quotient_action_slots"] and
            receipt["final_numeric_workspace_slots"] == 0, "Native process proof/phase mismatch")
    else:
        _need(not raw["native_streams"] and counts["rank_before_native"] is None, "Python sample invoked native")

def _run_child(command):
    return subprocess.run(command, cwd=ROOT, capture_output=True)

def run(output, executable):
    from pokerlab.native_exact_four_street import executable_identity
    output = Path(output).resolve()
    _need(output != ROOT and ROOT not in output.parents and not output.exists(), "Use a new external native study directory")
    source, build = _identity(), executable_identity(executable)
    _need(not source["status"], "Commit and clean complete native source before measurement")
    output.mkdir(parents=True)
    _write(output / "source-before.json", source)
    _write(output / "protocol.json", {"version": "native-exact-four-street-fixed-study-v1", "source_commit": source["commit"],
        "schedule": SCHEDULE, "runtime": _runtime(), "build": build, "retry_policy": "none; preserve first failure",
        "cases": {name: case_for(name) for name, *_ in SCHEDULE},
        "scope": "Both explicit dyadic/suit-equivariant/Q/per-decision modes keep old guards. Additional native work is charged separately. Complete solve+serialization/hash timing; native compiler excluded. Raw native wire observer extends buffer lifetimes; trace includes those Python bytes and excludes native heap. No universal time/memory claim."})
    samples, payloads, verification, pairs = [], {}, {}, {}
    failure = None
    for entry in SCHEDULE:
        name, mode, sample, traced = entry
        identifier = label(entry)
        try:
            command = [sys.executable, "-B", "-m", "scripts.benchmark_native_exact_four_street", "--child", name,
                "--mode", mode, "--sample", str(sample), "--native-executable", str(executable)] + (["--traced"] if traced else [])
            process = _run_child(command)
            (output / (identifier + ".json")).write_bytes(process.stdout)
            (output / (identifier + ".stderr.txt")).write_bytes(process.stderr)
            _need(process.returncode == 0, "Native study child process failed: " + str(process.returncode))
            raw = _decode(process.stdout); validate(raw, entry)
            samples.append({"artifact": identifier + ".json", **{key: value for key, value in raw.items() if key not in ("payload", "native_streams")}})
            _need(_identity() == source and executable_identity(executable) == build, "Source/build changed before saved replay")
            if raw["payload"] is not None:
                checked = _protected_verification(case_for(name), raw["payload"])
                _write(output / (identifier + "-verification.json"), checked)
                _need(checked["payload_metrics_within_tolerance"], "Independent native policy replay failed")
                payloads[identifier], verification[identifier] = raw["payload"], checked
            print(identifier, "captured and verified", flush=True)
        except Exception as exc:
            failure = {"sample": identifier, "type": type(exc).__name__, "message": str(exc)}
            _write(output / (identifier + "-failure.json"), failure)
            break
    try:
        if failure is None:
            for name, mode, sample, traced in SCHEDULE:
                if mode != "python" or name.endswith("qreject"):
                    continue
                left, right = (label((name, value, sample, traced)) for value in MODES)
                pairs[left + "__vs__" + right] = _policy_metric_certificate_identity(
                    payloads[left], payloads[right], verification[left], verification[right])
            for mode in MODES:
                baseline = "original-22-t10-" + mode + "-0"
                for sample in (1, 2, "traced"):
                    other = "original-22-t10-" + mode + "-" + str(sample)
                    _policy_metric_certificate_identity(payloads[baseline], payloads[other], verification[baseline], verification[other])
        after = _identity(); _write(output / "source-after.json", after)
        _need(after == source and executable_identity(executable) == build, "Native source/build drift after study")
    except Exception as exc:
        failure = {"stage": "post-run", "type": type(exc).__name__, "message": str(exc), "previous": failure}
        _write(output / "post-run-failure.json", failure)
    medians = {mode: statistics.median(row["seconds"] for row in samples if row["case"] == "original-22-t10" and
        row["mode"] == mode and not row["traced"]) for mode in MODES if any(row["case"] == "original-22-t10" and
        row["mode"] == mode and not row["traced"] for row in samples)}
    report = {"source_commit": source["commit"], "samples": samples, "paired_identities": pairs,
        "medians_seconds": medians, "calls_planned": len(SCHEDULE), "calls_completed": len(samples), "failure": failure,
        "scope": "Finite fixed games, conditional selected-runout model. Retain every target miss and original T1000 no-training rejection. Quality and complete-call time/memory remain distinct."}
    _write(output / "report.json", report)
    _write(output / "manifest.json", {"source_commit": source["commit"], "sha256": {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(output.iterdir()) if path.is_file()}})
    return {"outcome": "complete" if failure is None and len(samples) == len(SCHEDULE) else "failed", "failure": failure}

def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--native-executable", type=Path, required=True)
    parser.add_argument("--child", choices=sorted({row[0] for row in SCHEDULE}))
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--sample", default="0")
    parser.add_argument("--traced", action="store_true")
    args = parser.parse_args()
    if args.child:
        result = child(args.child, args.mode, args.sample if args.sample == "traced" else int(args.sample), args.traced, args.native_executable)
    else:
        if args.output is None:
            parser.error("--output is required")
        result = run(args.output, args.native_executable)
    print(json.dumps(result, allow_nan=False))
    return 0 if args.child or result["outcome"] == "complete" else 1

if __name__ == "__main__":
    raise SystemExit(main())
