"""Rank-free admission checks for the proposed JJ/KK physical basis."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import unittest
from unittest.mock import patch

from pokerlab import native_preflop_equity as native
from scripts import preflop_five_count_reference as reference
from scripts import preflop_jj_kk_basis_plan as plan


class JJKKBasisPlanTests(unittest.TestCase):
    def test_fixed_queries_and_named_work_are_exact_and_separate(self):
        admitted = plan.admit_plan()
        self.assertEqual(admitted.ordered_pairs, (
            ("JdJs", "KdKs"),
            ("JdJs", "KcKd"),
            ("JdJs", "KcKh"),
        ))
        self.assertEqual(admitted.shared_suits_by_pair, (2, 1, 0))
        record = admitted.to_record()
        self.assertEqual(record["five_card_conformance"], {
            "rank_tuples": 2_598_960,
            "tuple_width_bytes": 6,
            "dump_bytes": 15_593_760,
            "required_mismatches": 0,
        })
        self.assertEqual(record["best_five_reference"]["boards"], 5_136_912)
        self.assertEqual(record["best_five_reference"]["seven_card_rank_calls"], 10_273_824)
        self.assertEqual(record["best_five_reference"]["five_card_subset_calls"], 215_750_304)
        self.assertEqual(record["native_seven_card_recount"]["board_evaluations"], 5_136_912)
        self.assertEqual(record["native_seven_card_recount"]["rank_calls"], 10_273_824)
        self.assertEqual(record["aggregate_admission"]["budget_version"], "preflop-jj-kk-basis-admission-v1")
        self.assertEqual(record["aggregate_admission"]["reference_count_requests"], 2)
        self.assertEqual(record["aggregate_admission"]["five_card_conformance_tuples"], 2_598_960)
        self.assertEqual(record["aggregate_admission"]["reference_board_evaluations"], 10_273_824)
        self.assertEqual(record["aggregate_admission"]["reference_seven_card_rank_calls"], 20_547_648)
        self.assertEqual(record["aggregate_admission"]["reference_five_card_subset_calls"], 431_500_608)
        self.assertEqual(record["aggregate_admission"]["native_board_evaluations"], 10_273_824)
        self.assertEqual(record["aggregate_admission"]["native_seven_card_rank_calls"], 20_547_648)
        self.assertEqual(len(record["source_basis_prerequisite"]), 4)
        self.assertTrue(record["provenance"]["candidate_only"])
        self.assertFalse(record["provenance"]["independently_authenticated"])
        self.assertFalse(record["provenance"]["counts_generated"])
        self.assertFalse(record["provenance"]["equities_claimed"])

    def test_future_108_pair_pool_forecast_respects_existing_cap_without_equity_claims(self):
        pool = plan.admit_plan().to_record()["future_mixed_pool"]
        self.assertEqual(pool["sb_hands"], 18)
        self.assertEqual(pool["bb_hands"], 6)
        self.assertEqual(pool["compatible_pairs"], 108)
        self.assertEqual(pool["maximum_positive_sign_rows"], 324)
        self.assertEqual(pool["covered_pair_cap"], 128)
        self.assertIn("forecast-only", pool["status"])

    def test_literal_query_validation_checks_canonical_cards_blockers_and_suit_hierarchy(self):
        bad_requests = []
        change = plan.expected_request()
        change["pairs"][0]["sb_hand"] = "JsJd"
        bad_requests.append(change)
        change = plan.expected_request()
        change["pairs"][0]["sb_hand"] = "JdJd"
        bad_requests.append(change)
        change = plan.expected_request()
        change["pairs"][0]["bb_hand"] = "KdJd"
        bad_requests.append(change)
        change = plan.expected_request()
        change["pairs"][0]["sb_hand"] = "JdJx"
        bad_requests.append(change)
        change = plan.expected_request()
        change["pairs"][1], change["pairs"][2] = change["pairs"][2], change["pairs"][1]
        bad_requests.append(change)
        change = plan.expected_request()
        change["pairs"][0]["bb_hand"] = "KdKc"
        bad_requests.append(change)
        for request in bad_requests:
            with self.subTest(request=request), self.assertRaises(ValueError):
                plan.admit_plan(request)

    def test_missing_duplicate_extra_reordered_and_bool_alias_requests_reject_before_any_build_lookup(self):
        malformed = []
        change = plan.expected_request()
        del change["pairs"][-1]
        malformed.append(change)
        change = plan.expected_request()
        change["pairs"][2] = deepcopy(change["pairs"][0])
        malformed.append(change)
        change = plan.expected_request()
        change["unexpected"] = "alias"
        malformed.append(change)
        change = plan.expected_request()
        change["schema_version"] = True
        malformed.append(change)
        change = plan.expected_request()
        change["pairs"] = tuple(change["pairs"])
        malformed.append(change)

        with (patch.object(reference, "backend") as reference_lookup,
              patch.object(native, "_backend") as native_lookup,
              patch.object(plan, "_live_caps", side_effect=AssertionError("late cap/source stage")) as caps):
            for request in malformed:
                with self.subTest(request=request), self.assertRaises(ValueError):
                    plan.admit_plan(request)
            reference_lookup.assert_not_called()
            native_lookup.assert_not_called()
            caps.assert_not_called()

    def test_live_reference_and_native_caps_are_checked_not_silently_overridden(self):
        with patch.object(reference, "MAX_PAIRS", 5):
            with self.assertRaisesRegex(ValueError, "caps changed"):
                plan.admit_plan()
        with patch.object(reference, "MAX_PAIRS", True):
            with self.assertRaisesRegex(ValueError, "caps changed"):
                plan.admit_plan()
        with patch.object(plan, "MAX_BOARD_EVALUATIONS", 1):
            with self.assertRaisesRegex(ValueError, "caps changed"):
                plan.admit_plan()
        with patch.object(plan, "_MAX_AGGREGATE_REFERENCE_FIVE_CALLS", True):
            with self.assertRaisesRegex(ValueError, "aggregate named-work caps"):
                plan.admit_plan()

    def test_record_is_detached_and_plan_is_frozen(self):
        admitted = plan.admit_plan()
        first = admitted.to_record()
        first["ordered_pairs"][0][0] = "bad"
        first["future_mixed_pool"]["compatible_pairs"] = 1
        second = admitted.to_record()
        self.assertEqual(second["ordered_pairs"][0], ["JdJs", "KdKs"])
        self.assertEqual(second["future_mixed_pool"]["compatible_pairs"], 108)
        with self.assertRaises(FrozenInstanceError):
            admitted.benchmark_id = "changed"

    def test_mutating_public_example_request_cannot_redefine_admission(self):
        saved = deepcopy(plan.REQUEST)
        try:
            plan.REQUEST["pairs"][0]["bb_hand"] = "JdJs"
            self.assertEqual(plan.admit_plan().ordered_pairs[0], ("JdJs", "KdKs"))
            with self.assertRaises(ValueError):
                plan.admit_plan(plan.REQUEST)
        finally:
            plan.REQUEST.clear()
            plan.REQUEST.update(saved)


if __name__ == "__main__":
    unittest.main()
