"""Exact first/second moments for a fixed world's public action histories.

Analytic research oracle only. It visits every literal history to integrate
proposal randomness; it is neither a sampler nor a trainer. Distinct public
histories use independent proposal draws. Repeated information keys within
one selected world are explicitly unsupported.
"""
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType

Q=1<<52
SCHEMES=('uniform-target-average','policy-role-average')


def require(value,message):
    if not value:raise ValueError(message)


@dataclass(frozen=True)
class Node:
    kind:str
    children:tuple=()
    actor:int=-1
    key:tuple=()
    units:tuple=()
    utility:Fraction=Fraction(0) # Always global SB utility.


@dataclass(frozen=True)
class RowMoments:
    units:tuple
    regret_mean:tuple
    regret_second:tuple
    average_mean:tuple
    average_second:tuple
    own_reach:Fraction
    opponent_reach:Fraction


def integrate(game,scheme,budget):
    require(scheme in SCHEMES,'moment explicit proposal/update scheme')
    zero=budget.input(Fraction(0),'moment zero');one=budget.input(Fraction(1),'moment one')
    two=budget.input(Fraction(2),'moment two')
    def add(a,b):return budget.add(a,b,'moment_add')
    def sub(a,b):return budget.sub(a,b,'moment_sub')
    def mul(a,b):return budget.mul(a,b,'moment_mul')
    def div(a,b):return budget.div(a,b,'moment_div')
    def square(a):return mul(a,a)
    def total(values):
        result=zero
        for value in values:result=add(result,value)
        return result
    regrets={};averages={};descriptors={};roots=[];visits=[];slots=0
    counts={name:zero for name in ('visits','reads','terminals','reveals','actions','target_update_rows')}
    inclusions=[{},{}]
    for target in (0,1):
        count=0;seen=set()
        def visit(handle,reaches,prefix_q):
            nonlocal count,slots
            count+=1;require(count<=1105,'moment literal history cap')
            node=game.node(handle)
            require(type(node) is Node and node.kind in ('terminal','reveal','decision'),'moment supported node')
            require(0<=prefix_q<=1 and all(0<=r<=1 for r in reaches),'moment probability carrier domain')
            counts['visits']=add(counts['visits'],prefix_q)
            if node.kind=='terminal':
                require(not node.children and type(node.utility) is Fraction and abs(node.utility)<=8,'moment terminal utility domain')
                utility=budget.input(node.utility if target==0 else -node.utility,'moment terminal')
                counts['terminals']=add(counts['terminals'],prefix_q)
                return utility,square(utility)
            if node.kind=='reveal':
                require(len(node.children)==1 and not node.units,'moment reveal arity')
                counts['reveals']=add(counts['reveals'],prefix_q)
                return visit(node.children[0],reaches,prefix_q)
            k=len(node.children);actor=node.actor
            require(type(actor) is int and actor in (0,1) and 2<=k<=4 and len(node.units)==k and
                    all(type(u) is int and 0<=u<=Q for u in node.units) and sum(node.units)==Q and
                    type(node.key) is tuple and node.key not in seen,'moment visible information/menu partition')
            seen.add(node.key)
            counts['reads']=add(counts['reads'],prefix_q);inclusions[target][node.key]=prefix_q
            action_count=budget.input(Fraction(k if actor==target else 1),'moment action count')
            counts['actions']=add(counts['actions'],mul(prefix_q,action_count))
            if actor==target:counts['target_update_rows']=add(counts['target_update_rows'],prefix_q)
            probabilities=tuple(budget.input(Fraction(u,Q),'moment policy') for u in node.units)
            uniform=budget.input(Fraction(1,k),'moment proposal')
            proposals=(uniform,)*k if scheme=='uniform-target-average' else probabilities
            children=[]
            for i,child in enumerate(node.children):
                next_reach=list(reaches);next_reach[actor]=mul(reaches[actor],probabilities[i])
                q=mul(prefix_q,proposals[i]) if actor!=target else prefix_q
                children.append(visit(child,tuple(next_reach),q))
            mean=total(mul(p,child[0]) for p,child in zip(probabilities,children))
            variances=tuple(sub(second,square(first)) for first,second in children)
            require(all(v>=0 for v in variances),'moment child second moment nonnegative variance')
            if actor==target:
                variance=total(mul(square(p),v) for p,v in zip(probabilities,variances))
                second=add(square(mean),variance)
                own,opponent=reaches[actor],reaches[1-actor]
                if scheme=='policy-role-average':
                    require(prefix_q==opponent,'moment policy-proposal prefix cancellation')
                require(prefix_q>0 or opponent==0,'moment unsupported missing regret support')
                factor=div(square(opponent),prefix_q) if prefix_q else zero
                r=[];r2=[]
                for p,(child_mean,_child_second),v in zip(probabilities,children,variances):
                    difference=sub(child_mean,mean)
                    # Independent sibling future draws: Var(Va - sum pb*Vb).
                    delta_variance=add(variance,mul(sub(one,mul(two,p)),v))
                    require(delta_variance>=0,'moment centered-action variance')
                    r.append(mul(opponent,difference))
                    r2.append(mul(factor,add(square(difference),delta_variance)))
                require(node.key not in regrets and len(regrets)<434,'moment target regret row uniqueness')
                regrets[node.key]=(tuple(r),tuple(r2));descriptors[node.key]=(node.units,own,opponent)
                slots+=k;require(slots<=1039,'moment target regret slot cap')
                if scheme=='uniform-target-average':
                    require(prefix_q>0,'moment full-support average prefix')
                    a=tuple(mul(own,p) for p in probabilities)
                    a2=tuple(div(square(value),prefix_q) for value in a)
                    require(node.key not in averages,'moment average row uniqueness');averages[node.key]=(a,a2)
            else:
                weighted=[]
                for p,q,(_child_mean,child_second) in zip(probabilities,proposals,children):
                    require(q>0 or p==0,'moment opponent proposal support')
                    weighted.append(mul(div(square(p),q),child_second) if q else zero)
                second=total(weighted)
                if scheme=='policy-role-average':
                    own=reaches[actor]
                    require(prefix_q==own,'moment opposite-role own-prefix sampling')
                    a=tuple(mul(own,p) for p in probabilities)
                    a2=tuple(mul(own,square(p)) for p in probabilities)
                    require(node.key not in averages and len(averages)<434,'moment role-average uniqueness')
                    averages[node.key]=(a,a2)
            require(second>=square(mean),'moment value second moment')
            return mean,second
        try:roots.append(visit(game.root,(one,one),one))
        finally:visit=None
        visits.append(count)
    require(set(regrets)==set(averages)==set(descriptors) and roots[0][0]==-roots[1][0],
            'moment complete actor rows and expected zero-sum root')
    result={}
    for key,(r,r2) in regrets.items():
        a,a2=averages[key];units,own,opponent=descriptors[key]
        require(all(second>=square(first) for first,second in (*zip(r,r2),*zip(a,a2))),
                'moment raw row second moments')
        require(total(mul(value,budget.input(Fraction(unit,Q),'moment center policy')) for value,unit in zip(r,units))==0,
                'moment expected regret centers on frozen policy')
        result[key]=RowMoments(units,r,r2,a,a2,own,opponent)
    require(set(inclusions[0])==set(inclusions[1])==set(result),'moment both-target read inclusion keys')
    union=total(sub(add(inclusions[0][key],inclusions[1][key]),mul(inclusions[0][key],inclusions[1][key])) for key in result)
    return {'rows':MappingProxyType(result),'roots':tuple(roots),'analytic_visits':tuple(visits),
            'expected_traversal_counts':MappingProxyType(counts),'expected_unique_read_rows':union,
            'scheme':scheme,'sampled_walks':0,'native_calls':0,'rng_calls':0,'attempted_training':False,'quality_gate':None}


def deterministic_transcript(game,target,scheme,choice,budget):
    """A first/last supported transcript witness, never an RNG sample or training.

    Only the current visible row's menu/units determine the closed choice rule.
    Uniform proposals keep traversing selected zero-policy opponent branches.
    """
    require(type(target) is int and target in (0,1) and scheme in SCHEMES and choice in ('first','last'),
            'transcript explicit target/proposal/choice')
    one=budget.input(Fraction(1),'transcript one');zero=budget.input(Fraction(0),'transcript zero')
    def mul(a,b):return budget.mul(a,b,'transcript_mul')
    def add(a,b):return budget.add(a,b,'transcript_add')
    def sub(a,b):return budget.sub(a,b,'transcript_sub')
    def div(a,b):return budget.div(a,b,'transcript_div')
    def total(values):
        result=zero
        for value in values:result=add(result,value)
        return result
    observed={};regrets={};averages={};choices=[];count=0;zero_policy_choices=0
    def visit(handle,reaches,prefix_q):
        nonlocal count,zero_policy_choices
        count+=1;require(count<=1105,'transcript visit cap');node=game.node(handle)
        require(type(node) is Node,'transcript source type')
        if node.kind=='terminal':
            require(abs(node.utility)<=8 and not node.children,'transcript terminal domain')
            return budget.input(node.utility if target==0 else -node.utility,'transcript payoff')
        if node.kind=='reveal':
            require(len(node.children)==1,'transcript reveal arity');return visit(node.children[0],reaches,prefix_q)
        k=len(node.children);actor=node.actor
        require(node.kind=='decision' and type(actor) is int and actor in (0,1) and 2<=k<=4 and len(node.units)==k and
                all(type(u) is int and 0<=u<=Q for u in node.units) and sum(node.units)==Q and
                node.key not in observed and len(observed)<434,'transcript information/menu contract')
        observed[node.key]=node.units
        p=tuple(budget.input(Fraction(u,Q),'transcript policy') for u in node.units)
        if actor==target:
            values=[]
            for i,child in enumerate(node.children):
                advanced=list(reaches);advanced[actor]=mul(reaches[actor],p[i])
                values.append(visit(child,tuple(advanced),prefix_q))
            mixed=total(mul(probability,value) for probability,value in zip(p,values))
            require(prefix_q>0,'transcript reached prefix support')
            if scheme==SCHEMES[1]:require(prefix_q==reaches[1-actor],'transcript regret prefix cancellation')
            factor=div(reaches[1-actor],prefix_q)
            regrets[node.key]=tuple(mul(factor,sub(value,mixed)) for value in values)
            require(total(mul(r,probability) for r,probability in zip(regrets[node.key],p))==0,'transcript exact regret centering')
            if scheme==SCHEMES[0]:averages[node.key]=tuple(mul(div(reaches[actor],prefix_q),v) for v in p)
            return mixed
        q=(budget.input(Fraction(1,k),'transcript proposal'),)*k if scheme==SCHEMES[0] else p
        supported=[i for i,value in enumerate(q) if value>0]
        require(supported,'transcript nonempty proposal support');selected=supported[0] if choice=='first' else supported[-1]
        if scheme==SCHEMES[1]:
            require(prefix_q==reaches[actor],'transcript average prefix cancellation');averages[node.key]=p
        # Keep separate factors: the probability of an entire branched partial
        # tree can exceed the integer-width cap even when every route fits.
        choices.append((node.key,selected,q[selected]))
        zero_policy_choices+=int(p[selected]==0)
        advanced=list(reaches);advanced[actor]=mul(reaches[actor],p[selected])
        # Do not prune when p[selected] is zero; averages may still need this branch.
        child=visit(node.children[selected],tuple(advanced),mul(prefix_q,q[selected]))
        return mul(div(p[selected],q[selected]),child)
    try:root=visit(game.root,(one,one),one)
    finally:visit=None
    return {'root':root,'regrets':MappingProxyType(regrets),'averages':MappingProxyType(averages),
            'observed':MappingProxyType(observed),'choices':tuple(choices),'visits':count,
            'probability_materialized':False,'zero_policy_opponent_choices':zero_policy_choices,
            'native_calls':0,'rng_calls':0,'attempted_training':False,
            'scope':'Deterministic supported transcript witness, not a draw from q, learning iteration or quality result.'}
