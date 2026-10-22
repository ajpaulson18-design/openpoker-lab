import hashlib
import json
import unittest
from unittest.mock import Mock, patch

from scripts import flop_class_call_measurement as measurement


class FlopClassCallMeasurementTests(unittest.TestCase):
    def test_calls_once_and_returns_canonical_bytes_and_hashes(self):
        report = {"quality_target_met": True, "z": [2, 1], "artifact_sha256": "artifact", "a": 3}
        call = Mock(return_value=report)
        raw, metadata = measurement.measure_call(call)
        expected = json.dumps(report, sort_keys=True, separators=(",", ":"),
                              allow_nan=False).encode("utf-8") + b"\n"
        call.assert_called_once_with()
        self.assertEqual(raw, expected)
        self.assertEqual(metadata["raw_sha256"], hashlib.sha256(expected).hexdigest())
        self.assertEqual(metadata["artifact_sha256"], "artifact")
        self.assertIs(metadata["quality_target_met"], True)
        self.assertIs(metadata["allocation_trace"], False)
        self.assertIsNone(metadata["python_traced_peak_bytes"])
        self.assertIn("runtime", metadata)
        self.assertTrue(metadata["started_at_utc"].endswith("+00:00"))
        self.assertTrue(metadata["finished_at_utc"].endswith("+00:00"))

    def test_wall_and_process_timers_include_serialization_and_hash(self):
        wall = [10.0]
        cpu = [20.0]
        real_dumps = json.dumps

        def serialize(*args, **kwargs):
            wall[0] += 2.5
            cpu[0] += 1.25
            return real_dumps(*args, **kwargs)

        with patch.object(measurement, "perf_counter", side_effect=lambda: wall[0]), \
             patch.object(measurement, "process_time", side_effect=lambda: cpu[0]), \
             patch.object(measurement.json, "dumps", side_effect=serialize):
            _, metadata = measurement.measure_call(lambda: {"value": 1})
        self.assertEqual(metadata["wall_seconds"], 2.5)
        self.assertEqual(metadata["process_seconds"], 1.25)

    def test_allocation_mode_records_traced_peak_and_stops(self):
        stop = Mock(wraps=measurement.tracemalloc.stop)
        with patch.object(measurement.tracemalloc, "stop", stop):
            raw, metadata = measurement.measure_call(lambda: {"value": [0] * 1000}, allocation=True)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertIs(metadata["allocation_trace"], True)
        self.assertIs(type(metadata["python_traced_peak_bytes"]), int)
        self.assertGreater(metadata["python_traced_peak_bytes"], 0)
        self.assertNotIn("rss", metadata)
        stop.assert_called_once_with()
        self.assertFalse(measurement.tracemalloc.is_tracing())

    def test_allocation_trace_stops_when_call_raises_and_error_propagates(self):
        failure = RuntimeError("synthetic call failure")
        call = Mock(side_effect=failure)
        stop = Mock()
        with patch.object(measurement.tracemalloc, "start") as start, \
             patch.object(measurement.tracemalloc, "stop", stop), \
             patch.object(measurement.tracemalloc, "get_traced_memory") as traced:
            with self.assertRaisesRegex(RuntimeError, "synthetic call failure"):
                measurement.measure_call(call, allocation=True)
        call.assert_called_once_with()
        start.assert_called_once_with()
        stop.assert_called_once_with()
        traced.assert_not_called()

    def test_existing_trace_is_preserved_without_calling_or_stopping_it(self):
        call = Mock(return_value={})
        with patch.object(measurement.tracemalloc, "is_tracing", return_value=True), \
             patch.object(measurement.tracemalloc, "start") as start, \
             patch.object(measurement.tracemalloc, "stop") as stop:
            with self.assertRaisesRegex(ValueError, "inactive trace"):
                measurement.measure_call(call, allocation=True)
        call.assert_not_called()
        start.assert_not_called()
        stop.assert_not_called()

    def test_invalid_call_or_allocation_flag_rejects(self):
        with self.assertRaises(TypeError):
            measurement.measure_call(None)
        with self.assertRaises(TypeError):
            measurement.measure_call(lambda: {}, allocation=1)


if __name__ == "__main__":
    unittest.main()
