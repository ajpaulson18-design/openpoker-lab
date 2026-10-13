"""Frozen paired complete-call experiment for opt-in hidden-future grouping."""
import gc
import hashlib
import json
import platform
import re
import statistics
import tempfile
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

from scripts.benchmark_preflop_flop_checkdown import futures, solve, verify, SOURCES
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/preflop-hidden-future-groups-v1.json"
OUTPUT = ROOT / "benchmarks/results/preflop-hidden-future-groups-v1.json"


def complete(game, kwargs, checkpoint, grouped):
    options = dict(kwargs, future_indexing="flop-sign") if grouped else kwargs
    result = solve(game, options, checkpoint)
    return result, json.dumps(result, allow_nan=False)


def compare_policies(original, grouped, spec):
    for key in ("worlds", "selected_runouts", "reachable_runouts", "private_pair_probabilities",
                "public_states", "decisions", "info_sets", "postflop_action_configs"):
        if original[key] != grouped[key]:
            raise AssertionError(f"Physical/model output changed: {key}")
    if len(original["strategy"]) != len(grouped["strategy"]):
        raise AssertionError("Policy row count changed")
    max_policy_gap = 0.0
    for a, b in zip(original["strategy"], grouped["strategy"]):
        if {k:v for k,v in a.items() if k != "actions"} != {k:v for k,v in b.items() if k != "actions"}:
            raise AssertionError("Policy identity/order changed")
        if len(a["actions"]) != len(b["actions"]):
            raise AssertionError("Policy action count changed")
        for x, y in zip(a["actions"], b["actions"]):
            if {k:v for k,v in x.items() if k != "probability"} != {k:v for k,v in y.items() if k != "probability"}:
                raise AssertionError("Policy action structure changed")
            max_policy_gap = max(max_policy_gap, abs(x["probability"]-y["probability"]))
    if max_policy_gap > spec["policy_absolute_tolerance"]:
        raise AssertionError(f"Policy drift {max_policy_gap}")
    return {"physical_outputs_and_policy_structure_exactly_equal": True,
            "maximum_policy_probability_absolute_gap": max_policy_gap,
            "policy_absolute_tolerance": spec["policy_absolute_tolerance"]}


def verify_pair(profiles, game, kwargs, spec, require_target):
    results = {label:json.loads(raw) for label, raw in profiles.items()}
    parity = compare_policies(results["original"], results["grouped"], spec)
    checked = {label:verify(result, game, kwargs) for label,result in results.items()}
    metrics = ("value_sb", "sb_best_response_value", "bb_best_response_value", "nash_conv")
    differences = {key:abs(checked["original"]["configured_replay"][key] -
                           checked["grouped"]["configured_replay"][key]) for key in metrics}
    if max(differences.values()) > spec["scalar_absolute_tolerance"]:
        raise AssertionError(f"Scalar drift {differences}")
    if require_target and not all(record["target_met"] for record in checked.values()):
        raise AssertionError("An unchanged 0.005 quality target was missed")
    return {**parity, "independent_scalar_absolute_gaps_between_arms":differences,
            "independent_verification":checked,
            "grouped_view":results["grouped"]["future_indexing_metadata"]}


def main():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    game = json.loads((ROOT/spec["game_spec"]).read_text(encoding="utf-8"))
    revision, dirty = git_revision(None), worktree_dirty()
    if dirty is not False or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise RuntimeError("Freeze source/spec in a clean commit before measurement.")
    paths = tuple(dict.fromkeys((*SOURCES, "scripts/benchmark_preflop_hidden_future_groups.py",
                  "tests/test_preflop_future_groups.py", "tests/test_preflop_future_indexing.py",
                  spec["game_spec"], SPEC.relative_to(ROOT).as_posix())))
    hashes = {p:file_sha256(ROOT/p) for p in paths}
    if any(not isinstance(h,str) or not re.fullmatch(r"[0-9a-f]{64}",h) for h in hashes.values()):
        raise RuntimeError("Source/spec hash unavailable")
    kwargs = {"config":game["config"], "runouts":futures(game["flops"]),
              "flop_config":game["flop_config"], "postflop_scope":game["postflop_scope"]}
    pairs = []
    for index in range(spec["paired_timing"]["pairs"]):
        order = (False,True) if index%2 == 0 else (True,False)
        profiles = {}; seconds = {}
        for grouped in order:
            label = "grouped" if grouped else "original"
            print(f"pair {index+1}: {label} complete call start",flush=True)
            gc.collect(); start=time.perf_counter()
            result, serialized = complete(game,kwargs,spec["paired_timing"],grouped)
            seconds[label] = time.perf_counter()-start
            profiles[label] = serialized
            del result,serialized
        checked = verify_pair(profiles,game,kwargs,spec,True)
        pairs.append({"pair":index+1,"order":["grouped" if b else "original" for b in order],
                      "complete_call_seconds":seconds,**checked})
        print(f"  {seconds}; both independent targets met",flush=True)
        del profiles
    memory = {}
    with tempfile.TemporaryDirectory(prefix="openpoker-future-groups-") as scratch:
        for grouped in (False,True):
            label = "grouped" if grouped else "original"
            print(f"separate allocation trace: {label} start",flush=True)
            gc.collect(); tracemalloc.start()
            try:
                result, serialized = complete(game,kwargs,spec["memory"],grouped)
                _,peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            memory[label] = {"complete_peak_traced_python_bytes":peak,
                             "full_payload_sha256":hashlib.sha256(serialized.encode()).hexdigest()}
            # Disk retention happens after tracing. Neither prior policy nor
            # serialized string is live in the next allocation trace.
            (Path(scratch)/f"{label}.json").write_text(serialized,encoding="utf-8")
            del result,serialized
        profiles = {label:(Path(scratch)/f"{label}.json").read_text(encoding="utf-8")
                    for label in ("original","grouped")}
        memory_check = verify_pair(profiles,game,kwargs,spec,False)
        del profiles
    if hashes != {p:file_sha256(ROOT/p) for p in paths}:
        raise RuntimeError("Source/spec changed during measurement")
    if git_revision(None) != revision or worktree_dirty() is not False:
        raise RuntimeError("Revision/worktree changed during measurement")
    medians = {label:statistics.median(p["complete_call_seconds"][label] for p in pairs)
               for label in ("original","grouped")}
    reduction = 1-medians["grouped"]/medians["original"]
    report = {"schema_version":1,"benchmark_id":spec["benchmark_id"],
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),"source_revision":revision,
        "worktree_dirty_at_start":False,"source_hashes":hashes,
        "configuration_sha256":hashes[SPEC.relative_to(ROOT).as_posix()],
        "game_specification_sha256":hashes[spec["game_spec"]],
        "specification":spec,"game_specification":game,
        "python":platform.python_version(),"platform":platform.platform(),
        "paired_timings":pairs,"paired_timing_medians":medians,
        "observed_median_time_reduction":reduction,
        "runtime_gate_met":reduction >= spec["minimum_median_time_reduction"],
        "memory":memory,"memory_policy_verification":memory_check,
        "timing_scope":"Three alternating fixed90/delay45 complete calls plus JSON on one host. Includes physical enumeration, trees, full original-world admission census, group construction where enabled, training, exact diagnostics and serialization. Preallocated inputs, pre-call GC and independent replay excluded. No statistical or general speed claim.",
        "memory_scope":"Separate complete10/delay5 plus JSON traces. Prior policies/serialized strings are retained on disk after tracing and released before the next arm. No prior policy or grouping structure is live in either trace. Disk retention, digest and replay excluded. Python allocations only; no RSS/native or higher-iteration guarantee.",
        "quality_scope":"Both arms independently replay original full physical outcomes using numeric poker rules and exact legal visible-information best responses. Tolerance gates are predeclared, not bitwise or formal floating error proofs. The same0.005 target applies to both90/45 arms;10/5 misses remain visible.",
        "provenance":"Independently implemented sufficient-statistic aggregation from this repository's physical world model: per private pair/flop, fold payoff uses total mass and showdown uses signed mass. Three discrete sign buckets preserve these quantities mathematically. No third-party source/dependencies, shared postflop kernels, Coach or action-model changes. Luna implements/tests isolated helper; lead integrates/admission-tests and freezes/measures complete calls.",
        "model_limits":game["model_limits"]}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(f"saved {OUTPUT}; median reduction={reduction:.3%}; gate={report['runtime_gate_met']}",flush=True)


if __name__ == "__main__":
    main()
