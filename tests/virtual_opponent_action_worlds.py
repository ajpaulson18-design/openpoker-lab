"""Conditional full52-world moment study against the unchanged literal raw walk.

Each sealed reference range contains exactly the selected physical hand. It
authenticates the conditional world, not the full1326 chance expectation. No
single-pair prior is used as a weight in the sampled-update proof. Composition
with the separately verified full-range joint chance law remains explicit.
"""
from fractions import Fraction
from math import comb
import struct

from scripts.matrix_free_certificate_budget import Budget
from tests.full_deck_public_chance_reference import PROOF9,PROOF_LABELS,proof_ranges
from tests.virtual_frozen_update_reference import frozen_profile_probabilities
from tests.virtual_weighted_joint_reference import LIMITS,forecast as law_forecast
from tests.virtual_weighted_joint_raw_reference import Request,Policy,DR,DA,Q,reveal,SOURCE_WORK,SOURCE_BITS,RAW_WORK,RAW_BITS
from tests.virtual_opponent_action_moments import Node,SCHEMES,integrate,deterministic_transcript,require

CASE_PAIRS=((0,0),(0,1),(1,0))
WIRE_LIMIT=2_135_476
SIDE_LIMIT=1_048_576
SUMMARY_LIMIT=65536
MOMENT_LIMITS={'work':16_000_000,'entries':500_000,'created_bits':1_000_000_000,'integer_bits':4096}


def plan(case_count=3,limits=None):
    require(type(case_count) is int and 1<=case_count<=3,'moment study case count')
    require(limits is None or type(limits) is dict and set(limits)<=set(LIMITS),'moment study reduce-only limits')
    chosen=dict(LIMITS)
    for name,value in (limits or {}).items():
        require(type(value) is int and 0<value<=LIMITS[name],'moment study limit value');chosen[name]=value
    law=law_forecast(52,(1,1))
    source={'work':law['work']+SOURCE_WORK+RAW_WORK,'entries':law['entries']+131072+500000,
            'created_bits':law['created_bits']+SOURCE_BITS+RAW_BITS,'integer_bits':4096}
    output_bytes=WIRE_LIMIT+SIDE_LIMIT+SUMMARY_LIMIT
    complete={'work':case_count*(source['work']+MOMENT_LIMITS['work']+16*output_bytes),
              'entries':source['entries']+MOMENT_LIMITS['entries']+(case_count+2)*((output_bytes+7)//8),
              'created_bits':case_count*(source['created_bits']+MOMENT_LIMITS['created_bits']+16*output_bytes),
              'integer_bits':4096}
    require(all(complete[k]<=chosen[k] for k in LIMITS),'moment complete source/arithmetic/I-O study rejected')
    return {'source_case':source,'complete':complete,'limits':chosen,'case_count':case_count,'wire_limit':WIRE_LIMIT,
            'source_scope':'One selected physical hand per seat on full52; conditional operator only.',
            'scope':'Complete bounded reference/I-O reservation. No native admission or full1326 moment-law proof.'}


def board_rank(hands,board):
    require(type(hands) is tuple and len(hands)==2 and all(type(h) is tuple and len(h)==2 for h in hands) and
            len(set((*hands[0],*hands[1])))==4 and type(board) is tuple and len(board)==5 and len(set(board))==5 and
            tuple(sorted(board[:3]))==board[:3] and not set(board)&set((*hands[0],*hands[1])),'moment physical board domain')
    available=[c for c in range(52) if c not in (*hands[0],*hands[1])]
    indices=[available.index(c) for c in board[:3]];rank=0;first=0
    for position,index in enumerate(indices):
        for skipped in range(first,index):rank+=comb(47-skipped,2-position)
        first=index+1
    tail=[c for c in available if c not in board[:3]];turn=tail.index(board[3]);tail.remove(board[3]);river=tail.index(board[4])
    value=(rank*45+turn)*44+river
    require(0<=value<34_246_080,'moment full52 board rank boundary');return value


class FrozenWorld:
    def __init__(self,request,world,rows):
        self.request=request;self.world=world;self.rows=rows;self.root=(request.template.root,())
    def node(self,handle):
        source,history=handle;node=self.request.nodes[source]
        if node.phase in ('fold','showdown'):
            sign=self.world.showdown_sign if node.phase=='showdown' else (1 if node.state.winner==0 else -1)
            return Node('terminal',utility=self.request.stakes[source]*sign)
        if node.phase=='reveal':
            require(len(node.edges)==1,'moment source reveal arity')
            token=reveal(self.world.board,node.state.board_length)
            return Node('reveal',children=((node.edges[0].child,(*history,token)),))
        actor=node.state.player;key=(actor,self.world.holding_indices[actor],history)
        row=self.rows[key];menu=tuple(edge.token for edge in node.edges)
        require(node.phase=='decision' and row.source==source and row.menu==menu and len(row.units)==len(menu),
                'moment frozen literal policy/source binding')
        return Node('decision',tuple((edge.child,(*history,edge.token)) for edge in node.edges),actor,key,row.units)


def profile(request,world,hands,kind):
    require(kind in ('uniform','visible-hash'),'moment fixed policy profile')
    if kind=='uniform':return Policy(request,{})
    rows={};visits=0
    def visit(source,history):
        nonlocal visits
        visits+=1;require(visits<=1105,'moment profile source cap');node=request.nodes[source]
        if node.phase in ('fold','showdown'):return
        if node.phase=='reveal':
            visit(node.edges[0].child,(*history,reveal(world.board,node.state.board_length)));return
        actor=node.state.player;menu=tuple(edge.token for edge in node.edges)
        probabilities=frozen_profile_probabilities(actor,hands[actor],history,menu)
        units=tuple(int(p*Q) for p in probabilities)
        require(all(Fraction(u,Q)==p for u,p in zip(units,probabilities)),'moment exact frozen Q52 profile')
        rows[(actor,world.holding_indices[actor],history)]=units
        for edge in node.edges:visit(edge.child,(*history,edge.token))
    try:visit(request.template.root,())
    finally:visit=None
    return Policy(request,rows)


def scaled_number(value,denominator,words,signed):
    require(type(value) is Fraction and denominator%value.denominator==0,'moment exact carrier denominator')
    number=value.numerator*(denominator//value.denominator)
    require((signed or number>=0) and abs(number).bit_length()<=64*words-int(signed),'moment carrier magnitude')
    return number


def scaled(value,denominator,words,signed):
    return scaled_number(value,denominator,words,signed).to_bytes(8*words,'little',signed=signed)


def witness(game,literal,policy_index,scheme_index,choice,meter):
    scheme=SCHEMES[scheme_index];samples=[deterministic_transcript(game,t,scheme,choice,meter) for t in (0,1)]
    observed={};r={};a={}
    for sample in samples:
        require(sample['probability_materialized'] is False,'witness no global proposal product')
        require(not set(r)&set(sample['regrets']) and not set(a)&set(sample['averages']),'witness role disjointness')
        r.update(sample['regrets']);a.update(sample['averages'])
        for key,units in sample['observed'].items():
            require(key not in observed or observed[key]==units,'witness frozen shared-row units');observed[key]=units
    require(len(observed)<=204 and sum(len(s['choices']) for s in samples)<=204,'witness structural worst bound')
    data=bytearray(b'OPLOWT01')
    def words(values):data.extend(struct.pack('<'+'Q'*len(values),*values))
    slots=sum(map(len,observed.values()))
    words((1,policy_index,scheme_index,int(choice=='last'),len(observed),slots,len(samples[0]['choices']),len(samples[1]['choices']),0,
           samples[0]['visits'],samples[1]['visits']))
    max_r=max_a=0
    for sample in samples:
        data.extend(scaled(sample['root'],DR,11,True))
        if scheme_index==1:
            require(abs(sample['root'])<=8,'witness role root bound')
            scaled_number(sample['root'],1<<365,7,True)
    for key in sorted(observed,key=lambda k:(k[0],k[1],literal[k].ordinal)):
        units=observed[key];row=literal[key];rr=r.get(key,(Fraction(0),)*len(units));aa=a.get(key,(Fraction(0),)*len(units))
        mass=Fraction(0);center=Fraction(0);probabilities=tuple(meter.input(Fraction(u,Q),'witness policy') for u in units)
        for value in aa:mass=meter.add(mass,value,'witness average mass')
        for value,p in zip(rr,probabilities):center=meter.add(center,meter.mul(value,p,'witness regret product'),'witness regret sum')
        require(center==0 and all(value==meter.mul(mass,p,'witness average ratio') for value,p in zip(aa,probabilities)),
                'witness pointwise regret center and average policy ratio')
        words((key[0],key[1],row.ordinal,row.source,len(units)))
        for u,rv,av in zip(units,rr,aa):
            words((u,));data.extend(scaled(rv,DR,11,True));data.extend(scaled(av,DA,6,False))
            if scheme_index==1:
                require(abs(rv)<=16 and 0<=av<=1,'witness role raw bounds')
                nr=scaled_number(rv,1<<365,7,True);na=scaled_number(av,Q,1,False)
                max_r=max(max_r,abs(nr).bit_length());max_a=max(max_a,na.bit_length())
    for target,sample in enumerate(samples):
        for key,selected,q in sample['choices']:
            require(q>0 and q.numerator<Q+1 and q.denominator<Q+1,'witness bounded individual proposal factor')
            words((target,key[0],key[1],literal[key].ordinal,selected,q.numerator,q.denominator))
    require(len(data)<=SIDE_LIMIT,'witness side byte bound');struct.pack_into('<Q',data,8+8*8,len(data))
    return bytes(data),{'profile':policy_index,'scheme':scheme,'choice':choice,'observed_rows':len(observed),'slots':slots,
        'visits':[s['visits'] for s in samples],'proposal_factors':sum(len(s['choices']) for s in samples),
        'probability_materialized':False,'role_compact_denominators_verified':scheme_index==1,
        'role_observed_regret_bits':max_r,'role_observed_average_bits':max_a,
        'zero_policy_opponent_choices':sum(s['zero_policy_opponent_choices'] for s in samples),
        'scope':'A deterministic supported transcript witness, not a draw, native update or quality result.'}


def run_case(index,limits=None):
    # All scalar resource equations and selectors precede range/source/rank preparation.
    require(type(index) is int and 0<=index<3,'moment case selector')
    admission=plan(1,limits)
    ranges=proof_ranges();pair=CASE_PAIRS[index];hands=tuple(ranges[a][pair[a]][0] for a in (0,1))
    flop=tuple(sorted(PROOF_LABELS[6:]));tail=tuple(sorted(set(PROOF9)-set((*hands[0],*hands[1],*flop))))
    require(len(tail)==2,'moment fixed physical tail');board=(*flop,*tail);rank=board_rank(hands,board)
    def bits(value):return int.from_bytes(struct.pack('>d',float(value)),'big')
    request=Request(tuple(range(52)),tuple(((hand,bits(1)),) for hand in hands))
    require(dict(request.forecast)==admission['source_case'],'moment unchanged literal reference admission')
    world=request.law.decode(0,rank)
    require(world.board==board and world.holding_indices==(0,0),'moment independent physical world/rank verification')
    meter=Budget(MOMENT_LIMITS);meter.entries(450000,'moment analytic tables/source/encoder scratch')
    wire=bytearray(b'OPLOAM01');reports=[];visibility={};zero_own=zero_opponent=0
    side=bytearray(b'OPLOAW01'+struct.pack('<4Q',1,index,4,0));witnesses=[];own_depths=None
    def words(values):wire.extend(struct.pack('<'+'Q'*len(values),*values))
    words((1,index,52,1,1,rank,*hands[0],*hands[1],*board,world.showdown_sign+1,4,434,1039,625,364))
    for policy_index,kind in enumerate(('uniform','visible-hash')):
        frozen=profile(request,world,hands,kind);literal,root=request.one_sample(world,frozen)
        depths=tuple(1+max(row.prior_own_actions for key,row in literal.items() if key[0]==actor) for actor in (0,1))
        require(max(depths)<=7 and (own_depths is None or own_depths==depths),'moment source own-action depth envelope')
        own_depths=depths
        game=FrozenWorld(request,world,literal)
        for scheme_index,scheme in enumerate(SCHEMES):
            result=integrate(game,scheme,meter);rows=result['rows']
            require(len(rows)==434 and sum(len(row.units) for row in rows.values())==1039 and
                    result['analytic_visits']==(1105,1105),'moment complete four-street coverage')
            require(tuple(value[0] for value in result['roots'])==(Fraction(root,DR),Fraction(-root,DR)),
                    'moment both expected roots match unchanged scalar authority')
            if scheme_index==1:require(all(second<=64 for _mean,second in result['roots']),'moment role root second-moment bound')
            begin=len(wire);wire.extend(b'OPLOMT01')
            words((1,policy_index,scheme_index,434,1039,0,1105,1105,meter.work,meter.created_bits))
            for first,second in result['roots']:
                wire.extend(scaled(first,DR,11,True));wire.extend(scaled(second,DR*DR,21,False))
            variance_r=variance_a=0;mean_r2=mean_a2=0
            for key in sorted(rows,key=lambda k:(k[0],k[1],literal[k].ordinal)):
                row=rows[key];expected=literal[key]
                if scheme_index==1:
                    require(all(v<=256 for v in row.regret_second) and all(v<=1 for v in row.average_second),
                            'moment role marginal second-moment bounds')
                require(row.units==expected.units and tuple(p*DR for p in row.regret_mean)==expected.regrets and
                        tuple(p*DA for p in row.average_mean)==expected.averages,'moment all-coordinate R/A means match literal authority')
                if scheme_index==0:
                    zero_own+=int(row.own_reach==0 and any(row.regret_mean))
                    zero_opponent+=int(row.opponent_reach==0 and any(row.average_mean))
                words((key[0],key[1],expected.ordinal,expected.source,len(row.units)))
                for unit,r,r2,a,a2 in zip(row.units,row.regret_mean,row.regret_second,row.average_mean,row.average_second):
                    nr=scaled_number(r,DR,11,True);nr2=scaled_number(r2,DR*DR,21,False)
                    na=scaled_number(a,DA,6,False);na2=scaled_number(a2,DA*DA,12,False)
                    # Sum on fixed carriers, avoiding repeated large rational GCDs.
                    meter._reserve((1344,1344,2688,768,768,1536,1344,1344,1344,1344),
                                   'moment integer statistics')
                    rr=nr*nr;aa=na*na
                    require(nr2>=rr and na2>=aa,'moment integer variance nonnegative')
                    mean_r2+=rr;mean_a2+=aa;variance_r+=nr2-rr;variance_a+=na2-aa
                    require(max(mean_r2.bit_length(),mean_a2.bit_length(),variance_r.bit_length(),variance_a.bit_length())<=1344,
                            'moment aggregate statistics width')
                    words((unit,));wire.extend(nr.to_bytes(88,'little',signed=True));wire.extend(nr2.to_bytes(168,'little'))
                    wire.extend(na.to_bytes(48,'little'));wire.extend(na2.to_bytes(96,'little'))
                length=(expected.ordinal>>30)&7
                if scheme_index==0 and length in (0,3):
                    visibility[(policy_index,key[0],expected.ordinal)]=(row.units,expected.averages)
            size=len(wire)-begin
            require(size==441872,'moment fixed table byte census')
            struct.pack_into('<Q',wire,begin+8+5*8,size)
            def fraction(value,denominator):
                value=meter.input(Fraction(value,denominator),'moment aggregate fraction')
                return {'numerator':value.numerator,'denominator':value.denominator}
            reports.append({'profile':kind,'scheme':scheme,'rows':len(rows),'slots':1039,
                'expected_traversal_counts':{name:{'numerator':v.numerator,'denominator':v.denominator} for name,v in result['expected_traversal_counts'].items()},
                'expected_unique_read_rows':{'numerator':result['expected_unique_read_rows'].numerator,'denominator':result['expected_unique_read_rows'].denominator},
                'regret_variance_sum':fraction(variance_r,DR*DR),'average_variance_sum':fraction(variance_a,DA*DA),
                'regret_mean_square_sum':fraction(mean_r2,DR*DR),'average_mean_square_sum':fraction(mean_a2,DA*DA),
                'scope':'Conditional selected-world sampling variance only. No global chance variance or quality inference.'})
            piece,receipt=witness(game,literal,policy_index,scheme_index,'first' if policy_index==0 else 'last',meter)
            side.extend(piece);witnesses.append(receipt)
    struct.pack_into('<Q',side,8+3*8,len(side));require(len(side)<=SIDE_LIMIT,'moment complete witness side bound')
    wire.extend(b'OPLOMF01');words((meter.work,meter.logical_entries,meter.created_bits,meter.max_forecast_bits,4))
    require(len(wire)<=WIRE_LIMIT and meter.work<=MOMENT_LIMITS['work'] and meter.created_bits<=MOMENT_LIMITS['created_bits'],
            'moment complete arithmetic/wire resource bounds')
    report={'case':index,'hands':hands,'board':board,'showdown_sign':world.showdown_sign,'admission':admission,
            'tables':reports,'witnesses':witnesses,'source_max_own_actions_by_actor':own_depths,
            'role_compact_denominator_powers':{'regret':365,'average':52},
            'zero_own_nonzero_regret_rows':zero_own,'zero_opponent_nonzero_average_rows':zero_opponent,
            'moment_resource_accounting':{'work':meter.work,'entries':meter.logical_entries,'created_bits':meter.created_bits,'integer_bits':meter.max_forecast_bits},
            'native_calls':0,'rng_calls':0,'attempted_training':False,'quality_gate':None,
            'scope':'Named full52 conditional-world R/A first/second moments with selected-hand range witnesses. No full1326 moment-law admission, sampler, native training, convergence or quality.'}
    return bytes(wire),report,visibility,bytes(side)
