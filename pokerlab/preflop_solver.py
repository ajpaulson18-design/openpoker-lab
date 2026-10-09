"""Bounded heads-up preflop-to-river games over selected physical runouts.

This composes the preflop betting adapter with the repository's configured
postflop trees. It is an abstraction over the selected ranges, runouts, and
betting sizes, not an unrestricted preflop or Hold'em equilibrium solver.
"""
from dataclasses import dataclass
from itertools import islice
from math import comb, fsum, isfinite

from . import cfr
from .cfr_plus import train as train_cfrplus
from . import postflop_solver as _postflop
from .cards import DECK, cards, expand_range, rank_hand
from .planned_cfr import MAX_PLAN_OPS, train as train_planned
from .preflop_tree import PreflopConfig, PreflopContinuation, build_preflop_tree
from .river_config import RiverConfig
from .postflop_solver import _Chance, _build_public_tree
from .river_tree import _Action, _Node, _Terminal, _terminal_value


_MAX_CANDIDATE_HAND_ITERATIONS = _postflop._MAX_CANDIDATE_HAND_ITERATIONS
_MAX_WORLD_ITERATIONS = _postflop._MAX_WORLD_ITERATIONS
_MAX_PUBLIC_NODES = _postflop._MAX_PUBLIC_NODES
_MAX_PUBLIC_STATES = _postflop._MAX_PUBLIC_STATES
_MAX_WORLD_NODE_WORK = _postflop._MAX_WORLD_NODE_WORK
_MAX_PAIR_RUNOUT_PREFLIGHT_CHECKS = 30_000_000
_MAX_SELECTED_RUNOUTS = 300_000
_OUTCOMES_PER_UNBLOCKED_PAIR = comb(48, 3) * 45 * 44
_DECK_ORDER = {card: index for index, card in enumerate(DECK)}
_POSTFLOP_ACTION_DEFAULTS = {
    "bet_sizes": (0.5,), "raise_sizes": (), "max_raises": 0,
    "include_all_in": True,
}
_POSTFLOP_ACTION_FIELDS = frozenset(_POSTFLOP_ACTION_DEFAULTS)
_POSTFLOP_ACTION_ORDER = tuple(_POSTFLOP_ACTION_DEFAULTS)


def _clean(value):
    value = round(float(value), 9)
    return 0.0 if value == 0 else value


@dataclass(frozen=True)
class _StageSpec:
    actions: tuple

    def action_dict(self):
        return dict(self.actions)


def _make_stage_spec(value, inherited=None):
    """Normalize one action-only mapping, inheriting omitted stage actions."""
    inherited = inherited or _StageSpec(tuple(_POSTFLOP_ACTION_DEFAULTS.items()))
    if value is None:
        return inherited
    if not isinstance(value, dict):
        raise TypeError("Postflop stage configs must be action mappings.")
    extra = set(value) - _POSTFLOP_ACTION_FIELDS
    if extra:
        raise ValueError(f"Unknown postflop stage config fields: {sorted(extra)}")
    actions = inherited.action_dict()
    actions.update({key: item for key, item in value.items()
                    if key in _POSTFLOP_ACTION_FIELDS})
    candidate = RiverConfig(pot=1, effective_stack=(1, 1), **actions)
    return _StageSpec(tuple((key, getattr(candidate, key))
                            for key in _POSTFLOP_ACTION_ORDER))


def _stage_configs(flop_config, turn_config, river_config):
    flop = _make_stage_spec(flop_config)
    turn = _make_stage_spec(turn_config, flop)
    river = _make_stage_spec(river_config, flop)
    return {"flop": flop, "turn": turn, "river": river}


def _requested_runouts(runouts):
    if isinstance(runouts, (str, bytes)):
        raise ValueError("runouts must be a nonempty sequence of five-card outcomes.")
    normalized = []
    seen = set()
    try:
        iterator = iter(runouts)
    except TypeError as exc:
        raise ValueError("runouts must be a nonempty sequence of five-card outcomes.") from exc
    for item in iterator:
        if len(normalized) >= _MAX_SELECTED_RUNOUTS:
            raise ValueError("Selected runouts exceed the 300,000-outcome input limit.")
        if isinstance(item, (str, bytes)):
            runout = cards(item, 5)
        else:
            try:
                bounded = tuple(islice(iter(item), 6))
                if len(bounded) != 5:
                    raise ValueError("Each runout must contain exactly five cards.")
                runout = cards(bounded, 5)
            except TypeError as exc:
                raise ValueError("Each runout must be a five-card string or iterable.") from exc
        flop = tuple(sorted(runout[:3], key=_DECK_ORDER.__getitem__))
        canonical = (flop, runout[3], runout[4])
        if canonical in seen:
            raise ValueError("Duplicate canonical flop and ordered turn-river outcome.")
        seen.add(canonical)
        normalized.append(canonical)
    if not normalized:
        raise ValueError("At least one ordered five-card runout is required.")
    normalized.sort(key=lambda item: tuple(_DECK_ORDER[card]
                                           for card in item[0] + item[1:]))
    return tuple(normalized)


def _compatible(hands):
    return set(hands[0]).isdisjoint(hands[1])


def _rank_world(sb_hand, bb_hand, runout, cache):
    final_board = tuple(sorted(runout[0] + runout[1:], key=_DECK_ORDER.__getitem__))
    key_sb = (0, sb_hand, final_board)
    key_bb = (1, bb_hand, final_board)
    if key_sb not in cache:
        cache[key_sb] = rank_hand(sb_hand + final_board)
    if key_bb not in cache:
        cache[key_bb] = rank_hand(bb_hand + final_board)
    return (cache[key_sb] > cache[key_bb]) - (cache[key_sb] < cache[key_bb])


def _enumerate_physical_worlds(sb_range, bb_range, runouts, iterations):
    """Preflight and build normalized joint SB/BB/five-card worlds."""
    ranges = (expand_range(sb_range), expand_range(bb_range))
    hands = (list(ranges[0]), list(ranges[1]))
    candidate_pair_count = len(hands[0]) * len(hands[1])
    if candidate_pair_count * iterations > _MAX_CANDIDATE_HAND_ITERATIONS:
        raise ValueError("Preflop solver exceeds 3 million candidate-pair iterations.")

    if runouts is None:
        compatible_pairs = 0
        for sb_hand in hands[0]:
            for bb_hand in hands[1]:
                compatible_pairs += _compatible((sb_hand, bb_hand))
        if not compatible_pairs:
            raise ValueError("Ranges contain no compatible private-card pairs.")
        raise ValueError(
            "Full-deck preflop-to-river solving exceeds the 3 million world-iteration "
            f"limit: one compatible private pair has {_OUTCOMES_PER_UNBLOCKED_PAIR:,} "
            "physical runouts before iteration weighting. Supply a bounded selected runout set."
        )

    selected = _requested_runouts(runouts)
    candidate_pairs = []
    for sb_index, sb_hand in enumerate(hands[0]):
        for bb_index, bb_hand in enumerate(hands[1]):
            if _compatible((sb_hand, bb_hand)):
                candidate_pairs.append((sb_index, bb_index))
    if not candidate_pairs:
        raise ValueError("Ranges contain no compatible private-card pairs.")

    # Count exact compatible worlds before allocating the world or rank arrays.
    # This bounds the pair-by-runout preflight for adversarial large inputs.
    preflight_checks = 0
    compatible_counts = []
    world_count = 0
    for sb_index, bb_index in candidate_pairs:
        sb_hand, bb_hand = hands[0][sb_index], hands[1][bb_index]
        valid_count = 0
        blocked = set(sb_hand + bb_hand)
        for flop, turn, river in selected:
            preflight_checks += 1
            if preflight_checks > _MAX_PAIR_RUNOUT_PREFLIGHT_CHECKS:
                raise ValueError("Preflop physical-world preflight exceeds 30 million pair/runout checks.")
            if not blocked.isdisjoint(flop + (turn, river)):
                continue
            valid_count += 1
        if valid_count:
            compatible_counts.append((sb_index, bb_index, valid_count))
            world_count += valid_count
            if world_count * iterations > _MAX_WORLD_ITERATIONS:
                raise ValueError("Preflop solver exceeds 3 million world iterations.")
    if not world_count:
        raise ValueError("Selected runouts contain no compatible physical deals.")

    raw_worlds = []
    pair_masses = {}
    rank_cache = {}
    physical_denominator = _OUTCOMES_PER_UNBLOCKED_PAIR
    for sb_index, bb_index, valid_count in compatible_counts:
        sb_hand, bb_hand = hands[0][sb_index], hands[1][bb_index]
        pair_mass = ranges[0][sb_hand] * ranges[1][bb_hand] / physical_denominator
        pair_key = (sb_index, bb_index)
        pair_masses[pair_key] = pair_mass * valid_count
        blocked = set(sb_hand + bb_hand)
        for flop, turn, river in selected:
            if not blocked.isdisjoint(flop + (turn, river)):
                continue
            runout = (flop, turn, river)
            sign = _rank_world(sb_hand, bb_hand, runout, rank_cache)
            flop_key = "".join(flop)
            raw_worlds.append((sb_index, bb_index, pair_mass, sign,
                               flop_key, turn, river))

    normalizer = fsum(world[2] for world in raw_worlds)
    if not isfinite(normalizer) or normalizer <= 0:
        raise ValueError("Selected ranges and runouts have no positive joint mass.")
    worlds = [(world[0], world[1], world[2] / normalizer, *world[3:])
              for world in raw_worlds]
    pair_probabilities = [
        {"sb_hand": "".join(hands[0][sb_index]),
         "bb_hand": "".join(hands[1][bb_index]),
         "probability": mass / normalizer}
        for (sb_index, bb_index), mass in sorted(pair_masses.items())
    ]
    return hands, worlds, len(compatible_counts), pair_probabilities, selected, preflight_checks


def _revealed_board(history):
    board = []
    for token in history:
        if token.startswith("flop@"):
            board.extend(token[5 + offset:7 + offset]
                         for offset in range(0, len(token[5:]), 2))
        elif token.startswith("turn@"):
            board.append(token[5:])
        elif token.startswith("river@"):
            board.append(token[6:])
    return tuple(board)


def _chance_child(node, world):
    return node.branches[world[node.card_index]] if isinstance(node, _Chance) else None


def _chance_partitions(node, weighted_worlds):
    if not isinstance(node, _Chance):
        return None
    groups = {}
    for world in weighted_worlds:
        groups.setdefault(world[node.card_index], []).append(world)
    return [(node.branches[card], group) for card, group in groups.items()]


def _node_key(node, world):
    return node.player, world[node.player], node.history


def _all_nodes(root):
    nodes = []

    def visit(node):
        if isinstance(node, _Chance):
            for child in node.branches.values():
                visit(child)
        elif isinstance(node, _Node):
            nodes.append(node)
            for child in node.children:
                visit(child)

    try:
        visit(root)
    finally:
        visit = None
    return nodes


def _template_config(specs, boundary):
    pot = boundary.pot
    # Shared postflop APIs index OOP=BB and IP=SB.
    stacks = (boundary.remaining_stacks[1], boundary.remaining_stacks[0])
    if not isfinite(pot) or pot < 0.01:
        raise ValueError("A live preflop continuation pot below 0.01 is unsupported by RiverConfig.")
    if any(not isfinite(stack) or stack < 0.01 or stack > 1_000_000 for stack in stacks):
        raise ValueError("Live remaining stacks outside RiverConfig's 0.01-1,000,000 limits are unsupported.")
    return {
        stage: RiverConfig(pot=pot, effective_stack=stacks, **spec.action_dict())
        for stage, spec in specs.items()
    }


def _clone_template(root, history, matched, reserve):
    """Clone a local OOP=BB template into global SB=0/BB=1 identities."""
    def clone(node, public_history):
        if isinstance(node, _Chance):
            reserve("chance")
            branches = {}
            for card, child in node.branches.items():
                reveal = f"{node.street}@{card}"
                branches[card] = clone(child, public_history + (reveal,))
            return _Chance(tuple(public_history), branches, node.card_index + 1,
                           node.street)
        if isinstance(node, _Terminal):
            reserve("terminal")
            local_oop, local_ip = node.contributions
            return _Terminal(
                node.kind,
                (_clean(matched + local_ip), _clean(matched + local_oop)),
                None if node.winner is None else 1 - node.winner,
            )
        reserve("decision")
        player = 1 - node.player
        actions = []
        children = []
        for action, child in zip(node.actions, node.children):
            raise_to = action.raise_to
            if action.name not in {"check", "fold"} and raise_to:
                raise_to = _clean(matched + raise_to)
            copied = _Action(action.name, action.amount, raise_to, action.full_raise)
            actions.append(copied)
            children.append(clone(child, public_history + (copied.token,)))
        return _Node(tuple(public_history), player, tuple(actions), tuple(children))

    try:
        return clone(root, tuple(history))
    finally:
        clone = None


def _merge_preflop_tree(preflop_tree, worlds, specs, traversal, iterations):
    """Graft one transient postflop template per live boundary and flop."""
    continuations = []

    def find(node):
        if isinstance(node, PreflopContinuation):
            continuations.append(node)
        elif isinstance(node, _Node):
            for child in node.children:
                find(child)

    try:
        find(preflop_tree.root)
    finally:
        find = None

    state_count = preflop_tree.public_state_count - preflop_tree.continuation_count
    decision_count = preflop_tree.decision_node_count

    def reserve(kind):
        nonlocal state_count, decision_count
        if state_count >= _MAX_PUBLIC_STATES:
            raise ValueError("Combined preflop/postflop tree exceeds 250,000 public states.")
        if kind == "decision" and decision_count >= _MAX_PUBLIC_NODES:
            raise ValueError("Combined preflop/postflop tree exceeds 10,000 decisions.")
        state_count += 1
        if kind == "decision":
            decision_count += 1

    flop_world_counts = {}
    for world in worlds:
        flop_world_counts[world[4]] = flop_world_counts.get(world[4], 0) + 1
    max_template_states = max_template_decisions = 0
    preflop_plan_ops = preflop_tree.public_state_count - preflop_tree.continuation_count
    world_decision_work = (len(worlds) * preflop_tree.decision_node_count * iterations)
    if world_decision_work > _MAX_WORLD_NODE_WORK:
        raise ValueError("Combined preflop/postflop traversal exceeds 30 million world-decision iterations.")
    planned_operations = (len(worlds) * (preflop_plan_ops + len(continuations))
                          if traversal == "planned" else None)
    if planned_operations is not None and planned_operations > MAX_PLAN_OPS:
        raise ValueError("Planned preflop/postflop traversal exceeds 250,000 operations.")

    # Build, boundedly clone, and release a fresh template for every reachable
    # flop under every distinct live preflop boundary.
    def graft(node):
        nonlocal world_decision_work, planned_operations
        nonlocal max_template_states, max_template_decisions
        if isinstance(node, PreflopContinuation):
            if node.street == "showdown":
                reserve("terminal")
                matched = node.matched_contributions[0]
                return _Terminal("showdown", (matched, matched))
            reserve("chance")
            branches = {}
            for flop_key in flop_world_counts:
                boundary_configs = _template_config(specs, node)
                local_worlds = [
                    (world[1], world[0], world[2], -world[3], world[5], world[6])
                    for world in worlds if world[4] == flop_key
                ]
                allocation = {}
                template, template_nodes, _chance_count, visited_nodes, plan_ops = \
                    _build_public_tree(
                        3, boundary_configs["flop"],
                        turn_config=boundary_configs["turn"],
                        river_config=boundary_configs["river"],
                        worlds=local_worlds, allocation_counts=allocation,
                    )
                template_decisions = allocation["decision"]
                max_template_states = max(max_template_states, allocation["total"])
                max_template_decisions = max(max_template_decisions, template_decisions)
                if state_count + allocation["total"] > _MAX_PUBLIC_STATES:
                    raise ValueError("Combined preflop/postflop tree exceeds 250,000 public states.")
                if decision_count + template_decisions > _MAX_PUBLIC_NODES:
                    raise ValueError("Combined preflop/postflop tree exceeds 10,000 decisions.")
                added_work = flop_world_counts[flop_key] * visited_nodes * iterations
                if world_decision_work + added_work > _MAX_WORLD_NODE_WORK:
                    raise ValueError("Combined preflop/postflop traversal exceeds 30 million world-decision iterations.")
                added_plan_ops = flop_world_counts[flop_key] * plan_ops
                if (planned_operations is not None and
                        planned_operations + added_plan_ops > MAX_PLAN_OPS):
                    raise ValueError("Planned preflop/postflop traversal exceeds 250,000 operations.")
                public_history = node.history + (f"flop@{flop_key}",)
                branches[flop_key] = _clone_template(template, public_history,
                                                      node.matched_contributions[0], reserve)
                world_decision_work += added_work
                if planned_operations is not None:
                    planned_operations += added_plan_ops
                # Do not retain the temporary tree or its closure across flops.
                template = None
                template_nodes = None
                local_worlds = None
            return _Chance(node.history, branches, 4, "flop")
        if isinstance(node, _Node):
            node.children = tuple(graft(child) for child in node.children)
        return node

    try:
        root = graft(preflop_tree.root)
    finally:
        graft = None

    return (root, state_count, decision_count, world_decision_work,
            planned_operations, max_template_states, max_template_decisions)


def solve_preflop(sb_range, bb_range, config=None, *, runouts=None,
                  flop_config=None, turn_config=None, river_config=None,
                  iterations=1000, algorithm="vanilla", traversal="recursive"):
    """Solve a bounded heads-up preflop-to-river game.

    ``runouts`` is a required bounded list of five-card outcomes. The first
    three cards are a canonical unordered flop; turn and river remain ordered.
    Selected outcomes condition the joint private-hand/runout mass once, which
    can change private-pair probabilities through blockers.
    """
    if config is None:
        config = PreflopConfig()
    elif isinstance(config, dict):
        config = PreflopConfig.from_dict(config)
    elif not isinstance(config, PreflopConfig):
        raise TypeError("config must be a PreflopConfig or serializable mapping.")
    if type(iterations) is not int or not 10 <= iterations <= 10_000:
        raise ValueError("Use 10-10,000 solver iterations.")
    if algorithm not in ("vanilla", "dcfr", "cfrplus"):
        raise ValueError("Solver algorithm must be vanilla, dcfr, or cfrplus.")
    if traversal not in ("recursive", "planned"):
        raise ValueError("Preflop traversal supports recursive or planned CFR.")
    if algorithm == "cfrplus" and traversal != "recursive":
        raise ValueError("CFR+ supports recursive traversal only.")
    specs = _stage_configs(flop_config, turn_config, river_config)

    hands, worlds, compatible_pairs, pair_probabilities, selected, preflight_checks = \
        _enumerate_physical_worlds(sb_range, bb_range, runouts, iterations)
    preflop_tree = build_preflop_tree(config)
    (root, public_state_count, decision_count, world_decision_work, planned_ops,
     max_template_states, max_template_decisions) = \
        _merge_preflop_tree(preflop_tree, worlds, specs, traversal,
                            iterations * 3 if algorithm == "cfrplus" else iterations)

    # Global hand identity is SB=0, BB=1. Each history sees only own hands that
    # remain legal after its public flop/turn/river prefix.
    legal = {(player, ()): set() for player in (0, 1)}
    for world in worlds:
        future = cards(world[4], 3) + (world[5], world[6])
        for player in (0, 1):
            legal[(player, ())].add(world[player])
            for length in (3, 4, 5):
                legal.setdefault((player, future[:length]), set()).add(world[player])

    nodes = _all_nodes(root)
    infos, metadata = {}, {}
    for node in nodes:
        prefix = _revealed_board(node.history)
        for hand_index in sorted(legal.get((node.player, prefix), ())):
            key = (node.player, hand_index, node.history)
            infos[key] = len(node.actions)
            metadata[key] = node

    payoff = lambda terminal, world: _terminal_value(terminal, world[3], 0.0)
    if algorithm == "cfrplus" and not infos:
        averages = {}
    elif algorithm == "cfrplus":
        averages = train_cfrplus(root, worlds, infos, iterations, "cfrplus", payoff,
                                 _node_key, _chance_child)
    elif traversal == "planned":
        trainer = train_planned
        averages = trainer(root, worlds, infos, iterations, algorithm, payoff,
                           _node_key, _chance_child, max_plan_ops=MAX_PLAN_OPS)
    else:
        averages = cfr.train(root, worlds, infos, iterations, algorithm, payoff,
                           _node_key, _chance_child)
    value_sb = cfr.evaluate(root, worlds, averages, payoff, _node_key, _chance_child)
    br_sb = cfr.best_response(0, root, worlds, averages, payoff, _node_key,
                              _chance_partitions)
    br_bb = cfr.best_response(1, root, worlds, averages, payoff, _node_key,
                              _chance_partitions)
    gain_sb = max(0.0, br_sb - value_sb)
    gain_bb = max(0.0, br_bb + value_sb)
    nash_conv = gain_sb + gain_bb

    strategy = []
    for key in sorted(infos):
        player, hand_index, history = key
        node = metadata[key]
        board = _revealed_board(history)
        street = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}.get(len(board))
        if street is None:
            raise AssertionError("Strategy history reveals an invalid number of board cards.")
        strategy.append({
            "player": "sb" if player == 0 else "bb",
            "hand": "".join(hands[player][hand_index]),
            "street": street,
            "revealed_board": list(board),
            "history": list(history),
            "actions": [{
                "name": action.name,
                "amount": action.amount,
                "raise_to": action.raise_to,
                "history_key": action.token,
                "probability": probability,
            } for action, probability in zip(node.actions, averages[key])],
        })

    selected_output = [list(flop + (turn, river)) for flop, turn, river in selected]
    compatible_runouts = {world[4:7] for world in worlds}
    reachable_output = [list(flop + (turn, river)) for flop, turn, river in selected
                        if ("".join(flop), turn, river) in compatible_runouts]
    result = {
        "method": "full-traversal CFR",
        "solver_version": "preflop-strategy-v1",
        "strategy_schema": "preflop-strategy-v1",
        "algorithm": algorithm,
        "execution_backend": f"{traversal}-python",
        "preflop_config": config.to_dict(),
        "postflop_action_configs": {
            stage: {key: list(value) if isinstance(value, tuple) else value
                    for key, value in spec.actions}
            for stage, spec in specs.items()
        },
        "runout_mode": "conditioned-ordered-selected-runouts",
        "runout_scope": "Selected physical outcomes condition the joint private-pair/runout distribution once; flop order is canonical and turn-river order is preserved.",
        "selected_runouts": selected_output,
        "reachable_runouts": reachable_output,
        "iterations": iterations,
        "candidate_private_pairs": len(hands[0]) * len(hands[1]),
        "compatible_private_pairs": compatible_pairs,
        "worlds": len(worlds),
        "pair_runout_preflight_checks": preflight_checks,
        "private_pair_probabilities": pair_probabilities,
        "public_states": public_state_count,
        "decisions": decision_count,
        "info_sets": len(infos),
        "world_decision_work": world_decision_work,
        "planned_operations": planned_ops,
        "temporary_postflop_template_peak_states": max_template_states,
        "temporary_postflop_template_peak_decisions": max_template_decisions,
        "temporary_template_policy": "One bounded template per live preflop boundary and reachable flop is built, cloned under aggregate limits, and released before the next template.",
        "limits": {
            "candidate_pair_iterations": _MAX_CANDIDATE_HAND_ITERATIONS,
            "world_iterations": _MAX_WORLD_ITERATIONS,
            "pair_runout_preflight_checks": _MAX_PAIR_RUNOUT_PREFLIGHT_CHECKS,
            "world_decision_work": _MAX_WORLD_NODE_WORK,
            "public_states": _MAX_PUBLIC_STATES,
            "decision_nodes": _MAX_PUBLIC_NODES,
            "planned_operations": MAX_PLAN_OPS,
            "temporary_postflop_template_states": _MAX_PUBLIC_STATES,
            "temporary_postflop_template_decisions": _MAX_PUBLIC_NODES,
        },
        "value_sb": value_sb,
        "value_bb": -value_sb,
        "sb_best_response_value": br_sb,
        "bb_best_response_value": br_bb,
        "sb_gain": gain_sb,
        "bb_gain": gain_bb,
        "nash_conv": nash_conv,
        "exploitability": nash_conv / 2.0,
        "scope": "Approximate equilibrium of the configured heads-up finite betting abstraction and selected physical runouts; no unrestricted preflop or Hold'em GTO claim.",
        "strategy": strategy,
    }
    if algorithm == "cfrplus":
        result.update({
            "training_schedule": (
                "alternating-player-0-then-player-1; linear-own-reach-average-after-each-sweep"
                if infos else None
            ),
            "training_passes_per_iteration": 3 if infos else 0,
            "training_passes": iterations * 3 if infos else 0,
        })
    return result

