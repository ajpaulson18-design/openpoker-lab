"""A complete-board postflop game agrees with the established river API."""
import unittest

from pokerlab.postflop_solver import solve_postflop
from pokerlab.river_config import RiverConfig
from pokerlab.solver import solve


class PostflopRiverCompatibilityTests(unittest.TestCase):
    def test_complete_board_matches_configured_river_values_and_policies(self):
        config = RiverConfig(pot=20, effective_stack=(40, 25), bet_sizes=(.5, 1.),
                             raise_sizes=(.5,), max_raises=1, include_all_in=True)
        args = ("2c3d4h5s9c", "AsKd:0.5,QhQc:1", "JsJd:1,9s9d:0.75")
        for algorithm in ("vanilla", "dcfr"):
            reference = solve(*args, config=config, iterations=20, algorithm=algorithm)
            reference_rows = {(r["player"], r["hand"], tuple(r["history"])): r
                              for r in reference["strategy"]}
            for traversal in ("recursive", "planned"):
                with self.subTest(algorithm=algorithm, traversal=traversal):
                    actual = solve_postflop(*args, config=config, iterations=20,
                                           algorithm=algorithm, traversal=traversal)
                    self.assertEqual(actual["chance_nodes"], 0)
                    self.assertEqual(actual["runout_mode"], "none")
                    self.assertEqual(actual["runouts"], [])
                    self.assertEqual(actual["deals"], reference["deals"])
                    for field in ("value_oop", "oop_best_response_value",
                                  "ip_best_response_value", "nash_conv"):
                        self.assertAlmostEqual(actual[field], reference[field], places=12)
                    self.assertEqual(len(actual["strategy"]), len(reference_rows))
                    for row in actual["strategy"]:
                        self.assertEqual(row["street"], "river")
                        self.assertEqual(row["board"], actual["board"])
                        expected = reference_rows[(row["player"], row["hand"],
                                                   tuple(row["history"]))]
                        self.assertEqual(len(row["actions"]), len(expected["actions"]))
                        for a, b in zip(row["actions"], expected["actions"]):
                            for field in ("name", "amount", "raise_to", "history_key"):
                                self.assertEqual(a[field], b[field])
                            self.assertAlmostEqual(a["probability"], b["probability"], places=12)


if __name__ == "__main__":
    unittest.main()
