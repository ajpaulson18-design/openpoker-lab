"""Saved-only independent replay of the fixed16x16 river study. Never trains."""
import argparse,json,sys,hashlib
from pathlib import Path
from fractions import Fraction
from contextlib import ExitStack
from unittest.mock import patch

HEAD="db6cff583563072938c62e732078988b65e6e0d7"
def digest(raw):return hashlib.sha256(raw).hexdigest()
def verify(root,attempt,output):
    root=Path(root).resolve();attempt=Path(attempt).resolve();output=Path(output).resolve()
    if output.exists() or any(output.is_relative_to(p) for p in (root,attempt)):raise ValueError("new external output required")
    sys.path.insert(0,str(root))
    from scripts import benchmark_matrix_free_river_range_quality as r
    raw={n:(attempt/n).read_bytes() for n in ("claim.json","report.json","status.json")}
    claim,report,status=(json.loads(raw[n]) for n in ("claim.json","report.json","status.json"))
    if report["status"]!="completed" or status["status"]!="completed" or claim["claim_id"]!=report["claim_id"] or claim["claim_id"]!=status["claim_id"]:raise ValueError("incomplete evidence")
    if claim["retry_permitted"] is not False or status["retry_permitted"] is not False:raise ValueError("retry identity")
    manifest=claim["manifest"];r._validate_manifest(manifest)
    runtime=r.ProductionRuntime(root,root/"benchmarks/results/native-river-range-quality-v1",root/"benchmarks/results/native-river-controls-v1")
    source=runtime.source_snapshot(HEAD);base=runtime.baseline_snapshot()
    r._same(source,claim["source"],"source");r._same(base,claim["baselines"],"baselines")
    r._same(source,report["source"],"report source");r._same(base,report["baselines"],"report baseline")
    r._same(claim["preflight_admissions"],report["preflight_admissions"],"admissions")
    if len(report["profiles"])!=4:raise ValueError("profile count")
    blocked=[]
    def fail(*a,**k):
        blocked.append("forbidden trainer/native/lifecycle")
        raise AssertionError("saved verifier called training or backend")
    audits={};policies={};receipts=[];results=[]
    with ExitStack() as stack:
        for owner,name in [(r,"run"),(r,"run_with_runtime"),(runtime,"call"),(runtime,"preflight"),(runtime.mf,"solve_matrix_free_river"),(runtime.mf,"train_ranked_river"),(runtime.tail,"solve_matrix_free_river_tail"),(runtime.tail,"_train_tail"),(runtime.native,"validate_backend"),(runtime.native,"train_native_fixed_street")]:stack.enter_context(patch.object(owner,name,fail))
        for cell,profile,admission in zip(manifest["calls"],report["profiles"],claim["preflight_admissions"]):
            for k,v in cell.items():
                if profile[k]!=v:raise ValueError("grid")
            case=next(c for c in manifest["cases"] if c["id"]==cell["case"])
            path=attempt/profile["file"]
            if not path.resolve().is_relative_to(attempt):raise ValueError("path")
            policy_raw=path.read_bytes();raw[profile["file"]]=policy_raw
            if digest(policy_raw)!=profile["sha256"] or len(policy_raw)!=profile["bytes"]:raise ValueError("policy digest")
            result=json.loads(policy_raw)
            if r._json_bytes(result)!=policy_raw:raise ValueError("canonical policy")
            r._validate_admission(admission,cell);r._validate_return(result,case,cell,admission)
            audit=runtime.audit(result,case,cell)
            stored={k:v for k,v in profile["independent_audit"].items() if k not in ("replay_status","numeric_target_met","exact_target_met")}
            r._same(audit,stored,"whole deterministic audit")
            exact=audit["exact_audit"]
            if exact["status"]=="admitted":
                m={k:Fraction(v) for k,v in exact["metrics_fraction"].items()}
                r._legal_metric_identities(m,tolerance=Fraction())
                met=m["nash_conv"]<=Fraction(1,1000)
                if profile["exact_target_met"] is not met:raise ValueError("target")
            elif exact["status"]=="admission-rejected":
                if profile["exact_target_met"] is not None:raise ValueError("capacity gate")
            else:raise ValueError("exact status")
            numeric=audit["numeric_metrics"]["nash_conv"]<=.001
            if profile["numeric_target_met"] is not numeric:raise ValueError("numeric gate")
            key=(cell["case"],cell["backend"]);audits[key]=audit;policies[key]=result
            receipts.append({k:profile[k] for k in (*cell.keys(),"file","bytes","sha256")})
            results.append({**cell,"numeric_nash_conv":audit["numeric_metrics"]["nash_conv"],"exact_status":exact["status"],"exact_target_met":profile["exact_target_met"],"whole_audit_sha256":digest(r._json_bytes(audit)),"blocked_calls":audit["blocked_production_helper_calls"]})
        comparisons=[]
        for case in manifest["cases"]:
            old=(case["id"],r.BACKENDS[0]);tail=(case["id"],r.BACKENDS[1])
            comparisons.append({"case":case["id"],**r._descriptive_difference(policies[tail],policies[old],audits[tail],audits[old])})
        r._same(comparisons,report["descriptive_comparisons"],"comparisons")
        r._same(comparisons,status["descriptive_comparisons"],"status comparisons")
    r._same(receipts,status["saved_policies"],"saved receipts")
    r._same(source,runtime.source_snapshot(HEAD),"source after")
    r._same(base,runtime.baseline_snapshot(),"baselines after")
    for rel,b in raw.items():
        if (attempt/rel).read_bytes()!=b:raise ValueError("evidence changed")
    if blocked:raise ValueError("blocked calls")
    receipt={"schema":"matrix-free-river-range-quality-saved-replay-v1","status":"verified","claim_id":claim["claim_id"],"source_head":HEAD,"source":source,"baselines":base,"protected_bytes":[{"file":n,"bytes":len(b),"sha256":digest(b)} for n,b in raw.items()],"profiles":results,"comparisons":comparisons,"training_calls":0,"native_calls":0,"blocked_calls":blocked}
    r._exclusive(output,r._pretty(receipt));return receipt
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source-root",required=True);p.add_argument("--attempt",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    result=verify(a.source_root,a.attempt,a.output);print(json.dumps({"status":result["status"],"policies":len(result["profiles"]),"training_calls":0}))
