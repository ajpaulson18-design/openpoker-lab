from contextlib import contextmanager
from fractions import Fraction
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from scripts import benchmark_flop_class_reweight as runner
from scripts import flop_class_reweight_plan as planning
from scripts import flop_class_reweight_proof as reweighted
from scripts import flop_multistreet_validation as physical
from scripts import flop_public_classes as proof
from scripts import verify_flop_public_classes_publication as old_publication


def _snapshot():
    return {"revision": "a" * 40, "status": "",
            "source_lf_sha256": {"synthetic.py": "b" * 64}}


def _audit(mode="check-call", *, full=False):
    policy = ([[index % 2, f"As{index:02d}", [], [0.5, 0.5]]
               for index in range(466)] if full else
              [[0, "AdAs", [], [1.0, 0.0]]])
    return {"exact_metrics": {"nash_conv": f"{runner.CONTROLS.index(mode)}"}, "exact_metric_count": 8,
            "physical_rows_lifted": 16912, "class_rows": 466,
            "physical_strategy_sha256": "strategy-digest",
            "class_policy": policy}


def _old_report():
    return {"training_calls": 0,
            "physical_worlds_sha256": "old-worlds",
            "physical_tree_sha256": "old-tree",
            "source_lf_sha256": {"old.py": "c" * 64},
            "forbidden_production_calls": {f"old.{i}": 0 for i in range(41)},
            "controls": {mode: _audit(mode, full=True) for mode in runner.CONTROLS}}


def _model(plan, baseline):
    world = ("AdAs", "KdKs", Fraction(1, 3), 1,
             ("2c", "3d", "4h", "5c", "6c"))
    oracle = {"worlds": (world,), "normalizer": Fraction(13, 8),
              "pair_counts": (), "pair_probabilities": {},
              "root": physical._Terminal((), "fold", (5.0, 5.0), 0)}
    return SimpleNamespace(plan=plan, baseline=baseline, physical=oracle,
                           partition={"synthetic": True}, census=dict(reweighted.EXPECTED_CENSUS))


def _guard():
    calls = {f"guarded.{index}": 0 for index in range(41)}
    @contextmanager
    def manager():
        yield calls
    return manager, calls


class ReweightRunnerTests(unittest.TestCase):
    def test_real_protocol_preflights_all_three_cases_without_preparation(self):
        spec = runner._protocol()
        with patch.object(physical, "prepare_oracle") as prepare:
            plans, forecast = runner._preflight(spec)
        self.assertEqual(tuple(case_id for case_id, _ in plans), runner.CASE_IDS)
        self.assertEqual(forecast["oracle_builds"], 4)
        self.assertEqual(forecast["enumerated_physical_world_rows"], 23760)
        self.assertEqual(forecast["control_audits"], 12)
        self.assertEqual([plan.global_blocker_normalizer for _, plan in plans],
                         [Fraction(13, 8), Fraction(3), Fraction(9)])
        prepare.assert_not_called()

    def test_real_protocol_mocked_preparation_completes_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence"
            baseline = {"worlds": (), "root": physical._Terminal((), "fold", (5, 5), 0)}
            guard, expected_calls = _guard()
            events = []
            actual_audit = _audit(full=True)
            real_preflight = runner._preflight
            def preflight(spec):
                events.append("preflight")
                return real_preflight(spec)
            def prepare(*args, **kwargs):
                events.append("oracle")
                return baseline
            def build(plan, *, baseline):
                events.append("model")
                return _model(plan, baseline)
            with patch.object(runner, "_source_snapshot", return_value=_snapshot()), \
                 patch.object(runner, "_preflight", side_effect=preflight) as preflight_mock, \
                 patch.object(old_publication, "authenticate", return_value=_old_report()), \
                 patch.object(proof, "independent_guard", guard), \
                 patch.object(physical, "prepare_oracle", side_effect=prepare), \
                 patch.object(proof, "_physical_anchor"), \
                 patch.object(reweighted, "build_model", side_effect=build), \
                 patch.object(reweighted, "control_policy",
                              side_effect=lambda model, mode: {"strategy": [], "mode": mode}), \
                 patch.object(reweighted, "audit_policy",
                              side_effect=lambda payload, model: _audit(payload["mode"], full=True)):
                report = runner.run(output)
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["training_calls"], 0)
            self.assertEqual(len(report["cases"]), 3)
            self.assertTrue(all(case["status"] == "complete" and
                                case["source_before"] == case["source_after"] and
                                len(case["controls"]) == 4 and
                                all(row["status"] == "complete" for row in case["controls"])
                                for case in report["cases"]))
            self.assertEqual(len(report["files"]), 15)
            self.assertEqual(events[0], "preflight")
            self.assertEqual(events, ["preflight", "oracle", "model", "model", "model"])
            self.assertEqual(preflight_mock.call_count, 1)
            self.assertEqual(report["forbidden_production_calls"], expected_calls)
            self.assertEqual(len(list(output.glob("*.json.gz"))), 15)
            saved = json.loads((output / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "complete")
            self.assertLess((output / "index.json").stat().st_size, runner.MAX_INDEX_BYTES)
            self.assertTrue(all("class_policy" not in control["audit_summary"]
                                for case in saved["cases"] for control in case["controls"]))

    def test_first_control_failure_is_retained_without_retry_or_later_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence"
            baseline = {"worlds": (), "root": physical._Terminal((), "fold", (5, 5), 0)}
            guard, _ = _guard()
            builds, controls = [], []
            with patch.object(runner, "_source_snapshot", return_value=_snapshot()), \
                 patch.object(old_publication, "authenticate", return_value=_old_report()), \
                 patch.object(proof, "independent_guard", guard), \
                 patch.object(physical, "prepare_oracle", return_value=baseline), \
                 patch.object(proof, "_physical_anchor"), \
                 patch.object(reweighted, "build_model",
                              side_effect=lambda plan, baseline: (builds.append(plan) or
                                                                 _model(plan, baseline))), \
                 patch.object(reweighted, "control_policy",
                              side_effect=lambda model, mode: (controls.append(mode) or
                                  (_ for _ in ()).throw(RuntimeError("synthetic failure")))):
                report = runner.run(output)
            self.assertEqual(report["status"], "error")
            self.assertEqual(len(builds), 1)
            self.assertEqual(controls, ["check-call"])
            self.assertEqual([row["status"] for row in report["cases"]],
                             ["error", "not-run", "not-run"])
            self.assertEqual(report["cases"][0]["controls"][0]["status"], "error")
            self.assertTrue(report["errors"][0]["traceback"])

    def test_source_drift_stops_remaining_cases_and_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence"
            baseline = {"worlds": (), "root": physical._Terminal((), "fold", (5, 5), 0)}
            guard, _ = _guard()
            original, changed = _snapshot(), _snapshot()
            changed = {**changed, "revision": "c" * 40}
            snapshots = [original] * 4 + [changed] * 20
            builds, controls = [], []
            with patch.object(runner, "_source_snapshot", side_effect=snapshots), \
                 patch.object(old_publication, "authenticate", return_value=_old_report()), \
                 patch.object(proof, "independent_guard", guard), \
                 patch.object(physical, "prepare_oracle", return_value=baseline), \
                 patch.object(proof, "_physical_anchor"), \
                 patch.object(reweighted, "build_model",
                              side_effect=lambda plan, baseline: (builds.append(plan) or
                                                                 _model(plan, baseline))), \
                 patch.object(reweighted, "control_policy",
                              side_effect=lambda model, mode: (controls.append(mode) or {"strategy": [], "mode": mode})), \
                 patch.object(reweighted, "audit_policy",
                              side_effect=lambda payload, model: _audit(payload["mode"], full=True)):
                report = runner.run(output)
            self.assertEqual(report["status"], "error")
            self.assertEqual(len(builds), 1)
            self.assertEqual(controls, ["check-call"])
            self.assertEqual([row["status"] for row in report["cases"]],
                             ["error", "not-run", "not-run"])
            self.assertTrue(any("snapshot changed" in row["error"]
                                for row in report["errors"]))
            self.assertIn("Source snapshot changed during control audit",
                          report["errors"][0]["error"])

    def test_incomplete_zero_guard_inventory_cannot_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence"
            baseline = {"worlds": (), "root": physical._Terminal((), "fold", (5, 5), 0)}
            @contextmanager
            def empty_guard():
                yield {}
            with patch.object(runner, "_source_snapshot", return_value=_snapshot()), \
                 patch.object(old_publication, "authenticate", return_value=_old_report()), \
                 patch.object(proof, "independent_guard", empty_guard), \
                 patch.object(physical, "prepare_oracle", return_value=baseline), \
                 patch.object(proof, "_physical_anchor"), \
                 patch.object(reweighted, "build_model",
                              side_effect=lambda plan, baseline: _model(plan, baseline)), \
                 patch.object(reweighted, "control_policy",
                              side_effect=lambda model, mode: {"strategy": [], "mode": mode}), \
                 patch.object(reweighted, "audit_policy",
                              side_effect=lambda payload, model: _audit(payload["mode"], full=True)):
                report = runner.run(output)
            self.assertEqual(report["status"], "error")
            self.assertEqual(report["forbidden_production_calls"], {})
            self.assertTrue(any(error["phase"] == "authority-guard" for error in report["errors"]))
            self.assertTrue(all(case["status"] == "complete" for case in report["cases"]))
            self.assertEqual([error["phase"] for error in report["errors"]],
                             ["authority-guard"])

    def test_existing_output_and_source_ancestor_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "exists"
            existing.mkdir()
            with self.assertRaisesRegex(ValueError, "new and outside"):
                runner.run(existing)
            with self.assertRaisesRegex(ValueError, "new and outside"):
                runner.run(runner.ROOT.parent)


if __name__ == "__main__":
    unittest.main()
