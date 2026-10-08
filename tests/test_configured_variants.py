"""Cross-backend and independent best-response checks for configured DCFR."""
import unittest

from pokerlab.equilibrium import InfoSet, solve_equilibrium
from pokerlab.river_config import RiverConfig
from pokerlab.solver import solve
from tests.test_configurable_solver import BOARD, public_result_oracle


class ConfiguredVariantTests(unittest.TestCase):
    def test_configured_single_bet_matches_optimized_kernel(self):
        for algorithm in ("vanilla", "dcfr"):
            args = (BOARD, "AsAh:0.3,KsKh", "AsAd:0.7,QcQd")
            fast = solve(*args, pot=80, bet=30, iterations=120, algorithm=algorithm)
            tree = solve(*args, iterations=120, algorithm=algorithm,
                         config=RiverConfig(80, 300, (.375,), (), 0, False))
            self.assertEqual(fast["backend"], "optimized-binary-tree")
            self.assertEqual(tree["backend"], "exact-public-tree")
            for side in ("oop", "ip"):
                for a, b in zip(fast[side], tree[side]):
                    self.assertEqual(a["hand"], b["hand"])
                    for key in set(a)-{"hand"}:
                        self.assertAlmostEqual(a[key], b[key], places=10)
            for key in ("value_oop", "nash_conv", "oop_best_response_value", "ip_best_response_value"):
                self.assertAlmostEqual(fast[key], tree[key], places=9)

    def test_dcfr_multisize_and_raise_gaps_match_exhaustive_pure_policy_oracle(self):
        oop, ip = "AsAh:0.5,KsKh:1", "AcAd:1,KcKd:0.75"
        for config in (RiverConfig(100, 300, (.33, .75), (), 0, False),
                       RiverConfig(100, 220, (.75,), (.75,), 1, False)):
            r = solve(BOARD, oop, ip, iterations=120, config=config, algorithm="dcfr")
            value, (br0, br1) = public_result_oracle(r, BOARD, oop, ip)
            self.assertAlmostEqual(r["value_oop"], value, places=8)
            self.assertAlmostEqual(r["oop_best_response_value"], br0, places=8)
            self.assertAlmostEqual(r["ip_best_response_value"], br1, places=8)
            self.assertAlmostEqual(r["nash_conv"], br0+br1, places=8)
            self.assertEqual(r["strategy_schema"], "river-strategy-v1")

    def test_legacy_serialized_strategy_preserves_unsized_information_set_queries(self):
        eq = solve_equilibrium(BOARD, "AsAh", "KcKd", iterations=50, algorithm="dcfr")
        self.assertIsNone(eq.config)
        bare = eq.strategy_at(InfoSet("ip", "KcKd", ("bet",)))
        token = next(a.history_key for a in eq.legal_actions(InfoSet("oop", "AsAh")) if a.name == "bet")
        sized = eq.strategy_at(InfoSet("ip", "KcKd", (token,)))
        self.assertEqual(bare, sized)

    def test_configured_dcfr_converges_and_is_deterministic(self):
        config = RiverConfig(100, 150, (.5,), (.5,), 1, False)
        args = (BOARD, "AsAh,KsKh", "AcAd,KcKd")
        low = solve(*args, config=config, iterations=10, algorithm="dcfr")
        high = solve(*args, config=config, iterations=1000, algorithm="dcfr")
        self.assertLess(high["nash_conv"], low["nash_conv"]/3)
        self.assertEqual(low, solve(*args, config=config, iterations=10, algorithm="dcfr"))

    def test_invalid_algorithm_fails_closed_on_configured_tree(self):
        with self.assertRaises(ValueError):
            solve(BOARD, "AsAh", "KcKd", config=RiverConfig(), algorithm="unknown")
