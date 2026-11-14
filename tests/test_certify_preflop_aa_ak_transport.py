"""Synthetic orchestration checks; no physical candidate or counts are run."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import certify_preflop_aa_ak_transport as audit


class AaAkTransportAuditTests(unittest.TestCase):
    baseline = "a" * 40

    def setUp(self):
        self.clean = {"revision": "b" * 40, "status": [], "source_hashes": {}}
        self.produced = {"status": "candidate-only", "artifact_sha256": "c" * 64,
                         "rows": [{"sb_hand": "AcKc", "bb_hand": "KdKh"}]}
        self.receipt = {"status": "transport-authenticated-candidate-only",
                        "physical_pair_rows_authenticated": 84,
                        "equilibrium_or_policy_claim": False}

    def _patch_success(self, snapshots=None):
        return (
            patch.object(audit.candidate, "admit", return_value=None),
            patch.object(audit, "published_baseline", return_value=self.baseline),
            patch.object(audit, "snapshot", side_effect=snapshots or [self.clean, self.clean]),
            patch.object(audit.candidate, "build_candidate", return_value=self.produced),
            patch.object(audit.independent, "verify", return_value=self.receipt),
            patch.object(audit.independent, "verify_candidate_report", return_value=self.receipt),
        )

    def test_invalid_full_request_rejects_before_baseline_source_or_output(self):
        invalid = audit.candidate.expected_request()
        invalid["schema_version"] = True
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "not-created"
            with (patch.object(audit.candidate, "admit", side_effect=ValueError("bad request")) as admit,
                  patch.object(audit, "published_baseline", side_effect=AssertionError("baseline lookup")),
                  patch.object(audit, "snapshot", side_effect=AssertionError("source lookup"))):
                with self.assertRaisesRegex(ValueError, "bad request"):
                    audit.run(output, baseline_commit=self.baseline, request=invalid)
            admit.assert_called_once_with(invalid)
            self.assertFalse(output.exists())

    def test_baseline_failure_precedes_source_snapshot_and_output(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "not-created"
            with (patch.object(audit.candidate, "admit") as admit,
                  patch.object(audit, "published_baseline", side_effect=ValueError("bad baseline")) as baseline,
                  patch.object(audit, "snapshot", side_effect=AssertionError("source lookup"))):
                with self.assertRaisesRegex(ValueError, "bad baseline"):
                    audit.run(output, baseline_commit=self.baseline)
            admit.assert_called_once_with(None)
            baseline.assert_called_once_with(self.baseline)
            self.assertFalse(output.exists())

    def test_baseline_identity_rejects_before_git_and_oversize_before_blob_read(self):
        with patch.object(audit.subprocess, "run", side_effect=AssertionError("Git lookup")):
            for commit in (True, "a" * 39, "A" * 40, "--help"):
                with self.subTest(commit=commit), self.assertRaisesRegex(ValueError, "exact independently"):
                    audit.published_baseline(commit)
        commands = []
        def oversized(command, **_kwargs):
            commands.append(command)
            if command[1] == "merge-base":
                return SimpleNamespace(returncode=0, stdout=b"")
            self.assertEqual(command[1:3], ["cat-file", "-s"])
            return SimpleNamespace(returncode=0, stdout=b"1000000000\n")
        with patch.object(audit.subprocess, "run", side_effect=oversized):
            with self.assertRaisesRegex(ValueError, "unexpected size"):
                audit.published_baseline(self.baseline)
        self.assertEqual(len(commands), 2)

    def test_baseline_must_be_ancestor_and_contain_pinned_source_index(self):
        with patch.object(audit.subprocess, "run", return_value=SimpleNamespace(returncode=1)) as git:
            with self.assertRaisesRegex(ValueError, "not a current source ancestor"):
                audit.published_baseline(self.baseline)
            self.assertEqual(git.call_count, 1)
        raw = (audit.ROOT / "benchmarks/results/preflop-ak-kk-basis-v1/index.json").read_bytes()
        for payload in (raw, b"x" * len(raw)):
            receipts = [SimpleNamespace(returncode=0, stdout=b""),
                        SimpleNamespace(returncode=0, stdout=b"6080\n"),
                        SimpleNamespace(returncode=0, stdout=payload)]
            with self.subTest(valid=payload == raw), patch.object(audit.subprocess, "run", side_effect=receipts):
                if payload == raw:
                    self.assertEqual(audit.published_baseline(self.baseline), self.baseline)
                else:
                    with self.assertRaisesRegex(ValueError, "authenticated AK source corpus"):
                        audit.published_baseline(self.baseline)

    def test_success_runs_one_candidate_and_both_independent_guards(self):
        with tempfile.TemporaryDirectory() as temp:
            contexts = self._patch_success()
            with contexts[0], contexts[1], contexts[2], \
                    patch.object(audit.candidate, "build_candidate", return_value=self.produced) as build, \
                    patch.object(audit.independent, "verify", return_value=self.receipt) as memory, \
                    patch.object(audit.independent, "verify_candidate_report",
                                 return_value=self.receipt) as saved:
                path, result = audit.run(Path(temp) / "out", baseline_commit=self.baseline)
            self.assertEqual(result["status"], "transport-verified")
            self.assertEqual((result["candidate_attempts"], result["independent_attempts"]), (1, 2))
            self.assertEqual((build.call_count, memory.call_count, saved.call_count), (1, 1, 1))
            self.assertEqual(len(result["forbidden_calculation_calls"]), 16)
            self.assertTrue(all(type(count) is int and count == 0
                                for count in result["forbidden_calculation_calls"].values()))
            self.assertEqual(json.loads((path.parent / "candidate.json").read_text(encoding="utf-8")),
                             self.produced)
            self.assertEqual(result["independent_memory_verification"],
                             result["fresh_saved_file_verification"])

    def test_dirty_source_stops_before_candidate_build(self):
        dirty = {"revision": self.clean["revision"], "status": ["?? untracked"],
                 "source_hashes": {}}
        with tempfile.TemporaryDirectory() as temp:
            with (patch.object(audit.candidate, "admit"),
                  patch.object(audit, "published_baseline", return_value=self.baseline),
                  patch.object(audit, "snapshot", side_effect=[dirty, dirty]),
                  patch.object(audit.candidate, "build_candidate",
                               side_effect=AssertionError("candidate must not run")) as build):
                _path, result = audit.run(Path(temp) / "out", baseline_commit=self.baseline)
            build.assert_not_called()
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["candidate_attempts"], 0)
            self.assertIn("clean committed source", result["errors"][0]["message"])

    def test_first_candidate_error_and_late_source_drift_are_both_retained(self):
        changed = {**self.clean, "source_hashes": {"late": {"raw_sha256": "d" * 64}}}
        with tempfile.TemporaryDirectory() as temp:
            with (patch.object(audit.candidate, "admit"),
                  patch.object(audit, "published_baseline", return_value=self.baseline),
                  patch.object(audit, "snapshot", side_effect=[self.clean, changed]),
                  patch.object(audit.candidate, "build_candidate",
                               side_effect=ValueError("first candidate failure")) as build,
                  patch.object(audit.independent, "verify", side_effect=AssertionError("no retry")) as verify):
                _path, result = audit.run(Path(temp) / "out", baseline_commit=self.baseline)
            self.assertEqual(result["status"], "error")
            self.assertEqual([error["phase"] for error in result["errors"]],
                             ["audit", "source-finalization"])
            self.assertEqual(result["errors"][0]["message"], "first candidate failure")
            self.assertIn("source changed", result["errors"][1]["message"])
            self.assertEqual(build.call_count, 1)
            verify.assert_not_called()

    def test_successful_dual_receipts_are_rejected_if_source_drifts_afterward(self):
        changed = {**self.clean, "revision": "e" * 40}
        with tempfile.TemporaryDirectory() as temp:
            contexts = self._patch_success([self.clean, changed])
            with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], contexts[5]:
                path, result = audit.run(Path(temp) / "out", baseline_commit=self.baseline)
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["candidate_attempts"], 1)
            self.assertEqual(result["independent_attempts"], 2)
            self.assertEqual(result["errors"][-1]["phase"], "source-finalization")
            self.assertIn("source changed", result["errors"][-1]["message"])
            self.assertTrue((path.parent / "candidate.json").is_file())

    def test_forbidden_guard_restores_entry_points_and_records_direct_attempt(self):
        original_build = audit.candidate.build_candidate
        original_pool = audit.candidate.covered.pool_preflop_equities_by_suit
        calls = {}
        with audit.no_calculation(calls, independent_phase=True):
            with self.assertRaisesRegex(AssertionError, "Forbidden calculation"):
                audit.candidate.build_candidate()
            with self.assertRaisesRegex(AssertionError, "Forbidden calculation"):
                audit.candidate.covered.pool_preflop_equities_by_suit([], "AA", "KK")
        self.assertIs(audit.candidate.build_candidate, original_build)
        self.assertIs(audit.candidate.covered.pool_preflop_equities_by_suit, original_pool)
        self.assertEqual(calls["scripts.preflop_aa_ak_transport.build_candidate"], 1)
        self.assertEqual(calls["pokerlab.preflop_covered_equity.pool_preflop_equities_by_suit"], 1)
        self.assertTrue(all(type(count) is int for count in calls.values()))


if __name__ == "__main__":
    unittest.main()
