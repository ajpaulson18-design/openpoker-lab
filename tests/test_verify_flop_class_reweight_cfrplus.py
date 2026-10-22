"""Fast saved-policy replay checks; every physical oracle call is mocked."""
import gzip
import json
from fractions import Fraction
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pokerlab import cfr_plus
from scripts import flop_class_policy as policy
from scripts import flop_class_reweight_cfrplus as trainer
from scripts import flop_class_reweight_proof as reweighted
from scripts import flop_public_classes as proof
from scripts import verify_flop_class_compact_cfrplus_publication as compact_publication
from scripts import verify_flop_class_reweight_cfrplus as verifier


def _infos():
    result = {}
    for i in range(232):
        history = () if i == 0 else (f"oop-{i}",)
        result[(0, "AdAs", history)] = 2
    for i in range(234):
        result[(1, "KdKs", (f"ip-{i}",))] = 2
    return result


def _census():
    return {
        "compact_public_states": 1001, "compact_decisions": 316,
        "compact_chance_nodes": 58, "compact_terminals": 627,
        "physical_policy_rows": 16912, "compact_policy_rows": 466,
        "physical_action_slots": 33824, "compact_action_slots": 932,
        "compact_worlds": 126, "turn_classes": 11, "river_signatures": 19,
    }


def _guard():
    return {f"authority-{i}": 0 for i in range(41)}


class SavedReweightedReplayTests(unittest.TestCase):
    def _fixture(self, *, case_id="uniform", nash_conv="1/100"):
        plan = trainer.case_plan(case_id)
        infos = _infos()
        rows = {key: (0.5, 0.5) for key in infos}
        raw_rows = [[p, hand, list(history), list(values)]
                    for (p, hand, history), values in sorted(rows.items())]
        normalized, normalization = policy.canonicalize_binary_rows(rows)
        class_policy = [[p, hand, list(history), list(values)]
                        for (p, hand, history), values in sorted(normalized.items())]
        strategy = [{} for _ in range(16912)]
        nc = Fraction(nash_conv)
        exact_metrics = {
            "value_oop": "0", "value_ip": "0",
            "oop_best_response_value": str(nc / 2),
            "ip_best_response_value": str(nc / 2),
            "oop_best_response_gain": str(nc / 2),
            "ip_best_response_gain": str(nc / 2),
            "nash_conv": str(nc), "exploitability": str(nc / 2),
        }
        audit = {
            "exact_metrics": exact_metrics,
            "independent_numeric_metrics": {key: float(Fraction(value))
                                            for key, value in exact_metrics.items()},
            "exact_metric_count": 8,
            "physical_rows_lifted": 16912,
            "class_rows": 466,
            "maximum_numeric_gap": 0.0,
            "physical_strategy_sha256": proof._digest(strategy),
            "class_policy": class_policy,
        }
        world = ("AdAs", "KdKs", Fraction(1, 126), 1,
                 ("2c", "3d", "4h", "5c", "6d"))
        model = SimpleNamespace(
            physical={"worlds": tuple(world for _ in range(126))},
            baseline={"worlds": tuple(world for _ in range(126))},
            census=_census())
        source_map = {"frozen-source.py": "a" * 64}
        admission = trainer.admit_request(case_id, 560)
        payload = {
            "iterations": 560, "algorithm": "cfrplus", "averaging_delay": 0,
            "research_adapter": trainer.ADAPTER, "prior_case": case_id,
            "compact_resource_model": admission["compact_logical_admission"]["version"],
            "worlds": 5940, "compatible_pairs": 3, "deals": 3,
            "strategy_schema": "postflop-strategy-v1", "strategy": strategy,
        }
        compact_baseline = {
            "raw_sha256": compact_publication.RAW_SHA256,
            "artifact_sha256": compact_publication.ARTIFACT_SHA256,
            "iterations": compact_publication.EXPECTED_ITERATIONS,
            "nash_conv": compact_publication.EXPECTED_NASH_CONV,
            "quality_target_met": True,
        }
        report = {
            "schema_version": trainer.ADAPTER,
            "status": "trained-policy-physically-verified",
            "case_id": case_id, "training_calls": 1,
            "admission": admission, "plan": trainer._plan_record(plan),
            "source_lf_sha256": source_map,
            "compact_historical_baseline": compact_baseline,
            "proof_receipt": {"status": "saved-reweight-publication-authenticated"},
            "physical_worlds_sha256": proof._digest(reweighted._world_rows(model.physical["worlds"])),
            "baseline_worlds_sha256": proof._digest(reweighted._world_rows(model.baseline["worlds"])),
            "maximum_world_path_states": 33, "census": _census(),
            "normalization": normalization, "raw_class_policy": raw_rows,
            "physical_policy": payload, "audit": audit,
            "preparation_forbidden_calls": _guard(),
            "diagnostic_forbidden_calls": _guard(),
            "quality_target": 0.005,
            "quality_target_met": Fraction(nash_conv) <= Fraction(1, 200),
        }
        report["artifact_sha256"] = proof._digest(report)
        return report, rows, model, audit, source_map

    @staticmethod
    def _write(path, report, *, compressed=False):
        raw = json.dumps(report, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode() + b"\n"
        path.write_bytes(gzip.compress(raw, mtime=0) if compressed else raw)
        return raw

    @contextmanager
    def _replay_patches(self, report, rows, model, audit, source_map):
        history = {"forbidden_production_calls": _guard()}
        source_reads = [source_map, source_map]
        snapshot = {"revision": "b" * 40, "status": "",
                    "source_lf_sha256": {"source.py": "c" * 64}}

        @contextmanager
        def no_oracle_guard():
            yield _guard()

        with patch.object(verifier.trainer, "source_hashes", side_effect=source_reads), \
             patch.object(verifier.evidence, "_source_snapshot",
                          side_effect=[snapshot, snapshot]), \
             patch.object(verifier.trainer, "admit_request", return_value=report["admission"]), \
             patch.object(verifier.trainer, "case_plan", return_value=trainer.case_plan(report["case_id"])), \
             patch.object(verifier.publication, "verify", return_value=report["proof_receipt"]), \
             patch.object(verifier.publication.old_publication, "authenticate", return_value=history), \
             patch.object(verifier.compact_publication, "_read", return_value=(None, b"raw", {
                 "physical_policy": {"iterations": 560, "nash_conv": 0.0028924005277596834},
                 "quality_target_met": True})), \
             patch.object(verifier.proof, "independent_guard", side_effect=lambda: no_oracle_guard()), \
             patch.object(verifier.reweighted, "build_model", return_value=model) as build, \
             patch.object(verifier.trainer, "_training_inputs",
                          return_value=(tuple(), _infos(), 33)), \
             patch.object(verifier.reweighted, "project_policy", return_value=rows), \
             patch.object(verifier.reweighted, "audit_policy", return_value=audit), \
             patch.object(cfr_plus, "train", side_effect=AssertionError("must not train")):
            yield build

    def test_valid_raw_and_gzip_reports_replay_without_training(self):
        report, rows, model, _, source_map = self._fixture()
        audit = copy.deepcopy(report["audit"])
        audit["independent_numeric_metrics"]["value_oop"] += 5e-12
        audit["maximum_numeric_gap"] = 5e-12
        with TemporaryDirectory() as directory:
            for compressed, name in ((False, "policy.json"), (True, "policy.json.gz")):
                with self.subTest(compressed=compressed):
                    path = Path(directory) / name
                    self._write(path, report, compressed=compressed)
                    with self._replay_patches(report, rows, model, audit, source_map) as build:
                        result = verifier.verify_saved(path)
                    build.assert_called_once()
                    self.assertEqual(result["training_calls"], 0)
                    self.assertEqual(result["case_id"], "uniform")
                    self.assertFalse(result["quality_target_met"])

    def test_resigned_exact_metric_tamper_rejects_before_model(self):
        report, _, _, _, source_map = self._fixture()
        report["audit"]["exact_metrics"]["nash_conv"] = "1/50"
        report["artifact_sha256"] = proof._digest(
            {key: value for key, value in report.items() if key != "artifact_sha256"})
        with TemporaryDirectory() as directory:
            path = Path(directory) / "exact-tamper.json"
            self._write(path, report)
            with patch.object(verifier.trainer, "source_hashes", return_value=source_map), \
                 patch.object(verifier.trainer, "admit_request", return_value=report["admission"]), \
                 patch.object(verifier.trainer, "case_plan", return_value=trainer.case_plan("uniform")), \
                 patch.object(verifier.reweighted, "build_model",
                              side_effect=AssertionError("audit before model")) as build:
                with self.assertRaisesRegex(ValueError, "identities"):
                    verifier.verify_saved(path)
            build.assert_not_called()

    def test_resigned_duplicate_rows_reject_before_publication_or_model(self):
        report, rows, model, audit, source_map = self._fixture()
        report["raw_class_policy"][1] = list(report["raw_class_policy"][0])
        report["artifact_sha256"] = proof._digest(
            {key: value for key, value in report.items() if key != "artifact_sha256"})
        with TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            self._write(path, report)
            with patch.object(verifier.trainer, "source_hashes", return_value=source_map), \
                 patch.object(verifier.trainer, "admit_request", return_value=report["admission"]), \
                 patch.object(verifier.trainer, "case_plan", return_value=trainer.case_plan("uniform")), \
                 patch.object(verifier.publication, "verify",
                              side_effect=AssertionError("must reject before proof auth")), \
                 patch.object(verifier.reweighted, "build_model",
                              side_effect=AssertionError("must reject before model")) as build:
                with self.assertRaisesRegex(ValueError, "Duplicate raw compact"):
                    verifier.verify_saved(path)
            build.assert_not_called()

    def test_resigned_boolean_probability_rejects_before_model(self):
        report, _, _, _, source_map = self._fixture()
        report["raw_class_policy"][0][3][0] = True
        report["artifact_sha256"] = proof._digest(
            {key: value for key, value in report.items() if key != "artifact_sha256"})
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bool.json"
            self._write(path, report)
            with patch.object(verifier.trainer, "source_hashes", return_value=source_map), \
                 patch.object(verifier.trainer, "admit_request", return_value=report["admission"]), \
                 patch.object(verifier.trainer, "case_plan", return_value=trainer.case_plan("uniform")), \
                 patch.object(verifier.reweighted, "build_model",
                              side_effect=AssertionError("must reject before model")) as build:
                with self.assertRaises(ValueError):
                    verifier.verify_saved(path)
            build.assert_not_called()

    def test_bad_checksum_duplicate_json_and_nonfinite_reject_early(self):
        report, _, _, _, _ = self._fixture()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            raw = self._write(path, report)
            path.write_bytes(raw.replace(b'"uniform"', b'"skew"', 1))
            with patch.object(verifier.reweighted, "build_model",
                              side_effect=AssertionError("checksum before model")) as build:
                with self.assertRaisesRegex(ValueError, "checksum"):
                    verifier.verify_saved(path)
            build.assert_not_called()
            path.write_text('{"schema_version":"x","schema_version":"y"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                verifier.verify_saved(path)
            path.write_text('{"value":NaN}', encoding="utf-8")
            with self.assertRaises(ValueError):
                verifier.verify_saved(path)

    def test_re_signed_wrong_case_plan_rejects_before_saved_proof_or_model(self):
        report, _, _, _, source_map = self._fixture()
        report["plan"]["exact_pair_priors"][0][2] += 1
        report["artifact_sha256"] = proof._digest(
            {key: value for key, value in report.items() if key != "artifact_sha256"})
        with TemporaryDirectory() as directory:
            path = Path(directory) / "wrong-plan.json"
            self._write(path, report)
            with patch.object(verifier.trainer, "source_hashes", return_value=source_map), \
                 patch.object(verifier.trainer, "admit_request", return_value=report["admission"]), \
                 patch.object(verifier.trainer, "case_plan", return_value=trainer.case_plan("uniform")), \
                 patch.object(verifier.publication, "verify",
                              side_effect=AssertionError("plan before proof")) as authenticate, \
                 patch.object(verifier.reweighted, "build_model",
                              side_effect=AssertionError("plan before model")) as build:
                with self.assertRaisesRegex(ValueError, "plan"):
                    verifier.verify_saved(path)
            authenticate.assert_not_called()
            build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
