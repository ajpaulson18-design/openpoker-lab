"""Bounded real training against physical replay and original-weight tail flows."""
from fractions import Fraction as F
import inspect
import unittest
from unittest.mock import patch

from pokerlab import postflop_solver
from pokerlab import turn_class_tail_adapter as adapter
from pokerlab.turn_tail_adapter import solve_turn_tail
from scripts import turn_river_validation as rules
from scripts import turn_three_hand_classes as independent


def row_index(result):
    return {(r['player'], r['hand'], tuple(r['history'])): r for r in result['strategy']}


def normalized(row):
    values = tuple(F.from_float(a['probability']) for a in row['actions'])
    total = sum(values, F(0))
    if total <= 0:
        raise AssertionError('Empty saved policy row')
    return {a['history_key']: v / total for a, v in zip(row['actions'], values)}


def own_action_flows(result, worlds):
    rows = row_index(result)
    output = {}
    for (player, hand, history), row in rows.items():
        reach = F(1)
        prefix = []
        for token in history:
            prior = rows.get((player, hand, tuple(prefix)))
            if prior is not None:
                reach *= normalized(prior)[token]
            prefix.append(token)
        river = [token[6:] for token in history if token.startswith('river@')]
        marginal = sum((w['weight'] for w in worlds
                        if ''.join(w['hands'][0 if player == 'oop' else 1]) == hand
                        and (not river or w['river'] == river[0])), F(0))
        if marginal <= 0:
            raise AssertionError('Physically impossible own-hand row')
        for token, probability in normalized(row).items():
            output[player, hand, history, token] = (reach * probability,
                                                   marginal * reach * probability)
    return output


class TurnClassTailAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = independent.build_model()
        cls.results = []
        for discard in (0, 3):
            rank_inputs = []
            rank = postflop_solver.rank_hand

            def observed_rank(cards):
                rank_inputs.append(tuple(cards))
                return rank(cards)

            with patch.object(postflop_solver, 'rank_hand', side_effect=observed_rank):
                candidate = adapter.solve_turn_class_tail(
                    iterations=10, discard=discard, resource_model=adapter.budget.RESOURCE_MODEL)
            physical = solve_turn_tail(adapter.BOARD, adapter.OOP_RANGE, adapter.IP_RANGE,
                                       adapter.CONFIG, river_config=adapter.CONFIG,
                                       iterations=10, discard=discard)
            numeric = rules.replay_policy(candidate, adapter.OOP_RANGE, adapter.IP_RANGE,
                                          board=adapter.BOARD, config=adapter.CONFIG,
                                          river_config=adapter.CONFIG)
            differences = rules.compare_result(candidate, numeric, tolerance=1e-9)
            audit = independent.audit_policy(candidate, cls.model)
            cls.results.append((discard, candidate, physical, rank_inputs, differences, audit))

    def test_actual_full_deck_metadata_and_observed_ranking(self):
        for discard, candidate, _, rank_inputs, _, _ in self.results:
            self.assertEqual(candidate['runout_mode'], 'full-deck')
            self.assertEqual(len(candidate['runouts']), 48)
            self.assertEqual(len(set(candidate['runouts'])), 48)
            self.assertEqual(candidate['worlds'], 396)
            self.assertEqual(candidate['compatible_pairs'], 9)
            self.assertEqual(candidate['info_sets'], 3606)
            self.assertEqual(candidate['training_representation']['worlds'], 45)
            self.assertEqual(candidate['training_representation']['river_classes'], 7)
            self.assertEqual(candidate['average_weight_sum'], 55 - discard * (discard + 1) // 2)
            self.assertEqual(candidate['requested_regret_passes'], 20)
            self.assertEqual(candidate['averaged_sweeps'], 10 - discard)
            self.assertEqual(len(rank_inputs), 276)
            self.assertEqual(len(set(rank_inputs)), 276)
            self.assertEqual(candidate['modeled_rank_inputs'], len(rank_inputs))

    def test_all_physical_actions_and_own_realization_weights_match_reference(self):
        for _, candidate, physical, _, _, _ in self.results:
            left, right = row_index(candidate), row_index(physical)
            self.assertEqual(set(left), set(right))
            self.assertEqual(len(left), 3606)
            slots = 0
            for key, row in left.items():
                other = right[key]
                self.assertEqual(row['board'], other['board'])
                self.assertEqual(row['street'], other['street'])
                self.assertEqual(len(row['actions']), len(other['actions']))
                for a, b in zip(row['actions'], other['actions']):
                    self.assertEqual({k: v for k, v in a.items() if k != 'probability'},
                                     {k: v for k, v in b.items() if k != 'probability'})
                    self.assertLessEqual(abs(a['probability'] - b['probability']), 1e-9)
                    slots += 1
            self.assertEqual(slots, 8046)
            a = own_action_flows(candidate, self.model.physical[3])
            b = own_action_flows(physical, self.model.physical[3])
            self.assertEqual(set(a), set(b))
            for key in a:
                self.assertLessEqual(abs(a[key][0] - b[key][0]), F(1, 10**9))
                self.assertLessEqual(abs(a[key][1] - b[key][1]), F(1, 10**9))

    def test_independent_physical_and_both_exact_class_audits_agree(self):
        for _, _, _, _, differences, audit in self.results:
            self.assertLessEqual(max(map(abs, differences.values())), 1e-9)
            exact = audit['full_physical_exact_metrics']
            for mode in ('scan', 'partition'):
                self.assertEqual(exact, audit['generic_class_audits'][mode]['metrics'])
            self.assertEqual(audit['physical_oracle_counters']['policy_rows'], 3606)
            self.assertEqual(audit['physical_oracle_counters']['policy_action_slots'], 8046)
            self.assertEqual(audit['training_calls'], 0)

    def test_old_physical_admission_still_rejects_790_before_training(self):
        with patch('pokerlab.turn_tail_adapter._train_original_weight_tail',
                   side_effect=AssertionError('Old over-cap request trained')) as trainer:
            with self.assertRaisesRegex(ValueError, '30 million'):
                solve_turn_tail(adapter.BOARD, adapter.OOP_RANGE, adapter.IP_RANGE,
                                adapter.CONFIG, river_config=adapter.CONFIG,
                                iterations=790, discard=100)
        trainer.assert_not_called()
        plan = adapter.budget.plan_request(790, 100)
        self.assertFalse(plan['legacy_proxy_enforced'])
        self.assertGreater(plan['legacy_physical_world_proxy'], 30_000_000)

    def test_fixture_is_not_a_silent_general_range_or_configuration_api(self):
        signature = inspect.signature(adapter.solve_turn_class_tail)
        self.assertEqual(set(signature.parameters), {'iterations', 'discard', 'resource_model'})
        for parameter in signature.parameters.values():
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertEqual(parameter.default, inspect.Parameter.empty)
        with self.assertRaises(TypeError):
            adapter.solve_turn_class_tail(iterations=10, discard=0,
                                          resource_model=adapter.budget.RESOURCE_MODEL,
                                          board='2c7d9hJs')


if __name__ == '__main__':
    unittest.main()
