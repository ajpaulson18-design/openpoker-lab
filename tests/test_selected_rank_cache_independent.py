"""Independent physical and visible-information controls for rank-cache variants."""
import unittest
from unittest.mock import patch

from pokerlab.river_tree import _Terminal
from pokerlab.selected_runout_operator import SelectedRunoutOperator
from pokerlab.selected_operator_solver import solve_four_street_operator
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions
from scripts.preflop_validation import replay_policy, compare_result
from tests.test_selected_operator_independent import SB, BB, RUNOUTS, physical_rows


class RankCacheIndependentTests(unittest.TestCase):
    def test_weighted_physical_vectors_and_forced_eviction(self):
        baseline = SelectedRunoutOperator(SB, BB, RUNOUTS, rank_cache_boards=1)
        physical = physical_rows(baseline)
        prefixes = {()}
        for *_, prefix in physical:
            prefixes.update(prefix[:k] for k in range(1, 4))
        # Revisit earlier boards after traversing more than the two-board capacity.
        order = sorted(prefixes, key=lambda x: (len(x), x))
        for capacity in (2, 64):
            candidate = SelectedRunoutOperator(SB, BB, RUNOUTS, rank_cache_boards=capacity)
            baseline.pot = candidate.pot = 1.0
            for prefix in order + list(reversed(order)) + order:
                expected_edges = list(baseline.iter_edges(prefix, signed=True))
                self.assertEqual(list(candidate.iter_edges(prefix, signed=True)), expected_edges)
                for node in (_Terminal('showdown', (0.5, 2)),
                             _Terminal('fold', (1, 2), 1)):
                    for player in (0, 1):
                        reach = ([0.2, 0.9], [0.75, 0.1])[1-player]
                        self.assertEqual(candidate.values(node, reach, player, prefix),
                                         baseline.values(node, reach, player, prefix))
                expected = [row for row in physical if row[4][:len(prefix)] == prefix]
                for i, j, mass, signed in expected_edges:
                    pairs = [r for r in expected if r[:2] == (i, j)]
                    self.assertAlmostEqual(mass, sum(r[2] for r in pairs), delta=1e-14)
                    self.assertAlmostEqual(signed, sum(r[2]*r[3] for r in pairs), delta=1e-14)

    def test_visible_information_policy_replay(self):
        actions = {'bet_sizes': [0.5], 'raise_sizes': [], 'max_raises': 0,
                   'include_all_in': False}
        for config in ({'starting_stack': [1, 2], 'raise_sizes': [],
                        'max_raises': 0, 'include_all_in': True},
                       {'starting_stack': [3, 2.5], 'raise_sizes': [0.5],
                        'max_raises': 1, 'include_all_in': False}):
            req = FourStreetSolveRequest(
                SB, BB, RUNOUTS, preflop_config=PreflopConfig.from_dict(config),
                flop_actions=PostflopActions(**actions), iterations=10,
                algorithm='cfrplus', traversal='public-batched',
                diagnostics='public-batched', resource_model='public-vector')
            baseline = solve_four_street_operator(req, rank_cache_boards=1)
            for capacity in (2, 64):
                result = solve_four_street_operator(req, rank_cache_boards=capacity)
                self.assertEqual(result['strategy'], baseline['strategy'])
                for field in ('value_sb', 'value_bb', 'sb_best_response_value',
                              'bb_best_response_value', 'nash_conv'):
                    self.assertEqual(result[field], baseline[field])
                oracle = replay_policy(result, SB, BB, config=config, runouts=RUNOUTS,
                                       flop_config=actions)
                compare_result(result, oracle, tolerance=1e-10)

    def test_exact_rational_all_in_policy_replay(self):
        from scripts.four_street_certificate_v3 import evaluate_exact
        config = {'small_blind': 0.5, 'big_blind': 1.0,
                  'starting_stack': [1, 2], 'raise_sizes': [],
                  'max_raises': 0, 'include_all_in': True}
        actions = {'bet_sizes': [0.5], 'raise_sizes': [], 'max_raises': 0,
                   'include_all_in': False}
        case = {'id': 'cache-independent-short-stack', 'sb_range': SB,
                'bb_range': BB, 'runouts': list(RUNOUTS), 'config': config,
                'flop_config': actions, 'turn_config': actions,
                'river_config': actions}
        req = FourStreetSolveRequest(
            SB, BB, RUNOUTS, preflop_config=PreflopConfig.from_dict(config),
            flop_actions=PostflopActions(**actions), iterations=10,
            algorithm='cfrplus', traversal='public-batched',
            diagnostics='public-batched', resource_model='public-vector')
        baseline = solve_four_street_operator(req, rank_cache_boards=1)
        cached = solve_four_street_operator(req, rank_cache_boards=2)
        self.assertEqual(baseline['strategy'], cached['strategy'])
        a = evaluate_exact(case, baseline)
        b = evaluate_exact(case, cached)
        self.assertEqual(a['metrics'], b['metrics'])
        self.assertEqual(a['threshold_met'], b['threshold_met'])


if __name__ == '__main__':
    unittest.main()
