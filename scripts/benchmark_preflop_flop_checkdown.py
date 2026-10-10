"""Frozen preflop/flop checkdown quality, complete-call timing and memory."""
import gc
import json
import platform
import re
import statistics
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

from pokerlab.preflop_solver import solve_preflop
from scripts.benchmark_preflop_two_flops import futures
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty
from scripts.preflop_validation import compare_result, replay_policy

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/preflop-flop-checkdown-v1.json"
OUTPUT = ROOT / "benchmarks/results/preflop-flop-checkdown-v1.json"
SOURCES = tuple(sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "pokerlab").glob("*.py"))) + (
    "scripts/benchmark_preflop_flop_checkdown.py", "scripts/preflop_validation.py",
    "scripts/benchmark_preflop_two_flops.py", "scripts/benchmark_turn_solver.py",
    "scripts/cfr_quality.py",
    "tests/test_preflop_delayed_cfrplus.py", "tests/test_preflop_flop_checkdown.py")


def solve(spec, kwargs, checkpoint):
    return solve_preflop(spec["sb"], spec["bb"], **kwargs,
        iterations=checkpoint["iterations"], averaging_delay=checkpoint["delay"],
        algorithm="cfrplus", traversal="public-batched", diagnostics="public-batched",
        resource_model="public-vector")


def verify(result, spec, kwargs):
    oracle = replay_policy(result, spec["sb"], spec["bb"], **kwargs)
    gaps = compare_result(result, oracle)
    assert oracle["checked_information_sets"] == len(result["strategy"])
    assert result["solver_version"] == "preflop-flop-checkdown-v1"
    assert result["postflop_scope"] == "flop-checkdown"
    assert set(result["postflop_action_configs"]) == {"flop"}
    assert result["worlds"] == spec["expected_worlds"]
    assert len(result["selected_runouts"]) == spec["expected_selected_outcomes"]
    assert all(row["street"] in ("preflop", "flop") for row in result["strategy"])
    actual = {(r["sb_hand"], r["bb_hand"]): r["probability"] for r in result["private_pair_probabilities"]}
    expected = {(r["sb"], r["bb"]): r["probability"] for r in oracle["private_pair_probabilities"]}
    assert actual.keys() == expected.keys()
    assert max(abs(actual[k]-expected[k]) for k in actual) < 1e-12
    return {"configured_replay": oracle, "metric_absolute_gaps": gaps,
            "target_nash_conv": spec["target_nash_conv"],
            "target_met": oracle["nash_conv"] + spec["target_padding"] <= spec["target_nash_conv"],
            "vector_work_budget": result["vector_work_budget"],
            "worlds": result["worlds"], "public_states": result["public_states"],
            "decisions": result["decisions"], "information_sets": result["info_sets"],
            "private_pair_probabilities": result["private_pair_probabilities"]}


def main():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    revision, dirty = git_revision(None), worktree_dirty()
    if dirty is not False or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise RuntimeError("Freeze source/spec in a clean commit before measurement.")
    hashes = {p: file_sha256(ROOT / p) for p in SOURCES}
    spec_hash = file_sha256(SPEC)
    if any(not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h) for h in (*hashes.values(), spec_hash)):
        raise RuntimeError("Source/spec hash unavailable.")
    kwargs = {"config": spec["config"], "runouts": futures(spec["flops"]),
              "flop_config": spec["flop_config"], "postflop_scope": spec["postflop_scope"]}
    records = []
    reference_policy = None
    timing_seconds = []
    for checkpoint in spec["checkpoints"]:
        print(f"accuracy {checkpoint}: start", flush=True)
        gc.collect(); start = time.perf_counter()
        result = solve(spec, kwargs, checkpoint)
        json.dumps(result, allow_nan=False)
        elapsed = time.perf_counter()-start
        checked = verify(result, spec, kwargs)
        records.append({**checkpoint, "complete_call_seconds": elapsed, **checked})
        if checkpoint["iterations"] == spec["timing"]["iterations"] and checkpoint["delay"] == spec["timing"]["delay"]:
            reference_policy = json.dumps(result["strategy"], allow_nan=False)
            timing_seconds.append(elapsed)
        print(f"  independent gap={checked['configured_replay']['nash_conv']:.12g}; target={checked['target_met']}; seconds={elapsed:.3f}", flush=True)
        del result
    if reference_policy is None:
        raise RuntimeError("Timing checkpoint must be an accuracy checkpoint.")
    for repeat in range(1, spec["timing"]["repeats"]):
        print(f"complete-call timing repeat {repeat+1}: start", flush=True)
        gc.collect(); start = time.perf_counter()
        result = solve(spec, kwargs, spec["timing"])
        json.dumps(result, allow_nan=False)
        timing_seconds.append(time.perf_counter()-start)
        assert json.dumps(result["strategy"], allow_nan=False) == reference_policy
        del result
    del reference_policy
    print("separate complete-call Python allocation trace: start", flush=True)
    gc.collect(); tracemalloc.start()
    try:
        result = solve(spec, kwargs, spec["memory"])
        json.dumps(result, allow_nan=False)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    memory = {**spec["memory"], "complete_peak_traced_python_bytes": peak, **verify(result, spec, kwargs)}
    del result
    if hashes != {p: file_sha256(ROOT / p) for p in SOURCES} or spec_hash != file_sha256(SPEC):
        raise RuntimeError("Source/spec changed during measurement.")
    if git_revision(None) != revision or worktree_dirty() is not False:
        raise RuntimeError("Revision/worktree changed during measurement.")
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": revision, "worktree_dirty_at_start": False,
        "source_hashes": hashes, "configuration_sha256": spec_hash, "specification": spec,
        "python": platform.python_version(), "platform": platform.platform(),
        "records": records,
        "timing": {**spec["timing"], "complete_call_seconds": timing_seconds,
                   "median_complete_call_seconds": statistics.median(timing_seconds),
                   "repeated_policy_exactly_equal": True},
        "memory": memory,
        "timing_scope": "Three complete90/delay45 calls plus JSON on one host; includes construction, training and exact diagnostics. Preallocated runout arguments, pre-call GC and independent replay excluded. No speedup comparison to a different action model.",
        "memory_scope": "Separate complete10/delay5 call plus JSON under tracemalloc; no other production policy retained. Preallocated runouts, replay, native allocations and RSS excluded. No higher-iteration or whole-process guarantee.",
        "quality_scope": "Every unique accuracy/memory policy independently replayed using numeric poker rules, hidden future world integration and exact visible-information best responses; all checkpoints/misses retained. Exact means enumeration of this configured binary64 game with tolerances, not a floating-point proof.",
        "provenance": "Independently composed this repository's one-street betting builder and existing physical worlds; no third-party source, dependencies or commercial outputs. Luna implements/tests the bounded production mode; lead implements independent replay and freezes/measures the workload. Shared postflop/turn/river kernels and AI Coach are unchanged.",
        "model_limits": spec["model_limits"]}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"saved {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
