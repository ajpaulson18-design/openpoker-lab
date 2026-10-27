"""Independent physical-deal and best-five oracle for exact selected chance."""
import itertools
import unittest
from collections import Counter
from fractions import Fraction

from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel

RANKS = '23456789TJQKA'
SB = 'AsAd:0.7,QsQd:0.3,2c2d:1e-300,JhJc:0.4'
BB = 'KsKd:0.4,JhJc:0.6,AsAd:0.2,7h7d:0.5'
RUNOUTS = ('2c3c4d7h8h', '2c3c4dKc8s', '2c3c4d7hAd',
           'ThJhQhKhAh', '2c3c4d8h7h')


def five(cards):
    """Return lexicographic poker rank, using only physical card strings."""
    rs = [RANKS.index(c[0]) + 2 for c in cards]
    count = Counter(rs)
    groups = sorted(((n, r) for r, n in count.items()), reverse=True)
    distinct = sorted(set(rs), reverse=True)
    if distinct == [14, 5, 4, 3, 2]:
        straight = 5
    else:
        straight = distinct[0] if len(distinct) == 5 and distinct[0] - distinct[-1] == 4 else 0
    flush = len({c[1] for c in cards}) == 1
    if flush and straight:
        return (8, straight)
    if groups[0][0] == 4:
        return (7, groups[0][1], groups[1][1])
    if groups[0][0] == 3 and groups[1][0] == 2:
        return (6, groups[0][1], groups[1][1])
    if flush:
        return (5, *sorted(rs, reverse=True))
    if straight:
        return (4, straight)
    if groups[0][0] == 3:
        return (3, groups[0][1], *sorted((r for r in rs if r != groups[0][1]), reverse=True))
    if groups[0][0] == 2 and groups[1][0] == 2:
        pairs = sorted((groups[0][1], groups[1][1]), reverse=True)
        return (2, *pairs, groups[2][1])
    if groups[0][0] == 2:
        return (1, groups[0][1], *sorted((r for r in rs if r != groups[0][1]), reverse=True))
    return (0, *sorted(rs, reverse=True))


def rank(cards):
    return max(map(five, itertools.combinations(cards, 5)))


def explicit_weights(text):
    result = {}
    for token in text.split(','):
        hand, weight = token.split(':')
        result[frozenset((hand[:2], hand[2:]))] = Fraction.from_float(float(weight))
    return result


def physical(kernel):
    weights = tuple(map(explicit_weights, (SB, BB)))
    result = []
    for i, h0 in enumerate(kernel.hands[0]):
        for j, h1 in enumerate(kernel.hands[1]):
            if set(h0) & set(h1):
                continue
            for raw in RUNOUTS:
                board = tuple(raw[k:k+2] for k in range(0, 10, 2))
                if set(h0 + h1) & set(board):
                    continue
                r0, r1 = rank(h0 + board), rank(h1 + board)
                sign = (r0 > r1) - (r0 < r1)
                mass = weights[0][frozenset(h0)] * weights[1][frozenset(h1)]
                result.append((i, j, (''.join(board[:3]), board[3], board[4]), mass, sign))
    return result


class ExactSelectedPhysicalOracleTests(unittest.TestCase):
    def test_all_prefixes_marginals_pairs_folds_and_showdowns(self):
        kernel = ExactSelectedRunoutKernel(SB, BB, RUNOUTS)
        rows = physical(kernel)
        z = sum((r[3] for r in rows), Fraction())
        self.assertEqual(kernel.normalizer, z)
        prefixes = {(), ('2c3c4d',), ('2c3c4d', '7h'), ('2c3c4d', '7h', '8h'), ('5c6c7c',)}
        for row in rows:
            prefixes.update(row[2][:n] for n in (1, 2, 3))
        reaches = ((Fraction(0), Fraction(1, 3), Fraction(1), Fraction(1, 7)),
                   (Fraction(1, 2), Fraction(0), Fraction(2, 5), Fraction(1)))
        for prefix in prefixes:
            selected = [r for r in rows if r[2][:len(prefix)] == prefix]
            self.assertEqual(kernel.prefix_mass_exact(prefix), sum((r[3] for r in selected), Fraction()) / z)
            expected_legal = tuple(frozenset(r[p] for r in selected) for p in (0, 1))
            self.assertEqual(kernel.legal_hands(prefix), expected_legal)
            actual = kernel.joint_marginals_exact(prefix)
            for p in (0, 1):
                expected = tuple(sum((r[3] for r in selected if r[p] == i), Fraction()) / z
                                 for i in range(len(kernel.hands[p])))
                self.assertEqual(actual[p], expected)
            for i in range(len(kernel.hands[0])):
                for j in range(len(kernel.hands[1])):
                    expected = sum((r[3] for r in selected if r[:2] == (i, j)), Fraction()) / z
                    self.assertEqual(kernel.pair_probability_exact(i, j, prefix), expected)
            for p in (0, 1):
                for kind, scale in (('fold', Fraction(-3, 4)), ('showdown', Fraction(5, 4))):
                    expected = [Fraction() for _ in kernel.hands[p]]
                    for i, j, _, mass, sign in selected:
                        expected[(i, j)[p]] += mass * reaches[1-p][(j, i)[p]] * scale * (sign if kind == 'showdown' else 1) * (1 if p == 0 else -1) / z
                    actual_values = kernel.terminal_values_exact(prefix, kind=kind, payoff=scale, player=p, opponent_reach=reaches[1-p])
                    self.assertEqual(tuple(actual_values), tuple(expected))

    def test_independent_rank_anchors(self):
        self.assertGreater(rank(('As','Ks','Qs','Js','Ts','2c','3c')), rank(('Ac','Ad','Ah','As','2d','3d','4d')))
        self.assertEqual(rank(('As','2s','3s','4s','5s','Kd','Qd')), (8, 5))


if __name__ == '__main__':
    unittest.main()

class ExactLawDivergenceTests(unittest.TestCase):
    def test_legacy_binary64_world_rounding_is_not_rank_one(self):
        # All four pairs are physically compatible on this common board.
        # A rounded per-world product/divisor is the historical raw operation.
        divisor = 17296 * 45 * 44
        rounded = [[Fraction.from_float(x * y / divisor) for y in (0.4, 0.6)]
                   for x in (0.7, 0.3)]
        self.assertNotEqual(rounded[0][0] * rounded[1][1],
                            rounded[0][1] * rounded[1][0])
        exact = [[Fraction.from_float(x) * Fraction.from_float(y)
                  for y in (0.4, 0.6)] for x in (0.7, 0.3)]
        self.assertEqual(exact[0][0] * exact[1][1], exact[0][1] * exact[1][0])

class ExactSelectedBoundaryTests(unittest.TestCase):
    def test_duplicate_physical_holding_is_rejected(self):
        with self.assertRaises(ValueError):
            ExactSelectedRunoutKernel({('As', 'Ad'): .5, ('Ad', 'As'): .4},
                                     {('Ks', 'Kd'): 1.0}, ('2c3c4d7h8h',))

    def test_no_legacy_world_producer_is_called(self):
        from unittest.mock import patch
        from pokerlab.selected_runout_operator import SelectedRunoutOperator
        with patch.object(SelectedRunoutOperator, '_iter_worlds', side_effect=AssertionError('legacy world enumeration')):
            kernel = ExactSelectedRunoutKernel(SB, BB, RUNOUTS)
            kernel.joint_marginals_exact(())
            kernel.terminal_values_exact((), kind='showdown', payoff=1, player=0,
                                         opponent_reach=(1,) * len(kernel.hands[1]))

    def test_noncanonical_prefix_rejects_before_rank_cache(self):
        kernel = ExactSelectedRunoutKernel(SB, BB, RUNOUTS)
        before = kernel.statistics()['rank_calls']
        with self.assertRaises(ValueError):
            kernel.terminal_values_exact(('4d3c2c',), kind='showdown', payoff=1,
                                         player=0, opponent_reach=(1,) * len(kernel.hands[1]))
        self.assertEqual(before, kernel.statistics()['rank_calls'])

    def test_authoritative_snapshots_are_immutable(self):
        kernel = ExactSelectedRunoutKernel(SB, BB, RUNOUTS)
        for name in ('hands', 'weights', 'selected', 'normalizer', 'limits'):
            with self.subTest(name=name):
                with self.assertRaises((AttributeError, TypeError)):
                    setattr(kernel, name, None)

    def test_overlong_prefix_consumption_is_bounded(self):
        kernel = ExactSelectedRunoutKernel(SB, BB, RUNOUTS)
        consumed = []
        def tokens():
            for i in range(10000):
                consumed.append(i)
                yield '2c3c4d' if i == 0 else '7h'
        with self.assertRaises(ValueError):
            kernel.prefix_mass_exact(tokens())
        self.assertLessEqual(len(consumed), 4)

    def test_fraction_growth_rejects_before_ranking(self):
        kernel = ExactSelectedRunoutKernel(SB, BB, RUNOUTS)
        reach = (Fraction(1, 2**40000 - 1), Fraction(1, 2**39999 - 1), Fraction(0), Fraction(0))
        before = kernel.statistics()
        with self.assertRaises(ValueError):
            kernel.terminal_values_exact((), kind='showdown', payoff=1, player=0,
                                         opponent_reach=reach)
        after = kernel.statistics()
        self.assertEqual(after['rank_calls'], before['rank_calls'])
        self.assertEqual(after['rank_cache_misses'], before['rank_cache_misses'])

    def test_repeated_random_is_charged_before_range_expansion(self):
        from unittest.mock import patch
        from pokerlab.exact_selected_kernel import ExactSelectedKernelLimits
        limits = ExactSelectedKernelLimits(max_modeled_work=100000)
        with patch('pokerlab.exact_selected_kernel.expand_range', side_effect=AssertionError('parser entered')):
            with self.assertRaises(ValueError):
                ExactSelectedRunoutKernel(' '.join(['random'] * 30), 'KsKd',
                                          ('2c3c4d7h8h',), limits=limits)

    def test_mapping_cannot_exceed_declared_size(self):
        class DishonestMapping:
            def __len__(self): return 1
            def __bool__(self): return True
            def items(self):
                for i in range(10000):
                    consumed.append(i)
                    yield (('As', 'Ad') if i == 0 else ('Ks', 'Kd')), 1.0
        consumed = []
        with self.assertRaises(ValueError):
            ExactSelectedRunoutKernel(DishonestMapping(), 'QsQd', ('2c3c4d7h8h',))
        self.assertLessEqual(len(consumed), 2)

    def test_runout_cannot_exceed_declared_size(self):
        class DishonestRunouts:
            def __len__(self): return 1
            def __iter__(self):
                cards = [r + suit for r in RANKS for suit in 'cdhs' if r + suit not in ('2c', '3c', '4d')]
                for i, (turn, river) in enumerate(itertools.permutations(cards, 2)):
                    consumed.append(i)
                    yield '2c3c4d' + turn + river
        consumed = []
        with self.assertRaises(ValueError):
            ExactSelectedRunoutKernel('AsAd', 'KsKd', DishonestRunouts())
        self.assertLessEqual(len(consumed), 65)
