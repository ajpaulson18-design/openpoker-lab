"""Independent full-board count and closed-form preflop shove/fold replay.

Shares only card/range grammar and the independent best-five oracle. No
production equity/tree/payoff/training/evaluation/BR helper is an oracle.
"""
from fractions import Fraction
from itertools import combinations
from math import comb,fsum,isfinite
from pokerlab.cards import expand_range
from scripts.preflop_validation import independent_rank

BOARDS=comb(48,5)


def _require(condition, details=None):
    """Retain evidence checks when Python assertions are disabled."""
    if not condition:
        raise AssertionError(details)


def independent_counts(sb_range,bb_range,*,progress=None):
    ranges=[expand_range(r) for r in (sb_range,bb_range)]
    pairs=[(a,b,Fraction.from_float(x)*Fraction.from_float(y))
           for a,x in ranges[0].items() for b,y in ranges[1].items() if set(a).isdisjoint(b)]
    total=sum((w for _,_,w in pairs),Fraction())
    rows=[]
    for number,(a,b,weight) in enumerate(pairs,1):
        dead=set(a+b)
        deck=tuple(r+s for r in '23456789TJQKA' for s in 'cdhs' if r+s not in dead)
        wins=ties=losses=0
        if progress:progress(number,0,BOARDS)
        for processed,board in enumerate(combinations(deck,5),1):
            x,y=independent_rank(a+board),independent_rank(b+board)
            if x>y:wins+=1
            elif x<y:losses+=1
            else:ties+=1
            if progress and processed%100000==0:progress(number,processed,BOARDS)
        _require(wins+ties+losses==BOARDS)
        if progress:progress(number,BOARDS,BOARDS)
        rows.append({'sb_hand':''.join(a),'bb_hand':''.join(b),'wins':wins,
                     'ties':ties,'losses':losses,'boards':BOARDS,
                     'pair_probability':float(weight/total)})
    return tuple(rows)


def replay(result, sb_range, bb_range, config, counts, tolerance=1e-10):
    def money(x):return round(float(x),9)
    sb=money(config.get('small_blind',.5));bb=money(config.get('big_blind',1))
    raw=config.get('starting_stack',100)
    stacks=tuple(map(money,raw)) if isinstance(raw,(tuple,list)) else (money(raw),)*2
    matched=min(stacks)
    token='all_in@'+format(stacks[0],'.9f').rstrip('0').rstrip('.')
    ranges=[expand_range(r) for r in (sb_range,bb_range)]
    products=[(a,b,Fraction.from_float(x)*Fraction.from_float(y)) for a,x in ranges[0].items()
              for b,y in ranges[1].items() if set(a).isdisjoint(b)]
    normalizer=sum((w for _,_,w in products),Fraction())
    expected_pairs=[(''.join(a),''.join(b),w/normalizer) for a,b,w in products]
    _require(result['solver_version']=='preflop-push-fold-v1')
    _require(result['strategy_schema']=='preflop-strategy-v1')
    _require(result['runout_mode']=='full-deck-unordered-final-boards')
    _require(result['config']['small_blind']==sb and result['config']['big_blind']==bb)
    canonical_stack=list(stacks) if isinstance(raw,(tuple,list)) else stacks[0]
    _require(result['config']['starting_stack']==canonical_stack)
    chance={(r['sb_hand'],r['bb_hand']):r for r in counts}
    _require(len(chance)==len(counts)==len(expected_pairs))
    actual_counts={(r['sb_hand'],r['bb_hand']):r for r in result['pair_equities']}
    _require(len(actual_counts)==len(result['pair_equities'])==len(expected_pairs))
    _require(set(actual_counts)==set(chance)=={(a,b) for a,b,_ in expected_pairs})
    _require(result['compatible_pairs']==len(expected_pairs))
    _require(result['physical_boards']==BOARDS*len(expected_pairs))
    deals=[]
    for a,b,prior in expected_pairs:
        actual=actual_counts[(a,b)]
        expected=chance[(a,b)]
        _require(expected['boards']==BOARDS and expected['wins']+expected['ties']+expected['losses']==BOARDS)
        _require(all(type(expected[k]) is int and expected[k]>=0 for k in ('wins','ties','losses')))
        for k in ('sb_hand','bb_hand','wins','ties','losses','boards'):
            _require(actual[k]==expected[k], 'Full-board count mismatch')
        _require(abs(actual['pair_probability']-float(prior))<=1e-12)
        deals.append((a,b,float(prior),(expected['wins']-expected['losses'])/BOARDS))
    active=[{w[p] for w in deals} for p in (0,1)]
    rows={}
    for row in result['strategy']:
        _require(set(row)=={'player','hand','street','revealed_board','history','actions'})
        player={'sb':0,'bb':1}[row['player']]
        _require(row['street']=='preflop' and row['revealed_board']==[])
        _require(row['hand'] in active[player])
        _require(row['history']==([] if player==0 else [token]))
        key=player,row['hand'];_require(key not in rows)
        expected=(('fold',0.,0.,'fold'),('all_in',money(stacks[0]-sb),stacks[0],token)) if player==0 else (
            ('fold',0.,0.,'fold'),('call',money(matched-bb),matched,'call'))
        _require(len(row['actions'])==2)
        probabilities=[]
        for action,wanted in zip(row['actions'],expected):
            _require(set(action)=={'name','amount','raise_to','history_key','probability'})
            _require((action['name'],action['amount'],action['raise_to'],action['history_key'])==wanted, 'Blind/shove/call amount mismatch')
            p=float(action['probability']);_require(isfinite(p) and 0<=p<=1)
            probabilities.append(p)
        _require(abs(fsum(probabilities)-1)<=1e-9)
        rows[key]=tuple(probabilities)
    _require(set(rows)=={(p,h) for p in (0,1) for h in active[p]})
    _require(result['info_sets']==sum(map(len,active)))
    _require(result['compatible_pairs']==len(deals))
    _require(result['physical_boards']==BOARDS*len(deals))
    # Preserve both serialized action frequencies. Convert each binary64
    # value to its exact fraction, then normalize each row by its exact sum.
    # This makes the replay a normalized interpretation of the stored policy
    # despite permitted sub-ulp drift in emitted probability pairs.
    exact_rows={}
    raw_frequency_fractions={}
    for key,probabilities in rows.items():
        raw=tuple(Fraction.from_float(probability) for probability in probabilities)
        raw_total=sum(raw,Fraction())
        _require(raw_total>0)
        raw_frequency_fractions[key]=raw
        exact_rows[key]=tuple(probability/raw_total for probability in raw)
    exact_deals=[(a,b,prior,Fraction(chance[(a,b)]['wins']-chance[(a,b)]['losses'],BOARDS))
                 for a,b,prior in expected_pairs]
    exact_sb=Fraction.from_float(sb); exact_bb=Fraction.from_float(bb)
    exact_matched=Fraction.from_float(matched)
    value_exact=sum((w*(exact_rows[(0,a)][0]*(-exact_sb)+exact_rows[(0,a)][1]*
        (exact_rows[(1,b)][0]*exact_bb+exact_rows[(1,b)][1]*exact_matched*sign))
        for a,b,w,sign in exact_deals),Fraction())
    br0_exact=Fraction()
    for own in sorted(active[0]):
        fold=sum((-exact_sb*w for a,b,w,sign in exact_deals if a==own),Fraction())
        shove=sum((w*(exact_rows[(1,b)][0]*exact_bb+
                      exact_rows[(1,b)][1]*exact_matched*sign)
                   for a,b,w,sign in exact_deals if a==own),Fraction())
        br0_exact+=max(fold,shove)
    br1_exact=Fraction()
    for own in sorted(active[1]):
        sb_fold=sum((w*exact_rows[(0,a)][0]*exact_sb
                     for a,b,w,sign in exact_deals if b==own),Fraction())
        bb_fold=sum((-exact_bb*w*exact_rows[(0,a)][1]
                     for a,b,w,sign in exact_deals if b==own),Fraction())
        call=sum((-exact_matched*sign*w*exact_rows[(0,a)][1]
                  for a,b,w,sign in exact_deals if b==own),Fraction())
        br1_exact+=sb_fold+max(bb_fold,call)
    gap_exact=max(Fraction(),br0_exact+br1_exact)
    sb_gain_exact=max(Fraction(),br0_exact-value_exact)
    bb_gain_exact=max(Fraction(),br1_exact+value_exact)
    value=float(value_exact); br0=float(br0_exact); br1=float(br1_exact)
    gap=float(gap_exact)
    metrics={'value_sb':value,'value_bb':-value,'sb_best_response_value':br0,
             'bb_best_response_value':br1,'nash_conv':gap,'exploitability':float(gap_exact/2),
             'sb_best_response_gain':float(sb_gain_exact),
             'bb_best_response_gain':float(bb_gain_exact)}
    deltas={k:abs(result[k]-v) for k,v in metrics.items()}
    _require(all(isfinite(d) and d<=tolerance for d in deltas.values()), deltas)
    return {**metrics,'scalar_absolute_gaps':deltas,'checked_information_sets':len(rows),
            'checked_physical_boards':BOARDS*len(deals),
            'exact_fraction_replay':{
                'value_sb':[value_exact.numerator,value_exact.denominator],
                'sb_best_response_value':[br0_exact.numerator,br0_exact.denominator],
                'bb_best_response_value':[br1_exact.numerator,br1_exact.denominator],
                'nash_conv':[gap_exact.numerator,gap_exact.denominator],
                'sb_best_response_gain':[sb_gain_exact.numerator,sb_gain_exact.denominator],
                'bb_best_response_gain':[bb_gain_exact.numerator,bb_gain_exact.denominator],
                'input_frequencies':'serialized binary64 fractions',
                'normalization':'each action row normalized by its exact fraction sum',
                'exact_normalized_action_frequencies':{
                    f'{player}:{hand}':[[p.numerator,p.denominator] for p in exact_rows[(player,hand)]]
                    for player,hand in sorted(exact_rows)}}}


def weighted_equilibrium_certificate(result,counts):
    """Exact rational 3-pair certificate for the documented AA/QQ vs AK/KK game.

    AA always shoves and AK always calls. Solve QQ/KK indifference equations,
    checking those regimes before returning a candidate for independent replay.
    """
    from copy import deepcopy
    c={(r['sb_hand'],r['bb_hand']):r for r in counts}
    aa,qq,ak,kk='AdAs','QdQs','AsKh','KdKs'
    _require(set(c)=={(aa,kk),(qq,ak),(qq,kk)})
    def sign(key):return Fraction(c[key]['wins']-c[key]['losses'],BOARDS)
    config=result['config'];small=Fraction(str(config['small_blind']));big=Fraction(str(config['big_blind']))
    raw=config['starting_stack'];effective=Fraction(str(min(raw) if isinstance(raw,(tuple,list)) else raw))
    # The fixed range weights are AA:1 QQ:.5 and AK:.25 KK:1.
    a,b,d=Fraction(8,13),Fraction(1,13),Fraction(4,13)
    u,v,z=sign((aa,kk)),sign((qq,ak)),sign((qq,kk))
    _require(all(abs(c[key]['pair_probability']-float(prior))<=1e-15 for key,prior in (((aa,kk),a),((qq,ak),b),((qq,kk),d))))
    _require(effective*u>big and effective*v<big)
    x=a*(effective*u-big)/(d*(big-effective*z))
    y=(b*effective*v+d*big+small*(b+d))/(d*(big-effective*z))
    _require(0<x<1 and 0<y<1, 'Mixed certificate regime does not apply')
    certificate=deepcopy(result)
    for row in certificate['strategy']:
        frequency={aa:Fraction(1),qq:x,ak:Fraction(1),kk:y}[row['hand']]
        row['actions'][1]['probability']=float(frequency)
        row['actions'][0]['probability']=float(1-frequency)
    # Value at the exact rational certificate, including the SB-fold branch.
    value=a*((1-y)*big+y*effective*u)-small*(b+d)
    certificate.update(value_sb=float(value),value_bb=float(-value),
        sb_best_response_value=float(value),bb_best_response_value=float(-value),
        nash_conv=0.,exploitability=0.,sb_best_response_gain=0.,bb_best_response_gain=0.)
    return certificate,{'sb_qq_shove_fraction':[x.numerator,x.denominator],
                        'bb_kk_call_fraction':[y.numerator,y.denominator],
                        'value_sb_fraction':[value.numerator,value.denominator]}
