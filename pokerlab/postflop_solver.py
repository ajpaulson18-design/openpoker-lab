"""Exact finite heads-up postflop games for flop, turn, or river starts.

The solver enumerates compatible private-hand pairs and all requested future
public-card outcomes. Selected outcomes condition one joint physical game.
It is a bounded action abstraction, not a full no-limit Hold'em solver.
"""
from dataclasses import dataclass

from .cards import DECK, cards, expand_range, rank_hand
from .cfr import train, evaluate, best_response
from .planned_cfr import train as train_planned, MAX_PLAN_OPS
from .public_cfr import train_public_batched, MAX_PREFIX_EDGES
from .river_config import RiverConfig
from .river_tree import _Node, _Terminal, _build_tree, _terminal_value


_MAX_CANDIDATE_HAND_ITERATIONS = 3_000_000
_MAX_WORLD_ITERATIONS = 3_000_000
_MAX_PUBLIC_NODES = 10_000
_MAX_PUBLIC_STATES = 250_000
_MAX_WORLD_NODE_WORK = 30_000_000


@dataclass
class _Chance:
    """A public card reveal keyed by its position in each static world."""

    history: tuple
    branches: dict
    card_index: int = 4
    street: str = "river"


def _canonical_pairs(runouts, board):
    if isinstance(runouts, (str, bytes)):
        raise ValueError("Flop runouts must be ordered (turn, river) card pairs.")
    selected = []
    for sequence in runouts:
        if not isinstance(sequence, (tuple, list)) or len(sequence) != 2:
            raise ValueError("Each flop runout must contain an ordered turn and river card.")
        turn, river = cards(sequence)
        if turn == river or turn in board or river in board:
            raise ValueError("Runout cards must be distinct and outside the known board.")
        selected.append((turn, river))
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("Runouts must be a nonempty set of unique ordered pairs.")
    selected_set = set(selected)
    deck = [card for card in DECK if card not in board]
    return tuple((turn, river) for turn in deck for river in deck
                 if turn != river and (turn, river) in selected_set)


def _enumerate_worlds(board, oop_range, ip_range, runouts=None, iterations=10):
    """Return hands, normalized worlds, selected future cards, and pair count.

    World layout is ``(oop_index, ip_index, weight, showdown_sign, *future)``.
    A flop world contains ordered ``(turn, river)`` future cards, a turn world
    contains one river, and a river world has no future card fields.
    """
    board = cards(board)
    if len(board) not in (3, 4, 5):
        raise ValueError("Postflop board must contain exactly three, four, or five cards.")
    if type(iterations) is not int or iterations < 1:
        raise ValueError("World enumeration iterations must be a positive integer.")

    future_count = 5 - len(board)
    if future_count == 2:
        if runouts is None:
            remaining = tuple(card for card in DECK if card not in board)
            selected = tuple((turn, river) for turn in remaining for river in remaining
                             if turn != river)
        else:
            selected = _canonical_pairs(runouts, board)
        denominator = 45 * 44
    elif future_count == 1:
        remaining = tuple(card for card in DECK if card not in board)
        if runouts is None:
            selected = remaining
        else:
            requested = cards(runouts)
            if not requested or set(requested).intersection(board):
                raise ValueError("River runouts must be nonempty unique cards outside the turn board.")
            selected_set = set(requested)
            selected = tuple(card for card in remaining if card in selected_set)
        denominator = 44
    else:
        if runouts is not None:
            raise ValueError("A five-card board has no future public-card runouts.")
        selected = ()
        denominator = 1

    ranges = (expand_range(oop_range, board), expand_range(ip_range, board))
    hands = (list(ranges[0]), list(ranges[1]))
    if len(hands[0]) * len(hands[1]) * iterations > _MAX_CANDIDATE_HAND_ITERATIONS:
        raise ValueError("Postflop solver allows 3 million candidate hand-pair iterations.")

    worlds, compatible_pairs, rank_cache = [], 0, {}
    for oop_index, oop_hand in enumerate(hands[0]):
        for ip_index, ip_hand in enumerate(hands[1]):
            if not set(oop_hand).isdisjoint(ip_hand):
                continue
            if future_count == 2:
                legal_future = ((turn, river) for turn, river in selected
                                if turn not in oop_hand + ip_hand and
                                river not in oop_hand + ip_hand)
            elif future_count == 1:
                legal_future = ((river,) for river in selected
                                if river not in oop_hand + ip_hand)
            else:
                legal_future = ((),)

            pair_worlds = list(legal_future)
            if not pair_worlds:
                continue
            compatible_pairs += 1
            raw_mass = ranges[0][oop_hand] * ranges[1][ip_hand] / denominator
            for future in pair_worlds:
                # Hold'em showdown rank depends on the final board, not reveal
                # order. Keep ordered worlds distinct for strategy/chance while
                # sharing this rank computation across swapped card orderings.
                rank_board = tuple(sorted(future))
                key0 = (0, oop_index, rank_board)
                key1 = (1, ip_index, rank_board)
                if key0 not in rank_cache:
                    rank_cache[key0] = rank_hand(oop_hand + board + rank_board)
                if key1 not in rank_cache:
                    rank_cache[key1] = rank_hand(ip_hand + board + rank_board)
                rank0, rank1 = rank_cache[key0], rank_cache[key1]
                sign = (rank0 > rank1) - (rank0 < rank1)
                worlds.append((oop_index, ip_index, raw_mass, sign, *future))
                if len(worlds) * iterations > _MAX_WORLD_ITERATIONS:
                    raise ValueError("Postflop solver allows 3 million world iterations.")

    normalizer = sum(world[2] for world in worlds)
    if normalizer <= 0:
        raise ValueError("Ranges and future runouts contain no compatible physical deals.")
    normalized = [(world[0], world[1], world[2] / normalizer, *world[3:])
                  for world in worlds]
    return hands, normalized, selected, compatible_pairs


def _chance_child(node, world):
    if not isinstance(node, _Chance):
        return None
    # A missing branch means a malformed chance tree/world pairing. Let the
    # lookup fail loudly instead of treating it as a terminal node.
    return node.branches[world[node.card_index]]


def _chance_partitions(node, weighted_worlds):
    if not isinstance(node, _Chance):
        return None
    groups = {}
    for world in weighted_worlds:
        groups.setdefault(world[node.card_index], []).append(world)
    return [(node.branches[card], group) for card, group in groups.items()]


def _node_key(node, world):
    return node.player, world[node.player], node.history


def _build_public_tree(board_length, config, *, turn_config=None, river_config=None,
                       worlds, allocation_counts=None):
    """Build a public tree with zero, one, or two future chance layers.

    Configurations share the original pot and total stack caps. Contributions
    are cumulative across streets; unmatched excess is returned before a fresh
    street starts OOP. All-in branches still traverse every remaining reveal.
    """
    if board_length not in (3, 4, 5):
        raise ValueError("Postflop board must contain exactly three, four, or five cards.")
    if board_length == 3:
        later_configs = (turn_config or config, river_config or config)
    elif board_length == 4:
        later_configs = (river_config or config,)
    else:
        later_configs = ()
    if any(stage.pot != config.pot or stage.stacks != config.stacks
           for stage in later_configs):
        raise ValueError("Street configs must preserve the original pot and stack caps.")

    counts = {} if allocation_counts is None else allocation_counts
    counts.update(decision=0, chance=0, terminal=0, total=0)

    def reserve(kind):
        if counts["total"] >= _MAX_PUBLIC_STATES:
            raise ValueError("Postflop tree exceeds 250,000 public states.")
        if kind == "decision" and counts["decision"] >= _MAX_PUBLIC_NODES:
            raise ValueError("Postflop solver public tree exceeds 10,000 decision nodes.")
        counts[kind] += 1
        counts["total"] += 1

    def showdown(contributions):
        reserve("terminal")
        return _Terminal("showdown", contributions)

    def add_tree(stage_config, **kwargs):
        root, _ = _build_tree(stage_config, allocation_hook=reserve, **kwargs)
        return root

    def is_all_in(contributions):
        matched = min(contributions)
        return any(matched >= stack - 1e-9 for stack in config.stacks)

    if board_length == 5:
        root = add_tree(config)
    elif board_length == 4:
        river_config = later_configs[0]
        river_cards = tuple(sorted({world[4] for world in worlds}))

        def settled(history, contributions):
            reserve("chance")
            matched = min(contributions)
            carried = (matched, matched)
            branches = {}
            for river in river_cards:
                river_history = history + (f"river@{river}",)
                if is_all_in(carried):
                    branches[river] = showdown(carried)
                else:
                    branches[river] = add_tree(
                        river_config, starting_history=river_history,
                        starting_contributions=carried)
            return _Chance(history, branches, 4, "river")

        root = add_tree(config, showdown_factory=settled)
    else:
        turn_config, river_config = later_configs
        turns = tuple(sorted({world[4] for world in worlds}))
        rivers_by_turn = {
            turn: tuple(sorted({world[5] for world in worlds if world[4] == turn}))
            for turn in turns
        }

        def river_chance(history, contributions, turn):
            reserve("chance")
            matched = min(contributions)
            carried = (matched, matched)
            branches = {}
            for river in rivers_by_turn[turn]:
                river_history = history + (f"river@{river}",)
                if is_all_in(carried):
                    branches[river] = showdown(carried)
                else:
                    branches[river] = add_tree(
                        river_config, starting_history=river_history,
                        starting_contributions=carried)
            return _Chance(history, branches, 5, "river")

        def after_turn_reveal(history, contributions, turn):
            matched = min(contributions)
            carried = (matched, matched)
            if is_all_in(carried):
                return river_chance(history, carried, turn)
            return add_tree(
                turn_config, starting_history=history,
                starting_contributions=carried,
                showdown_factory=lambda turn_history, turn_contributions:
                    river_chance(turn_history, turn_contributions, turn))

        def after_flop_settles(history, contributions):
            reserve("chance")
            branches = {
                turn: after_turn_reveal(history + (f"turn@{turn}",),
                                         contributions, turn)
                for turn in turns
            }
            return _Chance(history, branches, 4, "turn")

        root = add_tree(config, showdown_factory=after_flop_settles)

    nodes = {}

    def collect(node):
        if isinstance(node, _Chance):
            for child in node.branches.values():
                collect(child)
        elif isinstance(node, _Node):
            nodes[(node.player, node.history)] = node
            for child in node.children:
                collect(child)

    try:
        collect(root)
    finally:
        # The recursive collector otherwise retains the complete tree in a cycle.
        collect = None
    if len(nodes) > _MAX_PUBLIC_NODES:
        raise ValueError("Postflop solver public tree exceeds 10,000 decision nodes.")

    def visited(node):
        if isinstance(node, _Chance):
            return max((visited(child) for child in node.branches.values()), default=0)
        if isinstance(node, _Terminal):
            return 0
        return 1 + sum(visited(child) for child in node.children)

    def plan_operations(node):
        if isinstance(node, _Chance):
            return max((plan_operations(child) for child in node.branches.values()), default=0)
        if isinstance(node, _Terminal):
            return 1
        return 1 + sum(plan_operations(child) for child in node.children)

    try:
        return root, nodes, counts["chance"], visited(root), plan_operations(root)
    finally:
        visited = None
        plan_operations = None


def _build_postflop_tree(board, config, *, turn_config=None, river_config=None,
                         worlds, allocation_counts=None):
    """Validate a concrete board and delegate to the card-count tree builder."""
    board = cards(board)
    if len(board) not in (3, 4, 5):
        raise ValueError("Postflop board must contain exactly three, four, or five cards.")
    return _build_public_tree(len(board), config, turn_config=turn_config,
                              river_config=river_config, worlds=worlds,
                              allocation_counts=allocation_counts)


def _prefix_hand_index(worlds):
    """Precompute legal own hands by revealed public-card prefix."""
    result = {(player, ()): set() for player in (0, 1)}
    for world in worlds:
        future = tuple(world[4:])
        for player in (0, 1):
            hand_index = world[player]
            result[(player, ())].add(hand_index)
            for prefix_length in range(1, len(future) + 1):
                result.setdefault((player, future[:prefix_length]), set()).add(hand_index)
    return result


def _public_reveals(history):
    reveals = []
    for token in history:
        if token.startswith("turn@"):
            reveals.append(token[5:])
        elif token.startswith("river@"):
            reveals.append(token[6:])
    return tuple(reveals)


def solve_postflop(board, oop_range, ip_range, config=None, *, turn_config=None,
                   river_config=None, runouts=None, iterations=1000,
                   algorithm="vanilla", traversal="recursive"):
    """Solve an exact configured heads-up game from flop, turn, or river.

    The initial ``config`` applies to the first unresolved street. For a flop
    start, ``turn_config`` and ``river_config`` may change street sizing. For a
    turn start, only ``river_config`` may override sizing. All configs preserve
    the starting pot and total stack caps. This excludes preflop and multiway.
    """
    board = cards(board)
    if len(board) not in (3, 4, 5):
        raise ValueError("Postflop board must contain exactly three, four, or five cards.")
    if algorithm not in ("vanilla", "dcfr"):
        raise ValueError("Solver algorithm must be vanilla or dcfr.")
    if traversal not in ("recursive", "planned", "public-batched"):
        raise ValueError("Traversal must be recursive, planned, or public-batched.")
    if type(iterations) is not int or not 10 <= iterations <= 10_000:
        raise ValueError("Use 10-10,000 solver iterations.")
    config = RiverConfig() if config is None else config
    if not isinstance(config, RiverConfig):
        config = RiverConfig.from_dict(config)

    def normalize_stage(stage):
        if stage is None or isinstance(stage, RiverConfig):
            return stage
        return RiverConfig.from_dict(stage)

    turn_config = normalize_stage(turn_config)
    river_config = normalize_stage(river_config)

    if len(board) == 3:
        turn_config = config if turn_config is None else turn_config
        river_config = config if river_config is None else river_config
        stages = {"flop": config, "turn": turn_config, "river": river_config}
    elif len(board) == 4:
        if turn_config is not None:
            raise ValueError("For a turn start, pass the first-street config as config.")
        river_config = config if river_config is None else river_config
        stages = {"turn": config, "river": river_config}
    else:
        if turn_config is not None or river_config is not None:
            raise ValueError("For a river start, only config applies.")
        stages = {"river": config}
    if any(stage.pot != config.pot or stage.stacks != config.stacks
           for stage in stages.values()):
        raise ValueError("Street configs must preserve the original pot and stack caps.")

    hands, worlds, selected, pair_count = _enumerate_worlds(
        board, oop_range, ip_range, runouts, iterations)
    public_counts = {}
    root, nodes, chance_nodes, visited_nodes, plan_ops_per_world = \
        _build_postflop_tree(board, config, turn_config=turn_config,
                             river_config=river_config, worlds=worlds,
                             allocation_counts=public_counts)
    if len(worlds) * visited_nodes * iterations > _MAX_WORLD_NODE_WORK:
        raise ValueError("Postflop solver exceeds 30 million world-node iterations.")
    if traversal == "planned" and len(worlds) * plan_ops_per_world > MAX_PLAN_OPS:
        raise ValueError("Planned postflop traversal exceeds 250,000 operations.")

    legal_hands = _prefix_hand_index(worlds)
    infos, metadata = {}, {}
    for (player, history), node in nodes.items():
        prefix = _public_reveals(history)
        for hand_index in sorted(legal_hands.get((player, prefix), ())):
            key = (player, hand_index, history)
            infos[key] = len(node.actions)
            metadata[key] = node

    payoff = lambda node, world: _terminal_value(node, world[3], config.pot)
    if traversal == "public-batched":
        averages = train_public_batched(root, worlds, infos, iterations, algorithm,
                                        pot=config.pot, chance_type=_Chance)
    else:
        trainer = train_planned if traversal == "planned" else train
        averages = trainer(root, worlds, infos, iterations, algorithm, payoff,
                           _node_key, _chance_child)
    value = evaluate(root, worlds, averages, payoff, _node_key, _chance_child)
    br0 = best_response(0, root, worlds, averages, payoff, _node_key,
                        _chance_partitions)
    br1 = best_response(1, root, worlds, averages, payoff, _node_key,
                        _chance_partitions)

    rows = []
    for key in sorted(infos):
        player, hand_index, history = key
        node = metadata[key]
        reveals = _public_reveals(history)
        public_board = board + reveals
        street = {3: "flop", 4: "turn", 5: "river"}[len(public_board)]
        rows.append({
            "player": "oop" if player == 0 else "ip",
            "hand": "".join(hands[player][hand_index]),
            "street": street,
            "board": list(public_board),
            "history": list(history),
            "actions": [{"name": action.name, "amount": action.amount,
                         "raise_to": action.raise_to, "history_key": action.token,
                         "probability": probability}
                        for action, probability in zip(node.actions, averages[key])],
        })
    nash_conv = max(0.0, br0 + br1)
    config_fields = {stage: value.to_dict() for stage, value in stages.items()}
    reachable_futures = {tuple(world[4:]) for world in worlds}
    if len(board) == 3:
        reachable_runouts = [list(sequence) for sequence in selected
                             if sequence in reachable_futures]
    elif len(board) == 4:
        reachable_runouts = [card for card in selected
                             if (card,) in reachable_futures]
    else:
        reachable_runouts = []
    if len(board) == 3:
        runout_mode = "full-deck" if runouts is None else "conditioned-ordered-subset"
        chance_note = "Joint private-pair/ordered turn-river physical worlds normalized once; 45 then 44 cards per pair."
    elif len(board) == 4:
        runout_mode = "full-deck" if runouts is None else "conditioned-subset"
        chance_note = "Joint private-pair/river physical worlds normalized once; 44 rivers per pair before subset conditioning."
    else:
        runout_mode = "none"
        chance_note = "Compatible private-pair range products normalized once; board is complete."
    return {
        "method": "full-traversal CFR", "algorithm": algorithm,
        "solver_version": "configured-postflop-v1",
        "strategy_schema": "postflop-strategy-v1",
        "execution_backend": f"{traversal}-python",
        "plan_operation_limit": MAX_PLAN_OPS if traversal == "planned" else None,
        "public_batch_edge_limit": MAX_PREFIX_EDGES if traversal == "public-batched" else None,
        "backend": "exact-public-chance-tree", "board": list(board),
        "config": config.to_dict(), "street_configs": config_fields,
        "turn_config": None if "turn" not in stages else stages["turn"].to_dict(),
        "river_config": None if "river" not in stages else stages["river"].to_dict(),
        "runouts": [list(item) if isinstance(item, tuple) else item for item in selected],
        "reachable_runouts": reachable_runouts,
        "runout_mode": runout_mode, "chance_note": chance_note,
        "iterations": iterations, "deals": pair_count,
        "compatible_pairs": pair_count, "worlds": len(worlds),
        "info_sets": len(infos), "public_nodes": len(nodes),
        "public_states": public_counts["total"],
        "terminal_nodes": public_counts["terminal"],
        "public_state_limit": _MAX_PUBLIC_STATES,
        "chance_nodes": chance_nodes, "world_traversal_nodes": visited_nodes,
        "tree_actions": sum(len(node.actions) for node in nodes.values()),
        "pot": config.pot, "effective_stack": config.to_dict()["effective_stack"],
        "value_oop": value, "value_ip": -value,
        "oop_best_response_value": br0, "ip_best_response_value": br1,
        "oop_best_response_gain": max(0.0, br0 - value),
        "ip_best_response_gain": max(0.0, br1 + value),
        "nash_conv": nash_conv, "exploitability": nash_conv / 2,
        "scope": "Approximate equilibrium of the configured heads-up postflop abstraction; no preflop, multiway play, or rake.",
        "strategy": rows,
    }
