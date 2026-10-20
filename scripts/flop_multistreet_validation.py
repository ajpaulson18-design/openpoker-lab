"""Independent physical-world and numeric-rule replay for flop-start games.

This module deliberately owns its card parser, blocker conditioning, action
construction, public tree, policy checks, and best responses. The only poker
helper imported from the application is the established independent best-five
ranker in :mod:`scripts.preflop_validation`; production parsing, trees,
utilities, trainers, and diagnostics are not replay authorities here.
"""

from collections import defaultdict
from fractions import Fraction
from itertools import permutations
from math import fsum, isfinite

from scripts.preflop_validation import independent_rank


RANKS = "23456789TJQKA"
SUITS = "cdhs"
DECK = tuple(rank + suit for rank in RANKS for suit in SUITS)
DECK_INDEX = {card: index for index, card in enumerate(DECK)}
EPSILON = 1e-9
MAX_PAIRS = 4
MAX_WORLDS = 7_920
MAX_DECISIONS = 10_000
MAX_PUBLIC_STATES = 250_000
MAX_CANDIDATE_HANDS = 4_096
MAX_CANDIDATE_PAIRS = 4_096
MAX_CONFIG_VALUE = 1e12


class _Decision:
    __slots__ = ("history", "player", "street", "board", "actions", "children")

    def __init__(self, history, player, street, board, actions, children):
        self.history = tuple(history)
        self.player = player
        self.street = street
        self.board = tuple(board)
        self.actions = tuple(actions)
        self.children = tuple(children)


class _Chance:
    __slots__ = ("history", "card_index", "street", "branches")

    def __init__(self, history, card_index, street, branches):
        self.history = tuple(history)
        self.card_index = card_index
        self.street = street
        self.branches = dict(branches)


class _Terminal:
    __slots__ = ("history", "kind", "contributions", "winner")

    def __init__(self, history, kind, contributions, winner=None):
        self.history = tuple(history)
        self.kind = kind
        self.contributions = tuple(contributions)
        self.winner = winner


def _card(value):
    if type(value) is not str or len(value) != 2 or value[0] not in RANKS or value[1] not in SUITS:
        raise ValueError(f"Invalid card: {value!r}")
    return value


def _cards(values, *, count=None):
    if type(values) in (str, bytes) or not isinstance(values, (list, tuple)):
        raise ValueError("Cards must be supplied as a sequence of card strings.")
    parsed = tuple(_card(value) for value in values)
    if count is not None and len(parsed) != count:
        raise ValueError(f"Expected exactly {count} cards.")
    if len(set(parsed)) != len(parsed):
        raise ValueError("Cards must be distinct.")
    return parsed


def _hand_rows(rows, board):
    if type(rows) not in (list, tuple) or not rows:
        raise ValueError("Each range must be a nonempty list of literal hand/weight rows.")
    if len(rows) > MAX_CANDIDATE_HANDS:
        raise ValueError("Literal range exceeds the 4,096-hand validation cap.")
    result = {}
    seen = set()
    for row in rows:
        if type(row) not in (list, tuple) or len(row) != 2 or type(row[1]) is not str:
            raise ValueError("Each hand row must be [two-card hand string, rational weight string].")
        label, raw_weight = row
        if type(label) is not str or len(label) != 4:
            raise ValueError("A literal hand must contain exactly two card strings.")
        cards = (_card(label[:2]), _card(label[2:]))
        if cards[0] == cards[1]:
            raise ValueError("A private hand must contain two distinct cards.")
        hand = tuple(sorted(cards))
        try:
            weight = Fraction(raw_weight)
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            raise ValueError("Hand weights must be finite rational strings.") from exc
        if weight <= 0:
            raise ValueError("Hand weights must be positive.")
        if hand in seen:
            raise ValueError("Duplicate literal private hand.")
        seen.add(hand)
        if set(hand).isdisjoint(board):
            result[hand] = weight
    return tuple(sorted(result.items(), key=lambda item: item[0]))


def _number(value, label, *, minimum=0.0, maximum=MAX_CONFIG_VALUE):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number.") from exc
    if not isfinite(number) or number < minimum or number > maximum:
        raise ValueError(f"{label} is outside the supported finite range.")
    return number


def _configuration(value):
    if type(value) is not dict:
        raise ValueError("Street config must be a mapping.")
    allowed = {"pot", "effective_stack", "bet_sizes", "raise_sizes", "max_raises", "include_all_in"}
    if set(value) - allowed:
        raise ValueError("Street config contains unsupported fields.")
    pot = _number(value.get("pot"), "pot", minimum=0.01)
    raw_stacks = value.get("effective_stack")
    if isinstance(raw_stacks, (list, tuple)):
        if len(raw_stacks) != 2:
            raise ValueError("effective_stack must be one number or an OOP/IP pair.")
        stacks = tuple(_number(item, "effective_stack", minimum=0.01) for item in raw_stacks)
    else:
        stack = _number(raw_stacks, "effective_stack", minimum=0.01)
        stacks = (stack, stack)

    def sizes(raw, name, required):
        if type(raw) not in (list, tuple) or (required and not raw) or len(raw) > 8:
            raise ValueError(f"{name} must be a sequence with at most eight sizes.")
        parsed = tuple(sorted(set(_number(item, name, minimum=1e-9) for item in raw)))
        return parsed

    bets = sizes(value.get("bet_sizes", (0.5,)), "bet_sizes", True)
    raises = sizes(value.get("raise_sizes", ()), "raise_sizes", False)
    max_raises = value.get("max_raises", 0)
    if type(max_raises) is not int or not 0 <= max_raises <= 8:
        raise ValueError("max_raises must be an integer from 0 through 8.")
    include_all_in = value.get("include_all_in", True)
    if type(include_all_in) is not bool:
        raise ValueError("include_all_in must be boolean.")
    stack_value = list(stacks)
    return {
        "pot": pot,
        "effective_stack": stack_value,
        "bet_sizes": list(bets),
        "raise_sizes": list(raises),
        "max_raises": max_raises,
        "include_all_in": include_all_in,
        "_stacks": stacks,
    }


def _money(value):
    value = round(float(value), 9)
    return 0.0 if value == 0 else value


def _token(name, target):
    if name not in ("bet", "raise", "all_in"):
        return name
    return name + "@" + format(float(target), ".9f").rstrip("0").rstrip(".")


def _action(name, amount=0.0, target=0.0, full_raise=False):
    # A call exposes its actual binary64 target; its displayed amount is
    # rounded independently. Later fresh-street starting ledgers are cleaned.
    exposed_target = float(target) if name == "call" else _money(target)
    return {"name": name, "amount": _money(amount), "raise_to": exposed_target,
            "history_key": _token(name, target), "full_raise": bool(full_raise)}


def _add_sized(actions, name, target, committed, stack, full_raise=False):
    target = _money(min(stack, max(committed, target)))
    if target <= committed + EPSILON:
        return
    if target >= stack - EPSILON:
        name = "all_in"
    if any(abs(existing["raise_to"] - target) <= EPSILON for existing in actions):
        return
    actions.append(_action(name, target - committed, target, full_raise))


def _legal_actions(state, config):
    player = state["player"]
    other = 1 - player
    own, theirs = state["committed"][player], state["committed"][other]
    stack = config["_stacks"][player]
    owed = max(0.0, theirs - own)
    if abs(own - theirs) <= EPSILON:
        actions = [_action("check")]
        for fraction in config["bet_sizes"]:
            total_pot = config["pot"] + sum(state["committed"])
            requested = own + float(fraction) * total_pot
            _add_sized(actions, "bet", requested, own, stack)
        if config["include_all_in"]:
            _add_sized(actions, "all_in", stack, own, stack)
        return tuple(actions)

    actual_call = min(owed, stack - own)
    actions = [_action("fold"), _action("call", actual_call, own + actual_call)]
    if (stack > theirs + EPSILON and state["reopened"]
            and state["raises"] < config["max_raises"]
            and theirs < config["_stacks"][other] - EPSILON):
        call_target = theirs
        amount_owed = theirs - own
        pot_after_call = config["pot"] + sum(state["committed"]) + amount_owed
        for fraction in config["raise_sizes"]:
            requested = call_target + float(fraction) * pot_after_call
            minimum = call_target + state["increment"]
            target = min(stack, max(minimum, requested))
            increment = target - call_target
            full = increment + EPSILON >= state["increment"]
            if full:
                _add_sized(actions, "raise", target, own, stack, True)
            elif requested + EPSILON >= stack or minimum > stack:
                _add_sized(actions, "all_in", stack, own, stack, False)
        if config["include_all_in"] and stack > call_target + EPSILON:
            increment = stack - call_target
            _add_sized(actions, "all_in", stack, own, stack,
                       increment + EPSILON >= state["increment"])
    actions[2:] = sorted(actions[2:], key=lambda item: item["raise_to"])
    return tuple(actions)


def _pair_identities(oop, ip):
    if len(oop) * len(ip) > MAX_CANDIDATE_PAIRS:
        raise ValueError("Independent oracle exceeds 4,096 candidate private pairs.")
    pairs = []
    for hand0, weight0 in oop:
        for hand1, weight1 in ip:
            if set(hand0).isdisjoint(hand1):
                pairs.append((hand0, hand1, weight0 * weight1))
                if len(pairs) > MAX_PAIRS:
                    raise ValueError("Independent oracle supports at most four compatible pairs.")
    return pairs


def _canonical_runouts(runouts, board):
    remaining = tuple(card for card in DECK if card not in board)
    if runouts is None:
        return tuple((turn, river) for turn in remaining for river in remaining if turn != river)
    if type(runouts) in (str, bytes) or type(runouts) not in (list, tuple) or not runouts:
        raise ValueError("runouts must be a nonempty sequence of ordered two-card pairs.")
    requested = []
    for item in runouts:
        cards = _cards(item, count=2)
        if cards[0] == cards[1] or set(cards).intersection(board):
            raise ValueError("Runout cards must be distinct and outside the flop.")
        if cards in requested:
            raise ValueError("Duplicate ordered runout.")
        requested.append(cards)
    selected_set = set(requested)
    return tuple((turn, river) for turn in remaining for river in remaining
                 if turn != river and (turn, river) in selected_set)


def _world_data(board, oop, ip, runouts):
    pairs = _pair_identities(oop, ip)
    if not pairs:
        raise ValueError("Ranges contain no compatible private-hand pairs.")
    if len(pairs) > MAX_PAIRS:
        raise ValueError("Independent oracle supports at most four compatible pairs.")
    selected = _canonical_runouts(runouts, board)
    actual_world_bound = sum(
        sum(1 for turn, river in selected
            if turn not in set(board + hand0 + hand1)
            and river not in set(board + hand0 + hand1))
        for hand0, hand1, _ in pairs
    )
    if actual_world_bound > MAX_WORLDS:
        raise ValueError("Requested ordered runouts exceed the 7,920-world oracle cap.")
    if actual_world_bound == 0:
        raise ValueError("The requested physical worlds contain no compatible deals.")
    pending = []
    counts = []
    rank_cache = {}
    raw_normalizer = Fraction()
    for hand0, hand1, pair_weight in pairs:
        dead = set(board + hand0 + hand1)
        outcomes = []
        for turn, river in selected:
            if turn in dead or river in dead:
                continue
            outcomes.append((turn, river))
        wins = ties = losses = 0
        raw_mass = pair_weight / 1980
        for turn, river in outcomes:
            fullboard = board + (turn, river)
            rank_board = tuple(sorted(fullboard, key=DECK_INDEX.__getitem__))
            rank0_key, rank1_key = hand0 + rank_board, hand1 + rank_board
            if rank0_key not in rank_cache:
                rank_cache[rank0_key] = independent_rank(rank0_key)
            if rank1_key not in rank_cache:
                rank_cache[rank1_key] = independent_rank(rank1_key)
            rank0, rank1 = rank_cache[rank0_key], rank_cache[rank1_key]
            sign = (rank0 > rank1) - (rank0 < rank1)
            if sign > 0:
                wins += 1
            elif sign < 0:
                losses += 1
            else:
                ties += 1
            pending.append(("".join(hand0), "".join(hand1), raw_mass, sign, fullboard))
            raw_normalizer += raw_mass
        counts.append({
            "oop_hand": "".join(hand0), "ip_hand": "".join(hand1),
            "wins": wins, "ties": ties, "losses": losses,
            "ordered_outcomes": len(outcomes),
        })
    if raw_normalizer <= 0:
        raise ValueError("The requested physical worlds contain no compatible deals.")
    worlds = tuple((oop_hand, ip_hand, raw_mass / raw_normalizer, sign, fullboard)
                   for oop_hand, ip_hand, raw_mass, sign, fullboard in pending)
    for row in counts:
        prior = sum((world[2] for world in worlds
                     if world[0] == row["oop_hand"] and world[1] == row["ip_hand"]), Fraction())
        row["pair_probability_fraction"] = f"{prior.numerator}/{prior.denominator}"
        row["pair_probability"] = float(prior)
    return worlds, tuple(counts), raw_normalizer, selected, len(pairs), len(rank_cache)


def _terminal(history, kind, contributions, winner=None, counts=None):
    _reserve(counts, "terminal")
    return _Terminal(history, kind, contributions, winner)


def _reserve(counts, kind):
    if counts["total"] >= MAX_PUBLIC_STATES:
        raise ValueError("Independent public tree exceeds 250,000 public states.")
    if kind == "decision" and counts["decision"] >= MAX_DECISIONS:
        raise ValueError("Independent public tree exceeds 10,000 decision nodes.")
    counts[kind] += 1
    counts["total"] += 1


def _build_tree(board, configs, worlds):
    counts = {"decision": 0, "chance": 0, "terminal": 0, "total": 0}
    nodes = {}
    stacks = configs["flop"]["_stacks"]
    pot = configs["flop"]["pot"]

    def showdown(history, committed):
        return _terminal(history, "showdown", committed, counts=counts)

    def reveal(history, committed, street, subset):
        if street == "river":
            return showdown(history, committed)
        _reserve(counts, "chance")
        card_index = 3 if street == "flop" else 4
        card_groups = defaultdict(list)
        for world in subset:
            card_groups[world[4][card_index]].append(world)
        next_street = "turn" if street == "flop" else "river"
        config = configs[next_street]
        branches = {}
        for card in sorted(card_groups, key=DECK_INDEX.__getitem__):
            next_history = history + (f"{next_street}@{card}",)
            next_board = board + tuple(token[6:] if token.startswith("river@") else token[5:]
                                       for token in next_history if token.startswith(("turn@", "river@")))
            if any(min(committed) >= stack - EPSILON for stack in stacks):
                branches[card] = reveal(next_history, committed, next_street, card_groups[card])
            else:
                branches[card] = betting(next_history, next_board, next_street,
                                         0, (_money(min(committed)), _money(min(committed))),
                                         0.0, 0, True, 0, card_groups[card], config)
        return _Chance(history, card_index, next_street, branches)

    def settled(history, current_board, street, committed, subset):
        matched = min(committed)
        carried = (matched, matched)
        if street == "river":
            return showdown(history, carried)
        return reveal(history, carried, street, subset)

    def betting(history, current_board, street, player, committed, increment,
                raises, reopened, checks, subset, config):
        if committed[player] >= config["_stacks"][player] - EPSILON:
            return settled(history, current_board, street, committed, subset)
        _reserve(counts, "decision")
        if len(history) > 32:
            raise ValueError("Independent public history exceeds 32 actions/reveals.")
        state = {"player": player, "committed": committed,
                 "increment": increment, "raises": raises, "reopened": reopened}
        actions = _legal_actions(state, config)
        children = []
        other = 1 - player
        for action in actions:
            name = action["name"]
            next_history = history + (action["history_key"],)
            if name == "fold":
                children.append(_terminal(history, "fold", committed, other, counts))
                continue
            if name == "call":
                next_committed = list(committed)
                next_committed[player] = action["raise_to"]
                children.append(settled(next_history, current_board, street,
                                        tuple(next_committed), subset))
                continue
            if name == "check":
                if checks == 1:
                    children.append(settled(next_history, current_board, street, committed, subset))
                else:
                    children.append(betting(next_history, current_board, street, other,
                                            committed, increment, raises, reopened,
                                            checks + 1, subset, config))
                continue

            next_committed = list(committed)
            next_committed[player] = action["raise_to"]
            opening = abs(committed[player] - committed[other]) <= EPSILON
            if opening:
                next_increment = action["amount"]
                next_raises = 0
                next_reopened = True
            else:
                full = action["full_raise"]
                inc = action["raise_to"] - committed[other]
                next_increment = inc if full else increment
                next_raises = raises + 1
                next_reopened = full
            children.append(betting(next_history, current_board, street, other,
                                    tuple(next_committed), next_increment,
                                    next_raises, next_reopened, 0, subset, config))
        node = _Decision(history, player, street, current_board, actions, children)
        key = (player, tuple(history))
        if key in nodes:
            raise RuntimeError("Independent public decision key collision.")
        nodes[key] = node
        return node

    root = betting((), board, "flop", 0, (0.0, 0.0), 0.0, 0, True, 0,
                   worlds, configs["flop"])
    return root, nodes, counts


def _normalize_configs(config, turn_config=None, river_config=None):
    base = _configuration(config)
    turn = _configuration(config if turn_config is None else turn_config)
    river = _configuration(config if river_config is None else river_config)
    for stage in (turn, river):
        if stage["pot"] != base["pot"] or stage["_stacks"] != base["_stacks"]:
            raise ValueError("Street configs must preserve original pot and total stack caps.")
    return {"flop": base, "turn": turn, "river": river}


def prepare_oracle(board, oop_hands, ip_hands, config, *,
                   turn_config=None, river_config=None, runouts=None):
    """Prepare an independently constructed flop-start physical game.

    ``oop_hands`` and ``ip_hands`` are literal ``[[hand, weight], ...]`` rows;
    no range-expression parser or production range expander is used. ``runouts``
    is either omitted for the full 45-by-44 ordered future deck per private
    pair, or a unique sequence of ordered ``(turn, river)`` pairs that globally
    conditions the physical joint distribution.
    """
    if type(board) is str:
        if len(board) != 6:
            raise ValueError("A flop board string must contain exactly three cards.")
        board = (board[0:2], board[2:4], board[4:6])
    board_cards = _cards(board, count=3)
    configs = _normalize_configs(config, turn_config, river_config)
    oop = _hand_rows(oop_hands, board_cards)
    ip = _hand_rows(ip_hands, board_cards)
    pairs = _pair_identities(oop, ip)
    if not pairs:
        raise ValueError("Ranges contain no compatible private-hand pairs.")
    if len(pairs) > MAX_PAIRS:
        raise ValueError("Independent oracle supports at most four compatible pairs.")
    worlds, pair_counts, normalizer, selected, pair_count, rank_calls = _world_data(
        board_cards, oop, ip, runouts)
    root, nodes, counts = _build_tree(board_cards, configs, worlds)
    chance_visits = sum(1 for _ in _walk(root) if isinstance(_, _Chance))
    terminal_count = sum(1 for _ in _walk(root) if isinstance(_, _Terminal))
    pair_probabilities = {(row["oop_hand"], row["ip_hand"]): row["pair_probability"]
                          for row in pair_counts}
    world_count_per_pair = {row["oop_hand"] + "/" + row["ip_hand"]: row["ordered_outcomes"]
                            for row in pair_counts}
    active_by_prefix = defaultdict(set)
    for world in worlds:
        future = world[4][3:]
        for player in (0, 1):
            for length in range(3):
                active_by_prefix[(player, tuple(future[:length]))].add(world[player])
    return {
        "active_hands_by_prefix": dict(active_by_prefix),
        "board": board_cards,
        "config": _public_config(configs["flop"]),
        "street_configs": {street: _public_config(value) for street, value in configs.items()},
        "runouts": selected,
        "reachable_runouts": tuple(sorted({world[4][3:] for world in worlds},
                                           key=lambda runout: tuple(DECK_INDEX[c] for c in runout))),
        "runout_mode": "full-deck" if runouts is None else "conditioned-ordered-subset",
        "normalizer": normalizer,
        "worlds": worlds,
        "deals": worlds,
        "counts": pair_counts,
        "pair_counts": pair_counts,
        "pair_probabilities": pair_probabilities,
        "world_count_per_pair": world_count_per_pair,
        "root": root,
        "nodes": nodes,
        "public_nodes": counts["decision"],
        "public_states": counts["total"],
        "chance_nodes": counts["chance"],
        "terminal_nodes": counts["terminal"],
        "compatible_pairs": pair_count,
        "physical_worlds": len(worlds),
        "worlds_count": len(worlds),
        "pot": configs["flop"]["pot"],
        "effective_stack": list(configs["flop"]["_stacks"]),
        "source_counters": {
            "rank_hand_calls": rank_calls,
            "physical_world_rows": len(worlds),
            "pair_runout_rows_checked": sum(row["ordered_outcomes"] for row in pair_counts),
            "world_count_by_pair": world_count_per_pair,
        },
    }


def _public_config(config):
    return {key: value for key, value in config.items() if not key.startswith("_")}


def _config_matches(actual, expected):
    try:
        normalized = _configuration(actual)
        wanted = _configuration(expected)
    except (TypeError, ValueError):
        return False
    return all(normalized[key] == wanted[key] for key in
               ("pot", "_stacks", "bet_sizes", "raise_sizes", "max_raises", "include_all_in"))


def _walk(node):
    yield node
    if isinstance(node, _Decision):
        for child in node.children:
            yield from _walk(child)
    elif isinstance(node, _Chance):
        for card in sorted(node.branches, key=DECK_INDEX.__getitem__):
            yield from _walk(node.branches[card])


def _revealed(history):
    cards = []
    for token in history:
        if token.startswith("turn@"):
            cards.append(token[5:])
        elif token.startswith("river@"):
            cards.append(token[6:])
    return tuple(cards)


def _canonical_hand_label(value):
    if type(value) is not str or len(value) != 4:
        raise ValueError("Strategy row has an invalid private hand.")
    parsed = (_card(value[:2]), _card(value[2:]))
    if parsed[0] == parsed[1]:
        raise ValueError("Strategy row has an invalid private hand.")
    return "".join(sorted(parsed))


def _validate_policy(result, oracle, tolerance):
    if type(result) is not dict or type(result.get("strategy")) is not list:
        raise ValueError("Result must contain a serialized strategy list.")
    if result.get("solver_version") != "configured-postflop-v1":
        raise ValueError("Expected the configured flop-start solver contract.")
    if result.get("strategy_schema") != "postflop-strategy-v1":
        raise ValueError("Expected postflop-strategy-v1 policy rows.")
    if tuple(result.get("board", ())) != oracle["board"]:
        raise ValueError("Result board does not match the independent oracle.")
    actual_stages = result.get("street_configs")
    expected_stages = oracle["street_configs"]
    if (not _config_matches(result.get("config"), oracle["config"]) or
            type(actual_stages) is not dict or set(actual_stages) != set(expected_stages) or
            any(not _config_matches(actual_stages[stage], expected_stages[stage])
                for stage in expected_stages)):
        raise ValueError("Result street configuration differs from the independent oracle.")
    if result.get("runout_mode") != oracle["runout_mode"]:
        raise ValueError("Result runout mode differs from the independent oracle.")
    got_runouts = result.get("runouts")
    if type(got_runouts) is not list:
        raise ValueError("Result runouts must be a serialized list.")
    parsed_result_runouts = tuple(tuple(_card(c) for c in row) for row in got_runouts)
    if parsed_result_runouts != oracle["runouts"]:
        raise ValueError("Result runouts differ from the independent physical selection.")
    rows = {}
    expected_rows = set()
    for (player, history), node in oracle["nodes"].items():
        for hand in sorted(oracle["active_hands_by_prefix"].get((player, _revealed(history)), ())):
            expected_rows.add((player, hand, history))

    for row in result["strategy"]:
        if type(row) is not dict:
            raise ValueError("Strategy rows must be mappings.")
        player_name = row.get("player")
        if player_name not in ("oop", "ip"):
            raise ValueError("Strategy row has an invalid player.")
        player = 0 if player_name == "oop" else 1
        hand = _canonical_hand_label(row.get("hand"))
        if hand != row["hand"]:
            raise ValueError("Strategy private hand must use its canonical identity.")
        history_raw = row.get("history")
        if type(history_raw) is not list or any(type(token) is not str for token in history_raw):
            raise ValueError("Strategy history must be a list of public tokens.")
        history = tuple(history_raw)
        key = (player, hand, history)
        if key in rows:
            raise ValueError("Duplicate serialized information set.")
        node = oracle["nodes"].get((player, history))
        if node is None:
            raise ValueError("Strategy contains an unreachable or extra information set.")
        own_hands = oracle["active_hands_by_prefix"].get((player, _revealed(history)), set())
        if hand not in own_hands:
            raise ValueError("Strategy row contains an inactive or opponent hand.")
        if row.get("street") != node.street:
            raise ValueError("Strategy row has an incorrect street.")
        public_board = oracle["board"] + _revealed(history)
        if tuple(row.get("board", ())) != public_board:
            raise ValueError("Strategy row reveals a future or private card.")
        actual_actions = row.get("actions")
        if type(actual_actions) is not list or len(actual_actions) != len(node.actions):
            raise ValueError("Strategy row has a missing, extra, or reordered legal action.")
        probabilities = []
        for actual, expected in zip(actual_actions, node.actions):
            if type(actual) is not dict:
                raise ValueError("Strategy actions must be mappings.")
            for field in ("name", "history_key"):
                if actual.get(field) != expected[field]:
                    raise ValueError("Serialized action differs from independent numeric rules.")
            for field in ("amount", "raise_to"):
                if type(actual.get(field)) not in (int, float):
                    raise ValueError("Serialized action amounts must be JSON numbers.")
                try:
                    number = float(actual[field])
                except (KeyError, TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("Serialized action amount is invalid.") from exc
                if isinstance(actual[field], bool) or not isfinite(number) or number != expected[field]:
                    raise ValueError("Serialized action amount differs from independent numeric rules.")
            if type(actual.get("probability")) not in (int, float):
                raise ValueError("Action probability must be a JSON number.")
            try:
                probability = float(actual["probability"])
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Action probability must be finite and in [0, 1].") from exc
            if isinstance(actual["probability"], bool) or not isfinite(probability) or probability < 0 or probability > 1:
                raise ValueError("Action probability must be finite and in [0, 1].")
            probabilities.append(probability)
        if abs(fsum(probabilities) - 1.0) > max(tolerance, 1e-12):
            raise ValueError("Action probabilities must sum to one.")
        rows[key] = tuple(probabilities)
    if set(rows) != expected_rows:
        raise ValueError("Serialized policy is missing or contains unexpected information sets.")
    if (result.get("worlds") != len(oracle["worlds"])
            or result.get("compatible_pairs") != oracle["compatible_pairs"]
            or result.get("deals") != oracle["compatible_pairs"]):
        raise ValueError("Serialized world/private-pair count differs from independent enumeration.")
    reachable = tuple(tuple(row) for row in result.get("reachable_runouts", ()))
    if reachable != oracle["reachable_runouts"]:
        raise ValueError("Serialized reachable ordered runouts differ from independent worlds.")
    return rows


def _world_visibly_reachable(world, history):
    reveals = _revealed(history)
    future = world[4][3:]
    return tuple(future[:len(reveals)]) == reveals


def _payoff(node, world, pot):
    unit = pot / 2.0 + min(node.contributions)
    if node.kind == "fold":
        sign = 1 if node.winner == 0 else -1
    else:
        sign = world[3]
    return sign * unit


def _best_response(root, worlds, rows, pot, player):
    """Own-hand response with hidden opponents/future outcomes summed before max."""
    def visit(node, weighted_worlds):
        if isinstance(node, _Terminal):
            return fsum(weight * _payoff(node, world, pot) * (1 if player == 0 else -1)
                        for world, weight in weighted_worlds)
        if isinstance(node, _Chance):
            groups = defaultdict(list)
            for world, weight in weighted_worlds:
                groups[world[4][node.card_index]].append((world, weight))
            return fsum(visit(node.branches[card], group)
                        for card, group in sorted(groups.items(), key=lambda item: DECK_INDEX[item[0]]))
        if node.player == player:
            if len({world[player] for world, _ in weighted_worlds}) > 1:
                raise RuntimeError("Independent BR reached a node before separating own hand.")
            values = [visit(child, weighted_worlds) for child in node.children]
            return max(values)
        result = 0.0
        for action_index, child in enumerate(node.children):
            group = [(world, weight * rows[(node.player, world[node.player], node.history)][action_index])
                     for world, weight in weighted_worlds]
            result += visit(child, group)
        return result

    total = 0.0
    own_hands = sorted({world[player] for world in worlds})
    for hand in own_hands:
        group = [(world, float(world[2])) for world in worlds if world[player] == hand]
        total += visit(root, group)
    return total



def replay(result, oracle, tolerance=1e-10):
    """Validate serialized rows and independently compute profile/value/BRs.

    Best responses maximize separately for each player's own private hand at
    every full public history. Opponent hands and unrevealed future cards stay
    grouped until their information is legally revealed.
    """
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not isfinite(float(tolerance)) or tolerance < 0:
        raise ValueError("tolerance must be a finite nonnegative number.")
    rows = _validate_policy(result, oracle, float(tolerance))
    pot = oracle["pot"]
    worlds = oracle["worlds"]

    def profile(node, world):
        if isinstance(node, _Terminal):
            return _payoff(node, world, pot)
        if isinstance(node, _Chance):
            return profile(node.branches[world[4][node.card_index]], world)
        probs = rows[(node.player, world[node.player], node.history)]
        return fsum(prob * profile(child, world)
                    for prob, child in zip(probs, node.children))

    value = fsum(float(world[2]) * profile(oracle["root"], world) for world in worlds)

    br_oop = _best_response(oracle["root"], worlds, rows, pot, 0)
    br_ip_own = _best_response(oracle["root"], worlds, rows, pot, 1)
    if br_oop < value - tolerance or br_ip_own < -value - tolerance:
        raise ValueError("Independent best responses violate legal response bounds.")
    nash_conv = max(0.0, br_oop + br_ip_own)
    metrics = {
        "value_oop": value,
        "value_ip": -value,
        "oop_best_response_value": br_oop,
        "ip_best_response_value": br_ip_own,
        "oop_best_response_gain": max(0.0, br_oop - value),
        "ip_best_response_gain": max(0.0, br_ip_own + value),
        "nash_conv": nash_conv,
        "exploitability": nash_conv / 2.0,
    }
    gaps = {}
    for key, expected in metrics.items():
        if type(result.get(key)) not in (int, float):
            raise ValueError("Result metrics must be JSON numbers: " + key)
        try:
            actual = float(result[key])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Result metric {key} is missing or invalid.") from exc
        if isinstance(result[key], bool) or not isfinite(actual):
            raise ValueError(f"Result metric {key} must be finite.")
        gaps[key] = abs(actual - expected)
    if any(gap > tolerance for gap in gaps.values()):
        raise ValueError(f"Serialized metrics differ from independent replay: {gaps}")
    if result.get("info_sets") != len(rows):
        raise ValueError("Serialized information-set count differs from policy rows.")
    if result.get("public_nodes") != oracle["public_nodes"]:
        raise ValueError("Serialized public-node count differs from independent tree.")
    if result.get("public_states") != oracle["public_states"]:
        raise ValueError("Serialized public-state count differs from independent tree.")
    for field in ("chance_nodes", "terminal_nodes"):
        if type(result.get(field)) is not int or result[field] != oracle[field]:
            raise ValueError("Serialized node census differs from independent tree: " + field)
    if result.get("chance_nodes") != oracle["chance_nodes"] or result.get("terminal_nodes") != oracle["terminal_nodes"]:
        raise ValueError("Serialized chance/terminal node counts differ from independent tree.")
    return {
        **metrics,
        "scalar_absolute_gaps": gaps,
        "checked_information_sets": len(rows),
        "checked_physical_worlds": len(worlds),
        "checked_public_nodes": oracle["public_nodes"],
        "checked_public_states": oracle["public_states"],
    }
