"""Toy-only tests for the staging flop public class candidate builder."""
from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import flop_public_classes_candidate as CANDIDATE

MODULE_PATH = Path(CANDIDATE.__file__)

BOARD = ("2c", "3d", "4h")
TURNS = ("5c", "5d")
RIVERS = ("6c", "6d")
PAIRS = (
    ("AsAd", "KsKd", "1/2"),
    ("QsQd", "JhJc", "1/3"),
    ("TcTh", "AcAh", "1/6"),
)
SIGNS = {
    "6c": (1, -1, 0),
    "6d": (-1, 1, 0),
}


def _worlds():
    rows = []
    for pair_index, (oop, ip, pair_mass) in enumerate(PAIRS):
        share = CANDIDATE.Fraction(pair_mass) / 4
        for turn in TURNS:
            for river in RIVERS:
                rows.append([oop, ip, str(share), SIGNS[river][pair_index],
                             [*BOARD, turn, river]])
    return rows


class FlopPublicClassesCandidateTests(unittest.TestCase):
    def test_symmetric_weighted_toy_merges_turns_and_preserves_pair_marginals(self):
        rows = _worlds()
        candidate = CANDIDATE.build_candidate(rows, board=BOARD)
        self.assertTrue(candidate["candidate_only"])
        self.assertEqual(candidate["physical_world_count"], 12)
        self.assertEqual(candidate["compatible_pair_count"], 3)
        self.assertEqual(candidate["turn_card_count"], 2)
        self.assertEqual(candidate["turn_class_count"], 1)
        self.assertEqual(candidate["river_class_count"], 2)
        self.assertEqual(len(candidate["class_worlds"]), 6)
        self.assertEqual(candidate["physical_mass"], [1, 1])
        self.assertEqual(
            [(row["oop_hand"], row["ip_hand"], row["marginal_mass"])
             for row in candidate["pairs"]],
            [(oop, ip, [CANDIDATE.Fraction(weight).numerator,
                        CANDIDATE.Fraction(weight).denominator])
             for oop, ip, weight in sorted(PAIRS, key=lambda row: row[:2])],
        )
        one = candidate["turn_classes"][0]
        self.assertEqual(one["members"], list(TURNS))
        self.assertEqual(len(one["river_transports"]), 4)
        self.assertEqual(sum(row["physical_world_count"]
                             for row in candidate["class_worlds"]), 12)

    def test_changed_one_pair_river_posterior_splits_turn_classes(self):
        rows = _worlds()
        # Shift mass within one pair's 5d turn while preserving that pair's
        # total marginal. Exact river signatures now differ between turns.
        target = [row for row in rows
                  if row[0] == "AsAd" and row[3] == 1 and row[4][3] == "5d"][0]
        target[2] = "3/16"
        other = [row for row in rows
                 if row[0] == "AsAd" and row[3] == -1 and row[4][3] == "5d"][0]
        other[2] = "1/16"
        candidate = CANDIDATE.build_candidate(rows, board=BOARD)
        self.assertEqual(candidate["turn_class_count"], 2)
        self.assertEqual(candidate["physical_mass"], [1, 1])
        self.assertEqual(len(candidate["class_worlds"]), 12)

    def test_changed_sign_vector_splits_turn_classes(self):
        rows = _worlds()
        target = next(row for row in rows
                      if row[0] == "AsAd" and row[4][3:] == ["5d", "6c"])
        target[3] = -1
        candidate = CANDIDATE.build_candidate(rows, board=BOARD)
        self.assertEqual(candidate["turn_class_count"], 2)

    def test_duplicate_or_malformed_physical_rows_reject(self):
        rows = _worlds()
        for mutate in (
            lambda values: values.append(list(values[0])),
            lambda values: values[0].__setitem__(2, "-1/8"),
            lambda values: values[0].__setitem__(2, True),
            lambda values: values[0].__setitem__(3, True),
            lambda values: values[0].__setitem__(4, [*BOARD, "5c", "5c"]),
            lambda values: values[0].__setitem__(4, ["2c", "3d", "4s", "5c", "6c"]),
        ):
            bad = [list(row) for row in rows]
            mutate(bad)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                CANDIDATE.build_candidate(bad, board=BOARD)

    def test_mass_text_and_integer_limits_apply_before_fraction_construction(self):
        with patch.object(CANDIDATE, "Fraction",
                          side_effect=AssertionError("Fraction construction must not run")):
            with self.assertRaisesRegex(ValueError, "text exceeds its size limit"):
                CANDIDATE._mass("9" * 10_000)
            with self.assertRaisesRegex(ValueError, "bit limit"):
                CANDIDATE._mass("9" * CANDIDATE.MAX_MASS_COMPONENT_DIGITS)

    def test_input_permutation_has_identical_candidate_serialization(self):
        rows = _worlds()
        forward = CANDIDATE.build_candidate(rows, board=BOARD)
        reverse = CANDIDATE.build_candidate(list(reversed(rows)), board=BOARD)
        self.assertEqual(forward, reverse)

    def test_same_physical_pair_requires_consistent_hand_labels(self):
        rows = _worlds()
        rows[1][0] = "AdAs"
        with self.assertRaisesRegex(ValueError, "inconsistent hand labels"):
            CANDIDATE.build_candidate(rows, board=BOARD)

    def test_partial_input_is_accepted_only_as_unverified_candidate_data(self):
        partial = [["AsAd", "KsKd", "1", 1, [*BOARD, "5c", "6c"]]]
        candidate = CANDIDATE.build_candidate(partial, board=BOARD)
        self.assertEqual(candidate["physical_world_count"], 1)
        self.assertTrue(candidate["candidate_only"])
        self.assertEqual(candidate["input_completeness"],
                         "unverified-caller-supplied-records")
        self.assertIs(candidate["physical_provenance"], False)
        self.assertIn("No ranking, physical provenance", candidate["scope"])

    def test_candidate_rejects_non_unit_global_mass_and_pair_overlap(self):
        rows = _worlds()
        rows[0][2] = "1/7"
        with self.assertRaisesRegex(ValueError, "sum globally"):
            CANDIDATE.build_candidate(rows, board=BOARD)

        bad = _worlds()
        bad[0][1] = "AsKh"
        with self.assertRaisesRegex(ValueError, "private hands overlap"):
            CANDIDATE.build_candidate(bad, board=BOARD)

    def test_source_compiles_without_using_any_solver_or_ranker(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        compile(source, str(MODULE_PATH), "exec")
        self.assertNotIn("pokerlab", source)
        self.assertNotIn("rank_hand", source)
        self.assertNotIn("solve_postflop", source)


if __name__ == "__main__":
    unittest.main()
