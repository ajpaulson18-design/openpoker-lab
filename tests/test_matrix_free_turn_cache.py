"""Short actual-solver parity and opt-in eligibility tests for turn caching."""
import copy
import unittest
from unittest import mock

from pokerlab import matrix_free_turn
from pokerlab.matrix_free_turn import solve_matrix_free_turn
from scripts import benchmark_turn_terminal_memoization as frozen


def _solve(case, mode):
    options = {key: case[key] for key in ("river_config", "runouts") if key in case}
    return solve_matrix_free_turn(
        case["board"], case["oop"], case["ip"], case["config"],
        iterations=10, algorithm="cfrplus", check_interval=10,
        terminal_cache=mode, **options,
    )


class MatrixFreeTurnCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = {}
        for case_id in (frozen.SELECTED_ID, frozen.FULL_ID):
            case = frozen._frozen_case(case_id)
            baseline = _solve(case, "none")
            cached = _solve(case, "ranked-lru")
            cls.profiles[case_id] = (case, baseline, cached)

    def test_real_short_profiles_preserve_complete_legacy_payload_and_replay(self):
        for case_id, (case, baseline, cached) in self.profiles.items():
            with self.subTest(case=case_id):
                legacy = copy.deepcopy(cached)
                stats = legacy.pop("terminal_cache")
                self.assertEqual(legacy, baseline)
                self.assertEqual(stats["mode"], "ranked-lru")
                self.assertEqual(stats["entries_after_cleanup"], 0)
                self.assertEqual(stats["current_entries"], 0)
                self.assertLessEqual(stats["actual_calls"], stats["reserved_calls"])
                self.assertGreater(stats["hits"], 0)

                options = {key: case[key] for key in ("river_config", "runouts") if key in case}
                from scripts.turn_river_validation import compare_result, replay_policy
                oracle = replay_policy(
                    cached, case["oop"], case["ip"], board=case["board"],
                    config=case["config"], **options,
                )
                differences = compare_result(cached, oracle, tolerance=1e-9)
                self.assertEqual(set(differences), set(frozen.METRICS))
                self.assertTrue(all(abs(delta) <= 1e-9 for delta in differences.values()))

    def test_unsupported_modes_targets_algorithms_and_shapes_fail_before_kernel(self):
        case = frozen._frozen_case(frozen.SELECTED_ID)
        with mock.patch.object(matrix_free_turn, "TurnRangePayoffs",
                               side_effect=AssertionError("kernel constructed")):
            for options in (
                {"algorithm": "vanilla"},
                {"target_exploitability": 0.0},
                {"iterations": 10_001},
            ):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    solve_matrix_free_turn(
                        case["board"], case["oop"], case["ip"], case["config"],
                        iterations=options.get("iterations", 10),
                        algorithm=options.get("algorithm", "cfrplus"),
                        target_exploitability=options.get("target_exploitability"),
                        terminal_cache="ranked-lru",
                    )

            with self.assertRaisesRegex(ValueError, "two original hands"):
                solve_matrix_free_turn(
                    "Js8d4c2h", "AsAh:1,KsKh:1,QcQd:1", "AcAd:1",
                    case["config"], iterations=10, terminal_cache="ranked-lru",
                )

    def test_full_cache_reservation_precedes_training(self):
        case = frozen._frozen_case(frozen.SELECTED_ID)
        with mock.patch.object(matrix_free_turn, "admit_cache",
                               side_effect=ValueError("injected reservation rejection")):
            with mock.patch.object(matrix_free_turn, "train_ranked_turn",
                                   side_effect=AssertionError("training started")) as train:
                with self.assertRaisesRegex(ValueError, "injected reservation"):
                    _solve(case, "ranked-lru")
                train.assert_not_called()

    def test_exceptional_conditioning_is_rejected_before_training(self):
        with mock.patch.object(matrix_free_turn, "train_ranked_turn",
                               side_effect=AssertionError("training started")) as train:
            with self.assertRaisesRegex(ValueError, "exceptional conditioning"):
                solve_matrix_free_turn(
                    "2c5d9hJc", "AhAs:1,KcKd:5e-324", "QhQs:1",
                    {"pot": 20, "effective_stack": 20, "bet_sizes": [1],
                     "raise_sizes": [], "max_raises": 0, "include_all_in": False},
                    runouts=("As",), iterations=10, terminal_cache="ranked-lru",
                )
            train.assert_not_called()

    def test_default_does_not_emit_cache_metadata(self):
        cached = self.profiles[frozen.SELECTED_ID][1]
        self.assertNotIn("terminal_cache", cached)


if __name__ == "__main__":
    unittest.main()
