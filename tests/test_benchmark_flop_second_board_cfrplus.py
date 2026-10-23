import gzip
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from scripts import benchmark_flop_second_board_cfrplus as bench
from scripts import flop_second_board_cfrplus_budget as budget
from scripts import flop_second_board_equivalence as proof
from scripts.verify_flop_class_owned_fingerprint_publication import AUTHORITY_KEYS


def source_state():
    return {"revision": "a" * 40, "status": "", "source_lf_sha256": {
        f"source-{index}": f"{index:064x}" for index in range(bench.SOURCE_COUNT)}}


def synthetic_report(iterations, source_hashes, *, quality=True):
    return {
        "status": "trained-policy-physically-verified",
        "iterations": iterations,
        "quality_target": 0.005,
        "quality_target_met": quality,
        "nash_conv": "1/100" if not quality else "1/500",
        "source_lf_sha256": dict(source_hashes),
        "raw_rows": [["row", iterations]],
        "normalized_class_policy": [["hand", [0.25, 0.75]]],
        "physical_policy": {"strategy": [["physical", iterations]]},
        "preparation_forbidden_calls": {key: 0 for key in AUTHORITY_KEYS},
        "diagnostic_forbidden_calls": {key: 0 for key in AUTHORITY_KEYS},
        "training_calls": 1,
        "preparation_progress": {"preparation_ranker_attempts": 4134,
                                 "preparation_rank_calls": 4134},
    }


class FakeAdapter:
    def __init__(self, source_hashes, *, fail_at=None, all_quality_pass=False):
        self.source_hashes = source_hashes
        self.fail_at = fail_at
        self.all_quality_pass = all_quality_pass
        self.admission_calls = []
        self.solve_calls = []

    def admit_request(self, iterations=560):
        self.admission_calls.append(iterations)
        return budget.admit_second_board_request(iterations)

    def solve_second_board(self, iterations=560, *, observation=None):
        self.solve_calls.append(iterations)
        observation.update(phase="model-build", progress={"iterations": iterations})
        if iterations == self.fail_at:
            observation.update(phase="failed", primary_error="synthetic failure")
            raise ValueError("synthetic adapter failure")
        model = proof.build_model()
        for _ in range(3):
            proof._make_model(None)
        for worlds in ((None,) * 170, (None,) * 5940):
            proof.shared._exact_metrics(model, worlds, {})
        proof.physical.replay(model, {})
        proof._project({}, model)
        proof._expected_rows(model)
        import pokerlab.cfr_plus
        pokerlab.cfr_plus.train(None, (), {}, 1)
        observation.update(phase="complete", progress={"iterations": iterations, "done": True})
        return synthetic_report(iterations, self.source_hashes,
                                quality=self.all_quality_pass or iterations != 140)


class ProtocolAndInstrumentationTests(unittest.TestCase):
    def test_actual_frozen_protocol_loads_and_full_request_admits_without_poker_work(self):
        with patch.object(proof, "build_model", side_effect=AssertionError("model")), \
             patch.object(proof.physical, "independent_rank", side_effect=AssertionError("rank")), \
             patch.object(bench.publication, "verify", side_effect=AssertionError("authentication")), \
             patch("pokerlab.cfr_plus.train", side_effect=AssertionError("training")):
            raw, spec = bench._protocol()
            admitted = bench._preflight(spec)
        self.assertGreater(len(raw), 0)
        self.assertEqual(spec, bench.expected_protocol())
        self.assertEqual(admitted["aggregate_logical_work"], 126_289_636)

    def test_protocol_is_fresh_and_reservations_are_exact(self):
        first, second = bench.expected_protocol(), bench.expected_protocol()
        self.assertEqual(first, second)
        first["request"]["iterations"].append(999)
        self.assertEqual(bench.expected_protocol()["request"]["iterations"], [140, 560])
        limits = second["limits"]
        self.assertEqual(limits["aggregate_logical_work_reservation"], 126_289_636)
        self.assertLessEqual(limits["aggregate_logical_work_reservation"],
                             limits["aggregate_logical_work_cap"])
        self.assertEqual(limits["aggregate_proof_pass_reservation"], 8_077_400)
        self.assertEqual(limits["exact_world_node_term_reservation"], 1_209_780)
        self.assertEqual(limits["numeric_world_node_term_reservation"], 1_176_120)
        self.assertEqual(limits["maximum_row_action_slots"], 4_000_000)
        self.assertEqual(limits["source_files"], 54)

    def test_preflight_admits_both_complete_cases(self):
        adapter = FakeAdapter(source_state()["source_lf_sha256"])
        admitted = bench._preflight(bench.expected_protocol(), adapter)
        self.assertEqual(adapter.admission_calls, [140, 560])
        self.assertEqual(admitted["aggregate_logical_work"], 126_289_636)
        self.assertEqual([item["requested_iterations"] for item in admitted["cases"]], [140, 560])

    def test_rank_receipt_is_idempotent_and_rejects_bool_or_calls_above_attempts(self):
        report = {"boundaries": {}}
        record = {}
        progress = {"preparation_ranker_attempts": 4134, "preparation_rank_calls": 4134}
        bench._record_preparation_rank_calls(report, record, progress)
        bench._record_preparation_rank_calls(report, record, progress)
        self.assertEqual(report["boundaries"]["preparation_ranker_attempts"], 4134)
        self.assertEqual(report["boundaries"]["preparation_rank_calls"], 4134)
        for malformed in (
            {"preparation_ranker_attempts": True, "preparation_rank_calls": 1},
            {"preparation_ranker_attempts": 2, "preparation_rank_calls": 3},
        ):
            with self.assertRaises(ValueError):
                bench._record_preparation_rank_calls({"boundaries": {}}, {}, malformed)

    def test_shared_wrappers_count_before_call_restore_and_keep_train_outside_guard(self):
        import pokerlab.cfr_plus

        originals = (proof.build_model, proof._make_model, proof.shared._exact_metrics,
                     proof.physical.replay, proof._project, proof._expected_rows,
                     pokerlab.cfr_plus.train, proof.shared.independent_guard)
        observed = {}
        @contextmanager
        def fake_guard(*args, **kwargs):
            yield {}

        with patch.object(proof, "build_model", lambda: object()), \
             patch.object(proof, "_make_model", lambda *args, **kwargs: object()), \
             patch.object(proof.shared, "_exact_metrics", lambda *args, **kwargs: 0), \
             patch.object(proof.physical, "replay", lambda *args, **kwargs: 0), \
             patch.object(proof, "_project", lambda *args, **kwargs: {}), \
             patch.object(proof, "_expected_rows", lambda *args, **kwargs: {"row": 2}), \
             patch.object(proof.shared, "independent_guard", fake_guard), \
             patch.object(pokerlab.cfr_plus, "train", lambda *args, **kwargs: "trained"):
            with bench._instrument(observed, object()):
                for _ in range(2):
                    proof.build_model()
                for _ in range(10):
                    proof._make_model(None)
                for _ in range(2):
                    proof.shared._exact_metrics(None, (None,) * 170, {})
                    proof.shared._exact_metrics(None, (None,) * 5940, {})
                    proof.physical.replay(None, {})
                    proof._project({}, None)
                    proof._expected_rows(None)
                # Invoke the dynamically patched shared trainer exactly twice.
                pokerla = __import__("pokerlab.cfr_plus", fromlist=["train"])
                pokerla.train(None)
                pokerla.train(None)
                self.assertEqual(observed["training_calls"], 2)
                self.assertEqual(observed["exact_metric_calls"], 4)
                self.assertEqual(observed["exact_world_node_terms"],
                                 bench.EXACT_WORLD_NODE_TERM_RESERVATION)
                self.assertEqual(observed["numeric_replay_calls"], 2)
                self.assertEqual(observed["numeric_world_node_terms"],
                                 bench.NUMERIC_WORLD_NODE_TERM_RESERVATION)
                self.assertEqual(observed["row_action_slots"], 4)
                with proof.shared.independent_guard(), self.assertRaisesRegex(
                        ValueError, "inside a forbidden-call guard"):
                    pokerla.train(None)
        self.assertEqual((proof.build_model, proof._make_model, proof.shared._exact_metrics,
                          proof.physical.replay, proof._project, proof._expected_rows,
                          pokerla.train, proof.shared.independent_guard), originals)
        self.assertEqual(observed["training_calls"], 2)


class RunHarnessTests(unittest.TestCase):
    def _run_with(self, temp, adapter, *, snapshots=None, snapshot_side_effect=None,
                  output_writer=None, fallback=None, index_writer=None):
        source = source_state()
        raw_protocol = b"synthetic canonical protocol\n"
        state = source if snapshots is None else snapshots
        stack = [
            patch.object(bench, "_protocol", return_value=(raw_protocol, bench.expected_protocol())),
            patch.object(bench, "_adapter", return_value=adapter),
            patch.object(bench, "_snapshot", side_effect=(snapshot_side_effect or [state, state])),
            patch.object(proof, "build_model", lambda: SimpleNamespace()),
            patch.object(proof, "_make_model", lambda *args, **kwargs: SimpleNamespace()),
            patch.object(proof.shared, "_exact_metrics", lambda *args, **kwargs: 0),
            patch.object(proof.physical, "replay", lambda *args, **kwargs: 0),
            patch.object(proof, "_project", lambda *args, **kwargs: {}),
            patch.object(proof, "_expected_rows", lambda *args, **kwargs: {"one": 2}),
        ]
        import pokerlab.cfr_plus
        stack.append(patch.object(pokerlab.cfr_plus, "train", lambda *args, **kwargs: None))
        if output_writer is not None:
            stack.append(patch.object(bench, "_write_case", side_effect=output_writer))
        if fallback is not None:
            stack.append(patch.object(bench, "_raw_fallback", side_effect=fallback))
        if index_writer is not None:
            stack.append(patch.object(bench, "_write_index", side_effect=index_writer))
        for context in stack:
            context.__enter__()
        try:
            return bench.run(Path(temp) / "result")
        finally:
            for context in reversed(stack):
                context.__exit__(None, None, None)

    def test_run_admits_before_output_authenticates_then_runs_two_fresh_cases_once(self):
        state = source_state()
        adapter = FakeAdapter(state["source_lf_sha256"])
        with tempfile.TemporaryDirectory() as temp:
            report = self._run_with(temp, adapter)
            target = Path(temp) / "result"
            self.assertTrue((target / "index.json").is_file())
            self.assertEqual(adapter.admission_calls, [140, 560])
            self.assertEqual(adapter.solve_calls, [140, 560])
            self.assertEqual(report["status"], "verified-quality-miss")
            self.assertEqual([case["status"] for case in report["cases"]],
                             ["quality-miss", "quality-pass"])
            self.assertEqual(report["boundaries"]["training_calls"], 2)
            self.assertEqual(report["boundaries"]["model_proof_calls"], 6)
            self.assertEqual(report["boundaries"]["preparation_ranker_attempts"], 8268)
            self.assertEqual(report["boundaries"]["preparation_rank_calls"], 8268)
            for case, iterations in zip(report["cases"], (140, 560)):
                self.assertEqual(case["payload"]["path"], f"case-{iterations}/reference.json.gz")
                with gzip.open(target / case["payload"]["path"], "rt", encoding="utf-8") as stream:
                    payload = json.load(stream)
                self.assertEqual(payload["adapter_report"]["iterations"], iterations)
                self.assertIn("raw_rows", payload["adapter_report"])
                self.assertIn("normalized_class_policy", payload["adapter_report"])
                self.assertIn("physical_policy", payload["adapter_report"])
                self.assertIn("progress", payload["observation"])

    def test_all_quality_passes_receive_verified_quality_pass_status(self):
        state = source_state()
        adapter = FakeAdapter(state["source_lf_sha256"], all_quality_pass=True)
        with tempfile.TemporaryDirectory() as temp:
            report = self._run_with(temp, adapter)
        self.assertEqual(report["status"], "verified-quality-pass")
        self.assertEqual([case["status"] for case in report["cases"]],
                         ["quality-pass", "quality-pass"])

    def test_first_case_error_stops_without_retry_and_serializes_observation(self):
        state = source_state()
        adapter = FakeAdapter(state["source_lf_sha256"], fail_at=140)
        with tempfile.TemporaryDirectory() as temp:
            report = self._run_with(temp, adapter)
            self.assertEqual(adapter.solve_calls, [140])
            self.assertEqual(report["status"], "error")
            self.assertIn("synthetic adapter failure", report["errors"][0]["message"])
            self.assertEqual(report["cases"][0]["payload"]["path"], "case-140/reference.json.gz")
            with gzip.open(Path(temp) / "result" / "case-140" / "reference.json.gz",
                           "rt", encoding="utf-8") as stream:
                payload = json.load(stream)
            self.assertIsNone(payload["adapter_report"])
            self.assertEqual(payload["observation"]["primary_error"], "synthetic failure")

    def test_preflight_failure_happens_before_output_or_source_snapshot(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(bench, "_protocol", return_value=(b"x", bench.expected_protocol())), \
             patch.object(bench, "_preflight", side_effect=ValueError("admission failed")), \
             patch.object(bench.previous.previous, "_output_directory") as output, \
             patch.object(bench, "_snapshot") as snapshot:
            report = bench.run(Path(temp) / "result")
        output.assert_not_called()
        snapshot.assert_not_called()
        self.assertFalse((Path(temp) / "result").exists())
        self.assertEqual(report["errors"][0]["message"], "ValueError: admission failed")

    def test_double_output_failure_keeps_full_report_in_return_and_index_marker(self):
        state = source_state()
        adapter = FakeAdapter(state["source_lf_sha256"], fail_at=140)
        def fail_gzip(*args, **kwargs):
            raise OSError("gzip output failed")
        def fail_raw(*args, **kwargs):
            raise OSError("raw fallback failed")
        with tempfile.TemporaryDirectory() as temp:
            report = self._run_with(temp, adapter, output_writer=fail_gzip, fallback=fail_raw)
            self.assertIn("unserialized_reports", report)
            self.assertEqual(report["unserialized_reports"][0]["payload"]["observation"]["primary_error"],
                             "synthetic failure")
            self.assertIs(report["unserialized_report_retention"]["durably_saved"], False)
            saved = json.loads((Path(temp) / "result" / "index.json").read_bytes())
            self.assertIs(saved["unserialized_report_retention"]["durably_saved"], False)
            self.assertNotIn("unserialized_reports", saved)
            self.assertIn("synthetic adapter failure", report["errors"][0]["message"])

    def test_gzip_failure_uses_bounded_raw_fallback_with_full_success_report(self):
        state = source_state()
        adapter = FakeAdapter(state["source_lf_sha256"], all_quality_pass=True)
        def fail_gzip(*args, **kwargs):
            raise OSError("synthetic gzip failure")
        with tempfile.TemporaryDirectory() as temp:
            report = self._run_with(temp, adapter, output_writer=fail_gzip)
            self.assertEqual(report["status"], "verified-quality-pass")
            self.assertEqual(adapter.solve_calls, [140, 560])
            case = report["cases"][0]
            self.assertIn("fallback_payload", case)
            fallback_path = Path(temp) / "result" / case["fallback_payload"]["path"]
            payload = json.loads(fallback_path.read_bytes())
            self.assertEqual(payload["adapter_report"]["iterations"], 140)
            self.assertIn("raw_rows", payload["adapter_report"])

    def test_source_after_and_index_errors_preserve_first_case_error(self):
        state = source_state()
        adapter = FakeAdapter(state["source_lf_sha256"], fail_at=140)
        original_write_index = bench._write_index
        index_writes = [0]
        def fail_final_index(directory, report):
            index_writes[0] += 1
            if index_writes[0] >= 2:
                raise OSError("index write failed")
            return original_write_index(directory, report)
        with tempfile.TemporaryDirectory() as temp:
            report = self._run_with(
                temp, adapter, snapshot_side_effect=[state, OSError("source changed")],
                index_writer=fail_final_index)
        self.assertIn("synthetic adapter failure", report["errors"][0]["message"])
        self.assertTrue(any("source changed" in error["message"] for error in report["errors"]))
        self.assertTrue(any("index write failed" in error["message"] for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
