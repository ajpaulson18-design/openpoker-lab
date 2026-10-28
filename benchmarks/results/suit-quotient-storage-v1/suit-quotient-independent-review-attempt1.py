"""Independent saved-only exact suit-quotient study review. Never executes producer."""
import argparse,hashlib,importlib.util,json,math,statistics,sys,itertools
from pathlib import Path
from fractions import Fraction
from contextlib import ExitStack
from unittest.mock import patch
AUTH='8171ead3ba108f8200f15e85696f40d109ed894209fa7d77598780b83c1401c5'
METRICS=('value_sb','value_bb','sb_best_response_value','bb_best_response_value','sb_gain','bb_gain','nash_conv','exploitability')
SCHEDULE=[('symmetric-t10','expanded',0,False),('symmetric-t10','suit-quotient',0,False),('symmetric-t10','suit-quotient',1,False),('symmetric-t10','expanded',1,False),('symmetric-t10','expanded',2,False),('symmetric-t10','suit-quotient',2,False),('symmetric-t10','expanded','traced',True),('symmetric-t10','suit-quotient','traced',True),('blocker-18','expanded',0,False),('blocker-18','suit-quotient',0,False),('asymmetric-weighted','expanded',0,False),('asymmetric-weighted','suit-quotient',0,False),('mixed-stabilizer','expanded',0,False),('mixed-stabilizer','suit-quotient',0,False),('symmetric-t100','expanded',0,False),('symmetric-t100','suit-quotient',0,False),('payoff-varied-t10','expanded',0,False),('payoff-varied-t10','suit-quotient',0,False),('payoff-varied-t100','expanded',0,False),('payoff-varied-t100','suit-quotient',0,False),('original-22-t10','expanded',0,False),('original-22-t10','suit-quotient',0,False),('original-22-qreject','suit-quotient',0,False)]
SUITS='cdhs';DECK=tuple(r+s for r in '23456789TJQKA' for s in SUITS);ORDER={c:i for i,c in enumerate(DECK)}
def card(c,m):return c[0]+m[c[1]]
def hand(h,m):return tuple(sorted(card(c,m) for c in h))
def board(b,m):return tuple(sorted((card(c,m) for c in b[:3]),key=ORDER.__getitem__))+tuple(card(c,m) for c in b[3:])
def history(h,m):
 out=[]
 for t in h:
  if t.startswith('flop@'):out.append('flop@'+''.join(sorted((card(t[i:i+2],m) for i in (5,7,9)),key=ORDER.__getitem__)))
  elif t.startswith(('turn@','river@')):out.append(t[:t.index('@')+1]+card(t[t.index('@')+1:],m))
  else:out.append(t)
 return tuple(out)
def key_image(k,m):
 player,h,hist=k;return player,''.join(hand((h[:2],h[2:]),m)),history(hist,m)
def menu(node):return tuple((a.name,a.amount,a.raise_to,a.token) for a in node.actions)
def main():
 p=argparse.ArgumentParser()
 for k in ('repo','study','archive','receipt'):p.add_argument('--'+k,type=Path,required=True)
 for k in ('source-commit','manifest-sha256','archive-sha256','confirmed-terminal-handle'):p.add_argument('--'+k,required=True)
 p.add_argument('--terminal-exit-code',type=int,required=True);a=p.parse_args()
 ap=Path(__file__).with_name('exact-selected-independent-review.py')
 if hashlib.sha256(ap.read_bytes()).hexdigest()!=AUTH:raise ValueError('authentication helper pin mismatch')
 spec=importlib.util.spec_from_file_location('saved_auth',ap);auth=importlib.util.module_from_spec(spec);spec.loader.exec_module(auth);auth.FROZEN=a.source_commit
 need,sha,parse=auth.need,auth.sha,auth.parse
 need(a.confirmed_terminal_handle=='77407' and a.terminal_exit_code==0,'terminal result mismatch')
 repo,study,out=a.repo.resolve(),a.study.resolve(),a.receipt.resolve()
 need(not out.exists() and repo not in out.parents and study not in out.parents,'new external receipt required')
 saved={x.relative_to(study).as_posix():x.read_bytes() for x in study.rglob('*') if x.is_file()}
 need(sha(saved['manifest.json'])==a.manifest_sha256,'manifest pin mismatch');manifest=parse(saved['manifest.json'])
 need(manifest['source_commit']==a.source_commit and set(saved)==set(manifest['sha256'])|{'manifest.json'},'manifest inventory mismatch')
 for name,digest in manifest['sha256'].items():need(Path(name).name==name and sha(saved[name])==digest,'artifact drift '+name)
 source=parse(saved['source-before.json']);authenticated=auth.source_identity(repo,source)
 need(parse(saved['source-after.json'])==source,'producer source changed');archive=auth.archive_check(a.archive,a.archive_sha256,saved)
 protocol,report=parse(saved['protocol.json']),parse(saved['report.json'])
 need(protocol['source_commit']==report['source_commit']==a.source_commit and protocol['source_sha256']==source['sha256'],'source declaration mismatch')
 need(protocol['version']=='suit-quotient-storage-fixed-study-v1' and protocol['schedule']==[list(x) for x in SCHEDULE],'protocol mismatch')
 need(protocol['rank_cache_boards']==64 and protocol['exact_arithmetic']=='dyadic' and protocol['pair_diagnostics']=='compact' and protocol['training_reduction']=='suit-equivariant-sorted-chance-binary64-v1','math contract mismatch')
 need(report['schedule_planned']==report['schedule_attempted']==23 and report['failure'] is None and len(report['samples'])==23,'incomplete producer')
 base=parse((repo/'benchmarks/four-street-integration-v1.json').read_bytes())['case']
 small=dict(base,config=dict(base['config'],starting_stack=[2,2]),runouts=['2c3c4h5s6h','2d3d4h5s6h'])
 expected={
  'symmetric-t10':dict(small,id='suit-exchange-symmetric-v1',sb_range='AcAh:1,AdAh:1',bb_range='KcKh:1,KdKh:1'),
  'blocker-18':dict(small,id='blocker-conditioned-18-worlds-v1',sb_range='AcAh,AdAh,2cAh,2dAh',bb_range='KcKh,KdKh,3cKh,3dKh'),
  'asymmetric-weighted':dict(small,id='weighted-asymmetric-suit-exchange-v1',sb_range='AcAh:0.7,AdAh:0.3',bb_range='KcKh:0.4,KdKh:0.6'),
  'mixed-stabilizer':dict(small,id='mixed-suit-stabilizer-v1',sb_range='AcAd',bb_range='KcKd'),
  'payoff-varied-t10':dict(small,id='payoff-varied-private-flush-v1',sb_range='AcQc,AdQd',bb_range='KcJc,KdJd',runouts=['2c3c7c9hTs','2d3d7d9hTs']),
  'original-22-t10':dict(base,id='original-22-exact-product-study')}
 expected['symmetric-t100']=expected['symmetric-t10'];expected['payoff-varied-t100']=expected['payoff-varied-t10'];expected['original-22-qreject']=expected['original-22-t10']
 need(protocol['cases']==expected,'independent case declarations differ')
 payloads={};raws={};rejection=None
 for rec,(name,storage,sample,traced) in zip(report['samples'],SCHEDULE):
  label=f'{name}-{storage}-{sample}';filename=label+'.json';raw=parse(saved[filename]);raws[label]=raw
  need(rec['artifact']==filename and {k:v for k,v in rec.items() if k!='artifact'}=={k:v for k,v in raw.items() if k!='payload'},'report/sample binding '+label)
  need(raw['case']==name and raw['storage']==storage and raw['sample']==sample and raw['traced']==traced and raw['runtime']==protocol['runtime'],'sample identity '+label)
  need(type(raw['seconds']) in (int,float) and math.isfinite(raw['seconds']) and raw['seconds']>0,'invalid timing '+label)
  need(type(raw['process_lifetime_peak_working_set_bytes']) is int and raw['process_lifetime_peak_working_set_bytes']>0,'invalid process peak')
  need((type(raw['python_peak_allocation_bytes']) is int and raw['python_peak_allocation_bytes']>0) if traced else raw['python_peak_allocation_bytes'] is None,'allocation trace flag mismatch')
  calls=raw['actual_calls'];need(all(type(v) is int and v>=0 for v in calls.values()) and all(calls[k]==0 for k in ('pair_query_calls','native_calls','world_producer_calls','popen_calls')),'forbidden producer call')
  if name=='original-22-qreject':
   need(raw['status']=='pretraining-rejected' and raw['payload'] is None and not any(calls.values()) and raw['iterations']==1000,'pretraining rejection mismatch');rejection=raw;continue
  T=100 if name.endswith('t100') else 10
  need(raw['status']=='complete' and raw['error'] is None and raw['iterations']==T and calls['rank_calls']>0,'complete call mismatch '+label)
  need(calls['equivariant_trainer_calls']==int(storage=='expanded') and calls['quotient_trainer_calls']==calls['quotient_plan_calls']==int(storage=='suit-quotient'),'trainer selection mismatch')
  x=raw['payload'];c=x['operator_census'];ad=c['whole_request_admission'];kr=c['kernel'];ar=c['float_adapter'];layout=c['packed_layout_actual'];bits=c['bit_forecast']['dyadic_integer'];actual=kr['integer_arithmetic']
  need(x['chance_contract']=='exact-product-selected-v1' and x['pair_diagnostics']=='compact-exact-product-inputs-v1' and x['training_reduction']=='suit-equivariant-sorted-chance-binary64-v1','payload law mismatch')
  need(x.get('strategy_storage','expanded')==('suit-quotient-packed-v1' if storage=='suit-quotient' else 'expanded'),'storage label mismatch')
  need(all(type(x[k]) in (int,float) and math.isfinite(x[k]) for k in METRICS),'nonfinite metric')
  need(kr['rank_calls']==calls['rank_calls'] and kr['work_units_cumulative']<=ad['kernel']['whole_request_upper_work'] and ar['modeled_work_entries']<=ad['adapter']['whole_request_work_upper'] and ad['combined_modeled_work_upper']<=ad['whole_request_limit'],'work admission mismatch')
  need(kr['storage_entries_peak']<=ad['retained_storage']['kernel_peak_upper'] and ar['retained_mapping_entries']<=ad['retained_storage']['adapter_peak_upper'] and ad['retained_storage']['whole_request_peak_upper']<=ad['retained_storage']['entry_limit'],'retained admission mismatch')
  need(actual['peak_operand_bits']<=actual['peak_forecast_bits']<=bits['maximum_bits_upper'] and actual['peak_integer_payload_bits']<=bits['logical_integer_payload_bits_upper']<=bits['logical_integer_payload_bit_limit'] and actual['modeled_limb_work_upper']<=bits['whole_request_limb_work_upper'],'integer admission mismatch')
  need(c['stored_complete_worlds']==c['stored_prefix_pair_edges']==c['exact_pair_output']['candidate_pairs_scanned']==0 and c['training']['calls']==1 and c['training']['layout']==layout,'representation/training receipt mismatch')
  payloads[label]=x
 need(len(payloads)==22 and rejection is not None,'missing complete policies')
 sys.path.insert(0,str(repo))
 from scripts import four_street_validation as physical, exact_selected_compact_certificate as cert
 from scripts.preflop_validation import compare_result,independent_rank
 forbidden=['pokerlab.exact_selected_solver.solve_four_street_exact_selected','pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.__init__','pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.terminal_values_exact','pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.joint_marginals_exact','pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.pair_probability_exact','pokerlab.exact_selected_kernel.rank_hand','pokerlab.cards.rank_hand','pokerlab.dyadic_selected_arithmetic.DyadicSelectedArithmeticPlan.__init__','pokerlab.dyadic_selected_arithmetic.DyadicSelectedArithmeticPlan.marginals','pokerlab.dyadic_selected_arithmetic.DyadicSelectedArithmeticPlan.terminal','pokerlab.suit_quotient_plan.SuitQuotientPlan.__init__','pokerlab.suit_quotient_cfr.train_suit_quotient','pokerlab.equivariant_packed_cfr.train_equivariant_packed','pokerlab.packed_operator_cfr.train_packed','pokerlab.preflop_solver._enumerate_physical_worlds','pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds','pokerlab.native_selected_operator.train_native_selected','pokerlab.native_selected_dag.train_native_selected_dag','pokerlab.native_public_cfr.train_native_public','subprocess.Popen']
 numeric=[];exact=[];orbits=[];models={}
 with ExitStack() as stack:
  for target in forbidden:stack.enter_context(patch(target,side_effect=AssertionError('forbidden replay entry: '+target)))
  for label,x in payloads.items():
   name=raws[label]['case'];case=expected[name]
   if name not in models:models[name]=physical.build_model(case)
   model=models[name]
   expanded=dict(x,compatible_private_pairs=model.counts['compatible_pairs'],private_pair_probabilities=[{'sb_hand':r['sb_hand'],'bb_hand':r['bb_hand'],'probability':float(Fraction(r['fraction']))} for r in model.counts['pair_probabilities']])
   replay=physical.replay_policy(expanded,case);compare_result(expanded,replay)
   v=replay['value_sb'];b0=replay['sb_best_response_value'];b1=replay['bb_best_response_value'];g0=max(0.,b0-v);g1=max(0.,b1+v)
   mm={'value_sb':v,'value_bb':-v,'sb_best_response_value':b0,'bb_best_response_value':b1,'sb_gain':g0,'bb_gain':g1,'nash_conv':g0+g1,'exploitability':(g0+g1)/2}
   gaps={k:abs(x[k]-mm[k]) for k in METRICS};need(max(gaps.values())<=1e-10,'numeric replay mismatch '+label)
   old=parse(saved[label+'-verification.json']);fresh=cert.evaluate_exact(case,x);f=fresh['exact_certificate'];r=old['exact_compact_certificate']['exact_certificate']
   for field in ('metrics','threshold','threshold_met','normalized_policy_sha256'):need(f[field]==r[field],'exact mismatch '+label+' '+field)
   need(fresh['compact_input_canonical_sha256']==old['exact_compact_certificate']['compact_input_canonical_sha256'],'compact hash mismatch')
   recorded=report['certificates'][label];need(recorded['metrics']==f['metrics'] and recorded['threshold_met']==f['threshold_met'] and recorded['verification_artifact']==label+'-verification.json','report certificate mismatch')
   numeric.append({'artifact':label,'gaps':gaps});exact.append({'artifact':label,'metrics':f['metrics'],'threshold_met':f['threshold_met'],'normalized_policy_sha256':f['normalized_policy_sha256']})
   if raws[label]['storage']!='suit-quotient':continue
   parsed=physical._case_inputs(case);outcomes,ranges=parsed[-2:]
   group=[]
   for perm in itertools.permutations(SUITS):
    mapping=dict(zip(SUITS,perm))
    if all({hand(h,mapping):Fraction.from_float(float(w)) for h,w in side.items()}=={h:Fraction.from_float(float(w)) for h,w in side.items()} for side in ranges) and {board(b,mapping) for b in outcomes}==set(outcomes):group.append((perm,mapping))
   keys=model.expected_infos;classes={};rows={(r['player'],r['hand'],tuple(r['history'])):r for r in x['strategy']};need(len(rows)==len(keys),'row identity size mismatch')
   for key,node in keys.items():
    images={key_image(key,m) for _,m in group};need(all(k in keys and menu(keys[k])==menu(node) for k in images),'missing/mismatched G-transformed row')
    representative=min(images);classes[representative]=(len(images),len(node.actions))
    prow=rows[('sb' if key[0]==0 else 'bb',key[1],key[2])]
    for mapped in images:
     other=rows[('sb' if mapped[0]==0 else 'bb',mapped[1],mapped[2])]
     need([a['probability'].hex() for a in prow['actions']]==[a['probability'].hex() for a in other['actions']],'orbit policy bit mismatch')
   worlds={(w['hands'],w['board']):w for w in model.worlds};signs=set()
   for w in model.worlds:
    ranks=[independent_rank(tuple(w['hands'][p])+tuple(w['board'])) for p in (0,1)];sign=(ranks[0]>ranks[1])-(ranks[0]<ranks[1]);need(sign==w['sign'],'rank oracle disagreement');signs.add(sign)
    for _,m in group:
     image=(tuple(hand(h,m) for h in w['hands']),board(w['board'],m));other=worlds[image]
     need(other['weight']==w['weight'] and other['sign']==sign,'weighted showdown automorphism failure')
   q=x['operator_census']['suit_quotient_storage'];packed=x['operator_census']['packed_layout_actual'];qslots=sum(n for _,n in classes.values())
   need(set(q['group'])=={''.join(g) for g,_ in group} and q['group_size']==len(group),'group mismatch')
   need(q['quotient_information_rows']==len(classes) and q['quotient_action_slots']==qslots and q['expanded_information_rows']==len(keys) and q['expanded_action_slots']==sum(len(n.actions) for n in keys.values()),'independent Q geometry mismatch')
   need(packed['numeric_buffer_bytes']==32*qslots and packed['member_checks']==2*raws[label]['iterations']*len(keys) and q['retained_expanded_row_lookup_entries']==0,'Q storage/member receipt mismatch')
   if name=='mixed-stabilizer':need(len({size for size,_ in classes.values()})>1,'missing mixed orbit sizes')
   if name.startswith('payoff-varied'):need(signs=={-1,1},'private-flush game lacks both payoff signs')
   if name=='blocker-18':need(len(worlds)==18 and packed['expanded_layout_equivalent']['dense_decision_hand_slots']>len(keys),'missing physical holes')
   orbits.append({'artifact':label,'group':[''.join(g) for g,_ in group],'rows':len(keys),'q_rows':len(classes),'q_action_slots':qslots,'orbit_sizes':sorted({size for size,_ in classes.values()}),'world_signs':sorted(signs)})
 # Pair complete row metadata/policy bits/metrics/exact certificate hashes.
 bylabel={x['artifact']:x for x in exact};pairs=[]
 for name,storage,sample,traced in SCHEDULE:
  if storage!='expanded':continue
  left=f'{name}-expanded-{sample}';right=f'{name}-suit-quotient-{sample}';x,y=payloads[left],payloads[right]
  need(len(x['strategy'])==len(y['strategy']) and x['chance_input_snapshot']==y['chance_input_snapshot'],'paired shape mismatch')
  for l,r in zip(x['strategy'],y['strategy']):
   need({k:v for k,v in l.items() if k!='actions'}=={k:v for k,v in r.items() if k!='actions'} and len(l['actions'])==len(r['actions']),'paired row mismatch')
   for la,ra in zip(l['actions'],r['actions']):need({k:v for k,v in la.items() if k!='probability'}=={k:v for k,v in ra.items() if k!='probability'} and la['probability'].hex()==ra['probability'].hex(),'paired action/policy mismatch')
  need(all(x[k]==y[k] for k in METRICS) and bylabel[left]['metrics']==bylabel[right]['metrics'] and bylabel[left]['threshold_met']==bylabel[right]['threshold_met'] and bylabel[left]['normalized_policy_sha256']==bylabel[right]['normalized_policy_sha256'],'paired metric/certificate mismatch')
  rec=report['paired_comparisons'][left+'__vs__'+right];need(rec['policy_bitwise_identical'] and rec['metric_values_identical'] and rec['exact_certificate_metrics_identical'] and rec['exact_threshold_flags_identical'],'report pair mismatch')
  pairs.append({'expanded':left,'quotient':right,'rows':len(x['strategy'])})
 need(len(pairs)==11,'pair count mismatch')
 for storage in ('expanded','suit-quotient'):
  baseline=payloads['symmetric-t10-'+storage+'-0']
  for sample in (1,2,'traced'):
   x=payloads[f'symmetric-t10-{storage}-{sample}'];need(x['strategy']==baseline['strategy'] and all(x[k]==baseline[k] for k in METRICS),'repeat mismatch')
 misses=[x['artifact'] for x in exact if not x['threshold_met']];passes=[x['artifact'] for x in exact if x['threshold_met']]
 need(set(misses)==set(report['finite_iteration_threshold_misses_retained']),'quality misses differ')
 medians={s:statistics.median(raws[f'symmetric-t10-{s}-{i}']['seconds'] for i in (0,1,2)) for s in ('expanded','suit-quotient')}
 for s,key in (('expanded','expanded'),('suit-quotient','suit_quotient')):need(medians[s]==report['paired_comparisons']['symmetric-t10-three-pair-medians'][key]['full_call_seconds'],'median mismatch')
 trace={s:{k:raws[f'symmetric-t10-{s}-traced'][k] for k in ('seconds','python_peak_allocation_bytes','process_lifetime_peak_working_set_bytes')} for s in ('expanded','suit-quotient')}
 after=auth.source_identity(repo,source);need(after['raw_sha256']==authenticated['raw_sha256'],'source drift')
 need({x.relative_to(study).as_posix():x.read_bytes() for x in study.rglob('*') if x.is_file()}==saved,'artifact drift')
 receipt={'status':'passed','source_commit':a.source_commit,'authenticated_source_files':authenticated['files'],'raw_source_sha256':authenticated['raw_sha256'],'archive':archive,'manifest_sha256':a.manifest_sha256,'helper_sha256':sha(Path(__file__).read_bytes()),'numeric_replays':numeric,'exact_certificates':exact,'independent_orbits':orbits,'pairs':pairs,'medians_seconds':medians,'traced_observations':trace,'quality_misses':misses,'quality_passes':passes,'rejection':rejection,'source_and_artifacts_unchanged':True,'scope':'Bounded saved-only independent physical policies, group/orbit and exact BR review. No production trainer, plan, kernel, rank, native, or process execution. Not proof of general convergence or memory/RSS benefit.'}
 out.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':'passed','numeric_replays':len(numeric),'exact_certificates':len(exact),'independent_Q_orbits':len(orbits),'paired_policies':len(pairs),'misses':len(misses),'passes':len(passes),'receipt_sha256':sha(out.read_bytes())}))
if __name__=='__main__':main()
