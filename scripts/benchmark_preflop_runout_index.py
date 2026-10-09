"""Measure exact blocker indexing while retaining original preflop admission caps."""
import argparse
from datetime import datetime, timezone
import gc
import hashlib
from itertools import combinations, islice, permutations
import json
from pathlib import Path
import platform
from statistics import median
import time
import tracemalloc
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from pokerlab.preflop_runout_index import RunoutBlockerIndex
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty
from scripts.preflop_validation import compare_result, replay_policy

ROOT = Path(__file__).resolve().parents[1]
SOURCES = tuple("pokerlab/" + name + ".py" for name in (
    "preflop_solver", "preflop_runout_index", "preflop_tree", "preflop_delayed_cfrplus",
    "preflop_vector_budget", "postflop_solver", "public_cfr", "public_diagnostics",
    "ranked_river", "turn_range_kernel", "cards", "cfr", "cfr_plus", "river_tree", "river_config")) + (
    "scripts/benchmark_preflop_runout_index.py", "scripts/preflop_validation.py",
    "scripts/benchmark_turn_solver.py", "tests/test_preflop_runout_index.py",
    "tests/test_preflop_indexed_worlds.py")


class ScalarBlockerIndex:
    """Measurement reference retaining both original disjoint-set blocker scans."""
    def __init__(self, selected):
        self.selected = selected

    def valid_count(self, private_cards):
        blocked = set(private_cards)
        return sum(blocked.isdisjoint(flop + (turn, river))
                   for flop, turn, river in self.selected)

    def iter_valid_indices(self, private_cards):
        blocked = set(private_cards)
        for index, (flop, turn, river) in enumerate(self.selected):
            if blocked.isdisjoint(flop + (turn, river)):
                yield index


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _measure(callback, repeats):
    samples = {"scalar": [], "indexed": []}
    digests = {}
    for repeat in range(repeats):
        order = ("scalar", "indexed") if repeat % 2 == 0 else ("indexed", "scalar")
        for backend in order:
            gc.collect()
            index_type = ScalarBlockerIndex if backend == "scalar" else RunoutBlockerIndex
            with patch.object(solver, "RunoutBlockerIndex", index_type):
                start = time.perf_counter()
                result = callback()
                json.dumps(result)
                samples[backend].append(time.perf_counter() - start)
            digest = _digest(result)
            if backend in digests:
                assert digests[backend] == digest
            digests[backend] = digest
    assert digests["scalar"] == digests["indexed"]
    return {"seconds": samples, "median_seconds": {key: median(rows) for key, rows in samples.items()},
            "identical_result_sha256": digests["indexed"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "benchmarks/preflop-runout-index-v1.json")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/results/preflop-runout-index-v1.json")
    args = parser.parse_args()
    spec = json.loads(args.config.read_text())
    config_hash = file_sha256(args.config)
    hashes = {path: file_sha256(ROOT / path) for path in SOURCES}
    revision, dirty = git_revision(None), worktree_dirty()
    full = spec["complete_fixed_flop"]
    flop = tuple(full["flop"])
    runouts = tuple(flop + future for future in permutations([card for card in solver.DECK if card not in flop], 2))

    def enumerate_full():
        result = solver._enumerate_physical_worlds(full["sb"], full["bb"], runouts, full["iterations"])
        assert len(result[1]) == full["worlds"]
        assert result[2] == 4
        assert result[5] == 4 * 2352
        return result

    print("Complete fixed-flop physical enumeration: alternating paired calls", flush=True)
    full_timing = _measure(enumerate_full, spec["repeats"])
    blocked = spec["blocked_preflight"]
    deck = [card for card in solver.DECK if card not in {"As", "Ad"}]
    bb = ",".join("".join(hand) for hand in islice(combinations(deck, 2), blocked["bb_combinations"]))
    board_deck = [card for card in solver.DECK if card != "As"]
    blocked_runouts = tuple(("As", a, b, c, d) for a, b, c, d in islice(
        combinations(board_deck, 4), blocked["selected_outcomes"]))
    assert len(blocked_runouts) == blocked["selected_outcomes"]
    assert len(solver.expand_range(bb)) == blocked["bb_combinations"]
    assert blocked["logical_pair_runout_checks"] == len(blocked_runouts) * len(solver.expand_range(bb))

    def reject_blocked():
        with patch.object(solver, "rank_hand", side_effect=AssertionError("ranking must not start")):
            try:
                solver._enumerate_physical_worlds(blocked["sb"], bb, blocked_runouts, blocked["iterations"])
            except ValueError as error:
                assert str(error) == blocked["expected_rejection"]
                return {"rejection": str(error)}
        raise AssertionError("all-blocked request unexpectedly admitted")

    print("Exactly 30 million charged checks, no physical worlds: paired preflight rejection", flush=True)
    blocked_timing = _measure(reject_blocked, spec["repeats"])
    canonical = solver._requested_runouts(blocked_runouts)
    gc.collect()
    tracemalloc.start()
    try:
        index = RunoutBlockerIndex(canonical)
        assert index.valid_count(("As", "Ad", "Ks", "Kd")) == 0
        _, peak = tracemalloc.get_traced_memory()
        payload = index.posting_payload_bytes
        conversion_payload = index.estimated_conversion_payload_bytes
    finally:
        tracemalloc.stop()
    index = None
    selected = spec["selected_game"]
    kwargs = {key: selected[key] for key in ("config", "runouts")}
    options = dict(iterations=selected["iterations"], algorithm="cfrplus", averaging_delay=selected["averaging_delay"],
                   traversal="public-batched", diagnostics="public-batched", resource_model="public-vector")
    print("Weighted selected-game complete solve: paired calls and independent legal replay", flush=True)
    game_timing = _measure(lambda: solver.solve_preflop(selected["sb"], selected["bb"], **kwargs, **options), spec["repeats"])
    candidate = solver.solve_preflop(selected["sb"], selected["bb"], **kwargs, **options)
    oracle = replay_policy(candidate, selected["sb"], selected["bb"], **kwargs)
    gaps = compare_result(candidate, oracle)
    assert oracle["checked_information_sets"] == len(candidate["strategy"])
    assert hashes == {path: file_sha256(ROOT / path) for path in SOURCES}
    assert config_hash == file_sha256(args.config)
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"], "generated_at": datetime.now(timezone.utc).isoformat(),
              "source_revision": revision, "worktree_dirty_at_start": dirty, "source_hashes": hashes,
              "configuration_sha256": config_hash, "specification": spec, "python": platform.python_version(), "platform": platform.platform(),
              "timing_scope": "Three complete alternating paired calls per scenario including normalization, ranking when applicable, and JSON serialization; pre-call GC and independent replay excluded. Scalar reference preserves both disjoint-set blocker scans in the same new integration; it is not the complete historical source. Shared-host medians are fixture-specific, not universal speedup claims.",
              "memory_scope": "Separate index construction plus one blocked count under tracemalloc with 100,000 canonical selected outcomes already allocated. Includes helper normalization/duplicate validation, posting construction, conversion and query; excludes solver input normalization, worlds, ranks, tree, training, diagnostics and RSS. Packed payload estimates exclude object headers/int limb padding and normalization copies; traced peak is measured separately.",
              "admission_scope": "All existing caps unchanged. pair_runout_preflight_checks is the original conservative logical admission charge, not the optimized Python disjoint-test count. The 30-million scenario is wholly blocked and rejects before ranking; it is preflight scalability, not a solved game.",
              "complete_fixed_flop_enumeration": full_timing, "blocked_preflight": blocked_timing,
              "index_construction_memory": {"selected_outcomes":len(canonical), "peak_traced_python_bytes":peak,
                                            "logical_posting_payload_bytes":payload, "logical_conversion_overlap_payload_bytes":conversion_payload},
              "weighted_complete_solve": game_timing, "configured_replay": oracle, "metric_absolute_gaps": gaps}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print("All paired results match exactly; independent replay passed", flush=True)


if __name__ == "__main__":
    main()
