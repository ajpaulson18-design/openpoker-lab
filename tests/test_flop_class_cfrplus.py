"""Fast contract tests for the bounded fixed-flop class CFR+ adapter."""
from fractions import Fraction
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pokerlab import cfr_plus
from scripts import flop_class_cfrplus as adapter
from scripts import flop_public_classes as proof


def _decision(player, history, children):
    return proof.physical._Decision(history, player, "flop", ("2c", "3d", "4h"),
                                    ({"name": "a"}, {"name": "b"}), children)


def _world(mass, sign, river):
    return ("AsAd", "KsKd", mass, sign, ("2c", "3d", "4h", "5c", river))


class FlopClassCFRPlusTests(unittest.TestCase):
    def test_invalid_full_requests_reject_before_sources_proof_tree_or_training(self):
        bad = (True, False, 0, -1, 141, 1.0, "1", None)
        with patch.object(adapter, "_source_hashes", side_effect=AssertionError("source")) as source, \
             patch.object(adapter.publication, "verify", side_effect=AssertionError("proof")) as receipt, \
             patch.object(adapter.proof, "build_model", side_effect=AssertionError("tree")) as build, \
             patch.object(adapter.cfr_plus, "train", side_effect=AssertionError("trainer")) as train:
            for value in bad:
                with self.subTest(iterations=value), self.assertRaises(ValueError):
                    adapter.solve_fixed(value)
        source.assert_not_called()
        receipt.assert_not_called()
        build.assert_not_called()
        train.assert_not_called()

    def test_exact_140_iteration_admission_counts(self):
        admission = adapter.admit_request(140)
        self.assertEqual(admission["training_passes"], 420)
        self.assertEqual(admission["retained_physical_world_iterations"], 2_494_800)
        self.assertEqual(admission["retained_physical_decision_world_iterations"], 29_937_600)
        self.assertEqual(admission["compact_world_iterations"], 52_920)
        self.assertEqual(admission["compact_state_visit_upper_bound"], 3_386_880)
        self.assertLessEqual(admission["retained_physical_decision_world_iterations"],
                             adapter.MAX_DECISION_WORLD_ITERATIONS)

    def test_node_key_hides_opponent_hand_and_future_board_but_keeps_own_hand(self):
        node = SimpleNamespace(player=0, history=("bet@2",))
        first = ("AsAd", "KsKd", 0.5, 1, ("2c", "3d", "4h", "5c", "6c"))
        second = ("AsAd", "QsQd", 0.5, -1, ("2c", "3d", "4h", "5d", "6d"))
        self.assertEqual(adapter._node_key(node, first), adapter._node_key(node, second))
        changed_own_hand = ("AhAc", "QsQd", 0.5, -1, second[4])
        self.assertNotEqual(adapter._node_key(node, first),
                            adapter._node_key(node, changed_own_hand))

    def test_chance_callback_routes_by_revealed_class_label(self):
        left, right = object(), object()
        chance = proof.physical._Chance(("bet",), 4, "river", {"6c": left, "6d": right})
        self.assertIs(adapter._chance_child(chance, _world(0.5, 1, "6c")), left)
        self.assertIs(adapter._chance_child(chance, _world(0.5, -1, "6d")), right)
        self.assertIsNone(adapter._chance_child(SimpleNamespace(branches={}), _world(1.0, 1, "6c")))

    def test_terminal_value_uses_matched_contribution_and_fold_winner(self):
        unequal = (Fraction(3), Fraction(8))
        fold0 = proof.physical._Terminal(("fold",), "fold", unequal, winner=0)
        fold1 = proof.physical._Terminal(("fold",), "fold", unequal, winner=1)
        showdown = proof.physical._Terminal(("call",), "showdown", unequal)
        self.assertEqual(adapter._terminal_value(fold0, _world(1.0, -1, "6c")), 8.0)
        self.assertEqual(adapter._terminal_value(fold1, _world(1.0, 1, "6c")), -8.0)
        # The unmatched five is refunded; only the matched contribution enters the pot.
        self.assertEqual(adapter._terminal_value(showdown, _world(1.0, 1, "6c")), 8.0)
        self.assertEqual(adapter._terminal_value(showdown, _world(1.0, -1, "6c")), -8.0)

    def test_hand_computed_weighted_hidden_world_tree_trains_alternating_policy(self):
        # The two worlds share both visible decision keys; only hidden river and
        # showdown sign differ. The root's weighted action means are 3 and 2.5,
        # so OOP selects X. After that update, IP prefers R at X. Y stays uniform.
        terminal_xl = (
            proof.physical._Terminal(("X", "L"), "showdown", (2, 2)),
            proof.physical._Terminal(("X", "L"), "showdown", (2, 2)),
        )
        terminal_xr = (
            proof.physical._Terminal(("X", "R"), "showdown", (0, 0)),
            proof.physical._Terminal(("X", "R"), "showdown", (0, 0)),
        )
        terminal_y = (
            proof.physical._Terminal(("Y", "L"), "showdown", (0, 0)),
            proof.physical._Terminal(("Y", "R"), "showdown", (0, 0)),
        )
        chance_xl = proof.physical._Chance(("X", "L"), 4, "river",
                                           {"6c": terminal_xl[0], "6d": terminal_xl[1]})
        chance_xr = proof.physical._Chance(("X", "R"), 4, "river",
                                           {"6c": terminal_xr[0], "6d": terminal_xr[1]})
        chance_yl = proof.physical._Chance(("Y", "L"), 4, "river",
                                           {"6c": terminal_y[0], "6d": terminal_y[0]})
        chance_yr = proof.physical._Chance(("Y", "R"), 4, "river",
                                           {"6c": terminal_y[1], "6d": terminal_y[1]})
        ip_x = _decision(1, ("X",), (chance_xl, chance_xr))
        ip_y = _decision(1, ("Y",), (chance_yl, chance_yr))
        root = _decision(0, (), (ip_x, ip_y))
        worlds = (_world(0.75, 1, "6c"), _world(0.25, -1, "6d"))
        infos = {(0, "AsAd", ()): 2, (1, "KsKd", ("X",)): 2,
                 (1, "KsKd", ("Y",)): 2}

        average = cfr_plus.train(root, worlds, infos, 1,
                                 algorithm="cfrplus",
                                 terminal_value=adapter._terminal_value,
                                 node_key=adapter._node_key,
                                 chance_child=adapter._chance_child)

        self.assertEqual(average[(0, "AsAd", ())], [1.0, 0.0])
        self.assertEqual(average[(1, "KsKd", ("X",))], [0.0, 1.0])
        self.assertEqual(average[(1, "KsKd", ("Y",))], [0.5, 0.5])

    def test_mutated_census_rejects_before_policy_rows_or_training(self):
        model = SimpleNamespace(root=object())
        bad_census = dict(adapter.EXPECTED_CENSUS, compact_worlds=127)
        with patch.object(adapter.proof, "validate_model", return_value=bad_census), \
             patch.object(adapter.proof, "_class_rows", side_effect=AssertionError("rows")) as rows, \
             patch.object(adapter.cfr_plus, "train", side_effect=AssertionError("training")) as train:
            with self.assertRaisesRegex(ValueError, "census"):
                adapter._training_inputs(model)
        rows.assert_not_called()
        train.assert_not_called()

    def test_trainer_output_key_mismatch_rejects_before_normalization_or_diagnostics(self):
        @contextmanager
        def empty_guard():
            yield {}

        model = SimpleNamespace(root=object())
        infos = {(0, "AsAd", ()): 2}
        with patch.object(adapter, "_source_hashes", return_value={}), \
             patch.object(adapter.publication, "verify", return_value={}), \
             patch.object(adapter.proof, "independent_guard", side_effect=empty_guard), \
             patch.object(adapter.proof, "build_model", return_value=model), \
             patch.object(adapter, "_training_inputs", return_value=((), infos, 1)), \
             patch.object(adapter.cfr_plus, "train", return_value={}), \
             patch.object(adapter.policy, "canonicalize_binary_rows",
                          side_effect=AssertionError("normalization")) as normalize, \
             patch.object(adapter.proof, "lift_policy",
                          side_effect=AssertionError("lift")) as lift, \
             patch.object(adapter.proof, "audit_policy",
                          side_effect=AssertionError("diagnostics")) as audit:
            with self.assertRaisesRegex(ValueError, "Trainer output"):
                adapter.solve_fixed(1)
        normalize.assert_not_called()
        lift.assert_not_called()
        audit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
