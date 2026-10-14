"""Exact Fraction replay of a legal profile on the independent numeric tree.

This is a development audit helper, not a solver. Its inputs must already have
passed the independent numeric-tree validator; each call rechecks model shape,
row probabilities, physical mass, and resource limits before exact evaluation.
"""
from fractions import Fraction
from math import isfinite
from numbers import Real

from scripts import turn_river_validation as validator


MAX_EXACT_DEPTH = 64
MAX_EXACT_WORK = 100_000
MAX_FRACTION_BITS = 65_536


class _Budget:
    def __init__(self, max_work, max_depth, max_bits):
        for name, value, ceiling in (
                ("max_work", max_work, MAX_EXACT_WORK),
                ("max_depth", max_depth, MAX_EXACT_DEPTH),
                ("max_bits", max_bits, MAX_FRACTION_BITS)):
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError(
                    f"{name} must be a positive exact integer no greater than {ceiling}")
        self.max_work = max_work
        self.max_depth = max_depth
        self.max_bits = max_bits
        self.work = 0
        self.counters = {}
        self.max_observed_bits = 1

    def charge(self, kind, amount=1):
        if type(amount) is not int or amount < 0:
            raise ValueError("work charge must be a nonnegative exact integer")
        if self.work + amount > self.max_work:
            raise ValueError("Exact rational certificate exceeds its work limit")
        self.work += amount
        self.counters[kind] = self.counters.get(kind, 0) + amount

    def fraction(self, value, label):
        if not isinstance(value, Fraction):
            raise TypeError(f"{label} must be an exact Fraction")
        bits = max(abs(value.numerator).bit_length(), value.denominator.bit_length(), 1)
        if bits > self.max_bits:
            raise ValueError(f"Exact rational certificate exceeds the {self.max_bits}-bit limit")
        self.max_observed_bits = max(self.max_observed_bits, bits)
        return value

    def add(self, left, right, label):
        self.charge("fraction_operations")
        return self.fraction(left + right, label)

    def multiply(self, left, right, label):
        self.charge("fraction_operations")
        return self.fraction(left * right, label)

    def divide(self, left, right, label):
        if right == 0:
            raise ZeroDivisionError(f"{label} has a zero denominator")
        self.charge("fraction_operations")
        return self.fraction(left / right, label)


def _input_fraction(value, budget, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} cannot be boolean")
    if isinstance(value, Fraction):
        exact = value
    elif type(value) is int:
        exact = Fraction(value)
    elif type(value) is float and isfinite(value):
        exact = Fraction.from_float(value)
    else:
        raise ValueError(f"{label} must be a finite binary64 number or Fraction")
    return budget.fraction(exact, label)


def _children(node):
    if isinstance(node, validator._Decision):
        return node.children
    if isinstance(node, validator._Chance):
        return node.branches.values()
    if isinstance(node, validator._Terminal):
        return ()
    raise TypeError("Exact replay received an unknown numeric-tree node")


def _preflight_tree(root, budget):
    """Iteratively bound depth and expanded nodes before recursive evaluation."""
    pending = [(root, 1)]
    nodes = 0
    deepest = 0
    while pending:
        node, depth = pending.pop()
        budget.charge("tree_preflight_nodes")
        nodes += 1
        deepest = max(deepest, depth)
        if depth > budget.max_depth:
            raise ValueError("Exact rational certificate exceeds its depth limit")
        if nodes > budget.max_work:
            raise ValueError("Exact rational certificate exceeds its node limit")
        children = _children(node)
        budget.charge("tree_preflight_edges", len(children))
        pending.extend((child, depth + 1) for child in children)
    return nodes, deepest


def _normalize_policies(policies, result, budget):
    """Convert validated float rows to exact, explicitly normalized rows."""
    row_index = {}
    budget.charge("serialized_strategy_row_index_entries",
                  len(result["strategy"]))
    for row in result["strategy"]:
        key = (0 if row["player"] == "oop" else 1,
               row["hand"], tuple(row["history"]))
        row_index[key] = row

    normalized = {}
    ledger = []
    canonical_rows = []
    max_adjustment = Fraction(0)
    budget.charge("policy_sort_entries", len(policies))
    for key in sorted(policies):
        raw_values = policies[key]
        budget.charge("row_normalization_entries", len(raw_values))
        raw = tuple(_input_fraction(value, budget, "serialized probability")
                    for value in raw_values)
        if not raw or any(value < 0 or value > 1 for value in raw):
            raise ValueError("Serialized policy row has invalid probability support")
        total = Fraction(0)
        for value in raw:
            total = budget.add(total, value, "serialized row probability sum")
        if total <= 0:
            raise ValueError("Serialized policy row has zero probability mass")
        row = tuple(budget.divide(value, total, "normalized row probability")
                    for value in raw)
        normalized[key] = row

        source = row_index.get(key)
        if source is None or len(source["actions"]) != len(row):
            raise ValueError("Normalized policy row lost its validated identity")
        action_ledger = []
        normalized_actions = []
        for index, (before, after, action) in enumerate(zip(raw, row, source["actions"])):
            delta = budget.add(after, -before, "row normalization adjustment")
            max_adjustment = max(max_adjustment, abs(delta))
            action_ledger.append({
                "index": index,
                "name": action["name"],
                "history_key": action["history_key"],
                "input_fraction": str(before),
                "normalized_fraction": str(after),
                "adjustment_fraction": str(delta),
                "adjustment_float": float(delta),
            })
            normalized_actions.append({
                "name": action["name"],
                "amount": action["amount"],
                "raise_to": action["raise_to"],
                "history_key": action["history_key"],
                "probability_fraction": str(after),
            })
        canonical_rows.append({
            "player": source["player"], "hand": source["hand"],
            "street": source["street"], "board": source["board"],
            "history": source["history"], "actions": normalized_actions,
        })
        ledger.append({
            "player": source["player"], "hand": source["hand"],
            "history": source["history"], "input_row_sum_fraction": str(total),
            "actions": action_ledger,
        })
    if set(normalized) != set(policies) or len(row_index) != len(policies):
        raise ValueError("Exact policy normalization did not preserve complete row coverage")
    return normalized, ledger, max_adjustment, canonical_rows


def _terminal_value(node, world, pot, budget):
    matched = min(node.contributions)
    sign = (1 if node.winner == 0 else -1) if node.kind == "fold" else world["sign"]
    # Match the independent numeric model's binary64 terminal boundary first;
    # convert that resulting binary64 value exactly, rather than decimal intent.
    payoff = sign * (pot / 2 + matched)
    if not isfinite(float(payoff)):
        raise ValueError("Exact replay rejects a nonfinite numeric terminal payoff")
    return budget.fraction(Fraction.from_float(float(payoff)), "terminal payoff")


def _profile_value(root, worlds, policies, pot, budget):
    def visit(node, world, depth):
        budget.charge("profile_node_world_visits")
        if depth > budget.max_depth:
            raise ValueError("Exact rational certificate exceeds its depth limit")
        if isinstance(node, validator._Chance):
            river = world["river"]
            child = node.branches.get(river)
            return Fraction(0) if child is None else visit(child, world, depth + 1)
        if isinstance(node, validator._Terminal):
            return _terminal_value(node, world, pot, budget)
        key = (node.player, "".join(world["hands"][node.player]), node.history)
        row = policies[key]
        total = Fraction(0)
        for probability, child in zip(row, node.children):
            child_value = visit(child, world, depth + 1)
            total = budget.add(total,
                               budget.multiply(probability, child_value,
                                               "profile action contribution"),
                               "profile action sum")
        return total

    value = Fraction(0)
    for world in worlds:
        mass = budget.fraction(world["weight"], "normalized physical world mass")
        contribution = budget.multiply(mass, visit(root, world, 1),
                                       "physical world profile contribution")
        value = budget.add(value, contribution, "profile EV sum")
    return value


def _partition_chance_group(group, branches, budget):
    """Bucket original world/mass entries by river with an upfront reservation."""
    branch_count = len(branches)
    group_count = len(group)
    # Reserve the entire conservative 2*B + 3*N model before constructing the
    # branch map/buckets or iterating the input group. The three N slots model
    # one entry scan, one river lookup and one retained bucket-reference slot.
    budget.charge("chance_partition_branch_map_bucket_slots", 2 * branch_count)
    budget.charge("chance_partition_entries_scanned", group_count)
    budget.charge("chance_partition_river_lookups", group_count)
    budget.charge("chance_partition_bucket_reference_slots", group_count)
    buckets = {river: [] for river in branches}
    for entry in group:
        river = entry[0]["river"]
        bucket = buckets.get(river)
        if bucket is not None:
            bucket.append(entry)
    return buckets


def _best_response(root, worlds, policies, player, pot, budget,
                   chance_grouping="scan"):
    budget.charge("own_hand_setup", len(worlds))
    own_hands = sorted({world["hands"][player] for world in worlds})

    def visit(node, own_hand, group, depth):
        budget.charge("best_response_node_group_visits")
        if depth > budget.max_depth:
            raise ValueError("Exact rational certificate exceeds its depth limit")
        if not group:
            return Fraction(0)
        if isinstance(node, validator._Chance):
            total = Fraction(0)
            if chance_grouping == "partition":
                buckets = _partition_chance_group(group, node.branches, budget)
                for river, child in node.branches.items():
                    value = visit(child, own_hand, buckets[river], depth + 1)
                    total = budget.add(total, value, "chance outcome sum")
                return total
            for river, child in node.branches.items():
                # Charge the whole filter scan before copying any world entries.
                budget.charge("chance_group_entries_scanned", len(group))
                budget.charge("chance_group_entries_copied", len(group))
                subset = tuple(entry for entry in group if entry[0]["river"] == river)
                value = visit(child, own_hand, subset, depth + 1)
                total = budget.add(total, value, "chance outcome sum")
            return total
        if isinstance(node, validator._Terminal):
            budget.charge("terminal_group_entries_scanned", len(group))
            total = Fraction(0)
            for world, mass in group:
                weighted = budget.multiply(mass, _terminal_value(node, world, pot, budget),
                                           "terminal world contribution")
                total = budget.add(total, weighted, "terminal group sum")
            return total
        if node.player == player:
            budget.charge("own_action_slots", len(node.children))
            values = [visit(child, own_hand, group, depth + 1)
                      for child in node.children]
            return max(values) if player == 0 else min(values)

        budget.charge("opponent_action_group_slots", len(node.children))
        action_groups = [[] for _ in node.children]
        # The opponent knows their own hand, so multiply each world by that
        # hand's policy row, but keep this player's own action fixed across the
        # entire visible-history group.
        budget.charge("opponent_group_entries_scanned",
                      len(group) * len(node.children))
        budget.charge("opponent_group_entries_copied",
                      len(group) * len(node.children))
        for world, mass in group:
            key = (node.player, "".join(world["hands"][node.player]), node.history)
            row = policies[key]
            for index, probability in enumerate(row):
                if probability:
                    action_groups[index].append((
                        world, budget.multiply(mass, probability,
                                               "opponent policy reach")))
        total = Fraction(0)
        for child, action_group in zip(node.children, action_groups):
            if action_group:
                value = visit(child, own_hand, action_group, depth + 1)
                total = budget.add(total, value, "opponent policy action sum")
        return total

    response = Fraction(0)
    for hand in own_hands:
        # Charge the selection scan before allocating this hand's group.
        budget.charge("own_hand_group_entries_scanned", len(worlds))
        budget.charge("own_hand_group_entries_copied", len(worlds))
        group = tuple((world, budget.fraction(world["weight"], "world mass"))
                      for world in worlds if world["hands"][player] == hand)
        value = visit(root, hand, group, 1)
        response = budget.add(response, value, "own-hand response sum")
    return response if player == 0 else -response


def evaluate_exact(root, worlds, policies, pot, *, max_work=MAX_EXACT_WORK,
                   max_depth=MAX_EXACT_DEPTH, max_bits=MAX_FRACTION_BITS,
                   result=None, chance_grouping="scan"):
    """Return exact EV and legal BR interval for validated numeric model data.

    Public use requires a complete successful ``turn_river_validation`` replay
    before this function is called. This routine shares that validator's tree,
    physical worlds, and validated visible-information policy mapping; it is an
    exact-arithmetic audit of the same configured model, not another rules
    implementation or a formal certificate for raw unnormalized float rows.
    """
    if type(chance_grouping) is not str or chance_grouping not in ("scan", "partition"):
        raise ValueError("chance_grouping must be exactly 'scan' or 'partition'")
    budget = _Budget(max_work, max_depth, max_bits)
    if isinstance(pot, bool) or not isinstance(pot, Real) or not isfinite(float(pot)):
        raise ValueError("Exact replay requires a finite numeric starting pot")
    pot = float(pot)
    tree_nodes, max_tree_depth = _preflight_tree(root, budget)
    if not worlds:
        raise ValueError("Exact replay requires positive physical worlds")
    budget.charge("world_setup_entries", len(worlds))
    total_mass = Fraction(0)
    for world in worlds:
        mass = budget.fraction(world["weight"], "normalized physical world mass")
        if mass <= 0:
            raise ValueError("Exact replay rejects nonpositive physical world mass")
        total_mass = budget.add(total_mass, mass, "physical world normalizer")
    if total_mass != 1:
        raise ValueError("Independent physical world masses must be globally normalized")

    if result is None:
        raise ValueError("Complete serialized result is required for row normalization")
    normalized, ledger, max_adjustment, canonical_rows = _normalize_policies(
        policies, result, budget)
    value = _profile_value(root, worlds, normalized, float(pot), budget)
    br_oop = _best_response(root, worlds, normalized, 0, float(pot), budget,
                            chance_grouping)
    br_ip = _best_response(root, worlds, normalized, 1, float(pot), budget,
                           chance_grouping)
    lower = budget.add(Fraction(0), -br_ip, "lower legal-response bound")
    upper = br_oop
    if not lower <= value <= upper:
        raise ValueError("Exact legal-response interval does not contain profile EV")
    oop_gain = budget.add(upper, -value, "OOP unilateral gain")
    ip_gain = budget.add(value, -lower, "IP unilateral gain")
    if oop_gain < 0 or ip_gain < 0:
        raise ValueError("Exact unilateral response gain is negative")
    nash_conv = budget.add(upper, -lower, "exact NashConv")
    exploitability = budget.divide(nash_conv, Fraction(2), "exact exploitability")
    metrics = {
        "value_oop": value, "value_ip": -value,
        "oop_best_response_value": br_oop,
        "ip_best_response_value": br_ip,
        "oop_best_response_gain": oop_gain,
        "ip_best_response_gain": ip_gain,
        "nash_conv": nash_conv, "exploitability": exploitability,
    }
    for name, metric in metrics.items():
        budget.fraction(metric, name)
    output = {
        "metrics": metrics,
        "lower_value_bound": lower,
        "upper_value_bound": upper,
        "threshold_met": nash_conv <= Fraction(1, 1000),
        "normalization_ledger": ledger,
        "max_row_adjustment": max_adjustment,
        "normalized_policy_rows": canonical_rows,
        "tree_nodes": tree_nodes,
        "tree_depth": max_tree_depth,
        "worlds": len(worlds),
        "work": budget.work,
        "work_by_kind": dict(sorted(budget.counters.items())),
        "maximum_fraction_bits": budget.max_observed_bits,
        "work_limit": budget.max_work,
        "depth_limit": budget.max_depth,
        "fraction_bit_limit": budget.max_bits,
    }
    if chance_grouping == "partition":
        output["chance_grouping"] = chance_grouping
    return output
