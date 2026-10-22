"""Fast synthetic orchestration checks for positive-prior class CFR+."""
from contextlib import contextmanager
from fractions import Fraction
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import flop_class_compact_budget as budget
from scripts import flop_class_reweight_cfrplus as trainer
from scripts import flop_class_reweight_proof as reweighted
from scripts import flop_multistreet_validation as physical
from scripts import flop_public_classes as proof


def _census():
    return {
        "compact_public_states": 1001, "compact_decisions": 316,
        "compact_chance_nodes": 58, "compact_terminals": 627,
        "physical_policy_rows": 16912, "compact_policy_rows": 466,
        "physical_action_slots": 33824, "compact_action_slots": 932,
        "compact_worlds": 126, "turn_classes": 11, "river_signatures": 19,
    }


def _infos_and_rows():
    infos = {}
    for i in range(232):
        history = () if i == 0 else (f"oop-{i}",)
        infos[(0, "AdAs", history)] = 2
    for i in range(234):
        infos[(1, "KdKs", (f"ip-{i}",))] = 2
    return infos


def _historical_guard():
    return {f"authority-{i}": 0 for i in range(41)}


class ReweightedCFRPlusTests(unittest.TestCase):
    def test_case_plans_keep_global_blocker_conditioning(self):
        baseline = trainer.case_plan("baseline")
        uniform = trainer.case_plan("uniform")
        skew = trainer.case_plan("skew")
        self.assertEqual(baseline.global_blocker_normalizer, Fraction(13, 8))
        self.assertEqual(tuple(p for _, _, p in baseline.exact_pair_priors),
                         (Fraction(8, 13), Fraction(1, 13), Fraction(4, 13)))
        self.assertEqual(tuple(p for _, _, p in uniform.exact_pair_priors),
                         (Fraction(1, 3),) * 3)
        self.assertEqual(tuple(p for _, _, p in skew.exact_pair_priors),
                         (Fraction(4, 9), Fraction(4, 9), Fraction(1, 9)))

    def test_invalid_case_and_iterations_stop_before_budget_or_authentication(self):
        with patch.object(trainer.budget, "admit_compact_request",
                          side_effect=AssertionError("budget")) as admit, \
             patch.object(trainer, "source_hashes", side_effect=AssertionError("sources")), \
             patch.object(trainer.publication, "verify", side_effect=AssertionError("saved auth")), \
             patch.object(trainer.reweighted, "build_model", side_effect=AssertionError("ranking")), \
             patch.object(trainer.cfr_plus, "train", side_effect=AssertionError("training")):
            for case_id, iterations in (("baseline", True), ("uniform", 0),
                                        ("skew", 561), ("Baseline", 560),
                                        (None, 560), ("uniform", 560.0)):
                with self.subTest(case=case_id, iterations=iterations), \
                     self.assertRaises(ValueError):
                    trainer.solve_reweighted(case_id, iterations)
        admit.assert_not_called()

    def test_admission_exposes_direct_sum_and_two_oracle_census(self):
        forecast = budget.admit_compact_request(560)
        admission = trainer.admit_request("uniform", 560)
        self.assertEqual(admission["total_admitted_work"], forecast["total_admitted_work"] + 126)
        self.assertEqual(admission["total_training_work"], forecast["total_training_work"])
        self.assertEqual(admission["fixed_setup_and_output_work"],
                         forecast["fixed_setup_and_output_work"] + 126)
        self.assertEqual(admission["weighted_setup_work"],
                         {"binary64_mass_sum_world_entries": 126})
        self.assertEqual(admission["combined_logical_work_cap"], 76_000_000)
        self.assertEqual(admission["weighted_proof_preparation_census"]["physical_oracle_builds"], 2)
        self.assertEqual(admission["weighted_proof_preparation_census"]["physical_world_rows_enumerated_total"],
                         11_880)
        self.assertEqual(admission["averaging_delay"], 0)

    def test_training_inputs_validate_weighted_model_and_exact_positive_mass(self):
        infos = _infos_and_rows()
        actions = ({"name": "check"}, {"name": "bet"})
        root = physical._Decision((), 0, "flop", ("2c", "3d", "4h"), actions,
                                  (physical._Terminal(("a",), "fold", (5, 5), 0),
                                   physical._Terminal(("b",), "fold", (5, 5), 1)))
        class_rows = {key: root for key in infos}
        worlds = tuple(("AdAs", "KdKs", Fraction(1, 126), 1,
                        ("2c", "3d", "4h", "5c", "6d")) for _ in range(126))
        model = SimpleNamespace(root=root, worlds=worlds, census=_census())
        with patch.object(trainer.reweighted, "validate_model", return_value=_census()) as validate, \
             patch.object(trainer.reweighted, "_class_rows", return_value=class_rows), \
             patch.object(trainer.proof, "validate_model",
                          side_effect=AssertionError("old fixed-prior validator")), \
             patch.object(trainer.budget, "validate_observed_dimensions",
                          wraps=budget.validate_observed_dimensions) as dimensions:
            compact_worlds, observed_infos, maximum = trainer._training_inputs(model)
        validate.assert_called_once_with(model)
        dimensions.assert_called_once()
        self.assertEqual(observed_infos, {key: 2 for key in infos})
        self.assertEqual(len(compact_worlds), 126)
        self.assertEqual(maximum, 3)
        self.assertEqual(sum((Fraction.from_float(row[2]) for row in compact_worlds), Fraction()),
                         Fraction(126) * Fraction.from_float(1 / 126))

    def test_training_inputs_rejects_zeroed_or_nonunit_joint_mass_before_train(self):
        infos = _infos_and_rows()
        actions = ({"name": "check"}, {"name": "bet"})
        root = physical._Decision((), 0, "flop", ("2c", "3d", "4h"), actions,
                                  (physical._Terminal(("a",), "fold", (5, 5), 0),
                                   physical._Terminal(("b",), "fold", (5, 5), 1)))
        model = SimpleNamespace(root=root, worlds=tuple(
            ("AdAs", "KdKs", Fraction(1, 125), 1, ("2c", "3d", "4h", "5c", "6d"))
            for _ in range(126)), census=_census())
        with patch.object(trainer.reweighted, "validate_model", return_value=_census()), \
             patch.object(trainer.reweighted, "_class_rows", return_value={key: root for key in infos}), \
             patch.object(trainer.budget, "validate_observed_dimensions",
                          side_effect=AssertionError("must fail mass first")), \
             patch.object(trainer.cfr_plus, "train", side_effect=AssertionError("training")) as train:
            with self.assertRaisesRegex(ValueError, "joint-world masses"):
                trainer._training_inputs(model)
        train.assert_not_called()

    @staticmethod
    @contextmanager
    def _guard():
        yield _historical_guard()

    def _fake_model(self, plan):
        infos = _infos_and_rows()
        raw = {key: [0.5, 0.5] for key in infos}
        world = ("AdAs", "KdKs", Fraction(1), 1,
                 ("2c", "3d", "4h", "5c", "6d"))
        return (SimpleNamespace(plan=plan, root=object(), census=_census(),
                                physical={"worlds": (world,)},
                                baseline={"worlds": (world,)}), infos, raw)

    def test_solve_authenticates_before_weighted_build_then_trains_once_and_audits(self):
        plan = trainer.case_plan("uniform")
        model, infos, raw = self._fake_model(plan)
        events = []
        fake_audit = {
            "exact_metric_count": 8, "exact_metrics": {"nash_conv": "1/100"},
            "physical_rows_lifted": 16912, "class_rows": 466,
            "maximum_numeric_gap": 0.0, "physical_strategy_sha256": "a" * 64,
            "class_policy": [[0, "AdAs", [], [0.5, 0.5]]],
        }

        def record(name, value):
            events.append(name)
            return value

        sources = {"source.py": "b" * 64}
        compact_report = {"physical_policy": {"iterations": 560, "nash_conv": 0.00289},
                          "quality_target_met": True}
        guard = self._guard
        with patch.object(trainer, "admit_request", side_effect=lambda c, t: (
                events.append("admit") or {"case_id": c, "requested_iterations": t,
                    "compact_logical_admission": {"version": budget.VERSION},
                    "weighted_proof_preparation_census": {"physical_oracle_builds": 2}})), \
             patch.object(trainer, "case_plan", return_value=plan), \
             patch.object(trainer, "source_hashes", side_effect=[sources, sources]), \
             patch.object(trainer.publication, "verify",
                          side_effect=lambda: record("publication", {"status": "saved-authenticated"})), \
             patch.object(trainer.compact_publication, "_read",
                          side_effect=lambda _path: (None, b"raw", compact_report)), \
             patch.object(trainer.publication.old_publication, "authenticate",
                          return_value={"forbidden_production_calls": _historical_guard()}), \
             patch.object(trainer.proof, "independent_guard", side_effect=lambda: guard()), \
             patch.object(trainer.reweighted, "build_model",
                          side_effect=lambda got: record("build", model)) as build, \
             patch.object(trainer.proof, "build_model",
                          side_effect=AssertionError("old fixed-prior model")), \
             patch.object(trainer, "_training_inputs",
                          return_value=(tuple(("AdAs", "KdKs", 1 / 126, 1,
                                               ("2c", "3d", "4h", "5c", "6d"))
                                              for _ in range(126)), infos, 33)), \
             patch.object(trainer.cfr_plus, "train",
                          side_effect=lambda *a, **k: record("train", raw)) as train, \
             patch.object(trainer.reweighted, "lift_policy",
                          side_effect=lambda _rows, _model: {"strategy": []}), \
             patch.object(trainer.reweighted, "audit_policy", return_value=fake_audit) as audit:
            report = trainer.solve_reweighted("uniform", 560)

        self.assertEqual(events[:2], ["admit", "publication"])
        build.assert_called_once_with(plan)
        train.assert_called_once()
        audit.assert_called_once()
        self.assertEqual(report["case_id"], "uniform")
        self.assertEqual(report["plan"]["physical_world_forecast"], 5940)
        self.assertEqual(report["training_calls"], 1)
        self.assertIs(report["quality_target_met"], False)
        self.assertEqual(report["physical_worlds_sha256"], report["baseline_worlds_sha256"])
        self.assertEqual(report["artifact_sha256"], proof._digest(
            {key: value for key, value in report.items() if key != "artifact_sha256"}))

    def test_nonzero_or_incomplete_guard_rejects_before_training(self):
        plan = trainer.case_plan("baseline")
        model, infos, raw = self._fake_model(plan)

        @contextmanager
        def bad_guard():
            calls = _historical_guard()
            calls["authority-0"] = 1
            yield calls

        with patch.object(trainer, "admit_request", return_value={
                "compact_logical_admission": {"version": budget.VERSION}}), \
             patch.object(trainer, "case_plan", return_value=plan), \
             patch.object(trainer, "source_hashes", return_value={"s": "x"}), \
             patch.object(trainer.publication, "verify", return_value={"status": "ok"}), \
             patch.object(trainer.compact_publication, "_read",
                          return_value=(None, b"raw", {"physical_policy": {"iterations": 560,
                              "nash_conv": 0.1}, "quality_target_met": False})), \
             patch.object(trainer.publication.old_publication, "authenticate",
                          return_value={"forbidden_production_calls": _historical_guard()}), \
             patch.object(trainer.proof, "independent_guard", side_effect=lambda: bad_guard()), \
             patch.object(trainer.reweighted, "build_model", return_value=model), \
             patch.object(trainer, "_training_inputs", return_value=((), infos, 1)), \
             patch.object(trainer.cfr_plus, "train", side_effect=AssertionError("training")) as train:
            with self.assertRaisesRegex(ValueError, "incomplete or nonzero"):
                trainer.solve_reweighted("baseline", 560)
        train.assert_not_called()

    def test_trainer_row_mismatch_rejects_before_normalization_and_lift(self):
        plan = trainer.case_plan("skew")
        model, infos, _ = self._fake_model(plan)
        with patch.object(trainer, "admit_request", return_value={
                "compact_logical_admission": {"version": budget.VERSION}}), \
             patch.object(trainer, "case_plan", return_value=plan), \
             patch.object(trainer, "source_hashes", return_value={"s": "x"}), \
             patch.object(trainer.publication, "verify", return_value={"status": "ok"}), \
             patch.object(trainer.compact_publication, "_read",
                          return_value=(None, b"raw", {"physical_policy": {"iterations": 560,
                              "nash_conv": 0.1}, "quality_target_met": False})), \
             patch.object(trainer.publication.old_publication, "authenticate",
                          return_value={"forbidden_production_calls": _historical_guard()}), \
             patch.object(trainer.proof, "independent_guard", side_effect=lambda: self._guard()), \
             patch.object(trainer.reweighted, "build_model", return_value=model), \
             patch.object(trainer, "_training_inputs", return_value=((), infos, 1)), \
             patch.object(trainer.cfr_plus, "train", return_value={}), \
             patch.object(trainer.policy, "canonicalize_binary_rows",
                          side_effect=AssertionError("normalization")) as normalize, \
             patch.object(trainer.reweighted, "lift_policy",
                          side_effect=AssertionError("lift")) as lift:
            with self.assertRaisesRegex(ValueError, "omits or adds"):
                trainer.solve_reweighted("skew", 560)
        normalize.assert_not_called()
        lift.assert_not_called()


if __name__ == "__main__":
    unittest.main()
