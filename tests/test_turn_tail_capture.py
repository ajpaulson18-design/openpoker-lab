"""Bounded research harness tests for same-run turn CFR+ prefix capture."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from scripts import turn_tail_capture as capture
from scripts.benchmark_turn_river_independent import solve
from pokerlab import matrix_free_turn, postflop_solver


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


class TurnTailCaptureTests(unittest.TestCase):
    def test_same_run_prefix_and_full_profiles_match_unwrapped_call_and_replay(self):
        # Bounded 10-sweep harness probes only; no fixed research budget is run.
        case = deepcopy(capture.FIXTURE)
        for backend in ("materialized", "matrix-free"):
            with self.subTest(backend=backend):
                full, prefix, evidence = capture.capture(
                    case, backend, discard=6, total=10, interval=3)
                unwrapped = solve(case, backend, "cfrplus", 10)
                self.assertEqual(canonical(full), canonical(unwrapped))
                self.assertEqual(evidence["callback_iterations"], [3, 6, 9, 10])
                self.assertEqual(evidence["trainer_calls"], 1)
                self.assertTrue(evidence["final_snapshot_exactly_matches_returned_profile"])
                self.assertEqual((evidence["verified_worlds"],
                                  evidence["verified_compatible_pairs"],
                                  evidence["verified_information_sets"]), (176, 4, 2404))
                self.assertEqual(prefix["iterations"], 6)
                self.assertEqual(prefix["source_requested_iterations"], 10)
                self.assertEqual(prefix["average_schedule"], "linear-prefix-own-reach")
                self.assertEqual(prefix["diagnostic_provenance"],
                                 "Independent numeric-rule replay and legal BR")
                self.assertEqual(evidence["derived_profile_scope"], prefix["scope"])

    def test_snapshot_copy_is_detached_from_callback_rows(self):
        key = (0, 0, ())
        original = [0.25, 0.75]
        copied = capture._copy_snapshot({key: original}, (key,), {key: 2})
        original[0] = 1.0
        self.assertEqual(copied[key], (0.25, 0.75))

    def test_observer_rejects_wrong_budget_algorithm_and_existing_target(self):
        key = (0, 0, ())
        infos = {key: 2}
        original = lambda *args, **kwargs: None
        cases = (
            ((None, [], infos, 9, "cfrplus"), {}, "budget"),
            ((None, [], infos, 10, "vanilla"), {}, "algorithm"),
            ((None, [], infos, 10, "cfrplus"),
             {"checkpoint_interval": 2, "checkpoint_callback": lambda *_: False}, "target"),
        )
        for args, kwargs, message in cases:
            with self.subTest(message=message):
                wrapped = capture._make_observer(original, "materialized", 4, 10, 2,
                                                 {}, [], [0])
                with self.assertRaisesRegex(ValueError, message):
                    wrapped(*args, **kwargs)

    def test_public_capture_rejects_invalid_budget_before_solving(self):
        with patch.object(capture, "solve", side_effect=AssertionError("solve called")):
            for discard, total in ((0, 10), (10, 10), (5, 4), (True, 10), (2, 9)):
                with self.subTest(discard=discard, total=total), self.assertRaises(ValueError):
                    capture.capture(deepcopy(capture.FIXTURE), "materialized",
                                    discard, total, interval=3)

    def test_both_trainer_bindings_restore_after_callback_and_trainer_errors(self):
        key = (0, 0, ())
        infos = {key: 2}
        for backend, module, name in (
            ("materialized", postflop_solver, "train_public_batched"),
            ("matrix-free", matrix_free_turn, "train_ranked_turn"),
        ):
            for failure in ("callback", "trainer"):
                with self.subTest(backend=backend, failure=failure):
                    def synthetic_trainer(*args, checkpoint_interval=None,
                                          checkpoint_callback=None, **kwargs):
                        if failure == "trainer":
                            raise RuntimeError("trainer failed")
                        checkpoint_callback(3, {key: [0.5, 0.5]})
                        checkpoint_callback(6, {key: [0.5, 0.5]})
                        checkpoint_callback(9, {key: [0.5, 0.5]})
                        checkpoint_callback(10, {key: [0.5, 0.5]})
                        return {key: [0.5, 0.5]}

                    def synthetic_solve(case, selected_backend, algorithm, iterations):
                        function = getattr(module, name)
                        if backend == "materialized":
                            return function(None, [], infos, iterations, algorithm)
                        return function(None, infos, iterations, algorithm,
                                        terminal_kernel=object(), chance_type=object)

                    with patch.object(module, name, synthetic_trainer):
                        bound_before = getattr(module, name)
                        with patch.object(capture, "solve", side_effect=synthetic_solve):
                            if failure == "callback":
                                with patch.object(capture, "_copy_snapshot",
                                                  side_effect=RuntimeError("copy failed")):
                                    with self.assertRaisesRegex(RuntimeError, "copy failed"):
                                        capture.capture(deepcopy(capture.FIXTURE), backend,
                                                        6, 10, 3)
                            else:
                                with self.assertRaisesRegex(RuntimeError, "trainer failed"):
                                    capture.capture(deepcopy(capture.FIXTURE), backend,
                                                    6, 10, 3)
                        self.assertIs(getattr(module, name), bound_before)


if __name__ == "__main__":
    unittest.main()
