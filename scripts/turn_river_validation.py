"""Independent numeric replay for configured turn and river solver results.

Development oracle only. It rebuilds the finite public action tree and physical
deal law from numeric inputs; it does not call production betting, payoff, CFR,
or best-response code.
"""
from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from math import fsum, isfinite
from numbers import Real

from pokerlab.cards import DECK, cards, expand_range
from scripts.preflop_validation import independent_rank


MAX_WORLD_COUNT = 200_000
# Conservative development admission estimate. It bounds major world/node passes,
# not every Python loop, elapsed time, or resident memory.
MAX_ORACLE_WORK = 8_000_000
EPS = 1e-9


def _clean(value):
    value = round(float(value), 9)
    return 0.0 if value == 0 else value


def _label(value):
    return format(_clean(value), ".9f").rstrip("0").rstrip(".")


@dataclass(frozen=True)
class _Action:
    name: str
    amount: float = 0.0
    raise_to: float = 0.0

    @property
    def token(self):
        return (f"{self.name}@{_label(self.raise_to)}"
                if self.name in ("bet", "raise", "all_in") else self.name)


@dataclass
class _Decision:
    player: int
    history: tuple
    board: tuple
    actions: tuple
    children: tuple


@dataclass
class _Chance:
    history: tuple
    branches: dict


@dataclass(frozen=True)
class _Terminal:
    kind: str
    contributions: tuple
    winner: int | None = None


@dataclass(frozen=True)
class _Rules:
    pot: float
    stacks: tuple
    effective_stack: object
    bet_sizes: tuple
    raise_sizes: tuple
    max_raises: int
    include_all_in: bool

    def to_dict(self):
        return {"pot": self.pot, "effective_stack": self.effective_stack,
                "bet_sizes": list(self.bet_sizes), "raise_sizes": list(self.raise_sizes),
                "max_raises": self.max_raises, "include_all_in": self.include_all_in}


def _config(value, label):
    if value is None:
        value = {"pot": 100.0, "effective_stack": 500.0,
                 "bet_sizes": (0.5,), "raise_sizes": (),
                 "max_raises": 0, "include_all_in": True}
    elif not isinstance(value, dict):
        if not callable(getattr(value, "to_dict", None)):
            raise TypeError(f"{label} must be a numeric config mapping or object with to_dict")
        value = value.to_dict()
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a numeric config mapping")
    allowed = {"pot", "effective_stack", "bet_sizes", "raise_sizes",
               "max_raises", "include_all_in"}
    if set(value) - allowed:
        raise ValueError(f"{label} contains unknown config fields")

    def number(raw, field, minimum):
        if isinstance(raw, bool) or not isinstance(raw, Real):
            raise ValueError(f"{label} {field} must be a finite number")
        number = float(raw)
        if not isfinite(number) or not minimum <= number <= 1_000_000:
            raise ValueError(f"{label} {field} is outside supported numeric bounds")
        return number

    pot = number(value.get("pot", 100.0), "pot", 0.01)
    raw_stacks = value.get("effective_stack", 500.0)
    if isinstance(raw_stacks, (tuple, list)):
        if len(raw_stacks) != 2:
            raise ValueError(f"{label} effective_stack must have two entries")
        stacks = tuple(number(raw, "effective_stack", 0.01) for raw in raw_stacks)
        effective_stack = list(stacks)
    else:
        stack = number(raw_stacks, "effective_stack", 0.01)
        stacks = (stack, stack)
        effective_stack = stack

    def sizes(raw, field, required=False):
        if isinstance(raw, (str, bytes)):
            raise ValueError(f"{label} {field} must be a sequence")
        try:
            result = tuple(sorted(set(number(item, field, 1e-9) for item in raw)))
        except TypeError as exc:
            raise ValueError(f"{label} {field} must be a sequence") from exc
        if len(result) > 8 or required and not result:
            raise ValueError(f"{label} {field} has invalid size count")
        return result

    bets = sizes(value.get("bet_sizes", (0.5,)), "bet_sizes", True)
    raises = sizes(value.get("raise_sizes", ()), "raise_sizes")
    max_raises = value.get("max_raises", 0)
    include = value.get("include_all_in", True)
    if type(max_raises) is not int or not 0 <= max_raises <= 8:
        raise ValueError(f"{label} max_raises must be an integer from 0 through 8")
    if type(include) is not bool:
        raise ValueError(f"{label} include_all_in must be boolean")
    return _Rules(pot, stacks, effective_stack, bets, raises, max_raises, include)


def _token_action(actions, name, target, committed, stack):
    target = _clean(min(stack, max(committed, target)))
    if target <= committed + EPS:
        return
    if target >= stack - EPS:
        name = "all_in"
    if any(abs(action.raise_to - target) <= EPS for action in actions):
        return
    actions.append(_Action(name, _clean(target - committed), target))


def _opening(config, contributions, player):
    committed = contributions[player]
    actions = []
    public_pot = config.pot + sum(contributions)
    for fraction in config.bet_sizes:
        _token_action(actions, "bet", committed + fraction * public_pot,
                      committed, config.stacks[player])
    if config.include_all_in:
        _token_action(actions, "all_in", config.stacks[player], committed,
                      config.stacks[player])
    return tuple(sorted(actions, key=lambda action: action.raise_to))


def _raises(config, contributions, player, previous_increment):
    committed = contributions[player]
    opponent = contributions[1 - player]
    call_amount = opponent - committed
    maximum = config.stacks[player]
    if maximum <= opponent + EPS:
        return ()
    minimum = opponent + previous_increment
    pot_after_call = config.pot + sum(contributions) + call_amount
    actions = []
    for fraction in config.raise_sizes:
        requested = opponent + fraction * pot_after_call
        target = min(maximum, max(minimum, requested))
        increment = target - opponent
        full = increment + EPS >= previous_increment
        if full:
            _token_action(actions, "raise", target, committed, maximum)
        elif requested + EPS >= maximum or minimum > maximum:
            _token_action(actions, "all_in", maximum, committed, maximum)
    if config.include_all_in and maximum > opponent + EPS:
        increment = maximum - opponent
        _token_action(actions, "all_in", maximum, committed, maximum)
    return tuple(sorted(actions, key=lambda action: action.raise_to))


def _build_street(config, history=(), contributions=(0.0, 0.0), board=(),
                  on_settled=None, budget=None):
    if budget is None:
        budget = {"decisions": 0}
    def settled(path, committed):
        if on_settled is not None:
            return on_settled(tuple(path), tuple(committed))
        _reserve_state(budget, "terminal")
        return _Terminal("showdown", tuple(committed))

    def build(path, player, committed, previous_increment, raises, reopened, checks):
        if committed[player] >= config.stacks[player] - EPS:
            return settled(path, committed)
        _reserve_state(budget, "decision")
        other = 1 - player
        own = committed[player]
        theirs = committed[other]
        if abs(own - theirs) <= EPS:
            check = _Action("check")
            if checks == 1:
                check_child = settled(path + ("check",), committed)
            else:
                check_child = build(path + ("check",), other, committed,
                                    previous_increment, raises, reopened, checks + 1)
            actions = [check]
            children = [check_child]
            for action in _opening(config, committed, player):
                updated = list(committed)
                updated[player] = action.raise_to
                actions.append(action)
                children.append(build(path + (action.token,), other, tuple(updated),
                                      action.amount, 0, True, 0))
            return _Decision(player, tuple(path), tuple(board), tuple(actions), tuple(children))

        call_amount = theirs - own
        actual_call = min(call_amount, config.stacks[player] - own)
        called = list(committed)
        called[player] = own + actual_call
        actions = (_Action("fold"), _Action("call", _clean(actual_call), called[player]))
        _reserve_state(budget, "terminal")
        children = [_Terminal("fold", tuple(committed), other),
                    settled(path + ("call",), tuple(called))]
        if reopened and raises < config.max_raises and theirs < config.stacks[other] - EPS:
            for action in _raises(config, committed, player, previous_increment):
                updated = list(committed)
                updated[player] = action.raise_to
                increment = action.raise_to - theirs
                full = increment + EPS >= previous_increment
                next_increment = increment if full else previous_increment
                actions += (action,)
                children.append(build(path + (action.token,), other, tuple(updated),
                                      next_increment, raises + 1, full, 0))
        return _Decision(player, tuple(path), tuple(board), actions, tuple(children))

    return build(tuple(history), 0, tuple(map(_clean, contributions)), 0.0, 0, True, 0)


def _reserve_state(budget, kind):
    budget["states"] += 1
    if budget["states"] > 250_000:
        raise ValueError("Independent replay exceeds 250,000 public states")
    if kind == "decision":
        budget["decisions"] += 1
        if budget["decisions"] > 10_000:
            raise ValueError("Independent replay exceeds 10,000 public decisions")


def _worlds(board, ranges, runouts):
    hands = tuple(tuple(sorted(hand)) for hand in ranges)
    weights = tuple({tuple(sorted(hand)): Fraction.from_float(float(weight))
                     for hand, weight in side.items()} for side in ranges)
    selected = (() if len(board) == 5 else
                tuple(card for card in DECK if card not in board) if runouts is None else
                tuple(cards(runouts)))
    if (len(board) == 4 and not selected) or len(set(selected)) != len(selected) or any(card in board for card in selected):
        raise ValueError("Runouts must be unique public cards outside the board")
    if len(board) == 5 and runouts is not None:
        raise ValueError("A complete river board cannot have future runouts")
    if selected:
        selected_set = set(selected)
        selected = tuple(card for card in DECK if card in selected_set)
    counts = [dict.fromkeys(DECK, 0), dict.fromkeys(DECK, 0)]
    for player in (0, 1):
        for hand, weight in ranges[player].items():
            if weight > 0:
                for card in hand:
                    counts[player][card] += 1
    compatible_pairs = (sum(weight > 0 for weight in ranges[0].values()) *
                        sum(weight > 0 for weight in ranges[1].values()) -
                        sum(counts[0][card] * counts[1][card] for card in DECK) +
                        sum(hand in ranges[1] and ranges[1][hand] > 0
                            for hand, weight in ranges[0].items() if weight > 0))
    candidate_worlds = compatible_pairs * (len(selected) if len(board) == 4 else 1)
    if candidate_worlds > MAX_WORLD_COUNT:
        raise ValueError("Independent replay exceeds 200,000 candidate physical worlds")
    pending = []
    for hand0, hand1 in product(hands[0], hands[1]):
        if set(hand0) & set(hand1):
            continue
        pair_mass = weights[0][hand0] * weights[1][hand1]
        for river in selected if len(board) == 4 else (None,):
            if river is not None and river in set(hand0) | set(hand1):
                continue
            pending.append((hand0, hand1, river, pair_mass))
            if len(pending) > MAX_WORLD_COUNT:
                raise ValueError("Independent replay exceeds 200,000 physical worlds")
    normalizer = sum((world[3] for world in pending), Fraction(0))
    if normalizer <= 0:
        raise ValueError("Ranges contain no compatible physical deals")
    worlds = []
    for hand0, hand1, river, mass in pending:
        board_now = board if river is None else board + (river,)
        rank0 = independent_rank(board_now + hand0)
        rank1 = independent_rank(board_now + hand1)
        sign = (rank0 > rank1) - (rank0 < rank1)
        worlds.append({"hands": (hand0, hand1), "river": river,
                       "board": board_now, "weight": mass / normalizer,
                       "sign": sign})
    return worlds, selected


def _public_tree(board, config, river_config, selected, worlds):
    budget = {"states": 0, "decisions": 0}
    def after_turn(history, contributions):
        branches = {}
        _reserve_state(budget, "chance")
        for river in selected:
            if not any(world["river"] == river for world in worlds):
                continue
            matched = min(contributions)
            carried = (matched, matched)
            all_in = any(matched >= stack - EPS for stack in config.stacks)
            river_history = history + (f"river@{river}",)
            if all_in:
                _reserve_state(budget, "terminal")
                branches[river] = _Terminal("showdown", carried)
            else:
                branches[river] = _build_street(river_config, river_history,
                                                 carried, board + (river,), budget=budget)
        return _Chance(history, branches)
    if len(board) == 5:
        return _build_street(config, board=board, budget=budget)
    return _build_street(config, board=board, on_settled=after_turn, budget=budget)


def _row_actions(node):
    return [{"name": action.name, "amount": action.amount,
             "raise_to": action.raise_to, "history_key": action.token}
            for action in node.actions]


def _collect_nodes(root):
    output = []
    pending = [root]
    while pending:
        node = pending.pop()
        if isinstance(node, _Decision):
            output.append(node)
            pending.extend(reversed(node.children))
        elif isinstance(node, _Chance):
            pending.extend(reversed(tuple(node.branches.values())))
        if len(output) > 10_000:
            raise ValueError("Independent replay exceeds 10,000 public decisions")
    return output


def _validate_policy(result, root, nodes, worlds, board, selected,
                     runouts_were_omitted):
    if len(nodes) * len(worlds) > MAX_ORACLE_WORK:
        raise ValueError("Independent policy replay exceeds work limit")

    required = ("board", "runouts", "runout_mode", "reachable_runouts")
    missing = [field for field in required if field not in result]
    if missing:
        raise ValueError(f"Result is missing required metadata: {', '.join(missing)}")
    result_board = result["board"]
    if (type(result_board) is not list or
            any(type(card) is not str or card not in DECK for card in result_board) or
            result_board != list(board)):
        raise ValueError("Result public board does not match replay input")
    result_runouts = result["runouts"]
    if (type(result_runouts) is not list or
            any(type(card) is not str or card not in DECK for card in result_runouts) or
            result_runouts != list(selected)):
        raise ValueError("Result runouts do not match replay conditioning")
    expected_mode = ("none" if len(board) == 5 else
                     "full-deck" if runouts_were_omitted else
                     "conditioned-subset")
    # Mode records the caller's conditioning choice, even when an explicit
    # subset happens to contain every available river.
    if type(result["runout_mode"]) is not str or result["runout_mode"] != expected_mode:
        raise ValueError("Result runout mode does not match replay conditioning")
    reachable = result["reachable_runouts"]
    if (type(reachable) is not list or
            any(type(card) is not str or card not in DECK for card in reachable) or
            len(set(reachable)) != len(reachable)):
        raise ValueError("Result reachable runouts must be unique canonical card strings")
    physically_reachable = {world["river"] for world in worlds
                            if world["river"] is not None and world["weight"] > 0}
    expected_reachable_deck = [card for card in selected
                               if card in physically_reachable]
    expected_reachable_lexical = sorted(expected_reachable_deck)
    if reachable not in (expected_reachable_deck, expected_reachable_lexical):
        raise ValueError("Result reachable runouts do not match positive physical support")
    rows = result.get("strategy")
    if not isinstance(rows, list):
        raise ValueError("Result strategy must be a list")
    expected = {}
    for node in nodes:
        for player in (node.player,):
            for world in worlds:
                if world["board"][:len(node.board)] != node.board:
                    continue
                hand = world["hands"][player]
                if set(hand) & set(node.board):
                    continue
                key = ("oop" if player == 0 else "ip", "".join(hand), node.history)
                expected[key] = node
    actual = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Strategy rows must be objects")
        if set(row) != {"player", "hand", "street", "board", "history", "actions"}:
            raise ValueError("Strategy row contains missing or unknown metadata")
        try:
            player, hand, history = row["player"], row["hand"], tuple(row["history"])
            key = (player, hand, history)
        except (KeyError, TypeError) as exc:
            raise ValueError("Malformed strategy row identity") from exc
        if key in actual:
            raise ValueError("Duplicate strategy row")
        actual[key] = row
    missing, extra = set(expected) - set(actual), set(actual) - set(expected)
    if missing or extra:
        raise ValueError(f"Strategy row set mismatch: {len(missing)} missing, {len(extra)} extra")
    policies = {}
    for key, node in expected.items():
        row = actual[key]
        player, hand, history = key
        expected_board = list(node.board)
        street = "turn" if len(node.board) == 4 else "river"
        if row.get("street") != street or row.get("board") != expected_board:
            raise ValueError("Strategy row street or public board does not match the numeric tree")
        if row.get("history") != list(history):
            raise ValueError("Strategy row history does not match the numeric tree")
        actions = row.get("actions")
        if not isinstance(actions, list) or len(actions) != len(node.actions):
            raise ValueError("Strategy row has missing or extra legal actions")
        probabilities = []
        for supplied, legal in zip(actions, _row_actions(node)):
            if not isinstance(supplied, dict):
                raise ValueError("Strategy actions must be objects")
            if set(supplied) != set(legal) | {"probability"}:
                raise ValueError("Strategy action contains missing or unknown fields")
            for field, value in legal.items():
                if field not in supplied or supplied[field] != value:
                    raise ValueError(f"Strategy action {field} does not match legal action")
                if field in ("amount", "raise_to"):
                    supplied_number = supplied[field]
                    if (isinstance(supplied_number, bool) or
                            not isinstance(supplied_number, Real) or
                            not isfinite(float(supplied_number)) or
                            float(supplied_number) != value):
                        raise ValueError(f"Strategy action {field} must be a finite matching number")
            probability = supplied.get("probability")
            if isinstance(probability, bool) or not isinstance(probability, (int, float)):
                raise ValueError("Strategy probabilities must be finite nonnegative numbers")
            probability = float(probability)
            if not isfinite(probability) or probability < 0 or probability > 1:
                raise ValueError("Strategy probabilities must be finite nonnegative numbers")
            probabilities.append(probability)
        if abs(fsum(probabilities) - 1.0) > 1e-9:
            raise ValueError("Strategy probabilities must sum to one")
        policies[(0 if player == "oop" else 1, hand, history)] = tuple(probabilities)
    return policies


def _validate_count_metadata(result, *, world_count, pair_count, info_count,
                             board_length):
    if "info_sets" not in result:
        raise ValueError("Result is missing required information-set count")
    count_fields = {
        "info_sets": info_count,
        "compatible_world_count": world_count,
        "worlds": world_count,
        "compatible_pairs": pair_count,
        "deals": pair_count,
    }
    for field, expected in count_fields.items():
        if field not in result:
            continue
        value = result[field]
        if type(value) is not int or value < 0:
            raise ValueError(f"Result count {field} must be a nonnegative integer")
        if value != expected:
            raise ValueError(f"Result count {field} differs from independent replay")
    required_aliases = ("compatible_world_count", "worlds") if board_length == 4 else (
        "compatible_pairs", "deals")
    if not any(field in result for field in required_aliases):
        raise ValueError("Result is missing its required physical deal count")


def _terminal_payoff(node, world):
    matched = min(node.contributions)
    if node.kind == "fold":
        sign = 1 if node.winner == 0 else -1
    else:
        sign = world["sign"]
    return sign * (world["pot"] / 2 + matched)


def _with_pot(world, pot):
    world = dict(world)
    world["pot"] = pot
    return world


def _profile(root, worlds, policies, pot):
    world_values = []
    def visit(node, world, reaches):
        if isinstance(node, _Chance):
            river = world["river"]
            if river not in node.branches:
                return 0.0
            return visit(node.branches[river], world, reaches)
        if isinstance(node, _Terminal):
            return _terminal_payoff(node, world)
        key = (node.player, "".join(world["hands"][node.player]), node.history)
        row = policies[key]
        return fsum(row[a] * visit(child, world, reaches)
                    for a, child in enumerate(node.children))
    for raw in worlds:
        world = _with_pot(raw, pot)
        world_values.append(float(world["weight"]) * visit(root, world, None))
    return fsum(world_values)


def _best_response(root, worlds, policies, player, pot):
    own_hands = sorted({world["hands"][player] for world in worlds})
    work = 0
    def visit(node, own_hand, group):
        nonlocal work
        work += max(1, len(group))
        if work > MAX_ORACLE_WORK:
            raise ValueError("Independent best-response replay exceeds work limit")
        if isinstance(node, _Chance):
            return fsum(visit(child, own_hand,
                              [entry for entry in group if entry[0]["river"] == river])
                        for river, child in node.branches.items())
        if isinstance(node, _Terminal):
            return fsum(mass * _terminal_payoff(node, _with_pot(world, pot))
                        for world, mass in group)
        if node.player == player:
            values = [visit(child, own_hand, group) for child in node.children]
            return max(values) if player == 0 else min(values)
        action_values = []
        for action, child in enumerate(node.children):
            action_group = []
            for world, mass in group:
                key = (node.player, "".join(world["hands"][node.player]), node.history)
                probability = policies[key][action]
                if probability:
                    action_group.append((world, mass * Fraction.from_float(probability)))
            if action_group:
                action_values.append(visit(child, own_hand, action_group))
        return fsum(action_values)
    hand_values = []
    for hand in own_hands:
        group = [(world, world["weight"]) for world in worlds
                 if world["hands"][player] == hand]
        hand_values.append(visit(root, hand, group))
    value = fsum(hand_values)
    return value if player == 0 else -value


def _diagnostic_gains(value, br0, br1, pot):
    """Validate independent response bounds, then clamp roundoff per player."""
    if not all(isfinite(number) for number in (value, br0, br1, pot)):
        raise ValueError("Independent diagnostic values must be finite")
    tolerance = 1e-10 * max(1.0, pot, abs(value), abs(br0), abs(br1))
    if br0 < value - tolerance or br1 < -value - tolerance:
        raise ValueError("Independent best response violates its legal lower bound")
    gain0 = max(0.0, br0 - value)
    gain1 = max(0.0, br1 + value)
    gap = gain0 + gain1
    if not all(isfinite(number) for number in (gain0, gain1, gap)):
        raise ValueError("Independent diagnostic gains must be finite")
    return gain0, gain1, gap


def replay_policy(result, oop_range, ip_range, *, board, config,
                  river_config=None, runouts=None):
    """Validate and independently replay one configured turn or river result."""
    if not isinstance(result, dict):
        raise ValueError("Result must be a complete serialized result object")
    board = cards(board)
    if len(board) not in (4, 5):
        raise ValueError("Replay board must contain four turn cards or five river cards")
    config = _config(config, "config")
    river_config = config if river_config is None else _config(river_config, "river_config")
    if river_config.pot != config.pot or river_config.stacks != config.stacks:
        raise ValueError("Turn and river configs must preserve pot and stack caps")
    ranges = (expand_range(oop_range, board), expand_range(ip_range, board))
    if any(weight <= 0 for side in ranges for weight in side.values()):
        ranges = tuple({hand: weight for hand, weight in side.items() if weight > 0}
                       for side in ranges)
    worlds, selected = _worlds(board, ranges, runouts)
    if any(not isfinite(float(world["weight"])) or float(world["weight"]) <= 0
           for world in worlds):
        raise ValueError("A positive physical world probability is not representable in binary64")
    config_dict = config.to_dict()
    river_dict = river_config.to_dict()
    if "config" in result and result["config"] != config_dict:
        raise ValueError("Result config does not match independent replay input")
    if "turn_config" in result and result["turn_config"] != (config_dict if len(board) == 4 else None):
        raise ValueError("Result turn config does not match independent replay input")
    if "river_config" in result and result["river_config"] != river_dict:
        raise ValueError("Result river config does not match independent replay input")
    if "street_configs" in result:
        expected_streets = ({"turn": config_dict, "river": river_dict}
                            if len(board) == 4 else {"river": river_dict})
        if result["street_configs"] != expected_streets:
            raise ValueError("Result street configs do not match independent replay input")
    root = _public_tree(board, config, river_config, selected, worlds)
    nodes = _collect_nodes(root)
    if len(nodes) * len(worlds) * 4 > MAX_ORACLE_WORK:
        raise ValueError("Independent replay exceeds conservative modeled world-node admission")
    policies = _validate_policy(result, root, nodes, worlds, board, selected,
                                runouts_were_omitted=runouts is None)
    pair_count = len({(world["hands"][0], world["hands"][1]) for world in worlds})
    _validate_count_metadata(
        result, world_count=len(worlds), pair_count=pair_count,
        info_count=len(policies), board_length=len(board),
    )
    value = _profile(root, worlds, policies, config.pot)
    br0 = _best_response(root, worlds, policies, 0, config.pot)
    br1 = _best_response(root, worlds, policies, 1, config.pot)
    gain0, gain1, gap = _diagnostic_gains(value, br0, br1, config.pot)
    pair_weights = {}
    river_weights = {}
    for world in worlds:
        pair = ("".join(world["hands"][0]), "".join(world["hands"][1]))
        pair_weights[pair] = pair_weights.get(pair, Fraction(0)) + world["weight"]
        if world["river"] is not None:
            river_weights[world["river"]] = river_weights.get(world["river"], Fraction(0)) + world["weight"]
    return {
        "value_oop": value, "value_ip": -value,
        "oop_best_response_value": br0, "ip_best_response_value": br1,
        "oop_best_response_gain": gain0, "ip_best_response_gain": gain1,
        "nash_conv": gap, "exploitability": gap / 2.0,
        "checked_rows": len(policies), "world_count": len(worlds),
        "checked_information_sets": len(policies), "worlds": len(worlds),
        "compatible_pair_count": len(pair_weights),
        "pair_probabilities": {key: float(value) for key, value in pair_weights.items()},
        "river_probabilities": {key: float(value) for key, value in river_weights.items()},
        "public_node_count": len(nodes), "selected_runouts": selected,
    }


def compare_result(result, oracle, tolerance=1e-9):
    """Compare solver diagnostics and structural counts with an oracle replay."""
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not isfinite(float(tolerance)) or tolerance < 0:
        raise ValueError("tolerance must be a finite nonnegative number")
    if not isinstance(result, dict) or not isinstance(oracle, dict):
        raise ValueError("Result and oracle must be objects")
    board = result.get("board")
    if type(board) is not list or len(board) not in (4, 5):
        raise ValueError("Result must include a four- or five-card public board")
    oracle_worlds = oracle.get("worlds")
    oracle_pairs = oracle.get("compatible_pair_count")
    oracle_infos = oracle.get("checked_information_sets")
    for name, value in (("oracle worlds", oracle_worlds),
                        ("oracle compatible pairs", oracle_pairs),
                        ("oracle information sets", oracle_infos)):
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    _validate_count_metadata(
        result, world_count=oracle_worlds, pair_count=oracle_pairs,
        info_count=oracle_infos, board_length=len(board),
    )
    differences = {}
    for field in ("value_oop", "value_ip", "oop_best_response_value",
                  "ip_best_response_value", "oop_best_response_gain",
                  "ip_best_response_gain", "nash_conv", "exploitability"):
        candidate = result.get(field)
        expected = oracle.get(field)
        if isinstance(candidate, bool) or not isinstance(candidate, (int, float)) or not isfinite(float(candidate)):
            raise ValueError(f"Result metric {field} must be finite")
        if isinstance(expected, bool) or not isinstance(expected, (int, float)) or not isfinite(float(expected)):
            raise ValueError(f"Oracle metric {field} must be finite")
        if field in ("oop_best_response_gain", "ip_best_response_gain",
                     "nash_conv", "exploitability") and (candidate < 0 or expected < 0):
            raise ValueError(f"Metric {field} must be nonnegative")
        differences[field] = float(candidate) - float(expected)
        if abs(differences[field]) > tolerance:
            raise ValueError(f"Result metric {field} differs from independent replay")
    identities = (
        ("zero-sum value identity", result["value_oop"] + result["value_ip"]),
        ("NashConv identity", result["nash_conv"] -
         (result["oop_best_response_gain"] + result["ip_best_response_gain"])),
        ("exploitability identity", result["exploitability"] - result["nash_conv"] / 2.0),
    )
    for label, error in identities:
        if abs(error) > tolerance:
            raise ValueError(f"Result violates {label}")
    return differences
