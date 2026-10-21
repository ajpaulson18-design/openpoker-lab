"""Fixed three-hand physical TURN reference and exact-audit regressions."""

from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
import unittest
from unittest import mock

from scripts import full_physical_exact_oracle as old_oracle
from scripts import turn_river_validation as rules
from scripts import turn_three_hand_exact_oracle as oracle
from scripts import turn_three_hand_reference as reference
from pokerlab import cfr, postflop_solver


METRICS = (
    "value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value",
    "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability",
)
CHECK_CALL_METRICS = {
    "value_oop": Fraction(-9500, 891),
    "value_ip": Fraction(9500, 891),
    "oop_best_response_value": Fraction(6925, 891),
    "ip_best_response_value": Fraction(57550, 891),
    "oop_best_response_gain": Fraction(16425, 891),
    "ip_best_response_gain": Fraction(48050, 891),
    "nash_conv": Fraction(64475, 891),
    "exploitability": Fraction(64475, 1782),
}


def _hand_cards(hand):
    return {hand[index:index + 2] for index in range(0, len(hand), 2)}


def _literal_worlds():
    """Build the fixed 3x3 law from its literal pair masses and rank rule."""
    board = ("Js", "8d", "4c", "2h")
    oop_hands = (("As", "Ah"), ("Ks", "Kh"), ("Qs", "Qh"))
    ip_hands = (("Ac", "Ad"), ("Kc", "Kd"), ("Qc", "Qd"))
    masses = ((8, 6, 4), (16, 12, 8), (12, 9, 6))
    rank = {card: "23456789TJQKA".index(card[0]) + 2 for card in rules.DECK}
    worlds = []
    for oi, oop in enumerate(oop_hands):
        for ii, ip in enumerate(ip_hands):
            pair_mass = Fraction(masses[oi][ii], 81)
            dead = set(board) | set(oop) | set(ip)
            rivers = [card for card in rules.DECK if card not in dead]
            if oi == ii:
                signs = [0] * len(rivers)
            else:
                # If the river pairs the lower pocket rank, that hand makes
                # trips and beats the higher pocket pair; otherwise the higher
                # pocket pair wins. The fixed board has no A/K/Q card.
                signs = []
                for river in rivers:
                    lower_hand = 0 if oi > ii else 1
                    low_rank = 14 - max(oi, ii)
                    if rank[river] == low_rank:
                        oop_wins = lower_hand == 0
                    else:
                        oop_wins = oi < ii
                    signs.append(1 if oop_wins else -1)
            for river, sign in zip(rivers, signs):
                worlds.append({"hands": (oop, ip), "river": river,
                               "weight": pair_mass / 44, "sign": sign})
    return worlds


def _literal_check_call_response(worlds, responder, *, reveal_hidden_river=False,
                                 reveal_hidden_opponent=False):
    """Closed-form response; aggregate opponent hands before each choice."""
    signed = {}
    for world in worlds:
        key = (world["hands"][responder],
               world["hands"][1 - responder] if reveal_hidden_opponent else None)
        by_river = signed.setdefault(key, {})
        by_river[world["river"]] = (by_river.get(world["river"], Fraction()) +
                                    world["weight"] * world["sign"])
    choose = max if responder == 0 else min
    result = Fraction()
    for by_river in signed.values():
        coefficients = {
            river: signed_mass + choose(Fraction(), signed_mass)
            for river, signed_mass in by_river.items()
        }
        if reveal_hidden_river:
            # Illegal control: choose the turn investment after learning the
            # hidden river. Legal play sums these river branches first.
            result += sum((choose(50 * coefficient, 100 * coefficient)
                           for coefficient in coefficients.values()), Fraction())
        else:
            coefficient = sum(coefficients.values(), Fraction())
            result += choose(50 * coefficient, 100 * coefficient)
    return result if responder == 0 else -result


def _tree_structure(node):
    if isinstance(node, rules._Terminal):
        return ["terminal", node.kind, node.winner, list(node.contributions)]
    if isinstance(node, rules._Chance):
        return ["chance", list(node.history),
                [[river, _tree_structure(child)]
                 for river, child in sorted(node.branches.items())]]
    if not isinstance(node, rules._Decision):
        raise AssertionError(f"unknown public tree node {type(node)!r}")
    return ["decision", node.player, list(node.history), list(node.board),
            [[action.name, action.token, action.amount, action.raise_to,
              _tree_structure(child)]
             for action, child in zip(node.actions, node.children)]]


def _tree_census(root, river=None):
    nodes = decisions = terminals = chance_nodes = chance_edges = action_edges = depth_max = 0

    def walk(node, depth):
        nonlocal nodes, decisions, terminals, chance_nodes, chance_edges, action_edges, depth_max
        nodes += 1
        depth_max = max(depth_max, depth)
        if isinstance(node, rules._Decision):
            decisions += 1
            action_edges += len(node.actions)
            for child in node.children:
                walk(child, depth + 1)
        elif isinstance(node, rules._Chance):
            chance_nodes += 1
            branches = node.branches.items() if river is None else ((river, node.branches[river]),)
            for _, child in branches:
                chance_edges += 1
                walk(child, depth + 1)
        elif isinstance(node, rules._Terminal):
            terminals += 1
        else:
            raise AssertionError(f"unknown public tree node {type(node)!r}")

    walk(root, 1)
    return (nodes, decisions, terminals, chance_nodes, chance_edges,
            action_edges, depth_max)


def _assert_numeric_replay(test, result, audit_result, model):
    fixture = model[0]
    replay = rules.replay_policy(
        result, fixture["oop"], fixture["ip"], board=fixture["board"],
        config=fixture["config"],
    )
    for name in METRICS:
        test.assertLessEqual(
            abs(float(audit_result["metrics"][name]) - float(replay[name])), 1e-9,
            f"independent numeric replay differs for {name}",
        )


def _audit_without_production_helpers(result, model):
    """Fail if the exact oracle reaches a production solver/evaluator path."""
    with mock.patch.object(rules, "independent_rank",
                           side_effect=AssertionError("source rank helper called")), \
         mock.patch.object(cfr, "train",
                           side_effect=AssertionError("production trainer called")), \
         mock.patch.object(cfr, "evaluate",
                           side_effect=AssertionError("production evaluator called")), \
         mock.patch.object(cfr, "best_response",
                           side_effect=AssertionError("production best response called")), \
         mock.patch.object(postflop_solver, "solve_postflop",
                           side_effect=AssertionError("production solver called")), \
         mock.patch.object(postflop_solver, "_build_postflop_tree",
                           side_effect=AssertionError("production tree builder called")):
        return oracle.audit_policy(result, model)


class TurnThreeHandPhysicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Count calls made by the independent physical-rules source during the
        # actual reference construction; do not trust a reported formula.
        with mock.patch.object(rules, "independent_rank",
                               wraps=rules.independent_rank) as independent_rank:
            cls.model = reference.model()
            cls.reference_rank_calls = independent_rank.call_count
        cls.controls = reference.reconstruct()
        cls.literal_worlds = _literal_worlds()

    def test_fixed_physical_support_and_independent_pair_law(self):
        fixture, board, config, worlds, selected, root, pair_rows = self.model
        self.assertEqual(fixture, reference.FIXTURE)
        self.assertEqual("".join(board), "Js8d4c2h")
        self.assertEqual((len(worlds), len(selected)), (396, 48))
        self.assertEqual(sum((world["weight"] for world in worlds), Fraction()), 1)
        self.assertEqual(len(pair_rows), 9)
        self.assertEqual(len(self.literal_worlds), 396)
        self.assertEqual(sum((world["weight"] for world in self.literal_worlds), Fraction()), 1)
        expected_worlds = {
            (tuple(sorted(world["hands"][0])), tuple(sorted(world["hands"][1])),
             world["river"]): (world["weight"], world["sign"])
            for world in self.literal_worlds
        }
        observed_worlds = {
            (tuple(sorted(world["hands"][0])), tuple(sorted(world["hands"][1])),
             world["river"]): (world["weight"], world["sign"])
            for world in worlds
        }
        self.assertEqual(observed_worlds, expected_worlds)
        self.assertEqual(
            [row["rivers"] for row in pair_rows], [44] * 9,
        )

        expected_mass_numerators = (
            (8, 6, 4), (16, 12, 8), (12, 9, 6),
        )
        rank_index = {"A": 0, "K": 1, "Q": 2}
        actual = [[None] * 3 for _ in range(3)]
        for row in pair_rows:
            oop_rank = row["oop"][0]
            ip_rank = row["ip"][0]
            actual[rank_index[oop_rank]][rank_index[ip_rank]] = Fraction(row["mass_fraction"])
            self.assertEqual(row["rivers"], 44)
            if oop_rank == ip_rank:
                self.assertEqual((row["wins"], row["ties"], row["losses"]), (0, 44, 0))
            elif rank_index[oop_rank] < rank_index[ip_rank]:
                self.assertEqual((row["wins"], row["ties"], row["losses"]), (42, 0, 2))
            else:
                self.assertEqual((row["wins"], row["ties"], row["losses"]), (2, 0, 42))
        self.assertEqual(actual, [[Fraction(value, 81) for value in row]
                                  for row in expected_mass_numerators])

        # The numeric rules tree must retain its canonical shape, action slots,
        # and complete active one-river structure.
        with mock.patch.object(rules, "independent_rank",
                               wraps=rules.independent_rank) as source_rank:
            reference.validate_model(self.model)
            self.assertEqual(source_rank.call_count, 0)
        shape = json.dumps(_tree_structure(root), sort_keys=True,
                           separators=(",", ":"), allow_nan=False).encode()
        self.assertEqual(sha256(shape).hexdigest(),
                         "70d87064c6d7048b75784b6623a2dc6249f57ac61384a27d1724c3d53563bd61")
        self.assertEqual(_tree_census(root), (3039, 1254, 1780, 5, 240, 2798, 9))
        self.assertEqual(_tree_census(root, "2c"), (78, 32, 41, 5, 5, 72, 9))
        self.assertEqual(self.reference_rank_calls, 792)
        policy = reference.make_check_call_policy(self.model)
        self.assertEqual(len(policy["strategy"]), 3606)
        self.assertEqual(sum(len(row["actions"]) for row in policy["strategy"]), 8046)
        self.assertEqual(self.controls["training_calls"], 0)

    def test_exact_oracle_five_card_rank_categories(self):
        examples = (
            (0, ("As", "Kd", "9c", "7h", "3s")),
            (1, ("As", "Ah", "Kd", "9c", "3h")),
            (2, ("As", "Ah", "Kd", "Kc", "3h")),
            (3, ("As", "Ah", "Ac", "Kd", "3h")),
            (4, ("As", "Kd", "Qc", "Jh", "Ts")),
            (5, ("As", "Ks", "9s", "7s", "3s")),
            (6, ("As", "Ah", "Ac", "Kd", "Kc")),
            (7, ("As", "Ah", "Ac", "Ad", "Ks")),
            (8, ("As", "Ks", "Qs", "Js", "Ts")),
        )
        self.assertEqual([oracle._rank_five(cards)[0] for _, cards in examples],
                         list(range(9)))
        self.assertEqual(oracle._rank_five(("As", "2d", "3c", "4h", "5s")),
                         (4, 5))

    def test_check_call_anchor_exact_metrics_and_legal_closed_form_responses(self):
        policy = reference.make_check_call_policy(self.model)
        with mock.patch.object(oracle, "_rank_five",
                               wraps=oracle._rank_five) as rank_five:
            exact = _audit_without_production_helpers(policy, self.model)
            self.assertEqual(rank_five.call_count, 5796)
        self.assertEqual(exact["metrics"], CHECK_CALL_METRICS)
        local_br0 = _literal_check_call_response(self.literal_worlds, 0)
        local_br1 = _literal_check_call_response(self.literal_worlds, 1)
        local_value = sum((world["weight"] * world["sign"] * 50
                           for world in self.literal_worlds), Fraction())
        self.assertEqual((local_value, local_br0, local_br1),
                         (Fraction(-9500, 891), Fraction(6925, 891),
                          Fraction(57550, 891)))
        self.assertEqual((exact["metrics"]["oop_best_response_value"],
                          exact["metrics"]["ip_best_response_value"]),
                         (local_br0, local_br1))
        self.assertEqual(reference.check_call_response_bounds(self.model[3]),
                         (local_br0, local_br1))
        self.assertEqual(self.controls["check_call_metrics"], CHECK_CALL_METRICS)
        _assert_numeric_replay(self, policy, exact, self.model)

        # This control proves turn decisions cannot condition on the still-hidden
        # river. Compute it independently from the literal physical law.
        illegal_br0 = _literal_check_call_response(
            self.literal_worlds, 0, reveal_hidden_river=True)
        illegal_br1 = _literal_check_call_response(
            self.literal_worlds, 1, reveal_hidden_river=True)
        self.assertEqual((illegal_br0, illegal_br1),
                         (Fraction(875, 81), Fraction(58775, 891)))
        self.assertNotEqual(illegal_br0, local_br0)
        self.assertNotEqual(illegal_br1, local_br1)

        opponent_revealed_br0 = _literal_check_call_response(
            self.literal_worlds, 0, reveal_hidden_opponent=True)
        opponent_revealed_br1 = _literal_check_call_response(
            self.literal_worlds, 1, reveal_hidden_opponent=True)
        self.assertEqual((opponent_revealed_br0, opponent_revealed_br1),
                         (Fraction(19325, 891), Fraction(67300, 891)))
        self.assertGreater(opponent_revealed_br0, local_br0)
        self.assertGreater(opponent_revealed_br1, local_br1)

    def test_one_river_deviation_and_uniform_full_support_match_numeric_replay(self):
        deviation = reference.make_check_call_policy(self.model)
        row = next(row for row in deviation["strategy"]
                   if row["player"] == "ip"
                   and _hand_cards(row["hand"]) == {"Kc", "Kd"}
                   and row["history"] == ["check", "check", "river@2c", "check"])
        bet = next(action for action in row["actions"] if action["name"] == "bet")
        self.assertEqual(bet["history_key"], "bet@50")
        for action in row["actions"]:
            action["probability"] = float(action is bet)
        self.assertEqual(deviation["runouts"], list(self.model[4]))
        self.assertEqual(deviation["compatible_world_count"], 396)
        self.assertEqual(deviation["compatible_pairs"], 9)
        deviation_exact = _audit_without_production_helpers(deviation, self.model)
        self.assertEqual(deviation_exact["metrics"]["value_oop"], Fraction(-19075, 1782))
        _assert_numeric_replay(self, deviation, deviation_exact, self.model)

        uniform = reference.make_check_call_policy(self.model)
        for row in uniform["strategy"]:
            probability = float(1 / len(row["actions"]))
            for action in row["actions"]:
                action["probability"] = probability
        uniform_exact = _audit_without_production_helpers(uniform, self.model)
        self.assertGreater(uniform_exact["counters"]["normalization_adjusted_rows"], 0)
        _assert_numeric_replay(self, uniform, uniform_exact, self.model)

    def test_exact_binary64_normalization_and_complete_resource_census(self):
        policy = reference.make_check_call_policy(self.model)
        # This is within the numeric validator's 1e-9 row-sum tolerance, but
        # its exact meaning comes from the original binary64 values. Do not
        # decimalize or round the inputs before exact row normalization.
        root = next(row for row in policy["strategy"]
                    if row["player"] == "oop"
                    and _hand_cards(row["hand"]) == {"As", "Ah"}
                    and row["history"] == [])
        check = next(action for action in root["actions"] if action["name"] == "check")
        bet = next(action for action in root["actions"] if action["name"] == "bet")
        check["probability"] = 0.3
        bet["probability"] = 0.7000000001
        self.assertAlmostEqual(sum(action["probability"] for action in root["actions"]),
                               1.0000000001, delta=1e-16)
        exact = _audit_without_production_helpers(policy, self.model)
        normalized_bet = (Fraction.from_float(0.7000000001) /
                          (Fraction.from_float(0.3) + Fraction.from_float(0.7000000001)))
        expected_value = Fraction(-9500, 891) + Fraction(5000, 891) * normalized_bet
        self.assertEqual(exact["metrics"]["value_oop"], expected_value)
        _assert_numeric_replay(self, policy, exact, self.model)
        counters = exact["counters"]
        self.assertEqual(counters["normalization_adjusted_rows"], 1)
        self.assertEqual(counters["structural_node_visits"], 27351)
        self.assertLessEqual(counters["weighted_row_operations"], 3610332)
        self.assertLessEqual(counters["exact_fraction_operations"], 1000000)
        self.assertLessEqual(counters["max_fraction_bits"], 65536)
        self.assertEqual(counters["rank_keys"], 276)
        self.assertEqual(counters["five_card_calls"], 5796)
        self.assertEqual(counters["independent_showdown_sign_checks"], 396)
        self.assertEqual(counters["policy_rows"], 3606)
        self.assertEqual(counters["policy_action_slots"], 8046)
        self.assertEqual(counters["public_nodes"], 3039)
        self.assertEqual(counters["public_decisions"], 1254)
        self.assertEqual(counters["terminal_nodes"], 1780)
        self.assertEqual(counters["chance_nodes"], 5)
        self.assertEqual(counters["chance_edges"], 240)
        self.assertEqual(counters["depth"], 9)
        self.assertLessEqual(counters["active_world_node_visits"], 92664)
        self.assertLessEqual(counters["consumed_policy_rows"], 38016)
        self.assertLessEqual(counters["policy_edge_multiplications"], 85536)
        self.assertLessEqual(counters["terminal_world_contributions"], 48708)
        self.assertFalse(counters["chance_grouping"])

        # New fixed limits stay local to the new oracle; old admission limits
        # keep their published values.
        self.assertEqual(oracle.MAX_WEIGHTED_ROW_OPERATIONS, 3610332)
        self.assertEqual(old_oracle.MAX_TREE_VISITS, 6 * 3039)
        self.assertEqual(old_oracle.MAX_WEIGHTED_ROW_OPERATIONS, 3 * 176 * 3039)
        self.assertEqual(rules.MAX_ORACLE_WORK, 8_000_000)

    def test_rejects_corrupt_reused_models(self):
        duplicate_world = list(deepcopy(self.model))
        duplicate_worlds = list(duplicate_world[3])
        duplicate_worlds[-1] = deepcopy(duplicate_worlds[0])
        duplicate_world[3] = duplicate_worlds

        shifted_mass = list(deepcopy(self.model))
        shifted_worlds = list(shifted_mass[3])
        shifted_worlds[0]["weight"] += Fraction(1, 10_000)
        shifted_mass[3] = shifted_worlds

        balanced_mass_shift = list(deepcopy(self.model))
        balanced_worlds = list(balanced_mass_shift[3])
        balanced_worlds[0]["weight"] += Fraction(1, 10_000)
        balanced_worlds[1]["weight"] -= Fraction(1, 10_000)
        self.assertEqual(sum((world["weight"] for world in balanced_worlds), Fraction()), 1)
        balanced_mass_shift[3] = balanced_worlds

        mutated_tree = list(deepcopy(self.model))
        mutated_tree[5].history = ("tampered",)
        wrong_support = list(deepcopy(self.model))
        wrong_support[4] = wrong_support[4][:-1]

        # Preserve each pair's aggregate 42/2 law while corrupting which river
        # wins. Literal world identities must carry their original signs.
        swapped_signs = deepcopy(self.model)
        pair = next(world["hands"] for world in swapped_signs[3]
                    if world["sign"] == -1)
        loss = next(world for world in swapped_signs[3]
                    if world["hands"] == pair and world["sign"] == -1)
        win = next(world for world in swapped_signs[3]
                   if world["hands"] == pair and world["sign"] == 1)
        loss["sign"], win["sign"] = win["sign"], loss["sign"]

        wrong_stacks = deepcopy(self.model)
        object.__setattr__(wrong_stacks[2], "stacks", (1.0, 1.0))

        for malformed in (tuple(duplicate_world), tuple(shifted_mass),
                          tuple(balanced_mass_shift),
                          tuple(mutated_tree), tuple(wrong_support),
                          swapped_signs, wrong_stacks):
            with self.subTest(malformed=malformed[1]):
                with self.assertRaises(ValueError):
                    reference.validate_model(malformed)

    def test_rejects_malformed_policy_rows_before_replay(self):
        baseline = reference.make_check_call_policy(self.model)
        mutations = {}

        result = deepcopy(baseline)
        result["strategy"].pop()
        mutations["missing row"] = result

        result = deepcopy(baseline)
        result["strategy"].append(deepcopy(result["strategy"][0]))
        mutations["duplicate row"] = result

        result = deepcopy(baseline)
        extra = deepcopy(result["strategy"][0])
        extra["history"] = ["not-a-public-history"]
        result["strategy"].append(extra)
        mutations["extra row"] = result

        result = deepcopy(baseline)
        result["strategy"][0]["actions"][0]["name"] = "future_action"
        mutations["wrong action"] = result

        result = deepcopy(baseline)
        result["strategy"][0]["actions"][0]["amount"] = 999.0
        mutations["wrong amount"] = result

        result = deepcopy(baseline)
        result["config"]["max_raises"] = True
        mutations["boolean config count"] = result

        for label in ("pot", "effective_stack"):
            result = deepcopy(baseline)
            result[label] = 1.0
            mutations["wrong " + label + " mirror"] = result

        result = deepcopy(baseline)
        river_row = next(row for row in result["strategy"] if row["street"] == "river")
        river_index = next(i for i, item in enumerate(river_row["history"])
                           if item.startswith("river@"))
        river_row["history"][river_index] = "river@As"
        mutations["future history metadata"] = result

        for value, name in ((float("nan"), "nan"), (float("inf"), "infinite"),
                            (Fraction(1, 2), "Fraction"), (1, "integer")):
            result = deepcopy(baseline)
            result["strategy"][0]["actions"][0]["probability"] = value
            mutations[f"{name} probability"] = result

        for name, malformed in mutations.items():
            with self.subTest(policy=name):
                # Invalid input must fail before any independent seven-card
                # ranking or profile/response work begins.
                with mock.patch.object(oracle, "_best_seven",
                                       side_effect=AssertionError("ranked malformed policy")), \
                     self.assertRaises(ValueError):
                    _audit_without_production_helpers(malformed, self.model)

    def test_caps_reject_before_the_corresponding_unchecked_work(self):
        policy = reference.make_check_call_policy(self.model)
        with mock.patch.object(oracle, "MAX_FRACTION_RESULTS", 0), \
             mock.patch.object(oracle, "_best_seven",
                              side_effect=AssertionError("ranking ran after fraction cap")):
            with self.assertRaisesRegex(ValueError, "Fraction"):
                oracle.audit_policy(policy, self.model)

        with mock.patch.object(oracle, "MAX_RANK_KEYS", 275), \
             mock.patch.object(oracle, "_rank_five",
                              side_effect=AssertionError("ranked before key cap")):
            with self.assertRaises(ValueError):
                oracle.audit_policy(policy, self.model)

        with mock.patch.object(oracle, "MAX_FIVE_CARD_CALLS", 5795), \
             mock.patch.object(oracle, "_rank_five",
                              side_effect=AssertionError("ranked before call admission")):
            with self.assertRaises(ValueError):
                oracle.audit_policy(policy, self.model)

        meter = oracle._Meter()
        meter.operations = oracle.MAX_FRACTION_RESULTS
        # Overflow admission must precede the next expensive rational operation.
        with mock.patch.object(Fraction, "__add__",
                               side_effect=AssertionError("computed beyond Fraction cap")):
            with self.assertRaisesRegex(ValueError, "Fraction"):
                meter.add(Fraction(1), Fraction(1))


if __name__ == "__main__":
    unittest.main()
