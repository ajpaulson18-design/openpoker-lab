"""Exact normalized-policy value and legal-response certificate for U3's model.

Each public call builds and validates a fresh bounded physical model. This
module never trains, calls production payoff/response code, or retains a graph.
"""
from fractions import Fraction
from decimal import Decimal, localcontext
import hashlib
import json
from math import isfinite

from scripts import four_street_validation as numeric
from scripts import turn_rational_certificate as rational


MAX_EXACT_WORK = 100_000
MAX_CENSUS_WORK = 8_000_000
MAX_FRACTION_BITS = 65_536
MAX_EXACT_DEPTH = 32
MAX_CASE_SNAPSHOT_NODES = 1_024
MAX_SERIALIZED_JSON_NODES = 100_000
THRESHOLD = Fraction(1, 1000)
SOURCE_IDENTITY = "four-street-independent-exact-v2"
BUDGET_SCHEDULE_VERSION = "four-street-exact-work-v2"


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _safe_json_value(value, depth=0, budget=None):
    """Accept only inert JSON-compatible built-ins; do not invoke user hooks."""
    if budget is None:
        budget = [0]
    budget[0] += 1
    if budget[0] > MAX_SERIALIZED_JSON_NODES:
        raise ValueError("serialized policy exceeds the bounded JSON node count")
    if depth > 40:
        raise ValueError("serialized policy exceeds the bounded JSON depth")
    if value is None or type(value) in (str, int, bool):
        if type(value) is str and len(value) > numeric.MAX_RANGE_EXPRESSION_LENGTH:
            raise ValueError("serialized policy string exceeds the bounded length")
        return
    if type(value) is float:
        if not isfinite(value):
            raise ValueError("serialized policy contains a nonfinite number")
        return
    if type(value) in (list, tuple):
        for item in value:
            _safe_json_value(item, depth + 1, budget)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("serialized policy object keys must be strings")
            if len(key) > numeric.MAX_RANGE_EXPRESSION_LENGTH:
                raise ValueError("serialized policy key exceeds the bounded length")
            _safe_json_value(item, depth + 1, budget)
        return
    raise ValueError("serialized policy must contain only JSON-compatible built-ins")


def _fraction_text(value):
    """Format an admitted exact fraction without Python's global int digit cap."""
    if type(value) is not Fraction:
        raise TypeError("fraction text requires an exact Fraction")
    bits = max(abs(value.numerator).bit_length(), value.denominator.bit_length(), 1)
    if bits > MAX_FRACTION_BITS:
        raise ValueError("Exact rational certificate exceeds the 65536-bit limit")
    with localcontext() as context:
        context.prec = 1
        numerator = format(Decimal(value.numerator), "f")
        if value.denominator == 1:
            return numerator
        denominator = format(Decimal(value.denominator), "f")
        return numerator + "/" + denominator


def _snapshot_case(case):
    if type(case) is not dict:
        raise ValueError("case must be a plain bounded dictionary")
    budget = [0]

    def clone(value, depth=0):
        budget[0] += 1
        if budget[0] > MAX_CASE_SNAPSHOT_NODES:
            raise ValueError("case exceeds bounded total node count")
        if depth > 8:
            raise ValueError("case exceeds bounded configuration depth")
        if value is None or type(value) is bool:
            return value
        if type(value) is str:
            if len(value) > numeric.MAX_RANGE_EXPRESSION_LENGTH:
                raise ValueError("case string exceeds bounded input length")
            return value
        if type(value) is int:
            if value.bit_length() > MAX_FRACTION_BITS:
                raise ValueError("case integer exceeds bounded bit width")
            return value
        if type(value) is float:
            if not isfinite(value):
                raise ValueError("case float must be finite")
            return value
        if type(value) is Fraction:
            if (value.numerator.bit_length() > MAX_FRACTION_BITS or
                    value.denominator.bit_length() > MAX_FRACTION_BITS):
                raise ValueError("case fraction exceeds bounded bit width")
            return value
        if type(value) in (list, tuple):
            if len(value) > 128:
                raise ValueError("case sequence exceeds bounded input size")
            return tuple(clone(item, depth + 1) for item in value) if type(value) is tuple else [
                clone(item, depth + 1) for item in value]
        if type(value) is dict:
            if len(value) > 32 or any(
                    type(key) is not str or
                    len(key) > numeric.MAX_RANGE_EXPRESSION_LENGTH for key in value):
                raise ValueError("case mapping exceeds bounded plain-string fields")
            return {key: clone(item, depth + 1) for key, item in value.items()}
        raise ValueError("case must contain only bounded scalar/list/tuple/dict values")

    return clone(case)


def _canonical_hash(value):
    def safe(item):
        if isinstance(item, Fraction):
            return {"$fraction": _fraction_text(item)}
        if type(item) is dict:
            return {key: safe(child) for key, child in item.items()}
        if type(item) in (list, tuple):
            return [safe(child) for child in item]
        return item

    raw = json.dumps(safe(value), sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _children(node):
    if isinstance(node, numeric._Decision):
        return node.children
    if isinstance(node, numeric.Reveal):
        return tuple(node.branches.values())
    if isinstance(node, numeric._Terminal):
        return ()
    raise ValueError("numeric graph contains an unknown node")


def _validate_graph(model, budget=None):
    """Check the complete owned graph and its exact physical reveal partition."""
    if not isinstance(model, numeric.NumericModel):
        raise ValueError("a fresh independent numeric model is required")
    worlds = model.worlds
    _need(type(worlds) is tuple and 0 < len(worlds) <= numeric.MAX_WORLDS,
          "numeric graph has invalid bounded physical worlds")
    total_mass = Fraction(0)
    for world in worlds:
        _need(type(world) is dict and set(world) == {"hands", "board", "weight", "sign"},
              "numeric world has an invalid shape")
        _need(type(world["hands"]) is tuple and len(world["hands"]) == 2 and
              all(type(hand) is tuple and len(hand) == 2 and
                  all(type(card) is str for card in hand) for hand in world["hands"]),
              "numeric world has invalid global SB/BB hands")
        _need(type(world["board"]) is tuple and len(world["board"]) == 5 and
              len(set(world["board"])) == 5 and all(type(card) is str for card in world["board"]),
              "numeric world has invalid ordered board")
        _need(type(world["weight"]) is Fraction and world["weight"] > 0,
              "numeric world mass must be a positive exact fraction")
        _need(type(world["sign"]) is int and world["sign"] in (-1, 0, 1),
              "numeric world showdown sign must be -1, zero or one")
        if budget is not None:
            budget.charge("physical_mass_validation_additions")
            total_mass = budget.fraction(
                total_mass + budget.fraction(world["weight"], "physical world mass"),
                "physical world normalizer")
        else:
            total_mass += world["weight"]
    _need(total_mass == 1, "numeric physical world masses must sum exactly to one")

    active = set()
    visited = set()
    nodes = []
    decisions = []
    expected_infos = {}

    def visit(node, subset, depth, public_history):
        if budget is not None:
            budget.charge("tree_preflight_nodes")
        _need(depth <= MAX_EXACT_DEPTH, "exact certificate exceeds depth 32")
        identity = id(node)
        _need(identity not in active, "numeric graph contains a cycle")
        _need(identity not in visited, "numeric graph aliases a mutable node")
        active.add(identity)
        visited.add(identity)
        nodes.append(node)
        _need(len(nodes) <= numeric.MAX_STATES,
              "numeric graph exceeds its admitted state bound")
        if isinstance(node, numeric._Decision):
            _need(type(node.player) is int and node.player in (0, 1),
                  "numeric decision actor must be global SB or BB")
            _need(type(node.history) is tuple and node.history == public_history,
                  "numeric decision has a mismatched public history")
            _need(type(node.board) is tuple and len(node.board) in (0, 3, 4, 5),
                  "numeric decision has an invalid visible board")
            _need(all(world["board"][:len(node.board)] == node.board for world in subset),
                  "numeric decision includes a hidden or mismatched board")
            _need(type(node.actions) is tuple and type(node.children) is tuple and
                  len(node.actions) > 0 and len(node.actions) == len(node.children),
                  "numeric action/child vectors are omitted or misaligned")
            decisions.append(node)
            for world in subset:
                hand = "".join(world["hands"][node.player])
                key = (node.player, hand, node.history)
                previous = expected_infos.get(key)
                _need(previous is None or previous is node,
                      "numeric graph aliases incompatible information decisions")
                expected_infos[key] = node
            if budget is not None:
                budget.charge("tree_preflight_edges", len(node.children))
            for action, child in zip(node.actions, node.children):
                visit(child, subset, depth + 1,
                      public_history + (action.token,))
        elif isinstance(node, numeric.Reveal):
            _need(type(node.history) is tuple and node.history == public_history,
                  "numeric reveal has a mismatched public history")
            _need(type(node.board_length) is int and node.board_length in (3, 4, 5),
                  "numeric reveal board length is invalid")
            _need(type(node.branches) is dict and node.branches,
                  "numeric reveal has no public branches in its exact partition")
            expected_prefixes = {world["board"][:node.board_length] for world in subset}
            _need(set(node.branches) == expected_prefixes,
                  "numeric reveal branches do not partition the complete visible prefix")
            if budget is not None:
                budget.charge("tree_preflight_edges", len(node.branches))
            for prefix, child in node.branches.items():
                _need(type(prefix) is tuple and len(prefix) == node.board_length,
                      "numeric reveal key is not a complete visible prefix")
                child_worlds = tuple(world for world in subset
                                     if world["board"][:node.board_length] == prefix)
                _need(child_worlds, "numeric reveal contains an unreachable branch")
                child_node = child
                if isinstance(child_node, (numeric._Decision, numeric.Reveal)):
                    visible = child_node.board if isinstance(child_node, numeric._Decision) else None
                    if visible is not None:
                        _need(visible == prefix, "numeric reveal child board differs from its branch")
                if node.board_length == 3:
                    reveal_token = "flop@" + "".join(prefix)
                elif node.board_length == 4:
                    reveal_token = "turn@" + prefix[-1]
                else:
                    reveal_token = "river@" + prefix[-1]
                visit(child, child_worlds, depth + 1,
                      public_history + (reveal_token,))
        elif isinstance(node, numeric._Terminal):
            _need(node.kind in ("fold", "showdown"), "numeric terminal kind is invalid")
            _need(type(node.contributions) is tuple and len(node.contributions) == 2 and
                  all(type(value) in (int, float) and isfinite(float(value)) and value >= 0
                      for value in node.contributions),
                  "numeric terminal contributions are invalid")
            if node.kind == "fold":
                _need(type(node.winner) is int and node.winner in (0, 1),
                      "numeric fold terminal has an invalid global winner")
            else:
                _need(node.winner is None, "showdown terminal cannot declare a winner")
        else:
            raise ValueError("numeric graph contains an unknown node")
        active.remove(identity)

    visit(model.root, worlds, 1, ())
    _need(len(decisions) == len(model.decisions) and
          all(left is right for left, right in zip(decisions, model.decisions)),
          "numeric decision index differs from the independently traversed graph")
    _need(set(expected_infos) == set(model.expected_infos) and all(
        expected_infos[key] is model.expected_infos[key] for key in expected_infos),
        "numeric information rows do not exactly cover visible own-hand decisions")
    if budget is not None and len(nodes) > 1:
        # Every tree edge was reserved at its parent; this bound is checked
        # independently from the U3 graph construction receipt.
        recorded_edges = getattr(budget, "counters", getattr(budget, "counts", {}))
        _need(recorded_edges.get("tree_preflight_edges", 0) == len(nodes) - 1,
              "numeric graph is not a rooted tree")
    return tuple(nodes), tuple(decisions), expected_infos


def _model_identity(model):
    graph_rows = []
    nodes, decisions, _ = _validate_graph(model)
    for node in nodes:
        if isinstance(node, numeric._Decision):
            graph_rows.append({"type": "decision", "player": node.player,
                               "history": list(node.history), "board": list(node.board),
                               "actions": [{"name": action.name,
                                            "amount": action.amount,
                                            "raise_to": action.raise_to,
                                            "history_key": action.token}
                                           for action in node.actions]})
        elif isinstance(node, numeric.Reveal):
            graph_rows.append({"type": "reveal", "history": list(node.history),
                               "board_length": node.board_length,
                               "branches": [list(prefix) for prefix in node.branches]})
        else:
            graph_rows.append({"type": "terminal", "kind": node.kind,
                               "contributions": list(node.contributions),
                               "winner": node.winner})
    support = [{"hands": [list(hand) for hand in world["hands"]],
                "board": list(world["board"]), "weight": _fraction_text(world["weight"]),
                "sign": world["sign"]} for world in model.worlds]
    return _canonical_hash({"case": model.case, "support": support,
                            "graph": graph_rows, "rows": len(model.expected_infos)})


class _Counter:
    def __init__(self, limit=MAX_CENSUS_WORK):
        self.limit = limit
        self.work = 0
        self.counts = {}

    def charge(self, kind, amount=1):
        if type(amount) is not int or amount < 0:
            raise ValueError("certificate work reservation must be a nonnegative integer")
        if self.work + amount > self.limit:
            raise ValueError(
                f"Exact structural census exceeds its {self.limit}-work limit "
                f"at {self.work}+{amount}; partial counters={self.counts!r}")
        self.work += amount
        self.counts[kind] = self.counts.get(kind, 0) + amount

    def fraction(self, value, label):
        if not isinstance(value, Fraction):
            raise TypeError(f"{label} must be an exact Fraction")
        if max(abs(value.numerator).bit_length(), value.denominator.bit_length(), 1) > MAX_FRACTION_BITS:
            raise ValueError("physical mass exceeds the 65536-bit fraction limit")
        return value

class _ObservedBudget(rational._Budget):
    """Keep the source helper's fixed caps while retaining first-failure work."""

    def _with_receipt(self, operation, value, label=None):
        try:
            return operation(value) if label is None else operation(value, label)
        except (ValueError, TypeError, ZeroDivisionError) as exc:
            raise ValueError(
                f"{exc}; partial exact counters work={self.work} "
                f"width={self.max_observed_bits} by_kind={self.counters!r}") from exc

    def charge(self, kind, amount=1):
        return self._with_receipt(lambda value: super(_ObservedBudget, self).charge(kind, value),
                                  amount)

    def fraction(self, value, label):
        return self._with_receipt(lambda item, name: super(_ObservedBudget, self).fraction(item, name),
                                  value, label)

    def named_add(self, kind, left, right, label):
        self.charge(kind)
        return self.fraction(left + right, label)

    def named_subtract(self, kind, left, right, label):
        self.charge(kind)
        return self.fraction(left - right, label)

    def named_multiply(self, kind, left, right, label):
        self.charge(kind)
        return self.fraction(left * right, label)

    def named_divide(self, kind, left, right, label):
        if right == 0:
            raise ZeroDivisionError(f"{label} has a zero denominator")
        self.charge(kind)
        return self.fraction(left / right, label)

    def named_negate(self, kind, value, label):
        self.charge(kind)
        return self.fraction(-value, label)

    def named_abs(self, kind, value, label):
        self.charge(kind)
        return self.fraction(abs(value), label)


def _budget_add(budget, kind, left, right, label):
    if isinstance(budget, _ObservedBudget):
        return budget.named_add(kind, left, right, label)
    budget.charge(kind)
    return budget.fraction(left + right, label)


def _br_structure(root, worlds, player, counter, terminal_group_forecast_operator):
    counter.charge("br_own_hand_setup", len(worlds))
    hands = sorted({world["hands"][player] for world in worlds})

    def visit(node, own_hand, group, depth):
        counter.charge("br_node_group_visits")
        _need(depth <= MAX_EXACT_DEPTH, "best-response forecast exceeds depth 32")
        if not group:
            return
        if isinstance(node, numeric._Terminal):
            terminal_group_forecast_operator(counter, len(group), node=node, group=group, worlds=worlds)
            return
        if isinstance(node, numeric.Reveal):
            branch_count = len(node.branches)
            counter.charge("br_reveal_branch_slots", 2 * branch_count)
            counter.charge("br_reveal_group_scans", len(group))
            counter.charge("br_reveal_bucket_references", len(group))
            buckets = {prefix: [] for prefix in node.branches}
            for world_id in group:
                world = worlds[world_id]
                buckets[world["board"][:node.board_length]].append(world_id)
            for prefix, child in node.branches.items():
                visit(child, own_hand, tuple(buckets[prefix]), depth + 1)
            counter.charge("br_reveal_branch_sum_operations", branch_count)
            if player == 0:
                counter.charge("fused_profile_reveal_additions", branch_count)
                counter.charge("fused_result_slots", 2)
            return
        if node.player == player:
            counter.charge("br_own_action_slots", len(node.children))
            if player == 0:
                counter.charge("fused_profile_own_row_lookups")
                counter.charge("fused_profile_own_action_multiplications", len(node.children))
                counter.charge("fused_profile_own_action_additions", len(node.children))
            for child in node.children:
                visit(child, own_hand, group, depth + 1)
            counter.charge("br_own_action_selection_operations", max(0, len(node.children) - 1))
            if player == 0:
                counter.charge("fused_result_slots", 2)
            return
        action_count = len(node.children)
        counter.charge("br_opponent_action_group_slots", action_count)
        counter.charge("br_opponent_group_scans", len(group) * action_count)
        counter.charge("br_opponent_group_copies", len(group) * action_count)
        counter.charge("br_opponent_reach_multiplications", len(group) * action_count)
        for child in node.children:
            # Forecast every policy action as positive, independent of a saved
            # payload's zero probabilities.
            visit(child, own_hand, group, depth + 1)
        counter.charge("br_opponent_action_sum_operations", action_count)
        if player == 0:
            counter.charge("fused_profile_opponent_additions", action_count)
            counter.charge("fused_result_slots", 2)

    for own_hand in hands:
        counter.charge("br_own_hand_group_scans", len(worlds))
        group = tuple(index for index, world in enumerate(worlds)
                      if world["hands"][player] == own_hand)
        counter.charge("br_own_hand_group_copies", len(group))
        visit(root, own_hand, group, 1)
        counter.charge("br_own_hand_response_sums")
        if player == 0:
            counter.charge("fused_profile_root_additions")
    if player == 0:
        counter.charge("fused_result_slots", 2)


def _forecast_terminal_group_literal(counter, group_size, **_context):
    counter.charge("br_terminal_group_scans", group_size)
    counter.charge("br_terminal_conversions", group_size)
    counter.charge("br_terminal_fraction_operations", 2 * group_size)


def _forecast_model(model, terminal_group_forecast_operator, *, normalization_action_factor=4):
    counter = _Counter()
    nodes, decisions, infos = _validate_graph(model, counter)
    worlds = model.worlds
    counter.charge("physical_world_setup_entries", len(worlds))
    counter.charge("physical_mass_normalization_operations", 2 * len(worlds))
    counter.charge("policy_row_index_entries", len(infos))
    counter.charge("policy_row_sort_entries", len(infos))
    action_slots = sum(len(node.actions) for node in infos.values())
    counter.charge("policy_action_conversion_entries", action_slots)
    counter.charge("policy_fraction_operation_slots", normalization_action_factor * action_slots + len(infos))
    counter.charge("normalization_ledger_row_slots", len(infos))
    counter.charge("normalization_ledger_action_slots", action_slots)
    counter.charge("normalized_output_row_slots", len(infos))
    counter.charge("normalized_output_action_slots", action_slots)
    counter.charge("policy_hash_row_action_slots", len(infos) + action_slots)
    _br_structure(model.root, worlds, 0, counter, terminal_group_forecast_operator)
    _br_structure(model.root, worlds, 1, counter, terminal_group_forecast_operator)
    counter.charge("final_metric_fraction_operations", 12)
    counter.charge("certificate_output_entries", 24 + len(infos) + action_slots)
    return {"work": counter.work, "work_limit": MAX_EXACT_WORK,
            "admitted": counter.work <= MAX_EXACT_WORK,
            "excess_work": max(0, counter.work - MAX_EXACT_WORK),
            "work_by_kind": dict(sorted(counter.counts.items())),
            "tree_nodes": len(nodes), "tree_decisions": len(decisions),
            "tree_depth": model.counts["depth"], "worlds": len(worlds),
            "information_rows": len(infos), "action_slots": action_slots,
            "maximum_depth": MAX_EXACT_DEPTH,
            "maximum_fraction_bits": MAX_FRACTION_BITS}


def _structural_preparation_receipt(census, passes):
    """Bound graph validation/identity preparation separately from exact work."""
    _need(type(passes) is int and passes in (2, 3),
          "structural preparation requires two or three owned-graph walks")
    states = census["tree_nodes"]
    decisions = census["tree_decisions"]
    worlds = census["worlds"]
    per_pass = {
        "world_scan_entries": 4 * states * worlds,
        "copied_world_references": states * worlds,
        "information_key_iterations": decisions * worlds,
        "physical_mass_validation_additions": worlds,
    }
    complete = {name: count * passes for name, count in per_pass.items()}
    total = sum(complete.values())
    _need(total <= MAX_CENSUS_WORK,
          "structural preparation exceeds its 8000000-entry limit")
    return {
        "owned_graph_validation_walks": passes,
        "per_walk_upper_bounds": per_pass,
        "full_call_upper_bounds": complete,
        "total_entries_upper_bound": total,
        "entry_limit": MAX_CENSUS_WORK,
        "admitted": True,
        "scope": (
            "Separately bounded structural scans, reference copies, information indexing "
            "and identity validation. Existing named exact node/edge and mass charges "
            "remain unchanged. These conservative envelopes can overlap; they are not "
            "Python-operation, byte, runtime or RSS totals."
        ),
    }


def _forecast_model_record(model, forecast, source_identity, budget_schedule_version, model_forecaster=None):
    forecast.update({"source_identity": source_identity,
                     "budget_schedule_version": budget_schedule_version,
                     "model_sha256": _model_identity(model),
                     "input_case_canonical_sha256": _canonical_hash(model.case),
                     "preparation_receipts": {
                         "structural_graph_validation": _structural_preparation_receipt(forecast, 2),
                         "independent_model_build": {
                             "worlds": len(model.worlds),
                             "public_states": model.counts["public_states"],
                             "decisions": model.counts["decisions"],
                             "information_rows": model.counts["infos"]},
                         "model_identity_hash": {
                             "tree_nodes": forecast["tree_nodes"],
                             "information_rows": forecast["information_rows"],
                             "action_slots": forecast["action_slots"],
                             "worlds": forecast["worlds"]}}})
    return forecast


def _prepare_forecast(safe_case, terminal_group_forecast_operator):
    model = numeric.build_model(safe_case)
    forecast = _forecast_model(model, terminal_group_forecast_operator)
    return model, forecast


def forecast_exact(case):
    """Admit the full shape/support without consulting trained probabilities."""
    safe_case = _snapshot_case(case)
    model, forecast = _prepare_forecast(safe_case, _forecast_terminal_group_literal)
    return _forecast_model_record(model, forecast, SOURCE_IDENTITY,
                                  BUDGET_SCHEDULE_VERSION)


def _normalise_policy(model, payload, checked, budget, *, row_extremum=False):
    rows = payload["strategy"]
    budget.charge("policy_row_index_entries", len(rows))
    budget.charge("policy_row_sort_entries", len(model.expected_infos))
    source_rows = {}
    for row in rows:
        key = numeric._row_key(row)
        source_rows[key] = row
    keys = sorted(checked)
    action_slot_count = sum(len(node.actions) for node in model.expected_infos.values())
    budget.charge("policy_action_conversion_entries", action_slot_count)
    budget.charge("normalization_ledger_row_slots", len(keys))
    budget.charge("normalization_ledger_action_slots", action_slot_count)
    budget.charge("normalized_output_row_slots", len(keys))
    budget.charge("normalized_output_action_slots", action_slot_count)
    normalized = {}
    ledger = []
    normalized_rows = []
    max_adjustment = Fraction(0)
    for key in keys:
        row = source_rows[key]
        raw_values = checked[key]
        raw = tuple(rational._input_fraction(value, budget, "serialized probability")
                    for value in raw_values)
        total = Fraction(0)
        for value in raw:
            total = budget.named_add("policy_fraction_operation_slots", total, value,
                                     "serialized row probability sum")
        if total <= 0:
            raise ValueError("serialized policy row has zero probability mass")
        probabilities = tuple(budget.named_divide("policy_fraction_operation_slots", value,
                                                   total, "normalized row probability")
                              for value in raw)
        normalized[key] = probabilities
        action_entries = []
        normalized_actions = []
        row_max_raw = None
        row_max_adjustment = None
        for index, (before, after, action) in enumerate(zip(raw, probabilities, row["actions"])):
            adjustment = budget.named_subtract("policy_fraction_operation_slots", after,
                                               before, "policy normalization adjustment")
            if row_extremum:
                if row_max_raw is None or before > row_max_raw:
                    row_max_raw = before
                    row_max_adjustment = adjustment
            else:
                magnitude = budget.named_abs("policy_fraction_operation_slots", adjustment,
                                             "policy normalization adjustment magnitude")
                max_adjustment = max(max_adjustment, magnitude)
            action_entries.append({"index": index, "name": action["name"],
                                   "history_key": action["history_key"],
                                   "raw_binary64_fraction": _fraction_text(before),
                                   "normalized_fraction": _fraction_text(after),
                                   "adjustment_fraction": _fraction_text(adjustment),
                                   "adjustment_float": float(adjustment)})
            normalized_actions.append({"name": action["name"],
                                       "amount": action["amount"],
                                       "raise_to": action["raise_to"],
                                       "history_key": action["history_key"],
                                       "probability_fraction": _fraction_text(after)})
        if row_extremum:
            _need(row_max_adjustment is not None,
                  "normalized policy row has no action for its adjustment extremum")
            magnitude = budget.named_abs(
                "policy_fraction_operation_slots", row_max_adjustment,
                "policy normalization row-extremum adjustment magnitude")
            max_adjustment = max(max_adjustment, magnitude)
        ledger.append({"player": row["player"], "hand": row["hand"],
                      "revealed_board": row["revealed_board"],
                      "history": row["history"],
                      "raw_row_sum_fraction": _fraction_text(total), "actions": action_entries})
        normalized_rows.append({"player": row["player"], "hand": row["hand"],
                                "street": row["street"],
                                "revealed_board": row["revealed_board"],
                                "history": row["history"], "actions": normalized_actions})
    _need(set(normalized) == set(model.expected_infos),
          "normalized policy rows do not cover the complete independent model")
    return normalized, ledger, normalized_rows, max_adjustment


def _terminal_value(node, world, budget):
    matched = min(node.contributions)
    sign = node.winner if node.kind == "fold" else world["sign"]
    if node.kind == "fold":
        sign = 1 if node.winner == 0 else -1
    payoff = float(sign) * float(matched)
    if not isfinite(payoff):
        raise ValueError("exact terminal payoff is nonfinite")
    budget.charge("br_terminal_conversions")
    return rational._input_fraction(payoff, budget, "binary64 terminal payoff")


def _terminal_group_literal(node, group, budget, contribution_label, sum_label):
    """Preserve the v2 per-world terminal conversion and summation order."""
    budget.charge("br_terminal_group_scans", len(group))
    total = Fraction(0)
    for world, mass in group:
        payoff = _terminal_value(node, world, budget)
        total = _budget_add(
            budget, "br_terminal_fraction_operations", total,
            budget.named_multiply("br_terminal_fraction_operations", mass,
                                  payoff, contribution_label),
            sum_label)
    return total


def _fused_sb(model, policies, budget, terminal_group_operator):
    """Compute SB legal BR and profile EV together, sharing terminal/future work."""
    worlds = model.worlds
    budget.charge("br_own_hand_setup", len(worlds))
    own_hands = sorted({world["hands"][0] for world in worlds})

    def visit(node, own_hand, group, depth):
        budget.charge("br_node_group_visits")
        if depth > MAX_EXACT_DEPTH:
            raise ValueError("fused SB traversal exceeds depth 32")
        if not group:
            return Fraction(0)
        if isinstance(node, numeric._Terminal):
            return terminal_group_operator(
                node, group, budget,
                "fused terminal contribution", "fused terminal sum")
        if isinstance(node, numeric.Reveal):
            budget.charge("br_reveal_branch_slots", 2 * len(node.branches))
            budget.charge("br_reveal_group_scans", len(group))
            budget.charge("br_reveal_bucket_references", len(group))
            buckets = {prefix: [] for prefix in node.branches}
            for entry in group:
                buckets[entry[0]["board"][:node.board_length]].append(entry)
            best_total = Fraction(0)
            profile_total = Fraction(0)
            for prefix, child in node.branches.items():
                result = visit(child, own_hand, tuple(buckets[prefix]), depth + 1)
                if type(result) is tuple:
                    best, profile = result
                else:
                    best = profile = result
                best_total = _budget_add(
                    budget, "br_reveal_branch_sum_operations", best_total, best,
                    "fused BR reveal sum")
                profile_total = _budget_add(
                    budget, "fused_profile_reveal_additions", profile_total, profile,
                    "fused profile reveal sum")
            budget.charge("fused_result_slots", 2)
            return best_total, profile_total
        if node.player == 0:
            budget.charge("br_own_action_slots", len(node.children))
            budget.charge("fused_profile_own_row_lookups")
            key = (0, "".join(own_hand), node.history)
            row = policies[key]
            best_values = []
            profile_total = Fraction(0)
            for probability, child in zip(row, node.children):
                result = visit(child, own_hand, group, depth + 1)
                if type(result) is tuple:
                    best, profile = result
                else:
                    best = profile = result
                best_values.append(best)
                weighted = budget.named_multiply(
                    "fused_profile_own_action_multiplications", probability,
                    profile, "fused own action profile value")
                profile_total = _budget_add(
                    budget, "fused_profile_own_action_additions", profile_total,
                    weighted, "fused own action profile sum")
            budget.charge("br_own_action_selection_operations", max(0, len(best_values) - 1))
            budget.charge("fused_result_slots", 2)
            return max(best_values), profile_total

        action_count = len(node.children)
        budget.charge("br_opponent_action_group_slots", action_count)
        budget.charge("br_opponent_group_scans", len(group) * action_count)
        budget.charge("br_opponent_group_copies", len(group) * action_count)
        action_groups = [[] for _ in node.children]
        for world, mass in group:
            key = (1, "".join(world["hands"][1]), node.history)
            row = policies[key]
            for index, probability in enumerate(row):
                if probability:
                    updated = budget.named_multiply(
                        "br_opponent_reach_multiplications", mass, probability,
                        "BB policy reach")
                    action_groups[index].append((world, updated))
        best_total = Fraction(0)
        profile_total = Fraction(0)
        for child, action_group in zip(node.children, action_groups):
            result = visit(child, own_hand, tuple(action_group), depth + 1)
            if type(result) is tuple:
                best, profile = result
            else:
                best = profile = result
            best_total = _budget_add(
                budget, "br_opponent_action_sum_operations", best_total, best,
                "fused BR opponent action sum")
            profile_total = _budget_add(
                budget, "fused_profile_opponent_additions", profile_total, profile,
                "fused profile opponent action sum")
        budget.charge("fused_result_slots", 2)
        return best_total, profile_total

    def root_value():
        best_total = Fraction(0)
        profile_total = Fraction(0)
        for own_hand in own_hands:
            budget.charge("br_own_hand_group_scans", len(worlds))
            group = tuple((world, world["weight"]) for world in worlds
                          if world["hands"][0] == own_hand)
            budget.charge("br_own_hand_group_copies", len(group))
            result = visit(model.root, own_hand, group, 1)
            if type(result) is tuple:
                best, profile = result
            else:
                best = profile = result
            best_total = _budget_add(
                budget, "br_own_hand_response_sums", best_total, best,
                "fused SB root response sum")
            profile_total = _budget_add(
                budget, "fused_profile_root_additions", profile_total, profile,
                "fused profile root sum")
        budget.charge("fused_result_slots", 2)
        return best_total, profile_total

    return root_value()


def _best_response(model, policies, player, budget, terminal_group_operator):
    worlds = model.worlds
    budget.charge("br_own_hand_setup", len(worlds))
    own_hands = sorted({world["hands"][player] for world in worlds})

    def visit(node, own_hand, group, depth):
        budget.charge("br_node_group_visits")
        if depth > MAX_EXACT_DEPTH:
            raise ValueError("best-response traversal exceeds depth 32")
        if not group:
            return Fraction(0)
        if isinstance(node, numeric._Terminal):
            return terminal_group_operator(
                node, group, budget,
                "BR terminal contribution", "BR terminal group sum")
        if isinstance(node, numeric.Reveal):
            budget.charge("br_reveal_branch_slots", 2 * len(node.branches))
            budget.charge("br_reveal_group_scans", len(group))
            budget.charge("br_reveal_bucket_references", len(group))
            buckets = {prefix: [] for prefix in node.branches}
            for entry in group:
                buckets[entry[0]["board"][:node.board_length]].append(entry)
            total = Fraction(0)
            for prefix, child in node.branches.items():
                branch = visit(child, own_hand, tuple(buckets[prefix]), depth + 1)
                total = _budget_add(budget, "br_reveal_branch_sum_operations", total,
                                    branch, "BR reveal branch sum")
            return total
        if node.player == player:
            budget.charge("br_own_action_slots", len(node.children))
            values = [visit(child, own_hand, group, depth + 1)
                      for child in node.children]
            budget.charge("br_own_action_selection_operations", max(0, len(values) - 1))
            if player == 0:
                return max(values)
            return min(values)
        action_count = len(node.children)
        budget.charge("br_opponent_action_group_slots", action_count)
        budget.charge("br_opponent_group_scans", len(group) * action_count)
        budget.charge("br_opponent_group_copies", len(group) * action_count)
        action_groups = [[] for _ in node.children]
        for world, mass in group:
            key = (node.player, "".join(world["hands"][node.player]), node.history)
            row = policies[key]
            for index, probability in enumerate(row):
                if probability:
                    action_groups[index].append((
                        world, budget.named_multiply("br_opponent_reach_multiplications",
                                                     mass, probability,
                                                     "opponent policy reach")))
        total = Fraction(0)
        for child, action_group in zip(node.children, action_groups):
            if action_group:
                total = _budget_add(budget, "br_opponent_action_sum_operations", total,
                                    visit(child, own_hand, tuple(action_group), depth + 1),
                                    "BR opponent action sum")
        return total

    response = Fraction(0)
    for own_hand in own_hands:
        budget.charge("br_own_hand_group_scans", len(worlds))
        group = tuple((world, world["weight"]) for world in worlds
                      if world["hands"][player] == own_hand)
        budget.charge("br_own_hand_group_copies", len(group))
        response = _budget_add(budget, "br_own_hand_response_sums", response,
                               visit(model.root, own_hand, group, 1),
                               "BR own-hand response sum")
    return response if player == 0 else response


def _evaluate_with_operators(case, payload, *, terminal_group_operator,
                             terminal_group_forecast_operator, normalizer,
                             source_identity, budget_schedule_version, model_forecaster=None):
    """Private orchestration for fixed trusted exact operators."""
    safe_case = _snapshot_case(case)
    if type(payload) is not dict:
        raise ValueError("payload must be a plain serialized mapping")
    if len(payload) > 128 or type(payload.get("strategy")) is not list or \
            len(payload["strategy"]) > numeric.MAX_ROWS:
        raise ValueError("payload exceeds bounded four-street result shape")
    json_nodes = [0]
    _safe_json_value(payload, budget=json_nodes)
    if model_forecaster is None:
        model, forecast = _prepare_forecast(safe_case, terminal_group_forecast_operator)
    else:
        model = numeric.build_model(safe_case)
        forecast = model_forecaster(model, 3)
    if not forecast["admitted"]:
        raise ValueError(
            f"exact certificate forecast exceeds its hard work limit: "
            f"forecast={forecast['work']} limit={MAX_EXACT_WORK} "
            f"counters={forecast['work_by_kind']!r}")
    budget = _ObservedBudget(MAX_EXACT_WORK, MAX_EXACT_DEPTH, MAX_FRACTION_BITS)
    budget.charge("physical_world_setup_entries", len(model.worlds))
    budget.charge("physical_mass_normalization_operations", 2 * len(model.worlds))
    _validate_graph(model, budget)
    policies_float = numeric.validate_policy(model, payload)
    normalized, ledger, normalized_rows, max_adjustment = normalizer(
        model, payload, policies_float, budget)
    br_sb, value = _fused_sb(model, normalized, budget, terminal_group_operator)
    min_sb = _best_response(model, normalized, 1, budget, terminal_group_operator)
    br_bb = budget.named_negate("final_metric_fraction_operations", min_sb,
                                "BB best response in SB coordinates")
    lower = min_sb
    upper = br_sb
    if not lower <= value <= upper:
        raise ValueError("exact legal-response interval does not contain policy value")
    negative_value = budget.named_negate("final_metric_fraction_operations", value,
                                         "negative profile value")
    negative_lower = budget.named_negate("final_metric_fraction_operations", lower,
                                         "negative lower response bound")
    gain_sb = budget.named_add("final_metric_fraction_operations", upper, negative_value,
                               "SB unilateral response gain")
    gain_bb = budget.named_add("final_metric_fraction_operations", value, negative_lower,
                               "BB unilateral response gain")
    if gain_sb < 0 or gain_bb < 0:
        raise ValueError("exact unilateral response gain is negative")
    nash_conv = budget.named_add("final_metric_fraction_operations", upper, negative_lower,
                                 "exact NashConv")
    exploitability = budget.named_divide("final_metric_fraction_operations", nash_conv,
                                         Fraction(2), "exact exploitability")
    budget.charge("certificate_output_entries", 24 + len(normalized_rows) +
                  sum(len(row["actions"]) for row in normalized_rows))
    metrics = {"value_sb": value, "value_bb": negative_value,
               "sb_best_response_value": br_sb, "bb_best_response_value": br_bb,
               "sb_best_response_gain": gain_sb, "bb_best_response_gain": gain_bb,
               "nash_conv": nash_conv, "exploitability": exploitability,
               "lower_value_bound": lower, "upper_value_bound": upper}
    for name, result in metrics.items():
        budget.fraction(result, name)

    budget.charge("policy_hash_row_action_slots", len(normalized_rows) +
                  sum(len(row["actions"]) for row in normalized_rows))
    normalized_policy_hash = _canonical_hash(normalized_rows)
    input_policy_hash = _canonical_hash(payload)
    float_replay = numeric.replay_policy(payload, safe_case)
    float_comparison = {}
    for key in ("value_sb", "value_bb", "sb_best_response_value",
                "bb_best_response_value", "nash_conv"):
        exact_float = float(metrics[key])
        observed = float_replay[key]
        difference = abs(exact_float - float(observed))
        if difference > 1e-9:
            raise ValueError(f"exact and independent floating replay disagree for {key}")
        float_comparison[key] = {"exact_float": exact_float, "independent_float": observed,
                                 "absolute_difference": difference}
    actual_work = budget.work
    forecast_by_kind = forecast["work_by_kind"]
    actual_by_kind = budget.counters
    unknown_actual = set(actual_by_kind) - set(forecast_by_kind)
    if unknown_actual:
        raise ValueError(f"actual exact work has unforecast families: {sorted(unknown_actual)!r}")
    if sum(forecast_by_kind.values()) != forecast["work"]:
        raise ValueError("shape-only forecast family counters do not sum to total work")
    if sum(actual_by_kind.values()) != actual_work:
        raise ValueError("runtime family counters do not sum to actual work")
    exceeded = {kind: (count, forecast_by_kind[kind])
                for kind, count in actual_by_kind.items()
                if count > forecast_by_kind[kind]}
    if exceeded:
        raise ValueError(f"actual exact work exceeded forecast families: {exceeded!r}")
    if actual_work > forecast["work"]:
        raise ValueError("actual exact work exceeded the shape-only forecast")
    return {"schema_version": 1, "source_identity": source_identity,
            "budget_schedule_version": budget_schedule_version,
            "model_sha256": _model_identity(model),
            "input_case_canonical_sha256": _canonical_hash(model.case),
            "input_policy_canonical_sha256": input_policy_hash,
            "normalized_policy_sha256": normalized_policy_hash,
            "metrics": {key: _fraction_text(result) for key, result in metrics.items()},
            "threshold": _fraction_text(THRESHOLD),
            "threshold_met": nash_conv <= THRESHOLD,
            "normalization_ledger": ledger,
            "normalized_policy_rows": normalized_rows,
            "maximum_row_adjustment": _fraction_text(max_adjustment),
            "floating_replay": float_replay,
            "floating_comparison": float_comparison,
            "preparation_receipts": {
                "input_policy_canonical_hash_json_nodes": json_nodes[0],
                "structural_graph_validation": _structural_preparation_receipt(forecast, 3),
                "model_identity_hash": {
                    "tree_nodes": forecast["tree_nodes"],
                    "information_rows": forecast["information_rows"],
                    "action_slots": forecast["action_slots"],
                    "worlds": forecast["worlds"]},
                "independent_numeric_replay": {
                    "worlds": model.counts["worlds"],
                    "public_states": model.counts["public_states"],
                    "information_rows": model.counts["infos"]}},
            "forecast": forecast,
            "actual_work": actual_work,
            "actual_work_by_kind": dict(sorted(budget.counters.items())),
            "maximum_fraction_bits": budget.max_observed_bits,
            "fraction_bit_limit": MAX_FRACTION_BITS,
            "work_limit": MAX_EXACT_WORK,
            "depth_limit": MAX_EXACT_DEPTH}


def evaluate_exact(case, payload):
    """Return exact profile EV, legal grouped BR bounds and normalization proof."""
    return _evaluate_with_operators(
        case, payload,
        terminal_group_operator=_terminal_group_literal,
        terminal_group_forecast_operator=_forecast_terminal_group_literal,
        normalizer=_normalise_policy,
        source_identity=SOURCE_IDENTITY,
        budget_schedule_version=BUDGET_SCHEDULE_VERSION)
