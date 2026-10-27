"""Source-frozen complete-call study of row and packed CFR+ storage.

Both modes retain the same 64-board rank-cache setting. The schedule is fixed
before children run: T100 three untraced and one traced call per mode, T1000
one untraced call per mode, no retries. Sample-zero policies receive independent
numeric and exact best-response replay; all raw samples are hashed/retained.
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
from scripts.benchmark_selected_operator import ROOT, _identity, _request, _rss, _write, verify_saved


def child(storage, iterations, traced):
    case = json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text())["case"]
    request = _request(case, iterations)
    if traced:
        tracemalloc.start()
    before = time.perf_counter()
    payload = solve_four_street_operator(request, rank_cache_boards=64, strategy_storage=storage)
    seconds = time.perf_counter() - before
    allocation = tracemalloc.get_traced_memory()[1] if traced else None
    if traced:
        tracemalloc.stop()
    return {"strategy_storage": storage, "iterations": iterations, "rank_cache_boards": 64,
            "traced": traced, "seconds": seconds, "python_peak_allocation_bytes": allocation,
            "process_lifetime_peak_working_set_bytes": _rss(), "payload": payload}


def run(output):
    output = output.resolve()
    if output.exists() or output == ROOT or ROOT in output.parents:
        raise ValueError("Use a fresh external output directory.")
    source = _identity()
    if source["status"]:
        raise ValueError("Commit source before the fixed study.")
    output.mkdir(parents=True)
    protocol = {"version": "selected-packed-strategy-comparison-v1", "source_commit": source["commit"],
                "storage_modes": ["rows", "packed"], "rank_cache_boards": 64, "retries": 0,
                "case": "four-street-weighted-shared-future-v1", "target_nash_conv_bb": "1/1000",
                "t100_untraced_samples_per_mode": 3, "t100_traced_samples_per_mode": 1,
                "t1000_untraced_samples_per_mode": 1,
                "scope": "Same selected finite game; excludes full-deck, general memory/speed or storage-complexity claims."}
    _write(output / "protocol.json", protocol)
    summaries = []
    for iterations in (100, 1000):
        cohort = output / f"t{iterations}"
        cohort.mkdir()
        _write(cohort / "source.json", source)
        _write(cohort / "protocol.json", protocol | {"iterations": iterations})
        samples = []
        schedule = [(traced, index, storage) for traced in (False, True)
                    if iterations == 100 or not traced
                    for index in range(1 if traced or iterations == 1000 else 3)
                    for storage in (("rows", "packed") if index % 2 == 0 else ("packed", "rows"))]
        for traced, index, storage in schedule:
            process = subprocess.run([
                sys.executable, "-B", "-m", "scripts.benchmark_packed_operator", "--child", storage,
                "--iterations", str(iterations), *(["--traced"] if traced else [])],
                capture_output=True, text=True, cwd=ROOT, check=True)
            raw = json.loads(process.stdout)
            name = f"{'reference' if storage == 'rows' else 'operator'}-{'traced' if traced else index}.json"
            _write(cohort / name, raw)
            samples.append({k: v for k, v in raw.items() if k != "payload"} | {"artifact": name})
            print(f"T{iterations} {storage} traced={traced} sample={index}: {raw['seconds']:.6f}s", flush=True)
        if _identity() != source:
            raise ValueError("Source changed during fixed measurements; retain partial output.")
        medians = {storage: statistics.median(s["seconds"] for s in samples
                                            if s["strategy_storage"] == storage and not s["traced"])
                   for storage in ("rows", "packed")}
        _write(cohort / "measurements.json", {"samples": samples, "medians_seconds": medians,
                                              "platform": platform.platform(), "python": sys.version})
        _write(cohort / "manifest.json", {"sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(cohort.iterdir()) if p.is_file()}})
        digest = hashlib.sha256((cohort / "manifest.json").read_bytes()).hexdigest()
        audit = verify_saved(cohort, digest)
        a = json.loads((cohort / "reference-0.json").read_text())["payload"]
        b = json.loads((cohort / "operator-0.json").read_text())["payload"]
        if a["strategy"] != b["strategy"] or audit["audits"][0]["exact_metrics"] != audit["audits"][1]["exact_metrics"]:
            raise ValueError("Storage modes differ in complete policy or independent exact metrics.")
        if a["operator_statistics"] != b["operator_statistics"]:
            raise ValueError("Storage modes changed probability/rank work.")
        summaries.append({"iterations": iterations, "manifest_sha256": digest,
                          "medians_seconds": medians, "complete_strategy_rows_identical": True,
                          "independent_exact_metrics_identical": True, "operator_statistics_identical": True,
                          "exact_targets_met": [x["exact_target_met"] for x in audit["audits"]]})
    if _identity() != source:
        raise ValueError("Source changed before study completion.")
    _write(output / "summary.json", {"protocol": protocol, "experiments": summaries})
    print(json.dumps(summaries), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", choices=("rows", "packed"))
    parser.add_argument("--iterations", type=int, choices=(100, 1000))
    parser.add_argument("--traced", action="store_true")
    parser.add_argument("--verify-saved", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args()
    if args.child:
        if args.iterations is None:
            parser.error("--iterations is required")
        print(json.dumps(child(args.child, args.iterations, args.traced), allow_nan=False))
    elif args.verify_saved:
        if not args.expected_manifest_sha256:
            parser.error("--expected-manifest-sha256 is required")
        print(json.dumps(verify_saved(args.verify_saved, args.expected_manifest_sha256)))
    elif args.output:
        run(args.output)
    else:
        parser.error("Choose --output, --child or --verify-saved")


if __name__ == "__main__":
    main()
