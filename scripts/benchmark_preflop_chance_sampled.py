"""Frozen finite-game sampling measurements with exact independent diagnostics."""
from datetime import datetime, timezone
import gc
from itertools import permutations
import json
from pathlib import Path
import platform
import time
import tracemalloc

from pokerlab.preflop_solver import solve_preflop
from pokerlab.preflop_sampled_cfr import train_chance_sampled
from pokerlab.postflop_solver import _chance_child, _node_key
from pokerlab.river_tree import _terminal_value
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty
from scripts.cfr_quality import build_kuhn_adapter, check_metrics
from scripts.preflop_validation import compare_result, replay_policy

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/preflop-chance-sampled-v1.json"
OUTPUT = ROOT / "benchmarks/results/preflop-chance-sampled-v1.json"
SOURCES = tuple(sorted(str(p.relative_to(ROOT)).replace("\\", "/")
                       for p in (ROOT / "pokerlab").glob("*.py"))) + (
    "scripts/benchmark_preflop_chance_sampled.py", "scripts/preflop_validation.py",
    "scripts/cfr_quality.py", "scripts/benchmark_turn_solver.py",
    "tests/test_preflop_sampled_cfr.py", "tests/test_preflop_sampled_budget.py",
    "tests/test_preflop_sampled_storage.py", "tests/test_preflop_sampled_integration.py")


def verify(result, game):
    oracle = replay_policy(result, game["sb"], game["bb"], **game["kwargs"])
    differences = compare_result(result, oracle)
    assert oracle["checked_information_sets"] == len(result["strategy"])
    actual = {(r["sb_hand"], r["bb_hand"]): r["probability"]
              for r in result["private_pair_probabilities"]}
    expected = {(r["sb"], r["bb"]): r["probability"]
                for r in oracle["private_pair_probabilities"]}
    assert actual.keys() == expected.keys()
    assert max(abs(actual[k]-expected[k]) for k in actual) < 1e-12
    return oracle, differences


def main():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    hashes = {path:file_sha256(ROOT/path) for path in SOURCES}
    spec_hash = file_sha256(SPEC)
    prior_path = ROOT/spec["historical_reference"]
    prior_hash = file_sha256(prior_path)
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    revision, dirty = git_revision(None), worktree_dirty()
    if dirty:
        raise RuntimeError("Freeze benchmark source in a clean commit before measuring.")
    full = spec["full_flop"]
    flop = tuple(full["flop"])
    deck = [r+s for r in "23456789TJQKA" for s in "cdhs" if r+s not in flop]
    selected = spec["selected_game"]
    games = {
        "complete_fixed_flop": dict(full, kwargs={"config":full["config"],
            "runouts":tuple(flop+future for future in permutations(deck,2))}),
        "weighted_selected_flops": dict(selected, kwargs={k:selected[k] for k in
            ("config", "runouts", "flop_config")}),
    }
    records = []
    for name, game in games.items():
        for iterations in game["iterations"]:
            for seed in spec["seeds"]:
                print(f"{name} iterations={iterations} seed={seed}: start",flush=True)
                gc.collect()
                start=time.perf_counter()
                result=solve_preflop(game["sb"],game["bb"],**game["kwargs"],
                    iterations=iterations,algorithm="vanilla",traversal="chance-sampled",
                    diagnostics="public-batched",resource_model="chance-sampled",
                    samples_per_iteration=game["samples_per_iteration"],sampling_seed=seed)
                json.dumps(result)
                seconds=time.perf_counter()-start
                oracle,differences=verify(result,game)
                if name=="complete_fixed_flop":
                    assert result["worlds"]==full["worlds"]
                    assert result["info_sets"]==full["information_sets"]
                record={"game":name,"iterations":iterations,"seed":seed,
                    "complete_call_seconds":seconds,"worlds":result["worlds"],
                    "information_sets":result["info_sets"],
                    "sampling_statistics":result["sampling_statistics"],
                    "sampled_work_budget":result["sampled_work_budget"],
                    "sampler_storage_budget":result["sampler_storage_budget"],
                    "exact_diagnostics_admission_reference":result["exact_diagnostics_admission_reference"],
                    "configured_replay":oracle,"metric_absolute_gaps":differences,
                    "target_nash_conv":game["target_nash_conv"],
                    "target_met":oracle["nash_conv"]<=game["target_nash_conv"],
                    "padded_value_interval":[-oracle["bb_best_response_value"]-1e-10,
                                             oracle["sb_best_response_value"]+1e-10]}
                records.append(record)
                print(f"  seconds={seconds:.3f} exact_gap={oracle['nash_conv']:.9g} target_met={record['target_met']}",flush=True)
                del result
    known=[]
    adapter=build_kuhn_adapter()
    payoff=lambda terminal,world:_terminal_value(terminal,world[3],adapter["config"].pot)
    for iterations in spec["kuhn"]["iterations"]:
        for seed in spec["seeds"]:
            profile,stats=train_chance_sampled(adapter["root"],adapter["worlds"],
                adapter["infos"],iterations,payoff,_node_key,_chance_child,seed=seed)
            metrics=check_metrics(profile,layout=adapter["layout"])
            assert metrics["nash_conv"]<=spec["kuhn"]["target_nash_conv"]
            assert metrics["value_error"]<=spec["kuhn"]["target_value_error"]
            known.append({"iterations":iterations,"seed":seed,"metrics":metrics,"sampling_statistics":stats})
    # A separate complete call, including final exact BR and serialization.
    # Its lower iteration count is explicit; no high-iteration RSS bound follows.
    game=games["complete_fixed_flop"]
    gc.collect();tracemalloc.start()
    try:
        measured=solve_preflop(game["sb"],game["bb"],**game["kwargs"],
            iterations=full["memory_iterations"],algorithm="vanilla",traversal="chance-sampled",
            diagnostics="public-batched",resource_model="chance-sampled",
            samples_per_iteration=full["samples_per_iteration"],sampling_seed=spec["seeds"][0])
        json.dumps(measured)
        current,peak=tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    oracle,differences=verify(measured,game)
    memory={"iterations":full["memory_iterations"],"seed":spec["seeds"][0],
        "current_traced_python_bytes":current,"peak_traced_python_bytes":peak,
        "scope":"Separate complete full-fixed-flop call through exact diagnostics and JSON serialization; excludes independent replay, interpreter/native allocations and process RSS. Not a high-iteration allocation guarantee.",
        "sampling_statistics":measured["sampling_statistics"],
        "configured_replay":oracle,"metric_absolute_gaps":differences}
    assert hashes=={path:file_sha256(ROOT/path) for path in SOURCES}
    assert spec_hash==file_sha256(SPEC) and prior_hash==file_sha256(prior_path)
    report={"benchmark_id":spec["benchmark_id"],"created_at":datetime.now(timezone.utc).isoformat(),
        "source_revision":revision,"worktree_dirty_at_start":dirty,"source_sha256":hashes,
        "specification_sha256":spec_hash,"specification":spec,
        "environment":{"platform":platform.platform(),"python":platform.python_version()},
        "timing_scope":"One complete uninstrumented call per seed/checkpoint, including JSON serialization; excludes pre-call GC and independent oracle. Seed variation is algorithmic, not repeated timing evidence or a controlled speed comparison.",
        "historical_reference":{"path":spec["historical_reference"],"sha256":prior_hash,
            "source_revision":prior["source_revision"],
            "scope":"Frozen prior delayed exact CFR+ accuracy reference only; no new timing comparison or equal-work claim."},
        "records":records,"known_kuhn":known,"whole_call_memory":memory}
    OUTPUT.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(f"wrote {OUTPUT}",flush=True)


if __name__=="__main__":
    main()
