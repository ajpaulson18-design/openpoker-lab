"""Profile one frozen weighted preflop/flop-checkdown call without memory tracing."""
from __future__ import annotations
import cProfile, gc, hashlib, json, platform, pstats, re, time
from datetime import datetime, timezone
from pathlib import Path
from scripts.benchmark_preflop_flop_checkdown import verify
from scripts.benchmark_preflop_weighted_range_coverage import (
    _assert_report_pair_posteriors, _independent_pair_audit, _options, _solve_kwargs, _source_paths,
)
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty
from pokerlab import preflop_solver as solver

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "benchmarks/preflop-local-profile-v1.json"
WEIGHTED_SPEC_PATH = ROOT / "benchmarks/preflop-weighted-range-coverage-v1.json"
OUTPUT_PATH = ROOT / "benchmarks/results/preflop-local-profile-v1.json"
SCRIPT_PATH = Path(__file__).resolve()


def safe_filename(filename: str, root: Path) -> str:
    if not filename or filename.startswith("~") or filename.startswith("<"):
        return "builtin"
    normalized = filename.replace("\\", "/")
    try:
        return Path(filename).resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        pass
    lower = normalized.lower()
    for marker in ("/lib/python", "/lib/"):
        pos = lower.find(marker)
        if pos >= 0:
            suffix = normalized[pos + len(marker):]
            return "stdlib/" + suffix.lstrip("/")
    return "external/" + Path(normalized).name


def profile_summary(stats: pstats.Stats, root: Path, top_n: int,
                    materiality_threshold: float) -> dict:
    rows = []
    for (filename, line, name), (primitive, calls, self_time, cumulative, _callers) in stats.stats.items():
        rows.append({"file": safe_filename(filename, root), "line": line, "function": name,
                     "primitive_calls": primitive, "calls": calls,
                     "self_seconds": self_time, "cumulative_seconds": cumulative})
    top_self = sorted(rows, key=lambda row: row["self_seconds"], reverse=True)[:top_n]
    top_cumulative = sorted(rows, key=lambda row: row["cumulative_seconds"], reverse=True)[:top_n]
    owned_self = sum(row["self_seconds"] for row in rows
                     if row["file"] == "pokerlab/preflop_delayed_cfrplus.py")
    keys = ("solve_preflop", "_enumerate_physical_worlds", "_merge_preflop_tree",
            "_legal_private_hands", "group_hidden_futures", "train_delayed_public_cfrplus",
            "accumulate_average", "_cfrplus_target_deltas", "train_public_batched",
            "evaluate_profile", "_evaluate_prepared", "best_response")
    key_records = [row for row in rows if row["function"] in keys]
    return {"total_calls": stats.total_calls, "primitive_calls": stats.prim_calls,
            "profile_total_self_seconds": stats.total_tt,
            "preflop_delayed_cfrplus_exclusive_self_seconds": owned_self,
            "preflop_delayed_cfrplus_share_of_profile_self": owned_self / stats.total_tt if stats.total_tt else 0.0,
            "materiality_threshold": materiality_threshold,
            "threshold_is_diagnostic_only": True,
            "function_records": sorted(rows, key=lambda row: (row["file"], row["line"], row["function"])),
            "top_self_time": top_self, "top_cumulative_time": top_cumulative,
            "key_function_records": key_records}


def source_paths(weighted_paths: tuple[str, ...]) -> tuple[str, ...]:
    extra = ("scripts/benchmark_preflop_weighted_range_coverage.py",
             "scripts/benchmark_preflop_flop_checkdown.py", "scripts/preflop_validation.py",
             "scripts/benchmark_turn_solver.py", "scripts/cfr_quality.py",
             "benchmarks/preflop-weighted-range-coverage-v1.json",
             "benchmarks/results/preflop-weighted-range-coverage-v1.json",
             "scripts/profile_preflop_local_costs.py", "benchmarks/preflop-local-profile-v1.json")
    return tuple(dict.fromkeys((*weighted_paths, *extra)))


def main() -> None:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    if spec.get("weighted_fixture") != WEIGHTED_SPEC_PATH.relative_to(ROOT).as_posix():
        raise ValueError("The declared weighted fixture does not match the profiled input")
    weighted_result_path = ROOT / spec["weighted_result_provenance"]
    expected_weighted_result = ROOT / "benchmarks/results/preflop-weighted-range-coverage-v1.json"
    if weighted_result_path != expected_weighted_result:
        raise ValueError("The declared weighted result provenance does not match the source manifest")
    weighted = json.loads(WEIGHTED_SPEC_PATH.read_text(encoding="utf-8"))
    revision, dirty = git_revision(None), worktree_dirty()
    if dirty is not False or not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise RuntimeError("Freeze merged source and both specifications before profiling")
    paths = source_paths(_source_paths())
    hashes = {path: file_sha256(ROOT / path) for path in paths}
    spec_hash, weighted_hash, script_hash = file_sha256(SPEC_PATH), file_sha256(WEIGHTED_SPEC_PATH), file_sha256(SCRIPT_PATH)
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
           for value in (*hashes.values(), spec_hash, weighted_hash, script_hash)):
        raise RuntimeError("A source/specification hash is unavailable")
    if spec["profile_repeats"] != 1:
        raise ValueError("This harness is fixed to one cProfile run")
    checkpoint = {"iterations": spec["iterations"], "delay": spec["averaging_delay"]}
    options = _options(weighted)
    kwargs = _solve_kwargs(weighted, checkpoint)
    gc.collect()
    profiler = cProfile.Profile(); start = time.perf_counter(); profiler.enable()
    try:
        result = solver.solve_preflop(weighted["sb_range"], weighted["bb_range"], **kwargs)
        serialized = json.dumps(result, allow_nan=False)
    finally:
        profiler.disable()
    profiled_wall = time.perf_counter() - start
    summary = profile_summary(pstats.Stats(profiler), ROOT, spec["top_function_rows"],
                              spec["preflop_local_self_time_share_threshold"])

    oracle_spec = {**weighted, "sb": weighted["sb_range"], "bb": weighted["bb_range"],
                   "expected_worlds": weighted["expected_physical_worlds"],
                   "expected_selected_outcomes": weighted["expected_selected_outcomes"]}
    checked = verify(result, oracle_spec, options)
    posterior = _assert_report_pair_posteriors(result, checked, _independent_pair_audit(weighted))
    gap = checked["configured_replay"]["nash_conv"]
    target_met = gap + weighted["target_padding"] <= weighted["target_nash_conv"]
    after_hashes = {path: file_sha256(ROOT / path) for path in paths}
    if hashes != after_hashes or file_sha256(SPEC_PATH) != spec_hash or file_sha256(WEIGHTED_SPEC_PATH) != weighted_hash or file_sha256(SCRIPT_PATH) != script_hash:
        raise RuntimeError("Source or specification changed during profile")
    if git_revision(None) != revision or worktree_dirty() is not False:
        raise RuntimeError("Frozen worktree changed during profile")
    report = {"schema_version": 1, "python": platform.python_version(), "platform": platform.platform(),
        "benchmark_id": spec["benchmark_id"], "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": revision, "worktree_dirty_at_start": False, "source_hashes": hashes,
        "profile_spec_sha256": spec_hash, "weighted_spec_sha256": weighted_hash,
        "profile_script_sha256": script_hash, "specification": spec,
        "profile_scope": spec["profile_scope"], "profiled_wall_seconds": profiled_wall,
        "serialized_json_bytes": len(serialized.encode("utf-8")), "serialized_json_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "profile": summary, "quality": {"independent_replay": checked,
            "rational_pair_posterior_comparison": posterior, "target_nash_conv": weighted["target_nash_conv"],
            "target_met": target_met},
        "interpretation": "A single instrumented profile locates work; its elapsed time is not a performance benchmark. No memory trace was collected.",
        "model_limits": weighted["model_limits"]}
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    del result, serialized
    print(f"saved {OUTPUT_PATH}; independent gap={gap:.12g}; target={target_met}", flush=True)

if __name__ == "__main__": main()
