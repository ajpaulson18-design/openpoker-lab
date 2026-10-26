"""Lifecycle controls for the separate native four-street benchmark runner."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import benchmark_native_four_street as benchmark


def _manifest():
    return json.loads(benchmark.MANIFEST.read_text(encoding="utf-8"))


class NativeFourStreetBenchmarkLifecycleTests(unittest.TestCase):
    def test_manifest_pins_iterations_and_every_alternating_pair(self):
        manifest = _manifest()
        self.assertEqual(benchmark._validate_manifest(manifest)["iterations"], 1000)
        bad_order = json.loads(json.dumps(manifest))
        bad_order["comparison"]["order_by_repeat"][1] = ["python", "python"]
        with self.assertRaisesRegex(ValueError, "schedule"):
            benchmark._validate_manifest(bad_order)
        bad_budget = json.loads(json.dumps(manifest))
        bad_budget["comparison"]["iterations"] = 100
        with self.assertRaisesRegex(ValueError, "selectors"):
            benchmark._validate_manifest(bad_budget)

    def test_dirty_source_is_recorded_and_stops_before_identity_or_solve(self):
        snapshot = {"head": "1" * 40, "status_porcelain": [" M source.py"],
                    "source_sha256": {"source.py": "2" * 64}}
        output = Path("Z:/native-public-benchmark-test/attempt")
        written = {}

        def save_json(path, value):
            written[Path(path).name] = value

        with patch.object(benchmark, "ROOT", Path("C:/fake-checkout")), \
                patch.object(benchmark, "_source_snapshot", return_value=snapshot), \
                patch.object(benchmark, "_write_json", side_effect=save_json), \
                patch.object(Path, "mkdir"), patch.object(Path, "exists", return_value=False), \
                patch.object(benchmark, "executable_identity") as identity, \
                patch.object(benchmark, "solve_four_street") as solve:
            result = benchmark.run(output, "unused-native-exe")
        self.assertEqual(result["outcome"], "rejected-dirty-source")
        self.assertEqual(written["report.json"]["outcome"], "rejected-dirty-source")
        identity.assert_not_called()
        solve.assert_not_called()

    def test_first_native_failure_is_saved_without_retry(self):
        manifest = _manifest()
        clean = {"head": "1" * 40, "status_porcelain": [],
                 "source_sha256": {"pokerlab.py": "2" * 64}}
        payload = {
            "strategy": [], "worlds": 1, "public_states": 1, "decisions": 0,
            "value_sb": 0.0, "value_bb": 0.0,
            "sb_best_response_value": 0.0, "bb_best_response_value": 0.0,
            "nash_conv": 0.0,
        }

        class Result:
            def to_json(self):
                return json.dumps({"payload": payload}, separators=(",", ":"))

        def solve(request, **kwargs):
            if kwargs:
                raise RuntimeError("first native launch failure")
            return Result()

        output = Path("Z:/native-public-benchmark-test/attempt")
        calls, written_json, written_bytes = [], {}, {}

        def counted_solve(request, **kwargs):
            calls.append(dict(kwargs))
            return solve(request, **kwargs)

        def save_json(path, value):
            written_json[Path(path).name] = value

        def save_bytes(path, value):
            written_bytes[Path(path).name] = value

        with patch.object(benchmark, "ROOT", Path("C:/fake-checkout")), \
                patch.object(benchmark, "_source_snapshot", return_value=clean), \
                patch.object(benchmark, "executable_identity", return_value={"protocol": "test"}), \
                patch.object(benchmark, "solve_four_street", side_effect=counted_solve), \
                patch.object(benchmark, "replay_policy", return_value={}), \
                patch.object(benchmark, "compare_result", return_value={}), \
                patch.object(benchmark, "_write_json", side_effect=save_json), \
                patch.object(benchmark, "_write_bytes", side_effect=save_bytes), \
                patch.object(Path, "mkdir"), patch.object(Path, "exists", return_value=False):
            result = benchmark.run(output, "unused-native-exe")

        self.assertEqual(result["outcome"], "failed-first-sample")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls, [{}, {"native_executable": "unused-native-exe"}])
        self.assertIn("repeat-1-python-raw-envelope.json", written_bytes)
        failure = written_json["repeat-1-native-failure.json"]
        self.assertEqual(failure["error"], "first native launch failure")
        report = written_json["report.json"]
        self.assertEqual(report["outcome"], "failed-first-sample")
        self.assertEqual(len(report["failures"]), 1)

    def test_complete_call_timer_includes_result_serialization(self):
        clean = {"head": "1" * 40, "status_porcelain": [],
                 "source_sha256": {"pokerlab.py": "2" * 64}}
        payload = {
            "strategy": [{"player": "sb", "hand": "AsAd", "history": [],
                          "actions": [{"history_key": "check", "probability": 1.0}]}],
            "worlds": 1, "public_states": 1, "decisions": 1,
            "value_sb": 0.0, "value_bb": 0.0,
            "sb_best_response_value": 0.0, "bb_best_response_value": 0.0,
            "nash_conv": 0.0,
        }
        clock = [0.0]

        class Result:
            def to_json(self):
                clock[0] += 3.0
                return json.dumps({"payload": payload}, separators=(",", ":"))

        written_json, written_bytes = {}, {}
        output = Path("Z:/native-public-benchmark-test/complete")

        def save_json(path, value):
            written_json[Path(path).name] = value

        def save_bytes(path, value):
            written_bytes[Path(path).name] = value

        with patch.object(benchmark, "ROOT", Path("C:/fake-checkout")), \
                patch.object(benchmark, "_source_snapshot", return_value=clean), \
                patch.object(benchmark, "executable_identity", return_value={"protocol": "test"}), \
                patch.object(benchmark, "solve_four_street", return_value=Result()), \
                patch.object(benchmark, "replay_policy", return_value={}), \
                patch.object(benchmark, "compare_result", return_value={}), \
                patch.object(benchmark, "_write_json", side_effect=save_json), \
                patch.object(benchmark, "_write_bytes", side_effect=save_bytes), \
                patch.object(benchmark.time, "perf_counter", side_effect=lambda: clock[0]), \
                patch.object(Path, "mkdir"), patch.object(Path, "exists", return_value=False):
            report = benchmark.run(output, "unused-native-exe")

        self.assertEqual(report["outcome"], "complete")
        self.assertEqual(report["policy_compatibility"], "pass")
        self.assertEqual(len(report["runs"]), 6)
        self.assertTrue(all(row["elapsed_seconds"] == 3.0 for row in report["runs"]))
        self.assertEqual(report["python_median_seconds"], 3.0)
        self.assertEqual(report["native_median_seconds"], 3.0)
        self.assertEqual(report["native_over_python_median_speedup"], 1.0)
        self.assertEqual(len(written_bytes), 6)
        self.assertIn("report.json", written_json)


if __name__ == "__main__":
    unittest.main()
