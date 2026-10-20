"""Independent global-suit model/policy reference; no transport, LP or trainer imports."""
from collections import defaultdict
from fractions import Fraction as F
from itertools import permutations
from pathlib import Path
import copy,hashlib,json,subprocess,math
from scripts import verify_turn_blocker_sequence as base
from scripts.turn_blocker_sequence_fixture import FIXTURE
ROOT=Path(__file__).resolve().parents[1]
SUITS='cdhs'
REFERENCE=ROOT/'benchmarks/results/turn-suit-exact-reference-v1.json'
WITNESS_SHA='1da6f053f308aae7e6804c7c543c7c5f79d572d5104617d8368486e3704deaf4'

def require(ok,message):
    if not ok:raise ValueError(message)

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def hand(value,table):
    # This reference is fixed to AA,QQ,6T hands; lexical canonical card order
    # equals the stored range-parser order for these rank patterns.
    require(type(value) is str and len(value)==4,'Expected fixed two-card hand')
    cards=[value[:2].translate(table),value[2:].translate(table)]
    require(len(set(cards))==2,'Duplicate physical card')
    return ''.join(sorted(cards))

def history(value,table):
    return tuple(token.translate(table) if token.startswith('river@') else token for token in value)

def fixture(target):
    require(type(target) is str and len(target)==4 and set(target)==set(SUITS),'Expected suit bijection')
    table=str.maketrans(SUITS,target)
    result=copy.deepcopy(FIXTURE)
    for name in ('board','oop','ip'):result[name]=result[name].translate(table)
    result['runouts']=[card.translate(table) for card in result['runouts']]
    return result

def game(f):
    board=base.rules.cards(f['board'])
    config=base.rules._config(f['config'],'config')
    worlds,selected=base.rules._worlds(board,tuple(base.rules.expand_range(f[p],board) for p in ('oop','ip')),f['runouts'])
    require(len(worlds)==6 and len(selected)==2,'Fixed physical support differs')
    tree=base.rules._public_tree(board,config,config,selected,worlds)
    pending=[(tree,1)];seen=set();decisions=[]
    while pending:
        node,depth=pending.pop()
        require(id(node) not in seen and depth<=8,'Expected bounded public tree')
        seen.add(id(node));require(len(seen)<=63,'Public tree cap')
        if isinstance(node,base.rules._Decision):
            decisions.append(node);pending.extend((c,depth+1) for c in node.children)
        elif isinstance(node,base.rules._Chance):pending.extend((c,depth+1) for c in node.branches.values())
        else:require(isinstance(node,base.rules._Terminal),'Unknown node')
    require(len(seen)==63 and len(decisions)==28,'Full/decision node census differs')
    for w in worlds:
        left,right=(base.rank(w['board']+h) for h in w['hands'])
        require((left>right)-(left<right)==w['sign'],'Independent best-five mismatch')
    return config,worlds,tree,decisions

def structure(node,inverse):
    if isinstance(node,base.rules._Terminal):return ['terminal',node.kind,node.winner,list(node.contributions)]
    if isinstance(node,base.rules._Chance):return ['chance',list(history(node.history,inverse)),[[card.translate(inverse),structure(child,inverse)] for card,child in sorted(node.branches.items(),key=lambda kv:kv[0].translate(inverse))]]
    return ['decision',node.player,list(history(node.history,inverse)),[c.translate(inverse) for c in node.board],[[a.name,a.token,a.amount,a.raise_to,structure(c,inverse)] for a,c in zip(node.actions,node.children)]]

def world_law(worlds,inverse):
    return sorted([hand(''.join(w['hands'][0]),inverse),hand(''.join(w['hands'][1]),inverse),w['river'].translate(inverse),str(w['weight']),w['sign']] for w in worlds)

def policy_rows(rows,target):
    table=str.maketrans(SUITS,target)
    transformed=copy.deepcopy(rows)
    for row in transformed:
        row['hand']=hand(row['hand'],table)
        row['board']=[c.translate(table) for c in row['board']]
        row['history']=list(history(row['history'],table))
    return transformed

def replay(rows,f,prepared=None):
    config,worlds,tree,nodes=prepared if prepared is not None else game(f)
    saved={(0 if r['player']=='oop' else 1,r['hand'],tuple(r['history'])):r for r in rows}
    require(len(saved)==len(rows)==56,'Expected complete unique legal policy rows')
    actions=[a for row in rows for a in row['actions']]
    rational=any('probability_fraction' in a for a in actions)
    require(all(('probability_fraction' in a)==rational for a in actions),'Mixed probability representation')
    # Fixed reference rationals are tiny; binary64 probabilities are dyadic.
    # With56 two-action rows, normalized denominator product bits are bounded
    # below65536 (56*1076 plus weights/utilities) before response arithmetic.
    for action in actions:
        if rational:
            text=action['probability_fraction']
            require(type(text) is str and len(text)<=128,'Bounded reference fraction encoding')
            value=F(text)
            require(str(value)==text and max(abs(value.numerator).bit_length(),value.denominator.bit_length())<=128,'Canonical bounded reference fraction')
            require(type(action['probability']) is float and action['probability']==float(value),'Reference float projection')
        else:
            require(type(action['probability']) is float and math.isfinite(action['probability']),'Binary64 probability required')
            value=F.from_float(action['probability'])
        require(0<=value<=1,'Probability outside unit interval')
    policies={}
    for node in nodes:
        for world in worlds:
            if world['board'][:len(node.board)]!=node.board:continue
            key=node.player,''.join(world['hands'][node.player]),node.history
            if key in policies:continue
            require(key in saved,'Missing legal policy row')
            row=saved[key]
            require(row['board']==list(node.board) and row['street']==('turn' if len(node.board)==4 else 'river'),'Wrong visible board/street')
            require(len(row['actions'])==len(node.actions),'Action count')
            for a,b in zip(row['actions'],node.actions):
                require((a['name'],a['history_key'],a['amount'],a['raise_to'])==(b.name,b.token,b.amount,b.raise_to),'Action identity')
            raw=tuple(F(a['probability_fraction']) if 'probability_fraction' in a else F.from_float(a['probability']) for a in row['actions'])
            require(all(v>=0 for v in raw) and sum(raw,F(0))>0,'Invalid probabilities')
            total=sum(raw,F(0))
            if rational:require(total==1,'Exact reference probabilities must sum to one')
            policies[key]=tuple(v/total for v in raw)
    require(set(policies)==set(saved),'Extraneous hidden/future identity')
    v=sum((w['weight']*base.profile(tree,w,policies,config.pot) for w in worlds),F(0))
    upper=base.response(tree,worlds,policies,config.pot,0)
    lower=base.response(tree,worlds,policies,config.pot,1)
    metrics=dict(value_oop=v,value_ip=-v,oop_best_response_value=upper,ip_best_response_value=-lower,oop_best_response_gain=upper-v,ip_best_response_gain=v-lower,nash_conv=upper-lower,exploitability=(upper-lower)/2)
    return {k:str(v) for k,v in metrics.items()}

def reconstruct():
    own=Path(__file__).read_bytes();sources=base._inputs()
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    raw=base.OUTPUT.read_bytes();require(hashlib.sha256(raw).hexdigest()==WITNESS_SHA,'Pinned exact source witness')
    report=base.verify_saved_artifact()
    rows=report['results'][0]['rational_strategy']
    base_game=game(FIXTURE);identity=str.maketrans(SUITS,SUITS)
    expected_structure=structure(base_game[2],identity)
    expected_law=world_law(base_game[1],identity)
    results=[]
    for chars in permutations(SUITS):
        target=''.join(chars);inverse=str.maketrans(target,SUITS)
        f=fixture(target);g=game(f)
        require(world_law(g[1],inverse)==expected_law,'Conditional world law is not equivariant')
        require(structure(g[2],inverse)==expected_structure,'Public action/payoff tree is not equivariant')
        transported=policy_rows(rows,target)
        metrics=replay(transported,f,g)
        require(metrics['value_oop']==metrics['oop_best_response_value']=='115/7' and metrics['ip_best_response_value']=='-115/7' and metrics['nash_conv']=='0','Exact transported equilibrium differs')
        results.append(dict(target=target,fixture=f,world_law_sha256=hashlib.sha256(canonical(expected_law)).hexdigest(),rational_strategy_sha256=hashlib.sha256(canonical(transported)).hexdigest(),metrics=metrics))
    require(base._inputs()==sources and base.OUTPUT.read_bytes()==raw and Path(__file__).read_bytes()==own,'Reference input/source drift')
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==head,'Reference HEAD drift')
    return dict(kind='PRESEARCH_24_GLOBAL_SUIT_EXACT_REFERENCE',source_witness_sha256=WITNESS_SHA,candidate_training_run=False,results=results)

if __name__=='__main__':
    result=reconstruct();raw=json.dumps(result,sort_keys=True,indent=2,allow_nan=False).encode()+b'\n'
    if REFERENCE.exists():require(REFERENCE.read_bytes()==raw,'Frozen exact reference changed')
    else:REFERENCE.write_bytes(raw)
    print(json.dumps(dict(status='PASS24_EXACT_GLOBAL_SUIT_ISOMORPHISMS',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()),sort_keys=True))
