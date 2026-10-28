"""External read-only authentication and saved replay for the fixed dyadic study.

Never run until the lead confirms the producer terminal handle and supplies
manifest/archive pins. No current/archived solver, training or native callback
is executed; the unchanged bounded physical oracle and compact certificate run
only after the complete clean committed source and every artifact authenticate.
"""
import argparse
import ast
from contextlib import ExitStack
from fractions import Fraction
import hashlib
import importlib.util
from itertools import combinations
import json
import math
from pathlib import Path
import statistics
import sys
from unittest.mock import patch

AUTH_SHA="8171ead3ba108f8200f15e85696f40d109ed894209fa7d77598780b83c1401c5"
FORMAT="compact-exact-product-inputs-v1"
MODES=("fraction","dyadic")
METRICS=("value_sb","value_bb","sb_best_response_value","bb_best_response_value",
         "sb_gain","bb_gain","nash_conv","exploitability")
FULL="full-range-forced-all-in"
SCHEDULE=(("original",10,"fraction",0,False),("original",10,"dyadic",0,False),
    ("original",10,"dyadic",1,False),("original",10,"fraction",1,False),
    ("original",10,"fraction",2,False),("original",10,"dyadic",2,False),
    ("original",10,"fraction","traced",True),("original",10,"dyadic","traced",True),
    ("original",100,"fraction",0,False),("original",100,"dyadic",0,False),
    ("one-world",1000,"fraction",0,False),("one-world",1000,"dyadic",0,False),
    ("original",1000,"dyadic","resource-control",False),(FULL,10,"dyadic",0,False))
PAIR_SCHEDULE=(("original",10,0,False),("original",10,1,False),("original",10,2,False),
    ("original",10,"traced",True),("original",100,0,False),("one-world",1000,0,False))


def case_for(base,name):
    if name=="original":return dict(base)
    if name=="one-world":return dict(base,id="dyadic-selected-one-world-four-street-v1",
        sb_range="AsAd",bb_range="KsKd",runouts=["2c3c4d7h8h"])
    if name==FULL:return dict(base,id="dyadic-selected-full-range-forced-all-in-v1",
        sb_range="random",bb_range="random",runouts=["2c3d4h5s6c"],config=dict(base["config"],starting_stack=[.5,1]))
    raise ValueError("unknown fixed saved case")


def structural(payload):
    c=payload["operator_census"];a=c["whole_request_admission"]
    return {"kernel_actual_work":c["kernel"]["work_units_cumulative"],
        "kernel_requested_work_upper":a["kernel"]["whole_request_upper_work"],
        "combined_requested_work_upper":a["combined_modeled_work_upper"],
        "retained_peak_entries_upper":a["retained_storage"]["whole_request_peak_upper"],
        "integer_arithmetic":c["kernel"].get("integer_arithmetic"),
        "dyadic_forecast":c.get("bit_forecast",{}).get("dyadic_integer"),
        "scope":"Logical modeled work/slots and integer-operation receipts; not CPU or Python memory bytes."}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("repo","study","receipt","archive"):parser.add_argument("--"+key,type=Path,required=True)
    for key in ("source-commit","manifest-sha256","archive-sha256","confirmed-terminal-handle"):
        parser.add_argument("--"+key,required=True)
    parser.add_argument("--terminal-exit-code",type=int,required=True)
    args=parser.parse_args()
    auth_path=Path(__file__).with_name("exact-selected-independent-review.py")
    if hashlib.sha256(auth_path.read_bytes()).hexdigest()!=AUTH_SHA:raise ValueError("authentication helper pin changed")
    spec=importlib.util.spec_from_file_location("dyadic_saved_auth",auth_path)
    auth=importlib.util.module_from_spec(spec);spec.loader.exec_module(auth)
    auth.FROZEN=args.source_commit
    need,sha,parse=auth.need,auth.sha,auth.parse
    need(args.confirmed_terminal_handle and args.terminal_exit_code==0,"lead-confirmed terminal success required")
    repo,study,out=args.repo.resolve(),args.study.resolve(),args.receipt.resolve()
    need(not out.exists() and repo not in out.parents and study not in out.parents,"new external receipt required")
    saved={p.relative_to(study).as_posix():p.read_bytes() for p in study.rglob("*") if p.is_file()}
    need(sha(saved["manifest.json"])==args.manifest_sha256,"external manifest pin mismatch")
    manifest=parse(saved["manifest.json"])
    need(manifest["source_commit"]==args.source_commit,"manifest source mismatch")
    need(set(saved)==set(manifest["sha256"])|{"manifest.json"},"manifest inventory mismatch")
    for name,digest in manifest["sha256"].items():
        need(Path(name).name==name and sha(saved[name])==digest,"saved artifact drift: "+name)
    source=parse(saved["source-before.json"])
    authenticated=auth.source_identity(repo,source) # BEFORE any repository imports or mathematical replay.
    need(parse(saved["source-after.json"])==source,"captured source changed during producer")
    archive=auth.archive_check(args.archive,args.archive_sha256,saved)
    # Pin unchanged independent arithmetic/shape caps without importing source.
    certificate_ast=ast.parse((repo/"scripts/four_street_certificate.py").read_text())
    values=[ast.literal_eval(n.value) for n in certificate_ast.body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=="MAX_FRACTION_BITS" for t in n.targets)]
    need(values==[65536],"independent exact integer-bit cap changed")
    protocol,report=parse(saved["protocol.json"]),parse(saved["report.json"])
    need(report["outcome"]=="complete" and report["failure"] is None,"producer did not complete")
    need(protocol==report["protocol"] and protocol["source_commit"]==report["source_commit"]==args.source_commit,
        "report/protocol source mismatch")
    need(protocol["version"]=="exact-product-dyadic-selected-paired-study-v1" and protocol["calls"]==14,
        "wrong dyadic protocol")
    need(protocol["source_sha256"]==source["sha256"] and
        protocol["runner_sha256"]==source["sha256"]["scripts/benchmark_dyadic_selected_solver.py"],"runner source binding mismatch")
    need(protocol["chance_contract"]=="exact-product-selected-v1" and
        protocol["conversion_contract"]=="exact-product-vectors-binary64-v1" and protocol["pair_diagnostics"]=="compact",
        "protocol mathematical law/output mode drift")
    need(protocol["schedule"]==[dict(case=n,iterations=t,mode=m,sample=s,traced=tr) for n,t,m,s,tr in SCHEDULE],
        "fixed 14-call schedule mismatch")
    runtime=protocol["runtime"]
    need(type(runtime) is dict and set(runtime)=={"python_implementation","python_version","python_sys_version",
        "os_system","os_platform","machine"} and all(type(value) is str and value for value in runtime.values()),
        "producer runtime fingerprint malformed")
    need(len(report["samples"])==report["complete_child_calls"]==14,"incomplete producer sample schedule")
    base=parse((repo/"benchmarks/four-street-integration-v1.json").read_bytes())["case"]
    payloads={};records=[];certificate_artifacts={};rejections=[];integer_receipts={}
    deck=tuple(r+s for r in "23456789TJQKA" for s in "cdhs")
    universe={"".join(sorted(h)):float(1).hex() for h in combinations(deck,2)}
    for record,(name,iterations,mode,sample,traced) in zip(report["samples"],SCHEDULE):
        label=f"{name}-T{iterations}-{mode}-{sample}";artifact=label+".json"
        raw=parse(saved[artifact]);payload=raw["payload"]
        need(raw["runtime"]==runtime,"child runtime differs from pinned producer protocol")
        need(record["artifact"]==artifact and record["sample"]==sample and record["raw_sha256"]==sha(saved[artifact]),
            "report/raw sample binding mismatch")
        need({k:v for k,v in record.items() if k not in ("artifact","sample","raw_sha256")}==
            {k:v for k,v in raw.items() if k!="payload"},"reported metadata differs from raw child")
        for key,expected in (("case",name),("iterations",iterations),("mode",mode),("pair_diagnostics","compact"),
                ("output_format",FORMAT),("traced",traced),("rank_cache_boards",64)):
            need(type(raw[key]) is type(expected) and raw[key]==expected,"wrong sample request metadata: "+key)
        need(type(raw["seconds"]) in (int,float) and math.isfinite(raw["seconds"]) and raw["seconds"]>0,"invalid time observation")
        need(type(raw["python_process_peak_bytes"]) is int and raw["python_process_peak_bytes"]>0,"invalid process peak")
        allocation=raw["python_allocation_peak_bytes"]
        need((type(allocation) is int and allocation>0) if traced else allocation is None,"allocation trace scope mismatch")
        for key in ("training_calls","pair_query_calls","rank_calls","native_calls"):
            need(type(raw[key]) is int and raw[key]>=0,"invalid actual call counter")
        need(raw["pair_query_calls"]==raw["native_calls"]==0,"producer entered private-pair or native execution")
        if sample=="resource-control":
            need(raw["status"]=="pretraining-rejected" and payload is None and raw["training_calls"]==raw["rank_calls"]==0,
                "resource control entered rank/training")
            error=raw["error"]
            need(type(error) is dict and error["type"]=="ValueError" and type(error["message"]) is str and
                any(token in error["message"].lower() for token in ("admission","limit","forecast","cap","envelope")),
                "resource control did not identify unchanged admission limit")
            rejections.append({"artifact":artifact,"raw_sha256":sha(saved[artifact]),"error":error,"training_calls":0,
                "rank_calls":0,"pair_query_calls":0,"native_calls":0,"quality_status":"not trained or certified"})
            need(label+"-certificate.json" not in saved,"untrained control has certificate")
            records.append(record);continue
        need(raw["status"]=="complete" and raw["error"] is None and type(payload) is dict,"expected complete solver sample")
        for key,expected in (("chance_contract","exact-product-selected-v1"),("conversion_contract","exact-product-vectors-binary64-v1"),
                ("execution_backend","exact-product-selected-direct-packed-python"),("pair_diagnostics",FORMAT),("iterations",iterations)):
            need(payload[key]==expected,"solver law/backend/iteration mismatch")
        need("private_pair_probabilities" not in payload and "compatible_private_pairs" not in payload,"compact policy contains pair table")
        need(type(payload["strategy"]) is list and type(payload["info_sets"]) is int and
            len(payload["strategy"])==payload["info_sets"],"saved strategy row coverage mismatch")
        need(all(type(payload[k]) in (int,float) and math.isfinite(payload[k]) for k in METRICS),"invalid floating diagnostic")
        c=payload["operator_census"];a=c["whole_request_admission"];k=c["kernel"]
        need(c["stored_complete_worlds"]==c["stored_prefix_pair_edges"]==0,"materialized complete hidden worlds")
        need(k["rank_calls"]==raw["rank_calls"] and c["training"]["calls"]==raw["training_calls"],"spy/census counter mismatch")
        need(k["work_units_cumulative"]<=a["kernel"]["whole_request_upper_work"]<=a["kernel"]["configured_limit"]==500000000,
            "kernel logical work cap exceeded or changed")
        need(a["combined_modeled_work_upper"]<=a["whole_request_limit"]==500000000 and
            a["retained_storage"]["whole_request_peak_upper"]<=a["retained_storage"]["entry_limit"],"whole-solve work/entry cap exceeded")
        need(c["float_adapter"]["modeled_work_entries"]<=a["adapter"]["whole_request_work_upper"]<=a["adapter"]["configured_work_limit"],
            "adapter work envelope exceeded")
        pairs=c["exact_pair_output"]
        need(payload["pair_runout_preflight_checks"]==pairs["candidate_pairs_scanned"]==pairs["board_scan_work_upper"]==pairs["output_entry_upper"]==0 and
            pairs["quadratic_diagnostic_stage"] is False,"compact pair output/work not zero")
        witness=payload["chance_input_snapshot"]
        need(type(witness) is dict and set(witness)=={"contract","ranges"} and witness["contract"]=="exact-product-selected-v1" and
            type(witness["ranges"]) is list and len(witness["ranges"])==2,"compact witness schema mismatch")
        sizes=[1326,1326] if name==FULL else ([1,1] if name=="one-world" else [2,2])
        for side,size in zip(witness["ranges"],sizes):
            need(type(side) is list and len(side)==size,"compact witness side count mismatch")
            need(all(type(row) is dict and set(row)=={"hand","weight_hex"} and type(row["hand"]) is str and len(row["hand"])==4 and
                type(row["weight_hex"]) is str and len(row["weight_hex"])<=64 for row in side),"malformed compact prior row")
            need(len({row["hand"] for row in side})==size,"duplicate compact holdings")
            for row in side:
                try:weight=float.fromhex(row["weight_hex"])
                except (ValueError,OverflowError) as exc:raise ValueError("invalid compact weight hex") from exc
                need(math.isfinite(weight) and weight>0 and weight.hex()==row["weight_hex"],"noncanonical compact binary64 prior")
        if mode=="dyadic":
            actual=k["integer_arithmetic"];forecast=c["bit_forecast"]["dyadic_integer"]
            need(k["arithmetic"]=="exact-dyadic-integer-buckets-v1" and actual["version"]=="dyadic-selected-arithmetic-v1", "dyadic arithmetic contract mismatch")
            need(actual["max_integer_bits"]==65536 and actual["integer_payload_bit_limit"]==forecast["logical_integer_payload_bit_limit"]==(1<<30),
                "dyadic integer/retained-payload cap changed")
            need(actual["peak_operand_bits"]<=forecast["maximum_bits_upper"]<=65536 and
                actual["peak_forecast_bits"]<=forecast["maximum_bits_upper"] and
                actual["peak_integer_payload_bits"]<=forecast["logical_integer_payload_bits_upper"]<=(1<<30) and
                actual["modeled_limb_work_upper"]<=forecast["whole_request_limb_work_upper"],"actual integer receipt exceeds forecast")
            for field in ("integer_additions","integer_multiplications","integer_shifts"):
                need(type(actual["integer_operations"][field]) is int and actual["integer_operations"][field]>=0,"invalid integer operation count")
            op_count=sum(actual["integer_operations"].values())+4*actual["rational_output_components"]
            need(actual["modeled_integer_and_fraction_output_ops"]==op_count and actual["modeled_limb_work_upper"]==
                op_count*max(1,(actual["peak_operand_bits"]+63)//64)**2,"counted integer-core work model inconsistent")
            need(actual["retained_plan_entries"]<=actual["setup_reservation_entries"],"dyadic retained plan exceeds reserve")
            need(forecast["whole_request_limb_work_upper"]==a["kernel"]["whole_request_upper_work"]*forecast["limbs64_per_value_upper"]**2,
                "whole-request counted-core limb envelope inconsistent")
            integer_receipts[label]={"actual":actual,"forecast":forecast}
        else:
            need("integer_arithmetic" not in k and "arithmetic" not in k,"Fraction mode unexpectedly used dyadic arithmetic")
        if name==FULL:
            need(raw["training_calls"]==0 and raw["rank_calls"]==2162 and payload["worlds"]==math.comb(47,2)*math.comb(45,2)==1070190 and
                payload["info_sets"]==0 and payload["strategy"]==[] and payload["public_states"]==1 and payload["decisions"]==0,
                "full-range forced control has choices or wrong support")
            need(payload["selected_runouts"]==payload["reachable_runouts"]==[["2c","3d","4h","5s","6c"]] and
                payload["runout_mode"]=="conditioned-ordered-selected-runouts","full-range selected chance identity changed")
            config=payload["preflop_config"]
            need(config["starting_stack"]==[.5,1] and config["small_blind"]==.5 and config["big_blind"]==1,
                "full-range zero-choice blind/stack identity changed")
            need(all(abs(payload[key])<=1e-12 for key in METRICS),"forced identical-prior symmetry failed")
            need(all({row["hand"]:row["weight_hex"] for row in side}==universe for side in witness["ranges"]),"full-range uniform witness incomplete")
        else:
            need(raw["training_calls"]==1 and raw["rank_calls"]>0 and payload["info_sets"]>0,"choice sample did not train/rank")
            need(payload["worlds"]==(1 if name=="one-world" else 22),"fixed physical world support differs")
            if name=="original":need(payload["info_sets"]==1200,"original four-street row count differs")
        payloads[(name,iterations,mode,sample,traced)]=payload
        if name in ("original","one-world") and sample==0:
            artifact=label+"-certificate.json";wrapper=parse(saved[artifact]);exact=wrapper["exact_certificate"]
            key=f"{name}|{iterations}|{mode}"
            need(wrapper["contract"]=="compact-exact-product-certificate-v1" and wrapper["physical_model_builds"]==3 and
                wrapper["production_pair_rows"]==wrapper["training_calls"]==wrapper["native_calls"]==0,"compact certificate preparation/call accounting mismatch")
            need(wrapper["compact_input_canonical_sha256"]==auth.canonical(payload) and
                wrapper["verification_expansion_canonical_sha256"]==exact["input_policy_canonical_sha256"],"saved compact/verification input hash binding mismatch")
            exact_metrics=auth.metrics(exact["metrics"])
            need(auth.bounded_fraction(exact["threshold"])==Fraction(1,1000) and type(exact["threshold_met"]) is bool and
                exact["threshold_met"]==(exact_metrics["nash_conv"]<=Fraction(1,1000)),"exact threshold/quality flag mismatch")
            need(exact["source_identity"]=="four-street-independent-exact-v3" and exact["fraction_bit_limit"]==65536 and
                exact["maximum_fraction_bits"]<=65536,"unchanged independent exact arithmetic cap/source mismatch")
            expected_summary={"artifact":artifact,"metrics":exact["metrics"],"threshold":exact["threshold"],
                "threshold_met":exact["threshold_met"],"normalized_policy_sha256":exact["normalized_policy_sha256"]}
            need(report["certificates"][key]==expected_summary,"report exact-certificate summary differs from saved artifact")
            certificate_artifacts[(name,iterations,mode)]=(artifact,wrapper)
        records.append(record)
    need(len(certificate_artifacts)==6 and set(report["certificates"])=={"|".join(map(str,key)) for key in certificate_artifacts},
        "expected six complete sample-zero certificates")
    need(sum(row["training_calls"] for row in records)==report["training_calls"]==12 and
        report["pair_query_calls"]==report["native_calls"]==0,"aggregate actual producer call counts differ")
    resource=next(row for row in records if row["sample"]=="resource-control")
    expected_resource={"case":"original-T1000-dyadic","sample":"resource-control","status":resource["status"],
        "raw_artifact":resource["artifact"],"raw_sha256":resource["raw_sha256"],"error":resource["error"],
        **{key:resource[key] for key in ("training_calls","rank_calls","pair_query_calls","native_calls")}}
    need(report["resource_control"]==expected_resource and len(rejections)==1,
        "resource control report disagrees with raw zero-call rejection")
    full_record=records[-1]
    full_cap=parse(saved["full-range-compact-certificate-rejection.json"])
    expected_full_cap={"status":"rejected-before-physical-model","error_type":"ValueError",
        "error":"each range must contain at most 4 hands","unchanged_hand_cap":4,"physical_model_builds":0,
        "training_calls":0,"native_calls":0,"production_pair_rows":0,
        "scope":"Independent compact certificate is intentionally capped; this rejection is not a solver quality failure.",
        "raw_artifact":full_record["artifact"],"raw_sha256":full_record["raw_sha256"],
        "solver_counters":{key:full_record[key] for key in ("training_calls","rank_calls","pair_query_calls","native_calls")}}
    need(full_cap==expected_full_cap and report["full_range_certificate_rejection"]==full_cap,
        "reported full-range capped-certificate rejection lacks raw binding or unchanged zero-build cap")
    comparisons=[];checks={}
    for name,iterations,sample,traced in PAIR_SCHEDULE:
        left,right=(payloads[(name,iterations,mode,sample,traced)] for mode in MODES)
        comparisons.append({"case":name,"iterations":iterations,"sample":sample,"traced":traced,
            "complete_strategy_identical":left["strategy"]==right["strategy"],
            "all_eight_metrics_identical":all(left[key]==right[key] for key in METRICS),
            "same_game_counts":all(left[key]==right[key] for key in ("worlds","public_states","decisions","info_sets"))})
        need(left["chance_input_snapshot"]==right["chance_input_snapshot"],"paired compact input witness differs")
    need(comparisons==report["paired_comparisons"],"reported paired comparisons do not match raw samples")
    checks["all_paired_strategies_identical"]=all(row["complete_strategy_identical"] for row in comparisons)
    checks["all_paired_eight_metrics_identical"]=all(row["all_eight_metrics_identical"] for row in comparisons)
    checks["all_paired_game_counts_identical"]=all(row["same_game_counts"] for row in comparisons)
    checks["paired_compact_chance_snapshots_identical"]=all(
        payloads[(name,iterations,"fraction",sample,traced)]["chance_input_snapshot"]==
        payloads[(name,iterations,"dyadic",sample,traced)]["chance_input_snapshot"]
        for name,iterations,sample,traced in PAIR_SCHEDULE)
    original=payloads[("original",10,"fraction",0,False)]
    t10=[payload for (name,iterations,mode,sample,traced),payload in payloads.items() if name=="original" and iterations==10]
    checks["all_original_T10_policies_match_sample_zero"]=len(t10)==8 and all(p["strategy"]==original["strategy"] for p in t10)
    checks["all_original_T10_metrics_match_sample_zero"]=len(t10)==8 and all(all(p[k]==original[k] for k in METRICS) for p in t10)
    for name,iterations in (("original",10),("original",100),("one-world",1000)):
        left,right=(certificate_artifacts[(name,iterations,mode)][1]["exact_certificate"] for mode in MODES)
        checks[f"{name}_T{iterations}_certificate_metrics_identical"]=left["metrics"]==right["metrics"]
        checks[f"{name}_T{iterations}_normalized_policy_hash_identical"]=left["normalized_policy_sha256"]==right["normalized_policy_sha256"]
        checks[f"{name}_T{iterations}_threshold_and_flag_identical"]=all(left[key]==right[key] for key in ("threshold","threshold_met"))
    checks["exact_threshold_flags_recorded"]=all(type(wrapper["exact_certificate"]["threshold_met"]) is bool for artifact,wrapper in certificate_artifacts.values())
    checks["full_range_compact_certificate_rejected_before_physical_model"]=(full_cap["physical_model_builds"]==0 and
        full_cap["raw_sha256"]==full_record["raw_sha256"])
    need(checks==report["checks"] and all(checks.values()),"reported certificate/paired acceptance differs from independent derivation")
    original=payloads[("original",10,"fraction",0,False)]
    for key,payload in payloads.items():
        name,iterations,mode,sample,traced=key
        if name!=FULL:
            certified_reference=payloads[(name,10 if name=="original" else 1000,"fraction",0,False)]
            identity_fields=("selected_runouts","reachable_runouts","preflop_config","postflop_action_configs",
                "runout_mode","chance_contract","conversion_contract","numerical_model","algorithm","method",
                "solver_version","strategy_schema","representation_version","public_topology",
                "worlds","public_states","decisions","info_sets")
            need(all(payload[field]==certified_reference[field] for field in identity_fields),
                "same-case declared game identity differs from independently certified sample zero")
        if name=="original" and iterations==10:
            need(payload["strategy"]==original["strategy"] and all(payload[field]==original[field] for field in METRICS) and
                payload["chance_input_snapshot"]==original["chance_input_snapshot"],"repeated T10 policy/metric/witness identity changed")
    structures={f"original_T10_{mode}":structural(payloads[("original",10,mode,0,False)]) for mode in MODES}
    structures["one_world_T1000_dyadic"]=structural(payloads[("one-world",1000,"dyadic",0,False)])
    structures["full_range_dyadic"]=structural(payloads[(FULL,10,"dyadic",0,False)])
    need(structures==report["structural_comparison"],"reported structural counters differ from actual saved payloads")
    for mode in MODES:
        times=[row["seconds"] for row in records if row["case"]=="original" and row["iterations"]==10 and row["mode"]==mode and not row["traced"]]
        need(len(times)==3 and report["medians_original_T10_seconds"][mode]==statistics.median(times),"reported T10 median differs from three raw untraced calls")
    # Source closure, all raw samples, witnesses and saved certificate bindings
    # authenticate above. Only now may independent bounded mathematics import.
    sys.dont_write_bytecode=True;sys.path.insert(0,str(repo))
    from scripts import four_street_validation as physical
    from scripts.preflop_validation import compare_result
    from scripts.exact_selected_compact_certificate import evaluate_exact
    forbidden=("pokerlab.exact_selected_solver.solve_four_street_exact_selected","pokerlab.exact_selected_solver.train_packed",
        "pokerlab.packed_operator_cfr.train_packed","pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.__init__",
        "pokerlab.dyadic_selected_arithmetic.DyadicSelectedArithmeticPlan.__init__",
        "pokerlab.dyadic_selected_arithmetic.DyadicSelectedArithmeticPlan.marginals",
        "pokerlab.dyadic_selected_arithmetic.DyadicSelectedArithmeticPlan.terminal",
        "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.terminal_values_exact",
        "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.joint_marginals_exact","pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.pair_probability_exact",
        "pokerlab.selected_operator_solver.solve_four_street_operator","pokerlab.preflop_solver.solve_preflop",
        "pokerlab.native_selected_operator.train_native_selected","pokerlab.native_selected_dag.train_native_selected_dag",
        "pokerlab.native_public_cfr.train_native_public","pokerlab.public_cfr._train_prepared","pokerlab.cfr.train","subprocess.Popen")
    numeric_replays=[];fresh_exacts={};models={};full_rejection=None
    with ExitStack() as stack:
        for target in forbidden:stack.enter_context(patch(target,side_effect=AssertionError("forbidden saved-review call: "+target)))
        for key,payload in payloads.items():
            name,iterations,mode,sample,traced=key
            if name==FULL:continue
            case=case_for(base,name)
            if name not in models:models[name]=physical.build_model(case)
            model=models[name]
            expected_witness=tuple({"".join(hand):float(weight).hex() for hand,weight in side.items()} for side in physical._case_inputs(case)[-1])
            observed=tuple({row["hand"]:row["weight_hex"] for row in side} for side in payload["chance_input_snapshot"]["ranges"])
            need(observed==expected_witness,"compact witness differs from independent physical case inputs")
            pair_rows=[{"sb_hand":row["sb_hand"],"bb_hand":row["bb_hand"],"probability":float(Fraction(row["fraction"]))}
                for row in model.counts["pair_probabilities"]]
            verification_only=dict(payload,private_pair_probabilities=pair_rows,compatible_private_pairs=model.counts["compatible_pairs"])
            replay=physical.replay_policy(verification_only,case)
            gaps=compare_result(verification_only,replay);auth.numeric_gaps(gaps)
            need(replay["checked_information_sets"]==payload["info_sets"] and replay["worlds"]==payload["worlds"],"fresh physical replay incomplete")
            label=f"{name}-T{iterations}-{mode}-{sample}"
            numeric_replays.append({"artifact":label+".json","rows":payload["info_sets"],"worlds":payload["worlds"],"numeric_gaps":gaps})
            if (name,iterations,mode) in certificate_artifacts and sample==0:
                builds=[];original_build=physical.build_model
                def counted_build(*args_,**kwargs_):
                    builds.append(1);return original_build(*args_,**kwargs_)
                with patch.object(physical,"build_model",new=counted_build):fresh=evaluate_exact(case,payload)
                artifact,stored=certificate_artifacts[(name,iterations,mode)]
                need(fresh==stored,"fresh unchanged compact exact certificate differs from saved certificate")
                need(len(builds)==fresh["physical_model_builds"]==3,"fresh compact certificate actual model-build count mismatch")
                exact=fresh["exact_certificate"];exact_metrics=auth.metrics(exact["metrics"])
                need(exact["threshold_met"]==(exact_metrics["nash_conv"]<=Fraction(1,1000)),"fresh exact target flag differs")
                fresh_exacts[label]={"artifact":artifact,"metrics":exact["metrics"],"threshold":exact["threshold"],
                    "threshold_met":exact["threshold_met"],"normalized_policy_sha256":exact["normalized_policy_sha256"],
                    "compact_input_canonical_sha256":fresh["compact_input_canonical_sha256"],"actual_model_builds":len(builds)}
        full_case=case_for(base,FULL)
        builds=[]
        def forbidden_build(*args_,**kwargs_):
            builds.append(1);raise AssertionError("full-range certificate entered physical model construction")
        with patch.object(physical,"build_model",new=forbidden_build):
            try:evaluate_exact(full_case,payloads[(FULL,10,"dyadic",0,False)])
            except ValueError as exc:
                need(str(exc)==f"each range must contain at most {physical.MAX_HANDS_PER_PLAYER} hands","full-range certificate rejection reason changed")
                need(physical.MAX_HANDS_PER_PLAYER==full_cap["unchanged_hand_cap"]==4 and
                    str(exc)==full_cap["error"] and type(exc).__name__==full_cap["error_type"],
                    "fresh full-range verifier cap differs from raw bound rejection")
                full_rejection={"error_type":type(exc).__name__,"error":str(exc),"physical_model_builds":len(builds),
                    "producer_bound_rejection":full_cap,"quality_status":"not certified under unchanged small-game hand cap"}
            else:raise ValueError("full-range forced game unexpectedly passed capped physical verification")
        need(not builds,"full-range verifier allocated physical model")
    need(len(numeric_replays)==12 and len(fresh_exacts)==6,"incomplete independent saved-policy/exact replay schedule")
    need(auth.source_identity(repo,source)==authenticated,"source changed during independent saved review")
    need({p.relative_to(study).as_posix():p.read_bytes() for p in study.rglob("*") if p.is_file()}==saved,"saved inventory/raw bytes changed during review")
    need(auth.archive_check(args.archive,args.archive_sha256,saved)==archive,"study archive changed during review")
    result={"outcome":"accepted","reviewer":"independent Sol substitute; bounded saved-only physical/exact replay",
        "source_commit":args.source_commit,"authenticated_source_files":authenticated["files"],"source_raw_sha256":authenticated["raw_sha256"],
        "raw_committed_blob_files":authenticated["raw_committed_blob_files"],"normalized_committed_blob_files":authenticated["normalized_committed_blob_files"],
        "source_and_artifacts_unchanged_after_review":True,"manifest_sha256":args.manifest_sha256,"archive":archive,
        "artifact_sha256":{name:sha(raw) for name,raw in saved.items()},"confirmed_terminal_handle":args.confirmed_terminal_handle,"terminal_exit_code":0,
        "producer_runtime":runtime,"producer_training_calls":12,"producer_pair_query_calls":0,"producer_native_calls":0,"review_training_calls":0,"review_native_calls":0,
        "review_exact_kernel_callback_calls":0,"forbidden_entry_points":list(forbidden),"fresh_numeric_replays":numeric_replays,"fresh_exact":fresh_exacts,
        "retained_pretraining_rejections":rejections,"full_range_capped_certificate_rejection":full_rejection,
        "derived_paired_comparisons":comparisons,"derived_checks":checks,"derived_structural_comparison":structures,"integer_receipts":integer_receipts,
        "review_helper_sha256":sha(Path(__file__).read_bytes()),"authentication_helper_sha256":AUTH_SHA,
        "quality_scope":"Actual unchanged 1/1000-BB exact target flags preserved per small fixed case; resource rejection and full-range zero-choice control are no larger-quality proof.",
        "computation_scope":"Integer limb receipts model counted query-core/output subsets, not complete arithmetic/CPU cost; original logical admission remains unchanged.",
        "memory_scope":"Trace allocations and process lifetime peaks are separate observations; modeled logical entries/payload bits are not Python allocator/RSS bounds."}
    out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"outcome":"accepted","receipt_sha256":sha(out.read_bytes()),"source_files":authenticated["files"],"numeric_replays":len(numeric_replays),
        "exact_recomputations":len(fresh_exacts),"max_numeric_gap":max(max(row["numeric_gaps"].values()) for row in numeric_replays),
        "exact_threshold_flags":{label:row["threshold_met"] for label,row in fresh_exacts.items()}}))


if __name__=="__main__":main()
