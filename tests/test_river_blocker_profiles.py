"""Saved-profile adversarial replay tests; verification must never train."""
import copy
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch
from scripts import river_blocker_profiles as p
ROOT = Path(__file__).resolve().parents[1]


class ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = p.verify_profiles()

    def run_report(self, report):
        path = ROOT / ("river-blocker-profile-test-" + uuid.uuid4().hex + ".json")
        try:
            path.write_text(json.dumps(report), encoding="utf-8")
            return p.verify_profiles(path)
        finally:
            path.unlink(missing_ok=True)

    def reject(self, edit):
        report = copy.deepcopy(self.report)
        edit(report)
        with self.assertRaises((ValueError, RuntimeError, KeyError, TypeError, IndexError)):
            self.run_report(report)

    def test_positive_grid_and_value_in_every_interval(self):
        from fractions import Fraction as F
        self.assertEqual({(r["backend"], r["iterations"]) for r in self.report["results"]}, set(p.GRID))
        value = F(-43339, 1751)
        self.assertEqual(F(self.report["known_game_value_fraction"]), value)
        for row in self.report["results"]:
            self.assertLessEqual(F(row["exact"]["lower_value_bound"]), value)
            self.assertGreaterEqual(F(row["exact"]["upper_value_bound"]), value)
            self.assertEqual(row["target_met"], F(row["exact"]["metrics"]["nash_conv"]) <= F(1, 1000))

    def test_verifier_never_trains(self):
        with patch.object(p, "solve", side_effect=AssertionError("Verifier tried training")):
            self.run_report(self.report)

    def test_false_zero_metrics(self):
        def edit(report):
            row = report["results"][0]
            row["exact"]["metrics"] = {n: "0" for n in row["exact"]["metrics"]}
            row["target_met"] = row["exact_zero_gap"] = True
        self.reject(edit)

    def test_altered_normalization(self):
        self.reject(lambda r: r["results"][0]["exact"]["normalization_ledger"][0].update(input_row_sum_fraction="999"))

    def test_missing_duplicate_bool_grid(self):
        self.reject(lambda r: r["results"].pop())
        self.reject(lambda r: r["results"].__setitem__(1, copy.deepcopy(r["results"][0])))
        self.reject(lambda r: r["results"][0].update(iterations=True))

    def test_policy_hash_and_unsafe_path(self):
        self.reject(lambda r: r["results"][0].update(policy_sha256="0" * 64))
        self.reject(lambda r: r["results"][0].update(policy_file="../unrelated.json"))

    def test_scope_threshold_schema(self):
        self.reject(lambda r: r.update(target_nash_conv_fraction="1"))
        self.reject(lambda r: r.update(scope="unrestricted"))
        self.reject(lambda r: r.update(schema_version=True))

    def test_source_pins_and_unsafe_inventory(self):
        self.reject(lambda r: r["source_sha256"].pop("scripts/turn_river_validation.py"))
        self.reject(lambda r: r["source_sha256"].update({"../unrelated.py": "0" * 64}))

    def test_unrelated_training_inventory_historical(self):
        report = copy.deepcopy(self.report)
        report["source_sha256"]["pokerlab/preflop_tree.py"] = "0" * 64
        self.run_report(report)

    def test_historical_generation_commit_not_looked_up(self):
        report = copy.deepcopy(self.report)
        report["baseline_git_commit"] = "b" * 40
        self.run_report(report)

    def test_mid_verification_head_and_source_drift(self):
        with patch.object(p, "head", side_effect=["a" * 40, "b" * 40]):
            with self.assertRaisesRegex(RuntimeError, "HEAD"):
                p.verify_profiles()
        original, calls = p.inputs, []
        def changing():
            value = original()
            calls.append(None)
            if len(calls) > 1:
                value["changed.py"] = "0" * 64
            return value
        with patch.object(p, "inputs", side_effect=changing):
            with self.assertRaisesRegex(RuntimeError, "Source"):
                p.verify_profiles()

    def test_mid_verification_policy_change(self):
        original, calls = p.read_bounded, {}
        target = p.POLICY_DIR / "river-blocker-materialized-1000.json"
        def changing(path, cap):
            raw = original(path, cap)
            if Path(path) == target:
                calls[target] = calls.get(target, 0) + 1
                if calls[target] > 1:
                    return raw + b" "
            return raw
        with patch.object(p, "read_bounded", side_effect=changing):
            with self.assertRaisesRegex(RuntimeError, "inputs changed"):
                p.verify_profiles()

    def test_actual_bytes_are_bounded(self):
        fake = Mock()
        fake.stat.return_value.st_size = 1
        fake.read_bytes.return_value = b"abcdef"
        with self.assertRaisesRegex(ValueError, "changed beyond"):
            p.read_bounded(fake, 3)
