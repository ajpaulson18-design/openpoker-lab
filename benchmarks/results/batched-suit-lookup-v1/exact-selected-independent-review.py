"""External read-only exact-product selected-solver study authentication.

Requires lead-confirmed terminal status plus an externally supplied manifest pin.
All current source/raw archived bytes authenticate before repository math imports.
No solve, training, native execution, or artifact rewriting is permitted.
"""
import argparse
import ast
from contextlib import ExitStack
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import sys
from unittest.mock import patch
import zipfile

FROZEN="66788d4a27b549a5cd1788649bae3e1dea047ac6"
MAX_RATIONAL_BITS=65536
THRESHOLD=Fraction(1,1000)
NUMERIC=("value_sb","value_bb","sb_best_response_value","bb_best_response_value","nash_conv")
ALL_METRICS=NUMERIC+("sb_gain","bb_gain","exploitability")
EXACT=frozenset(("value_sb","value_bb","sb_best_response_value","bb_best_response_value",
    "sb_best_response_gain","bb_best_response_gain","nash_conv","exploitability","lower_value_bound","upper_value_bound"))
SCHEDULE=(("original",10,0,False),("original",10,1,False),("original",10,2,False),
    ("original",10,"traced",True),("original",100,0,False),("original",1000,0,False),
    ("unit",10,0,False),("tiny",10,0,False),("one-world",1000,0,False),("full-range-census",0,0,False))
def need(condition, message):
    if not condition:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result

def parse(raw):
    return json.loads(raw, object_pairs_hook=no_duplicates,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON: " + value)))

def canonical(value):
    return sha(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii"))

def git(repo, *args, data=None):
    return subprocess.check_output(["git", *args], cwd=repo, input=data)

def source_identity(repo, source):
    need(source["commit"] == FROZEN and source["status"] == "", "wrong or dirty source snapshot")
    need(git(repo, "rev-parse", "HEAD").decode().strip() == FROZEN, "live source HEAD drift")
    need(not git(repo, "status", "--porcelain", "--untracked-files=all").strip(), "live source is dirty")
    tracked = git(repo, "ls-files", "-z").decode().rstrip("\0").split("\0")
    need(set(tracked) == set(source["sha256"]), "incomplete tracked source closure")
    observed = {}
    for name in tracked:
        path = repo / name
        need(path.is_file() and not path.is_symlink(), "nonordinary source file: " + name)
        observed[name] = sha(path.read_bytes())
    need(observed == source["sha256"], "raw source bytes differ from frozen study closure")
    # Git applies the checked-in attributes and configured text conversion. This
    # independently ties all raw-pinned working files to frozen committed blobs.
    entries = git(repo, "ls-tree", "-rz", "--full-tree", FROZEN).rstrip(b"\0").split(b"\0")
    blobs = {}
    for entry in entries:
        metadata, name = entry.split(b"\t", 1)
        mode, kind, digest = metadata.split()
        need(kind == b"blob" and mode in (b"100644", b"100755"), "nonordinary committed source entry")
        blobs[name.decode()] = digest.decode()
    need(set(blobs) == set(tracked), "commit source closure differs from tracked closure")
    need(all("\n" not in name and '"' not in name and "\\" not in name for name in tracked), "unsupported source filename")
    content = ("\n".join(tracked) + "\n").encode()
    normalized = git(repo, "hash-object", "--stdin-paths", data=content).decode().splitlines()
    need(len(normalized) == len(tracked), "incomplete committed-blob authentication")
    exact_raw, normalized_only = [], []
    for name, digest in zip(tracked, normalized):
        raw = (repo/name).read_bytes()
        raw_git_object = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        if raw_git_object == blobs[name]:
            exact_raw.append(name)
        else:
            need(digest == blobs[name], "working source differs from committed raw/normalized blob: " + name)
            normalized_only.append(name)
    return {"commit": FROZEN, "files": len(tracked), "raw_sha256": observed,
            "git_raw_or_normalized_committed_blobs_match": True,
            "raw_committed_blob_files": len(exact_raw),
            "normalized_committed_blob_files": len(normalized_only)}

def bounded_fraction(text):
    need(type(text) is str and re.fullmatch(r"[+-]?[0-9]+(?:/[0-9]+)?", text), "invalid bounded rational text")
    parts = text.split("/")
    # 30103/100000 is an upper decimal-digit approximation to log10(2).
    digits = (MAX_RATIONAL_BITS * 30103) // 100000 + 1
    def integer(part):
        negative = part.startswith("-")
        unsigned = part.lstrip("+-")
        need(len(unsigned) <= digits, "exact rational decimal length exceeds unchanged bit limit")
        value = 0
        for at in range(0, len(unsigned), 9):
            chunk = unsigned[at:at+9]
            value = value * (10 ** len(chunk)) + int(chunk)
            need(value.bit_length() <= MAX_RATIONAL_BITS, "exact rational exceeds unchanged bit limit")
        return -value if negative else value
    numerator = integer(parts[0])
    denominator = integer(parts[1]) if len(parts) == 2 else 1
    need(denominator > 0, "nonpositive exact denominator")
    return Fraction(numerator, denominator)

def metrics(value):
    need(type(value) is dict and set(value) == EXACT, "wrong exact metric fields")
    need(all(type(v) is str and v for v in value.values()), "exact metrics must be rational strings")
    result = {key: bounded_fraction(item) for key, item in value.items()}
    need(result["nash_conv"] >= 0 and result["exploitability"] >= 0, "negative exact quality metric")
    return result

def numeric_gaps(value):
    need(type(value) is dict and set(value) == set(NUMERIC), "wrong numeric replay gap fields")
    need(all(type(v) in (int,float) and math.isfinite(v) and 0 <= v <= 1e-10
             for v in value.values()), "numeric replay gap outside unchanged tolerance")

def independent_case(base,name):
    if name=="original":return dict(base)
    if name=="one-world":return dict(base,id="exact-product-one-world-four-street-v1",
        sb_range="AsAd",bb_range="KsKd",runouts=["2c3c4d7h8h"])
    need(name in ("unit","tiny"),"unexpected saved solver case")
    scale="1" if name=="unit" else "1e-200"
    return dict(base,id="exact-product-common-scale-"+name,
        sb_range="AsAd:"+scale+",QsQd:"+scale,bb_range="KsKd:"+scale+",JhJd:"+scale,
        config={"starting_stack":[4,3],"raise_sizes":[.5],"max_raises":1,"include_all_in":False},
        runouts=["2c3c4d7h8h","2c3c4d7hKc","Ac2d3h7s8c"])


def source_limit(repo,name):
    tree=ast.parse((repo/"scripts/four_street_certificate.py").read_text())
    values=[ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id==name for t in node.targets)]
    need(len(values)==1,"missing or duplicate certificate limit constant")
    return values[0]


def archive_check(path,pin,saved):
    need(pin and sha(path.read_bytes())==pin,"whole-study archive pin mismatch")
    with zipfile.ZipFile(path) as z:
        entries={info.filename:z.read(info) for info in z.infolist() if not info.is_dir()}
        need(len(entries)==len([x for x in z.infolist() if not x.is_dir()]),"duplicate archive paths")
        for name,raw in saved.items():
            need(name in entries and entries[name]==raw,"archive exact relative-path byte mismatch: "+name)
    return {"path":str(path.resolve()),"sha256":pin,"entries":len(entries),"saved_files_verified":len(saved)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo",type=Path,required=True);p.add_argument("--study",type=Path,required=True)
    p.add_argument("--receipt",type=Path,required=True);p.add_argument("--manifest-sha256",required=True)
    p.add_argument("--confirmed-terminal-handle",required=True);p.add_argument("--terminal-exit-code",type=int,required=True)
    p.add_argument("--archive",type=Path);p.add_argument("--archive-sha256")
    args=p.parse_args()
    need(args.confirmed_terminal_handle and args.terminal_exit_code==0,"lead-confirmed successful terminal handle required")
    repo,study,out=args.repo.resolve(),args.study.resolve(),args.receipt.resolve()
    need(repo not in out.parents and study not in out.parents and not out.exists(),"new external receipt path required")
    paths=sorted(x for x in study.rglob("*") if x.is_file())
    saved={x.relative_to(study).as_posix():x.read_bytes() for x in paths}
    artifact_hashes={name:sha(raw) for name,raw in saved.items()}
    need(sha(saved["manifest.json"])==args.manifest_sha256,"externally supplied manifest pin mismatch")
    manifest=parse(saved["manifest.json"])
    need(manifest["source_commit"]==FROZEN,"manifest source commit mismatch")
    need(set(saved)==set(manifest["sha256"])|{"manifest.json"},"manifest omits or adds saved study files")
    for name,digest in manifest["sha256"].items():
        need(Path(name).name==name and sha(saved[name])==digest,"saved study artifact pin mismatch: "+name)
    source=parse(saved["source-before.json"])
    authenticated=source_identity(repo,source) # Before ANY repository mathematics import.
    need(parse(saved["source-after.json"])==source,"frozen source before/after differ")
    need(source_limit(repo,"MAX_FRACTION_BITS")==MAX_RATIONAL_BITS,"rational parser must retain unchanged bit cap")
    report=parse(saved["report.json"]);protocol=parse(saved["protocol.json"])
    need(report["outcome"]=="complete" and report["failure"] is None,"producer study incomplete or failed")
    need(report["source_commit"]==protocol["source_commit"]==FROZEN,"report/protocol source mismatch")
    need(protocol["version"]=="exact-product-four-street-fixed-study-v1" and protocol["schedule"]==[list(x) for x in SCHEDULE],"fixed schedule mismatch")
    need(protocol["chance_contract"]=="exact-product-selected-v1" and protocol["conversion_contract"]=="exact-product-vectors-binary64-v1","study arithmetic contract mismatch")
    need(len(report["samples"])==10 and report["native_calls"]==0,"fixed study sample/native count mismatch")
    base=parse((repo/"benchmarks/four-street-integration-v1.json").read_bytes())["case"]
    records=[];payloads={};certificates={};rejections=[];training_calls=0
    for row,(name,iterations,sample,traced) in zip(report["samples"],SCHEDULE):
        label=f"{name}-t{iterations}-{sample}";artifact=label+".json"
        raw=parse(saved[artifact]);payload=raw["payload"]
        need(row["artifact"]==artifact and row["sample"]==sample,"sample report schedule mismatch")
        need({k:v for k,v in row.items() if k not in ("artifact","sample")}=={k:v for k,v in raw.items() if k!="payload"},"report differs from raw child metadata")
        for key,expected in (("case",name),("iterations",iterations),("traced",traced)):
            need(raw[key]==expected and type(raw[key]) is type(expected),"sample request/mode mismatch: "+key)
        need(type(raw["seconds"]) in (int,float) and math.isfinite(raw["seconds"]) and raw["seconds"]>0,"invalid measured elapsed time")
        need(type(raw["python_process_peak_bytes"]) is int and raw["python_process_peak_bytes"]>0,"invalid measured Python process peak")
        alloc=raw["python_allocation_peak_bytes"]
        need((type(alloc) is int and alloc>0) if traced else alloc is None,"trace allocation scope mismatch")
        need(type(raw["native_calls"]) is int and raw["native_calls"]==0,"unexpected native execution")
        need(type(raw["rank_calls"]) is int and raw["rank_calls"]>=0,"invalid rank call count")
        need(raw["status"] in ("complete","pretraining-rejected"),"invalid sample status")
        if raw["status"]=="pretraining-rejected":
            need((name,iterations,sample,traced)==("original",1000,0,False),"unexpected rejected request")
            need(payload is None and raw["training_calls"]==raw["rank_calls"]==0,"rejected request entered training/ranking")
            error=raw["error"]
            need(type(error) is dict and error["type"]=="ValueError" and any(x in error["message"].lower() for x in ("admission","limit","forecast","cap")),"rejection is not identified as resource admission")
            need(label+"-certificate.json" not in saved,"pretraining rejection must have no policy certificate")
            rejections.append({"artifact":artifact,"error":error,"training_calls":0,"rank_calls":0,"quality_status":"not trained or certified"})
        elif name=="full-range-census":
            need(raw["error"] is None and raw["training_calls"]==raw["rank_calls"]==0,"rank-free census entered training/ranking")
            statistics_=payload["statistics"]
            expected=math.comb(47,2)*math.comb(45,2)
            need(payload["expected_pair_board_occurrences"]==expected==1070190,"full-range combinatorial pair/board anchor mismatch")
            need(payload["exact_active_marginal"]=="1/1081" and payload["stored_worlds"]==payload["training_calls"]==0,"full-range marginal/storage scope mismatch")
            need(statistics_["contract"]=="exact-product-selected-v1" and statistics_["hands"]==[1326,1326] and statistics_["boards"]==1,"full-range input dimensions mismatch")
            need(statistics_["support_pair_board_occurrences"]==expected and statistics_["support_hand_board_counts"]==[1081,1081] and statistics_["rank_calls"]==statistics_["rank_sweeps"]==0,"full-range support/rank counters mismatch")
            need(statistics_["work_units_cumulative"]<=500_000_000 and statistics_["storage_entries_peak"]<=2_000_000,"full-range retained/work admission exceeded")
        else:
            need(raw["error"] is None and raw["training_calls"]==1 and raw["rank_calls"]>0,"completed solver call counts invalid")
            training_calls+=1
            need(type(payload) is dict and payload["iterations"]==iterations,"completed solver payload mismatch")
            need(payload["chance_contract"]=="exact-product-selected-v1" and payload["conversion_contract"]=="exact-product-vectors-binary64-v1" and payload["execution_backend"]=="exact-product-selected-direct-packed-python","solver backend/law mismatch")
            need(payload["info_sets"]==len(payload["strategy"])>0,"incomplete saved strategy rows")
            census=payload["operator_census"];admit=census["whole_request_admission"]
            need(census["stored_complete_worlds"]==census["stored_prefix_pair_edges"]==0,"materialized hidden-world representation found")
            need(census["training"]["calls"]==1 and census["kernel"]["rank_calls"]==raw["rank_calls"],"training/kernel call census mismatch")
            need(census["kernel"]["work_units_cumulative"]<=admit["kernel"]["whole_request_upper_work"]<=admit["kernel"]["configured_limit"],"kernel work admission mismatch")
            need(census["float_adapter"]["modeled_work_entries"]<=admit["adapter"]["whole_request_work_upper"]<=admit["adapter"]["configured_work_limit"],"adapter work admission mismatch")
            need(admit["combined_modeled_work_upper"]<=admit["whole_request_limit"] and admit["retained_storage"]["whole_request_peak_upper"]<=admit["retained_storage"]["entry_limit"],"whole-request work/entry admission mismatch")
            payloads[label]=(name,iterations,sample,traced,payload)
            if sample==0:
                cert=parse(saved[label+"-certificate.json"])
                need(cert["source_identity"]=="four-street-independent-exact-v3","unexpected exact certificate source")
                need(cert["input_policy_canonical_sha256"]==canonical(payload),"certificate does not bind the full saved payload")
                need(bounded_fraction(cert["threshold"])==THRESHOLD,"independent exact threshold changed")
                exact=metrics(cert["metrics"])
                need(type(cert["threshold_met"]) is bool and cert["threshold_met"]==(exact["nash_conv"]<=THRESHOLD),"certificate exact target flag mismatch")
                need(cert["fraction_bit_limit"]==MAX_RATIONAL_BITS and cert["maximum_fraction_bits"]<=MAX_RATIONAL_BITS,"certificate integer-bit cap changed or exceeded")
                need(report["exact_certificates"][label]=={"threshold_met":cert["threshold_met"],"metrics":cert["metrics"],"normalized_policy_sha256":cert["normalized_policy_sha256"]},"reported certificate differs from saved certificate")
                certificates[label]=cert
        records.append({"artifact":artifact,"sha256":sha(saved[artifact]),"case":name,"iterations":iterations,"sample":sample,"traced":traced,
            "status":raw["status"],"seconds":raw["seconds"],"training_calls":raw["training_calls"],"rank_calls":raw["rank_calls"],
            "python_allocation_peak_bytes":alloc,"python_process_peak_bytes":raw["python_process_peak_bytes"]})
    need(training_calls==report["training_calls"]==9-len(rejections),"actual solver training-call total mismatch")
    need(set(report["exact_certificates"])==set(certificates),"orphan or missing exact certificate")
    original=payloads["original-t10-0"][-1]
    checks={"three_t10_and_traced_policies_identical":all(payloads[f"original-t10-{sample}"][-1]["strategy"]==original["strategy"] for sample in (1,2,"traced"))}
    unit,tiny=payloads["unit-t10-0"][-1],payloads["tiny-t10-0"][-1]
    checks["common_scale_complete_strategy_identical"]=unit["strategy"]==tiny["strategy"]
    checks["common_scale_all_metrics_identical"]=all(unit[key]==tiny[key] for key in ALL_METRICS)
    checks["common_scale_pair_probabilities_identical"]=unit["private_pair_probabilities"]==tiny["private_pair_probabilities"]
    need(checks==report["checks"] and all(checks.values()),"metamorphic policy/metric/pair equality failed")
    timings=[x["seconds"] for x in records if x["case"]=="original" and x["iterations"]==10 and not x["traced"]]
    need(len(timings)==3 and report["t10_median_seconds"]==statistics.median(timings),"T10 three-sample median mismatch")
    # Full committed closure and every saved artifact are authenticated above.
    sys.dont_write_bytecode=True;sys.path.insert(0,str(repo))
    from scripts.four_street_validation import replay_policy
    from scripts.preflop_validation import compare_result
    from scripts.four_street_certificate_v3 import evaluate_exact
    forbidden=("pokerlab.exact_selected_solver.solve_four_street_exact_selected","pokerlab.packed_operator_cfr.train_packed",
        "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.terminal_values_exact",
        "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.joint_marginals_exact",
        "pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.pair_probability_exact",
        "pokerlab.selected_operator_solver.solve_four_street_operator","pokerlab.native_selected_dag.train_native_selected_dag",
        "pokerlab.native_selected_operator.train_native_selected","pokerlab.preflop_solver.solve_preflop",
        "pokerlab.public_cfr._train_prepared","pokerlab.cfr.train","subprocess.Popen")
    numeric_replays=[];fresh_exact={}
    with ExitStack() as stack:
        for target in forbidden:stack.enter_context(patch(target,side_effect=AssertionError("forbidden independent saved-review entry: "+target)))
        for label,(name,iterations,sample,traced,payload) in payloads.items():
            case=independent_case(base,name)
            replay=replay_policy(payload,case)
            gaps=compare_result(payload,replay);numeric_gaps(gaps)
            need(replay["checked_information_sets"]==payload["info_sets"] and replay["worlds"]==payload["worlds"],"fresh physical replay incomplete")
            numeric_replays.append({"artifact":label+".json","case":name,"iterations":iterations,"rows":payload["info_sets"],
                "worlds":payload["worlds"],"numeric_gaps":gaps})
            if label in certificates:
                actual=evaluate_exact(case,payload);saved_cert=certificates[label]
                need(metrics(actual["metrics"])==metrics(saved_cert["metrics"]),"fresh exact profile/BR metrics differ")
                need(bounded_fraction(actual["threshold"])==THRESHOLD and actual["threshold_met"]==saved_cert["threshold_met"],"fresh exact threshold flag changed")
                need(actual["normalized_policy_sha256"]==saved_cert["normalized_policy_sha256"] and actual["input_policy_canonical_sha256"]==saved_cert["input_policy_canonical_sha256"],"fresh exact policy identity changed")
                fresh_exact[label]={"metrics":actual["metrics"],"threshold":actual["threshold"],"threshold_met":actual["threshold_met"],
                    "normalized_policy_sha256":actual["normalized_policy_sha256"],"maximum_fraction_bits":actual["maximum_fraction_bits"]}
    need(sorted(x.relative_to(study).as_posix() for x in study.rglob("*") if x.is_file())==sorted(saved),"saved artifact inventory changed during review")
    need(all((study/name).read_bytes()==raw for name,raw in saved.items()),"saved artifact bytes changed during review")
    need(source_identity(repo,source)==authenticated,"source changed during independent review")
    archive=archive_check(args.archive,args.archive_sha256,saved) if args.archive else None
    result={"outcome":"accepted","reviewer":"independent Sol substitute for unavailable Terra",
        "source_commit":FROZEN,"authenticated_source_files":authenticated["files"],"source_raw_sha256":authenticated["raw_sha256"],
        "raw_committed_blob_files":authenticated["raw_committed_blob_files"],"normalized_committed_blob_files":authenticated["normalized_committed_blob_files"],
        "git_raw_or_normalized_committed_blobs_match":True,"source_and_artifacts_unchanged_after_review":True,
        "confirmed_terminal_handle":args.confirmed_terminal_handle,"terminal_exit_code":args.terminal_exit_code,
        "manifest_sha256":args.manifest_sha256,"artifact_sha256":artifact_hashes,"samples":records,
        "producer_training_calls":training_calls,"producer_native_calls":0,"solver_requests":9,"rank_free_full_range_censuses":1,
        "review_training_calls":0,"review_native_calls":0,"review_exact_kernel_callback_calls":0,
        "forbidden_entry_points":list(forbidden),"fresh_numeric_replays":numeric_replays,"fresh_exact":fresh_exact,
        "rational_parser_bit_limit":MAX_RATIONAL_BITS,"metamorphic_checks":checks,"retained_pretraining_rejections":rejections,
        "archive":archive,"archive_pin_pending":archive is None,"review_helper_sha256":sha(Path(__file__).read_bytes()),
        "quality_scope":"Actual exact certificate misses/passes are recorded per fixed case. Pretraining rejection is no quality evidence; no legacy-law bitwise-equivalence/full-deck/commercial claim.",
        "memory_scope":"Python allocation traces and Python process peaks remain separate; modeled logical entry/work counts are not measured bytes or CPU time."}
    out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"outcome":"accepted","receipt":str(out),"sha256":sha(out.read_bytes()),"source_files":authenticated["files"],
        "numeric_replays":len(numeric_replays),"exact_recomputations":len(fresh_exact),"producer_training_calls":training_calls,
        "max_numeric_gap":max(max(x["numeric_gaps"].values()) for x in numeric_replays),
        "exact_threshold_flags":{label:value["threshold_met"] for label,value in fresh_exact.items()}}))


if __name__=="__main__":main()
