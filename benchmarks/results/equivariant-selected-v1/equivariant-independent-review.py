"""Independent saved-only equivariant reference study authentication and replay."""
import argparse,hashlib,importlib.util,json,math,statistics,sys
from fractions import Fraction
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch

AUTH='8171ead3ba108f8200f15e85696f40d109ed894209fa7d77598780b83c1401c5'
METRICS=('value_sb','value_bb','sb_best_response_value','bb_best_response_value','sb_gain','bb_gain','nash_conv','exploitability')
SCHEDULE=[('symmetric','default',0,False),('symmetric','suit-equivariant',0,False),('symmetric','suit-equivariant',1,False),('symmetric','default',1,False),('symmetric','default',2,False),('symmetric','suit-equivariant',2,False),('symmetric','default','traced',True),('symmetric','suit-equivariant','traced',True),('asymmetric','default',0,False),('asymmetric','suit-equivariant',0,False),('original-22','default',0,False),('original-22','suit-equivariant',0,False),('one-world','default',0,False),('one-world','suit-equivariant',0,False),('original-22-reject','suit-equivariant',0,False)]
def kernel_limit(c):
 return c['kernel_work_admission'].get('storage_entries_limit',2000000)

def main():
 p=argparse.ArgumentParser()
 for k in ('repo','study','archive','receipt'):p.add_argument('--'+k,type=Path,required=True)
 for k in ('source-commit','manifest-sha256','archive-sha256','confirmed-terminal-handle'):p.add_argument('--'+k,required=True)
 p.add_argument('--terminal-exit-code',type=int,required=True);a=p.parse_args()
 ap=Path(__file__).with_name('exact-selected-independent-review.py')
 if hashlib.sha256(ap.read_bytes()).hexdigest()!=AUTH:raise ValueError('authentication helper pin mismatch')
 spec=importlib.util.spec_from_file_location('saved_auth',ap);auth=importlib.util.module_from_spec(spec);spec.loader.exec_module(auth);auth.FROZEN=a.source_commit
 need,sha,parse=auth.need,auth.sha,auth.parse
 need(a.confirmed_terminal_handle=='73256' and a.terminal_exit_code==0,'terminal result mismatch')
 repo,study,out=a.repo.resolve(),a.study.resolve(),a.receipt.resolve()
 need(not out.exists() and repo not in out.parents and study not in out.parents,'receipt must be new and external')
 saved={x.relative_to(study).as_posix():x.read_bytes() for x in study.rglob('*') if x.is_file()}
 need(sha(saved['manifest.json'])==a.manifest_sha256,'manifest pin mismatch');manifest=parse(saved['manifest.json'])
 need(manifest['source_commit']==a.source_commit and set(saved)==set(manifest['sha256'])|{'manifest.json'},'manifest inventory/source mismatch')
 for name,digest in manifest['sha256'].items():need(Path(name).name==name and sha(saved[name])==digest,'artifact drift: '+name)
 source=parse(saved['source-before.json']);authenticated=auth.source_identity(repo,source)
 need(parse(saved['source-after.json'])==source,'producer source snapshots differ')
 archive=auth.archive_check(a.archive,a.archive_sha256,saved)
 protocol,report=parse(saved['protocol.json']),parse(saved['report.json'])
 need(protocol['source_commit']==report['source_commit']==a.source_commit and protocol['source_sha256']==source['sha256'],'protocol source mismatch')
 need(protocol['version']=='equivariant-selected-cfrplus-fixed-study-v1' and protocol['schedule']==[list(x) for x in SCHEDULE],'schedule mismatch')
 need(report['schedule_planned']==report['schedule_attempted']==15 and report['failure'] is None and len(report['samples'])==15,'incomplete report')
 need(protocol['pair_diagnostics']=='compact' and protocol['exact_arithmetic']=='dyadic' and protocol['rank_cache_boards']==64,'protocol law mismatch')
 base=parse((repo/'benchmarks/four-street-integration-v1.json').read_bytes())['case']
 original=dict(base,id='original-22-exact-product-study')
 small=dict(base,config=dict(base['config'],starting_stack=[2,2]),runouts=['2c3c4h5s6h','2d3d4h5s6h'])
 expected={'original-22':original,'original-22-reject':original,'symmetric':dict(small,id='suit-exchange-symmetric-v1',sb_range='AcAh:1,AdAh:1',bb_range='KcKh:1,KdKh:1'),'asymmetric':dict(small,id='weighted-asymmetric-suit-exchange-v1',sb_range='AcAh:0.7,AdAh:0.3',bb_range='KcKh:0.4,KdKh:0.6'),'one-world':dict(base,id='one-world-t1000-v1',sb_range='AsAd',bb_range='KsKd',runouts=['2c3c4d7h8h'])}
 cases=protocol['cases'];need(cases==expected,'independent case reconstruction mismatch');payloads={};raws={};rejected=None
 for rec,(name,mode,sample,traced) in zip(report['samples'],SCHEDULE):
  label=f'{name}-{mode}-{sample}'; filename=label+'.json';raw=parse(saved[filename]);raws[label]=raw
  need(rec['artifact']==filename and {k:v for k,v in rec.items() if k!='artifact'}=={k:v for k,v in raw.items() if k!='payload'},'sample/report mismatch '+label)
  need(raw['case']==name and raw['reduction']==mode and raw['sample']==sample and raw['traced']==traced and raw['runtime']==protocol['runtime'],'sample metadata mismatch '+label)
  need(type(raw['seconds']) in (int,float) and math.isfinite(raw['seconds']) and raw['seconds']>0,'invalid time')
  calls=raw['actual_calls'];need(calls['pair_query_calls']==calls['native_calls']==calls['world_producer_calls']==calls['popen_calls']==0,'forbidden producer call')
  if name=='original-22-reject':
   need(raw['status']=='pretraining-rejected' and raw['payload'] is None and calls['rank_calls']==calls['default_trainer_calls']==calls['equivariant_trainer_calls']==0,'rejection mismatch');rejected=raw;continue
  need(raw['status']=='complete' and raw['error'] is None and raw['iterations']==(1000 if name=='one-world' else 10),'complete sample mismatch')
  need(calls['default_trainer_calls']==int(mode=='default') and calls['equivariant_trainer_calls']==int(mode=='suit-equivariant'),'trainer selection mismatch')
  payload=raw['payload'];need(payload['chance_contract']=='exact-product-selected-v1' and payload['pair_diagnostics']=='compact-exact-product-inputs-v1','payload law mismatch')
  need((payload.get('training_reduction')=='suit-equivariant-sorted-chance-binary64-v1')==(mode=='suit-equivariant'),'reduction label mismatch')
  adm=payload['operator_census']['whole_request_admission'];need(adm['combined_modeled_work_upper']<=adm['whole_request_limit'] and adm['retained_storage']['whole_request_peak_upper']<=adm['retained_storage']['entry_limit'],'admission exceeded')
  c=payload['operator_census'];kr=c['kernel'];ar=c['float_adapter'];ia=kr['integer_arithmetic'];forecast=c['bit_forecast']['dyadic_integer'];layout=c['packed_layout_actual']
  need(all(type(payload[k]) in (int,float) and math.isfinite(payload[k]) for k in METRICS),'nonfinite metric '+label)
  need(kr['rank_calls']==calls['rank_calls'] and kr['work_units_cumulative']<=adm['kernel']['whole_request_upper_work'] and kr['storage_entries_peak']<=kernel_limit(c),'kernel counters exceed admission '+label)
  need(ar['modeled_work_entries']<=adm['adapter']['whole_request_work_upper'] and ar['rejections']==0 and ar['conversion_contract']=='exact-product-vectors-binary64-v1','adapter counter mismatch '+label)
  need(ia['peak_operand_bits']<=ia['peak_forecast_bits']<=forecast['maximum_bits_upper'] and ia['peak_integer_payload_bits']<=forecast['logical_integer_payload_bits_upper']<=forecast['logical_integer_payload_bit_limit'],'integer bit/payload mismatch '+label)
  need(c['exact_pair_output']['candidate_pairs_scanned']==0 and c['exact_pair_output']['board_scan_work_upper']==0 and c['stored_complete_worlds']==c['stored_prefix_pair_edges']==0,'compact support mismatch '+label)
  need(c['training']['calls']==1 and c['training']['iterations']==raw['iterations'] and layout['information_sets']==payload['info_sets'] and layout['numeric_buffers']==4,'training/layout mismatch '+label)
  need(type(raw['process_lifetime_peak_working_set_bytes']) is int and raw['process_lifetime_peak_working_set_bytes']>0 and ((type(raw['python_peak_allocation_bytes']) is int and raw['python_peak_allocation_bytes']>0) if traced else raw['python_peak_allocation_bytes'] is None),'memory measurement mismatch '+label)
  payloads[label]=payload
 need(len(payloads)==14 and rejected is not None,'missing policies/rejection')
 # Only after source/archive authentication may repository mathematics import.
 sys.path.insert(0,str(repo))
 from scripts import four_street_validation as physical, exact_selected_compact_certificate as cert
 from scripts.preflop_validation import compare_result
 forbidden=['pokerlab.exact_selected_solver.solve_four_street_exact_selected','pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.__init__','pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.terminal_values_exact','pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.joint_marginals_exact','pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.pair_probability_exact','pokerlab.exact_selected_kernel.rank_hand','pokerlab.packed_operator_cfr.train_packed','pokerlab.equivariant_packed_cfr.train_equivariant_packed','pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds','pokerlab.preflop_solver._enumerate_physical_worlds','pokerlab.cards.rank_hand','pokerlab.dyadic_selected_arithmetic.DyadicSelectedArithmeticPlan.__init__','pokerlab.dyadic_selected_arithmetic.DyadicSelectedArithmeticPlan.marginals','pokerlab.dyadic_selected_arithmetic.DyadicSelectedArithmeticPlan.terminal','pokerlab.native_selected_operator.train_native_selected','pokerlab.native_selected_dag.train_native_selected_dag','pokerlab.native_public_cfr.train_native_public','subprocess.Popen']
 numeric=[];exact=[]
 with ExitStack() as stack:
  for target in forbidden:stack.enter_context(patch(target,side_effect=AssertionError('forbidden during saved replay: '+target)))
  for label,payload in payloads.items():
   name=raws[label]['case'];case=cases[name];model=physical.build_model(case)
   expanded=dict(payload,compatible_private_pairs=model.counts['compatible_pairs'],private_pair_probabilities=[{'sb_hand':row['sb_hand'],'bb_hand':row['bb_hand'],'probability':float(Fraction(row['fraction']))} for row in model.counts['pair_probabilities']])
   actual=physical.replay_policy(expanded,case);gaps=compare_result(expanded,actual)
   v=actual['value_sb'];b0=actual['sb_best_response_value'];b1=actual['bb_best_response_value'];gain0=max(0.,b0-v);gain1=max(0.,b1+v)
   metrics={'value_sb':v,'value_bb':-v,'sb_best_response_value':b0,'bb_best_response_value':b1,'sb_gain':gain0,'bb_gain':gain1,'nash_conv':gain0+gain1,'exploitability':(gain0+gain1)/2}
   allgaps={k:abs(float(payload[k])-metrics[k]) for k in METRICS};need(max(allgaps.values())<=1e-10,'numeric metric gap '+label)
   old=parse(saved[label+'-verification.json']);need(old['payload_metrics_within_tolerance'] is True and old['payload_metric_tolerance']==1e-10,'saved replay verdict mismatch')
   fresh=cert.evaluate_exact(case,payload);ref=old['exact_compact_certificate'];f=fresh['exact_certificate'];r=ref['exact_certificate']
   for field in ('metrics','threshold','threshold_met','normalized_policy_sha256'):
    need(f[field]==r[field],'exact certificate mismatch '+label+' '+field)
   need(fresh['compact_input_canonical_sha256']==ref['compact_input_canonical_sha256'],'raw policy hash mismatch')
   recorded=report['certificates'][label];need(recorded['metrics']==f['metrics'] and recorded['threshold_met']==f['threshold_met'] and recorded['verification_artifact']==label+'-verification.json','report certificate mismatch')
   numeric.append({'artifact':label,'gaps':allgaps});exact.append({'artifact':label,'threshold_met':f['threshold_met'],'normalized_policy_sha256':f['normalized_policy_sha256'],'metrics':f['metrics']})
 # Independently apply c/d swap to every public row and hand; no production symmetry code.
 order={r+s:i for i,(r,s) in enumerate((r,s) for r in '23456789TJQKA' for s in 'cdhs')};swap={'c':'d','d':'c','h':'h','s':'s'}
 def c(x):return x[0]+swap[x[1]]
 def image(row):
  h=row['history'];history=[]
  for token in h:
   if token.startswith('flop@'):history.append('flop@'+''.join(sorted((c(token[i:i+2]) for i in (5,7,9)),key=order.__getitem__)))
   elif token.startswith(('turn@','river@')):history.append(token[:token.index('@')+1]+c(token[token.index('@')+1:]))
   else:history.append(token)
  return row['player'],''.join(sorted((c(row['hand'][:2]),c(row['hand'][2:])))),tuple(history)
 orbit=[]
 for label,payload in payloads.items():
  if raws[label]['case']!='symmetric' or raws[label]['reduction']!='suit-equivariant':continue
  rows={(r['player'],r['hand'],tuple(r['history'])):r for r in payload['strategy']};need(len(rows)==len(payload['strategy']),'duplicate row')
  for row in rows.values():
   other=rows[image(row)];need([x['probability'].hex() for x in row['actions']]==[x['probability'].hex() for x in other['actions']],'suit orbit bit mismatch')
  old=parse(saved[label+'-orbit.json']);need(old['orbit_rows_checked']==len(rows) and old['maximum_probability_difference']==0,'saved orbit report mismatch');orbit.append({'artifact':label,'rows':len(rows)})
 need(len(orbit)==4,'missing symmetric orbit records')
 for mode in ('default','suit-equivariant'):
  baseline=payloads[f'symmetric-{mode}-0']
  for sample in (1,2,'traced'):
   other=payloads[f'symmetric-{mode}-{sample}'];need(other['strategy']==baseline['strategy'] and all(other[k]==baseline[k] for k in METRICS),'repeated-policy mismatch')
 comparisons={}
 for name in ('symmetric','asymmetric','original-22','one-world'):
  x,y=(payloads[f'{name}-{mode}-0'] for mode in ('default','suit-equivariant'))
  need(len(x['strategy'])==len(y['strategy']),'row count mismatch')
  difference=0.
  for l,r in zip(x['strategy'],y['strategy']):
   need({k:v for k,v in l.items() if k!='actions'}=={k:v for k,v in r.items() if k!='actions'} and len(l['actions'])==len(r['actions']),'row identity/menu mismatch')
   for la,ra in zip(l['actions'],r['actions']):
    need({k:v for k,v in la.items() if k!='probability'}=={k:v for k,v in ra.items() if k!='probability'},'action metadata mismatch')
    difference=max(difference,abs(la['probability']-ra['probability']))
  gaps={k:abs(x[k]-y[k]) for k in METRICS};rec=report['paired_comparisons'][name]
  need(rec['complete_rows']==len(x['strategy']) and rec['maximum_row_probability_difference']==difference and rec['metric_absolute_differences']==gaps,'report comparison mismatch')
  comparisons[name]={'rows':len(x['strategy']),'maximum_policy_difference':difference,'metric_gaps':gaps}
 need(comparisons['original-22']['maximum_policy_difference']==.5,'expected trajectory divergence missing')
 misses=[x['artifact'] for x in exact if not x['threshold_met']];passes=[x['artifact'] for x in exact if x['threshold_met']]
 need(len(misses)==12 and len(passes)==2 and set(misses)==set(report['finite_iteration_misses_retained']),'quality flags mismatch')
 times={mode:statistics.median(raws[f'symmetric-{mode}-{i}']['seconds'] for i in (0,1,2)) for mode in ('default','suit-equivariant')}
 after=auth.source_identity(repo,source);need(after['raw_sha256']==authenticated['raw_sha256'],'source drift')
 need({x.relative_to(study).as_posix():x.read_bytes() for x in study.rglob('*') if x.is_file()}==saved,'artifact drift')
 receipt={'status':'passed','source_commit':a.source_commit,'authenticated_source_files':authenticated['files'],'raw_source_sha256':authenticated['raw_sha256'],'archive':archive,'manifest_sha256':a.manifest_sha256,'helper_sha256':sha(Path(__file__).read_bytes()),'numeric_replays':numeric,'exact_certificates':exact,'suit_orbit_checks':orbit,'paired_comparisons':comparisons,'symmetric_t10_medians_seconds':times,'quality_misses':misses,'quality_passes':passes,'rejected_request':rejected,'source_and_artifacts_unchanged':True,'scope':'Saved-only conditional finite-game physical replay and bounded exact certificates; no production solve, training, rank, pair query, native execution or performance claim.'}
 out.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':'passed','numeric_replays':len(numeric),'exact_certificates':len(exact),'orbit_checks':len(orbit),'misses':len(misses),'passes':len(passes),'receipt_sha256':sha(out.read_bytes())}))
if __name__=='__main__':main()
