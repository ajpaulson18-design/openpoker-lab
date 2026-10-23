import copy
import math
import unittest
from unittest.mock import patch

from scripts import flop_second_board_cfrplus as v1
from scripts import flop_second_board_cfrplus_replay_v2 as v2
from scripts import flop_second_board_equivalence as proof
from scripts import benchmark_flop_second_board_cfrplus as base


def replay_result(**overrides):
    result = {name: float(index + 1) for index, name in enumerate(proof.METRICS)}
    result["scalar_absolute_gaps"] = {name: 0.0 for name in proof.METRICS}
    result.update(v2.EXPECTED_COUNTS)
    result.update(overrides)
    return result


def source_state():
    return {"revision": "1" * 40, "status": "", "source_lf_sha256": {
        f"source/{index:02d}.py": f"{index:064x}" for index in range(58)}}


def v1_report(state):
    return {
        "schema_version": v1.ADAPTER,
        "status": "trained-policy-physically-verified",
        "source_revision": state["revision"],
        "source_lf_sha256": dict(list(state["source_lf_sha256"].items())[:54]),
        "quality_target": 0.005,
        "quality_target_met": True,
        "training_calls": 1,
        "preparation_progress": {"preparation_ranker_attempts": 4_134,
                                 "preparation_rank_calls": 4_134},
        "preparation_forbidden_calls": {key: 0 for key in v1.publication.AUTHORITY_KEYS},
        "diagnostic_forbidden_calls": {key: 0 for key in v1.publication.AUTHORITY_KEYS},
        "audit": {"numeric_metrics": {name: float(i + 1)
                                       for i, name in enumerate(proof.METRICS)}},
        "artifact_sha256": "v1-artifact",
    }


class SecondBoardReplayV2Tests(unittest.TestCase):
    def setUp(self):
        self.state = source_state()
        self.raw = replay_result()
        self.source_patch = patch.object(v2, "_source_snapshot", return_value=self.state)
        self.source_patch.start()
        self.addCleanup(self.source_patch.stop)
        self.admission_patch = patch.object(v2, "admit_request", return_value={
            "requested_iterations": 560, "total_admitted_work": 100_992_488,
            "adapter_version": v2.VERSION})
        self.admission_patch.start()
        self.addCleanup(self.admission_patch.stop)
        self.auth_patch = patch.object(v2, "_failure_publication_receipt",
                                       return_value={"status": "failed-v1-authenticated"})
        self.auth_patch.start()
        self.addCleanup(self.auth_patch.stop)

    def _run_with(self, raw=None, *, solve_error=None, auth_error=None,
                  observation=None, capture_error=False, source_sequence=None):
        raw = self.raw if raw is None else raw
        original = proof.physical.replay
        calls = []

        def replay(*_args, **_kwargs):
            calls.append(1)
            return raw

        report = v1_report(self.state)

        def solve(_iterations, *, observation):
            observation.clear()  # Match the v1 adapter's observation contract.
            observation.update(status="running", phase="independent-numeric-replay",
                               preparation_progress=report["preparation_progress"],
                               preparation_forbidden_calls=report["preparation_forbidden_calls"],
                               diagnostic_forbidden_calls=report["diagnostic_forbidden_calls"])
            observation["legacy_replay_view"] = proof.physical.replay("policy", "model")
            if solve_error is not None:
                raise solve_error
            return report

        observation = {} if observation is None else observation
        auth_patch = patch.object(v2, "_failure_publication_receipt",
                                  side_effect=auth_error) if auth_error else patch.object(
                                      v2, "_failure_publication_receipt",
                                      return_value={"status": "failed-v1-authenticated"})
        source_patch = (patch.object(v2, "_source_snapshot", side_effect=source_sequence)
                        if source_sequence is not None else patch.object(
                            v2, "_source_snapshot", return_value=self.state))
        with auth_patch as auth, source_patch, \
             patch.object(v1, "solve_second_board", side_effect=solve) as solve_mock, \
             patch.object(proof.physical, "replay", replay):
            if auth_error:
                with self.assertRaisesRegex(type(auth_error), str(auth_error)):
                    v2.solve_second_board(560, observation=observation)
                return observation, calls, solve_mock, original, auth
            if solve_error is not None:
                with self.assertRaises(type(solve_error)) as raised:
                    v2.solve_second_board(560, observation=observation)
                self.assertIs(raised.exception, solve_error)
            else:
                try:
                    result = v2.solve_second_board(560, observation=observation)
                except BaseException as exc:
                    if not capture_error:
                        raise
                    return observation, calls, solve_mock, original, auth, exc
                return observation, calls, solve_mock, original, auth, result
        return observation, calls, solve_mock, original, auth

    def test_valid_13_field_result_is_retained_and_v1_receives_8_metrics(self):
        observed, calls, solve_mock, original, auth, result = self._run_with()
        self.assertEqual(len(calls), 1)
        self.assertEqual(solve_mock.call_count, 1)
        self.assertEqual(auth.call_count, 1)
        self.assertIs(proof.physical.replay, original)
        self.assertEqual(set(observed["numeric_replay_raw"]),
                         set(proof.METRICS) | {"scalar_absolute_gaps"} | set(v2.EXPECTED_COUNTS))
        self.assertEqual(observed["numeric_replay_receipt"]["raw_result_key_count"], 13)
        self.assertEqual(result["schema_version"], v2.VERSION)
        self.assertEqual(result["status"], "trained-policy-physically-verified")
        self.assertEqual(len(result["source_lf_sha256"]), 58)
        self.assertEqual(len(result["wrapped_v1_source_lf_sha256"]), 54)
        unsigned = {key: value for key, value in result.items() if key != "artifact_sha256"}
        self.assertEqual(result["artifact_sha256"], proof._digest(unsigned))
        self.assertEqual(observed["phase"], "complete")
        self.assertEqual(set(observed["legacy_replay_view"]), set(proof.METRICS))
        self.assertEqual(observed["legacy_replay_view"],
                         {key: self.raw[key] for key in proof.METRICS})

    def test_strict_replay_contract_rejects_bad_schema_types_gaps_and_counts(self):
        bad_cases = []
        extra = replay_result(); extra["unexpected"] = 1; bad_cases.append(extra)
        missing = replay_result(); del missing["checked_public_nodes"]; bad_cases.append(missing)
        bool_metric = replay_result(); bool_metric[proof.METRICS[0]] = True; bad_cases.append(bool_metric)
        nan_metric = replay_result(); nan_metric[proof.METRICS[0]] = math.nan; bad_cases.append(nan_metric)
        bad_gap_type = replay_result(); bad_gap_type["scalar_absolute_gaps"][proof.METRICS[0]] = 0; bad_cases.append(bad_gap_type)
        bad_gap = replay_result(); bad_gap["scalar_absolute_gaps"][proof.METRICS[0]] = 1.1e-10; bad_cases.append(bad_gap)
        bool_count = replay_result(); bool_count["checked_physical_worlds"] = True; bad_cases.append(bool_count)
        wrong_count = replay_result(); wrong_count["checked_public_states"] += 1; bad_cases.append(wrong_count)
        for raw in bad_cases:
            with self.subTest(raw=repr(raw)[:80]):
                observed, calls, solve_mock, original, _auth, error = self._run_with(
                    raw, observation={}, capture_error=True)
                self.assertEqual(len(calls), 1)
                self.assertEqual(solve_mock.call_count, 1)
                self.assertIs(proof.physical.replay, original)
                self.assertIs(observed["numeric_replay_raw"], raw)
                self.assertIn("numeric_replay_wrapper_calls", observed["v2_wrapper"])
                self.assertIsInstance(error, ValueError)

    def test_original_v1_exception_is_preserved_and_raw_receipt_survives(self):
        sentinel = RuntimeError("after numeric replay")
        observed, calls, solve_mock, original, _auth = self._run_with(solve_error=sentinel)
        self.assertEqual(len(calls), 1)
        self.assertEqual(solve_mock.call_count, 1)
        self.assertIs(proof.physical.replay, original)
        self.assertIs(observed["numeric_replay_raw"], self.raw)
        self.assertIs(observed["status"], "error")
        self.assertEqual(observed["v2_wrapper"]["wrapped_v1_call_count"], 1)

    def test_composes_with_harness_replay_counter_and_restores_each_layer(self):
        raw_callable = proof.physical.replay
        calls = []
        raw = self.raw

        def replay(*_args, **_kwargs):
            calls.append("original")
            return raw

        report = v1_report(self.state)
        observation = {}

        def fake_v1_solve(_iterations, *, observation):
            observation.clear()
            observation.update(status="running", phase="numeric-replay",
                               preparation_progress=report["preparation_progress"],
                               preparation_forbidden_calls=report["preparation_forbidden_calls"],
                               diagnostic_forbidden_calls=report["diagnostic_forbidden_calls"])
            view = proof.physical.replay("policy", "model")
            observation["legacy_replay_view"] = view
            return report

        boundaries = {}
        with patch.object(proof.physical, "replay", replay), \
             patch.object(v1, "solve_second_board", side_effect=fake_v1_solve), \
             base._instrument(boundaries, v2):
            harness_counted = proof.physical.replay
            self.assertIsNot(harness_counted, replay)
            result = v2.solve_second_board(560, observation=observation)
            self.assertIs(proof.physical.replay, harness_counted)
            self.assertEqual(boundaries["numeric_replay_calls"], 1)
            self.assertEqual(observation["legacy_replay_view"],
                             {key: raw[key] for key in proof.METRICS})
            self.assertEqual(result["numeric_replay_raw_receipt"], raw)
        self.assertIs(proof.physical.replay, raw_callable)
        self.assertEqual(calls, ["original"])

    def test_bad_replay_metadata_restores_outer_harness_wrapper(self):
        raw_callable = proof.physical.replay
        raw = self.raw

        def replay(*_args, **_kwargs):
            return {**raw, "checked_public_states": True}

        observation = {}
        report = v1_report(self.state)

        def fake_v1_solve(_iterations, *, observation):
            observation.clear()
            observation.update(status="running", preparation_progress=report["preparation_progress"])
            proof.physical.replay("policy", "model")

        boundaries = {}
        with patch.object(proof.physical, "replay", replay), \
             patch.object(v1, "solve_second_board", side_effect=fake_v1_solve), \
             base._instrument(boundaries, v2):
            outer = proof.physical.replay
            with self.assertRaisesRegex(ValueError, "checked_public_states"):
                v2.solve_second_board(560, observation=observation)
            self.assertIs(proof.physical.replay, outer)
            self.assertEqual(boundaries["numeric_replay_calls"], 1)
            self.assertEqual(observation["numeric_replay_raw"]["checked_public_states"], True)
            self.assertEqual(observation["v2_wrapper"]["numeric_replay_wrapper_calls"], 1)
        self.assertIs(proof.physical.replay, raw_callable)

    def test_source_drift_on_success_fails_without_returning_report(self):
        changed = copy.deepcopy(self.state)
        changed["revision"] = "2" * 40
        observation = {}
        observed, calls, solve_mock, original, _auth, error = self._run_with(
            observation=observation, source_sequence=[self.state, changed], capture_error=True)
        self.assertIsInstance(error, ValueError)
        self.assertIn("sources changed", str(error))
        self.assertEqual(calls, [1])
        self.assertEqual(solve_mock.call_count, 1)
        self.assertIs(proof.physical.replay, original)
        self.assertEqual(observed["status"], "error")
        self.assertIn("v2_report", observed)  # API receipt retained, but no report returned.

    def test_source_after_error_does_not_mask_primary_or_retry_snapshot(self):
        sentinel = RuntimeError("primary solver failure")
        source_error = OSError("source read failed")
        observed, calls, solve_mock, original, _auth = self._run_with(
            solve_error=sentinel, source_sequence=[self.state, source_error])
        self.assertEqual(calls, [1])
        self.assertEqual(solve_mock.call_count, 1)
        self.assertIs(proof.physical.replay, original)
        self.assertEqual(observed["status"], "error")
        self.assertIn("source read failed", observed["v2_source_after_error"])
        self.assertEqual(observed["v2_wrapper"]["wrapped_v1_call_count"], 1)

    def test_failure_publication_authentication_stops_before_v1_call(self):
        sentinel = ValueError("failed-v1 report mismatch")
        observed, calls, solve_mock, original, auth = self._run_with(auth_error=sentinel)
        self.assertEqual(auth.call_count, 1)
        self.assertEqual(solve_mock.call_count, 0)
        self.assertEqual(calls, [])
        self.assertIs(proof.physical.replay, original)
        self.assertEqual(observed["status"], "error")
        self.assertEqual(observed["v2_wrapper"]["wrapped_v1_call_count"], 0)

    def test_admission_rejects_before_source_authentication_or_old_call(self):
        sentinel = ValueError("invalid request")
        observation = {}
        with patch.object(v2, "admit_request", side_effect=sentinel), \
             patch.object(v2, "_source_snapshot", side_effect=AssertionError("source read")), \
             patch.object(v2, "_failure_publication_receipt", side_effect=AssertionError("auth")), \
             patch.object(v1, "solve_second_board", side_effect=AssertionError("v1 solve")):
            with self.assertRaises(ValueError) as raised:
                v2.solve_second_board(True, observation=observation)
        self.assertIs(raised.exception, sentinel)
        self.assertEqual(observation["status"], "error")
        self.assertEqual(observation["v2_wrapper"]["wrapped_v1_call_count"], 0)


if __name__ == "__main__":
    unittest.main()
