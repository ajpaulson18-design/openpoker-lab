"""Pinned physical AA/KK range inputs and independent constructive value bounds."""
from fractions import Fraction
from itertools import combinations
import json
from pathlib import Path
from pokerlab.preflop_full_board_equity import plan_preflop_equities, FullBoardEquities
from pokerlab.preflop_covered_equity import pool_preflop_equities_by_suit
from scripts import preflop_checkdown_validation as numeric
from scripts.validate_preflop_five_reference import verify_saved,checksum

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'benchmarks/results/preflop-five-basis-v1.json'
REPORT_SHA='2ae377e0af6d55491c667d574f41482f2ea6911ba8565ade3b9c8406b54010f7'
SPEC=ROOT/'benchmarks/preflop-aa-kk-physical-range-v1.json'
SPEC_SHA='28314b5a19a89246c1c8c63b3a178d99700378cceaa3ec777a49b81ea5f751c6'

def load_inputs(spec):
    if checksum(spec)!=SPEC_SHA:raise ValueError('AA/KK reference requires frozen game specification')
    if REPORT.stat().st_size>1000000:raise ValueError('Pinned basis report size exceeds its limit')
    report=json.loads(REPORT.read_bytes())
    if report.get('artifact_sha256')!=REPORT_SHA:raise ValueError('Pinned physical source report identity changed')
    summary=verify_saved(REPORT)
    if summary['status']!='passed':raise ValueError('Physical source count report did not pass independent checks')
    source_rows=report['independent_physical_count_rows']
    source_counts={(r['sb_hand'],r['bb_hand']):(r['wins'],r['ties'],r['losses']) for r in source_rows}
    plan=plan_preflop_equities('AdAs','KdKs,KcKd,KcKh');counts=[];worlds=[]
    for i,j,prior in plan.pairs:
        values=source_counts[(''.join(plan.hands[0][i]),''.join(plan.hands[1][j]))]
        counts.append(values)
        for sign,n in zip((-1,0,1),(values[2],values[1],values[0])):
            if n:worlds.append((i,j,float(prior*Fraction(n,1712304)),sign))
    source=FullBoardEquities(plan.hands,plan.pairs,tuple(counts),tuple(worlds),plan._budget_items)
    source.validate();table=pool_preflop_equities_by_suit([source],spec['sb_range'],spec['bb_range'])
    # Rebuild target count rows from independently checked endpoint mappings,
    # not candidate result equity fields or a guessed 169-hand bucket.
    trusted=[]
    for proof in table.provenance():
        a,b=proof['source_sb_hand'],proof['source_bb_hand'];mapping=proof['suit_permutation']
        if set(mapping)!=set('cdhs') or set(mapping.values())!=set('cdhs'):
            raise ValueError('AA/KK source map is not a suit bijection')
        def mapped(text):return ''.join(sorted(text[i]+mapping[text[i+1]] for i in (0,2)))
        if (mapped(a),mapped(b))!=(proof['target_sb_hand'],proof['target_bb_hand']):
            raise ValueError('AA/KK joint map does not preserve both ordered hands')
        w,t,l=source_counts[(a,b)]
        trusted.append({'sb_hand':proof['target_sb_hand'],'bb_hand':proof['target_bb_hand'],
                        'wins':w,'ties':t,'losses':l,'boards':1712304})
    if len(table.pairs)!=36 or any(prior!=Fraction(1,36) for _,_,prior in table.pairs):
        raise ValueError('Physical AA/KK pair census or exact priors changed')
    return table,trusted,{'path':REPORT.relative_to(ROOT).as_posix(),'artifact_sha256':REPORT_SHA,
                           'fresh_count_verification':summary}


def constructive_value(spec,counts):
    """Check explicit legal matching lower/upper bounds; never train or solve LP."""
    if checksum(spec)!=SPEC_SHA:raise ValueError('Constructive value requires the frozen AA/KK game')
    expected={(a+b,c+d) for a,b in combinations(tuple('A'+s for s in 'cdhs'),2)
                           for c,d in combinations(tuple('K'+s for s in 'cdhs'),2)}
    actual={};means=[];class_counts={}
    for row in counts:
        key=row['sb_hand'],row['bb_hand']
        if key not in expected or key in actual or row['boards']!=1712304:
            raise ValueError('Constructive proof requires all 36 physical pairs exactly once')
        if (any(type(row[k]) is not int or row[k]<0 for k in ('wins','ties','losses','boards'))
                or sum(row[k] for k in ('wins','ties','losses'))!=1712304):
            raise ValueError('Invalid exact physical row for constructive bound')
        mean=Fraction(row['wins']-row['losses'],row['boards'])
        if not Fraction(1,3)<mean<1:raise ValueError('AA/KK payoff inequalities do not prove the one-chip bound')
        means.append(mean);actual[key]=mean
        overlap=len({key[0][1],key[0][3]} & {key[1][1],key[1][3]})
        class_counts[overlap]=class_counts.get(overlap,0)+1
    if set(actual)!=expected or class_counts!={0:6,1:24,2:6}:
        raise ValueError('AA/KK physical suit-class coverage changed')
    root,census=numeric._build(numeric._config(spec['config']))
    if not isinstance(root,numeric._Node) or root.player!=0 or root.history!=():
        raise ValueError('Constructive game must start with the SB acting')
    choices={a.token:(a,child) for a,child in zip(root.actions,root.children)}
    if 'fold' not in choices or 'call' not in choices or 'all_in@3' not in choices:
        raise ValueError('Independent legal root misses fold/limp/three-chip shove')
    folded=choices['fold'][1]
    if not isinstance(folded,numeric._Terminal) or folded.winner!=1 or min(folded.contributions)!=.5:
        raise ValueError('Root fold payoff differs from the proved bound')
    limp=choices['call'][1]
    if not isinstance(limp,numeric._Node) or limp.player!=1:
        raise ValueError('Limp must preserve the BB option')
    check=next((child for a,child in zip(limp.actions,limp.children) if a.name=='check'),None)
    if not isinstance(check,numeric._Terminal) or check.winner is not None or min(check.contributions)!=1:
        raise ValueError('BB check after limp must settle at one matched chip')
    for token,(action,node) in choices.items():
        if token in ('fold','call'):continue
        if not isinstance(node,numeric._Node) or node.player!=1:
            raise ValueError('Every SB opening raise must allow a legal BB fold')
        fold=next((child for a,child in zip(node.actions,node.children) if a.name=='fold'),None)
        if not isinstance(fold,numeric._Terminal) or fold.winner!=0 or min(fold.contributions)!=1:
            raise ValueError('BB fold against an opening raise must cap SB at one chip')
    jam=choices['all_in@3'][1]
    if {a.name for a in jam.actions}!={'fold','call'}:raise ValueError('BB has unexpected choices after all-in')
    call=next(child for a,child in zip(jam.actions,jam.children) if a.name=='call')
    if not isinstance(call,numeric._Terminal) or call.winner is not None or min(call.contributions)!=3:
        raise ValueError('All-in call must settle at three matched chips')
    return {'status':'passed','exact_value_sb_fraction':'1','lower_bound_fraction':'1','upper_bound_fraction':'1',
            'sb_guarantee':'Open shove for every own AA hand; fold pays +1, call pays 3u > 1 for every compatible pair.',
            'bb_cap':'Check after every limp and fold to every SB opening raise; SB fold pays -1/2, checked limp pays u < 1, raise pays +1.',
            'minimum_conditional_mean_fraction':str(min(means)),
            'maximum_conditional_mean_fraction':str(max(means)),
            'compatible_pairs':36,'suit_overlap_class_counts':{str(k):v for k,v in sorted(class_counts.items())},
            'independent_public_tree':census,
            'scope':'Constructive exact value of the fixed AA/KK finite preflop/checkdown game, not an unrestricted or arbitrary-range equilibrium.'}
