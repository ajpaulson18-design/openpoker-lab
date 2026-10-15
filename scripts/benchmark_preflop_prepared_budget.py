"""Measure longer prepared-table solves under an explicit bounded work model."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import gc
import json
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter
import tracemalloc
from unittest.mock import patch

from pokerlab import preflop_full_board_equity as equity
from pokerlab.preflop_push_fold import solve_prepared_push_fold
from pokerlab.preflop_suit_equity import remap_preflop_equities_by_suit
from scripts import benchmark_preflop_suit_remap as suits
from scripts.preflop_push_fold_equilibrium import equilibrium
from scripts.preflop_push_fold_validation import replay

reference = suits.reference
ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'benchmarks/preflop-prepared-budget-v1.json'
CONFIG_SHA256 = '4e482f2e5352c1ada5de0d2ace66f7dc6d7b7eda3285bdc7c6caefc5717aa999'


def validate_config(config):
    if reference.checksum(config) != CONFIG_SHA256 or 'artifact_sha256' in config:
        raise ValueError('Runner requires the exact prepared-budget v1 fixture and gates')


def source_hashes():
    result = suits.source_hashes()
    for path in ('scripts/benchmark_preflop_prepared_budget.py',
                 'benchmarks/preflop-prepared-budget-v1.json'):
        result[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    return result


def run_case(table, case, algorithm, iterations, resource_model):
    result = solve_prepared_push_fold(table, config=case['config'], algorithm=algorithm,
        iterations=iterations, resource_model=resource_model)
    json.dumps(result, allow_nan=False)
    return result


def main():
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    validate_config(config)
    source = source_hashes()
    counts, historical = reference.reference_counts()
    source_table = reference.trusted_reference_table(counts)
    suit_config = json.loads(suits.CONFIG.read_text(encoding='utf-8'))
    suits.validate_config(suit_config)
    case = suits.cases(suit_config, counts)[-1]
    table = remap_preflop_equities_by_suit(source_table, case['sb_range'], case['bb_range'])
    transfer = suits.check_transfer_provenance(source_table, case, counts)
    before = deepcopy(table)
    witness = equilibrium(case['sb_range'], case['bb_range'], case['config'], case['counts'])
    if Fraction(*witness['value_sb_fraction']) != suits.KNOWN_VALUE:
        raise AssertionError('Prepared fixture exact value changed')
    results, failures = [], []
    with ExitStack() as stack:
        for name in ('rank_hand', '_board_combinations'):
            stack.enter_context(patch.object(equity, name,
                side_effect=AssertionError('Prepared benchmark attempted board work')))
        stack.enter_context(patch('pokerlab.cards.rank_hand',
            side_effect=AssertionError('Prepared benchmark attempted card ranking')))
        for algorithm in config['algorithms']:
            for iterations in config['checkpoints']:
                times, previous = [], None
                repeats = config['final_repeats'] if iterations == config['checkpoints'][-1] else 1
                for _ in range(repeats):
                    gc.collect()
                    started = perf_counter()
                    result = run_case(table, case, algorithm, iterations, config['resource_model'])
                    times.append(perf_counter() - started)
                    if previous is not None and previous != result:
                        raise AssertionError('Repeated prepared solve payload changed')
                    previous = result
                checked = replay(result, case['sb_range'], case['bb_range'], case['config'],
                                 case['counts'], config['metric_absolute_tolerance'])
                certificate = reference.replay_witness(result, case, case['counts'], witness,
                                                       config['metric_absolute_tolerance'])
                error = abs(checked['value_sb'] - float(suits.KNOWN_VALUE))
                # Compare numerics directly where the legacy model admits;
                # retain its rejected requests as evidence, not changed limits.
                try:
                    legacy = run_case(table, case, algorithm, iterations, 'source-inclusive')
                except ValueError as exc:
                    if '500,000,000 modeled loop entries' not in str(exc):
                        raise
                    legacy_admission = {'admitted': False, 'reason': str(exc)}
                else:
                    if {k: v for k, v in result.items() if k != 'work_budget'} != {
                            k: v for k, v in legacy.items() if k != 'work_budget'}:
                        raise AssertionError('Work model changed strategy or numerical diagnostics')
                    legacy_admission = {'admitted': True, 'exact_nonbudget_payload_agreement': True,
                        'work_budget': legacy['work_budget']}
                if legacy_admission['admitted'] != (iterations <= 2000):
                    raise AssertionError('Legacy source-inclusive admission changed')
                if iterations == config['checkpoints'][-1]:
                    if checked['exploitability'] > config['exploitability_chip_limit']:
                        failures.append(algorithm + ': final exploitability target missed')
                    if error > config['known_value_error_chip_limit']:
                        failures.append(algorithm + ': final known-value target missed')
                    if algorithm == 'cfrplus' and checked['exploitability'] > config['cfrplus_final_exploitability_chip_limit']:
                        failures.append(algorithm + ': stronger final exploitability target missed')
                results.append({'algorithm': algorithm, 'iterations': iterations, 'seconds': times,
                    'median_seconds': statistics.median(times), 'result': result,
                    'independent': checked, 'known_value_error': error,
                    'equilibrium_witness_replay': certificate, 'legacy_admission': legacy_admission})
                print(f"{algorithm} {iterations}: exploitability={checked['exploitability']:.9g}; "
                      f"legacy_admitted={legacy_admission['admitted']}", flush=True)
        gc.collect()
        tracemalloc.start()
        try:
            run_case(table, case, 'cfrplus', config['checkpoints'][-1], config['resource_model'])
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
    if table != before or source_hashes() != source:
        raise AssertionError('Source table or dependencies changed during measurement')
    report = {'schema_version': 1, 'benchmark_id': config['benchmark_id'], 'config': config,
        'input': case, 'historical_physical_count_evidence': historical,
        'checked_suit_transfer_provenance': transfer,
        'exact_equilibrium_witness': reference.jsonable(witness),
        'provenance': {'git_revision': reference.git('rev-parse', 'HEAD'),
            'git_status': reference.git('status', '--short').splitlines(), 'source_sha256': source,
            'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
            'created_utc': datetime.now(timezone.utc).isoformat()},
        'source_unchanged': True, 'source_table_unchanged': True,
        'ranking_and_enumeration_calls': 0, 'warm_call_traced_peak_bytes': peak,
        'methodology': 'Complete prepared solve + exact production diagnostics + JSON. One timed call per intermediate checkpoint, three at final 10000 iterations, GC before timing. Legacy admitted calls compared exactly outside timing; legacy rejections retained. Independent Fraction replay/witness outside timing. Separate complete final CFR+ allocation trace excludes caller input table, construction, historical loading, original enumeration and RSS. No monotone convergence, kernel acceleration, cold-call or cross-source speedup claim.',
        'results': results, 'passed': not failures, 'failures': failures}
    report['artifact_sha256'] = reference.checksum(report)
    output = ROOT / 'benchmarks/results/preflop-prepared-budget-v1.json'
    temporary = output.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(output)
    print(json.dumps({'passed': report['passed'], 'failures': failures}), flush=True)
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
