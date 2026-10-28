"""Bounded exact suit-automorphism check of an existing public structural DAG.

Only unique local signatures are interned. No occurrence/history expansion,
private deal enumeration, ranking, policy row construction, or training occurs.
Callers must separately prove invariance of role-specific weighted priors and
ordered selected boards. This is not proof of betting-game construction legality.
"""
import math

from .cards import DECK
from .shared_public_topology import (
    ActionRecord, ChanceVertex, DecisionVertex, SharedPublicTopology, TerminalVertex,
)

MAX_MODELED_WORK = 500_000_000
MAX_RETAINED_ENTRIES = 2_000_000
MAX_DEPTH = 256
MAX_TOKEN_BYTES = 64
_SUITS = "cdhs"
_ORDER = {card: index for index, card in enumerate(DECK)}


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value):
    _need(type(value) is str and 0 < len(value) <= MAX_TOKEN_BYTES and
          len(value.encode("utf-8")) <= MAX_TOKEN_BYTES, "Invalid bounded public graph token.")
    return value


def _number(value):
    _need(type(value) in (int, float), "Public graph money must be finite numeric values.")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError("Public graph money must be finite numeric values.") from exc
    _need(math.isfinite(result) and result >= 0, "Public graph money must be finite nonnegative values.")
    return result.hex()


def _reveal(street, label, image):
    _text(label)
    if street == "flop":
        _need(len(label) == 6, "Malformed public flop label.")
        cards = tuple(label[index:index+2] for index in (0, 2, 4))
        _need(all(card in _ORDER for card in cards) and len(set(cards)) == 3 and
              cards == tuple(sorted(cards, key=_ORDER.__getitem__)), "Noncanonical public flop label.")
        return "".join(sorted((card[0] + image[_SUITS.index(card[1])] for card in cards), key=_ORDER.__getitem__))
    _need(street in ("turn", "river") and label in _ORDER, "Malformed public turn/river label.")
    return label[0] + image[_SUITS.index(label[1])]


def _initial(history, image):
    _need(type(history) is tuple and len(history) <= MAX_DEPTH, "Malformed initial public history.")
    result = []
    stage = 0
    seen_cards = set()
    for value in history:
        _text(value)
        if value.startswith(("flop@", "turn@", "river@")):
            street, label = value.split("@", 1)
            _need(street == ("flop", "turn", "river")[stage] if stage < 3 else False,
                  "Initial public reveals are out of order.")
            cards = [label[index:index+2] for index in (0, 2, 4)] if street == "flop" else [label]
            mapped = _reveal(street, label, image)
            _need(not seen_cards.intersection(cards), "Repeated card in initial public history.")
            seen_cards.update(cards)
            result.append(street + "@" + mapped);stage += 1
        else:
            result.append(value)
    return tuple(result)


def _group(values):
    _need(type(values) in (tuple, list) and 1 <= len(values) <= 24, "Suit group requires 1 through 24 permutations.")
    result = []
    for image in values:
        _need(type(image) in (str, tuple, list) and len(image) == 4 and
              all(type(suit) is str and suit in _SUITS and len(suit) == 1 for suit in image), "Malformed suit permutation.")
        image = "".join(image)
        _need(set(image) == set(_SUITS) and image not in result, "Suit permutations must be distinct bijections.")
        result.append(image)
    _need(_SUITS in result, "Suit group is missing identity.")
    for first in result:
        inverse = "".join(_SUITS[first.index(suit)] for suit in _SUITS)
        _need(inverse in result, "Suit group is missing an inverse.")
        for second in result:
            composed = "".join(first[_SUITS.index(suit)] for suit in second)
            _need(composed in result, "Suit permutations are not closed under composition.")
    return tuple(sorted(result))


def _children(vertex):
    if type(vertex) is DecisionVertex:
        return vertex.child_ids
    if type(vertex) is ChanceVertex:
        return (child for _, child in vertex.branches)
    return ()


def verify_public_suit_automorphisms(topology, permutations, *,
                                    max_additional_work=MAX_MODELED_WORK,
                                    max_additional_entries=MAX_RETAINED_ENTRIES):
    """Prove exact transformed-root signature equality with bounded unique DAG work.

    Chance branches are label-indexed and compared in canonical label order;
    decision actions remain in their original order. Binary64 money uses hex
    identity, including signed zero. Transformed signatures are lookup-only in
    the identity interner, so an absent transformed subtree always rejects.
    """
    if type(topology) is not SharedPublicTopology:
        raise TypeError("Public suit verification requires SharedPublicTopology.")
    for value, ceiling, name in ((max_additional_work, MAX_MODELED_WORK, "max_additional_work"),
                                  (max_additional_entries, MAX_RETAINED_ENTRIES, "max_additional_entries")):
        _need(type(value) is int and 0 < value <= ceiling, f"{name} must be a positive integer at most {ceiling}.")
    # Reserve validation itself, not just later signature construction. These
    # are explicit conservative logical validation units, not CPU costs.
    _need(type(permutations) in (tuple, list) and 1 <= len(permutations) <= 24,
          "Suit group requires 1 through 24 permutations.")
    validation_work = 64 * len(permutations) ** 2 + 128 * len(permutations) + 128
    _need(validation_work <= max_additional_work,
          "Public suit work admission exceeded before subgroup validation.")

    def charge_validation(units):
        nonlocal validation_work
        _need(validation_work + units <= max_additional_work,
              "Public suit work admission exceeded before graph validation.")
        validation_work += units

    group = _group(permutations)
    vertices = topology.vertices
    _need(type(vertices) is tuple and 0 < len(vertices) <= 250_000, "Public graph vertex capacity exceeded.")
    size = len(vertices)
    _need(type(topology.root_id) is int and 0 <= topology.root_id < size, "Malformed public graph root ID.")
    _need(48 * size + 8192 <= max_additional_entries,
          "Public suit retained-entry admission exceeded before local validation.")
    # Charge the raw shape scan before visiting its vertices. Each variable
    # degree/token payload is charged before visiting/encoding that payload.
    charge_validation(128 * size + 128)
    _need(type(topology.initial_history) is tuple and len(topology.initial_history) <= MAX_DEPTH,
          "Malformed initial public history.")
    charge_validation(64 * len(topology.initial_history))
    for value in topology.initial_history:
        _need(type(value) is str and len(value) <= MAX_TOKEN_BYTES, "Invalid bounded public graph token.")
        charge_validation(32 * len(value))
    _initial(topology.initial_history, _SUITS)
    raw_edges = raw_text_units = 0
    for vertex in vertices:
        if type(vertex) is DecisionVertex:
            _need(type(vertex.actions) is tuple and type(vertex.child_ids) is tuple and
                  0 < len(vertex.actions) == len(vertex.child_ids) <= 32, "Malformed public decision/player/menu lengths.")
            degree = len(vertex.child_ids)
            charge_validation(128 * degree)
            for action in vertex.actions:
                _need(type(action) is ActionRecord and type(action.name) is str and type(action.token) is str and
                      len(action.name) <= MAX_TOKEN_BYTES and len(action.token) <= MAX_TOKEN_BYTES,
                      "Malformed bounded public action record.")
                units = 4 * (len(action.name) + len(action.token))
                charge_validation(32 * units);raw_text_units += units
        elif type(vertex) is ChanceVertex:
            _need(type(vertex.branches) is tuple and 0 < len(vertex.branches) <= 250_000,
                  "Malformed public chance vertex.")
            degree = len(vertex.branches)
            charge_validation(128 * degree)
            _need(48 * size + 32 * (raw_edges + degree) + 8192 <= max_additional_entries,
                  "Public suit retained-entry admission exceeded before branch validation.")
            for branch in vertex.branches:
                _need(type(branch) is tuple and len(branch) == 2 and type(branch[0]) is str and
                      len(branch[0]) <= MAX_TOKEN_BYTES, "Malformed bounded public chance branch.")
                units = 4 * len(branch[0])
                charge_validation(32 * units);raw_text_units += units
        elif type(vertex) is TerminalVertex:
            degree = 0
        else:
            raise ValueError("Unsupported public graph vertex type.")
        raw_edges += degree
        _need(raw_edges <= 1_000_000 and 48 * size + 32 * raw_edges + 8192 <= max_additional_entries,
              "Public suit retained-entry admission exceeded before graph allocation.")
    # This bound is known before monetary validation, child iteration, Kahn
    # arrays, or any identity/transformed signature dictionary is allocated.
    signature_work = (256 * (len(group) + 1) * (size + raw_edges + raw_text_units + 1) +
                      16 * len(group) * raw_edges * max(1, raw_edges.bit_length()) + 16 * len(group) ** 2)
    _need(validation_work + signature_work <= max_additional_work,
          "Public suit work admission exceeded before monetary/child validation.")
    edges = text_bytes = maximum_degree = 0
    # Validate and count before graph-sized arrays or signature dictionaries grow.
    for vertex in vertices:
        if type(vertex) is DecisionVertex:
            _need(type(vertex.player) is int and vertex.player in (0, 1) and type(vertex.actions) is tuple and
                  type(vertex.child_ids) is tuple and 0 < len(vertex.actions) == len(vertex.child_ids) <= 32,
                  "Malformed public decision/player/menu lengths.")
            labels = []
            for action in vertex.actions:
                _need(type(action) is ActionRecord and action.name in ("fold", "check", "call", "bet", "raise", "all_in") and
                      type(action.full_raise) is bool, "Malformed public action record.")
                _number(action.amount);_number(action.raise_to)
                label = _text(action.token)
                _need(not label.startswith(("flop@", "turn@", "river@")), "Decision token impersonates public reveal.")
                labels.append(label);text_bytes += len(label.encode("utf-8")) + len(action.name)
            _need(len(set(labels)) == len(labels), "Duplicate public action labels.")
            degree = len(vertex.child_ids)
        elif type(vertex) is ChanceVertex:
            _need(vertex.street in ("flop", "turn", "river") and type(vertex.card_index) is int and vertex.card_index >= 0 and
                  type(vertex.branches) is tuple and 0 < len(vertex.branches) <= 250_000, "Malformed public chance vertex.")
            # Local branch validation uses a bounded temporary at most E; the
            # conservative capacity guard precedes this allocation.
            _need(48 * size + 32 * (edges + len(vertex.branches)) + 8192 <= max_additional_entries,
                  "Public suit retained-entry admission exceeded before branch validation.")
            labels = []
            for branch in vertex.branches:
                _need(type(branch) is tuple and len(branch) == 2, "Malformed public chance branch.")
                label, _ = branch
                _reveal(vertex.street, label, _SUITS)
                labels.append(label);text_bytes += len(label.encode("utf-8"))
            _need(len(set(labels)) == len(labels), "Duplicate public chance labels.")
            degree = len(vertex.branches)
        elif type(vertex) is TerminalVertex:
            _need(vertex.kind in ("fold", "showdown") and type(vertex.contributions) is tuple and len(vertex.contributions) == 2,
                  "Malformed public terminal.")
            _need((type(vertex.winner) is int and vertex.winner in (0, 1)) if vertex.kind == "fold" else vertex.winner is None,
                  "Malformed public terminal winner.")
            for amount in vertex.contributions:_number(amount)
            degree = 0
        else:
            raise ValueError("Unsupported public graph vertex type.")
        edges += degree;maximum_degree = max(maximum_degree, degree)
        _need(edges <= 1_000_000 and 48 * size + 32 * edges + 8192 <= max_additional_entries,
              "Public suit retained-entry admission exceeded before graph allocation.")
        for child in _children(vertex):
            _need(type(child) is int and 0 <= child < size, "Malformed public graph child ID.")
    retained = 48 * size + 32 * edges + 8192
    work = validation_work + signature_work
    _need(work <= max_additional_work and retained <= max_additional_entries,
          "Public suit work/retained-entry admission exceeded before signatures.")
    indegrees = [0] * size
    for vertex in vertices:
        for child in _children(vertex):indegrees[child] += 1
    order = [index for index, degree in enumerate(indegrees) if degree == 0]
    at = 0
    while at < len(order):
        index = order[at];at += 1
        for child in _children(vertices[index]):
            indegrees[child] -= 1
            if indegrees[child] == 0:order.append(child)
    _need(len(order) == size, "Public graph contains a cycle.")
    depths = [-1] * size;depths[topology.root_id] = 0
    for index in order:
        _need(depths[index] >= 0, "Public graph contains unreachable vertices.")
        for child in _children(vertices[index]):
            depths[child] = max(depths[child], depths[index] + 1)
            _need(depths[child] + len(topology.initial_history) <= MAX_DEPTH, "Public graph depth capacity exceeded.")

    def key(vertex, signatures, image):
        if type(vertex) is TerminalVertex:
            return ("terminal", vertex.kind, vertex.winner, tuple(_number(value) for value in vertex.contributions))
        if type(vertex) is DecisionVertex:
            menu = tuple((a.name, _number(a.amount), _number(a.raise_to), a.full_raise, a.token) for a in vertex.actions)
            return ("decision", vertex.player, menu, tuple(signatures[child] for child in vertex.child_ids))
        return ("chance", vertex.street, vertex.card_index,
                tuple(sorted((_reveal(vertex.street, label, image), signatures[child]) for label, child in vertex.branches)))

    interner = {};identity_ids = [-1] * size
    for index in reversed(order):
        signature = key(vertices[index], identity_ids, _SUITS)
        identifier = interner.get(signature)
        if identifier is None:
            identifier = len(interner);interner[signature] = identifier
        identity_ids[index] = identifier
    identity_root = identity_ids[topology.root_id]
    lookups = 0
    for image in group:
        _need(_initial(topology.initial_history, image) == topology.initial_history,
              "Suit transformation changes initial public history.")
        transformed = [-1] * size
        for index in reversed(order):
            identifier = interner.get(key(vertices[index], transformed, image))
            _need(identifier is not None, "Suit transformation has a missing public subtree signature.")
            transformed[index] = identifier;lookups += 1
        _need(transformed[topology.root_id] == identity_root, "Suit transformation changes public root signature.")
    return {"contract": "exact-public-suit-automorphism-v1", "permutations": list(group),
        "group_size": len(group), "unique_vertices": size, "unique_edges": edges,
        "maximum_depth": max(depths), "identity_signature_count": len(interner),
        "transformed_signature_lookups": lookups, "transformed_signature_insertions": 0,
        "modeled_work_upper": work, "modeled_work_limit": max_additional_work,
        "validation_work_upper": validation_work, "signature_work_upper": signature_work,
        "retained_entries_upper": retained, "retained_entry_limit": max_additional_entries,
        "additional_retained_entries_upper": retained,
        "expanded_occurrences_visited": 0, "rank_calls": 0, "training_calls": 0,
        "full_public_graph_automorphism": True,
        "scope": "Exact unique-DAG signature proof of labeled public-history graph symmetry, conditional on the supplied graph. No history or information rows are merged. Weighted role priors/selected boards require separate invariance proof; no betting legality, reach-equivalence, policy quality, CPU or allocator-memory claim."}
