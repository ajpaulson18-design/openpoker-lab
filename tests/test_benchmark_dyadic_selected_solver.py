"""Protocol/state-machine tests; these never launch the fixed 14-call study."""
from copy import deepcopy
import hashlib
from itertools import combinations
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import benchmark_dyadic_selected_solver as study

SOURCE = {"commit": "fixed-test-source", "status": "", "sha256": {"solver.py": "source-hash"}}


def _payload(name, iterations, mode):
    full = name == study.FULL_RANGE
    worlds = 1_070_190 if full else (1 if name == "one-world" else 22)
    training = 0 if full else 1
    row = [] if full else ([{"synthetic_test_row": i} for i in range(1200)] if name == "original"
                           else [{"hand": "AdAs", "probability": 1.0}])
    rank_calls = 2162 if full else 23
    kernel = {"rank_calls": rank_calls, "work_units_cumulative": 10,
              "arithmetic": "exact-dyadic-integer-buckets-v1" if mode == "dyadic" else "exact-fraction-v1"}
    if mode == "dyadic":
        kernel["integer_arithmetic"] = {"peak_operand_bits": 128, "peak_forecast_bits": 128,
            "peak_integer_payload_bits": 1000, "modeled_limb_work_upper": 2000}
    census = {"stored_complete_worlds": 0, "stored_prefix_pair_edges": 0, "kernel": kernel,
        "training": {"calls": training},
        "float_adapter": {"modeled_work_entries": 100},
        "adapter_work_admission": {"whole_request_work_upper": 1000, "configured_work_limit": 500000000},
        "whole_request_admission": {"kernel": {"whole_request_upper_work": 1000, "configured_limit": 500000000},
            "combined_modeled_work_upper": 2000, "whole_request_limit": 500000000,
            "retained_storage": {"whole_request_peak_upper": 1000, "entry_limit": 25000000}},
        "exact_pair_output": {"candidate_pairs_scanned": 0, "board_scan_work_upper": 0,
            "output_entry_upper": 0, "quadratic_diagnostic_stage": False}}
    if mode == "dyadic":
        census["bit_forecast"] = {"dyadic_integer": {"maximum_bits_upper": 256,
            "logical_integer_payload_bits_upper": 2000, "whole_request_limb_work_upper": 3000,
            "logical_integer_payload_bit_limit": 1 << 30}}
    if full:
        deck = tuple(rank + suit for rank in "23456789TJQKA" for suit in "cdhs")
        hands = ["".join(sorted(hand)) for hand in combinations(deck, 2)]
        ranges = [[{"hand": hand, "weight_hex": float(1).hex()} for hand in hands] for _ in range(2)]
    elif name == "one-world":
        ranges = [[{"hand": "AdAs", "weight_hex": float(1).hex()}],
                  [{"hand": "KdKs", "weight_hex": float(1).hex()}]]
    else:
        ranges = [[{"hand": "AdAs", "weight_hex": float(.5).hex()}, {"hand": "QdQs", "weight_hex": float(.25).hex()}],
                  [{"hand": "KdKs", "weight_hex": float(.75).hex()}, {"hand": "JdJh", "weight_hex": float(.25).hex()}]]
    return {"chance_contract": "exact-product-selected-v1",
        "conversion_contract": "exact-product-vectors-binary64-v1",
        "execution_backend": "exact-product-selected-direct-packed-python", "pair_diagnostics": study.FORMAT,
        "strategy": row, "info_sets": len(row), "worlds": worlds,
        "public_states": 1 if full else 17, "decisions": 0 if full else 4,
        "pair_runout_preflight_checks": 0,
        "chance_input_snapshot": {"contract": "exact-product-selected-v1", "ranges": ranges},
        "operator_census": census, **{key: 0.0 for key in study.METRICS}}


def _raw(name="original", iterations=10, mode="fraction", traced=False, **changes):
    rejected = name == "original" and iterations == 1000 and mode == "dyadic"
    full = name == study.FULL_RANGE
    raw = {"case": name, "iterations": iterations, "mode": mode, "pair_diagnostics": "compact",
        "output_format": study.FORMAT, "traced": traced, "rank_cache_boards": study.RANK_CACHE_BOARDS,
        "runtime": study._runtime_identity(),
        "status": "pretraining-rejected" if rejected else "complete",
        "error": {"type": "ValueError", "message": "whole-request work admission exceeded before training"} if rejected else None,
        "seconds": 1.25, "python_allocation_peak_bytes": 2048 if traced else None,
        "python_process_peak_bytes": 4096,
        "training_calls": 0 if full or rejected else 1, "pair_query_calls": 0,
        "rank_calls": 0 if rejected else (2162 if full else 23), "native_calls": 0,
        "payload": None if rejected else _payload(name, iterations, mode)}
    raw.update(changes)
    return raw


def _process(value):
    return SimpleNamespace(returncode=0, stdout=json.dumps(value).encode("utf-8"), stderr=b"")


def _certificate(case, payload):
    digest = "a" * 64
    exact = {"metrics": {key: "0/1" for key in study.EXACT_METRICS},
        "threshold": "1/1000", "threshold_met": False,
        "source_identity": "four-street-independent-exact-v3",
        "input_policy_canonical_sha256": study._canonical(payload), "normalized_policy_sha256": digest}
    return exact, {"exact_certificate": exact, "training_calls": 0, "native_calls": 0,
        "production_pair_rows": 0, "physical_model_builds": 3,
        "compact_input_canonical_sha256": study._canonical(payload),
        "verification_expansion_canonical_sha256": exact["input_policy_canonical_sha256"]}


class DyadicSelectedSolverBenchmarkTests(unittest.TestCase):
    def test_schedule_has_exactly_fourteen_alternating_compact_calls(self):
        rows = study.schedule()
        self.assertEqual(len(rows), 14)
        self.assertEqual(rows[:6], (
            ("original", 10, "fraction", 0, False), ("original", 10, "dyadic", 0, False),
            ("original", 10, "dyadic", 1, False), ("original", 10, "fraction", 1, False),
            ("original", 10, "fraction", 2, False), ("original", 10, "dyadic", 2, False)))
        self.assertEqual(rows[6:8], (("original", 10, "fraction", "traced", True),
                                     ("original", 10, "dyadic", "traced", True)))
        self.assertEqual(rows[-2:], (("original", 1000, "dyadic", "resource-control", False),
                                     (study.FULL_RANGE, 10, "dyadic", 0, False)))
        self.assertEqual({row[2] for row in rows[:-2]}, set(study.MODES))

    def test_child_gates_mode_arguments_compact_format_and_pair_forbid(self):
        calls = {}
        def solve(request, **kwargs):
            calls.update(kwargs)
            from pokerlab.exact_selected_solver import train_packed
            from pokerlab.exact_selected_kernel import rank_hand
            train_packed()
            for _ in range(23):
                rank_hand(None, (), ())
            return _payload("one-world", 10, kwargs["exact_arithmetic"])
        with patch.object(study, "case_for", return_value={
                "sb_range": "AsAd", "bb_range": "KsKd", "runouts": ["2c3c4d7h8h"],
                "config": {"small_blind": .5, "big_blind": 1, "starting_stack": [2, 2], "raise_sizes": [.5], "max_raises": 1, "include_all_in": False},
                "flop_config": {"bet_sizes": [.5], "raise_sizes": [], "max_raises": 0, "include_all_in": False}}), \
             patch.object(study, "solve_four_street_exact_selected", side_effect=solve), \
             patch("pokerlab.exact_selected_solver.train_packed", return_value=None), \
             patch("pokerlab.exact_selected_kernel.rank_hand", return_value=0), \
             patch.object(study, "_rss", return_value=4096):
            raw = study.child("one-world", 10, "dyadic")
        self.assertEqual(calls, {"rank_cache_boards": study.RANK_CACHE_BOARDS,
                                 "pair_diagnostics": "compact", "exact_arithmetic": "dyadic"})
        self.assertEqual(raw["pair_query_calls"], 0)
        study._validate_child(raw, "one-world", 10, "dyadic")

    def test_rejection_is_only_original_t1000_dyadic_before_rank_or_train(self):
        raw = _raw(iterations=1000, mode="dyadic")
        study._validate_child(raw, "original", 1000, "dyadic")
        raw["rank_calls"] = 1
        with self.assertRaisesRegex(ValueError, "reject before work"):
            study._validate_child(raw, "original", 1000, "dyadic")
        raw = _raw(iterations=1000, mode="fraction")
        raw.update(status="pretraining-rejected", payload=None,
                   error={"type": "ValueError", "message": "whole-request work admission exceeded"},
                   training_calls=0, rank_calls=0)
        with self.assertRaisesRegex(ValueError, "completed exact-product"):
            study._validate_child(raw, "original", 1000, "fraction")

    def test_dyadic_counters_must_fit_pretraining_forecast(self):
        raw = _raw(mode="dyadic")
        raw["payload"]["operator_census"]["kernel"]["integer_arithmetic"]["peak_operand_bits"] = 257
        with self.assertRaisesRegex(ValueError, "forecast"):
            study._validate_child(raw, "original", 10, "dyadic")
        raw = _raw(mode="fraction")
        raw["payload"]["operator_census"]["exact_pair_output"]["candidate_pairs_scanned"] = 1
        with self.assertRaisesRegex(ValueError, "private pairs"):
            study._validate_child(raw, "original", 10, "fraction")

    def test_negative_controls_cover_contract_snapshot_caps_and_full_range_witness(self):
        mutations = []
        raw = _raw(mode="dyadic")
        raw["payload"]["operator_census"]["kernel"].pop("arithmetic")
        mutations.append((raw, "arithmetic mode"))
        raw = _raw()
        raw["payload"]["private_pair_probabilities"] = []
        mutations.append((raw, "pair-table fields"))
        raw = _raw()
        raw["payload"]["chance_input_snapshot"]["contract"] = "legacy"
        mutations.append((raw, "snapshot"))
        raw = _raw()
        raw["payload"]["info_sets"] = 1199
        raw["payload"]["strategy"].pop()
        mutations.append((raw, "fixture identity"))
        raw = _raw()
        raw["payload"]["operator_census"]["float_adapter"]["modeled_work_entries"] = 1001
        mutations.append((raw, "adapter work"))
        raw = _raw()
        raw["payload"]["operator_census"]["whole_request_admission"]["kernel"]["configured_limit"] = 500_000_001
        mutations.append((raw, "work/storage"))
        raw = _raw(mode="dyadic")
        raw["payload"]["operator_census"]["bit_forecast"]["dyadic_integer"]["logical_integer_payload_bit_limit"] = 1 << 29
        mutations.append((raw, "payload cap"))
        raw = _raw(study.FULL_RANGE, mode="dyadic")
        raw["payload"]["nash_conv"] = .25
        mutations.append((raw, "symmetry"))
        raw = _raw(study.FULL_RANGE, mode="dyadic")
        raw["payload"]["chance_input_snapshot"]["ranges"][0][0]["weight_hex"] = float(.5).hex()
        mutations.append((raw, "uniform 1326-hand witness"))
        raw = _raw()
        raw["runtime"]["python_version"] = "3.12.0-test-mismatch"
        mutations.append((raw, "runtime differs"))
        for data, message in mutations:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                study._validate_child(data, data["case"], data["iterations"], data["mode"], data["traced"])

    def _run_fake(self, out, fail_first=False):
        def fake_child(command, **kwargs):
            name = command[command.index("--child") + 1]
            iterations = int(command[command.index("--iterations") + 1])
            mode = command[command.index("--mode") + 1]
            traced = "--traced" in command
            if fail_first and kwargs.get("_unused"):
                return SimpleNamespace(returncode=1, stdout=b"partial", stderr=b"failure")
            return _process(_raw(name, iterations, mode, traced))
        identities = patch.object(study, "_identity", return_value=deepcopy(SOURCE))
        with identities, patch.object(study.subprocess, "run", side_effect=fake_child) as process, \
             patch.object(study, "_certificate", side_effect=_certificate):
            result = study.run(out)
        return result, process.call_count

    def test_fixed_runner_compares_all_pairs_and_builds_empty_safe_manifest(self):
        with TemporaryDirectory() as temp:
            out = Path(temp) / "study"
            result, calls = self._run_fake(out)
            self.assertEqual(calls, 14, json.loads((out / "report.json").read_text())["failure"])
            self.assertEqual(result["outcome"], "complete", json.loads((out / "report.json").read_text())["failure"])
            report = json.loads((out / "report.json").read_text(encoding="utf-8"))
            self.assertTrue(all(report["checks"].values()))
            self.assertEqual(report["complete_child_calls"], 14)
            self.assertEqual(report["pair_query_calls"], 0)
            self.assertEqual(report["native_calls"], 0)
            self.assertEqual(len(report["certificates"]), 6)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            for name, digest in manifest["sha256"].items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest)

    def test_raw_child_streams_are_written_before_bad_json_failure_without_retry(self):
        with TemporaryDirectory() as temp:
            out = Path(temp) / "study"
            response = SimpleNamespace(returncode=0, stdout=b"{bad", stderr=b"first stderr")
            with patch.object(study, "_identity", return_value=deepcopy(SOURCE)), \
                 patch.object(study.subprocess, "run", return_value=response) as process:
                result = study.run(out)
            self.assertEqual(process.call_count, 1)
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual((out / "original-T10-fraction-0.json").read_bytes(), response.stdout)
            self.assertEqual((out / "original-T10-fraction-0.stderr.txt").read_bytes(), response.stderr)
            report = json.loads((out / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["samples"], [])
            self.assertIsNone(report["medians_original_T10_seconds"]["fraction"])
            self.assertTrue((out / "manifest.json").exists())

    def test_tiny_common_scale_recovery_control_matches_exactly(self):
        """Small integration control for global normalization under raw product underflow."""
        from pokerlab.exact_selected_solver import solve_four_street_exact_selected
        from tests.test_four_street_certificate import _case
        from tests.test_selected_operator_solver import request
        base = _case(sb="AsAd:1,QsQd:1", bb="KsKd:1,JhJd:1", stacks=[2, 2])
        tiny = dict(base, sb_range="AsAd:1e-200,QsQd:1e-200", bb_range="KsKd:1e-200,JhJd:1e-200")
        ordinary_result = solve_four_street_exact_selected(request(base), pair_diagnostics="compact", exact_arithmetic="dyadic")
        tiny_result = solve_four_street_exact_selected(request(tiny), pair_diagnostics="compact", exact_arithmetic="dyadic")
        self.assertEqual(tiny_result["strategy"], ordinary_result["strategy"])
        for key in study.METRICS:
            self.assertEqual(tiny_result[key], ordinary_result[key], key)
        self.assertEqual(tiny_result["worlds"], ordinary_result["worlds"])
        self.assertEqual(tiny_result["info_sets"], ordinary_result["info_sets"])
        exact_tiny, _ = study._certificate(tiny, tiny_result)
        exact_base, _ = study._certificate(base, ordinary_result)
        self.assertEqual(exact_tiny["metrics"], exact_base["metrics"])
        self.assertEqual(exact_tiny["normalized_policy_sha256"], exact_base["normalized_policy_sha256"])


if __name__ == "__main__":
    unittest.main()
