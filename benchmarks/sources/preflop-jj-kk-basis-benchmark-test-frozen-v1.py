"""Synthetic orchestration and bounded stream tests; no poker counts are run."""
from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import benchmark_preflop_jj_kk_basis as benchmark
from scripts import preflop_jj_kk_basis_plan as planner


PAIRS = (("JdJs", "KdKs"), ("JdJs", "KcKd"), ("JdJs", "KcKh"))


def rows():
    return [dict(sb_hand=sb, bb_hand=bb, wins=800_000, ties=100_000,
                 losses=812_304, boards=1_712_304) for sb, bb in PAIRS]


class FakeCapture:
    instances = []

    def __init__(self, directory, reference_executable, native_executable, spec):
        self.directory = Path(directory)
        self.calls = []
        self.capture_errors = []
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @contextmanager
    def stage(self, name):
        yield


class JJKKBasisHarnessTests(unittest.TestCase):
    def setUp(self):
        FakeCapture.instances.clear()

    def test_invalid_complete_request_rejects_before_protocol_reports_output_or_build_lookup(self):
        bad = planner.expected_request()
        bad["schema_version"] = True
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "never-created"
            with (patch.object(benchmark, "_protocol", side_effect=AssertionError("protocol read")),
                  patch.object(benchmark, "_authenticate_bases", side_effect=AssertionError("report read")),
                  patch.object(benchmark, "_fresh_output", side_effect=AssertionError("output lookup")),
                  patch.object(benchmark.five, "backend", side_effect=AssertionError("build lookup")),
                  patch.object(benchmark.native, "_backend", side_effect=AssertionError("build lookup"))):
                with self.assertRaises(ValueError):
                    benchmark.run("missing-reference", "missing-native", output, request=bad)
            self.assertFalse(output.exists())

    def test_frozen_protocol_and_published_basis_authentication_are_rank_free(self):
        admission = planner.admit_plan().to_record()
        spec, digest = benchmark._protocol(admission)
        self.assertEqual(digest, benchmark.SPEC_SHA256)
        self.assertEqual(spec["required_stage_order"], list(benchmark.EXPECTED_STAGES))
        basis = benchmark._authenticate_bases(spec)
        self.assertEqual(basis["aa"]["verification"]["status"], "passed")
        self.assertEqual(basis["qq"]["verification"]["status"], "passed")
        self.assertEqual(len(basis["aa_rows"]), 3)
        self.assertEqual(len(basis["qq_rows"]), 3)

    def test_protocol_disk_read_does_not_resolve_backend_or_start_process(self):
        with (patch.object(benchmark.five, "backend", side_effect=AssertionError("backend lookup")),
              patch.object(benchmark.native, "_backend", side_effect=AssertionError("backend lookup")),
              patch.object(subprocess, "run", side_effect=AssertionError("process invocation"))):
            spec, digest = benchmark._protocol(planner.admit_plan().to_record())
        self.assertEqual(digest, benchmark.SPEC_SHA256)
        self.assertEqual(spec["benchmark_id"], "preflop-jj-kk-basis-v1")

    def _run_with_mocks(self, temp, *, conformance_status="error", reference_error=None,
                        native_error=None, source_after=None):
        output = Path(temp) / "out"
        spec = {"benchmark_id": "preflop-jj-kk-basis-v1", "sb_range": "JdJs",
                "bb_range": "KdKs,KcKd,KcKh",
                "limits": {"report_bytes": 4_194_304}}
        admission = planner.admit_plan()
        bases = {"aa": {"verification": {"status": "passed"}},
                 "qq": {"verification": {"status": "passed"}},
                 "aa_rows": rows(), "qq_rows": rows()}
        source = {"status": "", "source_hashes": {"synthetic": "0" * 64}}
        ref_build = {"manifest": {"id": "reference"}}
        candidate_build = {"manifest": {"id": "candidate"}}
        reference_order = (("JdJs", "KcKd"), ("JdJs", "KcKh"), ("JdJs", "KdKs"))
        raw_rows = [next(row for row in rows() if (row["sb_hand"], row["bb_hand"]) == key)
                    for key in reference_order]
        fake_result = SimpleNamespace(rows=raw_rows, metadata={"synthetic": True})
        conformance = {"status": conformance_status, "independent_physical_count_rows": rows()}
        fake_prepared = SimpleNamespace(metadata={"synthetic": True}, equities=SimpleNamespace(
            pairs=((0, 0, 1), (0, 1, 1), (0, 2, 1)),
            counts=((800_000, 100_000, 812_304),) * 3,
            hands=((tuple("JdJs"),), (tuple("KdKs"), tuple("KcKd"), tuple("KcKh"))),
            metadata=lambda: {"synthetic": True}))
        fake_run = (Path(temp) / "conformance.json", conformance)
        with (patch.object(benchmark, "_protocol", return_value=(spec, "a" * 64)),
              patch.object(benchmark, "_authenticate_bases", return_value=bases),
              patch.object(benchmark, "_snapshot", side_effect=[source, source_after or source]),
              patch.object(benchmark, "_candidate_identity", return_value=candidate_build),
              patch.object(benchmark.five, "backend", return_value=(Path("reference.exe"), ref_build)),
              patch.object(benchmark.native, "_backend", return_value=(Path("native.exe"), candidate_build["manifest"])),
              patch.object(benchmark, "_NumericalCapture", FakeCapture),
              patch.object(benchmark.five, "run", return_value=fake_run) as five_run,
              patch.object(benchmark.five, "verify_saved", return_value={"status": "passed"}),
              patch.object(benchmark.reference, "reference_preflop_counts",
                           side_effect=reference_error or (lambda *a, **kw: fake_result)) as ref_run,
              patch.object(benchmark.native, "prepare_native_preflop_equities",
                           side_effect=native_error or (lambda *a, **kw: fake_prepared)) as native_run):
            report_path, report = benchmark.run("reference-build", "candidate-build", output)
        return report_path, report, five_run, ref_run, native_run

    def test_conformance_failure_is_saved_and_stops_before_both_jj_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            path, report, five_run, ref_run, native_run = self._run_with_mocks(temp)
            self.assertEqual(report["status"], "error")
            self.assertTrue(path.is_file())
            self.assertEqual(five_run.call_count, 1)
            ref_run.assert_not_called()
            native_run.assert_not_called()
            self.assertTrue(report["source_unchanged"])
            self.assertTrue(report["reference_build_unchanged"])
            self.assertTrue(report["candidate_build_unchanged"])

    def test_reference_failure_retains_observation_and_never_calls_native(self):
        def fail(*args, **kwargs):
            error = benchmark.reference.ReferenceCountFailure("synthetic failure", {"stdout": "kept"})
            raise error

        with tempfile.TemporaryDirectory() as temp:
            _, report, five_run, ref_run, native_run = self._run_with_mocks(
                temp, conformance_status="passed", reference_error=fail)
            self.assertEqual(report["status"], "error")
            self.assertEqual(report["reference_failed_observation"], {"stdout": "kept"})
            self.assertEqual(five_run.call_count, 1)
            self.assertEqual(ref_run.call_count, 1)
            native_run.assert_not_called()
            self.assertEqual(report["errors"][0]["phase"], "reference-jj")

    def test_native_failure_keeps_reference_evidence_and_does_not_retry(self):
        def fail(*args, **kwargs):
            raise RuntimeError("synthetic native failure")

        with tempfile.TemporaryDirectory() as temp:
            _, report, five_run, ref_run, native_run = self._run_with_mocks(
                temp, conformance_status="passed", native_error=fail)
            self.assertEqual(report["status"], "error")
            self.assertEqual(report["independent_physical_count_rows"], rows())
            self.assertEqual(five_run.call_count, 1)
            self.assertEqual(ref_run.call_count, 1)
            self.assertEqual(native_run.call_count, 1)
            self.assertEqual(report["errors"][0]["phase"], "native-jj")

    def test_final_source_drift_is_secondary_to_original_reference_error(self):
        def fail(*args, **kwargs):
            raise benchmark.reference.ReferenceCountFailure("original failure", {"kept": True})
        changed = {"status": "", "source_hashes": {"synthetic": "1" * 64}}
        with tempfile.TemporaryDirectory() as temp:
            _, report, *_ = self._run_with_mocks(temp, conformance_status="passed",
                                                  reference_error=fail, source_after=changed)
            self.assertEqual(report["errors"][0]["phase"], "reference-jj")
            self.assertEqual(report["errors"][1]["phase"], "source-finalization")
            self.assertEqual(report["reference_failed_observation"], {"kept": True})

    def test_happy_synthetic_run_uses_five_stage_capture_and_preserves_full_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "out"
            spec, spec_hash = benchmark._protocol(planner.admit_plan().to_record())
            source = {"status": "", "source_hashes": {"synthetic": "0" * 64}}
            ref_build = {"manifest": {"id": "reference"}}
            candidate_build = {"manifest": {"id": "candidate"}}
            aa_rows = rows()
            ref_order = (("JdJs", "KcKd"), ("JdJs", "KcKh"), ("JdJs", "KdKs"))
            ref_rows = [next(row for row in aa_rows if (row["sb_hand"], row["bb_hand"]) == key)
                        for key in ref_order]
            prepared = SimpleNamespace(metadata={"candidate_metadata": "kept"}, equities=SimpleNamespace(
                pairs=((0, 0, 1), (0, 1, 1), (0, 2, 1)),
                counts=((800_000, 100_000, 812_304),) * 3,
                hands=((tuple("JdJs"),), (tuple("KdKs"), tuple("KcKd"), tuple("KcKh"))),
                metadata=lambda: {"equity_metadata": "kept"}))
            conformance = {"status": "passed", "independent_physical_count_rows": aa_rows}
            captures = []

            def capture_factory(*args):
                capture = SyntheticCapture(*args)
                captures.append(capture)
                return capture

            def fake_process(command, **kwargs):
                stream = kwargs.get("stdout")
                if hasattr(stream, "write"):
                    stream.write(b"stdout bytes")
                    stdout = None
                else:
                    stdout = b"stdout bytes"
                return SimpleNamespace(returncode=0, stdout=stdout, stderr=b"stderr bytes")

            class SyntheticCapture(benchmark._NumericalCapture):
                def __enter__(self):
                    super().__enter__()
                    self._real_original = self._original
                    self._original = fake_process
                    return self

                def __exit__(self, *args):
                    self._original = self._real_original
                    return super().__exit__(*args)

            def fake_five_run(_reference_build, _candidate_build, directory):
                directory = Path(directory)
                directory.mkdir(parents=True)
                with (directory / "all-five.bin").open("wb") as stream:
                    benchmark.subprocess.run(["reference.exe", "--all-five"],
                                              stdout=stream, stderr=subprocess.PIPE)
                benchmark.subprocess.run(["reference.exe", "--count-basis"],
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                with captures[-1].stage("native-aa-calibration"):
                    benchmark.subprocess.run(["native.exe", "--count-aa"],
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return directory / "conformance.json", conformance

            def fake_reference(*args, **kwargs):
                directory = Path(kwargs["observation_directory"])
                directory.mkdir(parents=True)
                with (directory / "stdout.json").open("wb") as stream:
                    benchmark.subprocess.run(["reference.exe", "--count-pairs"],
                                              stdout=stream, stderr=subprocess.PIPE)
                return SimpleNamespace(rows=ref_rows, metadata={"raw_reference_metadata": "kept"})

            def fake_native(*args, **kwargs):
                with tempfile.TemporaryFile(mode="w+b") as stdout, tempfile.TemporaryFile(mode="w+b") as stderr:
                    benchmark.subprocess.run(["native.exe", "--count-jj"],
                                             stdout=stdout, stderr=stderr)
                return prepared

            bases = {"aa": {"verification": {"status": "passed"}},
                     "qq": {"verification": {"status": "passed"}},
                     "aa_rows": aa_rows, "qq_rows": aa_rows}
            with (patch.object(benchmark, "_protocol", return_value=(spec, spec_hash)),
                  patch.object(benchmark, "_authenticate_bases", return_value=bases),
                  patch.object(benchmark, "_snapshot", side_effect=[source, source]),
                  patch.object(benchmark, "_candidate_identity", return_value=candidate_build),
                  patch.object(benchmark.five, "backend", return_value=(Path("reference.exe"), ref_build)),
                  patch.object(benchmark.native, "_backend", return_value=(Path("native.exe"), candidate_build["manifest"])),
                  patch.object(benchmark, "_NumericalCapture", side_effect=capture_factory),
                  patch.object(benchmark.five, "run", side_effect=fake_five_run),
                  patch.object(benchmark.five, "verify_saved", return_value={"status": "passed"}),
                  patch.object(benchmark.reference, "reference_preflop_counts", side_effect=fake_reference),
                  patch.object(benchmark.native, "prepare_native_preflop_equities", side_effect=fake_native),
                  patch.object(benchmark.platform, "platform", return_value="synthetic")):
                report_path, report = benchmark.run("reference-build", "candidate-build", output)

            self.assertEqual(report["status"], "passed", report["errors"])
            self.assertEqual(report["stage_order"], list(benchmark.EXPECTED_STAGES))
            self.assertEqual(len(report["numerical_subprocess_calls"]), 5)
            self.assertEqual(report["reference_metadata"], {"raw_reference_metadata": "kept"})
            self.assertEqual(report["candidate_metadata"], {"candidate_metadata": "kept"})
            self.assertEqual(report["candidate_equity_table"], {"equity_metadata": "kept"})
            self.assertEqual(report["reference_physical_count_rows_raw_order"], ref_rows)
            self.assertEqual(report["independent_physical_count_rows"], aa_rows)
            self.assertTrue(all(call["status"] == "returned" and call["returncode"] == 0
                                for call in report["numerical_subprocess_calls"]))
            self.assertTrue(report_path.is_file())

    def test_write_only_file_and_pipe_streams_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            spec = {"limits": {"raw_stdout_bytes": 32, "raw_stderr_bytes": 32}}
            capture = benchmark._NumericalCapture(temp, Path("reference.exe"), Path("native.exe"), spec)
            with capture:
                def fake_run(command, **kwargs):
                    if hasattr(kwargs["stdout"], "write"):
                        kwargs["stdout"].write(b"raw-out")
                        stdout = None
                    else:
                        stdout = b"raw-out"
                    return SimpleNamespace(returncode=0, stdout=stdout, stderr=b"raw-err")

                capture._original = fake_run
                with (Path(temp) / "out.bin").open("wb") as stream:
                    capture._run(["reference.exe", "--all-five"], stdout=stream,
                                 stderr=subprocess.PIPE)
                capture._run(["reference.exe", "--count-basis"], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
                with capture.stage("native-aa-calibration"):
                    capture._run(["native.exe", "--calibrate"], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
                capture._run(["reference.exe", "--count-pairs"], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
                with capture.stage("native-jj"):
                    capture._run(["native.exe", "--count"], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            call = capture.calls[0]
            self.assertEqual([row["stage"] for row in capture.calls], list(benchmark.EXPECTED_STAGES))
            self.assertEqual((Path(temp) / call["stdout"]["path"]).read_bytes(), b"raw-out")
            self.assertEqual((Path(temp) / call["stderr"]["path"]).read_bytes(), b"raw-err")
            self.assertFalse(call["stdout"]["over_bound"])
            self.assertFalse(call["stderr"]["over_bound"])
            with self.assertRaises(ValueError):
                capture._run(["reference.exe", "--count-pairs"], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)

    def test_temporary_file_capture_restores_original_positions(self):
        with tempfile.TemporaryDirectory() as temp:
            capture = benchmark._NumericalCapture(
                temp, Path("reference.exe"), Path("native.exe"),
                {"limits": {"raw_stdout_bytes": 32, "raw_stderr_bytes": 32}})
            with tempfile.TemporaryFile(mode="w+b") as stdout, tempfile.TemporaryFile(mode="w+b") as stderr:
                stdout.write(b"stdout-proof")
                stderr.write(b"stderr-proof")
                expected_positions = (stdout.tell(), stderr.tell())
                self.assertEqual(capture._extract_stream(stdout, None, 32)[0], b"stdout-proof")
                self.assertEqual(capture._extract_stream(stderr, None, 32)[0], b"stderr-proof")
                self.assertEqual((stdout.tell(), stderr.tell()), expected_positions)

    def test_timeout_partial_streams_and_exception_survive_patch_restoration(self):
        with tempfile.TemporaryDirectory() as temp:
            capture = benchmark._NumericalCapture(
                temp, Path("reference.exe"), Path("native.exe"),
                {"limits": {"raw_stdout_bytes": 32, "raw_stderr_bytes": 32}})
            expected_run = subprocess.run
            failure = subprocess.TimeoutExpired(["reference.exe", "--all-five"], 1,
                                                output=b"partial-out", stderr=b"partial-err")
            delegated = []
            def raise_timeout(*a, **k):
                if Path(str(a[0][0])).name.lower() == "reference.exe":
                    raise failure
                delegated.append(a[0])
                return SimpleNamespace(returncode=0, stdout=b"git-out", stderr=b"")
            with patch.object(subprocess, "run", side_effect=raise_timeout):
                with self.assertRaises(subprocess.TimeoutExpired) as caught:
                    with capture:
                        capture._run(["reference.exe", "--all-five"], stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
                capture._run(["git", "status"])
            self.assertIs(caught.exception, failure)
            self.assertIs(subprocess.run, expected_run)
            call = capture.calls[0]
            self.assertEqual((Path(temp) / call["stdout"]["path"]).read_bytes(), b"partial-out")
            self.assertEqual((Path(temp) / call["stderr"]["path"]).read_bytes(), b"partial-err")
            self.assertEqual(delegated, [["git", "status"]])
            self.assertEqual(len(capture.calls), 1)

    def test_overbound_stream_stops_before_a_later_numeric_call(self):
        with tempfile.TemporaryDirectory() as temp:
            capture = benchmark._NumericalCapture(
                temp, Path("reference.exe"), Path("native.exe"),
                {"limits": {"raw_stdout_bytes": 3, "raw_stderr_bytes": 3}})
            called = []
            def fake(*args, **kwargs):
                called.append(args[0])
                return SimpleNamespace(returncode=0, stdout=b"large", stderr=b"")
            with patch.object(subprocess, "run", side_effect=fake):
                with capture:
                    with self.assertRaisesRegex(ValueError, "raw stream cap"):
                        capture._run(["reference.exe", "--all-five"], stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
                    with self.assertRaisesRegex(ValueError, "stopped after"):
                        capture._run(["reference.exe", "--count-basis"], stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
                    capture._run(["git", "status"])
            self.assertEqual(len(called), 2)
            self.assertEqual(called[1], ["git", "status"])
            self.assertEqual(called[1], ["git", "status"])
            self.assertEqual(capture.calls[0]["status"], "over-bound")

    def test_capture_rejects_out_of_order_or_sixth_numeric_call(self):
        with tempfile.TemporaryDirectory() as temp:
            capture = benchmark._NumericalCapture(
                temp, Path("reference.exe"), Path("native.exe"),
                {"limits": {"raw_stdout_bytes": 8, "raw_stderr_bytes": 8}})
            with patch.object(subprocess, "run", return_value=SimpleNamespace(returncode=0,
                                                                               stdout=b"", stderr=b"")):
                with capture:
                    with self.assertRaises(ValueError):
                        capture._run(["native.exe", "--too-early"], stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)

    def test_inherited_or_unavailable_stream_is_rejected_before_invocation(self):
        with tempfile.TemporaryDirectory() as temp:
            capture = benchmark._NumericalCapture(
                temp, Path("reference.exe"), Path("native.exe"),
                {"limits": {"raw_stdout_bytes": 8, "raw_stderr_bytes": 8}})
            calls = []
            with patch.object(subprocess, "run", side_effect=lambda *a, **k: calls.append(a)):
                with capture:
                    with self.assertRaisesRegex(ValueError, "retainable bounded"):
                        capture._run(["reference.exe", "--all-five"], stdout=None,
                                     stderr=subprocess.PIPE)
            self.assertEqual(calls, [])

    def test_reference_pair_order_is_validated_then_reordered_to_admitted_order(self):
        raw_order = (("JdJs", "KcKd"), ("JdJs", "KcKh"), ("JdJs", "KdKs"))
        raw_rows = [{**next(row for row in rows() if (row["sb_hand"], row["bb_hand"]) == key)}
                    for key in raw_order]
        normalized = benchmark._rows_in_admitted_order(raw_rows, raw_order, PAIRS)
        self.assertEqual([(row["sb_hand"], row["bb_hand"]) for row in normalized], list(PAIRS))
        with self.assertRaises(ValueError):
            benchmark._rows_in_admitted_order([raw_rows[1], raw_rows[0], raw_rows[2]],
                                              raw_order, PAIRS)

    def test_physical_rows_reject_bool_aliases_and_wrong_order(self):
        with self.assertRaises(ValueError):
            benchmark._validate_rows([{**rows()[0], "wins": True}, *rows()[1:]], PAIRS)
        with self.assertRaises(ValueError):
            benchmark._validate_rows([rows()[1], rows()[0], rows()[2]], PAIRS)


if __name__ == "__main__":
    unittest.main()
