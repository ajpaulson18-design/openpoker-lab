"""Independent bounded N9 support and row-census reference.

This is test support for the first full-deck frozen-update proof only.  It
builds no native history/routing object, private-pair-by-board table, training
state, or RNG.  Public betting structure comes from the independent
card-free numeric template; physical support is factored by own hand and
visible prefix over the fixed nine-card proof deck.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations, permutations
from types import MappingProxyType

from tests.full_deck_public_chance_reference import PROOF9, proof_ranges
from tests.virtual_betting_template_reference import (
    build_reference_template,
    literal_reference_census,
)


PROFILE_VERSION = "frozen-pow2-profile-v1"
_PROFILE_DOMAIN = b"OPL-FROZEN-POLICY-V1\0"
_FNV_OFFSET = 14695981039346656037
_FNV_PRIME = 1099511628211
_MASK64 = (1 << 64) - 1
_STREETS = (0, 3, 4, 5)
_PREFIX_LENGTHS = (0, 3, 4, 5)
_TARGET_SUFFIX_COUNTS = {0: 20, 3: 2, 4: 1, 5: 1}
_TARGET_DK = {0: 1, 3: 10, 4: 20, 5: 20}
_UNFILTERED_COMPLETIONS = {0: 2520, 3: 30, 4: 5, 5: 1}
_MAX_PREFIXES = 3109
_MAX_PROPOSALS = 2520
_MAX_HANDS_PER_SEAT = 2
_MAX_HISTORY_TOKENS = 64
_MAX_ACTIONS = 20
_MAX_TOKEN_BYTES = 64
_MAX_WEIGHT_COMPONENT_BITS = 64


def scaled_proof9_ranges():
    """Return the frozen, exactly scaled two-hand ranges in input order."""
    sides = []
    for side in proof_ranges():
        # The frozen update protocol scales every binary64 range weight by 1/2.
        sides.append(tuple((tuple(hand), Fraction.from_float(float(weight)) / 2)
                           for hand, weight in side))
    return tuple(sides)


def _normalizer(ranges):
    total = Fraction(0)
    for hand0, weight0 in ranges[0]:
        for hand1, weight1 in ranges[1]:
            if set(hand0).isdisjoint(hand1):
                total += weight0 * weight1
    return total


def _compatible_pair_receipt(ranges, normalizer):
    rows = []
    for hand0, weight0 in ranges[0]:
        for hand1, weight1 in ranges[1]:
            if set(hand0).isdisjoint(hand1):
                raw = weight0 * weight1
                rows.append({"sb_hand_ids": hand0, "bb_hand_ids": hand1,
                             "raw_pair_mass": raw,
                             "normalized_pair_probability": raw / normalizer})
    return tuple(rows)


def _validated_profile_inputs(actor, hand, history, actions):
    if type(actor) is not int or actor not in (0, 1):
        raise ValueError("actor must be global seat 0 or 1")
    if (type(hand) is not tuple or len(hand) != 2 or
            any(type(card) is not int or not 0 <= card < 52 for card in hand) or
            hand[0] >= hand[1]):
        raise ValueError("hand must be two increasing physical card IDs")
    if type(history) is not tuple or len(history) > _MAX_HISTORY_TOKENS:
        raise ValueError("history must be a bounded tuple of visible tokens")
    token_bytes = []
    for token in history:
        if type(token) is not str:
            raise ValueError("history tokens must be strings")
        try:
            raw = token.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("history tokens must be ASCII") from exc
        if not raw or len(raw) > _MAX_TOKEN_BYTES:
            raise ValueError("history token length is outside the protocol")
        token_bytes.append(raw)
    if type(actions) is not tuple or not 1 <= len(actions) <= _MAX_ACTIONS:
        raise ValueError(f"ordered action menu must contain 1 through {_MAX_ACTIONS} tokens")
    for action in actions:
        if type(action) is not str:
            raise ValueError("action tokens must be strings")
        try:
            raw = action.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("action tokens must be ASCII") from exc
        if not raw or len(raw) > _MAX_TOKEN_BYTES:
            raise ValueError("action token length is outside the protocol")
    return tuple(token_bytes)


def selector_hash(actor, hand, history, actions):
    """Hash the exact pinned selector byte encoding; hashes never key rows."""
    token_bytes = _validated_profile_inputs(actor, hand, history, actions)
    payload = bytearray(_PROFILE_DOMAIN)
    payload.extend((actor, hand[0], hand[1]))
    payload.extend(len(token_bytes).to_bytes(2, "little"))
    for raw in token_bytes:
        payload.extend(len(raw).to_bytes(2, "little"))
        payload.extend(raw)
    payload.append(len(actions))
    value = _FNV_OFFSET
    for byte in payload:
        value ^= byte
        value = (value * _FNV_PRIME) & _MASK64
    return value


def frozen_profile_probabilities(actor, hand, history, actions):
    """Return exact protocol-v1 dyadic probabilities in ordered menu order."""
    value = selector_hash(actor, hand, history, actions)
    count = len(actions)
    rotated = [(index + ((value >> 32) % count)) % count
               for index in range(count)]
    zero_index = ((value >> 8) % count
                  if count > 1 and (value & 3) == 0 else None)
    active = [index for index in rotated if index != zero_index]
    width = len(active)
    result = [Fraction(0) for _ in actions]
    for position, index in enumerate(active):
        exponent = 0 if width == 1 else min(position + 1, width - 1)
        result[index] = Fraction(1, 1 << exponent)
    if sum(result, Fraction(0)) != 1:
        raise ArithmeticError("frozen profile does not sum exactly to one")
    return tuple(result)


def _proof_prefixes(deck):
    """Return canonical 0/3/4/5-card prefixes, capped at the fixed N9 size."""
    _validate_proof_deck(deck)
    by_length = {0: ((),)}
    flops = tuple(combinations(deck, 3))
    by_length[3] = flops
    turns = []
    rivers = []
    for flop in flops:
        remaining = tuple(card for card in deck if card not in flop)
        for turn in remaining:
            turns.append((*flop, turn))
            for river in remaining:
                if river != turn:
                    rivers.append((*flop, turn, river))
    by_length[4] = tuple(turns)
    by_length[5] = tuple(rivers)
    total = sum(map(len, by_length.values()))
    if total != _MAX_PREFIXES or len(by_length[5]) != _MAX_PROPOSALS:
        raise ArithmeticError("PROOF9 prefix geometry changed")
    return MappingProxyType({length: tuple(values)
                             for length, values in by_length.items()})


def _validate_proof_deck(deck):
    """Validate the exact built-in deck tuple before any range traversal."""
    if type(deck) is not tuple or len(deck) != len(PROOF9):
        raise ValueError("the physical prefix index accepts only the pinned PROOF9 tuple")
    for index, card in enumerate(deck):
        if type(card) is not int or card != PROOF9[index]:
            raise ValueError("the physical prefix index accepts only the pinned PROOF9 tuple")


def _board_proposals(prefixes):
    result = []
    for flop in prefixes[3]:
        remaining = tuple(card for card in PROOF9 if card not in flop)
        for turn, river in permutations(remaining, 2):
            result.append((*flop, turn, river))
    if len(result) != _MAX_PROPOSALS or len(set(result)) != _MAX_PROPOSALS:
        raise ArithmeticError("PROOF9 proposal enumeration changed")
    return tuple(result)


def _proposal_index(prefixes, proposals):
    """Return both proposal laws and their independently summed prefix q."""
    uniform_board = Fraction(1, _MAX_PROPOSALS)
    weighted_denominator = 12600
    river_weight = {card: index + 1 for index, card in enumerate(PROOF9)}
    uniform_prefix = {}
    weighted_prefix = {}
    weighted_board = {}
    for length in _PREFIX_LENGTHS:
        for prefix in prefixes[length]:
            uniform_prefix[prefix] = Fraction(_UNFILTERED_COMPLETIONS[length],
                                               _MAX_PROPOSALS)
            if length == 0:
                weighted_prefix[prefix] = Fraction(1)
            elif length == 3:
                outside = [card for card in PROOF9 if card not in prefix]
                weighted_prefix[prefix] = Fraction(
                    5 * sum(river_weight[card] for card in outside),
                    weighted_denominator)
            elif length == 4:
                outside = [card for card in PROOF9 if card not in prefix]
                weighted_prefix[prefix] = Fraction(
                    sum(river_weight[card] for card in outside),
                    weighted_denominator)
            else:
                weighted_prefix[prefix] = Fraction(river_weight[prefix[4]],
                                                    weighted_denominator)
    for board in proposals:
        weighted_board[board] = Fraction(river_weight[board[4]],
                                         weighted_denominator)
    if sum(weighted_board.values(), Fraction(0)) != 1:
        raise ArithmeticError("river-weighted PROOF9 proposal is not normalized")
    if sum(uniform_prefix[prefix] for prefix in prefixes[3]) != 1:
        raise ArithmeticError("uniform flop proposal is not normalized")
    if sum(weighted_prefix[prefix] for prefix in prefixes[3]) != 1:
        raise ArithmeticError("weighted flop proposal is not normalized")
    for length in (4, 5):
        if sum(uniform_prefix[prefix] for prefix in prefixes[length]) != 1:
            raise ArithmeticError("uniform prefix proposal is not normalized")
        if sum(weighted_prefix[prefix] for prefix in prefixes[length]) != 1:
            raise ArithmeticError("weighted prefix proposal is not normalized")
    return {
        "uniform": MappingProxyType({"board": uniform_board,
                                     "prefix": MappingProxyType(uniform_prefix)}),
        "river_weighted": MappingProxyType({"board": MappingProxyType(weighted_board),
                                             "prefix": MappingProxyType(weighted_prefix)}),
    }


@dataclass(frozen=True)
class PhysicalPrefixIndex:
    deck: tuple
    ranges: tuple
    normalizer: Fraction
    prefixes: object
    proposals: tuple
    proposal_laws: object
    # prefix -> (seat0 per-input-hand masses, seat1 per-input-hand masses)
    masses: object

    def mass(self, prefix, player, hand_index):
        if prefix not in self.masses:
            raise ValueError("unknown PROOF9 public prefix")
        if type(player) is not int or player not in (0, 1):
            raise ValueError("player must be global seat 0 or 1")
        if type(hand_index) is not int or not 0 <= hand_index < len(self.ranges[player]):
            raise ValueError("hand index is outside the pinned range")
        return self.masses[prefix][player][hand_index]

    def supported_hand_counts(self):
        return MappingProxyType({
            length: tuple(tuple(sum(self.mass(prefix, player, hand_index) > 0
                                     for prefix in self.prefixes[length])
                                for hand_index in range(len(self.ranges[player]))
                                ) for player in (0, 1))
            for length in _PREFIX_LENGTHS
        })


def build_physical_prefix_index(ranges=None, deck=PROOF9):
    """Build only the fixed 3,109-prefix physical support/mass index."""
    _validate_proof_deck(deck)
    ranges = scaled_proof9_ranges() if ranges is None else ranges
    if type(ranges) is not tuple or len(ranges) != 2:
        raise ValueError("ranges must contain the two pinned seats")
    for side in ranges:
        if type(side) is not tuple or len(side) != _MAX_HANDS_PER_SEAT:
            raise ValueError("PROOF9 census requires exactly two hands per seat")
        seen = set()
        for entry in side:
            if type(entry) is not tuple or len(entry) != 2:
                raise ValueError("range entries must be exact hand/weight tuples")
            hand, weight = entry
            if (type(hand) is not tuple or len(hand) != 2 or
                    any(type(card) is not int or card not in deck for card in hand) or
                    hand[0] >= hand[1] or hand in seen):
                raise ValueError("range hands must be unique increasing PROOF9 card pairs")
            if type(weight) is not Fraction:
                raise ValueError("range weights must be positive exact Fraction snapshots")
            if (weight.numerator.bit_length() > _MAX_WEIGHT_COMPONENT_BITS or
                    weight.denominator.bit_length() > _MAX_WEIGHT_COMPONENT_BITS):
                raise ValueError("range weight exceeds the bounded Fraction input width")
            if weight <= 0:
                raise ValueError("range weights must be positive exact Fraction snapshots")
            seen.add(hand)
    normalized_ranges = tuple(tuple((entry[0], entry[1]) for entry in side)
                              for side in ranges)
    if normalized_ranges != scaled_proof9_ranges():
        raise ValueError("the physical census accepts only the pinned scaled PROOF9 ranges")
    normalizer = _normalizer(normalized_ranges)
    if normalizer != Fraction(29, 64):
        raise ValueError("the pinned scaled PROOF9 normalizer must be 29/64")
    prefixes = _proof_prefixes(deck)
    proposals = _board_proposals(prefixes)
    proposal_laws = _proposal_index(prefixes, proposals)
    masses = {}
    for length in _PREFIX_LENGTHS:
        suffix_count = _TARGET_SUFFIX_COUNTS[length]
        for prefix in prefixes[length]:
            prefix_cards = set(prefix)
            seat_masses = []
            for player in (0, 1):
                own_masses = []
                opp = normalized_ranges[1 - player]
                for own_hand, own_weight in normalized_ranges[player]:
                    if prefix_cards.intersection(own_hand):
                        own_masses.append(Fraction(0))
                        continue
                    raw = Fraction(0)
                    for opp_hand, opp_weight in opp:
                        if (prefix_cards.isdisjoint(opp_hand) and
                                set(own_hand).isdisjoint(opp_hand)):
                            raw += own_weight * opp_weight * suffix_count
                    # The common denominator Z*20 keeps the selected target
                    # law distinct from both raw support and proposal q.
                    own_masses.append(raw / (normalizer * 20))
                seat_masses.append(tuple(own_masses))
            masses[prefix] = tuple(seat_masses)
    supported_boards = {prefix for prefix in prefixes[5]
                        if any(mass > 0 for side in masses[prefix] for mass in side)}
    if len(supported_boards) != 60:
        raise ArithmeticError("the pinned PROOF9 target support must contain 60 boards")
    # At every visible prefix length, normalized target mass sums to one for
    # each seat. This also detects accidental use of a selected-board Z.
    for length in _PREFIX_LENGTHS:
        for player in (0, 1):
            total = sum((self_mass for prefix in prefixes[length]
                         for self_mass in masses[prefix][player]), Fraction(0))
            if total != 1:
                raise ArithmeticError("normalized target prefix masses do not sum to one")
    return PhysicalPrefixIndex(
        deck, normalized_ranges, normalizer, prefixes, proposals,
        proposal_laws, MappingProxyType(masses))


def _template_case():
    """Return the exact v1 money/menu configuration with a normalization anchor."""
    later = {"bet_sizes": [0.5, 1.0], "raise_sizes": [0.25],
             "max_raises": 1, "include_all_in": True}
    return {
        "id": "frozen-update-v1-template-anchor",
        "sb_range": "AsAd",
        "bb_range": "KsKd",
        "config": {"starting_stack": 8.0, "small_blind": 0.5,
                    "big_blind": 1.0, "raise_sizes": [1.0],
                    "max_raises": 1, "include_all_in": True},
        # This one runout is required by the numeric input normalizer only;
        # it is not the PROOF9 chance space or a selected-world model.
        "runouts": ["2c3c4d7h8h"],
        "flop_config": dict(later),
        "turn_config": dict(later),
        "river_config": dict(later),
    }


def _literal_history_skeleton_counts(template):
    """Walk every action-history path and retain only a bounded uniqueness set.

    Reveal markers are symbolic placeholders here. Physical cards are counted
    later through prefix support factors; no expanded full-history rows are
    constructed.
    """
    counts = [0] * len(template.nodes)
    seen = set()
    todo = [(template.root, ())]
    while todo:
        node_id, history = todo.pop()
        node = template.nodes[node_id]
        identity = (node_id, history)
        if identity in seen:
            raise ArithmeticError("a literal action-history skeleton was revisited")
        seen.add(identity)
        counts[node_id] += 1
        if node.phase in ("fold", "showdown"):
            continue
        for edge in reversed(node.edges):
            if node.phase == "reveal":
                token = ("reveal", node.state.board_length)
            else:
                if edge.token is None:
                    raise ArithmeticError("a decision action lacks its full-history token")
                token = ("action", edge.token)
            todo.append((edge.child, (*history, token)))
        if len(seen) > 1105:
            raise ArithmeticError("the pinned literal history census exceeded its bound")
    if tuple(counts) != tuple(row[0] for row in template.histories):
        raise ArithmeticError("literal action-history walk disagrees with template factors")
    return len(seen)


def build_frozen_update_census(*, rule_budget=None):
    """Return an independent scalar row/action census for the pinned v1/N9 case.

    No physical row keys are retained. Full-history identity is counted from
    literal action-history multiplicities, with per-hand physical-prefix
    support applied as a separate factor.
    """
    case = _template_case()
    template = build_reference_template(case, rule_budget=rule_budget)
    literal = literal_reference_census(case, rule_budget=rule_budget)
    if template.receipt["nodes"] != 388 or template.receipt["edges"] != 410:
        raise ArithmeticError("the v1 card-free template geometry changed")
    if literal["logical_occurrences"] != 1105:
        raise ArithmeticError("the v1 literal history walk changed")
    literal_skeleton_count = _literal_history_skeleton_counts(template)
    if literal_skeleton_count != literal["logical_occurrences"]:
        raise ArithmeticError("full token skeleton count disagrees with literal census")
    for node_id, node in enumerate(template.nodes):
        if literal["by_key"].get(node.key, (0,))[0] != template.histories[node_id][0]:
            raise ArithmeticError("literal history and template path counts disagree")

    physical = build_physical_prefix_index()
    support_counts = physical.supported_hand_counts()
    positive_prefix_counts = {
        length: sum(
            any(physical.mass(prefix, player, hand_index) > 0
                for player in (0, 1)
                for hand_index in range(len(physical.ranges[player])))
            for prefix in physical.prefixes[length])
        for length in _PREFIX_LENGTHS
    }
    unfiltered_prefix_count = {0: 1, 3: 84, 4: 504, 5: 2520}
    by_street = {street: {
        "unfiltered_public_decision_occurrences": 0,
        "unfiltered_decision_action_slots": 0,
        "physical_supported_decision_occurrences": 0,
        "physical_supported_rows": 0,
        "physical_supported_decision_action_slots": 0,
        "physical_supported_row_history_tokens": 0,
        "physical_supported_row_history_bytes": 0,
        "unfiltered_terminal_occurrences": 0,
        "physical_supported_terminal_occurrences": 0,
    } for street in _STREETS}
    by_actor = {street: {player: {"unfiltered_decision_occurrences": 0,
                                  "unfiltered_decision_action_slots": 0,
                                  "supported_decision_occurrences": 0,
                                  "supported_rows": 0,
                                  "supported_decision_action_slots": 0}
                         for player in (0, 1)} for street in _STREETS}
    by_hand = {street: {player: [
        {"hand_ids": hand, "supported_prefix_count": support_counts[street][player][hand_index],
         "betting_history_occurrences": 0, "supported_rows": 0,
         "supported_decision_action_slots": 0}
        for hand_index, (hand, _weight) in enumerate(physical.ranges[player])]
        for player in (0, 1)} for street in _STREETS}
    literal_action_histories = 0
    unfiltered_public_decision_occurrences = 0
    unfiltered_decision_action_slots = 0
    physical_supported_decision_occurrences = 0
    physical_supported_rows = 0
    physical_supported_decision_action_slots = 0
    physical_supported_row_history_tokens = 0
    physical_supported_row_history_bytes = 0
    physical_supported_terminals = 0
    staged_record_visits_by_street = {}
    staged_history_tokens_by_street = {}
    staged_history_bytes_by_street = {}
    for node_id, node in enumerate(template.nodes):
        path_count = template.histories[node_id][0]
        if path_count == 0:
            raise ArithmeticError("template contains an unreachable state")
        street = node.state.board_length if node.phase == "reveal" else node.street
        if node.phase == "decision":
            street = node.street
            literal_action_histories += path_count
            prefix_count = unfiltered_prefix_count[street]
            unfiltered = path_count * prefix_count
            unfiltered_slots = unfiltered * len(node.edges)
            player = node.state.player
            own_prefix_rows = sum(support_counts[street][player])
            own_supported_prefixes = sum(
                any(physical.mass(prefix, player, hand_index) > 0
                    for hand_index in range(len(physical.ranges[player])))
                for prefix in physical.prefixes[street])
            supported_occurrences = path_count * own_supported_prefixes
            supported_rows = path_count * own_prefix_rows
            supported_slots = supported_rows * len(node.edges)
            path_history_tokens = template.histories[node_id][1]
            path_history_bytes = template.histories[node_id][2]
            row_history_tokens = path_history_tokens * own_prefix_rows
            row_history_bytes = path_history_bytes * own_prefix_rows
            totals = by_street[street]
            totals["unfiltered_public_decision_occurrences"] += unfiltered
            totals["unfiltered_decision_action_slots"] += unfiltered_slots
            totals["physical_supported_decision_occurrences"] += supported_occurrences
            totals["physical_supported_rows"] += supported_rows
            totals["physical_supported_decision_action_slots"] += supported_slots
            totals["physical_supported_row_history_tokens"] += row_history_tokens
            totals["physical_supported_row_history_bytes"] += row_history_bytes
            staged_record_visits_by_street[street] = (
                staged_record_visits_by_street.get(street, 0) + supported_rows)
            staged_history_tokens_by_street[street] = (
                staged_history_tokens_by_street.get(street, 0) + row_history_tokens)
            staged_history_bytes_by_street[street] = (
                staged_history_bytes_by_street.get(street, 0) + row_history_bytes)
            actor = by_actor[street][player]
            actor["unfiltered_decision_occurrences"] += unfiltered
            actor["unfiltered_decision_action_slots"] += unfiltered_slots
            actor["supported_decision_occurrences"] += supported_occurrences
            actor["supported_rows"] += supported_rows
            actor["supported_decision_action_slots"] += supported_slots
            for hand_index, _entry in enumerate(physical.ranges[player]):
                hand_rows = path_count * support_counts[street][player][hand_index]
                hand_record = by_hand[street][player][hand_index]
                hand_record["betting_history_occurrences"] += path_count
                hand_record["supported_rows"] += hand_rows
                hand_record["supported_decision_action_slots"] += hand_rows * len(node.edges)
            unfiltered_public_decision_occurrences += unfiltered
            unfiltered_decision_action_slots += unfiltered_slots
            physical_supported_decision_occurrences += supported_occurrences
            physical_supported_rows += supported_rows
            physical_supported_decision_action_slots += supported_slots
            physical_supported_row_history_tokens += row_history_tokens
            physical_supported_row_history_bytes += row_history_bytes
        elif node.phase in ("fold", "showdown"):
            prefix_count = unfiltered_prefix_count[node.street]
            unfiltered = path_count * prefix_count
            any_supported = sum(
                any(physical.mass(prefix, player, hand_index) > 0
                    for player in (0, 1)
                    for hand_index in range(len(physical.ranges[player])))
                for prefix in physical.prefixes[node.street])
            supported = path_count * any_supported
            by_street[node.street]["unfiltered_terminal_occurrences"] += unfiltered
            by_street[node.street]["physical_supported_terminal_occurrences"] += supported
            physical_supported_terminals += supported

    return {
        "version": "n9-frozen-update-census-v1",
        "scope": "bounded census only; no sampling, update, or training executed",
        "profile_version": PROFILE_VERSION,
        "target_prior": {
            "deck_ids": PROOF9,
            "ranges": physical.ranges,
            "normalizer_z": physical.normalizer,
            "weight_scale": "each original binary64 range weight divided by 2 exactly",
            "compatible_pairs": _compatible_pair_receipt(
                physical.ranges, physical.normalizer),
            "compatible_pair_probabilities": (Fraction(3, 29),
                                                Fraction(8, 29),
                                                Fraction(18, 29)),
            "normalizer_units": "actual scaled binary64 prior; Z=29/64",
        },
        "proposal_geometry": {
            "boards": len(physical.proposals),
            "prefix_counts": {length: len(physical.prefixes[length])
                              for length in _PREFIX_LENGTHS},
            "total_prefixes": sum(len(physical.prefixes[length])
                                  for length in _PREFIX_LENGTHS),
            "positive_target_prefix_counts": positive_prefix_counts,
            "positive_target_prefix_total": sum(positive_prefix_counts.values()),
            "unfiltered_completion_counts": dict(_UNFILTERED_COMPLETIONS),
            "target_suffix_counts": dict(_TARGET_SUFFIX_COUNTS),
            "target_dk": dict(_TARGET_DK),
            "uniform_q_prefix": physical.proposal_laws["uniform"]["prefix"],
            "river_weighted_q_prefix": physical.proposal_laws["river_weighted"]["prefix"],
            "uniform_q_board": physical.proposal_laws["uniform"]["board"],
            "river_weighted_q_board": physical.proposal_laws["river_weighted"]["board"],
            "target_supported_boards": sum(
                any(physical.mass(board, player, hand_index) > 0
                    for player in (0, 1)
                    for hand_index in range(len(physical.ranges[player])))
                for board in physical.prefixes[5]),
        },
        "template": dict(template.receipt),
        "literal_history_census": {
            "nodes": literal["nodes"], "edges": literal["edges"],
            "logical_occurrences": literal["logical_occurrences"],
            "unique_symbolic_history_skeletons": literal_skeleton_count,
            "max_depth": literal["max_depth"],
            "streets": literal["streets"],
        },
        "support_counts_by_hand": support_counts,
        "target_prefix_mass_sums": {
            length: tuple(sum((physical.mass(prefix, player, hand_index)
                               for prefix in physical.prefixes[length]
                               for hand_index in range(len(physical.ranges[player]))),
                              Fraction(0)) for player in (0, 1))
            for length in _PREFIX_LENGTHS
        },
        "rows": {
            "unfiltered_public_decision_occurrences": unfiltered_public_decision_occurrences,
            "unfiltered_decision_action_slots": unfiltered_decision_action_slots,
            "physical_supported_decision_occurrences": physical_supported_decision_occurrences,
            "physical_supported_rows": physical_supported_rows,
            "physical_supported_decision_action_slots": physical_supported_decision_action_slots,
            "physical_supported_row_history_tokens": physical_supported_row_history_tokens,
            "physical_supported_row_history_bytes": physical_supported_row_history_bytes,
            "physical_supported_terminal_occurrences": physical_supported_terminals,
            "estimated_unique_staging_rows": physical_supported_rows,
            "estimated_staging_record_visits_by_street_per_proposal_law": {
                street: staged_record_visits_by_street.get(street, 0) *
                _UNFILTERED_COMPLETIONS[street] for street in _STREETS},
            "estimated_staging_record_visits_per_proposal_law": sum(
                staged_record_visits_by_street.get(street, 0) *
                _UNFILTERED_COMPLETIONS[street] for street in _STREETS),
            "estimated_staging_record_visits_for_both_proposal_laws": 2 * sum(
                staged_record_visits_by_street.get(street, 0) *
                _UNFILTERED_COMPLETIONS[street] for street in _STREETS),
            "estimated_staging_history_tokens_by_street_per_proposal_law": {
                street: staged_history_tokens_by_street.get(street, 0) *
                _UNFILTERED_COMPLETIONS[street] for street in _STREETS},
            "estimated_staging_history_bytes_by_street_per_proposal_law": {
                street: staged_history_bytes_by_street.get(street, 0) *
                _UNFILTERED_COMPLETIONS[street] for street in _STREETS},
            "estimated_staging_history_tokens_per_proposal_law": sum(
                staged_history_tokens_by_street.get(street, 0) *
                _UNFILTERED_COMPLETIONS[street] for street in _STREETS),
            "estimated_staging_history_bytes_per_proposal_law": sum(
                staged_history_bytes_by_street.get(street, 0) *
                _UNFILTERED_COMPLETIONS[street] for street in _STREETS),
            "estimated_staging_history_tokens_for_both_proposal_laws": 2 * sum(
                staged_history_tokens_by_street.get(street, 0) *
                _UNFILTERED_COMPLETIONS[street] for street in _STREETS),
            "estimated_staging_history_bytes_for_both_proposal_laws": 2 * sum(
                staged_history_bytes_by_street.get(street, 0) *
                _UNFILTERED_COMPLETIONS[street] for street in _STREETS),
            "unfiltered_row_visits_per_board_two_target_passes": 2 * sum(
                by_street[street]["unfiltered_public_decision_occurrences"] //
                len(physical.prefixes[street]) for street in _STREETS),
            "unfiltered_action_slot_visits_per_board_two_target_passes": 2 * sum(
                by_street[street]["unfiltered_decision_action_slots"] //
                len(physical.prefixes[street]) for street in _STREETS),
            "staged_rows": None,
            "attempted_staging": False,
            "materialized_row_keys": 0,
            "by_street": by_street,
            "by_actor": by_actor,
            "by_hand": by_hand,
        },
    }
