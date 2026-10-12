"""Compare adapter-local CFR+ regret normalization without editing shared CFR."""
from __future__ import annotations
import gc, hashlib, json, platform, re, statistics, subprocess, time, tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from pokerlab import preflop_delayed_cfrplus as adapter
from pokerlab import preflop_solver as solver
from pokerlab.cfr import strategy as shared_strategy
from scripts.benchmark_preflop_flop_checkdown import verify
from scripts.benchmark_preflop_weighted_range_coverage import (
    _assert_report_pair_posteriors, _independent_pair_audit, _options, _solve_kwargs,
    _source_paths as weighted_source_paths,
)
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
SPEC = ROOT / "benchmarks/preflop-nonnegative-normalization-v1.json"
WEIGHTED_SPEC = ROOT / "benchmarks/preflop-weighted-range-coverage-v1.json"
WEIGHTED_RESULT = ROOT / "benchmarks/results/preflop-weighted-range-coverage-v1.json"
PROFILE_RESULT = ROOT / "benchmarks/results/preflop-local-profile-v1.json"
OUTPUT = ROOT / "benchmarks/results/preflop-nonnegative-normalization-v1.json"


def direct_nonnegative_strategy(regrets):
    """Regret matching when CFR+ has already clamped each row at zero."""
    mass = sum(regrets)
    if mass:
        return [value / mass for value in regrets]
    return [1.0 / len(regrets)] * len(regrets)


def _paths():
    paths = tuple(dict.fromkeys((*weighted_source_paths(),
        "pokerlab/preflop_delayed_cfrplus.py", "pokerlab/cfr.py",
        "scripts/profile_preflop_local_costs.py", "benchmarks/preflop-local-profile-v1.json",
        "benchmarks/results/preflop-local-profile-v1.json",
        "benchmarks/results/preflop-weighted-range-coverage-v1.json",
        "scripts/benchmark_preflop_nonnegative_normalization.py",
        "benchmarks/preflop-nonnegative-normalization-v1.json")))
    if any(not (ROOT / path).is_file() for path in paths):
        raise FileNotFoundError("A declared benchmark dependency is missing")
    return paths


def _hashes(paths):
    values = {path: file_sha256(ROOT / path) for path in paths}
    if any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v) for v in values.values()):
        raise RuntimeError("A source hash is unavailable")
    return values


def _normalization_self_check():
    # The production invariant is CFR+ nonnegative regret rows. Cover uniform,
    # sparse, ordinary, scaled and subnormal positive values without negative inputs.
    cases = ([0.0], [0.0, 0.0], [1.0], [1.0, 3.0], [0.0, 2.0, 0.0, 6.0],
             [1e-200, 3e-200], [5e-324, 1e-323])
    for regrets in cases:
        if direct_nonnegative_strategy(regrets) != shared_strategy(regrets):
            raise AssertionError(f"Direct CFR+ normalization differs on {regrets!r}")
    return {"case_count": len(cases), "exact_probability_parity": True,
            "scope": "nonnegative inputs only; negative-regret behavior is outside the CFR+ invariant"}


def _run(spec, weighted, checkpoint, candidate, trace=False, label="solver arm"):
    kwargs = _solve_kwargs(weighted, checkpoint)
    patch_context = patch.object(adapter, "strategy", direct_nonnegative_strategy if candidate else shared_strategy)
    print(f"starting {label}", flush=True)
    with patch_context:
        gc.collect()
        if trace:
            tracemalloc.start()
        start = time.perf_counter()
        try:
            result = solver.solve_preflop(weighted["sb_range"], weighted["bb_range"], **kwargs)
            payload = json.dumps(result, allow_nan=False, separators=(",", ":"))
        finally:
            elapsed = time.perf_counter() - start
            peak = None
            if trace:
                _current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    checked = verify(result, _oracle_spec(weighted), _options(weighted))
    posterior = _assert_report_pair_posteriors(result, checked, _independent_pair_audit(weighted))
    budget = result["vector_work_budget"]
    if budget["iterations"] != checkpoint["iterations"]:
        raise AssertionError("Full requested iteration ceiling was not admitted")
    target_met = checked["configured_replay"]["nash_conv"] + spec["target_padding"] <= spec["target_nash_conv"]
    row = {"candidate": candidate, "iterations": checkpoint["iterations"], "delay": checkpoint["delay"],
           "complete_call_plus_json_seconds": elapsed, "payload_sha256": digest,
           "payload_bytes": len(payload.encode("utf-8")),
           "nash_conv": checked["configured_replay"]["nash_conv"], "target_met": target_met,
           "posterior_audit": posterior, "replay_metrics": checked["configured_replay"],
           "metric_absolute_gaps": checked["metric_absolute_gaps"],
           "checked_information_sets": checked["configured_replay"]["checked_information_sets"],
           "vector_budget": budget}
    if trace:
        row["traced_peak_bytes"] = peak
    del result, payload, checked
    print(f"finished {label}; gap={row['nash_conv']:.12g}; target={target_met}", flush=True)
    return row


def _promotion_status(spec, rows, pair_results, allocation):
    timing_payload_exact = len({row["payload_sha256"] for row in rows}) == 1
    allocation_payload_exact = allocation[0]["payload_sha256"] == allocation[1]["payload_sha256"]
    allocation_peak_nonregression = allocation[1]["traced_peak_bytes"] <= (
        spec["allocation_peak_nonregression_ratio"] * allocation[0]["traced_peak_bytes"])
    failures = []
    for pair in pair_results:
        if not pair["payload_exact"]:
            failures.append(f"pair {pair['pair']} payload parity failed")
        if not pair["baseline_target_met"] or not pair["candidate_target_met"]:
            failures.append(f"pair {pair['pair']} quality target missed")
    if not timing_payload_exact:
        failures.append("serialized payload differs across timing arms")
    if not allocation_payload_exact:
        failures.append("allocation-arm payload parity failed")
    if not allocation_peak_nonregression:
        failures.append("allocation traced-peak nonregression gate failed")
    reductions = [1 - p["candidate_seconds"] / p["baseline_seconds"] for p in pair_results]
    median_reduction = statistics.median(reductions)
    all_pairs_faster = all(p["candidate_seconds"] < p["baseline_seconds"] for p in pair_results)
    if not all_pairs_faster:
        failures.append("candidate was not faster in every paired timing arm")
    if median_reduction < spec["timing_gate_median_reduction"]:
        failures.append("median timing reduction missed the frozen promotion threshold")
    gate = (all_pairs_faster and median_reduction >= spec["timing_gate_median_reduction"]
            and allocation_peak_nonregression and allocation_payload_exact and timing_payload_exact
            and all(p["payload_exact"] and p["baseline_target_met"] and p["candidate_target_met"]
                    for p in pair_results))
    return {"failures": failures, "median_reduction": median_reduction,
            "timing_payload_exact_all_arms": timing_payload_exact,
            "allocation_payload_exact": allocation_payload_exact,
            "allocation_peak_nonregression_met": allocation_peak_nonregression,
            "all_pairs_candidate_faster": all_pairs_faster, "promotion_gate_met": gate}


def _oracle_spec(weighted):
    return {**weighted, "sb": weighted["sb_range"], "bb": weighted["bb_range"],
            "expected_worlds": weighted["expected_physical_worlds"],
            "expected_selected_outcomes": weighted["expected_selected_outcomes"]}


def main():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    if (spec["weighted_fixture"] != WEIGHTED_SPEC.relative_to(ROOT).as_posix()
            or spec["weighted_result_provenance"] != WEIGHTED_RESULT.relative_to(ROOT).as_posix()
            or spec["profile_provenance"] != PROFILE_RESULT.relative_to(ROOT).as_posix()):
        raise ValueError("Weighted fixture/profile provenance paths differ from the frozen declaration")
    weighted = json.loads(WEIGHTED_SPEC.read_text(encoding="utf-8"))
    profile = json.loads(PROFILE_RESULT.read_text(encoding="utf-8"))
    revision = git_revision(None)
    if not re.fullmatch(r"[0-9a-f]{40}", revision or "") or worktree_dirty() is not False:
        raise RuntimeError("Freeze the source/spec in a clean commit before running")
    prior_revision = profile.get("source_revision")
    if not isinstance(prior_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", prior_revision):
        raise ValueError("Prior profile source revision is invalid")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", prior_revision, revision],
                              cwd=ROOT, capture_output=True, check=False)
    if ancestor.returncode != 0:
        raise ValueError("Prior profile source is not an ancestor of this frozen revision")
    if (profile.get("benchmark_id") != "preflop-local-profile-v1"
            or profile["specification"].get("weighted_fixture") != spec["weighted_fixture"]
            or profile.get("weighted_spec_sha256") != file_sha256(WEIGHTED_SPEC)):
        raise ValueError("Prior profile fixture provenance differs from the frozen weighted input")
    if profile["quality"]["independent_replay"]["configured_replay"]["nash_conv"] > spec["target_nash_conv"]:
        raise ValueError("Prior profile quality check misses this frozen target")
    expected_order = ["baseline", "candidate", "candidate", "baseline", "baseline", "candidate"]
    if (spec["iterations"] != 500 or spec["averaging_delay"] != 250
            or spec["timing_pairs"] != 3 or spec["pair_order"] != expected_order
            or spec["allocation_iterations"] != 10 or spec["allocation_delay"] != 5):
        raise ValueError("This harness expects the frozen three-pair, 500/delay-250 plan and 10/delay-5 allocation arms")
    if spec["target_nash_conv"] != weighted["target_nash_conv"] or spec["target_padding"] != weighted["target_padding"]:
        raise ValueError("Quality gate differs from the frozen weighted fixture")
    paths = _paths(); initial = _hashes(paths); spec_hash = file_sha256(SPEC); weighted_hash = file_sha256(WEIGHTED_SPEC)
    prior_hashes = profile.get("source_hashes", {})
    if not prior_hashes:
        raise ValueError("Prior profile source manifest is missing")
    for path, expected_hash in prior_hashes.items():
        prior_path = ROOT / path
        if not prior_path.is_file() or file_sha256(prior_path) != expected_hash:
            raise ValueError(f"Prior profile source differs from current frozen input: {path}")
    audit = _independent_pair_audit(weighted)
    normalization_check = _normalization_self_check()
    checkpoint = {"iterations": spec["iterations"], "delay": spec["averaging_delay"]}
    rows = []
    for index, arm in enumerate(spec["pair_order"]):
        row = _run(spec, weighted, checkpoint, arm == "candidate", label=f"timing {index + 1}/6 {arm}")
        rows.append({"pair": index // 2 + 1, **row})
    pair_results = []
    for pair in range(spec["timing_pairs"]):
        baseline, candidate = rows[pair * 2], rows[pair * 2 + 1]
        if spec["pair_order"][pair * 2:pair * 2 + 2] == ["candidate", "baseline"]:
            baseline, candidate = candidate, baseline
        pair_results.append({"pair": pair + 1, "baseline_seconds": baseline["complete_call_plus_json_seconds"],
            "candidate_seconds": candidate["complete_call_plus_json_seconds"],
            "payload_exact": baseline["payload_sha256"] == candidate["payload_sha256"],
            "baseline_target_met": baseline["target_met"], "candidate_target_met": candidate["target_met"]})
    allocation = []
    for candidate in (False, True):
        arm = "candidate" if candidate else "baseline"
        allocation.append(_run(spec, weighted, {"iterations": spec["allocation_iterations"],
            "delay": spec["allocation_delay"]}, candidate, trace=True, label=f"allocation {arm}"))
    gate = _promotion_status(spec, rows, pair_results, allocation)
    failures = gate["failures"]
    median_reduction = gate["median_reduction"]
    after = _hashes(paths)
    if initial != after or file_sha256(SPEC) != spec_hash or file_sha256(WEIGHTED_SPEC) != weighted_hash:
        raise RuntimeError("Frozen source/specification changed during experiment")
    if git_revision(None) != revision or worktree_dirty() is not False:
        raise RuntimeError("Frozen revision/worktree changed during experiment")
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "source_revision": revision,
        "worktree_dirty_at_start": False, "python": platform.python_version(), "platform": platform.platform(),
        "source_hashes": initial, "spec_sha256": spec_hash, "weighted_spec_sha256": weighted_hash,
        "profile_provenance_sha256": file_sha256(PROFILE_RESULT), "specification": spec,
        "independent_rational_pair_audit": audit, "normalization_self_check": normalization_check,
        "timing_arms": rows, "paired_results": pair_results,
        "timing_payload_exact_all_arms": gate["timing_payload_exact_all_arms"],
        "allocation_payload_exact": gate["allocation_payload_exact"],
        "allocation_peak_nonregression_met": gate["allocation_peak_nonregression_met"],
        "all_pairs_candidate_faster": gate["all_pairs_candidate_faster"],
        "failures": failures,
        "median_reduction": median_reduction, "promotion_gate": spec["promotion_gate_rule"],
        "promotion_gate_met": gate["promotion_gate_met"],
        "allocation_arms": allocation,
        "prior_profile_revision": prior_revision,
        "normalization_work_accounting": "For each rematched row, shared strategy allocates and clamps a positive list, sums it, then constructs normalized output; the candidate sums the already nonnegative row and constructs normalized output. This removes one clamp pass and temporary row allocation, adds no persistent state, and does not exceed the existing conservative row-loop budget. No budget is reduced.",
        "admission_scope": "Same existing public-vector model and requested iteration budgets in both arms. The direct normalization removes the shared max-clamp traversal only inside the preflop adapter alias; it adds no persistent per-row state. This does not relax or revise vector-budget accounting.",
        "interpretation": "Exact serialized payload parity and independent original-world replay are mandatory. A 5% median gate is required before considering promotion; this experiment alone does not establish general speedup or solver accuracy beyond this finite fixture. Traced peaks are Python allocations for the separate 10-iteration calls, not RSS or high-iteration memory.",
        "model_limits": spec["model_limits"]}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"saved {OUTPUT}; median reduction={median_reduction:.4%}; gate={report['promotion_gate_met']}; failures={len(failures)}", flush=True)
    if failures:
        raise AssertionError("Report saved with failed parity/quality checks: " + "; ".join(failures))

if __name__ == "__main__": main()
