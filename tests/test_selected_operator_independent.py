import unittest
from fractions import Fraction

from pokerlab.cards import expand_range
from pokerlab.river_tree import _Terminal
from pokerlab.selected_runout_operator import SelectedRunoutOperator
from scripts.preflop_validation import independent_rank


SB = 'AsAd:0.7,QsQd:0.3'
BB = 'KsKd:0.4,JhJc:0.6'
RUNOUTS = ('2c3c4d7h8h', '2c3c4dKc8s', '2c3c4d7hAd',
           'ThJhQhKhAh', '2c3c4d8h7h')


def physical_rows(operator):
    """Enumerate cards independently; retain exact binary64 range products."""
    ranges = (expand_range(SB), expand_range(BB))
    pending = []
    for i, h0 in enumerate(operator.hands[0]):
        for j, h1 in enumerate(operator.hands[1]):
            if len(set(h0 + h1)) != 4:
                continue
            for raw in RUNOUTS:
                board = tuple(raw[k:k+2] for k in range(0, 10, 2))
                if set(h0 + h1) & set(board):
                    continue
                r0 = independent_rank(h0 + board)
                r1 = independent_rank(h1 + board)
                sign = (r0 > r1) - (r0 < r1)
                raw_mass = Fraction.from_float(ranges[0][h0]) * Fraction.from_float(ranges[1][h1])
                prefix = (''.join(sorted(board[:3], key=lambda c: ('23456789TJQKA'.index(c[0]), 'cdhs'.index(c[1])))), board[3], board[4])
                pending.append((i, j, raw_mass, sign, prefix))
    z = sum((row[2] for row in pending), Fraction())
    return [(i, j, float(mass / z), sign, prefix) for i, j, mass, sign, prefix in pending]


class IndependentSelectedOperatorTests(unittest.TestCase):
    def test_prefix_and_terminal_physical_enumeration(self):
        op = SelectedRunoutOperator(SB, BB, RUNOUTS)
        op.pot = 1.0
        rows = physical_rows(op)
        prefixes = {()}
        for *_, prefix in rows:
            prefixes.update(prefix[:k] for k in range(1, 4))
        self.assertGreater(len(prefixes), 5)
        for prefix in prefixes:
            selected = [row for row in rows if row[4][:len(prefix)] == prefix]
            edges = {(i, j): (m, s) for i, j, m, s in op.iter_edges(prefix, signed=True)}
            pairs = {(i, j) for i, j, *_ in selected}
            self.assertEqual(set(edges), pairs)
            marginals = op.joint_marginals(prefix)
            for player in (0, 1):
                for index in range(op.hand_counts[player]):
                    expected = sum(row[2] for row in selected if row[player] == index)
                    self.assertAlmostEqual(marginals[player][index], expected, delta=1e-14)
            for i, j in pairs:
                expect_mass = sum(row[2] for row in selected if row[:2] == (i, j))
                expect_signed = sum(row[2] * row[3] for row in selected if row[:2] == (i, j))
                self.assertAlmostEqual(edges[i, j][0], expect_mass, delta=1e-14)
                self.assertAlmostEqual(edges[i, j][1], expect_signed, delta=1e-14)
            for node in (_Terminal('fold', (0.5, 2.0), 0),
                         _Terminal('fold', (1.5, 1.0), 1),
                         _Terminal('showdown', (0.5, 2.0))):
                for target in (0, 1):
                    reaches = ([0.2, 0.9], [0.75, 0.1])[1-target]
                    expected = [0.0] * op.hand_counts[target]
                    for i, j, mass, sign, _ in selected:
                        multiplier = (1 if node.winner == 0 else -1) if node.kind == 'fold' else sign
                        payoff = multiplier * (op.pot / 2 + min(node.contributions))
                        expected[(i, j)[target]] += mass * reaches[(j, i)[target]] * payoff * (1 if target == 0 else -1)
                    actual = op.values(node, reaches, target, prefix)
                    for a, b in zip(actual, expected):
                        self.assertAlmostEqual(a, b, delta=1e-14)


if __name__ == '__main__':
    unittest.main()



class IndependentSelectedPolicyTests(unittest.TestCase):
    def test_whole_game_serialized_policy_replay_with_short_all_in(self):
        from pokerlab.preflop_tree import PreflopConfig
        from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions
        from pokerlab.selected_operator_solver import solve_four_street_operator
        from scripts.preflop_validation import replay_policy, compare_result

        config = {'starting_stack': [1.0, 2.0], 'raise_sizes': [],
                  'max_raises': 0, 'include_all_in': True}
        actions = {'bet_sizes': [0.5], 'raise_sizes': [], 'max_raises': 0,
                   'include_all_in': False}
        request = FourStreetSolveRequest(
            SB, BB, RUNOUTS, preflop_config=PreflopConfig.from_dict(config),
            flop_actions=PostflopActions(**actions), iterations=10,
            algorithm='cfrplus', traversal='public-batched',
            diagnostics='public-batched', resource_model='public-vector')
        result = solve_four_street_operator(request)
        oracle = replay_policy(result, SB, BB, config=config, runouts=RUNOUTS,
                               flop_config=actions)
        compare_result(result, oracle, tolerance=1e-10)

    def test_four_street_weighted_raised_policy_replays(self):
        from pokerlab.preflop_tree import PreflopConfig
        from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions
        from pokerlab.selected_operator_solver import solve_four_street_operator
        from scripts.preflop_validation import replay_policy, compare_result

        config = {'starting_stack': [3, 2.5], 'raise_sizes': [0.5],
                  'max_raises': 1, 'include_all_in': False}
        actions = {'bet_sizes': [0.5], 'raise_sizes': [], 'max_raises': 0,
                   'include_all_in': False}
        selected = RUNOUTS[:2]
        request = FourStreetSolveRequest(
            SB, BB, selected, preflop_config=PreflopConfig.from_dict(config),
            flop_actions=PostflopActions(**actions), iterations=10,
            algorithm='vanilla', traversal='public-batched',
            diagnostics='public-batched', resource_model='public-vector')
        result = solve_four_street_operator(request)
        oracle = replay_policy(result, SB, BB, config=config, runouts=selected,
                               flop_config=actions)
        compare_result(result, oracle, tolerance=1e-10)
        self.assertEqual({row['street'] for row in result['strategy']},
                         {'preflop', 'flop', 'turn', 'river'})


if __name__ == '__main__':
    unittest.main()

