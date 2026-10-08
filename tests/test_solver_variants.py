"""Independent recursive CFR oracle for the optimized restricted-river kernel."""
import math
import unittest

from pokerlab.equilibrium import InfoSet, solve_equilibrium
from pokerlab.solver import solve
from tests.test_solver_validation import (
    BOARD, brute_best_responses, deals, keyed, mixed_value, play, strategies,
)


def reference_profile(board, oop, ip, pot, bet, iterations, algorithm):
    """Full recursive traversal, with independently defined public histories.

    Unlike the production four-node scalar kernel, derive every action utility
    recursively and accumulate counterfactual regret using explicit reaches.
    """
    dl = keyed(deals(board, oop, ip))
    hands = [sorted({d[p] for d in dl}) for p in (0, 1)]
    owners = {(): 0, ("check",): 1, ("bet",): 1, ("check", "bet"): 0}
    actions = {h: (("check", "bet") if h in ((), ("check",)) else ("fold", "call"))
               for h in owners}
    keys = [(player, hand, history) for history, player in owners.items()
            for hand in hands[player]]
    regrets = {k: [0., 0.] for k in keys}
    sums = {k: [0., 0.] for k in keys}
    terminals = {("check", "check"): "check_check", ("bet", "fold"): "bet_fold",
                 ("bet", "call"): "bet_call", ("check", "bet", "fold"): "check_bet_fold",
                 ("check", "bet", "call"): "check_bet_call"}
    for t in range(1, iterations + 1):
        current = {}
        for k, r in regrets.items():
            positive = [max(v, 0) for v in r]
            mass = sum(positive)
            current[k] = [v/mass for v in positive] if mass else [.5, .5]
        delta = {k: [0., 0.] for k in keys}
        for h0, h1, weight, sign in dl:
            def visit(history, reach):
                if history in terminals:
                    return play(terminals[history], sign, pot, bet)
                player = owners[history]
                k = (player, (h0, h1)[player], history)
                probs = current[k]
                values = []
                for a, name in enumerate(actions[history]):
                    nxt = list(reach)
                    nxt[player] *= probs[a]
                    values.append(visit(history + (name,), nxt))
                expected = sum(p*v for p, v in zip(probs, values))
                for a, value in enumerate(values):
                    delta[k][a] += weight * reach[1-player] * (1 if player == 0 else -1) * (value-expected)
                    sums[k][a] += weight * reach[player] * probs[a] * (t*t if algorithm == "dcfr" else 1)
                return expected
            visit((), [1., 1.])
        for k in keys:
            for a in (0, 1):
                total = regrets[k][a] + delta[k][a]
                if algorithm == "dcfr":
                    total *= (t**1.5/(t**1.5+1)) if total > 0 else .5
                regrets[k][a] = total
    avg = {k: [x/sum(v) for x in v] if sum(v) else [.5, .5] for k, v in sums.items()}
    return ({h: (avg[(0, h, ())][1], avg[(0, h, ("check", "bet"))][1]) for h in hands[0]},
            {h: (avg[(1, h, ("check",))][1], avg[(1, h, ("bet",))][1]) for h in hands[1]})


class SolverVariantTests(unittest.TestCase):
    def test_optimized_kernel_matches_recursive_oracle_for_both_variants(self):
        fixtures = (
            (BOARD, "AsAh:0.3,KsKh", "QcQd,AcKc:0.5", 100, 50),
            (BOARD, "AsAh,KsKh", "AsAd:0.7,QcQd", 80, 30),
            ("AsKsQsJsTs", "2c3c,4c5c", "2d3d,4d5d", 60, 60),
            ("2c7d9hJsKd", "AsAh,3c4c", "QsQh", 100, 100),
        )
        for algorithm in ("vanilla", "dcfr"):
            for board, oop, ip, pot, bet in fixtures:
                with self.subTest(algorithm=algorithm, board=board, oop=oop):
                    r = solve(board, oop, ip, pot, bet, 75, algorithm=algorithm)
                    actual = strategies(r)
                    expected = reference_profile(board, oop, ip, pot, bet, 75, algorithm)
                    for side in (0, 1):
                        for hand in expected[side]:
                            for a, b in zip(actual[side][hand], expected[side][hand]):
                                self.assertAlmostEqual(a, b, places=10)

    def test_dcfr_exact_gap_matches_exhaustive_information_set_best_responses(self):
        for oop, ip in (("AsAh:0.3,KsKh", "QcQd,AcKc:0.5"),
                        ("AsAh,KsKh", "AsAd:0.7,QcQd")):
            r = solve(BOARD, oop, ip, iterations=200, algorithm="dcfr")
            o, i = strategies(r)
            dl = keyed(deals(BOARD, oop, ip))
            br0, br1 = brute_best_responses(o, i, dl)
            self.assertAlmostEqual(r["nash_conv"], br0+br1, places=9)
            self.assertAlmostEqual(r["value_oop"], mixed_value(o, i, dl), places=9)

    def test_dcfr_known_bluff_catcher_equilibrium(self):
        r = solve("2c7d9hJsKd", "AsAh,3c4c", "QsQh", bet=100,
                  iterations=6000, algorithm="dcfr")
        oop = {h["hand"]: h for h in r["oop"]}
        self.assertAlmostEqual(r["value_oop"], 25, delta=.5)
        self.assertAlmostEqual(oop["3c4c"]["bet"], .5, delta=.04)
        self.assertAlmostEqual(r["ip"][0]["call"], .5, delta=.04)
        # Use the same one-chip tolerance as the legacy known-equilibrium
        # fixture. DCFR is optional and is not faster on every small game.
        self.assertLess(r["nash_conv"], 1.)

    def test_dcfr_convergence_across_distinct_games(self):
        fixtures = (
            (BOARD, "AsAh,KsKh,QsQh,AsKs", "AcAd,KcKd,QcQd,AcKc"),
            ("Ts9s4c2h7d", "AsKs,QsJs,8s8d,AhAd", "9h9d,7h7c,AcKc,QhQc"),
        )
        for board, oop, ip in fixtures:
            low = solve(board, oop, ip, iterations=10, algorithm="dcfr")
            high = solve(board, oop, ip, iterations=1500, algorithm="dcfr")
            self.assertLess(high["nash_conv"], low["nash_conv"]/4)
            self.assertTrue(math.isfinite(high["value_oop"]))

    def test_default_remains_vanilla_and_dcfr_is_deterministic(self):
        args = (BOARD, "AsAh,KsKh", "QcQd,AcKc")
        self.assertEqual(solve(*args, iterations=50), solve(*args, iterations=50, algorithm="vanilla"))
        a = solve(*args, iterations=50, algorithm="dcfr")
        self.assertEqual(a, solve(*args, iterations=50, algorithm="dcfr"))
        self.assertEqual(a["algorithm"], "dcfr")
        self.assertIn("quadratic", a["cfr_variant"])

    def test_node_locks_still_report_exact_frequencies_and_unrestricted_gap(self):
        for algorithm in ("vanilla", "dcfr"):
            r = solve(BOARD, "AsAh,KsKh", "QcQd,AcKc", iterations=100,
                      lock={"ip_bet": .3, "ip_call": .7}, algorithm=algorithm)
            for row in r["ip"]:
                self.assertAlmostEqual(row["bet_after_check"], .3, places=12)
                self.assertAlmostEqual(row["call"], .7, places=12)
            self.assertIn("not a convergence certificate", r["gap_note"])

    def test_equilibrium_interface_accepts_dcfr_without_changing_actions(self):
        eq = solve_equilibrium(BOARD, "AsAh", "KcKd", iterations=100, algorithm="dcfr")
        dist = eq.strategy_at(InfoSet("oop", "AsAh"))
        self.assertEqual({a.name for a, _ in dist}, {"check", "bet"})
        self.assertAlmostEqual(sum(p for _, p in dist), 1)

    def test_invalid_algorithm_is_rejected(self):
        for algorithm in (None, "gto", 1, [], {}):
            with self.assertRaises(ValueError):
                solve(BOARD, "AsAh", "KcKd", algorithm=algorithm)
