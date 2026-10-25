"""No-training lifecycle controls for the one-shot U5 integration runner."""
import copy
from contextlib import ExitStack
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import benchmark_four_street_integration as runner
from scripts import verify_four_street_integration_publication as verifier
from pokerlab.solver_contracts import FourStreetSolveResult
from tests.test_four_street_certificate import _check_call, _payload as _certificate_payload
from tests.four_street_publication_fixture import committed_source_fixture


EXPECTED = "a" * 40


def _support():
    pairs = (("AsAd", "KsKd"), ("AsAd", "JhJd"),
             ("QsQd", "KsKd"), ("QsQd", "JhJd"))
    rows = []
    for index in range(22):
        rows.append({"hands": list(pairs[index % len(pairs)]),
                     "board": ["2c", "3c", f"{index:02d}d", "7h", "8h"],
                     "sign": (index % 3) - 1, "weight": "1/22"})
    signs = {"sb_win": 7, "tie": 7, "bb_win": 8}
    return rows, signs


def _admissions():
    worlds, signs = _support()
    forecast = {"admitted": True, "work": 98_298, "work_limit": 100_000,
                "tree_nodes": 1414, "tree_decisions": 628, "tree_depth": 14,
                "worlds": 22, "information_rows": 1200, "action_slots": 2402,
                "preparation_receipts": {"independent_model_build": {
                    "worlds": 22, "public_states": 1414, "decisions": 628,
                    "information_rows": 1200}}}
    pairs = [{"sb_hand": sb, "bb_hand": bb, "fraction": fraction}
             for (sb, bb), fraction in zip(
                 (("AsAd", "KsKd"), ("AsAd", "JhJd"),
                  ("QsQd", "KsKd"), ("QsQd", "JhJd")),
                 ("36/68", "12/68", "15/68", "5/68"))]
    exact = {"schema": "four-street-exact-admission-v1", "forecast": forecast,
             "world_sign_counts": signs, "pair_probabilities": pairs,
             "world_support": worlds, "admitted": True, "attempted_training": False}
    production_worlds = [dict(row, weight=float(__import__("fractions").Fraction(row["weight"])))
                         for row in worlds]
    production = {"schema": "four-street-production-admission-v1", "admitted": True,
                  "attempted_training": False,
                  "counts": {"candidate_private_pairs": 4,
                             "compatible_private_pairs": 4,
                             "worlds": 22, "public_states": 1414,
                             "information_sets": 1200,
                             "information_set_action_slots": 2402,
                             "pair_runout_preflight_checks": 24,
                             "decisions": 628, "world_decision_work": 123456,
                             "positive_pot_training_view_states": 3000,
                             "positive_pot_training_anchor": 0.5},
                  "physical_pair_probabilities": [
                      {"sb_hand": sb, "bb_hand": bb,
                       "probability": float(__import__("fractions").Fraction(fraction))}
                      for sb, bb, fraction in
                      (("AsAd", "KsKd", "36/68"), ("AsAd", "JhJd", "12/68"),
                       ("QsQd", "KsKd", "15/68"), ("QsQd", "JhJd", "5/68"))],
                  "world_sign_counts": signs, "world_support": production_worlds,
                  "vector_budget": {"prefix_edges": 22, "dense_prefix_slots": 44,
                                    "total_loop_entries_upper_bound": 1000000},
                  "caps": {"candidate_pair_iterations": 3000000,
                           "world_iterations": 3000000,
                           "world_decision_work": 30000000,
                           "pair_runout_preflight_checks": 30000000,
                           "public_states": 250000, "decision_nodes": 10000,
                           "vector_prefix_edges": 250000}}
    return production, exact


def _payload(request):
    payload = {
        "solver_version": "preflop-strategy-v1", "strategy_schema": "preflop-strategy-v1",
        "runout_mode": "conditioned-ordered-selected-runouts", "algorithm": "cfrplus",
        "execution_backend": "public-batched-python", "iterations": 1000,
        "training_passes": 3000, "training_passes_per_iteration": 3,
        "training_schedule": "alternating-player-0-then-player-1; linear-own-reach-average-after-each-sweep",
        "diagnostics_backend": "public-batched-python", "worlds": 22,
        "value_sb": 0.0, "value_bb": 0.0,
        "sb_best_response_value": 0.0, "bb_best_response_value": 0.0,
        "nash_conv": 0.0, "exploitability": 0.0,
        "resource_model": "public-vector", "candidate_private_pairs": 4,
        "compatible_private_pairs": 4, "pair_runout_preflight_checks": 24,
        "public_states": 1414, "decisions": 628, "info_sets": 1200,
        "world_decision_work": 123456, "public_batched_training_view_states": 3000,
        "public_batched_training_pot_anchor": 0.5,
        "public_batched_prefix_edge_limit": 250000,
        "public_diagnostics_prefix_edge_limit": 250000,
        "public_diagnostics_view_states": 3000,
        "public_diagnostics_view_pot_anchor": 0.5,
        "public_diagnostics_view_source": "training-view-reused",
        "vector_work_budget": {"prefix_edges": 22, "dense_prefix_slots": 44,
                               "total_loop_entries_upper_bound": 1000000},
        "limits": {"candidate_pair_iterations": 3000000,
                   "world_iterations": 3000000,
                   "pair_runout_preflight_checks": 30000000,
                   "public_states": 250000, "decision_nodes": 10000,
                   "world_decision_work": None,
                   "reference_world_decision_work": 30000000},
        "strategy": [{"synthetic": True}],
    }
    payload["world_decision_work_enforced"] = False
    payload["limits"]["world_decision_work"] = None
    payload["limits"]["reference_world_decision_work"] = 30_000_000
    return payload


def _envelope(request, payload=None):
    return {"schema_version": "four-street-solve-v1", "request": request.to_dict(),
            "identities": {"seats": "sb-button-0-bb-1", "scope": "all-streets",
                           "numerical_model": "binary64-local-nine-decimal-whole-hand-v1",
                           "chance_model": "conditioned-ordered-selected-runouts",
                           "range_model": "physical-combo-product-blocker-conditioned-v1",
                           "reach_model": "global-joint-law-separated-sequence-reach-v1"},
            "source_identity": {"entry_point": "pokerlab.preflop_solver.solve_preflop",
                                "solver_version": "preflop-strategy-v1",
                                "source_revision": None,
                                "source_verification": "not-recorded"},
            "payload": _payload(request) if payload is None else payload}


class _Returned:
    def __init__(self, raw):
        self.raw = raw

    def to_json(self):
        return self.raw


def _services(tmp_path, *, exact_admission=None, production_admission=None,
              envelope=None, drift_at=None, solve_hook=None, numeric_hook=None,
              exact_hook=None):
    production, exact = _admissions()
    production = production if production_admission is None else production_admission
    exact = exact if exact_admission is None else exact_admission
    request = runner._literal_request()
    raw_value = _envelope(request) if envelope is None else envelope
    raw = json.dumps(raw_value, sort_keys=True, separators=(",", ":"))
    capture_count = [0]
    snapshot = {"head": EXPECTED, "status": "clean",
                "files": {"scripts/benchmark_four_street_integration.py": {
                    "bytes": 100, "raw_sha256": "1" * 64,
                    "normalized_lf_sha256": "2" * 64, "git_blob": "3" * 40}},
                "inventory_policy": "synthetic test inventory"}
    calls = {"solve": 0, "numeric": 0, "exact": 0}

    def capture(_expected):
        capture_count[0] += 1
        value = copy.deepcopy(snapshot)
        if drift_at == capture_count[0]:
            value["head"] = "b" * 40
        return value

    def fixture():
        return {"case": runner._literal_case(), "quality_run": runner._fixed_selectors()}

    def solve(got_request):
        calls["solve"] += 1
        if solve_hook:
            solve_hook(tmp_path, raw)
        return _Returned(raw)

    def numeric_replay(payload, case):
        calls["numeric"] += 1
        if numeric_hook:
            return numeric_hook(tmp_path, payload, case)
        return {"worlds": 22, "value_sb": 0.0, "value_bb": 0.0,
                "sb_best_response_value": 0.0, "bb_best_response_value": 0.0,
                "nash_conv": 0.0, "exploitability": 0.0,
                "numeric_counts": {"worlds": 22}}

    def exact_audit(case, payload):
        calls["exact"] += 1
        if exact_hook:
            return exact_hook(case, payload)
        return {"threshold_met": True,
                "metrics": {"value_sb": "1/34", "nash_conv": "1/1000"},
                "normalized_policy_rows": [{"row": 1}],
                "normalization_ledger": [{"row": 1}],
                "normalized_policy_sha256": "4" * 64,
                "actual_work": 98_000,
                "actual_work_by_kind": {"example": 98_000}}

    services = {"capture": capture, "fixture": fixture,
                "exact_prepare": lambda _case: copy.deepcopy(exact),
                "production_prepare": lambda _request: copy.deepcopy(production),
                "solve": solve, "numeric_replay": numeric_replay,
                "exact_audit": exact_audit}
    return services, calls, raw, capture_count


class FourStreetIntegrationRunnerTests(unittest.TestCase):
    def _root(self, temp):
        root = Path(temp) / "attempt"
        return root

    def test_one_call_raw_receipt_precedes_numeric_and_complete_success_is_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            attempt = self._root(temp)
            services, calls, raw, captures = _services(attempt)

            def numeric_check(directory, payload, case):
                self.assertEqual((directory / "raw-envelope.json").read_bytes(), raw.encode("utf-8"))
                receipt = json.loads((directory / "raw-receipt.json").read_text())
                self.assertEqual(receipt["sha256"], runner._sha256(raw.encode("utf-8")))
                calls["numeric"] += 1
                return {"worlds": 22, "value_sb": 0.0, "value_bb": 0.0,
                        "sb_best_response_value": 0.0, "bb_best_response_value": 0.0,
                        "nash_conv": 0.0, "exploitability": 0.0,
                        "numeric_counts": {"worlds": 22}}

            services["numeric_replay"] = lambda payload, case: numeric_check(attempt, payload, case)
            result = runner.run_attempt(EXPECTED, attempt, _services=services)
            self.assertEqual(result["outcome"], "completed-met", result.get("first_failure"))
            self.assertEqual(result["production_calls_entered"], 1)
            self.assertEqual(calls, {"solve": 1, "numeric": 1, "exact": 1})
            self.assertGreaterEqual(captures[0], 8)
            self.assertEqual((attempt / "raw-envelope.json").read_bytes(), raw.encode("utf-8"))
            self.assertTrue(json.loads((attempt / "status.json").read_text())["quality_gate"])
            claim = json.loads((attempt / "claim.json").read_text())
            self.assertFalse(claim["retry_permitted"])
            self.assertEqual(claim["production_calls_allowed"], 1)
            report = json.loads((attempt / "report.json").read_text())
            self.assertEqual(report["training"]["training_passes_returned"], 3000)
            self.assertEqual(report["training"]["modelled_expected_training_passes"], 3000)

    def test_exact_miss_and_capacity_unknown_are_distinct(self):
        with tempfile.TemporaryDirectory() as temp:
            miss_path = Path(temp) / "miss"
            services, _, _, _ = _services(miss_path, exact_hook=lambda *_: {
                "threshold_met": False, "metrics": {"nash_conv": "1/500"}})
            miss = runner.run_attempt(EXPECTED, miss_path, _services=services)
            self.assertEqual(miss["outcome"], "completed-missed")
            self.assertFalse(miss["quality_gate"])

            unknown_path = Path(temp) / "unknown"
            services, calls, _, _ = _services(unknown_path, exact_hook=lambda *_: (
                (_ for _ in ()).throw(ValueError("exact certificate forecast exceeds its hard work limit: counters={}"))))
            unknown = runner.run_attempt(EXPECTED, unknown_path, _services=services)
            self.assertEqual(unknown["outcome"], "completed-unknown")
            self.assertIsNone(unknown["quality_gate"])
            self.assertEqual(calls, {"solve": 1, "numeric": 1, "exact": 1})
            self.assertTrue((unknown_path / "numeric-replay.json").exists())

    def test_numeric_mismatch_is_failure_after_saving_independent_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            attempt = Path(temp) / "numeric-mismatch"

            def mismatched(_directory, _payload, _case):
                return {"worlds": 22, "value_sb": 0.01, "value_bb": 0.0,
                        "sb_best_response_value": 0.0, "bb_best_response_value": 0.0,
                        "nash_conv": 0.0, "exploitability": 0.0,
                        "numeric_counts": {"worlds": 22}}

            services, calls, _, _ = _services(attempt, numeric_hook=mismatched)
            result = runner.run_attempt(EXPECTED, attempt, _services=services)
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(calls, {"solve": 1, "numeric": 1, "exact": 0})
            self.assertTrue((attempt / "numeric-replay.json").exists())
            numeric_record = json.loads((attempt / "numeric-replay.json").read_text())
            self.assertFalse(numeric_record["production_comparison"]["all_within_tolerance"])

    def test_numeric_mismatch_is_failure_after_saving_independent_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            attempt = Path(temp) / "numeric-mismatch"

            def mismatched(_directory, _payload, _case):
                return {"worlds": 22, "value_sb": 0.01, "value_bb": 0.0,
                        "sb_best_response_value": 0.0, "bb_best_response_value": 0.0,
                        "nash_conv": 0.0, "exploitability": 0.0,
                        "numeric_counts": {"worlds": 22}}

            services, calls, _, _ = _services(attempt, numeric_hook=mismatched)
            result = runner.run_attempt(EXPECTED, attempt, _services=services)
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(calls, {"solve": 1, "numeric": 1, "exact": 0})
            self.assertTrue((attempt / "numeric-replay.json").exists())
            numeric_record = json.loads((attempt / "numeric-replay.json").read_text())
            self.assertFalse(numeric_record["production_comparison"]["all_within_tolerance"])

    def test_preparation_rejection_has_no_claim_or_solve(self):
        with tempfile.TemporaryDirectory() as temp:
            attempt = self._root(temp)
            prod, _ = _admissions()
            prod["admitted"] = False
            services, calls, _, _ = _services(attempt, production_admission=prod)
            result = runner.run_attempt(EXPECTED, attempt, _services=services)
            self.assertEqual(result["outcome"], "preparation-failed")
            self.assertEqual(result["production_calls_entered"], 0)
            self.assertFalse((attempt / "claim.json").exists())
            self.assertEqual(calls, {"solve": 0, "numeric": 0, "exact": 0})

    def test_source_drift_existing_attempt_and_existing_claim_refuse_training(self):
        with tempfile.TemporaryDirectory() as temp:
            existing = Path(temp) / "existing"
            existing.mkdir()
            with self.assertRaisesRegex(FileExistsError, "cannot resume"):
                runner.run_attempt(EXPECTED, existing, _services={})

            drift = Path(temp) / "drift"
            services, calls, _, _ = _services(drift, drift_at=2)
            result = runner.run_attempt(EXPECTED, drift, _services=services)
            self.assertEqual(result["outcome"], "preparation-failed")
            self.assertEqual(calls["solve"], 0)
            self.assertFalse((drift / "claim.json").exists())
            drift_source = json.loads((drift / "source-after.json").read_text())
            self.assertNotEqual(drift_source["source_state"]["head"], EXPECTED)
            drift_source = json.loads((drift / "source-after.json").read_text())
            self.assertNotEqual(drift_source["source_state"]["head"], EXPECTED)

            raced_claim = Path(temp) / "claim-race"
            services, calls, _, _ = _services(raced_claim)
            exact_prepare = services["exact_prepare"]

            def insert_claim(_case):
                (raced_claim / "claim.json").write_bytes(b"preexisting claim")
                return exact_prepare(_case)

            services["exact_prepare"] = insert_claim
            refused = runner.run_attempt(EXPECTED, raced_claim, _services=services)
            self.assertEqual(refused["outcome"], "preparation-failed")
            self.assertEqual(calls["solve"], 0)
            self.assertEqual((raced_claim / "claim.json").read_bytes(), b"preexisting claim")

    def test_crash_like_solve_entered_attempt_cannot_resume_or_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            attempt = self._root(temp)

            def crash(_directory, _raw):
                raise RuntimeError("inert simulated crash after entering facade")

            services, calls, _, _ = _services(attempt, solve_hook=crash)
            result = runner.run_attempt(EXPECTED, attempt, _services=services)
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(calls["solve"], 1)
            self.assertEqual(json.loads((attempt / "status.json").read_text())[
                "production_calls_entered"], 1)
            with self.assertRaisesRegex(FileExistsError, "cannot resume"):
                runner.run_attempt(EXPECTED, attempt, _services=services)

    def test_raw_metadata_mismatch_and_bad_payload_fail_after_preserving_raw(self):
        with tempfile.TemporaryDirectory() as temp:
            attempt = Path(temp) / "bad-meta"
            bad = _envelope(runner._literal_request())
            bad["payload"]["training_passes"] = 2999
            services, calls, raw, _ = _services(attempt, envelope=bad)
            result = runner.run_attempt(EXPECTED, attempt, _services=services)
            self.assertEqual(result["outcome"], "failed")
            self.assertEqual(calls["solve"], 1)
            self.assertEqual((attempt / "raw-envelope.json").read_bytes(), raw.encode("utf-8"))
            self.assertEqual(calls["numeric"], 0)

    def test_malformed_json_and_output_path_guards(self):
        for raw, message in ((b'{"x":1,"x":2}', "duplicate"),
                             (b'{"x":NaN}', "nonfinite")):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, message):
                runner._strict_json(raw, max_bytes=100)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "absolute"):
                runner._safe_output_directory("relative-attempt")
            with self.assertRaisesRegex(ValueError, "external"):
                runner._safe_output_directory(str(runner.REPO_ROOT / "attempt"))
            with self.assertRaisesRegex(ValueError, "40-character"):
                runner.run_attempt("bad", Path(temp) / "x", _services={})

    def test_partial_exclusive_write_is_retained_and_existing_raw_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "partial.json"
            real_open = runner.os.open

            def fail_fsync(fd):
                raise OSError("inert fsync failure")

            with patch.object(runner.os, "fsync", fail_fsync):
                with self.assertRaisesRegex(OSError, "inert fsync"):
                    runner._write_exclusive_preserving(target, b"partial evidence")
            self.assertEqual(target.read_bytes(), b"partial evidence")
            with self.assertRaises(FileExistsError):
                runner._write_exclusive_preserving(target, b"replacement")
            self.assertEqual(target.read_bytes(), b"partial evidence")

    def test_partial_raw_write_and_raw_mutation_during_audit_are_retained_as_failures(self):
        with tempfile.TemporaryDirectory() as temp:
            partial_attempt = Path(temp) / "partial-raw"
            services, calls, _, _ = _services(partial_attempt)
            original_writer = runner._write_exclusive_preserving

            def partial_writer(path, data):
                path = Path(path)
                if path.name == "raw-envelope.json":
                    path.write_bytes(b"partial raw envelope")
                    raise OSError("inert raw write failure")
                return original_writer(path, data)

            with patch.object(runner, "_write_exclusive_preserving", partial_writer):
                failed_write = runner.run_attempt(EXPECTED, partial_attempt, _services=services)
            self.assertEqual(failed_write["outcome"], "failed")
            self.assertEqual(calls, {"solve": 1, "numeric": 0, "exact": 0})
            self.assertEqual((partial_attempt / "raw-envelope.json").read_bytes(),
                             b"partial raw envelope")

            mutated_attempt = Path(temp) / "mutated-during-audit"
            services, calls, _, _ = _services(mutated_attempt)

            def mutate_after_audit(_case, _payload):
                calls["exact"] += 1
                (mutated_attempt / "raw-envelope.json").write_bytes(b"changed during audit")
                return {"threshold_met": True, "metrics": {"nash_conv": "0"}}

            services["exact_audit"] = mutate_after_audit
            rejected = runner.run_attempt(EXPECTED, mutated_attempt, _services=services)
            self.assertEqual(rejected["outcome"], "failed")
            self.assertEqual(calls, {"solve": 1, "numeric": 1, "exact": 1})
            self.assertEqual((mutated_attempt / "raw-envelope.json").read_bytes(),
                             b"changed during audit")

    def test_fixed_manifest_and_envelope_guards_match_literal_request(self):
        fixture = json.loads((runner.REPO_ROOT / runner.BENCHMARK_RELATIVE).read_text())
        self.assertEqual(fixture["case"], runner._literal_case())
        self.assertEqual(fixture["quality_run"], runner._fixed_selectors())
        request = runner._literal_request()
        payload = _payload(request)
        runner._assert_envelope(_envelope(request, payload), request)
        payload["averaging_delay"] = 1
        with self.assertRaisesRegex(ValueError, "unsupported or nonliteral"):
            runner._assert_envelope(_envelope(request, payload), request)

    def test_real_fixed_case_production_preparation_is_no_training_and_matches_oracle_support(self):
        from pokerlab import preflop_solver as solver
        names = ("solve_preflop", "train_public_batched", "train_cfrplus",
                 "train_planned", "train_delayed_public_cfrplus",
                 "train_chance_sampled", "evaluate_public_profile")
        tripwire_calls = []

        def tripwire(*_args, **_kwargs):
            tripwire_calls.append(True)
            raise AssertionError("production preflight entered a solve/training function")

        with ExitStack() as stack:
            for name in names:
                stack.enter_context(patch.object(solver, name, side_effect=tripwire))
            stack.enter_context(patch.object(solver.cfr, "train", side_effect=tripwire))
            production = runner._production_admission(runner._literal_request())
            exact = runner._independent_admission(runner._literal_case())
        comparison = runner._compare_admission_support(production, exact)
        self.assertEqual(production["counts"]["worlds"], 22)
        self.assertEqual(production["counts"]["compatible_private_pairs"], 4)
        self.assertEqual(production["counts"]["public_states"], 1462)
        self.assertEqual(production["counts"]["decisions"], 628)
        self.assertEqual(production["counts"]["information_sets"], 1200)
        self.assertEqual(production["counts"]["information_set_action_slots"], 2402)
        self.assertLessEqual(production["vector_budget"]["total_loop_entries_upper_bound"],
                             500_000_000)
        self.assertEqual(comparison["worlds_compared"], 22)
        self.assertEqual(comparison["pairs_compared"], 4)
        self.assertTrue(comparison["support_matches"])
        self.assertEqual(tripwire_calls, [])


def _synthetic_fixed_policy_payload(case, production):
    """Use the independent model only to encode a deterministic test policy."""
    model = runner.numeric.build_model(case)
    payload = _certificate_payload(model, _check_call)
    counts = production["counts"]
    caps = production["caps"]
    for name in ("value_sb", "value_bb", "sb_best_response_value",
                 "bb_best_response_value", "nash_conv", "exploitability"):
        # Filled by the independent numeric replay below, never by training.
        payload[name] = 0.0
    payload.update({
        "algorithm": "cfrplus", "execution_backend": "public-batched-python",
        "iterations": 1000, "completed_iterations": 1000,
        "training_passes": 3000, "training_passes_per_iteration": 3,
        "training_schedule": "alternating-player-0-then-player-1; linear-own-reach-average-after-each-sweep",
        "diagnostics_backend": "public-batched-python", "postflop_scope": "all-streets",
        "resource_model": "public-vector",
        "candidate_private_pairs": counts["candidate_private_pairs"],
        "worlds": counts["worlds"],
        "compatible_private_pairs": counts["compatible_private_pairs"],
        "pair_runout_preflight_checks": counts["pair_runout_preflight_checks"],
        "public_states": counts["public_states"], "decisions": counts["decisions"],
        "info_sets": counts["information_sets"],
        "world_decision_work": counts["world_decision_work"],
        "public_batched_training_view_states": counts["positive_pot_training_view_states"],
        "public_batched_training_pot_anchor": counts["positive_pot_training_anchor"],
        "public_batched_prefix_edge_limit": caps["vector_prefix_edges"],
        "public_diagnostics_prefix_edge_limit": caps["vector_prefix_edges"],
        "public_diagnostics_view_states": counts["positive_pot_training_view_states"],
        "public_diagnostics_view_pot_anchor": counts["positive_pot_training_anchor"],
        "public_diagnostics_view_source": "training-view-reused",
        "vector_work_budget": production["vector_budget"],
        "limits": {
            "candidate_pair_iterations": caps["candidate_pair_iterations"],
            "world_iterations": caps["world_iterations"],
            "pair_runout_preflight_checks": caps["pair_runout_preflight_checks"],
            "public_states": caps["public_states"],
            "decision_nodes": caps["decision_nodes"],
            "world_decision_work": None,
            "reference_world_decision_work": caps["world_decision_work"],
        },
        "world_decision_work_enforced": False,
    })
    return model, payload


def _write_record(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


class FourStreetSavedAttemptTests(unittest.TestCase):
    """Cross-component saved-only controls with no production solve/training."""

    @classmethod
    def setUpClass(cls):
        cls._source_fixture = committed_source_fixture(runner, verifier)
        cls.checkout, cls.commit = cls._source_fixture.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._source_fixture.__exit__(None, None, None)

    def _install_solve_tripwires(self, stack, calls):
        from pokerlab import preflop_solver as solver

        def tripwire(*_args, **_kwargs):
            calls.append(True)
            raise AssertionError("synthetic publication control entered real solve/training")

        for name in ("solve_preflop", "train_public_batched", "train_cfrplus",
                     "train_planned", "train_delayed_public_cfrplus",
                     "train_chance_sampled", "evaluate_public_profile"):
            stack.enter_context(patch.object(solver, name, side_effect=tripwire))
        stack.enter_context(patch.object(solver.cfr, "train", side_effect=tripwire))
        stack.enter_context(patch.object(runner, "solve_four_street", side_effect=tripwire))

    def _make_attempt(self, temp, *, exact_audit_hook=None,
                      claim_write_failure=False, expected_outcome="completed-missed",
                      expected_solve_calls=1):
        attempt = Path(temp) / "saved-attempt"
        case, request = runner._literal_case(), runner._literal_request()
        tripwire_calls = []
        with ExitStack() as stack:
            self._install_solve_tripwires(stack, tripwire_calls)
            production = runner._production_admission(request)
        services = runner._run_services()
        calls = {"synthetic_policy_returned": 0}

        model, payload = None, None
        if not claim_write_failure:
            model, payload = _synthetic_fixed_policy_payload(case, production)
            numeric_metrics = runner.numeric.replay_policy(payload, case)
            for name in ("value_sb", "value_bb", "sb_best_response_value",
                         "bb_best_response_value", "nash_conv"):
                payload[name] = numeric_metrics[name]
            payload["exploitability"] = numeric_metrics["nash_conv"] / 2
            returned = FourStreetSolveResult._from_payload(request, payload)

            def synthetic_solve(got_request):
                self.assertEqual(got_request, request)
                calls["synthetic_policy_returned"] += 1
                return returned
        else:
            def synthetic_solve(_got_request):
                calls["synthetic_policy_returned"] += 1
                raise AssertionError("claim-write failure entered the synthetic solve")

        services["solve"] = synthetic_solve
        if exact_audit_hook is not None:
            services["exact_audit"] = exact_audit_hook
        with ExitStack() as stack:
            self._install_solve_tripwires(stack, tripwire_calls)
            if claim_write_failure:
                real_writer = runner._write_exclusive_preserving

                def interrupted_claim_write(path, data):
                    path = Path(path)
                    if path.name == "claim.json":
                        path.write_bytes(b"{partial")
                        raise OSError("inert interrupted claim serialization")
                    return real_writer(path, data)

                stack.enter_context(patch.object(
                    runner, "_write_exclusive_preserving", interrupted_claim_write))
            result = runner.run_attempt(self.commit, attempt, _services=services)
        self.assertEqual(tripwire_calls, [])
        self.assertEqual(result["outcome"], expected_outcome, result.get("first_failure"))
        self.assertEqual(result["quality_gate"], False if expected_outcome == "completed-missed" else None)
        self.assertEqual(calls["synthetic_policy_returned"], expected_solve_calls)
        mode_records = ["attempt.json", "claim.json", "report.json"]
        if claim_write_failure:
            mode_records.remove("claim.json")
            self.assertEqual((attempt / "claim.json").read_bytes(), b"{partial")
        for name in mode_records:
            path = attempt / name
            record = json.loads(path.read_text(encoding="utf-8"))
            record["execution_mode"] = "frozen-production"
            _write_record(path, record)
        raw_report = (attempt / "report.json").read_bytes()
        report_digest = hashlib.sha256(raw_report).hexdigest()
        return attempt, report_digest, payload, model

    def _verify_no_training(self, attempt, report_digest):
        calls = []
        with ExitStack() as stack:
            self._install_solve_tripwires(stack, calls)
            verified = verifier.verify_publication(attempt, report_digest)
        self.assertEqual(calls, [])
        self.assertTrue(verified["saved_only"])
        self.assertEqual(verified["verifier_production_calls"], 0)
        self.assertEqual(verified["production_calls_entered"], 1)
        self.assertTrue(verified["source_verified"])
        self.assertEqual(verified["outcome"], "completed-missed")
        self.assertFalse(verified["quality_gate"])
        return verified

    def test_runner_saved_synthetic_miss_is_replayed_against_full_committed_source(self):
        with tempfile.TemporaryDirectory() as temp:
            attempt, report_digest, _payload, _model = self._make_attempt(temp)
            result = self._verify_no_training(attempt, report_digest)
            self.assertGreaterEqual(result["source_files_verified"], 10)
            self.assertTrue(result["policy_replayed"])
            self.assertIsNotNone(result["exact_metrics"])

    def test_saved_exact_ledger_mutation_is_rejected_after_report_pin(self):
        with tempfile.TemporaryDirectory() as temp:
            attempt, report_digest, _payload, _model = self._make_attempt(temp)
            path = attempt / "exact-certificate.json"
            record = json.loads(path.read_text(encoding="utf-8"))
            ledger = record["certificate"]["normalization_ledger"]
            self.assertTrue(ledger)
            ledger[0]["mutation_for_test"] = "synthetic tamper"
            _write_record(path, record)
            with self.assertRaises(ValueError):
                verifier.verify_publication(attempt, report_digest)

    def test_saved_numeric_raw_and_source_receipts_reject_tampering(self):
        for artifact, mutate in (
            ("numeric-replay.json", lambda p: p.update({"tampered": True})),
            ("raw-envelope.json", None),
            ("source-before.json", lambda p: p["source_state"]["files"][
                "pokerlab/__init__.py"].update({"git_blob": "0" * 40})),
        ):
            with self.subTest(artifact=artifact), tempfile.TemporaryDirectory() as temp:
                attempt, report_digest, _payload, _model = self._make_attempt(temp)
                path = attempt / artifact
                if mutate is None:
                    path.write_bytes(path.read_bytes() + b" ")
                else:
                    value = json.loads(path.read_text(encoding="utf-8"))
                    mutate(value)
                    _write_record(path, value)
                with self.assertRaises(ValueError):
                    verifier.verify_publication(attempt, report_digest)

    def test_partial_claim_write_is_preserved_and_preparation_failure_is_verified_without_math(self):
        with tempfile.TemporaryDirectory() as temp:
            attempt, report_digest, _payload, _model = self._make_attempt(
                temp, claim_write_failure=True, expected_outcome="preparation-failed",
                expected_solve_calls=0)
            with patch.object(verifier, "_load_math",
                              side_effect=AssertionError("math loaded for preparation failure")):
                result = verifier.verify_publication(attempt, report_digest)
            self.assertEqual((attempt / "claim.json").read_bytes(), b"{partial")
            self.assertEqual(result["outcome"], "preparation-failed")
            self.assertIsNone(result["quality_gate"])
            self.assertEqual(result["production_calls_entered"], 0)
            self.assertTrue(result["source_verified"])
            self.assertEqual(result["unreceipted_artifacts"]["claim.json"]["authentication"],
                             "observed bytes without an original saved receipt")

    def test_forged_capacity_unknown_is_rejected_when_fresh_exact_replay_succeeds(self):
        with tempfile.TemporaryDirectory() as temp:
            def forged_capacity(_case, _payload):
                raise ValueError("Exact rational certificate exceeds its work limit (forged test claim)")

            attempt, report_digest, _payload, _model = self._make_attempt(
                temp, exact_audit_hook=forged_capacity, expected_outcome="completed-unknown")
            calls = []
            with ExitStack() as stack:
                self._install_solve_tripwires(stack, calls)
                stack.enter_context(patch.object(verifier, "_load_math", wraps=verifier._load_math))
                with self.assertRaisesRegex(ValueError, "not reproduced"):
                    verifier.verify_publication(attempt, report_digest)
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
