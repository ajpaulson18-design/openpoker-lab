"""Bounded heads-up preflop-to-river games over selected physical runouts.

This composes the preflop betting adapter with the repository's configured
postflop trees. It is an abstraction over the selected ranges, runouts, and
betting sizes, not an unrestricted preflop or Hold'em equilibrium solver.
"""
from dataclasses import dataclass
from itertools import islice
from math import comb, frexp, fsum, isfinite, ldexp

from . import cfr
from .cfr_plus import train as train_cfrplus
from . import postflop_solver as _postflop
from .cards import DECK, cards, expand_range, rank_hand
from .planned_cfr import MAX_PLAN_OPS, train as train_planned
from .preflop_tree import PreflopConfig, PreflopContinuation, build_preflop_tree
from .preflop_vector_budget import MAX_INFO_ACTION_SLOTS, MAX_TOTAL_LOOP_ENTRIES, estimate_vector_budget
from .preflop_future_groups import estimate_future_grouping, group_hidden_futures
from .preflop_delayed_cfrplus import train_delayed_public_cfrplus
from .preflop_runout_index import RunoutBlockerIndex
from .preflop_private_indices import compact_private_indices
from .preflop_sampled_budget import estimate_sampled_budget
from .preflop_sampled_storage import MAX_SAMPLER_ENTRIES, estimate_sampler_storage
from .preflop_sampled_cfr import train_chance_sampled, validate_sampling_options
from .public_cfr import MAX_PREFIX_EDGES, train_public_batched
from .public_diagnostics import evaluate_profile as evaluate_public_profile
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


def _enumerate_physical_worlds(sb_range, bb_range, runouts, iterations, *,
                               materialized_world_limit=None):
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

    # Retain the original pair/runout admission charge and per-pair guard
    # order while postings replace dense Python-level blocker scans.
    if len(selected) > _MAX_PAIR_RUNOUT_PREFLIGHT_CHECKS:
        raise ValueError("Preflop physical-world preflight exceeds 30 million pair/runout checks.")
    runout_index = RunoutBlockerIndex(selected)
    preflight_checks = 0
    compatible_counts = []
    world_count = 0
    for sb_index, bb_index in candidate_pairs:
        sb_hand, bb_hand = hands[0][sb_index], hands[1][bb_index]
        preflight_checks += len(selected)
        if preflight_checks > _MAX_PAIR_RUNOUT_PREFLIGHT_CHECKS:
            raise ValueError("Preflop physical-world preflight exceeds 30 million pair/runout checks.")
        valid_count = runout_index.valid_count(sb_hand + bb_hand)
        if valid_count:
            compatible_counts.append((sb_index, bb_index, valid_count))
            world_count += valid_count
            if materialized_world_limit is not None and world_count > materialized_world_limit:
                raise ValueError("Sampled solver exceeds its materialized sampler-world entry limit.")
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
        for selected_index in runout_index.iter_valid_indices(sb_hand + bb_hand):
            flop, turn, river = selected[selected_index]
            runout = (flop, turn, river)
            sign = _rank_world(sb_hand, bb_hand, runout, rank_cache)
            flop_key = "".join(flop)
            raw_worlds.append((sb_index, bb_index, pair_mass, sign,
                               flop_key, turn, river))

    runout_index = None
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


def _legal_private_hands(worlds, postflop_scope="all-streets"):
    """Build each public node's legal own-hand set from physical worlds."""
    legal = {(player, ()): set() for player in (0, 1)}
    if postflop_scope == "all-streets":
        # Keep the established all-streets enumeration and ordering unchanged.
        for world in worlds:
            future = cards(world[4], 3) + (world[5], world[6])
            for player in (0, 1):
                legal[(player, ())].add(world[player])
                for length in (3, 4, 5):
                    legal.setdefault((player, future[:length]), set()).add(world[player])
        return legal
    if postflop_scope != "flop-checkdown":
        raise ValueError("postflop_scope must be all-streets or flop-checkdown.")

    flop_cards = {}
    for world in worlds:
        flop_key = world[4]
        flop = flop_cards.get(flop_key)
        if flop is None:
            flop = cards(flop_key, 3)
            flop_cards[flop_key] = flop
        for player in (0, 1):
            legal[(player, ())].add(world[player])
            legal.setdefault((player, flop), set()).add(world[player])
    return legal


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


def _positive_pot_training_view(root):
    """Copy a public tree with terminal contributions shifted for vector math.

    The specialized public trainer requires a positive starting pot and adds
    half that pot to each terminal payoff. Shifting every contribution by a
    power-of-two anchor no larger than the minimum matched terminal amount
    preserves each whole-hand utility without decimal cleanup. The original
    tree remains the source for default generic evaluation and best responses;
    optional vector diagnostics reuse this utility-preserving view.
    """
    minimum_matched = None
    pending = [root]
    while pending:
        node = pending.pop()
        if isinstance(node, _Chance):
            pending.extend(node.branches.values())
        elif isinstance(node, _Node):
            pending.extend(node.children)
        elif isinstance(node, _Terminal):
            matched = min(node.contributions)
            minimum_matched = matched if minimum_matched is None else min(
                minimum_matched, matched)
    if minimum_matched is None or not isfinite(minimum_matched) or minimum_matched <= 0:
        raise ValueError("Public-batched training requires positive terminal contributions.")

    anchor = ldexp(1.0, frexp(minimum_matched)[1] - 1)
    cloned_states = 0

    def reserve():
        nonlocal cloned_states
        if cloned_states >= _MAX_PUBLIC_STATES:
            raise ValueError("Public-batched training view exceeds 250,000 public states.")
        cloned_states += 1

    def clone(node):
        reserve()
        if isinstance(node, _Chance):
            return _Chance(node.history,
                           {card: clone(child) for card, child in node.branches.items()},
                           node.card_index, node.street)
        if isinstance(node, _Terminal):
            return _Terminal(
                node.kind,
                tuple(value - anchor for value in node.contributions),
                node.winner,
            )
        return _Node(node.history, node.player, node.actions,
                     tuple(clone(child) for child in node.children))

    try:
        training_root = clone(root)
    finally:
        clone = None
    return training_root, anchor, cloned_states


def _merge_preflop_tree(preflop_tree, worlds, specs, traversal, iterations,
                        postflop_scope="all-streets",
                        *, enforce_world_work=True, decision_limit=None):
    """Graft one transient postflop template per live boundary and flop."""
    decision_limit = _MAX_PUBLIC_NODES if decision_limit is None else decision_limit
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
        if kind == "decision" and decision_count >= decision_limit:
            raise ValueError(f"Combined preflop/postflop tree exceeds {decision_limit:,} decisions.")
        state_count += 1
        if kind == "decision":
            decision_count += 1

    flop_world_counts = {}
    for world in worlds:
        flop_world_counts[world[4]] = flop_world_counts.get(world[4], 0) + 1
    max_template_states = max_template_decisions = 0
    preflop_plan_ops = preflop_tree.public_state_count - preflop_tree.continuation_count
    world_decision_work = (len(worlds) * preflop_tree.decision_node_count * iterations)
    if enforce_world_work and world_decision_work > _MAX_WORLD_NODE_WORK:
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
                boundary_specs = ({"flop": specs["flop"]}
                                  if postflop_scope == "flop-checkdown" else specs)
                boundary_configs = _template_config(boundary_specs, node)
                local_worlds = [
                    (world[1], world[0], world[2], -world[3], world[5], world[6])
                    for world in worlds if world[4] == flop_key
                ]
                allocation = {}
                if postflop_scope == "flop-checkdown":
                    template, template_nodes, _chance_count, visited_nodes, plan_ops = \
                        _build_public_tree(
                            5, boundary_configs["flop"], worlds=local_worlds,
                            allocation_counts=allocation,
                        )
                else:
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
                if decision_count + template_decisions > decision_limit:
                    raise ValueError(f"Combined preflop/postflop tree exceeds {decision_limit:,} decisions.")
                added_work = flop_world_counts[flop_key] * visited_nodes * iterations
                if enforce_world_work and world_decision_work + added_work > _MAX_WORLD_NODE_WORK:
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
                  postflop_scope="all-streets",
                  iterations=1000, algorithm="vanilla", traversal="recursive",
                  diagnostics="recursive", resource_model="world", averaging_delay=0,
                  sampling_seed=0, samples_per_iteration=1, tree_admission="decision-count",
                  target_nash_conv=None, convergence_check_interval=None,
                  private_indexing="original", future_indexing="original"):
    """Solve a bounded heads-up preflop-to-river game.

    ``runouts`` is a required bounded list of five-card outcomes. The first
    three cards are a canonical unordered flop; turn and river remain ordered.
    Selected outcomes condition the joint private-hand/runout mass once, which
    can change private-pair probabilities through blockers.
    ``diagnostics="public-batched"`` optionally evaluates the policy and both
    legal best responses with private-hand vectors; recursive is the default.
    ``resource_model="public-vector"`` optionally bounds vector loop work and
    scratch dimensions instead of the conservative world-decision estimate.
    It requires public-batched training and diagnostics; other limits remain.
    Opt-in ``traversal=resource_model="chance-sampled"`` requires vanilla CFR
    and exact public-batched diagnostics. It replaces full-world training work
    charges with bounded sampled-node/action work, retaining construction caps.
    ``sampling_seed`` and ``samples_per_iteration`` control reproducible batches.
    ``tree_admission="vector"`` explicitly replaces the aggregate 10,000
    decision guard with public-state, action-slot and vector-work admission;
    it requires ``resource_model="public-vector"``. Templates remain bounded.
    Optional ``postflop_scope="flop-checkdown"`` builds only preflop and flop
    betting. It requires positive-delay CFR+ with public-batched training and
    diagnostics under the public-vector resource model. The selected complete
    future-board worlds stay hidden and are integrated at terminal utility;
    turn and river betting are not modeled. Turn/river action configs are
    rejected in this scope. The default ``all-streets`` path is unchanged.

    Optional ``future_indexing="flop-sign"`` groups hidden outcomes by private
    pair, public flop and final showdown sign in flop-checkdown mode only.
    Physical enumeration, outputs and all existing admission limits remain;
    a separately bounded grouped view serves training and exact diagnostics.
    Changed floating summation order can produce small numerical differences.

    Optional paired ``target_nash_conv`` / ``convergence_check_interval`` stop
    positive-delay public-vector CFR+ after a complete sweep whose exact legal
    best-response gap plus 1e-10 meets the target. The requested iteration cap
    and all possible checks must be admitted before training. ``iterations``
    remains the requested ceiling; ``completed_iterations`` records actual work.
    Positive ``averaging_delay`` optionally applies CFR+ weights
    ``max(iteration-delay, 0)`` after each completed alternating sweep.
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
    if traversal not in ("recursive", "planned", "public-batched", "chance-sampled"):
        raise ValueError("Preflop traversal supports recursive, planned, public-batched, or chance-sampled CFR.")
    if diagnostics not in ("recursive", "public-batched"):
        raise ValueError("Preflop diagnostics must be recursive or public-batched.")
    if private_indexing not in ("original", "compact"):
        raise ValueError("private_indexing must be original or compact.")
    if resource_model not in ("world", "public-vector", "chance-sampled"):
        raise ValueError("Preflop resource model must be world, public-vector, or chance-sampled.")
    if tree_admission not in ("decision-count", "vector"):
        raise ValueError("Tree admission must be decision-count or vector.")
    if postflop_scope not in ("all-streets", "flop-checkdown"):
        raise ValueError("postflop_scope must be all-streets or flop-checkdown.")
    if postflop_scope == "flop-checkdown" and (turn_config is not None or river_config is not None):
        raise ValueError("flop-checkdown does not accept turn_config or river_config.")
    if future_indexing not in ("original", "flop-sign"):
        raise ValueError("future_indexing must be original or flop-sign.")
    if future_indexing == "flop-sign" and postflop_scope != "flop-checkdown":
        raise ValueError("flop-sign future indexing requires flop-checkdown scope.")
    expanded_tree = tree_admission == "vector"
    if expanded_tree and resource_model != "public-vector":
        raise ValueError("Vector tree admission requires the public-vector resource model.")
    sampled = traversal == "chance-sampled"
    validate_sampling_options(sampling_seed, samples_per_iteration)
    if sampled:
        if (resource_model != "chance-sampled" or diagnostics != "public-batched"
                or algorithm != "vanilla"):
            raise ValueError("Chance-sampled training requires vanilla CFR, chance-sampled resource model and public-batched exact diagnostics.")
    elif (resource_model == "chance-sampled" or sampling_seed != 0
          or samples_per_iteration != 1):
        raise ValueError("Sampling options require chance-sampled traversal.")
    vector_budget_enabled = resource_model == "public-vector"
    if vector_budget_enabled and (traversal != "public-batched" or
                                  diagnostics != "public-batched"):
        raise ValueError("Public-vector resource model requires public-batched training and diagnostics.")
    if algorithm == "cfrplus" and traversal == "planned":
        raise ValueError("CFR+ supports recursive or public-batched traversal, not planned CFR.")
    if type(averaging_delay) is not int or not 0 <= averaging_delay < iterations:
        raise ValueError("CFR+ averaging delay must be an integer from zero to iterations-1.")
    if averaging_delay and algorithm != "cfrplus":
        raise ValueError("Positive averaging delay requires CFR+ training.")
    if postflop_scope == "flop-checkdown" and not (
            algorithm == "cfrplus" and averaging_delay > 0 and
            resource_model == "public-vector" and traversal == "public-batched" and
            diagnostics == "public-batched"):
        raise ValueError(
            "flop-checkdown requires positive-delay CFR+ with public-vector public-batched training and diagnostics.")
    if private_indexing == "compact" and not (
            algorithm == "cfrplus" and averaging_delay > 0 and
            resource_model == "public-vector" and traversal == "public-batched" and
            diagnostics == "public-batched"):
        raise ValueError(
            "Compact private indexing requires positive-delay CFR+ with public-vector "
            "public-batched training and diagnostics.")
    convergence_enabled = target_nash_conv is not None or convergence_check_interval is not None
    if convergence_enabled:
        if (isinstance(target_nash_conv, bool) or
                not isinstance(target_nash_conv, (int, float))):
            raise ValueError("Convergence target must be a finite positive number.")
        try:
            target_nash_conv = float(target_nash_conv)
        except (OverflowError, ValueError):
            raise ValueError("Convergence target must be a finite positive number.") from None
        if not isfinite(target_nash_conv) or target_nash_conv <= 0:
            raise ValueError("Convergence target must be a finite positive number.")
        if type(convergence_check_interval) is not int or convergence_check_interval < 1:
            raise ValueError("Convergence check interval must be a positive integer.")
        if (algorithm != "cfrplus" or not averaging_delay or not vector_budget_enabled):
            raise ValueError("Convergence stopping requires positive-delay public-vector CFR+.")
    specs = _stage_configs(flop_config, turn_config, river_config)

    hands, worlds, compatible_pairs, pair_probabilities, selected, preflight_checks = \
        _enumerate_physical_worlds(sb_range, bb_range, runouts,
                                   1 if sampled else iterations,
                                   **({"materialized_world_limit": MAX_SAMPLER_ENTRIES}
                                      if sampled else {}))
    preflop_tree = build_preflop_tree(config)
    (root, public_state_count, decision_count, world_decision_work, planned_ops,
     max_template_states, max_template_decisions) = \
        _merge_preflop_tree(preflop_tree, worlds, specs, traversal,
                            iterations * 3 if algorithm == "cfrplus" else iterations,
                            postflop_scope,
                            enforce_world_work=not (vector_budget_enabled or sampled),
                            **({"decision_limit": _MAX_PUBLIC_STATES} if expanded_tree else {}))

    # Global hand identity is SB=0, BB=1. Histories see only own hands
    # compatible with the public prefix represented by this tree scope.
    legal = _legal_private_hands(worlds, postflop_scope)

    nodes = _all_nodes(root)
    infos, metadata = {}, {}
    info_action_slots = 0
    for node in nodes:
        prefix = _revealed_board(node.history)
        for hand_index in sorted(legal.get((node.player, prefix), ())):
            if (vector_budget_enabled or sampled) and info_action_slots + len(node.actions) > MAX_INFO_ACTION_SLOTS:
                raise ValueError("Public-vector information-set action slots exceed 1,000,000.")
            key = (node.player, hand_index, node.history)
            infos[key] = len(node.actions)
            metadata[key] = node
            info_action_slots += len(node.actions)

    vector_budget = (estimate_vector_budget(
        root, worlds, infos, iterations, algorithm, chance_type=_Chance,
        **({"private_indexing": private_indexing} if private_indexing == "compact" else {}),
        **({"averaging_delay": averaging_delay} if averaging_delay else {}),
        **({"checkpoint_interval": convergence_check_interval} if convergence_enabled else {}))
        if vector_budget_enabled else None)

    # Retain the full physical-world vector envelope, including inactive future
    # prefixes. Grouping only reduces backend row/prefix work; no prior admission
    # is relaxed. Add its original-world scan/map/copy envelope before allocation.
    future_grouping_budget = None
    if future_indexing == "flop-sign":
        future_grouping_budget = estimate_future_grouping(worlds)
        total = (vector_budget["total_loop_entries_upper_bound"] +
                 future_grouping_budget["grouping_loop_entries_upper_bound"])
        if total > MAX_TOTAL_LOOP_ENTRIES:
            raise ValueError("Future grouping vector estimated loop entries exceed 500,000,000")
        vector_budget = dict(vector_budget)
        vector_budget.update({
            "physical_world_reference_budget_version": vector_budget["budget_version"],
            "budget_version": "preflop-public-vector-future-group-budget-v5",
            "future_grouping": future_grouping_budget,
            "total_loop_entries_upper_bound": total,
            "future_grouping_admission_scope": "Full original-world vector envelope retained, plus separately bounded grouping construction. Fewer/shorter backend rows and prefixes cannot relax any existing cap; compact copies remain charged against original seven-field worlds.",
        })

    # The estimator admits the extra copying before the compact structures are
    # allocated. Preserve the original identities for final policy labels and
    # public result counts; all training and vector diagnostics use compact ids.
    private_indexing_metadata = None
    compaction = None
    original_worlds = None
    original_infos = None
    if private_indexing == "compact":
        original_worlds, original_infos = worlds, infos
        compaction = compact_private_indices(worlds, infos)
        worlds, infos = compaction.worlds, compaction.infos
        private_indexing_metadata = compaction.metadata

    sampled_storage = estimate_sampler_storage(worlds) if sampled else None
    sampled_budget = (estimate_sampled_budget(
        root, infos, iterations, samples_per_iteration, chance_type=_Chance)
        if sampled else None)
    # This reference overcharges one unused vector training iteration. It
    # bounds complete exact diagnostics; no sampled gap estimates are used.
    sampled_diagnostic_budget = (estimate_vector_budget(
        root, worlds, infos, 1, "vanilla", chance_type=_Chance)
        if sampled else None)
    sampling_stats = None

    compaction_completed = False
    grouped_source_worlds = None
    future_indexing_metadata = None
    try:
        if future_indexing == "flop-sign":
            grouped_source_worlds = worlds
            worlds = group_hidden_futures(worlds)
            future_indexing_metadata = {
                "physical_world_count": len(grouped_source_worlds),
                "training_world_rows": len(worlds),
                "group_key": ["sb_hand", "bb_hand", "public_flop", "showdown_sign"],
                "scope": "First-seen groups sum the original normalized physical masses without renormalization. Final signs remain -1, 0 or 1. Only the public flop survives in the training/evaluation view; all selected futures remain hidden. Original worlds govern outputs and every old admission cap. Floating summation order changes; no bitwise policy equivalence claim.",
            }
        payoff = lambda terminal, world: _terminal_value(terminal, world[3], 0.0)
        training_pot_anchor = None
        training_view_states = 0
        diagnostic_values = None
        diagnostic_view_anchor = None
        diagnostic_view_states = 0
        diagnostic_view_source = None
        completed_iterations = iterations if infos else 0
        convergence_checkpoints = []
        convergence_reached = False
        if not infos and (algorithm == "cfrplus" or traversal == "public-batched" or
                          diagnostics == "public-batched"):
            averages = {}
        elif sampled:
            averages, sampling_stats = train_chance_sampled(
                root, worlds, infos, iterations, payoff, _node_key, _chance_child,
                seed=sampling_seed, batch_size=samples_per_iteration)
            if sampling_stats["actual_node_visits"] > sampled_budget["total_node_visits_upper_bound"]:
                raise RuntimeError("Sampled trainer exceeded its structural visit bound.")
        elif traversal == "public-batched":
            training_root, training_pot_anchor, training_view_states = \
                _positive_pot_training_view(root)
            def check_convergence(iteration, policy):
                nonlocal diagnostic_values, completed_iterations, convergence_reached
                # A delayed policy has no contributing average before this point.
                # Do not certify an untrained uniform fallback as a delayed result.
                if iteration <= averaging_delay:
                    return False
                values = evaluate_public_profile(
                    training_root, worlds, policy,
                    pot=2 * training_pot_anchor, chance_type=_Chance)
                if not all(isfinite(value) for value in values):
                    raise ValueError("Convergence diagnostic returned nonfinite values.")
                value, response_sb, response_bb = values
                gap = max(0.0, response_sb - value) + max(0.0, response_bb + value)
                reached = gap + 1e-10 <= target_nash_conv
                convergence_checkpoints.append({
                    "completed_iterations": iteration, "nash_conv": gap,
                    "value_sb": value, "sb_best_response_value": response_sb,
                    "bb_best_response_value": response_bb, "target_reached": reached,
                })
                completed_iterations = iteration
                diagnostic_values = values
                convergence_reached = reached
                return reached

            try:
                if averaging_delay:
                    averages = train_delayed_public_cfrplus(
                        training_root, worlds, infos, iterations,
                        averaging_delay=averaging_delay,
                        pot=2 * training_pot_anchor, chance_type=_Chance,
                        **({"checkpoint_interval": convergence_check_interval,
                            "checkpoint_callback": check_convergence} if convergence_enabled else {}),
                    )
                else:
                    averages = train_public_batched(
                        training_root, worlds, infos, iterations, algorithm,
                        pot=2 * training_pot_anchor, chance_type=_Chance,
                    )
                if diagnostics == "public-batched":
                    if not convergence_enabled or diagnostic_values is None:
                        diagnostic_values = evaluate_public_profile(
                            training_root, worlds, averages,
                            pot=2 * training_pot_anchor, chance_type=_Chance,
                        )
                    diagnostic_view_anchor = training_pot_anchor
                    diagnostic_view_states = training_view_states
                    diagnostic_view_source = "training-view-reused"
            finally:
                training_root = None
        elif algorithm == "cfrplus":
            if averaging_delay:
                averages = train_cfrplus(root, worlds, infos, iterations, "cfrplus", payoff,
                                         _node_key, _chance_child, delay=averaging_delay)
            else:
                averages = train_cfrplus(root, worlds, infos, iterations, "cfrplus", payoff,
                                         _node_key, _chance_child)
        elif traversal == "planned":
            trainer = train_planned
            averages = trainer(root, worlds, infos, iterations, algorithm, payoff,
                               _node_key, _chance_child, max_plan_ops=MAX_PLAN_OPS)
        else:
            averages = cfr.train(root, worlds, infos, iterations, algorithm, payoff,
                               _node_key, _chance_child)
        if diagnostics == "public-batched" and diagnostic_values is None:
            diagnostic_root, diagnostic_view_anchor, diagnostic_view_states = \
                _positive_pot_training_view(root)
            try:
                diagnostic_values = evaluate_public_profile(
                    diagnostic_root, worlds, averages,
                    pot=2 * diagnostic_view_anchor, chance_type=_Chance,
                )
                diagnostic_view_source = (
                    "no-information-set-evaluation-view" if not infos
                    else "separate-evaluation-view"
                )
            finally:
                diagnostic_root = None
        if diagnostic_values is None:
            value_sb = cfr.evaluate(root, worlds, averages, payoff, _node_key, _chance_child)
            br_sb = cfr.best_response(0, root, worlds, averages, payoff, _node_key,
                                      _chance_partitions)
            br_bb = cfr.best_response(1, root, worlds, averages, payoff, _node_key,
                                      _chance_partitions)
        else:
            value_sb, br_sb, br_bb = diagnostic_values
        gain_sb = max(0.0, br_sb - value_sb)
        gain_bb = max(0.0, br_bb + value_sb)
        nash_conv = gain_sb + gain_bb
        compaction_completed = True
    finally:
        if grouped_source_worlds is not None:
            worlds = grouped_source_worlds
            grouped_source_worlds = None
        if compaction is not None:
            try:
                if compaction_completed:
                    averages = compaction.restore_policy(averages)
            finally:
                worlds, infos = original_worlds, original_infos
                compaction = None
                original_worlds = original_infos = None

    if convergence_enabled and not all(isfinite(value) for value in
                                       (value_sb, br_sb, br_bb, nash_conv)):
        raise ValueError("Convergence diagnostic returned nonfinite values.")
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
        "solver_version": ("preflop-flop-checkdown-v1"
                            if postflop_scope == "flop-checkdown"
                            else "preflop-strategy-v1"),
        "strategy_schema": "preflop-strategy-v1",
        "algorithm": algorithm,
        "execution_backend": f"{traversal}-python",
        "preflop_config": config.to_dict(),
        "postflop_action_configs": {
            stage: {key: list(value) if isinstance(value, tuple) else value
                    for key, value in spec.actions}
            for stage, spec in specs.items()
            if postflop_scope == "all-streets" or stage == "flop"
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
    if postflop_scope == "flop-checkdown":
        result["postflop_scope"] = "flop-checkdown"
        result["scope"] = (
            "Approximate equilibrium of the conditioned finite game with preflop and flop betting, followed by forced checkdown over the selected complete future-board outcomes. Turn and river remain hidden; no turn or river decisions are modeled. This is not an all-streets Hold'em equilibrium claim."
        )
    if future_indexing == "flop-sign":
        result["future_indexing"] = "flop-sign"
        result["future_indexing_metadata"] = future_indexing_metadata
    if private_indexing == "compact":
        result["private_indexing"] = "compact"
        result["private_indexing_metadata"] = private_indexing_metadata
    if algorithm == "cfrplus":
        result.update({
            "training_schedule": (
                "alternating-player-0-then-player-1; linear-own-reach-average-after-each-sweep"
                if infos else None
            ),
            "training_passes_per_iteration": 3 if infos else 0,
            "training_passes": iterations * 3 if infos else 0,
        })
    if traversal == "public-batched":
        result.update({
            "public_batched_prefix_edge_limit": MAX_PREFIX_EDGES,
            "public_batched_training_pot_anchor": training_pot_anchor,
            "public_batched_training_view_states": training_view_states,
            "public_batched_training_view": (
                "terminal contributions shifted by minus the recorded anchor; trainer pot is twice that anchor"
                if infos else "not-built-no-information-sets"
            ),
        })
    if averaging_delay:
        average_passes = max(completed_iterations - averaging_delay, 0) if infos else 0
        result.update({
            "averaging_delay": averaging_delay,
            "averaging_positive_sweeps": max(completed_iterations - averaging_delay, 0) if infos else 0,
            "training_average_passes": average_passes,
            "training_regret_passes": completed_iterations * 2 if infos else 0,
            "training_passes": completed_iterations * 2 + average_passes if infos else 0,
            "training_schedule": (
                "alternating-player-0-then-player-1; delayed-linear-own-reach-average-after-each-sweep"
                if infos else None
            ),
        })
        if traversal == "public-batched":
            result["public_batched_training_kernel"] = "preflop-delayed-cfrplus-python"
        if infos:
            result["training_passes_per_iteration"] = None
    if diagnostics == "public-batched":
        result.update({
            "diagnostics_backend": "public-batched-python",
            "public_diagnostics_prefix_edge_limit": MAX_PREFIX_EDGES,
            "public_diagnostics_view_pot_anchor": diagnostic_view_anchor,
            "public_diagnostics_view_states": diagnostic_view_states,
            "public_diagnostics_view_source": diagnostic_view_source,
        })
    if convergence_enabled:
        if not infos:
            convergence_reached = nash_conv + 1e-10 <= target_nash_conv
            convergence_checkpoints.append({
                "completed_iterations": 0, "nash_conv": nash_conv,
                "value_sb": value_sb, "sb_best_response_value": br_sb,
                "bb_best_response_value": br_bb, "target_reached": convergence_reached,
            })
        result.update({
            "completed_iterations": completed_iterations,
            "target_nash_conv": target_nash_conv,
            "convergence_check_interval": convergence_check_interval,
            "convergence_numerical_padding": 1e-10,
            "convergence_target_reached": convergence_reached,
            "stopped_early": bool(infos) and completed_iterations < iterations,
            "convergence_stop_reason": ("no-information-sets" if not infos else
                                        "target-met" if convergence_reached else "iteration-limit"),
            "convergence_checkpoints": convergence_checkpoints,
            "convergence_scope": "Exact configured-game visible-information best responses to completed-sweep delayed average policies; checks start after positive averaging. iterations and vector budget retain the admitted requested ceiling; training pass counts record completed work. This is not a universal convergence or unrestricted-game certificate.",
        })
    if expanded_tree:
        result.update({
            "tree_admission": "vector",
            "decision_count_limit_enforced": False,
            "tree_admission_scope": "Aggregate public-state and information-set action-slot ceilings plus structural vector work replace the legacy aggregate decision count; temporary per-flop template ceilings remain.",
        })
        result["limits"]["reference_decision_nodes"] = _MAX_PUBLIC_NODES
        result["limits"]["decision_nodes"] = None
        result["limits"]["decision_nodes_from_public_states"] = _MAX_PUBLIC_STATES
    if sampled:
        result.update({
            "method": "chance-sampled Monte Carlo CFR",
            "resource_model": "chance-sampled",
            "sampling_seed": sampling_seed,
            "samples_per_iteration": samples_per_iteration,
            "sampled_work_budget": sampled_budget,
            "sampler_storage_budget": sampled_storage,
            "exact_diagnostics_admission_reference": sampled_diagnostic_budget,
            "sampling_statistics": sampling_stats if sampling_stats is not None else {
                "world_draws": 0, "actual_node_visits": 0,
                "visited_information_sets": 0},
            "world_decision_work_enforced": False,
            "world_construction_admission_iterations": 1,
            "training_schedule": "simultaneous vanilla regret updates after each frozen sampled batch; sampled own-reach average",
            "sampling_scope": "Samples the complete stored joint conditioned world law with replacement; all betting actions are traversed. Final profile values and legal best responses enumerate the whole configured game. Full-deck preflop remains unsupported.",
        })
        result["limits"]["reference_candidate_pair_iterations"] = _MAX_CANDIDATE_HAND_ITERATIONS
        result["limits"]["reference_world_iterations"] = _MAX_WORLD_ITERATIONS
        result["limits"]["reference_world_decision_work"] = _MAX_WORLD_NODE_WORK
        result["limits"]["candidate_pair_iterations"] = None
        result["limits"]["world_iterations"] = None
        result["limits"]["world_decision_work"] = None
        result["limits"]["constructed_candidate_pairs"] = _MAX_CANDIDATE_HAND_ITERATIONS
        result["limits"]["constructed_worlds"] = min(_MAX_WORLD_ITERATIONS, MAX_SAMPLER_ENTRIES)
    if vector_budget_enabled:
        result.update({
            "resource_model": "public-vector",
            "vector_work_budget": vector_budget,
            "world_decision_work_enforced": False,
        })
        # The legacy estimate is retained as reference evidence, not a second
        # enforced admission ceiling for this explicitly selected model.
        result["limits"]["reference_world_decision_work"] = _MAX_WORLD_NODE_WORK
        result["limits"]["world_decision_work"] = None
    return result

