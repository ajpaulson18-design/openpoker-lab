"""Public API parity and independent replay checks for batched postflop CFR."""
import unittest

from pokerlab.postflop_solver import solve_postflop
from pokerlab.river_config import RiverConfig
from pokerlab.turn_solver import solve_turn_river
from test_postflop_solver import (
    _assert_results_equal, _physical_worlds, _serialized_oracle,
)


def _cases():
    base = dict(pot=20, effective_stack=(35, 55), raise_sizes=(0.5,),
                max_raises=1, include_all_in=True)
    flop = {
        "board": "Js8d4c",
        "oop": "AsAh:0.5,KsKh:1",
        "ip": "AcAd:1,KcKd:0.75",
        "config": RiverConfig(bet_sizes=(0.25,), **base),
        "turn_config": RiverConfig(bet_sizes=(0.5,), **base),
        "river_config": RiverConfig(bet_sizes=(0.75,), **base),
        "runouts": (("As", "3c"), ("3c", "As"), ("5h", "9s")),
    }
    turn = {
        "board": "2c3c4d5h",
        "oop": "AsKd:0.5,QhQc:1",
        "ip": "JsJd:1,9s9d:0.75",
        "config": RiverConfig(pot=30, effective_stack=(40, 65),
                               bet_sizes=(0.5,), raise_sizes=(0.5,),
                               max_raises=1, include_all_in=True),
        "river_config": RiverConfig(pot=30, effective_stack=(40, 65),
                                    bet_sizes=(0.75,), raise_sizes=(0.5,),
                                    max_raises=1, include_all_in=True),
        "runouts": ("8c", "9c"),
    }
    river = {
        "board": "2c3c4d5h9s",
        "oop": "AsKd:0.5,QhQc:1",
        "ip": "JsJd:1,8c8d:0.75",
        "config": RiverConfig(pot=60, effective_stack=(100, 80),
                               bet_sizes=(0.33,), raise_sizes=(0.5,),
                               max_raises=1, include_all_in=True),
        "runouts": None,
    }
    return (flop, turn, river)


def _solve(case, algorithm, traversal):
    return solve_postflop(
        case["board"], case["oop"], case["ip"], case["config"],
        turn_config=case.get("turn_config"),
        river_config=case.get("river_config"),
        runouts=case["runouts"], iterations=10, algorithm=algorithm,
        traversal=traversal,
    )


class PublicBatchedPostflopAPITests(unittest.TestCase):
    def test_flop_turn_river_match_recursive_profiles_and_exact_responses(self):
        for case_index, case in enumerate(_cases()):
            for algorithm in ("vanilla", "dcfr"):
                with self.subTest(case=case_index, algorithm=algorithm):
                    recursive = _solve(case, algorithm, "recursive")
                    batched = _solve(case, algorithm, "public-batched")
                    self.assertEqual(recursive["execution_backend"], "recursive-python")
                    self.assertEqual(batched["execution_backend"],
                                     "public-batched-python")
                    self.assertIsNone(recursive["public_batch_edge_limit"])
                    self.assertEqual(batched["public_batch_edge_limit"], 250_000)
                    _assert_results_equal(self, recursive, batched)

                    self.assertEqual(recursive["worlds"], batched["worlds"])
                    self.assertEqual(recursive["public_nodes"], batched["public_nodes"])
                    self.assertEqual(recursive["public_states"], batched["public_states"])
                    for output in (recursive, batched):
                        for key in ("value_oop", "oop_best_response_value",
                                    "ip_best_response_value", "nash_conv",
                                    "exploitability"):
                            self.assertTrue(abs(output[key]) < float("inf"), key)

                    if case_index == 0:
                        hands, worlds, _ = _physical_worlds(
                            case["board"], case["oop"], case["ip"], case["runouts"],
                        )
                        self.assertAlmostEqual(
                            batched["value_oop"],
                            _serialized_oracle(batched, worlds, hands), places=9,
                        )
                        self.assertAlmostEqual(
                            batched["oop_best_response_value"],
                            _serialized_oracle(batched, worlds, hands,
                                               responder=0), places=9,
                        )
                        self.assertAlmostEqual(
                            batched["ip_best_response_value"],
                            _serialized_oracle(batched, worlds, hands,
                                               responder=1), places=9,
                        )

    def test_turn_facade_exposes_public_batched_backend(self):
        case = _cases()[1]
        for algorithm in ("vanilla", "dcfr"):
            generic = _solve(case, algorithm, "public-batched")
            turn = solve_turn_river(
                case["board"], case["oop"], case["ip"], case["config"],
                river_config=case["river_config"], runouts=case["runouts"],
                iterations=10, algorithm=algorithm, traversal="public-batched",
            )
            self.assertEqual(turn["execution_backend"], "public-batched-python")
            _assert_results_equal(self, generic, turn)


if __name__ == "__main__":
    unittest.main()
