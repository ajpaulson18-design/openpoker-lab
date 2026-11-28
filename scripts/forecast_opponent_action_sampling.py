"""Structural work/encounter worksheet for a full-support uniform menu proposal.

Research only: no sampled update operator, policy, RNG, native training,
performance, quality or longer-lifetime admission is implemented here.
"""
import argparse
from collections import Counter
from fractions import Fraction
from functools import lru_cache
from math import comb

CAPS={'work':500_000_000,'entries':8_000_000,'created_bits':16_000_000_000,'integer_bits':4096}
RESERVED={'work':80_000_000,'entries':262144,'created_bits':2_000_000_000,'integer_bits':4096}
SOURCE_WORK=43_000_000
METRICS=('visits','reads','terminals','reveals','actions','target_update_rows')
MAX_OBSERVATIONS=1_000_000_000


def need(value,message):
    if not value:raise ValueError(message)


def bounded(value):
    value=Fraction(value)
    need(max(abs(value.numerator).bit_length(),value.denominator.bit_length())<=256,'worksheet scalar256-bit boundary')
    return value


def occupancy(cells,probability,observations):
    """Outward integer bounds for cells*(1-(1-probability/cells)**T)."""
    need(type(cells) is int and cells>0 and type(observations) is int and 1<=observations<=MAX_OBSERVATIONS,
         'worksheet occupancy domain')
    need(type(probability) is Fraction and 0<probability<=1,'worksheet probability domain')
    first=bounded(observations*probability)
    pair=bounded(Fraction(observations*(observations-1),2*cells)*probability**2)
    cauchy=bounded(Fraction(observations*cells)*probability/(cells+(observations-1)*probability))
    lower=max(Fraction(0),bounded(first-pair),cauchy);upper=min(Fraction(cells),first)
    need(lower<=upper,'worksheet occupancy ordering')
    return {'lower':lower.numerator//lower.denominator,'upper':-(-upper.numerator//upper.denominator)}


def encoded(value):
    value=bounded(value);return {'numerator':value.numerator,'denominator':value.denominator}


def forecast(observations=(2,100,1000,1_000_000),*,deck_cards=52,limits=None):
    # Complete scalar admission precedes imports/Template/private preparation.
    need(type(observations) is tuple and 0<len(observations)<=16 and
         all(type(t) is int and 1<=t<=MAX_OBSERVATIONS for t in observations),'worksheet observation domain')
    need(type(deck_cards) is int and 9<=deck_cards<=52,'worksheet deck domain')
    need(limits is None or type(limits) is dict and set(limits)<=set(CAPS),'worksheet reduce-only limits')
    chosen=dict(CAPS)
    for key,value in (limits or {}).items():
        need(type(value) is int and 0<value<=CAPS[key],'worksheet reduce-only limit value');chosen[key]=value
    need(all(RESERVED[key]<=chosen[key] for key in CAPS),'worksheet complete request rejected before source')
    from scripts.matrix_free_certificate_budget import Budget
    from tests.virtual_betting_template_reference import build_reference_template
    from tests.virtual_frozen_update_reference import _template_case
    parent_budget=Budget(chosen);parent_budget.charge('opponent_proposal_reference_reserved',RESERVED['work'])
    parent_budget.entries(RESERVED['entries']-2,'source/scalar/returned-table reservation')
    parent_budget.created_bits=RESERVED['created_bits'];parent_budget.max_forecast_bits=RESERVED['integer_bits']
    source_budget=Budget({'work':SOURCE_WORK,'entries':131072,'created_bits':1_000_000_000,'integer_bits':4096})
    template=build_reference_template(_template_case(),rule_budget=source_budget);nodes=template.nodes
    need(len(nodes)==388 and sum(len(n.edges) for n in nodes)==410,'worksheet fixed source geometry')
    @lru_cache(maxsize=None)
    def cost(source,target):
        node=nodes[source];expected=[Fraction(0)]*6;worst=[0]*6;expected[0]=1;worst[0]=1
        if node.phase in ('fold','showdown'):expected[2]=1;worst[2]=1
        elif node.phase=='reveal':
            need(len(node.edges)==1,'worksheet reveal shape');expected[3]=1;worst[3]=1
            below,bound=cost(node.edges[0].child,target)
            expected=[a+b for a,b in zip(expected,below)];worst=[a+b for a,b in zip(worst,bound)]
        else:
            need(node.phase=='decision' and 2<=len(node.edges)<=4,'worksheet decision shape')
            actor=node.state.player;expected[1]=1;worst[1]=1
            target_node=actor==target;expected[5]=int(target_node);worst[5]=int(target_node)
            count=len(node.edges) if target_node else 1;expected[4]=count;worst[4]=count
            children=[cost(edge.child,target) for edge in node.edges]
            for metric in range(6):
                expected[metric]+=sum((row[0][metric] for row in children),Fraction(0))/(1 if target_node else len(children))
                worst[metric]+=sum(row[1][metric] for row in children) if target_node else max(row[1][metric] for row in children)
        return tuple(map(bounded,expected)),tuple(worst)
    roots=[cost(template.root,target) for target in (0,1)]
    one=[sum((r[0][i] for r in roots),Fraction(0)) for i in range(6)]
    worst=[sum(r[1][i] for r in roots) for i in range(6)]
    paths=[];visits=reveals=terminals=actions=0;by_street=Counter();max_inverse=[1,1];max_prefix_inverse=1
    def visit(source,inverses):
        nonlocal visits,reveals,terminals,actions,max_prefix_inverse
        visits+=1;need(visits<=1105,'worksheet literal occurrence cap')
        node=nodes[source]
        if node.phase in ('fold','showdown'):
            terminals+=1
            for target in (0,1):max_inverse[target]=max(max_inverse[target],inverses[1-target])
            return
        if node.phase=='reveal':reveals+=1;visit(node.edges[0].child,inverses);return
        actor=node.state.player;street=node.street;by_street[actor,street]+=1
        q_target=Fraction(1,inverses[1-actor]);q_other=Fraction(1,inverses[actor])
        union=bounded(q_target+q_other-q_target*q_other)
        paths.append((actor,street,q_target,union));max_prefix_inverse=max(max_prefix_inverse,inverses[1-actor])
        for edge in node.edges:
            actions+=1;next_inverse=list(inverses);next_inverse[actor]*=len(node.edges)
            visit(edge.child,tuple(next_inverse))
    visit(template.root,(1,1))
    need((visits,actions,reveals,terminals,len(paths))==(1105,1039,65,606,434),'worksheet independent literal geometry')
    need(all(by_street[a,s]==n for a in (0,1) for s,n in zip((0,3,4,5),(3,16,58,140))),'worksheet both-seat path census')
    need(one[5]==sum((p[2] for p in paths),Fraction(0)),'worksheet DP/target-inclusion equality')
    union=bounded(sum((p[3] for p in paths),Fraction(0)))
    public={0:1,3:comb(deck_cards,3),4:comb(deck_cards,3)*(deck_cards-3),5:comb(deck_cards,3)*(deck_cards-3)*(deck_cards-4)}
    own={s:comb(deck_cards,2)*(1 if s==0 else comb(deck_cards-2,3)*(1 if s==3 else deck_cards-5)*(1 if s<5 else deck_cards-6)) for s in public}
    lifetime=[]
    for count in observations:
        totals={name:{'lower':0,'upper':0} for name in ('catalog_public_blocks','catalog_seen_rows','target_update_encounters','full_walk_seen_rows')}
        for actor,street,probability,read_union in paths:
            for name,cells,p in (('catalog_public_blocks',public[street],read_union),('catalog_seen_rows',own[street],read_union),
                                 ('target_update_encounters',own[street],probability),('full_walk_seen_rows',own[street],Fraction(1))):
                interval=occupancy(cells,p,count)
                for endpoint in interval:totals[name][endpoint]+=interval[endpoint]
        lifetime.append({'observations':count,**totals})
    r_single=16*max(max_inverse)*(1<<625);a_single=max_prefix_inverse*(1<<364)
    scalar_work=4096*cost.cache_info().misses+1024*visits+1024*len(observations)*len(paths)*4
    need(cost.cache_info().misses<=776 and source_budget.work+scalar_work<=RESERVED['work'],
         'worksheet source/scalar work exceeds prepaid complete request')
    return {'status':'uniform-menu-opponent-proposal-structural-worksheet','deck_cards':deck_cards,
        'proposal':'Each target expands all own actions and samples an opponent menu uniformly with q=1/K. Two target passes share the world; proposal draws are independent across full histories. This is not policy-proportional external sampling.',
        'expected_two_target_counts':{name:encoded(value) for name,value in zip(METRICS,one)},
        'componentwise_two_target_worst_bounds':dict(zip(METRICS,worst)),
        'expected_unique_read_rows_one_world':encoded(union),
        'literal_full_walk_counts':{'visits':visits,'actions':actions,'reveals':reveals,'terminals':terminals,'reads':len(paths)},
        'inverse_proposal_bounds':{'full_opponent_path_by_target':max_inverse,'opponent_prefix_at_target_row':max_prefix_inverse},
        'hypothetical_carrier_magnitude_bits':{'single_regret':r_single.bit_length(),'two_regrets':(2*r_single).bit_length(),
            'single_average':a_single.bit_length(),'two_averages':(2*a_single).bit_length(),
            'regret_denominator_power':625,'average_denominator_power':364},
        'iid_uniform_joint_world_encounters':lifetime,
        'complete_reference_reservation':RESERVED,'source_work':source_budget.work,'numeric_template_nodes':len(nodes),
        'modeled_source_plus_scalar_work':source_budget.work+scalar_work,
        'resource_accounting':{'work':parent_budget.work,'entries':parent_budget.logical_entries,
            'created_bits':parent_budget.created_bits,'integer_bits':parent_budget.max_forecast_bits},
        'attempted_training':False,'native_calls':0,'rng_calls':0,'quality_gate':None,'native_admission':False,
        'scope':'Exact structural menu-law costs and outward encounter expectations only. Lifetime assumes iid uniform physical worlds and independent fixed uniform menu proposals, not evolving policy proposals. Target-role averaging would require inverse proposal correction and a separate all-slot expectation/variance proof. No sampler/update implementation, timing, numerical-retention, native lifetime, eleven-card or NLHE quality admission.'}


if __name__=='__main__':
    import json
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--observations',type=int,nargs='+',default=[2,100,1000,1_000_000])
    parser.add_argument('--deck-cards',type=int,default=52);args=parser.parse_args()
    print(json.dumps(forecast(tuple(args.observations),deck_cards=args.deck_cards),indent=2))
