"""Admit storage wrappers, verify actual ledgers, reuse unchanged literal math."""
import struct
from tests.virtual_role_walk_reference import Context,Q,D,plan,resources,need,OUTPUT
from tests.virtual_role_walk_wire_reference import Reader,header,parse,receipts,request_tapes,compare,quantizer_work
from tests.opponent_role_epoch_reference import forecast
from tests.virtual_joint_two_epoch_forecast_reference import copy

EXPANSION_SLOT_WORK=64+copy(631)+copy(366)


def native_resources(mode):
    need(type(mode) is int and mode in (0,1),'compact storage explicit mode')
    result=dict(resources());observation=1024+2448*64;expansion=(1024+2448*EXPANSION_SLOT_WORK) if mode else 0
    result['parent_work']+=observation+expansion;result['work']+=observation+expansion
    need(result['parent_work']<=115000000 and result['work']<=500000000,'compact storage unchanged complete caps')
    result['observation_work']=observation;result['expansion_work']=expansion
    return result


def unwrap(raw,request,profile,selectors,rule,mode):
    admission=plan(profile,selectors,rule);model=native_resources(mode);tapes=request_tapes(request,profile,selectors)
    r=Reader(raw,OUTPUT);r.magic(b'OPLRSW01');got=r.words(34);expected=list(header(profile));expected[0]=2
    expected[13]=model['work'];expected[22]=model['parent_work']
    need(got==tuple(expected),'compact storage independent complete resource header')
    need(r.words(6)==(1,mode,365 if mode else 625,52 if mode else 364,371 if mode else 649,54 if mode else 382),
         'compact storage explicit persistent carrier contract')
    normalized=bytearray(b'OPLROW01'+struct.pack('<34Q',*header(profile)));metrics=[]
    for epoch in (1,2):
        start=r.at;r.magic(b'OPLRWO01');h=r.words(18);nr,ns,nc=h[15:]
        need(h[0]==epoch and 0<nr<=204 and 2*nr<=ns<=4*nr and nc<=204,'compact storage raw bounded extents')
        r.take(280);slots=0
        for _ in range(nr):
            m=r.words(6);k=m[4];need(2<=k<=4,'compact storage raw bounded menu');r.take(72*k);slots+=k
        need(slots==ns,'compact storage complete raw slots');r.take(64*nc);r.magic(b'OPLREN01');r.words(3)
        r.magic(b'OPLRSN01');step,count,total=r.words(3)
        need(step==epoch and count<=204*epoch and 2*count<=total<=4*count,'compact storage bounded snapshot')
        slots=0
        for _ in range(count):
            m=r.words(5);k=m[4];need(2<=k<=4,'compact storage snapshot bounded menu');r.take(144*k);slots+=k
        need(slots==total,'compact storage complete snapshot slots');r.magic(b'OPLRRC01');r.words(36)
        normalized.extend(raw[start:r.at]);r.magic(b'OPLRSM01');metric=r.words(7)
        need(metric[:3]==(epoch,count,total) and metric[3] in (32,64) and metric[4]==2*total and
             metric[5]<=metric[6]<=2*total*4*max(2,(649+metric[3]-1)//metric[3]),
             'compact storage bounded backend capacity census');metrics.append(metric)
    r.magic(b'OPLRSF01');parent,expansion,observation,size=r.words(4);r.end()
    need(size==len(raw) and expansion<=model['expansion_work'] and observation<=model['observation_work'] and
         parent>=expansion+observation,'compact storage complete parent/export ledger')
    normalized.extend(b'OPLRFN01'+struct.pack('<2Q',parent-expansion-observation,len(normalized)+24))
    # Only wrapper metadata and declared resource/billing terms are removed.
    # Every original root/raw/canonical snapshot/choice byte is retained.
    records=parse(bytes(normalized),profile,selectors,tapes)
    expected_observation=expected_expansion=canonical_q=actual_q=0;checked=[];storage=[]
    for record,metric in zip(records,metrics):
        snapshot=record['snapshot'];slots=sum(len(x[0]) for x in snapshot.values())
        expected_observation+=512+64*slots
        if mode:expected_expansion+=512+EXPANSION_SLOT_WORK*slots
        used=0;canonical_bits=compact_bits=0
        for rr,aa,_units in snapshot.values():
            need(all(v%(1<<260)==0 for v in rr) and all(v%(1<<312)==0 for v in aa),
                 'compact storage exact canonical re-expansion alignment')
            for values,shift in ((rr,260),(aa,312)):
                for value in values:
                    small=value//(1<<shift);native=small if mode else value
                    need(small<<shift==value,'compact storage exact signed canonical expansion')
                    used+=max(1,(abs(native).bit_length()+metric[3]-1)//metric[3])
                    canonical_bits+=abs(value).bit_length();compact_bits+=abs(small).bit_length()
        need(metric[5]==used,'compact storage exact native used-limb census')
        for row in record['raw']:
            if any(row[7]):
                rr=snapshot[row[:3]][0];canonical_q+=quantizer_work(rr)
                actual_q+=quantizer_work(tuple(v//(1<<260) for v in rr)) if mode else quantizer_work(rr)
        actual=record['receipt'];need(actual[14]==actual_q and actual[9]+actual[14]+actual[0]<=model['component_work'],
            'compact storage actual quantizer and Store component ledgers')
        receipt=list(actual);receipt[14]=canonical_q;checked.append({**record,'receipt':tuple(receipt)})
        storage.append({'epoch':metric[0],'rows':metric[1],'slots':metric[2],'limb_bits':metric[3],
            'integer_objects':metric[4],'native_used_limbs':metric[5],'native_capacity_limbs':metric[6],
            'canonical_magnitude_bits':canonical_bits,'compact_magnitude_bits':compact_bits,
            'native_store_peak_logical_payload_bits':actual[23],
            'actual_quantizer_work':actual_q,'canonical_quantizer_work':canonical_q})
    need((expansion,observation)==(expected_expansion,expected_observation),
         'compact storage exact parent expansion/observation work')
    # The unchanged Store logical work/read/stage/commit and borrowed-owner
    # equations remain conservative. Verify actual compact quantizer work
    # above before substituting its canonical equivalent for that old checker.
    receipts(tuple(checked))
    return records,bytes(normalized),{'native_forecast':model,'storage':storage,
        'parent_actual':parent,'actual_expansion_work':expansion,'actual_observation_work':observation,
        'raw_wire_bytes':len(raw),'normalized_wire_bytes':len(normalized),'mode':mode},admission


def verify(raw,request,profile,selectors,rule,mode):
    records,normalized,storage,admission=unwrap(raw,request,profile,selectors,rule,mode)
    ctx=Context(profile,selectors,rule);ctx.run()
    report=compare(records,request,ctx,admission,len(normalized))
    return {**report,**storage,'contract':'same-owner-role-storage-v1','allocator_or_rss_admitted':False}


def verify_controls(raw):
    need(type(raw) is bytes and len(raw)<=65536,'compact storage controls bounded text');lines=raw.decode('ascii').splitlines()
    role=forecast(1,4,2,8,2);cat_words=1024+32*8+320*8+8;cat_work=1024+16*8+64*(512+256*20+32*(9).bit_length()+8)
    budget=(43000000+42000000+9*(1000000+cat_work+2*role[2])+1000000+16*65536,
        131072+35361+9*(12000+cat_words+2*role[5])+65536+16384,
        131072*64+(8<<20)+9*((1<<20)+64*cat_words+2*role[6])+(1<<22)+8*65536)
    need(lines[0]=='COMPACT_STORE_BUDGET '+' '.join(map(str,budget)) and lines[-1]=='COMPACT_STORE_PASS 2 12 10',
         'compact storage controls complete admission/footer')
    rows={};guards=set()
    for line in lines[1:-1]:
        values=line.split()
        if values[0]=='ROW':
            need(len(values)==8,'compact storage controls complete numeric row');step=int(values[1])
            need(step not in rows,'compact storage controls unique step');rows[step]=tuple(map(int,values[2:]))
        else:
            need(len(values)==3 and values[0]=='GUARD' and values[2]=='PASS' and values[1] not in guards,
                 'compact storage controls real guard result');guards.add(values[1])
    expected={1:(D,Q//2,Q,-D,Q//2,0),2:(D,3*Q//2,Q//2,D,Q//2,Q//2)}
    need(rows==expected and guards=={'unknown-persistent','compact-without-observation','two-policy-reads',
        'unknown-arithmetic','canonical-regret-scale','canonical-average-scale','wide-regret','wide-average',
        'negative-average','uncentered-regret'},'compact storage independent exact synthetic transitions/guards')
    return {'steps':2,'numeric_coordinates':12,'runtime_guards':10,'complete_budget':budget}
