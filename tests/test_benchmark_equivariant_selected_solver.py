"""Protocol and fixed-schedule controls for the equivariant solver study."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import benchmark_equivariant_selected_solver as study


SOURCE = {"commit": "pinned-study-test-source", "status": "", "sha256": {"source.py": "fixed"}}


def _payload(case_name, reduction):
    case = study.case_for(case_name)
    from pokerlab.cards import expand_range
    snapshot = [[{"hand": "".join(hand), "weight_hex": float(weight).hex()}
                 for hand, weight in expand_range(text).items()]
                for text in (case["sb_range"], case["bb_range"])]
    return {"chance_contract": "exact-product-selected-v1",
        "conversion_contract": "exact-product-vectors-binary64-v1",
        "training_reduction": ("suit-equivariant-sorted-chance-binary64-v1"
            if reduction == "suit-equivariant" else "default"),
        "pair_diagnostics": "compact-exact-product-inputs-v1",
        "chance_input_snapshot": {"ranges": snapshot}, "info_sets": 1,
        "value_sb": 0.0, "value_bb": 0.0, "sb_best_response_value": 0.0,
        "bb_best_response_value": 0.0, "sb_gain": 0.0, "bb_gain": 0.0,
        "nash_conv": 0.0, "exploitability": 0.0,
        "operator_census": {"stored_complete_worlds": 0, "stored_prefix_pair_edges": 0,
            "whole_request_admission": {"kernel": {"whole_request_upper_work": 1000},
                "adapter": {"whole_request_work_upper": 1000},
                "combined_modeled_work_upper": 2500, "whole_request_limit": 500_000_000,
                "retained_storage": {"kernel_peak_upper": 50, "adapter_peak_upper": 20,
                    "whole_request_peak_upper": 100, "entry_limit": 25_000_000,
                    "equivariant_extra_entries_upper": 500},
                "equivariant_additional_admission": {"modeled_work_upper": 100,
                    "whole_request_additional_work_upper": 150,
                    "additional_retained_entries_upper": 200}},
            "kernel": {"work_units_cumulative": 500, "storage_entries_peak": 25,
                "rank_calls": 3, "integer_arithmetic": {"peak_operand_bits": 10,
                    "peak_forecast_bits": 10, "peak_integer_payload_bits": 100,
                    "integer_payload_bit_limit": 1 << 30, "modeled_limb_work_upper": 50}},
            "float_adapter": {"modeled_work_entries": 200, "retained_mapping_entries": 10},
            "bit_forecast": {"dyadic_integer": {"maximum_bits_upper": 100,
                "logical_integer_payload_bits_upper": 1000, "whole_request_limb_work_upper": 100}},
            "training": {"calls": 1},
            "packed_layout_actual": {"requested_layout_loop_entries": 10, "action_slots": 1,
                "numeric_buffers": 4, "equivariant_additional_admission": {
                    "modeled_work_upper": 100, "additional_retained_entries_upper": 200}},
            "packed_layout_upper": {"upper_requested_layout_loop_entries": 20, "upper_action_slots": 2}},
        "strategy": [{"player": "sb", "hand": snapshot[0][0]["hand"],
            "history": [], "actions": [{"name": "check", "amount": 0.0,
                "raise_to": 0.0, "history_key": "check", "probability": 1.0}]}]}


def _raw(case_name="symmetric", reduction="default", sample=0, traced=False):
    calls = {"default_trainer_calls": int(reduction == "default"),
        "equivariant_trainer_calls": int(reduction == "suit-equivariant"),
        "rank_calls": 3, "pair_query_calls": 0, "native_calls": 0,
        "world_producer_calls": 0, "popen_calls": 0}
    return {"case": case_name, "reduction": reduction, "sample": sample,
        "iterations": study.ITERATIONS[case_name], "traced": traced,
        "status": "complete", "error": None, "seconds": 1.25,
        "python_peak_allocation_bytes": 1024 if traced else None,
        "process_lifetime_peak_working_set_bytes": 4096,
        "actual_calls": calls, "payload": _payload(case_name, reduction), "runtime": study._runtime()}


def _process(value, returncode=0, stdout=None, stderr=b""):
    raw = json.dumps(value).encode() if stdout is None else stdout
    return SimpleNamespace(returncode=returncode, stdout=raw, stderr=stderr)


class EquivariantSelectedBenchmarkTests(unittest.TestCase):
    def test_schedule_has_fifteen_calls_and_required_pairs(self):
        self.assertEqual(len(study.SCHEDULE), 15)
        symmetric = [row for row in study.SCHEDULE if row[0] == "symmetric" and not row[3]]
        self.assertEqual(len(symmetric), 6)
        self.assertEqual(sum(row[0] == "symmetric" and row[3] for row in study.SCHEDULE), 2)
        self.assertEqual(study.SCHEDULE[:6], (
            ("symmetric", "default", 0, False), ("symmetric", "suit-equivariant", 0, False),
            ("symmetric", "suit-equivariant", 1, False), ("symmetric", "default", 1, False),
            ("symmetric", "default", 2, False), ("symmetric", "suit-equivariant", 2, False)))
        for case in ("asymmetric", "original-22", "one-world"):
            self.assertEqual(sum(row[0] == case for row in study.SCHEDULE), 2)
        rejection = [row for row in study.SCHEDULE if row[0] == "original-22-reject"]
        self.assertEqual(rejection, [("original-22-reject", "suit-equivariant", 0, False)])
        self.assertEqual(study.ITERATIONS["one-world"], 1000)
        self.assertEqual(study.ITERATIONS["original-22-reject"], 1000)

    def test_child_payload_and_call_contract_validation(self):
        for reduction in ("default", "suit-equivariant"):
            entry = ("symmetric", reduction, 0, False)
            study._validate_child(_raw(*entry[:3], traced=False), entry)
        wrong = _raw()
        wrong["actual_calls"]["pair_query_calls"] = 1
        with self.assertRaisesRegex(ValueError, "forbidden pair/world/native"):
            study._validate_child(wrong, ("symmetric", "default", 0, False))
        wrong = _raw(reduction="suit-equivariant")
        wrong["payload"]["training_reduction"] = "default"
        with self.assertRaisesRegex(ValueError, "payload contract/reduction"):
            study._validate_child(wrong, ("symmetric", "suit-equivariant", 0, False))
        wrong = _raw()
        wrong["payload"]["nash_conv"] = float("nan")
        with self.assertRaisesRegex(ValueError, "metrics are missing or nonfinite"):
            study._validate_child(wrong, ("symmetric", "default", 0, False))
        wrong = _raw()
        wrong["actual_calls"]["default_trainer_calls"] = 0
        with self.assertRaisesRegex(ValueError, "trainer/rank call count"):
            study._validate_child(wrong, ("symmetric", "default", 0, False))
        wrong = _raw()
        wrong["payload"]["operator_census"]["kernel"]["work_units_cumulative"] = 1001
        with self.assertRaisesRegex(ValueError, "actual kernel/adapter"):
            study._validate_child(wrong, ("symmetric", "default", 0, False))

    def test_equivariant_orbit_check_requires_bitwise_policy_match(self):
        from tests.test_equivariant_selected_solver import symmetric_case
        case = symmetric_case()
        from tests.test_selected_operator_solver import request
        from pokerlab.exact_selected_solver import solve_four_street_exact_selected
        payload = solve_four_street_exact_selected(request(case), pair_diagnostics="compact",
            exact_arithmetic="dyadic", training_reduction="suit-equivariant")
        result = study._orbit_check(payload)
        self.assertEqual(result["maximum_probability_difference"], 0.0)
        self.assertEqual(result["orbit_rows_checked"], payload["info_sets"])
        verification = study._protected_verification(case, payload)
        self.assertEqual(verification["exact_compact_certificate"]["contract"],
                         "compact-exact-product-certificate-v1")
        self.assertEqual(verification["numeric_replay"]["checked_information_sets"], payload["info_sets"])
        self.assertEqual(set(verification["payload_metric_absolute_differences"]), set(study.METRICS))
        self.assertTrue(verification["payload_metrics_within_tolerance"])
        self.assertTrue(all(value == 0 for value in verification["forbidden_production_calls"].values()))

    def test_child_decoder_rejects_duplicate_keys_and_nonfinite_tokens(self):
        for raw in (b'{"case":1,"case":2}', b'{"case":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                study._decode(raw)

    def test_first_child_failure_is_retained_without_retry(self):
        with TemporaryDirectory() as temp:
            output = Path(temp) / "study"
            calls = []
            def fake_run(command, **kwargs):
                calls.append(command[command.index("--child") + 1])
                return _process(None, stdout=b"{first child output", stderr=b"first child error")
            with (patch.object(study, "_identity", return_value=SOURCE),
                  patch.object(study.subprocess, "run", side_effect=fake_run)):
                result = study.run(output)
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(len(calls), 1)
            self.assertEqual((output / "symmetric-default-0.json").read_bytes(), b"{first child output")
            self.assertEqual((output / "symmetric-default-0.stderr.txt").read_bytes(), b"first child error")
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["schedule_attempted"], 0)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            for name, digest in manifest["sha256"].items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)

    def test_late_comparison_failure_is_retained_with_manifest(self):
        with TemporaryDirectory() as temp:
            output = Path(temp) / "study"
            def fake_run(command, **kwargs):
                case_name = command[command.index("--child") + 1]
                reduction = command[command.index("--reduction") + 1]
                sample = command[command.index("--sample") + 1]
                traced = "--traced" in command
                sample = sample if sample == "traced" else int(sample)
                if case_name == "original-22-reject":
                    value = _raw(case_name, reduction, sample, traced)
                    value.update(status="pretraining-rejected", payload=None,
                        error={"type": "ValueError", "message": "whole-request admission exceeded"},
                        actual_calls={key: 0 for key in value["actual_calls"]})
                    return _process(value)
                return _process(_raw(case_name, reduction, sample, traced))
            verification = {"numeric_replay": {}, "payload_metrics_within_tolerance": True,
                "payload_metric_absolute_differences": {key: 0.0 for key in study.METRICS},
                "exact_compact_certificate":
                {"contract": "compact-exact-product-certificate-v1",
                 "exact_certificate": {"threshold_met": False, "metrics": {}}}}
            with (patch.object(study, "_identity", return_value=SOURCE),
                  patch.object(study.subprocess, "run", side_effect=fake_run),
                  patch.object(study, "_protected_verification", return_value=verification),
                  patch.object(study, "_orbit_check", return_value={"maximum_probability_difference": 0.0}),
                  patch.object(study, "_paired_diff", side_effect=RuntimeError("late comparison control"))):
                result = study.run(output)
            self.assertEqual(result["outcome"], "failed")
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["schedule_attempted"], 15)
            self.assertEqual(report["failure"]["stage"], "post-run-comparison-or-source-audit")
            self.assertTrue((output / "post-run-failure.json").exists())
            self.assertTrue((output / "manifest.json").exists())

    def test_metric_tolerance_failure_retains_full_verification_before_stopping(self):
        with TemporaryDirectory() as temp:
            output = Path(temp) / "study"
            calls = []
            def fake_run(command, **kwargs):
                calls.append(command[command.index("--child") + 1])
                return _process(_raw())
            verification = {"numeric_replay": {"checked_information_sets": 1},
                "payload_metrics_within_tolerance": False,
                "payload_metric_tolerance": study.REPLAY_TOLERANCE,
                "payload_metric_absolute_differences": {key: (0.5 if key == "value_sb" else 0.0)
                                                        for key in study.METRICS},
                "exact_compact_certificate": {"contract": "compact-exact-product-certificate-v1",
                    "exact_certificate": {"threshold_met": False, "metrics": {}}}}
            with (patch.object(study, "_identity", return_value=SOURCE),
                  patch.object(study.subprocess, "run", side_effect=fake_run),
                  patch.object(study, "_protected_verification", return_value=verification)):
                result = study.run(output)
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(calls, ["symmetric"])
            artifact = json.loads((output / "symmetric-default-0-verification.json").read_text(encoding="utf-8"))
            self.assertEqual(artifact["payload_metric_absolute_differences"]["value_sb"], 0.5)
            failure = json.loads((output / "symmetric-default-0-failure.json").read_text(encoding="utf-8"))
            self.assertIn("metric gap exceeds", failure["message"])
            self.assertTrue((output / "report.json").exists())
            self.assertTrue((output / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
