"""Q-free joint-world expected CFR update reference for the fixed PROOF9 game.

This test-only oracle streams the 60 compatible private-pair/board worlds. It
uses the independent card-free numeric template only as a memo of immutable
menus and money transitions. Every physical world recursively walks every
action history; no node-value, row, or chance result is shared across routes.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations, permutations
from types import MappingProxyType

from scripts.matrix_free_certificate_budget import Budget, DEFAULT_LIMITS
from scripts.preflop_validation import independent_rank
from tests.full_deck_public_chance_reference import PROOF9, card_name
from tests.virtual_betting_template_reference import build_reference_template
from tests.virtual_frozen_update_reference import (
    _template_case, build_frozen_update_census, scaled_proof9_ranges,
)


PROFILE_DOMAIN = b"OPL-FROZEN-POLICY-V1\0"
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
MASK64 = (1 << 64) - 1
MAX_ROWS = 24_420
MAX_ACTION_SLOTS = 58_164
MAX_WORLD_VISITS = 66_300
MAX_HISTORY_TOKENS = 249_662
MAX_HISTORY_BYTES = 1_500_675
MAX_FRACTION_CELLS = 140_748
MAX_OUTPUT_TEXT_BYTES = 16_777_216


@dataclass(frozen=True)
class ExpectedUpdateAdmission:
    limits: object
    template: object
    census: object
    ranges: tuple
    normalizer: Fraction
    worlds: int
    visits: int
    action_slots: int
    history_tokens: int
    history_bytes: int
    action_token_bytes: int
    output_text_bytes: int
    rank_calls: int
    fraction_operations_upper: int
    work_upper: int
    entries_upper: int
    created_bits_upper: int
    max_integer_bits_upper: int
    rule_setup_work: int
    rule_setup_entries: int
    rule_setup_created_bits: int

    def receipt(self):
        return {
            "version": "q-free-joint-world-expected-update-v1",
            "limits": dict(self.limits),
            "worlds_streamed": self.worlds,
            "world_node_visits_upper": self.visits,
            "world_action_slot_visits_upper": self.action_slots,
            "rank_calls_upper": self.rank_calls,
            "unique_rows_upper": MAX_ROWS,
            "unique_action_slots_upper": MAX_ACTION_SLOTS,
            "unique_history_tokens_upper": MAX_HISTORY_TOKENS,
            "unique_history_bytes_upper": MAX_HISTORY_BYTES,
            "unique_action_token_bytes_upper": self.action_token_bytes,
            "output_text_bytes_upper": self.output_text_bytes,
            "output_text_bytes_limit": self.limits["output_text_bytes"],
            "output_text_bytes_scope": (
                "UTF-8 payload of full-history and ordered action tokens; excludes object headers and serialization framing"),
            "fraction_cells_upper": MAX_FRACTION_CELLS,
            "fraction_operations_upper": self.fraction_operations_upper,
            "runtime_work_upper": self.work_upper,
            "retained_entries_upper": self.entries_upper,
            "created_fraction_bits_upper": self.created_bits_upper,
            "max_forecast_integer_bits_upper": self.max_integer_bits_upper,
            "card_free_rule_setup": {
                "work": self.rule_setup_work,
                "entries": self.rule_setup_entries,
                "created_bits": self.rule_setup_created_bits,
                "scope": "complete census, literal validation, second template build and fixed N9 setup on one shared reduce-only meter; values are reserved upper bounds",
            },
            "scope": "bounded nine-card expected update; no proposal q, sampling, training, or native values",
        }


@dataclass(frozen=True)
class ExpectedUpdateRow:
    actor: int
    hand_ids: tuple[int, int]
    history: tuple[str, ...]
    actions: tuple[str, ...]
    action_exponents: tuple[int, ...]
    regret_masses: tuple[Fraction, ...]
    average_reach_mass: Fraction
    average_action_masses: tuple[Fraction, ...]

    @property
    def key(self):
        return self.actor, self.hand_ids, self.history


@dataclass(frozen=True)
class ExpectedUpdateResult:
    admission: ExpectedUpdateAdmission
    rows: object
    receipt: object


def _profile_exponents(actor, hand, history, actions):
    """Compute the pinned profile locally; -1 denotes an exact zero action."""
    if (type(actor) is not int or actor not in (0, 1) or len(hand) != 2 or
            not 1 <= len(actions) <= 20 or len(history) > 64):
        raise ValueError("profile input is outside the frozen v1 bounds")
    payload = bytearray(PROFILE_DOMAIN)
    payload.extend((actor, hand[0], hand[1]))
    payload.extend(len(history).to_bytes(2, "little"))
    for token in history:
        raw = token.encode("ascii")
        if not 0 < len(raw) <= 64:
            raise ValueError("history token is outside the frozen v1 bounds")
        payload.extend(len(raw).to_bytes(2, "little"))
        payload.extend(raw)
    payload.append(len(actions))
    for action in actions:
        raw = action.encode("ascii")
        if not 0 < len(raw) <= 64:
            raise ValueError("action token is outside the frozen v1 bounds")
    value = FNV_OFFSET
    for byte in payload:
        value = ((value ^ byte) * FNV_PRIME) & MASK64
    width = len(actions)
    rotated = tuple((i + ((value >> 32) % width)) % width for i in range(width))
    zero = ((value >> 8) % width if width > 1 and (value & 3) == 0 else None)
    active = tuple(index for index in rotated if index != zero)
    result = [-1] * width
    for pos, index in enumerate(active):
        result[index] = 0 if len(active) == 1 else min(pos + 1, len(active) - 1)
    # The active-exponent construction is a geometric dyadic partition by
    # definition; tests compare it to the separately retained selector.
    return tuple(result)


def _checked_limits(limits):
    if limits is None:
        return {**DEFAULT_LIMITS, "output_text_bytes": MAX_OUTPUT_TEXT_BYTES}
    allowed = {*DEFAULT_LIMITS, "output_text_bytes"}
    if type(limits) is not dict or set(limits) - allowed:
        raise ValueError("expected-update limits must be a bounded plain mapping")
    result = {**DEFAULT_LIMITS, "output_text_bytes": MAX_OUTPUT_TEXT_BYTES}
    for name, value in limits.items():
        maximum = (MAX_OUTPUT_TEXT_BYTES if name == "output_text_bytes"
                   else DEFAULT_LIMITS[name])
        if type(value) is not int or not 0 < value <= maximum:
            raise ValueError("expected-update limits are positive and reduce-only")
        result[name] = value
    return result


def prepare_expected_update_reference(limits=None):
    """Build the bounded independent menu cache and pre-admit every later allocation."""
    ceilings = _checked_limits(limits)
    # The census checks the cache against the #283 literal route walk and
    # independently derives all physical-prefix support totals.
    setup_forecast = {"work": 200_000_000, "entries": 1_000_000,
                      "created_bits": 2_000_000_000, "integer_bits": 4096}
    for name,value in setup_forecast.items():
        if value>ceilings[name]:
            raise ValueError("expected-update complete setup "+{"entries":"entry","integer_bits":"integer bit","created_bits":"cumulative integer bit"}.get(name,name)+" limit exceeded")
    setup_budget=Budget(setup_forecast)
    # Precharge the fixed N9 physical-prefix/proposal scan, outside numeric rules.
    setup_budget.charge("fixed_n9_prefix_setup",10_000_000)
    setup_budget.entries(200_000,"fixed N9 setup scratch")
    setup_budget.created_bits += 100_000_000
    census = build_frozen_update_census(rule_budget=setup_budget)
    template = build_reference_template(_template_case(),rule_budget=setup_budget)
    ranges = scaled_proof9_ranges()
    normalizer = census["target_prior"]["normalizer_z"]
    if normalizer != Fraction(29, 64):
        raise ArithmeticError("scaled PROOF9 prior changed")
    if template.receipt["nodes"] != 388 or template.receipt["edges"] != 410:
        raise ArithmeticError("independent card-free template changed")
    if census["literal_history_census"]["logical_occurrences"] != 1105:
        raise ArithmeticError("independent literal history count changed")

    slots_per_world = sum(
        template.histories[node_id][0] * len(node.edges)
        for node_id, node in enumerate(template.nodes) if node.phase == "decision")
    visits_per_world = census["literal_history_census"]["logical_occurrences"]
    worlds = 60
    visits = worlds * visits_per_world
    action_slots = worlds * slots_per_world
    rank_calls = 2 * worlds
    rows = census["rows"]
    if (rows["physical_supported_rows"] != MAX_ROWS or
            rows["physical_supported_decision_action_slots"] != MAX_ACTION_SLOTS or
            rows["physical_supported_row_history_tokens"] != MAX_HISTORY_TOKENS or
            rows["physical_supported_row_history_bytes"] != MAX_HISTORY_BYTES):
        raise ArithmeticError("accepted physical row census changed")
    action_token_bytes = 0
    support_by_hand = census["support_counts_by_hand"]
    for node_id, node in enumerate(template.nodes):
        if node.phase != "decision":
            continue
        supported_hands = sum(support_by_hand[node.street][node.state.player])
        row_count = template.histories[node_id][0] * supported_hands
        menu_bytes = sum(len(edge.token.encode("ascii")) for edge in node.edges)
        action_token_bytes += row_count * menu_bytes
    output_text_bytes = rows["physical_supported_row_history_bytes"] + action_token_bytes

    # Every action slot performs at most twelve charged Fraction operations;
    # each literal node has at most sixteen scalar operations. Include profile
    # scans, world/rank visits, result cells, and the cache's one-time setup.
    fraction_ops_upper = 12 * action_slots + 16 * visits + 16 * MAX_ROWS
    runtime_work_upper = (fraction_ops_upper + 8 * visits + 8 * action_slots +
                          rank_calls * 4096 + 64 * MAX_HISTORY_TOKENS)
    retained_entries_upper = (16 * MAX_ROWS + 8 * MAX_ACTION_SLOTS +
                              4 * MAX_HISTORY_TOKENS + 8192)
    created_bits_upper = 4096 * fraction_ops_upper + 2_200 * rank_calls
    max_integer_bits_upper = 4096
    setup = template.receipt["rule_budget"]
    # Reserve the entire admitted setup, not just the last template build.
    setup_work = setup_forecast["work"]
    setup_entries = setup_forecast["entries"]
    setup_created = setup_forecast["created_bits"]

    # Admission happens before profile tables, row dictionaries, or result
    # vectors. The bound is a logical model, not Python RSS/allocator bytes.
    if setup_work + runtime_work_upper > ceilings["work"]:
        raise ValueError("expected-update certificate work limit exceeded")
    if setup_entries + retained_entries_upper > ceilings["entries"]:
        raise ValueError("expected-update certificate entry limit exceeded")
    if output_text_bytes > ceilings["output_text_bytes"]:
        raise ValueError("expected-update output text byte limit exceeded")
    if setup_created + created_bits_upper > ceilings["created_bits"]:
        raise ValueError("expected-update cumulative integer bit limit exceeded")
    if max_integer_bits_upper > ceilings["integer_bits"]:
        raise ValueError("expected-update integer bit limit exceeded")
    return ExpectedUpdateAdmission(
        MappingProxyType(ceilings), template, census, ranges, normalizer,
        worlds, visits, action_slots, MAX_HISTORY_TOKENS, MAX_HISTORY_BYTES,
        action_token_bytes, output_text_bytes, rank_calls, fraction_ops_upper,
        runtime_work_upper, retained_entries_upper, created_bits_upper,
        max_integer_bits_upper, setup_work, setup_entries, setup_created)


def _runout_stream(ranges):
    """Yield 60 exact compatible prior/board records without a world table."""
    for hand0, weight0 in ranges[0]:
        for hand1, weight1 in ranges[1]:
            if not set(hand0).isdisjoint(hand1):
                continue
            remaining = tuple(card for card in PROOF9 if card not in (*hand0, *hand1))
            for flop in combinations(remaining, 3):
                last = tuple(card for card in remaining if card not in flop)
                for turn, river in permutations(last, 2):
                    yield hand0, weight0, hand1, weight1, (*flop, turn, river)


def _reveal_token(board, next_length):
    if next_length == 3:
        flop = tuple(sorted(board[:3]))
        return "flop@" + "".join(card_name(card) for card in flop)
    if next_length == 4:
        return "turn@" + card_name(board[3])
    if next_length == 5:
        return "river@" + card_name(board[4])
    raise ArithmeticError("unexpected symbolic reveal length")


def compute_expected_update_reference(admission=None, limits=None):
    """Stream the exact joint-world CFR regret and average increments, with no q."""
    if admission is None:
        admission = prepare_expected_update_reference(limits)
    elif type(admission) is not ExpectedUpdateAdmission:
        raise ValueError("expected an admitted reference context")
    elif limits is not None:
        raise ValueError("limits belong to the preflight admission")

    budget_limits = {name: admission.limits[name] for name in DEFAULT_LIMITS}
    budget = Budget(budget_limits)
    # The four dynamic Budget counter families each retain two logical
    # metadata entries; those eight are already inside entries_upper.
    budget.entries(admission.entries_upper - 8,
                    "pre-admitted expected-update output")
    # All reachable action probabilities are 0 or 2^-e, e<=64. This immutable
    # power table avoids per-history probability construction and is charged
    # within the pre-admitted output/scratch model.
    powers = tuple(Fraction(1, 1 << exponent) for exponent in range(65))
    zero = Fraction(0)
    rows = {}
    rank_calls = world_count = node_visits = slot_visits = 0

    def walk(node_id, board, history, reaches, chance, rank_sign):
        nonlocal node_visits, slot_visits
        node = admission.template.nodes[node_id]
        node_visits += 1
        budget.charge("literal_full_history_node", 1)
        raw = node.state
        if node.phase in ("fold", "showdown"):
            matched = min(raw.state.committed)
            amount = budget.input(float(matched), "expected terminal matched contribution")
            if node.phase == "fold":
                return amount if raw.winner == 0 else budget.neg(amount, "global SB fold payoff")
            return budget.mul(amount, Fraction(rank_sign), "global SB showdown payoff")

        if node.phase == "reveal":
            edge = node.edges[0]
            token = _reveal_token(board, raw.board_length)
            return walk(edge.child, board, (*history, token), reaches, chance, rank_sign)

        actor = raw.player
        own_hand = board[5 + 2 * actor:7 + 2 * actor]
        # `board` is encoded as the physical five-card board followed by the
        # fixed input-order private hands; only the actor's two IDs enter rows.
        actions = tuple(edge.token for edge in node.edges)
        if any(action is None for action in actions):
            raise ArithmeticError("decision menu lost its action token")
        exponents = _profile_exponents(actor, own_hand, history, actions)
        key = (actor, own_hand, history)
        state = rows.get(key)
        if state is None:
            state = {
                "actions": actions,
                "exponents": exponents,
                "regrets": [zero] * len(actions),
                "average_mass": zero,
                "average_actions": [zero] * len(actions),
            }
            rows[key] = state
        elif state["actions"] != actions or state["exponents"] != exponents:
            raise ArithmeticError("same full-history row has inconsistent menu/profile")

        child_values = []
        for edge, exponent in zip(node.edges, exponents):
            child_reach = reaches[actor]
            if child_reach is not None:
                child_reach = None if exponent < 0 else child_reach + exponent
            updated = list(reaches)
            updated[actor] = child_reach
            slot_visits += 1
            budget.charge("literal_ordered_action_edge", 1)
            child_values.append(walk(edge.child, board, (*history, edge.token),
                                     tuple(updated), chance, rank_sign))

        mixed = zero
        for value, exponent in zip(child_values, exponents):
            if exponent >= 0:
                mixed = budget.add(mixed, budget.mul(powers[exponent], value,
                                                     "profile-weighted child value"),
                                   "ordered child-value accumulation")

        own_exp = reaches[actor]
        other_exp = reaches[1 - actor]
        own_reach = zero if own_exp is None else powers[own_exp]
        other_reach = zero if other_exp is None else powers[other_exp]
        average_increment = budget.mul(chance, own_reach, "joint chance times own reach")
        state["average_mass"] = budget.add(state["average_mass"], average_increment,
                                           "average reach-mass accumulation")
        counterfactual_mass = budget.mul(chance, other_reach,
                                         "joint chance times opponent reach")
        sign = 1 if actor == 0 else -1
        for index, (child_value, exponent) in enumerate(zip(child_values, exponents)):
            regret_delta = budget.sub(child_value, mixed, "action value minus node value")
            if sign < 0:
                regret_delta = budget.neg(regret_delta, "BB utility orientation")
            regret_delta = budget.mul(counterfactual_mass, regret_delta,
                                      "counterfactual regret increment")
            state["regrets"][index] = budget.add(state["regrets"][index], regret_delta,
                                                 "regret expectation accumulation")
            if exponent >= 0:
                average_delta = budget.mul(average_increment, powers[exponent],
                                           "profile-weighted average increment")
                state["average_actions"][index] = budget.add(
                    state["average_actions"][index], average_delta,
                    "average action-mass accumulation")
        return mixed

    for hand0, weight0, hand1, weight1, board in _runout_stream(admission.ranges):
        world_count += 1
        budget.charge("streamed_physical_world", 1)
        pair_mass = budget.div(budget.mul(weight0, weight1, "compatible private-pair prior"),
                               admission.normalizer, "global prior normalization")
        chance = budget.div(pair_mass, Fraction(20), "uniform ordered-board chance")
        rank0 = independent_rank(tuple(card_name(card) for card in (*hand0, *board)))
        rank1 = independent_rank(tuple(card_name(card) for card in (*hand1, *board)))
        rank_calls += 2
        rank_sign = (rank0 > rank1) - (rank0 < rank1)
        # The row/profile hand selector uses physical IDs, while the traversal
        # receives only the actual board plus both fixed private holdings.
        packed = (*board, *hand0, *hand1)
        value = walk(admission.template.root, packed, (), (0, 0), chance, rank_sign)
        if not isinstance(value, Fraction):
            raise ArithmeticError("world traversal did not return an exact value")

    if (world_count != admission.worlds or node_visits != admission.visits or
            slot_visits != admission.action_slots or rank_calls != admission.rank_calls):
        raise ArithmeticError("streamed expected-update work disagrees with pre-admission")
    if len(rows) != MAX_ROWS or sum(len(row["actions"]) for row in rows.values()) != MAX_ACTION_SLOTS:
        raise ArithmeticError("expected-update rows disagree with independent physical census")
    if budget.work > admission.work_upper or budget.logical_entries > admission.entries_upper:
        raise ArithmeticError(
            "actual expected-update receipt exceeded admitted logical bounds: "
            f"work={budget.work}/{admission.work_upper}, "
            f"entries={budget.logical_entries}/{admission.entries_upper}")
    if budget.created_bits > admission.created_bits_upper or budget.max_forecast_bits > admission.max_integer_bits_upper:
        raise ArithmeticError("actual Fraction receipt exceeded admitted bit bounds")

    frozen_rows = {}
    for key, state in rows.items():
        row = ExpectedUpdateRow(
            key[0], key[1], key[2], state["actions"], state["exponents"],
            tuple(state["regrets"]), state["average_mass"],
            tuple(state["average_actions"]))
        if sum(row.average_action_masses, zero) != row.average_reach_mass:
            raise ArithmeticError("average action increments do not sum to own-reach mass")
        weighted_regret = sum((Fraction(0) if exponent < 0 else
                               powers[exponent] * regret
                               for exponent, regret in zip(row.action_exponents,
                                                           row.regret_masses)), zero)
        if weighted_regret != 0:
            raise ArithmeticError("expected instantaneous regrets violate profile centering")
        frozen_rows[key] = row
    receipt = {
        "version": "q-free-joint-world-expected-update-v1",
        "worlds_streamed": world_count,
        "literal_node_visits": node_visits,
        "literal_action_edge_visits": slot_visits,
        "independent_rank_calls": rank_calls,
        "unique_full_history_rows": len(frozen_rows),
        "unique_action_slots": sum(len(row.actions) for row in frozen_rows.values()),
        "q_terms": 0,
        "sampling_or_training_calls": 0,
        "runtime_budget": budget.receipt(),
        "admission": admission.receipt(),
        "scope": "exact joint-world expected increments only; no sampled proposal estimator or training",
    }
    return ExpectedUpdateResult(admission, MappingProxyType(frozen_rows),
                                MappingProxyType(receipt))
