import unittest

from scripts.preflop_suit_validation import mapped_counts, verify_toy_suit_invariance


class PreflopSuitValidationTests(unittest.TestCase):
    def test_mapping_must_be_a_global_bijection_of_all_four_suits(self):
        with self.assertRaisesRegex(ValueError, "exactly c, d, h, and s"):
            mapped_counts([], {"c": "c", "d": "d", "h": "h"})
        with self.assertRaisesRegex(ValueError, "bijection"):
            mapped_counts([], {"c": "c", "d": "c", "h": "h", "s": "s"})
        with self.assertRaisesRegex(ValueError, "exactly c, d, h, and s"):
            mapped_counts([], {"c": "c", "d": "d", "h": "h", "s": "x"})

    def test_mapped_count_rows_preserve_roles_and_exact_counts(self):
        source = ({"sb_hand": "AdAs", "bb_hand": "KdKs",
                  "wins": 101, "ties": 7, "losses": 43, "boards": 151},)
        mapping = {"c": "d", "d": "h", "h": "s", "s": "c"}
        result = mapped_counts(source, mapping)
        self.assertEqual(result, ({"sb_hand": "AcAh", "bb_hand": "KcKh",
                                   "wins": 101, "ties": 7, "losses": 43,
                                   "boards": 151},))
        self.assertEqual(source[0]["sb_hand"], "AdAs")
        self.assertEqual(source[0]["bb_hand"], "KdKs")

    def test_toy_oracle_has_known_counts_and_all_24_images(self):
        evidence = verify_toy_suit_invariance()
        self.assertEqual(evidence["toy_deck_cards"], 16)
        self.assertEqual(evidence["toy_boards_per_image"], 792)
        self.assertEqual(evidence["suit_images"], 24)
        self.assertEqual(evidence["mapped_board_comparisons"], 19_008)
        self.assertEqual(evidence["source_counts"], {
            "wins": 540, "ties": 4, "losses": 248})
        self.assertTrue(evidence["all_images_match_source_counts"])
        self.assertFalse(evidence["physical_52_card_evidence"])
        self.assertEqual(len(evidence["images"]), 24)
        self.assertEqual({(row["wins"], row["ties"], row["losses"])
                          for row in evidence["images"]}, {(540, 4, 248)})

    def test_mapped_counts_rejects_corrupt_count_and_colliding_hands(self):
        identity = {suit: suit for suit in "cdhs"}
        with self.assertRaisesRegex(ValueError, "board count"):
            mapped_counts(({"sb_hand": "AdAs", "bb_hand": "KdKs",
                            "wins": 1, "ties": 0, "losses": 0, "boards": 2},), identity)
        with self.assertRaisesRegex(ValueError, "collide"):
            mapped_counts(({"sb_hand": "AdAs", "bb_hand": "AsKs",
                            "wins": 1, "ties": 0, "losses": 0},), identity)


if __name__ == "__main__":
    unittest.main()


