"""Integration checks for optional postflop CFR+ and diagnostic backends."""
import unittest
from unittest.mock import patch

from pokerlab.postflop_solver import solve_postflop
from pokerlab.river_config import RiverConfig


def _turn_case():
    base = dict(pot=20, effective_stack=(35, 55), raise_sizes=(0.5,),
                max_raises=1, include_all_in=True)
    return dict(
        board="2c3c4d5h", oop="AsKd:0.5,QhQc:1",
        ip="JsJd:1,9s9d:0.75",
        config=RiverConfig(bet_sizes=(0.25, 0.75), **base),
        river_config=RiverConfig(bet_sizes=(0.5, 1.0), **base),
        runouts=("8c", "9c", "Ts"),
    )


def _river_case():
    return dict(
        board="2c3c4d5h9s", oop="AsKd:0.5,QhQc:1",
        ip="JsJd:1,8c8d:0.75",
        config=RiverConfig(pot=30, effective_stack=(45, 60),
                           bet_sizes=(0.33, 0.75), raise_sizes=(0.5,),
                           max_raises=1, include_all_in=True),
        runouts=None,
    )


def _solve(case, *, algorithm="cfrplus", traversal="recursive",
           diagnostics="recursive", iterations=10):
    return solve_postflop(
        case["board"], case["oop"], case["ip"], case["config"],
        river_config=case.get("river_config"), runouts=case["runouts"],
        iterations=iterations, algorithm=algorithm, traversal=traversal,
        diagnostics=diagnostics,
    )


def _assert_metrics_equal(test, left, right, places=10):
    for name in ("value_oop", "oop_best_response_value", "ip_best_response_value",
                 "nash_conv", "exploitability"):
        test.assertAlmostEqual(left[name], right[name], places=places, msg=name)


def _assert_profiles_equal(test, left, right, places=10):
    def rows(result):
        return {(row["player"], row["hand"], tuple(row["board"]), tuple(row["history"])):
                row["actions"] for row in result["strategy"]}
    left_rows, right_rows = rows(left), rows(right)
    test.assertEqual(left_rows.keys(), right_rows.keys())
    for key in left_rows:
        test.assertEqual([a["name"] for a in left_rows[key]],
                         [a["name"] for a in right_rows[key]], key)
        for actual, expected in zip(left_rows[key], right_rows[key]):
            test.assertAlmostEqual(actual["probability"], expected["probability"],
                                   places=places, msg=(key, actual["name"]))


class TurnRiverQualityIntegrationTests(unittest.TestCase):
    def test_diagnostics_backend_preserves_metrics_and_strategy(self):
        for case_name, case in (("turn", _turn_case()), ("river", _river_case())):
            for algorithm in ("vanilla", "dcfr", "cfrplus"):
                with self.subTest(case=case_name, algorithm=algorithm):
                    recursive = _solve(case, algorithm=algorithm, diagnostics="recursive")
                    public = _solve(case, algorithm=algorithm, diagnostics="public-batched")
                    self.assertEqual(public["diagnostics_backend"], "public-batched-python")
                    self.assertNotIn("diagnostics_backend", recursive)
                    _assert_metrics_equal(self, recursive, public)
                    _assert_profiles_equal(self, recursive, public)

    def test_cfrplus_recursive_and_public_training_match_weighted_raises_game(self):
        case = _turn_case()
        recursive = _solve(case, algorithm="cfrplus", traversal="recursive")
        public = _solve(case, algorithm="cfrplus", traversal="public-batched")
        self.assertEqual(public["execution_backend"], "public-batched-python")
        self.assertEqual(recursive["execution_backend"], "recursive-python")
        _assert_profiles_equal(self, recursive, public)
        _assert_metrics_equal(self, recursive, public)

    def test_unsupported_cfrplus_and_diagnostic_starts_are_rejected(self):
        flop = "Js8d4c"
        config = RiverConfig(pot=10, effective_stack=10, bet_sizes=(0.5,))
        common = (flop, "AsAh", "KcKd", config)
        with self.assertRaisesRegex(ValueError, "only for turn and river"):
            solve_postflop(*common, iterations=10, algorithm="cfrplus")
        with self.assertRaisesRegex(ValueError, "only for turn and river"):
            solve_postflop(*common, iterations=10, diagnostics="public-batched")
        with self.assertRaisesRegex(ValueError, "requires recursive or public-batched"):
            _solve(_turn_case(), algorithm="cfrplus", traversal="planned")

    def test_legacy_default_metadata_is_unchanged(self):
        case = _river_case()
        implicit = solve_postflop(case["board"], case["oop"], case["ip"],
                                 case["config"], iterations=10)
        explicit = _solve(case, algorithm="vanilla", traversal="recursive",
                          diagnostics="recursive")
        for field in ("method", "algorithm", "solver_version", "strategy_schema",
                      "execution_backend", "plan_operation_limit",
                      "public_batch_edge_limit"):
            self.assertEqual(implicit[field], explicit[field], field)
        self.assertNotIn("diagnostics_backend", implicit)
        self.assertNotIn("update_schedule", implicit)
        _assert_metrics_equal(self, implicit, explicit)
        _assert_profiles_equal(self, implicit, explicit)

    def test_cfrplus_guard_counts_three_world_node_passes(self):
        case = _turn_case()
        baseline = _solve(case, algorithm="vanilla")
        one_pass_work = baseline["worlds"] * baseline["world_traversal_nodes"] * 10
        self.assertGreater(one_pass_work, 0)
        with patch("pokerlab.postflop_solver._MAX_WORLD_NODE_WORK",
                   one_pass_work * 2):
            with self.assertRaisesRegex(ValueError, "30 million world-node iterations"):
                _solve(case, algorithm="cfrplus")


if __name__ == "__main__":
    unittest.main()
