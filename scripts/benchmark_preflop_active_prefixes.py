"""Frozen full-call paired experiment for checkdown legal-prefix setup."""
import gc
import hashlib
import json
import platform
import re
import statistics
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from scripts.benchmark_preflop_flop_checkdown import futures, solve, verify, SOURCES
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty
from tests.test_preflop_active_prefixes import _original_legal_private_hands

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/preflop-active-prefixes-v1.json"
OUTPUT = ROOT / "benchmarks/results/preflop-active-prefixes-v1.json"


def original(worlds, postflop_scope="all-streets"):
    return _original_legal_private_hands(worlds)


def complete(game, kwargs, checkpoint, baseline):
    helper = original if baseline else solver._legal_private_hands
    with patch.object(solver, "_legal_private_hands", helper):
        result = solve(game, kwargs, checkpoint)
        serialized = json.dumps(result, allow_nan=False)
    return result, serialized


def main():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    game_path = ROOT / spec["game_spec"]
    game = json.loads(game_path.read_text(encoding="utf-8"))
    revision, dirty = git_revision(None), worktree_dirty()
    if dirty is not False or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise RuntimeError("Freeze source/spec in a clean commit before measurement.")
    paths = tuple(dict.fromkeys((*SOURCES, "scripts/benchmark_preflop_active_prefixes.py",
                 "tests/test_preflop_active_prefixes.py", spec["game_spec"], SPEC.relative_to(ROOT).as_posix())))
    hashes = {p: file_sha256(ROOT / p) for p in paths}
    if any(not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes.values()):
        raise RuntimeError("Source/spec hash unavailable.")
    kwargs = {"config": game["config"], "runouts": futures(game["flops"]),
              "flop_config": game["flop_config"], "postflop_scope": game["postflop_scope"]}
    pairs = []
    for index in range(spec["paired_timing"]["pairs"]):
        order = (True, False) if index % 2 == 0 else (False, True)
        profiles = {}; seconds = {}
        for baseline in order:
            label = "original" if baseline else "optimized"
            print(f"complete-call pair {index+1}: {label} start", flush=True)
            gc.collect(); start = time.perf_counter()
            result, serialized = complete(game, kwargs, spec["paired_timing"], baseline)
            seconds[label] = time.perf_counter()-start
            profiles[label] = serialized
            del result, serialized
        assert profiles["original"] == profiles["optimized"]
        # Verify the exact serialized policy once, after both timing arms.
        # No previous full result remains live during the second timed solve.
        result = json.loads(profiles["optimized"])
        checked = verify(result, game, kwargs)
        pairs.append({"pair": index+1, "order": ["original" if b else "optimized" for b in order],
                      "complete_call_seconds": seconds, "full_serialized_payload_exactly_equal": True,
                      "independent_equal_policy_verification": checked})
        print(f"  {seconds}; exact full-result parity", flush=True)
        del result, profiles
    memory = {}
    for baseline in (True, False):
        label = "original" if baseline else "optimized"
        print(f"separate complete-call allocation trace: {label} start", flush=True)
        gc.collect(); tracemalloc.start()
        try:
            result, serialized = complete(game, kwargs, spec["memory"], baseline)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        memory[label] = {"complete_peak_traced_python_bytes": peak,
                         "full_serialized_payload_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
                         "independent_verification": verify(result, game, kwargs)}
        del result, serialized
    assert memory["original"]["full_serialized_payload_sha256"] == memory["optimized"]["full_serialized_payload_sha256"]
    if hashes != {p: file_sha256(ROOT / p) for p in paths}:
        raise RuntimeError("Source/spec changed during measurement.")
    if git_revision(None) != revision or worktree_dirty() is not False:
        raise RuntimeError("Revision/worktree changed during measurement.")
    medians = {label: statistics.median(pair["complete_call_seconds"][label] for pair in pairs)
               for label in ("original", "optimized")}
    reduction = 1-medians["optimized"]/medians["original"]
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "source_revision": revision,
        "worktree_dirty_at_start": False, "source_hashes": hashes,
        "configuration_sha256": hashes[SPEC.relative_to(ROOT).as_posix()],
        "game_specification_sha256": hashes[spec["game_spec"]],
        "specification": spec, "game_specification": game,
        "python": platform.python_version(), "platform": platform.platform(),
        "paired_timings": pairs, "paired_timing_medians": medians,
        "observed_median_time_reduction": reduction,
        "runtime_gate_met": reduction >= spec["minimum_median_time_reduction"],
        "memory": memory, "memory_full_serialized_payload_exactly_equal": True,
        "timing_scope": "Three alternating pairs of complete90/delay45 solves plus JSON on one host. Includes original enumeration, trees, legal hand sets, training, exact diagnostics and serialization. Preallocated input runouts, pre-call GC and independent replay excluded. Equal fixed-policy workload; no statistical/universal speed or cross-model claim.",
        "memory_scope": "Separate complete10/delay5 calls plus JSON; no other complete policy retained in either trace. Preallocated arguments, replay and digest excluded; native allocations/RSS and higher-iteration bounds excluded. No assumed memory reduction.",
        "quality_scope": "Each equal pair policy and each memory policy independently replayed from numeric rules and exact legal visible-information best responses. Keep the unchanged0.005 target and memory-run misses. Exact full payload includes policy row order, values, diagnostics, physical priors, resource budget and all public counters.",
        "provenance": "Literal former inline legal-prefix loop retained in this repository's own regression tests; checkdown-only cache/active-prefix implementation independently composed from existing code. No third-party source/dependencies, new model, resource guard changes or shared kernel/Coach edits. Luna implements/tests helper; lead reviews/freezes/measures full calls.",
        "model_limits": game["model_limits"]}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(f"saved {OUTPUT}; median reduction={reduction:.3%}; gate={report['runtime_gate_met']}", flush=True)


if __name__ == "__main__":
    main()
