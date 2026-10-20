"""Focused controls for the fixed global-suit publication producer."""
from __future__ import annotations

from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import turn_suit_validation as validation


def _normalized_row(player, hand, history, probabilities):
    return {
        "player": player,
        "hand": hand,
        "street": "turn",
        "board": ["2c", "7d", "9h", "Js"],
        "history": list(history),
        "actions": [
            {"name": "check", "amount": 0, "raise_to": 0,
             "history_key": "check", "probability_fraction": probabilities[0]},
            {"name": "bet", "amount": 50, "raise_to": 50,
             "history_key": "bet@50", "probability_fraction": probabilities[1]},
        ],
    }


class TurnSuitValidationTests(unittest.TestCase):
    def test_predeclared_target_major_call_grid_is_fixed(self):
        self.assertEqual(validation.PERMUTATIONS, tuple(sorted(validation.PERMUTATIONS)))
        self.assertEqual(len(validation.PERMUTATIONS), 24)
        self.assertEqual(
            validation.GRID,
            tuple((target, backend, 1000)
                  for target in ("dcsh", "hscd", "shdc", "cdhs")
                  for backend in ("materialized", "matrix-free")),
        )
        self.assertEqual(len(validation.GRID), 8)
        self.assertEqual(validation.TARGET, F(1, 1000))
        self.assertEqual(validation.SYMMETRY_TARGET, F(1, 1_000_000_000))

    def test_normalized_hash_sorts_by_player_index_and_identity_not_input_order(self):
        oop = _normalized_row("oop", "AhAs", (), ("3/4", "1/4"))
        ip = _normalized_row("ip", "AdAs", ("check",), ("1/3", "2/3"))
        expected = validation.sha(validation.canonical([oop, ip]))
        self.assertEqual(validation.normalized_policy_rows_sha256([ip, oop]), expected)
        self.assertEqual(validation.normalized_policy_rows_sha256([oop, ip]), expected)
        altered = _normalized_row("oop", "AhAs", (), ("1/4", "3/4"))
        self.assertNotEqual(validation.normalized_policy_rows_sha256([ip, altered]), expected)

    def test_jsonable_preserves_non_string_policy_identity_keys(self):
        identity = ("oop", "AhAs", ("check", "bet@50"))
        encoded = json.loads(validation.canonical({identity: F(1, 3)}))
        self.assertEqual(encoded["key_value_entries"], [
            {"key": ["oop", "AhAs", ["check", "bet@50"]], "value": "1/3"}
        ])

    def test_exclusive_write_does_not_remove_an_existing_file(self):
        with tempfile.TemporaryDirectory(prefix="turn-suit-exclusive-") as directory:
            path = Path(directory) / "existing.json"
            original = b"immutable bytes"
            path.write_bytes(original)
            with self.assertRaises(FileExistsError):
                validation._write_exclusive(path, b"replacement")
            self.assertEqual(path.read_bytes(), original)

    def test_exact_policy_difference_uses_fraction_arithmetic(self):
        left = [_normalized_row("oop", "AhAs", (), ("1/3", "2/3"))]
        right = [_normalized_row("oop", "AhAs", (), ("333333333333333333/1000000000000000000",
                                                       "666666666666666667/1000000000000000000"))]
        self.assertEqual(validation._maximum_policy_difference(left, right), F(1, 3) - F(333333333333333333, 10**18))

    def test_one_sided_negative_control_is_structurally_rejected(self):
        raw = (validation.ROOT / "benchmarks/results/turn-suit-negative-reference-v1.json").read_bytes()
        base = validation.reference.game(validation.FIXTURE)
        evidence = validation._validate_negative_control(raw, base)
        self.assertEqual(evidence["worlds"], 8)
        self.assertEqual(evidence["compatible_pairs"], 4)
        self.assertEqual(evidence["new_pair_showdown_signs"], [0, 0])
        self.assertTrue(evidence["original_isomorphism_rejected"])

    def test_post_replace_verifier_rejection_restores_report_and_removes_only_new_policy(self):
        with tempfile.TemporaryDirectory(prefix="turn-suit-publish-") as directory:
            root = Path(directory)
            report_path = root / "report.json"
            policy_dir = root / "policies"
            policy_dir.mkdir()
            old_report = b'{"accepted":"previous"}\n'
            report_path.write_bytes(old_report)
            existing = policy_dir / "existing.json"
            existing_payload = b'{"immutable":true}\n'
            existing.write_bytes(existing_payload)
            new_policy = policy_dir / "new.json"
            report_payload = b'{"candidate":"cached-review-artifact"}\n'
            calls = []

            def reject_after_replace(path):
                calls.append(Path(path))
                if Path(path) == report_path:
                    raise ValueError("independent post-replace rejection")
                self.assertEqual(Path(path).read_bytes(), report_payload)
                return {"status": "cached candidate accepted for stage"}

            with patch.object(validation, "REPORT", report_path), \
                 patch.object(validation, "verify_saved_artifact", side_effect=reject_after_replace), \
                 patch.object(validation, "assert_unchanged", return_value=None):
                with self.assertRaisesRegex(ValueError, "post-replace rejection"):
                    validation._publish(
                        report_payload,
                        [(new_policy, b'{"new":true}\n'), (existing, existing_payload)],
                        "cached-head", {"cached-input": "pinned"},
                    )

            self.assertEqual(calls[-1], report_path)
            self.assertEqual(report_path.read_bytes(), old_report)
            self.assertFalse(new_policy.exists())
            self.assertEqual(existing.read_bytes(), existing_payload)
            self.assertFalse(list(root.glob("*.candidate")))

    def test_input_drift_guard_prevents_publication_before_writes(self):
        with tempfile.TemporaryDirectory(prefix="turn-suit-drift-") as directory:
            root = Path(directory)
            report_path = root / "report.json"
            prior = b'{"accepted":"previous"}\n'
            report_path.write_bytes(prior)
            policy = root / "policies" / "new.json"
            with patch.object(validation, "REPORT", report_path), \
                 patch.object(validation, "assert_unchanged",
                              side_effect=ValueError("pinned source drift")):
                with self.assertRaisesRegex(ValueError, "pinned source drift"):
                    validation._publish(b'{"candidate":true}\n',
                                        [(policy, b'{"policy":true}\n')],
                                        "head", {"input": "hash"})
            self.assertEqual(report_path.read_bytes(), prior)
            self.assertFalse(policy.exists())

    def test_numeric_projection_rejection_prevents_exact_witness_evaluation(self):
        witness = json.loads((validation.ROOT / "benchmarks/results/turn-blocker-sequence-equilibrium-v1.json").read_bytes())
        with patch.object(validation, "PERMUTATIONS", ("cdhs",)), \
             patch.object(validation.rules, "compare_result", side_effect=ValueError("numeric projection rejected")) as compared, \
             patch.object(validation.exact_helper, "evaluate_exact", side_effect=AssertionError("Exact evaluator ran before numeric acceptance")) as exact:
            with self.assertRaisesRegex(ValueError, "numeric projection rejected"):
                validation._validate_24_exact_transports(witness)
        compared.assert_called_once()
        exact.assert_not_called()

    def test_report_size_admission_happens_before_publication(self):
        with tempfile.TemporaryDirectory(prefix="turn-suit-cap-") as directory:
            report_path = Path(directory) / "report.json"
            with patch.object(validation, "REPORT", report_path), \
                 patch.object(validation, "MAX_REPORT_BYTES", 4):
                with self.assertRaisesRegex(ValueError, "2MB cap"):
                    validation._publish(b"12345", [], "head", {})
            self.assertFalse(report_path.exists())


if __name__ == "__main__":
    unittest.main()
