"""Orchestration and artifact-preservation controls for the Q storage study."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pokerlab.cards import DECK, cards, expand_range
from scripts import benchmark_suit_quotient_solver as study


SOURCE = {"commit": "frozen-test-commit", "status": "", "sha256": {"solver.py": "pinned"}}


def _snapshot(case):
    return {"contract": "exact-product-selected-v1", "ranges": [
        [{"hand": "".join(hand), "weight_hex": float(weight).hex()}
         for hand, weight in expand_range(case[key]).items()]
        for key in ("sb_range", "bb_range")
    ]}


def _selected(case):
    boards = []
    for runout in case["runouts"]:
        parsed = cards(runout, 5)
        boards.append(tuple(sorted(parsed[:3], key=DECK.index)) + parsed[3:])
    boards.sort(key=lambda board: tuple(DECK.index(card) for card in board))
    return [list(board) for board in boards]


def _payload(case_name="symmetric-t10", storage="expanded"):
    case = study.case_for(case_name)
    quotient = storage == "suit-quotient"
    payoff_fixture = case_name in ("payoff-varied-t10", "payoff-varied-t100")
    expanded_rows = 2 if payoff_fixture else 1
    expanded_slots = expanded_rows
    q_rows = 1 if payoff_fixture else expanded_rows
    q_slots = q_rows
    group_size = 2 if payoff_fixture else 1
    supported_members = 2 if payoff_fixture else 1
    legacy = {"information_sets": expanded_rows, "action_slots": expanded_slots,
        "requested_layout_loop_entries": 10, "numeric_buffers": 4,
        "numeric_buffer_bytes": 32 * expanded_slots, "retained_dense_lookup_slots": 0,
        "semantic_row_lookup_entries": expanded_rows, "equivariant_additional_admission": {
            "modeled_work_upper": 10, "whole_request_additional_work_upper": 20,
            "additional_retained_entries_upper": 5}}
    if quotient:
        packed = {"version": "suit-quotient-packed-cfr-layout-v1", "information_sets": q_rows,
            "action_slots": q_slots, "numeric_buffers": 4, "numeric_buffer_bytes": 32 * q_slots,
            "semantic_row_lookup_entries": q_rows, "retained_expanded_row_lookup_entries": 0,
            "quotient_information_rows": q_rows,
            "quotient_action_slots": q_slots, "expanded_information_rows": expanded_rows,
            "expanded_action_slots": expanded_slots, "expanded_policy_shadow_rows": expanded_rows,
            "expanded_policy_shadow_action_slots": expanded_slots,
            "member_checks": 2 * study.ITERATIONS[case_name] * supported_members,
            "expanded_layout_equivalent": legacy,
            "equivariant_additional_admission": legacy["equivariant_additional_admission"]}
        storage_receipt = {"group_size": group_size, "quotient_information_rows": q_rows,
            "quotient_action_slots": q_slots, "expanded_information_rows": expanded_rows,
            "expanded_action_slots": expanded_slots, "retained_expanded_row_lookup_entries": 0,
            "supported_member_count": supported_members, "iterations": study.ITERATIONS[case_name],
            "four_quotient_numeric_buffers_projected_payload_bytes": 32 * q_slots}
    else:
        packed = {**legacy, "version": "selected-shared-topology-packed-v1"}
        storage_receipt = None
    metrics = {key: 0.0 for key in study.METRICS}
    row_hands = list(expand_range(case["sb_range"]))[:expanded_rows]
    strategy = [{"player": "sb", "hand": "".join(hand), "history": [],
        "actions": [{"name": "check", "amount": 0.0, "raise_to": 0.0,
            "history_key": "check", "probability": 1.0}]} for hand in row_hands]
    payload = {"chance_contract": "exact-product-selected-v1",
        "conversion_contract": "exact-product-vectors-binary64-v1",
        "training_reduction": "suit-equivariant-sorted-chance-binary64-v1",
        "strategy_storage": "suit-quotient-packed-v1" if quotient else "expanded",
        "pair_diagnostics": "compact-exact-product-inputs-v1",
        "chance_input_snapshot": _snapshot(case), "info_sets": expanded_rows,
        "selected_runouts": _selected(case),
        "worlds": (18 if case_name == "blocker-18" else
            8 if payoff_fixture else 1),
        "strategy": strategy,
        **metrics}
    census = {"stored_complete_worlds": 0, "stored_prefix_pair_edges": 0,
        "whole_request_admission": {"kernel": {"whole_request_upper_work": 100},
            "adapter": {"whole_request_work_upper": 100}, "combined_modeled_work_upper": 100,
            "whole_request_limit": 500_000_000,
            "retained_storage": {"kernel_peak_upper": 100, "adapter_peak_upper": 100,
                "whole_request_peak_upper": 1000, "entry_limit": 25_000_000,
                "equivariant_extra_entries_upper": 100},
            "equivariant_additional_admission": {"modeled_work_upper": 10,
                "whole_request_additional_work_upper": 20,
                "additional_retained_entries_upper": 5}},
        "equivariant_additional_admission": {"modeled_work_upper": 10,
            "whole_request_additional_work_upper": 20, "additional_retained_entries_upper": 5},
        "kernel": {"work_units_cumulative": 50, "storage_entries_peak": 50,
            "rank_calls": 1, "integer_arithmetic": {"peak_operand_bits": 10,
                "peak_forecast_bits": 10, "peak_integer_payload_bits": 100,
                "integer_payload_bit_limit": 1 << 30, "modeled_limb_work_upper": 20}},
        "float_adapter": {"modeled_work_entries": 50, "retained_mapping_entries": 10},
        "bit_forecast": {"dyadic_integer": {"maximum_bits_upper": 20,
            "logical_integer_payload_bits_upper": 1000, "whole_request_limb_work_upper": 40}},
        "training": {"calls": 1, "layout": packed},
        "packed_layout_actual": packed,
        "packed_layout_upper": {"upper_requested_layout_loop_entries": 20,
            "upper_action_slots": 10}}
    if storage_receipt is not None:
        census["suit_quotient_storage"] = storage_receipt
    payload["operator_census"] = census
    return payload


def _raw(case_name="symmetric-t10", storage="expanded", sample=0, traced=False):
    calls = {"equivariant_trainer_calls": int(storage == "expanded"),
        "quotient_trainer_calls": int(storage == "suit-quotient"),
        "quotient_plan_calls": int(storage == "suit-quotient"), "rank_calls": 1,
        "pair_query_calls": 0, "native_calls": 0, "world_producer_calls": 0, "popen_calls": 0}
    return {"case": case_name, "storage": storage, "sample": sample,
        "iterations": study.ITERATIONS[case_name], "traced": traced, "status": "complete",
        "error": None, "seconds": 1.25, "python_peak_allocation_bytes": 2048 if traced else None,
        "process_lifetime_peak_working_set_bytes": 4096, "actual_calls": calls,
        "payload": _payload(case_name, storage), "runtime": study._runtime()}


def _process(value, returncode=0, stdout=None, stderr=b""):
    raw = json.dumps(value).encode() if stdout is None else stdout
    return SimpleNamespace(returncode=returncode, stdout=raw, stderr=stderr)


def _verification(gap=False):
    return {"payload_metrics_within_tolerance": not gap,
        "payload_metric_tolerance": study.REPLAY_TOLERANCE,
        "payload_metric_absolute_differences": {key: (0.5 if gap and key == "value_sb" else 0.0)
            for key in study.METRICS},
        "numeric_replay": {"checked_information_sets": 1},
        "exact_compact_certificate": {"exact_certificate": {
            "metrics": {"nash_conv": "0/1"}, "threshold": "1/1000", "threshold_met": False}}}


class SuitQuotientBenchmarkTests(unittest.TestCase):
    def test_fixed_23_call_schedule_has_all_required_pairs_and_alternation(self):
        self.assertEqual(len(study.SCHEDULE), 23)
        self.assertEqual(study.SCHEDULE[:6], (
            ("symmetric-t10", "expanded", 0, False),
            ("symmetric-t10", "suit-quotient", 0, False),
            ("symmetric-t10", "suit-quotient", 1, False),
            ("symmetric-t10", "expanded", 1, False),
            ("symmetric-t10", "expanded", 2, False),
            ("symmetric-t10", "suit-quotient", 2, False)))
        self.assertEqual(sum(entry[0] == "symmetric-t10" and entry[3] for entry in study.SCHEDULE), 2)
        self.assertEqual({entry[0] for entry in study.SCHEDULE}, set(study.ITERATIONS))
        for case in ("blocker-18", "asymmetric-weighted", "mixed-stabilizer",
                     "symmetric-t100", "payoff-varied-t10", "payoff-varied-t100",
                     "original-22-t10"):
            self.assertEqual(sum(entry[0] == case for entry in study.SCHEDULE), 2)
        self.assertEqual(study.SCHEDULE[-1], ("original-22-qreject", "suit-quotient", 0, False))
        self.assertEqual(study.case_for("blocker-18")["sb_range"], "AcAh,AdAh,2cAh,2dAh")
        self.assertEqual(study.case_for("blocker-18")["bb_range"], "KcKh,KdKh,3cKh,3dKh")
        for case in ("payoff-varied-t10", "payoff-varied-t100"):
            self.assertEqual(study.case_for(case)["sb_range"], "AcQc,AdQd")
            self.assertEqual(study.case_for(case)["bb_range"], "KcJc,KdJd")
            self.assertEqual(study.case_for(case)["runouts"], ["2c3c7c9hTs", "2d3d7d9hTs"])

    def test_child_validation_accepts_both_modes_and_rejects_wrong_q_receipts(self):
        for storage in ("expanded", "suit-quotient"):
            raw = _raw(storage=storage)
            study._validate_child(raw, ("symmetric-t10", storage, 0, False))
        for case_name in ("payoff-varied-t10", "payoff-varied-t100"):
            raw = _raw(case_name, "suit-quotient")
            study._validate_child(raw, (case_name, "suit-quotient", 0, False))
            quotient = raw["payload"]["operator_census"]["suit_quotient_storage"]
            self.assertEqual(quotient["group_size"], 2)
            orbit = study._orbit_check(raw["payload"], require_equal=True)
            self.assertEqual(orbit["maximum_probability_difference"], 0.0)
            self.assertGreater(orbit["orbit_rows_checked"], 0)
        wrong = _raw(storage="suit-quotient")
        wrong["payload"]["operator_census"]["packed_layout_actual"]["numeric_buffer_bytes"] = 64
        with self.assertRaisesRegex(ValueError, "Q buffer receipt"):
            study._validate_child(wrong, ("symmetric-t10", "suit-quotient", 0, False))
        wrong = _raw()
        wrong["actual_calls"]["pair_query_calls"] = 1
        with self.assertRaisesRegex(ValueError, "forbidden pair/world/native"):
            study._validate_child(wrong, ("symmetric-t10", "expanded", 0, False))
        wrong = _raw()
        wrong["runtime"]["version"] = "different"
        with self.assertRaisesRegex(ValueError, "runtime mismatch"):
            study._validate_child(wrong, ("symmetric-t10", "expanded", 0, False))

    def test_real_payoff_varied_t10_children_validate_and_replay(self):
        payloads, verifications = {}, {}
        for storage in ("expanded", "suit-quotient"):
            raw = study.child("payoff-varied-t10", storage, 0, False)
            study._validate_child(raw, ("payoff-varied-t10", storage, 0, False))
            self.assertEqual(raw["status"], "complete")
            payloads[storage] = raw["payload"]
            verifications[storage] = study._protected_verification(
                study.case_for("payoff-varied-t10"), raw["payload"])
            self.assertTrue(verifications[storage]["payload_metrics_within_tolerance"])
        comparison = study._pair_comparison(payloads["expanded"],
            payloads["suit-quotient"], verifications["expanded"],
            verifications["suit-quotient"])
        self.assertTrue(comparison["policy_bitwise_identical"])
        self.assertTrue(comparison["metric_values_identical"])
        self.assertEqual(study._orbit_check(payloads["suit-quotient"],
            require_equal=True)["maximum_probability_difference"], 0.0)

    def test_blocker_case_world_count_is_pinned_to_18(self):
        raw = _raw("blocker-18", "expanded")
        study._validate_child(raw, ("blocker-18", "expanded", 0, False))
        raw["payload"]["worlds"] = 17
        with self.assertRaisesRegex(ValueError, "exactly 18"):
            study._validate_child(raw, ("blocker-18", "expanded", 0, False))

    def test_t1000_resource_rejection_happens_before_plan_or_training(self):
        raw = _raw("original-22-qreject", "suit-quotient")
        raw.update(status="pretraining-rejected", payload=None,
            error={"type": "ValueError", "message": "Suit row plan work admission exceeded"},
            actual_calls={key: 0 for key in raw["actual_calls"]})
        study._validate_child(raw, ("original-22-qreject", "suit-quotient", 0, False))
        raw["actual_calls"]["quotient_plan_calls"] = 1
        with self.assertRaisesRegex(ValueError, "resource rejection"):
            study._validate_child(raw, ("original-22-qreject", "suit-quotient", 0, False))

    def test_pair_comparison_requires_snapshot_policy_metrics_and_certificate_identity(self):
        left, right = _payload(storage="expanded"), _payload(storage="suit-quotient")
        comparison = study._pair_comparison(left, right, _verification(), _verification())
        self.assertTrue(comparison["policy_bitwise_identical"])
        self.assertEqual(comparison["four_buffer_payload_bytes_saved"], 0)
        self.assertTrue(comparison["identity_group_storage_overhead"]["applies"])
        right["chance_input_snapshot"]["ranges"][0][0]["weight_hex"] = "0x1.0000000000000p-1"
        with self.assertRaisesRegex(ValueError, "different chance input snapshots"):
            study._pair_comparison(left, right, _verification(), _verification())

    def test_same_storage_repeat_identity_does_not_require_q_receipt_on_both_sides(self):
        left = _payload(storage="expanded")
        right = _payload(storage="expanded")
        result = study._policy_metric_certificate_identity(left, right, _verification(), _verification())
        self.assertTrue(result["policy_bitwise_identical"])
        left = _payload(storage="suit-quotient")
        right = _payload(storage="suit-quotient")
        self.assertTrue(study._policy_metric_certificate_identity(
            left, right, _verification(), _verification())["exact_threshold_flags_identical"])

    def test_strict_decoder_rejects_duplicate_keys_and_nonfinite_json(self):
        for raw in (b'{"case":1,"case":2}', b'{"case":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                study._decode(raw)

    def test_first_child_failure_keeps_raw_bytes_and_does_not_retry(self):
        with TemporaryDirectory() as temp:
            output = Path(temp) / "study"
            calls = []

            def fail_first(command, **kwargs):
                calls.append(command[command.index("--child") + 1])
                return _process(None, stdout=b"{malformed first child", stderr=b"first stderr")

            with patch.object(study, "_identity", return_value=SOURCE), \
                 patch.object(study.subprocess, "run", side_effect=fail_first):
                result = study.run(output)
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(len(calls), 1)
            label = study._label(study.SCHEDULE[0])
            self.assertEqual((output / (label + ".json")).read_bytes(), b"{malformed first child")
            self.assertEqual((output / (label + ".stderr.txt")).read_bytes(), b"first stderr")
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["schedule_attempted"], 0)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            for name, digest in manifest["sha256"].items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)

    def test_metric_replay_gap_is_saved_before_first_failure_stops_schedule(self):
        with TemporaryDirectory() as temp:
            output = Path(temp) / "study"
            child_calls = []

            def fake_child(command, **kwargs):
                child_calls.append(1)
                return _process(_raw("symmetric-t10", "expanded", 0, False))

            with patch.object(study, "_identity", return_value=SOURCE), \
                 patch.object(study.subprocess, "run", side_effect=fake_child), \
                 patch.object(study, "_protected_verification", return_value=_verification(gap=True)):
                result = study.run(output)
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(len(child_calls), 1)
            label = study._label(study.SCHEDULE[0])
            saved = json.loads((output / (label + "-verification.json")).read_text(encoding="utf-8"))
            self.assertFalse(saved["payload_metrics_within_tolerance"])
            failure = json.loads((output / (label + "-failure.json")).read_text(encoding="utf-8"))
            self.assertIn("metric gap exceeds", failure["message"])
            self.assertTrue((output / "manifest.json").exists())

    def test_late_comparison_failure_keeps_all_children_verifications_and_manifest(self):
        with TemporaryDirectory() as temp:
            output = Path(temp) / "study"
            child_calls = []

            def fake_child(command, **kwargs):
                case_name = command[command.index("--child") + 1]
                storage = command[command.index("--storage") + 1]
                sample = command[command.index("--sample") + 1]
                traced = "--traced" in command
                sample = sample if sample == "traced" else int(sample)
                child_calls.append((case_name, storage, sample, traced))
                if case_name == "original-22-qreject":
                    value = _raw(case_name, storage, sample, traced)
                    value.update(status="pretraining-rejected", payload=None,
                        error={"type": "ValueError", "message": "whole-request admission exceeded"},
                        actual_calls={key: 0 for key in value["actual_calls"]})
                    return _process(value)
                return _process(_raw(case_name, storage, sample, traced))

            def late_failure(*_args):
                raise RuntimeError("late paired comparison failure")

            with patch.object(study, "_identity", return_value=SOURCE), \
                 patch.object(study.subprocess, "run", side_effect=fake_child), \
                 patch.object(study, "_protected_verification", return_value=_verification()), \
                 patch.object(study, "_pair_comparison", side_effect=late_failure):
                result = study.run(output)
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(len(child_calls), 23)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["schedule_attempted"], 23)
            self.assertEqual(report["failure"]["stage"], "post-run-comparison")
            self.assertTrue((output / "post-run-failure.json").exists())
            self.assertTrue((output / "source-after.json").exists())
            self.assertTrue((output / "manifest.json").exists())

    def test_complete_fake_study_reports_every_pair_repeat_and_timing_shape(self):
        with TemporaryDirectory() as temp:
            output = Path(temp) / "study"
            child_calls = []

            def fake_child(command, **kwargs):
                case_name = command[command.index("--child") + 1]
                storage = command[command.index("--storage") + 1]
                sample = command[command.index("--sample") + 1]
                traced = "--traced" in command
                sample = sample if sample == "traced" else int(sample)
                child_calls.append((case_name, storage, sample, traced))
                if case_name == "original-22-qreject":
                    value = _raw(case_name, storage, sample, traced)
                    value.update(status="pretraining-rejected", payload=None,
                        error={"type": "ValueError", "message": "whole-request admission exceeded"},
                        actual_calls={key: 0 for key in value["actual_calls"]})
                    return _process(value)
                return _process(_raw(case_name, storage, sample, traced))

            with patch.object(study, "_identity", return_value=SOURCE), \
                 patch.object(study.subprocess, "run", side_effect=fake_child), \
                 patch.object(study, "_protected_verification", return_value=_verification()):
                result = study.run(output)
            self.assertEqual(result["outcome"], "complete")
            self.assertEqual(len(child_calls), 23)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["schedule_attempted"], 23)
            self.assertEqual(len(report["paired_comparisons"]), 14)
            medians = report["paired_comparisons"]["symmetric-t10-three-pair-medians"]
            self.assertEqual(len(medians["paired_q_minus_expanded_seconds"]), 3)
            self.assertIn("separate-traced-pair", report["paired_comparisons"])
            orbit_checks = report["quotient_orbit_checks"]
            self.assertEqual(len(orbit_checks), 2)
            self.assertEqual(sum("payoff-varied-t10" in key or "payoff-varied-t100" in key
                for key in orbit_checks), 2)
            self.assertTrue(all(entry["maximum_probability_difference"] == 0.0 and
                entry["orbit_rows_checked"] > 0 for entry in orbit_checks.values()))
            self.assertTrue(report["pretraining_rejection_retained"])
            self.assertTrue((output / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
