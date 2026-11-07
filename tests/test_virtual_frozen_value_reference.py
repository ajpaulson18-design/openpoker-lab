from fractions import Fraction
import unittest
from unittest.mock import patch

from tests.virtual_frozen_update_reference import (
    _template_case, build_frozen_update_census, frozen_profile_probabilities,
    scaled_proof9_ranges,
)
from tests import virtual_frozen_value_reference as expected
from tests.virtual_frozen_value_reference import (
    _profile_exponents, _runout_stream, compute_expected_update_reference,
    prepare_expected_update_reference,
)


class ExpectedUpdateAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admission = prepare_expected_update_reference()

    def test_preflight_is_bound_to_the_accepted_physical_and_literal_census(self):
        receipt = self.admission.receipt()
        self.assertEqual(receipt["worlds_streamed"], 60)
        self.assertEqual(receipt["world_node_visits_upper"], 66_300)
        self.assertEqual(receipt["unique_rows_upper"], 24_420)
        self.assertEqual(receipt["unique_action_slots_upper"], 58_164)
        self.assertEqual(receipt["unique_history_tokens_upper"], 249_662)
        self.assertEqual(receipt["unique_history_bytes_upper"], 1_500_675)
        self.assertEqual(receipt["fraction_cells_upper"], 140_748)
        self.assertEqual(self.admission.normalizer, Fraction(29, 64))
        self.assertLessEqual(receipt["output_text_bytes_upper"],
                             receipt["output_text_bytes_limit"])
        self.assertGreater(receipt["unique_action_token_bytes_upper"], 0)
        self.assertLessEqual(receipt["runtime_work_upper"] +
                             receipt["card_free_rule_setup"]["work"],
                             receipt["limits"]["work"])
        self.assertLessEqual(receipt["retained_entries_upper"] +
                             receipt["card_free_rule_setup"]["entries"],
                             receipt["limits"]["entries"])
        self.assertLessEqual(receipt["created_fraction_bits_upper"] +
                             receipt["card_free_rule_setup"]["created_bits"],
                             receipt["limits"]["created_bits"])

    def test_stream_contains_exactly_sixty_normalized_physical_worlds_without_table(self):
        ranges = scaled_proof9_ranges()
        worlds = _runout_stream(ranges)
        seen = 0
        total = Fraction(0)
        for hand0, weight0, hand1, weight1, board in worlds:
            self.assertTrue(set(hand0).isdisjoint(hand1))
            self.assertTrue(set((*hand0, *hand1)).isdisjoint(board))
            self.assertEqual(len(set(board)), 5)
            total += weight0 * weight1 / self.admission.normalizer / 20
            seen += 1
        self.assertEqual((seen, total), (60, Fraction(1)))

        pair_mass = {}
        for hand0, weight0, hand1, weight1, _board in _runout_stream(ranges):
            key = hand0, hand1
            pair_mass[key] = pair_mass.get(key, Fraction(0)) + (
                weight0 * weight1 / self.admission.normalizer / 20)
        self.assertEqual(tuple(pair_mass.values()),
                         (Fraction(3, 29), Fraction(8, 29), Fraction(18, 29)))

    def test_local_selector_matches_the_pinned_census_selector(self):
        template = self.admission.template
        checked = 0
        for node in template.nodes:
            if node.phase != "decision":
                continue
            actions = tuple(edge.token for edge in node.edges)
            history = ("check", "flop@2c3c4d")[:len(template.histories[0])]
            for actor, hand in ((0, (32, 43)), (1, (16, 24))):
                local = _profile_exponents(actor, hand, history, actions)
                independent = frozen_profile_probabilities(actor, hand, history, actions)
                converted = tuple(Fraction(0) if exponent < 0 else
                                  Fraction(1, 1 << exponent) for exponent in local)
                self.assertEqual(converted, independent)
                checked += 1
                if checked >= 24:
                    return
        self.fail("template did not contain enough decision menus")

    def test_reduce_only_failure_precedes_rank_or_result_row_creation(self):
        with patch.object(expected, "independent_rank",
                          side_effect=AssertionError("rank entered before admission")):
            with self.assertRaisesRegex(ValueError, "entry limit"):
                prepare_expected_update_reference({"entries": 1})
            with self.assertRaisesRegex(ValueError, "output text byte limit"):
                prepare_expected_update_reference({"output_text_bytes": 1})


class ExpectedUpdateOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = compute_expected_update_reference()

    def test_exact_joint_world_reference_visits_every_full_history(self):
        receipt = self.result.receipt
        self.assertEqual(receipt["worlds_streamed"], 60)
        self.assertEqual(receipt["literal_node_visits"], 66_300)
        self.assertEqual(receipt["independent_rank_calls"], 120)
        self.assertEqual(receipt["unique_full_history_rows"], 24_420)
        self.assertEqual(receipt["unique_action_slots"], 58_164)
        self.assertEqual(receipt["q_terms"], 0)
        self.assertEqual(receipt["sampling_or_training_calls"], 0)
        self.assertLessEqual(receipt["runtime_budget"]["work"],
                             receipt["admission"]["runtime_work_upper"])
        self.assertLessEqual(receipt["runtime_budget"]["entries"],
                             receipt["admission"]["retained_entries_upper"])
        self.assertLessEqual(receipt["runtime_budget"]["created_bits"],
                             receipt["admission"]["created_fraction_bits_upper"])

    def test_rows_keep_zero_reach_counterfactual_regrets_and_exact_average_mass(self):
        saw_zero_reach_nonzero_regret = False
        for key, row in self.result.rows.items():
            self.assertEqual(key, (row.actor, row.hand_ids, row.history))
            self.assertEqual(len(row.actions), len(row.regret_masses))
            self.assertEqual(len(row.actions), len(row.average_action_masses))
            self.assertEqual(len(row.actions), len(row.action_exponents))
            self.assertEqual(sum(row.average_action_masses, Fraction(0)),
                             row.average_reach_mass)
            weighted = sum((Fraction(0) if exponent < 0 else
                            Fraction(1, 1 << exponent) * regret
                            for exponent, regret in zip(row.action_exponents,
                                                        row.regret_masses)), Fraction(0))
            self.assertEqual(weighted, 0)
            if row.average_reach_mass == 0 and any(row.regret_masses):
                saw_zero_reach_nonzero_regret = True
        self.assertTrue(saw_zero_reach_nonzero_regret)

    def test_full_history_rows_are_not_merged_by_template_node_or_hash(self):
        histories_by_hand = {}
        for actor, hand, history in self.result.rows:
            histories_by_hand.setdefault((actor, hand), set()).add(history)
        self.assertTrue(any(len(histories) > 1 for histories in histories_by_hand.values()))
        self.assertEqual(len(self.result.rows), 24_420)
        # Every stored history is the complete ordered public/action token path.
        self.assertTrue(all(type(history) is tuple and
                            all(type(token) is str and token for token in history)
                            for _actor, _hand, history in self.result.rows))


if __name__ == "__main__":
    unittest.main()
