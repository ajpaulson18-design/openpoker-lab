"""Synthetic protocol controls for the fixed rank-free storage-frontier runner."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pokerlab.cards import expand_range
from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
from pokerlab.preflop_solver import _requested_runouts
from scripts import benchmark_exact_storage_frontier as study


SOURCE = {"commit": "fixed-storage-test-source", "status": "", "sha256": {"solver.py": "pinned-source"}}


def _census(spec, status=True):
    request = spec["request"]
    hand_counts = [len(x.split(",")) for x in (request.sb_range, request.bb_range)]
    boards = len(request.runouts)
    rows = 12
    slots = 20
    full = spec["axis"] == "suit_symmetry_control"
    perms = ["cdhs", "dchs"] if spec["id"] == "club-diamond-symmetric" else ["cdhs"]
    result = {"contract": "exact-selected-storage-census-v1", "chance_contract": "exact-product-selected-v1",
        "hand_counts": hand_counts, "selected_boards": boards, "reachable_boards": boards,
        "support_pair_board_occurrences": 18, "unique_vertices": 17, "unique_edges": 16,
        "vertex_prefix_contexts": 14, "context_edges": 13, "logical_visits": 17,
        "maximum_depth": 8, "information_rows": rows, "action_slots": slots,
        "dense_slots": 15, "dense_holes": 3, "history_token_entries": 30,
        "history_token_bytes": 180, "per_street_player": [],
        "four_packed_numeric_buffers_payload_bytes": 4 * slots * 8,
        "serialized_policy_rows": rows, "serialized_action_rows": slots,
        "complete_solve_admission": {"kernel": {"configured_limit": 500_000_000},
            "packed_layout": {"upper_action_slots": slots},
            "retained_storage": {"entry_limit": 25_000_000,
                "phase_upper_bounds": {"information_and_menu_peak": 300},
                "whole_request_peak_upper": 300}},
        "bit_forecast": {},
        "rank_free_kernel_receipt": {"hands": hand_counts, "rank_calls": 0, "queries": 18},
        "additional_census_admission": {"retained_entries_upper": 400,
            "modeled_work_upper": 500, "history_bytes_upper": 200,
            "context_upper": 100, "orbit_work_upper": 200, "actual_orbit_work": 100,
            "witness_entries_upper": 200,
            "limits": {"max_additional_entries": 2_000_000}},
        "suit_symmetry": {"requested": True, "permutations": perms,
            "conservative_stabilizer_size": len(perms), "supported_row_orbits": 8,
            "potential_row_reduction": 4 if len(perms) > 1 else 0},
        "training_calls": 0, "pair_query_calls": 0, "native_calls": 0, "quality_gate": None}
    def side(text):
        return [{"hand": "".join(hand), "weight_hex": float(weight).hex()}
            for hand, weight in expand_range(text).items()]
    result["structural_witness"] = {"contract": "exact-selected-structural-witness-v1", "root_id": 0,
        "initial_history": [], "vertices": [{"kind": "terminal", "terminal_kind": "showdown",
            "winner": None, "contributions_hex": [float(1).hex(), float(1).hex()]} for _ in range(17)],
        "ranges": [side(request.sb_range), side(request.bb_range)],
        "selected_runouts": [[runout[i:i+2] for i in range(0, 10, 2)] for runout in request.runouts],
        "scope": "Synthetic compact witness"}
    result["structural_witness"]["selected_runouts"] = [
        [*board[0], board[1], board[2]] for board in _requested_runouts(request.runouts)]
    return result


def _raw(spec, *, rejected=False):
    request = spec["request"]
    census = None if rejected else _census(spec)
    result = {"case_id": spec["id"], "status": "resource-rejected" if rejected else "accepted",
        "phase": "exact-selected-request-admission" if rejected else "rank-free-census-complete",
        "error_type": "ValueError" if rejected else None,
        "error": "Exact selected whole-request modeled work admission exceeded before allocation." if rejected else None,
        "resource_rejection": rejected,
        "actual_calls": {key: 0 for key in ("training_calls", "rank_calls", "pair_query_calls",
            "terminal_query_calls", "marginal_query_calls", "native_calls", "world_producer_calls", "popen_calls")},
        "census": census, "case": {"id": spec["id"], "axis": spec["axis"],
            "parameters": spec["parameters"], "request": study._case_input(request)},
        "runtime": study._runtime_identity(), "exact_arithmetic": study.ARITHMETIC,
        "rank_cache_boards": study.RANK_CACHE_BOARDS, "suit_orbits": study.SUIT_ORBITS,
        "include_witness": True,
        "independent_certificate_shape_screen": None if rejected else study._certificate_shape_screen(census),
        "training_requested": False, "rank_requested": False, "pair_queries_requested": False,
        "scope": "Rank-free synthetic runner fixture"}
    return result


def _process(value, returncode=0, stdout=None, stderr=b""):
    raw = json.dumps(value).encode("utf-8") if stdout is None else stdout
    return SimpleNamespace(returncode=returncode, stdout=raw, stderr=stderr)


class ExactStorageFrontierBenchmarkTests(unittest.TestCase):
    def test_fixed_fixture_axes_and_symmetry_pair_are_pinned(self):
        rows = study.fixtures()
        self.assertEqual(len(rows), 17)
        range_rows = [row for row in rows if row["axis"] == "private_range_scale"]
        board_rows = [row for row in rows if row["axis"] == "selected_board_scale"]
        menu_rows = [row for row in rows if row["axis"] == "betting_history_scale"]
        self.assertEqual([row["parameters"]["hands_per_seat"] for row in range_rows], [1, 2, 4, 8, 16])
        self.assertEqual([row["parameters"]["boards"] for row in range_rows], [6] * 5)
        self.assertEqual([row["parameters"]["boards"] for row in board_rows], [1, 6, 12, 24, 48])
        self.assertEqual([row["parameters"]["postflop_max_raises"] for row in menu_rows], [0, 1, 2])
        self.assertEqual(len([row for row in rows if row["axis"] == "original_anchor"]), 1)
        self.assertEqual(len([row for row in rows if row["axis"] == "heldout_reference"]), 1)
        symmetric, broken = [row for row in rows if row["axis"] == "suit_symmetry_control"]
        self.assertEqual(symmetric["parameters"]["selected_boards"], broken["parameters"]["selected_boards"])
        self.assertNotEqual(symmetric["request"].sb_range, broken["request"].sb_range)

    def test_child_instruments_and_forbids_all_production_work(self):
        spec = next(row for row in study.fixtures() if row["id"] == "original-22-world-anchor")
        with patch.object(study, "census_exact_selected_storage", return_value=_census(spec)):
            raw = study.child(spec["id"])
        study._validate_child(raw, spec)
        self.assertTrue(all(value == 0 for value in raw["actual_calls"].values()))

    def test_structural_witness_is_bound_to_input_and_entry_admission(self):
        spec = next(row for row in study.fixtures() if row["id"] == "original-22-world-anchor")
        raw = _raw(spec)
        raw["census"]["structural_witness"]["selected_runouts"][0][0] = "As"
        with self.assertRaisesRegex(ValueError, "frozen parsed request"):
            study._validate_child(raw, spec)
        raw = _raw(spec)
        raw["census"]["additional_census_admission"]["witness_entries_upper"] = 2_000_001
        with self.assertRaisesRegex(ValueError, "admitted slot bound"):
            study._validate_child(raw, spec)

    def test_query_spies_reject_terminal_or_marginal_entry(self):
        spec = next(row for row in study.fixtures() if row["id"] == "original-22-world-anchor")
        def sneaky(request, **kwargs):
            ExactSelectedRunoutKernel.joint_marginals_exact(None)
        with patch.object(study, "census_exact_selected_storage", side_effect=sneaky):
            raw = study.child(spec["id"])
        self.assertEqual(raw["status"], "forbidden-call-detected")
        self.assertEqual(raw["actual_calls"]["marginal_query_calls"], 1)

    def test_real_rank_free_smoke_original_and_both_symmetry_controls(self):
        selected = {row["id"]: row for row in study.fixtures()}
        for case_id in ("original-22-world-anchor", "club-diamond-symmetric", "club-diamond-weight-broken"):
            with self.subTest(case=case_id):
                spec = selected[case_id]
                # Exercise the exact JSON wire shape used by the isolated child.
                raw = study._decode(json.dumps(study.child(case_id)).encode("utf-8"))
                study._validate_child(raw, spec)
                self.assertTrue(all(value == 0 for value in raw["actual_calls"].values()))
                self.assertEqual(raw["census"]["rank_free_kernel_receipt"]["rank_calls"], 0)
        anchor = study.child("original-22-world-anchor")["census"]
        self.assertEqual((anchor["unique_vertices"], anchor["vertex_prefix_contexts"],
                          anchor["context_edges"], anchor["logical_visits"],
                          anchor["information_rows"], anchor["action_slots"]),
                         (99, 259, 321, 1462, 1200, 2402))

    def test_resource_rejection_retains_message_phase_and_unknown_counts(self):
        spec = next(row for row in study.fixtures() if row["id"] == "range-scale-16")
        rejected = _raw(spec, rejected=True)
        study._validate_child(rejected, spec)
        summary = study._summary(rejected)
        self.assertEqual(summary["error_type"], "ValueError")
        self.assertEqual(summary["phase"], "exact-selected-request-admission")
        self.assertIn("work admission", summary["error"])
        for field in ("information_rows", "action_slots", "history_token_entries", "unique_vertices",
                      "logical_visits", "additional_entries_upper", "supported_row_orbits"):
            self.assertIsNone(summary[field], field)
        wrong = dict(rejected, error="invalid config")
        with self.assertRaisesRegex(ValueError, "resource/admission boundary"):
            study._validate_child(wrong, spec)
        wrong_phase = dict(rejected, phase="census-preparation")
        with self.assertRaisesRegex(ValueError, "phase does not match"):
            study._validate_child(wrong_phase, spec)

    def test_accepted_record_cannot_hide_error_or_rejection(self):
        spec = next(row for row in study.fixtures() if row["id"] == "original-22-world-anchor")
        for forged in (
            {"error_type": "ValueError", "error": "escape from request validation"},
            {"resource_rejection": True},
            {"phase": "census-preparation"},
        ):
            raw = _raw(spec)
            raw.update(forged)
            with self.subTest(forged=forged), self.assertRaisesRegex(ValueError, "accepted child carries"):
                study._validate_child(raw, spec)

    def test_unrelated_value_error_is_first_failure_with_no_retry(self):
        self.assertFalse(study._expected_resource_rejection(ValueError("escape from unrelated validation")))
        self.assertFalse(study._expected_resource_rejection(ValueError("capricious config value")))
        with TemporaryDirectory() as temp:
            output = Path(temp) / "frontier"
            specs = study.fixtures()
            calls = []
            def fake_run(command, **kwargs):
                calls.append(command[command.index("--child") + 1])
                spec = next(row for row in specs if row["id"] == calls[-1])
                raw = _raw(spec)
                raw.update(status="failed", phase="census-preparation", error_type="ValueError",
                    error="escape from unrelated validation", resource_rejection=False)
                return _process(raw)
            with (patch.object(study, "_identity", return_value=SOURCE),
                  patch.object(study.subprocess, "run", side_effect=fake_run)):
                result = study.run(output)
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(calls, ["range-scale-1"])
            retained = json.loads((output / "range-scale-1.json").read_text(encoding="utf-8"))
            self.assertEqual(retained["error"], "escape from unrelated validation")
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["failure"]["case_id"], "range-scale-1")

    def test_symmetry_shape_screen_is_explicitly_not_a_certificate(self):
        from scripts import four_street_validation as physical
        spec = next(row for row in study.fixtures() if row["id"] == "original-22-world-anchor")
        screen = study._certificate_shape_screen(_census(spec))
        self.assertEqual(screen["status"], "screen-only")
        self.assertEqual(screen["validator_caps_source"], "scripts/four_street_validation.py")
        self.assertEqual(screen["gates"]["hands_per_player"]["limit"], physical.MAX_HANDS_PER_PLAYER)
        self.assertIn("does not establish", screen["scope"])

    def _run_fake(self, output, *, reject_one=False, fail_first=False, identities=None):
        specs = study.fixtures()
        def fake_run(command, **kwargs):
            case_id = command[command.index("--child") + 1]
            spec = next(row for row in specs if row["id"] == case_id)
            if fail_first:
                return _process(None, returncode=0, stdout=b"{broken", stderr=b"first child stderr")
            return _process(_raw(spec, rejected=reject_one and case_id == "range-scale-16"))
        identity_mock = patch.object(study, "_identity", return_value=SOURCE) if identities is None else patch.object(study, "_identity", side_effect=identities)
        with identity_mock, patch.object(study.subprocess, "run", side_effect=fake_run) as calls:
            result = study.run(output)
        return result, calls.call_count

    def test_batch_keeps_expected_rejection_and_empty_safe_manifest(self):
        with TemporaryDirectory() as temp:
            output = Path(temp) / "frontier"
            result, count = self._run_fake(output, reject_one=True)
            self.assertEqual(result["outcome"], "complete")
            self.assertEqual(count, 17)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["resource_rejections"], 1)
            self.assertEqual(report["training_calls"], 0)
            self.assertEqual(report["rank_calls"], 0)
            rejected = next(row for row in report["cases"] if row["case_id"] == "range-scale-16")
            self.assertIsNone(rejected["information_rows"])
            self.assertEqual(len(report["axes"]["private_range_scale"]["observations"]), 5)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            for name, digest in manifest["sha256"].items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)

    def test_first_raw_child_failure_is_retained_without_retry(self):
        with TemporaryDirectory() as temp:
            output = Path(temp) / "frontier"
            result, count = self._run_fake(output, fail_first=True)
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(count, 1)
            self.assertEqual((output / "range-scale-1.json").read_bytes(), b"{broken")
            self.assertEqual((output / "range-scale-1.stderr.txt").read_bytes(), b"first child stderr")
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["cases"], [])
            self.assertEqual(report["attempted_cases"], 1)
            self.assertEqual(report["axes"]["private_range_scale"]["case_count_attempted"], 1)
            self.assertTrue((output / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
