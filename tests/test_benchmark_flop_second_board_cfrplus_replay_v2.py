from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import benchmark_flop_second_board_cfrplus_replay_v2 as bench
from scripts import flop_second_board_equivalence as proof
from tests.test_benchmark_flop_second_board_cfrplus import FakeAdapter
from scripts import flop_second_board_cfrplus_replay_v2 as adapter_v2


def source_state():
    return {"revision": "a" * 40, "status": "", "source_lf_sha256": {
        f"source/{i}": f"{i:064x}" for i in range(58)}}


class FakeV2Adapter(FakeAdapter):
    def __init__(self, *args, omit_receipt=False, extra_replay=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.omit_receipt = omit_receipt
        self.extra_replay = extra_replay

    def _source_snapshot(self):
        return {"revision": "a" * 40, "status": "", "source_lf_sha256": self.source_hashes}

    def solve_second_board(self, iterations, *, observation):
        report = super().solve_second_board(iterations, observation=observation)
        if self.extra_replay:
            proof.physical.replay(None, {})
        report["schema_version"] = adapter_v2.VERSION
        if not self.omit_receipt:
            raw = {key: 0.0 for key in proof.METRICS}
            raw["scalar_absolute_gaps"] = {key: 0.0 for key in proof.METRICS}
            raw.update(adapter_v2.EXPECTED_COUNTS)
            receipt = {"numeric_metrics": {key: raw[key] for key in proof.METRICS},
                       "scalar_absolute_gaps": dict(raw["scalar_absolute_gaps"]),
                       "counts": dict(adapter_v2.EXPECTED_COUNTS), "raw_result_key_count": 13}
            report.update(numeric_replay_raw_receipt=raw, numeric_replay_v2_receipt=receipt)
        return report


class ReplayV2HarnessTests(unittest.TestCase):
    def test_real_protocol_and_both_admissions_are_rank_free(self):
        forbidden = AssertionError("unexpected poker computation")
        with patch.object(proof, "build_model", side_effect=forbidden), \
             patch.object(proof.physical, "independent_rank", side_effect=forbidden), \
             patch.object(bench.publication, "verify", side_effect=forbidden), \
             patch("pokerlab.cfr_plus.train", side_effect=forbidden):
            _, spec = bench._protocol()
            admission = bench._preflight(spec)
        self.assertEqual(spec["protocol_id"], bench.PROTOCOL)
        self.assertEqual(admission["aggregate_logical_work"], 126_289_636)
        self.assertEqual(admission["source_files"], 58)
        self.assertEqual(spec["replay_boundary"]["raw_result_keys"], 13)

    def _run(self, directory, adapter, source_after=None):
        state = source_state()
        import pokerlab.cfr_plus
        with ExitStack() as stack:
            stack.enter_context(patch.object(bench, "_adapter", return_value=adapter))
            stack.enter_context(patch.object(bench, "_snapshot", side_effect=[
                state, state if source_after is None else source_after]))
            for module, name, value in (
                (proof, "build_model", object()), (proof, "_make_model", object()),
                (proof.shared, "_exact_metrics", 0), (proof.physical, "replay", 0),
                (proof, "_project", {}), (proof, "_expected_rows", {"row": 2}),
                (pokerlab.cfr_plus, "train", None),
            ):
                stack.enter_context(patch.object(module, name, return_value=value))
            return bench.run(Path(directory) / "result")

    def test_two_fresh_cases_use_inherited_caps_and_keep_a_quality_miss(self):
        state = source_state()
        adapter = FakeV2Adapter(state["source_lf_sha256"])
        with tempfile.TemporaryDirectory() as directory:
            report = self._run(directory, adapter)
            self.assertTrue((Path(directory) / "result/index.json").is_file())
        self.assertEqual(adapter.solve_calls, [140, 560])
        self.assertEqual(report["protocol_id"], bench.PROTOCOL)
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["status"], "verified-quality-miss")
        self.assertEqual(report["boundaries"]["training_calls"], 2)
        self.assertEqual(report["boundaries"]["model_proof_calls"], 6)
        self.assertEqual(report["boundaries"]["preparation_rank_calls"], 8268)
        self.assertEqual([case["numeric_replay_calls_in_case"] for case in report["cases"]], [1, 1])
        import gzip
        import json
        # Verify actual lossless persistence of all raw replay fields.
        with tempfile.TemporaryDirectory() as directory:
            saved_report = self._run(directory, FakeV2Adapter(state["source_lf_sha256"]))
            for case in saved_report["cases"]:
                with gzip.open(Path(directory) / "result" / case["payload"]["path"], "rt") as stream:
                    payload = json.load(stream)
                self.assertEqual(len(payload["adapter_report"]["numeric_replay_raw_receipt"]), 13)
                bench._validate_replay_receipt(payload["adapter_report"])

    def test_first_case_failure_stops_and_source_drift_does_not_mask_it(self):
        state = source_state()
        adapter = FakeV2Adapter(state["source_lf_sha256"], fail_at=140)
        changed = source_state()
        changed["revision"] = "b" * 40
        with tempfile.TemporaryDirectory() as directory:
            report = self._run(directory, adapter, source_after=changed)
        self.assertEqual(adapter.solve_calls, [140])
        self.assertEqual(report["status"], "error")
        self.assertIn("synthetic adapter failure", report["errors"][0]["message"])
        self.assertEqual(report["errors"][1]["phase"], "source-finalization")
        self.assertEqual(len(report["cases"]), 1)
        self.assertIsNotNone(report["cases"][0]["payload"])

    def test_delegated_source_map_must_have_exactly_58_entries(self):
        for count in (57, 59):
            adapter = FakeV2Adapter({f"s/{i}": f"{i:064x}" for i in range(count)})
            with self.subTest(count=count), patch.object(bench, "_adapter", return_value=adapter):
                with self.assertRaisesRegex(ValueError, "exactly 58"):
                    bench._snapshot()

    def test_missing_replay_receipt_and_two_replays_in_one_case_stop_the_batch(self):
        for option, message in (("omit_receipt", "13-field"), ("extra_replay", "one-replay")):
            adapter = FakeV2Adapter(source_state()["source_lf_sha256"], **{option: True})
            with self.subTest(option=option), tempfile.TemporaryDirectory() as directory:
                report = self._run(directory, adapter)
            self.assertEqual(report["status"], "error")
            self.assertEqual(adapter.solve_calls, [140])
            self.assertIn(message, report["errors"][0]["message"])
            self.assertEqual(report["cases"][0]["status"], "error")
            if option == "extra_replay":
                self.assertEqual(report["boundaries"]["numeric_replay_calls"], 1)
                self.assertEqual(report["cases"][0]["numeric_replay_attempts_in_case"], 2)


if __name__ == "__main__":
    unittest.main()
