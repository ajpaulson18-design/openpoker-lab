"""Reweight verified historical pair counts; never re-enumerate their boards."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import gc
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from time import perf_counter
import tracemalloc
from unittest.mock import patch

from pokerlab import preflop_full_board_equity as equity
from pokerlab.preflop_push_fold import reweight_preflop_equities, solve_prepared_push_fold
from scripts.preflop_push_fold_equilibrium import equilibrium
from scripts.preflop_push_fold_validation import replay

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'benchmarks/preflop-equity-reweight-v1.json'
PARENT = 'a5e1b75ab424c97673f5126796b9d7eae14b0706'
CONFIG_SHA256 = 'fcef332396c2823a961667ab9dc4c961b2e768d95ab3fc93851bb1f82133540e'
PUBLISHED = {
    'preflop-push-fold-v1.json': 'f4a4c57dc7ec0d1e544450aa9b9832c090080479',
    'preflop-push-fold-v1-production.json': '7955c97d71252691adbb53e63314027b27edc633',
    'preflop-push-fold-v1-oracle-pair-0.json': 'cc510379eed9484f30e59e428917a9e55ba027a7',
    'preflop-push-fold-v1-oracle-pair-1.json': 'd639fecaee1c9f1ca1eaec95bb29e3162ddd00ff',
    'preflop-push-fold-v1-oracle-pair-2.json': '864c80c32739f6665b6010c200ad31bcb32e439f',
}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def checksum(data):
    return hashlib.sha256(json.dumps(
        {k: v for k, v in data.items() if k != 'artifact_sha256'},
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate_config(config):
    if checksum(config) != CONFIG_SHA256 or 'artifact_sha256' in config:
        raise ValueError('Runner requires the exact declared v1 fixture and gates')


def reference_counts():
    """Read immutable published blobs, not self-authenticating working JSON."""
    documents = {}
    for name, expected_blob in PUBLISHED.items():
        path = 'benchmarks/results/' + name
        if git('rev-parse', f'{PARENT}:{path}') != expected_blob:
            raise ValueError('Pinned historical Git blob mismatch')
        document = json.loads(git('show', f'{PARENT}:{path}'))
        if (document.get('artifact_sha256') != checksum(document)
                or document.get('schema_version') != 1
                or document.get('benchmark_id') != 'preflop-push-fold-v1'):
            raise ValueError('Invalid historical evidence checksum/schema')
        documents[name] = document
    verified = documents['preflop-push-fold-v1.json']
    production = documents['preflop-push-fold-v1-production.json']
    if verified['passed'] is not True or verified['failures']:
        raise ValueError('Historical physical evidence did not pass')
    counts = verified['independent_counts']
    if counts != production['results'][0]['result']['pair_equities']:
        raise ValueError('Historical production/oracle counts differ')
    identities = [('AdAs', 'KdKs'), ('QdQs', 'AsKh'), ('QdQs', 'KdKs')]
    for i, (row, identity, prior) in enumerate(zip(
            counts, identities, (Fraction(8, 13), Fraction(1, 13), Fraction(4, 13)))):
        oracle = documents[f'preflop-push-fold-v1-oracle-pair-{i}.json']
        if (oracle['counts'] != row or oracle['private_pair'] != list(identity)
                or oracle['pair_probability_fraction'] != [prior.numerator, prior.denominator]
                or oracle['phase'] != 'independent-full-board-oracle'
                or row['boards'] != 1_712_304
                or any(type(row[k]) is not int or row[k] < 0 for k in ('wins', 'ties', 'losses'))
                or sum(row[k] for k in ('wins', 'ties', 'losses')) != 1_712_304):
            raise ValueError('Historical pair identity/count proof mismatch')
    if len(counts) != 3:
        raise ValueError('Historical proof requires exactly three pairs')
    # The ranking and reference-ranking sources have not changed since proof.
    manifest = verified['provenance']['source_sha256']
    for path in ('pokerlab/cards.py', 'scripts/preflop_validation.py'):
        if git('rev-parse', f'{PARENT}:{path}') != git('hash-object', path):
            raise ValueError('Historical ranker dependency changed')
    return counts, {
        'published_parent_commit': PARENT, 'artifact_git_blobs': PUBLISHED,
        'original_solver_source': '4650d6591c88c25f1a04c28fcf4960efc6ec33de',
        'original_source_sha256': manifest,
        'verified_artifact_sha256': verified['artifact_sha256'],
        'scope': 'Previously independently enumerated physical pair counts. Reused exactly; no current full-board enumeration or new-pair coverage claim.',
    }


def trusted_reference_table(counts):
    plan = equity.plan_preflop_equities('AsAd:1,QsQd:0.5', 'AsKh:0.25,KsKd:1')
    by_pair = {(r['sb_hand'], r['bb_hand']): r for r in counts}
    rows, totals = [], []
    for i, j, prior in plan.pairs:
        item = by_pair[''.join(plan.hands[0][i]), ''.join(plan.hands[1][j])]
        totals.append((item['wins'], item['ties'], item['losses']))
        for sign, count in ((-1, item['losses']), (0, item['ties']), (1, item['wins'])):
            if count:
                rows.append((i, j, float(prior * Fraction(count, item['boards'])), sign))
    table = equity.FullBoardEquities(plan.hands, plan.pairs, tuple(totals), tuple(rows), plan._budget_items)
    table.validate()
    return table


def source_hashes():
    modules = ('__init__', 'cards', 'equity', 'analysis', 'cfr', 'cfr_plus',
               'river_config', 'river_tree', 'preflop_tree',
               'preflop_full_board_equity', 'preflop_push_fold')
    paths = [ROOT / 'pokerlab' / (name + '.py') for name in modules] + [
        ROOT / 'scripts/preflop_validation.py',
        ROOT / 'scripts/preflop_push_fold_validation.py',
        ROOT / 'scripts/preflop_push_fold_equilibrium.py',
        Path(__file__).resolve(), CONFIG,
    ]
    return {str(p.relative_to(ROOT)).replace('\\', '/'):
            hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def jsonable(value):
    if isinstance(value, Fraction):
        return [value.numerator, value.denominator]
    if isinstance(value, dict):
        return {f'{k[0]}:{k[1]}' if isinstance(k, tuple) else k: jsonable(v)
                for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(v) for v in value]
    return value


def run_case(table, case, config):
    changed = reweight_preflop_equities(table, case['sb_range'], case['bb_range'])
    result = solve_prepared_push_fold(changed, config=case['config'],
        iterations=config['iterations'], algorithm=config['algorithm'])
    json.dumps(result, allow_nan=False)
    return changed, result


def replay_witness(result, case, counts, witness, tolerance):
    """Check the matrix certificate through the separate own-hand BR replay."""
    candidate = deepcopy(result)
    for row in candidate['strategy']:
        player = {'sb': 0, 'bb': 1}[row['player']]
        probability = witness['behavioral_probabilities'][player, row['hand']]
        row['actions'][0]['probability'] = float(1 - probability)
        row['actions'][1]['probability'] = float(probability)
    value = float(Fraction(*witness['value_sb_fraction']))
    candidate.update(value_sb=value, value_bb=-value,
        sb_best_response_value=value, bb_best_response_value=-value,
        nash_conv=0., exploitability=0., sb_best_response_gain=0., bb_best_response_gain=0.)
    return replay(candidate, case['sb_range'], case['bb_range'], case['config'],
                  counts, tolerance)


def main():
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    validate_config(config)
    source = source_hashes()
    counts, historical = reference_counts()
    table = trusted_reference_table(counts)
    before = deepcopy(table)
    results, failures = [], []
    # Any accidental expensive path fails immediately, rather than reporting
    # a cached-step timing that secretly included new ranking.
    with ExitStack() as stack:
        for name in ('rank_hand', '_board_combinations'):
            stack.enter_context(patch.object(equity, name,
                side_effect=AssertionError('Reweight benchmark attempted board work')))
        stack.enter_context(patch('pokerlab.cards.rank_hand',
            side_effect=AssertionError('Reweight benchmark attempted card ranking')))
        for case in config['cases']:
            times = []
            previous_result = None
            for _ in range(config['repeats']):
                gc.collect()
                started = perf_counter()
                changed, result = run_case(table, case, config)
                times.append(perf_counter() - started)
                if previous_result is not None and result != previous_result:
                    raise AssertionError('Repeated solve payload changed')
                previous_result = result
            keys = {(row['sb_hand'], row['bb_hand']) for row in result['pair_equities']}
            selected_counts = [row for row in counts if (row['sb_hand'], row['bb_hand']) in keys]
            checked = replay(result, case['sb_range'], case['bb_range'], case['config'],
                             selected_counts, config['metric_absolute_tolerance'])
            witness = equilibrium(case['sb_range'], case['bb_range'], case['config'], selected_counts)
            certificate_check = replay_witness(result, case, selected_counts, witness,
                                               config['metric_absolute_tolerance'])
            error = abs(checked['value_sb'] - float(Fraction(*witness['value_sb_fraction'])))
            if checked['exploitability'] > config['exploitability_chip_limit']:
                failures.append(case['id'] + ': exploitability target missed')
            if error > config['known_value_error_chip_limit']:
                failures.append(case['id'] + ': known-value target missed')
            results.append({'id': case['id'], 'input': case,
                'median_seconds': statistics.median(times), 'seconds': times,
                'independent': checked, 'known_value_error': error,
                'equilibrium_witness_replay': certificate_check,
                'exact_equilibrium_witness': jsonable(witness), 'result': result})
            print(f"{case['id']}: exploitability={checked['exploitability']:.9g}, "
                  f"known-value-error={error:.9g}", flush=True)
        gc.collect()
        tracemalloc.start()
        try:
            run_case(table, config['cases'][0], config)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
    if table != before:
        raise AssertionError('Source equity table mutated')
    if source_hashes() != source:
        raise RuntimeError('Source changed during measurement')
    report = {'schema_version': 1, 'benchmark_id': config['benchmark_id'],
        'config': config, 'historical_physical_count_evidence': historical,
        'provenance': {'git_revision': git('rev-parse', 'HEAD'),
            'git_status': git('status', '--short').splitlines(), 'source_sha256': source,
            'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
            'created_utc': datetime.now(timezone.utc).isoformat()},
        'source_unchanged': True, 'ranking_and_enumeration_calls': 0,
        'source_table_unchanged': True, 'warm_call_traced_peak_bytes': peak,
        'methodology': 'Three repeated complete reweight + prepared solve + exact production diagnostics + JSON calls per case, GC before timing; independent Fraction equilibrium/replay outside timing. Separate allocation trace of the same warm call. Excludes original equity preparation, reference input table and historical-file loading; not RSS or a cross-source speedup comparison.',
        'results': results, 'passed': not failures, 'failures': failures}
    report['artifact_sha256'] = checksum(report)
    output = ROOT / 'benchmarks/results/preflop-equity-reweight-v1.json'
    temporary = output.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(output)
    print(json.dumps({'passed': report['passed'], 'failures': failures}), flush=True)
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
