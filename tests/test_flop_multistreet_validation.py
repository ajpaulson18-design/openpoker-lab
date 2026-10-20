"""Independent physical-world and policy replay for weighted flop starts."""

from copy import deepcopy
from fractions import Fraction
import unittest
from unittest.mock import patch

from pokerlab.river_config import RiverConfig
from pokerlab.postflop_solver import solve_postflop
from scripts import flop_multistreet_validation as independent


BOARD = ("2c", "3d", "4h")
OOP_HANDS = (("AsAd", "1"), ("QsQd", "1/2"))
IP_HANDS = (("AsKh", "1/4"), ("KsKd", "1"))
OOP_RANGE = "AsAd:1,QsQd:0.5"
IP_RANGE = "AsKh:0.25,KsKd:1"
BASE_CONFIG = {
    "pot": 10,
    "effective_stack": 5,
    "bet_sizes": [0.5],
    "raise_sizes": [],
    "max_raises": 0,
    "include_all_in": False,
}


def _production_calls_forbidden():
    """Patch solver authority points while the independent replay runs."""
    targets = (
        "pokerlab.cards.expand_range",
        "pokerlab.cards.rank_hand",
        "pokerlab.postflop_solver._enumerate_worlds",
        "pokerlab.postflop_solver._build_public_tree",
        "pokerlab.postflop_solver.train",
        "pokerlab.postflop_solver.train_planned",
        "pokerlab.postflop_solver.train_public_batched",
        "pokerlab.postflop_solver.evaluate",
        "pokerlab.postflop_solver.best_response",
        "pokerlab.public_diagnostics.evaluate_profile",
        "pokerlab.river_tree._build_tree",
        "pokerlab.river_tree._terminal_value",
    )
    stack = []
    for target in targets:
        stack.append(patch(target, side_effect=AssertionError(
            f"independent validation called production helper {target}")))
    return stack


class FlopMultistreetValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._production_guard = _production_calls_forbidden()
        for item in cls._production_guard:
            item.start()
        try:
            with patch.object(independent, 'independent_rank', wraps=independent.independent_rank) as rank:
                cls.oracle = independent.prepare_oracle(
                    BOARD, OOP_HANDS, IP_HANDS, BASE_CONFIG)
                cls.observed_reference_rank_calls = rank.call_count
        finally:
            for item in reversed(cls._production_guard):
                item.stop()

    def _replay_under_production_guard(self, result, oracle=None):
        managers = _production_calls_forbidden()
        for item in managers:
            item.start()
        try:
            return independent.replay(result, oracle or self.oracle)
        finally:
            for item in reversed(managers):
                item.stop()

    def _solve_full(self, algorithm, traversal):
        return solve_postflop(
            "".join(BOARD), OOP_RANGE, IP_RANGE,
            RiverConfig.from_dict(BASE_CONFIG), iterations=10,
            algorithm=algorithm, traversal=traversal,
        )

    def test_independent_full_deck_counts_and_global_blocker_priors(self):
        oracle = self.oracle
        self.assertEqual(oracle["normalizer"], Fraction(13, 8))
        self.assertEqual(oracle["compatible_pairs"], 3)
        self.assertEqual(oracle["physical_worlds"], 5_940)
        self.assertEqual(len(oracle["worlds"]), 5_940)
        self.assertEqual(oracle["runout_mode"], "full-deck")
        self.assertEqual(oracle["public_nodes"], 9_512)
        self.assertEqual(oracle["public_states"], 30_812)
        self.assertEqual(oracle["chance_nodes"], 248)
        self.assertEqual(oracle["terminal_nodes"], 21_052)
        self.assertEqual(oracle["source_counters"]["rank_hand_calls"], self.observed_reference_rank_calls)
        self.assertGreater(oracle["source_counters"]["rank_hand_calls"], 0)
        self.assertLessEqual(oracle["source_counters"]["rank_hand_calls"], 11_880)

        priors = {(row["oop_hand"], row["ip_hand"]):
                  (row["pair_probability_fraction"], row["pair_probability"])
                  for row in oracle["counts"]}
        self.assertEqual(priors, {
            ("AdAs", "KdKs"): ("8/13", float(Fraction(8, 13))),
            ("QdQs", "AsKh"): ("1/13", float(Fraction(1, 13))),
            ("QdQs", "KdKs"): ("4/13", float(Fraction(4, 13))),
        })
        self.assertTrue(all(row["ordered_outcomes"] == 1_980
                            and row["wins"] + row["ties"] + row["losses"] == 1_980
                            for row in oracle["counts"]))
        self.assertEqual(sum((world[2] for world in oracle["worlds"]), Fraction(0)),
                         Fraction(1))

    def test_full_deck_vanilla_planned_and_dcfr_recursive_replay(self):
        for algorithm, traversal in (("vanilla", "planned"), ("dcfr", "recursive")):
            with self.subTest(algorithm=algorithm, traversal=traversal):
                result = self._solve_full(algorithm, traversal)
                self.assertEqual(result["worlds"], 5_940)
                self.assertEqual(result["deals"], 3)
                self.assertEqual(result["runout_mode"], "full-deck")
                self.assertEqual(result["execution_backend"], f"{traversal}-python")
                self.assertEqual(result["public_nodes"], self.oracle["public_nodes"])
                replayed = self._replay_under_production_guard(result)
                for metric in ("value_oop", "value_ip", "oop_best_response_value",
                               "ip_best_response_value", "oop_best_response_gain",
                               "ip_best_response_gain", "nash_conv", "exploitability"):
                    self.assertAlmostEqual(result[metric], replayed[metric], places=10,
                                           msg=metric)
                    self.assertLessEqual(replayed["scalar_absolute_gaps"][metric], 1e-10)
                self.assertEqual(replayed["checked_physical_worlds"], 5_940)
                self.assertEqual(replayed["checked_information_sets"], result["info_sets"])

    def test_selected_ordered_runouts_multistreet_raise_and_asymmetric_refund(self):
        runouts = (("5c", "6c"), ("6c", "5c"))
        config = {
            "pot": 10,
            "effective_stack": [12, 20],
            "bet_sizes": [0.5],
            "raise_sizes": [0.5],
            "max_raises": 1,
            "include_all_in": True,
        }
        turn = {**config, "bet_sizes": [0.75]}
        river = {**config, "bet_sizes": [0.25]}
        oracle = independent.prepare_oracle(
            BOARD, OOP_HANDS, IP_HANDS, config, turn_config=turn,
            river_config=river, runouts=runouts)
        self.assertEqual(oracle["physical_worlds"], 6)
        self.assertEqual(oracle["runout_mode"], "conditioned-ordered-subset")
        self.assertEqual(oracle["runouts"], runouts)
        self.assertEqual(oracle["street_configs"]["turn"]["bet_sizes"], [0.75])
        self.assertEqual(oracle["street_configs"]["river"]["bet_sizes"], [0.25])

        result = solve_postflop(
            "".join(BOARD), OOP_RANGE, IP_RANGE, RiverConfig.from_dict(config),
            turn_config=turn, river_config=river, runouts=runouts,
            iterations=10, algorithm="vanilla", traversal="recursive")
        checked = independent.replay(result, oracle)
        self.assertEqual(checked["checked_physical_worlds"], 6)
        self.assertTrue(any(row["street"] == "turn" for row in result["strategy"]))
        self.assertTrue(any(row["street"] == "river" for row in result["strategy"]))
        self.assertTrue(any(action["name"] == "raise"
                            for row in result["strategy"] for action in row["actions"]))
        self.assertTrue(any(action["name"] == "all_in"
                            for row in result["strategy"] for action in row["actions"]))

    def test_replay_rejects_policy_and_visible_information_tampering(self):
        result = self._solve_full("vanilla", "recursive")
        self._replay_under_production_guard(result)

        mutations = []
        missing = deepcopy(result)
        missing["strategy"].pop()
        mutations.append(("missing row", missing))
        duplicate = deepcopy(result)
        duplicate["strategy"].append(deepcopy(duplicate["strategy"][0]))
        mutations.append(("duplicate row", duplicate))

        bad_amount = deepcopy(result)
        row = next(row for row in bad_amount["strategy"]
                   if any(action["name"] in ("bet", "all_in") for action in row["actions"]))
        action = next(action for action in row["actions"] if action["name"] in ("bet", "all_in"))
        action["amount"] += 0.25
        mutations.append(("action amount", bad_amount))

        bad_history = deepcopy(result)
        row = next(row for row in bad_history["strategy"] if row["history"])
        row["history"][-1] = "turn@5c"
        mutations.append(("history", bad_history))

        future_leak = deepcopy(result)
        row = next(row for row in future_leak["strategy"] if row["street"] == "flop")
        row["board"].extend(["5c", "6c"])
        mutations.append(("future board leak", future_leak))

        bad_probability = deepcopy(result)
        row = bad_probability["strategy"][0]
        row["actions"][0]["probability"] = 1.1
        mutations.append(("probability", bad_probability))

        for label, altered in mutations:
            with self.subTest(mutation=label), self.assertRaises(ValueError):
                independent.replay(altered, self.oracle)


class OracleInformationBoundaryTests(unittest.TestCase):
    def test_best_response_sums_hidden_future_before_maximizing(self):
        # Two-action abstract information game: showdown unit is 1 or 2.
        # The hidden sign is equally +/-; either fixed action has value zero,
        # while seeing the sign before choosing yields (2 - 1)/2 = .5.
        terminal_a = independent._Terminal((), "showdown", (0.0, 0.0))
        terminal_b = independent._Terminal((), "showdown", (1.0, 1.0))
        decision = independent._Decision((), 0, "flop", BOARD, ({}, {}),
                                         (terminal_a, terminal_b))
        worlds = (("AdAs", "KdKs", Fraction(1,2), 1, BOARD+("5c","6c")),
                  ("AdAs", "KdKs", Fraction(1,2), -1, BOARD+("7c","8c")))
        hidden = independent._best_response(decision, worlds, {}, 2.0, 0)
        exposed_turn = independent._Chance((), 3, "turn", {"5c":decision, "7c":decision})
        visible = independent._best_response(exposed_turn, worlds, {}, 2.0, 0)
        self.assertEqual(hidden, 0.0)
        self.assertEqual(visible, 0.5)
        same_turn_worlds = (worlds[0], worlds[1][:4]+(BOARD+("5c","8c"),))
        hidden_river = independent._Chance((), 3, "turn", {"5c":decision})
        exposed_river = independent._Chance((), 4, "river", {"6c":decision, "8c":decision})
        self.assertEqual(independent._best_response(hidden_river, same_turn_worlds, {}, 2.0, 0), 0.0)
        self.assertEqual(independent._best_response(exposed_river, same_turn_worlds, {}, 2.0, 0), 0.5)

    def test_invalid_literal_requests_reject_before_reference_ranking(self):
        cases = [
            {"board":"2c2c4h"},
            {"oop_hands":[["AsAs","1"]]},
            {"oop_hands":[["2cAs","1"],["As2c","1"]]},
            {"oop_hands":[["AsAd","0"]]},
            {"ip_hands":[["KsKd","1"],["JhJd","1"],["ThTd","1"]]},
            {"config":dict(BASE_CONFIG,max_raises=9)},
            {"turn_config":dict(BASE_CONFIG,pot=20)},
            {"runouts":[["5c","5c"]]},
        ]
        for change in cases:
            options = dict(board=BOARD,oop_hands=OOP_HANDS,ip_hands=IP_HANDS,config=BASE_CONFIG)
            options.update(change)
            with self.subTest(change=change), patch.object(independent,'independent_rank',
                    side_effect=AssertionError('ranked before validation')) as rank:
                with self.assertRaises(ValueError):
                    independent.prepare_oracle(**options)
                rank.assert_not_called()

    def test_binary64_call_targets_and_fresh_street_rounding(self):
        config = dict(pot=1.234567890123,effective_stack=[2.345678901234,3.456789012345],
                      bet_sizes=[.123456789123],raise_sizes=[.375],max_raises=1,include_all_in=True)
        runouts = (("5c","9h"),("9h","5c"))
        oracle = independent.prepare_oracle(BOARD,[["AsAd","1"]],[["KsKd","1"]],
                                             config,runouts=runouts)
        result = solve_postflop("".join(BOARD),"AsAd","KsKd",config=config,
                                runouts=runouts,iterations=10,algorithm="dcfr",traversal="planned")
        checked = independent.replay(result,oracle,tolerance=1e-10)
        self.assertLessEqual(max(checked['scalar_absolute_gaps'].values()),1e-10)
        calls = [a for row in result['strategy'] for a in row['actions'] if a['name']=='call']
        self.assertTrue(any(a['raise_to'] != round(a['raise_to'],9) for a in calls))
        self.assertTrue(any(row['street']=='river' for row in result['strategy']))

    def test_selected_blockers_condition_the_entire_joint_distribution(self):
        oracle = independent.prepare_oracle(
            BOARD, OOP_HANDS, IP_HANDS, BASE_CONFIG,
            runouts=(("As","5c"),("5c","As"),("5c","6c")))
        self.assertEqual(oracle["normalizer"], Fraction(7,5280))
        self.assertEqual(oracle["physical_worlds"], 5)
        actual = {(row["oop_hand"],row["ip_hand"]):row["pair_probability_fraction"]
                  for row in oracle["counts"]}
        self.assertEqual(actual, {("AdAs","KdKs"):"8/21",
                                  ("QdQs","AsKh"):"1/21",
                                  ("QdQs","KdKs"):"4/7"})


if __name__ == "__main__":
    unittest.main()
