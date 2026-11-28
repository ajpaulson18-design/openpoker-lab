"""Bounded role-walk wire admission and independent literal/Fraction comparison.

No native helper, production trainer, or saved source is executed here. Numeric
transport ordinals are checked separately from the literal semantic oracle.
"""
from fractions import Fraction
import struct

from tests.virtual_role_walk_reference import (Context, D, Q, INPUT, OUTPUT,
    need, plan, resources)
from tests.opponent_role_epoch_reference import forecast, uniform
from tests.virtual_joint_two_epoch_forecast_reference import copy, add, multiply, row_map


class Reader:
    def __init__(self, raw, cap):
        need(type(raw) is bytes and len(raw) <= cap, 'role wire bounded bytes')
        self.raw, self.at = raw, 0

    def take(self, count):
        need(0 <= count <= len(self.raw)-self.at, 'role wire truncated')
        value = self.raw[self.at:self.at+count]; self.at += count
        return value

    def magic(self, expected):
        need(self.take(8) == expected, 'role wire version/record order')

    def words(self, count):
        return struct.unpack('<'+'Q'*count, self.take(8*count))

    def integer(self, count, signed=True):
        return int.from_bytes(self.take(8*count), 'little', signed=signed)

    def end(self):
        need(self.at == len(self.raw), 'role wire trailing bytes')


def request_tapes(raw, profile, selectors):
    r = Reader(raw, INPUT); r.magic(b'OPLRIN01'); h = r.words(11)
    need(h[:3] == (1, profile, 2) and h[3:7] == tuple(v for x in selectors for v in x),
         'role request declared input')
    need(all(n <= 204 for n in h[7:]) and h[7]+h[8] <= 204 and h[9]+h[10] <= 204,
         'role request complete ticket extents')
    tapes = tuple(r.words(n) for n in h[7:]); r.end()
    need(all(0 <= x < Q for tape in tapes for x in tape), 'role request Q52 tickets')
    return tapes


def header(profile):
    f = resources()
    return (1, profile, 52, 1326, 1326, 2, Q, 365, 52, 625, 364, 704, 181,
        *[f[k] for k in ('work','entries','payload','output','input','catalog_work',
            'history_work','chance_work','component_work','parent_work','catalog_lookups',
            'catalog_words','role_own_work','store_component_work','role_combined_work')], *f['raw'])


def metadata(r, holdings, board):
    actor, hand, ordinal, source, k = r.words(5)
    need(actor < 2 and hand == holdings[actor] and source < 388 and 2 <= k <= 4,
         'role row actor/holding/source/menu domain')
    path, visible = ordinal >> 33, (ordinal >> 30) & 7
    need(path < 1105 and visible in (0,3,4,5) and
         ordinal & ((1 << 30)-1) == sum(c << (6*i) for i,c in enumerate(board[:visible])),
         'role row complete history transport/visible prefix')
    return actor, hand, ordinal, source, k


def raw_work(counts, rows):
    visits, actions, _, terminals, _, own, tickets = (sum(x) for x in counts)
    own_actions = actions-tickets
    slots = sum(row[4] for row in rows)
    average_slots = sum(row[4] for row in rows if row[5] & (1 << (1-row[0])))
    return (terminals*(32+copy(369)),
        own_actions*(8+multiply(369,53)+add(423)+copy(423))+own*(64+copy(423)+copy(369)+14),
        own_actions*(64+add(370)+copy(370)+512), 64*tickets+16*average_slots,
        1024+256*len(rows)+512*slots, 512+8*1105+256*visits+256*len(rows)+16*slots)


def parse(raw, profile, selectors, tapes):
    r = Reader(raw, OUTPUT); r.magic(b'OPLROW01')
    need(r.words(34) == header(profile), 'role wire independent complete forecast')
    records = []; seen = {}; previous = set(); parent = 1044096
    for epoch in (1,2):
        r.magic(b'OPLRWO01'); h = r.words(18)
        need(h[:3] == (epoch,*selectors[epoch-1]), 'role world selector/order')
        holdings, hands, board = h[3:5], h[5:9], h[9:14]
        need(all(c < 52 for c in (*hands,*board)) and len(set((*hands,*board))) == 9 and
             hands[0] < hands[1] and hands[2] < hands[3] and tuple(sorted(board[:3])) == board[:3] and h[14] <= 2,
             'role complete physical world domain')
        need(holdings == tuple(a*(103-a)//2+b-a-1 for a,b in (hands[:2],hands[2:])),
             'role original lexicographic holding indices')
        nr, ns, nc = h[15:]
        need(0 < nr <= 204 and 2*nr <= ns <= 4*nr and nc <= 204, 'role raw extents')
        roots = tuple(r.integer(7) for _ in range(2))
        need(all(abs(x) <= 8*D for x in roots), 'role target root payoff bound')
        counts = tuple(r.words(2) for _ in range(7)); work = r.words(6); peak, = r.words(1)
        need(all(sum(x) <= cap for x,cap in zip(counts,(367,327,41,127,204,76,204))) and peak <= 423,
             'role actual geometry/integer bounds')
        rows = []; current = {}
        for _ in range(nr):
            m = metadata(r,holdings,board); roles, = r.words(1); k = m[4]; key = m[:3]
            need(key not in current and roles in (1,2,3), 'role unique raw row/target roles')
            units=[]; rr=[]; aa=[]
            for _ in range(k):
                u, = r.words(1); v = r.integer(7); a, = r.words(1)
                need(u <= Q and abs(v) <= 16*D and a <= Q, 'role raw width/payoff bounds')
                units.append(u); rr.append(v); aa.append(a)
            units, rr, aa = tuple(units),tuple(rr),tuple(aa)
            need(sum(units) == Q and sum(u*v for u,v in zip(units,rr)) == 0,
                 'role raw partition/centering')
            need((roles & (1 << m[0]) or not any(rr)) and
                 aa == (units if roles & (1 << (1-m[0])) else (0,)*k), 'role raw authorized R/A roles')
            row = (*m,roles,units,rr,aa); rows.append(row); current[key]=row
            need(key not in seen or seen[key] == m, 'role persistent transport menu collision')
            seen[key]=m
        need(sum(row[4] for row in rows) == ns, 'role raw complete slots')
        for target in (0,1):
            visited = [row for row in rows if row[5] & (1 << target)]
            own = [row for row in visited if row[0] == target]
            opposite = len(visited)-len(own)
            need((counts[4][target],counts[5][target],counts[6][target]) == (len(visited),len(own),opposite) and
                 counts[1][target] == sum(row[4] for row in own)+opposite and
                 counts[0][target] == counts[1][target]+counts[2][target]+1 ==
                 counts[4][target]+counts[2][target]+counts[3][target], 'role target complete traversal census')
        choices=[]; consumed=[0,0]; choice_keys=set()
        for _ in range(nc):
            event=r.words(8); target,actor,hand,ordinal,source,action,ticket,u=event
            key=(actor,hand,ordinal); identity=(target,key)
            need(target < 2 and actor == 1-target and key in current and identity not in choice_keys,
                 'role unique opposite-target choice')
            row=current[key]; units=row[6]; tape=tapes[2*(epoch-1)+target]
            need(row[5] & (1 << target) and source == row[3] and action < row[4] and
                 consumed[target] < len(tape) and ticket == tape[consumed[target]], 'role complete supplied ticket order')
            need(u == units[action] and u > 0 and sum(units[:action]) <= ticket < sum(units[:action+1]),
                 'role exact supported ticket CDF interval')
            consumed[target]+=1; choice_keys.add(identity); choices.append(event)
        need(tuple(consumed) == counts[6] == tuple(len(tapes[2*(epoch-1)+t]) for t in (0,1)),
             'role no omitted or unused supplied tickets')
        need(work == raw_work(counts,rows) and all(x <= y for x,y in zip(work,resources()['raw'])),
             'role exact actual raw work')
        parent+=sum(work); r.magic(b'OPLREN01')
        need(r.words(3) == (sum(work),nr,ns), 'role completed raw footer')
        r.magic(b'OPLRSN01'); step,nrows,nslots=r.words(3)
        need(step == epoch and nrows <= 204*epoch and 2*nrows <= nslots <= 4*nrows,
             'role committed snapshot extents')
        snapshot={}
        for _ in range(nrows):
            # A retained row may belong to the preceding world. Do not bind its
            # private holding or visible board to the current world.
            m=r.words(5); key=m[:3]
            need(key in seen and seen[key] == m and key not in snapshot, 'role snapshot seen complete identity')
            rr=[];aa=[];units=[]
            for _ in range(m[4]):
                v=r.integer(11);a=r.integer(6,False);u,=r.words(1)
                need(abs(v).bit_length() <= 631 and a.bit_length() <= 366 and u <= Q,
                     'role cumulative fixed T2 numeric bounds')
                rr.append(v);aa.append(a);units.append(u)
            need((any(rr) or any(aa)) and sum(units) == Q, 'role implicit-zero/partition snapshot')
            snapshot[key]=(tuple(rr),tuple(aa),tuple(units))
        need(sum(len(x[0]) for x in snapshot.values()) == nslots and previous <= snapshot.keys(),
             'role retained row/slot census')
        previous=set(snapshot);r.magic(b'OPLRRC01');receipt=r.words(36)
        records.append({'world':h,'roots':roots,'counts':counts,'work':work,'peak_bits':peak,
            'raw':tuple(rows),'choices':tuple(choices),'snapshot':snapshot,'receipt':receipt})
    r.magic(b'OPLRFN01');need(r.words(2) == (parent,len(raw)), 'role final complete private output')
    r.end();return tuple(records)


def quantizer_work(weights):
    k=len(weights); positive=[x for x in weights if x>0]; cost=64+16*k
    if len(positive)<2:return cost+256+32*k
    words=lambda n:(n+63)//64
    cost+=sum(4*(words(x.bit_length())+1) for x in positive)
    common=min((x & -x).bit_length()-1 for x in positive)
    effective=max(x.bit_length() for x in positive)-common
    summed=effective+(len(positive)-1).bit_length()+1; scaled=effective+52; bits=max(summed,scaled,53)
    return cost+256+16*k*(words(bits)+1)+8*len(positive)*(2*words(scaled)*words(summed)+4*words(bits)+8)+4*k*k*(words(summed)+1)


def receipts(records):
    f=resources(); rf=forecast(); cum_rows=cum_slots=encounters=exports=export_slots=0
    max_rows=max_slots=quantized=qwork=0; store_work=2048; seen={}; blocks=set();menus=set();previous_history=0;previous_peak=0
    stage_slot=(48+copy(649)+add(649)+multiply(383,317)+add(382)+64+multiply(648,53)+add(703)+
        2*multiply(383,53)+add(383)+2*copy(436)+32)
    for epoch, record in enumerate(records,1):
        rows=record['raw'];snap=record['snapshot'];nr=len(rows);ns=sum(x[4] for x in rows)
        cum_rows+=nr;cum_slots+=ns;encounters+=sum(record['counts'][4]);exports+=len(snap)
        export_slots+=sum(len(x[0]) for x in snap.values());max_rows=max(max_rows,nr);max_slots=max(max_slots,ns)
        for row in rows:
            seen[row[:3]]=row;blocks.add((row[0],row[2]));menus.add(row[3])
            if any(row[7]):quantized+=1;qwork+=quantizer_work(snap[row[:3]][0])
        pending=sum(row[:3] in snap for row in rows)
        store_work+=128+nr*(160+128+2*row_map(408))+nr*128+1024+nr*(512+2*row_map(204)+2*row_map(408))+stage_slot*ns
        store_work+=2048+pending*(256+row_map(408)+128+128)+nr*128
        store_work+=128+len(snap)*256+sum(len(x[0]) for x in snap.values())*(copy(649)+copy(382)+8)
        role=(512+1536*epoch+1024*encounters+4224*cum_rows,encounters,cum_rows,encounters-cum_rows,
            cum_rows,cum_slots,epoch,max_rows,max_slots)
        s=(store_work,cum_rows,cum_rows,cum_slots,epoch,qwork,quantized,epoch,exports,export_slots,len(snap),0,
            sum(len(x[0]) for x in snap.values()),0)
        lookups=3*cum_rows+exports
        cat=(1024+16*408+lookups*(512+256*20+32*(409).bit_length()+8*21),lookups,len(blocks),len(seen),
            sum(row[4] for row in seen.values()),len(menus),f['catalog_words'],64*f['catalog_words'])
        actual=record['receipt']
        need(actual[:9] == role and actual[9:23] == s and actual[24:32] == cat,
             'role exact owner/read/commit/quantizer/catalog ledgers')
        need(previous_peak <= actual[23] <= rf[13] and previous_history <= actual[32] <= f['history_work'],
             'role modeled Store peak/History bounded monotone ledgers')
        previous_peak,previous_history=actual[23],actual[32]
        chance=65536+16384*2652+epoch*(12288+64*1326+256*(1326).bit_length())
        need(actual[33:] == (chance,2*epoch,epoch) and actual[0] <= f['role_own_work'] and
             store_work+qwork+actual[0] <= f['component_work'], 'role chance/component actual ledgers')


def verify(raw, request, profile, selectors, rule):
    admission=plan(profile,selectors,rule)
    tapes=request_tapes(request,profile,selectors)
    records=parse(raw,profile,selectors,tapes)
    # All framing, counts, widths and complete reservations precede physical
    # range/template preparation and the independent mathematical walk.
    receipts(records)
    ctx=Context(profile,selectors,rule);ctx.run()
    return compare(records,request,ctx,admission,len(raw))


def compare(records,request,ctx,admission,wire_bytes):
    """Compare an already independently generated request without a second law build.

    Original studies generate the admitted literal request before native launch;
    saved replay uses verify(), admitting the complete frame before fresh math.
    """
    expected=ctx.records
    need(request == ctx.request(), 'role literal oracle supplied transcript request')
    coordinates=0
    for got,want in zip(records,expected):
        world=want['world'];h=got['world']
        need(h[3:15] == (*world.holding_indices,*world.holdings[0],*world.holdings[1],*world.board,world.showdown_sign+1),
             'role independent full1326 joint chance decode')
        need(got['roots'] == tuple(s['root'] for s in want['samples']) and
             got['counts'] == tuple(tuple(s['counts'][i] for s in want['samples']) for i in range(7)) and
             got['raw'] == want['raw'] and got['choices'] == tuple(x for s in want['samples'] for x in s['choices']) and
             got['peak_bits'] == want['peak_bits'], 'role independent literal roots/raw roles/choices/width')
        snapshot={public:(*want['numeric'][key],want['policy'].get(key,uniform(k)))
            for public,(key,_,k) in ctx.transport.items() if key in want['numeric']}
        need(got['snapshot'] == snapshot, 'role independent all retained regret/average/policy coordinates')
        coordinates+=sum(3*row[4] for row in want['raw'])+sum(3*len(x[0]) for x in snapshot.values())+2
    return {'contract':'opponent-role-four-street-literal-v1','profile':ctx.profile,'selectors':ctx.selectors,'rule':ctx.rule,
        'executed_signed_regret_epochs':2,'production_calls':0,'rng_calls':0,'quality_gate':None,
        'all_numeric_coordinates':coordinates,'raw_rows':[len(r['raw']) for r in records],
        'retained_rows':[len(r['snapshot']) for r in records],'wire_bytes':wire_bytes,
        'native_forecast':admission['native'],'sample_reference_receipt':ctx.meter.receipt(),
        'ledger_scope':'Exact raw work, role, Store work/reads/commits/quantizer, Catalog and chance; bounded monotone Store payload peak and History work. Logical models, not RSS.'}


def verify_controls(raw):
    need(type(raw) is bytes and len(raw)<=65536,'role controls bounded text')
    lines=raw.decode('ascii').splitlines();role=forecast(1,4,2,8,2)
    cat_words=1024+32*8+320*8+8;cat_work=1024+16*8+64*(512+256*20+32*(9).bit_length()+8)
    control=(43000000+42000000+cat_work+2000000+role[2]+1000000+16*65536,
        131072+32*1105+1+cat_words+24000+role[5]+16384+2*65536,
        131072*64+(8<<20)+64*cat_words+2*(1<<20)+role[6]+(1<<22)+16*65536)
    need(lines[0]=='CONTROL_BUDGET '+' '.join(map(str,control)) and lines[-1]=='ROLE_WALK_CONTROLS_PASS 48 7 8',
         'role controls complete forecast/footer')
    profiles=((Q//2,Q//2),(Q,0),(0,Q),(1,Q-1),(Q//3+1,Q//3,Q//3),(0,Q//2,Q//2),(1,Q-3,1,1),(0,0,Q,0))
    expected=[]
    for i,units in enumerate(profiles):
        left=0
        for a,u in enumerate(units):
            if u:
                for ticket in (left,left+u-1,left+(u-1)//2):
                    point=Fraction(ticket,Q)
                    need(Fraction(sum(units[:a]),Q)<=point<Fraction(sum(units[:a+1]),Q),'role controls Fraction CDF')
                    expected.append((i,len(units),ticket,a,*units))
            left+=u
    selected=[];packed={};guards=set()
    for line in lines[1:-1]:
        v=line.split()
        if v[0]=='SELECT':selected.append(tuple(map(int,v[1:])))
        elif v[0]=='PACK':
            i,n,*words=map(int,v[1:]);need(i not in packed and len(words)==7,'role controls signed word extent')
            need(struct.pack('<7Q',*words)==n.to_bytes(56,'little',signed=True),'role controls independent signed codec')
            packed[i]=n
        else:
            need(len(v)==3 and v[0]=='GUARD' and v[2]=='PASS' and v[1] not in guards,'role controls real guard record')
            guards.add(v[1])
    need(selected==expected and packed==dict(enumerate((0,1,-1,16*D,-16*D,D-1,-(D-1)))) and guards=={
        'ticket-Q','empty-menu','single-action','short-partition','overflow-partition','wide-pack','wide-unpack','foreign-active-world'},
        'role controls complete independent matrix')
    return {'queries':48,'signed_codec_numbers':7,'runtime_guards':8,'complete_forecast':control}
