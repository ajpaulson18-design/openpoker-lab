"""Authenticate held-out DAG probe as saved data; never train or run native code."""
import importlib.util,json,hashlib,sys,zipfile
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
root=Path(__file__).resolve().parent
repo=root/'native-dag-repo'; study=root/'native-dag-heldout-probe-v1'
spec=importlib.util.spec_from_file_location('independent_auth',root/'native-dag-independent-review.py')
auth=importlib.util.module_from_spec(spec);spec.loader.exec_module(auth)
need=auth.need;sha=auth.sha;parse=auth.parse
saved={path.name:path.read_bytes() for path in study.iterdir() if path.is_file()}
source=parse(saved['source-before.json'])
authenticated=auth.source_identity(repo,source)
archive=root/'native-dag-heldout-probe-v1.zip'
archive_pin='3cf33eb1d2b63eb0b2333930c52ebf0e8a07d93ac479adfb01eba3a26236e3e0'
need(sha(archive.read_bytes())==archive_pin,'heldout archive pin mismatch')
with zipfile.ZipFile(archive) as z:
 entries={item.filename:z.read(item) for item in z.infolist() if not item.is_dir()}
 need(len(entries)==len([x for x in z.infolist() if not x.is_dir()]),'duplicate archive paths')
 for name,raw in saved.items():
  need(name in entries and entries[name]==raw,'heldout archive bytes mismatch '+name)
helper=root/'native-dag-heldout-probe.py'
receipt=parse(saved['receipt.json'])
need(receipt['source_commit']==auth.FROZEN and receipt['helper_sha256']==sha(helper.read_bytes()),'probe source/producer pin mismatch')
need('helper.py' not in entries or entries['helper.py']==helper.read_bytes(),'archive helper not byte-faithful')
historical=repo/'benchmarks/results/native-selected-heldout-v1/heldout-study.zip'
pin='834c84a24d371e20291ac6d4a7a915fe0e5ff9d2d9fd33f3a63a3b3947d241db'
need(sha(historical.read_bytes())==pin==receipt['historical_archive_sha256'],'historical data archive pin mismatch')
with zipfile.ZipFile(historical) as z:
 need(z.read('case.json')==saved['case.json'],'heldout case changed')
 previous=parse(z.read('t100-python.json'));previous=previous.get('payload',previous)
case=parse(saved['case.json']);payload=parse(saved['native-policy.json'])
checks={key:payload[key]==previous[key] for key in ('strategy','private_pair_probabilities','value_sb','value_bb','sb_best_response_value','bb_best_response_value','nash_conv')}
need(checks==receipt['checks'] and all(checks.values()),'historical heldout policy/metrics differ')
need(payload['worlds']==receipt['worlds']==96 and payload['info_sets']==receipt['info_sets']==len(payload['strategy'])==2224,'heldout counts mismatch')
need(payload['iterations']==100 and receipt['training_calls']==receipt['native_calls']==1,'producer call/iteration counts mismatch')
need(payload['native_training']==receipt['native_dag'] and payload['native_training']['calls']==1,'native receipt mismatch')
cpp=(repo/'native/selected_dag_train.cpp').read_bytes();identity=payload['native_training']['identity']
need(identity['source_sha256']==sha(cpp) and identity['source_lf_sha256']==sha(cpp.replace(b'\r\n',b'\n')),'native source guard mismatch')
exact=parse(saved['exact-gate.json']);later=parse(saved['t1000-admission.json'])
need(exact==receipt['exact']=={'status':'rejected','error_type':'ValueError','error':'payload exceeds bounded four-street result shape'},'exact rejection changed')
need(later==receipt['t1000'] and later['status']=='rejected' and later['training_calls']==0 and later['error']=='Selected operator requested scan envelope exceeds 500,000,000 entries.','T1000 rejection changed')
# Explicit source-inspected controls prove the miss was retained under the old cap.
import ast
validation=ast.parse((repo/'scripts/four_street_validation.py').read_text())
rows=[ast.literal_eval(n.value) for n in validation.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MAX_ROWS' for t in n.targets)]
need(rows==[2048] and len(payload['strategy'])>rows[0],'unchanged independent row cap not authenticated')
producer=helper.read_text()
need("patch('pokerlab.native_selected_dag.subprocess.run',side_effect=AssertionError" in producer and "patch('pokerlab.selected_runout_operator.rank_hand',side_effect=AssertionError" in producer,'heldout admission producer lacks before-rank/native controls')
sys.dont_write_bytecode=True;sys.path.insert(0,str(repo))
from scripts.preflop_validation import replay_policy,compare_result
forbidden=('pokerlab.selected_operator_solver.solve_four_street_operator','pokerlab.packed_operator_cfr.train_packed','pokerlab.native_selected_dag.train_native_selected_dag','pokerlab.native_selected_operator.train_native_selected','pokerlab.public_cfr._train_prepared','pokerlab.preflop_solver.solve_preflop','pokerlab.cfr.train','subprocess.Popen')
with ExitStack() as stack:
 for target in forbidden:stack.enter_context(patch(target,side_effect=AssertionError('forbidden saved heldout review '+target)))
 replay=replay_policy(payload,case['sb_range'],case['bb_range'],config=case['config'],runouts=case['runouts'],flop_config=case['flop_config'],turn_config=case['turn_config'],river_config=case['river_config'])
 gaps=compare_result(payload,replay);auth.numeric_gaps(gaps)
need(replay==parse(saved['numeric-replay.json']) and gaps==receipt['numeric_gaps'],'fresh heldout numeric replay changed')
need(replay['checked_information_sets']==2224 and replay['worlds']==96,'fresh heldout replay incomplete')
need(auth.source_identity(repo,source)==authenticated,'source changed during heldout review')
need(sorted(path.name for path in study.iterdir() if path.is_file())==sorted(saved) and all((study/name).read_bytes()==raw for name,raw in saved.items()),'heldout data changed during review')
result={'outcome':'accepted','reviewer':'independent Sol substitute for unavailable Terra','source_commit':auth.FROZEN,'authenticated_source_files':authenticated['files'],'archive_sha256':archive_pin,'archive_entries':len(entries),'historical_archive_sha256':pin,'probe_helper_sha256':sha(helper.read_bytes()),'producer_helper_in_archive':'helper.py' in entries,'preserved_first_review_helper_sha256':sha((root/'native-dag-heldout-independent-review-v1-archive-helper-name-preserved.py').read_bytes()),'preserved_first_review_failure_log_sha256':sha((root/'native-dag-heldout-independent-review-v1-archive-helper-name-failure.log').read_bytes()),'review_helper_sha256':sha(Path(__file__).read_bytes()),'artifact_sha256':{name:sha(raw) for name,raw in saved.items()},'historical_checks':checks,'worlds':96,'rows':2224,'fresh_numeric_gaps':gaps,'exact_status':'rejected unchanged2048row cap','t1000_status':'rejected before ranking/native by producer controls','training_calls':0,'native_calls':0,'source_and_artifacts_unchanged_after_review':True,'scope':'Heldout correctness/admission only. Historical archive read solely asdata. No larger exact qualitypass or speed/scalability claim.'}
out=root/'native-dag-heldout-independent-receipt.json'
need(not out.exists(),'refuse to overwrite independent heldout receipt')
out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
print(json.dumps({'outcome':'accepted','receipt':str(out),'sha256':sha(out.read_bytes()),'max_numeric_gap':max(gaps.values())}))
