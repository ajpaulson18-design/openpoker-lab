"""Fresh process profiles; durations are instrumentation, not benchmarks."""
import cProfile
import hashlib
import importlib.util
import json
from pathlib import Path
import pstats
import subprocess
import sys

BASE = Path(__file__).resolve().parent
REPO = BASE / "suit-storage-repo"
OUTPUT = BASE / "quotient-phase-profile-v1"
SOURCE = "3f59676e32878db86a3f01be340c148a45ed3cd4"
AUTH_SHA = "8171ead3ba108f8200f15e85696f40d109ed894209fa7d77598780b83c1401c5"
METRICS = ("value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value",
           "sb_gain", "bb_gain", "nash_conv", "exploitability")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def authenticate():
    path = BASE / "exact-selected-independent-review.py"
    if sha(path) != AUTH_SHA:
        raise ValueError("Source authenticator changed")
    spec = importlib.util.spec_from_file_location("profile_source_auth", path)
    auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(auth)
    auth.FROZEN = SOURCE
    snapshot = json.loads((BASE / "suit-quotient-study-v1/source-before.json").read_text())
    return auth.source_identity(REPO, snapshot)


def child(storage):
    before = authenticate()
    sys.path.insert(0, str(REPO))
    from pokerlab.exact_selected_solver import solve_four_street_exact_selected
    from scripts.benchmark_suit_quotient_solver import case_for, request_for
    request = request_for(case_for("original-22-t10"), 10)
    profiler = cProfile.Profile()
    result = profiler.runcall(solve_four_street_exact_selected, request,
        rank_cache_boards=64, pair_diagnostics="compact", exact_arithmetic="dyadic",
        training_reduction="suit-equivariant", strategy_storage=storage)
    profiler.dump_stats(str(OUTPUT / (storage + ".pstats")))
    raw = json.loads((BASE / f"suit-quotient-study-v1/original-22-t10-{storage}-0.json").read_text())
    if result["strategy"] != raw["payload"]["strategy"] or any(
            float(result[key]).hex() != float(raw["payload"][key]).hex() for key in METRICS):
        raise ValueError("Profiled policy/metrics differ from frozen complete sample")
    (OUTPUT / (storage + "-payload.json")).write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    stats = pstats.Stats(profiler)
    methods = []
    for (filename, line, name), (primitive, calls, own, cumulative, callers) in stats.stats.items():
        methods.append({"file": filename, "line": line, "name": name,
            "primitive_calls": primitive, "calls": calls, "own_seconds": own,
            "cumulative_seconds": cumulative})
    after = authenticate()
    if before != after:
        raise ValueError("Source changed during profile")
    summary = {"storage": storage, "source_commit": SOURCE,
        "source_files_authenticated": before["files"], "full_policy_and_eight_metrics_match_saved": True,
        "profile_total_calls": stats.total_calls, "profile_primitive_calls": stats.prim_calls,
        "profile_total_seconds": stats.total_tt, "methods": methods,
        "top_own": sorted(methods, key=lambda row: row["own_seconds"], reverse=True)[:25],
        "top_cumulative": sorted(methods, key=lambda row: row["cumulative_seconds"], reverse=True)[:25],
        "scope": "One instrumented fresh original-22 T10 full solve. Profiler times are not benchmark measurements or proof of causal speedup; payload is retained."}
    (OUTPUT / (storage + "-profile.json")).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("storage", "profile_total_calls", "profile_total_seconds", "full_policy_and_eight_metrics_match_saved")}))


def main():
    if len(sys.argv) > 1:
        child(sys.argv[1])
        return
    if OUTPUT.exists():
        raise ValueError("Use a new profile evidence directory")
    before = authenticate()
    OUTPUT.mkdir()
    (OUTPUT / "source-authentication.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    records = []
    failure = None
    for storage in ("expanded", "suit-quotient"):
        result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), storage],
            cwd=REPO, capture_output=True)
        (OUTPUT / (storage + ".stdout.txt")).write_bytes(result.stdout)
        (OUTPUT / (storage + ".stderr.txt")).write_bytes(result.stderr)
        records.append({"storage": storage, "exit_code": result.returncode})
        if result.returncode:
            failure = records[-1]
            break
    after = authenticate()
    if after != before:
        failure = {"stage": "source-drift", "previous": failure}
    report = {"source_commit": SOURCE, "helper_sha256": sha(Path(__file__)), "records": records,
        "failure": failure, "scope": "Separate profiling only; never combined with the formal timing samples."}
    (OUTPUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    manifest = {path.name: sha(path) for path in OUTPUT.iterdir() if path.is_file()}
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report))
    if failure:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
