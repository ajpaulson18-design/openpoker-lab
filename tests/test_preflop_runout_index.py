import random
import unittest
from itertools import combinations
from unittest.mock import patch

from pokerlab import preflop_runout_index as runout_index
from pokerlab.preflop_runout_index import RunoutBlockerIndex


DECK = tuple(rank + suit for rank in "23456789TJQKA" for suit in "cdhs")
ORDER = {card: index for index, card in enumerate(DECK)}


def _canonical_runout(cards):
    flop = tuple(sorted(cards[:3], key=ORDER.__getitem__))
    return flop, cards[3], cards[4]


class RunoutBlockerIndexTests(unittest.TestCase):
    def test_randomized_masks_counts_and_indices_match_brute_force(self):
        rng = random.Random(74129)
        selected = []
        seen = set()
        while len(selected) < 173:
            runout = _canonical_runout(rng.sample(DECK, 5))
            if runout not in seen:
                seen.add(runout)
                selected.append(runout)

        index = RunoutBlockerIndex(selected)
        private_sets = [rng.sample(DECK, 4) for _ in range(30)]
        private_sets.extend((list(selected[0][0]) + [selected[0][1]],
                             list(selected[-1][0]) + [selected[-1][2]]))
        for private_cards in private_sets:
            expected = [position for position, runout in enumerate(selected)
                        if set(private_cards).isdisjoint(runout[0] + runout[1:])]
            with self.subTest(private_cards=private_cards):
                self.assertEqual(list(index.iter_valid_indices(private_cards)), expected)
                self.assertEqual(index.valid_count(private_cards), len(expected))
                self.assertEqual(index.valid_mask(private_cards),
                                 sum(1 << position for position in expected))

    def test_ordered_future_cards_and_input_positions_are_preserved(self):
        first = (("2c", "3c", "4d"), "7h", "8h")
        swapped = (("2c", "3c", "4d"), "8h", "7h")
        index = RunoutBlockerIndex((first, swapped))
        self.assertEqual(index.selected_count, 2)
        self.assertEqual(list(index.iter_valid_indices(("As", "Ad", "Ks", "Kd"))), [0, 1])
        self.assertEqual(index.valid_mask(("2c", "3c", "4d", "7h")), 0)

    def test_dense_sparse_and_partial_final_byte_masks(self):
        selected = []
        for turn, river in (("7h", "8h"), ("7h", "9h"), ("8h", "9h"),
                            ("9h", "Th"), ("Th", "Jh"), ("Jh", "Qh"),
                            ("Qh", "Kh"), ("Kh", "Ah"), ("Ah", "7h"),
                            ("8h", "Th"), ("9h", "Jh")):
            selected.append((("2c", "3c", "4d"), turn, river))
        index = RunoutBlockerIndex(selected)
        all_open = ("As", "Ad", "Ks", "Kd")
        self.assertEqual(list(index.iter_valid_indices(all_open)), list(range(11)))
        self.assertEqual(index.valid_count(("2c", "3c", "4d", "7h")), 0)
        self.assertEqual(index.valid_mask(all_open) >> index.selected_count, 0)

    def test_memory_estimate_counts_conversion_overlap(self):
        index = RunoutBlockerIndex((
            (("2c", "3c", "4d"), "7h", "8h"),
            (("2c", "3c", "4d"), "8h", "7h"),
            (("2c", "3c", "4d"), "9h", "Th"),
        ))
        expected = 52 * 1
        self.assertEqual(index.posting_payload_bytes, expected)
        self.assertEqual(index.estimated_conversion_payload_bytes, 2 * expected)
        self.assertFalse(hasattr(index, "_runouts"))

    def test_empty_malformed_duplicate_and_noncanonical_inputs_reject(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            RunoutBlockerIndex(())
        bad_cases = (
            (("2c", "3c", "4d", "7h", "8h"),),
            ((("3c", "2c", "4d"), "7h", "8h"),),
            ((("2c", "3c", "4d"), "2c", "8h"),),
            ((("2c", "3c", "4d"), "7h", "7h"),),
            ((("2c", "3c", "4d"), "7h", "8z"),),
            ((("2c", "3c", "4d"), "7h", "8h"),
             (("2c", "3c", "4d"), "7h", "8h")),
            ((("2c", "3c", "4d"), "7h"),),
        )
        for selected in bad_cases:
            with self.subTest(selected=selected):
                with self.assertRaises(ValueError):
                    RunoutBlockerIndex(selected)
        with self.assertRaisesRegex(ValueError, "four distinct"):
            RunoutBlockerIndex(( (("2c", "3c", "4d"), "7h", "8h"), )).valid_count(
                ("As", "As", "Ks", "Kd"))
        with self.assertRaises(ValueError):
            RunoutBlockerIndex(( (("2c", "3c", "4d"), "7h", "8h"), )).valid_count(
                (card for card in ("As", "Ad", "Ks", "Kd", "Qs")))

    def test_outcome_limit_rejects_before_posting_allocation(self):
        one = (("2c", "3c", "4d"), "7h", "8h")
        two = (("2c", "3c", "4d"), "8h", "7h")
        three = (("2c", "3c", "4d"), "9h", "Th")
        with patch.object(runout_index, "MAX_SELECTED_RUNOUTS", 2):
            with patch.object(runout_index, "_build_postings",
                              side_effect=AssertionError("posting allocation started")):
                with self.assertRaisesRegex(ValueError, "outcome limit"):
                    RunoutBlockerIndex(iter((one, two, three)))


if __name__ == "__main__":
    unittest.main()
