"""Frozen expanded-range preflop/flop-checkdown experiment; run only after freeze."""
from __future__ import annotations
import gc, hashlib, json, platform, re, time
from datetime import datetime, timezone
from pathlib import Path

from pokerlab import preflop_solver as solver
from scripts import benchmark_preflop_weighted_range_coverage as weighted
from scripts.benchmark_preflop_flop_checkdown import verify
from scripts.benchmark_preflop_flop_raise_coverage import _coverage as flop_coverage

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = Path(__file__).resolve()
SPEC_PATH = ROOT / "benchmarks/preflop-expanded-range-v1.json"
OUTPUT_PATH = ROOT / "benchmarks/results/preflop-expanded-range-v1.json"
EXPECTED_BLOCKERS = {
    ("sb", "7s6s", ("5h", "6s", "Jc"), "6s"),
    ("sb", "Tc9c", ("9c", "Th", "2d"), "9c"),
    ("sb", "QhJh", ("Ks", "3d", "Qh"), "Qh"),
    ("bb", "KsKd", ("Ks", "3d", "Qh"), "Ks"),
}

def _extra_card_audit(spec: dict) -> dict:
    def cards(hand): return frozenset((hand[:2], hand[2:]))
    sb = weighted._parse_exact_range(spec["sb_range"])
    bb = weighted._parse_exact_range(spec["bb_range"])
    observed = set()
    for player, rows in (("sb", sb), ("bb", bb)):
        for hand, _weight in rows:
            for flop in map(tuple, spec["flops"]):
                overlap = cards(hand) & set(flop)
                if overlap:
                    if len(overlap) != 1: raise AssertionError("Unexpected multi-card hand/flop overlap")
                    observed.add((player, hand, flop, next(iter(overlap))))
    declared = {(row["player"], row["hand"], tuple(row["flop"]), row["shared_card"]) for row in spec["blocked_hand_flops"]}
    if declared != EXPECTED_BLOCKERS: raise AssertionError(f"Declared blocker list changed: {sorted(declared)}")
    if observed != EXPECTED_BLOCKERS:
        raise AssertionError(f"Unexpected full blocker set: {sorted(observed)}")
    both = spec["blocked_both_pair_flop"]
    sb_hit = cards(both["sb"]) & set(both["flop"])
    bb_hit = cards(both["bb"]) & set(both["flop"])
    if sb_hit != {"Qh"} or bb_hit != {"Ks"}:
        raise AssertionError(f"Expected QhJh/KsKd to be blocked on both sides: {sb_hit}, {bb_hit}")
    return {"all_hand_flop_blockers": [
        {"player": p, "hand": h, "flop": list(f), "card": c}
        for p, h, f, c in sorted(observed)],
        "both_sides_blocked_pair_flop": {**both, "sb_blockers": sorted(sb_hit), "bb_blockers": sorted(bb_hit)}}

def _manifest_paths() -> tuple[str, ...]:
    paths = (*weighted._source_paths(), "scripts/benchmark_preflop_expanded_range.py",
             "benchmarks/preflop-expanded-range-v1.json")
    return tuple(dict.fromkeys(paths))

def _hashes(paths) -> dict[str, str]:
    result = {path: weighted.file_sha256(ROOT / path) for path in paths}
    if any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v) for v in result.values()):
        raise RuntimeError("Source/spec hash unavailable")
    return result

def main() -> None:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    revision, dirty = weighted.git_revision(None), weighted.worktree_dirty()
    if dirty is not False or not re.fullmatch(r"[0-9a-f]{40}", revision or ""):
        raise RuntimeError("Freeze source/spec in a clean commit before measurement")
    source_paths = _manifest_paths()
    source_hashes, spec_hash, script_hash = _hashes(source_paths), weighted.file_sha256(SPEC_PATH), weighted.file_sha256(SCRIPT_PATH)
    if not re.fullmatch(r"[0-9a-f]{64}", spec_hash or "") or not re.fullmatch(r"[0-9a-f]{64}", script_hash or ""):
        raise RuntimeError("Harness/spec hash unavailable")
    pair_audit = weighted._independent_pair_audit(spec)
    blocker_audit = _extra_card_audit(spec)
    if pair_audit["physical_worlds"] != 91080 or pair_audit["selected_outcomes"] != 9408:
        raise AssertionError("Independent physical-world fixture count changed")
    checkpoints = spec["checkpoints"]
    if len(checkpoints) != 2 or any(c["delay"] * 2 != c["iterations"] for c in checkpoints):
        raise AssertionError("Expected the two frozen half-delay checkpoints")

    print("Preflighting both full-requested-T cases before any training", flush=True)
    admissions = []
    for checkpoint in checkpoints:
        row = weighted._preflight(spec, checkpoint)
        admissions.append(row)
        print(f"  T={checkpoint['iterations']} d={checkpoint['delay']}: {row['status']} "
              f"{row['rejection'] or row['combined_modeled_loop_entries']}", flush=True)

    oracle_spec = {**spec, "sb": spec["sb_range"], "bb": spec["bb_range"],
                   "expected_worlds": spec["expected_physical_worlds"],
                   "expected_selected_outcomes": spec["expected_selected_outcomes"]}
    options = weighted._options(spec)
    results, case_coverages = [], []
    for index, (checkpoint, admission) in enumerate(zip(checkpoints, admissions), 1):
        if admission["status"] != "admitted":
            results.append({"case": index, **checkpoint, "status": "rejected",
                            "rejection": admission["rejection"], "preflight": admission})
            continue
        kwargs = weighted._solve_kwargs(spec, checkpoint)
        print(f"Complete solve {index}/{len(checkpoints)} T={checkpoint['iterations']} d={checkpoint['delay']}", flush=True)
        gc.collect()
        start = time.perf_counter()
        result = solver.solve_preflop(spec["sb_range"], spec["bb_range"], **kwargs)
        serialized = json.dumps(result, allow_nan=False)
        elapsed = time.perf_counter() - start

        checked = verify(result, oracle_spec, options)
        posterior = weighted._assert_report_pair_posteriors(result, checked, pair_audit)
        if result.get("world_admission") != "grouped-vector" or result.get("worlds") != 91080:
            raise AssertionError("Solver result disagrees with requested grouped physical-world game")
        if result["vector_work_budget"]["iterations"] != checkpoint["iterations"]:
            raise AssertionError("Full requested iteration count was not retained")
        if result["vector_work_budget"]["total_loop_entries_upper_bound"] != admission["combined_modeled_loop_entries"]:
            raise AssertionError("Actual solve budget differs from preflight")
        preflop = weighted._coverage(result["strategy"])
        flop = flop_coverage(result["strategy"])
        preflop_ok = all(preflop["coverage_flags"].values())
        flop_ok = flop["union_has_check_call_bet_raise_all_in"] and flop["union_has_both_requested_flop_bet_amounts"]
        case_coverages.append({"case": index, "preflop": preflop, "flop": flop,
                               "preflop_complete": preflop_ok, "flop_complete": flop_ok})
        replay_gap = checked["configured_replay"]["nash_conv"]
        results.append({"case": index, **checkpoint, "status": "completed",
            "complete_call_plus_json_seconds": elapsed, "serialized_json_bytes": len(serialized.encode()),
            "full_payload_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
            "verification": checked, "rational_posterior_audit": posterior,
            "blocker_audit": blocker_audit, "preflop_action_coverage": preflop,
            "flop_action_coverage": flop, "coverage_complete_for_case": preflop_ok and flop_ok,
            "target_nash_conv": spec["target_nash_conv"],
            "target_padding": spec["target_padding"],
            "target_met": replay_gap + spec["target_padding"] <= spec["target_nash_conv"],
            "preflight": admission, "vector_work_budget": result["vector_work_budget"],
            "future_indexing_metadata": result["future_indexing_metadata"]})
        print(f"  independently replayed gap={replay_gap:.12g}; target="
              f"{replay_gap + spec['target_padding'] <= spec['target_nash_conv']}; seconds={elapsed:.3f}", flush=True)
        del result, serialized

    after_hashes = _hashes(source_paths)
    if source_hashes != after_hashes or spec_hash != weighted.file_sha256(SPEC_PATH) or script_hash != weighted.file_sha256(SCRIPT_PATH):
        raise RuntimeError("Source, spec, or harness changed during measurement")
    if weighted.git_revision(None) != revision or weighted.worktree_dirty() is not False:
        raise RuntimeError("Repository revision/worktree changed during measurement")
    completed = [r for r in results if r["status"] == "completed"]
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "source_revision": revision,
        "worktree_dirty_at_start": False, "source_hashes": source_hashes,
        "benchmark_script_location": "scripts/benchmark_preflop_expanded_range.py",
        "benchmark_script_sha256": script_hash, "configuration_sha256": spec_hash,
        "specification": spec, "python": platform.python_version(), "platform": platform.platform(),
        "independent_rational_pair_audit": pair_audit, "independent_full_blocker_audit": blocker_audit,
        "preflight": admissions, "results": results, "per_case_coverage": case_coverages,
        "target_summary": {"target_nash_conv": spec["target_nash_conv"], "padding": spec["target_padding"],
            "all_completed_cases_met": bool(completed) and all(r["target_met"] for r in completed)},
        "timing_scope": "One descriptive complete solve plus JSON serialization per admitted checkpoint, measured separately. Includes enumeration/ranking, tree construction, grouped-vector admission, grouping, full requested-T training and exact diagnostics. Runout input preparation, pre-call garbage collection and independent replay are excluded. No cross-game speed comparison or memory claim.",
        "quality_scope": "Every completed policy is independently replayed over all original physical worlds with numeric betting rules and exact legal visible-information best responses. Joint private-pair probabilities are independently checked against rational range weights and blocker-conditioned counts. Misses and preflight rejections are retained; NashConv + 1e-10 <= 0.005 is a finite-game checkpoint target, not a general convergence claim.",
        "admission_scope": "Both requested full-T cases are preflighted before training. The opt-in grouped-vector path replaces only the legacy physical-world-count times requested-iterations proxy with the 10-iteration construction guard; physical candidates, constructed-world ceiling, full requested-T vector/grouping work and all other existing limits remain enforced. No cap is raised and no rejected case is simplified or retried.",
        "provenance": "Luna drafted this fixed expanded-range experiment and harness outside the repository; the lead freezes and measures it. Combo overlap, blockers and rational posteriors are independently counted in this script; policy values and legal responses use the repository's independent numeric replay. No production, shared-kernel, Coach, dependency, or third-party-source changes.",
        "model_limits": spec["model_limits"]}
    output = OUTPUT_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    # Retain the complete report before treating any coverage omission as a harness failure.
    required = [r for r in completed if not r["coverage_complete_for_case"]]
    if required:
        raise AssertionError(f"Report saved; a completed checkpoint lacks required per-case action coverage: {[r['case'] for r in required]}")
    print(f"saved {output}; completed={len(completed)}/{len(checkpoints)}", flush=True)

if __name__ == "__main__":
    main()
