import unittest
import math
from unittest.mock import patch

from pokerlab.river_tree import _Terminal
from pokerlab.selected_runout_operator import SelectedRunoutOperator


RUNOUTS = ["2c3d4h5s6c", "2c3d4h7s8c"]


class SelectedRunoutOperatorTests(unittest.TestCase):
    def make(self, sb="AsKd", bb="QcJh", runouts=RUNOUTS, iterations=1):
        return SelectedRunoutOperator(sb, bb, runouts, iterations)

    def test_snapshots_ranges_and_runouts_without_ranking_constructor(self):
        with patch("pokerlab.selected_runout_operator.rank_hand",
                   side_effect=AssertionError("ranked during construction")):
            op = self.make()
        self.assertEqual(op.hand_counts, (1, 1))
        self.assertEqual(op.world_count, 2)
        self.assertEqual(op.compatible_pairs, 1)
        self.assertEqual(op.reachable_selected(), op.selected)
        self.assertAlmostEqual(sum(op.joint_marginals()[0]), 1)

    def test_blockers_and_global_normalization(self):
        op = self.make("AsKd:1,2c3d:0.5", "QcJh:1,5s6c:0.25")
        worlds = list(op._iter_worlds())
        self.assertGreater(len(worlds), 0)
        self.assertEqual(op.world_count, len(worlds))
        self.assertAlmostEqual(sum(op.joint_marginals()[0]), 1)
        self.assertAlmostEqual(sum(op.joint_marginals()[1]), 1)
        self.assertAlmostEqual(sum(x["probability"] for x in op.pair_probabilities()), 1)
        self.assertTrue(all(not (op._hand_masks[0][i] & op._hand_masks[1][j])
                            for i, j, _ in worlds))

    def test_compatible_pair_count_requires_selected_board_support(self):
        op = self.make("AsKd,2c3d", "QcJh")
        self.assertEqual(op.private_compatible_pairs, 2)
        self.assertEqual(op.compatible_pairs, 1)

    def test_unsupported_underflow_pair_does_not_reject_supported_worlds(self):
        op = self.make("AsKd:1,2c3d:1e-300", "QcJh")
        self.assertEqual(op.compatible_pairs, 1)
        self.assertEqual(op.world_count, 2)

    def test_prefixes_integrate_hidden_future_cards(self):
        op = self.make()
        flop = op._flop_keys[0]
        self.assertAlmostEqual(sum(op.joint_marginals((flop,))[0]), 1)
        self.assertEqual(op._prefix_world_count((flop,)), 2)
        self.assertEqual(op._prefix_world_count((flop, "5s")), 1)
        with self.assertRaises(ValueError):
            op.joint_marginals((flop, "5s", "6c", "9d"))

    def test_fold_and_showdown_vectors(self):
        op = self.make()
        op.pot = 2.0
        fold = _Terminal("fold", (1.0, 1.0), winner=0)
        got = op.values(fold, [1.0], 0)
        self.assertAlmostEqual(got[0], 2.0)
        self.assertAlmostEqual(op.values(fold, [1.0], 1)[0], -2.0)
        showdown = _Terminal("showdown", (1.0, 1.0))
        prefixes = [(), (op._flop_keys[0],),
                    (op._flop_keys[0], op.selected[0][1]),
                    (op._flop_keys[0], op.selected[0][1], op.selected[0][2])]
        root_value = op.values(showdown, [1.0], 0)[0]
        self.assertAlmostEqual(root_value, sum(
            op.values(showdown, [1.0], 0, (op._flop_keys[k], op.selected[k][1],
                                           op.selected[k][2]))[0]
            for k in range(len(op.selected))))
        for prefix in prefixes:
            p0 = op.values(showdown, [1.0], 0, prefix)[0]
            p1 = op.values(showdown, [1.0], 1, prefix)[0]
            self.assertAlmostEqual(p0, -p1)
        self.assertEqual(op.rank_calls, 26)
        self.assertEqual(op.rank_scratch_peak, 2)
        self.assertEqual(op.structural_storage_counts()["hand_entries"], 2)

    def test_reach_and_terminal_validation(self):
        op = self.make()
        op.pot = 2.0
        fold = _Terminal("fold", (1.0, 1.0), winner=0)
        # The smallest positive binary64 reach is accepted as finite, though
        # its resulting contribution may round to zero.
        self.assertTrue(math.isfinite(op.values(fold, [math.ulp(0.0)], 0)[0]))
        with self.assertRaises(ValueError):
            op.values(fold, [math.inf], 0)
        with self.assertRaises(ValueError):
            op.values(_Terminal("fold", (1.0, 1.0), winner=2), [1.0], 0)
        with self.assertRaises(ValueError):
            op.values(_Terminal("showdown", (-1.0, 1.0)), [1.0], 0, ())
        op.pot = -1.0
        with self.assertRaises(ValueError):
            op.values(fold, [1.0], 0)

    def test_mutable_range_containers_are_not_accepted(self):
        with self.assertRaises(ValueError):
            self.make(["AsKd"], ["QcJh"])

    def test_nonfinite_and_underflowing_range_mass_rejected(self):
        with self.assertRaises(ValueError):
            self.make("AsKd:1e-300", "QcJh:1e-300")
        with self.assertRaises(ValueError):
            self.make("AsKd:inf", "QcJh")

    def test_iteration_preflight(self):
        with self.assertRaises(ValueError):
            self.make(iterations=3_000_001)


if __name__ == "__main__":
    unittest.main()
