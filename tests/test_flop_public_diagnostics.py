"""Opt-in public-batched flop diagnostics and bounded prefix admission."""
from contextlib import contextmanager
from itertools import product
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from pokerlab import preflop_delayed_cfrplus as delayed_cfrplus
from pokerlab import postflop_solver as solver
from pokerlab import preflop_delayed_cfrplus as delayed_kernel
from pokerlab.public_diagnostics import evaluate_profile
from pokerlab.river_config import RiverConfig
from pokerlab.river_tree import _Terminal
from scripts import flop_multistreet_validation as independent
from scripts.benchmark_weighted_full_deck_flop import independent_guard as legacy_guard


@contextmanager
def independent_guard():
    # The original guard predates the isolated delayed trainer. Disable this
    # known production entry too when generating/replaying the independent game.
    with legacy_guard() as calls:
        key = "preflop_delayed_cfrplus.train_delayed_public_cfrplus"
        calls[key] = 0
        def forbidden(*args, **kwargs):
            calls[key] += 1
            raise AssertionError("Independent oracle called delayed production training")
        with patch.object(delayed_kernel,"train_delayed_public_cfrplus",side_effect=forbidden):
            yield calls


BOARD = "2c3d4h"
OOP = "AsAd:1,QsQd:0.5"
IP = "AsKh:0.25,KsKd:1"
OOP_HANDS = (("AdAs", "1"), ("QdQs", "1/2"))
IP_HANDS = (("AsKh", "1/4"), ("KdKs", "1"))
BASE = {"pot": 10, "effective_stack": 5, "bet_sizes": [0.5],
        "raise_sizes": [], "max_raises": 0, "include_all_in": False}


def _assert_profiles_match(test, reference, candidate, tolerance=1e-8):
    test.assertEqual(len(reference["strategy"]), len(candidate["strategy"]))
    for expected, got in zip(reference["strategy"], candidate["strategy"]):
        test.assertEqual({key: value for key, value in expected.items() if key != "actions"},
                         {key: value for key, value in got.items() if key != "actions"})
        test.assertEqual(len(expected["actions"]), len(got["actions"]))
        for left, right in zip(expected["actions"], got["actions"]):
            test.assertEqual({key: value for key, value in left.items() if key != "probability"},
                             {key: value for key, value in right.items() if key != "probability"})
            test.assertAlmostEqual(left["probability"], right["probability"], delta=tolerance)
    metrics = ("value_oop", "value_ip", "oop_best_response_value",
               "ip_best_response_value", "oop_best_response_gain",
               "ip_best_response_gain", "nash_conv", "exploitability")
    for key in metrics:
        test.assertAlmostEqual(reference[key], candidate[key], delta=tolerance, msg=key)


class _Chance:
    def __init__(self, branches, card_index):
        self.branches = branches
        self.card_index = card_index


class _Decision:
    def __init__(self, player, history, children):
        self.player = player
        self.history = tuple(history)
        self.children = tuple(children)
        self.actions = tuple(range(len(children)))


def _two_chance_toy():
    turns, rivers = ("2c", "3c"), ("4c", "5c")
    worlds = [
        (0, 0, 0.25, 1, turns[0], rivers[0]),
        (0, 0, 0.25, -1, turns[0], rivers[1]),
        (0, 0, 0.25, -1, turns[1], rivers[0]),
        (0, 0, 0.25, 1, turns[1], rivers[1]),
    ]
    root_branches = {}
    infos = {}
    for turn in turns:
        history = ("turn@" + turn,)
        action_children = []
        infos[(0, 0, history)] = 2
        for action, bet in (("check", False), ("bet", True)):
            river_branches = {}
            for river in rivers:
                ip_history = history + (action, "river@" + river)
                wager = 1.0 if bet else 0.0
                fold = _Terminal("fold", (wager, 0.0), 0)
                call = _Terminal("showdown", (wager + 1.0, wager + 1.0))
                river_branches[river] = _Decision(1, ip_history, (fold, call))
                infos[(1, 0, ip_history)] = 2
            action_children.append(_Chance(river_branches, 5))
        root_branches[turn] = _Decision(0, history, action_children)
    # Hand index 1 is explicitly in the action shape but is blocked from every
    # physical world. Omitting one such policy row must use zero-mass fallback.
    infos[(0, 1, ("turn@2c",))] = 2
    averages = {
        (0, 0, ("turn@2c",)): [0.6, 0.4],
        (0, 0, ("turn@3c",)): [0.3, 0.7],
    }
    for turn in turns:
        for action in ("check", "bet"):
            for river in rivers:
                key = (1, 0, ("turn@" + turn, action, "river@" + river))
                averages[key] = [0.25, 0.75] if river == "4c" else [0.65, 0.35]
    return _Chance(root_branches, 4), worlds, infos, averages


def _toy_payoff(node, sign, pot=2.0):
    if node.kind == "fold":
        return (1 if node.winner == 0 else -1) * (pot / 2 + min(node.contributions))
    return sign * (pot / 2 + min(node.contributions))


def _toy_value(root, worlds, policies, responder=None, choices=None):
    choices = choices or {}

    def visit(node, world):
        if isinstance(node, _Chance):
            return visit(node.branches[world[node.card_index]], world)
        if isinstance(node, _Terminal):
            return _toy_payoff(node, world[3])
        key = (node.player, world[node.player], node.history)
        if node.player == responder:
            return visit(node.children[choices[key]], world)
        if key in policies:
            return sum(probability * visit(child, world)
                       for probability, child in zip(policies[key], node.children))
        # Only the unreachable hand-index-1 fallback can be absent; no world
        # passed to this oracle has that hand.
        raise AssertionError("Independent toy encountered an absent reachable policy")

    return sum(world[2] * visit(root, world) for world in worlds)


def _toy_pure_br(root, worlds, policies, responder):
    keys = sorted(key for key in policies if key[0] == responder)
    best = float("-inf") if responder == 0 else float("inf")
    for actions in product(range(2), repeat=len(keys)):
        choices = dict(zip(keys, actions))
        value = _toy_value(root, worlds, policies, responder, choices)
        best = max(best, value) if responder == 0 else min(best, value)
    return best if responder == 0 else -best


class FlopPublicDiagnosticsTests(unittest.TestCase):
    def test_full_deck_flop_diagnostics_replay_both_trainers_and_delays(self):
        with independent_guard():
            oracle = independent.prepare_oracle(BOARD, OOP_HANDS, IP_HANDS, BASE)
        self.assertEqual(len(oracle["worlds"]), 5940)
        config = RiverConfig.from_dict(BASE)
        result_profiles = {}
        for traversal, delay in (("recursive", 0), ("public-batched", 0),
                                 ("recursive", 2), ("public-batched", 2)):
            with self.subTest(traversal=traversal, delay=delay):
                result = solver.solve_postflop(
                    BOARD, OOP, IP, config, iterations=10, algorithm="cfrplus",
                    traversal=traversal, diagnostics="public-batched",
                    averaging_delay=delay)
                with independent_guard() as calls:
                    checked = independent.replay(result, oracle, tolerance=1e-10)
                self.assertFalse(any(calls.values()))
                self.assertEqual(checked["checked_physical_worlds"], 5940)
                self.assertEqual(result["diagnostics_backend"], "public-batched-python")
                self.assertEqual(result["diagnostics_prefix_hand_edges"], 6078)
                self.assertEqual(result["diagnostics_prefix_edge_limit"], solver.MAX_PREFIX_EDGES)
                self.assertEqual(result["averaging_delay"] if delay else 0, delay)
                for gap in checked["scalar_absolute_gaps"].values():
                    self.assertLessEqual(gap, 1e-10)
                result_profiles[(traversal, delay)] = result
        for delay in (0, 2):
            _assert_profiles_match(self, result_profiles[("recursive", delay)],
                                    result_profiles[("public-batched", delay)])

    def test_weighted_multistreet_trainers_match_recursive_diagnostics_and_oracle(self):
        config = {"pot": 10, "effective_stack": [12, 20], "bet_sizes": [0.5],
                  "raise_sizes": [0.5], "max_raises": 1, "include_all_in": True}
        turn = dict(config, bet_sizes=[0.75])
        river = dict(config, bet_sizes=[0.25])
        runouts = [("As", "5c"), ("5c", "As"), ("5c", "9h")]
        with independent_guard():
            oracle = independent.prepare_oracle(
                BOARD, OOP_HANDS, IP_HANDS, config,
                turn_config=turn, river_config=river, runouts=runouts)
        cases = (("vanilla", "recursive", 0), ("vanilla", "planned", 0),
                 ("vanilla", "public-batched", 0), ("dcfr", "planned", 0),
                 ("dcfr", "public-batched", 0), ("cfrplus", "recursive", 0),
                 ("cfrplus", "public-batched", 2))
        for algorithm, traversal, delay in cases:
            with self.subTest(algorithm=algorithm, traversal=traversal, delay=delay):
                kwargs = dict(turn_config=turn, river_config=river, runouts=runouts,
                              iterations=10, algorithm=algorithm, traversal=traversal)
                if delay:
                    kwargs["averaging_delay"] = delay
                diagnostic = solver.solve_postflop(
                    BOARD, OOP, IP, config, diagnostics="public-batched", **kwargs)
                recursive_diagnostic = solver.solve_postflop(
                    BOARD, OOP, IP, config, diagnostics="recursive", **kwargs)
                with independent_guard() as calls:
                    checked = independent.replay(diagnostic, oracle, tolerance=1e-10)
                self.assertFalse(any(calls.values()))
                self.assertLessEqual(max(checked["scalar_absolute_gaps"].values()), 1e-10)
                self.assertEqual(recursive_diagnostic["strategy"], diagnostic["strategy"])
                _assert_profiles_match(self, recursive_diagnostic, diagnostic)
                self.assertEqual(diagnostic["diagnostics_backend"], "public-batched-python")
                self.assertTrue(any(row["street"] == "flop" for row in diagnostic["strategy"]))
                self.assertTrue(any(row["street"] == "turn" for row in diagnostic["strategy"]))
                self.assertTrue(any(row["street"] == "river" for row in diagnostic["strategy"]))

    def test_flop_prefix_edge_boundary_precedes_tree_and_training(self):
        worlds = solver._enumerate_worlds(
            tuple(BOARD[i:i+2] for i in range(0, 6, 2)), OOP, IP,
            (("5c", "6c"), ("6c", "5c")), 10)[1]
        edge_count = solver._reserve_flop_diagnostic_prefix_edges(worlds)
        self.assertGreater(edge_count, 0)

        class ReachedTrainer(Exception):
            pass

        trainers = {
            "recursive": (solver, "train"),
            "planned": (solver, "train_planned"),
            "public-batched": (solver, "train_public_batched"),
            "cfrplus-recursive": (solver, "train_plus"),
            "cfrplus-delayed-public": (delayed_cfrplus, "train_delayed_public_cfrplus"),
        }
        cases = (
            ("vanilla", "recursive", 0, "recursive"),
            ("vanilla", "planned", 0, "planned"),
            ("vanilla", "public-batched", 0, "public-batched"),
            ("dcfr", "recursive", 0, "recursive"),
            ("dcfr", "planned", 0, "planned"),
            ("dcfr", "public-batched", 0, "public-batched"),
            ("cfrplus", "recursive", 0, "cfrplus-recursive"),
            ("cfrplus", "recursive", 2, "cfrplus-recursive"),
            ("cfrplus", "public-batched", 0, "public-batched"),
            ("cfrplus", "public-batched", 2, "cfrplus-delayed-public"),
        )
        for algorithm, traversal, delay, expected_trainer in cases:
            with self.subTest(algorithm=algorithm, traversal=traversal, delay=delay):
                kwargs = dict(iterations=10, algorithm=algorithm, traversal=traversal,
                              diagnostics="public-batched",
                              runouts=(("5c", "6c"), ("6c", "5c")))
                if delay:
                    kwargs["averaging_delay"] = delay

                # The one-below cap must reject before tree or any trainer path.
                with ExitStack() as stack:
                    tree = stack.enter_context(patch.object(
                        solver, "_build_postflop_tree",
                        side_effect=AssertionError("tree allocation before cap")))
                    for module, name in trainers.values():
                        stack.enter_context(patch.object(
                            module, name,
                            side_effect=AssertionError("trainer called before cap")))
                    stack.enter_context(patch.object(solver, "MAX_PREFIX_EDGES", edge_count - 1))
                    with self.assertRaisesRegex(ValueError, "prefix/hand edges"):
                        solver.solve_postflop(BOARD, OOP, IP, config=BASE, **kwargs)
                    tree.assert_not_called()

                # At the exact cap, the solver reaches the correct training
                # dispatch after constructing the public tree.
                with ExitStack() as stack:
                    mocks = {}
                    for label, (module, name) in trainers.items():
                        mocks[label] = stack.enter_context(patch.object(
                            module, name, side_effect=ReachedTrainer))
                    stack.enter_context(patch.object(solver, "MAX_PREFIX_EDGES", edge_count))
                    with self.assertRaises(ReachedTrainer):
                        solver.solve_postflop(BOARD, OOP, IP, config=BASE, **kwargs)
                    mocks[expected_trainer].assert_called_once()
                    for label, mock in mocks.items():
                        if label != expected_trainer:
                            mock.assert_not_called()

    def test_two_chance_toy_uses_visible_histories_and_exact_own_hand_responses(self):
        root, worlds, infos, averages = _two_chance_toy()
        # All OOP decisions occur after turn only; river is downstream of those
        # decisions and cannot enter their own-hand information keys.
        oop_histories = {key[2] for key in averages if key[0] == 0}
        self.assertEqual(oop_histories, {("turn@2c",), ("turn@3c",)})
        self.assertTrue(all(not any(token.startswith("river@") for token in history)
                            for history in oop_histories))

        missing_positive = dict(averages)
        del missing_positive[(0, 0, ("turn@2c",))]
        with self.assertRaisesRegex(ValueError, "missing a reachable"):
            evaluate_profile(root, worlds, missing_positive, pot=2, chance_type=_Chance)

        # Hand index 1 is blocked from all worlds. Its absent row at turn 3c
        # receives only the evaluator's zero-marginal uniform fallback.
        with_zero_fallback = dict(averages)
        with_zero_fallback[(0, 1, ("turn@2c",))] = [0.2, 0.8]
        with_zero_fallback[(0, 1, ("turn@3c",))] = [0.2, 0.8]
        omitted_zero_row = dict(with_zero_fallback)
        del omitted_zero_row[(0, 1, ("turn@3c",))]
        got = evaluate_profile(root, worlds, omitted_zero_row, pot=2, chance_type=_Chance)
        expected_profile = _toy_value(root, worlds, averages)
        expected_br0 = _toy_pure_br(root, worlds, averages, 0)
        expected_br1 = _toy_pure_br(root, worlds, averages, 1)
        self.assertAlmostEqual(expected_profile, 0.42, places=12)
        self.assertAlmostEqual(expected_br0, 0.55, places=12)
        self.assertAlmostEqual(expected_br1, 0.775, places=12)
        for actual, expected in zip(got, (expected_profile, expected_br0, expected_br1)):
            self.assertAlmostEqual(actual, expected, places=12)
        filled_zero_row = dict(omitted_zero_row)
        filled_zero_row[(0, 1, ("turn@3c",))] = [0.9, 0.1]
        self.assertEqual(evaluate_profile(root, worlds, filled_zero_row,
                                          pot=2, chance_type=_Chance), got)

    def test_flop_public_diagnostics_are_opt_in_and_target_stopping_scope_is_unchanged(self):
        kwargs = dict(runouts=(("5c", "6c"), ("6c", "5c")), iterations=10)
        default = solver.solve_postflop(BOARD, OOP, IP, config=BASE, **kwargs)
        explicit = solver.solve_postflop(BOARD, OOP, IP, config=BASE,
                                         diagnostics="recursive", **kwargs)
        self.assertEqual(default, explicit)
        self.assertNotIn("diagnostics_backend", default)

        with patch.object(solver, "_enumerate_worlds",
                          side_effect=AssertionError("target guard must precede enumeration")):
            with self.assertRaisesRegex(ValueError, "only for turn and river"):
                solver.solve_postflop(BOARD, OOP, IP, config=BASE, iterations=10,
                                      traversal="public-batched", target_exploitability=0.01)
        with patch.object(solver, "_enumerate_worlds",
                          side_effect=AssertionError("planned CFR+ guard must precede enumeration")):
            with self.assertRaisesRegex(ValueError, "requires recursive"):
                solver.solve_postflop(BOARD, OOP, IP, config=BASE, iterations=10,
                                      algorithm="cfrplus", traversal="planned",
                                      diagnostics="public-batched")


if __name__ == "__main__":
    unittest.main()
