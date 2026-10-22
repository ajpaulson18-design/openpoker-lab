from contextlib import ExitStack
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import benchmark_flop_second_board_reference as batch


class SecondBoardBatchTests(unittest.TestCase):
    def receipt(self):
        return {"status": "saved-owned-fingerprint-census-authenticated",
                "raw_sha256": batch.prerequisite.RAW_REPORT_SHA256,
                "report_sha256": batch.prerequisite.REPORT_SHA256,
                "fingerprint_calls": 0, "full_validations": 0, "training_calls": 0}

    def payload(self):
        return {"scope": "fresh-physical-reference-and-candidate-partition-only",
                "physical": {"worlds_view": [["synthetic"]] * 5940,
                             "tree_view": [{"synthetic": True}],
                             "tree_census": {"public_states": 1},
                             "worlds_sha256": "test-only"},
                "candidate_partition": {
                    "board": ["7c", "8d", "9h"],
                    "candidate_only": True, "physical_provenance": False,
                    "input_completeness": "unverified-caller-supplied-records",
                    "physical_world_count": 5940, "compatible_pair_count": 3,
                    "turn_card_count": 49, "river_class_count": 77, "turn_class_count": 33},
                "claims": {"class_or_tree_equivalence_proved": False,
                           "policy_projection_or_lift_proved": False,
                           "physical_best_response_equality_proved": False,
                           "training_performed": False}}

    def setup_run(self, stack, *, prepare=None, snapshots=None):
        spec = batch.expected_protocol()
        stack.enter_context(mock.patch.object(batch, "_protocol", return_value=(
            json.dumps(spec, sort_keys=True).encode(), spec)))
        stable = {"revision": "a" * 40, "status": "", "source_lf_sha256": {"synthetic": "b" * 64}}
        stack.enter_context(mock.patch.object(batch, "_snapshot",
                                             side_effect=snapshots or [stable] * 3))
        stack.enter_context(mock.patch.object(batch.prerequisite, "verify",
                                             return_value=self.receipt()))
        if prepare is None:
            def prepare(plan, progress):
                progress.update({"phase": "complete", "physical_builds_attempted": 1,
                                 "physical_builds_completed": 1, "candidate_builds_attempted": 1,
                                 "candidate_builds_completed": 1, "physical_world_rows": 5940,
                                 "world_rows_validated": 5940, "candidate_world_rows": 5940,
                                 "tree_nodes_validated": 1, "preparation_rank_calls": 4,
                                 "preparation_ranker_attempts": 4, "recheck_rank_calls": 4,
                                 "recheck_ranker_attempts": 4})
                return self.payload()
        return stack.enter_context(mock.patch.object(batch.reference, "prepare_reference",
                                                    side_effect=prepare))

    def test_actual_protocol_and_full_admission_have_no_model_work(self):
        with mock.patch.object(batch.reference.physical, "prepare_oracle",
                               side_effect=AssertionError("must admit before oracle")), \
             mock.patch.object(batch.reference.physical, "independent_rank",
                               side_effect=AssertionError("must admit before ranker")):
            raw, spec = batch._protocol()
            admission = batch._preflight(spec)
        self.assertEqual(hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(), batch.SPEC_SHA256)
        self.assertEqual(admission["limits"]["total_best_five_combinations"], 498960)
        self.assertEqual(admission["limits"]["source_files"], 44)

    def test_preflight_rejects_tampered_request_before_auth_or_prepare(self):
        spec = batch.expected_protocol()
        spec["request"]["physical_oracle_builds"] = 2
        with tempfile.TemporaryDirectory() as temp, \
             mock.patch.object(batch, "_protocol", return_value=(b"{}", spec)), \
             mock.patch.object(batch.prerequisite, "verify",
                               side_effect=AssertionError("auth before admission")), \
             mock.patch.object(batch.reference, "prepare_reference",
                               side_effect=AssertionError("prepare before admission")):
            target = Path(temp) / "new"
            report = batch.run(target)
            self.assertEqual(report["status"], "error")
            self.assertFalse(target.exists())
            self.assertIn("request differs", report["errors"][0]["message"])

    def test_lowered_reference_limit_fails_full_admission(self):
        spec = batch.expected_protocol()
        with mock.patch.object(batch.reference, "MAX_PREPARATION_RANK_CALLS", 11879):
            with self.assertRaisesRegex(ValueError, "limits differ"):
                batch._preflight(spec)

    def test_synthetic_success_retains_full_payload_and_exact_guard_inventory(self):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            prepare = self.setup_run(stack)
            target = Path(temp) / "new"
            report = batch.run(target)
            self.assertEqual(report["status"], "complete", report["errors"])
            self.assertEqual(prepare.call_count, 1)
            self.assertEqual(len(report["authority_calls"]), 41)
            self.assertTrue(all(value == 0 for value in report["authority_calls"].values()))
            raw = gzip.decompress((target / "reference.json.gz").read_bytes())
            self.assertEqual(json.loads(raw), self.payload())
            self.assertEqual(report["payload"]["raw_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(json.loads((target / "index.json").read_text())["status"], "complete")
            self.assertEqual(report["summary"]["candidate"]["turn_class_count"], 33)

    def test_first_preparation_error_preserves_progress_final_sources_and_real_guard(self):
        def fail(plan, progress):
            progress["preparation_rank_calls_attempted"] = 3
            raise RuntimeError("original reference failure")

        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            prepare = self.setup_run(stack, prepare=fail)
            target = Path(temp) / "new"
            report = batch.run(target)
            self.assertEqual(prepare.call_count, 1)
            self.assertEqual(report["status"], "error")
            self.assertIn("original reference failure", report["errors"][0]["message"])
            self.assertEqual(report["progress"]["preparation_rank_calls_attempted"], 3)
            self.assertEqual(len(report["authority_calls"]), 41)
            self.assertEqual(report["source_before"], report["source_after"])
            self.assertIsNone(report["payload"])
            self.assertTrue((target / "index.json").exists())

    def test_guard_violation_retains_nonzero_actual_counter_and_first_error(self):
        def fail(plan, progress):
            from pokerlab import postflop_solver
            postflop_solver.solve_postflop(None)

        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            self.setup_run(stack, prepare=fail)
            report = batch.run(Path(temp) / "new")
            self.assertEqual(report["status"], "error")
            self.assertEqual(report["authority_calls"]["pokerlab.postflop_solver.solve_postflop"], 1)
            self.assertIn("solve_postflop", report["errors"][0]["message"])
            self.assertEqual(len(report["authority_calls"]), 41)

    def test_source_change_after_partial_failure_does_not_replace_first_error(self):
        stable = {"revision": "a" * 40, "status": "", "source_lf_sha256": {}}
        dirty = {**stable, "status": "dirty"}
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            self.setup_run(stack, prepare=lambda plan, progress: (_ for _ in ()).throw(
                RuntimeError("first failure")), snapshots=[stable, stable, dirty])
            report = batch.run(Path(temp) / "new")
            self.assertIn("first failure", report["errors"][0]["message"])
            self.assertEqual(report["errors"][1]["phase"], "source-finalization")

    def test_payload_caps_precede_writes_and_partial_output_is_retained(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(batch, "MAX_PAYLOAD_BYTES", 4):
            target = Path(temp)
            with self.assertRaisesRegex(ValueError, "Raw payload exceeds"):
                batch._write_payload(target, {"too-long": [1, 2]})
            self.assertTrue((target / "reference.json.gz.partial").exists())
            self.assertFalse((target / "reference.json.gz").exists())
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(batch, "MAX_GZIP_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "Compressed output exceeds"):
                batch._write_payload(Path(temp), {})
            self.assertLessEqual((Path(temp) / "reference.json.gz.partial").stat().st_size, 1)

    def test_output_rejects_existing_and_inside_checkout_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                batch._output_directory(Path(temp))
        with self.assertRaises(ValueError):
            batch._output_directory(batch.ROOT / "uncreated-second-board-test-output")

    def test_cli_uses_the_actual_supported_execution_state_schema(self):
        result = {"status": "complete", "errors": [], "progress": {}, "index_sha256": "test"}
        with mock.patch.object(batch, "run", return_value=result) as runner, \
             mock.patch("builtins.print"):
            self.assertEqual(batch.main(["--output", "synthetic-output"]), 0)
        state = runner.call_args.kwargs["execution_state"]
        self.assertEqual(batch.previous.diagnostic.evidence._execution_state(state),
                         {"mode": "ordinary-process", "system_required": False})


if __name__ == "__main__":
    unittest.main()
