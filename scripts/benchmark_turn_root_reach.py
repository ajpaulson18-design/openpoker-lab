"""Fixed root-fold arithmetic witnesses with independent physical-world sums.

These are payoff-primitive checks, not learned strategies or equilibrium tests.
The oracle uses the supplied binary64 weights as exact Fractions and enumerates
private hands and selected rivers without production probability/payoff helpers.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import platform
import sys

from pokerlab.turn_range_kernel import TurnRangePayoffs
from pokerlab.river_tree import _Terminal
from scripts.benchmark_turn_river_independent import ROOT, source_hashes
from scripts.validate_turn_reach_parity import BASE, EXPECTED, _historical


def cases():
    common = {
        'board': ['2c', '5d', '9h', 'Jc'], 'runouts': ['As'],
        'hands': [[['Ah', 'As'], ['Kc', 'Kd']], [['Qh', 'Qs']]],
        'weights': [[1.0, 1e-300], [1.0]],
        'reaches': [[1e-100], [0.0, 1e-100]],
    }
    return [
        dict(common, id='normal-mass-underflowed-reach', pot=20.0),
        dict(common, id='normal-mass-scale-one-unit', pot=2e100),
        dict(common, id='nonzero-subnormal-joint-product', pot=2e20,
             reaches=[[1e-20], [0.0, 1e-20]]),
        {
            'id': 'unequal-two-river-normal-masses',
            'board': ['2c', '7d', '9h', 'Js'], 'runouts': ['As', 'Ah'],
            'hands': [[['Ah', 'As'], ['3c', '4c'], ['3h', 'As']],
                      [['Ah', 'As'], ['5c', '6c']]],
            'weights': [[1.0, 1e-150, 2e-150], [1.0, 1e-150]],
            'reaches': [[1e-30, 2.5e-31], [1e-30, 2.5e-31, 7.5e-31]],
            'pot': 2e30,
        },
        dict(common, id='normal-joint-subnormal-normalized-product',
             runouts=['2d', '2h', '2s', '3c', '3d', '3h', '3s', '4c', '4d', '4h'],
             weights=[[1.0, 3e-309], [1.0]], reaches=[[1.0], [1.0, 1.0]],
             pot=1e308),
        dict(common, id='true-zero-reach-control', pot=20.0,
             reaches=[[0.0], [0.0, 0.0]]),
    ]


def physical_values(case, player, winner, matched):
    """Enumerate exact physical pair x selected-card mass, with no rank/tree."""
    total = F(0)
    numerator = [F(0) for _ in case['hands'][player]]
    worlds = 0
    for i, hand0 in enumerate(case['hands'][0]):
        for j, hand1 in enumerate(case['hands'][1]):
            if set(hand0).intersection(hand1):
                continue
            for river in case['runouts']:
                if river in case['board'] or river in hand0 or river in hand1:
                    continue
                worlds += 1
                mass = F.from_float(case['weights'][0][i]) * F.from_float(case['weights'][1][j])
                total += mass
                own, opponent = (i, j) if player == 0 else (j, i)
                numerator[own] += mass * F.from_float(case['reaches'][player][opponent])
    if not total or worlds > 1000:
        raise ValueError('Witness world count outside fixed small-game scope')
    scale = F.from_float(case['pot']) / 2 + F(matched)
    sign = 1 if winner == player else -1
    return [value / total * scale * sign for value in numerator], worlds


def _fingerprints(baseline):
    result = source_hashes()
    for name in ('benchmark_turn_root_reach.py', 'validate_turn_reach_parity.py'):
        path = ROOT / 'scripts' / name
        result[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in EXPECTED:
        result['historical/' + name] = hashlib.sha256((baseline / name).read_bytes()).hexdigest()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    _historical(args.baseline_dir)
    old_type = sys.modules['pokerlab._conditioning_baseline_kernel'].TurnRangePayoffs
    before = _fingerprints(args.baseline_dir)
    witnesses = cases()
    rows = []
    for case in witnesses:
        hand_tuples = tuple(tuple(tuple(hand) for hand in side) for side in case['hands'])
        current = TurnRangePayoffs(case['board'], hand_tuples, case['weights'],
                                   pot=case['pot'], runouts=case['runouts'])
        historical = old_type(case['board'], hand_tuples, case['weights'],
                              pot=case['pot'], runouts=case['runouts'])
        if current.exceptional_conditioning or historical.exceptional_conditioning:
            raise ValueError('Require ordinary raw branch mass in every witness')
        for player in (0, 1):
            reach = case['reaches'][player]
            for winner in (0, 1):
                for matched in (0, 4):
                    terminal = _Terminal('fold', (float(matched), float(matched)), winner)
                    exact, worlds = physical_values(case, player, winner, matched)
                    expected = list(map(float, exact))
                    old = historical.values(terminal, reach, player)
                    actual = current.values(terminal, reach, player)
                    prefixes = [current.values(terminal, reach, player, prefix=(river,))
                                for river in current.branch_probabilities]
                    summed = [sum(values[i] for values in prefixes) for i in range(len(actual))]
                    if not all(math.isfinite(value) for value in actual + summed):
                        raise ValueError('Every root/prefix witness value must be finite')
                    if any((e == 0.0 and a != 0.0) or (e != 0.0 and a == 0.0)
                           for a, e in zip(actual, expected)):
                        raise ValueError('Witness must preserve exact zero/nonzero support')
                    delta = [a - e for a, e in zip(actual, expected)]
                    normalized = [abs(d) / (abs(e) if e else 1.0) for d, e in zip(delta, expected)]
                    prefix_delta = [a - b for a, b in zip(actual, summed)]
                    if max(normalized, default=0.0) > 1e-12:
                        raise ValueError('Stable root disagrees with independent physical-world sum')
                    if any(abs(d) / (abs(e) if e else 1.0) > 1e-12
                           for d, e in zip(prefix_delta, expected)):
                        raise ValueError('Stable root disagrees with summed conditioned prefixes')
                    if case['id'] == 'normal-mass-scale-one-unit' and matched == 0:
                        anchor = [0.0, 1.0 if winner == player else -1.0] if player == 0 else [1.0 if winner == player else -1.0]
                        if actual != anchor or expected != anchor:
                            raise ValueError('Independent one-unit anchor must agree exactly')
                    rows.append({
                        'scenario': case['id'], 'player': player, 'winner': winner,
                        'matched': matched, 'physical_worlds': worlds,
                        'expected_fraction': list(map(str, exact)),
                        'expected_float': expected, 'historical_root': old,
                        'current_root': actual, 'summed_prefix': summed,
                        'current_physical_differences': delta,
                        'current_normalized_absolute_errors': normalized,
                        'historical_physical_differences': [a - e for a, e in zip(old, expected)],
                        'root_prefix_differences': prefix_delta,
                    })
        stable_calls = current.stable_root_fold_calls
        if case['id'] == 'true-zero-reach-control':
            if stable_calls or current.stable_root_fold_pair_checks:
                raise ValueError('True-zero control must not use stable path')
        elif not stable_calls:
            raise ValueError('Each declared risk witness must exercise stable path')
    if _fingerprints(args.baseline_dir) != before:
        raise RuntimeError('Protected source changed during witnesses; discard report')
    report = {
        'schema_version': 1, 'benchmark_id': 'turn-root-reach-witnesses-v1',
        'baseline_git_ref': BASE, 'baseline_canonical_sha256': EXPECTED,
        'source_sha256': before, 'python': platform.python_version(),
        'fixtures': witnesses, 'results': rows,
        'acceptance': {'max_normalized_absolute_error': 1e-12,
                       'one_unit_anchor_exact': True, 'true_zero_uses_stable_path': False},
        'scope': 'Forty-eight numerical fold-vector witnesses only. No learned strategy, convergence, speed, allocation or RSS claim. Independent Fraction oracle normalizes the raw supplied binary64 physical-world weights; stable production fallback uses its established binary64 root mass. Nonzero agreement uses the declared relative tolerance with exact zero/nonzero classification, not an exact normalization identity.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print('Verified', len(rows), 'independent root-fold numerical witnesses')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
