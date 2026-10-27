import hashlib
import json
import subprocess
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import benchmark_direct_shared_topology as benchmark


class DirectTopologyBenchmarkTests(unittest.TestCase):
    def _payload(self, *, changed=False, backend="literal", iterations=100, sample=0):
        probability = .5
        if changed and backend == "direct" and iterations == 100 and sample == 1:
            probability = .4
        metric = 1.25
        if changed == "metric" and backend == "direct" and iterations == 100 and sample == 2:
            metric = 1.3
        return {
            "info_sets": 1,
            "strategy": [{"history": [], "actions": [{"action": "fold",
                                                               "probability": probability}]}],
            "operator_census": {"information_sets": 1,
                                "strategy_storage": {"rows": 1},
                                "shared_strategy_storage": {"rows": 1},
                                "shared_public_topology": {"vertices": 99}},
            "value_sb": metric, "value_bb": -metric,
            "sb_best_response_value": metric + 1,
            "bb_best_response_value": -metric + 1,
            "nash_conv": 2., "sb_gain": .1, "bb_gain": .2,
            "exploitability": 1., "public_batched_training_pot_anchor": 100.,
            "private_pair_probabilities": [{"sb": "AsAd", "bb": "KhKd", "p": .25}],
            "candidate_private_pairs": 4, "compatible_private_pairs": 3,
            "worlds": 22, "pair_runout_preflight_checks": 66,
            "operator_statistics": {"scope": backend,
                                     "post_constructor_pair_board_checks": 10,
                                     "rank_calls": 4},
            "rank_cache": {"board_capacity": 64, "hits": 3, "misses": 4,
                           "evictions": 0, "retained_peak_rank_slots": 200,
                           "retained_plus_construction_peak_reference_slots": 200},
            "native_training": None,
        }

    def _fake_child(self, calls, *, changed=False):
        def run(command, **kwargs):
            expected = ["-B", "-m", "scripts.benchmark_direct_shared_topology"]
            if command[1:4] != expected:
                raise AssertionError(f"Unexpected child command: {command!r}")
            backend = command[command.index("--child") + 1]
            iterations = int(command[command.index("--iterations") + 1])
            traced = "--traced" in command
            if iterations == 100:
                sample = "traced" if traced else sum(
                    1 for t, b, tr, _ in calls if t == 100 and b == backend and not tr)
            else:
                sample = 0
            calls.append((iterations, backend, traced, sample))
            result = {"backend": backend, "iterations": iterations,
                      "public_topology": backend, "native_calls": 0,
                      "traced": traced, "seconds": 1.0,
                      "python_tracemalloc_peak_bytes": 123 if traced else None,
                      "python_process_lifetime_peak_working_set_bytes": 456,
                      "payload": self._payload(changed=changed, backend=backend,
                                               iterations=iterations, sample=sample)}
            return SimpleNamespace(stdout=json.dumps(result).encode(), stderr=b"", returncode=0)
        return run

    def _verifier(self, directory, digest):
        directory = Path(directory)
        manifest_raw = (directory / "manifest.json").read_bytes()
        self.assertEqual(hashlib.sha256(manifest_raw).hexdigest(), digest)
        manifest = json.loads(manifest_raw)
        for name, expected in manifest["sha256"].items():
            self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), expected)
        iterations = 1000 if directory.name.endswith("1000") else 100
        selected = [name for name in manifest["sha256"]
                    if name.startswith(f"t{iterations}-") and name.endswith(".json")]
        self.assertTrue(selected)
        self.assertIn(f"t{iterations}-literal-0.json", selected)
        self.assertIn(f"t{iterations}-direct-0.json", selected)
        gaps = {name: 0. for name in benchmark.NUMERIC_AUDIT_FIELDS}
        metrics = {name: "1/2" for name in benchmark.EXACT_METRIC_FIELDS}
        target = iterations == 1000
        return {"audits": [
            {"numeric_differences": dict(gaps), "exact_metrics": dict(metrics),
             "exact_target_met": target},
            {"numeric_differences": dict(gaps), "exact_metrics": dict(metrics),
             "exact_target_met": target}], "training_calls": 0, "native_calls": 0}

    def _run(self, *, changed=False, verifier=None, source_drift=False):
        calls = []
        identity = {"commit": "frozen", "status": [], "sha256": {}}
        identities = ([identity, {"commit": "drift", "status": [], "sha256": {}}]
                      if source_drift else [identity, identity])
        temp = benchmark.ROOT.parent / f"shared-topology-test-{uuid.uuid4().hex}"
        temp.mkdir()
        output = temp / "study"
        with patch.object(benchmark, "_identity", side_effect=identities), \
             patch.object(benchmark, "_script_sha256", return_value="runner-hash"), \
             patch.object(benchmark.platform, "platform",
                          return_value="synthetic-test-platform"), \
             patch.object(benchmark.subprocess, "run",
                          side_effect=self._fake_child(calls, changed=changed)), \
             patch.object(benchmark, "verify_saved",
                          side_effect=verifier or self._verifier):
            report = benchmark.run(output)
        return report, output, calls

    def test_schedule_is_alternating_and_has_fixed_call_counts(self):
        schedule = benchmark._schedule()
        t100 = [x for x in schedule if x[0] == 100 and not x[3]]
        self.assertEqual([x[1] for x in t100],
                         ["literal", "direct", "direct", "literal", "literal", "direct"])
        self.assertEqual(sum(x[0] == 100 and x[3] for x in schedule), 2)
        self.assertEqual(sum(x[0] == 1000 for x in schedule), 2)

    def test_child_passes_explicit_python_topology_and_measurement_modes(self):
        payload = {"native_training": None}
        with patch.object(benchmark, "_request", return_value=object()), \
             patch.object(benchmark, "solve_four_street_operator", return_value=payload) as solve, \
             patch.object(benchmark, "_rss", return_value=456):
            result = benchmark.child("direct", 100, False)
        self.assertEqual(solve.call_args.kwargs, {
            "strategy_storage": "packed", "rank_cache_boards": 64,
            "public_topology": "direct"})
        self.assertEqual(result["public_topology"], "direct")
        self.assertEqual(result["python_process_lifetime_peak_working_set_bytes"], 456)
        self.assertIsNone(result["python_tracemalloc_peak_bytes"])
        self.assertEqual(result["native_calls"], 0)

    def test_nonzero_child_retains_raw_stdout_and_stderr_without_retry(self):
        calls = []
        def fail(command, **_kwargs):
            calls.append(command)
            return SimpleNamespace(stdout=b"partial json", stderr=b"child failed", returncode=7)
        identity = {"commit": "frozen", "status": [], "sha256": {}}
        output_parent = benchmark.ROOT.parent / f"shared-topology-failure-{uuid.uuid4().hex}"
        output_parent.mkdir()
        output = output_parent / "study"
        with patch.object(benchmark, "_identity", return_value=identity), \
             patch.object(benchmark, "_script_sha256", return_value="runner-hash"), \
             patch.object(benchmark.subprocess, "run", side_effect=fail):
            result = benchmark.run(output)
        self.assertEqual(result["outcome"], "failed-first-sample")
        self.assertEqual(len(calls), 1)
        self.assertEqual((output / "t100-literal-0.json").read_bytes(), b"partial json")
        failure = json.loads((output / "t100-literal-0-failure.json").read_text())
        self.assertEqual(failure["child_stdout"], "partial json")
        self.assertEqual(failure["child_stderr"], "child failed")

    def test_audit_gates_require_exact_metrics_numeric_fields_and_targets(self):
        metrics = {name: "1/2" for name in benchmark.EXACT_METRIC_FIELDS}
        good = {"audits": [{"exact_metrics": dict(metrics), "exact_target_met": True,
                            "numeric_differences": {k: 0. for k in benchmark.NUMERIC_AUDIT_FIELDS}},
                           {"exact_metrics": dict(metrics), "exact_target_met": True,
                            "numeric_differences": {k: 0. for k in benchmark.NUMERIC_AUDIT_FIELDS}}]}
        self.assertTrue(benchmark._audit_metrics_equal(good))
        self.assertTrue(benchmark._numeric_replay_pass(good))
        self.assertTrue(benchmark._both_exact_targets_met(good))
        missing = {"audits": [dict(good["audits"][0], exact_metrics=None), good["audits"][1]]}
        self.assertFalse(benchmark._audit_metrics_equal(missing))
        subset = {"audits": [dict(row, numeric_differences={"value_sb": 0.})
                             for row in good["audits"]]}
        self.assertFalse(benchmark._numeric_replay_pass(subset))
        self.assertFalse(benchmark._both_exact_targets_met({"audits": [
            good["audits"][0], dict(good["audits"][1], exact_target_met=False)]}))

    def test_full_orchestration_closes_audit_manifests_and_retains_t100_miss(self):
        def verifier(directory, digest):
            result = self._verifier(directory, digest)
            if Path(directory).name == "audit-t100":
                for row in result["audits"]:
                    row["exact_target_met"] = False
            return result
        report, output, calls = self._run(verifier=verifier)
        self.assertEqual(report["outcome"], "complete")
        self.assertEqual(len(calls), 10)
        self.assertEqual(len(report["samples"]), 10)
        self.assertTrue(report["quality"]["t1000"]["sample_zero_exact_targets_met"])
        self.assertNotIn("sample_zero_exact_targets_met", report["quality"]["t100"])
        for t in (100, 1000):
            directory = output / f"audit-t{t}"
            manifest = json.loads((directory / "manifest.json").read_text())
            self.assertTrue(all((directory / name).exists() for name in manifest["sha256"]))
            self.assertEqual((directory / "reference-0.json").read_bytes(),
                             (directory / f"t{t}-literal-0.json").read_bytes())
            self.assertEqual((directory / "operator-0.json").read_bytes(),
                             (directory / f"t{t}-direct-0.json").read_bytes())

    def test_policy_and_metric_mismatch_are_retained_as_quality_misses(self):
        for change in (True, "metric"):
            report, _, _ = self._run(changed=change)
            self.assertEqual(report["outcome"], "quality-miss")

    def test_t1000_target_miss_and_missing_metrics_fail_quality_gate(self):
        def target_miss(directory, digest):
            result = self._verifier(directory, digest)
            if Path(directory).name == "audit-t1000":
                for row in result["audits"]:
                    row["exact_target_met"] = False
            return result
        report, _, _ = self._run(verifier=target_miss)
        self.assertEqual(report["outcome"], "quality-miss")

        def missing_metrics(directory, digest):
            result = self._verifier(directory, digest)
            for row in result["audits"]:
                row["exact_metrics"] = None
            return result
        report, _, _ = self._run(verifier=missing_metrics)
        self.assertEqual(report["outcome"], "quality-miss")

    def test_source_drift_prevents_saved_audit(self):
        with patch.object(benchmark, "verify_saved") as verify:
            report, output, calls = self._run(source_drift=True)
        self.assertEqual(report["outcome"], "source-changed-before-audit")
        self.assertEqual(len(calls), 10)
        self.assertFalse(verify.called)
        self.assertTrue((output / "partial-report.json").exists())

    def test_audit_failure_keeps_raw_calls_and_partial_receipt(self):
        def fail(_directory, _digest):
            raise RuntimeError("synthetic audit failure")
        report, output, _ = self._run(verifier=fail)
        self.assertEqual(report["outcome"], "audit-failed")
        self.assertTrue((output / "t100-literal-0.json").exists())
        partial = json.loads((output / "partial-report.json").read_text())
        self.assertEqual(partial["failed_audit"]["error"], "synthetic audit failure")


if __name__ == "__main__":
    unittest.main()
