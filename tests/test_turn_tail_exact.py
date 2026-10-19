"""Bounded synthetic tests for the future saved-policy exact tail audit.

These fixtures exercise audit plumbing only; they are not the D=1000/T=1500
experiment and do not call a trainer.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from scripts import audit_full_deck_raised_exact as quotient
from scripts import audit_turn_tail_exact as audit
from scripts import full_deck_raised_reference as reference

TEST_WORK_CHARGES = {"materialized": 1_000_000, "matrix-free": 2_000_000}


class TurnTailExactAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture, cls.board, cls.config, cls.worlds, cls.selected, cls.root, _ = reference.model()
        cls.model = (cls.fixture, cls.board, cls.config, cls.worlds,
                     cls.selected, cls.root, [])
        result = {
            "board": list(cls.board), "runouts": list(cls.selected),
            "runout_mode": "full-deck",
            "reachable_runouts": sorted({world["river"] for world in cls.worlds}),
            "strategy": reference._policy_rows(reference._walk(cls.root), cls.worlds),
            "info_sets": 2404, "compatible_world_count": 176,
            "compatible_pairs": 4, "config": cls.config.to_dict(),
            "river_config": cls.config.to_dict(),
        }
        replay = quotient.rules.replay_policy(
            result, cls.fixture["oop"], cls.fixture["ip"],
            board=cls.fixture["board"], config=cls.fixture["config"])
        result.update({name: replay[name] for name in audit.METRICS})
        cls.result = result
        cls.metrics = {name: result[name] for name in audit.METRICS}
        cls.source_map = {"draft-test-source": "0" * 64}
        cls.head = "a" * 40

    def _fixture(self, root, *, mutate_profile=None):
        policies_dir = root / "numeric-policies"
        policies_dir.mkdir()
        rows = []
        policy_bytes = {}
        for backend in audit.BACKENDS:
            for profile in audit.WINDOW:
                payload = deepcopy(self.result)
                payload["algorithm"] = "cfrplus"
                if profile == "full":
                    payload.update({
                        "iterations": audit.TOTAL,
                        "solver_version": "configured-postflop-v1",
                        "strategy_schema": "postflop-strategy-v1",
                        "average_schedule": "linear-post-sweep-own-reach",
                    })
                else:
                    payload.update({
                        "iterations": audit.DISCARD if profile == "prefix" else audit.TOTAL,
                        "solver_version": "research-raised-turn-tail-v1",
                        "source_solver_version": "configured-postflop-v1",
                        "research_profile": profile,
                        "source_requested_iterations": audit.TOTAL,
                        "source_iteration_window": ([1, audit.DISCARD] if profile == "prefix"
                                                    else [audit.DISCARD + 1, audit.TOTAL]),
                        "averaged_sweeps": audit.DISCARD if profile == "prefix" else audit.TOTAL-audit.DISCARD,
                        "average_schedule": ("linear-prefix-own-reach" if profile == "prefix"
                                             else "linear-tail-own-realization"),
                    })
                if mutate_profile == (backend, profile):
                    # Stay numerically valid while violating exact equivalence:
                    # alter only one river-class strategy row, then recompute
                    # all reported numeric metrics from the full physical game.
                    changed_row = next(row for row in payload["strategy"]
                                       if row["street"] == "river" and
                                       row["board"][-1] != "3c" and len(row["actions"]) > 1)
                    changed_row["actions"][0]["probability"] = 0.5
                    changed_row["actions"][1]["probability"] = 0.5
                    replay = quotient.rules.replay_policy(
                        payload, self.fixture["oop"], self.fixture["ip"],
                        board=self.fixture["board"], config=self.fixture["config"])
                    payload.update({name: replay[name] for name in audit.METRICS})

                name = audit._policy_name(backend, profile)
                raw = audit._canonical(payload)
                (policies_dir / name).write_bytes(raw)
                digest = hashlib.sha256(raw).hexdigest()
                metrics = {key: payload[key] for key in audit.METRICS}
                work = TEST_WORK_CHARGES[backend]
                rows.append({
                    "backend": backend, "profile": profile,
                    "algorithm": "cfrplus", "target_exploitability": None,
                    "threshold": audit.THRESHOLD,
                    "threshold_met": metrics["nash_conv"] <= audit.THRESHOLD,
                    "iterations": audit.DISCARD if profile == "prefix" else audit.TOTAL,
                    "iterations_completed": audit.TOTAL,
                    "source_requested_iterations": audit.TOTAL,
                    "capture_callback_iterations": [audit.DISCARD, audit.TOTAL],
                    "capture_trainer_calls": 1,
                    "final_snapshot_matches_returned_profile": True,
                    "work_charge": work,
                    "work_limit": audit.FIXED_WORK_LIMIT,
                    "worlds": 176, "compatible_pairs": 4,
                    "information_rows": 2404,
                    "policy_file": name, "policy_sha256": digest,
                    "metrics": metrics, "independent_metrics": metrics,
                    "ledger": ({"fixture_ledger": "synthetic-test-only"}
                               if profile == "tail" else None),
                })
                policy_bytes[(backend, profile)] = raw
        report = {
            "schema_version": 1,
            "benchmark_id": "full-deck-raised-turn-tail-v1",
            "generation_git_commit": "b" * 40,
            "generation_capture_calls": 2,
            "results": rows,
        }
        report_path = root / "numeric-report.json"
        raw_report = audit._canonical(report)
        report_path.write_bytes(raw_report)
        return report_path, policies_dir, hashlib.sha256(raw_report).hexdigest(), rows

    def _stable_guards(self):
        return (patch.object(audit, "fingerprints", return_value=self.source_map),
                patch.object(audit, "_head", return_value=self.head))

    def _scratch(self):
        parent = audit.ROOT / "tmp-turn-tail-exact-tests"
        parent.mkdir(exist_ok=True)
        root = parent / ("turn-tail-exact-" + uuid4().hex)
        root.mkdir()
        self.addCleanup(self._cleanup_scratch, root)
        return root

    @staticmethod
    def _cleanup_scratch(root):
        policies = root / "numeric-policies"
        if policies.exists():
            for backend in audit.BACKENDS:
                for profile in audit.WINDOW:
                    (policies / audit._policy_name(backend, profile)).unlink(missing_ok=True)
            policies.rmdir()
        for name in ("numeric-report.json", "exact-report.json"):
            (root / name).unlink(missing_ok=True)
        (root / "unrelated.txt").unlink(missing_ok=True)
        root.rmdir()

    def test_six_fixed_profiles_generate_and_verify_without_training(self):
        root = self._scratch()
        report, policies, digest, _ = self._fixture(root)
        output = root / "exact-report.json"
        fp, head = self._stable_guards()
        trainer_modules = {"pokerlab.postflop_solver", "pokerlab.matrix_free_turn"}
        loaded_before = trainer_modules.intersection(sys.modules)
        with fp, head:
            generated = audit.generate(
                output, numeric_report_path=report, policies_dir=policies,
                numeric_report_sha256=digest)
            verified = audit.verify_saved_artifact(
                output, numeric_report_path=report, policies_dir=policies,
                numeric_report_sha256=digest)
        self.assertEqual(trainer_modules.intersection(sys.modules), loaded_before)
        saved = json.loads(output.read_bytes())
        profiles = saved["audit"]["profiles"]
        self.assertEqual(generated["status"], "VERIFIED_EXACT_TURN_TAIL")
        self.assertEqual(verified["training_calls"], 0)
        self.assertEqual((verified["accepted_profiles"], verified["rejected_profiles"]), (6, 0))
        self.assertEqual(len(profiles), 6)
        for item in profiles:
            self.assertEqual(item["status"], "accepted")
            self.assertEqual(set(item["certificate"]["metrics"]), set(audit.METRICS))
            self.assertEqual(set(item["full_numeric_metrics"]), set(audit.METRICS))

    def test_exactly_nonconstant_policy_is_rejected_without_partial_certificate(self):
        root = self._scratch()
        report, policies, digest, _ = self._fixture(
            root, mutate_profile=("materialized", "tail"))
        output = root / "exact-report.json"
        fp, head = self._stable_guards()
        with fp, head:
            verified = audit.generate(
                output, numeric_report_path=report, policies_dir=policies,
                numeric_report_sha256=digest)
        saved = json.loads(output.read_bytes())["audit"]
        rejected = next(item for item in saved["profiles"]
                        if item["backend"] == "materialized" and item["profile"] == "tail")
        self.assertEqual((verified["accepted_profiles"], verified["rejected_profiles"]), (5, 1))
        self.assertEqual(rejected["status"], "rejected")
        self.assertIn("exactly class-constant", rejected["rejection_reason"])
        self.assertNotIn("certificate", rejected)
        self.assertNotIn("full_numeric_metrics", rejected)

    def test_empty_future_numeric_report_pin_fails_before_reading(self):
        with patch.object(audit, "NUMERIC_REPORT_SHA256", ""), \
             patch.object(Path, "read_bytes", side_effect=AssertionError("read despite empty pin")):
            with self.assertRaisesRegex(ValueError, "not configured"):
                audit._load_inputs("not-read.json", "not-read-policies", "")

    def test_final_input_and_source_drift_aborts_after_six_audit_calls(self):
        root = self._scratch()
        report, policies, digest, rows = self._fixture(root)
        inputs = audit._load_inputs(report, policies, digest)
        paths = [report, policies / rows[0]["policy_file"], audit.REFERENCE]
        for path in paths:
            with self.subTest(path=path.name):
                calls = 0
                original_read = audit._read_capped
                def late_read(candidate, cap, label):
                    raw = original_read(candidate, cap, label)
                    if Path(candidate) == path and calls >= 6:
                        return raw + b"late-drift"
                    return raw
                def fake_audit(*args):
                    nonlocal calls
                    calls += 1
                    return {"status": "accepted"}
                with patch.object(audit, "_guard"), \
                     patch.object(audit, "_read_capped", side_effect=late_read), \
                     patch.object(audit, "_audit_profile", side_effect=fake_audit):
                    with self.assertRaisesRegex(ValueError, "changed during exact audit"):
                        audit._reconstruct(inputs, self.source_map, self.head)
                self.assertEqual(calls, 6)

        for label in ("source", "HEAD"):
            calls = 0
            def fake_audit(*args):
                nonlocal calls
                calls += 1
                return {"status": "accepted"}
            def late_guard(source_map, head):
                if calls >= 6:
                    raise ValueError("Exact tail audit " + label + " changed")
            with self.subTest(drift=label), \
                 patch.object(audit, "_guard", side_effect=late_guard), \
                 patch.object(audit, "_audit_profile", side_effect=fake_audit):
                with self.assertRaisesRegex(ValueError, "changed"):
                    audit._reconstruct(inputs, self.source_map, self.head)
                self.assertEqual(calls, 6)

    def test_numeric_observations_allow_tolerance_but_exact_report_fields_do_not(self):
        expected = {"accepted_profiles": 1, "rejected_profiles": 0, "profiles": [{
            "status": "accepted",
            "full_numeric_metrics": {"nash_conv": 1.0},
            "exact_minus_numeric": {"nash_conv": 0.0},
            "certificate": {"metrics": {"nash_conv": "1/2"},
                            "ledger": {"normalization": "3/7"}},
            "numeric_tail_ledger": {"correction": "5/11"},
        }]}
        approximate = deepcopy(expected)
        approximate["profiles"][0]["full_numeric_metrics"]["nash_conv"] += 5e-13
        approximate["profiles"][0]["exact_minus_numeric"]["nash_conv"] -= 5e-13
        self.assertTrue(audit._compare_reconstructions(approximate, deepcopy(expected)))

        for field, mutate in (
            ("certificate", lambda item: item["certificate"]["metrics"].update(nash_conv="1/3")),
            ("ledger", lambda item: item["numeric_tail_ledger"].update(correction="7/13")),
        ):
            with self.subTest(field=field):
                tampered = deepcopy(expected)
                mutate(tampered["profiles"][0])
                self.assertFalse(audit._compare_reconstructions(tampered, deepcopy(expected)))

    def test_published_verify_failure_rolls_back_only_owned_report(self):
        root = self._scratch()
        report, policies, digest, _ = self._fixture(root)
        output = root / "exact-report.json"
        sibling = root / "unrelated.txt"
        sibling.write_text("keep this sibling", encoding="utf-8")
        inputs = audit._load_inputs(report, policies, digest)
        calls = 0
        def verify_candidate(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"status": "VERIFIED_EXACT_TURN_TAIL"}
            raise ValueError("controlled published verification rejection")
        fp, head = self._stable_guards()
        with fp, head, \
             patch.object(audit, "_load_inputs", return_value=inputs), \
             patch.object(audit, "_reconstruct", return_value={
                 "accepted_profiles": 6, "rejected_profiles": 0, "profiles": []}), \
             patch.object(audit, "verify_saved_artifact", side_effect=verify_candidate):
            with self.assertRaisesRegex(ValueError, "published verification rejection"):
                audit.generate(output, numeric_report_path=report, policies_dir=policies,
                               numeric_report_sha256=digest)
        self.assertEqual(calls, 2)
        self.assertFalse(output.exists())
        self.assertEqual(sibling.read_text(encoding="utf-8"), "keep this sibling")


if __name__ == "__main__":
    unittest.main()
