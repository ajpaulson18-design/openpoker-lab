import json
import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import benchmark_flop_second_board_cfrplus as benchmark
from scripts import flop_second_board_cfrplus as adapter
from scripts import verify_flop_second_board_cfrplus_failure_publication as verifier


def saved_source_snapshot():
    report = json.loads((verifier.PUBLICATION / "index.json").read_text(encoding="utf-8"))
    source = report["source_before"]
    return {"revision": "f" * 40, "status": "",
            "source_lf_sha256": dict(source["source_lf_sha256"])}


class SavedFailureVerifierTests(unittest.TestCase):
    def test_actual_saved_failure_is_authenticated_without_expensive_calls(self):
        forbidden = AssertionError("saved-data verification called an expensive model path")
        snapshot = saved_source_snapshot()
        with patch.object(verifier, "_source_snapshot", side_effect=[snapshot, snapshot]), \
             patch.object(adapter.proof, "build_model", side_effect=forbidden), \
             patch.object(adapter.proof, "validate_model", side_effect=forbidden), \
             patch.object(adapter.proof.shared, "_exact_metrics", side_effect=forbidden), \
             patch.object(adapter.proof.physical, "replay", side_effect=forbidden), \
             patch.object(adapter.proof.physical, "independent_rank", side_effect=forbidden), \
             patch.object(adapter.cfr_plus, "train", side_effect=forbidden), \
             patch.object(benchmark, "_adapter", side_effect=forbidden):
            receipt = verifier.verify()
        self.assertEqual(receipt["status"], "saved-stopped-cfrplus-attempt-authenticated")
        self.assertEqual(receipt["iteration_cases_attempted"], [140])
        self.assertEqual(receipt["iteration_cases_completed"], [])
        self.assertEqual(receipt["iteration_cases_not_run"], [560])
        self.assertEqual(receipt["recorded_training_calls"], 1)
        self.assertEqual(receipt["recorded_numeric_replay_calls"], 1)
        self.assertTrue(all(value == 0 for value in receipt["live_calls"].values()))
        self.assertIn("not saved", receipt["numeric_replay_result"])
        self.assertIn("not evaluated", receipt["quality_result"])
        self.assertGreater(receipt["saved_exact_nash_conv_float"], 0.005)

    def test_raw_index_tampering_is_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "corpus"
            shutil.copytree(verifier.PUBLICATION, target)
            index = target / "index.json"
            raw = bytearray(index.read_bytes())
            raw[-1] ^= 1
            index.write_bytes(raw)
            with patch.object(verifier, "_json", side_effect=AssertionError("parsed before hash")):
                with self.assertRaisesRegex(ValueError, "Raw stopped-run index pin"):
                    verifier.verify(target)

    def test_gzip_tampering_is_rejected_before_decompression(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "corpus"
            shutil.copytree(verifier.PUBLICATION, target)
            payload = target / "case-140" / "reference.json.gz"
            raw = bytearray(payload.read_bytes())
            raw[-1] ^= 1
            payload.write_bytes(raw)
            with patch.object(verifier, "_inflate_bounded",
                              side_effect=AssertionError("decompressed before hash")):
                with self.assertRaisesRegex(ValueError, "T140 gzip receipt"):
                    verifier.verify(target)

    def test_current_source_map_mismatch_is_rejected(self):
        current = saved_source_snapshot()
        current["source_lf_sha256"][next(iter(current["source_lf_sha256"]))] = "0" * 64
        with patch.object(verifier, "_source_snapshot", side_effect=[current, current]):
            with self.assertRaisesRegex(ValueError, "source maps are not identical"):
                verifier.verify()

    def test_current_source_drift_during_authentication_is_rejected(self):
        before = saved_source_snapshot()
        after = copy.deepcopy(before)
        after["revision"] = "e" * 40
        with patch.object(verifier, "_source_snapshot", side_effect=[before, after]):
            with self.assertRaisesRegex(ValueError, "Current source changed"):
                verifier.verify()

    def test_extra_file_is_rejected_by_bounded_exact_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "corpus"
            shutil.copytree(verifier.PUBLICATION, target)
            (target / "extra.txt").write_text("unexpected", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "too many entries"):
                verifier.verify(target)

    def test_nonfinite_physical_header_and_boolean_boundary_are_rejected(self):
        index, payload = verifier._index(verifier.PUBLICATION)
        changed = copy.deepcopy(payload["observation"]["physical_policy"])
        changed["nash_conv"] = float("nan")
        with self.assertRaisesRegex(ValueError, "metric headers are malformed"):
            verifier._validate_physical_policy(changed)
        bad_index = copy.deepcopy(index)
        bad_index["boundaries"]["training_calls"] = True
        with self.assertRaisesRegex(ValueError, "expensive-call boundaries"):
            verifier._validate_observation(bad_index, payload)

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_constants(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            verifier._json(b'{"x":1,"x":2}')
        with self.assertRaises(ValueError):
            verifier._json(b'{"x":NaN}')


if __name__ == "__main__":
    unittest.main()
