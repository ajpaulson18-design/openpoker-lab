"""Cheap full-deck harness checks backed by actual ten-sweep profiles."""
import copy
import unittest

from scripts.benchmark_full_deck_turn_accuracy import (
    ALGORITHM,
    BACKENDS,
    EXPECTED_CASE,
    EXPECTED_CANDIDATE_RUNOUTS,
    EXPECTED_INFORMATION_SETS,
    EXPECTED_MATRIX_ACTION_SLOTS,
    EXPECTED_MATRIX_FOLD_TERMINALS,
    EXPECTED_MATRIX_HAND_COUNTS,
    EXPECTED_MATRIX_HAND_SLOTS,
    EXPECTED_PAIRS,
    EXPECTED_PUBLIC_STATES,
    EXPECTED_REACHABLE_RUNOUTS,
    EXPECTED_WORLDS,
    ITERATIONS,
    MAX_MATRIX_LIMITS,
    MAX_WORLD_NODE_WORK,
    _accepted_replay,
    _full_deck_candidates,
    expected_work,
    frozen_case,
    solve,
    validate_profile_metadata,
)


class FullDeckTurnAccuracyHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = frozen_case()
        # Use actual solver payloads, not synthetic resource/count fixtures.
        cls.profiles = {
            backend: solve(cls.case, backend, ALGORITHM, 10)
            for backend in BACKENDS
        }
        for backend in BACKENDS:
            validate_profile_metadata(cls.profiles[backend], cls.case, backend, 10)

    def _profile(self, backend):
        return copy.deepcopy(self.profiles[backend])

    def test_frozen_fixture_uses_full_deck_not_selected_runouts(self):
        self.assertEqual(self.case["id"], EXPECTED_CASE["id"])
        self.assertEqual(self.case["board"], "Js8d4c2h")
        self.assertNotIn("runouts", self.case)
        self.assertEqual(len(_full_deck_candidates(self.case)), EXPECTED_CANDIDATE_RUNOUTS)
        self.assertEqual(EXPECTED_REACHABLE_RUNOUTS, 48)
        self.assertEqual(self.case["config"], self.case["river_config"])
        self.assertEqual(self.case["config"]["bet_sizes"], [0.75])
        self.assertEqual(self.case["config"]["raise_sizes"], [])
        self.assertFalse(self.case["config"]["include_all_in"])

    def test_fixed_full_budget_formulas_and_caps_are_backend_specific(self):
        expected_matrix = {1_000: 7_837_830, 1_500: 11_752_830,
                           3_000: 23_497_830}
        expected_materialized = {1_000: 8_448_000, 1_500: 12_672_000,
                                 3_000: 25_344_000}
        for iterations in ITERATIONS:
            self.assertEqual(expected_work("matrix-free", iterations),
                             expected_matrix[iterations])
            self.assertEqual(expected_work("materialized", iterations),
                             expected_materialized[iterations])
            self.assertLess(expected_work("matrix-free", iterations),
                            MAX_MATRIX_LIMITS["hand_state_pass_work"])
            self.assertLess(expected_work("materialized", iterations),
                            MAX_WORLD_NODE_WORK)
        self.assertEqual(EXPECTED_WORLDS, 176)
        self.assertEqual(EXPECTED_PAIRS, 4)
        self.assertEqual(EXPECTED_INFORMATION_SETS, 1_112)
        self.assertEqual(EXPECTED_PUBLIC_STATES, 1_305)

    def test_cached_actual_profiles_pass_metadata_and_independent_full_deck_replay(self):
        for backend in BACKENDS:
            with self.subTest(backend=backend):
                result = self._profile(backend)
                oracle, differences = _accepted_replay(result, self.case, backend, 10)
                self.assertEqual(oracle["worlds"], EXPECTED_WORLDS)
                self.assertEqual(oracle["compatible_pair_count"], EXPECTED_PAIRS)
                self.assertEqual(oracle["checked_information_sets"],
                                 EXPECTED_INFORMATION_SETS)
                self.assertEqual(oracle["public_node_count"], 580)
                self.assertEqual(set(differences), {
                    "value_oop", "value_ip", "oop_best_response_value",
                    "ip_best_response_value", "oop_best_response_gain",
                    "ip_best_response_gain", "nash_conv", "exploitability",
                })

    def test_either_documented_canonical_reachability_order_is_accepted(self):
        candidates = _full_deck_candidates(self.case)
        lexical = sorted(candidates)
        for backend in BACKENDS:
            for ordering in (candidates, lexical):
                with self.subTest(backend=backend, order="deck" if ordering == candidates else "lexical"):
                    result = self._profile(backend)
                    result["reachable_runouts"] = list(ordering)
                    validate_profile_metadata(result, self.case, backend, 10)

    def test_conditioning_configuration_counts_work_and_target_corruptions_fail(self):
        for backend in BACKENDS:
            with self.subTest(backend=backend):
                mutations = []

                wrong_board = self._profile(backend)
                wrong_board["board"] = ["Js", "8d", "4c", "2s"]
                mutations.append((wrong_board, "board"))

                selected_only = self._profile(backend)
                selected_only["runouts"] = selected_only["runouts"][:-1]
                mutations.append((selected_only, "runout"))

                wrong_mode = self._profile(backend)
                wrong_mode["runout_mode"] = "conditioned-subset"
                mutations.append((wrong_mode, "runout mode"))

                bad_reach = self._profile(backend)
                bad_reach["reachable_runouts"] = list(reversed(bad_reach["reachable_runouts"]))
                mutations.append((bad_reach, "Reachability"))

                wrong_river = self._profile(backend)
                wrong_river["river_config"]["bet_sizes"] = [0.5]
                mutations.append((wrong_river, "sizing metadata"))

                wrong_info_count = self._profile(backend)
                wrong_info_count["info_sets"] += 1
                mutations.append((wrong_info_count, "Information-set count"))

                target_stopping = self._profile(backend)
                target_stopping["convergence"] = {"target_exploitability": 0.001}
                mutations.append((target_stopping, "stop target"))

                for profile, message in mutations:
                    with self.subTest(mutation=message), self.assertRaisesRegex(
                            ValueError, message):
                        validate_profile_metadata(profile, self.case, backend, 10)

        bad_row = self._profile("materialized")
        bad_row["strategy"][0]["actions"][0]["probability"] = -0.01
        with self.assertRaises(ValueError):
            _accepted_replay(bad_row, self.case, "materialized", 10)

    def test_backend_resource_aliases_and_reported_caps_are_guarded(self):
        matrix = self._profile("matrix-free")
        matrix["resource_usage"]["hand_state_pass_work"] += 1
        with self.assertRaisesRegex(ValueError, "fixed-request work charge"):
            validate_profile_metadata(matrix, self.case, "matrix-free", 10)

        matrix = self._profile("matrix-free")
        matrix["resource_usage"]["limits"]["hand_state_pass_work"] += 1
        with self.assertRaisesRegex(ValueError, "resource limits"):
            validate_profile_metadata(matrix, self.case, "matrix-free", 10)

        matrix = self._profile("matrix-free")
        matrix["worlds_materialized"] = False
        with self.assertRaisesRegex(ValueError, "materialize"):
            validate_profile_metadata(matrix, self.case, "matrix-free", 10)

        materialized = self._profile("materialized")
        materialized["world_traversal_nodes"] += 1
        with self.assertRaisesRegex(ValueError, "per-world traversal-node"):
            validate_profile_metadata(materialized, self.case, "materialized", 10)

        materialized = self._profile("materialized")
        materialized["public_state_limit"] = 99_000_000
        with self.assertRaisesRegex(ValueError, "public-state limit"):
            validate_profile_metadata(materialized, self.case, "materialized", 10)

        for field, value in (("hand_slots", EXPECTED_MATRIX_HAND_SLOTS + 1),
                             ("info_action_slots", EXPECTED_MATRIX_ACTION_SLOTS + 1),
                             ("turn_fold_terminals", EXPECTED_MATRIX_FOLD_TERMINALS + 1)):
            matrix = self._profile("matrix-free")
            matrix["resource_usage"][field] = value
            with self.subTest(resource=field), self.assertRaisesRegex(
                    ValueError, "resource count"):
                validate_profile_metadata(matrix, self.case, "matrix-free", 10)


if __name__ == "__main__":
    unittest.main()
