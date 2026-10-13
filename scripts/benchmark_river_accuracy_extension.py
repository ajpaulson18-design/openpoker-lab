"""Evidence-guided CFR+ river accuracy extension; no performance comparison.

The prior 20/100/300 grid chose these existing river fixtures and CFR+ for an
explicit longer-budget extension. All fixed checkpoints/target misses remain.
"""
import argparse
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.benchmark_turn_river_independent import source_hashes, solve, CONFIG
from scripts.turn_river_validation import replay_policy, compare_result

ROOT = Path(__file__).resolve().parents[1]
TARGET = 0.001
CHECKPOINTS = (1000, 3000, 10000)


def hashes():
    result = source_hashes()
    result[str(Path(__file__).relative_to(ROOT))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policies-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    cases = [c for c in json.loads(CONFIG.read_text())["scenarios"] if len(c["board"]) == 10]
    if len(cases) != 2:
        raise ValueError("The frozen extension requires the two existing river fixtures")
    before = hashes()
    rows = []
    args.policies_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        for iterations in CHECKPOINTS:
            for backend in ("materialized", "matrix-free"):
                started = time.perf_counter()
                result = solve(case, backend, "cfrplus", iterations)
                payload = json.dumps(result, sort_keys=True, allow_nan=False)
                seconds = time.perf_counter() - started
                oracle = replay_policy(result, case["oop"], case["ip"],
                                       board=case["board"], config=case["config"])
                delta = compare_result(result, oracle, tolerance=1e-9)
                name = f"{case['id']}-{backend}-{iterations}.json"
                (args.policies_dir / name).write_bytes((payload + "\n").encode("utf-8"))
                metrics = {field: oracle[field] for field in (
                    "value_oop", "value_ip", "oop_best_response_value",
                    "ip_best_response_value", "oop_best_response_gain",
                    "ip_best_response_gain", "nash_conv", "exploitability")}
                rows.append({"scenario": case["id"], "backend": backend,
                             "algorithm": "cfrplus", "iterations": iterations,
                             "metrics": metrics, "scalar_differences": delta,
                             "nash_conv_target": TARGET,
                             "target_met": oracle["nash_conv"] <= TARGET,
                             "verified_worlds": oracle["worlds"],
                             "verified_information_sets": oracle["checked_information_sets"],
                             "complete_call_seconds": seconds,
                             "policy_file": name,
                             "policy_sha256": hashlib.sha256((payload + "\n").encode()).hexdigest()})
                print(case["id"], iterations, backend, f"gap={oracle['nash_conv']:.12g}", flush=True)
    if hashes() != before:
        raise RuntimeError("Source changed during extension; discard the run")
    report = {"schema_version": 1, "benchmark_id": "river-cfrplus-accuracy-extension-v1",
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "python": platform.python_version(), "platform": platform.platform(),
              "source_sha256": before, "fixtures": cases,
              "methodology": {
                  "selection": "Evidence-guided extension from the prior four-fixture grid; CFR+ had the smallest river gaps there. No general best-algorithm claim.",
                  "budget": "Predeclared fixed CFR+ checkpoints 1000/3000/10000 and unchanged 0.001-chip NashConv target; both existing backends, all misses retained.",
                  "accuracy": "Every complete learned policy independently replayed, including exact legal BRs, at1e-9 absolute chip tolerance.",
                  "runtime": "Single complete solve plus deterministic JSON samples on a shared host; no controlled timing, equal-cost comparison, speedup or memory claim.",
                  "scope": "Two synthetic small-range fixed-board finite games; no turn quality, broader ranges, arbitrary sizing, interval proof or commercial parity claim."},
              "results": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
