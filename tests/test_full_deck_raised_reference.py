"""Independent full-deck physics, carried-wager and frozen-reference regressions."""
from collections import defaultdict
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import full_deck_raised_reference as reference


class FullDeckRaisedReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.accepted = reference.verify_saved_artifact()

    def test_independent_model_checks_full_physical_law_and_carried_wagers(self):
        with patch("pokerlab.postflop_solver._build_postflop_tree", side_effect=AssertionError("Production tree used")), \
             patch("pokerlab.postflop_solver.solve_postflop", side_effect=AssertionError("Production solver used")), \
             patch("pokerlab.matrix_free_turn.solve_matrix_free_turn", side_effect=AssertionError("Production solver used")):
            value = reference.reconstruct()
        self.assertEqual(value["training_calls"], 0)
        self.assertEqual(value["all_check_policy_value_fraction"], "-2500/231")
        self.assertEqual([(r["wins"], r["ties"], r["losses"]) for r in value["physical_pairs"]],
                         [(0, 44, 0), (42, 0, 2), (2, 0, 42), (0, 44, 0)])
        self.assertEqual(value["carried_raise_witness"]["river_wager"], 70)
        self.assertEqual(value["carried_raise_witness"]["matched_showdown_contributions"], [220, 220])

    def test_production_structure_matches_independent_numeric_tree_and_physics(self):
        from scripts import full_deck_raised_fixture as candidate
        census = candidate.census()
        expected = self.accepted["reference"]
        self.assertEqual(census.public_nodes, expected["public_nodes"])
        self.assertEqual(census.decisions, expected["public_decisions"])
        self.assertEqual(census.information_rows, expected["information_rows"])
        self.assertEqual(census.public_tree_sha256, expected["public_tree_sha256"])

    def test_a_future_river_cannot_split_a_turn_information_set(self):
        f, board, config, worlds, selected, root, _ = reference.model()
        rows = reference._policy_rows(reference._walk(root), worlds)
        turn = next(row for row in rows if row["street"] == "turn")
        turn["history"].append("river@2c")
        result = dict(board=list(board), runouts=list(selected), runout_mode="full-deck",
                      reachable_runouts=sorted({w["river"] for w in worlds}),
                      strategy=rows, info_sets=2404)
        with self.assertRaisesRegex(ValueError, "row set mismatch"):
            reference.rules.replay_policy(result, f["oop"], f["ip"],
                                          board=f["board"], config=config)

    def test_future_aware_turn_max_before_river_integration_is_strictly_illegal(self):
        # A legal turn choice is made before the river: aggregate every river's
        # signed mass for an own hand, then choose between t=0 and t=50. This
        # counterfactual chooses t after seeing the river, while still summing
        # hidden opponent hands into each own-hand/river signed mass.
        _, _, _, worlds, _, _, _ = reference.model()
        legal_oop, legal_ip = reference.check_call_response_bounds(worlds)
        self.assertEqual((legal_oop, legal_ip), (F(2350, 231), F(14975, 231)))

        future_aware = []
        for player in (0, 1):
            by_hand_and_river = defaultdict(lambda: defaultdict(F))
            for world in worlds:
                by_hand_and_river[world["hands"][player]][world["river"]] += (
                    world["weight"] * world["sign"])
            turn_choice = max if player == 0 else min
            signed_response = F(0)
            for by_river in by_hand_and_river.values():
                for signed_mass in by_river.values():
                    # At the river, choose b=0 or b=50+t. The resulting
                    # coefficient is then multiplied by 50 or 100 for the
                    # turn investment t=0 or t=50.
                    river_coefficient = signed_mass + turn_choice(F(0), signed_mass)
                    signed_response += turn_choice(
                        50 * river_coefficient, 100 * river_coefficient)
            future_aware.append(signed_response if player == 0 else -signed_response)

        illegal_oop, illegal_ip = future_aware
        self.assertEqual((illegal_oop, illegal_ip), (F(2825, 231), F(15325, 231)))
        self.assertGreater(illegal_oop, legal_oop)
        self.assertGreater(illegal_ip, legal_ip)

    def test_self_consistent_false_reference_and_changed_sources_are_rejected(self):
        for change in (
            lambda report: report["reference"].update(all_check_policy_value_fraction="0"),
            lambda report: report["reference"]["carried_raise_witness"].update(river_wager=220),
            lambda report: report["source_sha256"].update({reference.SOURCE_PATHS[0]: "0" * 64}),
        ):
            saved = deepcopy(self.accepted)
            change(saved)
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "changed.json"
                path.write_bytes(reference.canonical(saved))
                with self.assertRaises(ValueError):
                    reference.verify_saved_artifact(path)

    def test_historical_generation_commit_is_metadata_and_live_head_must_be_stable(self):
        saved = deepcopy(self.accepted)
        saved["baseline_git_commit"] = "a" * 40
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "historical.json"
            path.write_bytes(reference.canonical(saved))
            reference.verify_saved_artifact(path)
            with patch.object(reference, "head", side_effect=["a" * 40, "b" * 40]):
                with self.assertRaisesRegex(ValueError, "HEAD"):
                    reference.verify_saved_artifact(path)

    def test_report_byte_admission_precedes_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "too-large.json"
            path.write_bytes(b" " * (reference.MAX_REPORT_BYTES + 1))
            with patch.object(Path, "read_bytes", side_effect=AssertionError("Oversized input read")):
                with self.assertRaisesRegex(ValueError, "byte cap"):
                    reference.verify_saved_artifact(path)


if __name__ == "__main__":
    unittest.main()
