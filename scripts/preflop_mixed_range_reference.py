"""Authenticated mixed physical preflop rows and independently legal value bounds."""
from fractions import Fraction
from itertools import combinations
import json
from pathlib import Path
from pokerlab.preflop_full_board_equity import plan_preflop_equities,FullBoardEquities
from pokerlab.preflop_covered_equity import pool_preflop_equities_by_suit
from scripts import preflop_aa_kk_reference as aa
from scripts import benchmark_preflop_qq_kk_basis as qq
from scripts.validate_preflop_five_reference import checksum,verify_saved

ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/'benchmarks/preflop-mixed-physical-range-v1.json'
SPEC_SHA='12debaea49eb6d9ac4b9ab6f49767e1dc25f00e4de6f163e69af5690f51653ca'
REPORTS=(aa.REPORT,ROOT/'benchmarks/results/preflop-qq-kk-basis-v1.json')


def load_inputs(spec):
    if checksum(spec)!=SPEC_SHA:raise ValueError('Requires frozen mixed physical specification')
    sources=[];trusted_sources={};identities=[]
    for path,pinned,sb,verify in zip(REPORTS,spec['basis_reports'],('AdAs','QdQs'),(verify_saved,qq.verify_saved)):
        if path.relative_to(ROOT).as_posix()!=pinned['path'] or path.stat().st_size>1000000:
            raise ValueError('Mixed physical source report path/size changed')
        report=json.loads(path.read_bytes())
        if report.get('artifact_sha256')!=pinned['artifact_sha256']:
            raise ValueError('Mixed physical source report identity changed')
        summary=verify(path)
        if summary['status']!='passed':raise ValueError('Mixed physical source verification failed')
        rows=report['independent_physical_count_rows']
        source_counts={(r['sb_hand'],r['bb_hand']):(r['wins'],r['ties'],r['losses']) for r in rows}
        plan=plan_preflop_equities(sb,'KdKs,KcKd,KcKh');counts=[];worlds=[]
        for i,j,prior in plan.pairs:
            key=(''.join(plan.hands[0][i]),''.join(plan.hands[1][j]));values=source_counts[key]
            counts.append(values);trusted_sources[key]=values
            for sign,n in zip((-1,0,1),(values[2],values[1],values[0])):
                if n:worlds.append((i,j,float(prior*Fraction(n,1712304)),sign))
        source=FullBoardEquities(plan.hands,plan.pairs,tuple(counts),tuple(worlds),plan._budget_items)
        source.validate();sources.append(source)
        identities.append({**pinned,'fresh_count_verification':summary})
    table=pool_preflop_equities_by_suit(sources,spec['sb_range'],spec['bb_range']);trusted=[]
    for proof in table.provenance():
        a,b=proof['source_sb_hand'],proof['source_bb_hand'];mapping=proof['suit_permutation']
        if set(mapping)!=set('cdhs') or set(mapping.values())!=set('cdhs'):
            raise ValueError('Mixed physical source map must be a suit bijection')
        def mapped(text):return ''.join(sorted(text[i]+mapping[text[i+1]] for i in (0,2)))
        if (mapped(a),mapped(b))!=(proof['target_sb_hand'],proof['target_bb_hand']):
            raise ValueError('Mixed physical map must preserve both ordered private hands')
        w,t,l=trusted_sources[(a,b)]
        trusted.append({'sb_hand':proof['target_sb_hand'],'bb_hand':proof['target_bb_hand'],
                        'wins':w,'ties':t,'losses':l,'boards':1712304})
    if (len(table.hands[0]),len(table.hands[1]),len(table.pairs))!=(12,6,72):
        raise ValueError('Mixed physical hand/pair census changed')
    for i,j,prior in table.pairs:
        expected=Fraction(1,54) if table.hands[0][i][0][0]=='A' else Fraction(1,108)
        if prior!=expected:raise ValueError('Mixed physical global prior changed')
    return table,trusted,identities


def constructive_bounds(spec,counts):
    """Check legal own-hand guarantees; do not train or infer an exact value."""
    if checksum(spec)!=SPEC_SHA:raise ValueError('Requires frozen mixed physical specification')
    expected={(a+b,c+d) for rank in ('A','Q') for a,b in combinations(tuple(rank+s for s in 'cdhs'),2)
                         for c,d in combinations(tuple('K'+s for s in 'cdhs'),2)}
    actual={};classes={rank:{0:0,1:0,2:0} for rank in ('A','Q')};weak=[];strong=[]
    for row in counts:
        key=row['sb_hand'],row['bb_hand']
        if (key not in expected or key in actual or type(row['boards']) is not int or row['boards']!=1712304
                or any(type(row[k]) is not int or row[k]<0 for k in ('wins','ties','losses'))
                or sum(row[k] for k in ('wins','ties','losses'))!=1712304):
            raise ValueError('Mixed constructive proof requires all 72 exact physical pairs')
        mean=Fraction(row['wins']-row['losses'],row['boards']);actual[key]=mean
        rank=key[0][0];overlap=len(set(key[0][1::2]) & set(key[1][1::2]));classes[rank][overlap]+=1
        if rank=='A':strong.append(row)
        else:
            if not -1<=mean<0:raise ValueError('QQ conditional showdown mean must be negative')
            weak.append(mean)
    if set(actual)!=expected or any(c!={0:6,1:24,2:6} for c in classes.values()):
        raise ValueError('Mixed physical suit-class coverage changed')
    # This independent checker establishes the exact legal root, BB check/fold
    # cap, and AA jam guarantee using the unchanged numeric rules and AA rows.
    # The current frozen config must match that checked game exactly.
    oldspec=json.loads(aa.SPEC.read_bytes())
    if spec['config']!=oldspec['config']:raise ValueError('Constructive legal game changed')
    aa_proof=aa.constructive_value(oldspec,strong)
    lower=Fraction(2,3)*Fraction(aa_proof['lower_bound_fraction'])+Fraction(1,3)*Fraction(-1,2)
    return {'status':'passed','lower_bound_fraction':str(lower),'upper_bound_fraction':'1',
            'sb_guarantee':'Jam for every own AA hand and fold every own QQ hand: AA guarantees +1; QQ loses 1/2; own-rank masses 2/3 and 1/3.',
            'bb_cap':'Check every limp and fold every opening raise: SB fold pays -1/2, checked limp has mean <=1, opening raise pays +1.',
            'aa_legal_bound_verification':aa_proof,'qq_conditional_mean_fraction_range':[str(min(weak)),str(max(weak))],
            'compatible_pairs':72,'suit_overlap_class_counts':{r:{str(k):v for k,v in sorted(c.items())} for r,c in classes.items()},
            'scope':'Legal constructive bounds for the fixed mixed finite game; no exact equilibrium value or unrestricted equilibrium claim.'}
