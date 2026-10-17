"""Separately frozen higher-budget follow-up to retained 3000-sweep misses."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
from scripts import benchmark_preflop_pair_mean as paired
from scripts.benchmark_native_preflop import checksum

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'benchmarks/preflop-pair-mean-quality-v1.json'
SPEC_SHA256 = 'ef40b2d73ad3fef71cd93a57bcf98e5a87dda4d381de0a1fe6ae4a9aece83b78'


def validate_spec(spec):
    if checksum(spec) != SPEC_SHA256:
        raise ValueError('Requires exact frozen pair-mean quality follow-up spec')
    return spec


def source_hashes():
    result = paired.source_hashes()
    raw = SPEC.read_bytes()
    result[SPEC.relative_to(ROOT).as_posix()] = {
        'raw_sha256': hashlib.sha256(raw).hexdigest(),
        'lf_sha256': hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()}
    return result


def previous_report(spec):
    reference = spec['previous_report']
    raw = (ROOT / reference['path']).read_bytes().replace(b'\r\n', b'\n')
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()
    report = json.loads(raw)
    digest = checksum({k: v for k, v in report.items() if k != 'artifact_sha256'})
    if (blob != reference['git_blob_sha1'] or digest != reference['artifact_sha256']
            or report.get('artifact_sha256') != digest or report['all_final_gates_pass'] is not False):
        raise ValueError('Earlier missed-target report identity changed')
    for request in spec['requests']:
        case = next(c for c in report['cases'] if c['id'] == request['case'])
        profile = next(p for p in case['profiles'] if p['algorithm'] == request['algorithm'] and p['iterations'] == 3000)
        if any(check['meets_final_quality_gate'] for mode in profile['modes'].values() for check in mode['checks']):
            raise ValueError('Follow-up request is not a retained two-mode final miss')
    return {'path': reference['path'], 'git_blob_sha1': blob, 'artifact_sha256': digest,
            'bytes_lf': len(raw), 'original_final_gates_pass': False}


def run(spec):
    validate_spec(spec)
    before, hashes = paired.baseline.snapshot(), source_hashes()
    if before['status']:
        raise ValueError('Quality follow-up requires clean committed source')
    previous = previous_report(spec)
    base = paired.validate_spec(json.loads(paired.SPEC.read_text(encoding='utf-8')))
    if checksum(base) != spec['base_spec_sha256']:
        raise ValueError('Base paired specification identity changed')
    derived = deepcopy(base)
    derived['algorithms'] = sorted({r['algorithm'] for r in spec['requests']})
    derived['checkpoints'] = [spec['iterations']]
    prepared, provenance = paired.prepare_cases(derived)
    by_id = {item['case']['id']: item for item in prepared}
    report = {'schema_version': 1, 'benchmark_id': spec['benchmark_id'],
              'started_utc': datetime.now(timezone.utc).isoformat(),
              'source': {'before': before, 'hashes': hashes},
              'specification': spec, 'spec_sha256': checksum(spec),
              'environment': {'python': sys.version, 'executable': sys.executable,
                              'platform': platform.platform()},
              'previous_report': previous, 'physical_count_provenance': provenance,
              'requests': [], 'errors': []}
    for index, request in enumerate(spec['requests']):
        item = by_id[request['case']]
        output = {**request, 'iterations': spec['iterations'], 'modes': {},
                  'admissions': [a for a in item['admissions'] if a['algorithm'] == request['algorithm']],
                  'count_derivations': item['derivations']}
        order = paired.MODES if index % 2 == 0 else tuple(reversed(paired.MODES))
        output['sample_order'] = list(order)
        for mode in order:
            print(f"START FOLLOWUP {request['case']} {request['algorithm']} {spec['iterations']} {mode}", flush=True)
            try:
                result, timing = paired.measure(item, spec['iterations'], request['algorithm'], mode)
                output['modes'][mode] = {'sample': timing, 'payload': result}
                check = paired.baseline.assess(result, item, spec)
                output['modes'][mode]['check'] = check
                print(f"DONE seconds={timing['seconds']:.6f} nash_conv={check['independent_replay']['nash_conv']:.10g}", flush=True)
            except Exception as exc:
                report['errors'].append({**request, 'mode': mode, 'type': type(exc).__name__, 'message': str(exc)})
        if set(output['modes']) == set(paired.MODES):
            try:
                output['paired_comparison'] = paired.compare_payloads(
                    output['modes']['categorical']['payload'], output['modes']['pair-mean']['payload'], spec)
            except Exception as exc:
                report['errors'].append({**request, 'phase': 'comparison', 'type': type(exc).__name__, 'message': str(exc)})
        report['requests'].append(output)
    try:
        report['previous_report_unchanged'] = previous_report(spec) == previous
    except Exception as exc:
        report['previous_report_unchanged'] = False
        report['errors'].append({'phase': 'previous_input_after', 'type': type(exc).__name__, 'message': str(exc)})
    after, after_hashes = paired.baseline.snapshot(), source_hashes()
    report['source'].update(after=after, unchanged=before == after and hashes == after_hashes)
    report['all_followup_gates_pass'] = (not report['errors'] and report['source']['unchanged'] and report['previous_report_unchanged']
        and len(report['requests']) == len(spec['requests'])
        and all(set(r['modes']) == set(paired.MODES)
                and all(m.get('check', {}).get('meets_final_quality_gate', False) for m in r['modes'].values())
                and r.get('paired_comparison', {}).get('meets_scalar_agreement_gate', False) for r in report['requests']))
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    report['artifact_sha256'] = checksum(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'benchmarks/results/preflop-pair-mean-quality-v1.json')
    args = parser.parse_args()
    report = run(json.loads(SPEC.read_text(encoding='utf-8')))
    args.output.write_bytes((json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n').encode('utf-8'))
    print(json.dumps({'artifact_sha256': report['artifact_sha256'],
                      'all_followup_gates_pass': report['all_followup_gates_pass'], 'errors': report['errors']}), flush=True)
    return 0 if report['all_followup_gates_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
