"""Fresh physical preparation and candidate partition for the fixed 7c8d9h plan.

This is a bounded reference-preparation layer only. It does not prove a class
quotient, policy equivalence, best-response equality, or training quality.
"""
from collections import defaultdict
from fractions import Fraction
import math

from scripts import flop_multistreet_validation as physical
from scripts import flop_public_classes as structural
from scripts import flop_public_classes_candidate as candidate
from scripts.flop_second_board_plan import (
    RUNOUTS_PER_PAIR, admit_plan, validate_plan,
)


CONFIG = {
    "pot": 10, "effective_stack": 5, "bet_sizes": [0.5],
    "raise_sizes": [], "max_raises": 0, "include_all_in": False,
}
MAX_TREE_DEPTH = 128
MAX_ACTIONS_PER_NODE = 64
MAX_TREE_STACK = MAX_TREE_DEPTH * MAX_ACTIONS_PER_NODE
MAX_PREPARATION_RANK_CALLS = 11_880
MAX_RECHECK_RANK_CALLS = 11_880
EXPECTED_FULL_OUTCOMES_PER_PAIR = RUNOUTS_PER_PAIR
RANKER_DESCRIPTION = "same established preflop_validation independent_rank implementation"


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _canonical_hand(label):
    _need(type(label) is str and len(label) == 4, "Malformed private hand label")
    return "".join(sorted((label[:2], label[2:])))


def _pair_priors(plan):
    validate_plan(plan)
    return {(_canonical_hand(oop), _canonical_hand(ip)): prior
            for oop, ip, prior in plan.exact_pair_priors}


def _validate_world_rows(plan, oracle, *, outcomes_per_pair=RUNOUTS_PER_PAIR):
    """Recheck exact world support, blockers, pair masses and pair counters.

    The smaller outcome-count argument is private and exists only for synthetic
    unit fixtures. The public preparation path always uses all 1,980 outcomes.
    """
    validate_plan(plan)
    _need(type(outcomes_per_pair) is int and outcomes_per_pair > 0,
          "Outcome count must be a positive exact integer")
    priors = _pair_priors(plan)
    board = tuple(plan.board)
    deck = physical.DECK
    _need(type(oracle) is dict, "Physical oracle must be a mapping")
    worlds = oracle.get("worlds")
    _need(type(worlds) is tuple and len(worlds) == len(priors) * outcomes_per_pair,
          "Fresh oracle world count differs from the admitted support")
    expected_support = {}
    for pair in priors:
        private = pair[0][:2], pair[0][2:], pair[1][:2], pair[1][2:]
        remaining = tuple(card for card in deck if card not in set(board + private))
        _need(len(remaining) == 45, "Private pair does not leave 45 cards")
        if outcomes_per_pair == EXPECTED_FULL_OUTCOMES_PER_PAIR:
            expected_support[pair] = {(turn, river) for turn in remaining
                                      for river in remaining if turn != river}
        else:
            expected_support[pair] = None

    seen = set()
    per_pair = defaultdict(list)
    for row in worlds:
        _need(type(row) is tuple and len(row) == 5, "Malformed physical world row")
        oop, ip, mass, sign, full_board = row
        _need(type(oop) is str and type(ip) is str and type(mass) is Fraction
              and type(sign) is int and sign in (-1, 0, 1)
              and type(full_board) is tuple and len(full_board) == 5,
              "Physical world fields have invalid types")
        pair = (oop, ip)
        _need(pair in priors, "World contains an unsupported private pair")
        _need(oop == _canonical_hand(oop) and ip == _canonical_hand(ip),
              "World hands are not physical parser canonical labels")
        _need(full_board[:3] == board and all(type(card) is str and card in deck
              for card in full_board), "World board differs from the fixture or deck")
        oop_cards = (oop[:2], oop[2:])
        ip_cards = (ip[:2], ip[2:])
        _need(len(set(oop_cards)) == len(set(ip_cards)) == 2
              and set(oop_cards).isdisjoint(ip_cards)
              and set(oop_cards + ip_cards).isdisjoint(board),
              "World private cards overlap each other or the flop")
        future = full_board[3:]
        _need(len(set(future)) == 2 and set(future).isdisjoint(board)
              and set(future).isdisjoint(oop_cards + ip_cards),
              "World future cards violate deck blockers")
        _need(mass == priors[pair] / outcomes_per_pair,
              "World mass differs from exact global pair prior")
        key = (pair, future)
        _need(key not in seen, "Duplicate ordered private-pair runout")
        seen.add(key)
        per_pair[pair].append((future, sign))
    for pair, rows in per_pair.items():
        _need(len(rows) == outcomes_per_pair, "Pair outcome count differs")
        if expected_support[pair] is not None:
            _need({future for future, _ in rows} == expected_support[pair],
                  "Pair does not cover every ordered two-card runout")
    _need(set(per_pair) == set(priors), "A compatible pair has no physical support")
    _need(sum((row[2] for row in worlds), Fraction()) == 1,
          "Physical joint world masses do not normalize to one")

    observed_counts = {}
    for pair, rows in per_pair.items():
        signs = [sign for _, sign in rows]
        observed_counts[pair] = (signs.count(1), signs.count(0), signs.count(-1), len(signs))
    counts = oracle.get("counts")
    _need(type(counts) is tuple and len(counts) == len(priors),
          "Physical pair-count metadata has the wrong shape")
    metadata = {}
    for row in counts:
        _need(type(row) is dict, "Malformed pair-count row")
        pair = (_canonical_hand(row.get("oop_hand")),
                _canonical_hand(row.get("ip_hand")))
        _need(pair in priors and pair not in metadata, "Duplicate/unsupported pair metadata")
        metadata[pair] = (
            row.get("wins"), row.get("ties"), row.get("losses"),
            row.get("ordered_outcomes"), row.get("pair_probability_fraction"),
            row.get("pair_probability"))
    _need(set(metadata) == set(priors), "Pair-count metadata omits a compatible pair")
    for pair, observed in observed_counts.items():
        row = metadata[pair]
        _need(all(type(v) is int for v in row[:4]) and row[:4] == observed,
              "Pair sign/count metadata differs from observed worlds")
        _need(row[4] == f"{priors[pair].numerator}/{priors[pair].denominator}"
              and type(row[5]) is float and math.isfinite(row[5])
              and row[5] == float(priors[pair]),
              "Pair prior metadata differs from exact joint prior")
    normalizer = oracle.get("normalizer")
    _need(type(normalizer) is Fraction and
          normalizer == plan.global_blocker_normalizer,
          "Physical oracle normalizer differs from the exact plan")
    return {
        "pair_count": len(priors), "world_count": len(worlds),
        "outcomes_per_pair": outcomes_per_pair,
        "joint_mass": "1/1",
        "pair_sign_counts": [
            {"oop_hand": pair[0], "ip_hand": pair[1],
             "wins": counts_[0], "ties": counts_[1], "losses": counts_[2],
             "ordered_outcomes": counts_[3]}
            for pair, counts_ in sorted(observed_counts.items())],
    }


def _rank_recheck(worlds, ranker=None):
    """Rerank produced rows with a fresh cache using the same reference ranker."""
    if ranker is None:
        ranker = physical.independent_rank
    cache = {}
    comparisons = 0
    for oop, ip, _mass, sign, board in worlds:
        rank_board = tuple(sorted(board, key=physical.DECK_INDEX.__getitem__))
        keys = (tuple((oop[:2], oop[2:])) + rank_board,
                tuple((ip[:2], ip[2:])) + rank_board)
        ranks = []
        for key in keys:
            if key not in cache:
                _need(len(cache) < MAX_RECHECK_RANK_CALLS,
                      "Fresh sign recheck exceeds its 11,880 rank-call allowance")
                cache[key] = ranker(key)
            ranks.append(cache[key])
        _need((ranks[0] > ranks[1]) - (ranks[0] < ranks[1]) == sign,
              "Fresh same-ranker sign recheck differs from world record")
        comparisons += 1
    return {"world_comparisons": comparisons, "unique_rank_calls": len(cache),
            "allowance": MAX_RECHECK_RANK_CALLS,
            "interpretation": "same established reference ranker; consistency check only"}


def _history_cards(history, board):
    _need(type(history) is tuple and len(history) <= 32
          and all(type(token) is str and len(token) <= 256 for token in history),
          "Node history exceeds the public history bound")
    visible = []
    for token in history:
        if token.startswith("turn@") or token.startswith("river@"):
            card = token.split("@", 1)[1]
            _need(card in physical.DECK, "History reveals an invalid public card")
            _need(len(visible) < 2 and card not in visible,
                  "History repeats or over-reveals public cards")
            if token.startswith("river@"):
                _need(len(visible) == 1, "River reveal must follow a turn reveal")
            elif token.startswith("turn@"):
                _need(len(visible) == 0, "Turn reveal appears after another reveal")
            visible.append(card)
        else:
            if token in ("fold", "check", "call"):
                continue
            prefix = next((name for name in ("bet@", "raise@", "all_in@")
                           if token.startswith(name)), None)
            _need(prefix is not None,
                  "History contains an unknown action or private-card token")
            try:
                amount = float(token[len(prefix):])
            except (ValueError, OverflowError):
                raise ValueError("History action token has a malformed amount") from None
            _need(math.isfinite(amount) and amount >= 0,
                  "History action token has a non-finite or negative amount")
    _need(len(set(tuple(board) + tuple(visible))) == len(board) + len(visible),
          "Public history repeats a flop or future card")
    return tuple(visible)


def _bounded_tree(oracle, board):
    """Bounded cycle-free tree walk, index check, and serializable node view."""
    root = oracle.get("root")
    _need(type(root) is physical._Decision and root.player == 0
          and root.street == "flop" and root.history == ()
          and root.board == tuple(board),
          "Numeric tree root is not the requested player-0 flop-start state")
    stack = [(root, 1, False)]
    active, seen, nodes, edges, decision_count = set(), set(), [], 0, 0
    max_depth, max_stack = 0, 1
    while stack:
        node, depth, exiting = stack.pop()
        ident = id(node)
        if exiting:
            active.remove(ident)
            continue
        _need(ident not in active, "Numeric tree contains a cycle")
        _need(ident not in seen, "Numeric structure aliases a node under multiple parents")
        seen.add(ident)
        active.add(ident)
        _need(len(seen) <= physical.MAX_PUBLIC_STATES
              and depth <= MAX_TREE_DEPTH,
              "Numeric tree exceeds explicit node/depth limits")
        nodes.append(node)
        max_depth = max(max_depth, depth)
        children = []
        history = node.history
        visible = _history_cards(history, board)
        if type(node) is physical._Decision:
            decision_count += 1
            _need(type(node.player) is int and node.player in (0, 1)
                  and node.street in ("flop", "turn", "river")
                  and type(node.board) is tuple
                  and all(type(card) is str and card in physical.DECK for card in node.board),
                  "Malformed decision node public state")
            expected_len = {"flop": 3, "turn": 4, "river": 5}[node.street]
            _need(node.board == tuple(board) + visible and len(node.board) == expected_len,
                  "Decision board differs from its public history")
            _need(type(node.actions) is tuple and type(node.children) is tuple
                  and 0 < len(node.actions) == len(node.children) <= MAX_ACTIONS_PER_NODE,
                  "Decision action/child structure is malformed or oversized")
            _need(decision_count <= physical.MAX_DECISIONS,
                  "Numeric tree exceeds the decision-node cap")
            for action, child in zip(node.actions, node.children):
                _need(type(action) is dict and set(action) ==
                      {"name", "amount", "raise_to", "history_key", "full_raise"}
                      and type(action["name"]) is str
                      and action["name"] in ("check", "fold", "call", "bet", "all_in")
                      and type(action["history_key"]) is str
                      and len(action["history_key"]) <= 256
                      and type(action["amount"]) is float
                      and math.isfinite(action["amount"]) and action["amount"] >= 0
                      and type(action["raise_to"]) is float
                      and math.isfinite(action["raise_to"]) and action["raise_to"] >= 0
                      and type(action["full_raise"]) is bool,
                      "Decision contains malformed or unbounded action metadata")
                name = action["name"]
                expected_key = name if name in ("check", "fold", "call") else name + "@"
                _need((name in ("check", "fold", "call")
                       and action["history_key"] == expected_key)
                      or (name in ("bet", "all_in")
                          and action["history_key"].startswith(expected_key)),
                      "Action name and public history key disagree")
                if name == "fold":
                    _need(type(child) is physical._Terminal and child.kind == "fold"
                          and child.history == history and child.winner == 1 - node.player,
                          "Fold terminal must retain the decision's parent history")
                else:
                    _need(child.history == history + (action["history_key"],),
                          "Non-fold child history must append the selected action")
            children = list(node.children)
            _need(len(node.actions) == 2,
                  "Fixed no-raise half-pot decision must retain two legal choices")
        elif type(node) is physical._Chance:
            _need(node.street in ("turn", "river") and type(node.card_index) is int
                  and node.card_index == (3 if node.street == "turn" else 4)
                  and type(node.branches) is dict and 0 < len(node.branches) <= 49,
                  "Malformed or oversized public chance node")
            token = "turn@" if node.street == "turn" else "river@"
            _need(len(visible) == (0 if node.street == "turn" else 1),
                  "Chance street differs from visible-card history")
            for card, child in node.branches.items():
                _need(type(card) is str and card in physical.DECK
                      and card not in tuple(board) + visible,
                      "Chance branch reveals an unavailable public card")
                _need(type(child) in (physical._Decision, physical._Chance, physical._Terminal)
                      and child.history == history + (token + card,),
                      "Chance child history does not reveal its branch card")
                children.append(child)
        elif type(node) is physical._Terminal:
            visible_count = len(visible)
            _need(node.kind in ("fold", "showdown")
                  and type(node.contributions) is tuple and len(node.contributions) == 2
                  and all(type(value) in (int, float) and math.isfinite(value)
                          and value >= 0 for value in node.contributions)
                  and ((node.kind == "fold" and type(node.winner) is int
                        and node.winner in (0, 1))
                       or (node.kind == "showdown" and node.winner is None
                           and visible_count == 2)),
                  "Malformed public terminal node")
        else:
            raise ValueError("Unknown public node type")
        stack.append((node, depth, True))
        edges += len(children)
        _need(edges <= physical.MAX_PUBLIC_STATES * MAX_ACTIONS_PER_NODE,
              "Numeric tree edge count exceeds its explicit bound")
        for child in reversed(children):
            stack.append((child, depth + 1, False))
        _need(len(stack) <= MAX_TREE_STACK,
              "Numeric tree traversal stack exceeds its explicit bound")
        max_stack = max(max_stack, len(stack))

    decisions = [node for node in nodes if type(node) is physical._Decision]
    expected_index = {}
    for node in decisions:
        key = (node.player, node.history)
        _need(key not in expected_index, "Duplicate rooted public decision index key")
        expected_index[key] = node
    actual_index = oracle.get("nodes")
    _need(type(actual_index) is dict and set(actual_index) == set(expected_index)
          and all(actual_index[key] is node for key, node in expected_index.items()),
          "Physical decision index does not point to every rooted node exactly")
    id_by_object = {id(node): index for index, node in enumerate(nodes)}
    view = []
    for index, node in enumerate(nodes):
        if type(node) is physical._Decision:
            view.append({"id": index, "kind": "decision", "history": list(node.history),
                         "player": node.player, "street": node.street,
                         "board": list(node.board), "actions": [dict(a) for a in node.actions],
                         "children": [id_by_object[id(child)] for child in node.children]})
        elif type(node) is physical._Chance:
            view.append({"id": index, "kind": "chance", "history": list(node.history),
                         "card_index": node.card_index, "street": node.street,
                         "branches": [[card, id_by_object[id(child)]]
                                      for card, child in sorted(node.branches.items())]})
        else:
            view.append({"id": index, "kind": "terminal", "history": list(node.history),
                         "terminal_kind": node.kind, "contributions": list(node.contributions),
                         "winner": node.winner})
    # The recursive generic structure serializer runs only after the bounded walk.
    structure_hash = structural._digest(structural._structure(root))
    return view, structure_hash, {
        "public_states": len(nodes), "decision_nodes": len(decisions),
        "chance_nodes": sum(type(node) is physical._Chance for node in nodes),
        "terminal_nodes": sum(type(node) is physical._Terminal for node in nodes),
        "tree_edges": edges, "maximum_depth": max_depth,
        "maximum_stack": max_stack, "stack_cap": MAX_TREE_STACK,
    }


def _metadata_check(plan, oracle, tree_census, preparation_rank_calls):
    worlds = oracle["worlds"]
    _need(oracle.get("deals") is worlds and oracle.get("pair_counts") is oracle.get("counts"),
          "Physical world/count aliases differ")
    _need(oracle.get("board") == tuple(plan.board)
          and oracle.get("normalizer") == plan.global_blocker_normalizer
          and oracle.get("runout_mode") == "full-deck"
          and type(oracle.get("worlds_count")) is int
          and oracle["worlds_count"] == len(worlds)
          and type(oracle.get("physical_worlds")) is int
          and oracle["physical_worlds"] == len(worlds)
          and type(oracle.get("compatible_pairs")) is int
          and oracle["compatible_pairs"] == len(plan.exact_pair_priors),
          "Physical oracle header differs from fresh plan/support")
    board_remaining = tuple(card for card in physical.DECK if card not in plan.board)
    expected_runouts = tuple((turn, river) for turn in board_remaining
                             for river in board_remaining if turn != river)
    _need(oracle.get("runouts") == expected_runouts,
          "Physical oracle did not enumerate the complete ordered runout set")
    actual_reachable = tuple(sorted({world[4][3:] for world in worlds},
                                    key=lambda runout: tuple(
                                        physical.DECK_INDEX[card] for card in runout)))
    _need(oracle.get("reachable_runouts") == actual_reachable,
          "Reachable-runout metadata differs from produced worlds")
    normalized = physical._configuration(CONFIG)
    public_config = physical._public_config(normalized)
    _need(oracle.get("config") == public_config
          and type(oracle.get("street_configs")) is dict
          and set(oracle["street_configs"]) == {"flop", "turn", "river"}
          and all(oracle["street_configs"][street] == public_config
                  for street in ("flop", "turn", "river")),
          "Oracle street configuration differs from the fixed no-raise game")
    _need(oracle.get("pot") == 10.0 and oracle.get("effective_stack") == [5.0, 5.0],
          "Oracle pot or effective-stack metadata differs")

    expected_world_count = {pair[0] + "/" + pair[1]: RUNOUTS_PER_PAIR
                            for pair in _pair_priors(plan)}
    _need(oracle.get("world_count_per_pair") == expected_world_count,
          "Physical per-pair support counters differ")
    expected_pair_probabilities = {pair: float(prior)
                                   for pair, prior in _pair_priors(plan).items()}
    _need(type(oracle.get("pair_probabilities")) is dict
          and oracle["pair_probabilities"] == expected_pair_probabilities
          and all(type(value) is float and math.isfinite(value)
                  for value in oracle["pair_probabilities"].values()),
          "Physical pair-probability metadata differs from exact priors")
    rank_keys = set()
    for oop, ip, _mass, _sign, full_board in worlds:
        rank_board = tuple(sorted(full_board, key=physical.DECK_INDEX.__getitem__))
        rank_keys.add((oop[:2], oop[2:]) + rank_board)
        rank_keys.add((ip[:2], ip[2:]) + rank_board)
    counters = oracle.get("source_counters")
    _need(type(counters) is dict and counters == {
        "rank_hand_calls": len(rank_keys), "physical_world_rows": len(worlds),
        "pair_runout_rows_checked": len(worlds),
        "world_count_by_pair": expected_world_count},
        "Physical preparation source counters differ from independently counted rows")
    _need(type(counters["rank_hand_calls"]) is int
          and counters["rank_hand_calls"] <= MAX_PREPARATION_RANK_CALLS
          and counters["rank_hand_calls"] == preparation_rank_calls,
          "Preparation ranking count differs from the reversible call counter")
    for metadata_key, census_key in (
        ("public_states", "public_states"), ("public_nodes", "decision_nodes"),
        ("chance_nodes", "chance_nodes"), ("terminal_nodes", "terminal_nodes"),
    ):
        _need(type(oracle.get(metadata_key)) is int
              and oracle[metadata_key] == tree_census[census_key],
              "Physical tree metadata differs from the bounded traversal census")
    return {"normalizer": f"{plan.global_blocker_normalizer.numerator}/"
            f"{plan.global_blocker_normalizer.denominator}",
            "world_count_by_pair": expected_world_count,
            "preparation_rank_calls": counters["rank_hand_calls"],
            "preparation_rank_call_allowance": MAX_PREPARATION_RANK_CALLS}


def _plan_record(plan):
    return {
        "board": list(plan.board),
        "oop_literal_range": [[label, f"{weight.numerator}/{weight.denominator}"]
                              for label, weight in plan.oop_ranges],
        "ip_literal_range": [[label, f"{weight.numerator}/{weight.denominator}"]
                             for label, weight in plan.ip_ranges],
        "compatible_pair_raw_products": [
            [oop, ip, f"{mass.numerator}/{mass.denominator}"]
            for oop, ip, mass in plan.compatible_pair_raw_products],
        "global_blocker_normalizer":
            f"{plan.global_blocker_normalizer.numerator}/"
            f"{plan.global_blocker_normalizer.denominator}",
        "exact_pair_priors": [[oop, ip, f"{mass.numerator}/{mass.denominator}"]
                              for oop, ip, mass in plan.exact_pair_priors],
        "canonical_pair_identities": [list(row)
                                      for row in plan.canonical_pair_identities],
        "ordered_runouts_per_pair": plan.ordered_runouts_per_pair,
        "distinct_turn_card_forecast": plan.distinct_turn_card_forecast,
        "physical_world_forecast": plan.physical_world_forecast,
        "scope": plan.scope,
    }


def prepare_reference(plan, *, progress=None):
    """Build one fresh physical oracle and candidate partition after admission.

    Optional ``progress`` receives JSON-friendly partial phase/counter receipts,
    including attempted and actual ranker calls if a later phase fails.
    """
    return _prepare_reference(plan, progress=progress)


def _prepare_reference(plan, *, progress=None):
    """Implementation split out so tests can instrument every call boundary."""
    if progress is not None and type(progress) is not dict:
        raise ValueError("progress must be an exact mutable dict or None")
    receipt = progress if progress is not None else {}
    receipt.update({
        "phase": "plan-validation", "preparation_ranker_attempts": 0,
        "preparation_rank_calls": 0, "recheck_ranker_attempts": 0,
        "recheck_rank_calls": 0, "physical_world_rows": 0,
        "world_rows_validated": 0, "tree_nodes_validated": 0,
        "candidate_world_rows": 0, "physical_builds_attempted": 0,
        "physical_builds_completed": 0, "candidate_builds_attempted": 0,
        "candidate_builds_completed": 0,
    })
    checked = validate_plan(plan)
    admission = admit_plan(checked)
    receipt["phase"] = "physical-preparation"
    oop_rows = [[label, f"{weight.numerator}/{weight.denominator}"]
                for label, weight in checked.oop_ranges]
    ip_rows = [[label, f"{weight.numerator}/{weight.denominator}"]
               for label, weight in checked.ip_ranges]
    original_ranker = physical.independent_rank
    prep_attempts = prep_calls = 0

    def preparation_ranker(key):
        nonlocal prep_attempts, prep_calls
        prep_attempts += 1
        receipt["preparation_ranker_attempts"] = prep_attempts
        if prep_attempts > MAX_PREPARATION_RANK_CALLS:
            raise ValueError("Physical preparation exceeded its rank-call allowance")
        prep_calls += 1
        receipt["preparation_rank_calls"] = prep_calls
        return original_ranker(key)

    physical.independent_rank = preparation_ranker
    try:
        receipt["physical_builds_attempted"] += 1
        oracle = physical.prepare_oracle(checked.board, oop_rows, ip_rows, dict(CONFIG))
        receipt["physical_builds_completed"] += 1
    finally:
        physical.independent_rank = original_ranker
    receipt["physical_world_rows"] = len(oracle.get("worlds", ()))
    receipt["phase"] = "world-support-validation"
    world_summary = _validate_world_rows(
        checked, oracle, outcomes_per_pair=RUNOUTS_PER_PAIR)
    receipt["world_rows_validated"] = world_summary["world_count"]
    receipt["phase"] = "same-ranker-sign-recheck"
    original_ranker = physical.independent_rank
    recheck_attempts = recheck_calls = 0

    def recheck_ranker(key):
        nonlocal recheck_attempts, recheck_calls
        recheck_attempts += 1
        receipt["recheck_ranker_attempts"] = recheck_attempts
        if recheck_attempts > MAX_RECHECK_RANK_CALLS:
            raise ValueError("Fresh sign recheck exceeded its rank-call allowance")
        recheck_calls += 1
        receipt["recheck_rank_calls"] = recheck_calls
        return original_ranker(key)

    reference_recheck = _rank_recheck(oracle["worlds"], ranker=recheck_ranker)
    _need(reference_recheck["unique_rank_calls"] == recheck_calls,
          "Fresh sign recheck counter differs from its cache")
    receipt["phase"] = "bounded-tree-validation"
    tree_view, tree_sha256, tree_census = _bounded_tree(oracle, checked.board)
    receipt["tree_nodes_validated"] = tree_census["public_states"]
    metadata = _metadata_check(checked, oracle, tree_census, prep_calls)
    world_view = [[oop, ip, mass.numerator, mass.denominator, sign, list(board)]
                  for oop, ip, mass, sign, board in oracle["worlds"]]
    world_sha256 = structural._digest(world_view)
    receipt["phase"] = "candidate-partition"
    receipt["candidate_world_rows"] = len(oracle["worlds"])
    receipt["candidate_builds_attempted"] += 1
    class_candidate = candidate.build_candidate(
        [[oop, ip, str(mass), sign, list(board)]
         for oop, ip, mass, sign, board in oracle["worlds"]],
        board=checked.board)
    receipt["candidate_builds_completed"] += 1
    _need(class_candidate.get("candidate_only") is True
          and class_candidate.get("physical_provenance") is False
          and class_candidate.get("input_completeness") ==
          "unverified-caller-supplied-records",
          "Candidate partition provenance flags changed")
    receipt["phase"] = "complete"
    return {
        "scope": "fresh-physical-reference-and-candidate-partition-only",
        "plan": _plan_record(checked),
        "admission": admission,
        "physical": {
            "normalizer": metadata["normalizer"],
            "worlds_sha256": world_sha256,
            "tree_sha256": tree_sha256,
            "worlds_view": world_view,
            "tree_view": tree_view,
            "world_summary": world_summary,
            "metadata_counters": metadata,
            "same_ranker_recheck": reference_recheck,
            "tree_census": tree_census,
        },
        "candidate_partition": class_candidate,
        "claims": {
            "class_or_tree_equivalence_proved": False,
            "policy_projection_or_lift_proved": False,
            "physical_best_response_equality_proved": False,
            "training_performed": False,
        },
    }
