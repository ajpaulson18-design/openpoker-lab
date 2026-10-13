import copy
import json
import unittest
from pathlib import Path

from scripts.preflop_validation import compare_result, replay_policy
from pokerlab.preflop_solver import solve_preflop


_ROOT = Path(__file__).resolve().parents[1]
_BOUNDARY = json.loads(
    (_ROOT / "benchmarks/preflop-rounding-boundary-v1.json").read_text(
        encoding="utf-8"))


def _solve_boundary(algorithm, traversal):
    fixture = _BOUNDARY
    return solve_preflop(
        fixture["sb"], fixture["bb"], fixture["config"],
        runouts=fixture["runouts"], flop_config=fixture["flop_config"],
        turn_config=fixture["turn_config"], river_config=fixture["river_config"],
        iterations=10, algorithm=algorithm, traversal=traversal,
    )


def _replay_boundary(result, mode="configured"):
    fixture = _BOUNDARY
    return replay_policy(
        result, fixture["sb"], fixture["bb"], config=fixture["config"],
        runouts=fixture["runouts"], flop_config=fixture["flop_config"],
        turn_config=fixture["turn_config"], river_config=fixture["river_config"],
        monetary_mode=mode,
    )


class PreflopMonetaryReplayTests(unittest.TestCase):
    def test_boundary_fixture_replays_across_backends_and_keeps_rational_diagnostic(self):
        routes = (("vanilla", "recursive"), ("dcfr", "planned"),
                  ("vanilla", "public-batched"), ("cfrplus", "recursive"))
        representative = None
        for algorithm, traversal in routes:
            with self.subTest(algorithm=algorithm, traversal=traversal):
                result = _solve_boundary(algorithm, traversal)
                oracle = _replay_boundary(result)
                self.assertEqual(oracle["monetary_mode"], "configured")
                compare_result(result, oracle)
                representative = result

        self.assertIsNotNone(representative)
        with self.assertRaises(AssertionError) as diagnostic:
            _replay_boundary(representative, "global-rational")
        self.assertIn("raise@1.293095146", str(diagnostic.exception))
        self.assertIn("raise@1.293095147", str(diagnostic.exception))

        origin = 0.691357802
        boundary_pot = 1.382715604
        local_bet = round(0.123456789 * boundary_pot, 9)
        local_raise = round(local_bet + 0.25 * (boundary_pot + 2 * local_bet), 9)
        whole_raise = round(origin + local_raise, 9)
        self.assertEqual(local_bet, 0.170705629)
        self.assertEqual(local_raise, 0.601737344)
        self.assertEqual(whole_raise, 1.293095146)
        self.assertTrue(any(
            action["name"] == "raise" and action["raise_to"] == whole_raise and
            action["history_key"] == "raise@1.293095146"
            for row in representative["strategy"] for action in row["actions"]))

    def test_one_nanonunit_changes_to_history_target_or_amount_are_rejected(self):
        result = _solve_boundary("vanilla", "recursive")
        target_row = next(
            row for row in result["strategy"]
            if row["street"] == "flop" and
            "bet@0.862063431" in row["history"])
        target_action = next(
            action for action in target_row["actions"]
            if action["history_key"] == "raise@1.293095146")

        for field, update in (
                ("history_key", lambda value: "raise@1.293095147"),
                ("raise_to", lambda value: value + 1e-9),
                ("amount", lambda value: value + 1e-9)):
            with self.subTest(field=field):
                mutated = copy.deepcopy(result)
                row = next(row for row in mutated["strategy"]
                           if row["street"] == "flop" and
                           "bet@0.862063431" in row["history"])
                action = next(action for action in row["actions"]
                              if action["history_key"] == "raise@1.293095146")
                action[field] = update(action[field])
                with self.assertRaises(AssertionError):
                    _replay_boundary(mutated)

        self.assertEqual(target_action["raise_to"], 1.293095146)

    def test_local_origin_persists_and_coefficients_keep_more_than_nine_decimals(self):
        kwargs = {
            "config": {"small_blind": 0.5, "big_blind": 1,
                       "starting_stack": 10, "raise_sizes": [0.75, 0.25, 0.75],
                       "max_raises": 1, "include_all_in": False},
            "runouts": ("2c3c4d7h8h", "Kc2d3h7s8c"),
            "flop_config": {"bet_sizes": [0.5, 0.123456789123, 0.5],
                            "raise_sizes": [0.234567891234, 0.1,
                                            0.234567891234],
                            "max_raises": 1, "include_all_in": False},
            "turn_config": {"bet_sizes": [0.345678912345],
                            "raise_sizes": [0.123456789123],
                            "max_raises": 1, "include_all_in": False},
            "river_config": {"bet_sizes": [0.456789123456],
                             "raise_sizes": [0.345678912345],
                             "max_raises": 1, "include_all_in": False},
        }
        result = solve_preflop("AsAd", "KsKd", iterations=10, **kwargs)
        oracle = replay_policy(result, "AsAd", "KsKd", **kwargs,
                               monetary_mode="configured")
        compare_result(result, oracle)
        self.assertEqual(oracle["monetary_mode"], "configured")
        self.assertTrue(any(row["street"] == "turn" for row in result["strategy"]))
        self.assertTrue(any(row["street"] == "river" for row in result["strategy"]))
        # At the first flop, M=2.5 and the local pot is 5. A coefficient
        # truncated to nine decimals would change this quantized local target.
        expected_local = round(0.123456789123 * 5, 9)
        truncated_local = round(round(0.123456789123, 9) * 5, 9)
        self.assertNotEqual(expected_local, truncated_local)
        self.assertTrue(any(
            row["street"] == "flop" and
            action["name"] == "bet" and action["raise_to"] == 3.117283946
            for row in result["strategy"] for action in row["actions"]))
        initial_flop_row = next(
            row for row in result["strategy"]
            if row["street"] == "flop" and
            row["history"][-1].startswith("flop@") and
            row["history"][-2] == "call")
        bet_targets = [action["raise_to"] for action in initial_flop_row["actions"]
                       if action["name"] == "bet"]
        self.assertEqual(bet_targets, sorted(set(bet_targets)))
        for street, reveal, target in (
                ("turn", "turn@", 4.228394562),
                ("river", "river@", 4.783945617)):
            self.assertTrue(any(
                row["street"] == street and row["history"][-1].startswith(reveal) and
                row["history"][-3:-1] == ["check", "check"] and
                any(action["name"] == "bet" and action["raise_to"] == target
                    for action in row["actions"])
                for row in result["strategy"]))

    def test_unknown_monetary_mode_is_rejected(self):
        result = _solve_boundary("vanilla", "recursive")
        with self.assertRaisesRegex(ValueError, "monetary_mode"):
            _replay_boundary(result, "approximate")


if __name__ == "__main__":
    unittest.main()
