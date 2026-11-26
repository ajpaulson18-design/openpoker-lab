"""Independent rational policy images on authenticated raw transcript rows."""
from fractions import Fraction
from hashlib import sha256
import struct
from scripts import joint_evidence_archive as archive,replay_joint_two_epoch_packet as helper
from scripts.opponent_action_moment_frame import Reader,parse,Q,DR,DA,need
from scripts.replay_opponent_action_moments import PACKET,PIN

D=1<<365


def allocate(weights):
    positive=[max(0,w) for w in weights];total=sum(positive)
    exact=[Fraction(w*Q,total) for w in positive] if total else [Fraction(Q,len(weights))]*len(weights)
    units=[x.numerator//x.denominator for x in exact]
    for i in sorted(range(len(weights)),key=lambda i:(-(exact[i]-units[i]),i))[:Q-sum(units)]:units[i]+=1
    return tuple(units)


def witness_rows():
    _manifest,loaded,_pins=archive.load(PACKET,helper,pin=PIN,version='opponent-moments',
        labels=('observations','builds','objects'),packager='package_opponent_moments1.py.txt')
    result=[]
    for case in range(3):
        files=loaded['observations'];prefix=f'study/case-{case}-normal'
        report=helper.decode(files[prefix+'/summary.json']);side=files[prefix+'/witness.bin']
        parse(files[prefix+'/stdout.bin'],side,report)
        reader=Reader(side,1_048_576);reader.magic(b'OPLOAW01');reader.words(4)
        for table in range(4):
            reader.magic(b'OPLOWT01');h=reader.words(11);reader.take(2*88)
            for _ in range(h[4]):
                actor,holding,ordinal,source,k=reader.words(5);units=[];rr=[];aa=[]
                for _a in range(k):
                    u=reader.words(1)[0];r=reader.integer(88,True);a=reader.integer(48)
                    if table%2:
                        need(r%(1<<260)==0 and a%(1<<312)==0,'row witness exact compact scale')
                        units.append(u);rr.append(r>>260);aa.append(a>>312)
                if table%2:result.append({'origin':{'case':case,'profile':table//2,'actor':actor,'holding':holding,
                    'ordinal':ordinal,'source':source},'initial':tuple(units),'steps':((tuple(rr),tuple(aa)),)})
            reader.take((h[6]+h[7])*56)
        reader.end()
    need(len(result)==85,'complete 85 named role witness rows');return result


def synthetic_rows():
    result=[]
    for k in (2,3,4):
        for profile in ('uniform','one-hot','tiny'):
            units=allocate([1]*k) if profile=='uniform' else ((Q,)+(0,)*(k-1) if profile=='one-hot' else (1,Q-1)+(0,)*(k-2))
            current=units;steps=[];cumulative=[0]*k
            for s in (0,1):
                # Dyadic whole-hand-sized values, exact on the compact carrier.
                children=tuple(((-1)**(i+s))*(i+1)*(D//2) for i in range(k))
                weighted=sum(u*v for u,v in zip(current,children));need(weighted%Q==0,'row synthetic exact mixture')
                mixed=weighted//Q;r=tuple(v-mixed for v in children);a=current
                steps.append((r,a));cumulative=[old+delta for old,delta in zip(cumulative,r)]
                current=allocate(cumulative)
            result.append({'origin':{'synthetic':profile,'actions':k},'initial':units,'steps':tuple(steps)})
    # Exact denominator and persistent signed negative/zero coordinates.
    result.append({'origin':{'synthetic':'tiny-signed'},'initial':(Q//2,Q//2),
                   'steps':(((1,-1),(Q//2,Q//2)),((0,-1),(Q,0)))})
    # A zero raw update preserves an explicitly frozen nonuniform image.
    result.append({'origin':{'synthetic':'zero-update'},'initial':(1,Q-1),
                   'steps':(((0,0),(0,0)),((0,0),(1,Q-1)))})
    return result


def request_rows():return witness_rows()+synthetic_rows()


def encode(rows):
    need(0<len(rows)<=204,'row bounded request');out=bytearray(b'OPLRQ001'+struct.pack('<Q',len(rows)))
    for index,row in enumerate(rows):
        k=len(row['initial']);steps=row['steps'];out.extend(struct.pack('<3Q',index,k,len(steps)))
        out.extend(struct.pack('<'+'Q'*k,*row['initial']))
        for rr,aa in steps:
            for r,a in zip(rr,aa):out.extend(r.to_bytes(56,'little',signed=True));out.extend(struct.pack('<Q',a))
    need(len(out)<=116000,'row bounded input bytes');return bytes(out)


def verify(raw,rows):
    reader=Reader(raw,131072);reader.magic(b'OPLRP001');need(reader.words(1)==(len(rows),),'row result count')
    negative=zero_positive=0;maximum_r=maximum_a=0;images=0
    for index,row in enumerate(rows):
        k=len(row['initial']);need(reader.words(3)==(index,k,len(row['steps'])),'row result descriptor')
        cumulative=[0]*k;averages=[0]*k;current=row['initial']
        for rr,aa in row['steps']:
            need(sum(u*r for u,r in zip(current,rr))==0 and (not any(aa) or aa==current),'row independent frozen role conditions')
            cumulative=[old+delta for old,delta in zip(cumulative,rr)];averages=[old+delta for old,delta in zip(averages,aa)]
            if any(rr):current=allocate(cumulative)
            # Independently prove that both integer carrier scalings preserve
            # signs, exact regret matching, remainder ties and average image.
            need(allocate(cumulative)==allocate([r<<260 for r in cumulative]),'row exact regret scaling homogeneity')
            need(allocate(averages)==allocate([a<<312 for a in averages]),'row exact average scaling homogeneity')
            for r,a,u in zip(cumulative,averages,current):
                need((reader.integer(56,True),reader.words(1)[0],reader.words(1)[0])==(r,a,u),'row every exact R/A/policy coordinate')
                maximum_r=max(maximum_r,abs(r).bit_length());maximum_a=max(maximum_a,a.bit_length())
                negative+=int(r<0);zero_positive+=int(u==0 and r>0)
            images+=1
    reader.magic(b'OPLRF001');footer=reader.words(10);reader.end()
    work,cq,bq,cbit,bbit,cpeak,bpeak,count,steps,forecast=footer
    need(count==len(rows) and steps==images and work==1024+2048*images+cq and
         work<=forecast<=5_000_000 and cq<=8_000*images and bq<=5_000_000 and
         cbit<=371 and bbit<=631 and cpeak<=426 and bpeak<=704,'row native complete resource accounting')
    return {'rows':len(rows),'images':images,'named_witness_rows':85,'synthetic_rows':len(rows)-85,
        'negative_cumulative_coordinates':negative,'positive_regrets_quantized_to_zero':zero_positive,
        'max_observed_regret_bits':maximum_r,'max_observed_average_bits':maximum_a,
        'native_counters':dict(zip(('work','compact_quantizer_work','canonical_quantizer_work','compact_input_bits',
            'canonical_input_bits','compact_peak_forecast_bits','canonical_peak_forecast_bits','rows','steps','forecast'),footer)),
        'output_sha256':sha256(raw).hexdigest(),'rng_calls':0,'attempted_training':False,'quality_gate':None,
        'scope':'Compact/canonical arithmetic and rational allocation on named transcript rows plus two-step synthetic controls. No History/role lease, native world traversal, stochastic learning or timing improvement.'}
