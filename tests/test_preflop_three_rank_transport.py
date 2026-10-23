"""Candidate admission and physical prepared-count pooling; no board counts."""
from fractions import Fraction
import unittest
from unittest.mock import patch

from scripts import preflop_three_rank_transport as candidate
from scripts import preflop_three_rank_transport_validation as independent


class ThreeRankTransportCandidateTests(unittest.TestCase):
    def test_complete_literal_admission_rejects_before_authentication_or_pooling(self):
        invalid = candidate.expected_request()
        invalid["schema_version"] = True
        with (patch.object(candidate, "_source_tables", side_effect=AssertionError("source I/O")),
              patch.object(candidate.covered, "pool_preflop_equities_by_suit",
                           side_effect=AssertionError("pooling"))):
            with self.assertRaises(ValueError):
                candidate.build_candidate(invalid)

    def test_rank_free_admission_keeps_literal_caps_and_global_priors(self):
        hands, pairs = candidate.admit()
        self.assertEqual((len(hands[0]), len(hands[1]), len(pairs)), (18, 6, 108))
        self.assertEqual(sum((prior for _, _, prior in pairs), Fraction()), 1)
        for i, _, prior in pairs:
            self.assertEqual(prior, {"A": Fraction(1, 63), "Q": Fraction(1, 126),
                                     "J": Fraction(1, 252)}[hands[0][i][0][0]])
        with patch.object(candidate.covered, "MAX_PAIRS", 129):
            with self.assertRaisesRegex(ValueError, "caps changed"):
                candidate.admit()

    def test_real_saved_bases_pool_all_108_pairs_without_ranking_or_training(self):
        with (patch.object(candidate.jj, "_current_source_check"),
              patch("pokerlab.preflop_full_board_equity.rank_hand", side_effect=AssertionError("rank")),
              patch("pokerlab.native_preflop_equity.prepare_native_preflop_equities",
                    side_effect=AssertionError("native count")),
              patch("scripts.preflop_five_count_reference.reference_preflop_counts",
                    side_effect=AssertionError("reference count")),
              patch("pokerlab.cfr_plus.train", side_effect=AssertionError("training"))):
            report = candidate.build_candidate()
        self.assertEqual(report["status"], "candidate-only")
        self.assertEqual(report["row_count"], 108)
        self.assertEqual(sum((Fraction(row["prior_fraction"]) for row in report["rows"]), Fraction()), 1)
        self.assertEqual({rank: sum(row["sb_hand"][0] == rank for row in report["rows"])
                          for rank in "AQJ"}, {"A": 36, "Q": 36, "J": 36})
        with (patch.object(candidate.jj, "_current_source_check"),
              patch.object(candidate, "build_candidate", side_effect=AssertionError("candidate reuse")),
              patch.object(candidate.covered, "pool_preflop_equities_by_suit",
                           side_effect=AssertionError("production pool")),
              patch.object(candidate.covered, "_ranges", side_effect=AssertionError("pool admission"))):
            checked = independent.verify_candidate_report(report)
        self.assertEqual(checked["physical_pair_rows_authenticated"], 108)
        self.assertEqual(checked["exact_global_prior_mass"], "1")
        self.assertIs(checked["equilibrium_or_policy_claim"], False)


if __name__ == "__main__":
    unittest.main()
