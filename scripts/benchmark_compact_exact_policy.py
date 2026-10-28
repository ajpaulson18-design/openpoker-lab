"""Fixed clean-source expanded/compact exact-product complete-call study.

Three alternating untraced T10 pairs and a separate traced pair use the same
22-world four-street game. A final full-range forced blind-all-in contrast has
no decisions; its expanded output must reject before pair/rank/training work.
All raw streams, first failures, certificate misses and requested-work rejections
are preserved. This runner does not alter any solver or oracle cap.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from itertools import combinations
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
from scripts.benchmark_exact_selected_solver import request_for
from scripts.benchmark_selected_operator import ROOT, _identity, _rss, _write
from scripts.four_street_certificate_v3 import evaluate_exact as expanded_exact
from scripts.exact_selected_compact_certificate import evaluate_exact as compact_exact
from scripts import four_street_validation as physical

MODES=("expanded","compact")
FORMATS={"expanded":"expanded-private-pairs-v1","compact":"compact-exact-product-inputs-v1"}
METRICS=("value_sb","value_bb","sb_best_response_value","bb_best_response_value",
         "sb_gain","bb_gain","nash_conv","exploitability")
EXACT_METRICS=frozenset(("value_sb","value_bb","sb_best_response_value","bb_best_response_value",
    "sb_best_response_gain","bb_best_response_gain","nash_conv","exploitability","lower_value_bound","upper_value_bound"))
RANK_CACHE_BOARDS=64
ITERATIONS=10
FULL_RANGE="full-range-blind-all-in"


def schedule():
    rows=[]
    for sample in range(3):
        rows.extend(("original",mode,sample,False) for mode in
                    (MODES if sample%2==0 else tuple(reversed(MODES))))
    rows.extend(("original",mode,"traced",True) for mode in MODES)
    rows.extend((FULL_RANGE,mode,0,False) for mode in MODES)
    return tuple(rows)


def case_for(name):
    base=json.loads((ROOT/"benchmarks/four-street-integration-v1.json").read_text(encoding="utf-8"))["case"]
    if name=="original":return base
    if name!=FULL_RANGE:raise ValueError("Unknown fixed compact-policy case")
    return dict(base,id="compact-exact-full-range-forced-blind-all-in-v1",sb_range="random",bb_range="random",
        runouts=["2c3d4h5s6c"],config=dict(base["config"],starting_stack=[.5,1]))


def admission_error(message):
    return any(token in message.lower() for token in ("admission","limit","forecast","cap"))


def child(name,mode,traced):
    if name not in ("original",FULL_RANGE) or mode not in MODES or type(traced) is not bool:
        raise ValueError("Unsupported compact-policy study child mode")
    from pokerlab import exact_selected_solver as solver
    from pokerlab import exact_selected_kernel as kernel_module
    calls={"training_calls":0,"pair_query_calls":0,"rank_calls":0,"native_calls":0}
    train,rank,pair=solver.train_packed,kernel_module.rank_hand,ExactSelectedRunoutKernel.pair_probability_exact
    def counted_train(*args,**kwargs):
        calls["training_calls"]+=1
        return train(*args,**kwargs)
    def counted_rank(*args,**kwargs):
        calls["rank_calls"]+=1
        return rank(*args,**kwargs)
    def counted_pair(*args,**kwargs):
        calls["pair_query_calls"]+=1
        if mode=="compact":raise AssertionError("Compact production entered a private-pair query")
        return pair(*args,**kwargs)
    def forbidden_native(*args,**kwargs):
        calls["native_calls"]+=1
        raise AssertionError("Native/subprocess execution is outside this Python study")
    forbidden=("pokerlab.preflop_solver._enumerate_physical_worlds",
        "pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds",
        "pokerlab.shared_public_topology.compile_shared_public_topology",
        "pokerlab.preflop_solver._merge_preflop_tree")
    native=("pokerlab.native_selected_operator.train_native_selected",
        "pokerlab.native_selected_dag.train_native_selected_dag",
        "pokerlab.native_public_cfr.train_native_public","subprocess.Popen")
    request=request_for(case_for(name),ITERATIONS)
    payload=None;error=None;status="complete"
    with ExitStack() as stack:
        for target in forbidden:stack.enter_context(patch(target,side_effect=AssertionError(target)))
        for target in native:stack.enter_context(patch(target,new=forbidden_native))
        stack.enter_context(patch.object(solver,"train_packed",new=counted_train))
        stack.enter_context(patch.object(kernel_module,"rank_hand",new=counted_rank))
        stack.enter_context(patch.object(ExactSelectedRunoutKernel,"pair_probability_exact",new=counted_pair))
        # Authenticate/instrumentation imports and request parsing precede the
        # measured complete solve; process lifetime peaks still include them.
        if traced:tracemalloc.start()
        before=time.perf_counter()
        try:
            try:
                payload=solve_four_street_exact_selected(request,rank_cache_boards=RANK_CACHE_BOARDS,pair_diagnostics=mode)
            except ValueError as exc:
                if (name!=FULL_RANGE or mode!="expanded" or any(calls.values()) or not admission_error(str(exc))):
                    raise
                status="pretraining-rejected"
                error={"type":type(exc).__name__,"message":str(exc)}
            seconds=time.perf_counter()-before
            allocation=tracemalloc.get_traced_memory()[1] if traced else None
        finally:
            if traced and tracemalloc.is_tracing():tracemalloc.stop()
    return {"case":name,"mode":mode,"output_format":FORMATS[mode],"iterations":ITERATIONS,"traced":traced,
        "rank_cache_boards":RANK_CACHE_BOARDS,"status":status,"error":error,"seconds":seconds,
        "python_allocation_peak_bytes":allocation,"python_process_peak_bytes":_rss(),**calls,"payload":payload}


def _need(condition,message):
    if not condition:raise ValueError(message)


def _object(pairs):
    output={}
    for key,value in pairs:
        _need(key not in output,"duplicate child JSON key")
        output[key]=value
    return output


def _decode(raw):
    return json.loads(raw,object_pairs_hook=_object,
        parse_constant=lambda value:(_ for _ in ()).throw(ValueError("nonfinite child JSON")))


def _validate_child(raw,name,mode,traced):
    _need(type(raw) is dict,"child result must be an object")
    for key,expected in (("case",name),("mode",mode),("output_format",FORMATS[mode]),
            ("iterations",ITERATIONS),("rank_cache_boards",RANK_CACHE_BOARDS),("traced",traced)):
        _need(type(raw.get(key)) is type(expected) and raw[key]==expected,"child request/format metadata mismatch")
    _need(type(raw.get("seconds")) in (int,float) and isfinite(raw["seconds"]) and raw["seconds"]>0,"invalid child elapsed time")
    allocation=raw.get("python_allocation_peak_bytes");rss=raw.get("python_process_peak_bytes")
    _need((type(allocation) is int and allocation>0) if traced else allocation is None,"child trace allocation scope mismatch")
    _need(type(rss) is int and rss>0,"invalid child Python process peak")
    for key in ("training_calls","pair_query_calls","rank_calls","native_calls"):
        _need(type(raw.get(key)) is int and raw[key]>=0,"invalid actual child call counter")
    _need(raw["native_calls"]==0,"Python study entered native execution")
    if name==FULL_RANGE and mode=="expanded":
        error=raw.get("error")
        _need(raw.get("status")=="pretraining-rejected" and raw.get("payload") is None and
            all(raw[key]==0 for key in ("training_calls","pair_query_calls","rank_calls","native_calls")) and
            type(error) is dict and error.get("type")=="ValueError" and type(error.get("message")) is str and
            admission_error(error["message"]),"expanded full-range output did not reject before pair/rank/training work")
        return
    payload=raw.get("payload")
    _need(raw.get("status")=="complete" and raw.get("error") is None and type(payload) is dict,"expected a completed compact-policy child")
    _need(payload.get("chance_contract")=="exact-product-selected-v1" and
        payload.get("conversion_contract")=="exact-product-vectors-binary64-v1" and
        payload.get("execution_backend")=="exact-product-selected-direct-packed-python","child solver arithmetic/backend mismatch")
    _need(type(payload.get("strategy")) is list and type(payload.get("info_sets")) is int and
        payload["info_sets"]==len(payload["strategy"]),"child policy row coverage mismatch")
    for key in METRICS:_need(type(payload.get(key)) in (int,float) and isfinite(payload[key]),"nonfinite/missing child diagnostic")
    census=payload["operator_census"];admit=census["whole_request_admission"]
    _need(census["stored_complete_worlds"]==census["stored_prefix_pair_edges"]==0,"child stored complete hidden worlds")
    _need(census["kernel"]["rank_calls"]==raw["rank_calls"] and census["training"]["calls"]==raw["training_calls"],"actual calls disagree with solver census")
    _need(census["kernel"]["work_units_cumulative"]<=admit["kernel"]["whole_request_upper_work"]<=admit["kernel"]["configured_limit"] and
        admit["combined_modeled_work_upper"]<=admit["whole_request_limit"],"child exceeded modeled requested work")
    _need(admit["retained_storage"]["whole_request_peak_upper"]<=admit["retained_storage"]["entry_limit"],"child exceeded modeled retained entry bound")
    pair_output=census["exact_pair_output"]
    if mode=="compact":
        _need(payload.get("pair_diagnostics")==FORMATS[mode] and "private_pair_probabilities" not in payload and
            "compatible_private_pairs" not in payload,"compact output unexpectedly contains pair diagnostics")
        _need(raw["pair_query_calls"]==payload.get("pair_runout_preflight_checks")==0 and
            pair_output["candidate_pairs_scanned"]==pair_output["board_scan_work_upper"]==pair_output["output_entry_upper"]==0 and
            pair_output["quadratic_diagnostic_stage"] is False,"compact output entered quadratic pair work")
        snapshot=payload["chance_input_snapshot"]
        _need(snapshot.get("contract")=="exact-product-selected-v1" and type(snapshot.get("ranges")) is list and len(snapshot["ranges"])==2,"compact prior snapshot missing")
    else:
        _need("pair_diagnostics" not in payload and "chance_input_snapshot" not in payload and
            type(payload.get("private_pair_probabilities")) is list and payload.get("compatible_private_pairs")==len(payload["private_pair_probabilities"]),"expanded output format changed")
        _need(raw["pair_query_calls"]==payload["candidate_private_pairs"]==pair_output["candidate_pairs_scanned"]==4,"expanded fixed game did not execute all candidate pair queries")
    if name=="original":
        _need(raw["training_calls"]==1 and raw["rank_calls"]>0 and payload["worlds"]==22 and payload["info_sets"]==1200,"original 22-world training identity mismatch")
    else:
        _need(mode=="compact" and raw["training_calls"]==0 and raw["rank_calls"]==2*comb(47,2) and
            payload["worlds"]==comb(47,2)*comb(45,2) and payload["info_sets"]==0 and payload["strategy"]==[],"full-range forced blind-all-in identity mismatch")
        ranges=payload["chance_input_snapshot"]["ranges"]
        _need([len(side) for side in ranges]==[1326,1326],"full-range compact prior dimensions mismatch")
        deck=tuple(rank+suit for rank in "23456789TJQKA" for suit in "cdhs")
        expected_hands={"".join(sorted(hand)) for hand in combinations(deck,2)}
        for side in ranges:
            _need(all(type(row) is dict and set(row)=={"hand","weight_hex"} and
                type(row["hand"]) is str and row["weight_hex"]==float(1).hex() for row in side),
                "full-range compact prior row/weight mismatch")
            _need({row["hand"] for row in side}==expected_hands,"full-range compact prior holdings do not cover the 52-card deck")
        _need(all(abs(payload[key])<=1e-12 for key in METRICS),"identical-prior forced-game value/BR/gain symmetry mismatch")


def _canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,
        allow_nan=False).encode("ascii")).hexdigest()


def _certificate(mode,case,payload):
    if mode=="expanded":
        exact=expanded_exact(case,payload)
        wrapper=None
    else:
        wrapper=compact_exact(case,payload)
        exact=wrapper["exact_certificate"]
        _need(wrapper["training_calls"]==wrapper["native_calls"]==0 and wrapper["production_pair_rows"]==0 and
            wrapper["physical_model_builds"]==3,"compact certificate preparation/call accounting mismatch")
        _need(wrapper["compact_input_canonical_sha256"]==_canonical(payload) and
            wrapper["verification_expansion_canonical_sha256"]==exact["input_policy_canonical_sha256"],
            "compact certificate input/verification hash binding mismatch")
    _need(type(exact.get("metrics")) is dict and set(exact["metrics"])==EXACT_METRICS and
        all(type(value) is str and value for value in exact["metrics"].values()),"exact certificate metric fields invalid")
    _need(exact.get("source_identity")=="four-street-independent-exact-v3" and exact.get("threshold")=="1/1000" and
        type(exact.get("threshold_met")) is bool,"exact certificate source/unchanged target invalid")
    normalized=exact.get("normalized_policy_sha256")
    _need(type(normalized) is str and len(normalized)==64 and all(c in "0123456789abcdef" for c in normalized),
        "exact normalized-policy hash invalid")
    if mode=="expanded":_need(exact.get("input_policy_canonical_sha256")==_canonical(payload),"expanded certificate input binding mismatch")
    return exact,wrapper


def _structural(payload):
    census=payload["operator_census"];admit=census["whole_request_admission"]
    return {"pair_output":census["exact_pair_output"],
        "kernel_actual_work":census["kernel"]["work_units_cumulative"],
        "kernel_requested_work_upper":admit["kernel"]["whole_request_upper_work"],
        "combined_requested_work_upper":admit["combined_modeled_work_upper"],
        "compact_input_snapshot_work_upper":admit["compact_input_snapshot_work_upper"],
        "modeled_retained_peak_entries":admit["retained_storage"]["whole_request_peak_upper"],
        "compact_prior_snapshot_entries_upper":admit["retained_storage"]["compact_prior_snapshot_entries_upper"],
        "scope":"Logical modeled work/retained slots and actual pair-query calls; not measured bytes or CPU time."}


def run(output):
    output=Path(output).resolve()
    _need(output!=ROOT and ROOT not in output.parents and not output.exists(),"Use a new external study directory")
    source=_identity();_need(not source["status"],"Commit and clean source before measurement")
    output.mkdir(parents=True)
    protocol={"version":"compact-exact-policy-complete-call-v1","source_commit":source["commit"],
        "source_sha256":source["sha256"],"runner_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "schedule":[{"case":name,"mode":mode,"sample":sample,"traced":traced} for name,mode,sample,traced in schedule()],
        "iterations":ITERATIONS,"rank_cache_boards":RANK_CACHE_BOARDS,"output_formats":FORMATS,
        "chance_contract":"exact-product-selected-v1","conversion_contract":"exact-product-vectors-binary64-v1",
        "retry_policy":"none; retain first sample/replay failure and every completed raw stream",
        "quality":"Compare unchanged exact metrics/normalized-policy hashes and retain every finite-iteration threshold miss. Rejection is not quality evidence.",
        "timing_scope":"Complete solve call with actual kernel/training count spies; request parsing and instrumentation imports precede timing/tracing. Independent certificates run outside measured children.",
        "memory_scope":"Separate complete-call Python allocation trace and Python process lifetime peak observations; never add them or infer general RAM savings.",
        "scope":"One 22-world choice-bearing four-street game and one-selected-board full-range forced blind-all-in contrast with zero decisions/training; no full-range choice solver/full-deck claim."}
    _write(output/"source-before.json",source);_write(output/"protocol.json",protocol)
    records=[];payloads={};certificates={};failure=None;rejection=None
    for name,mode,sample,traced in schedule():
        label=f"{name}-{mode}-{sample}";process=None
        try:
            command=[sys.executable,"-B","-m","scripts.benchmark_compact_exact_policy","--child",name,"--mode",mode]
            if traced:command.append("--traced")
            process=subprocess.run(command,cwd=ROOT,capture_output=True,check=False)
            (output/(label+".json")).write_bytes(process.stdout)
            (output/(label+".stderr.txt")).write_bytes(process.stderr)
            _need(process.returncode==0,"child exited with status "+str(process.returncode))
            raw=_decode(process.stdout);_validate_child(raw,name,mode,traced)
            record={"artifact":label+".json","raw_sha256":hashlib.sha256(process.stdout).hexdigest(),"sample":sample,
                **{key:value for key,value in raw.items() if key!="payload"}}
            records.append(record)
            print(label,raw["status"],f"{raw['seconds']:.6f}",flush=True)
            if raw["status"]=="complete":payloads[(name,mode,sample,traced)]=raw["payload"]
            if name=="original" and sample==0:
                _need(_identity()==source,"source changed before independent exact mathematics")
                exact,wrapper=_certificate(mode,case_for(name),raw["payload"])
                artifact=label+"-certificate.json"
                _write(output/artifact,wrapper if wrapper is not None else exact)
                certificates[mode]={"artifact":artifact,"metrics":exact["metrics"],"threshold":exact["threshold"],
                    "threshold_met":exact["threshold_met"],"normalized_policy_sha256":exact["normalized_policy_sha256"]}
            if name==FULL_RANGE and mode=="compact":
                _need(_identity()==source,"source changed before bounded full-range certificate control")
                builds=[]
                def forbidden_build(*args,**kwargs):
                    builds.append(1)
                    raise AssertionError("Full-range verification entered its capped physical model")
                with patch.object(physical,"build_model",new=forbidden_build):
                    try:compact_exact(case_for(name),raw["payload"])
                    except ValueError as exc:
                        _need(str(exc)==f"each range must contain at most {physical.MAX_HANDS_PER_PLAYER} hands",
                            "full-range verifier rejected for an unrelated reason")
                        rejection={"status":"rejected","error_type":type(exc).__name__,"error":str(exc),"physical_model_builds":len(builds),
                            "training_calls":0,"native_calls":0,"quality_status":"not certified under unchanged small-game caps"}
                    else:raise ValueError("Full-range compact policy unexpectedly passed the small-game certificate")
                _need(not builds,"full-range certificate entered physical model construction")
                _write(output/"full-range-compact-certificate-rejection.json",rejection)
        except Exception as exc:
            failure={"artifact":label,"error_type":type(exc).__name__,"error":str(exc),
                "child_returncode":None if process is None else process.returncode}
            _write(output/(label+"-failure.json"),failure)
            break
    source_after=None
    try:
        source_after=_identity()
        if source_after!=source:failure={"stage":"source-changed","prior_failure":failure}
    except Exception as exc:
        failure={"stage":"source-identity-failed","error_type":type(exc).__name__,"error":str(exc),"prior_failure":failure}
    _write(output/"source-after.json",source_after)
    comparisons=[];checks={};structures={}
    if failure is None:
        try:
            for sample,traced in ((0,False),(1,False),(2,False),("traced",True)):
                left=payloads[("original","expanded",sample,traced)];right=payloads[("original","compact",sample,traced)]
                comparisons.append({"sample":sample,"traced":traced,"complete_strategy_identical":left["strategy"]==right["strategy"],
                    "all_eight_metrics_identical":all(left[key]==right[key] for key in METRICS),
                    "same_game_counts":all(left[key]==right[key] for key in ("worlds","public_states","decisions","info_sets"))})
            checks["all_paired_complete_strategies_identical"]=all(row["complete_strategy_identical"] for row in comparisons)
            checks["all_paired_eight_metrics_identical"]=all(row["all_eight_metrics_identical"] for row in comparisons)
            checks["all_paired_game_counts_identical"]=all(row["same_game_counts"] for row in comparisons)
            reference=payloads[("original","expanded",0,False)]
            checks["all_normal_samples_match_sample_zero"]=all(
                value["strategy"]==reference["strategy"] and all(value[key]==reference[key] for key in METRICS)
                for (case_name,_mode,_sample,_traced),value in payloads.items() if case_name=="original")
            checks["sample_zero_exact_metrics_identical"]=certificates["expanded"]["metrics"]==certificates["compact"]["metrics"]
            checks["sample_zero_normalized_policy_hash_identical"]=certificates["expanded"]["normalized_policy_sha256"]==certificates["compact"]["normalized_policy_sha256"]
            checks["sample_zero_exact_threshold_and_flag_identical"]=all(certificates["expanded"][key]==certificates["compact"][key] for key in ("threshold","threshold_met"))
            checks["full_range_compact_certificate_rejected_before_physical_model"]=rejection is not None and rejection["physical_model_builds"]==0
            _need(all(checks.values()),"paired policy/metric/certificate acceptance mismatch")
            for mode in MODES:structures[mode]=_structural(payloads[("original",mode,0,False)])
            structures["full_range_compact"]=_structural(payloads[(FULL_RANGE,"compact",0,False)])
        except Exception as exc:
            failure={"stage":"paired-acceptance","error_type":type(exc).__name__,"error":str(exc)}
    medians={mode:None for mode in MODES}
    for mode in MODES:
        values=[row["seconds"] for row in records if row["case"]=="original" and row["mode"]==mode and not row["traced"]]
        if values:medians[mode]=statistics.median(values)
    report={"outcome":"complete" if failure is None else "failed","source_commit":source["commit"],"protocol":protocol,
        "samples":records,"paired_comparisons":comparisons,"checks":checks,"failure":failure,"certificates":certificates,
        "full_range_certificate_rejection":rejection,"structural_comparison":structures,"medians_seconds":medians,
        "complete_child_calls":len(records),"training_calls":sum(row["training_calls"] for row in records),
        "pair_query_calls":sum(row["pair_query_calls"] for row in records),"native_calls":sum(row["native_calls"] for row in records),
        "scope":protocol["scope"],"memory_scope":protocol["memory_scope"]}
    _write(output/"report.json",report)
    _write(output/"manifest.json",{"source_commit":source["commit"],"sha256":{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(output.iterdir()) if path.is_file()}})
    return {"outcome":report["outcome"],"manifest_sha256":hashlib.sha256((output/"manifest.json").read_bytes()).hexdigest(),"failure":failure}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--child",choices=("original",FULL_RANGE));parser.add_argument("--mode",choices=MODES)
    parser.add_argument("--traced",action="store_true")
    args=parser.parse_args()
    if args.child:
        if args.mode is None:parser.error("--mode is required for child execution")
        result=child(args.child,args.mode,args.traced)
    else:
        if args.output is None:parser.error("--output is required for a fixed study")
        result=run(args.output)
    print(json.dumps(result,allow_nan=False))
    return 0 if args.child or result["outcome"]=="complete" else 1


if __name__=="__main__":raise SystemExit(main())
