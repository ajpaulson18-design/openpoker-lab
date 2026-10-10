"""Resumable phase-separated complete-call evaluation of private-index compaction."""
import argparse
from datetime import datetime, timezone
import gc
import hashlib
import json
from pathlib import Path
import platform
import re
import statistics
import sys
import time
import tracemalloc

from pokerlab.preflop_solver import solve_preflop
from scripts.benchmark_preflop_two_flops import futures, verify
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/"benchmarks/preflop-private-compaction-v1.json"
OUTPUT=ROOT/"benchmarks/results/preflop-private-compaction-v1.json"
DEFAULT_STATE_DIR=ROOT.parent/"preflop-private-compaction-state"
PAIRS=("pair1","pair2","pair3")
PHASES=(*PAIRS,"accuracy","memory-original","memory-compact")
FIELDS=("strategy","value_sb","sb_best_response_value","bb_best_response_value","nash_conv",
        "private_pair_probabilities","reachable_runouts","worlds","info_sets","decisions","public_states")
SOURCES=tuple(sorted(str(p.relative_to(ROOT)).replace("\\","/")
                     for p in (ROOT/"pokerlab").glob("*.py")))+(
 "scripts/benchmark_preflop_private_compaction.py","scripts/benchmark_preflop_two_flops.py",
 "scripts/benchmark_turn_solver.py","scripts/preflop_validation.py",
 "tests/test_preflop_private_indices.py","tests/test_preflop_private_index_budget.py",
 "tests/test_preflop_private_index_integration.py")


def solve(spec,kwargs,checkpoint,mode):
    result=solve_preflop(spec["sb"],spec["bb"],**kwargs,iterations=checkpoint["iterations"],
        averaging_delay=checkpoint["delay"],algorithm="cfrplus",traversal="public-batched",
        diagnostics="public-batched",resource_model="public-vector",tree_admission="vector",
        private_indexing=mode)
    json.dumps(result,allow_nan=False)
    return result


def checked(result,spec,kwargs):
    independent=verify(result,spec,kwargs)
    gap=independent["configured_replay"]["nash_conv"]
    return {"worlds":result["worlds"],"information_sets":result["info_sets"],
        "decisions":result["decisions"],"public_states":result["public_states"],
        "private_pair_probabilities":result["private_pair_probabilities"],
        "target_nash_conv":spec["target_nash_conv"],
        "independent_target_met":gap+1e-10<=spec["target_nash_conv"],
        "vector_work_budget":result["vector_work_budget"],
        "private_indexing_metadata":result.get("private_indexing_metadata"),**independent}


def canonical_json(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,
                      separators=(",",":")).encode("utf-8")


def payload_sha256(payload):
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def digest(result):
    raw=json.dumps({k:result[k] for k in FIELDS},ensure_ascii=False,allow_nan=False,
                   separators=(",",":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def header_now():
    hashes={p:file_sha256(ROOT/p) for p in SOURCES}
    rev,dirty=git_revision(None),worktree_dirty()
    spec_hash=file_sha256(SPEC)
    if dirty is not False:
        raise RuntimeError("Git cleanliness unavailable or worktree dirty; freeze source/spec before measuring.")
    if not isinstance(rev,str) or re.fullmatch(r"[0-9a-fA-F]{40}",rev) is None:
        raise RuntimeError("Could not establish a full 40-character source revision.")
    valid_hash=lambda value: isinstance(value,str) and re.fullmatch(r"[0-9a-fA-F]{64}",value) is not None
    if not hashes or any(not valid_hash(value) for value in hashes.values()) or not valid_hash(spec_hash):
        raise RuntimeError("Could not establish complete SHA-256 provenance for source/spec.")
    return {"source_revision":rev,"source_hashes":hashes,"configuration_sha256":spec_hash,
            "python":sys.version,"platform":platform.platform()}


def check_header(header):
    if header_now()!=header: raise RuntimeError("Source/spec/runtime identity changed during phases.")


def run_pair(i,spec,kwargs):
    order=("original","compact") if i%2 else ("compact","original")
    rows={}; first=None
    for mode in order:
        print(f"{'pair'+str(i)}: {mode} start",flush=True); gc.collect()
        start=time.perf_counter(); result=solve(spec,kwargs,spec["paired_timing"],mode)
        elapsed=time.perf_counter()-start; rows[mode]={"complete_call_seconds":elapsed,**checked(result,spec,kwargs)}
        if first is None: first=result
        else:
            for field in FIELDS: assert first[field]==result[field],field
        print(f"  seconds={elapsed:.3f} gap={result['nash_conv']:.12g}",flush=True)
    del first,result
    return {"pair":i,"order":list(order),
        "policy_row_order_diagnostics_and_physical_priors_exactly_equal":True,"records":rows}


def run_accuracy(spec,kwargs):
    print("compact high-iteration accuracy checkpoint start",flush=True);gc.collect()
    start=time.perf_counter();result=solve(spec,kwargs,spec["accuracy"],"compact")
    out={**spec["accuracy"],"complete_call_seconds":time.perf_counter()-start,**checked(result,spec,kwargs)}
    print(f"  gap={result['nash_conv']:.12g}; target met={out['independent_target_met']}",flush=True)
    del result;return out


def run_memory(mode,spec,kwargs):
    print(f"separate complete-call allocation trace: {mode} start",flush=True);gc.collect()
    tracemalloc.start()
    try:
        result=solve(spec,kwargs,spec["memory"],mode);_,peak=tracemalloc.get_traced_memory()
    finally:tracemalloc.stop()
    out=checked(result,spec,kwargs);sha=digest(result);del result;gc.collect()
    print(f"  peak={peak}; parity digest={sha}",flush=True)
    return {"complete_peak_traced_python_bytes":peak,"parity_sha256":sha,**out}


def assemble(spec,header,done):
    if set(done)!=set(PHASES):return None
    pairs=[done[p] for p in PAIRS];mem={m:done["memory-"+m] for m in ("original","compact")}
    if mem["original"]["parity_sha256"]!=mem["compact"]["parity_sha256"]:
        raise AssertionError("Separate memory arms differ in serialized parity fields.")
    med={m:statistics.median(p["records"][m]["complete_call_seconds"] for p in pairs)
         for m in ("original","compact")}
    reduction=1-med["compact"]/med["original"]
    return {"schema_version":1,"benchmark_id":spec["benchmark_id"],
        "generated_at":datetime.now(timezone.utc).isoformat(),"source_revision":header["source_revision"],
        "worktree_dirty_at_start":False,"source_hashes":header["source_hashes"],
        "configuration_sha256":header["configuration_sha256"],"specification":spec,
        "python":platform.python_version(),"platform":header["platform"],"paired_timings":pairs,
        "paired_timing_medians":med,"observed_median_time_reduction":reduction,
        "runtime_gate_met":reduction>=spec["minimum_median_time_reduction"],
        "accuracy":done["accuracy"],"memory":mem,
        "memory_policy_row_order_diagnostics_and_physical_priors_exactly_equal":True,
        "accuracy_scope":"Same fixed iterations/delay for timing/memory arms; all final policies independently replayed from numeric rules and exact visible-information best responses. The compact90/delay45 checkpoint is a single accuracy measurement, with no speed comparison to original90. Unchanged0.005 target misses retained; no accuracy improvement claimed.",
        "timing_scope":"Three alternating pairs of complete two-flop20/delay10 solves plus JSON on one host, including preflight, compact copies, training, exact diagnostics and original-identity restoration. Preallocated runout arguments, pre-call GC and independent replay excluded. Shape-specific observed medians, no universal speed claim.",
        "memory_scope":"Separate complete two-flop10/delay5 solves plus JSON under tracemalloc. Each arm runs without retaining the other result; each includes its own copies through diagnostics/restoration. Runout args preallocated; replay and parity digest excluded. Traced Python allocations, not RSS/native or higher-iteration guarantees.",
        "admission_scope":"Independent v4 pre-copy structural census uses actual compact dimensions and reserves additional copy/restoration loop entries and logical reference slots. Original physical world/tree/candidate guards and numerical model unchanged. Logical slots exclude Python headers, allocator effects and RSS.",
        "provenance":"Independently implemented ascending bijection of this repository's own global active-hand indices. No third-party source/dependencies or shared postflop/turn/river changes. Luna owns compaction/integration and independent budget tests/review; lead owns workload admission, independent integration checks, frozen measurement and adoption decision.",
        "model_limits":"Conditioned finite heads-up two-selected-flop game with complete ordered future deals and narrow ranges with twelve globally inactive SB hands. No full-deck preflop, unrestricted NLHE, multiway, broad-range convergence, universal performance or formal floating-point certificate."}


def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase",choices=("all",*PHASES),default="all")
    p.add_argument("--resume",action="store_true")
    p.add_argument("--state-dir",type=Path,default=DEFAULT_STATE_DIR)
    return p.parse_args(argv)


def main(argv=None):
    args=parse_args(argv);spec=json.loads(SPEC.read_text(encoding="utf-8"));header=header_now()
    if spec.get("paired_timing",{}).get("pairs")!=len(PAIRS):
        raise RuntimeError("Frozen paired_timing.pairs must match the three named timing phases.")
    state=args.state_dir.resolve();state.mkdir(parents=True,exist_ok=True)
    paths={p:state/(p+".json") for p in PHASES}
    if any(p.exists() for p in paths.values()) and not args.resume:
        raise RuntimeError("Phase state already exists; pass --resume to validate and reuse it.")
    done={}
    if args.resume:
        for phase,path in paths.items():
            if not path.exists():continue
            rec=json.loads(path.read_text(encoding="utf-8"))
            payload=rec.get("payload")
            if rec.get("phase")!=phase or rec.get("completed") is not True or rec.get("header")!=header:
                raise RuntimeError(f"Invalid phase identity/provenance: {phase}")
            if not isinstance(payload,dict) or rec.get("payload_sha256")!=payload_sha256(payload):
                raise RuntimeError(f"Saved phase payload checksum is invalid: {phase}")
            done[phase]=payload
    kwargs={"config":spec["config"],"runouts":futures(spec["flops"])}
    selected=PHASES if args.phase=="all" else (args.phase,)
    for phase in selected:
        if phase in done:
            print(f"{phase}: reusing validated completed phase",flush=True);continue
        if phase=="memory-compact" and "memory-original" not in done:
            raise RuntimeError("memory-compact requires memory-original first.")
        check_header(header)
        phase_started_at=datetime.now(timezone.utc).isoformat()
        if phase in PAIRS:payload=run_pair(int(phase[-1]),spec,kwargs)
        elif phase=="accuracy":payload=run_accuracy(spec,kwargs)
        else:
            mode=phase.removeprefix("memory-");payload=run_memory(mode,spec,kwargs)
            if mode=="compact" and payload["parity_sha256"]!=done["memory-original"]["parity_sha256"]:
                raise AssertionError("Separate memory arms differ in serialized parity fields.")
        check_header(header)
        payload={**payload,"phase_started_at":phase_started_at,
                 "phase_completed_at":datetime.now(timezone.utc).isoformat()}
        tmp=paths[phase].with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"phase":phase,"completed":True,"header":header,
                                  "payload_sha256":payload_sha256(payload),"payload":payload},
                                  indent=2,allow_nan=False)+"\n",encoding="utf-8")
        tmp.replace(paths[phase]);done[phase]=payload
    check_header(header);report=assemble(spec,header,done)
    if report is None:
        print("phase saved; report deferred; missing: "+", ".join(p for p in PHASES if p not in done),flush=True)
        return
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(f"report saved; runtime gate={report['runtime_gate_met']}; reduction={report['observed_median_time_reduction']:.3%}",flush=True)


if __name__=="__main__":main()
