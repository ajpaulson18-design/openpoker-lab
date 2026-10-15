"""Verify global suit transfer, then measure complete bounded warm solves."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import gc
from itertools import permutations
import json
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter
import tracemalloc
from unittest.mock import patch

from pokerlab import preflop_full_board_equity as equity
from pokerlab.preflop_suit_equity import (
    remap_preflop_equities_by_suit, preflop_suit_remap_provenance,
)
from pokerlab.preflop_push_fold import solve_prepared_push_fold
from scripts import benchmark_preflop_equity_reweight as reference
from scripts.preflop_push_fold_equilibrium import equilibrium
from scripts.preflop_push_fold_validation import replay
from scripts.preflop_suit_validation import mapped_counts, verify_toy_suit_invariance

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'benchmarks/preflop-suit-remap-v1.json'
CONFIG_SHA256 = '1bc9040cbfda632b05e876103b0223d498e505586741ec59e1c6387b422ec480'
KNOWN_VALUE = Fraction(256757651065, 457587630786)


def validate_config(config):
    if reference.checksum(config) != CONFIG_SHA256 or 'artifact_sha256' in config:
        raise ValueError('Runner requires the exact v1 suit fixture and gates')


def transform_range(expression, mapping):
    output = []
    for token in expression.split(','):
        hand, weight = token.split(':')
        changed = ''.join(sorted(hand[i] + mapping[hand[i + 1]] for i in (0, 2)))
        output.append(changed + ':' + weight)
    return ','.join(output)


def cases(config, counts):
    result = []
    for target_suits in permutations('cdhs'):
        mapping = dict(zip('cdhs', target_suits))
        result.append({'id': 'suits-' + ''.join(target_suits),
            'sb_range': transform_range('AsAd:1,QsQd:0.5', mapping),
            'bb_range': transform_range('AsKh:0.25,KsKd:1', mapping),
            'config': {'small_blind': .5, 'big_blind': 1, 'starting_stack': 2},
            'suit_mapping': mapping, 'counts': mapped_counts(counts, mapping)})
    split = deepcopy(config['split_game'])
    split['id'] = 'split-ak-four-pairs-three-bb-hands'
    by_pair = {(r['sb_hand'], r['bb_hand']): r for r in counts}
    qq_ak = by_pair['QdQs', 'AsKh']
    added = mapped_counts([qq_ak], dict(zip('cdhs', 'hdcs')))[0]
    split['counts'] = [deepcopy(by_pair['AdAs', 'KdKs']), deepcopy(qq_ak),
                       added, deepcopy(by_pair['QdQs', 'KdKs'])]
    for row, prior in zip(split['counts'], (Fraction(8, 13), Fraction(1, 26),
                                          Fraction(1, 26), Fraction(4, 13))):
        row['pair_probability'] = float(prior)
    split['suit_transfer'] = {'source_pair': ['QdQs', 'AsKh'],
        'target_pair': ['QdQs', 'AsKc'], 'mapping': dict(zip('cdhs', 'hdcs')),
        'reason': 'h/c swap fixes both QQ cards and maps the complete ordered private pair'}
    return result + [split]


def source_hashes():
    import hashlib
    result = reference.source_hashes()
    for path in ('scripts/benchmark_preflop_equity_reweight.py',
                 'benchmarks/preflop-equity-reweight-v1.json',
                 'pokerlab/preflop_suit_equity.py',
                 'scripts/preflop_suit_validation.py',
                 'scripts/benchmark_preflop_suit_remap.py',
                 'benchmarks/preflop-suit-remap-v1.json'):
        result[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    return result


def run_case(table, case, config):
    changed = remap_preflop_equities_by_suit(table, case['sb_range'], case['bb_range'])
    result = solve_prepared_push_fold(changed, config=case['config'],
        iterations=config['iterations'], algorithm=config['algorithm'])
    json.dumps(result, allow_nan=False)
    return result


def check_transfer_provenance(table, case, source_counts):
    rows = preflop_suit_remap_provenance(table, case['sb_range'], case['bb_range'])
    source = {(r['sb_hand'], r['bb_hand']): r for r in source_counts}
    expected = {(r['sb_hand'], r['bb_hand']): r for r in case['counts']}
    checked = set()
    for row in rows:
        original = source[row['source_sb_hand'], row['source_bb_hand']]
        mapped = mapped_counts([original], row['suit_permutation'])[0]
        key = row['target_sb_hand'], row['target_bb_hand']
        if key in checked or key != (mapped['sb_hand'], mapped['bb_hand']):
            raise AssertionError('Reported suit map does not map both ordered endpoints')
        checked.add(key)
        for field in ('wins', 'ties', 'losses', 'boards'):
            if mapped[field] != expected[key][field]:
                raise AssertionError('Suit transfer changed source counts')
    if checked != set(expected):
        raise AssertionError('Suit provenance does not cover every target pair')
    return rows


def main():
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    validate_config(config)
    source = source_hashes()
    counts, historical = reference.reference_counts()
    table = reference.trusted_reference_table(counts)
    before = deepcopy(table)
    fixtures = cases(config, counts)
    assert len(fixtures) == 25 and len({r['id'] for r in fixtures}) == 25
    # Separate independent ranking on a declared toy deck, before timings.
    print('Running independent 24-image toy-deck proof', flush=True)
    toy_proof = verify_toy_suit_invariance()
    results, failures = [], []
    with ExitStack() as stack:
        for name in ('rank_hand', '_board_combinations'):
            stack.enter_context(patch.object(equity, name,
                side_effect=AssertionError('Suit remap attempted physical board work')))
        stack.enter_context(patch('pokerlab.cards.rank_hand',
            side_effect=AssertionError('Suit remap attempted production ranking')))
        for case in fixtures:
            times, previous = [], None
            for _ in range(config['repeats']):
                gc.collect()
                started = perf_counter()
                result = run_case(table, case, config)
                times.append(perf_counter() - started)
                if previous is not None and previous != result:
                    raise AssertionError('Repeated remap solve payload changed')
                previous = result
            checked = replay(result, case['sb_range'], case['bb_range'], case['config'],
                             case['counts'], config['metric_absolute_tolerance'])
            transfer = check_transfer_provenance(table, case, counts)
            witness = equilibrium(case['sb_range'], case['bb_range'], case['config'], case['counts'])
            if Fraction(*witness['value_sb_fraction']) != KNOWN_VALUE:
                raise AssertionError('Suit image or split game changed exact equilibrium value')
            certificate = reference.replay_witness(result, case, case['counts'], witness,
                                                    config['metric_absolute_tolerance'])
            error = abs(checked['value_sb'] - float(KNOWN_VALUE))
            if checked['exploitability'] > config['exploitability_chip_limit']:
                failures.append(case['id'] + ': exploitability target missed')
            if error > config['known_value_error_chip_limit']:
                failures.append(case['id'] + ': known-value target missed')
            results.append({'id': case['id'], 'input': case, 'seconds': times,
                'median_seconds': statistics.median(times), 'result': result,
                'independent': checked, 'known_value_error': error,
                'exact_equilibrium_witness': reference.jsonable(witness),
                'checked_suit_transfer_provenance': transfer,
                'equilibrium_witness_replay': certificate})
            print(case['id'] + ': independently verified', flush=True)
        gc.collect()
        tracemalloc.start()
        try:
            run_case(table, fixtures[-1], config)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
    if table != before or source_hashes() != source:
        raise AssertionError('Source table or benchmark dependencies changed')
    image_transfers = sum(len(row['checked_suit_transfer_provenance']) for row in results[:24])
    split_transfers = len(results[-1]['checked_suit_transfer_provenance'])
    if (image_transfers, split_transfers) != (72, 4):
        raise AssertionError('Pair-transfer coverage census changed')
    report = {'schema_version': 1, 'benchmark_id': config['benchmark_id'], 'config': config,
        'historical_physical_count_evidence': historical, 'independent_toy_suit_proof': toy_proof,
        'provenance': {'git_revision': reference.git('rev-parse', 'HEAD'),
            'git_status': reference.git('status', '--short').splitlines(), 'source_sha256': source,
            'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
            'created_utc': datetime.now(timezone.utc).isoformat()},
        'source_unchanged': True, 'source_table_unchanged': True,
        'fixture_count': 25, 'image_pair_transfers': image_transfers,
        'split_game_pair_transfers': split_transfers, 'total_pair_transfers': image_transfers + split_transfers,
        'production_ranking_and_enumeration_calls': 0, 'warm_call_traced_peak_bytes': peak,
        'methodology': '25 fixtures, three complete suit-remap + prepared solve + exact production diagnostics + JSON calls each, GC before timing. Independent toy ranking before timings; exact Fraction matrix witnesses and own-hand policy replay outside timing. Separate complete split-game warm allocation trace excludes source table, historical file loading, original full-board preparation and RSS. No cold-call or cross-source speed comparison. Suit transfers reuse original physical counts, not newly enumerated 52-card boards.',
        'results': results, 'passed': not failures, 'failures': failures}
    report['artifact_sha256'] = reference.checksum(report)
    output = ROOT / 'benchmarks/results/preflop-suit-remap-v1.json'
    temporary = output.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(output)
    print(json.dumps({'passed': report['passed'], 'failures': failures}), flush=True)
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
