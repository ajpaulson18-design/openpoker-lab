"""Frozen same-game complete-call comparison of bounded board-rank caches.

T100 has three untraced samples and a separate traced sample per mode. T1000
has one untraced sample per mode and an independent exact quality gate. Nothing
retries or adjusts iteration budgets after observing results. T100 misses are
retained. Saved-only replay delegates to the independent numeric/exact runner.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc

from pokerlab.selected_operator_solver import solve_four_street_operator
from scripts.benchmark_selected_operator import (
    ROOT, _identity, _request, _rss, _write, verify_saved,
)


def child(capacity, iterations, traced):
    case = json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text())["case"]
    request = _request(case, iterations)
    if traced:
        tracemalloc.start()
    before = time.perf_counter()
    payload = solve_four_street_operator(request, rank_cache_boards=capacity)
    seconds = time.perf_counter() - before
    allocation = tracemalloc.get_traced_memory()[1] if traced else None
    if traced:
        tracemalloc.stop()
    return {"rank_cache_boards": capacity, "iterations": iterations, "traced": traced,
            "seconds": seconds, "python_peak_allocation_bytes": allocation,
            "process_lifetime_peak_working_set_bytes": _rss(), "payload": payload}


def run(output):
    output = output.resolve()
    if output == ROOT or ROOT in output.parents or output.exists():
        raise ValueError("Use a fresh external output directory.")
    source = _identity()
    if source["status"]:
        raise ValueError("Commit all source before measurement.")
    output.mkdir(parents=True)
    protocol = {"version": "selected-rank-cache-comparison-v1",
                "source_commit": source["commit"], "case": "four-street-weighted-shared-future-v1",
                "capacities": [1, 64], "iterations": [100, 1000], "retries": 0,
                "t100_samples_per_mode": 3, "t100_traced_samples_per_mode": 1,
                "t1000_samples_per_mode": 1, "target_nash_conv_bb": "1/1000",
                "scope": "Finite selected game only; tracing/RSS and logical entries remain distinct."}
    _write(output / "protocol.json", protocol)
    summary = []
    for iterations in (100, 1000):
        directory = output / f"t{iterations}"
        directory.mkdir()
        _write(directory / "source.json", source)
        _write(directory / "protocol.json", protocol | {"iterations": iterations})
        samples = []
        # Alternate the first mode across repetitions; keep traced calls separate.
        schedule = [(traced, index, capacity) for traced in (False, True)
                    if iterations == 100 or not traced
                    for index in range(1 if traced or iterations == 1000 else 3)
                    for capacity in ((1, 64) if index % 2 == 0 else (64, 1))]
        for traced, index, capacity in schedule:
            process = subprocess.run([
                sys.executable, "-B", "-m", "scripts.benchmark_selected_rank_cache",
                "--child-capacity", str(capacity), "--iterations", str(iterations),
                *(["--traced"] if traced else []),
            ], capture_output=True, text=True, cwd=ROOT, check=True)
            sample = json.loads(process.stdout)
            name = f"{'reference' if capacity == 1 else 'operator'}-{'traced' if traced else index}.json"
            _write(directory / name, sample)
            samples.append({k: v for k, v in sample.items() if k != "payload"} | {"artifact": name})
            print(f"T{iterations} capacity={capacity} traced={traced} sample={index} seconds={sample['seconds']:.6f}", flush=True)
        if _identity() != source:
            raise ValueError("Source changed during measurements; retain partial output.")
        report = {"samples": samples, "platform": platform.platform(), "python": sys.version,
                  "iterations": iterations, "medians_seconds": {
                      str(cap): statistics.median(s["seconds"] for s in samples
                                                 if s["rank_cache_boards"] == cap and not s["traced"])
                      for cap in (1, 64)}}
        _write(directory / "measurements.json", report)
        manifest = {"sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted(directory.iterdir()) if p.is_file()}}
        _write(directory / "manifest.json", manifest)
        digest = hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest()
        replay = verify_saved(directory, digest)
        a = json.loads((directory / "reference-0.json").read_text())["payload"]
        b = json.loads((directory / "operator-0.json").read_text())["payload"]
        if a["strategy"] != b["strategy"]:
            raise ValueError("Cache capacities produced different complete strategies.")
        metrics_equal = replay["audits"][0]["exact_metrics"] == replay["audits"][1]["exact_metrics"]
        if not metrics_equal:
            raise ValueError("Cache capacities produced different independent exact metrics.")
        summary.append({"iterations": iterations, "manifest_sha256": digest,
                        "medians_seconds": report["medians_seconds"],
                        "complete_strategy_rows_identical": True, "exact_metrics_identical": True,
                        "targets_met": [a["exact_target_met"] for a in replay["audits"]]})
    if _identity() != source:
        raise ValueError("Source changed before experiment completion.")
    _write(output / "summary.json", {"experiments": summary, "protocol": protocol})
    print(json.dumps(summary), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child-capacity", type=int, choices=(1, 64))
    parser.add_argument("--iterations", type=int, choices=(100, 1000))
    parser.add_argument("--traced", action="store_true")
    parser.add_argument("--verify-saved", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args()
    if args.child_capacity:
        if not args.iterations:
            parser.error("--iterations required for child")
        print(json.dumps(child(args.child_capacity, args.iterations, args.traced), allow_nan=False))
    elif args.verify_saved:
        if not args.expected_manifest_sha256:
            parser.error("--expected-manifest-sha256 required")
        print(json.dumps(verify_saved(args.verify_saved, args.expected_manifest_sha256)))
    elif args.output:
        run(args.output)
    else:
        parser.error("Choose --output, --child-capacity or --verify-saved")


if __name__ == "__main__":
    main()
