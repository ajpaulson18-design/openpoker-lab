"""Independent exact fixed-river profile and visible-hand response certificate.

The rank/card-vector work model is separate from the unchanged physical oracle.
No production payoff, ranking, tree, trainer or BR code is used.
"""
from bisect import bisect_left,bisect_right
from fractions import Fraction
from math import isfinite
from scripts import turn_river_validation as rules
from scripts import preflop_validation as ranks
from scripts.turn_rational_certificate import _Budget

ZERO=Fraction(0)

class _RankPlan:
    """Immutable sorted rank/card topology and exact query endpoints."""
    def __init__(self, indexes, ranks, query_ranks, budget):
        budget.charge("static_rank_sort_comparisons_upper_bound",len(indexes)*max(1,len(indexes).bit_length()))
        self.indexes=tuple(sorted(indexes,key=lambda i:ranks[i]))
        ordered=tuple(ranks[i] for i in self.indexes)
        self.endpoints={}
        for rank in query_ranks:
            budget.charge("static_rank_query_comparisons_upper_bound",2*max(1,len(ordered).bit_length()))
            self.endpoints[rank]=(bisect_left(ordered,rank),bisect_right(ordered,rank))

class _RankMass:
    def __init__(self, plan, weighted, budget):
        self.budget=budget;self.plan=plan;self.prefix=[ZERO]
        for index in plan.indexes:
            budget.charge("rank_prefix_entries")
            self.prefix.append(budget.add(self.prefix[-1],weighted[index],"rank prefix mass"))
    def masses(self, rank):
        self.budget.charge("rank_query_endpoint_lookup")
        lo,hi=self.plan.endpoints[rank]
        equal=self.budget.add(self.prefix[hi],-self.prefix[lo],"equal rank mass")
        return self.prefix[-1],self.prefix[lo],equal

class ExactRankedRiverLaw:
    """Factorized exact input law and blocker-aware terminal vectors only."""
    def __init__(self, board, oop_range, ip_range, *, max_work=100000,max_depth=64,max_bits=65536):
        self.budget=_Budget(max_work,max_depth,max_bits)
        self.board=rules.cards(board,5)
        self.ranges=(rules.expand_range(oop_range,self.board),rules.expand_range(ip_range,self.board))
        self.hands=tuple(tuple(side) for side in self.ranges)
        self.weights=tuple(tuple(self.budget.fraction(Fraction.from_float(float(side[h])),"input weight") for h in hands) for side,hands in zip(self.ranges,self.hands))
        if any(not side for side in self.hands):raise ValueError("Positive ranges required")
        self.rank=[]
        for side in self.hands:
            own=[]
            for hand in side:
                # Seven-card independent evaluator considers all21 five-card sets.
                self.budget.charge("independent_rank_five_card_upper_bound",21)
                own.append(ranks.independent_rank(self.board+hand))
            self.rank.append(tuple(own))
        self.plans=[];self._index_cache={};self._terminal_cache={}
        for p in (0,1):
            by_card={}
            for i,h in enumerate(self.hands[p]):
                for card in h:
                    self.budget.charge("static_card_topology_entries")
                    by_card.setdefault(card,[]).append(i)
            queries=set(self.rank[1-p])
            self.plans.append((_RankPlan(range(len(self.hands[p])),self.rank[p],queries,self.budget),{c:_RankPlan(v,self.rank[p],queries,self.budget) for c,v in by_card.items()}))
        self.normalizer=ZERO
        self.marginals=[]
        for p in (0,1):
            mass_index=self._indexes(1-p,[Fraction(1)]*len(self.hands[1-p]))
            own=[]
            for i,h in enumerate(self.hands[p]):
                mass=self._compatible(mass_index,h,self.rank[p][i],signed=False)
                own.append(self.budget.multiply(self.weights[p][i],mass,"own compatible raw mass"))
            self.marginals.append(own)
        totals=[]
        for side in self.marginals:
            total=ZERO
            for v in side:total=self.budget.add(total,v,"global normalizer")
            totals.append(total)
        if totals[0]<=0 or totals[0]!=totals[1]:raise ValueError("No compatible physical mass or asymmetric normalization")
        self.normalizer=totals[0]
        self.marginals=tuple(tuple(self.budget.divide(v,self.normalizer,"normalized own marginal") for v in side) for side in self.marginals)

    def _indexes(self,p,reach):
        if len(reach)!=len(self.hands[p]):raise ValueError("Opponent reach dimension differs")
        self.budget.charge("reach_index_key_entries",len(reach))
        for value in reach:
            if not isinstance(value,Fraction) or not ZERO<=value<=1:raise ValueError("Exact reach must lie in[0,1]")
            self.budget.fraction(value,"reach")
        key=(p,tuple(reach))
        if key in self._index_cache:
            self.budget.charge("reach_index_cache_hits")
            return self._index_cache[key]
        weighted=[];identical={}
        for hand,w,value in zip(self.hands[p],self.weights[p],reach):
            self.budget.charge("opponent_index_entries")
            mass=self.budget.multiply(w,value,"opponent weighted reach")
            weighted.append(mass);identical[hand]=mass
        all_plan,card_plans=self.plans[p]
        self.budget.charge("retained_index_cache_slots",len(weighted)+len(all_plan.indexes)+sum(len(v.indexes) for v in card_plans.values())+3*len(card_plans)+2)
        value=(_RankMass(all_plan,weighted,self.budget),{c:_RankMass(v,weighted,self.budget) for c,v in card_plans.items()},identical)
        self._index_cache[key]=value
        return value

    def _compatible(self,index,hand,rank,*,signed):
        total,cards,identical=index
        def query(group):
            if group is None:return ZERO
            if not signed:
                self.budget.charge("total_mass_lookup")
                return group.prefix[-1]
            t,less,equal=group.masses(rank)
            twice=self.budget.multiply(Fraction(2),less,"twice lower rank mass")
            return self.budget.add(self.budget.add(twice,equal,"lower and equal mass"),-t,"signed rank mass")
        value=query(total)
        for card in hand:value=self.budget.add(value,-query(cards.get(card)),"exclude shared card")
        # The same exact holding is subtracted twice; add it once for mass.
        # Its showdown rank is equal, so its signed contribution is exactly0.
        if not signed:value=self.budget.add(value,identical.get(hand,ZERO),"identical holding correction")
        return value

    def terminal_vector(self,node,p,opponent_reach,pot):
        if type(p) is not int or p not in (0,1):raise ValueError("Invalid responding player")
        if not isinstance(node,rules._Terminal) or node.kind not in ("fold","showdown"):raise ValueError("Independent river terminal required")
        if isinstance(pot,bool) or not isinstance(pot,(int,float)) or not isfinite(pot) or pot<=0:raise ValueError("Positive finite pot required")
        if node.kind=="fold" and (type(node.winner) is not int or node.winner not in (0,1)):raise ValueError("Fold winner invalid")
        self.budget.charge("terminal_metadata_entries",2)
        if not isinstance(node.contributions,(tuple,list)) or len(node.contributions)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or v<0 for v in node.contributions):raise ValueError("Terminal contributions must be two finite nonnegative numbers")
        # Preserve the physical oracle's binary64 payoff boundary exactly.
        scale=self.budget.fraction(Fraction.from_float(float(pot/2+min(node.contributions))),"terminal boundary")
        index=self._indexes(1-p,opponent_reach)
        self.budget.charge("terminal_cache_key_entries",len(opponent_reach)+4)
        key=(p,node.kind,node.winner,scale,tuple(opponent_reach))
        if key in self._terminal_cache:
            self.budget.charge("terminal_vector_cache_hits")
            return self._terminal_cache[key]
        self.budget.charge("retained_terminal_cache_slots",len(self.hands[p]))
        out=[]
        for hand,rank,w in zip(self.hands[p],self.rank[p],self.weights[p]):
            self.budget.charge("own_terminal_vector_entries")
            mass=self._compatible(index,hand,rank,signed=node.kind=="showdown")
            if node.kind=="fold" and node.winner!=p:mass=-mass
            value=self.budget.multiply(w,mass,"own weighted terminal mass")
            value=self.budget.multiply(value,scale,"terminal payoff contribution")
            out.append(self.budget.divide(value,self.normalizer,"normalized terminal contribution"))
        self._terminal_cache[key]=tuple(out)
        return self._terminal_cache[key]


def evaluate_ranked_certificate(result, oop_range, ip_range, *, board, config=None,
                                max_work=100000, max_depth=64, max_bits=65536):
    """Exact fixed-river profile and legal own-hand responses without pair worlds.

    Distinct rank/card-vector work model; old physical certificates are unchanged.
    Rejected requests produce no metrics. This is a development audit, not training.
    """
    import json
    from math import fsum
    from scripts.turn_rational_certificate import _normalize_policies,_preflight_tree
    law=ExactRankedRiverLaw(board,oop_range,ip_range,max_work=max_work,max_depth=max_depth,max_bits=max_bits)
    b=law.budget;cfg=rules._config(config,"config")
    class TreeBudget(dict):
        def __setitem__(self,key,value):
            if key=="states":b.charge("independent_tree_build_states")
            super().__setitem__(key,value)
    root=rules._build_street(cfg,board=law.board,budget=TreeBudget(states=0,decisions=0))
    tree_nodes,depth=_preflight_tree(root,b)
    nodes=rules._collect_nodes(root)
    if not isinstance(result,dict):raise ValueError("Complete serialized result required")
    for key,value in (("board",list(law.board)),("runouts",[]),("reachable_runouts",[]),("runout_mode","none")):
        if result.get(key)!=value:raise ValueError("Result public conditioning differs: "+key)
    if result.get("strategy_schema")!="postflop-strategy-v1":raise ValueError("Result strategy schema differs")
    if json.dumps(result.get("config"),sort_keys=True)!=json.dumps(cfg.to_dict(),sort_keys=True):raise ValueError("Result numeric configuration differs")
    for key,expected in (("river_config",cfg.to_dict()),("street_configs",{"river":cfg.to_dict()}),("turn_config",None)):
        if key in result and json.dumps(result[key],sort_keys=True)!=json.dumps(expected,sort_keys=True):raise ValueError("Result configuration alias differs: "+key)
    counts={"public_nodes":len(nodes),"public_states":tree_nodes,"terminal_nodes":tree_nodes-len(nodes),"chance_nodes":0,"tree_actions":sum(len(n.actions) for n in nodes)}
    for key,expected in counts.items():
        if key in result and (type(result[key]) is not int or result[key]!=expected):raise ValueError("Result tree count differs: "+key)
    rows=result.get("strategy")
    if not isinstance(rows,list):raise ValueError("Result strategy must be a list")
    b.charge("serialized_policy_entries",len(rows))
    actual={}
    for row in rows:
        if not isinstance(row,dict) or set(row)!={"player","hand","street","board","history","actions"}:raise ValueError("Malformed strategy row")
        if row["player"] not in ("oop","ip") or type(row["hand"]) is not str or type(row["history"]) is not list or any(type(t) is not str for t in row["history"]):raise ValueError("Malformed information identity")
        key=(0 if row["player"]=="oop" else 1,row["hand"],tuple(row["history"]))
        if key in actual:raise ValueError("Duplicate information row")
        actual[key]=row
    policies={}
    for node in nodes:
        p=node.player
        for hand,marginal in zip(law.hands[p],law.marginals[p]):
            b.charge("expected_information_rows")
            if marginal==0:continue
            key=(p,"".join(hand),node.history)
            row=actual.get(key)
            if row is None:raise ValueError("Missing visible information row")
            if row["street"]!="river" or row["board"]!=list(law.board) or row["history"]!=list(node.history):raise ValueError("Row public history/street differs")
            actions=row["actions"];legal=rules._row_actions(node)
            if not isinstance(actions,list) or len(actions)!=len(legal):raise ValueError("Action coverage differs")
            probabilities=[]
            for action,expected in zip(actions,legal):
                b.charge("validated_action_entries")
                if not isinstance(action,dict) or set(action)!=set(expected)|{"probability"}:raise ValueError("Malformed action")
                for field,value in expected.items():
                    if action[field]!=value or field in ("amount","raise_to") and (isinstance(action[field],bool) or not isinstance(action[field],(int,float)) or not isfinite(action[field])):raise ValueError("Action metadata differs")
                probability=action["probability"]
                if isinstance(probability,bool) or not isinstance(probability,(int,float)) or not isfinite(probability) or not 0<=probability<=1:raise ValueError("Invalid probability")
                probabilities.append(float(probability))
            if abs(fsum(probabilities)-1)>1e-9:raise ValueError("Policy probabilities must sum to one")
            policies[key]=tuple(probabilities)
    if set(policies)!=set(actual):raise ValueError("Extra information row")
    # Compatible-pair count from card incidence, with identical-hand correction.
    counts=[]
    for p in (0,1):
        other=law.hands[1-p];cards={};same=set(other)
        for hand in other:
            for c in hand:
                b.charge("compatible_pair_card_entries")
                cards[c]=cards.get(c,0)+1
        count=0
        for h in law.hands[p]:
            b.charge("compatible_pair_hand_entries")
            count+=len(other)-cards.get(h[0],0)-cards.get(h[1],0)+(h in same)
        counts.append(count)
    if counts[0]!=counts[1]:raise ValueError("Pair count asymmetric")
    rules._validate_count_metadata(result,world_count=counts[0],pair_count=counts[0],info_count=len(policies),board_length=5)
    normalized,ledger,adjustment,canonical=_normalize_policies(policies,result,b)
    def row(node,p,index):
        key=(p,"".join(law.hands[p][index]),node.history)
        if key in normalized:return normalized[key]
        if law.marginals[p][index]!=0:raise ValueError("Missing positive information row")
        return (Fraction(1,len(node.children)),)*len(node.children)
    def evaluate(p,best):
        other=1-p
        def visit(node,reach):
            b.charge("vector_tree_visits")
            if isinstance(node,rules._Terminal):return law.terminal_vector(node,p,reach,cfg.pot)
            n=len(law.hands[p]);out=[ZERO]*n
            if node.player==other:
                for a,child in enumerate(node.children):
                    b.charge("opponent_policy_vector_entries",len(reach))
                    changed=tuple(b.multiply(v,row(node,other,i)[a],"opponent sequence reach") for i,v in enumerate(reach))
                    values=visit(child,changed)
                    for i,v in enumerate(values):out[i]=b.add(out[i],v,"opponent branch sum")
                return tuple(out)
            actions=[visit(child,reach) for child in node.children]
            b.charge("own_action_vector_entries",n*len(actions))
            for i in range(n):
                if best:out[i]=max(values[i] for values in actions)
                else:
                    for a,values in enumerate(actions):out[i]=b.add(out[i],b.multiply(row(node,p,i)[a],values[i],"profile own action"),"profile action sum")
            return tuple(out)
        try:values=visit(root,(Fraction(1),)*len(law.hands[other]))
        finally:visit=None
        total=ZERO
        for v in values:total=b.add(total,v,"own hand final sum")
        return total
    value=evaluate(0,False);oop=evaluate(0,True);ip=evaluate(1,True)
    lower=-ip;upper=oop
    if not lower<=value<=upper:raise ValueError("Exact legal-response bounds fail")
    g0=b.add(oop,-value,"OOP response gain");g1=b.add(ip,value,"IP response gain")
    nc=b.add(g0,g1,"NashConv");ex=b.divide(nc,Fraction(2),"exploitability")
    metrics={"value_oop":value,"value_ip":-value,"oop_best_response_value":oop,"ip_best_response_value":ip,"oop_best_response_gain":g0,"ip_best_response_gain":g1,"nash_conv":nc,"exploitability":ex}
    return {"schema":"independent-ranked-river-certificate-v1","work_model":"independent-rank-card-vectors-v1","metrics":metrics,"lower_value_bound":lower,"upper_value_bound":upper,"threshold_met":nc<=Fraction(1,1000),"normalization_ledger":ledger,"normalized_policy_rows":canonical,"max_row_adjustment":adjustment,"tree_nodes":tree_nodes,"tree_depth":depth,"compatible_pairs":counts[0],"worlds_materialized":0,"information_sets":len(policies),"work":b.work,"work_by_kind":dict(sorted(b.counters.items())),"maximum_fraction_bits":b.max_observed_bits,"work_limit":b.max_work,"depth_limit":b.max_depth,"fraction_bit_limit":b.max_bits}
