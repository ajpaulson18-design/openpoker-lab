"""Independent saved-only active-frame review. Never invokes a producer.

Raw/Git source, 198-header build, prior failure, continuation and archive are
authenticated before importing current independent replay/certificate modules.
The public DAG census/orbit/FRAME checks below use only this file's parser.
"""
import argparse
import base64
from collections import Counter, deque
from contextlib import ExitStack
import hashlib
from itertools import combinations, permutations
import json
import math
from pathlib import Path, PurePosixPath
import re
import statistics
import struct
import sys
import types
from unittest.mock import patch
import zipfile

COMMIT = None
AUTH = '8171ead3ba108f8200f15e85696f40d109ed894209fa7d77598780b83c1401c5'
CONTINUATION = 'd32352f9efc9b6d7c9cb458a4e5a6262d77868b5e17510d24f2fd09ffac8d643'
EXE = None
BUILD = None
DECK = tuple(r+s for r in '23456789TJQKA' for s in 'cdhs')
ORDER = {c:i for i,c in enumerate(DECK)}
METRICS = ('value_sb','value_bb','sb_best_response_value','bb_best_response_value',
           'sb_gain','bb_gain','nash_conv','exploitability')
BASE = ('original-22-t10','payoff-varied-t10','blocker-18','asymmetric-weighted','mixed-stabilizer','physical-g6')
MATRIX = ('original-weighted-2x2','balanced-4x4-unit','balanced-8x8-unit','balanced-16x16-unit','asymmetric-2x16-unit')
MODES = ('board-sweep','fold-mask-classes-v1')
SCHEDULE = [(n,10,m,0) for n in BASE for m in MODES]
SCHEDULE += [('original-22-t10',10,'fold-mask-classes-v1',1),('original-22-t10',10,'board-sweep',1),
             ('original-22-t10',10,'board-sweep',2),('original-22-t10',10,'fold-mask-classes-v1',2)]
SCHEDULE += [('original-22-t10',t,m,0) for t in (40,60) for m in MODES]
SCHEDULE += [('payoff-varied-t100',100,m,0) for m in MODES]
SCHEDULE += [(n,10,m,0) for n in MATRIX[1:] for m in MODES]
SCHEDULE += [('original-22-t10',t,m,0) for t in (100,1000) for m in MODES]
DONE = ('expanded_rows','expanded_action_slots','group_size','quotient_rows','quotient_action_slots',
        'member_checks','expected_member_checks','modeled_work_upper','kernel_work_upper','retained_entries_upper',
        'maximum_numeric_workspace_slots','final_numeric_workspace_slots','rank_calls')
ROUTE = ('q_rows map_entries map_upper r_lookup_entries old_q_histories_retained q_routes q_routes_upper '
         'q_tokens q_tokens_upper roots roots_upper edges edges_upper decisions decisions_upper prefixes prefixes_upper '
         'decision_comparisons prefix_comparisons legacy_extensions legacy_rows legacy_prefixes router_work router_work_upper '
         'index_work index_work_upper index_entries index_entries_upper router_retained router_retained_upper '
         'setup_scratch_upper query_scratch_upper cursor_fields cursor_frames_upper combined_work combined_entries '
         'caller_work caller_entries old_kernel_overlap old_history_forecast final_router_entries').split()
ADMISSION = ('plan_legacy_lookup_removed plan_legacy_action_removed trainer_legacy_history_removed plan_setup_work '
             'index_setup_work router_setup_work trainer_history_retained marginal_calls_upper marginal_calls_actual '
             'marginal_reuse combined_work combined_entries').split()
FRAME = ('group_size frames image_slots header_entries workspace_entries workspace_setup_work view_fields lease_fields '
         'borrowed_entries_upper flow_per_visit flow_work_upper validation_work_upper activations activations_upper '
         'released_frames release_calls final_active_frames final_workspace_entries value_cursor_learning_calls '
         'router_owned_workspace combined_work combined_entries').split()
FOLD = ('setup_work_upper setup_entries_upper mask_entries membership_entries classes_sb classes_bb class_calls_sb class_calls_bb literal_calls_sb literal_calls_bb buckets_sb buckets_bb own_checks retained_pair_entries query_allowance_retained combined_work combined_entries').split()
RESOURCE = re.compile(r'\b(?:admission|capacity|limit|cap|forecast|budget|ceiling|preflight|envelope)\b[^\n]*\bexceeded\b'
    r'|\bexceeds?\b[^\n]*\b(?:envelope|ceiling|limit|cap|capped|slots|states|depth|decisions|rows|work)\b'
    r'|\b(?:is |are )?capped at\b|\bno retained-entry allowance remains\b'
    r'|\bindexed router whole-work limit is below its bounded schedule scan floor\b'
    r'|\bhistory-index bounded input scan exceeds remaining combined work before token scan\b',re.I)

def check(value, message):
    if not value:
        raise ValueError(message)

def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def bits(value): return struct.pack('>d',value).hex()
def label(entry): return f'{entry[0]}-t{entry[1]}-{entry[2]}-p{entry[3]}'
def write(path,value):
    with path.open('xb') as stream:
        stream.write(json.dumps(value,sort_keys=True,indent=2,allow_nan=False).encode()+b'\n')
def bounded(message):
    return type(message) is str and not re.search(r'\b(?:stale|unsupported|missing|mismatch|invalid|requires|wrong|unknown)\b|already reserved|cannot exceed',message,re.I) and RESOURCE.search(message) is not None

def inventory(root):
    check(root.is_dir() and not root.is_symlink(),'ordinary evidence directory required')
    result={}
    for path in root.rglob('*'):
        check(not path.is_symlink(),'symlink evidence rejected')
        if path.is_file():
            check(path.stat().st_size<=256*1024*1024,'individual saved artifact cap')
            result[path.relative_to(root).as_posix()]=path.read_bytes()
    check(sum(map(len,result.values()))<=1024*1024*1024,'saved inventory cap')
    return result

def manifested(root,pin,parse):
    files=inventory(root)
    check(sha(files['manifest.json'])==pin,'external manifest pin')
    manifest=parse(files['manifest.json'])
    check(manifest['version']=='native-fold-mask-classes-evidence-manifest-v1','manifest contract')
    hashes=manifest['files']
    check(set(files)==set(hashes)|{'manifest.json'},'full evidence inventory')
    for name,digest in hashes.items():
        check(str(PurePosixPath(name))==name and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,
              'noncanonical evidence path')
        check(sha(files[name])==digest,'manifest artifact '+name)
    return files

def literal_range(expression):
    rows=[];seen=set()
    for token in expression.split(','):
        match=re.fullmatch(r'([2-9TJQKA][cdhs])([2-9TJQKA][cdhs])(?::([0-9]+(?:\.[0-9]+)?))?',token)
        check(match is not None,'independent fixture literal range grammar')
        a,b,weight=match.groups();hand=''.join(sorted((a,b)))
        value=float(weight) if weight else 1.
        check(a!=b and hand not in seen and math.isfinite(value) and value>0,'independent fixture prior')
        seen.add(hand);rows.append({'hand':hand,'weight_hex':value.hex()})
    check(0<len(rows)<=16,'independent structural replay holding cap')
    return rows

def cases_from_data(repo,parse):
    original=dict(parse((repo/'benchmarks/four-street-integration-v1.json').read_bytes())['case'],id='original-22-exact-product-study')
    def small(identifier,sb,bb):
        street={'bet_sizes':[.5],'raise_sizes':[],'max_raises':0,'include_all_in':False}
        return dict(id=identifier,sb_range=sb,bb_range=bb,
            config={'starting_stack':[2,2],'small_blind':.5,'big_blind':1,'raise_sizes':[.5],'max_raises':1,'include_all_in':False},
            runouts=['2c3c4h5s6h','2d3d4h5s6h'],flop_config=dict(street),turn_config=dict(street),river_config=dict(street))
    result={'original-22-t10':original,'original-weighted-2x2':dict(original),
        'blocker-18':small('blocker-conditioned-18-worlds-v1','AcAh,AdAh,2cAh,2dAh','KcKh,KdKh,3cKh,3dKh'),
        'asymmetric-weighted':small('weighted-asymmetric-suit-exchange-v1','AcAh:0.7,AdAh:0.3','KcKh:0.4,KdKh:0.6'),
        'mixed-stabilizer':small('mixed-suit-stabilizer-v1','AcAd','KcKd')}
    payoff=small('payoff-varied-private-flush-v1','AcQc,AdQd','KcJc,KdJd');payoff['runouts']=['2c3c7c9hTs','2d3d7d9hTs']
    result.update({'payoff-varied-t10':payoff,'payoff-varied-t100':dict(payoff),
        'physical-g6':dict(original,id='active-frame-physical-s3-v1',sb_range='AdAh,AdAs,AhAs',bb_range='KdKh,KdKs,KhKs',runouts=['2c3c4c7c8c'])})
    for name in MATRIX[1:]:
        counts=(2,16) if name==MATRIX[-1] else (int(name.split('-')[1].split('x')[0]),)*2
        case=dict(original,id='canonical-distinct-unit-'+name)
        for key,pool,count in zip(('sb_range','bb_range'),(('Ad','As','Qd','Qs','Ac','Ah','9c','9d'),('Kd','Ks','Jd','Jh','Qc','Qh','8d','8s')),counts):
            values=[]
            candidates=[tuple(t.split(':')[0][i:i+2] for i in (0,2)) for t in original[key].split(',')]+list(combinations(sorted(pool,key=ORDER.__getitem__),2))
            for pair in candidates:
                value=''.join(sorted(pair,key=ORDER.__getitem__))
                if value not in values and len(values)<count: values.append(value)
            check(len(values)==count,'canonical synthetic hand count')
            case[key]=','.join(values)
        result[name]=case
    return result

def board_inputs(case):
    result=[]
    for token in case['runouts']:
        check(len(token)==10,'fixed full selected board')
        cards=tuple(token[i:i+2] for i in range(0,10,2))
        check(all(c in ORDER for c in cards) and len(set(cards))==5,'fixed distinct selected cards')
        result.append(tuple(sorted(cards[:3],key=ORDER.__getitem__))+cards[3:])
    check(len(set(result))==len(result),'duplicate selected board')
    return sorted(result,key=lambda row:tuple(ORDER[c] for c in row))

def suit_group(wire):
    seats=[{(tuple(sorted(row['hand'])),row['weight_bits']) for row in side} for side in wire['ranges']]
    boards=set(map(tuple,wire['boards']));result=[]
    for image in permutations('cdhs'):
        def card(c):return c[0]+image['cdhs'.index(c[1])]
        if any({(tuple(sorted(map(card,pair))),weight) for pair,weight in side}!=side for side in seats):continue
        mapped=set()
        for board in boards:
            row=tuple(map(card,board));mapped.add(tuple(sorted(row[:3],key=ORDER.__getitem__))+row[3:])
        if mapped==boards:result.append(image)
    check(tuple('cdhs') in result,'suit identity absent')
    return result

def visible(history):
    result=[]
    for token in history:
        if token.startswith('flop@'):
            check(not result and len(token)==11,'invalid flop history');result.extend(token[i:i+2] for i in (5,7,9))
        elif token.startswith('turn@'):
            check(len(result)==3 and len(token)==7,'invalid turn history');result.append(token[5:])
        elif token.startswith('river@'):
            check(len(result)==4 and len(token)==8,'invalid river history');result.append(token[6:])
    check(all(c in ORDER for c in result) and len(set(result))==len(result),'invalid revealed cards')
    return tuple(result)

def transformed(history,image):
    def card(c):return c[0]+image['cdhs'.index(c[1])]
    result=[]
    for token in history:
        if token.startswith('flop@'):result.append('flop@'+''.join(sorted((card(token[i:i+2]) for i in (5,7,9)),key=ORDER.__getitem__)))
        elif token.startswith('turn@'):result.append('turn@'+card(token[5:]))
        elif token.startswith('river@'):result.append('river@'+card(token[6:]))
        else:result.append(token)
    return tuple(result)

def graph_census(wire,payload):
    """Bounded literal full-history walk; verifier-only rows, no producer graph APIs."""
    initial=tuple(wire['initial_history']);stack=[(wire['root'],initial)]
    visits=decisions=terminals=dh=actions=he=rb=depth=0;ht=len(initial)
    initial_bytes=sum(map(len,initial));hb=initial_bytes;transition_tokens=transition_bytes=0
    rows={};all_prefixes=set();marginals=set();supported={};decision_histories=set()
    while stack:
        node,history=stack.pop();v=wire['vertices'][node];visits+=1
        check(visits<=250000 and len(history)-len(initial)<=64,'independent occurrence/depth cap')
        ht+=len(history);hb+=sum(map(len,history));depth=max(depth,len(history)-len(initial))
        check(ht<=16000000 and hb<=16000000,'independent history budget')
        prefix=visible(history);indexes=tuple(i for i,b in enumerate(wire['boards']) if tuple(b[:len(prefix)])==prefix)
        check(indexes,'revealed prefix absent selected boards');all_prefixes.add(prefix)
        if prefix not in supported:
            sides=[set(),set()]
            for i,a in enumerate(wire['ranges'][0]):
                for j,b in enumerate(wire['ranges'][1]):
                    private=a['hand']+b['hand']
                    if len(set(private))==4 and any(not set(private).intersection(wire['boards'][k]) for k in indexes):
                        sides[0].add(i);sides[1].add(j)
            supported[prefix]=sides
        if v['kind']=='D':
            check(history not in decision_histories,'duplicate semantic decision history');decision_histories.add(history)
            decisions+=1;actor=v['actor'];a=len(v['actions']);dh+=len(wire['ranges'][actor]);actions+=a
            he+=len(history)+a;rb+=sum(map(len,history))+64*a;marginals.add(indexes)
            for h in supported[prefix][actor]:
                key=(actor,h,history);check(key not in rows and len(rows)<2000000,'independent R-row cap/identity');rows[key]=v['actions']
            edges=[(act['token'],child) for act,child in zip(v['actions'],v['children'])]
        elif v['kind']=='C':edges=[(('flop@','turn@','river@')[v['street']-1]+s,child) for s,child in v['branches']]
        else:terminals+=1;edges=[]
        transition_tokens+=len(edges);transition_bytes+=sum(len(t) for t,_ in edges)
        stack.extend((child,history+(token,)) for token,child in edges)
        check(len(stack)<=250000 and len(all_prefixes)<=2000000 and rb<=16000000,'structural verifier storage budget')
    direct=payload['operator_census']['direct_topology']
    for key,value in dict(expanded_logical_visits=visits,decision_occurrences=decisions,terminal_occurrences=terminals,maximum_depth=depth,
            logical_history_token_work=ht-len(initial)+transition_tokens,logical_history_token_bytes=hb-initial_bytes+transition_bytes).items():
        check(direct[key]==value,'independent graph census '+key)
    group=suit_group(wire);G=len(group);T=wire['iterations']
    lookup=G*(128*ht+256*dh);one=G*(16*he+4*rb+8*(depth+1)*dh+16*(depth+1)*visits)
    handmaps=[{tuple(sorted(r['hand'])):i for i,r in enumerate(side)} for side in wire['ranges']]
    orbits={};q_tokens=0
    for key,menu in rows.items():
        actor,h,history=key;members=set()
        for image in group:
            mappedhand=tuple(sorted(c[0]+image['cdhs'.index(c[1])] for c in wire['ranges'][actor][h]['hand']))
            k=(actor,handmaps[actor][mappedhand],transformed(history,image))
            check(k in rows and rows[k]==menu,'suit image lacks exact ordered row/menu closure');members.add(k)
        canonical_key=min(members)
        if canonical_key not in orbits:orbits[canonical_key]=len(menu);q_tokens+=len(canonical_key[2])
    return dict(visits=visits,decisions=decisions,terminals=terminals,depth=depth,group_size=G,expanded_rows=len(rows),
        expanded_action_slots=sum(map(len,rows.values())),quotient_rows=len(orbits),quotient_action_slots=sum(orbits.values()),q_tokens=q_tokens,
        rows=rows,amounts=dict(plan_legacy_lookup_removed=3*T*lookup,plan_legacy_action_removed=6*T*32*actions,
        trainer_legacy_history_removed=3*T*one,trainer_history_retained=4*one),marginal_calls_upper=len(all_prefixes),marginal_calls_actual=len(marginals))

def proof_record(line,tag,mode,names):
    cells=line.split('\t');check(cells[:2]==[tag,mode] and len(cells)==len(names)+2,'raw '+tag+' shape')
    result={}
    for cell in cells[2:]:
        key,sep,value=cell.partition('=')
        check(sep and key not in result and value.isascii() and value.isdecimal() and len(value)<=20,'invalid raw proof integer')
        result[key]=int(value)
    check(set(result)==set(names),'raw '+tag+' field closure')
    return result

def independent_fold_census(wire,T):
    """Count legal board masks and every literal public fold occurrence."""
    masks=[]
    for side in wire['ranges']:
        masks.append([sum(1<<k for k,board in enumerate(wire['boards']) if not set(row['hand']).intersection(board)) for row in side])
    C=[len(set(side)) for side in masks];H=[len(side) for side in masks];B=len(wire['boards'])
    stack=[(wire['root'],tuple(wire['initial_history']))];folds=0;class_occ=[0,0];visits=0;literal_allowance=0
    while stack:
        node,history=stack.pop();visits+=1;check(visits<=250000,'fold occurrence cap');v=wire['vertices'][node]
        if v['kind']=='F':
            folds+=1;prefix=visible(history);selected=sum(tuple(board[:len(prefix)])==prefix for board in wire['boards'])
            for player in (0,1):
                own,opp=H[player],H[1-player]
                class_work=C[1-player]*(64*own+256)+64*opp+8*selected+128
                literal=selected*(48*sum(H)+512)
                literal_allowance+=literal+8*opp+4*own+64
                if class_work<=literal:class_occ[player]+=1
        if v['kind']=='D':edges=[(act['token'],child) for act,child in zip(v['actions'],v['children'])]
        elif v['kind']=='C':edges=[(('flop@','turn@','river@')[v['street']-1]+label,child) for label,child in v['branches']]
        else:edges=[]
        stack.extend((child,history+(token,)) for token,child in edges)
    return dict(setup_work_upper=2048*sum(H)+8*B*sum(H)+65536,setup_entries_upper=10*sum(H)+128,
                mask_entries=sum(H),membership_entries=sum(H),classes_sb=C[0],classes_bb=C[1],
                class_calls_sb=T*class_occ[0],class_calls_bb=T*class_occ[1],
                literal_calls_sb=T*(folds-class_occ[0]),literal_calls_bb=T*(folds-class_occ[1]),literal_fold_work_minimum=T*literal_allowance)

def validate_completed(raw,entry,case):
    name,T,mode,sample=entry;x=raw['payload'];nc=x['operator_census']['native_exact']
    encoded=canonical(x)
    check((sha(encoded),len(encoded))==(raw['payload_sha256'],raw['payload_bytes']),'complete payload hash/length')
    expected_backend=('native-exact-four-street-fold-classes-v5' if mode=='fold-mask-classes-v1' else 'native-exact-four-street-active-frames-v4')
    check(x.get('training_backend')==expected_backend and x.get('native_traversal')=='active-frames' and x.get('native_routing')=='indexed' and x.get('native_admission')=='indexed-v1','exact V4/V5 schema')
    check((x.get('native_payoffs')==mode) if mode=='fold-mask-classes-v1' else ('native_payoffs' not in x),'exact payoff selector')
    for key,value in (('chance_contract','exact-product-selected-v1'),('conversion_contract','exact-product-vectors-binary64-v1'),
            ('training_reduction','suit-equivariant-sorted-chance-binary64-v1'),('pair_diagnostics','compact-exact-product-inputs-v1')):
        check(x.get(key)==value,'complete contract '+key)
    check('private_pair_probabilities' not in x and 'compatible_private_pairs' not in x,'unexpected production pair rows')
    check(all(type(x.get(k)) in (float,int) and math.isfinite(x[k]) for k in METRICS),'all eight finite metrics')
    check(x['operator_census']['stored_complete_worlds']==x['operator_census']['stored_prefix_pair_edges']==0,'production world/pair storage')
    stream=raw['native_streams'][0]
    check(set(stream)=={'request','stdout','stderr','returncode'} and stream['returncode']==0,'native stream closure')
    request,output,error=(base64.b64decode(stream[k],validate=True) for k in ('request','stdout','stderr'))
    check(not error and (sha(request),sha(output),len(request),len(output))==
          (nc['request_sha256'],nc['result_sha256'],nc['request_bytes'],nc['result_bytes']),'native streams/payload binding')
    wire=parse_wire(request,mode);check(wire['iterations']==T and wire['rank_cache_boards']==64,'wire schedule/cache')
    expected_ranges=[literal_range(case[key]) for key in ('sb_range','bb_range')]
    check(x['chance_input_snapshot']=={'contract':'exact-product-selected-v1','ranges':expected_ranges},'compact exact fixture snapshot')
    for side,expected in zip(wire['ranges'],expected_ranges):
        check([{'hand':''.join(sorted(row['hand'])),'weight_hex':struct.unpack('>d',bytes.fromhex(row['weight_bits']))[0].hex()}
               for row in side]==expected,'original wire range index/prior bits')
    check([tuple(b) for b in wire['boards']]==board_inputs(case) and x['selected_runouts']==[list(b) for b in board_inputs(case)],'original selected ordered boards')
    census=graph_census(wire,x);lines=output.decode('ascii').splitlines()
    expected_magic='OPENPOKER_NATIVE_EXACT_FOUR_STREET_'+('FOLD_CLASSES_RESULT_V5' if mode=='fold-mask-classes-v1' else 'ACTIVE_FRAMES_RESULT_V4')
    check(lines[0]==expected_magic,'native result protocol')
    records={};rawrows=[];phase=0
    for line in lines[1:]:
        cells=line.split('\t');tag=cells[0]
        if tag=='ROW':check(phase==0,'ROW after proof');rawrows.append(cells)
        else:
            expected_tags=('DONE','ROUTE','ADMISSION','FRAME','FOLD') if mode=='fold-mask-classes-v1' else ('DONE','ROUTE','ADMISSION','FRAME')
            check(phase<len(expected_tags) and tag==expected_tags[phase],'unknown/duplicate/out-of-order result record')
            records[tag]=line;phase+=1
    check(phase==(5 if mode=='fold-mask-classes-v1' else 4),'missing proof record')
    cells=records['DONE'].split('\t');check(len(cells)==14 and all(v.isascii() and v.isdecimal() and len(v)<=20 for v in cells[1:]),'DONE13 shape')
    done=dict(zip(DONE,map(int,cells[1:])));check(all(nc[k]==v for k,v in done.items()),'DONE/payload equality')
    route=proof_record(records['ROUTE'],'ROUTE','indexed',ROUTE);admission=proof_record(records['ADMISSION'],'ADMISSION','indexed-v1',ADMISSION)
    check(nc['indexed_routing']==dict(route,mode='indexed') and nc['indexed_admission']==dict(admission,mode='indexed-v1'),'raw route/admission receipt binding')
    for k in ('expanded_rows','expanded_action_slots','group_size','quotient_rows','quotient_action_slots'):
        check(done[k]==census[k],'independent row/orbit census '+k)
    check(done['expanded_rows']==x['info_sets'] and done['member_checks']==done['expected_member_checks']==2*T*x['info_sets'] and
          done['maximum_numeric_workspace_slots']==4*done['quotient_action_slots'] and done['final_numeric_workspace_slots']==0 and done['rank_calls']>0,'member/workspace guards')
    check(raw['counts']['python_rank']==done['rank_calls'] and raw['native_observations']=={'learning_completed':True,'rank_calls':done['rank_calls']},'observed completed ranks')
    payloadrows={}
    for row in x['strategy']:
        actor={'sb':0,'bb':1}[row['player']];handidx=[r['hand'] for r in expected_ranges[actor]].index(row['hand']);history=tuple(row['history']);key=(actor,handidx,history)
        check(key not in payloadrows and key in census['rows'],'complete supported semantic row identity')
        menu=census['rows'][key];check(len(row['actions'])==len(menu),'ordered action count')
        check(row['revealed_board']==list(visible(history)) and row['street']==('preflop' if len(visible(history))==0 else {3:'flop',4:'turn',5:'river'}[len(visible(history))]),'row visible scope')
        for a,b in zip(row['actions'],menu):
            check(a['name']==b['name'] and a['history_key']==b['token'] and bits(a['amount'])==b['amount_bits'] and bits(a['raise_to'])==b['raise_to_bits'] and
                  type(a['probability']) in (int,float) and math.isfinite(a['probability']) and 0<=a['probability']<=1,'full ordered action/menu bits')
        payloadrows[key]=row
    check(set(payloadrows)==set(census['rows']) and len(rawrows)==len(payloadrows),'all supported rows present')
    seen=set()
    for cells in rawrows:
        check(len(cells)>=6 and all(s.isdecimal() and len(s)<=12 for s in cells[1:4]),'ROW scalar shape')
        actor,h,n=map(int,cells[1:4]);check(n<=64 and len(cells)>4+n,'ROW history bound');history=tuple(cells[4:4+n]);count=int(cells[4+n]);key=(actor,h,history)
        check(key in payloadrows and key not in seen and len(cells)==5+n+count and cells[5+n:]==[bits(a['probability']) for a in payloadrows[key]['actions']],'every raw policy bit')
        seen.add(key)
    check(seen==set(payloadrows),'native ROW completeness')
    for k,v in dict(roots=3*T,edges=3*T*(census['visits']-1),decisions=3*T*census['decisions'],prefixes=T*(2*census['terminals']+census['decisions'])).items():
        check(route[k]==route[k+'_upper']==v,'independent schedule '+k)
    check(route['q_rows']==route['map_entries']==route['map_upper']==route['q_routes']==route['q_routes_upper']==census['quotient_rows'] and
          route['q_tokens']==route['q_tokens_upper']==census['q_tokens'],'Q construction history/token identity')
    check(all(route[k]==0 for k in ('r_lookup_entries','decision_comparisons','prefix_comparisons','legacy_extensions','legacy_rows','legacy_prefixes','final_router_entries')) and
          route['old_q_histories_retained']==1 and route['cursor_fields']==3,'indexed scope/cursor lifetime')
    check(all(type(route[k]) is int and 0<=route[k]<=route[k+'_upper'] for k in ('router_work','index_work','index_entries','router_retained')),'route bounds')
    check(all(admission[k]==v for k,v in census['amounts'].items()) and admission['marginal_calls_upper']==census['marginal_calls_upper'] and
          admission['marginal_calls_actual']==census['marginal_calls_actual'] and admission['marginal_reuse']==1 and
          route['old_history_forecast']==census['amounts']['trainer_history_retained'],'independent indexed removals/marginal reuse')
    combined=admission['plan_setup_work']+admission['index_setup_work']+admission['router_setup_work']+route['router_work_upper']+route['index_work_upper']+route['caller_work']
    check(combined==admission['combined_work']==route['combined_work']==done['modeled_work_upper']<=500000000 and
          admission['combined_entries']==route['combined_entries']==done['retained_entries_upper']<=2000000,'shared native whole ledger')
    res=x['operator_census']['whole_request_admission']['native_additional_admission']
    check(wire['limits'][4]==wire['limits'][7]==res['native_work_limit'] and wire['limits'][5]==wire['limits'][8]==res['native_entries_limit'] and
          combined<=res['native_work_limit'] and done['retained_entries_upper']<=res['native_entries_limit'] and done['kernel_work_upper']<=wire['limits'][1],'host remaining capacity')
    if True:
        frame=proof_record(records['FRAME'],'FRAME','active-v1',FRAME);check(nc['active_frames']==dict(frame,mode='active-v1'),'raw FRAME binding')
        D=census['depth'];G=census['group_size'];H=max(map(len,wire['ranges']));active=3*T*census['visits'];workspace=64+(D+1)*(3+8*G);borrowed=4*(D+4)*6
        expected=dict(group_size=G,frames=D+1,image_slots=(D+1)*G,header_entries=3*(D+1),workspace_entries=workspace,workspace_setup_work=workspace,
            view_fields=3,lease_fields=3,borrowed_entries_upper=borrowed,flow_per_visit=88+8*G,flow_work_upper=workspace+active*(88+8*G),
            validation_work_upper=32*(1+G+H*(1+G))*route['decisions']+64*route['prefixes'],activations=active,activations_upper=active,
            released_frames=active,release_calls=active,final_active_frames=0,final_workspace_entries=0,value_cursor_learning_calls=0,router_owned_workspace=1,
            combined_work=combined,combined_entries=done['retained_entries_upper'])
        check(frame==expected,'independent full FRAME22 algebra')
        check(route['cursor_frames_upper']==workspace+borrowed and route['caller_entries']>=workspace+borrowed and
              route['caller_work']>=frame['flow_work_upper'] and route['router_work_upper']>=frame['validation_work_upper'],'FRAME correct owner component accounting')
    if mode=='fold-mask-classes-v1':
        fold=proof_record(records['FOLD'],'FOLD','mask-classes-v1',FOLD)
        check(list(fold)==FOLD and nc['fold_classes']==dict(fold,mode='mask-classes-v1'),'ordered raw FOLD binding')
        expected=independent_fold_census(wire,T)
        for key,value in expected.items():
            if key!='literal_fold_work_minimum':check(fold[key]==value,'independent fold census '+key)
        check(done['kernel_work_upper']>=expected['literal_fold_work_minimum'],'old fold-query allowance retained')
        h0,h1=map(len,wire['ranges'])
        check(fold['buckets_sb']<=fold['class_calls_sb']*fold['classes_bb'] and fold['buckets_bb']<=fold['class_calls_bb']*fold['classes_sb'] and
              fold['own_checks']==fold['buckets_sb']*h0+fold['buckets_bb']*h1 and fold['retained_pair_entries']==0 and fold['query_allowance_retained']==1 and
              fold['combined_work']==combined and fold['combined_entries']==done['retained_entries_upper'] and
              admission['plan_setup_work']>=fold['setup_work_upper'] and admission['combined_entries']>=fold['setup_entries_upper'],'fold bucket/setup/whole ledger')
    else:check('fold_classes' not in nc,'V4 unexpectedly has fold proof')
    if name=='physical-g6':check(census['group_size']==6 and census['quotient_rows']<census['expanded_rows'],'noncommuting G6 fixture')
    return {k:v for k,v in census.items() if k!='rows'}


def parse_wire(raw, traversal):
    check(type(raw) is bytes and len(raw)<=64*1024*1024 and raw.endswith(b"\n"),"invalid native input envelope")
    tokens=raw.decode("ascii").split();check(len(tokens)<=10000000,"native input token cap")
    pos=0
    def take():
        nonlocal pos
        check(pos<len(tokens),"truncated native input")
        text=tokens[pos];pos+=1
        check(0<len(text)<=64 and all(32<ord(c)<127 for c in text),"invalid native token")
        return text
    def nat(ceiling):
        text=take();check(text.isdecimal() and len(text)<=12,"invalid natural field")
        value=int(text);check(value<=ceiling,"native natural exceeds independent cap");return value
    def fp():
        text=take();check(len(text)==16 and all(c in "0123456789abcdef" for c in text),"invalid exact FP bits")
        value=struct.unpack(">d",bytes.fromhex(text))[0];check(math.isfinite(value),"nonfinite native money/prior")
        return text
    check(take()==("OPENPOKER_NATIVE_EXACT_FOUR_STREET_FOLD_CLASSES_V5" if traversal=="fold-mask-classes-v1" else "OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_V4"),"wrong input magic")
    iterations=nat(10000);cache=nat(64);h0,h1=nat(16),nat(16);b=nat(64);n=nat(250000);e=nat(1000000);root=nat(max(n-1,0));initial_n=nat(64)
    check(iterations>=10 and cache and h0 and h1 and b and n,"unsupported fixed input dimensions")
    caps=(65536,500000000,2000000,1<<30,500000000,2000000,16000000,500000000,2000000,1000000,2000000)
    limits=[nat(cap) for cap in caps];check(all(limits),"zero native limit")
    ranges=[]
    for h in (h0,h1):
        side=[]
        for _ in range(h):
            a,c=nat(51),nat(51);weight=fp();check(a!=c and struct.unpack(">d",bytes.fromhex(weight))[0]>0,"invalid positive holding")
            side.append({"hand":[DECK[a],DECK[c]],"weight_bits":weight})
        check(len({tuple(sorted(row["hand"])) for row in side})==h,"duplicate private holding")
        ranges.append(side)
    boards=[[DECK[nat(51)] for _ in range(5)] for _ in range(b)]
    check(all(len(set(outcome))==5 and outcome[:3]==sorted(outcome[:3],key=ORDER.__getitem__) for outcome in boards) and
         boards==sorted(boards,key=lambda outcome:tuple(ORDER[c] for c in outcome)) and len({tuple(v) for v in boards})==b,"noncanonical or duplicate native selected boards")
    initial=[take() for _ in range(initial_n)];vertices=[];edges=0
    for _ in range(n):
        tag=take()
        if tag=="D":
            actor=nat(1);count=nat(32);check(count>0,"empty action menu");actions=[];children=[]
            for _ in range(count):
                action={"name":take(),"amount_bits":fp(),"raise_to_bits":fp(),"full_raise":bool(nat(1)),"token":take()}
                actions.append(action);children.append(nat(n-1))
            check(len({a["token"] for a in actions})==count,"duplicate native action tokens")
            vertices.append({"kind":"D","actor":actor,"actions":actions,"children":children});edges+=count
        elif tag=="C":
            street=nat(3);index=nat(6);count=nat(64);check(street and count and index==street+3,"wrong native reveal index/street")
            branches=[(take(),nat(n-1)) for _ in range(count)];check(len({v[0] for v in branches})==count,"duplicate chance labels")
            vertices.append({"kind":"C","street":street,"card_index":index,"branches":branches});edges+=count
        elif tag in ("F","S"):
            winner=nat(1) if tag=="F" else None
            contributions=[fp(),fp()];check(all(struct.unpack(">d",bytes.fromhex(value))[0]>=0 for value in contributions),"negative terminal money")
            vertices.append({"kind":tag,"winner":winner,"contribution_bits":contributions})
        else:raise ValueError("unknown native wire field/vertex tag")
    check(pos==len(tokens) and edges==e,"unknown trailing native fields or edge mismatch")
    def children(v):return v["children"] if v["kind"]=="D" else [child for _,child in v["branches"]] if v["kind"]=="C" else []
    degrees=[0]*n
    for vertex in vertices:
        for child in children(vertex):degrees[child]+=1
    queue=deque(i for i,d in enumerate(degrees) if d==0);order=[]
    while queue:
        i=queue.popleft();order.append(i)
        for child in children(vertices[i]):
            degrees[child]-=1
            if degrees[child]==0:queue.append(child)
    check(len(order)==n,"native graph cycle")
    reached={root};depth={root:0}
    for i in order:
        check(i in reached,"native graph unreachable vertex")
        for child in children(vertices[i]):
            reached.add(child);depth[child]=max(depth.get(child,0),depth[i]+1)
            check(depth[child]<=64,"independent numeric graph depth cap")
    return {"iterations":iterations,"rank_cache_boards":cache,"ranges":ranges,"boards":boards,"vertices":vertices,
        "root":root,"initial_history":initial,"edges":edges,"limits":limits,"maximum_depth":max(depth.values())}


def build_identity(repo,build,parse):
    exe=Path(build['executable']);manifest=exe.parent/'native-exact-build-manifest.json'
    raw=manifest.read_bytes();bm=parse(raw)
    check(sha(raw)==build['manifest_sha256']==BUILD and sha(exe.read_bytes())==build['executable_sha256']==EXE,'externally pinned engine/build bytes')
    names={'native/exact_four_street_train.cpp','native/exact_public_graph.hpp','native/exact_public_history_index.hpp',
        'native/exact_indexed_routing.hpp','native/exact_selected_cfr.hpp','native/exact_selected_kernel.hpp','native/exact_binary64.hpp',
        'scripts/build_native_exact_four_street.py','third_party/boost-multiprecision-1.92.0/manifest.json',
        'third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt','third_party/boost-multiprecision-1.92.0/headers.zip'}
    check(set(build['source_sha256'])==names and bm['source_sha256']==build['source_sha256'] and bm['executable_sha256']==EXE and
          all(sha((repo/k).read_bytes())==v for k,v in build['source_sha256'].items()),'complete build source closure')
    check('/fp:strict' in build['flags'] and '/O2' in build['flags'] and '/W4' in build['flags'] and '/WX' in build['flags'] and
          '/DBOOST_MP_STANDALONE' in build['flags'] and bm['flags']==build['flags'],'strict frozen build flags')
    depdir=repo/'third_party/boost-multiprecision-1.92.0'
    expected={'manifest.json':'4d6f33341887e35a0c29e9dc5da2a326d546427940c2b16b485db0c61b042555',
        'headers.zip':'33c422ab3ebfa9e86c62f41f372ec2b9c2cefa303f1885391aa4d8250ef2f831',
        'LICENSE_1_0.txt':'c9bff75738922193e67fa726fa225535870d2aa1059f91452c411736284ad566'}
    check(all(sha((depdir/k).read_bytes())==v for k,v in expected.items()),'pinned dependency artifacts')
    dep=parse((depdir/'manifest.json').read_bytes())
    with zipfile.ZipFile(depdir/'headers.zip') as z:
        entries=[i for i in z.infolist() if not i.is_dir()]
        check(len(entries)==198 and len({i.filename for i in entries})==198,'198 unique packaged headers')
        headers={i.filename:sha(z.read(i)) for i in entries}
    check(headers==dep['headers_sha256'] and len(headers)==dep['header_count']==198,'packaged header pins')
    actual=inventory(exe.parent/'boost-include')
    check({k:sha(v) for k,v in actual.items()}==headers,'actual compiled include header closure')
    return {'manifest':sha(raw),'executable':sha(exe.read_bytes()),'headers':headers,'sources':build['source_sha256']}

def capture_check(files,identifier,raw,parse):
    check(files[identifier+'.raw.json']==files[identifier+'.stdout.bin'],'retained JSON is exact original stdout')
    status=parse(files[identifier+'-process-status.json'])
    check(status==dict(returncode=0,stdout_sha256=sha(files[identifier+'.stdout.bin']),stderr_sha256=sha(files[identifier+'.stderr.bin'])),'raw process-status binding')
    for index,stream in enumerate(raw['native_streams']):
        prefix=f'{identifier}-native-{index}'
        for kind in ('request','stdout','stderr'):
            check(files[prefix+'-'+kind+'.bin']==base64.b64decode(stream[kind],validate=True),'decoded native artifact original bytes')
        expected={'returncode':stream['returncode'],**{kind+'_sha256':sha(base64.b64decode(stream[kind],validate=True)) for kind in ('request','stdout','stderr')}}
        check(parse(files[prefix+'-status.json'])==expected,'native status capture binding')

def inspect_child(raw,entry,case,runtime):
    name,T,mode,sample=entry
    check((raw['case'],raw['iterations'],raw['native_payoffs'],raw['native_traversal'],raw['sample'],raw['routing'],raw['native_admission'],raw['traced'])==
          (name,T,mode,'active-frames',sample,'indexed','indexed-v1',False) and raw['request_case']==case and raw['runtime']==runtime,'fixed child identity/runtime/case')
    check(not raw.get('source_build_guard_failure'),'child source/build failure')
    check(type(raw['seconds']) in (float,int) and math.isfinite(raw['seconds']) and raw['seconds']>0 and
          raw['python_allocation_peak_bytes'] is None and type(raw['process_peak_bytes']) is int and raw['process_peak_bytes']>0,'timing/allocation metadata')
    calls=raw['counts'];names={'python_trainer','native_invoke','python_rank','rank_before_native','pair','world','legacy'}
    check(set(calls)==names and all(type(calls[k]) is int and calls[k]>=0 for k in names-{'rank_before_native'}) and
          (calls['rank_before_native'] is None or type(calls['rank_before_native']) is int and calls['rank_before_native']==0),'call counter types')
    check(not any(calls[k] for k in ('python_trainer','pair','world','legacy')) and len(raw['native_streams'])==calls['native_invoke']<=1,'forbidden producer paths')
    status=raw['status'];check(status in ('complete','host-admission-rejected','native-resource-rejected'),'unexpected child status')
    if status=='complete':
        check(raw['failure'] is None and type(raw['payload']) is dict and calls['native_invoke']==1 and calls['rank_before_native']==0,'completion evidence')
        return validate_completed(raw,entry,case)
    check((name,T) not in {(n,10) for n in BASE}|{('payoff-varied-t100',100)},'required complete control rejected')
    check(raw['payload'] is None and type(raw['failure']) is dict and bounded(raw['failure']['message']) and calls['python_rank']==0,'bounded rejection with no contradictory payload')
    if status=='host-admission-rejected':
        check(raw['failure']['type']=='ValueError' and calls['native_invoke']==0 and not raw['native_streams'] and
              raw['native_observations']=={'learning_completed':False,'rank_calls':0},'host rejection observation')
    else:
        check(raw['failure']['type']=='NativeFailure' and calls['native_invoke']==1 and calls['rank_before_native']==0 and
              raw['native_observations']=={'learning_completed':None,'rank_calls':None},'native rejected internals remain unknown')
        stream=raw['native_streams'][0];error=base64.b64decode(stream['stderr'],validate=True).decode('utf-8','strict')
        check(stream['returncode']==2 and not base64.b64decode(stream['stdout'],validate=True) and
              error.startswith('native exact four-street rejected:') and bounded(error),'specific native budget exit')
        parse_wire(base64.b64decode(stream['request'],validate=True),mode)
    return None

FORBIDDEN = (
    'pokerlab.exact_selected_solver.solve_four_street_exact_selected',
    'pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.__init__',
    'pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.terminal_values_exact',
    'pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.joint_marginals_exact',
    'pokerlab.exact_selected_kernel.ExactSelectedRunoutKernel.pair_probability_exact',
    'pokerlab.exact_selected_kernel.rank_hand','pokerlab.cards.rank_hand',
    'pokerlab.dyadic_selected_arithmetic.DyadicSelectedArithmeticPlan.__init__',
    'pokerlab.dyadic_selected_arithmetic.DyadicSelectedArithmeticPlan.marginals',
    'pokerlab.dyadic_selected_arithmetic.DyadicSelectedArithmeticPlan.terminal',
    'pokerlab.suit_quotient_plan.SuitQuotientPlan.__init__','pokerlab.suit_quotient_cfr.train_suit_quotient',
    'pokerlab.equivariant_packed_cfr.train_equivariant_packed','pokerlab.packed_operator_cfr.train_packed',
    'pokerlab.preflop_solver._enumerate_physical_worlds','pokerlab.selected_runout_operator.SelectedRunoutOperator._iter_worlds',
    'pokerlab.native_selected_operator.train_native_selected','pokerlab.native_selected_dag.train_native_selected_dag',
    'pokerlab.native_public_cfr.train_native_public','pokerlab.native_exact_four_street._invoke',
    'pokerlab.native_exact_four_street.train','pokerlab.native_exact_four_street.wire',
    'pokerlab.native_exact_four_street.admit','pokerlab.native_exact_four_street.parse_policy','subprocess.Popen')

def replay_one(case,payload,saved,numeric_replay,cert,physical,auth,out,identifier):
    result={};before=sha(canonical(payload));build_calls=[]
    try:
        numeric=numeric_replay(payload,case['sb_range'],case['bb_range'],config=case['config'],runouts=case['runouts'],
            flop_config=case['flop_config'],turn_config=case['turn_config'],river_config=case['river_config'])
    except ValueError as error:
        check(bounded(str(error)) and saved['numeric']['status']=='resource-unverified','unexpected numeric verifier failure: '+str(error))
        result['numeric']={'status':'resource-unverified','error':str(error)}
        check(saved['quality_gate'] is None,'unverified numeric result has no quality pass')
    else:
        check(saved['numeric']['status']=='complete' and numeric['checked_information_sets']==payload['info_sets'],'numeric coverage/status')
        v=numeric['value_sb'];b0=numeric['sb_best_response_value'];b1=numeric['bb_best_response_value'];g0=max(0.,b0-v);g1=max(0.,b1+v)
        metrics=dict(value_sb=v,value_bb=-v,sb_best_response_value=b0,bb_best_response_value=b1,sb_gain=g0,bb_gain=g1,nash_conv=g0+g1,exploitability=(g0+g1)/2)
        gaps={k:abs(payload[k]-metrics[k]) for k in METRICS}
        check(all(math.isfinite(v) and v<=1e-10 for v in gaps.values()),'fresh complete numeric replay gap')
        check(set(saved['numeric_metric_gaps'])==set(METRICS) and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=1e-10 for v in saved['numeric_metric_gaps'].values()),'saved numeric tolerance flags')
        check(all(bits(numeric[k])==bits(saved['numeric']['result'][k]) for k in ('value_sb','value_bb','sb_best_response_value','bb_best_response_value','nash_conv')),'fresh/saved numeric replay identity')
        result['numeric']={'status':'complete','metric_gaps':gaps,'checked_information_sets':numeric['checked_information_sets']}
    original=physical.build_model
    def counted(*args,**kwargs):
        build_calls.append(1);check(len(build_calls)<=3,'unchanged compact verifier bounded builds');return original(*args,**kwargs)
    try:
        with patch.object(physical,'build_model',new=counted):
            fresh=cert.evaluate_exact(case,payload)
    except ValueError as error:
        check(bounded(str(error)) and saved['exact']['status']=='resource-unverified','unexpected exact verifier failure: '+str(error))
        check(saved['quality_gate'] is None,'resource-unverified exact is not quality pass')
        result['exact']={'status':'resource-unverified','error':str(error),'physical_model_calls':len(build_calls)}
    else:
        exact=fresh['exact_certificate'];old=saved['exact'];check(old['status']=='complete','fresh exact/saved status')
        check(fresh['physical_model_builds']==len(build_calls)==3 and fresh['production_pair_rows']==fresh['training_calls']==fresh['native_calls']==0,'capped verification-only expansion')
        check(fresh['compact_input_canonical_sha256']==before and fresh['verification_expansion_canonical_sha256']==exact['input_policy_canonical_sha256'],'compact/expanded certificate provenance')
        check(all(exact[k]==old['result']['exact_certificate'][k] for k in ('metrics','threshold','threshold_met','normalized_policy_sha256','input_case_canonical_sha256')),'fresh exact metrics/policy binding')
        check(canonical(exact['normalized_policy_rows'])==canonical(old['result']['exact_certificate']['normalized_policy_rows']),'fresh exact normalized-policy row binding')
        m={k:auth.bounded_fraction(value) for k,value in exact['metrics'].items()};threshold=auth.bounded_fraction(exact['threshold'])
        check(threshold==auth.bounded_fraction('1/1000') and type(exact['threshold_met']) is bool and exact['threshold_met']==(m['nash_conv']<=threshold),'exact unchanged rational quality threshold')
        check(m['value_bb']==-m['value_sb'] and m['sb_best_response_gain']==max(0,m['sb_best_response_value']-m['value_sb']) and
              m['bb_best_response_gain']==max(0,m['bb_best_response_value']+m['value_sb']) and
              m['nash_conv']==m['sb_best_response_gain']+m['bb_best_response_gain'] and m['exploitability']*2==m['nash_conv'],'exact rational metric identities')
        check(saved['quality_gate']==(exact['threshold_met'] if result['numeric']['status']=='complete' else None),'saved quality gate recomputation')
        result['exact']={'status':'complete','threshold':exact['threshold'],'threshold_met':exact['threshold_met'],
            'normalized_policy_sha256':exact['normalized_policy_sha256'],'metrics':exact['metrics'],'physical_model_calls':3}
        write(out/(identifier+'-fresh-certificate.json'),fresh)
    check(sha(canonical(payload))==before,'fresh replay mutated original saved payload')
    check(type(saved['forbidden_production_calls']) is dict and not any(saved['forbidden_production_calls'].values()),'saved verifier production calls')
    return result


def main():
    global COMMIT, EXE, BUILD
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('repo','study','output-dir'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('source-commit','manifest-sha256','report-sha256','source-after-sha256','build-sha256','exe-sha256','confirmed-terminal-handle'):p.add_argument('--'+name,required=True)
    p.add_argument('--terminal-exit-code',type=int,required=True);a=p.parse_args()
    check(a.terminal_exit_code==0 and bool(a.confirmed_terminal_handle),'actual successful producer terminal required')
    check(re.fullmatch(r'[0-9a-f]{40}',a.source_commit) is not None and all(re.fullmatch(r'[0-9a-f]{64}',getattr(a,k)) for k in ('manifest_sha256','report_sha256','source_after_sha256','build_sha256','exe_sha256')),'source/artifact pin syntax')
    COMMIT,BUILD,EXE=a.source_commit,a.build_sha256,a.exe_sha256
    repo,study,out=a.repo.resolve(),a.study.resolve(),a.output_dir.resolve()
    check(not out.exists() and repo not in out.parents and study not in out.parents,'new external review output required')
    out.mkdir(parents=True);stage='authentication';own=sha(Path(__file__).read_bytes())
    try:
        ap=Path(__file__).resolve().parents[1]/'exact-selected-independent-review.py';authraw=ap.read_bytes()
        check(sha(authraw)==AUTH,'pinned authentication helper');auth=types.ModuleType('pinned_auth');auth.__file__=str(ap)
        exec(compile(authraw,str(ap),'exec'),auth.__dict__);auth.FROZEN=COMMIT;parse=auth.parse
        files=manifested(study,a.manifest_sha256,parse)
        check(sha(files['report.json'])==a.report_sha256 and sha(files['source-after.json'])==a.source_after_sha256,'report/source-after pins')
        source=parse(files['source-before.json']);check(source['commit']==COMMIT and not source['status'] and parse(files['source-after.json'])==source,'frozen source snapshots')
        identity=auth.source_identity(repo,source);proof=parse(files['source-auth-proof.json'])
        check(proof['commit']==COMMIT and proof['tracked_raw_sha256']==source['sha256'] and proof['closure_count']==len(source['sha256']) and proof['raw_or_normalized_blob_match'] is True,'complete source authentication proof')
        protocol=parse(files['protocol.json']);report=parse(files['report.json']);build=parse(files['build-before.json'])
        check(protocol['version']=='native-fold-mask-classes-fixed-study-v1' and protocol['source_commit']==COMMIT and protocol['source_sha256']==source['sha256'] and protocol['schedule']==[list(v) for v in SCHEDULE] and protocol['payoff_modes']==list(MODES),'fixed source/schedule/payoffs')
        check(report['source_commit']==COMMIT and report['calls_planned']==report['calls_attempted']==report['calls_captured']==len(report['samples'])==34 and report['failure'] is None,'all 34 unique attempts completed')
        check(protocol['build']==build==parse(files['build-after.json']),'build snapshots');build_snapshot=build_identity(repo,build,parse)
        captured=parse(files['capture-time-sha256.json']);check(all(name in files and sha(files[name])==digest for name,digest in captured.items()),'capture-time raw artifacts')
        cases=cases_from_data(repo,parse)
        # All source, build, dependency and evidence authentication precedes project math imports.
        stage='raw proofs';raws={};structural={};statuses=Counter();expected_capture=set()
        for summary,entry in zip(report['samples'],SCHEDULE):
            identifier=label(entry);raw=parse(files[identifier+'.stdout.bin']);capture_check(files,identifier,raw,parse)
            sample={k:v for k,v in raw.items() if k not in ('payload','native_streams')};sample['artifact']=identifier+'.raw.json'
            check(canonical(summary)==canonical(sample),'report/raw observation identity '+identifier)
            structural[identifier]=inspect_child(raw,entry,cases[entry[0]],protocol['runtime']);raws[identifier]=raw;statuses[raw['status']]+=1
            expected_capture.update(identifier+x for x in ('.stdout.bin','.stderr.bin','-process-status.json','.raw.json'))
            for i in range(len(raw['native_streams'])):
                expected_capture.update(f'{identifier}-native-{i}-{kind}.bin' for kind in ('request','stdout','stderr'));expected_capture.add(f'{identifier}-native-{i}-status.json')
        check(expected_capture.issubset(captured),'all scheduled raw artifacts captured at origin')
        stage='protected mathematics';sys.dont_write_bytecode=True;sys.path.insert(0,str(repo))
        from scripts import four_street_validation as physical, exact_selected_compact_certificate as cert
        from scripts.preflop_validation import replay_policy as numeric_replay
        forbidden=Counter({name:0 for name in FORBIDDEN});fresh={}
        def reject(name):
            def blocked(*_args,**_kwargs):forbidden[name]+=1;raise AssertionError('forbidden replay path: '+name)
            return blocked
        with ExitStack() as guards:
            for name in FORBIDDEN:guards.enter_context(patch(name,new=reject(name)))
            for entry in SCHEDULE:
                identifier=label(entry);raw=raws[identifier]
                if raw['status']!='complete':continue
                stage='fresh replay '+identifier
                fresh[identifier]=replay_one(cases[entry[0]],raw['payload'],parse(files[identifier+'-verification.json']),numeric_replay,cert,physical,auth,out,identifier)
                print(identifier,fresh[identifier]['numeric']['status'],fresh[identifier]['exact']['status'],flush=True)
        check(not any(forbidden.values()),'forbidden production call during replay')
        stage='paired comparisons';pairs={};groups={}
        for entry in SCHEDULE:groups.setdefault((entry[0],entry[1],entry[3]),{})[entry[2]]=label(entry)
        for _,modes in groups.items():
            if set(modes)!=set(MODES):continue
            left,right=(modes[m] for m in MODES)
            if left not in fresh or right not in fresh:continue
            x,y=(raws[k]['payload'] for k in (left,right))
            check(canonical(x['strategy'])==canonical(y['strategy']) and x['chance_input_snapshot']==y['chance_input_snapshot'] and all(bits(x[k])==bits(y[k]) for k in METRICS),'paired complete policy/menu/metric bits')
            exact=[fresh[k]['exact'] for k in (left,right)]
            numeric=[fresh[k]['numeric'] for k in (left,right)]
            check(numeric[0]['status']==numeric[1]['status'] and exact[0]['status']==exact[1]['status'],'paired numeric/exact verifier status')
            if numeric[0]['status']=='complete':check(canonical(numeric[0]['metric_gaps'])==canonical(numeric[1]['metric_gaps']),'paired independently replayed numeric gaps')
            if all(e['status']=='complete' for e in exact):
                check(all(exact[0][k]==exact[1][k] for k in ('metrics','threshold','threshold_met','normalized_policy_sha256')),'paired exact policy and flags')
                certificates=[parse((out/(identifier+'-fresh-certificate.json')).read_bytes())['exact_certificate'] for identifier in (left,right)]
                check(canonical(certificates[0]['normalized_policy_rows'])==canonical(certificates[1]['normalized_policy_rows']),'paired normalized-policy rows')
            else:check(all(e['status'] in ('complete','resource-unverified') for e in exact),'verifier cap status')
            name=left+'__vs__'+right;claim=report['paired_comparisons'][name]
            check(claim['complete_policy_rows']==len(x['strategy']) and claim['complete_policy_and_action_rows_bitwise_identical'] is True and claim['all_eight_metric_binary64_identical'] is True and claim['board_sweep_seconds']==raws[left]['seconds'] and claim['fold_mask_classes_seconds']==raws[right]['seconds'] and parse(files[name+'-comparison.json'])==claim,'paired report binding')
            check(claim['independent_numeric_replay_gaps_identical']==(True if numeric[0]['status']=='complete' else None),'paired numeric replay claim')
            if all(e['status']=='complete' for e in exact):check(claim['exact_certificate_metrics_and_flags_identical'] is True and claim['threshold_met']==exact[0]['threshold_met'],'paired exact claim')
            else:check(claim['exact_certificate_metrics_and_flags_identical'] is None and claim['exact_certificate_statuses']==[e['status'] for e in exact],'paired exact unverified claim')
            pairs[name]={'exact_statuses':[e['status'] for e in exact]}
        check(set(pairs)==set(report['paired_comparisons']),'pair report coverage')
        expected_capture.update(identifier+'-verification.json' for identifier in fresh)
        expected_capture.update(name+'-comparison.json' for name in pairs)
        check(set(captured)==expected_capture,'exact producer and verification capture inventory; no extra attempts')
        medians={}
        for mode in MODES:
            ids=[label(('original-22-t10',10,mode,i)) for i in range(3)]
            check(all(i in fresh for i in ids),'required repeat completion')
            check(all(canonical(raws[i]['payload']['strategy'])==canonical(raws[ids[0]]['payload']['strategy']) and all(bits(raws[i]['payload'][k])==bits(raws[ids[0]]['payload'][k]) for k in METRICS) for i in ids),'repeat complete policy/metric equality')
            medians[mode]=statistics.median(raws[i]['seconds'] for i in ids);check(report['original_t10_three_pair_medians_seconds'][mode]==medians[mode],'descriptive median')
        misses=[label(e) for e in SCHEDULE if label(e) in fresh and (fresh[label(e)]['numeric']['status']!='complete' or fresh[label(e)]['exact'].get('threshold_met') is not True)]
        check(report['quality_misses_or_unverified_retained']==misses,'quality misses and verifier caps retained')
        stage='after authentication'
        check(auth.source_identity(repo,source)['raw_sha256']==identity['raw_sha256'] and inventory(study)==files and build_identity(repo,build,parse)==build_snapshot and sha(Path(__file__).read_bytes())==own and ap.read_bytes()==authraw,'source/build/artifact/helper drift')
        result={'status':'passed','source_commit':COMMIT,'source_files':identity['files'],'helper_sha256':own,'auth_helper_sha256':AUTH,'manifest_sha256':a.manifest_sha256,'report_sha256':a.report_sha256,'terminal_handle':a.confirmed_terminal_handle,'terminal_exit_code':0,'candidate_calls':0,'forbidden_calls':dict(forbidden),'counts':dict(statuses),'pairs':pairs,'descriptive_three_pair_medians_seconds':medians,'fresh':fresh,'structural':structural,'build':build_snapshot,'source_before_after_stable':True,'artifacts_before_after_stable':True,'scope':'34 fixed selected-runout attempts. Independent literal wire, fold-mask and bounded numeric/exact physical replay; verifier capacity is unknown quality. Original literal-board map accounting remains preexisting and is not newly proved. No CPU causation, full-deck or unrestricted convergence claim.'}
        write(out/'receipt.json',result);print(json.dumps({'status':'passed','receipt_sha256':sha((out/'receipt.json').read_bytes()),'counts':dict(statuses),'pairs':len(pairs)},sort_keys=True),flush=True)
    except BaseException as error:
        write(out/'first-failure.json',{'stage':stage,'type':type(error).__name__,'message':str(error),'helper_sha256':own});raise

if __name__=='__main__':main()
