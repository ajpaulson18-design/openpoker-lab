"""Measure finite preflop trees and replay their edges with rational chip rules.

This records betting-tree coverage, not strategy convergence or equity.
The independent replay never calls production betting/sizing helpers.
"""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import json
from pathlib import Path
import platform
import statistics
import time
import tracemalloc

from pokerlab.preflop_tree import PreflopConfig, PreflopContinuation, build_preflop_tree
from pokerlab.river_tree import _Node, _Terminal
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("pokerlab/preflop_tree.py", "pokerlab/river_tree.py",
           "pokerlab/analysis.py", "scripts/benchmark_preflop_tree.py",
           "scripts/benchmark_turn_solver.py")


def _q(value):
    return Fraction(str(value))


def audit_tree(tree):
    """Exhaustively replay one finite tree from independent blind/chip rules."""
    config = tree.config
    stacks = tuple(map(_q, config.stacks))
    blinds = (_q(config.small_blind), _q(config.big_blind))
    posted = tuple(min(stack, blind) for stack, blind in zip(stacks, blinds))
    counts = {"decision": 0, "fold": 0, "continuation": 0, "actions": 0}
    pending = [(tree.root, 0, posted, blinds[1], 0, True, False)]
    while pending:
        node, player, contributions, increment, raises, reopened, bb_option = pending.pop()
        other = 1 - player
        if isinstance(node, PreflopContinuation):
            counts["continuation"] += 1
            assert not bb_option, "A limp must preserve the BB decision"
            assert (contributions[0] == contributions[1] or
                    contributions[player] >= stacks[player] or
                    (contributions[other] >= stacks[other] and
                     contributions[player] >= contributions[other])), "Unresolved betting"
            matched = min(contributions)
            expected = {
                "matched_contributions": (matched, matched),
                "refunds": tuple(value - matched for value in contributions),
                "remaining_stacks": tuple(stack - matched for stack in stacks),
                "pot": 2 * matched,
            }
            for key, value in expected.items():
                actual = getattr(node, key)
                if isinstance(value, tuple):
                    assert len(actual) == len(value)
                    assert all(abs(float(a) - float(b)) < 1e-8 for a, b in zip(actual, value)), key
                else:
                    assert abs(actual - float(value)) < 1e-8, key
            all_in = tuple(matched >= stack for stack in stacks)
            assert node.all_in == all_in
            assert node.next_player == (None if any(all_in) else 1)
            assert node.street == ("showdown" if any(all_in) else "flop")
            continue
        if isinstance(node, _Terminal):
            counts["fold"] += 1
            assert node.kind == "fold"
            assert tuple(map(_q, node.contributions)) == contributions
            assert node.winner == other
            assert contributions[player] < contributions[other]
            continue
        assert isinstance(node, _Node)
        assert node.player == player
        assert contributions[player] < stacks[player]
        assert not (contributions[other] >= stacks[other] and
                    contributions[player] >= contributions[other])
        counts["decision"] += 1
        counts["actions"] += len(node.actions)
        owed = max(Fraction(0), contributions[other] - contributions[player])
        expected_names = ["fold", "call"] if owed else ["check"]
        expected_targets = []
        if reopened and raises < config.max_raises and contributions[other] < stacks[other]:
            for fraction in config.raise_sizes:
                target = min(stacks[player], max(contributions[other] + increment,
                             contributions[other] + _q(fraction) * 2 * contributions[other]))
                if target > contributions[other] and target not in expected_targets:
                    expected_targets.append(target)
            if config.include_all_in and stacks[player] > contributions[other] and stacks[player] not in expected_targets:
                expected_targets.append(stacks[player])
        expected_targets.sort()
        assert len(node.actions) == len(expected_names) + len(expected_targets)
        assert [action.name for action in node.actions[:len(expected_names)]] == expected_names
        assert len({action.token for action in node.actions}) == len(node.actions)
        for action, child in zip(node.actions, node.children):
            assert len(node.children) == len(node.actions)
            if action.name == "fold":
                pending.append((child, player, contributions, increment, raises, reopened, False))
                continue
            if action.name in ("check", "call"):
                paid = min(owed, stacks[player] - contributions[player])
                if action.name == "check":
                    assert paid == 0 and bb_option
                else:
                    assert abs(action.amount - float(paid)) < 1e-8
                    assert abs(action.raise_to - float(contributions[player] + paid)) < 1e-8
                updated = list(contributions)
                updated[player] += paid
                # Only the initial SB completion leaves BB an option, and only
                # while both players retain chips. A voluntary-raise call ends it.
                option = (player == 0 and raises == 0 and
                          all(value < stack for value, stack in zip(updated, stacks)))
                next_player = other if option else player
                pending.append((child, next_player, tuple(updated), increment,
                                raises, reopened, option))
                continue
            target = expected_targets.pop(0)
            assert abs(action.raise_to - float(target)) < 1e-8
            assert abs(action.amount - float(target - contributions[player])) < 1e-8
            assert action.name == ("all_in" if target == stacks[player] else "raise")
            full = target - contributions[other] >= increment
            assert action.full_raise == full
            updated = list(contributions)
            updated[player] = target
            pending.append((child, other, tuple(updated),
                            target - contributions[other] if full else increment,
                            raises + 1, full, False))
        assert not expected_targets
    return counts


def run_case(scenario, repeats):
    def build():
        return build_preflop_tree(PreflopConfig.from_dict(scenario["config"]))
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        tree = build()
        samples.append(time.perf_counter() - started)
    counts = audit_tree(tree)
    tracemalloc.start()
    try:
        measured = build()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert audit_tree(measured) == counts
    return {"scenario_id": scenario["id"], "config": tree.config.to_dict(),
            "independent_rule_replay": "passed", "tree_counts": counts,
            "runtime_seconds": {"samples": samples, "median": statistics.median(samples)},
            "peak_tracemalloc_bytes": peak}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "benchmarks/preflop-tree-v1.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if type(config["repeats"]) is not int or not 1 <= config["repeats"] <= 25:
        parser.error("Use 1-25 timed repeats.")
    def hashes():
        return {name: file_sha256(ROOT / name) for name in SOURCES} | {"config": file_sha256(config_path)}
    before = hashes()
    if any(value is None for value in before.values()):
        parser.error("Missing benchmark source/config.")
    revision, dirty = git_revision(None), worktree_dirty()
    results = [run_case(scenario, config["repeats"]) for scenario in config["scenarios"]]
    if hashes() != before:
        raise RuntimeError("Sources changed during measurement; discard the report.")
    report = {"schema_version": 1, "benchmark_id": config["benchmark_id"],
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "provenance": {"git_revision": revision, "worktree_dirty": dirty,
                             "source_sha256": before, "source_unchanged": True,
                             "python_version": platform.python_version(), "platform": platform.platform()},
              "methodology": {"timing": "Complete config validation and tree build; replay excluded",
                              "memory": "Separate complete config/tree call; traced Python peak, not RSS",
                              "validation": "Exhaustive independent rational blind, raise, and settlement replay",
                              "scope": "Preflop betting coverage; no equity, strategy, or equilibrium claim"},
              "results": results}
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(results)} independently replayed tree measurements to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
