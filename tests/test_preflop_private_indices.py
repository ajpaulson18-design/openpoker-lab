import gc
import unittest
import weakref
from unittest.mock import patch

from pokerlab import preflop_solver
from pokerlab.postflop_solver import _Chance
from pokerlab.public_cfr import _aggregate_prefixes
from pokerlab.preflop_delayed_cfrplus import train_delayed_public_cfrplus
from pokerlab.river_tree import _Action, _Node, _Terminal
from pokerlab import preflop_private_indices as compaction
from scripts.preflop_validation import compare_result, replay_policy


def _dense_hole_fixture():
    after_a = _Node(("A", "bb"), 1,
                    (_Action("fold"), _Action("call")),
                    (_Terminal("fold", (1.0, 2.0), 0),
                     _Terminal("showdown", (2.0, 2.0))))
    after_b = _Node(("B", "bb"), 1,
                    (_Action("fold"), _Action("call")),
                    (_Terminal("fold", (1.5, 2.0), 1),
                     _Terminal("showdown", (2.5, 2.5))))
    chance = _Chance(("board",), {"A": after_a, "B": after_b})
    root = _Node(("preflop",), 0,
                 (_Action("fold"), _Action("continue")),
                 (_Terminal("fold", (0.5, 1.0), 1), chance))
    worlds = (
        (2, 1, 0.10, 1, "A"), (2, 4, 0.20, -1, "A"),
        (8, 1, 0.30, -1, "B"), (8, 4, 0.40, 1, "B"),
    )
    # Deliberately interleave row order; compact output must restore it.
    infos = {
        (1, 4, after_b.history): 2,
        (0, 8, root.history): 2,
        (1, 1, after_a.history): 2,
        (0, 2, root.history): 2,
        (1, 1, after_b.history): 2,
        (1, 4, after_a.history): 2,
    }
    return root, worlds, infos


def _train(root, worlds, infos):
    return train_delayed_public_cfrplus(
        root, worlds, infos, 10, averaging_delay=5,
        pot=2.0, chance_type=_Chance)


class PreflopPrivateIndicesTests(unittest.TestCase):
    def test_dense_holes_compact_and_restore_training_policy_exactly(self):
        root, worlds, infos = _dense_hole_fixture()
        original_worlds = worlds
        original_infos = dict(infos)
        compact = compaction.compact_private_indices(worlds, infos)
        self.assertEqual(compact.original_to_compact,
                         ({2: 0, 8: 1}, {1: 0, 4: 1}))
        self.assertEqual(compact.metadata["original_hand_dimensions"], [9, 5])
        self.assertEqual(compact.metadata["compact_hand_dimensions"], [2, 2])
        self.assertEqual(compact.worlds, (
            (0, 0, 0.10, 1, "A"), (0, 1, 0.20, -1, "A"),
            (1, 0, 0.30, -1, "B"), (1, 1, 0.40, 1, "B"),
        ))
        self.assertEqual(tuple(compact.infos.values()), tuple(infos.values()))
        self.assertEqual(worlds, original_worlds)
        self.assertEqual(infos, original_infos)

        expected = _train(root, worlds, infos)
        compact_policy = _train(root, compact.worlds, compact.infos)
        self.assertEqual(compact.restore_policy(compact_policy), expected)
        self.assertEqual(list(compact.restore_policy(compact_policy)), list(infos))

    def test_real_blocker_fixture_preserves_full_solve_and_independent_replay(self):
        sb = ",".join([f"As{rank}s" for rank in "23456789TJQK"] + ["2c3c"])
        bb = "AsAd"
        kwargs = {
            "config": {"starting_stack": 2, "max_raises": 0,
                       "include_all_in": False},
            "runouts": ("4c5c6c7c8c",),
        }
        baseline = preflop_solver.solve_preflop(
            sb, bb, **kwargs, iterations=10, averaging_delay=5,
            algorithm="cfrplus", traversal="public-batched",
            diagnostics="public-batched", resource_model="public-vector")
        self.assertNotIn("private_indexing", baseline)

        optimized = preflop_solver.solve_preflop(
            sb, bb, **kwargs, iterations=10, averaging_delay=5,
            algorithm="cfrplus", traversal="public-batched",
            diagnostics="public-batched", resource_model="public-vector",
            private_indexing="compact")

        self.assertEqual(optimized["private_indexing"], "compact")
        self.assertEqual(optimized["private_indexing_metadata"]["original_hand_dimensions"], [13, 1])
        self.assertEqual(optimized["private_indexing_metadata"]["compact_hand_dimensions"], [1, 1])
        self.assertEqual(optimized["strategy"], baseline["strategy"])
        self.assertEqual(optimized["value_sb"], baseline["value_sb"])
        self.assertEqual(optimized["sb_best_response_value"],
                         baseline["sb_best_response_value"])
        self.assertEqual(optimized["bb_best_response_value"],
                         baseline["bb_best_response_value"])
        self.assertEqual(optimized["private_pair_probabilities"],
                         baseline["private_pair_probabilities"])
        oracle = replay_policy(optimized, sb, bb, **kwargs)
        compare_result(optimized, oracle)
        self.assertEqual(oracle["checked_information_sets"], optimized["info_sets"])

    def test_compaction_is_opt_in_and_rejects_unsupported_modes_before_enumeration(self):
        with patch.object(preflop_solver, "_enumerate_physical_worlds",
                          side_effect=AssertionError("enumeration started")):
            with self.assertRaisesRegex(ValueError, r"positive-delay CFR\+"):
                preflop_solver.solve_preflop(
                    "AsAd", "KsKd", runouts=("2c3c4d7h8h",), iterations=10,
                    private_indexing="compact")
            with self.assertRaisesRegex(ValueError, r"positive-delay CFR\+"):
                preflop_solver.solve_preflop(
                    "AsAd", "KsKd", runouts=("2c3c4d7h8h",), iterations=10,
                    averaging_delay=1, algorithm="cfrplus", traversal="public-batched",
                    diagnostics="public-batched", private_indexing="compact")
            with self.assertRaisesRegex(ValueError, "public-vector"):
                preflop_solver.solve_preflop(
                    "AsAd", "KsKd", runouts=("2c3c4d7h8h",), iterations=10,
                    averaging_delay=1, algorithm="cfrplus", traversal="public-batched",
                    diagnostics="public-batched", private_indexing="compact",
                    resource_model="world")
            with self.assertRaisesRegex(ValueError, "private_indexing"):
                preflop_solver.solve_preflop(
                    "AsAd", "KsKd", runouts=("2c3c4d7h8h",), iterations=10,
                    private_indexing="automatic")

    def test_compaction_reference_is_released_when_training_raises_without_gc(self):
        references = []
        original_compactor = preflop_solver.compact_private_indices

        def track_compaction(worlds, infos):
            compact = original_compactor(worlds, infos)
            references.append(weakref.ref(compact))
            return compact

        with patch.object(preflop_solver, "compact_private_indices", new=track_compaction), \
                patch.object(preflop_solver, "train_delayed_public_cfrplus",
                             side_effect=RuntimeError("trainer failure")), \
                patch.object(gc, "collect", side_effect=AssertionError("forced collection")):
            with self.assertRaisesRegex(RuntimeError, "trainer failure"):
                preflop_solver.solve_preflop(
                    "AsAd", "KsKd", config={"starting_stack": 2, "max_raises": 0,
                                             "include_all_in": False},
                    runouts=("2c3c4d7h8h",), iterations=10, averaging_delay=5,
                    algorithm="cfrplus", traversal="public-batched",
                    diagnostics="public-batched", resource_model="public-vector",
                    private_indexing="compact")
        self.assertEqual(len(references), 1)
        self.assertIsNone(references[0]())

    def test_caps_and_inactive_info_indices_fail_before_copying(self):
        root, worlds, infos = _dense_hole_fixture()
        with patch.object(compaction, "_copy_world_row",
                          side_effect=AssertionError("world copy started")):
            with self.assertRaisesRegex(ValueError, "world-row cap"):
                compaction.compact_private_indices(worlds, infos, max_world_rows=1)
            with self.assertRaisesRegex(ValueError, "info-action cap"):
                compaction.compact_private_indices(worlds, infos, max_info_action_slots=1)
            inactive = dict(infos)
            inactive[(0, 7, root.history)] = 2
            with self.assertRaisesRegex(ValueError, "absent from all physical worlds"):
                compaction.compact_private_indices(worlds, inactive)

    def test_invalid_indices_and_policy_key_sets_fail_closed(self):
        bad_worlds = (
            ((True, 0, 1.0, 1),),
            ((1326, 0, 1.0, 1),),
            ((0, 0, 1.0),),
        )
        for worlds in bad_worlds:
            with self.subTest(worlds=worlds):
                with self.assertRaises(ValueError):
                    compaction.compact_private_indices(worlds, {})

        _root, worlds, infos = _dense_hole_fixture()
        compact = compaction.compact_private_indices(worlds, infos)
        with self.assertRaisesRegex(ValueError, "keys must match"):
            compact.restore_policy({})
        bad = dict((key, [0.5, 0.5]) for key in compact.infos)
        bad[(0, 99, ("foreign",))] = [0.5, 0.5]
        with self.assertRaisesRegex(ValueError, "keys must match"):
            compact.restore_policy(bad)

    def test_no_information_rows_round_trip_empty_policy(self):
        worlds = ((7, 2, 0.5, 1, "A"), (9, 2, 0.5, -1, "B"))
        compact = compaction.compact_private_indices(worlds, {})
        self.assertEqual(compact.original_to_compact, ({7: 0, 9: 1}, {2: 0}))
        self.assertEqual(compact.restore_policy({}), {})

    def test_no_information_compact_diagnostics_preserve_refund_and_zero_passes(self):
        kwargs = {
            "config": {"starting_stack": [0.5, 20], "max_raises": 0},
            "runouts": ("2c3c4d7h8h",), "iterations": 10,
            "algorithm": "cfrplus", "averaging_delay": 5,
            "traversal": "public-batched", "diagnostics": "public-batched",
            "resource_model": "public-vector",
        }
        original = preflop_solver.solve_preflop("AsAd", "KsKd", **kwargs)
        compact = preflop_solver.solve_preflop(
            "AsAd", "KsKd", **kwargs, private_indexing="compact")
        self.assertEqual(original["strategy"], compact["strategy"])
        self.assertEqual(original["value_sb"], compact["value_sb"])
        self.assertEqual(original["sb_best_response_value"],
                         compact["sb_best_response_value"])
        self.assertEqual(original["bb_best_response_value"],
                         compact["bb_best_response_value"])
        self.assertEqual(compact["info_sets"], 0)
        self.assertEqual(compact["training_passes"], 0)
        self.assertEqual(compact["private_indexing_metadata"]["compact_hand_dimensions"], [1, 1])
        compare_result(compact, replay_policy(compact, "AsAd", "KsKd",
                                               config=kwargs["config"],
                                               runouts=kwargs["runouts"]))

    def test_compact_convergence_callback_and_final_diagnostics_match_original_ids(self):
        sb = ",".join([f"As{rank}s" for rank in "23456789TJQK"] + ["2c3c"])
        kwargs = {
            "config": {"starting_stack": 2, "max_raises": 0,
                       "include_all_in": False},
            "runouts": ("4c5c6c7c8c",), "iterations": 10,
            "algorithm": "cfrplus", "averaging_delay": 1,
            "traversal": "public-batched", "diagnostics": "public-batched",
            "resource_model": "public-vector",
            "target_nash_conv": 10.0, "convergence_check_interval": 2,
        }
        original = preflop_solver.solve_preflop(sb, "AsAd", **kwargs)
        compact = preflop_solver.solve_preflop(
            sb, "AsAd", **kwargs, private_indexing="compact")
        self.assertEqual(original["convergence_checkpoints"],
                         compact["convergence_checkpoints"])
        self.assertEqual(compact["completed_iterations"], 2)
        self.assertTrue(compact["convergence_target_reached"])
        self.assertEqual(original["strategy"], compact["strategy"])
        self.assertEqual(original["value_sb"], compact["value_sb"])
        self.assertEqual(original["sb_best_response_value"],
                         compact["sb_best_response_value"])
        self.assertEqual(original["bb_best_response_value"],
                         compact["bb_best_response_value"])
        self.assertEqual(compact["private_indexing_metadata"]["original_active_indices"],
                         [[12], [0]])
        self.assertEqual(compact["private_indexing_metadata"]["compact_hand_dimensions"], [1, 1])


if __name__ == "__main__":
    unittest.main()
