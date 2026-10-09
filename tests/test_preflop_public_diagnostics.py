import gc
import json
import unittest
import weakref
from pathlib import Path
from unittest.mock import patch

from scripts.preflop_validation import compare_result, replay_policy
from pokerlab.preflop_solver import solve_preflop


_FIXTURE = {
    "sb": "AsAd:1,AhAc:0.25",
    "bb": "KsKd:1,KcKh:0.5",
    "config": {"starting_stack": [4, 3], "raise_sizes": [0.5],
                "max_raises": 1, "include_all_in": False},
    "runouts": ("2c3c4d7h8h", "Kc2d3h7s8c", "Ac2c3h7s8c"),
    "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                    "max_raises": 0, "include_all_in": False},
}
_VALUE_FIELDS = ("value_sb", "value_bb", "sb_best_response_value",
                 "bb_best_response_value", "sb_gain", "bb_gain",
                 "nash_conv", "exploitability")


def _solve(fixture, **overrides):
    kwargs = {key: value for key, value in fixture.items()
              if key in {"config", "runouts", "flop_config", "turn_config", "river_config"}}
    kwargs.update(overrides)
    return solve_preflop(fixture["sb"], fixture["bb"], **kwargs)


def _assert_policies_equal(test, left, right):
    test.assertEqual(len(left), len(right))
    for a, b in zip(left, right):
        for field in ("player", "hand", "street", "revealed_board", "history"):
            test.assertEqual(a[field], b[field])
        test.assertEqual(len(a["actions"]), len(b["actions"]))
        for x, y in zip(a["actions"], b["actions"]):
            for field in ("name", "amount", "raise_to", "history_key"):
                test.assertEqual(x[field], y[field])
            test.assertAlmostEqual(x["probability"], y["probability"], delta=1e-10)


class PreflopPublicDiagnosticsTests(unittest.TestCase):
    def test_vector_diagnostics_match_reference_and_independent_replay(self):
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                recursive = _solve(_FIXTURE, iterations=10, algorithm=algorithm)
                vector = _solve(_FIXTURE, iterations=10, algorithm=algorithm,
                                diagnostics="public-batched")
                _assert_policies_equal(self, recursive["strategy"], vector["strategy"])
                for field in _VALUE_FIELDS:
                    self.assertAlmostEqual(recursive[field], vector[field], delta=1e-10)
                self.assertEqual(vector["diagnostics_backend"], "public-batched-python")
                self.assertEqual(vector["public_diagnostics_view_source"],
                                 "separate-evaluation-view")
                self.assertGreater(vector["public_diagnostics_view_pot_anchor"], 0)
                oracle = replay_policy(vector, _FIXTURE["sb"], _FIXTURE["bb"],
                                       **{k: v for k, v in _FIXTURE.items()
                                          if k not in ("sb", "bb")})
                compare_result(vector, oracle)

    def test_fractional_rounding_boundary_matches_configured_replay(self):
        path = Path(__file__).parents[1] / "benchmarks" / "preflop-rounding-boundary-v1.json"
        fixture = json.loads(path.read_text(encoding="utf-8"))
        kwargs = {key: value for key, value in fixture.items()
                  if key in {"config", "runouts", "flop_config", "turn_config", "river_config"}}
        recursive = solve_preflop(fixture["sb"], fixture["bb"], iterations=10, **kwargs)
        vector = solve_preflop(fixture["sb"], fixture["bb"], iterations=10,
                               diagnostics="public-batched", **kwargs)
        _assert_policies_equal(self, recursive["strategy"], vector["strategy"])
        for field in _VALUE_FIELDS:
            self.assertAlmostEqual(recursive[field], vector[field], delta=1e-10)
        replay = replay_policy(vector, fixture["sb"], fixture["bb"], **kwargs)
        compare_result(vector, replay)
        with self.assertRaises(AssertionError):
            replay_policy(vector, fixture["sb"], fixture["bb"],
                          monetary_mode="global-rational", **kwargs)

    def test_no_info_root_default_is_copy_free_and_explicit_vector_works(self):
        fixture = {"sb": "AsAd", "bb": "KsKd",
                   "config": {"starting_stack": [0.5, 20], "max_raises": 0},
                   "runouts": ("2c3c4d7h8h",)}
        import pokerlab.preflop_solver as solver
        with patch.object(solver, "_positive_pot_training_view",
                          side_effect=AssertionError("unexpected default copy")):
            plain = _solve(fixture, iterations=10)
        vector = _solve(fixture, iterations=10, diagnostics="public-batched")
        self.assertEqual(plain["strategy"], [])
        self.assertNotIn("diagnostics_backend", plain)
        self.assertEqual(vector["strategy"], [])
        self.assertEqual(vector["public_diagnostics_view_source"],
                         "no-information-set-evaluation-view")
        self.assertGreater(vector["public_diagnostics_view_pot_anchor"], 0)
        for field in _VALUE_FIELDS:
            self.assertAlmostEqual(plain[field], vector[field], delta=1e-12)
        self.assertAlmostEqual(vector["value_sb"], 0.5, delta=1e-12)

    def test_training_and_diagnostic_views_are_released_on_evaluator_failure(self):
        import pokerlab.preflop_solver as solver
        original = solver._positive_pot_training_view
        refs = []

        def tracked(root):
            view, anchor, states = original(root)
            refs.append(weakref.ref(view))
            return view, anchor, states

        for traversal in ("recursive", "public-batched"):
            refs.clear()
            with patch.object(solver, "_positive_pot_training_view", side_effect=tracked):
                with patch.object(solver, "evaluate_public_profile",
                                  side_effect=RuntimeError("diagnostic failure")):
                    with self.assertRaisesRegex(RuntimeError, "diagnostic failure"):
                        _solve(_FIXTURE, iterations=10, traversal=traversal,
                               diagnostics="public-batched")
            gc.collect()
            self.assertEqual(len(refs), 1)
            self.assertIsNone(refs[0]())

    def test_public_training_view_is_reused_for_diagnostics(self):
        import pokerlab.preflop_solver as solver
        original_build = solver._positive_pot_training_view
        original_evaluate = solver.evaluate_public_profile
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                built, evaluated = [], []

                def build(root):
                    view = original_build(root)
                    built.append(view[0])
                    return view

                def evaluate(root, *args, **kwargs):
                    evaluated.append(root)
                    return original_evaluate(root, *args, **kwargs)

                with patch.object(solver, "_positive_pot_training_view", side_effect=build):
                    with patch.object(solver, "evaluate_public_profile", side_effect=evaluate):
                        diagnostic = _solve(_FIXTURE, iterations=10, algorithm=algorithm,
                                             traversal="public-batched",
                                             diagnostics="public-batched")
                baseline = _solve(_FIXTURE, iterations=10, algorithm=algorithm,
                                  traversal="public-batched")
                self.assertEqual(len(built), 1)
                self.assertEqual(evaluated, built)
                self.assertEqual(diagnostic["public_diagnostics_view_source"],
                                 "training-view-reused")
                _assert_policies_equal(self, baseline["strategy"], diagnostic["strategy"])
                for field in _VALUE_FIELDS:
                    self.assertAlmostEqual(baseline[field], diagnostic[field], delta=1e-10)

    def test_planned_dcfr_uses_separate_vector_diagnostics_view(self):
        planned = _solve(_FIXTURE, iterations=10, algorithm="dcfr", traversal="planned",
                         diagnostics="public-batched")
        recursive = _solve(_FIXTURE, iterations=10, algorithm="dcfr", traversal="planned")
        _assert_policies_equal(self, recursive["strategy"], planned["strategy"])
        for field in _VALUE_FIELDS:
            self.assertAlmostEqual(recursive[field], planned[field], delta=1e-10)
        self.assertEqual(planned["public_diagnostics_view_source"],
                         "separate-evaluation-view")
        oracle = replay_policy(planned, _FIXTURE["sb"], _FIXTURE["bb"],
                               **{k: v for k, v in _FIXTURE.items()
                                  if k not in ("sb", "bb")})
        compare_result(planned, oracle)

    def test_hidden_future_outcome_preflop_response_anchor(self):
        fixture = {
            "sb": "AsAd", "bb": "KsKd",
            "config": {"starting_stack": [2, 1], "max_raises": 0},
            "runouts": ("2c3c4d7h8h", "Kc2d3h7s8c"),
        }
        result = _solve(fixture, iterations=10, diagnostics="public-batched")
        oracle = replay_policy(result, fixture["sb"], fixture["bb"],
                               **{k: v for k, v in fixture.items()
                                  if k not in ("sb", "bb")})
        compare_result(result, oracle)
        self.assertAlmostEqual(result["sb_best_response_value"], 0.0, delta=1e-12)
        sb_root_rows = [row for row in result["strategy"]
                        if row["player"] == "sb" and row["street"] == "preflop"]
        self.assertEqual(len(sb_root_rows), 1)
        self.assertEqual(sb_root_rows[0]["revealed_board"], [])
        self.assertEqual(sb_root_rows[0]["history"], [])
        self.assertFalse(any(row["street"] != "preflop" for row in result["strategy"]))

    def test_separate_diagnostics_view_obeys_shared_prefix_edge_guard(self):
        from pokerlab import public_diagnostics
        with patch.object(public_diagnostics.public_cfr, "MAX_PREFIX_EDGES", 1):
            with self.assertRaisesRegex(ValueError, "prefix/hand edges"):
                _solve(_FIXTURE, iterations=10, traversal="recursive",
                       diagnostics="public-batched")

    def test_invalid_diagnostics_rejected_before_world_enumeration(self):
        import pokerlab.preflop_solver as solver
        with patch.object(solver, "_enumerate_physical_worlds",
                          side_effect=AssertionError("work started")):
            with self.assertRaisesRegex(ValueError, "diagnostics"):
                solve_preflop("AsAd", "KsKd", runouts=("2c3c4d7h8h",),
                              iterations=10, diagnostics="unsupported")


if __name__ == "__main__":
    unittest.main()
