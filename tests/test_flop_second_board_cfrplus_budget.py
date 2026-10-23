import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.flop_second_board_cfrplus_budget import (
    COMPACT_TREE_SHA256,
    INFO_ROWS,
    LOGICAL_WORK_CAP,
    MAX_ITERATIONS,
    VERSION,
    admit_second_board_request,
    validate_observed_dimensions,
)
from scripts import flop_second_board_cfrplus_budget as budget
from scripts.flop_class_compact_budget import KERNEL_LF_SHA256


ROOT = Path(__file__).resolve().parents[1]


def census():
    return {
        "compact_public_states": 1270,
        "compact_decisions": 400,
        "compact_chance_nodes": 68,
        "compact_terminals": 802,
        "compact_worlds": 170,
        "compact_policy_rows": 608,
        "compact_action_slots": 1216,
        "physical_policy_rows": 16912,
        "physical_action_slots": 33824,
        "compact_tree_sha256": COMPACT_TREE_SHA256,
    }


def infos():
    rows = {}
    for player in (0, 1):
        for index in range(304):
            hand = ("AdAs", "QdQs")[index % 2] if player == 0 else ("AsKh", "KdKs")[index % 2]
            rows[(player, hand, (f"history-{index}",))] = 2
    return rows


class FlopSecondBoardCfrplusBudgetTests(unittest.TestCase):
    def test_forecasts_are_exact_fresh_and_include_mass_sum_setup(self):
        low = admit_second_board_request(1)
        high = admit_second_board_request(MAX_ITERATIONS)
        self.assertEqual(low["version"], VERSION)
        self.assertEqual(low["logical_work_per_sweep"], 180227)
        self.assertEqual(low["total_training_work"], low["logical_work_per_sweep"])
        self.assertEqual(high["total_training_work"], 100927120)
        self.assertEqual(high["fixed_setup_and_output_work"], 65368)
        self.assertEqual(high["total_admitted_work"], 100992488)
        self.assertLessEqual(high["total_admitted_work"], LOGICAL_WORK_CAP)
        self.assertEqual(high["fixed_setup"]["world_mass_sum_terms"], 170)
        self.assertEqual(high["dimensions"]["compact_worlds"], 170)
        self.assertEqual(high["dimensions"]["compact_information_rows"], INFO_ROWS)
        self.assertEqual(high["partial_storage_bookkeeping"]["largest_single_player_delta_action_slots"], 608)
        self.assertEqual(high["census_and_scope"]["compact_tree_sha256"], COMPACT_TREE_SHA256)
        self.assertEqual(high["census_and_scope"]["compact_public_states"], 1270)
        self.assertEqual(high["census_and_scope"]["public_action_edges"], 800)
        self.assertEqual(high["census_and_scope"]["tree_edges_including_chance"], 1269)
        self.assertEqual(high["fixed_physical_preparation_census"]["oracle_worlds"], 5940)
        self.assertEqual(high["fixed_physical_preparation_census"]["physical_public_states"], 30812)
        self.assertIn("not proof-work", high["fixed_physical_preparation_census"]["meaning"])
        self.assertEqual(set(high["kernel_lf_sha256"]), set(KERNEL_LF_SHA256))
        low["per_sweep"]["outer_world_loop_entries"] = -1
        self.assertEqual(admit_second_board_request(1)["per_sweep"]["outer_world_loop_entries"], 510)
        meaning = high["census_and_scope"]["meaning"]
        for claim in ("runtime", "allocation", "RSS", "speed", "strategy-quality"):
            self.assertIn(claim, meaning)

    def test_invalid_iteration_values_reject_before_kernel_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            for invalid in (True, False, 0, -1, MAX_ITERATIONS + 1, 1.0, "1", None):
                with self.subTest(invalid=invalid), patch.object(
                        budget, "_kernel_hashes", side_effect=AssertionError("source read")) as hashes:
                    with self.assertRaises(ValueError):
                        admit_second_board_request(invalid, source_root=directory)
                    hashes.assert_not_called()

    def test_shared_kernel_mutation_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in KERNEL_LF_SHA256:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            forecast = admit_second_board_request(1, source_root=root)
            self.assertEqual(forecast["kernel_lf_sha256"], KERNEL_LF_SHA256)
            changed = root / "pokerlab" / "cfr_plus.py"
            changed.write_bytes(changed.read_bytes() + b"\n# mutation\n")
            with self.assertRaisesRegex(ValueError, "source changed"):
                admit_second_board_request(1, source_root=root)

    def test_admitted_cap_is_enforced(self):
        with patch("scripts.flop_second_board_cfrplus_budget.LOGICAL_WORK_CAP", 1):
            with self.assertRaisesRegex(ValueError, "cap exceeded"):
                admit_second_board_request(1)

    def test_new_dimensions_and_optional_tree_digest(self):
        self.assertTrue(validate_observed_dimensions(census(), 33, infos(),
                                                    require_compact_tree_hash=True))
        without_hash = census()
        del without_hash["compact_tree_sha256"]
        self.assertTrue(validate_observed_dimensions(without_hash, 33, infos()))
        with self.assertRaisesRegex(ValueError, "digest"):
            validate_observed_dimensions(without_hash, 33, infos(),
                                         require_compact_tree_hash=True)
        for path_states in (0, 34, True, 33.0):
            with self.subTest(path_states=path_states), self.assertRaises(ValueError):
                validate_observed_dimensions(census(), path_states, infos())
        for key, wrong in (("compact_worlds", True), ("compact_policy_rows", 466),
                           ("compact_decisions", 399), ("physical_action_slots", 33823)):
            altered = dict(census(), **{key: wrong})
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_observed_dimensions(altered, 33)

    def test_information_key_shape_action_count_and_player_split_are_strict(self):
        valid = infos()
        self.assertTrue(validate_observed_dimensions(census(), 33, valid))
        malformed = dict(valid)
        first = next(iter(malformed))
        malformed.pop(first)
        malformed[(0, "hand", "history-not-tuple")] = 2
        with self.assertRaisesRegex(ValueError, "shape"):
            validate_observed_dimensions(census(), 33, malformed)
        malformed = dict(valid)
        malformed[first] = 1
        with self.assertRaisesRegex(ValueError, "shape"):
            validate_observed_dimensions(census(), 33, malformed)
        all_player_zero = {(0, "AdAs", (f"history-{index}",)): 2
                           for index in range(INFO_ROWS)}
        with self.assertRaisesRegex(ValueError, "per-player"):
            validate_observed_dimensions(census(), 33, all_player_zero)

    def test_hashes_that_are_present_must_match_the_proved_tree(self):
        altered = dict(census(), compact_tree_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "digest"):
            validate_observed_dimensions(altered, 33)

    def test_exact_dict_bool_and_canonical_hand_history_types(self):
        class DictSubclass(dict):
            pass

        class TupleSubclass(tuple):
            pass

        with self.assertRaisesRegex(ValueError, "dimensions"):
            validate_observed_dimensions(DictSubclass(census()), 33)
        with self.assertRaisesRegex(ValueError, "information rows"):
            validate_observed_dimensions(census(), 33, DictSubclass(infos()))
        with self.assertRaisesRegex(ValueError, "must be a bool"):
            validate_observed_dimensions(census(), 33, infos(), require_compact_tree_hash=1)

        cases = [
            (0, 7, ("h",)),
            (0, "not-canonical", ("h",)),
            (0, "AdAs", TupleSubclass(("h",))),
            (0, "AdAs", ("h" * 257,)),
            (0, "AdAs", tuple("x" for _ in range(33))),
            (0, "AdAs", (1,)),
        ]
        for bad_key in cases:
            with self.subTest(bad_key=bad_key):
                rows = infos()
                rows.pop(next(iter(rows)))
                rows[bad_key] = 2
                with self.assertRaisesRegex(ValueError, "shape"):
                    validate_observed_dimensions(census(), 33, rows)


if __name__ == "__main__":
    unittest.main()
