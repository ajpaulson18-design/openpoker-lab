"""Frozen two-flop coverage and exact delayed-CFR+ work measurements."""
from datetime import datetime, timezone
import gc
from itertools import permutations
import json
from pathlib import Path
import platform
import statistics
import time
import tracemalloc
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty
from scripts.preflop_validation import compare_result, replay_policy
from tests.test_preflop_delayed_cfrplus import _frozen_original_adapter

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/preflop-two-complete-flops-v1.json"
OUTPUT = ROOT / "benchmarks/results/preflop-two-complete-flops-v1.json"
SOURCES = tuple(sorted(str(p.relative_to(ROOT)).replace("\\", "/")
                       for p in (ROOT / "pokerlab").glob("*.py"))) + (
    "scripts/benchmark_preflop_two_flops.py", "scripts/preflop_validation.py",
    "scripts/benchmark_turn_solver.py", "tests/test_preflop_delayed_cfrplus.py",
    "tests/test_preflop_tree_admission.py", "tests/test_preflop_vector_budget.py")


def futures(flops):
    deck = [r+s for r in "23456789TJQKA" for s in "cdhs"]
    return tuple(tuple(flop)+future for flop in flops
                 for future in permutations([c for c in deck if c not in flop], 2))


def verify(result, spec, kwargs):
    oracle = replay_policy(result, spec["sb"], spec["bb"], **kwargs)
    differences = compare_result(result, oracle)
    assert oracle["checked_information_sets"] == len(result["strategy"])
    actual = {(r["sb_hand"], r["bb_hand"]): r["probability"]
              for r in result["private_pair_probabilities"]}
    expected = {(r["sb"], r["bb"]): r["probability"]
                for r in oracle["private_pair_probabilities"]}
    assert actual.keys() == expected.keys()
    assert max(abs(actual[k]-expected[k]) for k in actual) < 1e-12
    return {"configured_replay": oracle, "metric_absolute_gaps": differences,
            "padded_value_interval": [-oracle["bb_best_response_value"]-1e-10,
                                      oracle["sb_best_response_value"]+1e-10]}


def original(root, worlds, infos, iterations, *, averaging_delay, pot, chance_type):
    return _frozen_original_adapter(root, worlds, infos, iterations, averaging_delay,
                                    pot=pot, chance_type=chance_type)


def solve(spec, kwargs, iterations, delay, baseline=False, expanded=False):
    trainer = original if baseline else solver.train_delayed_public_cfrplus
    estimator = solver.estimate_vector_budget

    def admission(*args, **kwargs):
        if baseline:
            # Frozen adapter still executes all zero-weight averages and three
            # whole-profile rematches. Use its unchanged conservative v1 bound.
            kwargs.pop("averaging_delay", None)
        return estimator(*args, **kwargs)

    with patch.object(solver, "train_delayed_public_cfrplus", trainer), \
            patch.object(solver, "estimate_vector_budget", admission):
        return solver.solve_preflop(spec["sb"], spec["bb"], **kwargs,
            iterations=iterations, averaging_delay=delay, algorithm="cfrplus",
            traversal="public-batched", diagnostics="public-batched",
            resource_model="public-vector",
            tree_admission="vector" if expanded else "decision-count")


def main():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    hashes = {path:file_sha256(ROOT/path) for path in SOURCES}
    spec_hash = file_sha256(SPEC)
    prior_path = ROOT/spec["historical_reference"]
    prior_hash = file_sha256(prior_path)
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    revision, dirty = git_revision(None), worktree_dirty()
    if dirty:
        raise RuntimeError("Freeze source/spec in a clean commit before measuring.")
    fixed = {"config":spec["config"], "runouts":futures(spec["flops"][:1])}
    both = {"config":spec["config"], "runouts":futures(spec["flops"])}
    timing = spec["paired_timing"]
    pairs = []
    for index in range(timing["pairs"]):
        order = (False, True) if index % 2 else (True, False)
        profiles = {}
        seconds = {}
        budgets = {}
        for baseline in order:
            label = "original" if baseline else "optimized"
            print(f"paired fixed-flop timing {index+1}: {label} start", flush=True)
            gc.collect()
            start = time.perf_counter()
            result = solve(spec, fixed, timing["iterations"], timing["delay"], baseline)
            json.dumps(result)
            seconds[label] = time.perf_counter()-start
            profiles[label] = result["strategy"]
            budgets[label] = result["vector_work_budget"]
            if not baseline:
                check = verify(result, spec, fixed)
        assert profiles["original"] == profiles["optimized"]
        pairs.append({"pair":index+1, "order":["original" if b else "optimized" for b in order],
                      "seconds":seconds, "admission_budgets":budgets, "policy_exactly_equal":True,
                      "independent_optimized_verification":check})
        print(f"  pair seconds: {seconds}", flush=True)
        del result, profiles
    regress = spec["fixed_flop_regression"]
    print("fixed-flop historical accuracy regression start",flush=True)
    gc.collect()
    start=time.perf_counter()
    result=solve(spec,fixed,regress["iterations"],regress["delay"])
    json.dumps(result)
    elapsed=time.perf_counter()-start
    check=verify(result,spec,fixed)
    old=next(r for r in prior["records"] if r["averaging_delay"]==regress["delay"])
    assert abs(check["configured_replay"]["nash_conv"]-old["configured_replay"]["nash_conv"]) < 1e-12
    fixed_record={"iterations":regress["iterations"],"delay":regress["delay"],
                  "complete_call_seconds":elapsed,"historical_accuracy_preserved":True,
                  "vector_work_budget":result["vector_work_budget"],**check}
    del result
    records=[]
    for checkpoint in spec["checkpoints"]:
        print(f"two complete flop futures {checkpoint}: start",flush=True)
        gc.collect()
        start=time.perf_counter()
        result=solve(spec,both,checkpoint["iterations"],checkpoint["delay"],expanded=True)
        json.dumps(result)
        elapsed=time.perf_counter()-start
        assert result["worlds"]==spec["worlds"]
        assert result["info_sets"]==spec["information_sets"]
        assert result["decisions"]>10000
        check=verify(result,spec,both)
        gap=check["configured_replay"]["nash_conv"]
        records.append({**checkpoint,"complete_call_seconds":elapsed,"worlds":result["worlds"],
                        "public_states":result["public_states"],"decisions":result["decisions"],
                        "information_sets":result["info_sets"],"selected_outcomes":len(both["runouts"]),
                        "reachable_outcomes":len(result["reachable_runouts"]),
                        "private_pair_probabilities":result["private_pair_probabilities"],
                        "vector_work_budget":result["vector_work_budget"],
                        "target_nash_conv":spec["target_nash_conv"],
                        "target_met":gap+1e-10<=spec["target_nash_conv"],**check})
        print(f"  exact gap={gap:.12g}; target met={records[-1]['target_met']}; seconds={elapsed:.3f}",flush=True)
        del result
    memory=spec["memory"]
    print("separate two-flop complete-call memory measurement start",flush=True)
    gc.collect()
    tracemalloc.start()
    try:
        result=solve(spec,both,memory["iterations"],memory["delay"],expanded=True)
        json.dumps(result)
        _,peak=tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    memory_record={**memory,"complete_peak_traced_python_bytes":peak,**verify(result,spec,both)}
    assert hashes=={path:file_sha256(ROOT/path) for path in SOURCES}
    assert spec_hash==file_sha256(SPEC)
    assert prior_hash==file_sha256(prior_path)
    medians={label:statistics.median(p["seconds"][label] for p in pairs)
             for label in ("original","optimized")}
    report={"schema_version":1,"benchmark_id":spec["benchmark_id"],
            "generated_at":datetime.now(timezone.utc).isoformat(),"source_revision":revision,
            "worktree_dirty_at_start":dirty,"source_hashes":hashes,"configuration_sha256":spec_hash,
            "specification":spec,"python":platform.python_version(),"platform":platform.platform(),
            "paired_fixed_flop_timings":pairs,"paired_timing_medians":medians,
            "observed_paired_median_ratio":medians["original"]/medians["optimized"],
            "fixed_flop_regression":fixed_record,"records":records,"memory":memory_record,
            "historical_reference":{"path":spec["historical_reference"],"sha256":prior_hash,
                                    "source_revision":prior["source_revision"]},
            "method_source":"https://arxiv.org/pdf/1407.5042",
            "provenance":"Independent same-repository CFR+ implementation; selective rematching and zero-weight traversal removal preserve completed-sweep own-reach delayed linear averages. Frozen original adapter in tests is our own prior implementation, not third-party source. No dependencies added.",
            "timing_scope":"Three alternating pairs of complete fixed-flop solve plus JSON calls on one shared host, at 40 iterations/delay20. Both use current orchestration with adapter and its conservative admission estimate swapped: baseline uses v1 and executes 3T traversals; optimized uses delayed v2 and executes 3T-D. Each includes its own preflight. Independent replay and pre-call GC excluded. Report observed medians only, not universal speed or equal-time convergence. Broader checkpoints and historical160 regression are single calls.",
            "memory_scope":"Separate complete two-flop solve plus JSON at10 iterations/delay5 under tracemalloc. Runout arguments preallocated; independent replay excluded. Python allocations, not RSS/native memory or higher-iteration guarantee.",
            "model_limits":"Conditioned two canonical flops with complete ordered future deals, finite 2-chip heads-up action abstraction, four candidate private pairs. Exact visible-information BR and replay within configured binary64 arithmetic. No full-deck preflop, unrestricted NLHE, multiway or commercial parity claim; shared postflop kernels and AI Coach untouched."}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(f"report saved; memory peak={peak}",flush=True)


if __name__=="__main__":
    main()
