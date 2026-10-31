"""Opt-in independent exact saved-policy certificate for finite selected boards.

This verifier never trains and never constructs compatible-pair/world records.
The old capped literal certificate remains an unchanged independent reference.
Whole-game acceptance and saved-source provenance are separate caller gates.
"""
from fractions import Fraction
from math import fsum

from scripts.matrix_free_certificate_budget import Budget
from scripts.matrix_free_four_street_rules import (
    Decision, Reveal, Terminal, build_public_model,
)
from scripts.matrix_free_selected_payoffs import PayoffModel, RANK_CACHE_ENTRIES, RANK_TEMP_ENTRIES
from scripts.matrix_free_certificate_serialization import clone_json, canonical_hash, FractionText

MAX_ROWS = 20_000
MAX_ACTION_SLOTS = 100_000
SOURCE_IDENTITY = "four-street-independent-matrix-free-exact-v1"
THRESHOLD = Fraction(1, 1000)
ZERO, ONE = Fraction(0), Fraction(1)


def _need(value, message):
    if not value:
        raise ValueError(message)


def _row_key(row):
    _need(type(row) is dict and set(row) == {
        "player", "hand", "street", "revealed_board", "history", "actions"},
        "strategy row has missing or unknown fields")
    _need(type(row["player"]) is str and row["player"] in ("sb", "bb"),
          "strategy player must be sb or bb")
    _need(type(row["hand"]) is str and len(row["hand"]) == 4,
          "strategy hand must contain two cards")
    history = row["history"]
    _need(type(history) is list and len(history) <= 64 and
          all(type(token) is str and 0 < len(token) <= 64 for token in history),
          "strategy history must be bounded visible tokens")
    return (0 if row["player"] == "sb" else 1, row["hand"], tuple(history))


def _validate(model, kernel, payload, budget, formatter):
    _need(type(payload) is dict and len(payload) <= 128 and
          payload.get("solver_version") == payload.get("strategy_schema") == "preflop-strategy-v1",
          "complete four-street strategy schema required")
    _need(payload.get("chance_contract") == "exact-product-selected-v1" and
          payload.get("conversion_contract") == "exact-product-vectors-binary64-v1" and
          payload.get("pair_diagnostics") == "compact-exact-product-inputs-v1" and
          "private_pair_probabilities" not in payload and "compatible_private_pairs" not in payload,
          "compact selected-product chance contract required")
    _need(payload.get("runout_mode") == "conditioned-ordered-selected-runouts" and
          ("postflop_scope" not in payload or payload["postflop_scope"] == "all-streets"),
          "policy must model all four selected-runout streets")
    _need(payload.get("selected_runouts") == [list(board) for board in model.outcomes] and
          payload.get("reachable_runouts") == [list(board) for board in kernel.reachable_boards] and
          type(payload.get("worlds")) is int and payload["worlds"] == kernel.physical_worlds,
          "policy selected/reachable physical support differs from requested game")
    snapshot = payload.get("chance_input_snapshot")
    _need(type(snapshot) is dict and set(snapshot) == {"contract", "ranges"} and
          snapshot["contract"] == "exact-product-selected-v1" and
          type(snapshot["ranges"]) is list and len(snapshot["ranges"]) == 2,
          "malformed compact range snapshot")
    for rows, side in zip(snapshot["ranges"], model.ranges):
        _need(type(rows) is list and len(rows) == len(side), "range snapshot width differs")
        expected = {"".join(hand): float(weight).hex() for hand, weight in side.items()}
        observed = {}
        for row in rows:
            _need(type(row) is dict and set(row) == {"hand", "weight_hex"} and
                  type(row["hand"]) is str and row["hand"] not in observed and
                  type(row["weight_hex"]) is str, "malformed compact range row")
            observed[row["hand"]] = row["weight_hex"]
        _need(observed == expected, "range weights/holdings differ from requested game")

    expected = {}
    supports = {}
    slots = 0
    for node in model.decisions:
        budget.charge("supported_policy_decisions")
        if node.board not in supports:
            supports[node.board] = kernel.prefix_support(node.board)
            budget.entries(2 + sum(map(len, kernel.hands)), "cached physical prefix support")
        for i, hand in enumerate(kernel.hands[node.player]):
            budget.charge("supported_policy_hand_checks")
            if not supports[node.board][node.player][i]:
                continue
            key = (node.player, "".join(hand), node.history)
            _need(key not in expected, "full visible history aliases independent public decisions")
            _need(len(expected) < MAX_ROWS, "certificate policy-row limit exceeded")
            slots += len(node.actions)
            _need(slots <= MAX_ACTION_SLOTS, "certificate action-slot limit exceeded")
            budget.entries(4, "expected full-history information row")
            expected[key] = node
    rows = payload.get("strategy")
    _need(type(rows) is list and len(rows) == len(expected) and
          type(payload.get("info_sets")) is int and payload["info_sets"] == len(expected),
          "complete policy row count differs from supported information sets")
    supplied = {}
    for row in rows:
        key = _row_key(row)
        budget.charge("serialized_row_history", 8 + sum(map(len, key[2])))
        _need(key not in supplied, "duplicate serialized information set")
        budget.entries(2, "supplied policy row index")
        supplied[key] = row
    _need(set(supplied) == set(expected), "missing, extra or unsupported policy row")
    policies, normalized_rows = {}, []
    streets = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}
    budget.entries(len(expected), "sorted information row references")
    history_bytes = max((sum(map(len, key[2])) for key in expected), default=0)
    budget.charge("information_row_sort_upper",
                  len(expected) * (1 + len(expected).bit_length()) * (8 + history_bytes))
    for key in sorted(expected):
        node, row = expected[key], supplied[key]
        budget.charge("policy_row_validation", 8 + len(node.history))
        _need(row["street"] == streets[len(node.board)] and
              row["revealed_board"] == list(node.board) and row["history"] == list(node.history),
              "policy street, board or full visible history differs")
        actions = row["actions"]
        _need(type(actions) is list and len(actions) == len(node.actions), "ordered legal menu differs")
        budget.entries(16 + 12 * len(actions), "normalized policy row/action output")
        raw = []
        for actual, legal in zip(actions, node.actions):
            _need(type(actual) is dict and set(actual) == {
                "name", "amount", "raise_to", "history_key", "probability"}, "malformed policy action")
            _need(actual["name"] == legal.name and actual["history_key"] == legal.token,
                  "action identity differs from independent numeric rule")
            for field, value in (("amount", legal.amount), ("raise_to", legal.raise_to)):
                _need(type(actual[field]) in (int, float) and actual[field] == value,
                      "action amount/target differs from whole-hand numeric rule")
            value = actual["probability"]
            _need(type(value) in (int, float) and 0 <= value <= 1,
                  "policy probability must be finite binary64 in [0,1]")
            raw.append(float(value))
        _need(abs(fsum(raw) - 1.0) <= 1e-10, "serialized row does not sum to one")
        exact = tuple(budget.input(value, "serialized probability") for value in raw)
        total = ZERO
        for value in exact:
            total = budget.add(total, value, "serialized row sum")
        _need(total.numerator > 0, "zero-mass policy row")
        probabilities = tuple(budget.div(value, total, "normalized policy probability") for value in exact)
        policies[key] = probabilities
        normalized_rows.append({"player": row["player"], "hand": row["hand"],
            "street": row["street"], "revealed_board": row["revealed_board"], "history": row["history"],
            "actions": [{"name": action["name"], "amount": action["amount"], "raise_to": action["raise_to"],
                         "history_key": action["history_key"], "probability_fraction": formatter.format(probability)}
                        for action, probability in zip(actions, probabilities)]})
    return policies, normalized_rows, {"rows": len(expected), "action_slots": slots,
                                      "physically_supported_prefixes": len(supports)}


def _walk(node, responder, policies, kernel, budget, *, best_response, reach=None, depth=0):
    """Exclude responder reach for BR; terminal vectors include its prior once."""
    _need(depth <= 64, "certificate public traversal depth exceeded")
    own, opp = len(kernel.hands[responder]), len(kernel.hands[1 - responder])
    if reach is None:
        budget.entries(opp + 1, "root opponent reach")
        reach = (ONE,) * opp
    budget.charge("certificate_public_visits", 1 + opp)
    budget.charge("walk_vector_slots", 2 * own + 1)
    budget.entries(2 * own + 1, "own-hand list/returned tuple references")
    if not any(reach):
        budget.charge("zero_opponent_reach_shortcuts")
        return (ZERO,) * own
    if isinstance(node, Terminal):
        return kernel.terminal(responder, reach, node.board, node.matched, node.winner)
    result = [ZERO] * own
    if isinstance(node, Reveal):
        budget.charge("walk_public_edges", len(node.branches))
        for child in node.branches.values():
            branch = _walk(child, responder, policies, kernel, budget,
                           best_response=best_response, reach=reach, depth=depth + 1)
            for i, value in enumerate(branch):
                result[i] = budget.add(result[i], value, "ordered public reveal sum")
        return tuple(result)
    _need(isinstance(node, Decision), "unknown independent public node")
    budget.charge("walk_public_edges", len(node.children))
    budget.charge("walk_history_scan", len(node.history))
    history_work = 8 + sum(map(len, node.history))
    if node.player == responder:
        budget.entries(len(node.children) * (own + 1) + 1, "own legal action vectors")
        branches = [_walk(child, responder, policies, kernel, budget,
                          best_response=best_response, reach=reach, depth=depth + 1)
                    for child in node.children]
        for i, hand in enumerate(kernel.hands[responder]):
            budget.charge("walk_policy_lookups", history_work)
            key = (responder, "".join(hand), node.history)
            if key not in policies:  # Physically unsupported, not merely policy-zero.
                continue
            if best_response:
                value = branches[0][i]
                for branch in branches[1:]:
                    if budget.compare(branch[i], value, "own-hand legal response selection") > 0:
                        value = branch[i]
                result[i] = value
            else:
                for probability, branch in zip(policies[key], branches):
                    contribution = budget.mul(probability, branch[i], "own profile action weight")
                    result[i] = budget.add(result[i], contribution, "own profile action sum")
    else:
        for action_index, child in enumerate(node.children):
            budget.entries(2 * opp + 1, "opponent action reach list/tuple")
            child_reach = []
            for hand, value in zip(kernel.hands[node.player], reach):
                budget.charge("walk_policy_lookups", history_work)
                key = (node.player, "".join(hand), node.history)
                probability = policies[key][action_index] if key in policies else ZERO
                child_reach.append(budget.mul(value, probability, "opponent action reach"))
            branch = _walk(child, responder, policies, kernel, budget,
                           best_response=best_response, reach=tuple(child_reach), depth=depth + 1)
            for i, value in enumerate(branch):
                result[i] = budget.add(result[i], value, "opponent action expectation")
    return tuple(result)


def _sum_vector(values, budget, label):
    result = ZERO
    for value in values:
        result = budget.add(result, value, label)
    return result


def _walk_forecast(model, kernel, budget, final_hash_receipts, formatter):
    """Pre-admit every remaining named work family and logical reference bound.

    Two responder-0 walks (profile and BR), one responder-1 walk. All actions
    and zero-reach branches are forecast even when numeric work can skip them.
    """
    budget.charge("whole_walk_forecast_setup", 512)
    budget.entries(8192, "forecast/counter/final receipt metadata upper")
    nodes = terminals = terminal_boards = reveal_edges = 0
    history_tokens = max_history_chars = 0
    decision_nodes, decision_edges = [0, 0], [0, 0]
    budget.entries(1, "whole-walk census stack")
    stack = [model.root]
    while stack:
        node = stack.pop(); nodes += 1
        budget.charge("whole_walk_forecast_nodes")
        _need(nodes <= 250_000, "certificate public occurrence census exceeded")
        if isinstance(node, Terminal):
            terminals += 1
            cost = len(kernel.boards) * (1 + len(node.board))
            budget.charge("whole_walk_forecast_terminal_boards", cost)
            budget.entries(cost + 1, "terminal prefix-slice census scratch")
            terminal_boards += sum(board[:len(node.board)] == node.board for board in kernel.boards)
        elif isinstance(node, Decision):
            budget.charge("whole_walk_forecast_history", len(node.history))
            history_tokens += len(node.history)
            max_history_chars = max(max_history_chars, sum(map(len, node.history)))
            decision_nodes[node.player] += 1
            decision_edges[node.player] += len(node.children)
            budget.entries(len(node.children), "census public child references")
            stack.extend(node.children)
        elif isinstance(node, Reveal):
            reveal_edges += len(node.branches)
            budget.entries(len(node.branches), "census reveal child references")
            stack.extend(node.branches.values())
        else:
            raise ValueError("unknown public node during whole-call census")
    h0, h1 = map(len, kernel.hands); h = h0 + h1; b = len(kernel.boards)
    d0, d1 = decision_nodes; e0, e1 = decision_edges; t = terminal_boards
    # Each rank sweep inserts each opponent into all/lower/equal at most once,
    # and does three blocker lookups plus four other operations per own hand.
    inserts = 3 * t * (2 * h1 + h0)
    lookups = 3 * t * (2 * h0 + h1)
    terminal_fraction = (2 * terminals * (2 * h1 + 1 + 3 * h0) +
                         terminals * (2 * h0 + 1 + 3 * h1) +
                         3 * inserts + 3 * lookups + 4 * t * (2 * h0 + h1))
    own_profile = 2 * h0 * e0
    own_comparisons = h0 * (e0 - d0) + h1 * (e1 - d1)
    opponent_reach = 2 * h1 * e1 + h0 * e0
    opponent_sums = 2 * h0 * e1 + h1 * e0
    reveal_sums = (2 * h0 + h1) * reveal_edges
    root_sums = 2 * h0 + h1
    digits = (budget.limits["integer_bits"] * 30103) // 100000 + 1
    metric_text_upper = 10 * (2 * digits + 2)
    _need(formatter.bytes_upper + metric_text_upper <= formatter.max_bytes,
          "certificate final Fraction text forecast exceeds byte limit")
    future = {
        "certificate_public_visits": nodes * (3 + 2 * h1 + h0),
        "zero_opponent_reach_shortcuts": 3 * nodes,
        "walk_vector_slots": nodes * (2 * (2 * h0 + 1) + (2 * h1 + 1)),
        "walk_public_edges": 3 * (e0 + e1 + reveal_edges),
        "walk_history_scan": 3 * history_tokens,
        "walk_policy_lookups": (2 * h0 * d0 + h1 * d1 + 2 * h1 * e1 + h0 * e0) * (8 + max_history_chars),
        "board_prefix_scan": 3 * terminals * b,
        "terminal_board_scan": 3 * t * (8 + 4 * h),
        "bucket_insert": inserts, "bucket_lookup": lookups,
        "rank_cache_lookup": 3 * t * 64 * h,
        "rank_sort": 3 * t * 128 * h,
        "independent_best_five": 4096 * b * h,
        "fraction_operations": (terminal_fraction + own_profile + own_comparisons +
                                opponent_reach + opponent_sums + reveal_sums + root_sums + 32),
        # Ten result fractions, with separate input/hash encoding receipts.
        "fraction_decimal_character_work": 16 * metric_text_upper,
    }
    hash_entries = 0
    for receipt in final_hash_receipts:
        hash_entries += receipt["entry_delta"]
        for key, count in receipt["counters_delta"].items():
            future[key] = future.get(key, 0) + count
    # Public frames/vectors, opponent reaches, all terminal scratch and the
    # worst-case number of equal-rank buckets. Cumulative allocations are
    # deliberately more conservative than live memory. No Python RSS claim.
    entries = (nodes * (2 * (2 * h0 + 1) + (2 * h1 + 1)) +
               2 * h0 * e0 + 2 * e0 + h1 * e1 + 2 * e1 + 3 * (d0 + d1) +
               2 * (2 * h1 + 1) * e1 + (2 * h0 + 1) * e0 +
               2 * h1 + h0 + 3 +
               2 * terminals * (2 * h1 + h0) + terminals * (2 * h0 + h1) +
               3 * terminals * b +
               t * (128 * (2 * h0 + h1 + 6) + 54 * h + 192) +
               b * h * (RANK_CACHE_ENTRIES + RANK_TEMP_ENTRIES) + hash_entries + 64)
    remaining = sum(future.values())
    _need(budget.work + remaining <= budget.limits["work"],
          "certificate whole-request walk forecast exceeds work limit")
    _need(budget.logical_entries + entries <= budget.limits["entries"],
          "certificate whole-request walk forecast exceeds entry limit")
    return {"public_occurrences": nodes, "terminals": terminals,
            "decision_nodes_by_player": decision_nodes, "decision_edges_by_player": decision_edges,
            "reveal_edges": reveal_edges, "terminal_board_occurrences": t,
            "work_before_walks": budget.work, "entries_before_walks": budget.logical_entries,
            "counters_before_walks": dict(budget.counters),
            "future_work_by_kind_upper": future, "walk_work_upper": remaining,
            "walk_entries_upper": entries, "whole_entries_upper": budget.logical_entries + entries,
            "whole_work_upper": budget.work + remaining,
            "scope": "Named logical construction/arithmetic/encoding envelope; Fraction width and cumulative forecast bits reject dynamically. Not machine instructions, actual Python allocations, runtime or RSS."}


def evaluate_exact(case, payload, *, limits=None, public_limits=None):
    """Certify one inert compact policy; failures do not imply a quality pass."""
    budget = Budget(limits)
    safe_case, case_receipt = clone_json(case, budget)
    safe_policy, input_receipt = clone_json(payload, budget)
    case_hash, case_hash_receipt = canonical_hash(safe_case, budget)
    policy_hash, policy_hash_receipt = canonical_hash(safe_policy, budget)
    model = build_public_model(safe_case, budget, public_limits)
    kernel = PayoffModel(model.ranges, model.outcomes, budget)
    formatter = FractionText(budget)
    policies, normalized, shape = _validate(model, kernel, safe_policy, budget, formatter)
    normalized_hash, normalized_hash_receipt = canonical_hash(normalized, budget)
    forecast = _walk_forecast(model, kernel, budget, (case_hash_receipt, policy_hash_receipt), formatter)
    value = _sum_vector(_walk(model.root, 0, policies, kernel, budget, best_response=False), budget, "profile root sum")
    sb = _sum_vector(_walk(model.root, 0, policies, kernel, budget, best_response=True), budget, "SB response root sum")
    bb = _sum_vector(_walk(model.root, 1, policies, kernel, budget, best_response=True), budget, "BB response root sum")
    negative = budget.neg(value, "BB profile value")
    gain_sb = budget.sub(sb, value, "SB response gain")
    gain_bb = budget.add(bb, value, "BB response gain")
    _need(gain_sb.numerator >= 0 and gain_bb.numerator >= 0,
          "negative exact legal-response gain contradicts profile feasibility")
    nash = budget.add(gain_sb, gain_bb, "NashConv")
    metrics = {"value_sb": value, "value_bb": negative,
               "sb_best_response_value": sb, "bb_best_response_value": bb,
               "sb_best_response_gain": gain_sb, "bb_best_response_gain": gain_bb,
               "nash_conv": nash, "exploitability": budget.div(nash, Fraction(2), "exploitability"),
               "lower_value_bound": budget.neg(bb, "lower response bound"), "upper_value_bound": sb}
    met = budget.compare(nash, THRESHOLD, "fixed quality threshold") <= 0
    metric_text = {key: formatter.format(number) for key, number in metrics.items()}
    after_case_hash, _ = canonical_hash(safe_case, budget)
    after_policy_hash, _ = canonical_hash(safe_policy, budget)
    _need(after_case_hash == case_hash and after_policy_hash == policy_hash,
          "certificate mutated its private input snapshots")
    for key, count in budget.counters.items():
        actual = count - forecast["counters_before_walks"].get(key, 0)
        _need(actual <= forecast["future_work_by_kind_upper"].get(key, 0),
              "actual named work exceeds pre-walk family forecast: " + key)
    _need(budget.work <= forecast["whole_work_upper"] and
          budget.logical_entries <= forecast["whole_entries_upper"],
          "actual work/entries exceed whole-call forecast")
    return {"contract": "matrix-free-selected-certificate-v1", "source_identity": SOURCE_IDENTITY,
            "input_case_canonical_sha256": case_hash, "input_policy_canonical_sha256": policy_hash,
            "normalized_policy_sha256": normalized_hash, "normalized_policy_rows": normalized,
            "metrics": metric_text, "threshold": "1/1000", "threshold_met": met,
            "case_snapshot": case_receipt, "policy_snapshot": input_receipt,
            "case_hash": case_hash_receipt, "policy_hash": policy_hash_receipt,
            "normalized_hash": normalized_hash_receipt, "fraction_text": formatter.receipt(),
            "policy_shape": shape, "public_model": model.counts,
            "operator": kernel.receipt(), "forecast": forecast, "budget": budget.receipt(),
            "production_pair_rows": 0, "training_calls": 0, "native_calls": 0,
            "scope": "Finite selected-product game, normalized serialized binary64 policy and independent public rules/ranks. No full-deck, unrestricted solver, native-memory or commercial-quality claim."}
