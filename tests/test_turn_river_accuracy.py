import re
import unittest

from pokerlab.postflop_solver import solve_postflop
from pokerlab.river_config import RiverConfig
from pokerlab.turn_solver import solve_turn_river


def _river_raised_case():
    # A compact but nontrivial raise tree with asymmetric stacks and ranges.
    config = RiverConfig(pot=20, effective_stack=(35, 55),
                         bet_sizes=(0.5,), raise_sizes=(0.5,), max_raises=1,
                         include_all_in=True)
    return ("2c3c4d5h9s", "AsKd:0.5,QhQc:1", "JsJd:1,8c8d:0.75", config)


def _turn_complete_chance_case():
    # With one compatible private pair and no selected runouts, this turn
    # fixture traverses every legal river (44 physical cards).
    config = RiverConfig(pot=10, effective_stack=15, bet_sizes=(0.5,),
                         max_raises=0, include_all_in=False)
    return ("2c3c4d5h", "AsKd", "JsJd", config)


def _solve(case, *, iterations=20, target=0.0, check_interval=5,
           algorithm="vanilla", diagnostics="recursive"):
    board, oop, ip, config = case
    return solve_postflop(
        board, oop, ip, config, iterations=iterations,
        traversal="public-batched", algorithm=algorithm,
        diagnostics=diagnostics, target_exploitability=target,
        check_interval=check_interval,
    )


def _strategy_rows(result):
    return {(row["player"], row["hand"], tuple(row["board"]),
             tuple(row["history"])): row["actions"] for row in result["strategy"]}


class TurnRiverAccuracyTests(unittest.TestCase):
    def test_loose_target_stops_at_first_eligible_checkpoint_and_matches_fixed_policy(self):
        case = _river_raised_case()
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                early = _solve(case, iterations=25, target=1e9, check_interval=5,
                               algorithm=algorithm)
                self.assertEqual(early["iterations"], 10)
                self.assertEqual(early["convergence"]["stop_reason"], "target-reached")
                self.assertTrue(early["convergence"]["achieved"] <= 1e9)
                fixed = solve_postflop(case[0], case[1], case[2], case[3],
                                       iterations=early["iterations"],
                                       traversal="public-batched", algorithm=algorithm)
                self.assertEqual(_strategy_rows(early), _strategy_rows(fixed))
                for field in ("value_oop", "oop_best_response_value",
                              "ip_best_response_value", "nash_conv", "exploitability"):
                    self.assertAlmostEqual(early[field], fixed[field], places=12,
                                           msg=field)

    def test_zero_target_runs_budget_and_nondivisible_budget_has_final_checkpoint(self):
        result = _solve(_turn_complete_chance_case(), iterations=13,
                        target=0.0, check_interval=5)
        self.assertEqual(result["worlds"], 44)
        self.assertEqual(result["iterations"], 13)
        convergence = result["convergence"]
        self.assertEqual(convergence["stop_reason"], "iteration-limit")
        self.assertEqual([row["iteration"] for row in convergence["checkpoints"]],
                         [10, 13])
        self.assertFalse(convergence["achieved"] <= 0.0)

    def test_legacy_turn_facade_exposes_the_same_accuracy_stop(self):
        board, oop, ip, config = _turn_complete_chance_case()
        result = solve_turn_river(board, oop, ip, config, iterations=20,
                                  traversal="public-batched",
                                  target_exploitability=1e9, check_interval=10)
        self.assertEqual(result["solver_version"], "configured-turn-river-v3")
        self.assertEqual(result["iterations"], 10)
        self.assertEqual(result["convergence"]["stop_reason"], "target-reached")

    def test_checkpoint_metrics_are_exact_br_metrics_in_chip_units(self):
        result = _solve(_river_raised_case(), iterations=12,
                        target=0.0, check_interval=6)
        self.assertEqual([row["iteration"] for row in result["convergence"]["checkpoints"]],
                         [12])
        for checkpoint in result["convergence"]["checkpoints"]:
            self.assertAlmostEqual(checkpoint["nash_conv"],
                                   max(0.0, checkpoint["oop_best_response_value"] +
                                       checkpoint["ip_best_response_value"]), places=12)
            self.assertAlmostEqual(checkpoint["exploitability"],
                                   checkpoint["nash_conv"] / 2, places=12)
        final = result["convergence"]["checkpoints"][-1]
        self.assertAlmostEqual(result["value_oop"], final["value_oop"], places=12)
        self.assertAlmostEqual(result["exploitability"], final["exploitability"], places=12)
        doubled_config = RiverConfig(pot=40, effective_stack=(70, 110),
                                     bet_sizes=(0.5,), raise_sizes=(0.5,),
                                     max_raises=1, include_all_in=True)
        board, oop, ip, _ = _river_raised_case()
        doubled = solve_postflop(board, oop, ip, doubled_config, iterations=12,
                                 traversal="public-batched", target_exploitability=0.0,
                                 check_interval=12)
        base_rows, doubled_rows = _strategy_rows(result), _strategy_rows(doubled)
        normalize = lambda key: (key[0], key[1], key[2],
                                 tuple(re.sub(r"@\d+(?:\.\d+)?", "@amount", token)
                                       for token in key[3]))
        base_rows = {normalize(key): value for key, value in base_rows.items()}
        doubled_rows = {normalize(key): value for key, value in doubled_rows.items()}
        self.assertEqual(base_rows.keys(), doubled_rows.keys())
        for key in base_rows:
            self.assertEqual([action["name"] for action in base_rows[key]],
                             [action["name"] for action in doubled_rows[key]])
            for left, right in zip(base_rows[key], doubled_rows[key]):
                self.assertAlmostEqual(left["probability"], right["probability"],
                                       places=12)
        self.assertAlmostEqual(doubled["exploitability"],
                               2 * result["exploitability"], places=9)

    def test_recursive_diagnostics_match_public_batched_checkpoint(self):
        case = _river_raised_case()
        targeted = _solve(case, iterations=10, target=0.0, check_interval=10,
                          diagnostics="public-batched")
        reference = _solve(case, iterations=10, target=0.0, check_interval=10,
                           diagnostics="recursive")
        for field in ("value_oop", "oop_best_response_value",
                      "ip_best_response_value", "nash_conv", "exploitability"):
            self.assertAlmostEqual(targeted[field], reference[field], places=9,
                                   msg=field)

    def test_exact_threshold_reached_at_final_checkpoint(self):
        case = _river_raised_case()
        baseline = _solve(case, iterations=10, target=0.0, check_interval=10)
        threshold = baseline["convergence"]["achieved"]
        exact = _solve(case, iterations=10, target=threshold, check_interval=10)
        self.assertEqual(exact["convergence"]["stop_reason"], "target-reached")
        self.assertAlmostEqual(exact["convergence"]["achieved"], threshold, places=12)

    def test_nonfinite_checkpoint_diagnostics_cannot_certify_target(self):
        from unittest.mock import patch

        case = _river_raised_case()
        with patch("pokerlab.postflop_solver.evaluate_profile",
                   return_value=(float("nan"), 0.0, 0.0)):
            with self.assertRaisesRegex(ValueError, "finite"):
                _solve(case, iterations=10, target=1e9, check_interval=10,
                       diagnostics="public-batched")

    def test_impossible_best_response_values_cannot_certify_target(self):
        from unittest.mock import patch

        case = _river_raised_case()
        # A best response cannot perform worse than following the profile for
        # that player. These finite but invalid diagnostics must never certify.
        with patch("pokerlab.postflop_solver.evaluate_profile",
                   return_value=(0.0, -1.0, -1.0)):
            with self.assertRaisesRegex(RuntimeError, "Best-response"):
                _solve(case, iterations=10, target=1e9, check_interval=10,
                       diagnostics="public-batched")

    def test_defaults_are_unchanged_and_target_guards_reject_invalid_inputs(self):
        case = _river_raised_case()
        ordinary = solve_postflop(case[0], case[1], case[2], case[3], iterations=10)
        self.assertNotIn("convergence", ordinary)
        for target in (True, -1, float("nan"), float("inf"), -float("inf"), 10**1000):
            with self.subTest(target=target), self.assertRaises(ValueError):
                _solve(case, iterations=10, target=target)
        for interval in (True, 0, -1, 1.5):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                _solve(case, iterations=10, check_interval=interval)
        with self.assertRaisesRegex(ValueError, "turn and river"):
            solve_postflop("2c3c4d", "AsKd", "JsJd", case[3], iterations=10,
                           traversal="public-batched", target_exploitability=1)
        with self.assertRaisesRegex(ValueError, "requires public-batched"):
            solve_postflop(case[0], case[1], case[2], case[3], iterations=10,
                           traversal="recursive", target_exploitability=1)
        with self.assertRaisesRegex(ValueError, "requires public-batched"):
            solve_postflop(case[0], case[1], case[2], case[3], iterations=10,
                           traversal="planned", target_exploitability=1)


if __name__ == "__main__":
    unittest.main()
