"""Bounded independent physical support and policy validation for four streets.

This development oracle composes numeric rules across preflop, flop, turn and
river. It does not use the production tree, ranker, payoff, trainer or BR code.
The legacy configured replay is called only after this module has independently
checked the complete capped graph and every serialized row.
"""
from dataclasses import dataclass, replace
from fractions import Fraction
from itertools import product
from math import fsum, isfinite
from numbers import Real

from pokerlab.cards import DECK, cards, expand_range
from scripts import preflop_validation as legacy
from scripts.turn_river_validation import _Action, _Decision, _Terminal


MAX_WORLDS = 32
MAX_STATES = 2048
MAX_DECISIONS = 2048
MAX_ROWS = 2048
MAX_ACTIONS = 4096
MAX_DEPTH = 32
MAX_SELECTED = 8
MAX_HANDS_PER_PLAYER = 4
MAX_CASE_ID_LENGTH = 128
MAX_RANGE_EXPRESSION_LENGTH = 4096
MAX_RUNOUT_STRING_LENGTH = 128
MAX_ROW_HISTORY = MAX_DEPTH
MAX_HISTORY_TOKEN_LENGTH = 64
EPS = 1e-9


@dataclass
class Reveal:
    """Public chance node indexed by the complete visible board prefix."""
    history: tuple
    board_length: int
    branches: dict


@dataclass(frozen=True)
class NumericModel:
    root: object
    worlds: tuple
    decisions: tuple
    expected_infos: dict
    counts: dict
    case: dict


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _as_mapping(value, label):
    _need(isinstance(value, dict), f"{label} must be a mapping")
    return dict(value)


def _configured_money(value, label):
    _need(not isinstance(value, bool) and isinstance(value, Real),
          f"{label} must be a finite number")
    number = float(value)
    _need(isfinite(number) and 0.000000001 <= number <= 1_000_000,
          f"{label} must be between 1e-9 and 1000000")
    return legacy._q(number)


def _normalize_stage(value, inherited, label):
    stage = dict(inherited)
    if value is None:
        return stage
    value = _as_mapping(value, label)
    allowed = {"bet_sizes", "raise_sizes", "max_raises", "include_all_in"}
    _need(not (set(value) - allowed), f"{label} has unknown fields")
    stage.update(value)
    for field in ("bet_sizes", "raise_sizes"):
        raw = stage[field]
        _need(type(raw) in (list, tuple), f"{label} {field} must be a bounded list or tuple")
        _need(len(raw) <= 8, f"{label} {field} exceeds eight sizes")
        _need(all(not isinstance(item, bool) and isinstance(item, Real) for item in raw),
              f"{label} {field} must contain numeric values")
        converted = tuple(float(item) for item in raw)
        sizes = tuple(sorted(set(converted)))
        _need(all(isfinite(item) and 0.000000001 <= item <= 1_000_000 for item in sizes),
              f"{label} {field} has an unsupported size")
        if field == "bet_sizes":
            _need(bool(sizes), f"{label} needs at least one bet size")
        stage[field] = sizes
    _need(type(stage["max_raises"]) is int and 0 <= stage["max_raises"] <= 8,
          f"{label} max_raises is invalid")
    _need(type(stage["include_all_in"]) is bool, f"{label} include_all_in is invalid")
    return stage


def _case_inputs(case):
    _need(isinstance(case, dict), "case must be a mapping")
    required = {"id", "sb_range", "bb_range", "config", "runouts",
                "flop_config", "turn_config", "river_config"}
    _need(set(case) == required, "case must contain exactly the declared four-street inputs")
    _need(type(case["id"]) is str, "case id must be a string")
    _need(len(case["id"]) <= MAX_CASE_ID_LENGTH,
          f"case id exceeds {MAX_CASE_ID_LENGTH} characters")
    _need(case["id"].strip(), "case id must be nonblank")
    _need(type(case["sb_range"]) is str and type(case["bb_range"]) is str,
          "ranges must be bounded string descriptions")
    _need(len(case["sb_range"]) <= MAX_RANGE_EXPRESSION_LENGTH and
          len(case["bb_range"]) <= MAX_RANGE_EXPRESSION_LENGTH,
          f"each range expression must be at most {MAX_RANGE_EXPRESSION_LENGTH} characters")
    config = _as_mapping(case["config"], "config")
    allowed_config = {"starting_stack", "small_blind", "big_blind", "raise_sizes",
                      "max_raises", "include_all_in"}
    _need(not (set(config) - allowed_config), "config has unknown fields")
    stack_raw = config.get("starting_stack", 100)
    if isinstance(stack_raw, (list, tuple)):
        _need(len(stack_raw) == 2, "starting_stack must be scalar or a pair")
        stacks = tuple(_configured_money(item, "starting_stack") for item in stack_raw)
    else:
        stacks = (_configured_money(stack_raw, "starting_stack"),) * 2
    _need(all(stack > 0 for stack in stacks), "starting stacks must be positive")
    sb_blind = _configured_money(config.get("small_blind", 0.5), "small_blind")
    bb_blind = _configured_money(config.get("big_blind", 1), "big_blind")
    _need(sb_blind < bb_blind and sb_blind > Fraction(1, 1_000_000_000) and
          bb_blind - sb_blind > Fraction(1, 1_000_000_000),
          "blinds and their difference must exceed the 1e-9-chip tolerance")
    preflop = _normalize_stage({
        "raise_sizes": config.get("raise_sizes", [1]),
        "max_raises": config.get("max_raises", 3),
        "include_all_in": config.get("include_all_in", True),
    }, {"bet_sizes": (0.5,), "raise_sizes": (1.0,), "max_raises": 3,
        "include_all_in": True}, "preflop config")
    defaults = {"bet_sizes": (0.5,), "raise_sizes": (), "max_raises": 0,
                "include_all_in": True}
    flop = _normalize_stage(case["flop_config"], defaults, "flop_config")
    turn = _normalize_stage(case["turn_config"], flop, "turn_config")
    river = _normalize_stage(case["river_config"], flop, "river_config")
    runouts = case["runouts"]
    _need(type(runouts) in (list, tuple), "runouts must be a bounded list or tuple")
    _need(0 < len(runouts) <= MAX_SELECTED,
          f"runouts must contain 1 through {MAX_SELECTED} outcomes")
    normalized = []
    seen = set()
    order = {card: index for index, card in enumerate(DECK)}
    for raw in runouts:
        _need(type(raw) is str, "each runout must be a five-card string")
        _need(len(raw) <= MAX_RUNOUT_STRING_LENGTH,
              f"each runout string must be at most {MAX_RUNOUT_STRING_LENGTH} characters")
        parsed = cards(raw, 5)
        flop_cards = tuple(sorted(parsed[:3], key=order.__getitem__))
        outcome = flop_cards + parsed[3:]
        _need(outcome not in seen, "duplicate canonical flop and ordered runout")
        seen.add(outcome)
        normalized.append(outcome)
    normalized.sort(key=lambda outcome: tuple(order[card] for card in outcome))
    sb_range = expand_range(case["sb_range"])
    bb_range = expand_range(case["bb_range"])
    _need(0 < len(sb_range) <= MAX_HANDS_PER_PLAYER and
          0 < len(bb_range) <= MAX_HANDS_PER_PLAYER,
          f"each range must contain at most {MAX_HANDS_PER_PLAYER} hands")
    _need(all(isfinite(float(w)) and w > 0 for side in (sb_range, bb_range)
              for w in side.values()), "range weights must be finite and positive")
    _need(len(sb_range) * len(bb_range) * len(normalized) <= 128,
          "candidate world support exceeds bounded preflight")
    return config, stacks, sb_blind, bb_blind, preflop, (preflop, flop, turn, river), \
        normalized, (sb_range, bb_range)


def _physical_support(ranges, outcomes):
    """Build bounded blocker-conditioned support without evaluating ranks."""
    pending = []
    for sb_hand, sb_weight in sorted(ranges[0].items()):
        for bb_hand, bb_weight in sorted(ranges[1].items()):
            if set(sb_hand) & set(bb_hand):
                continue
            pair_mass = Fraction.from_float(float(sb_weight)) * Fraction.from_float(float(bb_weight))
            for board in outcomes:
                if (set(sb_hand) | set(bb_hand)) & set(board):
                    continue
                _need(len(pending) < MAX_WORLDS,
                      f"physical world support exceeds {MAX_WORLDS}")
                pending.append({"hands": (tuple(sb_hand), tuple(bb_hand)),
                                "board": tuple(board), "weight": pair_mass,
                                "sign": 0})
    normalizer = sum((item["weight"] for item in pending), Fraction(0))
    _need(normalizer > 0, "ranges and selected outcomes contain no compatible worlds")
    for item in pending:
        item["weight"] /= normalizer
    return pending


def _build_graph(support, stacks, sb_blind, bb_blind, stages):
    preflop, flop, turn, river = stages
    all_worlds = support
    state_count = action_count = max_depth = policy_slots = 0
    decisions = []
    expected_infos = {}

    def reserve(depth, actions=0, decision=False):
        nonlocal state_count, action_count
        state_count += 1
        action_count += actions
        _need(state_count <= MAX_STATES, f"graph exceeds {MAX_STATES} states")
        _need(action_count <= MAX_ACTIONS, f"graph exceeds {MAX_ACTIONS} action slots")
        _need(depth <= MAX_DEPTH, f"graph exceeds depth {MAX_DEPTH}")
        _need(not decision or len(decisions) < MAX_DECISIONS,
              f"graph exceeds {MAX_DECISIONS} decisions")

    def actions_for(state):
        player, other = state.player, 1 - state.player
        global_own = float(state.committed[player])
        global_theirs = float(state.committed[other])
        origin = 0.0 if state.origin is None else state.origin
        if state.local_committed is None:
            own, theirs = global_own, global_theirs
        else:
            own, theirs = state.local_committed[player], state.local_committed[other]
        local_stacks = legacy._money(float(stacks[player]) - origin)
        other_local_stack = legacy._money(float(stacks[other]) - origin)
        amount_owed = theirs - own
        owed = 0.0 if abs(amount_owed) <= EPS else max(0.0, amount_owed)
        if owed:
            call_amount = legacy._money(min(owed, local_stacks - own))
            local_call = legacy._money(min(theirs, local_stacks))
            candidates = [("fold", 0.0, 0.0, False),
                          ("call", call_amount, legacy._money(origin + local_call), False,
                           local_call)]
        else:
            candidates = [("check", 0.0, 0.0, False)]
        opts = {0: preflop, 3: flop, 4: turn, 5: river}[state.street]
        base_pot = state.boundary_pot if state.origin is not None else 0.0
        sized = []

        def add(name, target, committed, maximum, full=False):
            target = legacy._money(min(maximum, max(committed, target)))
            if target <= committed + EPS:
                return
            if target >= maximum - EPS:
                name = "all_in"
            global_target = legacy._money(origin + target)
            if any(abs(old[4] - target) <= EPS for old in sized):
                return
            sized.append((name, legacy._money(target - committed), global_target, full, target))

        if state.street and not owed:
            for fraction in legacy._configured_sizes(opts["bet_sizes"]):
                total_pot = base_pot + sum((own, theirs))
                requested = own + float(fraction) * total_pot
                add("bet", requested, own, local_stacks)
            if opts["include_all_in"] and local_stacks > own + EPS:
                add("all_in", local_stacks, own, local_stacks)
        elif ((owed or state.street == 0) and state.reopened and
              state.raises < opts["max_raises"] and local_stacks > theirs + EPS and
              theirs < other_local_stack - EPS):
            pot_after_call = base_pot + sum((own, theirs)) + amount_owed
            for fraction in legacy._configured_sizes(opts["raise_sizes"]):
                requested = theirs + fraction * pot_after_call
                minimum = theirs + float(state.increment)
                target = legacy._money(min(local_stacks, max(minimum, requested)))
                full = target - theirs + EPS >= float(state.increment)
                if full:
                    add("raise", target, own, local_stacks, True)
                elif requested + EPS >= local_stacks or minimum > local_stacks:
                    add("all_in", local_stacks, own, local_stacks, False)
            if opts["include_all_in"] and local_stacks > theirs + EPS:
                increment = local_stacks - theirs
                add("all_in", local_stacks, own, local_stacks,
                    increment + EPS >= float(state.increment))
        candidates.extend(sorted(sized, key=lambda item: item[2]))
        return tuple(_Action(name, amount, target) for name, amount, target, *_ in candidates), candidates

    def terminal(state, winner=None, depth=0):
        reserve(depth)
        return _Terminal("fold" if winner is not None else "showdown",
                         tuple(map(float, state.committed)), winner)

    def reveal(state, board_length, depth):
        reserve(depth)
        branches = {}
        prefixes = sorted({world["board"][:board_length] for world in all_worlds
                           if world["board"][:len(state.board)] == tuple(state.board)})
        for prefix in prefixes:
            subset = [world for world in all_worlds if world["board"][:board_length] == prefix]
            if not subset:
                continue
            if board_length == 3:
                label, street = "flop@" + "".join(prefix), 3
            elif board_length == 4:
                label, street = "turn@" + prefix[-1], 4
            else:
                label, street = "river@" + prefix[-1], 5
            local = state.local_committed
            origin, boundary_pot = state.origin, state.boundary_pot
            committed = state.committed
            if origin is None:
                origin = legacy._money(min(state.committed))
                boundary_pot = legacy._money(2 * origin)
                local = (0.0, 0.0)
                committed = (origin, origin)
            elif local is not None:
                matched_local = min(local)
                local = (matched_local, matched_local)
                whole = legacy._money(origin + matched_local)
                committed = (whole, whole)
            new_state = legacy._State(street, 1, tuple(committed),
                                      state.history + (label,), tuple(prefix),
                                      origin=origin, boundary_pot=boundary_pot,
                                      local_committed=local)
            branches[tuple(prefix)] = build(new_state, depth + 1)
        return Reveal(tuple(state.history), board_length, branches)

    def settle(state, depth):
        matched = min(state.committed)
        state = replace(state, committed=(matched, matched))
        if state.street == 5 or any(float(matched) >= float(stack) - EPS for stack in stacks):
            return terminal(state, depth=depth)
        if state.street == 0:
            origin = legacy._money(matched)
            boundary_pot = legacy._money(origin + origin)
            remaining = tuple(legacy._money(float(stack) - origin) for stack in stacks)
            _need(isfinite(boundary_pot) and 0.01 <= boundary_pot <= 1_000_000,
                  "live preflop continuation pot must be within 0.01-1000000")
            _need(all(isfinite(value) and 0.01 <= value <= 1_000_000
                      for value in remaining),
                  "live preflop continuation stacks must be within 0.01-1000000")
        next_len = {0: 3, 3: 4, 4: 5}[state.street]
        return reveal(state, next_len, depth)

    def child(state, action_data, depth):
        name, amount, target, full = action_data[:4]
        local_target = action_data[4] if len(action_data) > 4 else None
        player, other = state.player, 1 - state.player
        next_state = replace(state, history=state.history + (legacy._token(name, target),))
        if name == "fold":
            return terminal(state, other, depth)
        if name == "call":
            committed = list(state.committed)
            committed[player] = target
            local = state.local_committed
            if state.street and local is not None:
                local_values = list(local)
                local_values[player] = legacy._money(local_target)
                local = tuple(local_values)
            else:
                local = None
            next_state = replace(next_state, committed=tuple(committed), local_committed=local)
            same = abs(float(committed[0]) - float(committed[1])) <= EPS
            chips_each = all(float(value) < float(stack) - EPS
                             for value, stack in zip(committed, stacks))
            if state.street == 0 and not state.history and same and chips_each:
                return build(replace(next_state, player=1), depth)
            return settle(next_state, depth)
        if name == "check":
            if state.street == 0 or state.checks == 1:
                return settle(next_state, depth)
            return build(replace(next_state, player=other, checks=1), depth)
        committed = list(state.committed)
        committed[player] = target
        if state.street and state.local_committed is not None:
            opening = abs(state.local_committed[0] - state.local_committed[1]) <= EPS
            local_values = list(state.local_committed)
            local_target = (legacy._money(local_values[player] + amount)
                            if local_target is None else local_target)
            local_values[player] = local_target
            increment = amount if opening else (local_target - state.local_committed[other]
                                                 if full else state.increment)
            local = tuple(local_values)
        else:
            opening = bool(state.street and state.committed[0] == state.committed[1])
            increment = amount if opening else (target - state.committed[other]
                                                 if full else state.increment)
            local = None
        nxt = replace(next_state, player=other, committed=tuple(committed),
                      increment=increment, raises=0 if opening else state.raises + 1,
                      reopened=True if opening else full, checks=0, local_committed=local)
        return build(nxt, depth)

    def build(state, depth):
        if float(state.committed[state.player]) >= float(stacks[state.player]) - EPS:
            return settle(state, depth)
        actions, details = actions_for(state)
        reserve(depth, len(actions), True)
        node = _Decision(state.player, tuple(state.history), tuple(state.board),
                         actions, ())
        decisions.append(node)
        children = tuple(child(state, details[index], depth + 1)
                         for index in range(len(actions)))
        node.children = children
        nonlocal policy_slots
        for world in all_worlds:
            if world["board"][:len(state.board)] != tuple(state.board):
                continue
            hand = "".join(world["hands"][state.player])
            key = (state.player, hand, tuple(state.history))
            previous = expected_infos.get(key)
            if previous is None:
                _need(len(expected_infos) + 1 <= MAX_ROWS,
                      f"graph exceeds {MAX_ROWS} policy rows")
                policy_slots += len(node.actions)
                _need(policy_slots <= MAX_ACTIONS,
                      f"graph exceeds {MAX_ACTIONS} row action slots")
                expected_infos[key] = node
            else:
                _need(previous is node,
                      f"public history aliases incompatible numeric decisions: {key!r}")
        _need(len(expected_infos) <= MAX_ROWS, f"graph exceeds {MAX_ROWS} policy rows")
        return node

    posted = tuple(legacy._money(min(blind, stack))
                   for blind, stack in zip((sb_blind, bb_blind), stacks))
    initial = legacy._State(0, 0, posted, increment=legacy._money(bb_blind))
    if any(posted[player] >= stacks[player] - EPS and
           posted[1 - player] >= posted[player] - EPS for player in (0, 1)):
        root = terminal(initial, depth=0)
    else:
        root = build(initial, 0)

    all_nodes = []
    pending = [(root, 0)]
    while pending:
        node, depth = pending.pop()
        all_nodes.append(node)
        max_depth = max(max_depth, depth)
        _need(len(all_nodes) <= MAX_STATES, f"graph exceeds {MAX_STATES} states")
        if isinstance(node, _Decision):
            pending.extend((child_node, depth + 1) for child_node in reversed(node.children))
        elif isinstance(node, Reveal):
            pending.extend((child_node, depth + 1) for child_node in reversed(tuple(node.branches.values())))
    _need(max_depth <= MAX_DEPTH, f"graph exceeds depth {MAX_DEPTH}")
    return root, tuple(decisions), expected_infos, len(all_nodes), policy_slots, max_depth


def build_model(case):
    """Build the bounded complete numeric graph before independently ranking worlds."""
    config, stacks, sb, bb, preflop, stages, outcomes, ranges = _case_inputs(case)
    support = _physical_support(ranges, outcomes)
    root, decisions, expected_infos, state_count, slots, depth = _build_graph(
        support, stacks, sb, bb, stages)
    # Ranking is deliberately delayed until support and complete shape passed all caps.
    ranked = []
    for world in support:
        final_board = tuple(sorted(world["board"], key=DECK.index))
        ranks = [legacy.independent_rank(tuple(world["hands"][p]) + final_board)
                 for p in (0, 1)]
        ranked.append({**world, "sign": (ranks[0] > ranks[1]) - (ranks[0] < ranks[1])})
    pair_mass = {}
    for world in ranked:
        pair = tuple("".join(hand) for hand in world["hands"])
        pair_mass[pair] = pair_mass.get(pair, Fraction(0)) + world["weight"]
    counts = {
        "worlds": len(ranked), "public_states": state_count,
        "decisions": len(decisions), "infos": len(expected_infos),
        "slots": slots, "depth": depth, "selected_outcomes": len(outcomes),
        "compatible_pairs": len(pair_mass),
        "pair_probabilities": [
            {"sb_hand": pair[0], "bb_hand": pair[1],
             "fraction": f"{mass.numerator}/{mass.denominator}"}
            for pair, mass in sorted(pair_mass.items())
        ],
    }
    # Store only normalized, bounded built-ins. The caller may mutate its input
    # dictionaries/lists after construction without changing replay semantics.
    def stage_snapshot(stage):
        return {"bet_sizes": tuple(stage["bet_sizes"]),
                "raise_sizes": tuple(stage["raise_sizes"]),
                "max_raises": stage["max_raises"],
                "include_all_in": stage["include_all_in"]}

    config_snapshot = {
        "starting_stack": tuple(stacks) if isinstance(config.get("starting_stack", 100), (list, tuple))
                          else stacks[0],
        "small_blind": sb, "big_blind": bb,
        "raise_sizes": tuple(preflop["raise_sizes"]),
        "max_raises": preflop["max_raises"],
        "include_all_in": preflop["include_all_in"],
    }
    case_snapshot = {
        "id": case["id"], "sb_range": case["sb_range"], "bb_range": case["bb_range"],
        "config": config_snapshot,
        "runouts": tuple(" ".join(outcome) for outcome in outcomes),
        "flop_config": stage_snapshot(stages[1]),
        "turn_config": stage_snapshot(stages[2]),
        "river_config": stage_snapshot(stages[3]),
    }
    return NumericModel(root, tuple(ranked), decisions, expected_infos, counts, case_snapshot)


def _row_key(row):
    _need(isinstance(row, dict), "strategy rows must be objects")
    _need(set(row) == {"player", "hand", "street", "revealed_board", "history", "actions"},
          "strategy row has missing or unknown fields")
    _need(type(row["player"]) is str and row["player"] in ("sb", "bb"),
          "strategy actor must be sb or bb")
    _need(type(row["hand"]) is str and len(row["hand"]) == 4,
          "strategy hand must contain exactly four characters")
    _need(type(row["history"]) is list, "strategy history must be a string list")
    _need(len(row["history"]) <= MAX_ROW_HISTORY,
          f"strategy history exceeds {MAX_ROW_HISTORY} tokens")
    _need(all(type(token) is str for token in row["history"]),
          "strategy history must be a string list")
    _need(all(len(token) <= MAX_HISTORY_TOKEN_LENGTH for token in row["history"]),
          f"strategy history token exceeds {MAX_HISTORY_TOKEN_LENGTH} characters")
    return (0 if row["player"] == "sb" else 1, row["hand"], tuple(row["history"]))


def validate_policy(model, payload):
    """Validate every exact physical information row and return probability tuples."""
    _need(isinstance(model, NumericModel), "model must come from build_model")
    _need(isinstance(payload, dict), "payload must be a serialized result mapping")
    _need(payload.get("solver_version") == "preflop-strategy-v1" and
          payload.get("strategy_schema") == "preflop-strategy-v1",
          "payload must use the complete four-street preflop strategy schema")
    _need(payload.get("runout_mode") == "conditioned-ordered-selected-runouts",
          "payload runout mode does not match the selected physical game")
    _need("postflop_scope" not in payload or payload["postflop_scope"] == "all-streets",
          "payload scope must include all four streets")
    case = model.case
    _, _, _, _, _, _, outcomes, _ = _case_inputs(case)
    expected_selected = [list(outcome) for outcome in outcomes]
    _need(payload.get("selected_runouts") == expected_selected,
          "payload selected runouts do not match the physical support")
    expected_reachable = [list(outcome) for outcome in outcomes
                          if any(world["board"] == outcome for world in model.worlds)]
    _need(payload.get("reachable_runouts") == expected_reachable,
          "payload reachable runouts do not match positive physical support")
    _need(type(payload.get("worlds")) is int and payload["worlds"] == len(model.worlds),
          "payload world count differs from independent support")
    pair_count = len(model.counts["pair_probabilities"])
    _need(type(payload.get("compatible_private_pairs")) is int and
          payload["compatible_private_pairs"] == pair_count,
          "payload compatible pair count differs from independent support")
    _need(type(payload.get("info_sets")) is int and
          payload["info_sets"] == len(model.expected_infos),
          "payload information-set count differs from independent shape")
    supplied_pairs = payload.get("private_pair_probabilities")
    _need(type(supplied_pairs) is list and len(supplied_pairs) == pair_count,
          "payload private-pair masses do not cover independent support")
    expected_pairs = {(item["sb_hand"], item["bb_hand"]): Fraction(item["fraction"])
                      for item in model.counts["pair_probabilities"]}
    observed_pairs = {}
    for item in supplied_pairs:
        _need(isinstance(item, dict) and
              set(item) == {"sb_hand", "bb_hand", "probability"},
              "payload private-pair mass row is malformed")
        pair = (item["sb_hand"], item["bb_hand"])
        _need(all(type(hand) is str for hand in pair) and pair not in observed_pairs,
              "payload private-pair support has invalid or duplicate identities")
        value = item["probability"]
        _need(not isinstance(value, bool) and isinstance(value, Real) and
              isfinite(float(value)) and float(value) > 0,
              "payload private-pair mass must be finite and positive")
        observed_pairs[pair] = float(value)
    _need(set(observed_pairs) == set(expected_pairs),
          "payload private-pair support differs from independent support")
    for pair, exact_mass in expected_pairs.items():
        _need(abs(observed_pairs[pair] - float(exact_mass)) <= 1e-12,
              "payload private-pair mass differs from independent physical law")
    rows = payload.get("strategy")
    _need(type(rows) is list, "payload strategy must be a list")
    _need(len(model.expected_infos) <= MAX_ROWS and len(rows) == len(model.expected_infos),
          "strategy row count exceeds cap or differs from complete information support")
    actual = {}
    for row in rows:
        key = _row_key(row)
        _need(key not in actual, "duplicate serialized information set")
        actual[key] = row
    expected = {(player, hand, history): node
                for (player, hand, history), node in model.expected_infos.items()}
    _need(set(actual) == set(expected),
          f"strategy row set mismatch: {len(set(expected)-set(actual))} missing, "
          f"{len(set(actual)-set(expected))} extra")
    checked = {}
    streets = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}
    for key, node in expected.items():
        row = actual[key]
        _need(row["street"] == streets.get(len(node.board)), "strategy street mismatch")
        _need(row["revealed_board"] == list(node.board), "row reveals incorrect board")
        _need(row["history"] == list(node.history), "row history mismatch")
        actions = row["actions"]
        _need(type(actions) is list and len(actions) == len(node.actions),
              "row has missing or extra actions")
        probabilities = []
        for supplied, legal in zip(actions, node.actions):
            _need(isinstance(supplied, dict) and
                  set(supplied) == {"name", "amount", "raise_to", "history_key", "probability"},
                  "action has missing or unknown fields")
            _need(supplied["name"] == legal.name and supplied["history_key"] == legal.token,
                  "action name or history token does not match legal numeric state")
            for field, expected_number in (("amount", legal.amount), ("raise_to", legal.raise_to)):
                number = supplied[field]
                _need(not isinstance(number, bool) and isinstance(number, Real) and
                      isfinite(float(number)) and float(number) == expected_number,
                      f"action {field} does not match whole-hand numeric rule")
            probability = supplied["probability"]
            _need(not isinstance(probability, bool) and isinstance(probability, Real),
                  "probability must be a finite number")
            probability = float(probability)
            _need(isfinite(probability) and 0 <= probability <= 1,
                  "probability must be finite and between zero and one")
            probabilities.append(probability)
        _need(abs(fsum(probabilities) - 1.0) <= 1e-10,
              "row probabilities must sum to one")
        checked[key] = tuple(probabilities)
    return checked


def replay_policy(payload, case):
    """Validate a complete policy independently, then return numeric replay metrics."""
    model = build_model(case)
    validate_policy(model, payload)
    case = model.case
    legacy_metrics = legacy.replay_policy(
        payload, case["sb_range"], case["bb_range"], config=case["config"],
        runouts=case["runouts"], flop_config=case["flop_config"],
        turn_config=case["turn_config"], river_config=case["river_config"],
        monetary_mode="configured", postflop_scope="all-streets")
    _need(legacy_metrics["worlds"] == model.counts["worlds"],
          "legacy numeric metrics disagree with independent world count")
    observed = {(item["sb"], item["bb"]): item["probability"]
                for item in legacy_metrics["private_pair_probabilities"]}
    expected = {(item["sb_hand"], item["bb_hand"]): Fraction(item["fraction"])
                for item in model.counts["pair_probabilities"]}
    _need(set(observed) == set(expected),
          "legacy numeric metrics disagree with independent private-pair support")
    legacy_metrics["numeric_counts"] = dict(model.counts)
    return legacy_metrics
