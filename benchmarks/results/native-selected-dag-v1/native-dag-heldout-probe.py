"""Current-source DAG held-out replay; historical files are read as data only."""
import hashlib,json,time,sys
from pathlib import Path
from zipfile import ZipFile
from unittest.mock import patch
from contextlib import ExitStack
repo=Path(__file__).resolve().parent/'native-dag-repo'
sys.path.insert(0,str(repo))
from scripts.benchmark_selected_operator import _identity,_request,_write
from pokerlab.selected_operator_solver import solve_four_street_operator,census_four_street_operator
from scripts.preflop_validation import replay_policy,compare_result
from scripts.four_street_certificate_v3 import evaluate_exact
ROOT=Path(__file__).resolve().parent
output=ROOT/'native-dag-heldout-probe-v1'
output.mkdir(exist_ok=False)
source=_identity()
if source['status']: raise ValueError('source dirty')
_write(output/'source-before.json',source)
archive=repo/'benchmarks/results/native-selected-heldout-v1/heldout-study.zip'
raw=archive.read_bytes()
if hashlib.sha256(raw).hexdigest()!='834c84a24d371e20291ac6d4a7a915fe0e5ff9d2d9fd33f3a63a3b3947d241db': raise ValueError('historical data changed')
with ZipFile(archive) as z:
 case_raw=z.read('case.json'); case=json.loads(case_raw)
 previous=json.loads(z.read('t100-python.json'))
 previous=previous.get('payload',previous)
(output/'case.json').write_bytes(case_raw)
exe=ROOT/'native-dag-build/native-selected-dag-train.exe'
forbidden=('pokerlab.preflop_solver._merge_preflop_tree','pokerlab.preflop_solver._clone_template','pokerlab.preflop_solver._all_nodes','pokerlab.preflop_solver._positive_pot_training_view','pokerlab.postflop_solver._build_public_tree','pokerlab.river_tree._build_tree','pokerlab.shared_public_topology.compile_shared_public_topology','pokerlab.packed_operator_cfr.train_packed','pokerlab.preflop_solver._enumerate_physical_worlds')
with ExitStack() as stack:
 for name in forbidden: stack.enter_context(patch(name,side_effect=AssertionError(name)))
 result=solve_four_street_operator(_request(case,100),strategy_storage='packed',rank_cache_boards=64,public_topology='direct',native_executable=exe)
_write(output/'native-policy.json',result)
checks={key: result[key]==previous[key] for key in ('strategy','private_pair_probabilities','value_sb','value_bb','sb_best_response_value','bb_best_response_value','nash_conv')}
if not all(checks.values()): raise ValueError('historical policy/diagnostic mismatch: '+repr(checks))
replay=replay_policy(result,case['sb_range'],case['bb_range'],config=case['config'],runouts=case['runouts'],flop_config=case['flop_config'],turn_config=case['turn_config'],river_config=case['river_config'])
gaps=compare_result(result,replay)
_write(output/'numeric-replay.json',replay)
try:
 certificate=evaluate_exact(case,result)
 exact={'status':'accepted','certificate':certificate}
except ValueError as exc:
 exact={'status':'rejected','error_type':type(exc).__name__,'error':str(exc)}
_write(output/'exact-gate.json',exact)
with patch('pokerlab.native_selected_dag.subprocess.run',side_effect=AssertionError('native call before rejected admission')),patch('pokerlab.selected_runout_operator.rank_hand',side_effect=AssertionError('rank before rejection')):
 try:
  census_four_street_operator(_request(case,1000),strategy_storage='packed',public_topology='direct',native_executable=exe)
 except ValueError as exc:
  t1000={'training_calls':0,'status':'rejected','error':str(exc)}
 else: raise ValueError('expected T1000 admission rejection did not occur')
_write(output/'t1000-admission.json',t1000)
if _identity()!=source: raise ValueError('source changed during probe')
receipt={'source_commit':source['commit'],'historical_archive_sha256':hashlib.sha256(raw).hexdigest(),'helper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'training_calls':1,'native_calls':1,'worlds':result['worlds'],'info_sets':result['info_sets'],'checks':checks,'numeric_gaps':gaps,'exact':exact,'t1000':t1000,'native_dag':result['native_training'],'scope':'Held-out correctness/admission probe; no paired timing, larger exact quality pass or general scaling claim.'}
_write(output/'receipt.json',receipt)
print(json.dumps({'worlds':result['worlds'],'rows':result['info_sets'],'exact':exact,'t1000':t1000,'checks':checks,'numeric_gaps':gaps},sort_keys=True))
