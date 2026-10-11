"""Frozen higher-iteration quality under explicit grouped-world admission."""
import gc
import hashlib
import json
import platform
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from scripts.benchmark_preflop_flop_checkdown import futures, verify, SOURCES
from scripts.benchmark_preflop_flop_raise_coverage import preflight_case, _coverage
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/preflop-grouped-world-admission-v1.json"
OUTPUT = ROOT / "benchmarks/results/preflop-grouped-world-admission-v1.json"


def preflight(spec, checkpoint, opt_in):
    game = dict(spec, preflop_config={k:v for k,v in spec["config"].items() if k != "starting_stack"},
                physical_outcomes={"flops":spec["flops"]},
                algorithm="cfrplus", traversal="public-batched", diagnostics="public-batched",
                resource_model="public-vector", future_indexing="flop-sign")
    original_solve = solver.solve_preflop
    def with_admission(*args, **kwargs):
        return original_solve(*args, **kwargs, world_admission="grouped-vector")
    if opt_in:
        with patch.object(solver,"solve_preflop",with_admission):
            return preflight_case(game,spec["config"]["starting_stack"],checkpoint)
    return preflight_case(game,spec["config"]["starting_stack"],checkpoint)


def complete(spec, kwargs, checkpoint, opt_in):
    result = solver.solve_preflop(spec["sb"],spec["bb"],**kwargs,
        iterations=checkpoint["iterations"],averaging_delay=checkpoint["delay"],
        algorithm="cfrplus",traversal="public-batched",diagnostics="public-batched",
        resource_model="public-vector",future_indexing="flop-sign",
        **({"world_admission":"grouped-vector"} if opt_in else {}))
    return result,json.dumps(result,allow_nan=False)


def main():
    spec=json.loads(SPEC.read_text(encoding="utf-8"))
    revision,dirty=git_revision(None),worktree_dirty()
    if dirty is not False or not re.fullmatch(r"[0-9a-f]{40}",revision):
        raise RuntimeError("Freeze source/spec in a clean commit before measurement")
    paths=tuple(dict.fromkeys((*SOURCES,"scripts/benchmark_preflop_flop_raise_coverage.py",
        "scripts/benchmark_preflop_grouped_world_admission.py",
        "tests/test_preflop_grouped_world_admission.py",spec["game_spec"],
        SPEC.relative_to(ROOT).as_posix())))
    hashes={p:file_sha256(ROOT/p) for p in paths}
    if any(not isinstance(h,str) or not re.fullmatch(r"[0-9a-f]{64}",h) for h in hashes.values()):
        raise RuntimeError("Source/spec hash unavailable")
    kwargs={"config":spec["config"],"runouts":futures(spec["flops"]),
            "flop_config":spec["flop_config"],"postflop_scope":spec["postflop_scope"]}
    admissions=[]
    for checkpoint in spec["checkpoints"]:
        record={**checkpoint}
        for opt_in in (False,True):
            label="grouped-vector" if opt_in else "world-iterations"
            print(f"preflight {label} {checkpoint}",flush=True)
            record[label]=preflight(spec,checkpoint,opt_in)
            print(f"  {record[label]['status']}: {record[label]['rejection']}",flush=True)
        admissions.append(record)
    # The old admitted250 policy is a reference for admission-only arithmetic
    # parity. Store serialized strategy plus small physical/scalar fields, not
    # the previous complete result, across the next complete call.
    reference_checkpoint=spec["checkpoints"][0]
    if reference_checkpoint["iterations"] != 250 or admissions[0]["world-iterations"]["status"] != "admitted":
        raise AssertionError("Expected original250 admission reference")
    print("legacy250 exact-policy reference start",flush=True)
    result,serialized=complete(spec,kwargs,reference_checkpoint,False)
    reference_policy=json.dumps(result["strategy"],allow_nan=False)
    fields=("worlds","selected_runouts","reachable_runouts","private_pair_probabilities",
            "public_states","decisions","info_sets","value_sb","value_bb",
            "sb_best_response_value","bb_best_response_value","nash_conv")
    reference={k:result[k] for k in fields}
    reference_verification=verify(result,spec,kwargs)
    del result,serialized
    records=[]
    for checkpoint,admission in zip(spec["checkpoints"],admissions):
        if admission["grouped-vector"]["status"] == "rejected":
            records.append({**checkpoint,"status":"rejected","preflight":admission})
            continue
        print(f"complete opt-in {checkpoint} start",flush=True)
        gc.collect();start=time.perf_counter()
        result,serialized=complete(spec,kwargs,checkpoint,True)
        seconds=time.perf_counter()-start
        checked=verify(result,spec,kwargs)
        if result["world_admission"] != "grouped-vector":
            raise AssertionError("Expected explicit grouped-world admission")
        if result["vector_work_budget"]["iterations"] != checkpoint["iterations"]:
            raise AssertionError("Full requested iteration ceiling was not admitted")
        if result["vector_work_budget"]["total_loop_entries_upper_bound"] != admission["grouped-vector"]["combined_modeled_loop_entries"]:
            raise AssertionError("Actual vector admission differs from preflight")
        record={**checkpoint,"status":"completed","complete_call_seconds":seconds,
                "full_payload_sha256":hashlib.sha256(serialized.encode()).hexdigest(),
                "verification":checked,"action_coverage":_coverage(result["strategy"]),
                "future_indexing_metadata":result["future_indexing_metadata"],
                "world_admission":result["world_admission"],"limits":result["limits"],
                "world_construction_admission_iterations":result["world_construction_admission_iterations"],
                "preflight":admission}
        if checkpoint == reference_checkpoint:
            if json.dumps(result["strategy"],allow_nan=False) != reference_policy or {k:result[k] for k in fields} != reference:
                raise AssertionError("Admission changed250 policy/physical outputs/scalars")
            record["legacy250_policy_physical_scalar_exact_parity"]=True
            del reference_policy,reference
        records.append(record)
        print(f"  independent gap={checked['configured_replay']['nash_conv']:.12g}; target={checked['target_met']}; seconds={seconds:.3f}",flush=True)
        del result,serialized
    if hashes != {p:file_sha256(ROOT/p) for p in paths}:
        raise RuntimeError("Source/spec changed during measurement")
    if git_revision(None) != revision or worktree_dirty() is not False:
        raise RuntimeError("Revision/worktree changed during measurement")
    report={"schema_version":1,"benchmark_id":spec["benchmark_id"],
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),"source_revision":revision,
        "worktree_dirty_at_start":False,"source_hashes":hashes,
        "configuration_sha256":hashes[SPEC.relative_to(ROOT).as_posix()],
        "specification":spec,"python":platform.python_version(),"platform":platform.platform(),
        "preflight":admissions,"legacy250_reference_verification":reference_verification,
        "records":records,
        "timing_scope":"One descriptive complete-call plus JSON time per admitted opt-in case; preallocated inputs, pre-call GC and independent replay excluded. Prior full policies released, while the250 reference retains only serialized strategy and selected physical/scalar fields for parity. No speed comparison or statistical runtime claim.",
        "quality_scope":"Original complete physical-world numeric replay and exact legal visible-information best responses at every checkpoint, including the legacy250 reference. Same0.005-chip target and1e-10 padding, all misses/rejections retained. The requested iteration ceiling is charged in full before grouping/compact/view/training allocation; no early stopping or outcome reduction.",
        "provenance":"Luna implements/tests the narrowly eligible opt-in admission; lead reviews and freezes the unchanged six-chip action/world game at four declared iteration ceilings. Construction scan/ranking does not depend on training sweeps; its maximum physical count is bounded by the previous minimum-iteration construction allowance. No shared postflop/turn/river kernels, Coach, third-party source/dependencies or proprietary output.",
        "model_limits":spec["model_limits"]}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(f"saved {OUTPUT}",flush=True)


if __name__ == "__main__":
    main()
