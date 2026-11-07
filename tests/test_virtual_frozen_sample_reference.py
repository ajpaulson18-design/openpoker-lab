from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
import unittest
from unittest.mock import patch

from tests.full_deck_public_chance_reference import PROOF9, card_name
from scripts.preflop_validation import independent_rank
from tests import virtual_frozen_sample_reference as sampled
from tests.virtual_frozen_sample_reference import (
    admit_sampled_board, build_sampled_reference_context,
    compute_sampled_update_reference,
)


def _rank_sign(context, board, pair):
    i, j = pair
    hand0 = context.ranges[0][i][0]
    hand1 = context.ranges[1][j][0]
    rank0 = independent_rank(tuple(card_name(card) for card in (*hand0, *board)))
    rank1 = independent_rank(tuple(card_name(card) for card in (*hand1, *board)))
    return (rank0 > rank1) - (rank0 < rank1)


class SampledReferenceContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = build_sampled_reference_context()
        cls.samples = {}
        cls.zero_board = None
        for board in cls.context.physical.proposals:
            pairs = []
            for i, (hand0, _w0) in enumerate(cls.context.ranges[0]):
                if set(hand0).intersection(board):
                    continue
                for j, (hand1, _w1) in enumerate(cls.context.ranges[1]):
                    if set(hand1).intersection(board) or not set(hand0).isdisjoint(hand1):
                        continue
                    pairs.append((i, j))
            if (not pairs and cls.zero_board is None and any(
                    cls.context.physical.mass(board[:4], player, hand_index) > 0
                    for player, side in enumerate(cls.context.ranges)
                    for hand_index in range(len(side)))):
                cls.zero_board = board
            for pair in pairs:
                sign = _rank_sign(cls.context, board, pair)
                cls.samples.setdefault(sign, board)
            if len(cls.samples) == 3 and cls.zero_board is not None:
                break

    def test_context_has_immutable_card_free_and_physical_inputs(self):
        receipt = self.context.receipt()
        self.assertEqual(receipt["template_nodes"], 388)
        self.assertEqual(receipt["template_edges"], 410)
        self.assertEqual(receipt["physical_prefix_count"], 3109)
        self.assertEqual(receipt["physical_proposal_count"], 2520)
        self.assertEqual(self.context.normalizer, Fraction(29, 64))
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            self.context.nodes[0].phase = "showdown"
        with self.assertRaises(TypeError):
            self.context.prefix_walk_stats[0] = {}

    def test_one_board_exact_regret_estimator_covers_win_tie_and_loss(self):
        self.assertEqual(set(self.samples), {-1, 0, 1})
        for sign, board in self.samples.items():
            admission = admit_sampled_board(self.context, board, "uniform")
            result = compute_sampled_update_reference(admission)
            self.assertEqual(result.receipt["rank_outcomes"][{1: "sb_win", 0: "tie", -1: "sb_loss"}[sign]],
                             sum(_rank_sign(self.context, board, pair) == sign
                                 for pair in admission.compatible_pairs))
            self.assertEqual(result.receipt["independent_rank_calls"],
                             2 * len(admission.compatible_pairs))
            self.assertEqual(result.receipt["rows"], admission.row_count_upper)
            self.assertEqual(result.receipt["action_slots"], admission.action_slots_upper)
            self.assertLessEqual(result.receipt["rows"], sampled.MAX_PER_BOARD_ROWS)
            self.assertLessEqual(result.receipt["action_slots"],
                                 sampled.MAX_PER_BOARD_ACTION_SLOTS)
            for row in result.rows.values():
                self.assertEqual(len(row.actions), len(row.regret_masses))
                self.assertEqual(len(row.actions), len(row.average_action_masses))
                self.assertEqual(sum(row.average_action_masses, Fraction(0)),
                                 row.average_mass)
                self.assertLessEqual(row.average_prefix_visits, 1)

    def test_zero_target_board_keeps_prefix_averages_but_has_no_regret_worlds(self):
        self.assertIsNotNone(self.zero_board)
        admission = admit_sampled_board(self.context, self.zero_board, "uniform")
        self.assertEqual(len(admission.compatible_pairs), 0)
        result = compute_sampled_update_reference(admission)
        self.assertEqual(result.receipt["compatible_worlds"], 0)
        self.assertEqual(result.receipt["independent_rank_calls"], 0)
        self.assertGreater(result.receipt["zero_regret_average_only_rows"], 0)
        self.assertTrue(all(not any(row.regret_masses) for row in result.rows.values()))
        self.assertTrue(any(any(token.startswith("flop@") for token in row.history) and
                            not any(token.startswith("turn@") for token in row.history) and
                            row.average_mass > 0 for row in result.rows.values()))
        self.assertTrue(any(any(token.startswith("turn@") for token in row.history) and
                            not any(token.startswith("river@") for token in row.history) and
                            row.average_mass > 0 for row in result.rows.values()))
        self.assertTrue(all(row.average_mass == 0 or
                            not any(token.startswith("river@") for token in row.history)
                            for row in result.rows.values()))

    def test_uniform_and_river_weighted_estimators_rescale_by_exact_q(self):
        board = self.samples[1]
        uniform = compute_sampled_update_reference(
            admit_sampled_board(self.context, board, "uniform"))
        weighted = compute_sampled_update_reference(
            admit_sampled_board(self.context, board, "river_weighted"))
        self.assertEqual(set(uniform.rows), set(weighted.rows))
        qbu = uniform.admission.board_probability
        qbw = weighted.admission.board_probability
        for key, row in uniform.rows.items():
            other = weighted.rows[key]
            self.assertEqual(row.action_exponents, other.action_exponents)
            self.assertEqual(tuple(value * qbu for value in row.regret_masses),
                             tuple(value * qbw for value in other.regret_masses))
            history = row.history
            length = (5 if any(token.startswith("river@") for token in history) else
                      4 if any(token.startswith("turn@") for token in history) else
                      3 if any(token.startswith("flop@") for token in history) else 0)
            qpu = uniform.admission.prefix_probabilities[length]
            qpw = weighted.admission.prefix_probabilities[length]
            self.assertEqual(row.average_mass * qpu, other.average_mass * qpw)
            self.assertEqual(tuple(value * qpu for value in row.average_action_masses),
                             tuple(value * qpw for value in other.average_action_masses))

    def test_earlier_prefix_averages_do_not_leak_future_turn_or_river(self):
        first = None
        second = None
        seen = {}
        for board in self.context.physical.proposals:
            flop = board[:3]
            if flop not in seen:
                seen[flop] = board
            elif first is None:
                first, second = seen[flop], board
                break
        self.assertIsNotNone(first)
        a = compute_sampled_update_reference(admit_sampled_board(self.context, first, "uniform"))
        b = compute_sampled_update_reference(admit_sampled_board(self.context, second, "uniform"))
        earlier_a = {key: row for key, row in a.rows.items()
                     if row.average_prefix_visits and
                     not any(token.startswith("turn@") for token in row.history)}
        earlier_b = {key: row for key, row in b.rows.items()
                     if row.average_prefix_visits and
                     not any(token.startswith("turn@") for token in row.history)}
        self.assertEqual(set(earlier_a), set(earlier_b))
        for key, row in earlier_a.items():
            self.assertEqual(row.average_mass, earlier_b[key].average_mass)
            self.assertEqual(row.average_action_masses, earlier_b[key].average_action_masses)

    def test_board_admission_rejects_bad_board_and_tiny_work_before_rank_calls(self):
        board = self.samples[1]
        with self.assertRaises(ValueError):
            admit_sampled_board(self.context, list(board), "uniform")
        with self.assertRaisesRegex(ValueError, "work limit"):
            admit_sampled_board(self.context, board, "uniform", {"work": 1})
        admission = admit_sampled_board(self.context, board, "uniform")
        forged = replace(admission, context=build_sampled_reference_context())
        with patch.object(sampled, "independent_rank",
                          side_effect=AssertionError("forged admission reached rank")):
            with self.assertRaisesRegex(ValueError, "seal mismatch"):
                compute_sampled_update_reference(forged)


if __name__ == "__main__":
    unittest.main()
