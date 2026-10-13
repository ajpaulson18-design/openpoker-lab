import itertools
import unittest
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from pokerlab import preflop_vector_budget as budget
from pokerlab import postflop_solver as postflop
from scripts.preflop_validation import compare_result, replay_policy


SB = "AsAd,QsQd"
BB = "KsKd,JhJc"
CONFIG = {"starting_stack": 2, "max_raises": 0, "include_all_in": False}
OPTIONS = {"iterations": 10, "algorithm": "cfrplus", "averaging_delay": 5,
           "traversal": "public-batched", "diagnostics": "public-batched",
           "resource_model": "public-vector"}


def complete_futures(flops):
    deck = [rank + suit for rank in "23456789TJQKA" for suit in "cdhs"]
    return tuple(tuple(flop) + future for flop in flops
                 for future in itertools.permutations([c for c in deck if c not in flop], 2))


class PreflopTreeAdmissionTests(unittest.TestCase):
    def test_default_admission_preserves_output_and_explicit_vector_policy(self):
        kwargs = {"config": CONFIG, "runouts": ("2c3c4d7h8h", "5h6sJc7h8h")}
        default = solver.solve_preflop(SB, BB, **kwargs, **OPTIONS)
        explicit = solver.solve_preflop(SB, BB, **kwargs, **OPTIONS,
                                        tree_admission="decision-count")
        self.assertEqual(default, explicit)
        self.assertNotIn("tree_admission", default)
        vector = solver.solve_preflop(SB, BB, **kwargs, **OPTIONS, tree_admission="vector")
        self.assertEqual(vector["strategy"], default["strategy"])
        self.assertFalse(vector["decision_count_limit_enforced"])
        self.assertIsNone(vector["limits"]["decision_nodes"])
        compare_result(vector, replay_policy(vector, SB, BB, **kwargs))

    def test_invalid_or_mixed_selection_rejects_before_enumeration(self):
        for selection, model in ((None, "public-vector"), (True, "public-vector"),
                                  ("invalid", "public-vector"), ("vector", "world"),
                                  ("vector", "chance-sampled")):
            with self.subTest(selection=selection, model=model):
                with patch.object(solver, "_enumerate_physical_worlds") as worlds:
                    with self.assertRaisesRegex(ValueError, "admission"):
                        solver.solve_preflop(SB, BB, config=CONFIG, runouts=("2c3c4d7h8h",),
                                             tree_admission=selection, resource_model=model)
                    worlds.assert_not_called()

    def test_all_structural_caps_still_precede_training_and_view(self):
        kwargs = {"config": CONFIG, "runouts": ("2c3c4d7h8h",)}
        caps = ((solver, "_MAX_PUBLIC_STATES"), (solver, "MAX_INFO_ACTION_SLOTS"),
                (postflop, "_MAX_PUBLIC_STATES"), (postflop, "_MAX_PUBLIC_NODES"), (budget, "MAX_PREFIX_EDGES"),
                (budget, "MAX_DENSE_PREFIX_SLOTS"), (budget, "MAX_INFO_ACTION_SLOTS"),
                (budget, "MAX_TOTAL_LOOP_ENTRIES"))
        for module, name in caps:
            with self.subTest(cap=name):
                with patch.object(module, name, 1):
                    with patch.object(solver, "_positive_pot_training_view") as view:
                        with patch.object(solver, "train_delayed_public_cfrplus") as train:
                            with self.assertRaises(ValueError):
                                solver.solve_preflop(SB, BB, **kwargs, **OPTIONS,
                                                     tree_admission="vector")
                            view.assert_not_called()
                            train.assert_not_called()

    def test_two_complete_flop_futures_have_physical_posteriors_and_replay(self):
        kwargs = {"config": CONFIG,
                  "runouts": complete_futures((("2c", "3c", "4d"), ("5h", "6s", "Jc")))}
        self.assertEqual(len(kwargs["runouts"]), 4704)
        with self.assertRaisesRegex(ValueError, "10,000 decisions"):
            solver.solve_preflop(SB, BB, **kwargs, **OPTIONS)
        result = solver.solve_preflop(SB, BB, **kwargs, **OPTIONS, tree_admission="vector")
        self.assertEqual(result["worlds"], 11880)
        self.assertEqual(result["compatible_private_pairs"], 4)
        self.assertGreater(result["decisions"], 10000)
        oracle = replay_policy(result, SB, BB, **kwargs)
        compare_result(result, oracle)
        self.assertEqual(oracle["checked_information_sets"], len(result["strategy"]))
        pair_rows = result["private_pair_probabilities"]
        for row in pair_rows:
            expected = 1 / 6 if "Jh" in row["bb_hand"] else 1 / 3
            self.assertAlmostEqual(row["probability"], expected, delta=1e-12)
        for row in result["strategy"]:
            board = row["revealed_board"]
            if not board:
                self.assertFalse(any("flop" in token for token in row["history"]))
            else:
                self.assertIn(tuple(board[:3]), (("2c", "3c", "4d"), ("5h", "6s", "Jc")))
                self.assertFalse(set(board) & {row["hand"][:2], row["hand"][2:]})


if __name__ == "__main__":
    unittest.main()
