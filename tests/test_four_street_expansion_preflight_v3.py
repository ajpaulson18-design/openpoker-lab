from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch

from pokerlab import four_street_solver, preflop_solver
from scripts import benchmark_four_street_integration as runner
from scripts import four_street_certificate_v3 as certificate
from scripts import four_street_expansion_preflight as preflight_v2
from scripts import four_street_expansion_preflight_v3 as preflight_v3


ROOT = Path(__file__).resolve().parents[1]
V2_CORE_FIELDS = {
    "schema", "benchmark_id", "outcome", "quality_gate",
    "production_calls_entered", "attempted_training", "case", "request",
    "production_admission", "independent_admission", "support_comparison",
    "first_rejection",
}
V2_RECEIPT_SHA256 = "0025236b3c71c23991bd2b0db6df95ba7b84d89e786d7041daaabeb8c63334ba"


class FourStreetExpansionPreflightV3Tests(unittest.TestCase):

    def test_default_v2_core_matches_byte_authenticated_preserved_receipt(self):
        receipt_path = (ROOT / "benchmarks" / "results" /
                        "four-street-expansion-preflight-v2" / "receipt.json")
        receipt_bytes = receipt_path.read_bytes()
        self.assertEqual(hashlib.sha256(receipt_bytes).hexdigest(), V2_RECEIPT_SHA256)
        preserved = json.loads(receipt_bytes)
        expected_core = {key: preserved[key] for key in V2_CORE_FIELDS}
        self.assertEqual(set(expected_core), V2_CORE_FIELDS)

        actual = preflight_v2.prepare_expansion()
        actual_core = {key: actual[key] for key in V2_CORE_FIELDS}
        self.assertEqual(set(actual_core), V2_CORE_FIELDS)
        self.assertEqual(actual_core, expected_core)

    def test_fixed_v2_v3_v2_interleaving_and_candidate_identity(self):
        before = preflight_v2.prepare_expansion()
        corrected = preflight_v3.prepare_expansion()
        after = preflight_v2.prepare_expansion()

        self.assertEqual(before, after)
        self.assertEqual(before["schema"], "four-street-expansion-preflight-v1")
        self.assertEqual(corrected["schema"], "four-street-expansion-preflight-v2")
        self.assertEqual(corrected["independent_admission"]["schema"],
                         "four-street-expansion-independent-admission-v2")
        self.assertEqual(corrected["benchmark_id"], "four-street-shared-river-expansion-v2")
        self.assertEqual(corrected["validator_entrypoint"], "scripts.four_street_certificate_v3.forecast_exact")
        self.assertEqual(corrected["source_identity"], certificate.SOURCE_IDENTITY)
        self.assertEqual(corrected["budget_schedule_version"], certificate.BUDGET_SCHEDULE_VERSION)
        baseline_case = runner._literal_case()
        expected_case = dict(baseline_case)
        expected_case["id"] = "four-street-shared-river-expansion-v2"
        expected_case["runouts"] = [*baseline_case["runouts"], "5c6d7s8cKc"]
        self.assertEqual(corrected["case"], expected_case)
        expected_request = runner._literal_request().to_dict()
        expected_request["runouts"] = expected_case["runouts"]
        self.assertEqual(corrected["request"], expected_request)
        self.assertFalse(corrected["attempted_training"])
        self.assertEqual(corrected["production_calls_entered"], 0)
        self.assertIsNone(corrected["quality_gate"])

    def test_real_facade_has_trainer_tripwires_and_exact_support_identities(self):
        calls = []

        def forbidden(*_args, **_kwargs):
            calls.append(True)
            raise AssertionError("preflight entered production solving or training")

        owners = (
            (preflop_solver, "solve_preflop"),
            (preflop_solver, "train_public_batched"),
            (preflop_solver, "train_cfrplus"),
            (preflop_solver, "train_planned"),
            (preflop_solver, "train_delayed_public_cfrplus"),
            (preflop_solver, "train_chance_sampled"),
            (preflop_solver, "evaluate_public_profile"),
            (preflop_solver.cfr, "train"),
            (four_street_solver, "solve_four_street"),
            (runner, "solve_four_street"),
        )
        with ExitStack() as stack:
            for owner, name in owners:
                stack.enter_context(patch.object(owner, name, side_effect=forbidden))
            receipt = preflight_v3.prepare_expansion()
        self.assertEqual(calls, [])
        self.assertFalse(receipt["attempted_training"])
        self.assertEqual(receipt["production_calls_entered"], 0)
        independent = receipt["independent_admission"]
        forecast = independent["forecast"]
        self.assertEqual(forecast["source_identity"], certificate.SOURCE_IDENTITY)
        self.assertEqual(forecast["budget_schedule_version"], certificate.BUDGET_SCHEDULE_VERSION)
        self.assertEqual(independent["counts"]["worlds"], 26)
        self.assertEqual(receipt["support_comparison"]["worlds_compared"], 26)
        self.assertEqual(receipt["support_comparison"]["pairs_compared"], 4)
        self.assertTrue(receipt["support_comparison"]["support_matches"])
        expected_counts = {"worlds": forecast["worlds"],
                           "public_states": forecast["tree_nodes"],
                           "decisions": forecast["tree_decisions"],
                           "information_rows": forecast["information_rows"],
                           "action_slots": forecast["action_slots"]}
        self.assertEqual(independent["counts"], expected_counts)
        self.assertEqual(receipt["outcome"] == "admitted", forecast["admitted"])
        self.assertEqual(receipt["preparation_accounting"]["independent_model_build_paths"], [
            "explicit numeric.build_model support and count build",
            "fresh v3 exact forecaster graph and census build",
        ])
        accounting = receipt["preparation_accounting"]
        self.assertTrue(accounting["forecaster_preparation_cap_is_not_whole_preflight_cap"])
        prep_receipts = accounting["forecaster_preparation_receipts"]
        self.assertIn("terminal_group_census", prep_receipts)
        self.assertIn("aggregate_preparation", prep_receipts)

    def test_wrong_forecaster_identity_rejects_after_support_comparison(self):
        original = certificate.forecast_exact

        def wrong_identity(case):
            forecast = original(case)
            forecast["source_identity"] = "wrong-source"
            return forecast

        with patch.object(preflight_v3, "_forecast", side_effect=wrong_identity):
            receipt = preflight_v3.prepare_expansion()
        self.assertEqual(receipt["first_rejection"]["stage"], "exact-work-forecast-identity")
        self.assertIsNotNone(receipt["independent_admission"]["forecast"])
        self.assertTrue(receipt["support_comparison"]["support_matches"])
        self.assertEqual(receipt["outcome"], "rejected")

    def test_public_facades_reject_operator_and_mode_injection(self):
        with self.assertRaises(TypeError):
            preflight_v3.prepare_expansion(lambda _case: {})
        with self.assertRaises(TypeError):
            preflight_v3.prepare_expansion(mode="v2")
        with self.assertRaises(TypeError):
            preflight_v3.run_preflight("0" * 40, "unused", forecast_operator=lambda _case: {})

    def test_first_production_failure_and_v2_schema_are_preserved(self):
        failure = RuntimeError("inert admission failure")
        with patch.object(runner, "_production_admission", side_effect=failure):
            receipt = preflight_v3.prepare_expansion()
        self.assertEqual(receipt["first_rejection"], {
            "stage": "production-admission",
            "error_type": "RuntimeError",
            "message": "inert admission failure",
        })
        self.assertEqual(receipt["schema"], "four-street-expansion-preflight-v2")
        self.assertFalse(receipt["attempted_training"])


if __name__ == "__main__":
    unittest.main()
