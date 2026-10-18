"""Sol's independent normalized policy check; no LP/trainer/exact-helper imports."""
from pathlib import Path
from fractions import Fraction as F
import sys,json,hashlib,math,subprocess,argparse
ROOT=Path(__file__).resolve().parents[1]
from scripts import verify_turn_weighted_sequence as reference
from scripts.turn_weighted_sequence_fixture import FIXTURE
rules=reference.rules
def need(condition,message):
    if not condition:raise ValueError(message)
def read(path,limit):
    need(path.stat().st_size<=limit,'Input cap')
    raw=path.read_bytes()
    need(len(raw)<=limit,'Input drift cap')
    return raw
def reconstruct(path=None):
    own_source=Path(__file__).read_bytes()
    git_before=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    report_path=Path(path) if path is not None else ROOT/'benchmarks/results/turn-weighted-cfrplus-profiles-v1.json'
    report_raw=read(report_path,2000000)
    report=json.loads(report_raw)
    observed=[(report_path,hashlib.sha256(report_raw).hexdigest(),2000000)]
    sources_before=reference._inputs()
    model_reference=reference.model(FIXTURE)
    model_bytes=json.dumps([model_reference],indent=2,sort_keys=True,allow_nan=False).encode()+b'\n'
    need(hashlib.sha256(model_bytes).hexdigest()=='7059a28917fb04d2be6d846245160a61539da83456a26c534e5e34d3c1841f2a','Independent physical model identity')
    hand=reference.analytical_policy(FIXTURE)
    need(hand['lower']==hand['value']==hand['upper']=='30','Independent known value')
    board=rules.cards(FIXTURE['board'])
    config=rules._config(FIXTURE['config'],'config')
    worlds,selected=rules._worlds(board,tuple(rules.expand_range(FIXTURE[p],board) for p in ('oop','ip')),FIXTURE['runouts'])
    root=rules._public_tree(board,config,config,selected,worlds)
    need(report['known_game_value_fraction']=='30' and report['target_nash_conv_fraction']=='1/1000','Known anchor or target changed')
    seen=set()
    summary=[]
    for item in report['results']:
        key=item['backend'],item['iterations_requested']
        need(key in {(b,n) for b in ('materialized','matrix-free') for n in (1000,3000,10000)} and key not in seen,'Grid identity')
        seen.add(key)
        policy_path=ROOT/'benchmarks/results/turn-weighted-cfrplus-policies-v1'/('turn-weighted-%s-%d.json'%key)
        need(item['policy_file']==policy_path.relative_to(ROOT).as_posix(),'Fixed grid policy path')
        payload=read(policy_path,1000000)
        observed.append((policy_path,hashlib.sha256(payload).hexdigest(),1000000))
        need(hashlib.sha256(payload).hexdigest()==item['policy_sha256'],'Policy hash')
        result=json.loads(payload)
        oracle=rules.replay_policy(result,FIXTURE['oop'],FIXTURE['ip'],board=FIXTURE['board'],config=FIXTURE['config'],river_config=FIXTURE['config'],runouts=FIXTURE['runouts'])
        rules.compare_result(result,oracle,tolerance=1e-9)
        need(result['iterations']==key[1] and item['iterations_completed']==key[1] and result['algorithm']=='cfrplus','Training metadata')
        policies,originals={},{}
        for row in result['strategy']:
            identity=(0 if row['player']=='oop' else 1,row['hand'],tuple(row['history']))
            need(identity not in policies,'Repeated row')
            raw=tuple(F.from_float(float(a['probability'])) for a in row['actions'])
            total=sum(raw,F(0))
            policies[identity]=tuple(v/total for v in raw)
            originals[identity]=(row,raw,total)
        value=sum((w['weight']*reference.profile(root,w,policies,config.pot) for w in worlds),F(0))
        upper=reference.response(root,worlds,policies,config.pot,0)
        lower=reference.response(root,worlds,policies,config.pot,1)
        expected=dict(value_oop=value,value_ip=-value,oop_best_response_value=upper,ip_best_response_value=-lower,oop_best_response_gain=upper-value,ip_best_response_gain=value-lower,nash_conv=upper-lower,exploitability=(upper-lower)/2)
        cert=item['exact']
        need(cert['metrics']=={k:str(v) for k,v in expected.items()},'Independent exact metric differs')
        need(F(cert['lower_value_bound'])==lower<=30<=upper==F(cert['upper_value_bound']),'Known-value response interval')
        need(item['target_met']==(upper-lower<=F(1,1000)) and type(item['target_met']) is bool,'Target decision')
        need(item['threshold_miss']==(upper-lower>F(1,1000)) and type(item['threshold_miss']) is bool,'Threshold-miss label')
        max_delta=max(abs(float(v)-oracle[k]) for k,v in expected.items())
        need(math.isfinite(max_delta) and max_delta<=1e-9,'Exact/float crosscheck')
        need(len(policies)==42 and len(cert['normalization_ledger'])==42,'Complete row census')
        ledger_seen=set()
        max_adjustment=F(0)
        normalized=[]
        for entry in cert['normalization_ledger']:
            identity=(0 if entry['player']=='oop' else 1,entry['hand'],tuple(entry['history']))
            need(identity in policies and identity not in ledger_seen,'Ledger identity')
            ledger_seen.add(identity)
            source,raw,total=originals[identity]
            need(F(entry['input_row_sum_fraction'])==total,'Ledger total')
            need(len(entry['actions'])==len(raw),'Ledger action coverage')
            for index,(action,before,after) in enumerate(zip(entry['actions'],raw,policies[identity])):
                delta=after-before
                max_adjustment=max(max_adjustment,abs(delta))
                need(action['index']==index and action['name']==source['actions'][index]['name'] and action['history_key']==source['actions'][index]['history_key'],'Ledger action')
                need(F(action['input_fraction'])==before and F(action['normalized_fraction'])==after and F(action['adjustment_fraction'])==delta and action['adjustment_float']==float(delta),'Ledger arithmetic')
        for identity in sorted(originals):
            row,_,_=originals[identity]
            normalized.append({k:row[k] for k in ('player','hand','street','board','history')}|{'actions':[{k:a[k] for k in ('name','amount','raise_to','history_key')}|{'probability_fraction':str(p)} for a,p in zip(row['actions'],policies[identity])]})
        need(cert['normalized_policy_rows']==normalized and F(cert['max_row_adjustment'])==max_adjustment,'Normalized rows')
        need(cert['worlds']==4 and cert['tree_nodes']==63 and cert['tree_depth']==8,'Physical tree census')
        need(cert['work_limit']==100000 and cert['depth_limit']==64 and cert['fraction_bit_limit']==65536,'Exact caps')
        need(type(cert['work']) is int and 0<cert['work']<=100000 and sum(cert['work_by_kind'].values())==cert['work'] and all(type(v) is int and v>=0 for v in cert['work_by_kind'].values()),'Work accounting')
        summary.append(dict(backend=key[0],iterations=key[1],nash_conv_fraction=str(upper-lower),nash_conv_float=float(upper-lower),target_met=item['target_met'],max_exact_vs_float_delta=max_delta,known_value='30'))
    need(len(seen)==6,'Missing grid profile')
    need(reference._inputs()==sources_before,'Reference source changed during reconstruction')
    need(all(hashlib.sha256(read(p,cap)).hexdigest()==digest for p,digest,cap in observed),'Input bytes changed during reconstruction')
    need(Path(__file__).read_bytes()==own_source,'Independent verifier source changed')
    need(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==git_before,'HEAD changed during independent reconstruction')
    return dict(status='SIX_POLICIES_INDEPENDENTLY_RECONSTRUCTED',results=summary)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path)
    args=parser.parse_args()
    result=reconstruct(args.input)
    print(json.dumps(dict(status=result['status'],results=[{k:v for k,v in row.items() if k!='nash_conv_fraction'} for row in result['results']]),indent=2,sort_keys=True),flush=True)

if __name__=='__main__':main()
