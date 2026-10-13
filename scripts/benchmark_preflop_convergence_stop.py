"""Frozen preflop exact accuracy stopping, complete-call runtime and memory."""
from datetime import datetime, timezone
import gc
import json
from pathlib import Path
import platform
import statistics
import time
import tracemalloc

from pokerlab.preflop_solver import solve_preflop
from scripts.benchmark_preflop_two_flops import futures, verify
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/preflop-convergence-stop-v1.json"
OUTPUT = ROOT / "benchmarks/results/preflop-convergence-stop-v1.json"
SOURCES = tuple(sorted(str(p.relative_to(ROOT)).replace("\\", "/")
                       for p in (ROOT / "pokerlab").glob("*.py"))) + (
    "scripts/benchmark_preflop_convergence_stop.py", "scripts/benchmark_preflop_two_flops.py",
    "scripts/preflop_validation.py", "scripts/benchmark_turn_solver.py",
    "tests/test_preflop_convergence.py", "tests/test_preflop_delayed_cfrplus.py",
    "tests/test_preflop_vector_budget.py", "tests/test_preflop_tree_admission.py")


def solve(game, kwargs, checkpoint, adaptive, expanded=False, iterations=None):
    return solve_preflop(game["sb"],game["bb"],**kwargs,
        iterations=checkpoint["iterations"] if iterations is None else iterations,
        averaging_delay=checkpoint["delay"],algorithm="cfrplus",traversal="public-batched",
        diagnostics="public-batched",resource_model="public-vector",
        tree_admission="vector" if expanded else "decision-count",
        **({"target_nash_conv":checkpoint["target_nash_conv"],
            "convergence_check_interval":checkpoint["interval"]} if adaptive else {}))


def record(result, game, kwargs, checkpoint, seconds=None):
    verification=verify(result,game,kwargs)
    independent_gap=verification["configured_replay"]["nash_conv"]
    adaptive="completed_iterations" in result
    completed=result["completed_iterations"] if adaptive else result["iterations"]
    target_met=independent_gap+1e-10<=checkpoint["target_nash_conv"]
    if adaptive:
        assert target_met==result["convergence_target_reached"]
        assert result["training_regret_passes"]==2*completed
        assert result["training_average_passes"]==max(completed-checkpoint["delay"],0)
        assert result["vector_work_budget"]["iterations"]==checkpoint["iterations"]
    return {"requested_iterations":checkpoint["iterations"],"completed_iterations":completed,
        "delay":checkpoint["delay"],"interval":checkpoint["interval"] if adaptive else None,
        "complete_call_seconds":seconds,"worlds":result["worlds"],"information_sets":result["info_sets"],
        "target_nash_conv":checkpoint["target_nash_conv"],"independent_target_met":target_met,
        "stopped_early":result.get("stopped_early",False),
        "convergence_checkpoints":result.get("convergence_checkpoints",[]),
        "vector_work_budget":result["vector_work_budget"],**verification}


def main():
    spec=json.loads(SPEC.read_text(encoding="utf-8"))
    hashes={path:file_sha256(ROOT/path) for path in SOURCES}
    spec_hash=file_sha256(SPEC)
    prior_path=ROOT/spec["historical_reference"]
    prior_hash=file_sha256(prior_path)
    prior=json.loads(prior_path.read_text(encoding="utf-8"))
    revision,dirty=git_revision(None),worktree_dirty()
    if dirty:
        raise RuntimeError("Freeze source/spec in a clean commit before measuring.")
    fixed={"config":spec["config"],"runouts":futures(spec["flops"][:1])}
    both={"config":spec["config"],"runouts":futures(spec["flops"])}
    checkpoint=spec["paired_fixed_flop"]
    pairs=[]
    reference_checked=False
    for index in range(checkpoint["pairs"]):
        order=(False,True) if index%2==0 else (True,False)
        rows={}
        for adaptive in order:
            label="accuracy-stopped" if adaptive else "fixed-ceiling"
            print(f"pair{index+1}: {label} start",flush=True)
            gc.collect()
            start=time.perf_counter()
            result=solve(spec,fixed,checkpoint,adaptive)
            json.dumps(result)
            seconds=time.perf_counter()-start
            rows[label]=record(result,spec,fixed,checkpoint,seconds)
            if adaptive and not reference_checked:
                # Independent same-completed-iteration algorithm parity, outside
                # timing. A stopped profile is not expected to equal ceiling40.
                exact=solve(spec,fixed,checkpoint,False,
                            iterations=result["completed_iterations"])
                assert exact["strategy"]==result["strategy"]
                rows[label]["fixed_completed_iteration_policy_exactly_equal"]=True
                reference_checked=True
                del exact
            print(f"  completed={rows[label]['completed_iterations']} gap={rows[label]['configured_replay']['nash_conv']:.12g} seconds={seconds:.3f}",flush=True)
            del result
        pairs.append({"pair":index+1,"order":["accuracy-stopped" if a else "fixed-ceiling" for a in order],"records":rows})
    checkpoint=spec["full_game"]
    print("two-flop historical0.005 target: start",flush=True)
    gc.collect()
    start=time.perf_counter()
    result=solve(spec,both,checkpoint,True,expanded=True)
    json.dumps(result)
    seconds=time.perf_counter()-start
    full=record(result,spec,both,checkpoint,seconds)
    exact=solve(spec,both,checkpoint,False,expanded=True,
                iterations=result["completed_iterations"])
    assert exact["strategy"]==result["strategy"]
    full["fixed_completed_iteration_policy_exactly_equal"]=True
    full["historical_ceiling_nash_conv"]=prior["records"][-1]["configured_replay"]["nash_conv"]
    print(f"  completed={full['completed_iterations']} gap={full['configured_replay']['nash_conv']:.12g} target={full['independent_target_met']}",flush=True)
    del result,exact
    selected=spec["unmet_selected"]
    selected_kwargs={k:selected[k] for k in ("config","runouts","flop_config")}
    result=solve(selected,selected_kwargs,selected,True)
    exact=solve(selected,selected_kwargs,selected,False)
    assert exact["strategy"]==result["strategy"]
    assert not result["convergence_target_reached"]
    assert result["completed_iterations"]==selected["iterations"]
    unmet=record(result,selected,selected_kwargs,selected)
    unmet["fixed_ceiling_policy_exactly_equal"]=True
    del result,exact
    checkpoint=spec["memory"]
    print("separate two-flop complete-call allocation trace: start",flush=True)
    gc.collect()
    tracemalloc.start()
    try:
        result=solve(spec,both,checkpoint,True,expanded=True)
        json.dumps(result)
        _,peak=tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    memory=record(result,spec,both,checkpoint)
    memory["complete_peak_traced_python_bytes"]=peak
    assert hashes=={path:file_sha256(ROOT/path) for path in SOURCES}
    assert spec_hash==file_sha256(SPEC)
    assert prior_hash==file_sha256(prior_path)
    medians={label:statistics.median(p["records"][label]["complete_call_seconds"] for p in pairs)
             for label in ("fixed-ceiling","accuracy-stopped")}
    report={"schema_version":1,"benchmark_id":spec["benchmark_id"],"generated_at":datetime.now(timezone.utc).isoformat(),
        "source_revision":revision,"worktree_dirty_at_start":dirty,"source_hashes":hashes,
        "configuration_sha256":spec_hash,"specification":spec,"python":platform.python_version(),
        "platform":platform.platform(),"paired_timings":pairs,"paired_timing_medians":medians,
        "observed_median_ratio":medians["fixed-ceiling"]/medians["accuracy-stopped"],
        "full_game":full,"unmet_selected":unmet,"memory":memory,
        "historical_reference":{"path":spec["historical_reference"],"sha256":prior_hash,"source_revision":prior["source_revision"]},
        "accuracy_scope":"Final policies independently replayed from numeric poker rules, physical posteriors and exact visible-information best responses. Checkpoint history is production exact diagnostics; integration tests independently reconstruct every checkpoint in a smaller weighted game. Same-completed-iteration policy parity is checked separately. Fixed delay remains unchanged when stopping; all misses retained.",
        "timing_scope":"Three alternating paired complete fixed-first-flop40/delay10 calls plus JSON, with requested0.05 accuracy on adaptive calls. Fixed calls always finish ceiling40. Both final policies are independently assessed against the same timing-fixture target; policy accuracy can differ. Pre-call GC, independent replay and extra parity calls excluded. One shared host; no universal speed claim. Core two-flop0.005 target is a separate single complete adaptive call and is not weakened by the timing target.",
        "memory_scope":"Separate complete two-flop10/delay5/interval5 adaptive call plus JSON under tracemalloc, including exact check while trainer state is live. Runout arguments preallocated; independent replay and native/RSS excluded. No high-iteration guarantee or controlled comparison against historical memory.",
        "provenance":"Independent preflop-local checkpoint orchestration around our existing CFR+ and exact diagnostic implementation. Published delay schedule remains completed-sweep own-reach, not verbatim Algorithm1. No third-party source/dependencies; shared postflop/turn/river kernels and AI Coach unchanged.",
        "model_limits":"Conditioned finite heads-up selected-flop betting game. Full requested ceiling and possible snapshots/diagnostics are admitted before training. Target uses a1e-10 numerical guard, not a formal floating-point error bound; targets below that cannot be certified. No full-deck preflop, unrestricted NLHE or multiway claim."}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(f"report saved; traced peak={peak}",flush=True)


if __name__=="__main__":
    main()
