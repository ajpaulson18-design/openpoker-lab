"""Construct the selected four-street public DAG without a postflop source tree.

The direct builder shares public betting states while retaining complete
history-dependent occurrences in the bounded topology cursor. It deliberately
reuses only the bounded preflop skeleton; every postflop betting state is built
as a memoized immutable-vertex recurrence.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
import math

from .cards import DECK, cards
from .postflop_solver import _MAX_PUBLIC_NODES, _MAX_PUBLIC_STATES
from .preflop_solver import (
    PreflopContinuation,
    _MAX_SELECTED_RUNOUTS,
    _template_config,
)
from .preflop_tree import PreflopConfig, build_preflop_tree
from .river_tree import (
    _EPSILON,
    _Action,
    _Node,
    _Terminal,
    _clean,
    _opening_actions,
    _raise_actions,
)
from .river_config import RiverConfig
from .shared_public_topology import (
    ActionRecord,
    ChanceVertex,
    DecisionVertex,
    SharedPublicTopology,
    TerminalVertex,
    TopologyCensus,
    TopologyLimits,
    _action_key,
    _float_bits,
    _token_bytes,
    _vertex_degree,
)


_DECK_ORDER = {card: index for index, card in enumerate(DECK)}


def _action_record(action: _Action, *, matched=None) -> ActionRecord:
    target = action.raise_to
    if matched is not None and action.name not in {"check", "fold"} and target:
        target = _clean(matched + target)
    copied = _Action(action.name, action.amount, target, action.full_raise)
    return ActionRecord(copied.name, copied.amount, copied.raise_to,
                        copied.full_raise, copied.token)


def _config_key(config: RiverConfig) -> tuple:
    return (
        _float_bits(config.pot),
        tuple(_float_bits(value) for value in config.stacks),
        tuple(_float_bits(value) for value in config.bet_sizes),
        tuple(_float_bits(value) for value in config.raise_sizes),
        config.max_raises,
        config.include_all_in,
    )


def _iter_selected_records(selected_runouts):
    if isinstance(selected_runouts, (str, bytes)):
        raise ValueError("selected_runouts must be canonical (flop, turn, river) records.")
    try:
        iterator = iter(selected_runouts)
    except TypeError as exc:
        raise ValueError("selected_runouts must be a finite sequence of canonical records.") from exc
    count = 0
    for record in iterator:
        count += 1
        if count > _MAX_SELECTED_RUNOUTS:
            raise ValueError("selected_runouts must contain at most 300,000 canonical records.")
        if isinstance(record, (str, bytes)):
            raise ValueError("Each selected runout must be a (flop, turn, river) record.")
        try:
            if len(record) != 3:
                raise ValueError("Each selected runout must contain a flop, turn and river.")
            raw_flop, turn, river = record
            flop = cards(raw_flop, 3)
            cards((turn, river), 2)
            if tuple(sorted(flop, key=_DECK_ORDER.__getitem__)) != flop:
                raise ValueError("Selected flops must use canonical deck order.")
            cards(flop + (turn, river), 5)
        except (TypeError, KeyError) as exc:
            raise ValueError("Malformed canonical selected runout.") from exc
        yield (flop, turn, river)
    if count == 0:
        raise ValueError("selected_runouts must contain 1-300,000 canonical records.")


class _DirectBuilder:
    def __init__(self, limits):
        self.limits = limits
        self.vertices = []
        self.interned = {}
        self.betting_states = {}
        self.template_roots = []
        self.template_cache = {}
        self.context_ids = {}
        self.support_ids = {}
        self.support_shapes = []
        self.prefix_ids = {}
        self.summaries = []
        self._edge_count = 0
        self.source_nodes = 0
        self.source_continuations = 0
        self.source_edges = 0
        self.memoized_betting_edges = 0
        self.reserved_recurrence_transitions = 0
        self.scratch_peak = 0
        self.fixed_scratch_entries = 0
        self.active_betting = set()
        self.transient_entries = 0
        self.global_logical_states = 0
        self.global_logical_decisions = 0
        self.template_logical_states = 0
        self.template_logical_decisions = 0
        self.logical_template_peak_states = 0
        self.logical_template_peak_decisions = 0
        self.template_charges = []
        self.selected_input_records = 0
        self.support_shape_hash_entries = 0

    def _scratch(self, extra=0):
        # Charge retained tables, memo keys, summaries and active construction
        # frames together.  ``extra`` is reserved before the corresponding
        # append/insertion, not measured after it has happened.
        used = (len(self.vertices) + len(self.interned) + len(self.summaries) +
                len(self.betting_states) * 2 + len(self.template_cache) +
                len(self.context_ids) + len(self.support_ids) + len(self.prefix_ids) +
                len(self.support_shapes) +
                len(self.template_roots) + len(self.active_betting) * 2 +
                self.transient_entries + self.fixed_scratch_entries + extra)
        self.scratch_peak = max(self.scratch_peak, used)
        if used > self.limits.max_build_scratch_entries:
            raise ValueError("Direct public topology exceeds its build-scratch limit.")

    def _guard_summary(self, summary, *, template=False):
        if summary[0] > self.limits.max_logical_visits:
            raise ValueError("Direct topology exceeds its expanded logical-visit limit.")
        if summary[8] > self.limits.max_depth:
            raise ValueError("Direct topology exceeds its maximum-depth limit.")
        if summary[4] + summary[6] > self.limits.max_history_token_work:
            raise ValueError("Direct topology exceeds its logical history-token work limit.")
        if summary[5] + summary[7] > self.limits.max_history_token_bytes:
            raise ValueError("Direct topology exceeds its logical history-token byte limit.")
        if summary[1] > _MAX_PUBLIC_NODES:
            label = "Direct postflop template" if template else "Combined preflop/postflop tree"
            raise ValueError(f"{label} exceeds 10,000 logical decisions.")
        if summary[0] > _MAX_PUBLIC_STATES:
            label = "Direct postflop template" if template else "Combined preflop/postflop tree"
            raise ValueError(f"{label} exceeds 250,000 logical states.")

    def initialize_preflop_ledger(self, states, decisions):
        self.global_logical_states = states
        self.global_logical_decisions = decisions
        if (states > self.limits.max_logical_visits or
                states > _MAX_PUBLIC_STATES or decisions > _MAX_PUBLIC_NODES):
            raise ValueError("Preflop skeleton exceeds the global logical-tree limits.")

    def _reserve_logical(self, *, states=0, decisions=0, template=True):
        global_states = self.global_logical_states + states
        global_decisions = self.global_logical_decisions + decisions
        if global_states > self.limits.max_logical_visits:
            raise ValueError("Direct topology exceeds its expanded logical-visit limit.")
        if global_states > _MAX_PUBLIC_STATES:
            raise ValueError("Combined preflop/postflop tree exceeds 250,000 logical states.")
        if global_decisions > _MAX_PUBLIC_NODES:
            raise ValueError("Combined preflop/postflop tree exceeds 10,000 logical decisions.")
        if template:
            local_states = self.template_logical_states + states
            local_decisions = self.template_logical_decisions + decisions
            if local_states > _MAX_PUBLIC_STATES:
                raise ValueError("Direct postflop template exceeds 250,000 logical states.")
            if local_decisions > _MAX_PUBLIC_NODES:
                raise ValueError("Direct postflop template exceeds 10,000 logical decisions.")
            self.template_logical_states = local_states
            self.template_logical_decisions = local_decisions
            self.logical_template_peak_states = max(
                self.logical_template_peak_states, local_states)
            self.logical_template_peak_decisions = max(
                self.logical_template_peak_decisions, local_decisions)
        self.global_logical_states = global_states
        self.global_logical_decisions = global_decisions

    def register_support(self, support, support_by_turn):
        # The caller supplies the already canonical immutable shape; reuse it
        # as the lookup key rather than rebuilding and rehashing a copy.
        key = support
        existing = self.support_ids.get(key)
        if existing is not None:
            return existing
        if (len(self.support_ids) + len(self.prefix_ids) >=
                self.limits.max_support_prefixes):
            raise ValueError("Direct topology exceeds its distinct support-shape limit.")
        self._scratch(extra=2)
        support_id = len(self.support_shapes)
        self.support_ids[key] = support_id
        self.support_shapes.append((support, support_by_turn))
        self.support_shape_hash_entries += len(support) + sum(
            len(rivers) for _, rivers in support)
        return support_id

    def _summary_for(self, vertex, branches):
        if isinstance(vertex, DecisionVertex):
            summary = (1, 1, 0, 0, 0, 0, 0, 0, 0)
        elif isinstance(vertex, ChanceVertex):
            summary = (1, 0, 1, 0, 0, 0, 0, 0, 0)
        else:
            summary = (1, 0, 0, 1, 0, 0, 0, 0, 0)
        for token, child_id in branches:
            summary = self._extend_summary(summary, token, child_id)
        self._guard_summary(summary)
        return summary

    def _extend_summary(self, summary, token, child_id):
        child = self.summaries[child_id]
        token_size = _token_bytes(token)
        result = (
            summary[0] + child[0], summary[1] + child[1],
            summary[2] + child[2], summary[3] + child[3],
            summary[4] + child[4] + child[0],
            summary[5] + child[5] + child[0] * token_size,
            summary[6] + 1 + child[6], summary[7] + token_size + child[7],
            max(summary[8], 1 + child[8]),
        )
        self._guard_summary(result)
        return result

    def _intern(self, vertex, key):
        existing = self.interned.get(key)
        if existing is not None:
            return existing
        # Reserve the retained vertex/key/summary and the temporary summary
        # accumulator before creating those entries.
        self._scratch(extra=4)
        degree = _vertex_degree(vertex)
        if len(self.vertices) >= self.limits.max_vertices:
            raise ValueError("Direct public topology exceeds its unique-vertex limit.")
        if self.edge_count + degree > self.limits.max_edges:
            raise ValueError("Direct public topology exceeds its unique-edge limit.")
        if isinstance(vertex, DecisionVertex):
            summary = self._summary_for(
                vertex, ((action.token, child) for action, child in
                         zip(vertex.actions, vertex.child_ids)))
        elif isinstance(vertex, ChanceVertex):
            summary = self._summary_for(
                vertex, ((f"{vertex.street}@{token}", child)
                         for token, child in vertex.branches))
        else:
            summary = self._summary_for(vertex, ())
        vertex_id = len(self.vertices)
        self.vertices.append(vertex)
        self.interned[key] = vertex_id
        self.summaries.append(summary)
        self.edge_count += degree
        return vertex_id

    def _table_id(self, table, key, name):
        existing = table.get(key)
        if existing is not None:
            return existing
        if (table is not self.context_ids and
                len(self.support_ids) + len(self.prefix_ids) >= self.limits.max_support_prefixes):
            raise ValueError("Direct topology exceeds its distinct context/support-prefix limit.")
        self._scratch(extra=1)
        value = len(table)
        table[key] = value
        return value

    def _reserve_fixed(self, amount):
        if amount < 0:
            raise ValueError("Fixed scratch reservation must be nonnegative.")
        self._scratch(extra=amount)
        self.fixed_scratch_entries += amount

    def _release_fixed(self, amount):
        self.fixed_scratch_entries -= amount
        if self.fixed_scratch_entries < 0:
            raise AssertionError("Unbalanced direct-builder fixed reservation.")

    def _reserve_transition(self):
        if self.reserved_recurrence_transitions >= self.limits.max_edges:
            raise ValueError("Direct topology exceeds its recurrence-transition limit.")
        self._scratch(extra=1)
        self.reserved_recurrence_transitions += 1
        self.memoized_betting_edges = self.reserved_recurrence_transitions

    def _reserve_transient(self, amount):
        if amount < 0:
            raise ValueError("Transient reservation must be nonnegative.")
        self._scratch(extra=amount)
        self.transient_entries += amount

    def _release_transient(self, amount):
        self.transient_entries -= amount
        if self.transient_entries < 0:
            raise AssertionError("Unbalanced direct-builder scratch reservation.")

    @property
    def edge_count(self):
        return getattr(self, "_edge_count", 0)

    @edge_count.setter
    def edge_count(self, value):
        self._edge_count = value

    def terminal(self, kind, contributions, winner=None):
        self._scratch(extra=2)
        contributions = tuple(float(value) for value in contributions)
        if (kind not in ("fold", "showdown") or len(contributions) != 2 or
                any(not math.isfinite(value) or value < 0 for value in contributions) or
                (kind == "fold" and winner not in (0, 1)) or
                (kind == "showdown" and winner is not None)):
            raise ValueError("Malformed direct terminal vertex.")
        vertex = TerminalVertex(kind, contributions, winner)
        key = ("terminal", kind, tuple(_float_bits(v) for v in contributions), winner)
        return self._intern(vertex, key)

    def chance(self, street, card_index, branches):
        try:
            branch_count = len(branches)
        except TypeError:
            branch_count = 1
        self._scratch(extra=branch_count + 1)
        branches = tuple(branches)
        if (street not in ("flop", "turn", "river") or type(card_index) is not int or
                card_index < 0 or not branches or any(
                    type(token) is not str or not token or type(child) is not int
                    for token, child in branches)):
            raise ValueError("Malformed direct chance vertex.")
        vertex = ChanceVertex(street, card_index, branches)
        key = ("chance", street, card_index, branches)
        return self._intern(vertex, key)

    def decision(self, player, actions, children):
        self._scratch(extra=1)
        actions, children = tuple(actions), tuple(children)
        if (type(player) is not int or player not in (0, 1) or not actions or
                len(actions) != len(children)):
            raise ValueError("Malformed direct decision vertex.")
        vertex = DecisionVertex(player, actions, children)
        key = ("decision", player, tuple(_action_key(action) for action in actions), children)
        return self._intern(vertex, key)

    def _source_to_vertex(self, root, continue_at, max_depth):
        memo = {}
        active = set()
        stack = [(root, False, 0)]
        try:
          while stack:
            node, exiting, depth = stack.pop()
            self.transient_entries = len(memo) + len(active) + len(stack)
            if depth > max_depth:
                raise ValueError("Direct topology exceeds its maximum depth.")
            source_id = id(node)
            if exiting:
                active.remove(source_id)
                if isinstance(node, PreflopContinuation):
                    vertex_id = continue_at(node)
                elif isinstance(node, _Terminal):
                    vertex_id = self.terminal(node.kind, node.contributions, node.winner)
                elif isinstance(node, _Node):
                    self._reserve_transient(3 * len(node.children))
                    child_ids = []
                    # Guard the logical prefix after each child occurrence,
                    # before proceeding to the next sibling.
                    partial = (1, 1, 0, 0, 0, 0, 0, 0, 0)
                    for action, child in zip(node.actions, node.children):
                        child_id = memo[id(child)]
                        child_ids.append(child_id)
                        child = self.summaries[child_id]
                        token_size = _token_bytes(action.token)
                        partial = (
                            partial[0] + child[0], partial[1] + child[1],
                            partial[2] + child[2], partial[3] + child[3],
                            partial[4] + child[4] + child[0],
                            partial[5] + child[5] + child[0] * token_size,
                            partial[6] + 1 + child[6],
                            partial[7] + token_size + child[7],
                            max(partial[8], 1 + child[8]),
                        )
                        self._guard_summary(partial)
                    children = tuple(child_ids)
                    actions = tuple(_action_record(action) for action in node.actions)
                    vertex_id = self.decision(node.player, actions, children)
                    self._release_transient(3 * len(node.children))
                else:
                    raise TypeError("Unexpected preflop skeleton node.")
                self.transient_entries = len(memo) + len(active) + len(stack)
                self._scratch(extra=1)
                memo[source_id] = vertex_id
                continue
            if source_id in memo:
                continue
            if source_id in active:
                raise ValueError("Preflop skeleton contains a cycle.")
            active.add(source_id)
            children = node.children if isinstance(node, _Node) else ()
            self.transient_entries = len(memo) + len(active) + len(stack) + 1 + len(children)
            self._scratch()
            stack.append((node, True, depth))
            if isinstance(node, _Node):
                self.source_nodes += 1
                self.source_edges += len(node.children)
                for child in reversed(node.children):
                    stack.append((child, False, depth + 1))
            elif isinstance(node, _Terminal):
                self.source_nodes += 1
            elif isinstance(node, PreflopContinuation):
                self.source_nodes += 1
                self.source_continuations += 1
            else:
                raise TypeError("Unexpected preflop skeleton node.")
            if self.source_nodes > self.limits.max_source_nodes:
                raise ValueError("Direct topology exceeds its preflop source-node limit.")
            if self.source_edges > self.limits.max_source_edges:
                raise ValueError("Direct topology exceeds its preflop source-edge limit.")
          result = memo[id(root)]
          memo.clear()
          active.clear()
          return result
        finally:
            self.transient_entries = 0

    def build_template(self, configs, support_id, flop, translation_offset):
        translation_offset = float(translation_offset)
        config_key = tuple((name, _config_key(configs[name]))
                           for name in ("flop", "turn", "river"))
        context_id = self._table_id(
            self.context_ids, (config_key, _float_bits(translation_offset)), "context")
        prefix_id = self._table_id(self.prefix_ids, (flop,), "prefix")
        template_key = (context_id, prefix_id, support_id)
        self.template_logical_states = 0
        self.template_logical_decisions = 0
        existing = self.template_cache.get(template_key)
        if existing is not None:
            summary = self.summaries[existing]
            self._reserve_logical(states=summary[0], decisions=summary[1])
            self.template_charges.append((existing, self.template_logical_states,
                                          self.template_logical_decisions))
            self._scratch(extra=1)
            self.template_roots.append(existing)
            self._scratch()
            return existing
        if len(self.template_cache) >= self.limits.max_support_prefixes:
            raise ValueError("Direct topology exceeds its distinct postflop template limit.")

        support, support_by_turn = self.support_shapes[support_id]

        def translate_terminal(kind, local_contributions, winner=None):
            self._reserve_logical(states=1)
            oop, ip = local_contributions
            global_contributions = (_clean(translation_offset + ip),
                                    _clean(translation_offset + oop))
            global_winner = None if winner is None else 1 - winner
            return self.terminal(kind, global_contributions, global_winner)

        def is_all_in(contributions, config):
            matched = min(contributions)
            return any(matched >= stack - _EPSILON for stack in config.stacks)

        def river_chance(local_contributions, turn, board_prefix):
            matched = min(local_contributions)
            carried = (matched, matched)
            rivers = support_by_turn[turn]
            self._reserve_logical(states=1)
            self._reserve_transient(len(rivers))
            branches = []
            partial = (1, 0, 1, 0, 0, 0, 0, 0, 0)
            try:
                for river in rivers:
                    if is_all_in(carried, configs["river"]):
                        child = translate_terminal("showdown", carried)
                    else:
                        self._reserve_transition()
                        child = start_fresh_stage(
                            "river", board_prefix + (river,), carried,
                            translation_offset, configs, support, turn,
                        )
                    branches.append((river, child))
                    partial = self._extend_summary(
                        partial, f"river@{river}", child)
                return self.chance("river", 6, branches)
            finally:
                self._release_transient(len(rivers))

        def turn_chance(local_contributions, board_prefix):
            self._reserve_logical(states=1)
            self._reserve_transient(len(support))
            branches = []
            partial = (1, 0, 1, 0, 0, 0, 0, 0, 0)
            try:
                for turn, _rivers in support:
                    carried_value = min(local_contributions)
                    carried = (carried_value, carried_value)
                    if is_all_in(carried, configs["turn"]):
                        child = river_chance(carried, turn, board_prefix + (turn,))
                    else:
                        self._reserve_transition()
                        child = start_fresh_stage(
                            "turn", board_prefix + (turn,), carried,
                            translation_offset, configs, support, turn,
                        )
                    branches.append((turn, child))
                    partial = self._extend_summary(
                        partial, f"turn@{turn}", child)
                return self.chance("turn", 5, branches)
            finally:
                self._release_transient(len(support))

        def settled(stage, local_contributions, board_prefix, turn):
            if stage == "flop":
                return turn_chance(local_contributions, board_prefix)
            if stage == "turn":
                return river_chance(local_contributions, turn, board_prefix)
            return translate_terminal("showdown", local_contributions)

        def build_betting(stage, board_prefix, contributions,
                          matched, stage_configs, full_support, turn,
                          player, previous_full_raise, raises_made,
                          raise_reopened, checks, depth):
            if depth > self.limits.max_depth:
                raise ValueError("Direct topology exceeds its maximum depth.")
            config = stage_configs[stage]
            contributions = tuple(contributions)
            local_prefix_id = self._table_id(self.prefix_ids, tuple(board_prefix), "prefix")
            self._scratch(extra=1)  # fixed-size memo key before construction
            key = (
                stage, local_prefix_id, context_id, support_id,
                _float_bits(matched), tuple(_float_bits(v) for v in contributions),
                player, _float_bits(previous_full_raise), raises_made,
                raise_reopened, checks,
            )
            cached = self.betting_states.get(key)
            if cached is not None:
                summary = self.summaries[cached]
                self._reserve_logical(states=summary[0], decisions=summary[1])
                return cached
            if key in self.active_betting:
                raise ValueError("Direct betting-state recurrence contains a cycle.")
            self._scratch(extra=2)  # memo key plus active recurrence frame
            self.active_betting.add(key)
            local_entries = 0
            try:
                if contributions[player] >= config.stacks[player] - _EPSILON:
                    result = settled(stage, contributions, board_prefix, turn)
                else:
                    opponent = 1 - player
                    self._reserve_logical(states=1, decisions=1)
                    committed, other = contributions[player], contributions[opponent]
                    actions = []
                    children = []
                    partial = (1, 1, 0, 0, 0, 0, 0, 0, 0)
                    if abs(committed - other) <= _EPSILON:
                        check = _Action("check")
                        self._reserve_transient(2)
                        local_entries += 2
                        actions.append(_action_record(check, matched=matched))
                        if checks == 1:
                            child = settled(stage, contributions, board_prefix, turn)
                        else:
                            self._reserve_transition()
                            child = build_betting(
                                stage, board_prefix, contributions,
                                matched, stage_configs, full_support, turn,
                                opponent, previous_full_raise, raises_made,
                                raise_reopened, checks + 1, depth + 1,
                            )
                        children.append(child)
                        partial = self._extend_summary(partial, actions[-1].token, child)
                        for action in _opening_actions(
                                config, committed, config.pot + sum(contributions), player):
                            updated = list(contributions)
                            updated[player] = action.raise_to
                            self._reserve_transient(2)
                            local_entries += 2
                            actions.append(_action_record(action, matched=matched))
                            self._reserve_transition()
                            children.append(build_betting(
                                stage, board_prefix, tuple(updated),
                                matched, stage_configs, full_support, turn,
                                opponent, action.amount, 0, True, 0, depth + 1,
                            ))
                            partial = self._extend_summary(
                                partial, actions[-1].token, children[-1])
                    else:
                        call_amount = other - committed
                        actual_call = min(call_amount, config.stacks[player] - committed)
                        call_contributions = list(contributions)
                        call_contributions[player] = committed + actual_call
                        self._reserve_transient(4)
                        local_entries += 4
                        actions.extend((_action_record(_Action("fold"), matched=matched),
                                       _action_record(_Action(
                                           "call", _clean(actual_call),
                                           call_contributions[player]), matched=matched)))
                        children.extend((
                            translate_terminal("fold", contributions, opponent),
                            settled(stage, tuple(call_contributions), board_prefix, turn),
                        ))
                        partial = self._extend_summary(partial, actions[0].token, children[0])
                        partial = self._extend_summary(partial, actions[1].token, children[1])
                        if (raise_reopened and raises_made < config.max_raises and
                                other < config.stacks[opponent] - _EPSILON):
                            for action in _raise_actions(
                                    config, contributions, player,
                                    previous_full_raise, raises_made):
                                updated = list(contributions)
                                updated[player] = action.raise_to
                                actions.append(_action_record(action, matched=matched))
                                increment = action.raise_to - other
                                full_raise = increment + _EPSILON >= previous_full_raise
                                next_full_raise = increment if full_raise else previous_full_raise
                                self._reserve_transient(2)
                                local_entries += 2
                                self._reserve_transition()
                                children.append(build_betting(
                                    stage, board_prefix, tuple(updated),
                                    matched, stage_configs, full_support, turn,
                                    opponent, next_full_raise, raises_made + 1,
                                    full_raise, 0, depth + 1,
                                ))
                                partial = self._extend_summary(
                                    partial, actions[-1].token, children[-1])
                    result = self.decision(1 - player, tuple(actions), tuple(children))
                    self._release_transient(local_entries)
                    local_entries = 0
                self._scratch(extra=2)  # completed memo entry and key
                self.betting_states[key] = result
                return result
            finally:
                if local_entries:
                    self._release_transient(local_entries)
                self.active_betting.remove(key)

        def start_fresh_stage(stage, board_prefix, contributions,
                              matched, stage_configs, full_support, turn):
            # river_tree._build_tree cleans only at each fresh-street entry.
            cleaned = tuple(_clean(value) for value in contributions)
            return build_betting(
                stage, board_prefix, cleaned, matched,
                stage_configs, full_support, turn, 0, 0.0, 0, True, 0, 0,
            )

        self._scratch(extra=1)
        # A template continuation is already represented by its preflop
        # placeholder.  This chance is the replacement node, so charge it
        # only if the skeleton placeholder was not counted (it was).
        root = start_fresh_stage(
            "flop", (flop,), (0.0, 0.0),
            translation_offset, configs, support, None,
        )
        self._guard_summary(self.summaries[root], template=True)
        if (self.template_logical_states != self.summaries[root][0] or
                self.template_logical_decisions != self.summaries[root][1]):
            raise AssertionError("Template logical reservations disagree with its subtree summary.")
        self.template_charges.append((root, self.template_logical_states,
                                      self.template_logical_decisions))
        self._scratch(extra=2)
        self.template_cache[template_key] = root
        self.template_roots.append(root)
        self._scratch()
        return root

    def finish(self, root_id, initial_history=()):
        if not 0 <= root_id < len(self.summaries):
            raise ValueError("Direct topology root is not a completed DAG vertex.")
        summary = self.summaries[root_id]
        self._guard_summary(summary)
        if (self.global_logical_states != summary[0] or
                self.global_logical_decisions != summary[1]):
            raise AssertionError("Global logical reservations disagree with the root subtree summary.")
        for template_root, states, decisions in self.template_charges:
            template_summary = self.summaries[template_root]
            if (states != template_summary[0] or decisions != template_summary[1]):
                raise AssertionError("Template logical reservations disagree with its subtree summary.")
        logical_history_work = summary[4] + summary[6]
        logical_history_bytes = summary[5] + summary[7]
        max_template_states = self.logical_template_peak_states
        max_template_decisions = self.logical_template_peak_decisions

        prefix = tuple(initial_history)
        history_work = len(prefix) * summary[0] + summary[4] + summary[6]
        history_bytes = (sum(_token_bytes(token) for token in prefix) * summary[0] +
                         summary[5] + summary[7])
        if history_work > self.limits.max_history_token_work:
            raise ValueError("Direct topology exceeds its logical history-token work limit.")
        if history_bytes > self.limits.max_history_token_bytes:
            raise ValueError("Direct topology exceeds its logical history-token byte limit.")
        census = TopologyCensus(
            self.source_nodes, self.source_edges,
            len(self.vertices), self.edge_count,
            summary[0], summary[1], summary[2], summary[3],
            history_work, history_bytes, summary[8], self.scratch_peak,
            None, None, (),
        )
        topology = SharedPublicTopology(tuple(self.vertices), root_id, prefix,
                                        census, self.limits)
        receipt = {
            "version": "direct-selected-public-topology-construction-v1",
            "limits": asdict(self.limits),
            "original_logical_caps": {
                "template_states": _MAX_PUBLIC_STATES,
                "template_decisions": _MAX_PUBLIC_NODES,
                "combined_states": _MAX_PUBLIC_STATES,
                "combined_decisions": _MAX_PUBLIC_NODES,
            },
            "recurrence_transition_limit": self.limits.max_edges,
            "build_scratch_peak_entries": self.scratch_peak,
            "resource_scope": (
                "Entry-count admission and logical-work limits; not allocator bytes, "
                "RSS, or a CPU-time bound."),
            "materialized_preflop_source_states": self.source_nodes,
            "materialized_preflop_source_continuations": self.source_continuations,
            "materialized_preflop_source_edges": self.source_edges,
            "materialized_postflop_nodes": 0,
            "compiler_snapshots": 0,
            "memoized_betting_states": len(self.betting_states),
            "memoized_betting_edges": self.memoized_betting_edges,
            "reserved_recurrence_transitions": self.reserved_recurrence_transitions,
            "canonical_context_ids": len(self.context_ids),
            "canonical_support_shape_ids": len(self.support_ids),
            "canonical_prefix_ids": len(self.prefix_ids),
            "completed_subtree_summaries": len(self.summaries),
            "unique_dag_vertices": len(self.vertices),
            "unique_dag_edges": self.edge_count,
            "logical_template_peak_states": max_template_states,
            "logical_template_peak_decisions": max_template_decisions,
            "logical_template_count": len(self.template_roots),
            "reserved_global_logical_states": self.global_logical_states,
            "reserved_global_logical_decisions": self.global_logical_decisions,
            "selected_input_records": self.selected_input_records,
            "support_shape_hash_entries": self.support_shape_hash_entries,
            "expanded_logical_visits": summary[0],
            "decision_occurrences": summary[1],
            "chance_occurrences": summary[2],
            "terminal_occurrences": summary[3],
            "maximum_depth": summary[8],
            "logical_history_token_work": history_work,
            "logical_history_token_bytes": history_bytes,
        }
        return topology, receipt


def build_direct_shared_topology(preflop_config, specs, selected_runouts, *,
                                 limits=TopologyLimits()):
    """Return an interned direct topology and truthful construction receipt.

    ``selected_runouts`` must be the globally reachable canonical records from
    ``SelectedRunoutOperator.reachable_selected()``. Records remain ordered for
    first-seen flop branches; turn and river branches preserve the literal
    builder's lexical card ordering.
    """
    if not isinstance(limits, TopologyLimits):
        raise TypeError("limits must be a TopologyLimits instance.")
    if not isinstance(preflop_config, PreflopConfig):
        raise TypeError("preflop_config must be a PreflopConfig instance.")
    if not isinstance(specs, Mapping) or set(specs) != {"flop", "turn", "river"}:
        raise ValueError("specs must contain exactly flop, turn and river stage specs.")
    for stage in ("flop", "turn", "river"):
        spec = specs[stage]
        if not callable(getattr(spec, "action_dict", None)):
            raise TypeError("Each postflop spec must be a normalized stage spec.")
        RiverConfig(pot=1, effective_stack=(1, 1), **spec.action_dict())
    builder = _DirectBuilder(limits)
    builder._reserve_fixed(4)  # grouping list/maps and duplicate-check table
    flop_order = []
    by_flop = {}
    grouped_entries = 0
    support_prefix_count = 0
    selected_seen = set()
    selected_reserved = 0
    iterator = iter(_iter_selected_records(selected_runouts))
    while True:
        # One normalized record/card tuple is the only parser scratch outside
        # retained grouping structures; reserve it before asking the iterator.
        builder._reserve_transient(3)
        try:
            item = next(iterator)
        except StopIteration:
            builder._release_transient(3)
            break
        try:
            flop, turn, river = item
            if item in selected_seen:
                raise ValueError("Duplicate canonical selected runout.")
            builder._reserve_fixed(3)  # retained duplicate-check key
            selected_reserved += 3
            selected_seen.add(item)
            builder.selected_input_records += 1
            flop_key = "".join(flop)
            if flop_key not in by_flop:
                if support_prefix_count >= limits.max_support_prefixes:
                    raise ValueError("Direct topology exceeds its distinct support-prefix limit.")
                builder._reserve_fixed(2)  # flop mapping entry and ordered-flop entry
                grouped_entries += 2
                support_prefix_count += 1
                flop_order.append(flop_key)
                by_flop[flop_key] = {}
            turns = by_flop[flop_key]
            if turn not in turns:
                if support_prefix_count >= limits.max_support_prefixes:
                    raise ValueError("Direct topology exceeds its distinct support-prefix limit.")
                builder._reserve_fixed(1)  # turn-to-rivers mapping entry
                grouped_entries += 1
                support_prefix_count += 1
                turns[turn] = set()
            if river not in turns[turn]:
                builder._reserve_fixed(1)  # unique river-support entry
                grouped_entries += 1
                turns[turn].add(river)
        finally:
            builder._release_transient(3)
    selected_seen.clear()
    builder._release_fixed(selected_reserved)
    builder._reserve_fixed(1)
    support_by_flop = {}
    for flop, turns in by_flop.items():
        river_count = sum(len(rivers) for rivers in turns.values())
        canonical_entries = 2 + len(turns) + river_count
        sort_scratch = len(turns) + max(
            (len(rivers) for rivers in turns.values()), default=0)
        # Reserve canonical tuples/maps and peak sorting scratch before copies.
        builder._reserve_fixed(canonical_entries)
        builder._reserve_transient(sort_scratch)
        support = tuple((turn, tuple(sorted(rivers)))
                        for turn, rivers in sorted(turns.items()))
        support_by_turn = dict(support)
        support_id = builder.register_support(support, support_by_turn)
        builder._reserve_fixed(1)
        support_by_flop[flop] = support_id
        builder._release_transient(sort_scratch)
    builder._release_fixed(grouped_entries - len(flop_order))
    by_flop = None
    preflop = build_preflop_tree(preflop_config)
    if preflop.public_state_count > limits.max_source_nodes:
        raise ValueError("Direct topology exceeds its preflop source-node limit.")
    if preflop.public_state_count > limits.max_logical_visits:
        raise ValueError("Preflop skeleton exceeds the global logical-visit limit.")
    builder.initialize_preflop_ledger(
        preflop.public_state_count, preflop.decision_node_count)

    def continuation(boundary):
        if boundary.street == "showdown":
            matched = boundary.matched_contributions[0]
            return builder.terminal("showdown", (matched, matched))
        if boundary.street != "flop":
            raise ValueError("Unexpected preflop continuation street.")
        configs = _template_config(specs, boundary)
        translation = boundary.matched_contributions[0]
        builder._reserve_transient(len(flop_order))
        branches = []
        try:
            for flop in flop_order:
                support_id = support_by_flop[flop]
                child = builder.build_template(configs, support_id, flop, translation)
                branches.append((flop, child))
            return builder.chance("flop", 4, branches)
        finally:
            builder._release_transient(len(flop_order))

    try:
        root_id = builder._source_to_vertex(
            preflop.root, continuation, limits.max_depth)
        if builder.source_edges > limits.max_source_edges:
            raise ValueError("Direct topology exceeds its preflop source-edge limit.")
        return builder.finish(root_id)
    finally:
        preflop = None
        builder.template_cache.clear()
        builder.betting_states.clear()
        builder.template_roots.clear()
