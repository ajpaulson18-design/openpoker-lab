"""Bounded streaming exact-reference artifacts for the PROOF9 update proof.

The checksum detects byte drift; it does not authenticate source or establish
independence. No producer/ranker/build is executed by this codec.
"""
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import hashlib
import json
import re
from tests.virtual_frozen_probe_protocol import HANDS, request

BITS = 4096
MAX_LINE = 32768
MAX_HEADER = 4096
HEX = re.compile(r'(?:0|-?[1-9a-f][0-9a-f]*)\Z')
SHAPES = {'sampled': (868,2078), 'expected': (24420,58164)}


def artifact_allowance(kind, rows, slots):
    if (type(kind) is not str or kind not in SHAPES or type(rows) is not int or type(slots) is not int or
            not 1 <= rows <= SHAPES[kind][0] or not rows <= slots <= min(4*rows,SHAPES[kind][1])):
        raise ValueError('artifact shape outside fixed bounds')
    fields = rows + 2*slots
    size = 8192 + rows*(256+15*130) + slots*130 + 2*fields*(BITS//4+4)
    return {'bytes':size, 'row_bytes':MAX_LINE, 'scalar_fields':fields,
            'work':size+32*fields, 'entries':32*rows+8*slots+60*rows+16*MAX_LINE,
            'retained_integer_payload_bits':2*BITS*fields,
            'row_scratch_integer_and_text_bits':64*BITS+8*MAX_LINE,
            'scope':'bounded framing/model entries and integer payload, not CPU/RSS'}


def _dump(value):
    return (json.dumps(value,ensure_ascii=True,separators=(',',':'))+'\n').encode('ascii')


def _loads(raw):
    if not raw.endswith(b'\n') or len(raw)>MAX_LINE or any(x!=10 and not 32<=x<=126 for x in raw):
        raise ValueError('invalid artifact line')
    # Check nesting before JSON creates any containers. Ignore delimiters in
    # quoted strings, including escaped quotes/backslashes.
    quoted = escaped = False
    depth = 0
    for byte in raw:
        if quoted:
            if escaped: escaped=False
            elif byte==92: escaped=True
            elif byte==34: quoted=False
        elif byte==34: quoted=True
        elif byte in (91,123):
            depth+=1
            if depth>6:raise ValueError('artifact nesting bound')
        elif byte in (93,125):depth-=1
    def number(text):
        if len(text)>8:raise ValueError('artifact decimal width')
        return int(text)
    def pairs(values):
        result={}
        for key,value in values:
            if key in result:raise ValueError('duplicate artifact field')
            result[key]=value
        return result
    def no_float(_):raise ValueError('floating artifact field')
    return json.loads(raw,parse_int=number,parse_float=no_float,
                      parse_constant=no_float,object_pairs_hook=pairs)


def _integer(value):
    if type(value) is not str or len(value)>BITS//4+1 or not HEX.fullmatch(value):
        raise ValueError('invalid artifact exact integer')
    digits=value[1:] if value.startswith('-') else value
    if len(digits)>BITS//4:raise ValueError('artifact integer width')
    return int(value,16)


def _fraction(value):
    if type(value) is not list or len(value)!=2:raise ValueError('invalid rational pair')
    n,d=map(_integer,value)
    if d<=0:raise ValueError('nonpositive artifact denominator')
    return Fraction(n,d)


def _pair(value):
    if (type(value) is not Fraction or value.numerator.bit_length()>BITS or
            value.denominator.bit_length()>BITS):
        raise ValueError('artifact rational width')
    return [format(value.numerator,'x'),format(value.denominator,'x')]


@dataclass(frozen=True)
class SavedReferenceRow:
    actor: int
    hand_ids: tuple
    history: tuple
    actions: tuple
    action_exponents: tuple
    regret_masses: tuple
    average_mass: Fraction
    average_action_masses: tuple
    @property
    def key(self):return self.actor,self.hand_ids,self.history
    @property
    def average_reach_mass(self):return self.average_mass


def _decode_row(value,index):
    if type(value) is not list or len(value)!=10 or type(value[0]) is not int or value[0]!=index:
        raise ValueError('artifact row framing/order')
    _,actor,hand,history,actions,exponents,mass,regrets,averages,tag=value
    if (type(actor) is not int or actor not in HANDS or type(hand) is not list or
            len(hand)!=2 or any(type(c) is not int for c in hand) or tuple(hand) not in HANDS[actor]):
        raise ValueError('artifact physical identity')
    if (type(history) is not list or len(history)>15 or type(actions) is not list or
            not 1<=len(actions)<=4 or any(type(t) is not str for t in actions) or len(set(actions))!=len(actions)):
        raise ValueError('artifact history/menu shape')
    if any(type(t) is not str or not 0<len(t)<=64 or any(not 33<=ord(c)<=126 for c in t)
           for t in (*history,*actions)):
        raise ValueError('artifact token bound')
    if (type(exponents) is not list or len(exponents)!=len(actions) or
            any(type(e) is not int or not -1<=e<=19 for e in exponents) or
            type(regrets) is not list or type(averages) is not list or
            len(regrets)!=len(actions) or len(averages)!=len(actions) or tag!='row'):
        raise ValueError('artifact vector shape')
    mass=_fraction(mass);regrets=tuple(map(_fraction,regrets));averages=tuple(map(_fraction,averages))
    # Mathematical values are preserved, not certified by the transport. Avoid
    # multiplying independent 4096-bit rational denominators during framing.
    if mass<0 or any(value<0 for value in averages):
        raise ValueError('negative artifact average')
    units=sum(0 if e<0 else 1<<(19-e) for e in exponents)
    if units!=1<<19:raise ValueError('artifact policy partition')
    return SavedReferenceRow(actor,tuple(hand),tuple(history),tuple(actions),tuple(exponents),regrets,mass,averages)


def _metadata(kind,result,rows,slots):
    artifact_allowance(kind,rows,slots)
    if kind=='sampled':
        board=tuple(result.admission.board);law=result.admission.proposal_law
        if law not in ('uniform','river_weighted'):raise ValueError('artifact proposal law')
        request('EVAL','UNIFORM' if law=='uniform' else 'RIVER_WEIGHTED',board)
    else:board=law=None
    return {'version':'exact-frozen-reference-v1','kind':kind,'rows':rows,'slots':slots,
            'board':board,'law':law,'integer_bits':BITS}


def write_reference(path,result,kind,*,byte_limit=None):
    """Exclusive output, bounded row buffer; retain incomplete file on failure."""
    rows=len(result.rows)
    if type(kind) is not str or kind not in SHAPES or rows>SHAPES[kind][0]:raise ValueError('artifact row count')
    slots=0
    for row in result.rows.values():
        if (len(row.history)>15 or not 1<=len(row.actions)<=4 or len(row.hand_ids)!=2 or
                len(row.action_exponents)!=len(row.actions) or len(row.regret_masses)!=len(row.actions) or
                len(row.average_action_masses)!=len(row.actions)):
            raise ValueError('artifact input shape')
        if any(type(t) is not str or not 0<len(t)<=64 or any(not 33<=ord(c)<=126 for c in t)
               for t in (*row.history,*row.actions)):
            raise ValueError('artifact input token bound')
        slots+=len(row.actions)
    header=_metadata(kind,result,rows,slots);allowance=artifact_allowance(kind,rows,slots)
    cap=allowance['bytes'] if byte_limit is None else byte_limit
    if type(cap) is not int or not allowance['bytes']<=cap<=allowance['bytes']:
        raise ValueError('complete artifact byte admission exceeded')
    digest=hashlib.sha256();total=0;seen=set()
    with Path(path).open('xb') as output:
        def put(raw,hash_body=True):
            nonlocal total
            if len(raw)>MAX_LINE or total+len(raw)>cap:raise ValueError('artifact byte forecast exceeded')
            output.write(raw);total+=len(raw)
            if hash_body:digest.update(raw)
        put(_dump(header))
        for index,(key,row) in enumerate(result.rows.items()):
            mass=row.average_mass if kind=='sampled' else row.average_reach_mass
            value=[index,row.actor,list(row.hand_ids),list(row.history),list(row.actions),
                   list(row.action_exponents),_pair(mass),list(map(_pair,row.regret_masses)),
                   list(map(_pair,row.average_action_masses)),'row']
            line=_dump(value)
            checked=_decode_row(value,index)
            if key!=checked.key or checked.key in seen:raise ValueError('artifact duplicate/mismatched key')
            seen.add(checked.key);put(line)
        body_sha=digest.hexdigest()
        put(_dump({'end':rows,'body_sha256':body_sha}),False)
    return {'bytes':total,'body_sha256':body_sha,'rows':rows,'slots':slots,'allowance':allowance}


def read_reference(path,*,byte_limit):
    """Load bounded semantic rows; no complete-file byte/string buffer."""
    if type(byte_limit) is not int or not 0<byte_limit<=artifact_allowance('expected',24420,58164)['bytes']:
        raise ValueError('reader byte limit')
    digest=hashlib.sha256();total=0;cap=byte_limit
    with Path(path).open('rb') as source:
        def line(maximum=MAX_LINE,hash_body=True):
            nonlocal total
            raw=source.readline(min(maximum,cap-total)+1)
            if not raw or len(raw)>maximum or total+len(raw)>cap:raise ValueError('artifact read byte bound/truncation')
            total+=len(raw)
            if hash_body:digest.update(raw)
            return raw
        headraw=line(MAX_HEADER);header=_loads(headraw)
        required={'version','kind','rows','slots','board','law','integer_bits'}
        if type(header) is not dict or set(header)!=required or header['version']!='exact-frozen-reference-v1' or header['integer_bits']!=BITS:
            raise ValueError('artifact header')
        allowance=artifact_allowance(header['kind'],header['rows'],header['slots'])
        if allowance['bytes']>byte_limit:raise ValueError('whole artifact reader admission')
        cap=allowance['bytes']
        if header['kind']=='sampled':
            admission=SimpleNamespace(board=tuple(header['board']),proposal_law=header['law'])
            _metadata('sampled',SimpleNamespace(admission=admission),header['rows'],header['slots'])
        else:
            if header['board'] is not None or header['law'] is not None:raise ValueError('q-free artifact has proposal data')
            admission=None
        rows={};slots=0
        for index in range(header['rows']):
            row=_decode_row(_loads(line()),index)
            if row.key in rows:raise ValueError('duplicate artifact full key')
            slots+=len(row.actions)
            if slots>header['slots']:raise ValueError('artifact slot count exceeded')
            rows[row.key]=row
        expected=digest.hexdigest();footer=_loads(line(MAX_HEADER,False))
        if (type(footer) is not dict or type(footer.get('end')) is not int or
                footer!={'end':header['rows'],'body_sha256':expected} or slots!=header['slots']):
            raise ValueError('artifact footer/checksum/count mismatch')
        if source.read(1):raise ValueError('trailing artifact bytes')
    return SimpleNamespace(rows=MappingProxyType(rows),admission=admission,
                           receipt={'bytes':total,'body_sha256':expected,'allowance':allowance,
                                    'scope':'saved semantic artifact only; no source provenance implied'})



def reference_study_allowance():
    """Whole semantic-export family, excluding native/log/source artifacts.

    107,080 row records per law is separately established by the complete
    rank-free census. Four slots per row bounds every admitted legal menu.
    """
    row_records, slot_records, boards = 107080, 4*107080, 2520
    scalar_fields = row_records + 2*slot_records
    law_bytes = (8192*boards + row_records*(256+15*130) + slot_records*130 +
                 2*scalar_fields*(BITS//4+4))
    expected = artifact_allowance('expected',24420,58164)
    total = 2*law_bytes + expected['bytes']
    fields = 2*scalar_fields + expected['scalar_fields']
    return {'sampled_law_bytes_upper':law_bytes,'q_free_bytes_upper':expected['bytes'],
            'all_reference_artifact_bytes_upper':total,
            'one_export_or_read_named_work_upper':total+32*fields,
            'scope':'semantic rows only; native stdout/stderr, requests, receipts, source/build closure and outer logs require separate admission',
            'full_study_admission':False}
