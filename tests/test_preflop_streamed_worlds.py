import copy
from collections import Counter
import unittest
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from pokerlab.preflop_future_groups import group_hidden_futures
from scripts.preflop_validation import compare_result, replay_policy

SB = "AsAd:1,AhAc:0.25,QsQd:0.5"
BB = "KsKd:1,KcKh:0.5,8h8d:0.75"
RUNOUTS = (
    "2c3c4d7h8h", "2c3c4d8h7h", "2c3d4h7s8c",
    "Ac2c3d7h8h", "9cTcJcQcKc",
)
PREFLOP = {"starting_stack": [2.5, 2], "raise_sizes": [0.5],
           "max_raises": 1, "include_all_in": False}
FLOP = {"bet_sizes": [0.5], "raise_sizes": [0.5],
        "max_raises": 1, "include_all_in": False}
SOLVE_OPTIONS = {
    "config": PREFLOP, "runouts": RUNOUTS, "flop_config": FLOP,
    "postflop_scope": "flop-checkdown", "iterations": 10,
    "algorithm": "cfrplus", "averaging_delay": 5,
    "traversal": "public-batched", "diagnostics": "public-batched",
    "resource_model": "public-vector", "future_indexing": "flop-sign",
    "world_admission": "grouped-vector",
}


def _enumerate(stream):
    return solver._enumerate_physical_worlds(
        SB, BB, RUNOUTS, 10, world_work_iterations=10,
        stream_groups=stream)


def _strip_streaming_only_fields(result):
    normalized = copy.deepcopy(result)
    normalized.pop("world_storage")
    normalized.pop("world_storage_metadata")
    budget = normalized["vector_work_budget"]
    streamed = budget.pop("streamed_world_construction")
    reference_version = budget.pop("streamed_world_reference_budget_version")
    budget["total_loop_entries_upper_bound"] -= streamed["additional_loop_entries_upper_bound"]
    budget["budget_version"] = reference_version
    return normalized


class PreflopStreamedWorldsTests(unittest.TestCase):
    def test_descriptor_matches_materialized_mass_legal_and_group_order(self):
        hands, worlds, pairs, probabilities, selected, checks = _enumerate(False)
        streamed_hands, descriptor, streamed_pairs, streamed_probabilities, streamed_selected, streamed_checks = _enumerate(True)
        self.assertEqual(streamed_hands, hands)
        self.assertEqual(streamed_pairs, pairs)
        self.assertEqual(streamed_probabilities, probabilities)
        self.assertEqual(streamed_selected, selected)
        self.assertEqual(streamed_checks, checks)
        self.assertEqual(len(descriptor), len(worlds))
        self.assertEqual(descriptor.pair_probabilities, probabilities)

        shape_rows = tuple(descriptor.shape_rows())
        expected_shape = tuple((row[0], row[1], row[2], 0, *row[4:]) for row in worlds)
        self.assertEqual(shape_rows, expected_shape)
        self.assertEqual(descriptor.legal_hands(), solver._legal_private_hands(worlds, "flop-checkdown"))
        self.assertEqual(descriptor.flop_world_counts,
                         dict(Counter(row[4] for row in worlds)))
        world_runouts = {(row[4], row[5], row[6]) for row in worlds}
        expected_reachable = bytes(
            int(("".join(flop), turn, river) in world_runouts)
            for flop, turn, river in selected)
        self.assertEqual(bytes(descriptor.reachable_indices), expected_reachable)

        expected_groups = group_hidden_futures(worlds)
        actual_groups = descriptor.grouped_rows(solver._rank_world)
        self.assertEqual(actual_groups, expected_groups)
        self.assertIsNone(descriptor._index)
        self.assertIsNone(descriptor._hands)
        self.assertIsNone(descriptor._selected)
        self.assertIsNone(descriptor._pairs)

    def test_streamed_solver_matches_materialized_and_independent_replay(self):
        materialized = solver.solve_preflop(SB, BB, **SOLVE_OPTIONS)
        streamed = solver.solve_preflop(SB, BB, **SOLVE_OPTIONS,
                                        world_storage="streamed-flop-sign")
        normalized = _strip_streaming_only_fields(streamed)
        self.assertEqual(normalized, materialized)
        self.assertEqual(streamed["world_storage"], "streamed-flop-sign")
        oracle = replay_policy(streamed, SB, BB, config=PREFLOP,
                               runouts=RUNOUTS, flop_config=FLOP,
                               postflop_scope="flop-checkdown")
        compare_result(streamed, oracle)
        self.assertIn(0, {row[3] for row in _enumerate(False)[1]})
        self.assertEqual(streamed["worlds"], len(_enumerate(False)[1]))

    def test_invalid_mode_combinations_reject_before_enumeration(self):
        cases = (
            {"world_storage": "invalid"},
            {"world_storage": "streamed-flop-sign", "future_indexing": "original"},
            {"world_storage": "streamed-flop-sign", "private_indexing": "compact"},
            {"world_storage": "streamed-flop-sign", "postflop_scope": "all-streets"},
        )
        for changes in cases:
            options = dict(SOLVE_OPTIONS)
            options.update(changes)
            with self.subTest(changes=changes), patch.object(
                    solver, "_enumerate_physical_worlds",
                    side_effect=AssertionError("enumeration started")) as enumerate_worlds:
                with self.assertRaises(ValueError):
                    solver.solve_preflop(SB, BB, **options)
                enumerate_worlds.assert_not_called()

    def test_physical_vector_and_stream_construction_guards_precede_ranking(self):
        with patch.object(solver, "_MAX_WORLD_ITERATIONS", 1), \
             patch.object(solver, "_rank_world") as rank:
            with self.assertRaisesRegex(ValueError, "world iterations"):
                solver.solve_preflop(SB, BB, **SOLVE_OPTIONS,
                                     world_storage="streamed-flop-sign")
            rank.assert_not_called()

        with patch("pokerlab.preflop_streamed_worlds.MAX_STREAM_REFERENCE_SLOTS", 1), \
             patch.object(solver, "_rank_world") as rank:
            with self.assertRaisesRegex(ValueError, "reference-slot cap"):
                solver.solve_preflop(SB, BB, **SOLVE_OPTIONS,
                                     world_storage="streamed-flop-sign")
            rank.assert_not_called()

        with patch("pokerlab.preflop_vector_budget.MAX_TOTAL_LOOP_ENTRIES", 1), \
             patch.object(solver, "_rank_world") as rank:
            with self.assertRaisesRegex(ValueError, "loop entries"):
                solver.solve_preflop(SB, BB, **SOLVE_OPTIONS,
                                     world_storage="streamed-flop-sign")
            rank.assert_not_called()

    def test_extra_stream_construction_work_cap_precedes_ranking(self):
        # Keep the base vector and future-grouping admission below the patched
        # cap, but make the separately charged stream-construction term exceed it.
        original_estimator = solver.estimate_vector_budget_from_rows
        world_count = len(_enumerate(True)[1])
        group_budget = solver.estimate_future_grouping_count(world_count)["grouping_loop_entries_upper_bound"]
        cap = group_budget + 1

        def small_base_budget(*args, **kwargs):
            result = original_estimator(*args, **kwargs)
            result["total_loop_entries_upper_bound"] = 0
            return result

        with patch.object(solver, "estimate_vector_budget_from_rows", small_base_budget), \
             patch.object(solver, "MAX_TOTAL_LOOP_ENTRIES", cap), \
             patch.object(solver, "_rank_world") as rank:
            with self.assertRaisesRegex(ValueError, "Streamed construction vector"):
                solver.solve_preflop(SB, BB, **SOLVE_OPTIONS,
                                     world_storage="streamed-flop-sign")
            rank.assert_not_called()

    def test_descriptor_releases_inputs_when_ranking_raises(self):
        _hands, descriptor, *_ = _enumerate(True)
        with patch.object(solver, "_rank_world", side_effect=RuntimeError("rank failure")):
            with self.assertRaisesRegex(RuntimeError, "rank failure"):
                descriptor.grouped_rows(solver._rank_world)
        self.assertIsNone(descriptor._index)
        self.assertIsNone(descriptor._hands)
        self.assertIsNone(descriptor._selected)
        self.assertIsNone(descriptor._pairs)
        self.assertIsNone(descriptor._private_flops)


if __name__ == "__main__":
    unittest.main()

