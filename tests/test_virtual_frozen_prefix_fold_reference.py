from fractions import Fraction
import unittest

from scripts.matrix_free_certificate_budget import Budget, DEFAULT_LIMITS
from tests.virtual_frozen_sample_reference import (
    _prefix_fold_terminal_values,
    admit_sampled_board,
    build_sampled_reference_context,
    compute_sampled_update_reference,
)


class PrefixFoldReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = build_sampled_reference_context()

    def test_folded_terminal_uses_visible_prefix_only_for_both_seats(self):
        context = self.context
        boards_by_flop = {}
        first, second = None, None
        for board in context.physical.proposals:
            if board[:3] in boards_by_flop:
                first, second = boards_by_flop[board[:3]], board
                if first[3:] != second[3:]:
                    break
            else:
                boards_by_flop[board[:3]] = board
        self.assertIsNotNone(first)
        self.assertNotEqual(first[3:], second[3:])
        prefix = first[:3]
        node = next(n for n in context.nodes if n.phase == "fold" and n.street == 3)
        powers = tuple(Fraction(1, 1 << exponent) for exponent in range(65))

        for target in (0, 1):
            reaches = tuple(0 if i % 2 == 0 else 1
                            for i in range(len(context.ranges[1-target])))
            values_a = _prefix_fold_terminal_values(
                context, target, node, first[:3], reaches, Budget(DEFAULT_LIMITS), powers)
            values_b = _prefix_fold_terminal_values(
                context, target, node, second[:3], reaches, Budget(DEFAULT_LIMITS), powers)
            self.assertEqual(values_a, values_b)

            q_prefix = context.physical.proposal_laws["uniform"]["prefix"][prefix]
            suffix_count = 2
            payoff = Fraction(node.matched) * (1 if node.winner == target else -1)
            for own_index, (own_hand, own_weight) in enumerate(context.ranges[target]):
                expected = Fraction(0)
                if not set(own_hand).intersection(prefix):
                    for opponent_index, (opponent_hand, opponent_weight) in enumerate(
                            context.ranges[1-target]):
                        if (set(opponent_hand).intersection(prefix) or
                                not set(own_hand).isdisjoint(opponent_hand)):
                            continue
                        reach = powers[reaches[opponent_index]]
                        expected += (own_weight * opponent_weight * suffix_count /
                                     (context.normalizer * 20) * reach)
                    expected = expected * payoff / q_prefix
                self.assertEqual(values_a[own_index], expected)

    def test_zero_full_board_support_keeps_prefix_fold_regrets_and_averages(self):
        context = self.context
        board = None
        for candidate in context.physical.proposals:
            compatible = any(
                not set(hand0).intersection(candidate) and
                not set(hand1).intersection(candidate) and
                set(hand0).isdisjoint(hand1)
                for hand0, _weight0 in context.ranges[0]
                for hand1, _weight1 in context.ranges[1])
            prefix_supported = any(
                context.physical.mass(candidate[:4], player, index) > 0
                for player, side in enumerate(context.ranges)
                for index in range(len(side)))
            if not compatible and prefix_supported:
                board = candidate
                break
        self.assertIsNotNone(board)
        admission = admit_sampled_board(context, board, "uniform", prefix_folds=True)
        ordinary = compute_sampled_update_reference(admission)
        folded = compute_sampled_update_reference(admission, prefix_folds=True)
        self.assertEqual(len(admission.compatible_pairs), 0)
        self.assertEqual(folded.receipt["proposal_law"], "uniform")
        self.assertTrue(folded.receipt["q_corrected_prefix_fold_regret"])
        self.assertEqual(set(folded.rows), set(ordinary.rows))
        projection = folded.receipt["prefix_fold_projection"]
        self.assertLessEqual(projection["actual_runtime_work"], projection["combined_work_upper"])
        self.assertLessEqual(projection["actual_runtime_entries"], projection["combined_entries_upper"])
        self.assertLessEqual(projection["actual_created_bits"],
                             projection["combined_created_bits_upper"])
        self.assertLessEqual(projection["actual_max_integer_bits"],
                             projection["combined_max_integer_bits_upper"])

        for key, row in folded.rows.items():
            baseline = ordinary.rows[key]
            self.assertEqual(row.action_exponents, baseline.action_exponents)
            self.assertEqual(row.average_mass, baseline.average_mass)
            self.assertEqual(row.average_action_masses, baseline.average_action_masses)
            self.assertEqual(len(row.prefix_fold_regret_masses), len(row.actions))
        for actor in (0, 1):
            self.assertTrue(any(
                row.actor == actor and row.regret_world_visits == 0 and
                any(row.prefix_fold_regret_masses)
                for row in folded.rows.values()))

    def test_prefix_fold_mode_rejects_river_weighted_proposals(self):
        board = self.context.physical.proposals[0]
        with self.assertRaisesRegex(ValueError, "uniform proposal law"):
            admit_sampled_board(self.context, board, "river_weighted", prefix_folds=True)

    def test_fold_projection_rejects_reduced_work_before_computation(self):
        board = self.context.physical.proposals[0]
        with self.assertRaisesRegex(ValueError, "work limit"):
            admit_sampled_board(self.context, board, "uniform", {"work": 1},
                                prefix_folds=True)

    def test_fold_receipt_projects_all_added_work_and_scratch(self):
        board = next(board for board in self.context.physical.proposals
                     if admit_sampled_board(self.context, board, "uniform").compatible_pairs)
        admission = admit_sampled_board(self.context, board, "uniform", prefix_folds=True)
        envelope = admission.receipt()
        exact_entries = (self.context.setup_receipt["entries"] +
                         envelope["combined_entries_upper"])
        self.assertLessEqual(exact_entries, DEFAULT_LIMITS["entries"])
        admit_sampled_board(self.context, board, "uniform",
                            {"entries": exact_entries}, prefix_folds=True)
        with self.assertRaisesRegex(ValueError, "entry limit"):
            admit_sampled_board(self.context, board, "uniform",
                                {"entries": exact_entries - 1}, prefix_folds=True)
        result = compute_sampled_update_reference(admission, prefix_folds=True)
        projection = result.receipt["prefix_fold_projection"]
        self.assertTrue(projection["admitted"])
        self.assertLessEqual(projection["actual_node_visits"], projection["node_visits_upper"])
        self.assertLessEqual(projection["actual_action_edge_visits"],
                             projection["action_edges_upper"])
        self.assertLessEqual(projection["actual_runtime_work"], projection["combined_work_upper"])
        self.assertLessEqual(projection["actual_runtime_entries"],
                             projection["combined_entries_upper"])
        self.assertLessEqual(projection["actual_created_bits"],
                             projection["combined_created_bits_upper"])
        self.assertLessEqual(projection["actual_max_integer_bits"],
                             projection["combined_max_integer_bits_upper"])


if __name__ == "__main__":
    unittest.main()
