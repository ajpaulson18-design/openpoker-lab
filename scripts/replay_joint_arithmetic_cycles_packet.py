"""Saved exact arithmetic-observer replay; preserve the failed overhead gate."""
import argparse
import json
import math
from pathlib import Path
import statistics
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'benchmarks/results/joint-arithmetic-cycles-v1'
PIN = (2087, 'dc78a8c65b8be4e7f47ab8229fdd7c06611d259df4d52eb14b0e1f44a4db0233')
ORIGIN = '7d5401712a3f104628949e20a864db18bfe0a939'
LIGHT_PACKET = ROOT / 'benchmarks/results/joint-arithmetic-light-v1'
LIGHT_PIN = (2075, '1c7beace60d836d94ec015ec3b39c33c7a1a197b46674804d24f841a0dc4fcdb')
LIGHT_ORIGIN = 'dea4f35458481f67eb427645a39080753211dd14'


def replay(packet=None, *, light=False):
    packet = (LIGHT_PACKET if light else PACKET) if packet is None else Path(packet)
    origin = LIGHT_ORIGIN if light else ORIGIN
    from scripts import replay_joint_cycles_packet as base, joint_evidence_archive as archive
    from scripts import replay_joint_two_epoch_packet as helper, replay_lazy_joint_packet as mathematics
    need = base.need; digest = base.digest
    def bootstrap():
        prior = base.bootstrap(); name = 'scripts/replay_joint_arithmetic_cycles_packet.py'
        need(not base.git('status', '--porcelain', '--untracked-files=all', '--', name), 'arithmetic reader committed source')
        raw = archive.read(ROOT / name)
        need(digest(raw) in base.variants(base.git('show', prior[0] + ':' + name)), 'arithmetic reader raw source drift')
        return prior, digest(raw)
    before = bootstrap()
    need(not any(n == 'tests' or n.startswith(('tests.', 'pokerlab')) for n in sys.modules), 'arithmetic fresh numerical process')
    def load(): return archive.load(packet, helper, pin=LIGHT_PIN if light else PIN, version='joint-cycles',
        labels=('controls','parity','overhead','builds','objects'),
        packager='package_arithmetic_light1.py.txt' if light else 'package_arithmetic_cycles1.py.txt')
    manifest, loaded, pins = load()
    objects, captured, authentication = base.authenticate(loaded, helper, origin=origin,
        expected_inventory={'controls':2,'parity':270,'overhead':260,'builds':0,'objects':0},
        added_headers=('native/joint_thread_cycle_recorder.hpp','native/joint_arithmetic_light_recorder.hpp' if light else
                       'native/joint_arithmetic_cycle_recorder.hpp'), allowed_exits=(0,2))
    math_before = mathematics.current_math(helper, objects, captured)
    def parser_identity():
        hashes = {}
        names=('tests/virtual_joint_cycle_reference.py','tests/virtual_joint_arithmetic_cycle_reference.py',
               *(('tests/virtual_joint_arithmetic_light_reference.py',) if light else ()))
        for name in names:
            raw = mathematics.read(ROOT / name, 2 << 20); canonical = objects.body(origin, name)
            need(not base.git('status','--porcelain','--untracked-files=all','--',name) and digest(raw) in base.variants(canonical) and
                 digest(captured[name]) in base.variants(canonical), 'arithmetic current/captured parser drift')
            hashes[name] = digest(raw)
        return hashes
    parser_before = parser_identity(); previous = sys.pycache_prefix, sys.dont_write_bytecode
    with TemporaryDirectory(prefix='arithmetic-cycle-empty-cache-',dir=ROOT.parent) as cache:
        sys.pycache_prefix=cache;sys.dont_write_bytecode=True
        try:
            from tests.virtual_native_single_pass_reference import verify
            from tests.virtual_joint_arithmetic_cycle_reference import decode, numeric_sequence, grouped_sequence, COUNTS, FAMILIES
            if light:
                from tests.virtual_joint_arithmetic_light_reference import decode
            sequence = numeric_sequence(); parity = loaded['parity']
            wires = [parity[f'normal/standard-{case}/stdout.bin'] for case in range(4)]
            references = [verify(1,pair,raw) for pair,raw in zip(base.SELECTORS,wires)]
            def exited(files,prefix,code):
                receipt=helper.decode(files[prefix+'/process.json']);need(receipt['returncode']==code,'arithmetic exact original exit')
                duration=receipt['duration_seconds']
                need(type(duration) in (int,float) and math.isfinite(duration) and duration>0,'arithmetic finite duration')
                return duration
            for mode in ('normal','optimized'):
                need(helper.decode(parity[mode+'/independent-expected.json'])==json.loads(json.dumps(references)),'arithmetic current all-row math')
                for case in range(4):
                    prefix=f'{mode}/standard-{case}';exited(parity,prefix,0)
                    need(parity[prefix+'/stdout.bin']==wires[case] and parity[prefix+'/stderr.bin']==b'','arithmetic standard exact wire')
                    for offset in range(32):
                        prefix=f'{mode}/diagnostic-{case}-{offset}';duration=exited(parity,prefix,0)
                        need(parity[prefix+'/stdout.bin']==wires[case],'arithmetic every offset exact wire')
                        report=decode(parity[prefix+'/stderr.bin'],offset,sequence=sequence)
                        need(helper.decode(parity[prefix+'.json'])=={'case_index':case,'offset':offset,'duration_seconds':duration,'cpu':report},'arithmetic current offset accounting')
                for guard in ('arity','offset-boundary','negative'):
                    prefix=f'{mode}/reject-{guard}';exited(parity,prefix,2)
                    need(parity[prefix+'/stdout.bin']==b'' and parity[prefix+'/stderr.bin']!=b'','arithmetic original real rejection')
                need(helper.decode(parity[mode+'/result.json'])['actual_native_calls']==135,'arithmetic complete parity count')
            for mode in ('normal','optimized'):
                files=loaded['controls'];prefix=mode+'/native';exited(files,prefix,0)
                need(files[prefix+'/stderr.bin']==b'','arithmetic synthetic stderr')
                lines=files[prefix+'/stdout.bin'].splitlines(keepends=True);need(len(lines)==(48 if light else 47),'arithmetic synthetic record inventory')
                expected_marker=b'JOINT_ARITHMETIC_LIGHT_GUARDS_V1 PASS 15' if light else b'JOINT_ARITHMETIC_CYCLE_GUARDS_V1 PASS 14'
                need(lines[-1].rstrip(b'\r\n')==expected_marker,'arithmetic synthetic guard marker')
                if light:need(any(line.rstrip(b'\r\n')==b'GUARD foreign-tls-thread PASS' for line in lines[32:]),'arithmetic actual foreign-thread guard')
                bodies=(3000,5000,7000,11000);totals={k:0 for k in FAMILIES}
                for offset in range(32):
                    report=decode(lines[offset],offset,synthetic=True,sequence=grouped_sequence());value=report['raw']
                    need(value['empty_pair_cycles']==[1000]*16 and report['empirical_walk_cycles_proxy']==27918000 and
                         value['events'][-1][2]==27918000+1000*(value['cycle_queries']-1),'arithmetic synthetic clock/body census')
                    for epoch in range(2):
                        for family in range(4):
                            need(value['epoch_sampled_helper_cycles'][epoch][family]==value['epoch_sampled_calls'][epoch][family]*(bodies[family]+1000),'arithmetic exact sampled body')
                    for family in FAMILIES:totals[family]+=report['empirical_full_helper_cycles_proxies'][family]
                need(totals=={name:32*2*COUNTS[i]*bodies[i] for i,name in enumerate(FAMILIES)},'arithmetic balanced full synthetic recovery')
            files=loaded['overhead'];protocol=helper.decode(files['study/protocol.json'])
            need(protocol.get('observer_mode','virtual-scopes-v1')==('typed-tls-inline-v1' if light else 'virtual-scopes-v1'),'arithmetic explicit observer study')
            need(protocol['independent_numeric_rule_helper_sequence']==list(sequence) and protocol['labels']==list(base.LABELS) and
                 protocol['selectors']==[[list(x) for x in pair] for pair in base.SELECTORS] and protocol['profile']==1 and
                 protocol['blocks']==8 and protocol['calls_per_block']==16 and protocol['warmups_per_target']==2 and protocol['automatic_retries']==0 and
                 protocol['median_diagnostic_standard_limit']==1.05 and protocol['maximum_pairs_above_1_10']==2,'arithmetic unchanged frozen protocol')
            def measured(mode,path,case,offset):
                prefix='study/'+path;duration=exited(files,prefix,0)
                need(files[prefix+'/stdout.bin']==wires[case] and protocol['full_wire_sha256'][case]==digest(wires[case]),'arithmetic measured exact wire')
                stderr=files[prefix+'/stderr.bin'];report=decode(stderr,offset,sequence=sequence) if mode=='diagnostic' else None
                if mode=='standard':need(stderr==b'','arithmetic measured standard stderr')
                return {'case_index':case,'offset':offset,'duration_seconds':duration,'cpu':report}
            need([measured(mode,f'warmup-{mode}-{i}',i,i) for mode in ('standard','diagnostic') for i in range(2)]==helper.decode(files['study/warmups.json']),'arithmetic original warmups')
            ratios=[];offsets=[set() for _ in range(4)]
            for block in range(8):
                record=helper.decode(files[f'study/block-{block}.json'])
                need(record['block']==block and record['order']==(['standard','diagnostic'] if block%2==0 else ['diagnostic','standard']),'arithmetic alternating order')
                for mode in ('standard','diagnostic'):
                    need([measured(mode,f'block-{block}-{mode}-{i}',i%4,(5*(4*block+i//4))%32) for i in range(16)]==record[mode],'arithmetic every original balanced call')
                for i in range(16):offsets[i%4].add((5*(4*block+i//4))%32)
                ratio=sum(x['duration_seconds'] for x in record['diagnostic'])/sum(x['duration_seconds'] for x in record['standard'])
                need(ratio==record['elapsed_ratio'],'arithmetic paired ratio arithmetic');ratios.append(ratio)
            need(all(v==set(range(32)) for v in offsets),'arithmetic each case covers every offset')
            median=statistics.median(ratios);above=sum(r>1.10 for r in ratios);accepted=median<=1.05 and above<=2
            result=helper.decode(files['study/result.json'])
            need(result['actual_native_calls']==260 and result['paired_elapsed_ratios']==ratios and result['median_diagnostic_standard_ratio']==median and
                 result['pairs_above_1_10']==above and result['observer_overhead_gate_pass']==accepted and not accepted,'arithmetic preserve original observer miss')
            need(bootstrap()==before and mathematics.current_math(helper,objects,captured)==math_before and parser_identity()==parser_before and load()[2]==pins,'arithmetic replay source/evidence drift')
            reply={'status':'arithmetic-light-observer-exact-math-and-overhead-miss-replayed' if light else
                          'arithmetic-observer-exact-math-and-overhead-miss-replayed','authentication':authentication,
                'independent_cases':4,'parity_native_calls':270,'synthetic_offsets_per_mode':32,
                'observer_gate':{'paired_ratios':ratios,'median_ratio':median,'pairs_above_1_10':above,'accepted':False},
                'attribution_admitted':False,'native_calls':0,'archived_source_executed':False,'quality_gate':None,
                'stored_expanded_bytes':manifest['stored_expanded_bytes'],
                'scope':'Saved all-row math, independent helper sequence, sampled accounting, argument rejections and failed observer gate. No hardware query, usable helper attribution, solver improvement or realistic-game admission.'}
            if light:reply['observer_mode']='typed-tls-inline-v1'
            return reply
        finally:sys.pycache_prefix,sys.dont_write_bytecode=previous


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('packet',nargs='?',type=Path)
    parser.add_argument('--light',action='store_true');args=parser.parse_args()
    print(json.dumps(replay(args.packet,light=args.light),indent=2))
