import copy
from fractions import Fraction
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import benchmark_flop_second_board_cfrplus_replay_v2 as harness
from scripts import flop_second_board_cfrplus_replay_v2 as adapter
from scripts import flop_second_board_equivalence as proof
from scripts import verify_flop_second_board_cfrplus_replay_v2_publication as verifier


def _snapshot():
    index = json.loads((verifier.PUBLICATION / "index.json").read_bytes())
    return {"revision": "f" * 40, "status": "",
            "source_lf_sha256": dict(index["source_before"]["source_lf_sha256"])}


class SavedReplayV2VerifierTests(unittest.TestCase):
    def test_fraction_numerator_bit_bound_precedes_metric_arithmetic(self):
        metrics = {key: "0" for key in verifier.METRICS}
        metrics[verifier.METRICS[0]] = str(1 << 4097)
        with self.assertRaisesRegex(ValueError, "too large"):
            verifier._metrics({"audit": {"exact_metrics": metrics}}, 140)

    def test_authenticates_both_saved_cases_without_expensive_calls(self):
        forbidden = AssertionError("saved-data verification called a model or replay path")
        with patch.object(harness, "_snapshot", return_value=_snapshot()), \
             patch.object(adapter.proof, "build_model", side_effect=forbidden), \
             patch.object(adapter.proof, "validate_model", side_effect=forbidden), \
             patch.object(adapter.proof.shared, "_exact_metrics", side_effect=forbidden), \
             patch.object(adapter.proof.physical, "replay", side_effect=forbidden), \
             patch.object(adapter.proof.physical, "independent_rank", side_effect=forbidden), \
             patch.object(adapter.v1.cfr_plus, "train", side_effect=forbidden):
            receipt = verifier.verify()
        self.assertEqual(receipt["status"], "saved-second-board-replay-v2-batch-authenticated")
        self.assertEqual(receipt["iteration_cases_attempted"], [140, 560])
        self.assertEqual(receipt["iteration_cases_completed"], [140, 560])
        self.assertEqual(receipt["quality_outcomes"], {"140": "miss", "560": "pass"})
        self.assertEqual(float(Fraction(receipt["case_results"][0]["exact_nash_conv"])),
                         0.014166984012911272)
        self.assertEqual(float(Fraction(receipt["case_results"][1]["exact_nash_conv"])),
                         0.0016464625267553663)
        self.assertTrue(all(value == 0 for value in receipt["live_calls"].values()))
        self.assertEqual(receipt["recorded_training_calls"], 2)

    def test_raw_index_pin_precedes_json_parse(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "batch"
            shutil.copytree(verifier.PUBLICATION, target)
            index = target / "index.json"
            raw = bytearray(index.read_bytes())
            raw[-2] ^= 1
            index.write_bytes(raw)
            with patch.object(verifier, "_json", side_effect=AssertionError("parsed before pin")):
                with self.assertRaisesRegex(ValueError, "Raw replay-v2 index pin"):
                    verifier.verify(target)

    def test_gzip_pin_precedes_inflate(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "batch"
            shutil.copytree(verifier.PUBLICATION, target)
            path = target / "case-140" / "reference.json.gz"
            raw = bytearray(path.read_bytes())
            raw[-1] ^= 1
            path.write_bytes(raw)
            with patch.object(harness, "_snapshot", return_value=_snapshot()), \
                 patch.object(verifier.gzip, "GzipFile", side_effect=AssertionError("inflated before pin")):
                with self.assertRaisesRegex(ValueError, "Case gzip pin"):
                    verifier.verify(target)

    def test_clean_source_map_mismatch_and_mid_check_drift_fail(self):
        wrong = _snapshot()
        wrong["source_lf_sha256"][next(iter(wrong["source_lf_sha256"]))] = "0" * 64
        with patch.object(harness, "_snapshot", return_value=wrong):
            with self.assertRaisesRegex(ValueError, "Current clean source map differs"):
                verifier.verify()
        before, after = _snapshot(), _snapshot()
        after["revision"] = "e" * 40
        with patch.object(harness, "_snapshot", side_effect=[before, after]):
            with self.assertRaisesRegex(ValueError, "Current source changed"):
                verifier.verify()

    def test_extra_artifact_is_rejected_by_bounded_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "batch"
            shutil.copytree(verifier.PUBLICATION, target)
            (target / "unexpected.txt").write_text("extra", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "too many entries"):
                verifier.verify(target)

    def test_strict_json_and_boolean_count_alias_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            verifier._json(b'{"a":1,"a":2}')
        with self.assertRaises(ValueError):
            verifier._json(b'{"a":NaN}')
        with self.assertRaises(ValueError):
            verifier._json(b'{"a":1e999}')
        index = verifier._index(verifier.PUBLICATION)
        index["boundaries"]["training_calls"] = True
        with self.assertRaisesRegex(ValueError, "expensive-call boundaries"):
            verifier._validate_index(index)

    def test_semantic_raw_replay_count_tamper_is_rejected_after_digest_updates(self):
        index = verifier._index(verifier.PUBLICATION)
        payload = verifier._payload(verifier.PUBLICATION, index["cases"][0])
        report = payload["adapter_report"]
        report["numeric_replay_raw_receipt"]["checked_information_sets"] = True
        report["artifact_sha256"] = proof._digest(
            {key: value for key, value in report.items() if key != "artifact_sha256"})
        payload["observation"]["v2_report"] = copy.deepcopy(report)
        payload["observation"]["numeric_replay_raw"]["checked_information_sets"] = True
        with self.assertRaisesRegex(ValueError, "Raw numeric replay gaps or counts"):
            verifier._validate_case(index, index["cases"][0], payload)


if __name__ == "__main__":
    unittest.main()
