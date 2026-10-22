"""One frozen three-prior CFR+ batch; retain every miss and first failure."""
from contextlib import nullcontext
from datetime import datetime, timezone
from fractions import Fraction
import argparse
import gc
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import traceback
from unittest.mock import patch

from pokerlab import cfr_plus
from scripts import benchmark_flop_class_reweight as evidence
from scripts import benchmark_weighted_full_deck_flop as power
from scripts import flop_class_reweight_cfrplus as trainer
from scripts import flop_public_classes as proof
from scripts import verify_flop_class_compact_cfrplus_publication as old_pilot
from scripts import verify_flop_class_reweight_publication as publication

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'benchmarks/flop-class-reweight-cfrplus-pilot-v1.json'
SPEC_LF_SHA256 = '747457bc4557be273368a9c24c3af7e418f9c9fde782837bc8595a0de4e3822d'
CASES = ('baseline', 'uniform', 'skew')
MAX_SOURCE_BYTES = 2 * 1024 * 1024


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _protocol():
    proof._need(SPEC.stat().st_size <= evidence.MAX_SPEC_BYTES, 'Pilot protocol exceeds bound')
    with SPEC.open('rb') as stream:
        raw = stream.read(evidence.MAX_SPEC_BYTES + 1)
    proof._need(len(raw) <= evidence.MAX_SPEC_BYTES and
                hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest() == SPEC_LF_SHA256,
                'Frozen weighted pilot protocol differs')
    spec = json.loads(raw, object_pairs_hook=evidence._pairs,
                      parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    proof._need(type(spec) is dict and spec.get('protocol_id') ==
                'fixed-flop-prior-cfrplus-pilot-v1' and
                proof._typed(spec.get('cases')) == proof._typed([
                    {'case_id': case_id, 'iterations': 560} for case_id in CASES]) and
                proof._typed(spec.get('quality_target_fraction')) == proof._typed([1, 200]) and
                type(spec.get('averaging_delay')) is int and spec['averaging_delay'] == 0,
                'Pilot request scope differs')
    proof._need(spec['source_proof'] == {
        'index_raw_sha256': publication.INDEX_RAW_SHA256,
        'index_sha256': publication.INDEX_SHA256,
        'source_revision': publication.EXPECTED_REVISION}, 'No-training proof identity differs')
    return spec


def _preflight(spec):
    requests = [(row['case_id'], row['iterations'],
                 trainer.admit_request(row['case_id'], row['iterations']))
                for row in spec['cases']]
    total = sum(admission['total_admitted_work'] for _, _, admission in requests)
    expected = spec['preflight']
    proof._need(len(requests) == 3 and
                all(admission['total_admitted_work'] == 75_107_956
                    for _, _, admission in requests) and total == 225_323_868 and
                proof._typed(expected) == proof._typed({
                    'training_calls': 3, 'logical_work_per_call': 75_107_956,
                    'total_logical_work': total, 'batch_logical_cap': 230_000_000,
                    'physical_oracle_builds': 6, 'enumerated_physical_world_rows': 35_640,
                    'maximum_live_physical_oracles': 2, 'compact_worlds_per_call': 126,
                    'compact_policy_rows_per_call': 466, 'physical_policy_rows_per_call': 16912,
                    'scope_note': 'Named training/setup/output loops including 126 additional binary64 mass-sum entries per call, plus separate physical census only. Not total arithmetic, allocated memory, wall time, CPU or RSS bounds.'}) and
                total <= expected['batch_logical_cap'], 'Weighted batch admission differs')
    return requests


def _snapshot():
    state = evidence._source_snapshot()
    hashes = trainer.source_hashes()
    for relative in ('scripts/benchmark_flop_class_reweight_cfrplus.py',
                     'benchmarks/flop-class-reweight-cfrplus-pilot-v1.json',
                     'scripts/verify_flop_class_compact_cfrplus_publication.py',
                     'scripts/verify_flop_class_reweight_cfrplus.py'):
        path = ROOT / relative
        proof._need(path.stat().st_size <= MAX_SOURCE_BYTES, 'Pilot source exceeds bound')
        with path.open('rb') as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        proof._need(len(raw) <= MAX_SOURCE_BYTES, 'Pilot source exceeds bound')
        hashes[relative] = hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()
    return {**state, 'source_lf_sha256': dict(sorted(hashes.items()))}


def _proof_world_identities():
    _, index = publication._read_index(publication.PUBLICATION / 'index.json')
    result = {}
    for case in index['cases']:
        _, prep = publication._read_gzip(publication.PUBLICATION, case['preparation_file'])
        result[case['case_id']] = prep['weighted_worlds_sha256']
    proof._need(set(result) == set(CASES), 'Authenticated prior world inventory differs')
    return result


def _baseline_reference(spec):
    _, _, old = old_pilot._read(old_pilot.PUBLICATION)
    acceptance = spec['baseline_acceptance']
    proof._need(acceptance['pilot_raw_sha256'] == old_pilot.RAW_SHA256 and
                acceptance['pilot_artifact_sha256'] == old_pilot.ARTIFACT_SHA256,
                'Frozen old pilot identity differs')
    return old


def _validate_report(case_id, iterations, admission, result, expected_world_sha):
    proof._need(type(result) is dict and result.get('case_id') == case_id and
                result.get('status') == 'trained-policy-physically-verified',
                'Weighted call result scope differs')
    proof._need(result.get('baseline_worlds_sha256') == proof.PHYSICAL_WORLDS_SHA256 and
                result.get('physical_worlds_sha256') == expected_world_sha,
                'Weighted physical world identity differs from authenticated prior proof')
    census = result.get('census')
    proof._need(type(census) is dict and all(type(census.get(key)) is int and
                census[key] == value for key, value in trainer.reweighted.EXPECTED_CENSUS.items())
                and type(result.get('maximum_world_path_states')) is int and
                1 <= result['maximum_world_path_states'] <= 33,
                'Weighted physical/compact census or path differs')
    unsigned = {key: value for key, value in result.items() if key != 'artifact_sha256'}
    proof._need(proof._digest(unsigned) == result.get('artifact_sha256'),
                'Weighted call report checksum differs')
    proof._need(proof._typed(result.get('admission')) == proof._typed(admission) and
                proof._typed(result.get('plan')) ==
                proof._typed(evidence._plan_record(trainer.case_plan(case_id))) and
                proof._typed(result.get('source_lf_sha256')) ==
                proof._typed(trainer.source_hashes()), 'Call admission, priors or source identity differs')
    payload, audit = result.get('physical_policy'), result.get('audit')
    proof._need(type(payload) is dict and type(audit) is dict and
                type(payload.get('iterations')) is int and payload['iterations'] == iterations and
                payload.get('algorithm') == 'cfrplus' and
                type(payload.get('averaging_delay')) is int and payload['averaging_delay'] == 0 and
                type(payload.get('strategy')) is list and len(payload['strategy']) == 16912 and
                type(result.get('raw_class_policy')) is list and
                len(result['raw_class_policy']) == 466, 'Weighted policy dimensions or request differs')
    proof._need(audit.get('exact_metric_count') == 8 and
                set(audit.get('exact_metrics', {})) == set(proof.METRICS) and
                audit.get('class_rows') == 466 and audit.get('physical_rows_lifted') == 16912 and
                type(audit.get('maximum_numeric_gap')) in (int, float) and
                0 <= audit['maximum_numeric_gap'] <= 1e-10 and
                audit.get('physical_strategy_sha256') == proof._digest(payload['strategy']),
                'Weighted exact physical audit differs')
    proof._need(type(result.get('quality_target')) is float and result['quality_target'] == 0.005 and
                type(result.get('quality_target_met')) is bool and
                result['quality_target_met'] ==
                (Fraction(audit['exact_metrics']['nash_conv']) <= Fraction(1, 200)),
                'Weighted quality outcome is misstated')
    for key in ('preparation_forbidden_calls', 'diagnostic_forbidden_calls'):
        proof._need(evidence._valid_guard_census(result.get(key)),
                    'Weighted production authority guard is incomplete or nonzero')
    return {'exact_metrics': audit['exact_metrics'],
            'maximum_numeric_gap': audit['maximum_numeric_gap'],
            'physical_strategy_sha256': audit['physical_strategy_sha256'],
            'quality_target_met': result['quality_target_met']}


def _compare_baseline(result, old, spec):
    fields = spec['baseline_acceptance']['fields']
    audit_fields = spec['baseline_acceptance']['audit_fields']
    proof._need(all(proof._typed(result.get(key)) == proof._typed(old.get(key)) for key in fields)
                and all(proof._typed(result['audit'].get(key)) ==
                        proof._typed(old['audit'].get(key)) for key in audit_fields),
                'New adapter baseline differs from the published 560-sweep pilot')


def run(output, *, execution_state=None):
    output = Path(output).resolve()
    root = ROOT.resolve()
    proof._need(not output.exists() and output != root and root not in output.parents and
                output not in root.parents, 'Pilot output must be new and outside source')
    output.mkdir(parents=True, exist_ok=False)
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    report = {'schema_version': 1, 'protocol_id': 'fixed-flop-prior-cfrplus-pilot-v1',
              'status': 'preparing', 'created_at_utc': _utc(), 'errors': [], 'files': [],
              'cases': [], 'training_calls': 0, 'solve_calls_started': 0,
              'solve_calls_completed': 0,
              'execution_state': evidence._execution_state(execution_state),
              'runtime': {'python': sys.version, 'implementation': platform.python_implementation(),
                          'platform': platform.platform()}}
    source = None
    counts = {'training_calls': 0}
    original_train = cfr_plus.train
    def counted_train(*args, **kwargs):
        counts['training_calls'] += 1
        return original_train(*args, **kwargs)
    try:
        spec = _protocol()
        requests = _preflight(spec)  # all requests before any proof/ranking/training
        source = _snapshot()
        proof._need(source['status'] == '', 'Weighted pilot source must be committed and clean')
        report.update(protocol=spec, preflight=spec['preflight'], source_before=source,
                      cases=[{'case_id': case_id, 'iterations': iterations,
                              'admission': admission, 'status': 'not-run'}
                             for case_id, iterations, admission in requests])
        evidence._write_index(output, report)
        expected_worlds = _proof_world_identities()
        old = _baseline_reference(spec)
        proof._need(_snapshot() == source, 'Source changed during old pilot authentication')
        with patch.object(cfr_plus, 'train', counted_train):
            for row in report['cases']:
                before_calls = counts['training_calls']
                row.update(status='active', started_at_utc=_utc(), source_before=_snapshot())
                report['active_case'] = row['case_id']
                proof._need(row['source_before'] == source, 'Source changed before weighted call')
                report['solve_calls_started'] += 1
                evidence._write_index(output, report)
                case_wall, case_cpu = time.perf_counter(), time.process_time()
                result = None
                try:
                    result = trainer.solve_reweighted(row['case_id'], row['iterations'])
                    report['solve_calls_completed'] += 1
                    # Save the complete returned report before downstream acceptance;
                    # preserve an invalid returned policy as evidence of the failure.
                    file_row = evidence._write_gzip(output, row['case_id']+'-560.json.gz', result)
                    report['files'].append(file_row)
                    row['evidence_file'] = file_row
                    row['source_after'] = _snapshot()
                    proof._need(row['source_after'] == source, 'Source changed during weighted call')
                    proof._need(counts['training_calls'] - before_calls == 1,
                                'Weighted call must invoke the shared trainer exactly once')
                    row['audit_summary'] = _validate_report(row['case_id'], row['iterations'],
                                                           row['admission'], result,
                                                           expected_worlds[row['case_id']])
                    if row['case_id'] == 'baseline':
                        _compare_baseline(result, old, spec)
                        row['old_baseline_semantics_equal'] = True
                        old = None
                    row['status'] = 'complete'
                except BaseException as exc:
                    row['status'] = 'error'
                    report['errors'].append({'phase': 'weighted-call', 'case_id': row['case_id'],
                        'error': f'{type(exc).__name__}: {exc}', 'traceback': traceback.format_exc()})
                    raise
                finally:
                    row.update(finished_at_utc=_utc(), wall_seconds=time.perf_counter()-case_wall,
                               process_seconds=time.process_time()-case_cpu,
                               training_calls=counts['training_calls']-before_calls)
                    report['training_calls'] = counts['training_calls']
                    result = None
                    gc.collect()
                    report.pop('active_case', None)
                    evidence._write_index(output, report)
    except BaseException as exc:
        if not report['errors']:
            report['errors'].append({'phase': 'run', 'error': f'{type(exc).__name__}: {exc}',
                                     'traceback': traceback.format_exc()})
        report['status'] = 'error'
        for row in report['cases']:
            if row['status'] == 'active':
                row['status'] = 'error'
            elif row['status'] == 'not-run':
                row['not_run_reason'] = 'stopped-after-earlier-failure'
    finally:
        try:
            report['source_after'] = _snapshot()
            if source is not None and report['source_after'] != source:
                report['errors'].append({'phase': 'final-source-check',
                                         'error': 'Source changed during weighted pilot'})
        except BaseException as exc:
            report['errors'].append({'phase': 'final-source-check',
                'error': f'{type(exc).__name__}: {exc}', 'traceback': traceback.format_exc()})
        report.update(training_calls=counts['training_calls'], finished_at_utc=_utc(),
                      wall_seconds=time.perf_counter()-started_wall,
                      process_seconds=time.process_time()-started_cpu)
        report['status'] = ('complete' if not report['errors'] and len(report['cases']) == 3 and
                            all(row['status'] == 'complete' for row in report['cases']) and
                            counts['training_calls'] == 3 else 'error')
        evidence._write_index(output, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    context = (power.measurement_execution_state() if sys.platform == 'win32' else
               nullcontext({'mode': 'ordinary-process', 'system_required': False}))
    with context as state:
        result = run(args.output, execution_state=state)
    print(json.dumps({key: result[key] for key in
                     ('status', 'training_calls', 'solve_calls_completed')}, sort_keys=True))
    return 0 if result['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
