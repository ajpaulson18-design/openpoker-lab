"""Poker-specific rational equilibrium anchors independent of CFR code."""
from fractions import Fraction as F
import unittest

from pokerlab.cfr import evaluate, best_response
from pokerlab.postflop_solver import _Chance, _node_key, solve_postflop
from pokerlab.public_diagnostics import evaluate_profile
from pokerlab.river_config import RiverConfig
from pokerlab.river_tree import _build_tree, _terminal_value
from scripts.river_analytical import equilibrium, metrics, serialized_profile


class PolarisedRiverAnalyticalTests(unittest.TestCase):
    def test_rational_equilibria_and_production_best_responses(self):
        # Different prior weights and bet-to-pot ratios, with rational anchors.
        for nuts in (F(1, 4), F(1, 2)):
            for bet in (50, 100, 200):
                with self.subTest(nuts=nuts, bet=bet):
                    oracle, value = equilibrium(nuts, 100, bet)
                    self.assertEqual(metrics(oracle, nuts, 100, bet), (value, value, -value))
                    config = RiverConfig(100, 500, (bet / 100,), (), 0, False)
                    root = _build_tree(config)[0]
                    worlds = [(0, 0, float(nuts), 1), (1, 0, float(1 - nuts), -1)]
                    profile = {}
                    for (player, hand, history), row in oracle.items():
                        history = tuple(f"bet@{bet}" if token == "bet" else token
                                        for token in history)
                        profile[(player, 0 if hand != "air" else 1, history)] = list(map(float, row))
                    payoff = lambda node, world: _terminal_value(node, world[3], 100)
                    candidates = (
                        evaluate_profile(root, worlds, profile, pot=100, chance_type=_Chance),
                        (evaluate(root, worlds, profile, payoff, _node_key),
                         best_response(0, root, worlds, profile, payoff, _node_key),
                         best_response(1, root, worlds, profile, payoff, _node_key)),
                    )
                    for candidate in candidates:
                        for got, expected in zip(candidate, (value, value, -value)):
                            self.assertAlmostEqual(got, float(expected), places=11)

    def test_trained_holdem_policy_is_verified_by_independent_pure_br_oracle(self):
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                result = solve_postflop(
                    "2c7d9hJsKd", "AsAh,3c4c", "QsQh",
                    RiverConfig(100, 500, (1.,), (), 0, False),
                    iterations=300, algorithm=algorithm,
                    traversal="public-batched", diagnostics="public-batched",
                )
                expected = metrics(serialized_profile(result))
                for field, value in zip(("value_oop", "oop_best_response_value",
                                         "ip_best_response_value"), expected):
                    self.assertAlmostEqual(result[field], float(value), places=10)
                self.assertAlmostEqual(result["nash_conv"], float(expected[1] + expected[2]), places=10)
                # The independently calculated game value is 25 chips. Bound
                # the approximate profile by its own unilateral response gaps.
                self.assertGreaterEqual(float(expected[1]) + 1e-10, 25)
                self.assertLessEqual(-float(expected[2]) - 1e-10, 25)
                self.assertLess(result["nash_conv"], 4)


if __name__ == "__main__":
    unittest.main()
