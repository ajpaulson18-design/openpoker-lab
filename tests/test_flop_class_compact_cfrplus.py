"""Fast orchestration and saved-report rejection checks for compact CFR+."""
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import flop_class_compact_budget as budget
from scripts import flop_class_compact_cfrplus as trainer
from scripts import flop_public_classes as proof
from scripts import verify_flop_class_compact_cfrplus as replay


class CompactCFRPlusOrchestrationTests(unittest.TestCase):
    def test_new_budget_accepts_above_legacy_limit_without_changing_legacy_admission(self):
        forecast = budget.admit_compact_request(141)
        self.assertEqual(forecast["requested_iterations"], 141)
        self.assertGreater(forecast["total_admitted_work"], 0)
        with self.assertRaises(ValueError):
            trainer.base.admit_request(141)

    def test_invalid_requests_stop_before_sources_baseline_proof_or_training(self):
        bad = (True, False, 0, -1, 561, 1.0, "1", None)
        with patch.object(trainer, "source_hashes", side_effect=AssertionError("sources")) as sources, \
             patch.object(trainer.baseline, "_read", side_effect=AssertionError("baseline")) as baseline_read, \
             patch.object(trainer.publication, "verify", side_effect=AssertionError("proof")) as receipt, \
             patch.object(trainer.proof, "build_model", side_effect=AssertionError("tree")) as build, \
             patch.object(trainer.cfr_plus, "train", side_effect=AssertionError("train")) as train:
            for value in bad:
                with self.subTest(iterations=value), self.assertRaises(ValueError):
                    trainer.solve_fixed_compact(value)
        sources.assert_not_called()
        baseline_read.assert_not_called()
        receipt.assert_not_called()
        build.assert_not_called()
        train.assert_not_called()

    def test_oversized_adapter_source_is_rejected_before_read(self):
        with patch.object(trainer.base, "_source_hashes", return_value={}), \
             patch.object(Path, "stat", return_value=SimpleNamespace(st_size=2 * 1024 * 1024 + 1)), \
             patch.object(Path, "read_bytes", side_effect=AssertionError("must reject before read")) as read:
            with self.assertRaisesRegex(ValueError, "exceeds bound"):
                trainer.source_hashes()
        read.assert_not_called()

    @staticmethod
    @contextmanager
    def _guard():
        yield {}

    def _solve_patches(self, *, raw_rows=None, source_hashes=None,
                       validate_side_effect=None):
        infos = {(0, "AsAd", ()): 2, (1, "KsKd", ("bet",)): 2}
        raw_rows = {key: [0.5, 0.5] for key in infos} if raw_rows is None else raw_rows
        model = SimpleNamespace(root=object(), census={"compact_worlds": 126})
        captured = {}

        def lift(rows, _model):
            captured["rows"] = rows
            return {"strategy": []}

        def audit(payload, _model):
            captured["payload"] = dict(payload)
            return {"exact_metrics": {"nash_conv": "1/100"}, "physical_rows_lifted": 9}

        validator = patch.object(
            trainer.budget, "validate_observed_dimensions",
            side_effect=validate_side_effect or (lambda *args: True))
        patchers = [
            patch.object(trainer, "source_hashes", side_effect=source_hashes or [{"s": "same"}, {"s": "same"}]),
            patch.object(trainer.baseline, "_read", return_value=(None, b"pinned")),
            patch.object(trainer.publication, "verify", return_value={"receipt": True}),
            patch.object(trainer.proof, "independent_guard", side_effect=lambda: self._guard()),
            patch.object(trainer.proof, "build_model", return_value=model),
            patch.object(trainer.base, "_training_inputs", return_value=((), infos, 33)),
            validator,
            patch.object(trainer.cfr_plus, "train", return_value=raw_rows),
            patch.object(trainer.policy, "canonicalize_binary_rows",
                         return_value=(infos.copy(), {"rows_changed": 0})),
            patch.object(trainer.proof, "lift_policy", side_effect=lift),
            patch.object(trainer.proof, "audit_policy", side_effect=audit),
            patch.object(trainer.proof, "_digest", return_value="digest"),
        ]
        return patchers, captured, infos

    def test_baseline_miss_authentication_failure_stops_before_tree_and_training(self):
        with patch.object(trainer, "source_hashes", return_value={"s": "same"}), \
             patch.object(trainer.baseline, "_read", side_effect=ValueError("pinned miss changed")) as baseline_read, \
             patch.object(trainer.publication, "verify", side_effect=AssertionError("proof")) as receipt, \
             patch.object(trainer.proof, "build_model", side_effect=AssertionError("tree")) as build, \
             patch.object(trainer.cfr_plus, "train", side_effect=AssertionError("train")) as train:
            with self.assertRaisesRegex(ValueError, "pinned miss changed"):
                trainer.solve_fixed_compact(141)
        baseline_read.assert_called_once()
        receipt.assert_not_called()
        build.assert_not_called()
        train.assert_not_called()

    def test_observed_dimension_check_precedes_trainer(self):
        patchers, _, _ = self._solve_patches(
            validate_side_effect=ValueError("census mismatch"))
        with patchers[0], patchers[1], patchers[2], patchers[3], patchers[4], \
             patchers[5], patchers[6] as validate, patchers[7] as train:
            with self.assertRaisesRegex(ValueError, "census mismatch"):
                trainer.solve_fixed_compact(141)
        validate.assert_called_once()
        train.assert_not_called()

    def test_missing_or_extra_trainer_rows_reject_before_policy_lift(self):
        for bad_rows in ({(0, "AsAd", ()): [0.5, 0.5]},
                         {(0, "AsAd", ()): [0.5, 0.5], (1, "KsKd", ("bet",)): [0.5, 0.5],
                          (1, "extra", ()): [0.5, 0.5]}):
            with self.subTest(row_count=len(bad_rows)):
                patchers, _, _ = self._solve_patches(raw_rows=bad_rows)
                with patchers[0], patchers[1], patchers[2], patchers[3], patchers[4], \
                     patchers[5], patchers[6], patchers[7] as train, patchers[8] as normalize, \
                     patchers[9] as lift:
                    with self.assertRaisesRegex(ValueError, "every information set"):
                        trainer.solve_fixed_compact(141)
                train.assert_called_once()
                normalize.assert_not_called()
                lift.assert_not_called()

    def test_source_drift_after_independent_diagnostics_rejects_result(self):
        patchers, _, _ = self._solve_patches(source_hashes=[{"s": "before"}, {"s": "after"}])
        with patchers[0], patchers[1], patchers[2], patchers[3], patchers[4], \
             patchers[5], patchers[6], patchers[7], patchers[8], patchers[9] as lift, \
             patchers[10] as audit:
            with self.assertRaisesRegex(ValueError, "Source changed"):
                trainer.solve_fixed_compact(141)
        lift.assert_called_once()
        audit.assert_called_once()

    def test_trainer_emits_exact_zero_delay_and_budget_version_metadata(self):
        patchers, captured, _ = self._solve_patches()
        with patchers[0], patchers[1], patchers[2], patchers[3], patchers[4], \
             patchers[5], patchers[6], patchers[7], patchers[8], patchers[9], \
             patchers[10], patchers[11]:
            result = trainer.solve_fixed_compact(141)
        payload = captured["payload"]
        self.assertIs(type(payload["averaging_delay"]), int)
        self.assertEqual(payload["averaging_delay"], 0)
        self.assertEqual(payload["resource_model"], budget.VERSION)
        self.assertEqual(result["admission"]["requested_iterations"], 141)

    def _saved_report(self, *, schema=None, iterations=141, delay=0,
                      baseline_mismatch=False, admission_mismatch=False):
        admission = budget.admit_compact_request(iterations)
        if admission_mismatch:
            admission = dict(admission, total_admitted_work=admission["total_admitted_work"] + 1)
        payload = {"iterations": iterations, "algorithm": "cfrplus",
                   "averaging_delay": delay, "research_adapter": trainer.ADAPTER,
                   "resource_model": admission["version"]}
        expected_baseline = {
            "raw_sha256": replay.baseline.RAW_SHA256,
            "artifact_sha256": replay.baseline.ARTIFACT_SHA256,
            "nash_conv": replay.baseline.EXPECTED_NASH_CONV,
            "quality_target_met": False,
        }
        if baseline_mismatch:
            expected_baseline["quality_target_met"] = True
        report = {"schema_version": schema or trainer.ADAPTER,
                  "status": "trained-policy-physically-verified",
                  "physical_policy": payload,
                  "admission": admission,
                  "source_lf_sha256": {"s": "pinned"},
                  "baseline_pilot": expected_baseline}
        report["artifact_sha256"] = proof._digest(
            {key: value for key, value in report.items() if key != "artifact_sha256"})
        return report

    def _verify_before_proof_rejects(self, report, message):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(report, separators=(",", ":")), encoding="utf-8")
            with patch.object(replay.trainer, "source_hashes", return_value={"s": "pinned"}), \
                 patch.object(replay.baseline, "_read", side_effect=AssertionError("baseline read")) as baseline_read, \
                 patch.object(replay.publication, "verify", side_effect=AssertionError("proof build")) as proof_verify, \
                 patch.object(replay.proof, "build_model", side_effect=AssertionError("model")) as model:
                with self.assertRaisesRegex(ValueError, message):
                    replay.verify_saved(path)
        baseline_read.assert_not_called()
        proof_verify.assert_not_called()
        model.assert_not_called()

    def test_saved_schema_admission_and_baseline_mismatch_reject_before_proof(self):
        self._verify_before_proof_rejects(
            self._saved_report(schema="wrong-schema"), "scope/status")
        self._verify_before_proof_rejects(
            self._saved_report(admission_mismatch=True), "admission")
        self._verify_before_proof_rejects(
            self._saved_report(baseline_mismatch=True), "Historical pilot miss")

    def test_saved_replay_requires_exact_integer_zero_delay(self):
        self._verify_before_proof_rejects(self._saved_report(delay=True), "method or admission")
        self._verify_before_proof_rejects(self._saved_report(delay=0.0), "method or admission")
        good = self._saved_report(delay=0)
        self.assertIs(type(good["physical_policy"]["averaging_delay"]), int)
        self.assertEqual(good["physical_policy"]["averaging_delay"], 0)
        self.assertEqual(good["physical_policy"]["resource_model"], budget.VERSION)


if __name__ == "__main__":
    unittest.main()
