"""Short, actual-profile gates for the isolated turn-cache benchmark."""
import copy
import json
import unittest
from fractions import Fraction

from scripts import benchmark_turn_terminal_cache as benchmark


class BenchmarkTurnTerminalCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pinned = benchmark._verify_pinned_inputs()
        cls.profiles = {}
        for case_id in benchmark.SCENARIOS:
            case = benchmark._case(case_id)
            baseline = benchmark._solve(case, 10, cached=False)
            candidate = benchmark._solve(case, 10, cached=True)
            cls.profiles[case_id] = (case, baseline, candidate)

    def test_actual_short_payload_parity_replay_and_threshold_reporting(self):
        for case_id, (case, baseline, candidate) in self.profiles.items():
            with self.subTest(case=case_id):
                benchmark._validate_profile(baseline, case, 10, cached=False)
                benchmark._validate_profile(candidate, case, 10, cached=True)
                self.assertEqual(benchmark._json_bytes(baseline),
                                 benchmark._json_bytes(benchmark._legacy_payload(candidate)))
                oracle, differences = benchmark._replay(candidate, case)
                self.assertEqual(set(differences), set(benchmark.METRICS))
                self.assertTrue(all(abs(delta) <= 1e-9 for delta in differences.values()))
                evidence = benchmark._profile_evidence(
                    candidate, oracle, differences, case_id, 10, "test")
                self.assertEqual(set(evidence["independent_metrics"]), set(benchmark.METRICS))
                self.assertEqual(evidence["physical_counts"]["worlds"], oracle["world_count"])
                self.assertEqual(evidence["benchmark_nash_conv_threshold"], 0.001)
                self.assertEqual(
                    evidence["benchmark_nash_conv_threshold_met"],
                    oracle["nash_conv"] <= 0.001,
                )

    def test_validator_rejects_corrupt_counts_rows_and_cache_admission(self):
        for case_id, (case, _baseline, candidate) in self.profiles.items():
            corruptions = []
            wrong_mode = copy.deepcopy(candidate)
            wrong_mode["runout_mode"] = "none"
            corruptions.append(wrong_mode)
            wrong_info_count = copy.deepcopy(candidate)
            wrong_info_count["info_sets"] += 1
            corruptions.append(wrong_info_count)
            for malformed in corruptions:
                with self.subTest(case=case_id, field=malformed.get("runout_mode")):
                    with self.assertRaises(ValueError):
                        benchmark._replay(malformed, case)

            for field, bad in (
                ("terminal_count", candidate["terminal_cache"]["terminal_count"] + 1),
                ("reserved_calls", candidate["terminal_cache"]["reserved_calls"] + 1),
                ("hits", True),
                ("entries_after_cleanup", 1),
                ("logical_payload_bytes_upper_bound", 0),
            ):
                altered = copy.deepcopy(candidate)
                altered["terminal_cache"][field] = bad
                with self.subTest(case=case_id, cache_field=field):
                    with self.assertRaises(ValueError):
                        benchmark._validate_profile(altered, case, 10, cached=True)

    def test_selected_3k_archive_matches_exact_normalized_fraction_certificate(self):
        case = benchmark._case(benchmark.SELECTED_ID)
        archived_path = (benchmark.SELECTED_POLICY_DIR /
                         benchmark.SELECTED_3K_POLICY_NAME)
        payload = archived_path.read_bytes()
        self.assertEqual(benchmark._sha256(payload), benchmark.SELECTED_3K_POLICY_SHA256)
        archived = json.loads(payload.decode("utf-8"))
        evidence = benchmark._exact_selected_3k(archived, case, self.pinned)
        self.assertTrue(evidence["exact_nash_conv_threshold_met"])
        self.assertEqual(evidence["normalized_policy_sha256"],
                         benchmark.RATIONAL_EXPECTED_NORMALIZED_SHA256)
        self.assertAlmostEqual(
            float(Fraction(evidence["exact_metrics"]["nash_conv"])),
            0.00047081004655702104,
            delta=1e-12,
        )

    def test_independent_terminal_and_branch_dimensions_match_preflight_model(self):
        self.assertEqual(
            benchmark._independent_terminal_count(benchmark._case(benchmark.SELECTED_ID)),
            (107, 2),
        )
        self.assertEqual(
            benchmark._independent_terminal_count(benchmark._case(benchmark.FULL_ID)),
            (722, 48),
        )
        selected_calls = 107 * (2 * 1_000 + 4)
        selected_setup = 16 * 2 + 64
        full_calls = 722 * (2 * 1_000 + 4)
        full_setup = 16 * 48 + 64
        self.assertEqual(selected_calls * 20 + selected_setup, 4_288_656)
        self.assertEqual(full_calls * 20 + full_setup, 28_938_592)

    def test_reduced_pair_loop_retains_results_and_checks_complete_parity(self):
        case = benchmark._case(benchmark.SELECTED_ID)
        rows, first, samples = benchmark._run_paired_calls(
            case, 10, (("baseline", "ranked-lru"),))
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(first), {"baseline", "ranked-lru"})
        self.assertEqual(set(samples), {"baseline", "ranked-lru"})
        self.assertEqual(len(samples["baseline"]), 1)
        self.assertEqual(len(samples["ranked-lru"]), 1)
        baseline = first["baseline"]["result"]
        candidate = first["ranked-lru"]["result"]
        self.assertEqual(benchmark._json_bytes(baseline),
                         benchmark._json_bytes(benchmark._legacy_payload(candidate)))
        self.assertEqual(rows[0]["baseline_payload_sha256"],
                         first["baseline"]["sha256"])
        oracle, differences = benchmark._replay(candidate, case)
        self.assertEqual(set(differences), set(benchmark.METRICS))
        self.assertEqual(oracle["world_count"], 8)

    def test_parent_verification_does_not_apply_historical_production_pin(self):
        # The old timing CLI remains source-pinned through _verify_parents();
        # this current harness verifies archive bytes and fixtures separately.
        reports = benchmark.old_benchmark._verify_parent_archive()
        self.assertEqual(set(reports), set(benchmark.SCENARIOS))
        with self.assertRaises(ValueError):
            benchmark.old_benchmark._verify_parents()


if __name__ == "__main__":
    unittest.main()
