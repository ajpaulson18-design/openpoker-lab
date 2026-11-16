"""Independent exact one-board regret and prefix-average estimator reference.

This bounded PROOF9 helper is deliberately separate from the native router and
arena. It shares only an immutable card-free betting-template snapshot and an
independent exact physical-prefix index. Regret uses compatible private pairs
for the sampled complete board; averaging uses the target mass of each visible
prefix and is never filtered by the board's hidden future cards.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from types import MappingProxyType

from scripts.matrix_free_certificate_budget import Budget, DEFAULT_LIMITS
from scripts.preflop_validation import independent_rank
from tests.full_deck_public_chance_reference import PROOF9, card_name
from tests.virtual_betting_template_reference import (
    build_reference_template, literal_reference_census,
)
from tests.virtual_frozen_update_reference import (
    _template_case, build_physical_prefix_index, scaled_proof9_ranges,
)
from tests.virtual_frozen_value_reference import _profile_exponents


PREFIX_LENGTHS = (0, 3, 4, 5)
MAX_PER_BOARD_ROWS = 868
MAX_PER_BOARD_ACTION_SLOTS = 2078
MAX_OUTPUT_TEXT_BYTES = 8_388_608
MAX_CONTEXT_ENTRIES = 200_000
MAX_CONTEXT_WORK = 150_000_000
MAX_CONTEXT_CREATED_BITS = 1_000_000_000
MAX_CONTEXT_INTEGER_BITS = 4096
MAX_WORLD_PAIRS = 3
MAX_PREFIX_RUNS = 16


@dataclass(frozen=True)
class TemplateEdge:
    kind: str
    token: str | None
    child: int


@dataclass(frozen=True)
class TemplateNode:
    phase: str
    street: int
    actor: int | None
    reveal_length: int
    winner: int | None
    matched: float
    edges: tuple[TemplateEdge, ...]
    path_count: int
    history_tokens: int
    history_bytes: int


@dataclass(frozen=True)
class SampledReferenceContext:
    nodes: tuple[TemplateNode, ...]
    root: int
    ranges: tuple
    normalizer: Fraction
    physical: object
    profile_version: str
    prefix_walk_stats: object
    decision_slots_per_world: int
    decision_nodes_per_world: int
    all_edges_per_world: int
    profile_token_scan_per_world: int
    setup_receipt: object
    _seal: object

    def receipt(self):
        return {
            "version": "n9-sampled-board-reference-context-v1",
            "template_nodes": len(self.nodes),
            "template_edges": sum(len(node.edges) for node in self.nodes),
            "normalizer_z": self.normalizer,
            "physical_prefix_count": sum(len(rows) for rows in self.physical.prefixes.values()),
            "physical_proposal_count": len(self.physical.proposals),
            "profile_version": self.profile_version,
            "prefix_walk_stats": dict(self.prefix_walk_stats),
            "setup_admission": dict(self.setup_receipt),
            "scope": "one reusable immutable PROOF9 reference context; no native objects or sampled results cached",
        }


@dataclass(frozen=True)
class SampledBoardAdmission:
    context: SampledReferenceContext
    board: tuple[int, int, int, int, int]
    proposal_law: str
    board_probability: Fraction
    prefix_probabilities: object
    compatible_pairs: tuple
    average_runs: tuple
    row_count_upper: int
    action_slots_upper: int
    history_tokens_upper: int
    history_bytes_upper: int
    action_token_bytes_upper: int
    output_text_bytes_upper: int
    regret_visits_upper: int
    regret_edges_upper: int
    average_visits_upper: int
    average_edges_upper: int
    rank_calls_upper: int
    fraction_operations_upper: int
    work_upper: int
    entries_upper: int
    created_bits_upper: int
    max_integer_bits_upper: int
    limits: object
    _seal: object
    prefix_fold_admitted: bool = False
    prefix_fold_node_visits_upper: int = 0
    prefix_fold_action_edges_upper: int = 0
    prefix_fold_terminal_queries_upper: int = 0
    prefix_fold_opponent_pair_scans_upper: int = 0
    prefix_fold_scalar_operations_upper: int = 0
    prefix_fold_frame_entries_upper: int = 0
    prefix_fold_return_vector_entries_upper: int = 0
    prefix_fold_reach_copy_entries_upper: int = 0
    prefix_fold_policy_entries_upper: int = 0
    prefix_fold_history_token_entries_upper: int = 0
    prefix_fold_pair_temporary_entries_upper: int = 0
    prefix_fold_counter_metadata_entries_upper: int = 0
    prefix_fold_work_upper: int = 0
    prefix_fold_entries_upper: int = 0
    prefix_fold_created_bits_upper: int = 0
    prefix_fold_max_integer_bits_upper: int = 0

    def receipt(self):
        return {
            "version": "n9-sampled-board-admission-v1",
            "board": self.board,
            "proposal_law": self.proposal_law,
            "q_board": self.board_probability,
            "q_prefix": dict(self.prefix_probabilities),
            "compatible_pair_worlds": len(self.compatible_pairs),
            "average_prefix_runs": len(self.average_runs),
            "row_count_upper": self.row_count_upper,
            "action_slots_upper": self.action_slots_upper,
            "history_tokens_upper": self.history_tokens_upper,
            "history_bytes_upper": self.history_bytes_upper,
            "action_token_bytes_upper": self.action_token_bytes_upper,
            "output_text_bytes_upper": self.output_text_bytes_upper,
            "regret_node_visits_upper": self.regret_visits_upper,
            "regret_action_edge_visits_upper": self.regret_edges_upper,
            "average_node_visits_upper": self.average_visits_upper,
            "average_action_edge_visits_upper": self.average_edges_upper,
            "rank_calls_upper": self.rank_calls_upper,
            "fraction_operations_upper": self.fraction_operations_upper,
            "work_upper": self.work_upper,
            "entries_upper": self.entries_upper,
            "created_bits_upper": self.created_bits_upper,
            "max_integer_bits_upper": self.max_integer_bits_upper,
            "prefix_fold_admitted": self.prefix_fold_admitted,
            "prefix_fold_node_visits_upper": self.prefix_fold_node_visits_upper,
            "prefix_fold_action_edges_upper": self.prefix_fold_action_edges_upper,
            "prefix_fold_terminal_queries_upper": self.prefix_fold_terminal_queries_upper,
            "prefix_fold_opponent_pair_scans_upper": self.prefix_fold_opponent_pair_scans_upper,
            "prefix_fold_scalar_operations_upper": self.prefix_fold_scalar_operations_upper,
            "prefix_fold_frame_entries_upper": self.prefix_fold_frame_entries_upper,
            "prefix_fold_return_vector_entries_upper": self.prefix_fold_return_vector_entries_upper,
            "prefix_fold_reach_copy_entries_upper": self.prefix_fold_reach_copy_entries_upper,
            "prefix_fold_policy_entries_upper": self.prefix_fold_policy_entries_upper,
            "prefix_fold_history_token_entries_upper": self.prefix_fold_history_token_entries_upper,
            "prefix_fold_pair_temporary_entries_upper": self.prefix_fold_pair_temporary_entries_upper,
            "prefix_fold_counter_metadata_entries_upper": self.prefix_fold_counter_metadata_entries_upper,
            "prefix_fold_work_upper": self.prefix_fold_work_upper,
            "prefix_fold_entries_upper": self.prefix_fold_entries_upper,
            "prefix_fold_created_bits_upper": self.prefix_fold_created_bits_upper,
            "prefix_fold_max_integer_bits_upper": self.prefix_fold_max_integer_bits_upper,
            "combined_work_upper": self.work_upper + self.prefix_fold_work_upper,
            "combined_entries_upper": self.entries_upper + self.prefix_fold_entries_upper,
            "combined_created_bits_upper": self.created_bits_upper + self.prefix_fold_created_bits_upper,
            "combined_max_integer_bits_upper": max(self.max_integer_bits_upper,
                self.prefix_fold_max_integer_bits_upper),
            "limits": dict(self.limits),
            "context_setup_is_counted_once": True,
            "scope": "one sampled board call; not an aggregate 5,040-call study admission",
        }


@dataclass(frozen=True)
class SampledUpdateRow:
    actor: int
    hand_ids: tuple[int, int]
    history: tuple[str, ...]
    actions: tuple[str, ...]
    action_exponents: tuple[int, ...]
    regret_masses: tuple[Fraction, ...]
    average_mass: Fraction
    average_action_masses: tuple[Fraction, ...]
    regret_world_visits: int
    average_prefix_visits: int
    prefix_fold_regret_masses: tuple[Fraction, ...] = ()

    @property
    def key(self):
        return self.actor, self.hand_ids, self.history


@dataclass(frozen=True)
class SampledUpdateResult:
    admission: SampledBoardAdmission
    rows: object
    receipt: object


@dataclass
class _MutableRow:
    actions: tuple[str, ...]
    exponents: tuple[int, ...]
    regrets: list[Fraction]
    average_mass: Fraction
    average_actions: list[Fraction]
    prefix_fold_regrets: list[Fraction]
    regret_world_visits: int = 0
    average_prefix_visits: int = 0


def _limits_snapshot(limits):
    allowed = {*DEFAULT_LIMITS, "output_text_bytes"}
    result = {**DEFAULT_LIMITS, "output_text_bytes": MAX_OUTPUT_TEXT_BYTES}
    if limits is None:
        return MappingProxyType(result)
    if type(limits) is not dict or set(limits) - allowed:
        raise ValueError("sampled-reference limits must be a bounded plain mapping")
    for name, value in limits.items():
        maximum = MAX_OUTPUT_TEXT_BYTES if name == "output_text_bytes" else DEFAULT_LIMITS[name]
        if type(value) is not int or not 0 < value <= maximum:
            raise ValueError("sampled-reference limits are positive and reduce-only")
        result[name] = value
    return MappingProxyType(result)


def _snapshot_template(template):
    nodes = []
    for node in template.nodes:
        raw = node.state
        if node.phase == "reveal":
            state = raw.state
            actor = None
            reveal_length = raw.board_length
            winner = None
            matched = 0.0
        elif node.phase in ("fold", "showdown"):
            state = raw.state
            actor = None
            reveal_length = 0
            winner = raw.winner
            matched = float(min(state.committed))
        else:
            state = raw
            actor = state.player
            reveal_length = 0
            winner = None
            matched = 0.0
        hist = template.histories[len(nodes)]
        nodes.append(TemplateNode(
            node.phase, state.street, actor, reveal_length, winner, matched,
            tuple(TemplateEdge(edge.kind, edge.token, edge.child) for edge in node.edges),
            hist[0], hist[1], hist[2]))
    return tuple(nodes)


def _prefix_walk_stats(nodes, root, topological_order):
    stats = {}
    for visible_length in PREFIX_LENGTHS:
        paths = [0] * len(nodes)
        paths[root] = 1
        visits = edge_visits = action_edge_visits = 0
        profile_decisions = profile_token_bytes = 0
        stage_decisions = stage_action_slots = 0
        for node_id in topological_order:
            node = nodes[node_id]
            count = paths[node_id]
            if not count:
                continue
            visits += count
            if node.phase == "reveal" and node.reveal_length > visible_length:
                continue
            edge_visits += count * len(node.edges)
            if node.phase == "decision":
                action_edge_visits += count * len(node.edges)
                profile_decisions += count
                profile_token_bytes += node.history_bytes
                if node.street == visible_length:
                    stage_decisions += count
                    stage_action_slots += count * len(node.edges)
            for edge in node.edges:
                paths[edge.child] += count
        stats[visible_length] = MappingProxyType({
            "node_visits": visits, "edge_visits": edge_visits,
            "action_edge_visits": action_edge_visits,
            "profile_decisions": profile_decisions,
            "profile_token_bytes": profile_token_bytes,
            "stage_decisions": stage_decisions,
            "stage_action_slots": stage_action_slots,
        })
    return MappingProxyType(stats)


def build_sampled_reference_context(limits=None):
    """Build once and freeze the independent money/menu cache and N9 prefix law."""
    ceilings = _limits_snapshot(limits)
    # Fixed preflight envelope for this named 388-node/N9 fixture. These are
    # logical reference costs, not Python allocator/RSS claims.
    setup_forecast = {
        "work": MAX_CONTEXT_WORK,
        "entries": MAX_CONTEXT_ENTRIES,
        "created_bits": MAX_CONTEXT_CREATED_BITS,
        "max_integer_bits": MAX_CONTEXT_INTEGER_BITS,
    }
    for field in ("work", "entries", "created_bits", "integer_bits"):
        key = "max_integer_bits" if field == "integer_bits" else field
        if setup_forecast[key] > ceilings[field]:
            raise ValueError(f"sampled-reference context {field} limit exceeded")

    case = _template_case()
    setup_budget=Budget({"work":MAX_CONTEXT_WORK,"entries":1_000_000,
                         "integer_bits":MAX_CONTEXT_INTEGER_BITS,
                         "created_bits":MAX_CONTEXT_CREATED_BITS})
    setup_budget.charge("fixed_n9_context_scan",1_000_000)
    setup_budget.created_bits += 100_000_000
    template = build_reference_template(case,rule_budget=setup_budget)
    literal = literal_reference_census(case,rule_budget=setup_budget)
    if (template.receipt["nodes"] != 388 or template.receipt["edges"] != 410 or
            literal["logical_occurrences"] != 1105 or
            any(literal["by_key"].get(node.key, (0,))[0] != template.histories[index][0]
                for index, node in enumerate(template.nodes))):
        raise ArithmeticError("independent template/literal history census changed")
    setup_work = setup_budget.work
    setup_entries = (64 * len(template.nodes) + 32 * template.receipt["edges"] +
                     32 * 3109 + 16 * literal["logical_occurrences"] + 512)
    setup_created = setup_budget.created_bits
    if (setup_work > setup_forecast["work"] or
            setup_entries > setup_forecast["entries"] or
            setup_created > setup_forecast["created_bits"]):
        raise ArithmeticError("independent context exceeded its fixed setup forecast")

    physical = build_physical_prefix_index()
    if physical.normalizer != Fraction(29, 64) or len(physical.proposals) != 2520:
        raise ArithmeticError("fixed scaled PROOF9 chance law changed")
    frozen_nodes = _snapshot_template(template)
    prefix_stats = _prefix_walk_stats(frozen_nodes, template.root,
                                      template.topological_order)
    # Independent retained model: nodes/edges, full history factors, 3,109
    # prefixes, their per-hand masses and two proposal-q maps.
    context_entries = setup_entries
    context_receipt = MappingProxyType({
        **setup_forecast,
        "actual_rule_setup_work": setup_work,
        "numeric_setup_cumulative_entries": setup_budget.logical_entries,
        "numeric_setup_entries_limit":setup_budget.limits["entries"],
        "actual_logical_entry_upper": setup_entries,
        "actual_created_bits_upper": setup_created,
        "actual_template_nodes": len(frozen_nodes),
        "actual_template_edges": sum(len(node.edges) for node in frozen_nodes),
        "actual_physical_prefixes": sum(len(rows) for rows in physical.prefixes.values()),
        "actual_context_entries_upper": context_entries,
        "scope": "card-free numeric reference cache plus exact PROOF9 masses/q; allocated once per context",
    })
    decisions = sum(node.path_count for node in frozen_nodes if node.phase == "decision")
    slots = sum(node.path_count * len(node.edges)
                for node in frozen_nodes if node.phase == "decision")
    edges = sum(node.path_count * len(node.edges) for node in frozen_nodes)
    profile_bytes = sum(node.history_bytes for node in frozen_nodes
                        if node.phase == "decision")
    if decisions <= 0:
        raise ArithmeticError("card-free decision occurrence count is invalid")
    return SampledReferenceContext(
        frozen_nodes, template.root, scaled_proof9_ranges(), physical.normalizer,
        physical, "frozen-pow2-profile-v1", prefix_stats, slots, decisions,
        edges, profile_bytes, context_receipt, object())


def _validate_board(context, board, proposal_law):
    if type(context) is not SampledReferenceContext:
        raise ValueError("expected an immutable sampled-reference context")
    if type(proposal_law) is not str or proposal_law not in ("uniform", "river_weighted"):
        raise ValueError("proposal law must be uniform or river_weighted")
    if type(board) is not tuple or len(board) != 5 or any(type(c) is not int for c in board):
        raise ValueError("board must be a five-card physical ID tuple")
    if (any(card not in PROOF9 for card in board) or len(set(board)) != 5 or
            tuple(sorted(board[:3])) != board[:3]):
        raise ValueError("board must use a canonical PROOF9 flop and ordered turn/river")
    if board not in context.physical.proposals:
        raise ValueError("board is outside the pinned PROOF9 proposal space")
    q_board = context.physical.proposal_laws[proposal_law]["board"]
    return q_board if proposal_law == "uniform" else q_board[board]


def admit_sampled_board(context, board, proposal_law="uniform", limits=None, *,
                        prefix_folds=False):
    """Preflight a single proposal board without allocating update rows."""
    if type(prefix_folds) is not bool:
        raise ValueError("prefix_folds must be an explicit boolean")
    if prefix_folds and proposal_law != "uniform":
        raise ValueError("prefix folds require the uniform proposal law")
    ceilings = _limits_snapshot(limits)
    q_board = _validate_board(context, board, proposal_law)
    if q_board <= 0:
        raise ValueError("sampled board proposal probability must be positive")
    prefixes = {length: board[:length] for length in PREFIX_LENGTHS}
    q_prefix = MappingProxyType({
        length: context.physical.proposal_laws[proposal_law]["prefix"][prefix]
        for length, prefix in prefixes.items()})
    if any(q <= 0 for q in q_prefix.values()):
        raise ValueError("visible-prefix proposal probability must be positive")

    compatible = []
    for i, (hand0, _weight0) in enumerate(context.ranges[0]):
        if set(hand0).intersection(board):
            continue
        for j, (hand1, _weight1) in enumerate(context.ranges[1]):
            if (set(hand1).intersection(board) or
                    not set(hand0).isdisjoint(hand1)):
                continue
            compatible.append((i, j))
    if len(compatible) > MAX_WORLD_PAIRS:
        raise ArithmeticError("compatible pair count exceeds the fixed PROOF9 bound")

    regret_support = [[False] * len(side) for side in context.ranges]
    for i, j in compatible:
        regret_support[0][i] = True
        regret_support[1][j] = True
    average_runs = []
    average_support = {length: [[False] * len(side) for side in context.ranges]
                       for length in PREFIX_LENGTHS}
    for length, prefix in prefixes.items():
        for player, side in enumerate(context.ranges):
            for hand_index in range(len(side)):
                if context.physical.mass(prefix, player, hand_index) > 0:
                    average_support[length][player][hand_index] = True
                    average_runs.append((length, player, hand_index))
    if len(average_runs) > MAX_PREFIX_RUNS:
        raise ArithmeticError("average prefix run count exceeds the fixed PROOF9 bound")

    rows_upper = slots_upper = history_tokens = history_bytes = action_bytes = 0
    for node in context.nodes:
        if node.phase != "decision":
            continue
        hand_count = sum(
            regret_support[node.actor][hand_index] or
            average_support[node.street][node.actor][hand_index]
            for hand_index in range(len(context.ranges[node.actor])))
        rows = node.path_count * hand_count
        rows_upper += rows
        slots_upper += rows * len(node.edges)
        history_tokens += node.history_tokens * hand_count
        history_bytes += node.history_bytes * hand_count
        action_bytes += (node.path_count * hand_count *
                         sum(len(edge.token.encode("ascii")) for edge in node.edges))
    output_text_bytes = history_bytes + action_bytes
    if rows_upper > MAX_PER_BOARD_ROWS or slots_upper > MAX_PER_BOARD_ACTION_SLOTS:
        raise ValueError("sampled-board row/action cap exceeded")
    if output_text_bytes > ceilings["output_text_bytes"]:
        raise ValueError("sampled-board output text byte limit exceeded")

    regret_visits = len(compatible) * 1105
    regret_edges = len(compatible) * context.decision_slots_per_world
    average_visits = sum(context.prefix_walk_stats[length]["node_visits"]
                         for length, _player, _hand in average_runs)
    average_edges = sum(context.prefix_walk_stats[length]["action_edge_visits"]
                        for length, _player, _hand in average_runs)
    rank_calls = 2 * len(compatible)
    fraction_ops = (12 * regret_edges + 16 * regret_visits +
                    6 * average_edges + 8 * average_visits + 16 * rows_upper + 512)
    profile_scan = (len(compatible) * context.profile_token_scan_per_world +
                    sum(context.prefix_walk_stats[length]["profile_token_bytes"]
                        for length, _player, _hand in average_runs))
    work_upper = (fraction_ops + regret_visits + regret_edges +
                  average_visits + average_edges + rank_calls * 4096 +
                  profile_scan + 4096)
    entries_upper = (16 * rows_upper + 8 * slots_upper +
                     2 * history_tokens + 8192 + 12)
    created_bits_upper = 4096 * fraction_ops + 2200 * rank_calls
    max_bits_upper = 4096

    fold_node_visits = fold_action_edges = fold_terminal_queries = 0
    fold_pair_scans = fold_scalar_ops = fold_frame_entries = 0
    fold_return_vector_entries = fold_reach_copy_entries = 0
    fold_policy_entries = fold_history_token_entries = fold_pair_temp_entries = 0
    fold_counter_metadata_entries = 0
    fold_work_upper = fold_entries_upper = fold_created_bits_upper = fold_max_bits_upper = 0
    if prefix_folds:
        full_walk = context.prefix_walk_stats[5]
        fold_node_visits = 2 * full_walk["node_visits"]
        fold_action_edges = 2 * full_walk["action_edge_visits"]
        fold_terminal_queries = 2 * sum(
            node.path_count for node in context.nodes if node.phase == "fold")
        fold_pair_scans = (fold_terminal_queries * len(context.ranges[0]) *
                           len(context.ranges[1]))
        decision_occurrences = 2 * sum(
            node.path_count for node in context.nodes if node.phase == "decision")
        max_hands = max(map(len, context.ranges))
        max_actions = max(len(node.edges) for node in context.nodes
                          if node.phase == "decision")
        fold_return_vector_entries = fold_node_visits * max_hands
        fold_reach_copy_entries = fold_action_edges * sum(map(len, context.ranges))
        fold_policy_entries = decision_occurrences * max_hands * max_actions
        fold_history_token_entries = 2 * sum(node.history_tokens for node in context.nodes)
        fold_pair_temp_entries = 8 * fold_pair_scans
        fold_scalar_ops = (
            4 * fold_node_visits + 8 * fold_action_edges +
            fold_terminal_queries * (16 + 16 * len(context.ranges[0]) *
                                     len(context.ranges[1])) +
            decision_occurrences * max_hands * max_actions * 16 +
            2 * (len(context.nodes) + sum(map(len, context.ranges))))
        # Count all simultaneously live fold traversal structures: one return
        # vector per visited node, copied global reaches per action edge,
        # bounded policy tuples, full-history token references, and rational
        # marginal temporaries for every candidate hand pair.
        fold_frame_entries = (fold_return_vector_entries + fold_reach_copy_entries +
                              fold_policy_entries + fold_history_token_entries +
                              fold_pair_temp_entries)
        fold_work_upper = (4 * fold_node_visits + 8 * fold_action_edges +
                           16 * fold_pair_scans +
                           decision_occurrences * max_hands * max_actions * 8 +
                           fold_scalar_ops)
        # Budget.charge creates two logical entries for each new counter
        # family. Fold mode adds exactly these two families.
        fold_counter_metadata_entries = 2 * 2
        fold_entries_upper = fold_frame_entries + fold_counter_metadata_entries
        fold_created_bits_upper = 4096 * fold_scalar_ops
        fold_max_bits_upper = MAX_CONTEXT_INTEGER_BITS
    setup = context.setup_receipt
    combined_work = work_upper + fold_work_upper
    combined_entries = entries_upper + fold_entries_upper
    combined_created_bits = created_bits_upper + fold_created_bits_upper
    combined_max_bits = max(max_bits_upper, fold_max_bits_upper)
    if setup["work"] + combined_work > ceilings["work"]:
        raise ValueError("sampled-board certificate work limit exceeded")
    if setup["entries"] + combined_entries > ceilings["entries"]:
        raise ValueError("sampled-board certificate entry limit exceeded")
    if setup["created_bits"] + combined_created_bits > ceilings["created_bits"]:
        raise ValueError("sampled-board cumulative integer bit limit exceeded")
    if combined_max_bits > ceilings["integer_bits"]:
        raise ValueError("sampled-board integer bit limit exceeded")

    return SampledBoardAdmission(
        context, board, proposal_law, q_board, q_prefix, tuple(compatible),
        tuple(average_runs), rows_upper, slots_upper, history_tokens,
        history_bytes, action_bytes, output_text_bytes, regret_visits,
        regret_edges, average_visits, average_edges, rank_calls, fraction_ops,
        work_upper, entries_upper, created_bits_upper, max_bits_upper,
        ceilings, context._seal, prefix_folds, fold_node_visits,
        fold_action_edges, fold_terminal_queries, fold_pair_scans,
        fold_scalar_ops, fold_frame_entries, fold_return_vector_entries,
        fold_reach_copy_entries, fold_policy_entries, fold_history_token_entries,
        fold_pair_temp_entries, fold_counter_metadata_entries, fold_work_upper,
        fold_entries_upper, fold_created_bits_upper, fold_max_bits_upper)


def _reveal_token(board, length):
    if length == 3:
        return "flop@" + "".join(card_name(card) for card in board[:3])
    if length == 4:
        return "turn@" + card_name(board[3])
    if length == 5:
        return "river@" + card_name(board[4])
    raise ArithmeticError("invalid symbolic reveal length")


def _prefix_fold_terminal_values(context, target, node, prefix, opponent_reaches,
                                 budget, powers):
    """Exact target-hand utility vector for one fixed-payoff visible fold.

    This is intentionally independent of native chance helpers. The fixed N9
    suffix census is over the five cards left after both private hands.
    """
    suffix_counts = {0: 20, 3: 2, 4: 1, 5: 1}
    if (node.phase != "fold" or type(target) is not int or target not in (0, 1) or
            type(prefix) is not tuple or len(prefix) != node.street or
            node.street not in suffix_counts or prefix not in context.physical.masses or
            type(opponent_reaches) is not tuple or
            len(opponent_reaches) != len(context.ranges[1-target])):
        raise ValueError("invalid visible folded-terminal query")
    q_prefix = context.physical.proposal_laws["uniform"]["prefix"][prefix]
    payoff = budget.input(node.matched, "folded whole-hand payoff")
    if node.winner != target:
        payoff = budget.neg(payoff, "folded target-seat payoff orientation")
    result = []
    for own_hand, own_weight in context.ranges[target]:
        if set(own_hand).intersection(prefix):
            result.append(Fraction(0))
            continue
        mass = Fraction(0)
        for (opponent_hand, opponent_weight), exponent in zip(
                context.ranges[1-target], opponent_reaches):
            if (set(opponent_hand).intersection(prefix) or
                    not set(own_hand).isdisjoint(opponent_hand) or exponent < 0):
                continue
            pair_mass = budget.div(
                budget.div(budget.mul(own_weight, opponent_weight,
                                     "folded compatible private prior"),
                           context.normalizer,
                           "folded global prior normalization"),
                Fraction(20), "folded complete-board target mass")
            pair_mass = budget.mul(pair_mass, Fraction(suffix_counts[node.street]),
                                   "folded legal suffix multiplicity")
            pair_mass = budget.mul(pair_mass, powers[exponent], "folded opponent reach")
            mass = budget.add(mass, pair_mass, "folded opponent marginal")
        mass = budget.div(mass, q_prefix, "folded prefix inverse proposal")
        result.append(budget.mul(mass, payoff, "folded signed whole-hand payoff"))
    return result


def compute_sampled_update_reference(admission, *, prefix_folds=False):
    """Compute one exact per-board proposal estimator and prefix average.

    ``prefix_folds`` is an explicit uniform-proposal reference mode. It folds
    fixed-payoff fold terminals over all private-compatible unseen suffixes at
    their visible prefix; showdown terminals and the average walk retain the
    ordinary sampled-board calculation.
    """
    if type(admission) is not SampledBoardAdmission or admission._seal is not admission.context._seal:
        raise ValueError("sampled-board admission/context seal mismatch")
    if type(prefix_folds) is not bool:
        raise ValueError("prefix_folds must be an explicit boolean")
    if prefix_folds and admission.proposal_law != "uniform":
        raise ValueError("prefix folds require the uniform proposal law")
    if prefix_folds and not admission.prefix_fold_admitted:
        raise ValueError("sampled-board admission does not match prefix-fold mode")
    context = admission.context
    budget = Budget({name: admission.limits[name] for name in DEFAULT_LIMITS})
    budget.entries(admission.entries_upper - 12,
                    "pre-admitted sampled-board output")
    powers = tuple(Fraction(1, 1 << exponent) for exponent in range(65))
    zero = Fraction(0)
    rows = {}
    regret_worlds = rank_calls = regret_node_visits = regret_edge_visits = 0
    average_node_visits = average_edge_visits = 0
    prefix_fold_node_visits = prefix_fold_edge_visits = 0
    rank_outcomes = {"sb_win": 0, "tie": 0, "sb_loss": 0}

    def ensure_row(actor, hand, history, actions, exponents):
        key = (actor, hand, history)
        row = rows.get(key)
        if row is None:
            row = _MutableRow(actions, exponents, [zero] * len(actions), zero,
                              [zero] * len(actions), [zero] * len(actions))
            rows[key] = row
        elif row.actions != actions or row.exponents != exponents:
            raise ArithmeticError("same full-history row has inconsistent menu/profile")
        return row

    def regret_walk(node_id, history, reaches, chance, rank_sign, world_hands):
        nonlocal regret_node_visits, regret_edge_visits
        node = context.nodes[node_id]
        regret_node_visits += 1
        budget.charge("sample_regret_node", 1)
        if node.phase in ("fold", "showdown"):
            amount = budget.input(node.matched, "sampled terminal matched contribution")
            if node.phase == "fold":
                if prefix_folds:
                    return zero
                return amount if node.winner == 0 else budget.neg(amount, "global SB fold sign")
            return budget.mul(amount, Fraction(rank_sign), "global SB showdown utility")
        if node.phase == "reveal":
            edge = node.edges[0]
            return regret_walk(edge.child, (*history, _reveal_token(admission.board,
                                                                     node.reveal_length)),
                               reaches, chance, rank_sign, world_hands)
        actor = node.actor
        hand = world_hands[actor]
        actions = tuple(edge.token for edge in node.edges)
        exponents = _profile_exponents(actor, hand, history, actions)
        row = ensure_row(actor, hand, history, actions, exponents)
        row.regret_world_visits += 1
        values = []
        for edge, exponent in zip(node.edges, exponents):
            updated = list(reaches)
            if updated[actor] is not None:
                updated[actor] = None if exponent < 0 else updated[actor] + exponent
            regret_edge_visits += 1
            budget.charge("sample_regret_action_edge", 1)
            values.append(regret_walk(edge.child, (*history, edge.token), tuple(updated),
                                      chance, rank_sign, world_hands))
        mixed = zero
        for value, exponent in zip(values, exponents):
            if exponent >= 0:
                mixed = budget.add(mixed, budget.mul(powers[exponent], value,
                                                     "sample profile-weighted value"),
                                   "sample ordered value sum")
        other_exp = reaches[1 - actor]
        other = zero if other_exp is None else powers[other_exp]
        cf_mass = budget.mul(chance, other, "board mass times opponent reach")
        sign = 1 if actor == 0 else -1
        for index, (value, exponent) in enumerate(zip(values, exponents)):
            delta = budget.sub(value, mixed, "sample action value difference")
            if sign < 0:
                delta = budget.neg(delta, "BB utility orientation")
            delta = budget.mul(cf_mass, delta, "sample counterfactual regret")
            row.regrets[index] = budget.add(row.regrets[index], delta,
                                            "sample regret accumulation")
        return mixed

    # Regrets use only worlds compatible with this full board. All action
    # branches are traversed even where either player's own reach is zero.
    for hand0_index, hand1_index in admission.compatible_pairs:
        hand0, weight0 = context.ranges[0][hand0_index]
        hand1, weight1 = context.ranges[1][hand1_index]
        chance = budget.div(
            budget.div(budget.mul(weight0, weight1, "compatible pair prior"),
                       context.normalizer, "global prior normalization"),
            Fraction(20), "complete-board target mass")
        chance = budget.div(chance, admission.board_probability,
                            "sample-board inverse proposal")
        rank0 = independent_rank(tuple(card_name(card)
                                       for card in (*hand0, *admission.board)))
        rank1 = independent_rank(tuple(card_name(card)
                                       for card in (*hand1, *admission.board)))
        rank_calls += 2
        regret_worlds += 1
        budget.charge("sample_compatible_world", 1)
        sign = (rank0 > rank1) - (rank0 < rank1)
        rank_outcomes[{1: "sb_win", 0: "tie", -1: "sb_loss"}[sign]] += 1
        regret_walk(context.root, (), (0, 0), chance, sign, (hand0, hand1))

    if prefix_folds:
        # Fold utility is fixed before any hidden suffix is revealed. For each
        # acting seat, integrate literal opponent holdings and all legal N9
        # completions at that fold's visible prefix, then correct by q(prefix).
        def folded_walk(target, node_id, history, reaches):
            nonlocal prefix_fold_node_visits, prefix_fold_edge_visits
            node = context.nodes[node_id]
            prefix_fold_node_visits += 1
            budget.charge("sample_prefix_fold_node", 1)
            if node.phase == "showdown":
                return [zero] * len(context.ranges[target])
            if node.phase == "fold":
                length = node.street
                prefix = admission.board[:length]
                return _prefix_fold_terminal_values(
                    context, target, node, prefix, reaches[1-target], budget, powers)
            if node.phase == "reveal":
                if node.reveal_length > admission.board.__len__():
                    return [zero] * len(context.ranges[target])
                edge = node.edges[0]
                return folded_walk(target, edge.child,
                    (*history, _reveal_token(admission.board, node.reveal_length)), reaches)

            actor = node.actor
            actions = tuple(edge.token for edge in node.edges)
            side = context.ranges[actor]
            policies = tuple(_profile_exponents(actor, hand, history, actions)
                             for hand, _weight in side)
            children = []
            for action_index, edge in enumerate(node.edges):
                updated = [list(reaches[0]), list(reaches[1])]
                for hand_index, policy in enumerate(policies):
                    current = updated[actor][hand_index]
                    exponent = policy[action_index]
                    updated[actor][hand_index] = (
                        -1 if current < 0 or exponent < 0 else current + exponent)
                prefix_fold_edge_visits += 1
                budget.charge("sample_prefix_fold_action_edge", 1)
                children.append(folded_walk(target, edge.child, (*history, edge.token),
                                            tuple(tuple(x) for x in updated)))
            result = [zero] * len(context.ranges[target])
            if actor == target:
                length = node.street
                for hand_index, (hand, _weight) in enumerate(context.ranges[target]):
                    exponents = policies[hand_index]
                    mixed = zero
                    for action_index, exponent in enumerate(exponents):
                        if exponent >= 0:
                            mixed = budget.add(mixed,
                                budget.mul(powers[exponent], children[action_index][hand_index],
                                           "folded own-policy value"),
                                "folded own-policy mix")
                    if context.physical.mass(admission.board[:length], target, hand_index) > 0:
                        row = ensure_row(target, hand, history, actions, exponents)
                        for action_index, child_values in enumerate(children):
                            delta = budget.sub(child_values[hand_index], mixed,
                                               "folded action regret difference")
                            row.regrets[action_index] = budget.add(
                                row.regrets[action_index],
                                delta,
                                "folded regret accumulation")
                            row.prefix_fold_regrets[action_index] = budget.add(
                                row.prefix_fold_regrets[action_index], delta,
                                "folded component accumulation")
                    result[hand_index] = mixed
            else:
                for child_values in children:
                    for hand_index, value in enumerate(child_values):
                        result[hand_index] = budget.add(result[hand_index], value,
                                                        "folded opponent action sum")
            return result

        for target in (0, 1):
            initial_reaches = (tuple(0 for _ in context.ranges[0]),
                               tuple(0 for _ in context.ranges[1]))
            folded_walk(target, context.root, (), initial_reaches)

    def average_walk(node_id, target_player, target_hand, target_length,
                     average_scale, own_exp, history):
        nonlocal average_node_visits, average_edge_visits
        node = context.nodes[node_id]
        average_node_visits += 1
        budget.charge("sample_average_node", 1)
        if node.phase in ("fold", "showdown"):
            return
        if node.phase == "reveal":
            if node.reveal_length > target_length:
                return
            edge = node.edges[0]
            average_walk(edge.child, target_player, target_hand, target_length,
                         average_scale, own_exp,
                         (*history, _reveal_token(admission.board, node.reveal_length)))
            return

        actor = node.actor
        actions = tuple(edge.token for edge in node.edges)
        exponents = (_profile_exponents(actor, target_hand, history, actions)
                     if actor == target_player else None)
        if actor == target_player and node.street == target_length:
            row = ensure_row(actor, target_hand, history, actions, exponents)
            row.average_prefix_visits += 1
            own_reach = zero if own_exp is None else powers[own_exp]
            increment = budget.mul(average_scale, own_reach,
                                   "target prefix mass times own reach")
            row.average_mass = budget.add(row.average_mass, increment,
                                          "sample average mass accumulation")
            for index, exponent in enumerate(exponents):
                if exponent >= 0:
                    delta = budget.mul(increment, powers[exponent],
                                       "profile-weighted sample average")
                    row.average_actions[index] = budget.add(
                        row.average_actions[index], delta,
                        "sample average action accumulation")

        for edge_index, edge in enumerate(node.edges):
            updated_exp = own_exp
            if actor == target_player and updated_exp is not None:
                exponent = exponents[edge_index]
                updated_exp = None if exponent < 0 else updated_exp + exponent
            average_edge_visits += 1
            budget.charge("sample_average_action_edge", 1)
            average_walk(edge.child, target_player, target_hand, target_length,
                         average_scale, updated_exp, (*history, edge.token))

    # Prefix averages are a separate reach walk. Each run uses the target
    # μ_i(P)/q(P) and stops before the first reveal not yet visible at P.
    for length, player, hand_index in admission.average_runs:
        hand, _weight = context.ranges[player][hand_index]
        prefix = admission.board[:length]
        target_mass = context.physical.mass(prefix, player, hand_index)
        scale = budget.div(target_mass, admission.prefix_probabilities[length],
                           "target prefix mass over proposal mass")
        average_walk(context.root, player, hand, length, scale, 0, ())

    if (regret_worlds != len(admission.compatible_pairs) or
            rank_calls != admission.rank_calls_upper or
            regret_node_visits != admission.regret_visits_upper or
            regret_edge_visits != admission.regret_edges_upper or
            average_node_visits != admission.average_visits_upper or
            average_edge_visits != admission.average_edges_upper):
        raise ArithmeticError(
            "sampled reference actual work disagrees with admission: "
            f"worlds={regret_worlds}/{len(admission.compatible_pairs)}, "
            f"ranks={rank_calls}/{admission.rank_calls_upper}, "
            f"regret_nodes={regret_node_visits}/{admission.regret_visits_upper}, "
            f"regret_edges={regret_edge_visits}/{admission.regret_edges_upper}, "
            f"average_nodes={average_node_visits}/{admission.average_visits_upper}, "
            f"average_edges={average_edge_visits}/{admission.average_edges_upper}")
    if (not prefix_folds and
            (len(rows) != admission.row_count_upper or
             sum(len(row.actions) for row in rows.values()) != admission.action_slots_upper)):
        raise ArithmeticError("sampled reference rows disagree with the preflight census")
    if prefix_folds and (len(rows) > MAX_PER_BOARD_ROWS or
                         sum(len(row.actions) for row in rows.values()) > MAX_PER_BOARD_ACTION_SLOTS):
        raise ArithmeticError("prefix-fold reference exceeded fixed row/action bounds")
    if (not prefix_folds and
            (budget.work > admission.work_upper or
             budget.logical_entries > admission.entries_upper)):
        raise ArithmeticError("sampled reference actual work/entries exceeded admission")
    if prefix_folds and (budget.work > admission.work_upper + admission.prefix_fold_work_upper or
                         budget.logical_entries > admission.entries_upper +
                         admission.prefix_fold_entries_upper):
        raise ArithmeticError(
            "prefix-fold reference exceeded combined work/entries: "
            f"{budget.work}/{admission.work_upper + admission.prefix_fold_work_upper}, "
            f"{budget.logical_entries}/{admission.entries_upper + admission.prefix_fold_entries_upper}")
    if (not prefix_folds and
            (budget.created_bits > admission.created_bits_upper or
             budget.max_forecast_bits > admission.max_integer_bits_upper)):
        raise ArithmeticError("sampled reference actual integer forecast exceeded admission")
    if prefix_folds and (
            budget.created_bits > admission.created_bits_upper +
            admission.prefix_fold_created_bits_upper or
            budget.max_forecast_bits > max(admission.max_integer_bits_upper,
                                           admission.prefix_fold_max_integer_bits_upper)):
        raise ArithmeticError("prefix-fold reference exceeded its combined integer forecast")

    frozen = {}
    for key, row in rows.items():
        if sum(row.average_actions, zero) != row.average_mass:
            raise ArithmeticError("sample average action masses do not sum to average mass")
        frozen[key] = SampledUpdateRow(
            key[0], key[1], key[2], row.actions, row.exponents,
            tuple(row.regrets), row.average_mass, tuple(row.average_actions),
            row.regret_world_visits, row.average_prefix_visits,
            tuple(row.prefix_fold_regrets) if prefix_folds else ())
    receipt = MappingProxyType({
        "version": "n9-sampled-board-update-reference-v1",
        "board": admission.board,
        "proposal_law": admission.proposal_law,
        "q_board": admission.board_probability,
        "q_prefix": admission.prefix_probabilities,
        "compatible_worlds": regret_worlds,
        "regret_node_visits": regret_node_visits,
        "regret_action_edge_visits": regret_edge_visits,
        "independent_rank_calls": rank_calls,
        "rank_outcomes": MappingProxyType(rank_outcomes),
        "average_prefix_runs": len(admission.average_runs),
        "average_node_visits": average_node_visits,
        "average_action_edge_visits": average_edge_visits,
        "rows": len(frozen),
        "action_slots": sum(len(row.actions) for row in frozen.values()),
        "zero_regret_average_only_rows": sum(
            row.regret_world_visits == 0 and row.average_prefix_visits > 0
            for row in frozen.values()),
        "q_corrected_regret": True,
        "q_corrected_prefix_fold_regret": prefix_folds,
        "prefix_fold_node_visits": prefix_fold_node_visits,
        "prefix_fold_action_edge_visits": prefix_fold_edge_visits,
        "prefix_fold_projection": MappingProxyType({
            "admitted": admission.prefix_fold_admitted,
            "node_visits_upper": admission.prefix_fold_node_visits_upper,
            "action_edges_upper": admission.prefix_fold_action_edges_upper,
            "terminal_queries_upper": admission.prefix_fold_terminal_queries_upper,
            "opponent_pair_scans_upper": admission.prefix_fold_opponent_pair_scans_upper,
            "scalar_operations_upper": admission.prefix_fold_scalar_operations_upper,
            "frame_entries_upper": admission.prefix_fold_frame_entries_upper,
            "return_vector_entries_upper": admission.prefix_fold_return_vector_entries_upper,
            "reach_copy_entries_upper": admission.prefix_fold_reach_copy_entries_upper,
            "policy_entries_upper": admission.prefix_fold_policy_entries_upper,
            "history_token_entries_upper": admission.prefix_fold_history_token_entries_upper,
            "pair_temporary_entries_upper": admission.prefix_fold_pair_temporary_entries_upper,
            "counter_metadata_entries_upper": admission.prefix_fold_counter_metadata_entries_upper,
            "work_upper": admission.prefix_fold_work_upper,
            "entries_upper": admission.prefix_fold_entries_upper,
            "created_bits_upper": admission.prefix_fold_created_bits_upper,
            "max_integer_bits_upper": admission.prefix_fold_max_integer_bits_upper,
            "combined_work_upper": admission.work_upper + admission.prefix_fold_work_upper,
            "combined_entries_upper": admission.entries_upper + admission.prefix_fold_entries_upper,
            "combined_created_bits_upper": admission.created_bits_upper + admission.prefix_fold_created_bits_upper,
            "combined_max_integer_bits_upper": max(admission.max_integer_bits_upper,
                admission.prefix_fold_max_integer_bits_upper),
            "actual_node_visits": prefix_fold_node_visits,
            "actual_action_edge_visits": prefix_fold_edge_visits,
            "actual_runtime_work": budget.work,
            "actual_runtime_entries": budget.logical_entries,
            "actual_created_bits": budget.created_bits,
            "actual_max_integer_bits": budget.max_forecast_bits,
        }) if prefix_folds else None,
        "q_corrected_prefix_average": True,
        "average_uses_future_board_blockers": False,
        "runtime_budget": budget.receipt(),
        "admission": admission.receipt(),
        "scope": "one bounded PROOF9 sampled-board reference only; no 2,520-board study or training",
    })
    return SampledUpdateResult(admission, MappingProxyType(frozen), receipt)
