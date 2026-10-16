"""Short, actual-profile gates for the terminal memoization harness."""
import copy
import unittest

from scripts import benchmark_turn_terminal_memoization as benchmark


class BenchmarkTurnTerminalMemoizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Exercise the actual matrix-free APIs and serialized results. Keeping
        # these tiny solves cached makes each mutation test deterministic and
        # avoids fabricated solver metadata.
        # Keep immutable archive/policy/fixture checks in routine regression
        # tests. The old timing CLI still applies its strict historical source
        # gate through _verify_parents(); current solver edits must not rewrite
        # or silently rebaseline that experiment.
        benchmark._verify_parent_archive()
        cls.profiles = {}
        for case_id in (benchmark.SELECTED_ID, benchmark.FULL_ID):
            case = benchmark._frozen_case(case_id)
            baseline = benchmark._solve_baseline(case, 10)
            candidate, stats = benchmark._solve_memoized(case, 10)
            benchmark._validate_fixed_result(baseline, case, 10)
            benchmark._validate_fixed_result(candidate, case, 10)
            cls.profiles[case_id] = (case, baseline, candidate, stats)

    def test_actual_short_profiles_match_and_replay_all_metrics(self):
        for case_id, (case, baseline, candidate, stats) in self.profiles.items():
            with self.subTest(case=case_id):
                self.assertEqual(benchmark._json_bytes(baseline),
                                 benchmark._json_bytes(candidate))
                oracle, differences = benchmark._replay(candidate, case)
                self.assertEqual(set(differences), set(benchmark.METRICS))
                self.assertTrue(all(abs(value) <= 1e-9
                                    for value in differences.values()))
                evidence = benchmark._independent_profile_fields(oracle)
                self.assertEqual(set(evidence["independent_metrics"]),
                                 set(benchmark.METRICS))
                self.assertEqual(evidence["independent_worlds"], oracle["worlds"])
                self.assertEqual(evidence["checked_information_sets"],
                                 oracle["checked_information_sets"])
                self.assertEqual(evidence["benchmark_nash_conv_threshold"], 0.001)
                self.assertEqual(
                    evidence["benchmark_nash_conv_threshold_met"],
                    oracle["nash_conv"] <= 0.001,
                )
                self.assertGreater(stats["inner_values_calls"], 0)
                self.assertEqual(stats["inner_values_calls"],
                                 stats["cache_hits"] + stats["cache_misses"])
                self.assertEqual(stats["logical_slot_work"],
                                 stats["inner_values_calls"] *
                                 benchmark.CACHE_SLOTS_PER_CALL)
                self.assertGreaterEqual(oracle["worlds"], 1)

    def test_replay_rejects_mutated_runout_and_physical_count_metadata(self):
        for case_id, (case, _baseline, candidate, _stats) in self.profiles.items():
            mutations = []
            wrong_mode = copy.deepcopy(candidate)
            wrong_mode["runout_mode"] = "none"
            mutations.append(wrong_mode)
            wrong_reachable = copy.deepcopy(candidate)
            wrong_reachable["reachable_runouts"] = ["2c"]
            mutations.append(wrong_reachable)
            wrong_runouts = copy.deepcopy(candidate)
            wrong_runouts["runouts"] = ["2c"]
            mutations.append(wrong_runouts)
            wrong_worlds = copy.deepcopy(candidate)
            wrong_worlds["worlds"] = True
            mutations.append(wrong_worlds)
            for malformed in mutations:
                with self.subTest(case=case_id,
                                  mode=malformed.get("runout_mode"),
                                  runouts=malformed.get("runouts"),
                                  worlds=malformed.get("worlds")):
                    with self.assertRaises(ValueError):
                        benchmark._replay(malformed, case)

    def test_harness_rejects_bad_fixed_metadata_and_canonical_fixture_aliases(self):
        for case_id, (case, _baseline, candidate, _stats) in self.profiles.items():
            with self.subTest(case=case_id):
                boolean_iteration = copy.deepcopy(candidate)
                boolean_iteration["iterations"] = True
                with self.assertRaises(ValueError):
                    benchmark._validate_fixed_result(boolean_iteration, case, 10)
                wrong_board = copy.deepcopy(candidate)
                wrong_board["board"][0] = "2c"
                with self.assertRaises(ValueError):
                    benchmark._validate_fixed_result(wrong_board, case, 10)

        changed = copy.deepcopy(benchmark.EXPECTED_CASES[benchmark.SELECTED_ID])
        changed["config"]["max_raises"] = False
        with self.assertRaisesRegex(ValueError, "canonical model"):
            benchmark._validate_case(changed)

    def test_counter_validator_rejects_malformed_or_over_cap_copies(self):
        for case_id, (_case, _baseline, _candidate, stats) in self.profiles.items():
            with self.subTest(case=case_id):
                benchmark._validate_memoizer_stats(
                    benchmark._frozen_case(case_id), stats, 10
                )
                for field, invalid in (
                    ("inner_values_calls", True),
                    ("logical_slot_work", stats["logical_slot_limit"] + 20),
                    ("current_entries", 1),
                    ("entries_after_cleanup", 1),
                    ("cache_hits", stats["cache_hits"] + 1),
                    ("maximum_entries", stats["cache_entry_limit"] + 1),
                ):
                    altered = dict(stats)
                    altered[field] = invalid
                    with self.subTest(field=field):
                        with self.assertRaises(ValueError):
                            benchmark._validate_memoizer_stats(
                                benchmark._frozen_case(case_id), altered, 10
                            )


if __name__ == "__main__":
    unittest.main()
