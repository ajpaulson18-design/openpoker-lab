from contextlib import ExitStack
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import certify_preflop_three_rank_sequence as harness
from scripts import preflop_three_rank_sequence_candidate as candidate
from scripts import preflop_three_rank_pure_response as independent


class ThreeRankSequenceHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "source"
        self.root.mkdir()
        self.output = self.base / "evidence"
        self.state = {"revision": "a" * 40, "status": [],
                      "source_hashes": {"source.py": {"lf_sha256": "b" * 64}}}

    def _patched(self, *, build=None, verify=None, snapshots=None):
        stack = ExitStack()
        stack.enter_context(patch.object(harness, "ROOT", self.root))
        stack.enter_context(patch.object(harness, "_baseline_is_ancestor"))
        stack.enter_context(patch.object(harness, "_snapshot", side_effect=snapshots or
                                         [deepcopy(self.state), deepcopy(self.state)]))
        stack.enter_context(patch.object(candidate, "build_candidate", side_effect=build))
        stack.enter_context(patch.object(independent, "verify_candidate", side_effect=verify))
        return stack

    def test_full_wrapper_saves_candidate_and_runs_two_independent_checks(self):
        lp_calls = []
        def fake_solve(*_args, **_kwargs):
            lp_calls.append(1)
        produced = {"status": "candidate-only", "artifact_sha256": "c" * 64,
                    "policies": []}
        def build(_request):
            candidate.lp._solve_lp(None, "oop")
            candidate.lp._solve_lp(None, "ip")
            return produced
        receipt = {"status": "passed", "exact_mutual_response_verified": True,
                   "nash_conv_fraction": "0"}
        with patch.object(candidate.lp, "_solve_lp", side_effect=fake_solve):
            with self._patched(build=build, verify=[receipt, receipt]):
                path, report = harness.run(self.output, "a" * 40)
        self.assertEqual(path, self.output / "report.json")
        self.assertEqual(report["status"], "physically-verified")
        self.assertEqual((report["candidate_attempts"], report["lp_solve_calls"],
                          report["independent_verification_calls"]), (1, 2, 2))
        self.assertTrue((self.output / "candidate.json").is_file())
        self.assertEqual(report["forbidden_calculation_calls"],
                         {key: 0 for key in report["forbidden_calculation_calls"]})

    def test_quality_miss_is_preserved_as_a_completed_result(self):
        produced = {"status": "candidate-only", "artifact_sha256": "d" * 64}
        receipt = {"status": "failed", "exact_mutual_response_verified": False,
                   "nash_conv_fraction": "1/7"}
        def build(_request):
            candidate.lp._solve_lp(None, "oop")
            candidate.lp._solve_lp(None, "ip")
            return produced
        with patch.object(candidate.lp, "_solve_lp", return_value=None):
            with self._patched(build=build, verify=[receipt, receipt]):
                _, report = harness.run(self.output, "a" * 40)
        self.assertEqual(report["status"], "candidate-quality-miss")
        self.assertEqual(report["saved_file_verification"]["nash_conv_fraction"], "1/7")

    def test_invalid_full_request_or_baseline_rejects_before_output_or_source(self):
        bad_request = candidate.expected_request()
        bad_request["max_raises"] = True
        with patch.object(harness, "_snapshot", side_effect=AssertionError("snapshot called")):
            with self.assertRaises(ValueError):
                harness.run(self.output, "a" * 40, bad_request)
            with self.assertRaises(ValueError):
                harness.run(self.output, "A" * 40)
        self.assertFalse(self.output.exists())

    def test_candidate_failure_is_retained_and_final_source_error_is_secondary(self):
        primary = RuntimeError("candidate stopped")
        changed = deepcopy(self.state)
        changed["source_hashes"]["source.py"]["lf_sha256"] = "e" * 64
        with self._patched(build=side_effect(primary), verify=None,
                           snapshots=[deepcopy(self.state), changed]):
            _, report = harness.run(self.output, "a" * 40)
        self.assertEqual(report["errors"][0]["message"], "candidate stopped")
        self.assertEqual(report["cleanup_errors"][0]["phase"], "source-finalization")
        self.assertEqual(report["candidate_attempts"], 1)
        self.assertFalse(report["source_unchanged"])
        self.assertTrue((self.output / "report.json").is_file())

    def test_source_drift_overrides_success_status_but_preserves_quality_receipt(self):
        produced = {"status": "candidate-only", "artifact_sha256": "f" * 64}
        receipt = {"status": "passed", "exact_mutual_response_verified": True,
                   "nash_conv_fraction": "0"}
        changed = deepcopy(self.state)
        changed["source_hashes"]["source.py"]["lf_sha256"] = "9" * 64
        def build(_request):
            candidate.lp._solve_lp(None, "oop")
            candidate.lp._solve_lp(None, "ip")
            return produced
        with patch.object(candidate.lp, "_solve_lp", return_value=None):
            with self._patched(build=build, verify=[receipt, receipt],
                               snapshots=[deepcopy(self.state), changed]):
                _, report = harness.run(self.output, "a" * 40)
        self.assertEqual(report["status"], "error")
        self.assertTrue(report["quality_target_met"])
        self.assertEqual(report["cleanup_errors"][0]["phase"], "source-finalization")
        self.assertTrue((self.output / "candidate.json").is_file())


def side_effect(exc):
    def fail(*_args, **_kwargs):
        raise exc
    return fail


if __name__ == "__main__":
    unittest.main()
