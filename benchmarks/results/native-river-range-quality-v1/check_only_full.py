"""Read-only full-request/source/build/control preflight; never trains."""
import json,sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
root=Path(sys.argv[1]).resolve(); build=Path(sys.argv[2]).resolve(); evidence=Path(sys.argv[3]).resolve()
sys.path.insert(0,str(root))
from scripts import benchmark_native_river_range_quality as r
runtime=r.ProductionRuntime(root,build)
head="7371b450976a8b904afb7c7583070db4d5b84595"
source=runtime.source_snapshot(head); built=runtime.build_snapshot()
control=r.authenticate_control_corpus(root/"benchmarks/results/native-river-controls-v1")
manifest_raw=r.CASE_MANIFEST.read_bytes()
if r._sha(r._lf(manifest_raw))!=r.CASE_MANIFEST_LF_SHA256: raise RuntimeError("manifest hash mismatch")
manifest=json.loads(manifest_raw); r._validate_manifest(manifest)
blocked=[]
def forbid(*a,**k):
    blocked.append("trainer-or-backend-lookup")
    raise AssertionError("preflight reached trainer/backend lookup")
admissions=[]
with ExitStack() as stack:
    for owner,name in [(runtime.native,"solve_native_river"),(runtime.river,"solve_river_tail"),(runtime.fixed,"validate_backend"),(runtime.fixed,"train_native_fixed_street"),(runtime.turn,"_train_original_weight_tail"),(runtime.river,"_train_original_weight_tail"),(runtime.public,"_train_prepared")]: stack.enter_context(patch.object(owner,name,forbid))
    for cell in manifest["calls"]:
        case=next(c for c in manifest["cases"] if c["id"]==cell["case"])
        item=runtime.preflight(case,manifest["iterations"]);item["backend_cell"]=cell["backend"]
        admissions.append(r._validate_admission(item))
        print(json.dumps({"preflight":cell,"worlds":item["worlds"],"native_loop_bound":item["native_shape_admission"]["total_loop_entries_upper_bound"]}),flush=True)
r._same(source,runtime.source_snapshot(head),"full source preflight")
r._same(built,runtime.build_snapshot(),"full build preflight")
r._same(control,r.authenticate_control_corpus(control["root"]),"full control preflight")
if blocked:raise AssertionError(blocked)
report={"schema":"native-river-range-quality-check-only-v1","status":"passed","source":source,"build":built,"control_authentication":control,"manifest_lf_sha256":r._sha(r._lf(manifest_raw)),"preflight_admissions":admissions,"blocked_trainer_or_backend_calls":blocked,"actual_quality_calls":0}
r._exclusive(evidence,r._pretty(report))
print(json.dumps({"status":"passed","actual_quality_calls":0,"source_files":len(source["files"]),"output":str(evidence)}),flush=True)
