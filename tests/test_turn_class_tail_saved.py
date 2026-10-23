"""Fast CI replay of the immutable T6000 saved artifact.

This test replays policy mathematics and checks current math-source identities.
It intentionally does not recreate the full historical Git provenance check:
that check was performed in the frozen publication checkout, while CI's
shallow checkout may not contain the historical source commit.
"""
from __future__ import annotations

from contextlib import ExitStack
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import unittest
from unittest import mock

from pokerlab import postflop_solver
from pokerlab import public_diagnostics
from pokerlab import turn_class_tail_adapter
from pokerlab import turn_tail_adapter
from scripts import verify_turn_class_tail_experiment as verifier


REPORT_BYTES = 57_338
REPORT_SHA256 = "b974a13afcc93cb862f835af44d37fcc296b971a486c4f6c39c89d27b0d9d207"
POLICY_BYTES = 2_553_093
POLICY_SHA256 = "17e1e61135e4e4efd8757ad764ff532e0cda01757173172b8c584b556c611652"
FROZEN_COMMIT = "2aa02c4f2db75beb7bc8a229e3c36073a56c5118"
MATH_SOURCES = (
    "pokerlab/cards.py",
    "pokerlab/turn_class_vector_budget.py",
    "scripts/preflop_validation.py",
    "scripts/turn_river_validation.py",
    "scripts/turn_three_hand_reference.py",
    "scripts/turn_three_hand_exact_oracle.py",
    "scripts/turn_three_hand_classes.py",
    "scripts/turn_rational_certificate.py",
    "scripts/verify_turn_class_tail_experiment.py",
)
COUNTER_VALUES = {
    "chance_edges": 35,
    "chance_nodes": 5,
    "decision_edges": 420,
    "depth": 9,
    "pair_class_prefix_entries": 54,
    "physical_branch_subtrees_compared": 240,
    "policy_action_slots": 1086,
    "policy_rows": 486,
    "public_decisions": 188,
    "public_nodes": 456,
    "terminal_nodes": 263,
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _compare_saved(actual, expected, path="report"):
    """Require exact structure/types, allowing tolerance only for finite floats."""
    if type(expected) is dict:
        if type(actual) is not dict or set(actual) != set(expected):
            raise AssertionError(f"{path}: object keys differ")
        for key in expected:
            _compare_saved(actual[key], expected[key], f"{path}.{key}")
        return
    if type(expected) is list:
        if type(actual) is not list or len(actual) != len(expected):
            raise AssertionError(f"{path}: array shape differs")
        for index, (left, right) in enumerate(zip(actual, expected)):
            _compare_saved(left, right, f"{path}[{index}]")
        return
    if type(expected) is float:
        if type(actual) is not float or not math.isfinite(actual) or not math.isfinite(expected):
            raise AssertionError(f"{path}: expected finite float")
        if abs(actual - expected) > 1e-9:
            raise AssertionError(f"{path}: float differs by more than 1e-9")
        return
    if type(actual) is not type(expected) or actual != expected:
        raise AssertionError(f"{path}: exact value/type differs")


def _read_identity(path: Path, expected_bytes: int, expected_sha: str) -> bytes:
    if path.stat().st_size != expected_bytes:
        raise AssertionError(f"frozen artifact size mismatch: {path.name}")
    raw = path.read_bytes()
    if len(raw) != expected_bytes or _sha(raw) != expected_sha:
        raise AssertionError(f"frozen artifact identity mismatch: {path.name}")
    return raw


class SavedTurnClassTailArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(verifier.__file__).resolve().parents[1]
        folder = cls.root / "benchmarks" / "results"
        cls.report_raw = _read_identity(
            folder / verifier.REPORT_NAME, REPORT_BYTES, REPORT_SHA256)
        cls.policy_raw = _read_identity(
            folder / verifier.POLICY_NAME, POLICY_BYTES, POLICY_SHA256)
        cls.report = json.loads(cls.report_raw)
        cls.policy = json.loads(cls.policy_raw)

        cls.observed = verifier.jsonable(cls._audit_without_production_helpers())

    @classmethod
    def _audit_without_production_helpers(cls):
        # Independent audit must not call the production solver, production
        # tail trainer, production tree builder, or production diagnostics.
        with ExitStack() as stack:
            for target, name in (
                (turn_class_tail_adapter, "solve_turn_class_tail"),
                (turn_tail_adapter, "_train_original_weight_tail"),
                (postflop_solver, "_build_postflop_tree"),
                (public_diagnostics, "evaluate_profile"),
            ):
                stack.enter_context(mock.patch.object(
                    target, name, side_effect=AssertionError(
                        "production helper used during independent artifact replay")))
            return verifier.audit_payload(cls.policy, root=cls.root)

    def test_frozen_bytes_commit_and_current_math_source_subset(self):
        self.assertEqual(self.report["generation_head"], FROZEN_COMMIT)
        self.assertEqual(self.report["training_source_git_commit"], FROZEN_COMMIT)
        self.assertEqual(self.report["policy_bytes"], POLICY_BYTES)
        self.assertEqual(self.report["policy_sha256"], POLICY_SHA256)

        pinned = self.report["source_sha256"]
        for name in MATH_SOURCES:
            with self.subTest(source=name):
                raw = (self.root / name).read_bytes()
                if name.endswith(".py"):
                    raw = raw.replace(b"\r\n", b"\n")
                self.assertIn(name, pinned)
                self.assertEqual(_sha(raw), pinned[name])

    def test_fixed_t6000_schedule_scope_and_full_physical_policy(self):
        self.assertEqual(self.report["schema"], verifier.SCHEMA)
        self.assertIs(type(self.report["schema_version"]), int)
        self.assertEqual(self.report["schema_version"], 1)
        self.assertEqual(self.report["completed_training_calls"], 1)
        self.assertEqual(self.report["fixture"], verifier.FIXTURE)
        self.assertEqual(self.report["request"], verifier.REQUEST)
        self.assertEqual(self.policy["algorithm"], "cfrplus")
        self.assertEqual(self.policy["iterations"], 6000)
        self.assertEqual(self.policy["discard"], 2000)
        self.assertEqual(self.policy["averaged_sweeps"], 4000)
        self.assertEqual(self.policy["average_weight_sum"], 16_002_000)
        self.assertEqual(self.policy["requested_regret_passes"], 12_000)
        self.assertEqual(self.policy["requested_average_passes"], 4000)
        self.assertEqual(self.policy["requested_total_traversal_passes"], 16_000)
        self.assertEqual(self.policy["resource_model"], "turn-seven-class-vector-v1")
        self.assertEqual(self.policy["runout_mode"], "full-deck")
        self.assertEqual(self.policy["worlds"], 396)
        self.assertEqual(self.policy["worlds_materialized"], 396)
        self.assertEqual(self.policy["compatible_pairs"], 9)
        self.assertEqual(self.policy["deals"], 9)
        self.assertEqual(len(self.policy["runouts"]), 48)
        self.assertEqual(self.policy["runouts"], self.policy["reachable_runouts"])
        self.assertEqual(self.policy["training_calls"], 1)

    def test_independent_full_replay_matches_all_saved_math(self):
        fields = (
            "numeric_oracle_metrics",
            "exact_numeric_differences",
            "class_audit",
            "exact_metrics_fractions",
            "exact_value_interval",
            "target_nash_conv_fraction",
            "target_met",
            "threshold_miss",
            "old_baseline",
        )
        for name in fields:
            with self.subTest(field=name):
                _compare_saved(self.observed[name], self.report[name], name)

        exact = self.observed["exact_metrics_fractions"]
        self.assertEqual(len(exact), 8)
        self.assertEqual(set(exact), set(verifier.METRICS))
        exact_nc = Fraction(exact["nash_conv"])
        self.assertLessEqual(exact_nc, Fraction(1, 1000))
        self.assertIs(self.observed["target_met"], True)
        self.assertIs(self.observed["threshold_miss"], False)

    def test_class_scan_partition_counters_and_old_miss_are_preserved(self):
        audit = self.observed["class_audit"]
        self.assertEqual(audit["training_calls"], 0)
        self.assertEqual(set(audit["full_physical_exact_metrics"]), set(verifier.METRICS))
        self.assertEqual(
            audit["generic_class_audits"]["scan"]["metrics"],
            audit["full_physical_exact_metrics"])
        self.assertEqual(
            audit["generic_class_audits"]["partition"]["metrics"],
            audit["full_physical_exact_metrics"])
        self.assertEqual(audit["class_census"], COUNTER_VALUES)

        old = self.observed["old_baseline"]
        self.assertIs(old["threshold_miss"], True)
        self.assertEqual(
            set(old["exact_metrics_fractions"]), set(verifier.METRICS))
        self.assertGreater(
            Fraction(old["exact_metrics_fractions"]["nash_conv"]),
            Fraction(1, 1000))
        self.assertLessEqual(
            Fraction(self.observed["exact_value_interval"]["lower"]),
            Fraction(self.observed["exact_value_interval"]["upper"]))


if __name__ == "__main__":
    unittest.main()
