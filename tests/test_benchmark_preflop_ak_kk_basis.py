from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import benchmark_preflop_ak_kk_basis as study


class AKKKBasisHarnessTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, study.native.subprocess, "run", study.native.subprocess.run)

    def _capture(self, directory, limit=32):
        return study.SevenStageCapture(directory, directory / "reference.exe", directory / "native.exe",
                                       {"limits": {"raw_stdout_bytes": limit, "raw_stderr_bytes": limit}})

    def _call(self, capture, stage):
        reference = stage.startswith("reference-")
        command = [str(capture.reference_executable if reference else capture.native_executable)]
        if stage == "reference-all-five":
            command.append("--all-five")
        elif stage == "reference-aa-calibration":
            command.append("--count-basis")
        elif reference:
            command.append("--count-pairs")
        with capture.stage(stage):
            return study.native.subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_seven_stage_order_preserves_original_five_stage_contract_and_restores_wrapper(self):
        prior = tuple(study.retained.EXPECTED_STAGES)
        with tempfile.TemporaryDirectory() as temporary:
            capture = self._capture(Path(temporary))
            with patch.object(study.native.subprocess, "run", return_value=
                              subprocess.CompletedProcess([], 0, b"out", b"err")) as original:
                with capture:
                    for stage in study.EXPECTED_STAGES:
                        self._call(capture, stage)
                    with self.assertRaisesRegex(ValueError, "repeated"):
                        self._call(capture, study.EXPECTED_STAGES[-1])
                self.assertIs(study.native.subprocess.run, original)
                self.assertEqual(original.call_count, 7)
            self.assertEqual([row["stage"] for row in capture.calls], list(study.EXPECTED_STAGES))
            self.assertTrue(all(row["stdout"]["bytes_retained"] == 3 for row in capture.calls))
        self.assertEqual(study.retained.EXPECTED_STAGES, prior)
        self.assertEqual(len(prior), 5)

    def test_wrong_backend_and_unretainable_stream_reject_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = self._capture(Path(temporary))
            with patch.object(study.native.subprocess, "run") as original, capture:
                with self.assertRaisesRegex(ValueError, "retainable"):
                    study.native.subprocess.run([str(capture.reference_executable), "--all-five"])
                capture.calls = [{"stage": name} for name in study.EXPECTED_STAGES[:3]]
                with capture.stage("reference-ak-suited"):
                    with self.assertRaisesRegex(ValueError, "Unexpected"):
                        study.native.subprocess.run([str(capture.native_executable)],
                                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                original.assert_not_called()

    def test_timeout_retains_partial_streams_and_stops_further_numerical_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = self._capture(Path(temporary))
            error = subprocess.TimeoutExpired("reference", 1, output=b"partial", stderr=b"cause")
            with patch.object(study.native.subprocess, "run", side_effect=error) as original, capture:
                with self.assertRaises(subprocess.TimeoutExpired):
                    self._call(capture, "reference-all-five")
                with self.assertRaisesRegex(ValueError, "stopped"):
                    self._call(capture, "reference-all-five")
                self.assertEqual(original.call_count, 1)
            self.assertEqual(capture.calls[0]["stdout"]["bytes_retained"], 7)
            self.assertEqual(capture.calls[0]["stderr"]["bytes_retained"], 5)

    def test_over_bound_receipt_is_retained_and_unrelated_git_still_delegates(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = self._capture(Path(temporary), 4)
            with patch.object(study.native.subprocess, "run", return_value=
                              subprocess.CompletedProcess([], 0, b"12345", b"")) as original, capture:
                with self.assertRaisesRegex(ValueError, "cap"):
                    self._call(capture, "reference-all-five")
                study.native.subprocess.run(["git", "status"], capture_output=True)
                self.assertEqual(original.call_count, 2)
            self.assertTrue(capture.calls[0]["stdout"]["over_bound"])
            self.assertEqual(capture.calls[0]["stdout"]["bytes_retained"], 4)

    def test_file_backed_and_seekable_stream_routes_preserve_bytes_and_cursor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            capture = self._capture(root)

            def complete(command, **options):
                options["stdout"].write(b"raw")
                options["stderr"].write(b"err")
                return subprocess.CompletedProcess(command, 0)

            with (root / "out").open("wb") as output, tempfile.TemporaryFile() as error:
                with patch.object(study.native.subprocess, "run", side_effect=complete), capture:
                    study.native.subprocess.run([str(capture.reference_executable), "--all-five"],
                                                stdout=output, stderr=error)
                    self.assertEqual(error.tell(), 3)
            self.assertEqual(capture.calls[0]["stdout"]["capture_source"], "file-backed-stream")
            self.assertEqual(capture.calls[0]["stderr"]["capture_source"], "seekable-stream")

    def test_invalid_whole_request_precedes_protocol_basis_output_and_build_lookup(self):
        request = study.planner.expected_request()
        request["schema_version"] = True
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "never"
            with patch.object(study, "_protocol", side_effect=AssertionError("protocol read")), \
                    patch.object(study, "_authenticate_aa", side_effect=AssertionError("basis read")):
                with self.assertRaisesRegex(ValueError, "entire literal"):
                    study.run("reference", "native", output, request)
            self.assertFalse(output.exists())

    def test_frozen_protocol_rejects_resigned_shape_change_before_basis(self):
        spec = study.expected_protocol(study.planner.admit_plan())
        spec["limits"]["numerical_subprocess_calls"] = 8
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "spec.json"
            path.write_text(json.dumps(spec))
            with patch.object(study, "SPEC", path), \
                    patch.object(study, "_authenticate_aa", side_effect=AssertionError("basis read")):
                with self.assertRaisesRegex(ValueError, "entire frozen"):
                    study.run("reference", "native", Path(temporary) / "never")

    def _rows(self, query):
        return [{"sb_hand": a, "bb_hand": b, "wins": 1, "ties": 2,
                 "losses": 1_712_301, "boards": 1_712_304} for a, b in query["ordered_pairs"]]

    def _pipeline(self, directory, *, fail=False, drift=False):
        plan = study.planner.admit_plan()
        spec = study.expected_protocol(plan)
        before = {"revision": "a" * 40, "status": [], "source_hashes": {}}
        after = {**before, "revision": "b" * 40} if drift else before
        ref = directory / "reference.exe"
        nat = directory / "native.exe"
        aa = [{"synthetic_calibration": True}]

        def conformance(_reference, _native, output):
            if fail:
                raise ValueError("original conformance failure")
            for command in ([str(ref), "--all-five"], [str(ref), "--count-basis"], [str(nat)]):
                study.native.subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return output / "report.json", {"status": "passed", "independent_physical_count_rows": aa}

        def reference_counts(sb, bb, **options):
            query = next(row for row in plan["count_requests"] if row["sb_range"] == sb)
            study.native.subprocess.run([str(ref), "--count-pairs"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return SimpleNamespace(rows=self._rows(query), metadata={"synthetic": True})

        def native_counts(sb, bb, **options):
            query = next(row for row in plan["count_requests"] if row["sb_range"] == sb)
            study.native.subprocess.run([str(nat)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            hands = tuple(tuple(text[i:i + 2] for i in (0, 2)) for text in
                          dict.fromkeys(pair[1] for pair in query["ordered_pairs"]))
            table = SimpleNamespace(hands=((tuple(sb[i:i + 2] for i in (0, 2)),), hands),
                                    pairs=tuple((0, i, None) for i in range(len(hands))),
                                    counts=((1, 2, 1_712_301),) * len(hands),
                                    metadata=lambda: {"synthetic": True})
            return SimpleNamespace(equities=table, metadata={"synthetic": True})

        with patch.object(study, "_protocol", return_value=(spec, "synthetic-protocol")), \
                patch.object(study, "_authenticate_aa", return_value=({"synthetic": True}, aa)), \
                patch.object(study, "snapshot", side_effect=(before, after)), \
                patch.object(study.five, "backend", return_value=(ref, {"synthetic": True})), \
                patch.object(study.native, "_backend", return_value=(nat, {"synthetic": True})), \
                patch.object(study.retained, "_candidate_identity", return_value={"synthetic": True}), \
                patch.object(study.five, "run", side_effect=conformance), \
                patch.object(study.five, "verify_saved", return_value={"status": "passed"}), \
                patch.object(study.reference, "reference_preflop_counts", side_effect=reference_counts), \
                patch.object(study.native, "prepare_native_preflop_equities", side_effect=native_counts), \
                patch.object(study.native.subprocess, "run", return_value=
                             subprocess.CompletedProcess([], 0, b"synthetic", b"")):
            return study.run(ref, nat, directory / "observation")

    def test_complete_synthetic_pipeline_calls_seven_stages_once_without_retries(self):
        with tempfile.TemporaryDirectory() as temporary:
            path, report = self._pipeline(Path(temporary))
            self.assertTrue(path.is_file())
            self.assertEqual(report["status"], "passed")
            self.assertEqual([row["stage"] for row in report["numerical_subprocess_calls"]],
                             list(study.EXPECTED_STAGES))
            self.assertEqual(len(report["independent_physical_count_rows"]), 3)
            self.assertEqual(report["errors"], [])

    def test_original_failure_and_later_source_drift_are_preserved_without_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            path, report = self._pipeline(Path(temporary), fail=True, drift=True)
            self.assertTrue(path.is_file())
            self.assertEqual(report["status"], "error")
            self.assertIn("original conformance failure", report["errors"][0]["message"])
            self.assertIn("source identity changed", report["errors"][1]["message"])
            self.assertEqual(report["numerical_subprocess_calls"], [])

    def test_successful_counts_followed_by_source_drift_are_an_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, report = self._pipeline(Path(temporary), drift=True)
            self.assertEqual(report["status"], "error")
            self.assertEqual(len(report["independent_physical_count_rows"]), 3)
            self.assertFalse(report["source_unchanged"])

    def test_row_validation_rejects_boolean_and_duplicate_physical_counts(self):
        query = study.planner.admit_plan()["count_requests"][-1]
        expected = [tuple(pair) for pair in query["ordered_pairs"]]
        rows = self._rows(query)
        rows[0]["wins"] = True
        with self.assertRaisesRegex(ValueError, "integer coverage"):
            study._rows(rows, expected)
        rows = self._rows(query)
        rows[1] = deepcopy(rows[0])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            study._rows(rows, expected)


if __name__ == "__main__":
    unittest.main()
