"""Independent profile/BR replay regression for preflop hidden-card policies."""
from fractions import Fraction
from itertools import product
import unittest

from pokerlab.cards import expand_range
from scripts import preflop_checkdown_validation as oracle

BOARDS = 1_712_304
CONFIG = {
    "small_blind": 0.5,
    "big_blind": 1.0,
    "starting_stack": 2.0,
    "raise_sizes": [0.5],
    "max_raises": 1,
    "include_all_in": True,
}
SB_RANGE = "AdAs:1,QdQs:0.5"
BB_RANGE = "AsKh:0.25,KdKs:1"

# Independently enumerated PR125 full-board census rows, also retained in
# benchmarks/results/preflop-suit-remap-v1.json. No new enumeration here.
COUNTS = [
    {"sb_hand": "AdAs", "bb_hand": "KdKs", "wins": 1_410_336,
     "ties": 9_308, "losses": 292_660, "boards": BOARDS},
    {"sb_hand": "QdQs", "bb_hand": "AsKh", "wins": 968_267,
     "ties": 7_226, "losses": 736_811, "boards": BOARDS},
    {"sb_hand": "QdQs", "bb_hand": "KdKs", "wins": 292_846,
     "ties": 9_336, "losses": 1_410_122, "boards": BOARDS},
]


def _terminal(contributions, winner=None):
    return {"terminal": (tuple(map(float, contributions)), winner)}


def _action(name, amount, target, probability):
    key = name if name not in ("raise", "bet", "all_in") else name + "@" + format(float(target), ".9f").rstrip("0").rstrip(".")
    return {"name": name, "amount": float(amount), "raise_to": float(target),
            "history_key": key, "probability": float(probability)}


def _node(player, history, actions, children):
    return {"player": player, "history": tuple(history),
            "actions": tuple(actions), "children": tuple(children)}


def _make_fixture():
    # This is the complete stack-2, one-raise game written as public histories.
    # Its only betting choices are the root SB action and the BB option after
    # a limp; calls/folds close the remaining branches.
    bb_after_limp = _node(
        1, ("call",),
        (_action("check", 0, 0, 1), _action("all_in", 1, 2, 0)),
        (_terminal((1, 1)), _node(
            0, ("call", "all_in@2"),
            (_action("fold", 0, 0, 1), _action("call", 1, 2, 0)),
            (_terminal((1, 2), 1), _terminal((2, 2))))),
    )
    bb_facing_sb_shove = _node(
        1, ("all_in@2",),
        (_action("fold", 0, 0, 1), _action("call", 1, 2, 0)),
        (_terminal((2, 1), 0), _terminal((2, 2))),
    )
    root = _node(
        0, (),
        (_action("fold", 0, 0, 1), _action("call", 0.5, 1, 0),
         _action("all_in", 1.5, 2, 0)),
        (_terminal((0.5, 1), 1), bb_after_limp, bb_facing_sb_shove),
    )
    ranges = (expand_range(SB_RANGE), expand_range(BB_RANGE))
    hands = tuple(tuple(sorted(r)) for r in ranges)
    raw = []
    for sb in hands[0]:
        for bb in hands[1]:
            if not set(sb) & set(bb):
                mass = (Fraction.from_float(float(ranges[0][sb])) *
                        Fraction.from_float(float(ranges[1][bb])))
                raw.append((sb, bb, mass))
    normalizer = sum((x[2] for x in raw), Fraction())
    pairs = tuple((sb, bb, mass / normalizer) for sb, bb, mass in raw)
    assert [("".join(a), "".join(b), p) for a, b, p in pairs] == [
        ("AdAs", "KdKs", Fraction(8, 13)),
        ("QdQs", "AsKh", Fraction(1, 13)),
        ("QdQs", "KdKs", Fraction(4, 13)),
    ]
    count_by_pair = {(r["sb_hand"], r["bb_hand"]): r for r in COUNTS}
    signs = {
        (sb, bb): Fraction(count_by_pair[(''.join(sb), ''.join(bb))]["wins"] -
                           count_by_pair[(''.join(sb), ''.join(bb))]["losses"], BOARDS)
        for sb, bb, _ in pairs
    }

    raw_policy = {
        (0, "AdAs", ()): (0.2, 0.5, 0.3),
        (0, "QdQs", ()): (0.3, 0.4, 0.3),
        (1, "AsKh", ("call",)): (0.4, 0.6),
        (1, "KdKs", ("call",)): (0.8, 0.2),
        (1, "AsKh", ("all_in@2",)): (0.25, 0.75),
        (1, "KdKs", ("all_in@2",)): (0.6, 0.4),
        (0, "AdAs", ("call", "all_in@2")): (0.7, 0.3),
        (0, "QdQs", ("call", "all_in@2")): (0.35, 0.65),
    }
    rows = []
    policy = {}

    def collect(node):
        if "terminal" in node:
            return
        player, history = node["player"], node["history"]
        for hand in hands[player]:
            if not any((hand, other) in {(a, b) for a, b, _ in pairs}
                       for other in hands[1]) if player == 0 else not any(
                           (other, hand) in {(a, b) for a, b, _ in pairs}
                           for other in hands[0]):
                continue
            hand_text = "".join(hand)
            probs = raw_policy[(player, hand_text, history)]
            policy[(player, hand_text, history)] = tuple(
                Fraction.from_float(float(p)) /
                sum((Fraction.from_float(float(q)) for q in probs), Fraction())
                for p in probs)
            rows.append({
                "player": ("sb", "bb")[player], "hand": hand_text,
                "street": "preflop", "revealed_board": [],
                "history": list(history),
                "actions": [_action(a["name"], a["amount"], a["raise_to"], p)
                            for a, p in zip(node["actions"], probs)],
            })
        for child in node["children"]:
            collect(child)

    collect(root)

    def utility(terminal, sb, bb, responder):
        contributions, winner = terminal["terminal"]
        matched = Fraction.from_float(float(min(contributions)))
        sign = Fraction(1 if winner == 0 else -1) if winner is not None else signs[sb, bb]
        p0 = matched * sign
        return p0 if responder == 0 else -p0

    def policy_value(node, sb, bb, responder, chosen):
        if "terminal" in node:
            return utility(node, sb, bb, responder)
        hand = (sb, bb)[node["player"]]
        probs = chosen[(node["player"], "".join(hand), node["history"])]
        return sum((p * policy_value(child, sb, bb, responder, chosen)
                    for p, child in zip(probs, node["children"])), Fraction())

    profile_value = sum((prior * policy_value(root, sb, bb, 0, policy)
                         for sb, bb, prior in pairs), Fraction())

    def exhaustive_br(responder):
        total = Fraction()
        own_hands = sorted({(sb, bb)[responder] for sb, bb, _ in pairs})
        for own_hand in own_hands:
            group = [(sb, bb, prior) for sb, bb, prior in pairs
                     if (sb, bb)[responder] == own_hand]
            infos = []

            def collect_infos(node):
                if "terminal" in node:
                    return
                if node["player"] == responder:
                    key = (responder, "".join(own_hand), node["history"])
                    if key not in infos:
                        infos.append(key)
                for child in node["children"]:
                    collect_infos(child)

            collect_infos(root)
            actions_by_info = {}
            for key in infos:
                found = []

                def find_actions(node):
                    if "terminal" in node:
                        return
                    if (node["player"], "".join(own_hand), node["history"]) == key:
                        found.extend(range(len(node["actions"])))
                    for child in node["children"]:
                        find_actions(child)

                find_actions(root)
                actions_by_info[key] = range(len(found))

            best = None
            for choices in product(*(actions_by_info[k] for k in infos)):
                candidate = dict(policy)
                for key, allowed, choice in zip(infos,
                                                (actions_by_info[k] for k in infos),
                                                choices):
                    pure = [Fraction(0)] * len(allowed)
                    pure[choice] = Fraction(1)
                    candidate[key] = tuple(pure)
                value = sum((prior * policy_value(root, sb, bb, responder, candidate)
                             for sb, bb, prior in group), Fraction())
                best = value if best is None or value > best else best
            total += best
        return total

    def leaked_pairwise_br(responder):
        """Forbidden comparison that lets the responder see both hands."""
        total = Fraction()
        for sb, bb, prior in pairs:
            infos = []

            def collect_pair_infos(node):
                if "terminal" in node:
                    return
                if node["player"] == responder:
                    key = (responder, "".join((sb, bb)[responder]), node["history"])
                    if key not in infos:
                        infos.append(key)
                for child in node["children"]:
                    collect_pair_infos(child)

            collect_pair_infos(root)
            counts = []
            for key in infos:
                found = []

                def find_pair_actions(node):
                    if "terminal" in node:
                        return
                    if (node["player"], "".join((sb, bb)[responder]), node["history"]) == key:
                        found.extend(range(len(node["actions"])))
                    for child in node["children"]:
                        find_pair_actions(child)

                find_pair_actions(root)
                counts.append(range(len(found)))
            best = None
            for choices in product(*counts):
                candidate = dict(policy)
                for key, allowed, choice in zip(infos, counts, choices):
                    pure = [Fraction(0)] * len(allowed)
                    pure[choice] = Fraction(1)
                    candidate[key] = tuple(pure)
                score = policy_value(root, sb, bb, responder, candidate)
                best = score if best is None or score > best else best
            total += prior * best
        return total

    br_sb = exhaustive_br(0)
    br_bb = exhaustive_br(1)
    peek_sb = leaked_pairwise_br(0)
    peek_bb = leaked_pairwise_br(1)
    gap_sb = max(Fraction(0), br_sb - profile_value)
    gap_bb = max(Fraction(0), br_bb + profile_value)
    nash_conv = gap_sb + gap_bb
    world_rows = sum(sum(row[key] > 0 for key in ("wins", "ties", "losses"))
                     for row in COUNTS)
    equity_rows = []
    for sb, bb, prior in pairs:
        count = count_by_pair[("".join(sb), "".join(bb))]
        equity_rows.append({
            **count, "pair_probability": float(prior),
            "pair_probability_fraction": [prior.numerator, prior.denominator],
        })
    tree_counts = {"decision_nodes": 4, "fold_terminals": 3,
                   "continuations": 3, "public_states": 10}
    result = {
        "solver_version": "preflop-full-checkdown-v1",
        "strategy_schema": "preflop-strategy-v1",
        "algorithm": "vanilla", "iterations": 10,
        "training_iterations_completed": 10, "config": CONFIG,
        "runout_mode": "full-deck-hidden-final-board-checkdown",
        "compatible_pairs": len(pairs), "physical_boards": BOARDS * len(pairs),
        "training_world_rows": world_rows, "info_sets": len(rows),
        "tree": tree_counts, "work_budget": {},
        "pair_equities": equity_rows, "strategy": rows,
        "value_sb": float(profile_value), "value_bb": float(-profile_value),
        "sb_best_response_value": float(br_sb),
        "bb_best_response_value": float(br_bb),
        "sb_best_response_gain": float(gap_sb),
        "bb_best_response_gain": float(gap_bb),
        "nash_conv": float(nash_conv), "exploitability": float(nash_conv / 2),
        "scope": "synthetic mixed policy using trusted full-board counts",
    }
    return result, profile_value, br_sb, br_bb, nash_conv, peek_sb, peek_bb


class PreflopCheckdownOracleTests(unittest.TestCase):
    def test_exact_profile_and_hidden_hand_best_responses(self):
        result, value, br_sb, br_bb, nash_conv, peek_sb, peek_bb = _make_fixture()
        replay = oracle.replay(result, SB_RANGE, BB_RANGE, CONFIG, COUNTS)
        self.assertEqual(replay["value_sb_fraction"],
                         [value.numerator, value.denominator])
        self.assertEqual(replay["sb_best_response_fraction"],
                         [br_sb.numerator, br_sb.denominator])
        self.assertEqual(replay["bb_best_response_fraction"],
                         [br_bb.numerator, br_bb.denominator])
        self.assertEqual(replay["nash_conv_fraction"],
                         [nash_conv.numerator, nash_conv.denominator])
        self.assertTrue(replay["exact_fraction_replay"])
        self.assertEqual(replay["checked_information_sets"], 8)
        self.assertEqual(replay["checked_physical_boards"], BOARDS * 3)
        self.assertAlmostEqual(float(value), 0.15199176494181119, places=14)
        self.assertAlmostEqual(float(br_sb), 0.7494037722992395, places=14)
        self.assertAlmostEqual(float(br_bb), 0.24016375956246447, places=14)
        self.assertGreaterEqual(peek_sb, br_sb)
        self.assertGreater(peek_bb, br_bb)

    def test_boolean_numeric_configuration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "booleans"):
            oracle._config({**CONFIG, "starting_stack": True})
        with self.assertRaisesRegex(ValueError, "booleans"):
            oracle._config({**CONFIG, "raise_sizes": [True]})
        result, *_ = _make_fixture()
        result['config'] = {**CONFIG, 'big_blind': True}
        with self.assertRaisesRegex(ValueError, 'booleans'):
            oracle.replay(result, SB_RANGE, BB_RANGE, CONFIG, COUNTS)


if __name__ == "__main__":
    unittest.main()
