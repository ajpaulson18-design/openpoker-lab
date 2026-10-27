"""Independent Sol substitute review: payoff-sensitive occurrence identity."""
import math
import os
import subprocess
import unittest

EXE = os.environ.get("OPENPOKER_NATIVE_SELECTED_DAG_EXE")


def independent_cfr(iterations):
    # Complete little two-world game, duplicated response histories kept separate.
    # Terminal SB values depend only on its hidden card and explicit public terminal.
    a = (1, "A", ("showdown", -.5))
    b = (1, "B-C", ("showdown", -.5))
    c = (0, "B", (-.25, b))
    root = (0, "root", (a, c))
    nodes = (root, a, c, b)
    menus = {(p, hand, name): 2 for p, name, _ in nodes
             for hand in (range(2) if p == 0 else range(1))}
    regrets = {key: [0., 0.] for key in menus}
    totals = {key: [0., 0.] for key in menus}

    def matching():
        profile = {}
        for key, regret in regrets.items():
            positive = [max(0., x) for x in regret]
            total = math.fsum(positive)
            profile[key] = [x / total for x in positive] if total else [.5, .5]
        return profile

    def visit(node, private, profile, player, opponent_reach, delta):
        if not isinstance(node, tuple):
            utility = (1. if private == 0 else -1.) if node == "showdown" else node
            return (.5 * utility if player == 0 else -.5 * utility) * opponent_reach
        owner, name, children = node
        key = (owner, private if owner == 0 else 0, name)
        sigma = profile[key]
        values = [visit(child, private, profile, player,
                        opponent_reach * (sigma[i] if owner != player else 1.), delta)
                  for i, child in enumerate(children)]
        if owner == player:
            expected = math.fsum(sigma[i] * values[i] for i in range(2))
            for i in range(2):
                delta[key][i] += values[i] - expected
            return expected
        return sum(values)

    def average(node, private, profile, reach0, reach1, iteration):
        if not isinstance(node, tuple):
            return
        owner, name, children = node
        key = (owner, private if owner == 0 else 0, name)
        own = reach0 if owner == 0 else reach1
        for i, probability in enumerate(profile[key]):
            totals[key][i] += .5 * own * probability * iteration
            average(children[i], private, profile,
                    reach0 * (probability if owner == 0 else 1.),
                    reach1 * (probability if owner == 1 else 1.), iteration)

    profile = matching()
    for iteration in range(1, iterations + 1):
        for player in range(2):
            delta = {key: [0., 0.] for key in menus}
            for private in range(2):
                visit(root, private, profile, player, 1., delta)
            for key in menus:
                if key[0] == player:
                    regrets[key] = [max(0., regrets[key][i] + delta[key][i]) for i in range(2)]
            profile = matching()
        for private in range(2):
            average(root, private, profile, 1., 1., iteration)
    return {key: [x / math.fsum(values) for x in values] if math.fsum(values) else [.5, .5]
            for key, values in totals.items()}


class NativeDagPlanLifetimeReviewTests(unittest.TestCase):
    def test_prepare_and_failed_wire_release_operator_without_cyclic_gc(self):
        import gc
        import weakref
        from unittest.mock import patch
        from pokerlab.native_selected_dag import prepare, wire
        from tests.test_native_selected_dag import direct_prepared
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            def create_and_drop(fail):
                req, operator, view, infos = direct_prepared()
                marker = weakref.ref(operator)
                plan, _ = prepare(view, infos, req.iterations, operator)
                if fail:
                    with patch("pokerlab.native_selected_dag.MAX_INPUT_BYTES", 1):
                        with self.assertRaises(ValueError):
                            wire(plan)
                return marker
            for fail in (False, True):
                marker = create_and_drop(fail)
                self.assertIsNone(marker())
        finally:
            if was_enabled:
                gc.enable()


@unittest.skipUnless(EXE, "Compile the selected DAG helper for review controls")
class NativeDagReviewTests(unittest.TestCase):
    def test_repeated_context_with_different_opponent_reaches(self):
        # Nodes: showdown, BB-wins .5, BB-wins .25, shared BB response,
        # SB selection, SB root. No poker-rule claim is made for this protocol game.
        # Physical mask/rank records are intentionally explicit and dyadic probabilities.
        from pokerlab.cards import DECK
        bit = lambda card: 1 << DECK.index(card)
        mask = lambda cards: sum(bit(card) for card in cards)
        iterations = 30
        normalizer = math.fsum([1. / 34246080.] * 2)
        lines = ["OPENPOKER_SELECTED_DAG_V1",
                 f"6 6 6 6 6 12 2 1 1 4 {iterations} 1 5 9 6 10 8 12 12 0 8",
                 normalizer.hex(),
                 f"{mask(('As','Ad'))} 0x1p+0", f"{mask(('Qs','Qd'))} 0x1p+0",
                 f"{mask(('Ks','Kd'))} 0x1p+0",
                 f"{mask(('2c','3c','4c'))} {bit('7h')} {bit('8h')}",
                 # Structurally valid category-1 kicker codes; ordered SB win/loss.
                 f"{int('1e9870',16)} {int('1c9870',16)} {int('1d9870',16)}",
                 "0 -1 0 0 0 1 0x1p+0", "0 -1 0 0 0 0 -0x1p-1",
                 "0 -1 0 0 0 0 -0x1p-2", "1 1 0 2 0 -1 0x0.0p+0",
                 "1 0 2 2 0 -1 0x0.0p+0", "1 0 4 2 0 -1 0x0.0p+0",
                 "0 0", "1 0", "2 0", "3 0", "3 0", "4 0"]
        result = subprocess.run([EXE], input=("\n".join(lines)+"\n").encode(), capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        tokens = result.stdout.decode().split()
        values = [float.fromhex(x) for x in tokens[5:-2]]
        reference = independent_cfr(iterations)
        keys = [(0,0,"root"),(0,1,"root"),(1,0,"A"),(0,0,"B"),(0,1,"B"),(1,0,"B-C")]
        self.assertGreater(abs(reference[(1,0,"A")][0]-reference[(1,0,"B-C")][0]), 1e-4)
        for index, key in enumerate(keys):
            for action in range(2):
                self.assertAlmostEqual(values[2*index+action], reference[key][action], delta=1e-12)

    def test_globally_unsupported_board_and_pair_blocked_holes(self):
        from pokerlab.selected_operator_solver import solve_four_street_operator
        from tests.test_selected_operator_solver import CASE, request
        from scripts.preflop_validation import replay_policy, compare_result
        case = dict(CASE, sb_range="AsAd:1,AhAc:.25,2c3c:.5", bb_range="AsKd",
                    runouts=["2c3c4d7h8h", "As2d3h7s8c"])
        req = request(case)
        actual = solve_four_street_operator(req, strategy_storage="packed",
                    public_topology="direct", native_executable=EXE)
        expected = solve_four_street_operator(req, strategy_storage="packed", public_topology="direct")
        self.assertEqual(actual["strategy"], expected["strategy"])
        self.assertEqual(actual["native_training"]["selected_boards"], 2)
        self.assertEqual(actual["native_training"]["prefixes"], 4)
        numeric = replay_policy(actual, req.sb_range, req.bb_range,
                    config=case["config"], runouts=case["runouts"], flop_config=case["flop_config"])
        compare_result(actual, numeric)
