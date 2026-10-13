import itertools
import unittest
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from pokerlab import preflop_vector_budget as budget
from pokerlab.cards import DECK
from scripts.preflop_validation import compare_result, replay_policy


_SB = "AsAd:1,AhAc:0.25"
_BB = "KsKd:1,KcKh:0.5"
_KWARGS = {
    "config": {"starting_stack": [4, 3], "raise_sizes": [0.5],
               "max_raises": 1, "include_all_in": False},
    "runouts": ("2c3c4d7h8h", "Kc2d3h7s8c", "Ac2d3h7s8c"),
}
_FIELDS = ("value_sb", "value_bb", "sb_best_response_value",
           "bb_best_response_value", "nash_conv", "exploitability")


def _solve(**options):
    return solver.solve_preflop(
        _SB, _BB, **_KWARGS, iterations=10, traversal="public-batched",
        diagnostics="public-batched", **options)


class PreflopVectorResourceTests(unittest.TestCase):
    def test_opt_in_preserves_policies_values_and_default_payload(self):
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                default = _solve(algorithm=algorithm)
                explicit = _solve(algorithm=algorithm, resource_model="world")
                self.assertEqual(default, explicit)
                self.assertNotIn("resource_model", default)
                vector = _solve(algorithm=algorithm, resource_model="public-vector")
                self.assertEqual(vector["strategy"], default["strategy"])
                for field in _FIELDS:
                    self.assertAlmostEqual(vector[field], default[field], delta=1e-12)
                self.assertEqual(vector["private_pair_probabilities"],
                                 default["private_pair_probabilities"])
                self.assertFalse(vector["world_decision_work_enforced"])
                self.assertIsNone(vector["limits"]["world_decision_work"])
                estimate = vector["vector_work_budget"]
                self.assertEqual(estimate["information_sets"], vector["info_sets"])
                self.assertLessEqual(estimate["total_loop_entries_upper_bound"],
                                     estimate["total_loop_entry_limit"])
                oracle = replay_policy(vector, _SB, _BB, **_KWARGS)
                compare_result(vector, oracle)

    def test_replacement_is_explicit_and_legacy_guard_remains(self):
        with patch.object(solver, "_MAX_WORLD_NODE_WORK", 1):
            with self.assertRaisesRegex(ValueError, "world-decision iterations"):
                _solve()
            vector = _solve(resource_model="public-vector")
            self.assertGreater(vector["world_decision_work"], 1)
            self.assertEqual(vector["limits"]["reference_world_decision_work"], 1)
            compare_result(vector, replay_policy(vector, _SB, _BB, **_KWARGS))

    def test_budget_failures_precede_trainer_and_training_view(self):
        for name in ("MAX_PREFIX_EDGES", "MAX_DENSE_PREFIX_SLOTS",
                     "MAX_INFO_ACTION_SLOTS", "MAX_TOTAL_LOOP_ENTRIES"):
            with self.subTest(cap=name):
                with patch.object(budget, name, 1):
                    with patch.object(solver, "train_public_batched") as train:
                        with patch.object(solver, "_positive_pot_training_view") as view:
                            with self.assertRaises(ValueError):
                                _solve(resource_model="public-vector")
                            train.assert_not_called()
                            view.assert_not_called()
        with patch.object(solver, "MAX_INFO_ACTION_SLOTS", 1):
            with patch.object(solver, "estimate_vector_budget") as estimate:
                with self.assertRaisesRegex(ValueError, "action slots"):
                    _solve(resource_model="public-vector")
                estimate.assert_not_called()

    def test_invalid_or_mixed_models_reject_before_enumeration(self):
        selections = (("invalid", "public-batched", "public-batched"),
                      ("public-vector", "recursive", "public-batched"),
                      ("public-vector", "planned", "public-batched"),
                      ("public-vector", "public-batched", "recursive"))
        for model, traversal, diagnostics in selections:
            with self.subTest(model=model, traversal=traversal, diagnostics=diagnostics):
                with patch.object(solver, "_enumerate_physical_worlds") as enumerate_worlds:
                    with self.assertRaisesRegex(ValueError, "resource model"):
                        solver.solve_preflop(_SB, _BB, **_KWARGS, iterations=10,
                                             resource_model=model, traversal=traversal,
                                             diagnostics=diagnostics)
                    enumerate_worlds.assert_not_called()

    def test_original_world_candidate_and_state_guards_still_apply(self):
        common = {"resource_model": "public-vector", "traversal": "public-batched",
                  "diagnostics": "public-batched"}
        with patch.object(solver, "rank_hand") as rank:
            with self.assertRaisesRegex(ValueError, "candidate-pair iterations"):
                solver.solve_preflop("random", "random", runouts=("2c3c4d7h8h",),
                                     iterations=10, **common)
            rank.assert_not_called()
        deck = [card for card in DECK if card not in {"As", "Ad", "Ks", "Kd"}]
        outcomes = list(itertools.islice(itertools.combinations(deck, 5), 301))
        with patch.object(solver, "rank_hand") as rank:
            with self.assertRaisesRegex(ValueError, "3 million world iterations"):
                solver.solve_preflop("AsAd", "KsKd", runouts=outcomes,
                                     iterations=10_000, **common)
            rank.assert_not_called()
        with patch.object(solver, "_MAX_PUBLIC_STATES", 2):
            with self.assertRaisesRegex(ValueError, "Combined preflop/postflop tree"):
                _solve(resource_model="public-vector")

    def test_terminal_game_keeps_diagnostics_and_zero_training_accounting(self):
        kwargs = {"config": {"starting_stack": [0.5, 20], "max_raises": 0},
                  "runouts": ("2c3c4d7h8h",)}
        with patch.object(solver, "train_public_batched") as train:
            result = solver.solve_preflop(
                "AsAd", "KsKd", **kwargs, iterations=10,
                traversal="public-batched", diagnostics="public-batched",
                resource_model="public-vector")
            train.assert_not_called()
        estimate = result["vector_work_budget"]
        self.assertEqual(estimate["training_loop_entries_upper_bound"], 0)
        self.assertEqual(estimate["aggregation_count"], 1)
        self.assertGreater(estimate["diagnostics_loop_entries_upper_bound"], 0)
        self.assertEqual(result["strategy"], [])
        self.assertAlmostEqual(result["value_sb"], 0.5, delta=1e-12)
        compare_result(result, replay_policy(result, "AsAd", "KsKd", **kwargs))


if __name__ == "__main__":
    unittest.main()
