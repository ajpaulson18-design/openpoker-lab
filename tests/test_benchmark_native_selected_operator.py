import unittest
import hashlib
import io
import json
from contextlib import ExitStack
from pathlib import Path
from subprocess import CalledProcessError
from types import SimpleNamespace
from unittest.mock import patch

from scripts import benchmark_native_selected_operator as benchmark


class NativeSelectedOperatorBenchmarkTests(unittest.TestCase):
    def _memory_filesystem(self):
        files = {}

        class Writer(io.BytesIO):
            def __init__(self, path):
                super().__init__()
                self.path = str(path)

            def __exit__(self, *args):
                if args[0] is None:
                    files[self.path] = self.getvalue()
                return super().__exit__(*args)

        def write_text(path, data, encoding=None, **_kwargs):
            files[str(path)] = str(data).encode(encoding or "utf-8")
            return len(data)

        def write_bytes(path, data):
            files[str(path)] = bytes(data)
            return len(data)

        def read_bytes(path):
            return files[str(path)]

        def read_text(path, encoding=None, **_kwargs):
            return files[str(path)].decode(encoding or "utf-8")

        def open_path(path, mode="r", *args, **kwargs):
            if "x" in mode and str(path) in files:
                raise FileExistsError(str(path))
            if "w" in mode or "x" in mode:
                return Writer(path)
            if "b" in mode:
                return io.BytesIO(files[str(path)])
            return io.StringIO(files[str(path)].decode(kwargs.get("encoding") or "utf-8"))

        patches = [
            patch.object(Path, "resolve", autospec=True, side_effect=lambda self, strict=False: self),
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "mkdir", return_value=None),
            patch.object(Path, "write_text", autospec=True, side_effect=write_text),
            patch.object(Path, "write_bytes", autospec=True, side_effect=write_bytes),
            patch.object(Path, "read_bytes", autospec=True, side_effect=read_bytes),
            patch.object(Path, "read_text", autospec=True, side_effect=read_text),
            patch.object(Path, "open", autospec=True, side_effect=open_path),
            patch.object(benchmark.platform, "platform", return_value="synthetic-test-platform"),
        ]
        return files, patches

    @staticmethod
    def _patch_all(patches):
        stack = ExitStack()
        for item in patches:
            stack.enter_context(item)
        return stack

    def test_fixed_schedule_has_required_sample_counts_and_alternates(self):
        schedule = benchmark._schedule()
        t100_untraced = [row for row in schedule if row[0] == 100 and not row[3]]
        t100_traced = [row for row in schedule if row[0] == 100 and row[3]]
        t1000 = [row for row in schedule if row[0] == 1000]
        self.assertEqual(len(t100_untraced), 6)
        self.assertEqual(len(t100_traced), 2)
        self.assertEqual(len(t1000), 2)
        self.assertEqual([row[1] for row in t100_untraced],
                         ["python", "native", "native", "python", "python", "native"])
        self.assertEqual([row[1] for row in t1000], ["python", "native"])
        self.assertTrue(all(row[2] == 0 for row in t1000))

    def test_child_native_path_is_explicit_and_never_falls_back(self):
        payload = {"native_training": {"native_process_lifetime_peak_working_set_bytes": 123},
                   "strategy": [{"player": "sb"}]}
        executable = Path("C:/benchmark/native-selected-train.exe")
        with patch.object(benchmark, "_request", return_value=object()), \
             patch.object(benchmark, "solve_four_street_operator", return_value=payload) as solve, \
             patch.object(Path, "resolve", return_value=executable), \
             patch.object(benchmark, "_rss", return_value=456):
            result = benchmark.child("native", 100, False, executable)
        kwargs = solve.call_args.kwargs
        self.assertEqual(kwargs["native_executable"], str(executable))
        self.assertEqual(kwargs["rank_cache_boards"], 64)
        self.assertEqual(kwargs["strategy_storage"], "packed")
        self.assertEqual(result["native_process_lifetime_peak_working_set_bytes"], 123)
        self.assertEqual(result["python_process_lifetime_peak_working_set_bytes"], 456)
        self.assertIsNone(result["python_tracemalloc_peak_bytes"])

    def test_native_child_requires_executable(self):
        with self.assertRaises(ValueError):
            benchmark.child("native", 100, False)

    def test_python_child_omits_native_executable(self):
        payload = {"native_training": None, "strategy": []}
        with patch.object(benchmark, "_request", return_value=object()), \
             patch.object(benchmark, "solve_four_street_operator", return_value=payload) as solve, \
             patch.object(benchmark, "_rss", return_value=1):
            result = benchmark.child("python", 100, False)
        self.assertNotIn("native_executable", solve.call_args.kwargs)
        self.assertIsNone(result["native_process_lifetime_peak_working_set_bytes"])

    def test_strategy_comparison_requires_complete_exact_rows(self):
        payloads = {}
        for iterations, samples in ((100, [(0, False), (1, False), (2, False), ("traced", True)]),
                                    (1000, [(0, False)])):
            for sample, traced in samples:
                for backend in benchmark.BACKENDS:
                    payloads[(iterations, backend, sample, traced)] = {
                        "strategy": [{"history": [], "actions": [{"probability": 0.75}]}]}
        self.assertTrue(benchmark._paired_strategy_results(payloads, 100))
        payloads[(100, "native", 1, False)]["strategy"][0]["actions"][0]["probability"] = 0.5
        self.assertFalse(benchmark._paired_strategy_results(payloads, 100))

    def test_exact_audit_metrics_require_both_backend_certificates(self):
        good = {"audits": [{"exact_metrics": {"gap": 0}, "exact_target_met": True},
                            {"exact_metrics": {"gap": 0}, "exact_target_met": False}]}
        bad = {"audits": [{"exact_metrics": {"gap": 0}, "exact_target_met": True},
                           {"exact_metrics": {"gap": 1}, "exact_target_met": True}]}
        missing = {"audits": [{"exact_metrics": None, "exact_target_met": True},
                               {"exact_metrics": None, "exact_target_met": True}]}
        self.assertTrue(benchmark._audit_metrics_equal(good))
        self.assertFalse(benchmark._audit_metrics_equal(bad))
        self.assertFalse(benchmark._audit_metrics_equal(missing))
        self.assertFalse(benchmark._audit_metrics_equal({"audits": []}))
        zero_gaps = {field: 0.0 for field in (
            "value_sb", "value_bb", "sb_best_response_value",
            "bb_best_response_value", "nash_conv")}
        self.assertTrue(benchmark._numeric_replay_pass({"audits": [
            {"numeric_differences": zero_gaps},
            {"numeric_differences": zero_gaps},
        ]}))
        incomplete = dict(zero_gaps)
        incomplete.pop("nash_conv")
        self.assertFalse(benchmark._numeric_replay_pass({"audits": [
            {"numeric_differences": incomplete},
            {"numeric_differences": zero_gaps},
        ]}))
        self.assertFalse(benchmark._numeric_replay_pass({"audits": [
            {"numeric_differences": zero_gaps | {"nash_conv": 1e-4}},
            {"numeric_differences": zero_gaps},
        ]}))

    def _payload(self, backend, iterations, sample, *, changed=False):
        probability = 0.5
        if changed and backend == "native" and iterations == 100 and sample == 1:
            probability = 0.4
        return {"backend": backend, "iterations": iterations,
                "strategy": [{"player": "sb", "hand": "AsAd", "history": [],
                              "actions": [{"history_key": "fold", "probability": probability}]}],
                "operator_statistics": {"rank_calls": 7},
                "native_training": ({"native_process_lifetime_peak_working_set_bytes": 999,
                                     "terminal_pair_board_checks": 10}
                                    if backend == "native" else None)}

    def _fake_child_runner(self, *, changed=False):
        def run(command, **_kwargs):
            if command[1:4] != ["-B", "-m", "scripts.benchmark_native_selected_operator"]:
                raise AssertionError(f"Unexpected subprocess command in synthetic test: {command!r}")
            backend = command[command.index("--child") + 1]
            iterations = int(command[command.index("--iterations") + 1])
            traced = "--traced" in command
            if iterations == 100:
                sample = "traced" if traced else len([
                    item for item in self.child_calls
                    if item[0] == 100 and item[1] == backend and not item[2]])
            else:
                sample = 0
            self.child_calls.append((iterations, backend, traced, sample))
            result = {"backend": backend, "iterations": iterations,
                      "traced": traced, "seconds": 1.0,
                      "python_tracemalloc_peak_bytes": 10 if traced else None,
                      "python_process_lifetime_peak_working_set_bytes": 20,
                      "native_process_lifetime_peak_working_set_bytes": 999 if backend == "native" else None,
                      "payload": self._payload(backend, iterations, sample, changed=changed)}
            return SimpleNamespace(stdout=json.dumps(result), stderr="", returncode=0)
        return run

    def _fake_verifier(self, directory, digest):
        directory = Path(directory)
        manifest_raw = (directory / "manifest.json").read_bytes()
        self.assertEqual(hashlib.sha256(manifest_raw).hexdigest(), digest)
        manifest = json.loads(manifest_raw)
        for name, expected in manifest["sha256"].items():
            raw = (directory / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
        target_met = "t1000" in directory.name
        gaps = {"value_sb": 0.0, "value_bb": 0.0,
                "sb_best_response_value": 0.0,
                "bb_best_response_value": 0.0, "nash_conv": 0.0}
        return {"training_calls": 0, "native_calls": 0,
                "audits": [{"numeric_differences": gaps,
                            "exact_metrics": {"gap": 0}, "exact_target_met": target_met},
                           {"numeric_differences": {"value_sb": 0.0, "value_bb": 0.0,
                                                      "sb_best_response_value": 0.0,
                                                      "bb_best_response_value": 0.0,
                                                      "nash_conv": 0.0},
                            "exact_metrics": {"gap": 0}, "exact_target_met": target_met}]}

    def _run_synthetic_batch(self, verifier):
        self.child_calls = []
        identity = {"commit": "frozen", "status": [], "sha256": {}}
        binary = {"source_sha256": "src", "executable_sha256": "bin"}
        files, fs_patches = self._memory_filesystem()
        with self._patch_all([
            patch.object(benchmark, "_identity", return_value=identity),
            patch.object(benchmark, "_native_identity", return_value=binary),
            patch.object(benchmark.subprocess, "run", side_effect=self._fake_child_runner()),
            patch.object(benchmark, "verify_saved", side_effect=verifier), *fs_patches,
        ]):
            output = Path("C:/benchmark-output/synthetic")
            result = benchmark.run(output, Path("C:/benchmark-output/native-selected-train.exe"))
        return result, files, output

    def test_full_orchestration_stages_raw_manifests_and_audits_both_budgets(self):
        self.child_calls = []
        identity = {"commit": "frozen", "status": [], "sha256": {}}
        binary = {"source_sha256": "src", "executable_sha256": "bin"}
        files, fs_patches = self._memory_filesystem()

        def fake_verify(directory, digest):
            return self._fake_verifier(directory, digest)

        with self._patch_all([
            patch.object(benchmark, "_identity", return_value=identity),
            patch.object(benchmark, "_native_identity", return_value=binary),
            patch.object(benchmark.subprocess, "run", side_effect=self._fake_child_runner()),
            patch.object(benchmark, "verify_saved", side_effect=fake_verify),
            *fs_patches,
        ]):
            output = Path("C:/benchmark-output/results")
            report = benchmark.run(output, Path("C:/benchmark-output/native-selected-train.exe"))
        self.assertEqual(report["outcome"], "complete")
        self.assertEqual(len(report["samples"]), 10)
        self.assertTrue(report["quality"]["t100"]["complete_strategy_rows_identical"])
        self.assertTrue(report["quality"]["t1000"]["sample_zero_exact_metrics_identical"])
        self.assertTrue(report["quality"]["t1000"]["sample_zero_numeric_replay_passed"])
        self.assertTrue(report["quality"]["t1000"]["sample_zero_exact_targets_met"])
        self.assertEqual(len(report["externally_pinnable_manifest_sha256"]), 2)
        self.assertIn(str(output / "audit-t100" / "t100-python-0.json"), files)
        self.assertIn(str(output / "audit-t1000" / "t1000-native-0.json"), files)

    def test_source_drift_stops_before_verifier(self):
        self.child_calls = []
        clean = {"commit": "frozen", "status": [], "sha256": {}}
        drift = {"commit": "changed", "status": [], "sha256": {}}
        binary = {"source_sha256": "src", "executable_sha256": "bin"}
        files, fs_patches = self._memory_filesystem()
        verifier = unittest.mock.Mock()
        with self._patch_all([
            patch.object(benchmark, "_identity", side_effect=[clean, drift]),
            patch.object(benchmark, "_native_identity", return_value=binary),
            patch.object(benchmark.subprocess, "run", side_effect=self._fake_child_runner()),
            patch.object(benchmark, "verify_saved", verifier), *fs_patches,
        ]):
            output = Path("C:/benchmark-output/drift")
            result = benchmark.run(output, Path("C:/benchmark-output/native-selected-train.exe"))
        self.assertEqual(result["outcome"], "source-or-binary-changed-before-audit")
        verifier.assert_not_called()
        self.assertIn(str(output / "partial-report.json"), files)

    def test_native_binary_drift_stops_before_verifier(self):
        self.child_calls = []
        identity = {"commit": "frozen", "status": [], "sha256": {}}
        before = {"source_sha256": "src", "executable_sha256": "bin"}
        after = {"source_sha256": "src", "executable_sha256": "changed"}
        files, fs_patches = self._memory_filesystem()
        verifier = unittest.mock.Mock()
        with self._patch_all([
            patch.object(benchmark, "_identity", return_value=identity),
            patch.object(benchmark, "_native_identity", side_effect=[before, after]),
            patch.object(benchmark.subprocess, "run", side_effect=self._fake_child_runner()),
            patch.object(benchmark, "verify_saved", verifier), *fs_patches,
        ]):
            output = Path("C:/benchmark-output/binary-drift")
            result = benchmark.run(output, Path("C:/benchmark-output/native-selected-train.exe"))
        self.assertEqual(result["outcome"], "source-or-binary-changed-before-audit")
        verifier.assert_not_called()
        self.assertIn(str(output / "partial-report.json"), files)

    def test_t100_any_paired_policy_difference_is_rejected(self):
        self.child_calls = []
        identity = {"commit": "frozen", "status": [], "sha256": {}}
        binary = {"source_sha256": "src", "executable_sha256": "bin"}
        files, fs_patches = self._memory_filesystem()
        with self._patch_all([
            patch.object(benchmark, "_identity", return_value=identity),
            patch.object(benchmark, "_native_identity", return_value=binary),
            patch.object(benchmark.subprocess, "run", side_effect=self._fake_child_runner(changed=True)),
            patch.object(benchmark, "verify_saved", side_effect=self._fake_verifier),
            *fs_patches,
        ]):
            output = Path("C:/benchmark-output/policy")
            report = benchmark.run(output, Path("C:/benchmark-output/native-selected-train.exe"))
        self.assertEqual(report["outcome"], "quality-miss")
        self.assertFalse(report["quality"]["t100"]["complete_strategy_rows_identical"])
        self.assertIn(str(output / "report.json"), files)

    def test_child_error_retains_stdout_stderr(self):
        error = CalledProcessError(2, ["child"], output=b"partial raw", stderr=b"failure detail")
        details = benchmark._child_error(error)
        self.assertEqual(details["child_stdout"], "partial raw")
        self.assertEqual(details["child_stderr"], "failure detail")

    def test_numeric_replay_mismatch_is_retained_as_quality_miss(self):
        def verifier(directory, digest):
            result = self._fake_verifier(directory, digest)
            result["audits"][0]["numeric_differences"]["value_sb"] = 1e-4
            return result
        report, files, output = self._run_synthetic_batch(verifier)
        self.assertEqual(report["outcome"], "quality-miss")
        self.assertFalse(report["quality"]["t100"]["sample_zero_numeric_replay_passed"])
        self.assertIn(str(output / "report.json"), files)

    def test_t1000_target_miss_is_retained_as_quality_miss(self):
        def verifier(directory, digest):
            result = self._fake_verifier(directory, digest)
            if Path(directory).name == "audit-t1000":
                for row in result["audits"]:
                    row["exact_target_met"] = False
            return result
        report, files, output = self._run_synthetic_batch(verifier)
        self.assertEqual(report["outcome"], "quality-miss")
        self.assertFalse(report["quality"]["t1000"]["sample_zero_exact_targets_met"])
        self.assertIn(str(output / "report.json"), files)

    def test_missing_metrics_cannot_pass_as_matching_none_values(self):
        def verifier(directory, digest):
            result = self._fake_verifier(directory, digest)
            for row in result["audits"]:
                row["exact_metrics"] = None
            return result
        report, files, output = self._run_synthetic_batch(verifier)
        self.assertEqual(report["outcome"], "quality-miss")
        self.assertFalse(report["quality"]["t100"]["sample_zero_exact_metrics_identical"])
        self.assertFalse(report["quality"]["t1000"]["sample_zero_exact_metrics_identical"])
        self.assertIn(str(output / "report.json"), files)

    def test_audit_failure_writes_partial_receipt_with_raw_samples(self):
        def verifier(_directory, _digest):
            raise RuntimeError("synthetic audit failure")
        report, files, output = self._run_synthetic_batch(verifier)
        self.assertEqual(report["outcome"], "audit-failed")
        self.assertIn(str(output / "t100-python-0.json"), files)
        partial = json.loads(files[str(output / "partial-report.json")])
        self.assertEqual(partial["failed_audit"]["error"], "synthetic audit failure")
        self.assertEqual(partial["completed_audits"], {})

    def test_nonzero_child_result_retains_output_without_identity_error_masking(self):
        self.child_calls = []
        identity = {"commit": "frozen", "status": [], "sha256": {}}
        binary = {"source_sha256": "src", "executable_sha256": "bin"}
        error = CalledProcessError(3, ["python", "child"], output=b"partial JSON",
                                   stderr=b"native trainer failed")
        files, fs_patches = self._memory_filesystem()
        with self._patch_all([
            patch.object(benchmark, "_identity", return_value=identity),
            patch.object(benchmark, "_native_identity", side_effect=[binary, OSError("manifest unreadable")]),
            patch.object(benchmark.subprocess, "run", side_effect=error), *fs_patches,
        ]):
            output = Path("C:/benchmark-output/child-failure")
            result = benchmark.run(output, Path("C:/benchmark-output/native-selected-train.exe"))
        self.assertEqual(result["outcome"], "failed-first-sample")
        failures = json.loads(files[str(output / "t100-python-0-failure.json")])
        self.assertEqual(failures["child_stdout"], "partial JSON")
        self.assertEqual(failures["child_stderr"], "native trainer failed")
        partial = json.loads(files[str(output / "partial-report.json")])
        self.assertTrue(any(row["identity"] == "native" for row in partial["identity_errors"]))


if __name__ == "__main__":
    unittest.main()
