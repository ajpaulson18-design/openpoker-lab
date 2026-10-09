"""Rational equilibria and finite CFR checks at polarized bluff boundaries."""
from fractions import Fraction as F
import unittest

from pokerlab.matrix_free_river import solve_matrix_free_river
from pokerlab.river_config import RiverConfig
from scripts.river_analytical import equilibrium, metrics, serialized_profile


class RiverAnalyticalBoundaryTests(unittest.TestCase):
    def test_unsaturated_boundary_saturated_and_endpoint_anchors_are_exact(self):
        cases = (
            # Existing unsaturated anchors stay on the original formula.
            (F(1, 4), 100, 50),
            (F(1, 2), 100, 100),
            # Exact threshold: bluff probability reaches one and IP is indifferent.
            (F(3, 4), 100, 50),
            # Strictly saturated: every OOP hand bets and IP folds.
            (F(4, 5), 100, 100),
            (F(9, 10), 100, 200),
            # Pure-prior endpoints have exact degenerate equilibria.
            (F(0), 100, 100),
            (F(1), 100, 100),
        )
        for nuts, pot, bet in cases:
            with self.subTest(nuts=nuts, pot=pot, bet=bet):
                profile, value = equilibrium(nuts, pot, bet)
                self.assertEqual(metrics(profile, nuts, pot, bet),
                                 (value, value, -value))
                self.assertEqual(value,
                                 -F(pot, 2) if nuts == 0 else
                                 F(pot, 2) if nuts == 1 or
                                 nuts / (1 - nuts) * F(bet, pot + bet) >= 1 else
                                 (2 * nuts - 1) * F(pot, 2) +
                                 nuts * bet * pot / (pot + bet))

        boundary, boundary_value = equilibrium(F(3, 4), 100, 50)
        self.assertEqual(boundary[(1, "catcher", ("bet",))],
                         (F(1, 3), F(2, 3)))
        self.assertEqual(boundary_value, 50)
        saturated, saturated_value = equilibrium(F(4, 5), 100, 100)
        self.assertEqual(saturated[(0, "nuts", ())], (F(0), F(1)))
        self.assertEqual(saturated[(0, "air", ())], (F(0), F(1)))
        self.assertEqual(saturated[(1, "catcher", ("bet",))], (F(1), F(0)))
        self.assertEqual(saturated[(1, "catcher", ("check",))], (F(1), F(0)))
        self.assertEqual(saturated_value, 50)

    def test_high_nut_trained_policies_match_exact_best_responses_and_value_gaps(self):
        board = "2c7d9hJsKd"
        cases = (
            # Exact saturation boundary for B/P=1/2.
            (F(3, 4), 50),
            # Above the saturation boundary for B/P=1 and 2.
            (F(4, 5), 100),
            (F(9, 10), 200),
        )
        for nuts, bet in cases:
            with self.subTest(nuts=nuts, bet=bet):
                fraction = float(F(bet, 100))
                result = solve_matrix_free_river(
                    board, f"AsAh:{float(nuts)},3c4c:{float(1 - nuts)}",
                    "QsQh", RiverConfig(100, 500, (fraction,), (), 0, False),
                    iterations=1500, algorithm="cfrplus",
                )
                exact_value, exact_br_oop, exact_br_ip = metrics(
                    serialized_profile(result), nuts, 100, bet)
                anchor_profile, anchor_value = equilibrium(nuts, 100, bet)
                self.assertEqual(metrics(anchor_profile, nuts, 100, bet),
                                 (anchor_value, anchor_value, -anchor_value))
                self.assertAlmostEqual(result["value_oop"], float(exact_value), places=9)
                self.assertAlmostEqual(result["oop_best_response_value"],
                                       float(exact_br_oop), places=9)
                self.assertAlmostEqual(result["ip_best_response_value"],
                                       float(exact_br_ip), places=9)
                self.assertAlmostEqual(result["nash_conv"],
                                       float(exact_br_oop + exact_br_ip), places=9)
                self.assertLess(result["nash_conv"], 0.001)
                self.assertLess(abs(float(exact_value - anchor_value)), 0.001)


if __name__ == "__main__":
    unittest.main()
