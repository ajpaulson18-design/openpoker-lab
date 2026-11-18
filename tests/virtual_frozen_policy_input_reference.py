"""Independent bounded snapshot format, catalog census and saved-wire replay.

Only this oracle may retain the sixty literal worlds. Native State imports
walk the supported public catalog and never construct a world table.
"""
import struct

from tests.virtual_dyadic_training_reference import Q

HANDS=(((43,48),(32,43)),((24,37),(16,32)))
INPUT_CAP=8<<20
OUTPUT_CAP=2_100_000


def require(value,message):
    if not value:raise ValueError(message)


def profile(fixture,name):
    if name=='uniform':return fixture.grid()
    require(name=='zero-skew','unknown snapshot profile')
    result={}
    for i,key in enumerate(sorted(fixture.menus)):
        count=len(fixture.menus[key]);units=[0 if i%2 else 1]*count
        units[i%count]=Q-sum(units)+units[i%count];result[key]=tuple(units)
    return result


def encode_snapshot(fixture,policy):
    fixture._probabilities(policy)
    ordered=tuple(fixture.ordered_rows())
    require(len(ordered)==len(set(ordered))==24420,'snapshot complete row order')
    tokens=sum(len(k[2]) for k in ordered)
    history_bytes=sum(sum(len(t.encode('ascii')) for t in k[2]) for k in ordered)
    action_bytes=sum(sum(len(t.encode('ascii')) for t in fixture.menus[k]) for k in ordered)
    data=bytearray(b'OPLFGS01'+struct.pack('<6Q',24420,58164,tokens,history_bytes,action_bytes,Q))
    layout={}
    def token(text):
        raw=text.encode('ascii');require(0<len(raw)<=64,'snapshot token bound')
        data.extend(bytes((len(raw),)));data.extend(raw)
    for row,key in enumerate(ordered):
        actor,holding,history=key;menu=fixture.menus[key];first,second=HANDS[actor][holding]
        data.extend(struct.pack('<5Q',actor,first,second,len(history),len(menu)))
        if history and 'history' not in layout:layout['history']=len(data)
        for text in history:token(text)
        if not row:layout['menu']=len(data)
        for text in menu:token(text)
        layout['last_units']=len(data);layout['last_width']=len(menu)
        data.extend(struct.pack('<'+'Q'*len(menu),*policy[key]))
    require(len(data)<=INPUT_CAP,'snapshot byte ceiling')
    return bytes(data),ordered,layout


def decode_snapshot(fixture,data):
    require(type(data) is bytes and 56<=len(data)<=INPUT_CAP,'saved input byte bound')
    require(data[:8]==b'OPLFGS01','saved input version')
    require(struct.unpack_from('<6Q',data,8)==(24420,58164,249662,1500675,294353,Q),'saved complete input census')
    position=56;policy={}
    def take(n):
        nonlocal position
        require(n<=len(data)-position,'saved input truncation')
        raw=data[position:position+n];position+=n;return raw
    def token():
        n=take(1)[0];require(0<n<=64,'saved input token bound')
        return take(n).decode('ascii')
    for key in fixture.ordered_rows():
        actor,first,second,n,m=struct.unpack('<5Q',take(40))
        menu=fixture.menus[key]
        require((actor,first,second,n,m)==(key[0],*HANDS[key[0]][key[1]],len(key[2]),len(menu)),
                'saved input original holding/history/menu extent')
        require(tuple(token() for _ in range(n))==key[2],'saved input full visible history')
        require(tuple(token() for _ in range(m))==menu,'saved input ordered legal menu')
        units=struct.unpack('<'+'Q'*m,take(8*m))
        require(all(u<=Q for u in units) and sum(units)==Q,'saved input exact grid partition')
        policy[key]=units
    require(position==len(data) and len(policy)==24420,'saved input complete coverage')
    return policy


def public_census(fixture):
    """Group independent physical worlds by visible prefix, not native nodes."""
    counts={name:0 for name in ('visits','actions','reveals','candidates','folds','showdowns','rows','slots')}
    def visit(node_id,worlds):
        node=fixture.nodes[node_id];counts['visits']+=1
        if node.phase=='reveal':
            size=node.state.board_length;previous=0 if size==3 else size-1
            counts['candidates']+=84 if previous==0 else 9-previous
            groups={}
            for w in worlds:groups.setdefault(w.board[:size],[]).append(w)
            for group in groups.values():
                counts['reveals']+=1;visit(node.edges[0].child,group)
        elif node.phase=='decision':
            actor=node.state.player;rows=len({w.holdings[actor] for w in worlds})
            counts['rows']+=rows;counts['slots']+=rows*len(node.edges);counts['actions']+=len(node.edges)
            for edge in node.edges:visit(edge.child,worlds)
        else:counts['folds' if node.phase=='fold' else 'showdowns']+=1
    visit(fixture.template.root,fixture.worlds)
    return counts


def expected_reservation(fixture):
    c=public_census(fixture);r,s=c['rows'],c['slots'];literal=len(fixture.paths)
    require((r,s,literal)==(24420,58164,1105),'reference catalog geometry')
    log=(r+1-1).bit_length()
    import_work=1088+130*r+258*s;read_work=(208+16*log)*r
    state=1024+8*r+16*s+4*11+r*(128+16*log)+256*s+import_work+read_work
    history=4096*literal+1280+40*c['actions']+72*c['reveals']+48*c['visits']+40*r+8*r+72*249662+56*r+16*s+40*r+288*r
    parent=3_000_000+8*c['visits']+64*c['candidates']+16*r+4*s
    work=43_000_000+65536+history+state+1+parent+16*INPUT_CAP+16*OUTPUT_CAP
    entries=1024+16*r+10*s+131072+32*literal+1+12000+16384
    payload=(5*s+256)*(648+58)+128*s+512*s+16*r+(1<<20)+8*(1<<20)+(1<<22)+32*181+8*16384
    return (r,s,work,entries,payload,history,state),parent


def verify_snapshot_wire(fixture,policy,raw):
    require(type(raw) is bytes and len(raw)==1442320 and len(raw)<=OUTPUT_CAP,'saved output byte bound')
    require(raw[:8]==b'OPLFGV01','saved output version')
    header=struct.unpack_from('<7Q',raw,8)
    expected,parent_bound=expected_reservation(fixture)
    require(header==expected,'independent snapshot reservation mismatch')
    rows,slots,work,entries,payload,history_work,state_work=header
    require(work<=500_000_000 and entries<=2_000_000 and payload<=1<<30 and
            history_work<=42_000_000 and state_work+1<=75_000_000,'snapshot resource caps')
    position=64;offset=0
    for key in fixture.ordered_rows():
        actor,holding,ordinal,slot,count=struct.unpack_from('<5Q',raw,position);position+=40
        require((actor,holding,slot,count)==(key[0],key[1],offset,len(fixture.menus[key])),'saved output row identity/order')
        require(fixture.compact_key(ordinal,actor,holding)==key,'saved output full-history key mismatch')
        units=struct.unpack_from('<'+'Q'*count,raw,position);position+=8*count
        require(units==policy[key],'saved output exact grid units mismatch');offset+=count
    footer=struct.unpack_from('<18Q',raw,position);position+=144
    require(position==len(raw) and footer[:2]==(rows,slots) and offset==slots,'saved final row/slot coverage')
    actual,actual_history,actual_state=footer[2:5]
    template,parent,chance,input_bytes,output_bytes=footer[5:10]
    require(footer[10:15]==(0,0,0,0,0) and footer[15:]==(24420,24420,1),'saved native scope counters')
    require(output_bytes==len(raw) and input_bytes==3545022,'saved native byte counters')
    require(actual==template+parent+chance+actual_history+actual_state+16*input_bytes+16*output_bytes,
            'saved composed actual work')
    require(actual<=work and actual_history<=history_work and actual_state<=state_work and
            template<=43_000_000 and parent<=parent_bound and chance<=65536,'saved resource reservation underrun')
    return {'rows':rows,'slots':slots,'work_forecast':work,'work_actual':actual,'entries_forecast':entries,
            'payload_bits_forecast':payload,'history_work_forecast':history_work,'history_work_actual':actual_history,
            'state_work_forecast':state_work,'state_work_actual':actual_state,'input_bytes':input_bytes,
            'output_bytes':output_bytes,'native_rank_calls':0,'native_contractions':0,'training_iterations':0,
            'quantizer_work':0,'all_policy_units_exact':True}
