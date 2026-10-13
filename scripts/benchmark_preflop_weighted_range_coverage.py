"""Frozen weighted private-range coverage for a finite flop-checkdown game.

This harness preflights every case before training. Run only after it has
been copied into a clean, frozen repository commit with its matching spec.
"""
from __future__ import annotations

import gc
import hashlib
import json
import platform
import re
import time
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

from pokerlab import preflop_solver as solver
from scripts.benchmark_preflop_flop_checkdown import futures, verify, SOURCES
from scripts.benchmark_preflop_action_coverage import _coverage, _coverage_union, _preflight as action_preflight
from scripts.benchmark_preflop_flop_raise_coverage import _coverage as flop_coverage, _merge_coverage as merge_flop_coverage
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = Path(__file__).resolve()
SPEC_PATH = ROOT / "benchmarks/preflop-weighted-range-coverage-v1.json"
OUTPUT_PATH = ROOT / "benchmarks/results/preflop-weighted-range-coverage-v1.json"


def _source_paths() -> tuple[str, ...]:
    extra = (
        "scripts/benchmark_preflop_weighted_range_coverage.py",
        "scripts/benchmark_preflop_action_coverage.py",
        "scripts/benchmark_preflop_flop_raise_coverage.py",
        "scripts/benchmark_preflop_flop_checkdown.py",
        "scripts/preflop_validation.py",
        "scripts/benchmark_preflop_two_flops.py",
        "scripts/benchmark_preflop_grouped_world_admission.py",
        "scripts/benchmark_turn_solver.py",
        "scripts/cfr_quality.py",
        "tests/test_preflop_delayed_cfrplus.py",
        "tests/test_preflop_flop_checkdown.py",
        "tests/test_preflop_future_groups.py",
        "tests/test_preflop_future_indexing.py",
        "tests/test_preflop_grouped_world_admission.py",
        "benchmarks/preflop-flop-checkdown-v1.json",
        "benchmarks/preflop-flop-raise-coverage-v1.json",
        "benchmarks/preflop-grouped-world-admission-v1.json",
        "benchmarks/preflop-action-coverage-v1.json",
        "benchmarks/preflop-weighted-range-coverage-v1.json",
    )
    return tuple(dict.fromkeys((*SOURCES, *extra)))


def _game_spec(spec: dict) -> dict:
    return {
        "sb": spec["sb_range"],
        "bb": spec["bb_range"],
        "preflop_config": dict(spec["preflop_config"]),
        "flops": spec["flops"],
        "physical_outcomes": {"flops": spec["flops"]},
        "flop_config": dict(spec["flop_config"]),
        "postflop_scope": spec["postflop_scope"],
        "algorithm": spec["algorithm"],
        "traversal": spec["traversal"],
        "diagnostics": spec["diagnostics"],
        "resource_model": spec["resource_model"],
        "future_indexing": spec["future_indexing"],
    }


def _options(spec: dict) -> dict:
    return {
        "config": {"starting_stack": spec["starting_stack"], **spec["preflop_config"]},
        "runouts": futures(spec["flops"]),
        "flop_config": spec["flop_config"],
        "postflop_scope": spec["postflop_scope"],
    }


def _solve_kwargs(spec: dict, checkpoint: dict) -> dict:
    return {
        **_options(spec),
        "iterations": checkpoint["iterations"],
        "averaging_delay": checkpoint["delay"],
        "algorithm": spec["algorithm"],
        "traversal": spec["traversal"],
        "diagnostics": spec["diagnostics"],
        "resource_model": spec["resource_model"],
        "future_indexing": spec["future_indexing"],
        "world_admission": spec["world_admission"],
    }


def _preflight(spec: dict, checkpoint: dict) -> dict:
    # The reused admission harness stops exactly before grouped-world allocation;
    # it captures both full-T vector work and the separate grouping charge.
    return action_preflight(_game_spec(spec), spec["starting_stack"], checkpoint, grouped=True)


def _parse_exact_range(text: str) -> list[tuple[str, Fraction]]:
    """Parse only explicit two-card combos and rational weights for the audit."""
    rows: list[tuple[str, Fraction]] = []
    for item in text.split(","):
        hand_text, separator, weight_text = item.partition(":")
        if not separator or len(hand_text) != 4:
            raise ValueError(f"Expected explicit combo:weight token, got {item!r}")
        cards = (hand_text[:2], hand_text[2:])
        if cards[0] == cards[1] or len(set(cards)) != 2:
            raise ValueError(f"Invalid two-card combo {hand_text!r}")
        rows.append((hand_text, Fraction(weight_text)))
    if len({hand for hand, _ in rows}) != len(rows):
        raise ValueError("Duplicate combo in fixed weighted range")
    return rows


def _hand_cards(hand: str) -> frozenset[str]:
    return frozenset((hand[:2], hand[2:]))


def _independent_pair_audit(spec: dict) -> dict:
    """Hand-count compatibility, blocker worlds, and exact posterior fractions."""
    sb = _parse_exact_range(spec["sb_range"])
    bb = _parse_exact_range(spec["bb_range"])
    flops = [tuple(flop) for flop in spec["flops"]]
    if any(len(flop) != 3 or len(set(flop)) != 3 for flop in flops):
        raise AssertionError("Each selected flop must contain three distinct cards")
    if len(set(flops)) != len(flops):
        raise AssertionError("Duplicate selected flop")

    candidates = []
    legal_worlds: dict[tuple[str, str], int] = {}
    raw_pair_mass: dict[tuple[str, str], Fraction] = {}
    overlapping = []
    blocked_flop_pairs = []
    for sh, sw in sb:
        for bh, bw in bb:
            pair = (sh, bh)
            scards, bcards = _hand_cards(sh), _hand_cards(bh)
            if scards & bcards:
                overlapping.append({"sb": sh, "bb": bh, "shared_cards": sorted(scards & bcards)})
                continue
            candidates.append(pair)
            deal_count = 0
            for flop in flops:
                if (scards | bcards) & set(flop):
                    if scards & set(flop):
                        blocked_flop_pairs.append({"sb": sh, "bb": bh, "flop": list(flop), "blocked": "sb"})
                    elif bcards & set(flop):
                        blocked_flop_pairs.append({"sb": sh, "bb": bh, "flop": list(flop), "blocked": "bb"})
                    continue
                # Four private cards and the fixed flop leave 45 cards; turn
                # and river are ordered, hence 45*44 physical outcomes.
                deal_count += 45 * 44
            if deal_count == 0:
                continue
            legal_worlds[pair] = deal_count
            raw_pair_mass[pair] = sw * bw * deal_count

    total_mass = sum(raw_pair_mass.values(), Fraction(0))
    posterior = {pair: mass / total_mass for pair, mass in raw_pair_mass.items()}
    expected_rows = spec["expected_pair_distribution"]
    expected_posterior = {(row["sb"], row["bb"]): Fraction(row["numerator"], spec["posterior_denominator"])
                          for row in expected_rows}
    expected_worlds = {(row["sb"], row["bb"]): row["worlds"] for row in expected_rows}
    if len(sb) * len(bb) != spec["expected_candidate_private_pairs"]:
        raise AssertionError("Independent range-combo product disagrees with frozen candidate count")
    if len(candidates) != spec["expected_compatible_private_pairs"]:
        raise AssertionError("Independent overlap count disagrees with frozen compatible-pair count")
    if overlapping != [{"sb": spec["expected_overlapping_pair"]["sb"],
                        "bb": spec["expected_overlapping_pair"]["bb"],
                        "shared_cards": [spec["expected_overlapping_pair"]["shared_card"]]}]:
        raise AssertionError(f"Unexpected exact overlap pair(s): {overlapping}")
    blocker = spec["expected_blocked_flop_hand"]
    blocker_cards = _hand_cards(blocker["hand"]) & set(blocker["flop"])
    if blocker_cards != {spec["expected_blocked_flop_hand"]["shared_card"]}:
        raise AssertionError("The declared blocker card does not match the hand/flop intersection")
    observed_blocker = any(
        row["sb"] == blocker["hand"] and row["flop"] == blocker["flop"]
        and row["blocked"] == "sb"
        for row in blocked_flop_pairs
    )
    if not observed_blocker:
        raise AssertionError("The predeclared SB flop blocker was not independently observed")
    if legal_worlds != expected_worlds or posterior != expected_posterior:
        raise AssertionError("Hand-counted pair worlds or rational posterior disagree with frozen spec")
    candidate_outcomes = len(flops) * 49 * 48
    if candidate_outcomes != spec["expected_selected_outcomes"]:
        raise AssertionError("Independent ordered future-outcome count disagrees with frozen spec")
    if sum(legal_worlds.values()) != spec["expected_physical_worlds"]:
        raise AssertionError("Independent physical-world count disagrees with frozen spec")

    return {
        "candidate_private_pairs": len(sb) * len(bb),
        "compatible_private_pair_keys": [list(pair) for pair in legal_worlds],
        "overlapping_private_pairs": overlapping,
        "flop_blocker_observations": blocked_flop_pairs,
        "worlds_by_private_pair": [
            {"sb": pair[0], "bb": pair[1], "worlds": legal_worlds[pair]}
            for pair in legal_worlds
        ],
        "posterior_denominator": spec["posterior_denominator"],
        "exact_posterior_by_private_pair": [
            {"sb": pair[0], "bb": pair[1], "numerator": posterior[pair].numerator,
             "denominator": posterior[pair].denominator,
             "expected_numerator_over_frozen_denominator": expected_posterior[pair].numerator,
             "expected_denominator_over_frozen_denominator": expected_posterior[pair].denominator}
            for pair in legal_worlds
        ],
        "selected_outcomes": candidate_outcomes,
        "physical_worlds": sum(legal_worlds.values()),
    }


def _assert_report_pair_posteriors(result: dict, checked: dict, pair_audit: dict) -> dict:
    def hand_key(hand: str) -> tuple[str, str]:
        if not isinstance(hand, str) or len(hand) != 4:
            raise AssertionError(f"Expected a two-card hand label, got {hand!r}")
        return tuple(sorted((hand[:2], hand[2:])))

    expected = {(hand_key(row["sb"]), hand_key(row["bb"])):
                Fraction(row["numerator"], row["denominator"])
                for row in pair_audit["exact_posterior_by_private_pair"]}
    actual = {(hand_key(row["sb_hand"]), hand_key(row["bb_hand"])): float(row["probability"])
              for row in result["private_pair_probabilities"]}
    oracle_rows = checked["configured_replay"]["private_pair_probabilities"]
    oracle = {(hand_key(row["sb"]), hand_key(row["bb"])): float(row["probability"]) for row in oracle_rows}
    if actual.keys() != expected.keys() or oracle.keys() != expected.keys():
        raise AssertionError("Solver/oracle private-pair keyset differs from independently counted legal pairs")
    max_solver_delta = max(abs(actual[pair] - float(prob)) for pair, prob in expected.items())
    max_oracle_delta = max(abs(oracle[pair] - float(prob)) for pair, prob in expected.items())
    if max_solver_delta > 1e-12 or max_oracle_delta > 1e-12:
        raise AssertionError("Solver/oracle joint posterior differs from independent rational blocker audit")
    return {"max_solver_probability_delta_vs_rational": max_solver_delta,
            "max_oracle_probability_delta_vs_rational": max_oracle_delta,
            "tolerance": 1e-12}


def _hash_manifest(paths: tuple[str, ...]) -> dict[str, str]:
    hashes = {path: file_sha256(ROOT / path) for path in paths}
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
           for value in hashes.values()):
        raise RuntimeError("A source hash is unavailable")
    return hashes


def main() -> None:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    revision, dirty = git_revision(None), worktree_dirty()
    if dirty is not False or not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise RuntimeError("Freeze source/spec in a clean commit before running")
    source_paths = _source_paths()
    source_hashes = _hash_manifest(source_paths)
    spec_hash = file_sha256(SPEC_PATH)
    script_hash = file_sha256(SCRIPT_PATH)
    if not re.fullmatch(r"[0-9a-f]{64}", spec_hash or "") or not re.fullmatch(r"[0-9a-f]{64}", script_hash or ""):
        raise RuntimeError("Spec or harness hash unavailable")
    pair_audit = _independent_pair_audit(spec)

    checkpoints = spec["checkpoints"]
    if len(checkpoints) != 2 or any(c["delay"] * 2 != c["iterations"] for c in checkpoints):
        raise AssertionError("Frozen fixture must contain exactly two half-delay checkpoints")
    print("Preflighting both grouped-vector cases before any training", flush=True)
    admissions = []
    for checkpoint in checkpoints:
        admission = _preflight(spec, checkpoint)
        admissions.append(admission)
        print(f"  T={checkpoint['iterations']} d={checkpoint['delay']}: {admission['status']} "
              f"{admission['rejection'] or admission['combined_modeled_loop_entries']}", flush=True)

    oracle_spec = {
        **spec,
        "sb": spec["sb_range"],
        "bb": spec["bb_range"],
        "expected_worlds": spec["expected_physical_worlds"],
        "expected_selected_outcomes": spec["expected_selected_outcomes"],
    }
    options = _options(spec)
    results = []
    all_preflop_coverage = []
    all_flop_coverage = []
    for index, (checkpoint, admission) in enumerate(zip(checkpoints, admissions), 1):
        if admission["status"] != "admitted":
            results.append({"case": index, **checkpoint, "status": "rejected",
                            "rejection": admission["rejection"], "preflight": admission})
            continue
        kwargs = _solve_kwargs(spec, checkpoint)
        print(f"Complete solve {index}/{len(checkpoints)} T={checkpoint['iterations']} d={checkpoint['delay']}", flush=True)
        gc.collect()
        start = time.perf_counter()
        result = solver.solve_preflop(spec["sb_range"], spec["bb_range"], **kwargs)
        serialized = json.dumps(result, allow_nan=False)
        elapsed = time.perf_counter() - start

        checked = verify(result, oracle_spec, options)
        posterior_audit = _assert_report_pair_posteriors(result, checked, pair_audit)
        if result.get("world_admission") != "grouped-vector":
            raise AssertionError("Result does not report the requested grouped-vector admission mode")
        if result.get("postflop_scope") != "flop-checkdown" or result.get("future_indexing") != "flop-sign":
            raise AssertionError("Result does not report the frozen game scope/indexing mode")
        if result.get("worlds") != spec["expected_physical_worlds"]:
            raise AssertionError("Physical-world count changed")
        actual_budget = result["vector_work_budget"]
        if actual_budget["iterations"] != checkpoint["iterations"]:
            raise AssertionError("Full requested iteration ceiling was not retained in vector admission")
        if actual_budget["total_loop_entries_upper_bound"] != admission["combined_modeled_loop_entries"]:
            raise AssertionError("Actual solve admission does not match captured full-T preflight")
        preflop_actions = _coverage(result["strategy"])
        flop_actions = flop_coverage(result["strategy"])
        all_preflop_coverage.append({"starting_stack": spec["starting_stack"], **preflop_actions})
        all_flop_coverage.append(flop_actions)
        target_met = checked["configured_replay"]["nash_conv"] + spec["target_padding"] <= spec["target_nash_conv"]
        results.append({
            "case": index,
            **checkpoint,
            "status": "completed",
            "complete_call_plus_json_seconds": elapsed,
            "serialized_json_bytes": len(serialized.encode("utf-8")),
            "full_payload_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            "verification": checked,
            "rational_posterior_audit": posterior_audit,
            "preflop_action_coverage": preflop_actions,
            "flop_action_coverage": flop_actions,
            "target_nash_conv": spec["target_nash_conv"],
            "target_met": target_met,
            "preflight": admission,
            "future_indexing_metadata": result["future_indexing_metadata"],
        })
        print(f"  independent gap={checked['configured_replay']['nash_conv']:.12g}; "
              f"target={target_met}; seconds={elapsed:.3f}", flush=True)
        del result, serialized

    coverage_union = {
        "preflop": _coverage_union(all_preflop_coverage),
        "flop": merge_flop_coverage(all_flop_coverage),
    }
    after_hashes = _hash_manifest(source_paths)
    if source_hashes != after_hashes or spec_hash != file_sha256(SPEC_PATH) or script_hash != file_sha256(SCRIPT_PATH):
        raise RuntimeError("Source, harness or spec changed during run")
    if git_revision(None) != revision or worktree_dirty() is not False:
        raise RuntimeError("Repository revision/worktree changed during run")
    report = {
        "schema_version": 1,
        "benchmark_id": spec["benchmark_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": revision,
        "worktree_dirty_at_start": False,
        "source_hashes": source_hashes,
        "benchmark_script_location": SCRIPT_PATH.relative_to(ROOT).as_posix(),
        "benchmark_script_sha256": script_hash,
        "configuration_sha256": spec_hash,
        "specification": spec,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "independent_rational_pair_audit": pair_audit,
        "preflight": admissions,
        "results": results,
        "action_coverage_union": coverage_union,
        "timing_scope": "One descriptive complete solve plus JSON serialization per admitted checkpoint. Includes physical enumeration/ranking, tree construction, original-world and grouped-vector admission, grouping, training and exact diagnostics. Preallocated selected runouts, pre-call garbage collection and independent replay are excluded. No speedup or memory comparison.",
        "quality_scope": "Every admitted result is independently replayed over original physical worlds with numeric poker rules and exact visible-information best responses. Pair posterior probabilities are separately checked against hand-counted rational combo weights and blocker-conditioned world counts. All target misses and preflight rejections remain visible; the finite-game 0.005-chip target is per checkpoint, not a general convergence claim.",
        "admission_scope": "Both grouped-vector cases are preflighted before any training. The preflight stops before grouping/copy/trainer allocation, preserves the full requested iteration count in the vector envelope, and includes the separately reported grouping charge. Existing grouped-vector mode replaces only the legacy physical-world-count times requested-iterations proxy with its ten-iteration construction guard. Full requested work stays in the vector/grouping envelope and every remaining cap stays enforced; this experiment changes no additional caps and no rejected case is simplified or retried.",
        "provenance": "Luna drafted this isolated weighted-range fixture and harness; the lead freezes and measures the committed experiment. Independent combo/pair/posterior assertions are hand-counted in this script using rational weights; policy values and legal responses use the existing independent numeric replay. A preflop result-metadata wording fix explicitly identifies the existing replaced world guard; calculation paths and default metadata remain unchanged. No shared-kernel, Coach, third-party source, or dependency changes.",
        "model_limits": spec["model_limits"],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    # Save a complete report even if no admitted policy exhibited the intended
    # action coverage or every admitted quality checkpoint misses its target.
    required_preflop = coverage_union["preflop"]["coverage_flags"]
    required_flop = coverage_union["flop"]
    if not all(required_preflop.values()) or not required_flop["union_has_check_call_bet_raise_all_in"] or not required_flop["union_has_both_requested_flop_bet_amounts"]:
        raise AssertionError(
            "Report saved, but weighted-matrix action coverage is incomplete: "
            f"preflop={required_preflop}, flop={required_flop}")
    print(f"saved {OUTPUT_PATH}; admitted={sum(row['status']=='admitted' for row in admissions)}/{len(admissions)}", flush=True)


if __name__ == "__main__":
    main()
