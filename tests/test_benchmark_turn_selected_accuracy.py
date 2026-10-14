"""Cheap structural checks for the selected-turn accuracy harness."""
import copy
import unittest

from scripts.benchmark_turn_selected_accuracy import (
    EXPECTED_CASE,
    _expected_work,
    frozen_case,
    solve,
    validate_profile_metadata,
)


class SelectedTurnAccuracyHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        case = frozen_case()
        cls.profiles = {
            backend: solve(case, backend, "cfrplus", 10)
            for backend in ("materialized", "matrix-free")
        }

    def _profile(self, backend):
        return copy.deepcopy(self.profiles[backend])

    def test_frozen_fixture_pins_distinct_river_sizing_and_selected_cards(self):
        case = frozen_case()
        self.assertEqual(case["id"], EXPECTED_CASE["id"])
        self.assertEqual(case["runouts"], ["3c", "5h"])
        self.assertNotEqual(case["config"]["bet_sizes"],
                            case["river_config"]["bet_sizes"])

    def test_fixed_work_charges_use_the_correct_backend_dimensions(self):
        self.assertEqual(_expected_work("matrix-free", 10_000), 11_281_128)
        self.assertEqual(_expected_work("materialized", 10_000), 9_840_000)
        self.assertEqual(_expected_work("materialized", 10_000),
                         8 * 41 * 10_000 * 3)

    def test_profile_metadata_requires_backend_specific_counts_and_work(self):
        case = frozen_case()
        for backend in ("matrix-free", "materialized"):
            with self.subTest(backend=backend):
                validate_profile_metadata(self._profile(backend), case, backend, 10)

        bad_matrix = self._profile("matrix-free")
        bad_matrix["resource_usage"]["hand_state_pass_work"] += 1
        with self.assertRaisesRegex(ValueError, "full-request work charge"):
            validate_profile_metadata(bad_matrix, case, "matrix-free", 10)

        bad_materialized = self._profile("materialized")
        bad_materialized["world_traversal_nodes"] += 1
        with self.assertRaisesRegex(ValueError, "per-world traversal-node"):
            validate_profile_metadata(bad_materialized, case, "materialized", 10)

        bad_river = self._profile("matrix-free")
        bad_river["river_config"]["bet_sizes"] = [0.5]
        with self.assertRaisesRegex(ValueError, "river configuration"):
            validate_profile_metadata(bad_river, case, "matrix-free", 10)

        self_authorized = self._profile("matrix-free")
        self_authorized["resource_usage"]["limits"]["hand_state_pass_work"] = 99_000_000
        with self.assertRaisesRegex(ValueError, "fixed 30 million"):
            validate_profile_metadata(self_authorized, case, "matrix-free", 10)

        for checks, limit in ((True, 10), (0, True), (-1, 10), (11, 10)):
            with self.subTest(stable_root_pair_counts=(checks, limit)):
                invalid_pairs = self._profile("matrix-free")
                invalid_pairs["resource_usage"].update({
                    "stable_root_fold_pair_checks": checks,
                    "stable_root_fold_pair_limit": limit,
                })
                with self.assertRaisesRegex(ValueError, "stable-root pair cap"):
                    validate_profile_metadata(invalid_pairs, case, "matrix-free", 10)


if __name__ == "__main__":
    unittest.main()
