"""Fixed clean-source study of the explicit exact-product four-street path.

The legacy rounded law is not an equivalence reference for the new arithmetic.
All raw outputs, requested-work rejections and finite-iteration misses are kept.
"""
import argparse
from contextlib import ExitStack
from fractions import Fraction
import hashlib
import json
from math import comb, isfinite
from pathlib import Path
import statistics
import subprocess
import sys
import time
import tracemalloc
from unittest.mock import patch

from pokerlab.exact_selected_solver import solve_four_street_exact_selected
from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions
from scripts.benchmark_selected_operator import ROOT, _identity, _rss, _write
from scripts.four_street_certificate_v3 import evaluate_exact

SCHEDULE = (("original",10,0,False),("original",10,1,False),
    ("original",10,2,False),("original",10,"traced",True),
    ("original",100,0,False),("original",1000,0,False),
    ("unit",10,0,False),("tiny",10,0,False),("one-world",1000,0,False),
    ("full-range-census",0,0,False))
METRICS = ("value_sb","value_bb","sb_best_response_value","bb_best_response_value",
    "sb_gain","bb_gain","nash_conv","exploitability")


def case_for(name):
    base = json.loads((ROOT/"benchmarks/four-street-integration-v1.json").read_text(encoding="utf-8"))["case"]
    if name == "original":
        return base
    if name == "one-world":
        return dict(base,id="exact-product-one-world-four-street-v1",sb_range="AsAd",bb_range="KsKd",runouts=["2c3c4d7h8h"])
    if name not in ("unit","tiny"):
        raise ValueError("Unknown fixed case")
    scale = "1e-200" if name == "tiny" else "1"
    return dict(base,id="exact-product-common-scale-"+name,
        sb_range=f"AsAd:{scale},QsQd:{scale}",bb_range=f"KsKd:{scale},JhJd:{scale}",
        config={"starting_stack":[4,3],"raise_sizes":[.5],"max_raises":1,"include_all_in":False},
        runouts=["2c3c4d7h8h","2c3c4d7hKc","Ac2d3h7s8c"])


def request_for(case, iterations):
    return FourStreetSolveRequest(case["sb_range"],case["bb_range"],tuple(case["runouts"]),
        preflop_config=PreflopConfig.from_dict(case["config"]),
        flop_actions=PostflopActions(**case["flop_config"]),
        turn_actions=None if case.get("turn_config") is None else PostflopActions(**case["turn_config"]),
        river_actions=None if case.get("river_config") is None else PostflopActions(**case["river_config"]),
        iterations=iterations,algorithm="cfrplus",traversal="public-batched",diagnostics="public-batched",resource_model="public-vector")


def child(name, iterations, traced):
    counts={"training_calls":0,"rank_calls":0,"native_calls":0}
    from pokerlab import exact_selected_solver as solver
    from pokerlab import exact_selected_kernel as kernel_module
    train, rank = solver.train_packed, kernel_module.rank_hand
    def counted_train(*args,**kwargs):
        counts["training_calls"]+=1
        return train(*args,**kwargs)
    def counted_rank(*args,**kwargs):
        counts["rank_calls"]+=1
        return rank(*args,**kwargs)
    forbidden=("pokerlab.preflop_solver._enumerate_physical_worlds",
        "pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds",
        "pokerlab.shared_public_topology.compile_shared_public_topology",
        "pokerlab.preflop_solver._merge_preflop_tree")
    if traced: tracemalloc.start()
    before=time.perf_counter()
    try:
        with ExitStack() as stack:
            for target in forbidden: stack.enter_context(patch(target,side_effect=AssertionError(target)))
            stack.enter_context(patch.object(solver,"train_packed",new=counted_train))
            stack.enter_context(patch.object(kernel_module,"rank_hand",new=counted_rank))
            if name == "full-range-census":
                kernel=ExactSelectedRunoutKernel("random","random",["2c3d4h5s6c"])
                values=kernel.joint_marginals_exact()
                expected=comb(47,2)*comb(45,2)
                if kernel.statistics()["support_pair_board_occurrences"]!=expected or any(sum(side,Fraction())!=1 or
                        sum(x>0 for x in side)!=comb(47,2) or any(x not in (Fraction(),Fraction(1,comb(47,2))) for x in side) for side in values):
                    raise ValueError("Full-range combinatorial anchor mismatch")
                payload={"statistics":dict(kernel.receipt()),"expected_pair_board_occurrences":expected,
                    "exact_active_marginal":"1/1081","stored_worlds":0,"training_calls":0}
            else:
                payload=solve_four_street_exact_selected(request_for(case_for(name),iterations),rank_cache_boards=64)
        status="complete"; error=None
    except ValueError as exc:
        if (name != "original" or iterations != 1000 or counts["training_calls"] or counts["rank_calls"] or
                not any(token in str(exc).lower() for token in ("admission", "limit", "forecast", "cap"))):
            raise
        # The fixed larger request is allowed to reject before rank/training;
        # its exact first error and zero-call evidence stay in the study.
        status="pretraining-rejected"; payload=None
        error={"type":type(exc).__name__,"message":str(exc)}
    seconds=time.perf_counter()-before
    allocation=tracemalloc.get_traced_memory()[1] if traced else None
    if traced: tracemalloc.stop()
    return {"case":name,"iterations":iterations,"traced":traced,"status":status,"error":error,
        "seconds":seconds,"python_allocation_peak_bytes":allocation,"python_process_peak_bytes":_rss(),
        **counts,"payload":payload}


def run(output):
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents or output.exists():
        raise ValueError("Use a new external study directory")
    source=_identity()
    if source["status"]: raise ValueError("Commit and clean source before measurement")
    output.mkdir(parents=True)
    _write(output/"source-before.json",source)
    _write(output/"protocol.json",{"version":"exact-product-four-street-fixed-study-v1","schedule":SCHEDULE,
        "source_commit":source["commit"],"chance_contract":"exact-product-selected-v1",
        "conversion_contract":"exact-product-vectors-binary64-v1","retry_policy":"none; preserve first failure",
        "quality":"Record every exact certificate and threshold miss; no convergence claim from admission or numeric agreement.",
        "scope":"Bounded new-law four-street training, tiny-scale metamorphic control and rank-free full-range one-selected-board census."})
    records=[]; certificates={}; failure=None
    for name,iterations,sample,traced in SCHEDULE:
        label=f"{name}-t{iterations}-{sample}"
        command=[sys.executable,"-B","-m","scripts.benchmark_exact_selected_solver","--child",name,"--iterations",str(iterations)]
        if traced: command.append("--traced")
        process=None
        try:
            process=subprocess.run(command,cwd=ROOT,capture_output=True,check=False)
            # Preserve streams before interpreting exit status, metadata or math.
            (output/(label+".json")).write_bytes(process.stdout)
            (output/(label+".stderr.txt")).write_bytes(process.stderr)
            if process.returncode:
                raise RuntimeError("child exited with status "+str(process.returncode))
            raw=json.loads(process.stdout)
            if (raw.get("case")!=name or raw.get("iterations")!=iterations or
                    raw.get("traced") is not traced or type(raw.get("seconds")) not in (int,float) or
                    not isfinite(raw["seconds"]) or raw["seconds"]<=0 or
                    raw.get("status") not in ("complete","pretraining-rejected") or
                    type(raw.get("rank_calls")) is not int or raw["rank_calls"]<0 or
                    type(raw.get("native_calls")) is not int or raw["native_calls"]!=0):
                raise ValueError("child metadata/status/counter mismatch")
            allocation=raw.get("python_allocation_peak_bytes")
            rss=raw.get("python_process_peak_bytes")
            if ((traced and (type(allocation) is not int or allocation<=0)) or
                    (not traced and allocation is not None) or type(rss) is not int or rss<=0):
                raise ValueError("child allocation/process measurement mismatch")
            expected_calls=0 if name=="full-range-census" or raw["status"]=="pretraining-rejected" else 1
            if type(raw.get("training_calls")) is not int or raw["training_calls"]!=expected_calls:
                raise ValueError("child training call count mismatch")
            if raw["status"]=="pretraining-rejected":
                error=raw.get("error")
                if (name!="original" or iterations!=1000 or raw["rank_calls"] or raw.get("payload") is not None or
                        type(error) is not dict or error.get("type")!="ValueError" or
                        not any(token in error.get("message","").lower() for token in ("admission","limit","forecast","cap"))):
                    raise ValueError("unexpected or malformed pretraining rejection")
            elif type(raw.get("payload")) is not dict:
                raise ValueError("completed child omitted its payload")
            elif name=="full-range-census":
                if raw["rank_calls"] or raw["payload"].get("expected_pair_board_occurrences")!=1070190:
                    raise ValueError("rank-free census identity mismatch")
            elif (raw["payload"].get("chance_contract")!="exact-product-selected-v1" or
                    raw["payload"].get("conversion_contract")!="exact-product-vectors-binary64-v1"):
                raise ValueError("completed solver contract mismatch")
            records.append({"artifact":label+".json","sample":sample,**{k:v for k,v in raw.items() if k!="payload"}})
            print(label,raw["status"],round(raw["seconds"],6),flush=True)
            if raw["status"]=="complete" and name!="full-range-census" and sample==0:
                # Authenticate current clean closure before independent mathematics.
                if _identity()!=source:
                    raise ValueError("source changed before independent exact replay")
                cert=evaluate_exact(case_for(name),raw["payload"])
                _write(output/(label+"-certificate.json"),cert)
                certificates[label]={"threshold_met":cert["threshold_met"],"metrics":cert["metrics"],
                    "normalized_policy_sha256":cert["normalized_policy_sha256"]}
        except Exception as exc:
            failure={"artifact":label,"error_type":type(exc).__name__,"error":str(exc),
                "returncode":None if process is None else process.returncode}
            _write(output/(label+"-failure.json"),failure)
            break
    source_after=_identity();_write(output/"source-after.json",source_after)
    if source_after!=source: failure={"stage":"source-changed","prior_failure":failure}
    checks={}
    if not failure:
        load=lambda label:json.loads((output/(label+".json")).read_text(encoding="utf-8"))["payload"]
        reference=load("original-t10-0")
        checks["three_t10_and_traced_policies_identical"]=all(load("original-t10-"+str(sample))["strategy"]==reference["strategy"] for sample in (1,2,"traced"))
        unit,tiny=load("unit-t10-0"),load("tiny-t10-0")
        checks["common_scale_complete_strategy_identical"]=unit["strategy"]==tiny["strategy"]
        checks["common_scale_all_metrics_identical"]=all(unit[k]==tiny[k] for k in METRICS)
        checks["common_scale_pair_probabilities_identical"]=unit["private_pair_probabilities"]==tiny["private_pair_probabilities"]
        if not all(checks.values()): failure={"stage":"metamorphic-policy-checks","checks":checks}
    report={"outcome":"complete" if failure is None else "failed","source_commit":source["commit"],
        "samples":records,"exact_certificates":certificates,"checks":checks,"failure":failure,
        "training_calls":sum(row["training_calls"] for row in records),"native_calls":0,
        "t10_median_seconds":(statistics.median(row["seconds"] for row in records
            if row["case"]=="original" and row["iterations"]==10 and not row["traced"])
            if any(row["case"]=="original" and row["iterations"]==10 and not row["traced"] for row in records) else None),
        "scope":"Exact arithmetic contract is different from the legacy rounded law; measured costs and finite-iteration misses apply only to these fixed cases."}
    _write(output/"report.json",report)
    _write(output/"manifest.json",{"source_commit":source["commit"],"sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()}})
    digest=hashlib.sha256((output/"manifest.json").read_bytes()).hexdigest()
    return {"outcome":report["outcome"],"manifest_sha256":digest,"failure":failure}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--child",choices=("original","unit","tiny","one-world","full-range-census"))
    parser.add_argument("--iterations",type=int,default=10)
    parser.add_argument("--traced",action="store_true")
    args=parser.parse_args()
    result=child(args.child,args.iterations,args.traced) if args.child else run(args.output)
    print(json.dumps(result,allow_nan=False))
    return 0 if args.child or result["outcome"]=="complete" else 1

if __name__=="__main__":
    raise SystemExit(main())
