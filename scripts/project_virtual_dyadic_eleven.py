"""Rank-free N11 two-sweep work forecast with explicit experimental prerequisites."""
from collections import Counter
from functools import lru_cache
from hashlib import sha256
from itertools import combinations, permutations
import json
from math import comb
from pathlib import Path

from scripts.census_virtual_dyadic_storage import supported_prefixes
from tests.virtual_dyadic_stage_schedule import stage_schedule
from tests.virtual_dyadic_directory_trace import directory_trace
from tests.full_deck_public_chance_reference import PROOF9, proof_ranges
from tests.virtual_betting_template_reference import build_reference_template
from tests.virtual_frozen_update_reference import _template_case

template = build_reference_template(_template_case())
ranges = proof_ranges()
PRIOR_PATH = (Path(__file__).resolve().parents[1] / "benchmarks/results"
              / "native-dyadic-indexed-cache-ten-card-accepted-v1/manifest.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def words(bits):
    return (bits + 63) // 64


def uniform_exp(actions):
    return {2: 1, 4: 2}.get(actions, 52)


@lru_cache(None)
def tail(i):
    node=template.nodes[i]
    return (uniform_exp(len(node.edges)) if node.phase=='decision' else 0)+max(
        (tail(edge.child) for edge in node.edges),default=0)

def cost(m,e,bits,divisions):
    total=e+(m-1).bit_length()+1
    scaled=e+52
    high=max(53,total,scaled)
    return (64+16*m+4*m*(words(bits)+1)+256+16*m*(words(high)+1)
            +8*m*(divisions*words(scaled)*words(total)+4*words(high)+8)
            +4*m*m*(words(total)+1))

def forecast(n,bits,base_bits,divisions):
    deck=tuple(sorted((*PROOF9,*range(n-9))))
    r={(street,p):sum(supported_prefixes(deck,p,hand,street,ranges) for hand,_ in ranges[p])
       for street in (0,3,4,5) for p in (0,1)}
    out=[0,0,0]
    def visit(i,past,first):
        node=template.nodes[i]
        if node.phase=='decision':
            p=node.state.player
            m=len(node.edges)
            rows=r[node.street,p]
            e=first[1-p]+tail(i)
            ea=52*(past[p]+1)
            out[0]+=rows*(320+48*m)
            out[1]+=rows*cost(m,base_bits+2+4+1+e,bits,divisions)
            out[2]+=rows*cost(m,base_bits+2+ea,bits,divisions)
            past=tuple(v+int(j==p) for j,v in enumerate(past))
            first=tuple(v+(uniform_exp(m) if j==p else 0) for j,v in enumerate(first))
        for edge in node.edges:
            visit(edge.child,past,first)
    visit(template.root,(0,0),(0,0))
    return out


def collect(n,bits,base_bits):
    deck=tuple(sorted((*PROOF9,*range(n-9))))
    occupied=[set(a)|set(b) for a,_ in ranges[0] for b,_ in ranges[1] if set(a).isdisjoint(b)]
    prefixes={k:set() for k in (0,3,4,5)}
    for private in occupied:
        left=set(deck)-private
        for flop in combinations(sorted(left),3):
            for reveal in permutations(sorted(left-set(flop)),2):
                board=flop+reveal
                for k in prefixes:
                    prefixes[k].add(board[:k])
    np={k:len(rows) for k,rows in prefixes.items()}
    supported={(k,p):sum(supported_prefixes(deck,p,hand,k,ranges) for hand,_ in ranges[p])
               for k in np for p in (0,1)}
    shape=Counter()
    value_add=scaled_average=0
    add=lambda width:2+3*words(width)
    cp=lambda width:1+2*words(width)
    mul=lambda a,b:2+2*(words(a)+words(b))+words(a)*words(b)
    candidates=lambda k:comb(n,3) if k==0 else n-k
    visits_order=(0,3,4,5)
    def walk(i,past):
        nonlocal value_add,scaled_average
        node=template.nodes[i]
        k=node.street
        shape['visits']+=np[k]
        if node.phase=='decision':
            m=len(node.edges)
            p=node.state.player
            r=supported[k,p]
            shape['actions']+=np[k]*m
            shape['rows']+=r
            shape['slots']+=r*m
            value_add+=4*np[k]*m*add(bits)
            past_bits=52*past[p]
            row_bits=past_bits+base_bits
            scaled_average+=2*r*(32+mul(past_bits+1,base_bits)+cp(row_bits)+m*(8+mul(row_bits,53)))
            past=tuple(v+int(j==p) for j,v in enumerate(past))
        elif node.phase=='reveal':
            count=np[node.state.board_length]
            shape['reveals']+=count
            shape['candidates']+=np[k]*candidates(k)
            value_add+=8*count*add(bits)
        elif node.phase=='showdown':
            shape['showdowns']+=np[k]
            shape['showdown_contractions']+=np[5]
            if k<5:
                shape['hidden_candidates']+=sum(np[j]*candidates(j) for j in visits_order[visits_order.index(k):-1])
                value_add+=8*np[5]*add(bits)
        elif node.phase=='fold':
            shape['folds']+=np[k]
        else:
            raise ValueError(node.phase)
        for edge in node.edges:
            walk(edge.child,past)
    walk(template.root,(0,0))
    return dict(shape),np,scaled_average,value_add

def project(n, stage, directory, chance_forecast):
    d5=comb(n-4,3)*(n-7)*(n-8)
    base=29*d5
    db=base.bit_length()+625
    bits=db+7
    shape,prefixes,scaled_average,value_add=collect(n,bits,base.bit_length())
    r,s=shape['rows'],shape['slots']
    A,G=stage['average_words'],stage['regret_words']
    L=A+G
    require((stage['rows'], stage['slots'], stage['image_words']) == (r, s, L),
            'strategy trace geometry differs')
    require(directory['logical_reads'] == 10 * r, 'directory trace geometry differs')
    require(stage['logical_read_calls'] == 7 * r and stage['direct_write_calls'] == 4 * r,
            'strategy request schedule differs')
    pwork=(16*11*s+2*(5*A+6*G)+16*L+8*4*s+4*L+160*stage['batched_write_calls']
           +2*(4096+64+1) -(16*11+8*4)*(s-r))
    dwork=4*4608+16*r+16*10*r+4*directory['misses']*128
    spill=2*(32*r+16*(s-r)+4*s)+64
    codecA=32*r+36*A+(6*words(bits)+70)*s
    codecG=32*r+44*G+(16*words(bits)+88)*s
    add=lambda width:2+3*words(width)
    copy=lambda width:1+2*words(width)
    mul=lambda a,b:2+2*(words(a)+words(b))+words(a)*words(b)
    parent={'geometry':3_000_000,'visit':32*shape['visits'],
            'support':64*(3*shape['candidates']+2*shape['hidden_candidates']),
            'reach':2*shape['actions']*(24+2*(mul(365,53)+copy(365))),
            'value_add':value_add,
            'terminal_scale':8*(shape['showdowns']+shape['folds'])*(16+mul(bits,4)+mul(bits,6)+copy(bits)),
            'average':scaled_average+4*(shape['reveals']+1)*24+codecA,
            'route':48*r+4*s+codecG+pwork+dwork+spill,
            'output':6*s+24*r+2*(6*s+32*r)+160*1105+65536}
    history=4096*1105+1280+3*(40*shape['actions']+72*shape['reveals']+48*shape['visits']+40*r)-8*r+24*146+16*371+32*r
    registration=64*146+16*371+16*r
    state=(1024+8*r+16*s+4*words(db)+160*r+registration+8*s+2*r
           +2*(88*r+132*s+(16*s+8*r)*words(bits+58))+(4*words(bits)+4)*s+20*r+4*s)
    terms=forecast(n,bits,base.bit_length(),1)
    components={'template':42556544,'chance':chance_forecast,'history':history,'state':state,
                'quantizer':sum(terms),'parent':sum(parent.values())}
    stream=8+16*8+11*8+1105*96+r*24+2*(8*s+4*12*8)+8*s+r+8+64*8
    transport=2*(2*L+64*((8*L+32767)//32768)+32)
    # Extend the accepted paged-phase envelope by row tags. Include the
    # row-batched codec increment and the separate streaming reservation.
    state_payload = 8 * (16_384 + 36_864 + (410 + 388) * 16 + 591_008
                         + r + 1_024 + 88 + 256 * words(bits + 58) * 8 + (352 - 88))
    owner_payload = state_payload + 13_637_280
    state_entries = 7_675 + r + 128 + (591_008 + 88) // 8 + (352 - 88) // 8
    owner_entries = state_entries + 159_417
    return {
        'deck_cards': n, 'd5': d5, 'denominator_base': base, 'denominator_shift': 625,
        'denominator_bits': db, 'value_bits': bits, 'state_integer_bits_with_scratch': bits + 58,
        'shape': shape, 'supported_prefixes': prefixes, 'component_work': components,
        'parent_work': parent, 'quantizer_terms': terms, 'paging_work': pwork, 'directory_work': dwork,
        'retained_numerical_bytes': stream, 'wire_bytes': stream + 2 * (32 + 8 * L),
        'numerical_work': sum(components.values()), 'transport_work': transport,
        'composed_work_with_transport': sum(components.values()) + transport,
        'state_payload_bits': state_payload, 'owner_payload_bits': owner_payload,
        'composed_payload_bits': owner_payload + 8 * (32_768 + 32),
        'state_entries': state_entries, 'owner_entries': owner_entries,
        'composed_entries': owner_entries + (32_768 + 32) // 8,
    }


def main():
    prior_raw = PRIOR_PATH.read_bytes()
    prior = json.loads(prior_raw)
    # Reuse the independently reconstructed Chance ledger in the indexed
    # study. Its archive contains the full rank-free projection and sources.
    chance = prior['rank_free_chance_forecast']['fixtures']
    admission = prior['admission']
    ten_stage = stage_schedule(ten_card=True, virtual_zero=True, batch_rows=True)
    ten_directory = directory_trace()
    require(ten_directory == prior['row_directory']['independent_trace'],
            'ten-card directory trace differs from accepted evidence')
    n10 = project(10, ten_stage, ten_directory, chance['10']['indexed']['chance_total'])
    calibrations = {
        'component_work': admission['component_work'],
        'parent_work': admission['parent_work'],
        'quantizer_terms': admission['quantizer_terms'],
        'numerical_work': admission['planned_total_work'],
        'transport_work': admission['sweep_stream']['copy_work'],
        'retained_numerical_bytes': admission['output_bytes'],
        'wire_bytes': prior['sweep_capture']['contract']['wire_bytes'],
        'owner_entries': admission['entries'],
        'state_payload_bits': admission['state_payload_bits'],
        'owner_payload_bits': admission['payload_bits'],
        'paging_work': admission['paging_work'],
        'directory_work': admission['directory_work'],
    }
    for key, expected in calibrations.items():
        require(n10[key] == expected, f'ten-card {key} differs from accepted evidence')

    stage = stage_schedule(eleven_card=True, virtual_zero=True, batch_rows=True)
    directory = directory_trace(ten_card=False, eleven_card=True)
    n11 = project(11, stage, directory, chance['11']['indexed']['chance_total'])
    require((n11['d5'], n11['denominator_bits'], n11['value_bits']) == (420, 639, 646),
            'eleven-card integer geometry differs')
    work = n11['component_work']
    projections = {
        'composed_entries': (n11['composed_entries'], 2_000_000),
        'composed_payload_bits': (n11['composed_payload_bits'], 1_200_000_000),
        'template_work': (work['template'], 43_000_000),
        'chance_fixture_work': (work['chance'], 450_000_000),
        'chance_owner_work': (work['chance'], 500_000_000),
        'history_fixture_work': (work['history'], 100_000_000),
        'state_fixture_work': (work['state'], 300_000_000),
        'quantizer_fixture_work': (work['quantizer'], 520_000_000),
        'state_and_quantizer_owner_work': (work['state'] + work['quantizer'], 810_000_000),
        'composed_work': (n11['composed_work_with_transport'], 2_150_000_000),
        'native_retained_output_bytes': (n11['retained_numerical_bytes'], 9_833_076),
    }
    axes = {name: {'projected': value, 'ten_card_limit': limit, 'fits': value <= limit}
            for name, (value, limit) in projections.items()}
    terminal_nodes = n11['shape']['folds'] + n11['shape']['showdowns']
    result = {
        'status': 'rank_free_projection_only',
        'native_producer_calls': 0,
        'hand_rank_calls': 0,
        'n10_calibration_manifest_sha256': sha256(prior_raw).hexdigest(),
        'n10_calibrated_fields': list(calibrations),
        'n10_reproduced': n10,
        'n11_prospective': n11,
        'n11_independent_io_traces': {'row_batched_pager': stage, 'row_directory': directory},
        'capacity_axes': axes,
        'capacity_blockers': [name for name, axis in axes.items() if not axis['fits']],
        'terminal_scale_fusion': {
            'structural_operations_eliminated': 2 * 2 * 2 * terminal_nodes,
            'modeled_work_saved': 0,
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
