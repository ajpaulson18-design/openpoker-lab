"""Orchestration tests for the bounded saved transport audit."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import certify_preflop_three_rank_transport as audit


class TransportAuditTests(unittest.TestCase):
    def test_invalid_request_precedes_output_and_source_access(self):
        request = audit.candidate.expected_request()
        request["schema_version"] = True
        with (patch.object(audit, "snapshot", side_effect=AssertionError("source read")),
              tempfile.TemporaryDirectory() as temp):
            output = Path(temp) / "never-created"
            with self.assertRaises(ValueError):
                audit.run(output, request)
            self.assertFalse(output.exists())

    def test_forbidden_guard_restores_callables_and_records_attempts(self):
        original = audit.candidate.build_candidate
        calls = {}
        with audit.no_calculation(calls, independent_phase=True):
            with self.assertRaisesRegex(AssertionError, "Forbidden calculation"):
                audit.candidate.build_candidate()
        self.assertIs(audit.candidate.build_candidate, original)
        self.assertEqual(calls["scripts.preflop_three_rank_transport.build_candidate"], 1)

    def _run(self, temp, *, failure=None, drift=False):
        clean = {"revision": "a" * 40, "status": [], "source_hashes": {}}
        after = {**clean, "revision": "b" * 40} if drift else clean
        produced = {"status": "candidate-only", "artifact_sha256": "a" * 64}
        receipt = {"status": "transport-authenticated-candidate-only"}
        with (patch.object(audit, "snapshot", side_effect=[clean, after]),
              patch.object(audit.candidate, "build_candidate", return_value=produced) as build,
              patch.object(audit.independent, "verify_candidate_report",
                           side_effect=failure or (lambda _value: receipt)) as verify):
            path, result = audit.run(Path(temp) / "out")
        return path, result, build, verify

    def test_single_candidate_and_fresh_saved_replay_are_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            path, result, build, verify = self._run(temp)
            self.assertTrue(path.is_file())
            self.assertEqual(result["status"], "transport-verified")
            self.assertEqual(build.call_count, 1)
            self.assertEqual(verify.call_count, 2)
            self.assertIsInstance(verify.call_args.args[0], Path)
            self.assertFalse(any(result["forbidden_calculation_calls"].values()))

    def test_original_verification_error_survives_later_source_drift_without_retry(self):
        def fail(_value):
            raise ValueError("original verification failure")
        with tempfile.TemporaryDirectory() as temp:
            path, result, build, verify = self._run(temp, failure=fail, drift=True)
            self.assertTrue(path.is_file())
            self.assertTrue((path.parent / "candidate.json").is_file())
            self.assertEqual(result["status"], "error")
            self.assertEqual([row["phase"] for row in result["errors"]], ["audit", "source-finalization"])
            self.assertEqual(result["errors"][0]["message"], "original verification failure")
            self.assertEqual((build.call_count, verify.call_count), (1, 1))


if __name__ == "__main__":
    unittest.main()
