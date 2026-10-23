import gzip
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import benchmark_flop_second_board_equivalence as bench
from scripts import flop_second_board_equivalence as proof


def synthetic_policy():
    return {"board": ["7c", "8d", "9h"], "strategy": [
        {"player": "oop", "hand": "AdAs", "history": ["turn@Tc"],
         "actions": [{"name": "check", "probability": 0.5},
                     {"name": "bet", "probability": 0.5}]},
        {"player": "oop", "hand": "AdAs", "history": ["turn@Jc"],
         "actions": [{"name": "check", "probability": 0.5},
                     {"name": "bet", "probability": 0.5}]},
    ]}


class AdmissionAndInstrumentationTests(unittest.TestCase):
    def test_real_protocol_and_full_preflight_reservation(self):
        raw, spec = bench._protocol()
        admitted = bench._preflight(spec)
        self.assertEqual(bench.SPEC_SHA256,
                         "f27d10e7f23968d5d8a6826e098b7fa5cbb643b2263f9b73077c98e4878e2198")
        self.assertEqual(admitted["request"]["full_model_proofs"], 10)
        self.assertEqual(admitted["request"]["exact_metric_calls"], 8)
        self.assertEqual(admitted["request"]["numeric_replays"], 4)
        self.assertEqual(admitted["request"]["projection_attempts"], 6)
        self.assertEqual(admitted["limits"]["named_reservation"], 16849200)
        self.assertLessEqual(admitted["limits"]["named_reservation"],
                             admitted["limits"]["named_cap"])
        self.assertTrue(raw.endswith(b"\n"))

    def test_run_stops_at_preflight_before_auth_or_model_preparation(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "result"
            with patch.object(bench, "_preflight", side_effect=ValueError("full request rejected")), \
                 patch.object(proof.prerequisite, "verify") as authenticate, \
                 patch.object(proof, "build_model") as build:
                report = bench.run(output)
            authenticate.assert_not_called()
            build.assert_not_called()
            self.assertFalse(output.exists())
            self.assertEqual(report["status"], "error")
            self.assertIn("full request rejected", report["errors"][0]["message"])
            self.assertIsNone(report["source_before"])

    def test_instrumentation_records_full_families_and_restores_callables(self):
        originals = {("proof", "_make_model"): proof._make_model,
                     ("shared", "_exact_metrics"): proof.shared._exact_metrics,
                     ("physical", "replay"): proof.physical.replay,
                     ("proof", "_project"): proof._project,
                     ("proof", "_expected_rows"): proof._expected_rows}
        observed = {}
        with patch.object(proof, "_make_model", lambda *a, **k: None), \
             patch.object(proof.shared, "_exact_metrics", lambda *a, **k: None), \
             patch.object(proof.physical, "replay", lambda *a, **k: None), \
             patch.object(proof, "_project", lambda *a, **k: None), \
             patch.object(proof, "_expected_rows", lambda *a, **k: {"a": 1, "b": 2}):
            with bench._instrument(observed):
                for _ in range(10):
                    proof._make_model(None, None, 0)
                for world_count in (170,) * 4 + (5940,) * 4:
                    proof.shared._exact_metrics(None, (None,) * world_count, {})
                for _ in range(4):
                    proof.physical.replay(None, None)
                for _ in range(6):
                    proof._project(None, None)
                for _ in range(2):
                    proof._expected_rows(None)
            self.assertEqual(observed["full_model_proofs"], 10)
            self.assertEqual(observed["exact_metric_calls"], 8)
            self.assertEqual(observed["exact_world_node_terms"], bench.EXACT_TERM_RESERVATION)
            self.assertEqual(observed["numeric_replays"], 4)
            self.assertEqual(observed["numeric_world_node_terms"], bench.NUMERIC_TERM_RESERVATION)
            self.assertEqual(observed["projection_attempts"], 6)
            self.assertEqual(observed["expected_row_tables"], 2)
            self.assertEqual(observed["row_action_slots"], 8)
        self.assertIs(proof._make_model, originals[("proof", "_make_model")])
        self.assertIs(proof.shared._exact_metrics, originals[("shared", "_exact_metrics")])
        self.assertIs(proof.physical.replay, originals[("physical", "replay")])
        self.assertIs(proof._project, originals[("proof", "_project")])
        self.assertIs(proof._expected_rows, originals[("proof", "_expected_rows")])

    def test_failed_boundary_attempt_is_counted_and_wrapper_restored(self):
        original = proof._make_model
        observed = {}
        with patch.object(proof, "_make_model", side_effect=RuntimeError("probe failure")):
            with bench._instrument(observed):
                with self.assertRaisesRegex(RuntimeError, "probe failure"):
                    proof._make_model(None, None, 0)
                self.assertEqual(observed["full_model_proofs"], 1)
        self.assertIs(proof._make_model, original)


class ControlRetentionTests(unittest.TestCase):
    def test_negative_rejections_retain_both_complete_payloads(self):
        model = type("Model", (), {"turns": {"Tc": "T00", "Jc": "T00"}, "rivers": {}})()
        original = synthetic_policy()
        records = []
        persisted = []

        def save(directory, name, payload):
            persisted.append((name, payload))
            return {"path": name + "/fixture.json.gz", "raw_bytes": 100,
                    "gzip_bytes": 50, "raw_sha256": "a" * 64, "gzip_sha256": "b" * 64}

        with patch.object(bench, "_payload", side_effect=save), \
             patch.object(proof, "_project", side_effect=ValueError(
                 "Within-class physical-card probabilities differ bitwise")):
            bench._negative(model, original, "within-class-card-variation", Path("unused"), records)
        with patch.object(bench, "_payload", side_effect=save), \
             patch.object(proof, "_project", side_effect=ValueError(
                 "Exact audit requires binary64 probabilities summing exactly to one")):
            bench._negative(model, original, "near-normalized", Path("unused"), records)
        self.assertEqual([row["status"] for row in records], ["expected-rejection"] * 2)
        self.assertEqual([row[0] for row in persisted], ["within-class-card-variation", "near-normalized"])
        self.assertEqual(len(persisted[0][1]["strategy"]), 2)
        self.assertEqual(persisted[1][1]["strategy"][0]["actions"][1]["probability"], 2.0 ** -54)

    def test_positive_control_keeps_primary_error_and_partial_observation_on_write_failure(self):
        policy = synthetic_policy()
        observation = {"physical_policy": policy, "class_policy": [[0, "AdAs", [], [0.5, 0.5]]],
                       "phase": "physical-replay", "exact_compact_metrics": {"value_oop": "1/2"}}
        primary = ValueError("control metric mismatch")
        record_list = []
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(proof, "audit_control", side_effect=lambda *a, **k:
                           (k["observation"].update(observation), (_ for _ in ()).throw(primary))[1]), \
             patch.object(bench, "_payload", side_effect=OSError("synthetic gzip write failure")):
            with self.assertRaisesRegex(ValueError, "control metric mismatch") as raised:
                bench._positive(None, "check-call", Path(temp), record_list)
            record = record_list[0]
            receipt = record["fallback_payload"]
            raw = (Path(temp) / receipt["path"]).read_bytes()
            self.assertEqual(json.loads(raw), policy)
            self.assertEqual(receipt["raw_bytes"], len(raw))
        record = record_list[0]
        self.assertIs(raised.exception, primary)
        self.assertEqual(record["status"], "error")
        self.assertIn("class_policy", record)
        self.assertIn("serialization_error", record)
        self.assertEqual(receipt["format"], "raw-json-failure-fallback")

    def test_both_output_failures_keep_primary_error_and_expose_available_policy(self):
        policy, primary, records = synthetic_policy(), ValueError("first audit error"), []
        def fail(*args, observation):
            observation.update(physical_policy=policy)
            raise primary
        with patch.object(proof, "audit_control", side_effect=fail), \
             patch.object(bench, "_payload", side_effect=OSError("gzip unavailable")), \
             patch.object(bench, "_raw_fallback", side_effect=OSError("raw unavailable")):
            with self.assertRaises(ValueError) as raised:
                bench._positive(None, "check-call", Path("unused"), records)
        self.assertIs(raised.exception, primary)
        self.assertIs(primary.second_board_unserialized_policy, policy)
        self.assertIn("fallback_error", records[0])
        self.assertEqual(len(records[0]["retained_partial_paths"]), 2)

    def test_six_payload_writes_are_lossless_and_distinct(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            records = [bench._payload(root, "control-%d" % i,
                                      {"mode": str(i), "policy": synthetic_policy()})
                       for i in range(6)]
            self.assertEqual(len({row["path"] for row in records}), 6)
            for receipt in records:
                path = root / receipt["path"]
                with gzip.open(path, "rb") as stream:
                    raw = stream.read()
                self.assertEqual(len(raw), receipt["raw_bytes"])
                self.assertEqual(json.loads(raw)["policy"], synthetic_policy())
                self.assertEqual(path.stat().st_size, receipt["gzip_bytes"])


class RunFinalizationAndCliTests(unittest.TestCase):
    def test_run_retains_unwritten_policy_in_api_and_marks_index_not_durable(self):
        policy, primary = synthetic_policy(), ValueError("first control failure")
        state = {"revision": "a" * 40, "status": "", "source_lf_sha256": {}}
        model = SimpleNamespace(census={}, partition={}, worlds=())
        def fail(*args, observation):
            observation["physical_policy"] = policy
            raise primary
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(bench, "_snapshot", return_value=state), \
             patch.object(proof, "build_model", return_value=model), \
             patch.object(proof, "audit_control", side_effect=fail), \
             patch.object(bench, "_payload", side_effect=OSError("gzip unavailable")), \
             patch.object(bench, "_raw_fallback", side_effect=OSError("raw unavailable")):
            target = Path(temp) / "output"
            report = bench.run(target)
            index = json.loads((target / "index.json").read_bytes())
        self.assertIs(report["unserialized_policy"], policy)
        self.assertNotIn("unserialized_policy", index)
        self.assertIs(index["unserialized_policy_retention"]["durably_saved"], False)
        self.assertEqual(index["status"], "error")
        self.assertIn("first control failure", index["errors"][0]["message"])

    def test_final_receipt_write_cannot_mask_original_model_error(self):
        state = {"revision": "a" * 40, "status": "", "source_lf_sha256": {}}
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(bench, "_snapshot", return_value=state), \
             patch.object(bench.previous, "_write_index", side_effect=(None, OSError("receipt unavailable"))), \
             patch.object(proof, "build_model", side_effect=RuntimeError("first model error")):
            report = bench.run(Path(temp) / "output")
        self.assertEqual(report["status"], "error")
        self.assertIn("first model error", report["errors"][0]["message"])
        self.assertEqual(report["errors"][-1]["phase"], "final-index-write")
        self.assertIsNone(report["index_sha256"])

    def test_guard_receipt_is_merged_after_suppressed_primary_and_source_error_stays_secondary(self):
        state = {"revision": "a" * 40, "status": "", "source_lf_sha256": {}}
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "result"
            with patch.object(bench, "_snapshot", side_effect=(state, RuntimeError("source drift"))), \
                 patch.object(proof, "build_model", side_effect=RuntimeError("primary model failure")):
                report = bench.run(output)
            self.assertEqual(report["status"], "error")
            self.assertEqual(len(report["authority_calls"]), 41)
            self.assertTrue(all(value == 0 for value in report["authority_calls"].values()))
            self.assertIn("primary model failure", report["errors"][0]["message"])
            self.assertEqual(report["errors"][1]["phase"], "source-finalization")
            self.assertIn("source drift", report["errors"][1]["message"])
            self.assertTrue((output / "index.json").is_file())

    def test_cli_passes_actual_execution_state_shape_and_returns_error_status(self):
        returned = {"status": "error", "errors": [{"message": "synthetic"}],
                    "boundaries": {}, "index_sha256": "a" * 64}
        with patch.object(bench, "run", return_value=returned) as run, patch("builtins.print"):
            self.assertEqual(bench.main(["--output", "unused-output"]), 1)
        self.assertEqual(run.call_args.kwargs["execution_state"],
                         {"mode": "ordinary-process", "system_required": False})


if __name__ == "__main__":
    unittest.main()
