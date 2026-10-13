"""Fixed preflight/quality matrix for larger flop betting in a finite checkdown game.

All nine cases are preflighted before any training. Each admitted case gets one
complete solve plus JSON serialization; timing is descriptive, not comparative.
"""
from __future__ import annotations
import gc, json, platform, re, time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = Path(__file__).resolve()
SPEC_PATH = ROOT / "benchmarks/preflop-flop-raise-coverage-v1.json"
OUTPUT = ROOT / "benchmarks/results/preflop-flop-raise-coverage-v1.json"
from pokerlab import preflop_solver as solver
from scripts.benchmark_preflop_flop_checkdown import futures, verify, SOURCES
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty

class _PreflightComplete(Exception): pass

def _source_paths():
    extra = ("scripts/benchmark_preflop_flop_raise_coverage.py",
        "scripts/benchmark_preflop_flop_checkdown.py", "scripts/preflop_validation.py",
        "scripts/benchmark_preflop_two_flops.py", "scripts/benchmark_turn_solver.py",
        "scripts/cfr_quality.py", "tests/test_preflop_delayed_cfrplus.py",
        "tests/test_preflop_flop_checkdown.py", "tests/test_preflop_future_groups.py",
        "tests/test_preflop_future_indexing.py", "benchmarks/preflop-flop-checkdown-v1.json",
        "benchmarks/preflop-flop-raise-coverage-v1.json")
    return tuple(dict.fromkeys((*SOURCES, *extra)))

def _options(spec, stack):
    return {"config": {"starting_stack": stack, **spec["preflop_config"]},
        "runouts": futures(spec["physical_outcomes"]["flops"]),
        "flop_config": spec["flop_config"], "postflop_scope": spec["postflop_scope"]}

def _solve_kwargs(spec, options, checkpoint):
    return dict(options, iterations=checkpoint["iterations"], averaging_delay=checkpoint["delay"],
        algorithm=spec["algorithm"], traversal=spec["traversal"], diagnostics=spec["diagnostics"],
        resource_model=spec["resource_model"], future_indexing=spec["future_indexing"])

def preflight_case(spec, stack, checkpoint):
    kwargs = _solve_kwargs(spec, _options(spec, stack), checkpoint)
    captured = {"vector": None, "grouping": None, "tree": None, "allocation_called": False}
    real_vector, real_grouping = solver.estimate_vector_budget, solver.estimate_future_grouping
    real_merge = solver._merge_preflop_tree
    def capture_tree(*args, **kw):
        value = real_merge(*args, **kw)
        captured["tree"] = {"public_states":value[1], "decisions":value[2],
                            "maximum_template_states":value[5],
                            "maximum_template_decisions":value[6]}
        return value
    def capture_vector(*args, **kw):
        value = real_vector(*args, **kw)
        if captured["vector"] is not None: raise AssertionError("unexpected repeated vector estimate")
        captured["vector"] = value
        return value
    def capture_grouping(worlds):
        value = real_grouping(worlds); captured["grouping"] = value; return value
    def stop_before_group_allocation(_worlds): raise _PreflightComplete
    def forbidden(*_args, **_kwargs):
        captured["allocation_called"] = True
        raise AssertionError("preflight entered grouping/training allocation")
    try:
        with patch.object(solver, "_merge_preflop_tree", capture_tree), \
             patch.object(solver, "estimate_vector_budget", capture_vector), \
             patch.object(solver, "estimate_future_grouping", capture_grouping), \
             patch.object(solver, "group_hidden_futures", stop_before_group_allocation), \
             patch.object(solver, "_positive_pot_training_view", forbidden), \
             patch.object(solver, "train_delayed_public_cfrplus", forbidden):
            solver.solve_preflop(spec["sb"], spec["bb"], **kwargs)
    except _PreflightComplete:
        if captured["vector"] is None or captured["grouping"] is None:
            raise AssertionError("preflight stopped before both admission estimates")
        status, reason = "admitted", None
    except ValueError as exc:
        if not any(word in str(exc).lower() for word in ("cap", "limit", "exceed", "bound")):
            raise
        status, reason = "rejected", str(exc)
    else:
        raise AssertionError("preflight returned without reaching guarded grouping point")
    if captured["allocation_called"]: raise AssertionError("preflight entered an allocation/trainer")
    vector, grouping = captured["vector"], captured["grouping"]
    combined = (vector["total_loop_entries_upper_bound"] + grouping["grouping_loop_entries_upper_bound"]
                if vector is not None and grouping is not None else None)
    return {"starting_stack": stack, **checkpoint, "status": status, "rejection": reason,
        "world_count": vector["world_count"] if vector else None,
        "public_prefixes": vector["public_prefixes"] if vector else None,
        "decision_nodes": vector["decision_nodes"] if vector else None,
        "information_sets": vector["information_sets"] if vector else None,
        "tree_counts":captured["tree"],
        "vector_work_budget": vector, "grouping_budget": grouping,
        "combined_modeled_loop_entries": combined,
        "grouping_or_training_allocation_called": captured["allocation_called"]}

def _coverage(rows):
    # Independent replay has checked every reachable row and action. Count flop
    # actions only, so a preflop raise cannot falsely certify flop coverage.
    names = {"check": 0, "call": 0, "bet": 0, "raise": 0, "all_in": 0}
    opening_bets = set()
    for row in rows:
        if row["street"] != "flop":
            continue
        history = row["history"]
        limp_check_root = (len(history) == 3 and history[:2] == ["call", "check"] and
                           history[2].startswith("flop@") and row["player"] == "bb")
        for action in row["actions"]:
            if action["name"] in names:
                names[action["name"]] += 1
            if limp_check_root and action["name"] == "bet":
                opening_bets.add(action["amount"])
    return {"serialized_flop_action_rows_by_name": names,
            "limp_check_root_flop_bet_amounts": sorted(opening_bets),
            "union_has_check_call_bet_raise_all_in": all(names.values()),
            "union_has_both_requested_flop_bet_amounts": all(x in opening_bets for x in (1.0, 2.0))}


def _merge_coverage(coverages):
    names = {key:sum(c["serialized_flop_action_rows_by_name"][key] for c in coverages)
             for key in ("check", "call", "bet", "raise", "all_in")}
    bets = sorted({x for c in coverages for x in c["limp_check_root_flop_bet_amounts"]})
    return {"serialized_flop_action_rows_by_name":names,
            "limp_check_root_flop_bet_amounts":bets,
            "union_has_check_call_bet_raise_all_in":all(names.values()),
            "union_has_both_requested_flop_bet_amounts":all(x in bets for x in (1.0, 2.0))}


def main():
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8")); revision, dirty = git_revision(None), worktree_dirty()
    if dirty is not False or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise RuntimeError("Freeze repository source/spec in a clean commit before running.")
    paths = _source_paths(); hashes = {p: file_sha256(ROOT / p) for p in paths}
    spec_hash, script_hash = file_sha256(SPEC_PATH), file_sha256(SCRIPT_PATH)
    if any(not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h)
           for h in (*hashes.values(), spec_hash, script_hash)):
        raise RuntimeError("Source/spec hash unavailable.")
    cases = [(s, c) for s in spec["matrix"]["starting_stacks"] for c in spec["matrix"]["checkpoints"]]
    if len(cases) != spec["matrix"]["cases"]: raise ValueError("Frozen matrix case count mismatch")
    print("Preflighting every matrix case before training", flush=True); admissions = []
    for i, (stack, checkpoint) in enumerate(cases, 1):
        print(f"  preflight {i}/{len(cases)} stack={stack} {checkpoint}", flush=True)
        row = preflight_case(spec, stack, checkpoint); admissions.append(row)
        print(f"    {row['status']}: {row['rejection'] or row['combined_modeled_loop_entries']}", flush=True)
    results, coverages = [], []
    oracle_spec = dict(spec, expected_worlds=spec["physical_outcomes"]["compatible_physical_worlds"],
        expected_selected_outcomes=spec["physical_outcomes"]["ordered_future_candidates"])
    for i, ((stack, checkpoint), admission) in enumerate(zip(cases, admissions), 1):
        if admission["status"] == "rejected":
            results.append({"starting_stack": stack, **checkpoint, "status": "rejected",
                "rejection": admission["rejection"], "preflight": admission}); continue
        options = _options(spec, stack); kwargs = _solve_kwargs(spec, options, checkpoint)
        print(f"Training admitted case {i}/{len(cases)} stack={stack} {checkpoint}", flush=True)
        gc.collect(); start = time.perf_counter()
        result = solver.solve_preflop(spec["sb"], spec["bb"], **kwargs)
        serialized = json.dumps(result, allow_nan=False); elapsed = time.perf_counter() - start
        checked = verify(result, oracle_spec, options)
        if result.get("future_indexing") != "flop-sign": raise AssertionError("Expected grouped training view")
        if result["vector_work_budget"]["total_loop_entries_upper_bound"] != admission["combined_modeled_loop_entries"]:
            raise AssertionError("Actual solve admission differs from preflight")
        coverage = _coverage(result["strategy"])
        coverages.append(coverage)
        target = checked["configured_replay"]["nash_conv"] + spec["target_padding"] <= spec["target_nash_conv"]
        results.append({"starting_stack": stack, **checkpoint, "status": "completed",
            "complete_call_seconds": elapsed, "serialized_json_bytes": len(serialized.encode()),
            "target_nash_conv": spec["target_nash_conv"], "target_met": target,
            "preflight": admission, "verification": checked, "action_coverage":coverage,
            "future_indexing_metadata":result["future_indexing_metadata"]})
        print(f"  independent gap={checked['configured_replay']['nash_conv']:.12g}; target={target}; seconds={elapsed:.3f}", flush=True)
        del result, serialized
    coverage = _merge_coverage(coverages)
    if hashes != {p: file_sha256(ROOT / p) for p in paths}: raise RuntimeError("Source/spec hash changed")
    if spec_hash != file_sha256(SPEC_PATH) or script_hash != file_sha256(SCRIPT_PATH): raise RuntimeError("Harness/spec hash changed")
    if git_revision(None) != revision or worktree_dirty() is not False: raise RuntimeError("Repository changed during run")
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "source_revision": revision,
        "worktree_dirty_at_start": False, "source_hashes": hashes, "benchmark_script_sha256": script_hash,
        "benchmark_script_location": SCRIPT_PATH.relative_to(ROOT).as_posix(), "configuration_sha256": spec_hash,
        "specification": spec, "python": platform.python_version(), "platform": platform.platform(),
        "preflight": admissions, "results": results, "action_coverage": coverage,
        "action_coverage_note": "Coverage is reported across the admitted matrix, not asserted per individual case; capped/deduplicated sizes may remove actions.",
        "timing_scope": "One descriptive complete solve plus JSON per admitted case on one host. Includes physical enumeration/ranking, tree construction, original-world admission, grouping, training and exact diagnostics. Preallocated runouts, pre-call GC and independent replay excluded. No speedup comparison.",
        "quality_scope": "Every admitted case is independently replayed over original physical worlds with numeric poker rules and exact visible-information best responses. All misses and preflight rejections remain visible. The 0.005-chip target is per checkpoint in this finite fixture, not a general convergence claim.",
        "provenance": "Fixed action/stack coverage extension of this repository game. Luna drafted the isolated benchmark/spec; lead reviewed, narrowed action coverage to independently checked flop rows, preserved rejection reports and froze/measured the full matrix. No production, shared postflop/turn/river kernel, Coach, third-party source or dependency changes.",
        "admission_scope": "All nine configurations are preflighted before training. Group allocation, training-view construction and trainer entry are forbidden during preflight. Existing caps are unchanged; no rejected case is simplified or retried.",
        "model_limits": spec["model_limits"]}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True); OUTPUT.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    # Preserve the full matrix, including an all-rejected outcome, before
    # treating absent intended action coverage as an experiment failure.
    if not coverage["union_has_check_call_bet_raise_all_in"] or not coverage["union_has_both_requested_flop_bet_amounts"]:
        raise AssertionError(f"Report saved, but intended flop action coverage missing: {coverage}")
    print(f"saved {OUTPUT}; admitted={sum(x['status']=='admitted' for x in admissions)}/{len(admissions)}", flush=True)

if __name__ == "__main__": main()
