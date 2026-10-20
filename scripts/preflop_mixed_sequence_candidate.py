"""Candidate-only exact rank quotient and physical-policy lift for one finite game.

The independent physical pure-response oracle is the certificate authority;
this producer and its reduced LP are never imported by that oracle.
"""
from fractions import Fraction as Q
import json
from pathlib import Path
from scripts import preflop_mixed_range_reference as reference
from scripts import preflop_checkdown_validation as rules
from scripts import river_sequence_form as lp
from scripts.benchmark_preflop_covered_counts import checksum

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/'benchmarks/preflop-mixed-exact-witness-v1.json'
SPEC_SHA='4307f9590e2f34d568cab929c0401eab572a7c0af0725f6181299a5b6636aa19'


def _jsonable(value):
    if isinstance(value,Q):return str(value)
    if isinstance(value,dict):return {k:_jsonable(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [_jsonable(v) for v in value]
    return value


def build_candidate(spec=None):
    if spec is None:spec=json.loads(SPEC.read_bytes())
    if checksum(spec)!=SPEC_SHA:raise ValueError('Requires frozen mixed exact witness specification')
    if any(lp.CAPS[k]!=v for k,v in spec['lp_caps'].items()):raise ValueError('Existing exact LP caps changed')
    game=json.loads(reference.SPEC.read_bytes())
    if checksum(game)!=spec['physical_game_spec_sha256']:raise ValueError('Pinned physical game specification changed')
    game=json.loads(reference.SPEC.read_bytes());table,physical,sources=reference.load_inputs(game)
    means={}
    for rank in 'AQ':
     prior=Q(1,54) if rank=='A' else Q(1,108)
     mass=sum((prior for x in physical if x['sb_hand'][0]==rank),Q(0))
     means[rank]=sum((prior*Q(x['wins']-x['losses'],x['boards']) for x in physical if x['sb_hand'][0]==rank),Q(0))/mass
    root,census=rules._build(rules._config(game['config']))
    seqs=[[('empty',)],[('empty',)]];parents=[{},{}];menus=[{},{}];children=[{},{}]
    pairs=[('AA','KK',Q(2,3),means['A']),('QQ','KK',Q(1,3),means['Q'])]
    def collect(node,current,pair):
     if isinstance(node,rules._Terminal):return
     p=node.player;hand=pair[p];key=(hand,node.history)
     if key in parents[p]:assert parents[p][key]==current[p]
     parents[p][key]=current[p];menus[p][key]=tuple(a.token for a in node.actions);kids=[]
     for a,child in zip(node.actions,node.children):
      sid=(hand,node.history,a.token)
      if sid not in seqs[p]:seqs[p].append(sid)
      kids.append(sid);nxt=list(current);nxt[p]=sid;collect(child,nxt,pair)
     children[p][key]=kids
    for pair in pairs:collect(root,(('empty',),('empty',)),pair)
    nx,ny=map(len,seqs);me,mf=(len(x)+1 for x in parents)
    shapes={'oop':(me+ny,nx+2*mf+ny+me+ny),'ip':(mf+nx,ny+2*me+nx+mf+nx)}
    for name,(rows,cols) in shapes.items():
     if [rows,cols,(rows+1)*(cols+1)]!=spec['candidate_lp_shapes'][name]:raise ValueError('Candidate LP structural census changed')
    if census!=spec['public_tree']:raise ValueError('Independent numeric public tree changed')
    for rows,cols in shapes.values():
     assert rows<=lp.CAPS['rows'] and cols<=lp.CAPS['columns'] and (rows+1)*(cols+1)<=lp.CAPS['cells']
    flows=[];labels=[];indexes=[{s:i for i,s in enumerate(seq)} for seq in seqs]
    for p in (0,1):
     row=[Q(0)]*len(seqs[p]);row[0]=Q(1);flows.append(row);labels.append({'id':str(p)+':empty'})
     for key in parents[p]:
      row=[Q(0)]*len(seqs[p]);row[indexes[p][parents[p][key]]]-=1
      for child in children[p][key]:row[indexes[p][child]]+=1
      flows.append(row);labels.append({'id':str((p,key))})
    A=[[Q(0)]*ny for _ in range(nx)]
    def accumulate(node,current,pair):
     if isinstance(node,rules._Terminal):
      matched=Q(min(node.contributions));u=matched*(pair[3] if node.winner is None else (1 if node.winner==0 else -1))
      A[indexes[0][current[0]]][indexes[1][current[1]]]+=pair[2]*u
      return
     p=node.player;hand=pair[p]
     for a,child in zip(node.actions,node.children):
      nxt=list(current);nxt[p]=(hand,node.history,a.token);accumulate(child,nxt,pair)
    for pair in pairs:accumulate(root,(('empty',),('empty',)),pair)
    model={'A':A,'infos':parents,'flows':flows,'flow_labels':labels,'sequences':[[{'id':str(s)} for s in ss] for ss in seqs]}
    solutions=[lp._solve_lp(model,kind) for kind in ('oop_guarantee','ip_ceiling')]
    policies=[]
    for p,sol in enumerate(solutions):
     realization=sol[1]
     for key in parents[p]:
      mass=realization[indexes[p][parents[p][key]]];probs=[realization[indexes[p][child]]/mass if mass else Q(1,len(children[p][key])) for child in children[p][key]]
      assert sum(probs)==1
      policies.append({'player':p,'type':key[0],'history':key[1],'actions':menus[p][key],'probabilities':list(map(str,probs))})
    values=[sol[2][0] for sol in solutions]
    x,y=solutions[0][1],solutions[1][1]
    matrix_value=sum((x[i]*A[i][j]*y[j] for i in range(nx) for j in range(ny)),Q(0))
    if values[0]!=values[1] or matrix_value!=values[0]:raise ValueError('Candidate primal/dual values disagree')
    for p,(start,size) in enumerate(((0,me),(me,mf))):
        for r,row in enumerate(flows[start:start+size]):
            observed=sum((a*b for a,b in zip(row,solutions[p][1])),Q(0))
            if observed!=Q(1 if r==0 else 0):raise ValueError('Candidate realization flow failed')
    if any(v<0 for sol in solutions for v in (*sol[1],*sol[3])):
        raise ValueError('Candidate realization or dual slack is negative')
    if (sum((a*b for a,b in zip(x,solutions[1][3])),Q(0))!=0
            or sum((a*b for a,b in zip(y,solutions[0][3])),Q(0))!=0):
        raise ValueError('Candidate complementary slackness failed')
    physical_policies=[]
    for p in (0,1):
     for hand in table.hands[p]:
      text=''.join(hand);ranktype=hand[0][0]*2
      for row in policies:
       if row['player']==p and row['type']==ranktype:
        physical_policies.append({'player':p,'hand':text,'history':list(row['history']),
                                  'actions':list(row['actions']),'probabilities':row['probabilities']})
    if len(physical_policies)!=72:raise ValueError('Lifted own-hand policy census changed')
    report={'schema_version':1,'certificate_id':spec['certificate_id'],'status':'candidate-only',
            'spec_sha256':SPEC_SHA,'physical_game_spec_sha256':spec['physical_game_spec_sha256'],
            'value_candidate_fraction':str(values[0]),'policies':physical_policies,
            'candidate_rank_mean_fractions':{r:str(x) for r,x in means.items()},'numeric_rule_census':census,
            'source_reference':sources,'candidate_lp_shapes':shapes,'rank_type_policies':policies,
            'candidate_reduced_model':{'sequences':model['sequences'],'flow_labels':labels,'flows':flows,'payoff_matrix':A},
            'candidate_primal_dual_observations':[{'lp':sol[0],'realization':sol[1],'dual':sol[2],'slacks':sol[3]} for sol in solutions]}
    report=_jsonable(report);report['artifact_sha256']=checksum(report)
    return report
