"""Native DAG study acceptance and failure-preservation controls."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import benchmark_native_selected_dag as study

class NativeDagStudyTests(unittest.TestCase):
    def test_fixed_schedule_and_explicit_direct_modes(self):
        self.assertEqual([row[1] for row in study._schedule()],
            ["python", "native", "native", "python", "python", "native", "python", "native", "python", "native"])
        for backend in ("python", "native"):
            with patch.dict(study.os.environ, {"OPENPOKER_NATIVE_SELECTED_DAG_EXE": "chosen-helper"}), \
                 patch.object(study, "_request", return_value=object()), \
                 patch.object(study, "solve_four_street_operator", return_value={}) as solve, \
                 patch.object(study, "_rss", return_value=456):
                result = study.child(backend, 100, False)
            self.assertEqual(solve.call_args.kwargs, {"strategy_storage": "packed", "rank_cache_boards": 64,
                "public_topology": "direct", "native_executable": "chosen-helper" if backend == "native" else None})
            self.assertEqual(result["native_calls"], int(backend == "native"))
            self.assertIsNone(result["native_process_lifetime_peak_working_set_bytes"])

    def test_first_failure_preserves_streams_and_never_retries(self):
        with TemporaryDirectory(dir=study.ROOT.parent) as parent:
            output = Path(parent) / "study"
            with patch.dict(study.os.environ, {"OPENPOKER_NATIVE_SELECTED_DAG_EXE": "chosen-helper"}), \
                 patch.object(study, "_identity", return_value={"commit": "frozen", "status": "", "sha256": {}}), \
                 patch.object(study, "executable_identity", return_value={"protocol": "DAG"}), \
                 patch.object(study.subprocess, "run", return_value=SimpleNamespace(returncode=2, stdout=b"partial", stderr=b"failed")) as run:
                report = study.run(output)
            self.assertEqual(report["outcome"], "failed-first-sample")
            self.assertEqual(run.call_count, 1)
            self.assertEqual((output / "t100-python-0.json").read_bytes(), b"partial")
            self.assertEqual((output / "t100-python-0.stderr.txt").read_bytes(), b"failed")
            self.assertTrue((output / "partial-report.json").exists())

    def test_quality_acceptance_rejects_missing_replay_and_preserves_target_miss(self):
        metrics = {key: "1/2" for key in study.EXACT_METRIC_FIELDS}
        rows = [{"exact_metrics": dict(metrics), "exact_target_met": True,
                 "numeric_differences": {key: 0.0 for key in study.NUMERIC_AUDIT_FIELDS}} for _ in range(2)]
        audit = {"audits": rows}
        self.assertTrue(study._audit_metrics_equal(audit))
        self.assertTrue(study._numeric_replay_pass(audit))
        rows[1]["exact_target_met"] = False
        self.assertFalse(study._both_exact_targets_met(audit))
        rows[1]["numeric_differences"] = {"value_sb": 0.0}
        self.assertFalse(study._numeric_replay_pass(audit))
        rows[1]["exact_metrics"]["nash_conv"] = "1/3"
        self.assertFalse(study._audit_metrics_equal(audit))
