"""Bounded independent exact replay for the fixed three-hand TURN game."""
from fractions import Fraction
from itertools import combinations
from math import isfinite

from scripts import turn_river_validation as rules
from scripts import turn_three_hand_reference as reference


METRICS = (
    "value_oop", "value_ip", "oop_best_response_value",
    "ip_best_response_value", "oop_best_response_gain",
    "ip_best_response_gain", "nash_conv", "exploitability",
)
MAX_STRUCTURAL_VISITS = 27_351
MAX_WEIGHTED_ROW_OPERATIONS = 3_610_332
MAX_ACTIVE_WORLD_NODE_VISITS = 92_664
MAX_CONSUMED_POLICY_ROWS = 38_016
MAX_POLICY_EDGE_MULTIPLICATIONS = 85_536
MAX_TERMINAL_WORLD_CONTRIBUTIONS = 48_708
MAX_FRACTION_RESULTS = 1_000_000
MAX_FRACTION_BITS = 65_536
MAX_RANK_KEYS = 276
MAX_FIVE_CARD_CALLS = 5_796
MAX_POLICY_ROWS = 3_606
MAX_POLICY_ACTION_SLOTS = 8_046
MAX_PUBLIC_NODES = 3_039
MAX_PUBLIC_DEPTH = 9
_RANKS = {rank: index for index, rank in enumerate("23456789TJQKA", 2)}


def _need(condition, message):
    if not condition:
        raise ValueError(message)


class _Meter:
    def __init__(self):
        self.operations = 0
        self.max_bits = 0
        self.zero = self.integer(0)
        self.two = self.integer(2)

    def accept(self, value):
        if type(value) is not Fraction:
            raise TypeError("Exact arithmetic result must be a Fraction")
        self._reserve()
        self.operations += 1
        bits = max(abs(value.numerator).bit_length(), value.denominator.bit_length())
        self.max_bits = max(self.max_bits, bits)
        if bits > MAX_FRACTION_BITS:
            raise ValueError("Exact replay exceeds 65,536-bit Fraction ceiling")
        return value

    def integer(self, value):
        self._reserve()
        return self.accept(Fraction(value))

    def from_float(self, value):
        self._reserve()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Only finite binary64 numeric values are accepted")
        number = float(value)
        if not isfinite(number):
            raise ValueError("Non-finite binary64 value")
        return self.accept(Fraction.from_float(number))

    def add(self, left, right):
        self._reserve()
        return self.accept(left + right)

    def sub(self, left, right):
        self._reserve()
        return self.accept(left - right)

    def mul(self, left, right):
        self._reserve()
        return self.accept(left * right)

    def div(self, left, right):
        if not right:
            raise ZeroDivisionError("Exact replay division by zero")
        self._reserve()
        return self.accept(left / right)

    def neg(self, value):
        self._reserve()
        return self.accept(-value)

    def add_many(self, values):
        total = self.zero
        for value in values:
            total = self.add(total, value)
        return total

    def _reserve(self):
        if self.operations + 1 > MAX_FRACTION_RESULTS:
            raise ValueError("Exact replay exceeds one million Fraction results")


def _rank_five(cards):
    """Independent category-tuple rank of exactly five distinct cards."""
    _need(len(cards) == 5 and len(set(cards)) == 5, "Invalid five-card key")
    ranks = [_RANKS[card[0]] for card in cards]
    suits = [card[1] for card in cards]
    counts = {}
    for rank in ranks:
        counts[rank] = counts.get(rank, 0) + 1
    groups = sorted(((count, rank) for rank, count in counts.items()), reverse=True)
    distinct = sorted(counts, reverse=True)
    straight = 0
    if len(distinct) == 5:
        if distinct[0] - distinct[-1] == 4:
            straight = distinct[0]
        elif distinct == [14, 5, 4, 3, 2]:
            straight = 5
    flush = len(set(suits)) == 1
    if flush and straight:
        return (8, straight)
    if groups[0][0] == 4:
        return (7, groups[0][1], groups[1][1])
    if [count for count, _ in groups] == [3, 2]:
        return (6, groups[0][1], groups[1][1])
    if flush:
        return (5, *sorted(ranks, reverse=True))
    if straight:
        return (4, straight)
    if groups[0][0] == 3:
        trip = groups[0][1]
        return (3, trip, *sorted((rank for rank in ranks if rank != trip), reverse=True))
    if [count for count, _ in groups] == [2, 2, 1]:
        pairs = sorted((rank for count, rank in groups if count == 2), reverse=True)
        kicker = next(rank for count, rank in groups if count == 1)
        return (2, *pairs, kicker)
    if groups[0][0] == 2:
        pair = groups[0][1]
        return (1, pair, *sorted((rank for rank in ranks if rank != pair), reverse=True))
    return (0, *sorted(ranks, reverse=True))


def _best_seven(cards):
    _need(len(cards) == 7 and len(set(cards)) == 7, "Invalid seven-card key")
    return max(_rank_five(combo) for combo in combinations(cards, 5))


def _independent_signs(worlds):
    keys = set()
    for world in worlds:
        board = tuple(world["board"])
        for hand in world["hands"]:
            keys.add(tuple(sorted(tuple(hand) + board)))
            if len(keys) > MAX_RANK_KEYS:
                raise ValueError("Exact rank key set exceeds 276")
    _need(len(keys) == MAX_RANK_KEYS, "Fixed exact rank key count differs")
    _need(len(keys) * 21 == MAX_FIVE_CARD_CALLS,
          "Fixed exact rank work is rejected before ranking")
    ranks = {key: _best_seven(key) for key in sorted(keys)}
    calls = len(ranks) * 21
    _need(calls == MAX_FIVE_CARD_CALLS, "Fixed exact five-card call count differs")
    signs = []
    for world in worlds:
        board = tuple(world["board"])
        oop = tuple(sorted(tuple(world["hands"][0]) + board))
        ip = tuple(sorted(tuple(world["hands"][1]) + board))
        sign = (ranks[oop] > ranks[ip]) - (ranks[oop] < ranks[ip])
        _need(type(sign) is int and sign in (-1, 0, 1), "Invalid exact showdown sign")
        _need(sign == world["sign"], "Reference world sign disagrees with local exact ranker")
        signs.append(sign)
    return signs, len(ranks), calls


def _normalize_policy(result, game, meter):
    fixture, board, config, worlds, selected, root, _ = game
    nodes = rules._collect_nodes(root)
    _need(len(nodes) == 1_254, "Public decision count differs from fixed bound")
    rows = result.get("strategy") if isinstance(result, dict) else None
    _need(type(rows) is list and len(rows) <= MAX_POLICY_ROWS,
          "Policy row count exceeds fixed bound")
    slots = 0
    for row in rows:
        _need(type(row) is dict and type(row.get("actions")) is list,
              "Malformed policy row")
        _need(len(row["actions"]) <= 3, "Policy row exceeds three legal actions")
        slots += len(row["actions"])
        for action in row["actions"]:
            _need(type(action) is dict and type(action.get("probability")) is float,
                  "Policy probabilities must be binary64 floats")
            _need(isfinite(action["probability"]), "Policy probability is non-finite")
    _need(len(rows) == MAX_POLICY_ROWS and slots == MAX_POLICY_ACTION_SLOTS,
          "Fixed policy row/action census differs")
    _need(type(result.get("config")) is dict and result["config"] == fixture["config"],
          "Policy config differs from fixed game")
    _need(result.get("turn_config") == fixture["config"]
          and result.get("river_config") == fixture["config"]
          and result.get("street_configs") == {
              "turn": fixture["config"], "river": fixture["config"]},
          "Policy street configuration metadata differs")
    for label in ("config", "turn_config", "river_config"):
        _need(rules._config(result[label], label) == config,
              "Policy configuration has invalid numeric types")
    for label, supplied in result["street_configs"].items():
        _need(rules._config(supplied, label) == config,
              "Policy street configuration has invalid numeric types")
    for label, expected in (("pot", config.pot), ("effective_stack", 220.0)):
        if label in result:
            supplied = result[label]
            _need(type(supplied) in (int, float) and supplied == expected
                  and isfinite(supplied),
                  "Policy numeric mirror differs: " + label)
    _need(type(result.get("runout_mode")) is str
          and result["runout_mode"] == "full-deck",
          "Policy must preserve full-deck runout mode")
    # Validate the complete row/action identity through the independent rules
    # parser, but retain original JSON floats for exact binary64 conversion.
    rules._validate_policy(result, root, nodes, worlds, board, selected, True)
    by_key = {}
    for row in rows:
        player = 0 if row["player"] == "oop" else 1 if row["player"] == "ip" else None
        _need(player is not None, "Unknown strategy player")
        key = (player, row["hand"], tuple(row["history"]))
        _need(key not in by_key, "Duplicate exact strategy row")
        by_key[key] = row
    normalized = {}
    adjustments = 0
    for key, row in by_key.items():
        probs = tuple(meter.from_float(action["probability"])
                      for action in row["actions"])
        total = meter.add_many(probs)
        _need(total > 0, "Policy row has zero exact binary64 probability mass")
        exact = tuple(meter.div(probability, total) for probability in probs)
        _need(meter.add_many(exact) == 1, "Exact policy row is not stochastic")
        normalized[key] = exact
        adjustments += exact != probs
    rules._validate_count_metadata(result, world_count=len(worlds), pair_count=9,
                                   info_count=MAX_POLICY_ROWS, board_length=4)
    _need(len(normalized) == MAX_POLICY_ROWS,
          "Exact policy normalization lost or added rows")
    return normalized, slots, adjustments


def _terminal_magnitudes(root, config, meter):
    values = {}
    half_pot = meter.div(meter.from_float(config.pot), meter.two)
    for node in _all_nodes(root):
        if not isinstance(node, rules._Terminal):
            continue
        contributions = tuple(meter.from_float(value) for value in node.contributions)
        matched = min(contributions)
        magnitude = meter.add(half_pot, matched)
        values[id(node)] = magnitude
    return values


def _all_nodes(root):
    nodes = []
    pending = [root]
    while pending:
        node = pending.pop()
        nodes.append(node)
        if len(nodes) > MAX_PUBLIC_NODES:
            raise ValueError("Exact replay exceeds public-node limit")
        if isinstance(node, rules._Decision):
            _need(len(node.actions) == len(node.children)
                  and 0 < len(node.actions) <= 3,
                  "Malformed or oversized decision node")
            pending.extend(node.children)
        elif isinstance(node, rules._Chance):
            _need(0 < len(node.branches) <= 48,
                  "Malformed or oversized chance node")
            pending.extend(node.branches.values())
    _need(len(nodes) == MAX_PUBLIC_NODES, "Fixed public-node census differs")
    return nodes


def _evaluate(root, worlds, policy, player, mode, magnitudes, meter, counters):
    """Sum one complete public traversal for each private hand of player."""
    own_hands = sorted({world["hands"][player] for world in worlds})
    _need(len(own_hands) == 3, "Fixed game must have three hands per player")

    def visit(node, group):
        counters["structural_node_visits"] += 1
        if counters["structural_node_visits"] > MAX_STRUCTURAL_VISITS:
            raise ValueError("Exact replay exceeds structural node visit bound")
        counters["active_world_node_visits"] += len(group)
        if counters["active_world_node_visits"] > MAX_ACTIVE_WORLD_NODE_VISITS:
            raise ValueError("Exact replay exceeds active world/node bound")
        if isinstance(node, rules._Terminal):
            counters["terminal_world_contributions"] += len(group)
            if counters["terminal_world_contributions"] > MAX_TERMINAL_WORLD_CONTRIBUTIONS:
                raise ValueError("Exact replay exceeds terminal contribution bound")
            total = meter.zero
            magnitude = magnitudes[id(node)]
            for world, mass in group:
                if node.kind == "fold":
                    sign = 1 if node.winner == 0 else -1
                else:
                    sign = world["sign"]
                payoff = magnitude if sign == 1 else meter.neg(magnitude) if sign == -1 else meter.zero
                total = meter.add(total, meter.mul(mass, payoff))
            return total
        if isinstance(node, rules._Chance):
            total = meter.zero
            for river, child in node.branches.items():
                branch = [(world, mass) for world, mass in group
                          if world["river"] == river]
                total = meter.add(total, visit(child, branch))
            return total
        if not isinstance(node, rules._Decision):
            raise ValueError("Unknown node in exact public tree")
        counters["active_decision_world_visits"] += len(group)
        if counters["active_decision_world_visits"] > MAX_CONSUMED_POLICY_ROWS:
            raise ValueError("Exact replay exceeds active decision/world bound")
        if mode != "profile" and node.player == player:
            values = [visit(child, group) for child in node.children]
            return max(values) if mode == "max" else min(values)
        counters["consumed_policy_rows"] += len(group)
        counters["weighted_row_operations"] += len(group)
        if counters["consumed_policy_rows"] > MAX_CONSUMED_POLICY_ROWS:
            raise ValueError("Exact replay exceeds consumed policy-row bound")
        if counters["weighted_row_operations"] > MAX_WEIGHTED_ROW_OPERATIONS:
            raise ValueError("Exact replay exceeds weighted-row operation bound")
        values = []
        for action_index, child in enumerate(node.children):
            branch = []
            for world, mass in group:
                key = (node.player, "".join(world["hands"][node.player]), node.history)
                probability = policy[key][action_index]
                if probability:
                    counters["policy_edge_multiplications"] += 1
                    if counters["policy_edge_multiplications"] > MAX_POLICY_EDGE_MULTIPLICATIONS:
                        raise ValueError("Exact replay exceeds policy-edge multiplication bound")
                    branch.append((world, meter.mul(mass, probability)))
            values.append(visit(child, branch))
        return meter.add_many(values)

    result = meter.zero
    for hand in own_hands:
        group = [(world, meter.accept(world["weight"])) for world in worlds
                 if world["hands"][player] == hand]
        value = visit(root, group)
        result = meter.add(result, value)
    return result


def _audit_counters(census, rank_keys, five_card_calls, meter, counters, slots, adjustments):
    counters.update({
        "rank_keys": rank_keys,
        "five_card_calls": five_card_calls,
        "independent_showdown_sign_checks": 396,
        "policy_rows": MAX_POLICY_ROWS,
        "policy_action_slots": slots,
        "normalization_adjusted_rows": adjustments,
        "public_nodes": census["public_nodes"],
        "public_decisions": census["public_decisions"],
        "terminal_nodes": census["terminal_nodes"],
        "chance_nodes": census["chance_nodes"],
        "chance_edges": census["chance_edges"],
        "depth": census["depth"],
        "exact_fraction_operations": meter.operations,
        "max_fraction_bits": meter.max_bits,
        "chance_grouping": False,
    })
    return counters


def audit_policy(result, model=None):
    """Return all eight exact metrics plus bounded-work counters for one policy."""
    game = reference.model() if model is None else model
    census = reference.validate_model(game)
    fixture, board, config, worlds, selected, root, _ = game
    _need(census["public_nodes"] <= MAX_PUBLIC_NODES
          and census["depth"] <= MAX_PUBLIC_DEPTH,
          "Fixed tree exceeds exact oracle bounds")
    meter = _Meter()
    policy, slots, adjustments = _normalize_policy(result, game, meter)
    # Both rank dimensions are reserved before the first best-five call.
    _need(MAX_RANK_KEYS * 21 == MAX_FIVE_CARD_CALLS,
          "Fixed independent rank work envelope differs")
    signs, rank_keys, five_card_calls = _independent_signs(worlds)
    _need(len(signs) == len(worlds) == 396, "Showdown sign audit incomplete")
    magnitudes = _terminal_magnitudes(root, config, meter)
    counters = {
        "structural_node_visits": 0,
        "weighted_row_operations": 0,
        "active_world_node_visits": 0,
        "consumed_policy_rows": 0,
        "active_decision_world_visits": 0,
        "policy_edge_multiplications": 0,
        "terminal_world_contributions": 0,
    }
    value = _evaluate(root, worlds, policy, 0, "profile", magnitudes, meter, counters)
    br0 = _evaluate(root, worlds, policy, 0, "max", magnitudes, meter, counters)
    min_ip = _evaluate(root, worlds, policy, 1, "min", magnitudes, meter, counters)
    br1 = meter.neg(min_ip)
    oop_gain = meter.sub(br0, value)
    ip_gain = meter.add(br1, value)
    nash_conv = meter.add(oop_gain, ip_gain)
    exploitability = meter.div(nash_conv, meter.two)
    _need(all(value >= 0 for value in (oop_gain, ip_gain, nash_conv, exploitability)),
          "Exact response gains must be nonnegative")
    _need(counters["structural_node_visits"] == MAX_STRUCTURAL_VISITS,
          "Exact replay structural traversal count differs")
    metrics = {
        "value_oop": value,
        "value_ip": meter.neg(value),
        "oop_best_response_value": br0,
        "ip_best_response_value": br1,
        "oop_best_response_gain": oop_gain,
        "ip_best_response_gain": ip_gain,
        "nash_conv": nash_conv,
        "exploitability": exploitability,
    }
    counters = _audit_counters(census, rank_keys, five_card_calls, meter, counters, slots, adjustments)
    return {"metrics": metrics, "counters": counters}
