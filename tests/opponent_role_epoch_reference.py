"""Independent synthetic row arithmetic and combined facade resource equations."""
from fractions import Fraction
from tests.virtual_joint_two_epoch_forecast_reference import copy,add,multiply,row_map

Q=1<<52
DR=1<<625
DA=1<<364
GUARDS=('duplicate-role','target-order','premature-seal','abandoned-callback','one-target-only','missing-first-root',
    'wrong-holding','wrong-actor','foreign-history-cursor','stage-before-seal','duplicate-stage','default-token',
    'foreign-token','stale-token','wrong-average','uncentered-regret','regret-magnitude','stage-menu',
    'unvisited-regret-role','unvisited-average-role','repeat-enumeration','read-after-seal','finish-after-seal',
    'late-callback-error','swallowed-error','export-while-active','reentrant-world','invalidated-certificate',
    'third-epoch','wrong-public-prefix','wrong-history-deck','missing-second-root','cache-row-bound','cache-slot-bound',
    'role-encounter-bound','foreign-catalog-history','range-binding','reduce-work','reduce-entries','reduce-payload',
    'row-ceiling','encounter-ceiling','slot-ceiling','recycled-store-address')


def need(value,message):
    if not value:raise ValueError(message)


def forecast(rows=204,slots=816,encounters=204,blocks=408,holdings=1326):
    cumulative_rows,cumulative_slots,reads=2*rows,2*slots,2*rows
    # Existing canonical Store equations, derived independently from its
    # bounded phases; this does not execute a native forecast or producer.
    read=reads*(160+32*4+2*row_map(cumulative_rows))+2*rows*128
    per_slot=(48+copy(649)+add(649)+multiply(383,317)+add(382)+64+multiply(648,53)+add(703)+
              2*multiply(383,53)+add(383)+2*copy(436)+32)
    staging=2*(1024+rows*(512+2*row_map(rows)+2*row_map(cumulative_rows)+4*per_slot))
    commit=2*(2048+rows*(256+row_map(cumulative_rows)+32*4+256))
    enumeration=2*rows*(256+row_map(rows))
    export=256+3*rows*(256+4*(copy(649)+copy(382)+8))
    store_own=2048+256+read+staging+commit+enumeration+export
    quantizer=2*rows*12000
    cat=(reads*2+2*rows)*(512+256*20+32*(blocks+1).bit_length()+8*((holdings+63)//64))
    history=reads*288
    store_work=store_own+quantizer+cat+history
    store_entries=256+48*cumulative_rows+16*cumulative_slots+2048
    store_payload=2*cumulative_slots*(649+382+64)+2*cumulative_rows*2048+64*64000
    facade=512+2*(256+encounters*(512+64*(rows+1).bit_length())+rows*(4096+128)+512+256+256)+512
    extra_history=2*encounters*48
    cache_entries=256+64*rows
    cache_payload=64*cache_entries+2*(4*630+4*365+425)
    return (facade,extra_history,store_work+facade+extra_history,cache_entries,cache_payload,
            store_entries+cache_entries,store_payload+cache_payload,store_own,quantizer,cat,history,
            store_work,store_entries,store_payload)


def uniform(k):
    base,left=divmod(Q,k);return tuple(base+(i<left) for i in range(k))


def allocate(weights):
    total=sum(max(0,w) for w in weights)
    exact=[Fraction(max(0,w)*Q,total) for w in weights] if total else [Fraction(Q,len(weights))]*len(weights)
    units=[v.numerator//v.denominator for v in exact]
    for i in sorted(range(len(weights)),key=lambda i:(-(exact[i]-units[i]),i))[:Q-sum(units)]:units[i]+=1
    return tuple(units)


def verify(raw):
    need(type(raw) is bytes and len(raw)<=65536,'role epoch bounded frame');lines=raw.decode('ascii').splitlines()
    need(lines[0]=='ROLE_EPOCH_COMPONENT_V1' and lines[-2:] ==
         ['STATIC_EPOCH_SCOPE PASS 3','ROLE_EPOCH_COMPONENT_PASS 44 5'],'role epoch frame/footer')
    forecasts={};receipts={};rows={};guards={};alias=None;probe=None
    for line in lines[1:-2]:
        values=line.split();kind=values[0]
        if kind=='FORECAST':
            need(values[1] not in forecasts,'role duplicate forecast');forecasts[values[1]]=tuple(map(int,values[2:]))
        elif kind=='ROW':
            label=values[1];step,actor,holding,ordinal,k=map(int,values[2:7]);key=(label,step,actor,holding,ordinal)
            need(key not in rows and actor in (0,1) and holding==0 and 2<=k<=4 and len(values)==7+3*k,'role unique bounded numeric row')
            triples=list(map(int,values[7:]));rows[key]=(tuple(triples[::3]),tuple(triples[1::3]),tuple(triples[2::3]))
        elif kind=='RECEIPT':
            need(values[1] not in receipts and len(values)==15,'role complete unique receipt');receipts[values[1]]=tuple(map(int,values[2:]))
        elif kind=='GUARD':
            need(len(values)==4 and values[2]=='PASS' and values[1] not in guards,'role duplicate/malformed guard');guards[values[1]]=int(values[3])
        elif kind=='ALIAS':need(alias is None and len(values)==6,'role alias census');alias=tuple(map(int,values[1:]))
        elif kind=='PROBE_FORECAST':need(probe is None and len(values)==5,'role whole probe forecast');probe=tuple(map(int,values[1:]))
        else:raise ValueError('role unknown frame record')
    need(forecasts=={'full':forecast(),'small':forecast(3,12,6,8,2)},'role independent complete facade resource equations')
    need(set(guards)==set(GUARDS) and all(value==({'stale-token':1,'third-epoch':2}.get(name,0)) for name,value in guards.items()),
         'role every refusal preserves its prior commit count')
    need(set(receipts)=={'both','average-only','regret-only','shared-source'},'role complete four successful cases')
    need(alias is not None and alias[0]<388 and alias[1]!=alias[2] and alias[1]>0 and alias[2]>0 and alias[3] in (0,1) and 2<=alias[4]<=4,
         'role distinct full histories under shared numeric source')
    nonroot=[key for key in rows if key[0]=='both' and key[1]==1 and key[2]==1]
    need(len(nonroot)==1,'role named BB row');bb_key=nonroot[0][2:];bb_k=len(rows[nonroot[0]][0])
    need(bb_key[2]>0,'role full BB history');expected_keys=set();coordinates=0
    for label,steps in (('both',2),('average-only',1),('regret-only',1)):
        for step in range(1,steps+1):
            root=(label,step,0,0,0);bb=(label,step,*bb_key);expected_keys.update((root,bb))
            if label=='both':
                r=(5,-3,0,-2) if step==1 else (5,1,2,-3)
                a=(DA//4,)*4 if step==1 else (5*DA//4,DA//4,DA//4,DA//4)
                root_expected=(tuple(v*DR for v in r),a,allocate(r))
            else:root_expected=((0,)*4,(DA//4,)*4,uniform(4))
            need(rows.get(root)==root_expected,'role exact unclipped evolving root R/A/policy')
            u=uniform(bb_k)
            if label=='regret-only':
                r=(u[1]<<260,-(u[0]<<260))+(0,)*(bb_k-2)
                bb_expected=(r,(0,)*bb_k,allocate(r))
            else:bb_expected=((0,)*bb_k,tuple(step*v*(DA//Q) for v in u),u)
            need(rows.get(bb)==bb_expected,'role exact missing-role BB R/A/policy');coordinates+=3*(4+bb_k)
    actor,k=alias[3:];alias_keys=[(0,0,0)]+([(actor,0,alias[i]) for i in (1,2)] if actor==1 else [])
    for info in alias_keys:
        key=('shared-source',1,*info);expected_keys.add(key);size=4 if info[0]==0 else k;u=uniform(size)
        need(rows.get(key)==((0,)*size,tuple(v*(DA//Q) for v in u),u),'role shared-source numeric/default retention')
        coordinates+=3*size
    need(set(rows)==expected_keys,'role no orphan or omitted emitted row')
    # Exact own ledger: constructor512; begin/commit/export256, two finishes,
    # seal256+128*unique rows; per observed role704; per stage4096.
    for label,epochs,encounters,unique,slots in (
        ('both',2,7,4,2*(4+bb_k)),('average-only',1,3,2,4+bb_k),('regret-only',1,3,2,4+bb_k),
        ('shared-source',1,4,3,4+2*k)):
        snapshots=epochs if label!='shared-source' else 1
        own=512+epochs*(256+512+256+256)+encounters*704+unique*(4096+128)+snapshots*256
        peak_rows=3 if label=='shared-source' else 2;peak_slots=4+2*k if label=='shared-source' else 4+bb_k
        current_rows=(3 if actor==1 else 1) if label=='shared-source' else 2
        current_slots=(4+2*k if actor==1 else 4) if label=='shared-source' else 4+bb_k
        need(receipts[label]==(own,encounters,unique,encounters-unique,unique,slots,epochs,peak_rows,peak_slots,
             unique,epochs,current_rows,current_slots),'role exact frozen-read reuse and stage/commit ledgers')
    # Independent full probe budget: one template, two History owners, one
    # Catalog, up to64 tiny facades and compact chance owners, bounded I/O.
    cat_words=1024+32*8+320*8+8
    cat_work=1024+8*8+8*8+2048*(512+256*20+32*(8+1).bit_length()+8)
    chance=64*(65536+16384*4+2*(12288+64*2+256*(2).bit_length()))
    small=forecasts['small']
    expected_probe=(43000000+2*42000000+cat_work+64*small[2]+chance+1000000+16*65536,
        131072+2*(32*1105+1)+cat_words+2*small[5]+12000+16384+2*65536+2048,
        131072*64+2*(8<<20)+64*cat_words+2*small[6]+(1<<20)+(1<<22)+16*65536,chance)
    need(probe==expected_probe and probe[0]<=500000000 and probe[1]<=2000000 and probe[2]<=1<<30 and chance<=110000000,
         'role source-inclusive probe admission under original caps')
    return {'status':'shared-store-role-component-exact','runtime_refusal_guards':44,'static_scope_checks':3,
        'independently_checked_R_A_policy_coordinates':coordinates,'good_committed_epochs':5,
        'forecasts':forecasts,'probe_forecast':probe,'receipts':receipts,'alias':alias,
        'native_rng_calls':0,'attempted_training':False,'quality_gate':None,
        'scope':'Synthetic row role/owner/certificate lifetime and canonical shared-Store transitions. No complete native sampled traversal, recursive branch proof, longer learning, timing or quality.'}
