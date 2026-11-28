"""Independent bounded parser for the sparse strategy-catalog identity controls.

This validates catalog coordinates and menus only. Declared holding indices are
generic identities; this module makes no physical-support, policy, or quality
claim for them.
"""

from tests.virtual_frozen_value_reference import _reveal_token

WIRE_LIMIT=65536
VERSION='VIRTUAL_STRATEGY_CATALOG_V1'
ROW_LABELS=('root-first','root-last','after-action','flop-a','flop-b')
CONTROL_LABELS=('sparse-endpoints','action-perfect-recall','ordered-prefix-perfect-recall')
GUARD_LABELS=(
    'default-row-id-poisons','foreign-row-id-poisons','foreign-history-poisons',
    'unknown-holding-poisons','wrong-actor-poisons','changed-menu-poisons',
    'row-cap-poisons','metadata-one-short','work-one-short','view-read-cap-poisons',
    'zero-block-limit','holding-limit','work-limit',
)


def _require(condition,message):
    if not condition:
        raise ValueError(message)


def _decode_full_key(fixture,ordinal,actor,holding):
    """Decode the compact ordinal using independent literal occurrence paths."""
    _require(0<=ordinal<1<<64,'row ordinal outside uint64')
    occurrence,length=ordinal>>33,(ordinal>>30)&7
    packed=ordinal&((1<<30)-1)
    _require(occurrence<len(fixture.paths),'ordinal occurrence is unknown')
    _require(length in (0,3,4,5),'ordinal visible-prefix length is invalid')
    _require(not packed>>(6*length),'ordinal has nonzero unused card bits')
    board=tuple((packed>>(6*i))&63 for i in range(length))
    _require(len(set(board))==length and set(board)<=set(fixture.deck),'ordinal board is invalid')
    _require(length<3 or tuple(sorted(board[:3]))==board[:3],'ordinal flop ordering is invalid')
    source,_,_,street,_=fixture.paths[occurrence]
    _require(street==length,'ordinal prefix length disagrees with occurrence')
    tokens=[]
    while occurrence:
        _,parent,token,visible,_=fixture.paths[occurrence]
        tokens.append(token if token is not None else _reveal_token(board,visible))
        occurrence=parent
    node=fixture.nodes[source]
    _require(node.phase=='decision','row ordinal does not identify a decision')
    _require(actor==node.state.player,'row actor disagrees with independent template')
    menu=tuple(edge.token for edge in node.edges)
    _require(2<=len(menu)<=20,'independent decision menu extent')
    return {
        'ordinal':ordinal,'actor':actor,'holding_index':holding,
        'history_tokens':list(reversed(tokens)),'visible_board':list(board),
        'source_menu_ref':source,'actions':list(menu),
    }


def _parse_row(parts,fixture):
    _require(len(parts)>=7 and parts[0]=='ROW','malformed ROW record')
    label=parts[1]
    _require(label in ROW_LABELS,'unknown row label')
    try:
        ordinal,actor,holding,source,menu_count=map(int,parts[2:7])
    except ValueError as exc:
        raise ValueError('nonnumeric ROW field') from exc
    _require(all(v>=0 for v in (ordinal,actor,holding,source,menu_count)),'negative ROW field')
    actions=parts[7:]
    _require(len(actions)==menu_count,'ROW action count differs from frame')
    key=_decode_full_key(fixture,ordinal,actor,holding)
    _require(key['source_menu_ref']==source,'ROW menu source differs from ordinal')
    _require(key['actions']==actions,'ROW ordered menu differs from independent template')
    key['label']=label
    return key


def parse_catalog_wire(raw,fixture):
    """Parse one exact native stdout frame and independently verify all fields.

    Returns only bounded identity metadata. No catalog row is interpreted as
    physically reachable just because its declared generic holding index is in
    range.
    """
    _require(type(raw) is bytes,'catalog frame must be raw bytes')
    _require(0<len(raw)<=WIRE_LIMIT,'catalog frame byte limit')
    _require(raw.endswith(b'\n'),'catalog frame must end in newline')
    _require(b'\0' not in raw,'catalog frame contains NUL')
    # Windows text-mode stdout translates each LF to CRLF. Accept either
    # complete convention, but reject bare CR and mixed line endings.
    crlf=raw.count(b'\r\n')
    normalized=raw.replace(b'\r\n',b'\n')
    _require(b'\r' not in normalized,'catalog frame contains bare CR')
    _require(crlf==0 or crlf==raw.count(b'\n'),'catalog frame mixes newline conventions')
    try: text=normalized.decode('ascii')
    except UnicodeDecodeError as exc: raise ValueError('catalog frame is not ASCII') from exc
    lines=text[:-1].split('\n')
    _require(all(lines) and lines[0]==VERSION and lines[-1]=='END','catalog frame boundary/version')
    _require(all(len(line)<=4096 for line in lines),'catalog line byte limit')

    rows=[];controls=[];guards=[];receipt=None;events=[]
    for line in lines[1:-1]:
        parts=line.split()
        _require(parts,'empty catalog record')
        tag=parts[0]
        if tag=='ROW':
            _require(receipt is None and not guards and len(controls)<=2,
                     'ROW appeared outside its frame position')
            parsed=_parse_row(parts,fixture); rows.append(parsed)
            events.append(('ROW',parsed['label']))
            _require(len(rows)<=len(ROW_LABELS),'too many ROW records')
        elif tag=='CONTROL':
            _require(receipt is None and not guards and len(parts)==3 and parts[2]=='PASS',
                     'malformed or unordered CONTROL record')
            controls.append(parts[1]);events.append(('CONTROL',parts[1]))
        elif tag=='GUARD':
            _require(len(rows)==5 and len(controls)==3 and receipt is None and len(parts)==3 and parts[2]=='PASS',
                     'malformed or unordered GUARD record')
            guards.append(parts[1]);events.append(('GUARD',parts[1]))
        elif tag=='RECEIPT':
            _require(tuple(guards)==GUARD_LABELS and receipt is None and len(parts)==9,
                     'malformed or unordered RECEIPT record')
            try: receipt=tuple(map(int,parts[1:]))
            except ValueError as exc: raise ValueError('nonnumeric RECEIPT field') from exc
            events.append(('RECEIPT',''))
        else:
            raise ValueError('unknown catalog record')

    _require(tuple(row['label'] for row in rows)==ROW_LABELS,'missing, duplicate, or unordered row labels')
    _require(tuple(controls)==CONTROL_LABELS,'missing, duplicate, or unordered control claims')
    _require(tuple(guards)==GUARD_LABELS,'missing, duplicate, or unordered guard records')
    expected_events=(('ROW','root-first'),('ROW','root-last'),('CONTROL','sparse-endpoints'),
        ('ROW','after-action'),('CONTROL','action-perfect-recall'),('ROW','flop-a'),
        ('ROW','flop-b'),('CONTROL','ordered-prefix-perfect-recall'),
        *(('GUARD',label) for label in GUARD_LABELS),('RECEIPT',''))
    _require(tuple(events)==expected_events,'catalog record sequence differs from frozen frame')
    _require(receipt is not None,'missing catalog receipt')

    indexed={row['label']:row for row in rows}
    first,last=indexed['root-first'],indexed['root-last']
    _require((first['ordinal'],first['actor'],first['source_menu_ref'],first['actions'])==
             (last['ordinal'],last['actor'],last['source_menu_ref'],last['actions']),
             'sparse endpoint holdings do not share their public row/menu')
    _require((first['actor'],first['holding_index'],last['holding_index'])==(0,0,1325),
             'declared holding endpoints differ')
    after=indexed['after-action']
    _require(after['ordinal']!=first['ordinal'] and after['history_tokens']!=first['history_tokens'],
             'different action history collapsed')
    flop_a,flop_b=indexed['flop-a'],indexed['flop-b']
    _require(flop_a['ordinal']!=flop_b['ordinal'] and flop_a['history_tokens']!=flop_b['history_tokens'],
             'different ordered visible prefixes collapsed')
    _require((flop_a['source_menu_ref'],flop_a['actor'],flop_a['actions'])==
             (flop_b['source_menu_ref'],flop_b['actor'],flop_b['actions']),
             'same source-node menu was not preserved across public prefixes')
    _require(len({(r['ordinal'],r['actor'],r['holding_index']) for r in rows})==5,
             'public information-row coordinates are not distinct')

    work,lookups,blocks,seen_rows,slots,menus,entries,payload=receipt
    # Fixed control geometry: B=8, M=8, H=1326, K=32; the fixture emits 16
    # accesses. Keep this arithmetic independent from the native forecast API.
    b,m,h,k,accesses=8,8,1326,32,16
    expected_work=1024+8*b+8*m+accesses*(512+256*20+32*(b+1).bit_length()+8*((h+63)//64))
    expected_entries=1024+32*b+320*m+b*((h+63)//64)
    _require((work,lookups,blocks,seen_rows,slots,menus,entries,payload)==
             (expected_work,accesses,4,5,19,3,expected_entries,expected_entries*64),
             'receipt differs from independent fixed-geometry equation')
    _require(work<=75_000_000 and entries<=2_000_000 and payload<=1<<30,
             'receipt exceeds catalog component caps')
    _require(sum(len(row['actions']) for row in rows)==slots,
             'action-slot receipt differs from emitted information rows')
    return {
        'scope':'identity and legal-menu controls only; no physical-support, policy, training, or quality claim',
        'rows':rows,'controls':list(controls),'guards':list(guards),
        'receipt':{'work':work,'lookups':lookups,'public_blocks':blocks,
                   'information_rows_seen':seen_rows,'action_slots_seen':slots,
                   'menus':menus,'metadata_entries':entries,'metadata_payload_bits':payload},
    }
