"""Independent exact replay for bounded full-board preflop checkdown.

Only the established range grammar is shared. Legal actions, public tree,
policy replay and own-hand best responses are rebuilt here independently.
"""
from dataclasses import dataclass
from fractions import Fraction
from math import fsum, isfinite
from pokerlab.cards import expand_range

_EPS=1e-9
_BOARDS=1_712_304
_MAX_DECISIONS=10_000
_MAX_STATES=250_000
_RESULT_KEYS={"solver_version","strategy_schema","algorithm","iterations","training_iterations_completed","config","runout_mode","compatible_pairs","physical_boards","training_world_rows","info_sets","tree","work_budget","pair_equities","strategy","value_sb","value_bb","sb_best_response_value","bb_best_response_value","nash_conv","exploitability","sb_best_response_gain","bb_best_response_gain","scope"}
_EQUITY_KEYS={"sb_hand","bb_hand","wins","ties","losses","boards","pair_probability","pair_probability_fraction"}
_ROW_KEYS={"player","hand","street","revealed_board","history","actions"}
_ACTION_KEYS={"name","amount","raise_to","history_key","probability"}

def _clean(v):
    v=round(float(v),9)
    return 0.0 if v==0 else v

def _numeric(value):
    if isinstance(value, bool):
        raise ValueError('configuration amounts must be numbers, not booleans')
    number = float(value)
    if not isfinite(number) or not 1e-9 <= number <= 1_000_000:
        raise ValueError('configuration amounts outside supported numeric bounds')
    return number

def _token(name,target):
    return name if name not in ("bet","raise","all_in") else name+"@"+format(float(target),".9f").rstrip("0").rstrip(".")

@dataclass(frozen=True)
class _Action:
    name:str
    amount:float
    target:float
    full:bool=False
    @property
    def token(self): return _token(self.name,self.target)

@dataclass(frozen=True)
class _Terminal:
    contributions:tuple
    winner:int|None=None

@dataclass(frozen=True)
class _Node:
    player:int
    history:tuple
    contributions:tuple
    actions:tuple
    children:tuple

def _config(raw):
    if type(raw) is not dict or set(raw)-{"small_blind","big_blind","starting_stack","raise_sizes","max_raises","include_all_in"}:
        raise ValueError("invalid configuration mapping")
    sb=_clean(_numeric(raw.get("small_blind",.5))); bb=_clean(_numeric(raw.get("big_blind",1)))
    st=raw.get("starting_stack",3)
    if isinstance(st,(list,tuple)):
        if len(st)!=2: raise ValueError("starting_stack must be scalar or pair")
        stacks=tuple(_clean(_numeric(x)) for x in st); stcanon=list(stacks)
    else: stacks=(_clean(_numeric(st)),)*2; stcanon=stacks[0]
    raw_sizes=raw.get("raise_sizes",(.5,))
    if type(raw_sizes) not in (list,tuple) or len(raw_sizes)>8: raise ValueError("invalid raise_sizes")
    sizes=tuple(sorted({_numeric(x) for x in raw_sizes}))
    mr=raw.get("max_raises",1); ia=raw.get("include_all_in",True)
    if not all(isfinite(x) for x in (sb,bb,*stacks,*sizes)) or sb<=_EPS or bb-sb<=_EPS or min(stacks)<=0 or any(x<=0 for x in sizes): raise ValueError("invalid blinds, stacks or sizing")
    if type(mr) is not int or not 0<=mr<=8 or type(ia) is not bool: raise ValueError("invalid raise controls")
    canon={"small_blind":sb,"big_blind":bb,"starting_stack":stcanon,"raise_sizes":list(sizes),"max_raises":mr,"include_all_in":ia}
    return canon,sb,bb,stacks,sizes,mr,ia

def _raises(player,committed,stacks,previous,sizes,include_all_in):
    other=1-player; own,theirs=committed[player],committed[other]
    if own>theirs+_EPS or stacks[other]<=theirs+_EPS: return ()
    maximum=stacks[player]; call_target=theirs
    pot_call=sum(committed)+max(0.0,theirs-own); minimum=call_target+previous
    found={}
    def add(target,full):
        target=_clean(min(maximum,max(call_target,target)))
        if target<=call_target+_EPS:return
        found[target]=_Action("all_in" if target>=maximum-_EPS else "raise",_clean(target-own),target,full)
    for frac in sizes:
        requested=call_target+frac*pot_call
        target=_clean(min(maximum,max(minimum,requested)))
        full=target-call_target+_EPS>=previous
        if full:add(target,True)
        elif requested+_EPS>=maximum or minimum>maximum:add(maximum,False)
    if include_all_in and maximum>call_target+_EPS:
        add(maximum,maximum-call_target+_EPS>=previous)
    return tuple(found[k] for k in sorted(found))

def _build(parts):
    _,sb,bb,stacks,sizes,max_raises,include_all_in=parts
    counts={"decision_nodes":0,"fold_terminals":0,"continuations":0,"public_states":0}
    def reserve(kind):
        if counts["public_states"]>=_MAX_STATES: raise ValueError("independent replay public-state limit exceeded")
        if kind=="decision" and counts[kind+"_nodes"]>=_MAX_DECISIONS: raise ValueError("independent replay decision-node limit exceeded")
        counts["public_states"]+=1
        counts["decision_nodes" if kind=="decision" else "fold_terminals" if kind=="fold" else "continuations"]+=1
    def terminal(contrib,winner=None):
        reserve("continuation" if winner is None else "fold")
        return _Terminal(tuple(map(_clean,contrib)),winner)
    def build(history,player,contrib,previous,raises,reopened):
        reserve("decision"); other=1-player; own,theirs=contrib[player],contrib[other]
        acts=[]; kids=[]
        if abs(own-theirs)<=_EPS:
            check=_Action("check",0.,0.)
            acts.append(check); kids.append(terminal(contrib))
            if raises<max_raises and contrib[other]<stacks[other]-_EPS:
                for a in _raises(player,contrib,stacks,previous,sizes,include_all_in):
                    up=list(contrib); up[player]=a.target; inc=a.target-theirs; full=inc+_EPS>=previous
                    acts.append(a); kids.append(build(history+(a.token,),other,tuple(up),inc if full else previous,raises+1,full))
        else:
            callto=_clean(min(theirs,stacks[player]))
            fold=_Action("fold",0.,0.); call=_Action("call",_clean(callto-own),callto)
            acts.extend((fold,call)); kids.extend((terminal(contrib,other),None))
            up=list(contrib); up[player]=callto; up=tuple(map(_clean,up))
            if player==0 and not history and abs(up[0]-up[1])<=_EPS and all(up[p]<stacks[p]-_EPS for p in (0,1)):
                kids[1]=build(history+("call",),1,up,bb,raises,True)
            else:kids[1]=terminal(up)
            if raises<max_raises and reopened and contrib[other]<stacks[other]-_EPS:
                for a in _raises(player,contrib,stacks,previous,sizes,include_all_in):
                    nxt=list(contrib); nxt[player]=a.target; inc=a.target-theirs; full=inc+_EPS>=previous
                    acts.append(a); kids.append(build(history+(a.token,),other,tuple(nxt),inc if full else previous,raises+1,full))
        return _Node(player,tuple(history),tuple(contrib),tuple(acts),tuple(kids))
    raw=(_clean(min(sb,stacks[0])),_clean(min(bb,stacks[1])))
    allin=tuple(stacks[p]<=raw[p]+_EPS for p in (0,1))
    try:
        if any(allin) and any(raw[1-p]>=raw[p]-_EPS for p in (0,1) if allin[p]): root=terminal(raw)
        else: root=build((),0,raw,bb,0,True)
        return root,counts
    finally:
        build=None; terminal=None; reserve=None

def replay(result,sb_range,bb_range,config,counts,*,tolerance=1e-10):
    """Validate serialized policy against trusted physical W/T/L rows.

    The input ``counts`` must come from an independent physical-board census;
    result equity rows are only checked against it, never treated as evidence.
    """
    if type(result) is not dict or set(result)!=_RESULT_KEYS: raise ValueError("unexpected full-checkdown result schema")
    if result["solver_version"]!="preflop-full-checkdown-v1" or result["strategy_schema"]!="preflop-strategy-v1": raise ValueError("unsupported solver schema")
    if result["algorithm"] not in ("vanilla","dcfr","cfrplus"): raise ValueError("unsupported algorithm")
    if type(result["iterations"]) is not int or not 10<=result["iterations"]<=10000: raise ValueError("invalid requested iterations")
    if type(result["training_iterations_completed"]) is not int: raise ValueError("invalid completed iterations")
    if result["runout_mode"]!="full-deck-hidden-final-board-checkdown": raise ValueError("unexpected runout scope")
    if type(tolerance) not in (int,float) or not isfinite(float(tolerance)) or tolerance<0: raise ValueError("invalid tolerance")
    canon,sb,bb,stacks,sizes,mr,ia=_config(config)
    if _config(result["config"])[0]!=canon or result["config"]!=canon: raise ValueError("serialized config differs from requested config")
    ranges=(expand_range(sb_range),expand_range(bb_range)); hands=tuple(tuple(sorted(r)) for r in ranges)
    if len(hands[0])*len(hands[1])>4096: raise ValueError("independent private-candidate limit exceeded")
    candidate=[]
    for h0 in hands[0]:
        for h1 in hands[1]:
            w=Fraction.from_float(float(ranges[0][h0]))*Fraction.from_float(float(ranges[1][h1]))
            if w and not (set(h0)&set(h1)):
                candidate.append((h0,h1,w))
                if len(candidate)>4: raise ValueError("independent compatible-pair limit exceeded")
    norm=sum((x[2] for x in candidate),Fraction())
    if not candidate or norm<=0: raise ValueError("no compatible private hand pairs")
    priors={(a,b):w/norm for a,b,w in candidate}
    labels={("".join(a),"".join(b)):(a,b) for a,b in priors}
    if type(counts) not in (list,tuple): raise ValueError("trusted counts must be a sequence")
    census={}
    for row in counts:
        if type(row) is not dict: raise ValueError("trusted count row must be an object")
        if type(row.get('sb_hand')) is not str or type(row.get('bb_hand')) is not str: raise ValueError('invalid trusted hand labels')
        key=labels.get((row['sb_hand'],row['bb_hand']))
        if key is None or key in census: raise ValueError("duplicate or incompatible trusted count row")
        w,t,l=(row.get(k) for k in ("wins","ties","losses"))
        if any(type(x) is not int or x<0 for x in (w,t,l)) or w+t+l!=_BOARDS: raise ValueError("invalid physical W/T/L census")
        if type(row.get("boards")) is not int or row["boards"]!=_BOARDS: raise ValueError("wrong physical board count")
        # Physical counts do not depend on historical source range weights.
        # Target priors are derived independently above, never copied from a
        # trusted source row's optional pair_probability metadata.
        census[key]=(w,t,l)
    if set(census)!=set(priors): raise ValueError("trusted census misses a compatible pair")
    parts=(canon,sb,bb,stacks,sizes,mr,ia); root,tree=_build(parts)
    if type(result["tree"]) is not dict or result["tree"]!=tree or any(type(v) is not int for v in result['tree'].values()): raise ValueError("public tree counts mismatch")
    expected_completed=result['iterations'] if tree['decision_nodes'] else 0
    if result['training_iterations_completed']!=expected_completed: raise ValueError('invalid completed iterations')
    positive_rows=sum(sum(value>0 for value in row) for row in census.values())
    if any(type(result[field]) is not int for field in ('compatible_pairs','physical_boards','training_world_rows','info_sets')): raise ValueError('invalid game census types')
    if (result["compatible_pairs"],result["physical_boards"],result["training_world_rows"])!=(len(priors),_BOARDS*len(priors),positive_rows): raise ValueError("physical game dimensions mismatch")
    if type(result["work_budget"]) is not dict: raise ValueError("missing work budget")
    eq={p:Fraction(w-l,_BOARDS) for p,(w,t,l) in census.items()}
    if type(result["strategy"]) is not list: raise ValueError("strategy must be a list")
    serialized={}
    for row in result["strategy"]:
        if type(row) is not dict or set(row)!=_ROW_KEYS: raise ValueError("unexpected strategy row fields")
        if row['player'] not in ('sb','bb') or type(row['hand']) is not str: raise ValueError('invalid private policy labels')
        player={"sb":0,"bb":1}.get(row["player"])
        if player is None or row["street"]!="preflop" or row["revealed_board"]!=[]: raise ValueError("strategy leaks or mislabels public information")
        if type(row["history"]) is not list or any(type(x) is not str for x in row["history"]): raise ValueError("invalid public history")
        key=(player,row["hand"],tuple(row["history"]))
        if key in serialized: raise ValueError("duplicate strategy row")
        serialized[key]=row
    exact_policy={}; node_map={}; seen=set()
    def visit(node):
        if isinstance(node,_Terminal):return
        p=node.player
        for hand in hands[p]:
            if not any((hand,x) in priors for x in hands[1]) if p==0 else not any((x,hand) in priors for x in hands[0]): continue
            key=(p,"".join(hand),node.history); row=serialized.get(key)
            if row is None: raise ValueError(f"missing information set {key}")
            if key in seen: continue
            seen.add(key); node_map[key]=node
            actual=row["actions"]
            if type(actual) is not list or len(actual)!=len(node.actions): raise ValueError("action list differs from independent legal tree")
            probs=[]
            for got,want in zip(actual,node.actions):
                if type(got) is not dict or set(got)!=_ACTION_KEYS: raise ValueError("unexpected serialized action fields")
                if any(type(got[field]) not in (int,float) or not isfinite(float(got[field])) for field in ('amount','raise_to')): raise ValueError('invalid numeric action fields')
                if (got["name"],got["amount"],got["raise_to"],got["history_key"])!=(want.name,want.amount,want.target,want.token): raise ValueError("serialized action differs from independent numeric rules")
                q=got["probability"]
                if type(q) not in (int,float) or not isfinite(float(q)) or not 0<=q<=1: raise ValueError("invalid policy probability")
                probs.append(Fraction.from_float(float(q)))
            if not probs or abs(fsum(float(q) for q in probs)-1)>tolerance: raise ValueError("policy row probabilities do not sum to one")
            total=sum(probs,Fraction())
            exact_policy[key]=tuple(q/total for q in probs)
        for child in node.children: visit(child)
    visit(root)
    if set(serialized)!=seen or result["info_sets"]!=len(seen): raise ValueError("unreachable/missing infoset or wrong count")
    pairs=tuple((a,b,p) for (a,b),p in priors.items())
    def payoff(term,a,b,player):
        matched=Fraction.from_float(float(min(term.contributions)))
        sign=(1 if term.winner==0 else -1) if term.winner is not None else eq[(a,b)]
        val=matched*sign
        return val if player==0 else -val
    def policy_value(node,a,b,player):
        if isinstance(node,_Terminal): return payoff(node,a,b,player)
        key=(node.player,"".join((a,b)[node.player]),node.history)
        return sum((q*policy_value(child,a,b,player) for q,child in zip(exact_policy[key],node.children)),Fraction())
    value=sum((p*policy_value(root,a,b,0) for a,b,p in pairs),Fraction())
    def br(node,group,responder):
        if isinstance(node,_Terminal): return sum((p*payoff(node,a,b,responder) for a,b,p in group),Fraction())
        if node.player==responder:
            vals=[br(ch,group,responder) for ch in node.children]
            # payoff() already returns the responder's own utility. Both
            # players therefore maximize here, after hidden hands are summed.
            return max(vals)
        total=Fraction()
        # Keep all worlds together across opponent actions. Splitting into a
        # separate recursive call per hidden opponent hand would let the
        # responder condition its later choice on that private hand.
        for action_index,child in enumerate(node.children):
            child_group=[]
            for a,b,p in group:
                key=(node.player,"".join((a,b)[node.player]),node.history)
                mass=p*exact_policy[key][action_index]
                if mass: child_group.append((a,b,mass))
            if child_group:
                total+=br(child,tuple(child_group),responder)
        return total
    brs=[]
    for responder in (0,1):
        groups={}
        for a,b,p in pairs: groups.setdefault((a,b)[responder],[]).append((a,b,p))
        brs.append(sum((br(root,tuple(g),responder) for g in groups.values()),Fraction()))
    brsb,brbb=brs; valuebb=-value
    gains=(max(Fraction(),brsb-value),max(Fraction(),brbb-valuebb)); gap=sum(gains,Fraction())
    expected=[]
    for (a,b),p in priors.items():
        w,t,l=census[(a,b)]
        expected.append({"sb_hand":"".join(a),"bb_hand":"".join(b),"wins":w,"ties":t,"losses":l,"boards":_BOARDS,"pair_probability":float(p),"pair_probability_fraction":[p.numerator,p.denominator]})
    if type(result['pair_equities']) is not list: raise ValueError('equity rows must be a list')
    actual_equities={}
    for row in result['pair_equities']:
        if type(row) is not dict or set(row)!=_EQUITY_KEYS: raise ValueError('unexpected equity fields')
        if type(row['sb_hand']) is not str or type(row['bb_hand']) is not str: raise ValueError('invalid equity labels')
        if any(type(row[field]) is not int for field in ('wins','ties','losses','boards')): raise ValueError('invalid equity count types')
        exact_prior=row['pair_probability_fraction']
        if type(exact_prior) is not list or len(exact_prior)!=2 or any(type(n) is not int for n in exact_prior): raise ValueError('invalid exact prior encoding')
        if type(row['pair_probability']) not in (int,float) or not isfinite(float(row['pair_probability'])): raise ValueError('invalid equity probability')
        key=(row['sb_hand'],row['bb_hand'])
        if key in actual_equities: raise ValueError('duplicate equity row')
        actual_equities[key]=row
    expected_equities={(row['sb_hand'],row['bb_hand']):row for row in expected}
    if actual_equities!=expected_equities: raise ValueError("serialized pair equities differ from trusted census")
    exact={"value_sb":value,"value_bb":valuebb,"sb_best_response_value":brsb,"bb_best_response_value":brbb,"sb_best_response_gain":gains[0],"bb_best_response_gain":gains[1],"nash_conv":gap,"exploitability":gap/2}
    gaps={}
    for field,want in exact.items():
        got=result[field]
        if type(got) not in (int,float) or not isfinite(float(got)): raise ValueError(f"invalid metric {field}")
        gaps[field]=abs(float(got)-float(want))
        if gaps[field]>tolerance: raise ValueError(f"{field} differs from independent replay by {gaps[field]}")
    output={**{field:float(v) for field,v in exact.items()},
            'value_sb_fraction':[value.numerator,value.denominator],
            'value_bb_fraction':[valuebb.numerator,valuebb.denominator],
            'sb_best_response_fraction':[brsb.numerator,brsb.denominator],
            'bb_best_response_fraction':[brbb.numerator,brbb.denominator],
            'nash_conv_fraction':[gap.numerator,gap.denominator],
            'exploitability_fraction':[(gap/2).numerator,(gap/2).denominator],
            'scalar_absolute_gaps':gaps,'checked_information_sets':len(seen),
            'checked_physical_boards':_BOARDS*len(priors),
            'exact_fraction_replay':{field:[v.numerator,v.denominator] for field,v in exact.items()},
            'tree_counts':tree}
    visit=None; policy_value=None; br=None
    return output


