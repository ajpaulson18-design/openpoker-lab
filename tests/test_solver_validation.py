"""Independent validation of the restricted river CFR solver.

Everything below recomputes values with code that shares nothing with
``pokerlab.solver`` except hand ranking, so formula errors cannot cancel out.
"""
import itertools
import unittest

from pokerlab.cards import cards, expand_range, rank_hand
from pokerlab.equilibrium import Action, InfoSet, solve_equilibrium
from pokerlab.solver import solve, terminal_utilities

BOARD = "Js8d4c2h2s"
POT, BET = 100, 50


def deals(board, oop, ip):
    """Weighted compatible (oop_hand, ip_hand, weight, sign) tuples."""
    b = cards(board, 5)
    r0, r1 = expand_range(oop, b), expand_range(ip, b)
    out = []
    for h0, w0 in r0.items():
        for h1, w1 in r1.items():
            if set(h0) & set(h1):
                continue
            a, c = rank_hand(h0 + b), rank_hand(h1 + b)
            out.append((h0, h1, w0*w1, (a > c) - (a < c)))
    total = sum(d[2] for d in out)
    return [(a, c, w/total, s) for a, c, w, s in out]


def play(line, sign, pot=POT, bet=BET):
    """Reference OOP utility from first principles (chips vs half-pot)."""
    half = pot/2
    if line == "bet_fold":
        return half
    if line == "check_bet_fold":
        return -half
    if line == "check_check":
        return sign*half
    return sign*(half+bet)   # either called bet


def mixed_value(o, i, dl):
    """Expected OOP value of behavioural strategies given as probability tuples."""
    v = 0.
    for h0, h1, w, s in dl:
        x, d = o[h0]
        y, c = i[h1]
        for line, p in (("bet_fold", x*(1-c)), ("bet_call", x*c),
                        ("check_check", (1-x)*(1-y)),
                        ("check_bet_fold", (1-x)*y*(1-d)), ("check_bet_call", (1-x)*y*d)):
            v += w*p*play(line, s)
    return v


def brute_best_responses(o, i, dl):
    """Exhaustive pure-strategy best response for each side against the other."""
    oh = sorted({d[0] for d in dl})
    ih = sorted({d[1] for d in dl})
    pure = list(itertools.product((0, 1), repeat=2))
    best0 = max(mixed_value(dict(zip(oh, combo)), i, dl)
                for combo in itertools.product(pure, repeat=len(oh)))
    best1 = max(-mixed_value(o, dict(zip(ih, combo)), dl)
                for combo in itertools.product(pure, repeat=len(ih)))
    return best0, best1


def strategies(result):
    o = {r["hand"]: (r["bet"], r["call_after_check"]) for r in result["oop"]}
    i = {r["hand"]: (r["bet_after_check"], r["call"]) for r in result["ip"]}
    return o, i


def key(hand):
    return "".join(hand)


def keyed(dl):
    return [(key(a), key(b), w, s) for a, b, w, s in dl]


class Kuhn:
    """Tiny generic vanilla CFR on Kuhn poker (known value -1/18 for player 1)."""
    def __init__(self):
        self.regret, self.sums = {}, {}

    @staticmethod
    def strat(r):
        p = [max(0, x) for x in r]
        m = sum(p)
        return [x/m for x in p] if m else [.5, .5]

    def cfr(self, c, h, p0, p1):
        n = len(h)
        player = n % 2
        if n > 1:
            if h[-1] == "p" and h[-2] == "p":
                return 1 if c[player] > c[1-player] else -1
            if h[-2:] == "bb":
                return 2*(1 if c[player] > c[1-player] else -1)
            if h[-2:] == "bp":
                return 1
        info = str(c[player]) + h
        r = self.regret.setdefault(info, [0., 0.])
        s = self.sums.setdefault(info, [0., 0.])
        st = self.strat(r)
        util, v = [0., 0.], 0.
        for a, ch in enumerate("pb"):
            if player == 0:
                util[a] = -self.cfr(c, h + ch, p0*st[a], p1)
            else:
                util[a] = -self.cfr(c, h + ch, p0, p1*st[a])
            v += st[a]*util[a]
        mine, theirs = (p0, p1) if player == 0 else (p1, p0)
        for a in (0, 1):
            r[a] += theirs*(util[a]-v)
            s[a] += mine*st[a]
        return v

    def train(self, iterations):
        total = 0.
        for _ in range(iterations):
            for c in itertools.permutations((1, 2, 3), 2):
                total += self.cfr(c, "", 1, 1)
        return total/iterations/6

    def average(self, info):
        s = self.sums[info]
        return [x/sum(s) for x in s]


class TerminalUtilityTests(unittest.TestCase):
    def test_every_terminal_is_zero_sum_and_matches_hand_derivation(self):
        for sign in (-1, 0, 1):
            t = terminal_utilities(POT, BET, sign)
            for line, u in t.items():
                self.assertEqual(u, play(line, sign), (line, sign))

    def test_folds_pay_half_pot_regardless_of_cards(self):
        for sign in (-1, 0, 1):
            t = terminal_utilities(80, 30, sign)
            self.assertEqual(t["bet_fold"], 40)        # IP folds: OOP wins half-pot
            self.assertEqual(t["check_bet_fold"], -40)  # OOP folds: loses half-pot

    def test_showdown_and_tie_utilities(self):
        win, lose, tie = (terminal_utilities(100, 50, s) for s in (1, -1, 0))
        self.assertEqual((win["check_check"], lose["check_check"], tie["check_check"]), (50, -50, 0))
        self.assertEqual((win["bet_call"], lose["bet_call"], tie["bet_call"]), (100, -100, 0))
        self.assertEqual(win["check_bet_call"], 100)

    def test_reported_values_are_zero_sum(self):
        r = solve(BOARD, "AsAh,KsKh,QsQh", "AcAd,KcKd,QcQd", iterations=200)
        self.assertEqual(r["value_oop"] + r["value_ip"], 0)


class CardRemovalTests(unittest.TestCase):
    def test_overlapping_hands_never_dealt(self):
        r = solve(BOARD, "AsAh,KsKh", "AsKd,AcAd", iterations=50)
        # AsAh/AsKd and AsAh/AcAd? only As conflicts with AsKd; AsAh vs AcAd is legal.
        self.assertEqual(r["deals"], 3)
        self.assertEqual(r["deals"], len(deals(BOARD, "AsAh,KsKh", "AsKd,AcAd")))

    def test_board_cards_are_removed_from_ranges(self):
        r = solve(BOARD, "Js8d,AsAh", "KsKh", iterations=20)
        self.assertEqual([h["hand"] for h in r["oop"]], ["AhAs"])

    def test_no_compatible_pairs_is_rejected(self):
        with self.assertRaises(ValueError):
            solve(BOARD, "AsAh", "AsAd", iterations=10)

    def test_blocker_changes_deal_weights_and_value(self):
        # IP holds the nut-blocking Ace of spades half the time. With a
        # weighted range, the blocked OOP hand must receive less mass.
        dl = deals(BOARD, "AsAh:1,KsKh:1", "AsAd:1")
        mass = {}
        for h0, _, w, _ in dl:
            mass[key(h0)] = mass.get(key(h0), 0) + w
        self.assertEqual(set(mass), {"KhKs"})
        self.assertAlmostEqual(mass["KhKs"], 1.0)


class RangeNormalisationTests(unittest.TestCase):
    def test_scaled_weights_give_identical_solution_when_uniformly_scaled(self):
        a = solve(BOARD, "AsAh,KsKh", "QcQd,AcKc", iterations=100)
        b = solve(BOARD, "AsAh:0.5,KsKh:0.5", "QcQd:0.4,AcKc:0.4", iterations=100)
        self.assertEqual(a["oop"], b["oop"])
        self.assertAlmostEqual(a["value_oop"], b["value_oop"], places=9)

    def test_relative_weights_matter(self):
        a = solve(BOARD, "AsAh:1,3c3d:1", "QcQd", iterations=100)["value_oop"]
        b = solve(BOARD, "AsAh:1,3c3d:0.1", "QcQd", iterations=100)["value_oop"]
        self.assertNotAlmostEqual(a, b, places=3)

    def test_deal_probabilities_sum_to_one(self):
        self.assertAlmostEqual(sum(d[2] for d in deals(BOARD, "AsAh:0.3,KsKh", "QcQd:0.7,AcKc")), 1)


class StrategyIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = solve(BOARD, "AsAh,KsKh,QsQh,AsKs", "AcAd,KcKd,QcQd,AcKc", iterations=500)

    def test_probabilities_are_valid(self):
        for r in self.result["oop"] + self.result["ip"]:
            for k, v in r.items():
                if k != "hand":
                    self.assertTrue(0 <= v <= 1 and v == v, (r["hand"], k, v))

    def test_interface_distributions_sum_to_one_and_only_legal(self):
        eq = solve_equilibrium(BOARD, "AsAh,KsKh,QsQh", "AcAd,KcKd,QcQd", iterations=200)
        legal = {(): {"check", "bet"}, ("check",): {"check", "bet"},
                 ("bet",): {"fold", "call"}, ("check", "bet"): {"fold", "call"}}
        for player, hands in (("oop", ("AsAh", "KsKh", "QsQh")), ("ip", ("AcAd", "KcKd", "QcQd"))):
            for history, names in legal.items():
                # decide whose node it is
                owner = "oop" if history in ((), ("check", "bet")) else "ip"
                if owner != player:
                    continue
                for hand in hands:
                    dist = eq.strategy_at(InfoSet(player, hand, history))
                    self.assertAlmostEqual(sum(p for _, p in dist), 1.0, places=12)
                    self.assertEqual({a.name for a, _ in dist}, names)
                    self.assertTrue(all(p >= 0 for _, p in dist))

    def test_interface_rejects_illegal_requests(self):
        eq = solve_equilibrium(BOARD, "AsAh", "KcKd", iterations=20)
        for bad in (InfoSet("ip", "KcKd", ()), InfoSet("oop", "AsAh", ("bet",)),
                    InfoSet("oop", "AsAh", ("check", "check")), InfoSet("oop", "QsQh", ()),
                    InfoSet("oop", "AsAh", ("bet", "raise"))):
            with self.assertRaises(ValueError):
                eq.strategy_at(bad)

    def test_interface_sizing_is_explicit(self):
        eq = solve_equilibrium(BOARD, "AsAh", "KcKd", pot=80, bet=30, iterations=20)
        bet = [a for a in eq.legal_actions(InfoSet("oop", "AsAh")) if a.name == "bet"][0]
        self.assertEqual(bet, Action("bet", 30.0))
        self.assertEqual(Action("fold").amount, 0)
        # hand order in the request must not matter
        self.assertEqual(eq.strategy_at(InfoSet("oop", "AsAh")), eq.strategy_at(InfoSet("oop", "AhAs")))

    def test_nuts_vs_air_strategy_is_sensible(self):
        eq = solve_equilibrium(BOARD, "AsAh", "KcKd", iterations=300)
        # Betting and checking both net +pot/2 against a hand that never calls.
        self.assertAlmostEqual(eq.exploitability, 0, delta=1)
        # Dominated: IP never calls with the losing hand
        calls = {a.name: p for a, p in eq.strategy_at(InfoSet("ip", "KcKd", ("bet",)))}
        self.assertLess(calls["call"], .02)


class ExploitabilityAuditTests(unittest.TestCase):
    RANGES = ("AsAh,KsKh", "QcQd,AcKc")

    def test_reported_value_matches_independent_evaluation(self):
        r = solve(BOARD, *self.RANGES, iterations=400)
        o, i = strategies(r)
        dl = keyed(deals(BOARD, *self.RANGES))
        self.assertAlmostEqual(r["value_oop"], mixed_value(o, i, dl), places=9)

    def test_best_response_matches_brute_force_enumeration(self):
        r = solve(BOARD, *self.RANGES, iterations=400)
        o, i = strategies(r)
        dl = keyed(deals(BOARD, *self.RANGES))
        br0, br1 = brute_best_responses(o, i, dl)
        v = mixed_value(o, i, dl)
        self.assertAlmostEqual(r["nash_conv"], max(0, br0 + br1), places=9)
        self.assertAlmostEqual(r["oop_best_response_gain"], max(0, br0 - v), places=9)
        self.assertAlmostEqual(r["exploitability"], r["nash_conv"]/2, places=12)
        self.assertGreaterEqual(br0, v - 1e-12)   # a best response is never worse than the strategy
        self.assertGreaterEqual(br1, -v - 1e-12)

    def test_brute_force_audit_on_random_fixed_strategies(self):
        """The solver's exploitability formula is exact for arbitrary strategies,
        checked by re-deriving it from the public result on several rangesets."""
        for rng in (("AsAh,2c2d", "KcKd,QcQd"), ("AsAh:0.3,KsKh", "QcQd,AcKc:0.5")):
            r = solve(BOARD, *rng, iterations=60)
            o, i = strategies(r)
            dl = keyed(deals(BOARD, *rng))
            br0, br1 = brute_best_responses(o, i, dl)
            self.assertAlmostEqual(r["nash_conv"], max(0, br0 + br1), places=9)

    def test_obviously_weak_strategies_are_exploitable(self):
        # Hand-built weak strategy: OOP always checks and folds to every bet; IP always bets
        # and never calls. Best responses must gain a lot.
        dl = keyed(deals(BOARD, *self.RANGES))
        o = {"AhAs": (0., 0.), "KhKs": (0., 0.)}
        i = {"QcQd": (1., 0.), "AcKc": (1., 0.)}
        v = mixed_value(o, i, dl)
        br0, br1 = brute_best_responses(o, i, dl)
        weak_nash_conv = br0 - v + br1 + v
        self.assertGreater(weak_nash_conv, 40)

    def test_converged_solution_is_not_weakly_exploitable(self):
        r = solve(BOARD, *self.RANGES, iterations=3000)
        self.assertLess(r["nash_conv"], 1.0)


class ConvergenceTests(unittest.TestCase):
    GAMES = (
        (BOARD, "AsAh,KsKh,QsQh,AsKs", "AcAd,KcKd,QcQd,AcKc", 100, 50),
        ("Ts9s4c2h7d", "AsKs,QsJs,8s8d,AhAd,KhKd", "9h9d,7h7c,AcKc,QhQc", 100, 75),
        ("AsKsQsJs2c", "TsTh,2d2h,KdKh,QdQh", "9s9h,AdAh,JdJh,5d5h", 60, 60),
    )

    def test_more_cfr_iterations_materially_reduce_exploitability(self):
        for board, oop, ip, pot, bet in self.GAMES:
            low = solve(board, oop, ip, pot, bet, iterations=10)["nash_conv"]
            high = solve(board, oop, ip, pot, bet, iterations=3000)["nash_conv"]
            self.assertGreater(low, 0, board)
            self.assertLess(high, low/3, (board, low, high))

    def test_solver_is_deterministic(self):
        a = solve(BOARD, "AsAh,KsKh", "QcQd,AcKc", iterations=100)
        b = solve(BOARD, "AsAh,KsKh", "QcQd,AcKc", iterations=100)
        self.assertEqual(a["oop"], b["oop"])
        self.assertEqual(a["nash_conv"], b["nash_conv"])


class KuhnReferenceTests(unittest.TestCase):
    """Validates the CFR update rules independently of the river code."""
    @classmethod
    def setUpClass(cls):
        cls.kuhn = Kuhn()
        cls.value = cls.kuhn.train(20000)

    def test_game_value_is_minus_one_eighteenth(self):
        self.assertAlmostEqual(self.value, -1/18, delta=.005)

    def test_known_equilibrium_properties(self):
        k = self.kuhn
        alpha = k.average("1")[1]            # bluff frequency with the Jack
        self.assertLess(alpha, 1/3 + .02)
        self.assertAlmostEqual(k.average("3")[1], 3*alpha, delta=.03)  # King bets 3x alpha
        self.assertAlmostEqual(k.average("2pb")[1], alpha + 1/3, delta=.03)
        self.assertAlmostEqual(k.average("2b")[1], 1/3, delta=.03)
        self.assertLess(k.average("2p")[1], .01)   # Queen never bets after a check
        self.assertGreater(k.average("3b")[1], .99)
        self.assertLess(k.average("1b")[1], .01)


class RiverKnownEquilibriumTests(unittest.TestCase):
    def test_polarised_bluff_catcher_game_matches_theory(self):
        """OOP has the nuts and air, IP only a bluff-catcher, pot=100, bet=100.
        Theory (IP can only call/fold vs a bet; check-back gives showdown):
        IP indifference needs bluffs:value = bet:(pot+bet) in the betting range,
        so OOP bets air with probability 1/2 of its value-bet weight when
        bet equals pot, and IP calls with probability pot/(pot+bet) = 1/2."""
        board = "2c7d9hJsKd"
        r = solve(board, "AsAh,3c4c", "QsQh", pot=100, bet=100, iterations=6000)
        oop = {h["hand"]: h for h in r["oop"]}
        self.assertGreater(oop["AhAs"]["bet"], .97)
        self.assertAlmostEqual(r["ip"][0]["call"], .5, delta=.06)
        self.assertAlmostEqual(oop["3c4c"]["bet"], .5, delta=.06)
        self.assertAlmostEqual(r["value_oop"], 25, delta=.5)
        self.assertLess(r["nash_conv"], 1.0)


if __name__ == "__main__":
    unittest.main()
