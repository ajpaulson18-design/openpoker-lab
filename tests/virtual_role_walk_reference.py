"""Direct literal ticket transcripts and full-range chance; no native helpers."""
from fractions import Fraction
from itertools import combinations
from types import MappingProxyType
import struct

from scripts.matrix_free_certificate_budget import Budget
from tests.virtual_weighted_joint_reference import LIMITS,forecast as law_forecast,build_law
from tests.virtual_betting_template_reference import build_reference_template
from tests.virtual_frozen_update_reference import _template_case
from tests.full_deck_public_chance_reference import card_name
from tests.opponent_role_epoch_reference import forecast as role_forecast,allocate,uniform
from tests.virtual_joint_two_epoch_forecast_reference import copy,add,multiply

Q=1<<52
D=1<<365
DR=1<<625
DA=1<<364
OUTPUT=549280
INPUT=4096
SUMMARY=16384
SAMPLE={'work':1_000_000,'entries':500000,'created_bits':227840000,'integer_bits':4096}
RULES=('first','last','middle','alternating')


def need(condition,message):
    if not condition:raise ValueError(message)


def resources():
    role=role_forecast();blocks=408;menus=408;lookups=1836
    cat_words=1024+32*blocks+320*menus+21*blocks
    cat_work=1024+8*blocks+8*menus+lookups*(512+256*20+32*(blocks+1).bit_length()+8*21)
    raw=(127*(32+copy(369)),327*(8+multiply(369,53)+add(423)+copy(423))+76*(64+copy(423)+copy(369)+2*7),
         327*(64+add(370)+copy(370)+512),204*(64+16*4),1024+204*256+816*512,
         512+256*367+204*(256+16*4)+8*1105)
    history=4096*1105+1280+2*(48*327+80*41+16+8*367+8*204)+role[1]+role[10]
    chance=65536+16384*2652+2*(12288+64*1326+256*(1326).bit_length())
    component=role[7]+role[8]+role[0];parent=1040000+4096+2*sum(raw)
    work=43000000+cat_work+history+chance+component+parent+16*(OUTPUT+INPUT)
    raw_entries=56*204+8*204+1105+64*19+64
    entries=131072+cat_words+role[5]+12000+256+(32*1105+1)+16384+raw_entries+OUTPUT+4096
    payload=131072*64+64*cat_words+role[6]+(1<<20)+8192+8*(1<<20)+(1<<22)+3140970+8*OUTPUT+4096*64+32*181
    need(work<=500000000 and entries<=2000000 and payload<=1<<30 and history<=42000000 and
         chance<=110000000 and component<=75000000 and parent<=115000000 and OUTPUT<=2100000,
         'direct role native complete request envelope')
    return {'work':work,'entries':entries,'payload':payload,'output':OUTPUT,'input':INPUT,
        'catalog_work':cat_work,'history_work':history,'chance_work':chance,'component_work':component,'parent_work':parent,
        'catalog_lookups':lookups,'catalog_words':cat_words,'role_own_work':role[0],
        'store_component_work':role[7]+role[8],'role_combined_work':role[2],'raw':raw}


def plan(profile,selectors,rule,limits=None):
    need(type(profile) is int and profile in (0,1) and type(rule) is str and rule in RULES and
         type(selectors) is tuple and len(selectors)==2 and all(type(x) is tuple and len(x)==2 and
         all(type(v) is int for v in x) and 0<=x[0]<(1624350,25908876)[profile] and 0<=x[1]<34246080 for x in selectors),
         'direct role complete input domain')
    need(limits is None or type(limits) is dict and set(limits)<=set(LIMITS),'direct role reduce-only limits')
    chosen=dict(LIMITS)
    for key,value in (limits or {}).items():
        need(type(value) is int and 0<value<=LIMITS[key],'direct role reduce-only limit value');chosen[key]=value
    law=law_forecast(52,(1326,1326));io=16*(OUTPUT+INPUT+SUMMARY)
    complete={'work':law['work']+43000000+SAMPLE['work']+io,
        'entries':law['entries']+131072+SAMPLE['entries']+2*(OUTPUT+INPUT+SUMMARY),
        'created_bits':law['created_bits']+1000000000+SAMPLE['created_bits']+io,'integer_bits':4096}
    need(all(complete[k]<=chosen[k] for k in LIMITS),'direct role source/sample/I-O reference admission rejected')
    return {'complete':complete,'limits':chosen,'native':resources(),'sample_allowance':SAMPLE,
        'scope':'Full1326 independent chance law, literal source and direct T2 ticket transcripts. No old full-raw walk reservation, larger limits, stochastic convergence or quality.'}


def scaled(value,denominator):
    need(type(value) is Fraction and denominator%value.denominator==0,'direct role exact scalar carrier')
    return value.numerator*(denominator//value.denominator)


def ticket(rule,index):
    if rule=='first':return 0
    if rule=='last':return Q-1
    if rule=='middle':return Q//2
    need(rule=='alternating','direct role closed ticket rule')
    return (0,Q-1,Q//2,(Q+2)//3,2*Q//3,1,Q-2)[index%7]


class Context:
    def __init__(self,profile,selectors,rule,limits=None):
        self.admission=plan(profile,selectors,rule,limits);self.profile=profile;self.selectors=selectors;self.rule=rule
        # The original independent O(H)-storage law retains its complete
        # admission/counters; no factory or private counter is bypassed/reset.
        side=tuple((hand,struct.unpack('>Q',struct.pack('>d',float(i%7+1 if profile else 1)))[0])
                   for i,hand in enumerate(combinations(range(52),2)))
        self.law=build_law(tuple(range(52)),(side,side))
        self.source_budget=Budget({'work':43000000,'entries':131072,'created_bits':1000000000,'integer_bits':4096})
        self.tree=build_reference_template(_template_case(),rule_budget=self.source_budget);self.nodes=self.tree.nodes
        need(len(self.nodes)==388 and self.tree.receipt['logical_occurrences']==1105,'direct role literal source geometry')
        self.meter=Budget(SAMPLE);self.meter.entries(499000,'direct transcript/state/descriptor/allocator scratch')
        self.meter.charge('literal_path_setup',32*1105)
        self.paths=[self.tree.root];self.children={}
        for path,source in enumerate(self.paths):
            for action,edge in enumerate(self.nodes[source].edges):
                need(len(self.paths)<1105,'direct role literal path bound')
                self.children[path,action]=len(self.paths);self.paths.append(edge.child)
        need(len(self.paths)==1105,'direct role full literal path transport')
        self.stakes={source:min(Fraction.from_float(float(x)) for x in node.state.state.committed)
                     for source,node in enumerate(self.nodes) if node.phase in ('fold','showdown')}
        need(all(abs(x)<=8 and (2*x).denominator==1 for x in self.stakes.values()),'direct role whole-hand payoff geometry')
        self.transport={};self.numeric={};self.policy={};self.records=[]

    def transcript(self,world,target,frozen):
        m=self.meter;observed={};rr={};aa={};choices=[];tape=[];counts=[0]*7;peak=0
        def value_bits(value):
            nonlocal peak
            integer=scaled(value,D);peak=max(peak,abs(integer).bit_length());return integer
        def mul(a,b):return m.mul(a,b,'direct transcript product')
        def plus(a,b):return m.add(a,b,'direct transcript sum')
        def minus(a,b):return m.sub(a,b,'direct transcript difference')
        def divide(a,b):return m.div(a,b,'direct transcript quotient')
        one=m.input(Fraction(1),'direct transcript one');zero=m.input(Fraction(0),'direct transcript zero')
        def visit(path,history,reaches,qprefix):
            nonlocal peak
            m.charge('literal_role_visits',128);counts[0]+=1;need(counts[0]<=367,'direct role target visits')
            source=self.paths[path];node=self.nodes[source]
            if node.phase in ('fold','showdown'):
                counts[3]+=1;sign=world.showdown_sign if node.phase=='showdown' else (1 if node.state.winner==0 else -1)
                value=m.input(self.stakes[source]*sign*(1 if target==0 else -1),'direct target terminal');value_bits(value);return value
            if node.phase=='reveal':
                counts[2]+=1;length=node.state.board_length
                token_text=('flop@'+''.join(card_name(c) for c in world.board[:3]) if length==3 else
                            ('turn@' if length==4 else 'river@')+card_name(world.board[length-1]))
                return visit(self.children[path,0],(*history,token_text),reaches,qprefix)
            counts[4]+=1;actor=node.state.player;k=len(node.edges);key=(actor,world.holding_indices[actor],history)
            need(node.phase=='decision' and key not in observed and len(observed)<204,'direct role full-history information identity')
            units=frozen.get(key,uniform(k));need(len(units)==k and sum(units)==Q and all(0<=u<=Q for u in units),'direct role frozen Q52 partition')
            visible=world.board[:node.street];ordinal=(path<<33)|(len(visible)<<30)|sum(c<<(6*i) for i,c in enumerate(visible))
            metadata=(actor,world.holding_indices[actor],ordinal,source,k)
            public=metadata[:3]
            need(public not in self.transport or self.transport[public][0]==key,'direct role transport alias')
            self.transport[public]=(key,source,k);observed[key]=(metadata,units)
            probabilities=tuple(m.input(Fraction(u,Q),'direct frozen probability') for u in units)
            if actor==target:
                counts[5]+=1;values=[]
                for a in range(k):
                    counts[1]+=1;next_reach=list(reaches);next_reach[actor]=mul(reaches[actor],probabilities[a])
                    values.append(visit(self.children[path,a],(*history,node.edges[a].token),tuple(next_reach),qprefix))
                mixed=zero;native_mixed=0
                for probability,value,u in zip(probabilities,values,units):
                    mixed=plus(mixed,mul(probability,value));m._reserve((423,423,423),'direct native value projection')
                    product=value_bits(value)*u;native_mixed+=product;peak=max(peak,abs(product).bit_length(),abs(native_mixed).bit_length())
                value_bits(mixed);need(reaches[1-actor]==qprefix and qprefix>0,'direct regret cancellation hypothesis')
                factor=divide(reaches[1-actor],qprefix);rr[key]=tuple(mul(factor,minus(value,mixed)) for value in values)
                center=zero
                for r,p in zip(rr[key],probabilities):center=plus(center,mul(r,p));value_bits(r)
                need(center==0,'direct exact regret centering');return mixed
            counts[6]+=1;index=len(tape);chosen_ticket=ticket(self.rule,index);tape.append(chosen_ticket);m.charge('ticket_cdf',32*k)
            # Fraction intervals, rather than the native integer prefix loop.
            point=m.input(Fraction(chosen_ticket,Q),'direct ticket point');left=zero;selected=None
            for a,p in enumerate(probabilities):
                right=plus(left,p)
                if m.compare(left,point,'direct CDF lower')<=0 and m.compare(point,right,'direct CDF upper')<0:selected=a;break
                left=right
            need(selected is not None and probabilities[selected]>0,'direct supported CDF interval')
            p=probabilities[selected];need(reaches[actor]==qprefix and qprefix>0,'direct average cancellation hypothesis')
            aa[key]=tuple(mul(divide(reaches[actor],qprefix),v) for v in probabilities)
            choices.append((target,actor,metadata[1],ordinal,source,selected,chosen_ticket,units[selected]))
            next_reach=list(reaches);next_reach[actor]=mul(reaches[actor],p);counts[1]+=1
            child=visit(self.children[path,selected],(*history,node.edges[selected].token),tuple(next_reach),mul(qprefix,p))
            return mul(divide(p,p),child)
        try:root=visit(0,(),(one,one),one)
        finally:visit=None
        return {'root':scaled(root,D),'observed':observed,'regrets':rr,'averages':aa,'choices':choices,
                'tickets':tuple(tape),'counts':tuple(counts),'peak_bits':peak}

    def run(self):
        need(not self.records,'direct role reference owner reused')
        for private,rank in self.selectors:
            world=self.law.decode(private,rank);frozen=MappingProxyType(dict(self.policy))
            samples=tuple(self.transcript(world,target,frozen) for target in (0,1));observed={};regrets={};averages={}
            for sample in samples:
                for key,data in sample['observed'].items():need(key not in observed or observed[key]==data,'direct dual frozen identity');observed[key]=data
                need(not set(regrets)&sample['regrets'].keys() and not set(averages)&sample['averages'].keys(),'direct disjoint target roles')
                regrets.update(sample['regrets']);averages.update(sample['averages'])
            raw=[]
            for key,(metadata,units) in observed.items():
                k=len(units);zero=(Fraction(0),)*k
                rr=tuple(scaled(v,D) for v in regrets.get(key,zero));aa=tuple(scaled(v,Q) for v in averages.get(key,zero))
                roles=sum((1<<target) for target in (0,1) if key in samples[target]['observed'])
                need(sum(u*r for u,r in zip(units,rr))==0 and (not any(aa) or aa==units),'direct raw row authorization')
                raw.append((*metadata,roles,units,rr,aa))
                old_r,old_a=self.numeric.get(key,((0,)*k,(0,)*k))
                m=self.meter;m._reserve((704,704,1408,1408,1408,1408,704,704)*4,'direct state/allocator reservation')
                m.charge('state_and_allocator',64*k+64*k*k)
                current_r=tuple(a+(b<<260) for a,b in zip(old_r,rr));current_a=tuple(a+(b<<312) for a,b in zip(old_a,aa))
                if any(current_r) or any(current_a):self.numeric[key]=(current_r,current_a)
                else:need(key not in self.numeric,'direct nonzero state vanished despite centered matching policy')
                if any(rr):self.policy[key]=allocate(current_r)
            total_counts=tuple(sum(s['counts'][i] for s in samples) for i in range(7))
            need(all(v<=cap for v,cap in zip(total_counts,(367,327,41,127,204,76,204))) and len(raw)<=204,
                 'direct exact selected transcript geometry bound')
            self.records.append({'world':world,'samples':samples,'raw':tuple(raw),'counts':total_counts,
                'numeric':MappingProxyType(dict(self.numeric)),'policy':MappingProxyType(dict(self.policy)),
                'peak_bits':max(s['peak_bits'] for s in samples)})
        need(len(self.numeric)<=408 and sum(len(x[0]) for x in self.numeric.values())<=1632,'direct cumulative T2 storage bound')
        return tuple(self.records)

    def request(self):
        need(len(self.records)==2,'direct request needs complete independent transcripts')
        tapes=[s['tickets'] for record in self.records for s in record['samples']]
        words=(1,self.profile,2,*[v for item in self.selectors for v in item],*[len(tape) for tape in tapes])
        raw=b'OPLRIN01'+struct.pack('<11Q',*words)+b''.join(struct.pack('<Q',v) for tape in tapes for v in tape)
        need(len(raw)<=INPUT,'direct complete input bytes');return raw
