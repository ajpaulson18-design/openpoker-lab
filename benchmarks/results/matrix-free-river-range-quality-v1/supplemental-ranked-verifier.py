"""Supplemental saved-only ranked/physical exact equivalence; never training."""
from pathlib import Path
from fractions import Fraction
import json,sys,hashlib,subprocess,importlib.util
ROOT=Path(sys.argv[1]).resolve();ATTEMPT=Path(sys.argv[2]).resolve();OUT=Path(sys.argv[3]).resolve()
sys.path.insert(0,str(ROOT))
from scripts import river_ranked_certificate as ranked
from scripts import benchmark_river_heldout_quality as baseline
head="949060275f00bbd2f174a05a6de247ece1852e73"
helper_path=ROOT/"benchmarks/results/native-river-controls-v1/validate_compiled_river.py"
if hashlib.sha256(helper_path.read_bytes()).hexdigest()!="a4155547d39b49c65a7fcb3b22a0ee5ce751de17a6183026ee713f62f88203b6":raise ValueError("helper digest")
spec=importlib.util.spec_from_file_location("tripwire",helper_path);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
def source():
    state=helper._source_snapshot(ROOT,baseline)
    if state["head"]!=head or state["status"]!="clean":raise ValueError("source")
    for rel in ("scripts/river_ranked_certificate.py","tests/test_river_ranked_certificate.py","docs/independent-ranked-river-certificate.md"):
        raw=(ROOT/rel).read_bytes();committed=subprocess.check_output(["git","-C",str(ROOT),"show",head+":"+rel])
        lf=lambda b:b.replace(b"\r\n",b"\n").replace(b"\r",b"\n")
        if lf(raw)!=lf(committed):raise ValueError("new source not committed")
        state["files"][rel]={"raw_sha256":hashlib.sha256(raw).hexdigest(),"normalized_lf_sha256":hashlib.sha256(lf(raw)).hexdigest()}
    return state
before=source();report_raw=(ATTEMPT/"report.json").read_bytes();claim_raw=(ATTEMPT/"claim.json").read_bytes()
if hashlib.sha256(report_raw).hexdigest()!="384a63f99e0d8f99b27236f083fc066ce3160c9d4deb43269816c40e96ac57da":raise ValueError("report digest")
if hashlib.sha256(claim_raw).hexdigest()!="59234ac2515a69084c2b164ec8c88cd60ccc625386724f9d74bdb2e8b6ce615e":raise ValueError("claim digest")
report=json.loads(report_raw);claim=json.loads(claim_raw);cases={c["id"]:c for c in claim["manifest"]["cases"]};rows=[]
with helper._production_helpers_forbidden() as blocked:
    for p in report["profiles"]:
        raw=(ATTEMPT/p["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=p["sha256"] or len(raw)!=p["bytes"]:raise ValueError("policy receipt")
        case=cases[p["case"]];policy=json.loads(raw)
        out=ranked.evaluate_ranked_certificate(policy,case["oop"],case["ip"],board=case["board"],config=case["config"])
        old=p["independent_audit"]["exact_audit"]
        for mode in ("scan","partition"):
            g=old["chance_groupings"][mode]
            if out["metrics"]!={k:Fraction(v) for k,v in g["metrics_fraction"].items()}:raise ValueError("exact metric parity")
            if out["normalized_policy_rows"]!=g["normalized_policy_rows"] or out["normalization_ledger"]!=g["normalization_ledger"]:raise ValueError("normalization parity")
        rows.append({"case":p["case"],"backend":p["backend"],"policy_sha256":p["sha256"],"all_eight_metrics_exactly_match_scan_and_partition":True,"all_normalization_rows_and_ledgers_match":True,"work":out["work"],"work_by_kind":out["work_by_kind"],"maximum_fraction_bits":out["maximum_fraction_bits"],"worlds_materialized":out["worlds_materialized"]})
        print(json.dumps({"case":p["case"],"backend":p["backend"],"work":out["work"],"bits":out["maximum_fraction_bits"]}),flush=True)
if blocked:raise ValueError("production helper called")
if source()!=before:raise ValueError("source changed")
if (ATTEMPT/"report.json").read_bytes()!=report_raw or (ATTEMPT/"claim.json").read_bytes()!=claim_raw:raise ValueError("evidence changed")
receipt={"schema":"ranked-river-supplemental-saved-equivalence-v1","status":"verified","source":before,"source_head":head,"original_study_claim":claim["claim_id"],"profiles":rows,"blocked_production_calls":blocked,"training_calls":0,"scope":"Additional saved-policy exact equivalence only; original study auditor/caps/outcomes unchanged."}
with OUT.open("x",encoding="utf-8",newline="\n") as f:json.dump(receipt,f,sort_keys=True,indent=2);f.write("\n")
