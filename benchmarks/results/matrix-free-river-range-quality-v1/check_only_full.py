"""Authenticate the committed study without invoking either trainer."""
import json,sys
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
from scripts import benchmark_matrix_free_river_range_quality as r
rt=r.ProductionRuntime(root,root/"benchmarks/results/native-river-range-quality-v1",root/"benchmarks/results/native-river-controls-v1")
head="db6cff583563072938c62e732078988b65e6e0d7"
src=rt.source_snapshot(head);base=rt.baseline_snapshot()
manifest=json.loads(r.MANIFEST_PATH.read_text(encoding="utf-8"));r._validate_manifest(manifest)
blocked=[]
def fail(*a,**k):
    blocked.append("trainer-or-native")
    raise AssertionError("unexpected trainer or native call")
rows=[]
with ExitStack() as stack:
    for owner,name in [(rt.mf,"solve_matrix_free_river"),(rt.mf,"train_ranked_river"),(rt.tail,"solve_matrix_free_river_tail"),(rt.tail,"_train_tail"),(rt.native,"validate_backend"),(rt.native,"train_native_fixed_street")]:stack.enter_context(patch.object(owner,name,fail))
    for cell in manifest["calls"]:
        case=next(c for c in manifest["cases"] if c["id"]==cell["case"])
        admission=rt.preflight(case,cell);r._validate_admission(admission,cell);rows.append(admission)
        print(json.dumps({"case":cell["case"],"backend":cell["backend"],"work":admission["hand_state_pass_work"]}),flush=True)
r._same(src,rt.source_snapshot(head),"sourcebeforeafter")
r._same(base,rt.baseline_snapshot(),"baselinesbeforeafter")
r._exclusive(Path(sys.argv[2]),r._pretty({"schema":"mf16-check-only-v1","status":"passed","source":src,"baselines":base,"admissions":rows,"blocked_calls":blocked,"training_calls":0}))
print("full-source/preflight PASS; zero training calls",flush=True)
