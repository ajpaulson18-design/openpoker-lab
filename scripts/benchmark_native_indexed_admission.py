"""Fixed 28-request capacity study; imports project math only after source authentication.

One observation per capacity point is not a speed experiment. No retry, cap
increase, substitute fixture, or quality-pass inference from admission occurs.
"""
from argparse import ArgumentParser
import base64
from contextlib import ExitStack
import hashlib
from itertools import combinations
import json
from math import isfinite
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DECK = tuple(rank + suit for rank in '23456789TJQKA' for suit in 'cdhs')
BASELINES = ('original-22-t10', 'payoff-varied-t10', 'blocker-18',
             'asymmetric-weighted', 'mixed-stabilizer')
MATRIX = ('original-weighted-2x2', 'balanced-4x4-unit', 'balanced-8x8-unit',
          'balanced-16x16-unit', 'asymmetric-2x16-unit')
# (fixture, iterations, admission). Original matrix T10 aliases its A record.
SCHEDULE = tuple((name, 10, mode) for name in BASELINES for mode in ('legacy', 'indexed-v1')) + \
    tuple(('original-22-t10', t, mode) for t in (20, 40) for mode in ('legacy', 'indexed-v1')) + \
    tuple((name, t, 'indexed-v1') for name in MATRIX for t in (10, 100, 1000)
          if (name, t) != ('original-weighted-2x2', 10))
RESOURCE = re.compile(
    r'\b(?:admission|capacity|limit|cap|forecast|budget|ceiling|preflight|envelope)\b[^\n]*\bexceeded\b'
    r'|\bexceeds?\b[^\n]*\b(?:envelope|ceiling|limit|cap|capped|slots|states|depth|decisions|rows)\b'
    r'|\b(?:is |are )?capped at\b|\bleaves no native allowance\b'
    r'|\bno retained-entry allowance remains\b'
    r'|\bindexed router whole-work limit is below its bounded schedule scan floor\b'
    r'|\bhistory-index bounded input scan exceeds remaining combined work before token scan\b', re.I)
_AUTH = None

def need(value, message):
    if not value:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def write(path, value):
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode() + b'\n')

def decode(raw):
    def unique(items):
        value = {}
        for key, item in items:
            need(key not in value, 'duplicate JSON key')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON token')))

def git(*args, data=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, input=data)

def _identity():
    names = git('ls-files', '-z').decode().split('\0')[:-1]
    return {'commit': git('rev-parse', 'HEAD').decode().strip(),
        'status': git('status', '--porcelain', '--untracked-files=all').decode().strip(),
        'sha256': {name: sha((ROOT / name).read_bytes()) for name in names}}

def _authenticate_source():
    """Full raw closure AND committed raw-or-attribute-normalized Git blobs."""
    global _AUTH
    source = _identity()
    need(not source['status'], 'Commit and clean all tracked source before running the study')
    tree = {}
    for item in git('ls-tree', '-rz', '--full-tree', source['commit']).split(b'\0')[:-1]:
        metadata, name = item.split(b'\t', 1)
        mode, kind, oid = metadata.split()
        need(kind == b'blob' and mode in (b'100644', b'100755'), 'nonordinary source entry')
        tree[name.decode()] = oid.decode()
    names = list(source['sha256'])
    need(set(names) == set(tree), 'tracked source keyset differs from committed tree')
    normalized = git('hash-object', '--stdin-paths',
        data=('\n'.join(names) + '\n').encode()).decode().splitlines()
    need(len(normalized) == len(names), 'incomplete Git normalization closure')
    for name, oid in zip(names, normalized):
        raw = (ROOT / name).read_bytes()
        raw_oid = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        need(raw_oid == tree[name] or oid == tree[name], 'raw/normalized committed blob mismatch: ' + name)
    need(_identity() == source, 'source changed during authentication')
    _AUTH = source
    return source

def _dependencies():
    need(_AUTH is not None, 'authenticate source before importing project code')
    from scripts import benchmark_native_indexed_routing as old
    from scripts import benchmark_suit_quotient_solver as quotient
    from scripts import benchmark_equivariant_selected_solver as equivariant
    from pokerlab import native_exact_four_street as native, exact_selected_solver as solver
    from pokerlab.cards import expand_range
    return SimpleNamespace(old=old, quotient=quotient, equivariant=equivariant,
        native=native, solver=solver, expand_range=expand_range)

def _unit_range(original, pool, size):
    def hand(value):
        cards = (value[:2], value[2:])
        need(all(card in DECK for card in cards) and cards[0] != cards[1], 'invalid concrete holding')
        return ''.join(sorted(cards, key=DECK.index))
    values = []
    for token in original.split(','):
        value = hand(token.split(':')[0])
        if value not in values:
            values.append(value)
    for cards in combinations(sorted(pool, key=DECK.index), 2):
        if len(values) >= size:
            break
        value = hand(''.join(cards))
        if value not in values:
            values.append(value)
    need(len(values) == size and len(set(values)) == size, 'distinct unit fixture size mismatch')
    return ','.join(values) # every holding, including the original two, has unit weight

def case_for(name, deps):
    if name in BASELINES:
        return deps.quotient.case_for(name)
    need(name in MATRIX, 'unknown fixed capacity fixture')
    case = dict(deps.quotient.case_for('original-22-t10'))
    if name == MATRIX[0]:
        return case
    h0, h1 = (2, 16) if name == MATRIX[-1] else (int(name.split('-')[1].split('x')[0]),) * 2
    case['sb_range'] = _unit_range(case['sb_range'], ('Ad','As','Qd','Qs','Ac','Ah','9c','9d'), h0)
    case['bb_range'] = _unit_range(case['bb_range'], ('Kd','Ks','Jd','Jh','Qc','Qh','8d','8s'), h1)
    case['id'] = 'canonical-distinct-unit-' + name
    return case

def validate_cases(deps):
    result = {name: case_for(name, deps) for name in (*BASELINES, *MATRIX)}
    for name in MATRIX[1:]:
        expected = (2,16) if name == MATRIX[-1] else (int(name.split('-')[1].split('x')[0]),) * 2
        for key, size in zip(('sb_range','bb_range'), expected):
            expanded = deps.expand_range(result[name][key])
            need(len(expanded) == size and all(float(v).hex() == (1.0).hex() for v in expanded.values()),
                 'canonical unit fixture changed after real range parsing')
    return result

def label(entry):
    return f'{entry[0]}-t{entry[1]}-{entry[2]}'

def _resource_outcome(raw):
    error, counts, streams = raw.get('failure'), raw.get('counts', {}), raw.get('native_streams')
    if not (raw.get('payload') is None and type(error) is dict and error.get('type') in ('ValueError','NativeFailure')
            and _bounded_resource(error.get('message', '')) and counts.get('python_rank') == 0):
        return None
    if counts.get('native_invoke') == 0 and streams == [] and error['type'] == 'ValueError':
        return 'host-admission-rejected'
    if counts.get('native_invoke') == 1 and counts.get('rank_before_native') == 0 and type(streams) is list and len(streams) == 1:
        stream = streams[0]
        output, error_bytes = (base64.b64decode(stream[k], validate=True) for k in ('stdout','stderr'))
        if stream.get('returncode') == 2 and not output and b'native exact four-street rejected:' in error_bytes and _bounded_resource(error_bytes.decode('utf-8', 'replace')):
            return 'native-resource-rejected'
    return None

def _bounded_resource(message):
    # A word such as "admission" alone is not a capacity outcome: stale
    # prepared owners, missing proofs and wrong execution modes are defects.
    return (type(message) is str and not re.search(
        r'\b(?:stale|unsupported|missing|mismatch|invalid|requires)\b|already reserved|cannot exceed',message,re.I)
        and RESOURCE.search(message) is not None)

def child(entry, executable):
    _authenticate_source()
    deps = _dependencies()
    cases = validate_cases(deps)
    build = deps.native.executable_identity(executable)
    name, iterations, admission = entry
    need(entry in SCHEDULE, 'child not in fixed schedule')
    original = deps.solver.solve_four_street_exact_selected
    extra_training = {'packed':0,'equivariant':0}
    def solve(request, **kwargs):
        return original(request, native_admission=admission, **kwargs)
    # Reuse established instrumentation/raw-native capture and complete-call
    # timing. Only the fixed fixture and explicit admission option differ.
    def forbidden(counter):
        def reject(*_args, **_kwargs):
            extra_training[counter]+=1
            raise AssertionError('forbidden Python training entered: '+counter)
        return reject
    with patch('pokerlab.exact_selected_solver.train_packed',new=forbidden('packed')), \
         patch('pokerlab.equivariant_packed_cfr.train_equivariant_packed',new=forbidden('equivariant')), \
         patch.object(deps.old, 'case_for', new=lambda key: cases[key]), \
         patch.object(deps.old, 'ITERATIONS', new={name: iterations}), \
         patch.object(deps.solver, 'solve_four_street_exact_selected', new=solve):
        raw = deps.old.child(name, 'indexed', 0, False, executable)
    raw['counts']['python_trainer']+=sum(extra_training.values())
    raw.update(native_admission=admission, request_case=cases[name])
    raw['status'] = 'complete' if raw['failure'] is None else (_resource_outcome(raw) or 'failed')
    # Native internals are unobserved on a process-side rejection. Absence of
    # stdout does not establish zero rank or zero learning inside that process.
    raw['native_observations'] = ({'learning_completed': True,
        'rank_calls': raw['payload']['operator_census']['native_exact']['rank_calls']}
        if raw['status'] == 'complete' else {'learning_completed': False if raw['counts']['native_invoke'] == 0 else None,
        'rank_calls': 0 if raw['counts']['native_invoke'] == 0 else None})
    need(_identity() == _AUTH and deps.native.executable_identity(executable) == build,
         'child source/build changed during complete call')
    return raw

def validate(raw, entry, deps, cases):
    name, iterations, admission = entry
    need(type(raw) is dict and (raw.get('case'), raw.get('iterations'), raw.get('native_admission')) == entry and
        raw.get('routing') == 'indexed' and type(raw.get('sample')) is int and raw['sample'] == 0 and raw.get('traced') is False and
        raw.get('request_case') == cases[name] and raw.get('runtime') == deps.quotient._runtime(), 'child identity/runtime/fixture mismatch')
    need(type(raw.get('seconds')) in (int,float) and isfinite(raw['seconds']) and raw['seconds'] > 0 and
        type(raw.get('process_peak_bytes')) is int and raw['process_peak_bytes'] > 0 and
        raw.get('python_allocation_peak_bytes') is None, 'invalid complete-call observation')
    counts = raw.get('counts');keys = {'python_trainer','native_invoke','python_rank','rank_before_native','pair','world','legacy'}
    need(type(counts) is dict and set(counts) == keys and all(type(counts[k]) is int and counts[k] >= 0 for k in keys-{'rank_before_native'}) and
        (counts['rank_before_native'] is None or type(counts['rank_before_native']) is int and counts['rank_before_native'] == 0) and
        not any(counts[k] for k in ('python_trainer','pair','world','legacy')), 'forbidden/malformed call count')
    streams=raw.get('native_streams')
    need(type(streams) is list and len(streams)==counts['native_invoke']<=1,'native stream/count mismatch')
    for record in streams:
        need(type(record) is dict and set(record)=={'request','stdout','stderr','returncode'} and
             type(record['returncode']) is int,'malformed native stream status')
        request,output,error=(base64.b64decode(record[k],validate=True) for k in ('request','stdout','stderr'))
        expected='OPENPOKER_NATIVE_EXACT_FOUR_STREET_INDEXED_ADMISSION_V3' if admission=='indexed-v1' else 'OPENPOKER_NATIVE_EXACT_FOUR_STREET_ROUTED_V2'
        need(request.decode('ascii').split()[0]==expected,'native request admission header mismatch')
    outcome = _resource_outcome(raw)
    need(raw.get('status') in ('complete','host-admission-rejected','native-resource-rejected','failed'), 'unknown status')
    if outcome:
        need(raw['status'] == outcome and not (name in BASELINES and iterations == 10), 'baseline regression or mismatched rejection')
        expected = {'learning_completed': False, 'rank_calls': 0} if counts['native_invoke'] == 0 else {'learning_completed': None,'rank_calls': None}
        need(raw.get('native_observations') == expected, 'unobserved native internals labeled zero')
        return
    need(raw['status'] == 'complete' and raw.get('failure') is None and type(raw.get('payload')) is dict and
        counts['native_invoke'] == 1 and counts['rank_before_native'] == 0 and counts['python_rank'] > 0, 'unexpected solve failure or rank ordering')
    payload = raw['payload'];encoded = canonical(payload)
    need(sha(encoded) == raw.get('payload_sha256') and len(encoded) == raw.get('payload_bytes'), 'complete payload hash mismatch')
    need(payload.get('native_routing') == 'indexed' and payload.get('training_backend') ==
        ('native-exact-four-street-routed-v2' if admission == 'legacy' else 'native-exact-four-street-indexed-admission-v3') and
        (payload.get('native_admission') == 'indexed-v1' if admission == 'indexed-v1' else 'native_admission' not in payload), 'admission/backend contract mismatch')
    # Reuse the old complete raw-policy/resource/route validation after binding
    # the original V3 contract and hash above. This validation-only projection
    # changes no preserved payload or native stream, only its backend marker.
    view = dict(raw);projected = dict(payload);projected['training_backend'] = 'native-exact-four-street-routed-v2'
    view['payload'] = projected;view['payload_sha256'] = sha(canonical(projected));view['payload_bytes'] = len(canonical(projected))
    with patch.object(deps.old, 'ITERATIONS', new={name: iterations}):
        deps.old.validate(view, (name,'indexed',0,False))
    receipt = payload['operator_census']['native_exact'];need(receipt['retained_entries_upper'] <= 2_000_000, 'native whole entry ceiling changed')
    need(raw.get('native_observations') == {'learning_completed': True,'rank_calls': receipt['rank_calls']}, 'completed native observations differ')
    if admission == 'indexed-v1':
        proof = receipt.get('indexed_admission');need(type(proof) is dict and proof.get('mode') == admission, 'missing admission proof')
        route = receipt['indexed_routing']
        need(proof['combined_work'] == route['combined_work'] == proof['plan_setup_work'] + proof['index_setup_work'] +
             proof['router_setup_work'] + route['router_work_upper'] + route['index_work_upper'] + route['caller_work'] and
             proof['combined_entries'] == route['combined_entries'] and proof['marginal_reuse'] == 1 and
             0 < proof['marginal_calls_actual'] <= proof['marginal_calls_upper'], 'admission ledger/marginal reuse mismatch')
        record = raw['native_streams'][0];output = base64.b64decode(record['stdout'],validate=True)
        lines = output.decode('ascii').splitlines();fields = lines[-1].split('\t')
        need(lines[0]=='OPENPOKER_NATIVE_EXACT_FOUR_STREET_INDEXED_ADMISSION_RESULT_V3','raw V3 result header mismatch')
        need(fields[:2] == ['ADMISSION','indexed-v1'], 'raw ADMISSION line missing')
        pairs = [item.split('=',1) for item in fields[2:]]
        need(len({p[0] for p in pairs}) == len(pairs) and {k:int(v) for k,v in pairs} == {k:v for k,v in proof.items() if k!='mode'}, 'raw admission proof differs')

def _verify(case, payload, deps):
    """Reuse the guarded replay seam, retaining numeric and exact cap outcomes separately."""
    equiv = deps.equivariant
    def stage(function):
        try:
            return {'status':'complete','result':function()}
        except ValueError as exc:
            if not _bounded_resource(str(exc)):
                raise
            return {'status':'resource-unverified','error':{'type':type(exc).__name__,'message':str(exc)}}
    def verify_case(case, payload):
        numeric = stage(lambda: equiv.replay_policy(payload, case['sb_range'], case['bb_range'], config=case['config'],
            runouts=case['runouts'],flop_config=case['flop_config'],turn_config=case['turn_config'],river_config=case['river_config']))
        exact = stage(lambda: equiv.evaluate_exact(case,payload))
        result = {'numeric':numeric,'exact':exact,'quality_gate':None}
        if numeric['status']=='complete':
            replay=numeric['result'];metrics={key:replay[key] for key in ('value_sb','value_bb','sb_best_response_value','bb_best_response_value')}
            metrics.update(sb_gain=max(0.,metrics['sb_best_response_value']-metrics['value_sb']),bb_gain=max(0.,metrics['bb_best_response_value']+metrics['value_sb']))
            metrics['nash_conv']=metrics['sb_gain']+metrics['bb_gain'];metrics['exploitability']=metrics['nash_conv']/2
            gaps={key:abs(payload[key]-metrics[key]) for key in equiv.METRICS}
            need(replay['checked_information_sets']==payload['info_sets'] and all(isfinite(v) and v<=equiv.REPLAY_TOLERANCE for v in gaps.values()),'independent numeric replay mismatch')
            result['numeric_metric_gaps']=gaps
        if exact['status']=='complete' and numeric['status']=='complete':
            result['quality_gate']=exact['result']['exact_certificate']['threshold_met']
        return result
    with patch.object(deps.quotient,'_verify_payload',new=verify_case):
        return deps.quotient._protected_verification(case,payload)

def _pair(left,right,checks,deps):
    need(left['chance_input_snapshot']==right['chance_input_snapshot'] and canonical(left['strategy'])==canonical(right['strategy']), 'paired full policy/input mismatch')
    need(all(float(left[k]).hex()==float(right[k]).hex() for k in deps.equivariant.METRICS), 'paired eight metric bits differ')
    # Python equality equates signed zero: require the probability bits too.
    need([float(a['probability']).hex() for row in left['strategy'] for a in row['actions']]==
         [float(a['probability']).hex() for row in right['strategy'] for a in row['actions']], 'paired policy bits differ')
    if all(c['exact']['status']=='complete' for c in checks):
        l,r=(c['exact']['result']['exact_certificate'] for c in checks)
        need(all(l[k]==r[k] for k in ('metrics','threshold','threshold_met')), 'paired exact certificate differs')
    return {'full_policy_bits_identical':True,'all_eight_metric_bits_identical':True,
        'exact_comparison_verified':all(c['exact']['status']=='complete' for c in checks)}

def _run_child(command):
    return subprocess.run(command,cwd=ROOT,capture_output=True,check=False)

def run(output, executable):
    output=Path(output).resolve();need(output!=ROOT and ROOT not in output.parents and not output.exists(),'new external output directory required')
    output.mkdir(parents=True)
    samples=[];payloads={};checks={};pairs={};failure=None;cases={};source=build=deps=None;attempts=0
    raw_pins={};stage='source-authentication'
    def raw_unchanged():
        need(all(sha((output/name).read_bytes())==digest for name,digest in raw_pins.items()),'captured raw artifact changed')
    try:
        source=_authenticate_source();write(output/'source-before.json',source)
        deps=_dependencies();build=deps.native.executable_identity(executable);write(output/'build-before.json',build)
        stage='fixture-validation'
        cases=validate_cases(deps)
        write(output/'protocol.json',{'version':'native-indexed-admission-capacity-study-v1','source':source,'build':build,
            'runtime':deps.quotient._runtime(),'schedule':SCHEDULE,'cases':cases,'options':deps.old.OPTIONS,
            'matrix_original_t10_alias':label(('original-22-t10',10,'indexed-v1')),
            'scope':'Fixed capacity outcomes, one observation each; not a speed study. No tracing/retry/cap increase. Larger verifier-cap outcomes are unverified, never quality passes.'})
        for entry in SCHEDULE:
            identifier=label(entry)
            stage='child:'+identifier
            need(_identity()==source and deps.native.executable_identity(executable)==build,'source/build drift before child')
            attempts+=1
            process=_run_child([sys.executable,'-B','-m','scripts.benchmark_native_indexed_admission','--child',str(SCHEDULE.index(entry)),
                '--native-executable',str(executable)])
            (output/(identifier+'.stdout.bin')).write_bytes(process.stdout);(output/(identifier+'.stderr.bin')).write_bytes(process.stderr)
            write(output/(identifier+'-status.json'),{'returncode':process.returncode})
            for suffix in ('.stdout.bin','.stderr.bin','-status.json'):
                name=identifier+suffix;raw_pins[name]=sha((output/name).read_bytes())
            need(process.returncode==0,'child process failed: '+str(process.returncode))
            raw=decode(process.stdout);validate(raw,entry,deps,cases)
            samples.append({'label':identifier,'entry':entry,**{k:v for k,v in raw.items() if k not in ('payload','native_streams')}})
            if raw['payload'] is not None:
                stage='protected-verification:'+identifier
                need(_identity()==source and deps.native.executable_identity(executable)==build,'source/build drift before protected math')
                raw_unchanged();payload_pin=sha(canonical(raw['payload']))
                checked=_verify(cases[entry[0]],raw['payload'],deps)
                need(sha(canonical(raw['payload']))==payload_pin,'protected verification changed complete payload')
                raw_unchanged();write(output/(identifier+'-verification.json'),checked)
                payloads[identifier]=raw['payload'];checks[identifier]=checked
            print(identifier,raw['status'],flush=True)
        for name,t,mode in SCHEDULE:
            if mode!='legacy':continue
            left,right=label((name,t,'legacy')),label((name,t,'indexed-v1'))
            stage='paired-identity:'+left
            pairs[left+'__vs__'+right]=(_pair(payloads[left],payloads[right],[checks[left],checks[right]],deps)
                if left in payloads and right in payloads else {'status':'not-both-complete','quality_gate':None})
    except Exception as exc:
        failure={'stage':stage,'type':type(exc).__name__,'message':str(exc),'calls_captured':len(samples)}
        write(output/'first-failure.json',failure)
    try:
        raw_unchanged()
        if source is not None:
            after=_identity();write(output/'source-after.json',after);need(after==source,'source drift after study')
        if build is not None:
            build_after=deps.native.executable_identity(executable);write(output/'build-after.json',build_after)
            need(build_after==build,'build drift after study')
    except Exception as exc:
        failure={'stage':'final-authentication','type':type(exc).__name__,'message':str(exc),'previous':failure}
        write(output/'final-authentication-failure.json',failure)
    outcome='complete' if failure is None and len(samples)==28 else 'failed'
    report={'outcome':outcome,'failure':failure,'calls_planned':28,'calls_attempted':attempts,'calls_captured':len(samples),'samples':samples,'paired_identities':pairs,
        'captured_raw_artifact_sha256':raw_pins,
        'verification_status':{k:{'numeric':v['numeric']['status'],'exact':v['exact']['status'],'quality_gate':v['quality_gate']} for k,v in checks.items()},
        'scope':'Admission/complete solve/verified quality are separate outcomes. Native internals on process rejection are unknown. Fixed one-sample capacity observations carry no speed claim.'}
    write(output/'report.json',report);write(output/'manifest.json',{'source_commit':source['commit'] if source else None,'sha256':{
        p.name:sha(p.read_bytes()) for p in sorted(output.iterdir()) if p.is_file()}})
    return {'outcome':outcome,'failure':failure}

def main():
    parser=ArgumentParser(description=__doc__);parser.add_argument('--native-executable',required=True,type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--child',type=int,choices=range(28));args=parser.parse_args()
    if args.child is not None:
        value=child(SCHEDULE[args.child],args.native_executable)
    else:
        if args.output is None:parser.error('--output is required')
        value=run(args.output,args.native_executable)
    print(json.dumps(value,allow_nan=False));return 0 if args.child is not None or value['outcome']=='complete' else 1

if __name__=='__main__':raise SystemExit(main())
