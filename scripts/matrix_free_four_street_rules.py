"""Independent bounded public betting tree for the matrix-free certificate.

This module builds public game structure only. It never constructs private
opponent pairs, deal worlds, hand ranks, terminal utilities, or a training tree.
Physical support and payoffs belong to the separately budgeted PayoffModel.
"""
from dataclasses import dataclass, replace as _replace
from fractions import Fraction
from math import isfinite
from types import MappingProxyType

from pokerlab.cards import DECK, cards, expand_range
from scripts import preflop_validation as money_rules
from scripts.matrix_free_certificate_budget import Budget


MAX_HANDS_PER_SEAT = 16
MAX_SELECTED_OUTCOMES = 64
MAX_PUBLIC_NODES = 250_000
MAX_PUBLIC_DEPTH = 64
MAX_CASE_ID_LENGTH = 128
MAX_RANGE_EXPRESSION_LENGTH = 4096
MAX_RUNOUT_TEXT_LENGTH = 128
MAX_STAGE_SIZES = 8
MAX_ACTIONS_PER_DECISION = 20
MAX_NUMERIC_INPUT_BITS = 4096
_FLOAT_CONVERSION_WORK_UPPER = 2300
EPS = 1e-9
_CARD_ORDER = {card: index for index, card in enumerate(DECK)}
_CASE_FIELDS = frozenset({"id", "sb_range", "bb_range", "config", "runouts",
                          "flop_config", "turn_config", "river_config"})


@dataclass(frozen=True)
class Action:
    """A public legal action with the literal full-history token."""

    name: str
    amount: float
    raise_to: float
    token: str


@dataclass(frozen=True)
class Decision:
    player: int
    history: tuple
    board: tuple
    actions: tuple
    children: tuple


@dataclass(frozen=True)
class Reveal:
    history: tuple
    board_length: int
    branches: object


@dataclass(frozen=True)
class Terminal:
    kind: str
    committed: tuple
    winner: int | None
    board: tuple
    history: tuple
    matched: float


@dataclass(frozen=True)
class _RevealStart:
    state: object
    board_length: int


@dataclass(frozen=True)
class _TerminalStart:
    state: object
    winner: int | None = None


@dataclass(frozen=True)
class PublicModel:
    case: dict
    ranges: tuple
    outcomes: tuple
    root: object
    decisions: tuple
    counts: dict


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _limits_snapshot(limits):
    allowed = {"hands_per_seat", "selected_outcomes", "public_nodes", "public_depth"}
    if limits is None:
        supplied = {}
    else:
        _need(type(limits) is dict and len(limits) <= len(allowed),
              "public-model limits must be a bounded plain mapping")
        supplied = dict(limits)
    _need(not (set(supplied) - allowed), "unknown public-model limit")
    ceilings = {"hands_per_seat": MAX_HANDS_PER_SEAT,
                "selected_outcomes": MAX_SELECTED_OUTCOMES,
                "public_nodes": MAX_PUBLIC_NODES,
                "public_depth": MAX_PUBLIC_DEPTH}
    for key, value in supplied.items():
        _need(type(value) is int and 0 < value <= ceilings[key],
              "public-model limits must be positive integers and reduce-only")
        ceilings[key] = value
    return ceilings


def _checked_budget(budget):
    if budget is None:
        return Budget()
    _need(callable(getattr(budget, "charge", None)) and
          callable(getattr(budget, "entries", None)),
          "budget must provide charge(kind, n) and entries(n, label)")
    return budget


def _numeric_float(value, label, budget):
    """Convert only bounded builtin numeric inputs after charging the budget."""
    _need(type(value) in (int, float, Fraction),
          f"{label} must be an exact int, float or Fraction")
    budget.charge("numeric_input_conversion_upper", 64)
    budget.entries(4, f"{label} numeric conversion scratch")
    if type(value) is int:
        _need(value.bit_length() <= MAX_NUMERIC_INPUT_BITS,
              f"{label} integer exceeds {MAX_NUMERIC_INPUT_BITS} bits")
    elif type(value) is Fraction:
        _need(value.numerator.bit_length() <= MAX_NUMERIC_INPUT_BITS and
              value.denominator.bit_length() <= MAX_NUMERIC_INPUT_BITS,
              f"{label} fraction exceeds {MAX_NUMERIC_INPUT_BITS} bits")
    # Budget.input forecasts the exact Fraction snapshot/bit width before
    # conversion, and type(value) above prevents custom __float__ hooks.
    budget.input(value, label)
    budget.charge("bounded_float_conversion_work_upper",
                  _FLOAT_CONVERSION_WORK_UPPER)
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} cannot be converted to finite binary64") from exc
    _need(isfinite(number), f"{label} must be finite")
    return number


def _money(value, label, budget, *, positive=False):
    number = _numeric_float(value, label, budget)
    _need(abs(number) <= 1_000_000 and (not positive or number >= 1e-9),
          f"{label} is outside supported money bounds")
    cleaned = round(number, 9)
    cleaned = 0.0 if cleaned == 0 else cleaned
    budget.charge("money_quantization_work_upper", 32)
    budget.entries(2, f"{label} quantized money")
    # Reserving the rounded binary64 input is a conservative forecast for the
    # small decimal Fraction constructed from its 9-digit cleaned spelling.
    budget.input(cleaned, f"{label} quantized money forecast")
    return cleaned


def _stage(value, inherited, label, budget):
    stage = dict(inherited)
    if value is not None:
        _need(type(value) is dict, f"{label} must be a plain mapping")
        _need(not (set(value) - {"bet_sizes", "raise_sizes", "max_raises", "include_all_in"}),
              f"{label} has unknown fields")
        stage.update(value)
    for field in ("bet_sizes", "raise_sizes"):
        raw = stage[field]
        _need(type(raw) in (list, tuple) and len(raw) <= MAX_STAGE_SIZES,
              f"{label} {field} must have at most {MAX_STAGE_SIZES} entries")
        converted = []
        for item in raw:
            number = _numeric_float(item, f"{label} {field}", budget)
            _need(isfinite(number) and 1e-9 <= number <= 1_000_000,
                  f"{label} {field} contains an unsupported size")
            converted.append(number)
        stage[field] = tuple(sorted(set(converted)))
    _need(bool(stage["bet_sizes"]), f"{label} needs at least one bet size")
    _need(type(stage["max_raises"]) is int and 0 <= stage["max_raises"] <= 8,
          f"{label} max_raises is invalid")
    _need(type(stage["include_all_in"]) is bool, f"{label} include_all_in is invalid")
    return stage


def _expand_bounded_range(text, label, max_hands, budget):
    _need(type(text) is str and 0 < len(text) <= MAX_RANGE_EXPRESSION_LENGTH,
          f"{label} must be a nonempty range string up to {MAX_RANGE_EXPRESSION_LENGTH} characters")
    budget.charge("range_text_scan", len(text))
    token_count = len(text.replace(",", " ").split())
    _need(0 < token_count <= len(text), f"{label} has no valid range tokens")
    # `random` visits all 1,326 physical holdings for each token. Charge this
    # conservative parser ceiling before handing text to the range expander.
    budget.charge("range_expansion_visits_upper", 1326 * token_count)
    budget.entries(2 * 1326 + 16, f"{label} parser scratch")
    expanded = expand_range(text)
    _need(0 < len(expanded) <= max_hands,
          f"{label} exceeds the {max_hands}-holding research cap")
    snapshot = {}
    for hand, weight in expanded.items():
        _need(type(hand) is tuple and len(hand) == 2 and hand[0] in DECK and hand[1] in DECK and
              hand[0] < hand[1], f"{label} contains a noncanonical holding")
        number = float(weight)
        _need(isfinite(number) and number > 0,
              f"{label} weights must be finite and positive")
        snapshot[hand] = number
    budget.entries(len(snapshot), f"{label} retained holdings")
    return snapshot


def _snapshot_inputs(case, budget, limits):
    _need(type(case) is dict and set(case) == _CASE_FIELDS,
          "case must contain exactly the declared four-street fields")
    case_id = case["id"]
    _need(type(case_id) is str and case_id.strip() and len(case_id) <= MAX_CASE_ID_LENGTH,
          "case id must be a bounded nonblank string")
    budget.charge("case_metadata_scan", len(case_id) + len(_CASE_FIELDS))

    max_hands = limits["hands_per_seat"]
    ranges = (_expand_bounded_range(case["sb_range"], "small-blind range", max_hands, budget),
              _expand_bounded_range(case["bb_range"], "big-blind range", max_hands, budget))

    raw_config = case["config"]
    _need(type(raw_config) is dict, "config must be a plain mapping")
    allowed = {"starting_stack", "small_blind", "big_blind", "raise_sizes",
               "max_raises", "include_all_in"}
    _need(not (set(raw_config) - allowed), "config has unknown fields")
    budget.charge("config_validation", len(raw_config) + 8)
    stack_raw = raw_config.get("starting_stack", 100)
    if type(stack_raw) in (list, tuple):
        _need(len(stack_raw) == 2, "starting_stack must be scalar or a pair")
        stacks = tuple(_money(value, "starting_stack", budget, positive=True)
                       for value in stack_raw)
    else:
        stacks = (_money(stack_raw, "starting_stack", budget, positive=True),) * 2
    sb_blind = _money(raw_config.get("small_blind", 0.5), "small_blind", budget, positive=True)
    bb_blind = _money(raw_config.get("big_blind", 1), "big_blind", budget, positive=True)
    _need(all(stack > 0 for stack in stacks), "starting stacks must be positive")
    _need(sb_blind < bb_blind and sb_blind > Fraction(1, 1_000_000_000) and
          bb_blind - sb_blind > Fraction(1, 1_000_000_000),
          "blinds and their difference must exceed the 1e-9-chip tolerance")

    budget.entries(96, "normalized configuration and case snapshot")
    preflop = _stage({"raise_sizes": raw_config.get("raise_sizes", [1]),
                      "max_raises": raw_config.get("max_raises", 3),
                      "include_all_in": raw_config.get("include_all_in", True)},
                     {"bet_sizes": (0.5,), "raise_sizes": (1.0,),
                      "max_raises": 3, "include_all_in": True}, "preflop config", budget)
    defaults = {"bet_sizes": (0.5,), "raise_sizes": (), "max_raises": 0,
                "include_all_in": True}
    flop = _stage(case["flop_config"], defaults, "flop_config", budget)
    turn = _stage(case["turn_config"], flop, "turn_config", budget)
    river = _stage(case["river_config"], flop, "river_config", budget)
    stages = {0: preflop, 3: flop, 4: turn, 5: river}

    raw_runouts = case["runouts"]
    _need(type(raw_runouts) in (list, tuple) and
          0 < len(raw_runouts) <= limits["selected_outcomes"],
          f"runouts must contain 1 through {limits['selected_outcomes']} outcomes")
    budget.charge("runout_validation", sum(len(item) if type(item) is str else 0
                                             for item in raw_runouts) + 12 * len(raw_runouts))
    budget.entries(5 * len(raw_runouts) + 16, "selected outcome snapshot")
    outcomes = []
    seen = set()
    for raw in raw_runouts:
        _need(type(raw) is str and len(raw) <= MAX_RUNOUT_TEXT_LENGTH,
              "each runout must be a bounded five-card string")
        parsed = cards(raw, 5)
        outcome = tuple(sorted(parsed[:3], key=_CARD_ORDER.__getitem__)) + parsed[3:]
        _need(outcome not in seen, "duplicate canonical flop and ordered runout")
        seen.add(outcome)
        outcomes.append(outcome)
    outcomes.sort(key=lambda board: tuple(_CARD_ORDER[card] for card in board))

    def stage_snapshot(stage):
        return {"bet_sizes": tuple(stage["bet_sizes"]),
                "raise_sizes": tuple(stage["raise_sizes"]),
                "max_raises": stage["max_raises"],
                "include_all_in": stage["include_all_in"]}

    config_snapshot = {
        "starting_stack": tuple(stacks) if type(stack_raw) in (list, tuple) else stacks[0],
        "small_blind": sb_blind, "big_blind": bb_blind,
        "raise_sizes": tuple(preflop["raise_sizes"]),
        "max_raises": preflop["max_raises"],
        "include_all_in": preflop["include_all_in"],
    }
    case_snapshot = {
        "id": case_id, "sb_range": case["sb_range"], "bb_range": case["bb_range"],
        "config": config_snapshot,
        "runouts": tuple(" ".join(board) for board in outcomes),
        "flop_config": stage_snapshot(flop), "turn_config": stage_snapshot(turn),
        "river_config": stage_snapshot(river),
    }
    return case_snapshot, ranges, tuple(outcomes), stacks, sb_blind, bb_blind, stages


def _actions_for(state, stacks, stages, budget):
    player, other = state.player, 1 - state.player
    global_own = float(state.committed[player])
    global_theirs = float(state.committed[other])
    origin = 0.0 if state.origin is None else state.origin
    if state.local_committed is None:
        own, theirs = global_own, global_theirs
    else:
        own, theirs = state.local_committed[player], state.local_committed[other]
    local_stack = _money(float(stacks[player]) - origin, "local stack", budget)
    other_local_stack = _money(float(stacks[other]) - origin, "other local stack", budget)
    owed_raw = theirs - own
    owed = 0.0 if abs(owed_raw) <= EPS else max(0.0, owed_raw)
    candidates = []
    if owed:
        call_amount = _money(min(owed, local_stack - own), "call amount", budget)
        local_call = _money(min(theirs, local_stack), "local call target", budget)
        candidates.extend((
            ("fold", 0.0, 0.0, False, None),
            ("call", call_amount, _money(origin + local_call, "global call target", budget),
             False, local_call),
        ))
    else:
        candidates.append(("check", 0.0, 0.0, False, None))

    options = stages[state.street]
    base_pot = state.boundary_pot if state.origin is not None else 0.0
    sized = []

    def add(name, target, committed, maximum, full=False):
        target = _money(min(maximum, max(committed, target)), "sized action target", budget)
        if target <= committed + EPS:
            return
        if target >= maximum - EPS:
            name = "all_in"
        global_target = _money(origin + target, "global action target", budget)
        if any(abs(old[4] - target) <= EPS for old in sized):
            return
        sized.append((name, _money(target - committed, "action amount", budget),
                      global_target, full, target))

    if state.street and not owed:
        for fraction in money_rules._configured_sizes(options["bet_sizes"]):
            total_pot = base_pot + sum((own, theirs))
            add("bet", own + float(fraction) * total_pot, own, local_stack)
        if options["include_all_in"] and local_stack > own + EPS:
            add("all_in", local_stack, own, local_stack)
    elif ((owed or state.street == 0) and state.reopened and
          state.raises < options["max_raises"] and local_stack > theirs + EPS and
          theirs < other_local_stack - EPS):
        pot_after_call = base_pot + sum((own, theirs)) + owed_raw
        for fraction in money_rules._configured_sizes(options["raise_sizes"]):
            requested = theirs + fraction * pot_after_call
            minimum = theirs + float(state.increment)
            target = _money(min(local_stack, max(minimum, requested)), "raise target", budget)
            full = target - theirs + EPS >= float(state.increment)
            if full:
                add("raise", target, own, local_stack, True)
            elif requested + EPS >= local_stack or minimum > local_stack:
                add("all_in", local_stack, own, local_stack, False)
        if options["include_all_in"] and local_stack > theirs + EPS:
            increment = local_stack - theirs
            add("all_in", local_stack, own, local_stack,
                increment + EPS >= float(state.increment))

    candidates.extend(sorted(sized, key=lambda item: item[2]))
    return tuple(Action(name, amount, target, money_rules._token(name, target))
                 for name, amount, target, *_ in candidates), tuple(candidates)


def _history_chars(state):
    return sum(len(token) for token in state.history)


def _charge_action_menu(budget, state, stages):
    """Reserve configured-size, dedupe, money and token work before the menu helper."""
    options = stages[state.street]
    configured_sizes = max(len(options["bet_sizes"]), len(options["raise_sizes"]))
    # A raise-size candidate can be rounded once before `add` and up to four
    # more times inside it. The extra fixed calls cover stack/call/all-in paths.
    money_calls = 8 + 6 * configured_sizes
    history_chars = _history_chars(state)
    # Units are conservative modeled helper steps, not Python operations or CPU time.
    reserve = (256 + 128 * configured_sizes + 64 * MAX_ACTIONS_PER_DECISION +
               16 * history_chars + 2 * money_calls * _FLOAT_CONVERSION_WORK_UPPER)
    budget.charge("public_action_menu_rule_work_upper", reserve)
    budget.entries(4 * MAX_ACTIONS_PER_DECISION + 16 + len(state.history),
                   "public action menu bounded scratch")


def _charge_successor(budget, state):
    history_chars = _history_chars(state)
    # Covers one token/state transition, settlement money cleanup, and exact
    # Fraction input forecasts before the successor helper runs.
    money_calls = 7
    reserve = (384 + 16 * history_chars +
               2 * money_calls * _FLOAT_CONVERSION_WORK_UPPER)
    budget.charge("public_successor_rule_work_upper", reserve)
    budget.entries(12 + len(state.history) + history_chars,
                   "public successor bounded scratch")


def _charge_settlement(budget, state):
    history_chars = _history_chars(state)
    reserve = 256 + 16 * history_chars + 2 * 3 * _FLOAT_CONVERSION_WORK_UPPER
    budget.charge("public_settlement_rule_work_upper", reserve)
    budget.entries(8 + len(state.history) + history_chars,
                   "public settlement bounded scratch")


def _charge_reveal_successor(budget, state, board_length):
    history_chars = _history_chars(state)
    # At most three rounded money values and one full-history reveal label.
    reserve = (256 + 16 * history_chars + 16 * board_length +
               2 * 3 * _FLOAT_CONVERSION_WORK_UPPER)
    budget.charge("public_reveal_successor_rule_work_upper", reserve)
    budget.entries(10 + len(state.history) + history_chars + board_length,
                   "public reveal successor bounded scratch")


def _terminal(state, winner=None):
    committed = tuple(float(value) for value in state.committed)
    return Terminal("fold" if winner is not None else "showdown", committed,
                    winner, tuple(state.board), tuple(state.history),
                    float(min(state.committed)))


def _next_decision(state, action_data, stacks, budget):
    """Return the successor state for one action; terminals are handled by caller."""
    name, amount, target, full = action_data[:4]
    local_target = action_data[4] if len(action_data) > 4 else None
    player, other = state.player, 1 - state.player
    next_state = _replace(state, history=state.history +
                          (money_rules._token(name, target),))
    if name == "fold":
        return _TerminalStart(state, other), None
    if name == "call":
        committed = list(state.committed)
        committed[player] = target
        local = state.local_committed
        if state.street and local is not None:
            local_values = list(local)
            local_values[player] = _money(local_target, "local call target", budget)
            local = tuple(local_values)
        else:
            local = None
        next_state = _replace(next_state, committed=tuple(committed),
                              local_committed=local)
        same = abs(float(committed[0]) - float(committed[1])) <= EPS
        chips_each = all(float(value) < float(stack) - EPS
                         for value, stack in zip(committed, stacks))
        if state.street == 0 and not state.history and same and chips_each:
            return _replace(next_state, player=1), None
        return _settle_state(next_state, stacks, budget), None
    if name == "check":
        if state.street == 0 or state.checks == 1:
            return _settle_state(next_state, stacks, budget), None
        return _replace(next_state, player=other, checks=1), None

    committed = list(state.committed)
    committed[player] = target
    if state.street and state.local_committed is not None:
        opening = abs(state.local_committed[0] - state.local_committed[1]) <= EPS
        local_values = list(state.local_committed)
        local_target = (_money(local_values[player] + amount, "local sized target", budget)
                        if local_target is None else local_target)
        local_values[player] = local_target
        increment = (amount if opening else
                     (local_target - state.local_committed[other] if full else state.increment))
        local = tuple(local_values)
    else:
        opening = bool(state.street and state.committed[0] == state.committed[1])
        increment = (amount if opening else
                     (target - state.committed[other] if full else state.increment))
        local = None
    return _replace(
        next_state, player=other, committed=tuple(committed), increment=increment,
        raises=0 if opening else state.raises + 1,
        reopened=True if opening else full, checks=0, local_committed=local), None


def _settle_state(state, stacks, budget):
    matched = min(state.committed)
    state = _replace(state, committed=(matched, matched))
    if state.street == 5 or any(float(matched) >= float(stack) - EPS for stack in stacks):
        return _TerminalStart(state)
    next_length = {0: 3, 3: 4, 4: 5}[state.street]
    if state.street == 0:
        origin = _money(matched, "settlement origin", budget)
        boundary_pot = _money(origin + origin, "settlement boundary pot", budget)
        remaining = tuple(_money(float(stack) - origin, "remaining stack", budget)
                          for stack in stacks)
        _need(isfinite(boundary_pot) and 0.01 <= boundary_pot <= 1_000_000,
              "live preflop continuation pot must be within 0.01-1000000")
        _need(all(isfinite(value) and 0.01 <= value <= 1_000_000 for value in remaining),
              "live preflop continuation stacks must be within 0.01-1000000")
    return _RevealStart(state, next_length)


def _reveal_prefixes(outcomes, board, next_length):
    # All prefixes are retained, including prefixes that later have zero
    # blocker-compatible mass; the independent PayoffModel owns that filter.
    # The old independent public builder visits its branch dictionary in
    # lexical tuple order; retain that observable traversal order.
    return tuple(sorted({outcome[:next_length] for outcome in outcomes
                         if outcome[:len(board)] == tuple(board)}))


def _initial_state(stacks, sb_blind, bb_blind, budget):
    posted = tuple(_money(min(blind, stack), "posted blind", budget)
                   for blind, stack in zip((sb_blind, bb_blind), stacks))
    return money_rules._State(0, 0, posted, increment=_money(bb_blind, "preflop increment", budget))


def _blind_all_in(state, stacks):
    return any(float(state.committed[player]) >= float(stacks[player]) - EPS and
               float(state.committed[1 - player]) >=
               float(state.committed[player]) - EPS for player in (0, 1))


def _census(state, outcomes, stacks, stages, budget, limits):
    """Count the complete public graph without retaining any graph nodes."""
    node_count = action_count = reveal_nodes = reveal_edges = 0
    decision_nodes = terminal_fold = terminal_showdown = 0
    history_tokens = history_characters = action_token_characters = 0
    max_depth = 0
    stack = [(state, 0)]
    while stack:
        current, depth = stack.pop()
        if isinstance(current, money_rules._State) and \
                float(current.committed[current.player]) >= float(stacks[current.player]) - EPS:
            _charge_settlement(budget, current)
            current = _settle_state(current, stacks, budget)
        max_depth = max(max_depth, depth)
        _need(depth <= limits["public_depth"],
              f"public graph exceeds depth {limits['public_depth']}")
        node_count += 1
        _need(node_count <= limits["public_nodes"],
              f"public graph exceeds {limits['public_nodes']} nodes")
        # Work is reserved before generating action menus or prefix containers.
        history = (current.state.history if isinstance(current, (_TerminalStart, _RevealStart))
                   else current.history)
        token_chars = sum(len(token) for token in history)
        history_tokens += len(history)
        history_characters += token_chars
        budget.charge("public_census_node", 2 + len(history) + token_chars)
        if isinstance(current, _TerminalStart):
            if current.winner is None:
                terminal_showdown += 1
            else:
                terminal_fold += 1
            continue
        if isinstance(current, _RevealStart):
            reveal_nodes += 1
            board_length = current.board_length
            budget.entries(2 * len(outcomes) + 1,
                           "public census prefix scan scratch")
            budget.charge("public_census_reveal_scan",
                          len(outcomes) * (len(current.state.board) + 1))
            prefixes = _reveal_prefixes(outcomes, current.state.board, board_length)
            budget.entries(len(prefixes) + 1, "public reveal census branches")
            reveal_edges += len(prefixes)
            for prefix in reversed(prefixes):
                _charge_reveal_successor(budget, current.state, board_length)
                next_state = _state_after_reveal(current.state, prefix, board_length, budget)
                stack.append((next_state, depth + 1))
            continue

        decision_nodes += 1
        _charge_action_menu(budget, current, stages)
        budget.entries(2 * MAX_ACTIONS_PER_DECISION + 4,
                       "public census action scratch")
        actions, details = _actions_for(current, stacks, stages, budget)
        _need(0 < len(actions) <= MAX_ACTIONS_PER_DECISION,
              "public action menu exceeds bounded per-decision width")
        action_count += len(actions)
        action_token_characters += sum(len(action.token) for action in actions)
        budget.charge("public_census_action_edges", len(actions))
        budget.entries(len(actions), "public census pending successors")
        for action_data in reversed(details):
            _charge_successor(budget, current)
            next_node, _winner = _next_decision(current, action_data, stacks, budget)
            stack.append((next_node, depth + 1))
    return {"public_nodes": node_count, "decisions": decision_nodes,
            "reveals": reveal_nodes, "actions": action_count,
            "reveal_edges": reveal_edges, "fold_terminals": terminal_fold,
            "showdown_terminals": terminal_showdown, "depth": max_depth,
            "history_tokens": history_tokens,
            "history_characters": history_characters,
            "action_token_characters": action_token_characters}


def _state_after_reveal(state, prefix, board_length, budget):
    local = state.local_committed
    origin = state.origin
    boundary_pot = state.boundary_pot
    committed = state.committed
    if origin is None:
        origin = _money(min(state.committed), "revealed origin", budget)
        boundary_pot = _money(2 * origin, "revealed boundary pot", budget)
        local = (0.0, 0.0)
        committed = (origin, origin)
    elif local is not None:
        matched_local = min(local)
        local = (matched_local, matched_local)
        whole = _money(origin + matched_local, "revealed whole contribution", budget)
        committed = (whole, whole)
    if board_length == 3:
        label = "flop@" + "".join(prefix)
    elif board_length == 4:
        label = "turn@" + prefix[-1]
    elif board_length == 5:
        label = "river@" + prefix[-1]
    else:
        raise ValueError("unsupported reveal length")
    new_state = _replace(
        state, street=board_length, player=1, committed=tuple(committed),
        board=tuple(prefix), history=tuple(state.history) + (label,),
        origin=origin, boundary_pot=boundary_pot, local_committed=local,
        increment=Fraction(0), raises=0, reopened=True, checks=0)
    return new_state


def build_public_model(case, budget=None, limits=None):
    """Build a bounded full-history public tree without private deal expansion.

    ``budget`` is the shared reduce-only matrix-free certificate budget. The
    optional ``limits`` mapping can only lower the independent structural caps.
    """
    budget = _checked_budget(budget)
    structural_limits = _limits_snapshot(limits)
    inputs = _snapshot_inputs(case, budget, structural_limits)
    case_snapshot, ranges, outcomes, stacks, sb_blind, bb_blind, stages = inputs

    initial = _initial_state(stacks, sb_blind, bb_blind, budget)
    root_seed = (_TerminalStart(initial) if _blind_all_in(initial, stacks) else initial)
    census = _census(root_seed, outcomes, stacks, stages, budget, structural_limits)

    # Reserve every retained tree node/action/child slot before materializing
    # the graph. This keeps failures at the admission boundary rather than
    # after a partially allocated public model.
    case_text_entries = (len(case_snapshot["id"]) + len(case_snapshot["sb_range"]) +
                         len(case_snapshot["bb_range"]) +
                         sum(len(value) for value in case_snapshot["runouts"]))
    retained_entries = (12 * census["public_nodes"] + 4 * census["actions"] +
                        8 * census["reveal_edges"] + 6 * len(outcomes) +
                        sum(len(side) for side in ranges) +
                        census["history_tokens"] + census["history_characters"] +
                        census["action_token_characters"] + case_text_entries + 128)
    budget.entries(retained_entries, "matrix-free public graph")
    materialization_scratch_entries = (
        64 * (2 * len(outcomes) + 2 * MAX_ACTIONS_PER_DECISION + 8))
    budget.entries(materialization_scratch_entries,
                   "matrix-free graph materialization scratch")

    decisions = []
    actual_nodes = actual_actions = actual_reveal_edges = 0

    def materialize(state, depth=0):
        nonlocal actual_nodes, actual_actions, actual_reveal_edges
        if isinstance(state, money_rules._State) and \
                float(state.committed[state.player]) >= float(stacks[state.player]) - EPS:
            _charge_settlement(budget, state)
            state = _settle_state(state, stacks, budget)
        actual_nodes += 1
        _need(actual_nodes <= census["public_nodes"],
              "public graph exceeded its admitted node census")
        if isinstance(state, _TerminalStart):
            return _terminal(state.state, state.winner)
        if isinstance(state, _RevealStart):
            marked_state, board_length = state.state, state.board_length
            budget.entries(2 * len(outcomes) + 1,
                           "public materialization prefix scan scratch")
            budget.charge("public_materialize_reveal", len(outcomes) *
                          (len(marked_state.board) + 1))
            prefixes = _reveal_prefixes(outcomes, marked_state.board, board_length)
            branches = {}
            for prefix in prefixes:
                actual_reveal_edges += 1
                _charge_reveal_successor(budget, marked_state, board_length)
                child_state = _state_after_reveal(marked_state, prefix, board_length, budget)
                branches[prefix] = materialize(child_state, depth + 1)
            return Reveal(tuple(marked_state.history), board_length,
                          MappingProxyType(branches))
        current = state

        _charge_action_menu(budget, current, stages)
        budget.charge("public_materialize_decision", 2 + len(current.history))
        budget.entries(2 * MAX_ACTIONS_PER_DECISION + 4,
                       "public materialization action scratch")
        actions, details = _actions_for(current, stacks, stages, budget)
        actual_actions += len(actions)
        budget.charge("public_materialize_action_edges", len(actions))
        child_nodes = []
        for action_data in details:
            _charge_successor(budget, current)
            next_node, _winner = _next_decision(current, action_data, stacks, budget)
            child_nodes.append(materialize(next_node, depth + 1))
        decision = Decision(current.player, tuple(current.history), tuple(current.board),
                            actions, tuple(child_nodes))
        decisions.append(decision)
        return decision

    # Root fold/raise/call tree is deterministic; decisions are exposed in
    # the old validator's preorder for stable diagnostics.
    root = materialize(root_seed)
    decisions_out = _preorder_decisions(root)

    _need(actual_nodes == census["public_nodes"],
          "materialized public node count differs from its dry census")
    _need(actual_actions == census["actions"],
          "materialized public action count differs from its dry census")
    _need(len(decisions_out) == census["decisions"],
          "materialized decision count differs from its dry census")
    actual_reveals = sum(isinstance(node, Reveal) for node in _preorder_public(root))
    _need(actual_reveals == census["reveals"],
          "materialized reveal count differs from its dry census")
    counts = dict(census)
    counts.update({"decisions": len(decisions_out), "selected_outcomes": len(outcomes),
                   "range_hands": tuple(len(side) for side in ranges),
                   "actual_public_nodes": actual_nodes,
                   "actual_action_slots": actual_actions,
                   "actual_reveal_edges": actual_reveal_edges,
                   "retained_entry_upper": retained_entries,
                   "materialization_scratch_entry_upper": materialization_scratch_entries,
                   "private_worlds_materialized": False,
                   "physical_support_filtered": False,
                   "retained_entry_model": "matrix-free-public-model-entries-v1",
                   "budget": budget.receipt() if callable(getattr(budget, "receipt", None)) else None})
    return PublicModel(case_snapshot, ranges, outcomes, root, decisions_out, counts)


def _preorder_decisions(root):
    result = []
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, Decision):
            result.append(node)
            stack.extend(reversed(node.children))
        elif isinstance(node, Reveal):
            stack.extend(reversed(tuple(node.branches.values())))
    return tuple(result)


def _preorder_public(root):
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, Decision):
            stack.extend(reversed(node.children))
        elif isinstance(node, Reveal):
            stack.extend(reversed(tuple(node.branches.values())))

