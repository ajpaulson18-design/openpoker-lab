"""Reassess the unchanged target-plan research helper on a grouped finite game."""
from __future__ import annotations
import gc, hashlib, json, platform, re, subprocess, time, tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from pokerlab import public_cfr, preflop_solver
from scripts import benchmark_preflop_weighted_range_coverage as weighted
from scripts import benchmark_preflop_expanded_range as expanded
from scripts.benchmark_preflop_flop_checkdown import verify
from scripts.benchmark_preflop_nonnegative_normalization import _promotion_status
from scripts.preflop_target_plan_prototype import compile_target_plan

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/preflop-grouped-target-plan-v1.json"
GAME = ROOT / "benchmarks/preflop-expanded-range-v1.json"
PRIOR = ROOT / "benchmarks/results/preflop-expanded-range-v1.json"
OLD = ROOT / "benchmarks/results/preflop-target-plan-prototype-v1.json"
OUTPUT = ROOT / "benchmarks/results/preflop-grouped-target-plan-v1.json"


def _paths():
    return tuple(dict.fromkeys((*expanded._manifest_paths(),
        "scripts/benchmark_preflop_nonnegative_normalization.py",
        "scripts/preflop_target_plan_prototype.py", "tests/test_preflop_target_plan_prototype.py",
        "benchmarks/results/preflop-expanded-range-v1.json",
        "benchmarks/results/preflop-target-plan-prototype-v1.json",
        "scripts/benchmark_preflop_grouped_target_plan.py",
        "benchmarks/preflop-grouped-target-plan-v1.json")))


def _run(spec, game, checkpoint, candidate, *, trace=False, label="", expected_budget=None):
    kwargs = weighted._solve_kwargs(game, checkpoint)
    plan = identity = metadata = None
    calls = 0
    original = public_cfr._cfrplus_target_deltas

    def target(root, edges, infos, current, player, counts, half_pot, chance_type):
        nonlocal plan, identity, metadata, calls
        current_identity = (id(root), id(edges), id(infos), tuple(counts), half_pot, chance_type)
        if plan is None:
            plan = compile_target_plan(root, edges, infos, counts, half_pot, chance_type)
            identity = current_identity
            metadata = dict(plan.metadata)
        if identity != current_identity:
            raise AssertionError("Plan inputs changed during a complete solver call")
        calls += 1
        return plan.target_deltas(current, player)

    print(f"starting {label}", flush=True)
    with patch.object(public_cfr, "_cfrplus_target_deltas", target if candidate else original):
        gc.collect()
        if trace:
            tracemalloc.start()
        start = time.perf_counter()
        try:
            result = preflop_solver.solve_preflop(game["sb_range"], game["bb_range"], **kwargs)
            payload = json.dumps(result, allow_nan=False, separators=(",", ":"))
        finally:
            # Compilation, retained-plan lifetime through JSON, and release are timed.
            plan = identity = None
            elapsed = time.perf_counter() - start
            peak = None
            if trace:
                _current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
    if candidate and calls != 2 * checkpoint["iterations"]:
        raise AssertionError("Expected exactly two target passes per requested sweep")
    oracle_spec = {**game, "sb": game["sb_range"], "bb": game["bb_range"],
                   "expected_worlds": game["expected_physical_worlds"]}
    checked = verify(result, oracle_spec, weighted._options(game))
    posterior = weighted._assert_report_pair_posteriors(result, checked, weighted._independent_pair_audit(game))
    budget = result["vector_work_budget"]
    if budget["iterations"] != checkpoint["iterations"]:
        raise AssertionError("Full requested iteration count was not admitted")
    if budget["total_loop_entries_upper_bound"] != expected_budget:
        raise AssertionError("Actual original-world budget differs from preflight")
    gap = checked["configured_replay"]["nash_conv"]
    row = {"candidate": candidate, **checkpoint, "complete_call_plus_json_seconds": elapsed,
        "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(), "payload_bytes": len(payload.encode()),
        "nash_conv": gap, "target_met": gap + spec["target_padding"] <= spec["target_nash_conv"],
        "metric_absolute_gaps": checked["metric_absolute_gaps"], "replay_metrics": checked["configured_replay"],
        "checked_information_sets": checked["configured_replay"]["checked_information_sets"],
        "posterior_audit": posterior, "vector_budget_excluding_prototype": budget,
        "plan_metadata": metadata, "target_delta_calls": calls if candidate else None}
    if trace:
        row["traced_peak_bytes"] = peak
    del result, payload, checked
    print(f"finished {label}; seconds={elapsed:.6f}; gap={gap:.12g}; target={row['target_met']}", flush=True)
    return row


def main():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    game = json.loads(GAME.read_text(encoding="utf-8"))
    prior = json.loads(PRIOR.read_text(encoding="utf-8"))
    revision = weighted.git_revision(None)
    if not re.fullmatch(r"[0-9a-f]{40}", revision or "") or weighted.worktree_dirty() is not False:
        raise RuntimeError("Freeze source/spec in a clean commit before measurement")
    if (spec["game_spec"] != GAME.relative_to(ROOT).as_posix()
            or spec["verified_game_report"] != PRIOR.relative_to(ROOT).as_posix()
            or spec["previous_plan_report"] != OLD.relative_to(ROOT).as_posix()):
        raise ValueError("Declared experiment provenance paths differ")
    if (spec["checkpoint"] != {"iterations": 1000, "delay": 500}
            or spec["allocation_checkpoint"] != {"iterations": 10, "delay": 5}
            or spec["pair_order"] != ["baseline", "candidate", "candidate", "baseline", "baseline", "candidate"]):
        raise ValueError("This harness implements only the fixed three-pair plan")
    if spec["target_nash_conv"] != game["target_nash_conv"] or spec["target_padding"] != game["target_padding"]:
        raise ValueError("Quality target differs from the verified game")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", prior["source_revision"], revision],
                              cwd=ROOT, capture_output=True, check=False)
    if ancestor.returncode != 0:
        raise ValueError("Verified game source is not an ancestor of this frozen revision")
    hashes = expanded._hashes(_paths())
    for path, digest in prior["source_hashes"].items():
        if weighted.file_sha256(ROOT / path) != digest:
            raise ValueError(f"Verified-game source changed: {path}")
    anchor = next(r for r in prior["results"] if r["iterations"] == 1000)
    if not anchor["target_met"] or anchor["verification"]["worlds"] != 91080:
        raise ValueError("Prior full-world quality anchor is unavailable")
    pair_audit = weighted._independent_pair_audit(game)
    blockers = expanded._extra_card_audit(game)
    admissions = []
    for checkpoint in (spec["checkpoint"], spec["allocation_checkpoint"]):
        admission = weighted._preflight(game, checkpoint)
        admissions.append({**checkpoint, **admission})
    if any(a["status"] != "admitted" for a in admissions):
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps({"benchmark_id": spec["benchmark_id"], "source_revision": revision,
            "source_hashes": hashes, "specification": spec, "preflight": admissions,
            "timing_arms": [], "experiment_gate_met": False,
            "failures": ["Frozen complete-call fixture rejected before experiment"]}, indent=2) + "\n", encoding="utf-8")
        raise RuntimeError("Preflight rejection saved before any solver call")
    rows = []
    for index, arm in enumerate(spec["pair_order"]):
        row = _run(spec, game, spec["checkpoint"], arm == "candidate", label=f"timing {index + 1}/6 {arm}",
                   expected_budget=admissions[0]["combined_modeled_loop_entries"])
        rows.append({"pair": index // 2 + 1, **row})
    pairs = []
    for index in range(3):
        first, second = rows[2 * index:2 * index + 2]
        baseline, candidate = (second, first) if first["candidate"] else (first, second)
        pairs.append({"pair": index + 1, "baseline_seconds": baseline["complete_call_plus_json_seconds"],
            "candidate_seconds": candidate["complete_call_plus_json_seconds"],
            "payload_exact": baseline["payload_sha256"] == candidate["payload_sha256"],
            "baseline_target_met": baseline["target_met"], "candidate_target_met": candidate["target_met"]})
    allocation = [_run(spec, game, spec["allocation_checkpoint"], candidate,
        trace=True, label=f"allocation {'candidate' if candidate else 'baseline'}",
        expected_budget=admissions[1]["combined_modeled_loop_entries"]) for candidate in (False, True)]
    gate = _promotion_status(spec, rows, pairs, allocation)
    gate["experiment_gate_met"] = gate.pop("promotion_gate_met")
    if hashes != expanded._hashes(_paths()) or weighted.git_revision(None) != revision or weighted.worktree_dirty() is not False:
        raise RuntimeError("Frozen source/spec/revision changed during experiment")
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "source_revision": revision,
        "worktree_dirty_at_start": False, "source_hashes": hashes, "specification": spec,
        "python": platform.python_version(), "platform": platform.platform(),
        "independent_rational_pair_audit": pair_audit, "full_blocker_audit": blockers,
        "preflight": admissions, "timing_arms": rows, "paired_results": pairs,
        "allocation_arms": allocation, **gate,
        "admission_scope": "Standalone prototype record/reference caps apply before compilation; existing production vector_work_budget does not charge prototype census, compilation, retained records or partition/conversion overlap. No production integration is authorized by this experiment gate. A separate independent versioned workload/allocation envelope is required before any adoption. No existing cap is relaxed.",
        "timing_scope": "Three alternating complete solves plus JSON, including first-call census/compile and plan release. Patch contexts, runout preparation and GC precede timing. Plan is retained through final diagnostics/JSON. Independent original-world replay follows timing. Policies are released between arms.",
        "allocation_scope": "Separate 10/delay5 complete calls plus JSON and plan release under tracemalloc. These are Python-traced allocations, not RSS or high-iteration memory. Target misses remain visible.",
        "interpretation": "New fixed grouped flop-checkdown workload, not a rerun or replacement of the earlier failed 20-sweep all-streets plan test. Exact full payload parity, independent legal best responses, all-three-pair direction, 5% median reduction and separate 1.01x peak gate are required. No general speedup or full-game convergence claim.",
        "model_limits": game["model_limits"]}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"saved {OUTPUT}; median={gate['median_reduction']:.4%}; gate={gate['experiment_gate_met']}", flush=True)
    if gate["failures"]:
        raise AssertionError("Report saved with failed gates: " + "; ".join(gate["failures"]))

if __name__ == "__main__":
    main()
