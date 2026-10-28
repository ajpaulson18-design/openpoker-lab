"""Authenticate a saved frontier, then independently count its bounded graph.

This reviewer never imports repository code. Structural acceptance is conditional
on the exported graph; it is not independent betting-game legality or quality.
Execute only after the lead confirms terminal completion and external pins.
"""
import argparse
import ast
from collections import Counter, deque
import hashlib
import importlib.util
from itertools import combinations, permutations, islice
import json
import math
from pathlib import Path
import re
from unittest.mock import patch

AUTH_SHA = "8171ead3ba108f8200f15e85696f40d109ed894209fa7d77598780b83c1401c5"
DECK = tuple(r + s for r in "23456789TJQKA" for s in "cdhs")
ORDER = {card: index for index, card in enumerate(DECK)}
STREETS = ("preflop", "flop", "turn", "river")
CALLS = {name: 0 for name in ("training_calls", "rank_calls", "pair_query_calls", "terminal_query_calls",
    "marginal_query_calls", "native_calls", "world_producer_calls", "popen_calls")}
CAPS = {"hands_per_player": 4, "selected_boards": 8, "physical_worlds": 32,
    "states": 2048, "policy_rows": 2048, "action_slots": 4096}
LIMITS = {"vertices": 250000, "edges": 250000, "logical_visits": 250000, "depth": 256,
    "rows": 2000000, "modeled_work": 500000000, "entries": 2000000,
    "history_bytes": 16000000, "hands_per_seat": 16, "boards": 48,
    "token_bytes": 64, "file_bytes": 64000000, "study_bytes": 256000000}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, label, maximum=None):
    need(type(value) is int and value >= 0 and (maximum is None or value <= maximum), "invalid bounded integer: " + label)
    return value


def token(value):
    need(type(value) is str and 0 < len(value.encode("utf-8")) <= LIMITS["token_bytes"], "invalid bounded history token")
    return value


def float_hex(value):
    need(type(value) is str and 0 < len(value) <= 64, "invalid float hex token")
    try:
        result = float.fromhex(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError("invalid binary64 witness value") from exc
    need(math.isfinite(result) and result >= 0 and result.hex() == value, "noncanonical/nonfinite/negative binary64 witness value")
    return result


def parse_range(text):
    """Independent restricted grammar: concrete two-card holdings and weights."""
    need(type(text) is str and 0 < len(text) <= 4096, "range text outside structural verification cap")
    result = {}
    for part in re.split(r"[\s,]+", text.strip()):
        match = re.fullmatch(r"([2-9TJQKA][cdhs])([2-9TJQKA][cdhs])(?::([^:]+))?", part)
        need(match is not None, "structural reviewer supports only fixed concrete range tokens")
        hand = tuple(sorted(match.group(1, 2)))
        need(hand[0] != hand[1], "duplicate card within private holding")
        weight = float(match.group(3)) if match.group(3) is not None else 1.0
        need(math.isfinite(weight) and 0 <= weight <= 1, "invalid private weight")
        if weight:
            result[hand] = weight.hex()
        else:
            result.pop(hand, None)
        need(len(result) <= LIMITS["hands_per_seat"], "new structural verifier private-range cap exceeded")
    need(result, "empty private range")
    return result


def board(value):
    cards = tuple(value[index:index+2] for index in range(0, 10, 2)) if type(value) is str else tuple(value)
    need(len(cards) == 5 and all(type(card) is str and card in ORDER for card in cards) and len(set(cards)) == 5,
         "invalid five-card selected outcome")
    return tuple(sorted(cards[:3], key=ORDER.__getitem__)) + cards[3:]


def boards(values):
    need(type(values) is list and 0 < len(values) <= LIMITS["boards"], "new structural verifier selected-board cap exceeded")
    result = tuple(board(value) for value in values)
    need(len(set(result)) == len(result), "duplicate canonical ordered selected outcome")
    return result


def board_prefixes(outcome):
    return ((), ("".join(outcome[:3]),), ("".join(outcome[:3]), outcome[3]),
            ("".join(outcome[:3]), outcome[3], outcome[4]))


def fixture_request(sb, bb, outcomes, *, stacks=(8, 8), raises=0, preflop_raises=1):
    actions = {"bet_sizes": [.5], "raise_sizes": [.5] if raises else [], "max_raises": raises, "include_all_in": False}
    return {"sb_range": sb, "bb_range": bb, "runouts": ["".join(value) for value in outcomes],
        "preflop_config": {"small_blind": .5, "big_blind": 1., "starting_stack": list(stacks),
            "raise_sizes": [.5], "max_raises": preflop_raises, "include_all_in": False},
        "flop_actions": actions, "turn_actions": dict(actions), "river_actions": dict(actions),
        "iterations": 10, "algorithm": "cfrplus", "traversal": "public-batched",
        "diagnostics": "public-batched", "resource_model": "public-vector"}


def fixed_cases(repo, parse):
    """Build the schedule from independent constants and authenticated data."""
    pool0, pool1, later = DECK[:12], DECK[12:24], DECK[27:]
    outcomes = tuple(DECK[24:27] + pair for pair in islice(permutations(later, 2), 48))
    def ranges(pool, count):
        return ",".join("".join(hand) for hand in islice(combinations(pool, 2), count))
    result = []
    for count in (1, 2, 4, 8, 16):
        result.append({"id": f"range-scale-{count}", "axis": "private_range_scale",
            "parameters": {"hands_per_seat": count, "boards": 6, "postflop_max_raises": 0},
            "request": fixture_request(ranges(pool0, count), ranges(pool1, count), outcomes[:6])})
    for count in (1, 6, 12, 24, 48):
        result.append({"id": f"board-scale-{count}", "axis": "selected_board_scale",
            "parameters": {"hands_per_seat": 4, "boards": count, "postflop_max_raises": 0},
            "request": fixture_request(ranges(pool0, 4), ranges(pool1, 4), outcomes[:count])})
    for raises in (0, 1, 2):
        result.append({"id": f"menu-scale-{raises}", "axis": "betting_history_scale",
            "parameters": {"hands_per_seat": 4, "boards": 6, "postflop_max_raises": raises},
            "request": fixture_request(ranges(pool0, 4), ranges(pool1, 4), outcomes[:6], raises=raises)})
    held = parse((repo / "benchmarks/results/native-selected-heldout-v1/study-receipt.json").read_bytes())["case"]
    original = parse((repo / "benchmarks/four-street-integration-v1.json").read_bytes())["case"]
    result.append({"id": "heldout-96-worlds", "axis": "heldout_reference",
        "parameters": {"hands_per_seat": 4, "boards": 6, "flops": 2, "represented_worlds_expected": 96},
        "request": fixture_request(held["sb_range"], held["bb_range"], held["runouts"],
            stacks=held["config"]["starting_stack"], preflop_raises=held["config"]["max_raises"])})
    result.append({"id": "original-22-world-anchor", "axis": "original_anchor",
        "parameters": {"hands_per_seat": 2, "boards": len(original["runouts"]), "worlds_expected": 22},
        "request": fixture_request(original["sb_range"], original["bb_range"], original["runouts"],
            stacks=original["config"]["starting_stack"], raises=original["flop_config"]["max_raises"],
            preflop_raises=original["config"]["max_raises"])})
    symmetry = ("2c3c4h5s6h", "2d3d4h5s6h")
    for name, priors, counterpart in (("symmetric", ("AcAh:1,AdAh:1", "KcKh:1,KdKh:1"), "range-weights-broken"),
            ("weight-broken", ("AcAh:0.7,AdAh:0.3", "KcKh:0.4,KdKh:0.6"), "invariant-ranges-and-boards")):
        result.append({"id": "club-diamond-" + name, "axis": "suit_symmetry_control",
            "parameters": {"selected_boards": list(symmetry), "ranges": list(priors), "counterpart": counterpart},
            "request": fixture_request(*priors, symmetry, stacks=(2, 2))})
    return result


def graph_shape(witness, request):
    need(type(witness) is dict and set(witness) == {"contract", "root_id", "initial_history", "vertices", "ranges", "selected_runouts", "scope"}
         and witness["contract"] == "exact-selected-structural-witness-v1", "witness schema drift")
    need(witness["initial_history"] == [], "fixed whole-game preflop fixture has unexpected initial history")
    priors = (parse_range(request["sb_range"]), parse_range(request["bb_range"]))
    expected_ranges = [[{"hand": "".join(hand), "weight_hex": weight} for hand, weight in side.items()] for side in priors]
    need(witness["ranges"] == expected_ranges, "witness ordered private inputs differ from protocol request")
    selected = boards(request["runouts"])
    need(witness["selected_runouts"] == [list(value) for value in selected], "witness selected outcomes differ from canonical requested outcomes")
    vertices = witness["vertices"]
    need(type(vertices) is list and 0 < len(vertices) <= LIMITS["vertices"], "new structural verifier vertex cap exceeded")
    root = integer(witness["root_id"], "root", len(vertices) - 1)
    # Reject adjacency/DP growth before making any graph-sized copies.
    declared_edges = 0
    for value in vertices:
        need(type(value) is dict, "non-object graph vertex")
        outgoing = value.get("children") if value.get("kind") == "decision" else value.get("branches") if value.get("kind") == "chance" else []
        need(type(outgoing) is list and len(outgoing) <= 48, "unbounded vertex outdegree")
        declared_edges += len(outgoing)
    need(declared_edges <= LIMITS["edges"] and 16 * (len(vertices) + declared_edges) + 8192 <= LIMITS["entries"],
         "new structural verifier adjacency/DP entry admission exceeded before graph copies")
    edges = []
    max_actions = 0
    money_cap = max(request["preflop_config"]["starting_stack"])
    for value in vertices:
        need(type(value) is dict, "non-object graph vertex")
        kind = value.get("kind")
        outgoing = []
        if kind == "decision":
            need(set(value) == {"kind", "player", "actions", "children"} and type(value["player"]) is int and value["player"] in (0, 1), "invalid decision schema/player")
            actions, children = value["actions"], value["children"]
            need(type(actions) is list and type(children) is list and 0 < len(actions) == len(children) <= 32, "invalid bounded decision menu")
            tokens = []
            for action, child in zip(actions, children):
                need(type(action) is dict and set(action) == {"name", "amount_hex", "raise_to_hex", "full_raise", "token"}, "invalid action schema")
                need(action["name"] in ("fold", "check", "call", "bet", "raise", "all_in") and type(action["full_raise"]) is bool, "invalid action fields")
                amount, target = float_hex(action["amount_hex"]), float_hex(action["raise_to_hex"])
                need(max(amount, target) <= money_cap + 1e-9, "action money exceeds declared starting-stack upper")
                text = token(action["token"])
                need(not text.startswith(("flop@", "turn@", "river@")), "decision action impersonates public reveal")
                if action["name"] in ("fold", "check", "call"):
                    need(text == action["name"], "plain action token/name mismatch")
                else:
                    need(text.startswith(action["name"] + "@"), "sized action token/name mismatch")
                tokens.append(text)
                outgoing.append((integer(child, "decision child", len(vertices)-1), text))
            need(len(set(tokens)) == len(tokens), "duplicate action history tokens")
            max_actions = max(max_actions, len(actions))
        elif kind == "chance":
            need(set(value) == {"kind", "street", "card_index", "branches"} and value["street"] in STREETS[1:]
                 and type(value["card_index"]) is int and value["card_index"] == {"flop": 4, "turn": 5, "river": 6}[value["street"]], "invalid chance schema/street/index")
            branches = value["branches"]
            need(type(branches) is list and 0 < len(branches) <= LIMITS["boards"], "invalid chance branch count")
            tokens = []
            for branch in branches:
                need(type(branch) is list and len(branch) == 2, "invalid chance branch")
                text = token(branch[0]);tokens.append(text)
                if value["street"] == "flop":
                    cards = tuple(text[index:index+2] for index in (0, 2, 4))
                    need(len(text) == 6 and all(card in ORDER for card in cards) and len(set(cards)) == 3 and
                         cards == tuple(sorted(cards, key=ORDER.__getitem__)), "noncanonical flop branch")
                else:
                    need(text in ORDER, "invalid turn/river branch card")
                outgoing.append((integer(branch[1], "chance child", len(vertices)-1), value["street"] + "@" + text))
            need(len(set(tokens)) == len(tokens), "duplicate chance branches")
        elif kind == "terminal":
            need(set(value) == {"kind", "terminal_kind", "winner", "contributions_hex"} and
                 value["terminal_kind"] in ("fold", "showdown"), "invalid terminal schema")
            winner = value["winner"]
            need((type(winner) is int and winner in (0, 1)) if value["terminal_kind"] == "fold" else winner is None, "invalid terminal winner")
            need(type(value["contributions_hex"]) is list and len(value["contributions_hex"]) == 2, "invalid terminal contribution shape")
            contributions = [float_hex(item) for item in value["contributions_hex"]]
            need(all(value <= limit + 1e-9 for value, limit in zip(contributions, request["preflop_config"]["starting_stack"])),
                 "terminal contributions exceed declared role-specific starting stacks")
        else:
            raise ValueError("unsupported graph vertex kind")
        edges.append(outgoing)
    edge_count = sum(map(len, edges))
    need(edge_count <= LIMITS["edges"], "new structural verifier edge cap exceeded")
    # Kahn order proves acyclicity without recursion or production cursors.
    indegree = [0] * len(vertices)
    for outgoing in edges:
        for child, _ in outgoing:indegree[child] += 1
    pending = deque(index for index, degree in enumerate(indegree) if degree == 0)
    order = []
    while pending:
        index = pending.popleft();order.append(index)
        for child, _ in edges[index]:
            indegree[child] -= 1
            if indegree[child] == 0:pending.append(child)
    need(len(order) == len(vertices), "cyclic exported topology")
    count = [0] * len(vertices);depth = [0] * len(vertices)
    lengths = [0] * len(vertices);byte_lengths = [0] * len(vertices)
    count[root] = 1
    for index in order:
        need(count[index] > 0, "exported topology includes unreachable vertices")
        for child, text in edges[index]:
            count[child] += count[index]
            lengths[child] += lengths[index] + count[index]
            byte_lengths[child] += byte_lengths[index] + count[index] * len(text.encode("utf-8"))
            depth[child] = max(depth[child], depth[index] + 1)
            need(count[child] <= LIMITS["logical_visits"] and depth[child] <= LIMITS["depth"], "expanded path/depth bound exceeded before history traversal")
    logical = sum(count)
    need(logical <= LIMITS["logical_visits"], "expanded logical-visit cap exceeded before history traversal")
    hcounts = list(map(len, priors))
    dense = sum(count[index] * hcounts[value["player"]] for index, value in enumerate(vertices) if value["kind"] == "decision")
    dense_actions = sum(count[index] * hcounts[value["player"]] * len(value["actions"]) for index, value in enumerate(vertices) if value["kind"] == "decision")
    history_upper = sum(lengths[index] * hcounts[value["player"]] for index, value in enumerate(vertices) if value["kind"] == "decision")
    bytes_upper = sum(byte_lengths[index] * hcounts[value["player"]] for index, value in enumerate(vertices) if value["kind"] == "decision")
    all_history_tokens = sum(lengths)
    all_history_bytes = sum(byte_lengths)
    # Explicit verifier-only logical entries: graph/DP scratch, occurrence
    # contexts, supported row+history keys, orbit sets, and transform scratch.
    pending_history_scratch = 4 * (max(depth) + 1) ** 2 * (max(map(len, edges), default=0) + 1)
    entries_upper = (16 * (len(vertices) + edge_count) + 12 * logical + 24 * dense + 2 * history_upper +
        128 * max(depth) + pending_history_scratch + 8 * logical + 2 * all_history_tokens + 8192)
    work_upper = (48 * len(selected) * hcounts[0] * hcounts[1] +
        24 * (12 * history_upper + 64 * dense + 8 * sum(hcounts) + 16 * len(selected)) +
        8 * logical * (max(depth) + 16) + 32 * (len(vertices) + edge_count) +
        24 * (12 * all_history_tokens + 32 * logical))
    need(dense <= LIMITS["rows"] and bytes_upper + all_history_bytes <= LIMITS["history_bytes"] and
         entries_upper <= LIMITS["entries"] and work_upper <= LIMITS["modeled_work"], "new structural verifier row/history/entry/work admission exceeded before expanded rows/orbits")
    return priors, selected, vertices, edges, root, {"logical_visits": logical, "maximum_depth": max(depth),
        "dense_slots": dense, "dense_action_slots_upper": dense_actions, "history_token_entries_upper": history_upper,
        "history_token_bytes_upper": bytes_upper, "retained_entries_upper": entries_upper, "modeled_work_upper": work_upper,
        "all_public_history_tokens": all_history_tokens, "all_public_history_bytes": all_history_bytes,
        "unique_vertices": len(vertices), "unique_edges": edge_count}


def transformed_history(history, suit_map):
    result = []
    for text in history:
        if text.startswith("flop@"):
            cards = (text[index:index+2] for index in (5, 7, 9))
            changed = sorted((card[0] + suit_map[card[1]] for card in cards), key=ORDER.__getitem__)
            result.append("flop@" + "".join(changed))
        elif text.startswith(("turn@", "river@")):
            result.append(text[:-1] + suit_map[text[-1]])
        else:
            result.append(text)
    return tuple(result)


def replay(witness, request):
    priors, selected, vertices, edges, root, admission = graph_shape(witness, request)
    # Verification-only literal compatibility; no production probability law,
    # ranks, cursor, or pair queries are called.
    support = {prefix: (set(), set()) for outcome in selected for prefix in board_prefixes(outcome)}
    reachable = set();worlds = 0;pair_board_checks = 0
    for hand0 in priors[0]:
        for hand1 in priors[1]:
            private = set(hand0 + hand1)
            for outcome in selected:
                pair_board_checks += 1
                if len(private) != 4 or private.intersection(outcome):continue
                worlds += 1;reachable.add(outcome)
                for prefix in board_prefixes(outcome):
                    support[prefix][0].add(hand0);support[prefix][1].add(hand1)
    need(worlds > 0, "witness has no literal compatible complete deal")
    groups = []
    for image in permutations("cdhs"):
        suit_map = dict(zip("cdhs", image))
        def hand_map(hand):return tuple(sorted(card[0] + suit_map[card[1]] for card in hand))
        if any({hand_map(hand): weight for hand, weight in side.items()} != side for side in priors):continue
        changed = {tuple(sorted((card[0] + suit_map[card[1]] for card in outcome[:3]), key=ORDER.__getitem__)) +
            tuple(card[0] + suit_map[card[1]] for card in outcome[3:]) for outcome in selected}
        if changed == set(selected):groups.append(("".join(image), suit_map))
    need(groups and groups[0][0] == "cdhs", "weighted selected game lost identity suit stabilizer")
    row_counts, slot_counts, orbit_rows = Counter(), Counter(), {}
    row_menus = {};public_signatures = {};contexts = set();context_edges = set()
    # Canonical action-menu tuples are stored once per unique vertex; histories
    # and private rows retain references rather than duplicate action vectors.
    menus = {index: tuple((a["name"], a["amount_hex"], a["raise_to_hex"], a["full_raise"], a["token"])
        for a in value["actions"]) for index, value in enumerate(vertices) if value["kind"] == "decision"}
    rows = slots = histories = history_bytes = visits = dense = maximum_depth = orbit_work = 0
    # Independent DFS stores only the current public path plus admitted row
    # identities required for the explicit S4 menu-closure check.
    pending = [(root, (), (), None, 0)]
    while pending:
        index, history, prefix, parent, depth = pending.pop()
        visits += 1;maximum_depth = max(maximum_depth, depth)
        context = (index, prefix);contexts.add(context)
        if parent is not None:context_edges.add((parent, history[-1], context))
        need(prefix in support, "public history reveals a prefix outside selected outcomes")
        value = vertices[index]
        need(history not in public_signatures, "duplicate full public-history node identity")
        if value["kind"] == "chance":
            next_depth = {"flop": 0, "turn": 1, "river": 2}[value["street"]]
            need(len(prefix) == next_depth, "chance node reveals future cards out of sequence")
            expected = {board_prefixes(outcome)[next_depth + 1][-1] for outcome in reachable
                if board_prefixes(outcome)[next_depth] == prefix}
            need({branch[0] for branch in value["branches"]} == expected, "chance branches differ from independent reachable selected outcomes")
            public_signatures[history] = ("chance", value["street"], value["card_index"], tuple(sorted(branch[0] for branch in value["branches"])))
        elif value["kind"] == "decision":
            player = value["player"];live = support[prefix][player]
            group = (STREETS[len(prefix)], player)
            dense += len(priors[player]);row_counts[group] += len(live)
            slot_counts[group] += len(live) * len(value["actions"])
            rows += len(live);slots += len(live) * len(value["actions"])
            histories += len(live) * len(history)
            history_bytes += len(live) * sum(len(text.encode("utf-8")) for text in history)
            menu = menus[index]
            public_signatures[history] = ("decision", player, menu)
            for hand in live:
                key = (player, hand, history)
                need(key not in row_menus, "duplicate full-history information-row identity")
                row_menus[key] = menu
                equivalents = [(player, tuple(sorted(card[0] + suit_map[card[1]] for card in hand)),
                    transformed_history(history, suit_map)) for _, suit_map in groups]
                orbit_rows.setdefault(group, set()).add(min(equivalents))
                orbit_work += len(groups) * (12 * len(history) + 32)
        else:
            public_signatures[history] = ("terminal", value["terminal_kind"], value["winner"], tuple(value["contributions_hex"]))
        children = []
        for child, text in edges[index]:
            new_prefix = prefix + (text.split("@", 1)[1],) if value["kind"] == "chance" else prefix
            children.append((child, history + (text,), new_prefix, context, depth + 1))
        pending.extend(reversed(children))
    need(visits == admission["logical_visits"] and maximum_depth == admission["maximum_depth"] and dense == admission["dense_slots"], "independent DAG summary and history traversal disagree")
    for (player, hand, history), menu in row_menus.items():
        for _, suit_map in groups:
            changed = (player, tuple(sorted(card[0] + suit_map[card[1]] for card in hand)), transformed_history(history, suit_map))
            need(row_menus.get(changed) == menu, "claimed suit stabilizer is not closed over actual supported row identities/action menus")
    for history, signature in public_signatures.items():
        for _, suit_map in groups:
            changed_history = transformed_history(history, suit_map)
            expected_signature = signature
            if signature[0] == "chance":
                street, card_index, labels = signature[1:]
                changed_labels = []
                for label in labels:
                    if street == "flop":
                        cards = (label[at:at+2] for at in (0, 2, 4))
                        changed_labels.append("".join(sorted((card[0] + suit_map[card[1]] for card in cards), key=ORDER.__getitem__)))
                    else:
                        changed_labels.append(label[0] + suit_map[label[1]])
                expected_signature = ("chance", street, card_index, tuple(sorted(changed_labels)))
            need(public_signatures.get(changed_history) == expected_signature,
                 "claimed suit stabilizer is not closed over full public graph signatures/terminal payoffs")
    orbit_count = sum(map(len, orbit_rows.values()))
    per_group = [{"street": street, "player": "sb" if player == 0 else "bb", "information_rows": count,
        "action_slots": slot_counts[(street, player)], "suit_row_orbits": len(orbit_rows[(street, player)])}
        for (street, player), count in sorted(row_counts.items())]
    counts = {"hand_counts": list(map(len, priors)), "selected_boards": len(selected), "reachable_boards": len(reachable),
        "support_pair_board_occurrences": worlds, "unique_vertices": len(vertices), "unique_edges": sum(map(len, edges)),
        "vertex_prefix_contexts": len(contexts), "context_edges": len(context_edges), "logical_visits": visits,
        "maximum_depth": maximum_depth, "information_rows": rows, "action_slots": slots, "dense_slots": dense,
        "dense_holes": dense - rows, "history_token_entries": histories, "history_token_bytes": history_bytes,
        "per_street_player": per_group, "four_packed_numeric_buffers_payload_bytes": 4 * slots * 8,
        "serialized_policy_rows": rows, "serialized_action_rows": slots}
    symmetry = {"permutations": [image for image, _ in groups], "conservative_stabilizer_size": len(groups),
        "supported_row_orbits": orbit_count, "potential_row_reduction": rows - orbit_count}
    return {"counts": counts, "suit_symmetry": symmetry, "independent_structural_admission": admission,
        "actual_literal_pair_board_checks": pair_board_checks, "actual_orbit_work": orbit_work,
        "s4_supported_row_menu_closure": True, "s4_full_public_graph_closure": True, "quality_gate": None,
        "scope": "Independent input/support/history/orbit counts conditional on the authenticated exported public graph; no independent betting-game legality or solver quality proof."}


def shape_screen(census, counts, dense_action_slots):
    observed = {"hands_per_player": counts["hand_counts"], "selected_boards": counts["selected_boards"],
        "physical_worlds": counts["support_pair_board_occurrences"], "states": counts["logical_visits"],
        "policy_rows": counts["information_rows"], "action_slots": counts["action_slots"]}
    gates = {key: {"observed": value, "limit": CAPS[key], "passes_shape_screen":
        all(item <= CAPS[key] for item in value) if key == "hands_per_player" else value <= CAPS[key]}
        for key, value in observed.items()}
    return gates, all(value["passes_shape_screen"] for value in gates.values())


def summary(raw):
    base = {"case_id": raw["case_id"], "axis": raw["case"]["axis"], "parameters": raw["case"]["parameters"], "status": raw["status"]}
    if raw["status"] == "resource-rejected":
        return {**base, "phase": raw["phase"], "error_type": raw["error_type"], "error": raw["error"], "actual_calls": raw["actual_calls"],
            **{key: None for key in ("information_rows", "action_slots", "dense_slots", "dense_holes", "history_token_entries", "history_token_bytes",
                "unique_vertices", "unique_edges", "vertex_prefix_contexts", "context_edges", "logical_visits", "maximum_depth", "numeric_payload_bytes",
                "phase_upper_bounds", "solver_retained_peak_upper", "additional_entries_upper", "additional_work_upper", "stabilizer_size",
                "supported_row_orbits", "potential_row_reduction", "independent_certificate_shape_screen")}}
    c = raw["census"];a = c["complete_solve_admission"];storage = a["retained_storage"];sym = c["suit_symmetry"];extra = c["additional_census_admission"]
    return {**base, **{key: c[key] for key in ("information_rows", "action_slots", "dense_slots", "dense_holes", "history_token_entries", "history_token_bytes",
        "unique_vertices", "unique_edges", "vertex_prefix_contexts", "context_edges", "logical_visits", "maximum_depth")},
        "numeric_payload_bytes": c["four_packed_numeric_buffers_payload_bytes"], "phase_upper_bounds": storage["phase_upper_bounds"],
        "solver_retained_peak_upper": storage["whole_request_peak_upper"], "additional_entries_upper": extra["retained_entries_upper"],
        "additional_work_upper": extra["modeled_work_upper"], "stabilizer_size": sym["conservative_stabilizer_size"], "suit_permutations": sym["permutations"],
        "supported_row_orbits": sym["supported_row_orbits"], "potential_row_reduction": sym["potential_row_reduction"],
        "independent_certificate_shape_screen": raw["independent_certificate_shape_screen"],
        "structural_witness": {"contract": c["structural_witness"]["contract"],
            "vertex_count": len(c["structural_witness"]["vertices"]),
            "input_range_counts": [len(side) for side in c["structural_witness"]["ranges"]],
            "selected_board_count": len(c["structural_witness"]["selected_runouts"]),
            "scope": c["structural_witness"]["scope"]}, "actual_calls": raw["actual_calls"]}


def rejection_phase(text):
    value = text.lower()
    if any(word in value for word in ("postflop solver public tree", "preflop", "topology")):return "direct-topology-construction"
    if "storage census" in value or "census history-byte" in value:return "additional-census-admission"
    if any(word in value for word in ("whole-request", "output", "fraction forecast", "integer-bit")):return "exact-selected-request-admission"
    if any(word in value for word in ("range", "runout", "supports")):return "request-or-kernel-input-validation"
    return "census-preparation"


def resource_rejection(text):
    return type(text) is str and re.search(
        r"\b(?:admission|limit|exceeds?|exceeded|supports at most|too many|capacity|forecast|cap)\b", text.lower()) is not None


def read_inventory(study):
    result = {};total = 0
    for path in sorted(study.rglob("*")):
        if path.is_file():
            need(not path.is_symlink(), "study symlink rejected")
            size = path.stat().st_size
            need(size <= LIMITS["file_bytes"], "saved file exceeds independent preparse byte cap")
            total += size;need(total <= LIMITS["study_bytes"], "study exceeds independent preparse byte cap")
            result[path.relative_to(study).as_posix()] = path.read_bytes()
    return result


def json_envelope(raw):
    """Bound aggregate JSON containers/scalars before the generic parser grows."""
    in_string = escaped = False
    depth = entries = string_bytes = 0
    for byte in raw:
        if in_string:
            string_bytes += 1
            need(string_bytes <= 16384, "JSON scalar exceeds independent preparse byte cap")
            if escaped:escaped = False
            elif byte == 92:escaped = True
            elif byte == 34:in_string = False
        elif byte == 34:
            in_string = True;string_bytes = 0;entries += 1
        elif byte in (91, 123):
            depth += 1;entries += 1
            need(depth <= 512, "JSON nesting exceeds independent preparse cap")
        elif byte in (93, 125):depth -= 1
        elif byte in (44, 58):entries += 1
        need(entries <= LIMITS["entries"], "JSON logical-entry cap exceeded before parsing")
    need(not in_string and depth == 0, "unbalanced JSON envelope")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "study", "receipt", "archive"):parser.add_argument("--" + name, type=Path, required=True)
    for name in ("source-commit", "manifest-sha256", "archive-sha256", "confirmed-terminal-handle"):parser.add_argument("--" + name, required=True)
    parser.add_argument("--terminal-exit-code", type=int, required=True)
    args = parser.parse_args()
    need(args.confirmed_terminal_handle and args.terminal_exit_code == 0, "lead-confirmed successful terminal required")
    repo, study, receipt = args.repo.resolve(), args.study.resolve(), args.receipt.resolve()
    need(not receipt.exists() and repo not in receipt.parents and study not in receipt.parents, "new receipt must be external")
    auth_path = Path(__file__).with_name("exact-selected-independent-review.py")
    need(hashlib.sha256(auth_path.read_bytes()).hexdigest() == AUTH_SHA, "authentication helper pin drift")
    spec = importlib.util.spec_from_file_location("storage_frontier_pinned_auth", auth_path)
    auth = importlib.util.module_from_spec(spec);spec.loader.exec_module(auth);auth.FROZEN = args.source_commit
    def parse(raw):
        json_envelope(raw)
        return auth.parse(raw)
    saved = read_inventory(study)
    need(auth.sha(saved["manifest.json"]) == args.manifest_sha256, "external manifest pin mismatch")
    manifest = parse(saved["manifest.json"])
    need(manifest["source_commit"] == args.source_commit and set(saved) == set(manifest["sha256"]) | {"manifest.json"}, "manifest/source/inventory mismatch")
    for name, digest in manifest["sha256"].items():
        need(Path(name).name == name and auth.sha(saved[name]) == digest, "raw artifact hash drift: " + name)
    source = parse(saved["source-before.json"])
    authenticated = auth.source_identity(repo, source)
    need(parse(saved["source-after.json"]) == source, "producer source-before/after drift")
    archive = auth.archive_check(args.archive, args.archive_sha256, saved)
    # No repository code is imported. After authentication every process launch
    # is forbidden until final Git source authentication runs outside this block.
    with patch("subprocess.Popen", side_effect=AssertionError("process launch forbidden during saved structural replay")):
        protocol, report = parse(saved["protocol.json"]), parse(saved["report.json"])
        need(report["outcome"] == "complete" and report["failure"] is None and report["protocol"] == protocol, "incomplete producer/report protocol mismatch")
        need(protocol["version"] == "exact-selected-storage-frontier-v1" and protocol["source_commit"] == report["source_commit"] == args.source_commit,
             "wrong frontier source/protocol")
        need(protocol["source_sha256"] == source["sha256"] and protocol["runner_sha256"] == source["sha256"]["scripts/benchmark_exact_storage_frontier.py"], "runner full-source binding mismatch")
        runtime = protocol["runtime"]
        need(type(runtime) is dict and set(runtime) == {"implementation", "version", "sys_version", "system", "platform", "machine"}
             and all(type(value) is str and value for value in runtime.values()), "producer runtime fingerprint malformed")
        need(protocol["iterations_requested"] == 10 and protocol["exact_arithmetic"] == "fraction" and protocol["rank_cache_boards"] == 1
             and protocol["suit_orbits"] is True, "fixed frontier request mode changed")
        witness_protocol = protocol["structural_witness"]
        need(witness_protocol["requested"] is witness_protocol["include_witness"] is True and
             witness_protocol["contract"] == "exact-selected-structural-witness-v1", "structural witness was not requested by fixed protocol")
        cases = fixed_cases(repo, parse)
        need(protocol["case_count"] == len(cases) == 17 and protocol["cases"] == cases, "fixed fixture schedule differs from independent inputs")
        constants = {"MAX_HANDS_PER_PLAYER": 4, "MAX_SELECTED": 8, "MAX_WORLDS": 32, "MAX_STATES": 2048, "MAX_ROWS": 2048, "MAX_ACTIONS": 4096}
        tree = ast.parse((repo / "scripts/four_street_validation.py").read_bytes())
        observed = {target.id: ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
            for target in node.targets if isinstance(target, ast.Name) and target.id in constants}
        need(observed == constants and protocol["independent_certificate_shape_screen"]["caps"] == CAPS, "old physical quality shape caps changed")
        need(len(report["raw_records"]) == len(report["cases"]) == len(cases), "incomplete raw/report schedule")
        results = [];summaries = [];records = [];rejections = []
        for case, record, declared_summary in zip(cases, report["raw_records"], report["cases"]):
            label = case["id"];artifact = label + ".json";raw = parse(saved[artifact])
            need(label + ".stderr.txt" in saved, "missing retained raw child stderr")
            need(raw["case_id"] == label and raw["case"] == case and raw["runtime"] == runtime, "raw request/runtime identity mismatch")
            need(raw["exact_arithmetic"] == "fraction" and raw["rank_cache_boards"] == 1 and raw["suit_orbits"] is True and
                 raw["include_witness"] is True and
                 raw["training_requested"] is raw["rank_requested"] is raw["pair_queries_requested"] is False, "child requested production work")
            need(type(raw["actual_calls"]) is dict and set(raw["actual_calls"]) == set(CALLS) and
                 all(type(value) is int and value == 0 for value in raw["actual_calls"].values()), "child entered forbidden callback")
            expected_record = {"artifact": artifact, "raw_sha256": auth.sha(saved[artifact]), "status": raw["status"], "phase": raw["phase"], "actual_calls": CALLS}
            need(record == expected_record, "report/raw record binding mismatch")
            need(raw["status"] in ("accepted", "resource-rejected"), "unrecognized child status")
            if raw["status"] == "resource-rejected":
                text = raw["error"]
                need(type(text) is str and 0 < len(text) <= 4096 and raw["error_type"] == "ValueError" and raw["resource_rejection"] is True
                     and resource_rejection(text), "not a typed resource/admission rejection")
                need(raw["phase"] == rejection_phase(text) and raw["census"] is raw["independent_certificate_shape_screen"] is None,
                     "rejected request invented counts/shape or lost rejection phase")
                rejections.append({"artifact": artifact, "raw_sha256": record["raw_sha256"], "phase": raw["phase"], "error_type": raw["error_type"],
                    "error": text, "actual_calls": CALLS, "unknown_counts": True, "independent_admission_recomputed": False, "quality_gate": None})
            else:
                need(raw["phase"] == "rank-free-census-complete" and raw["error"] is raw["error_type"] is None and raw["resource_rejection"] is False, "accepted record retains error/rejection")
                c = raw["census"]
                need(c["contract"] == "exact-selected-storage-census-v1" and c["chance_contract"] == "exact-product-selected-v1" and
                     c["arithmetic"] == "fraction" and c["iterations_requested"] == 10 and c["quality_gate"] is None and
                     all(type(c[key]) is int and c[key] == 0 for key in ("training_calls", "pair_query_calls", "native_calls")), "census scope/call contract drift")
                derived = replay(c["structural_witness"], case["request"])
                need(auth.canonical({key: c[key] for key in derived["counts"]}) == auth.canonical(derived["counts"]), "independently derived support/history/graph counts disagree")
                need(c["suit_symmetry"]["requested"] is True and
                     auth.canonical({key: c["suit_symmetry"][key] for key in derived["suit_symmetry"]}) == auth.canonical(derived["suit_symmetry"]),
                     "independent weighted-game stabilizer/orbit counts disagree")
                kernel = c["rank_free_kernel_receipt"]
                need(kernel["rank_calls"] == 0 and kernel["hands"] == derived["counts"]["hand_counts"] and type(kernel["queries"]) is int and kernel["queries"] >= 0, "kernel rank/input receipt drift")
                admission = c["complete_solve_admission"];storage = admission["retained_storage"];extra = c["additional_census_admission"]
                for value, label_, ceiling in ((admission["combined_modeled_work_upper"], "producer combined work", 500000000),
                        (admission["kernel"]["whole_request_upper_work"], "producer kernel work", 500000000),
                        (kernel["work_units_cumulative"], "producer actual logical work", 500000000),
                        (storage["whole_request_peak_upper"], "producer solver retained slots", 25000000),
                        (extra["retained_entries_upper"], "producer additional retained slots", 2000000),
                        (extra["modeled_work_upper"], "producer additional modeled work", 500000000),
                        (extra["history_bytes_upper"], "producer history bytes", 16000000)):
                    integer(value, label_, ceiling)
                need(admission["kernel"]["configured_limit"] == admission["whole_request_limit"] == 500000000 and
                     storage["entry_limit"] == 25000000 and admission["combined_modeled_work_upper"] <= 500000000 and
                     storage["whole_request_peak_upper"] <= 25000000 and
                     kernel["work_units_cumulative"] <= admission["kernel"]["whole_request_upper_work"], "producer changed or exceeded old solver caps")
                dense_actions = derived["independent_structural_admission"]["dense_action_slots_upper"]
                need(admission["packed_layout"]["upper_action_slots"] == dense_actions, "producer dense action bound differs from independent graph")
                need(extra["limits"] == {"max_additional_entries": 2000000, "max_modeled_work": 500000000, "max_history_token_bytes": 16000000}
                     and extra["retained_entries_upper"] <= 2000000 and extra["modeled_work_upper"] <= 500000000 and extra["history_bytes_upper"] <= 16000000
                     and type(extra["actual_orbit_work"]) is int and extra["actual_orbit_work"] == derived["actual_orbit_work"], "producer additional census caps/counts drift")
                gates, passes = shape_screen(c, derived["counts"], dense_actions)
                screen = raw["independent_certificate_shape_screen"]
                need(screen["version"] == "exact-selected-certificate-shape-screen-v1" and screen["status"] == "screen-only" and
                     screen["validator_caps_source"] == "scripts/four_street_validation.py" and screen["gates"] == gates and
                     type(screen["all_shape_gates_pass"]) is bool and screen["all_shape_gates_pass"] == passes, "independently derived physical shape screen differs")
                if label == "club-diamond-symmetric":need("dchs" in derived["suit_symmetry"]["permutations"] and derived["suit_symmetry"]["potential_row_reduction"] > 0, "positive suit control lost symmetry opportunity")
                if label == "club-diamond-weight-broken":need("dchs" not in derived["suit_symmetry"]["permutations"], "negative weighted suit control retains broken symmetry")
                derived.update({"case_id": label, "raw_artifact": artifact, "raw_sha256": record["raw_sha256"],
                    "witness_canonical_sha256": auth.canonical(c["structural_witness"]), "independent_certificate_shape_screen": screen})
                results.append(derived)
            expected_summary = summary(raw)
            need(declared_summary == expected_summary, "report summary differs from authenticated raw counts/rejection")
            summaries.append(expected_summary);records.append(expected_record)
        ids = [case["id"] for case in cases]
        need({"original-22-world-anchor", "club-diamond-symmetric", "club-diamond-weight-broken"} <=
             {value["case_id"] for value in results}, "small positive/negative structural controls were not independently counted")
        need(report["attempted_case_ids"] == ids and report["attempted_cases"] == report["validated_records"] == len(cases)
             and report["accepted_cases"] == len(results) and report["resource_rejections"] == len(rejections), "aggregate request/rejection counts differ")
        need(all(type(report[key]) is int and report[key] == 0 for key in ("training_calls", "rank_calls", "pair_query_calls", "native_calls", "popen_calls_inside_children")), "aggregate forbidden calls nonzero")
        axes = {}
        for axis in sorted({case["axis"] for case in cases}):
            selected = [value for value in summaries if value["axis"] == axis]
            axes[axis] = {"case_count_planned": len(selected), "case_count_attempted": len(selected),
                "accepted": sum(value["status"] == "accepted" for value in selected),
                "resource_rejected": sum(value["status"] == "resource-rejected" for value in selected), "observations": selected}
        need(report["axes"] == axes, "report frontier axes differ from independent raw aggregation")
    need(auth.source_identity(repo, source) == authenticated, "source changed during independent structural review")
    need(read_inventory(study) == saved, "saved artifacts/inventory changed during structural review")
    need(auth.archive_check(args.archive, args.archive_sha256, saved) == archive, "saved archive changed during structural review")
    result = {"outcome": "accepted", "source_commit": args.source_commit, "authenticated_source": authenticated,
        "manifest_sha256": args.manifest_sha256, "archive": archive, "artifact_sha256": {name: auth.sha(value) for name, value in saved.items()},
        "confirmed_terminal_handle": args.confirmed_terminal_handle, "terminal_exit_code": 0, "producer_runtime": runtime,
        "source_and_artifacts_unchanged_after_review": True, "independent_structural_limits": LIMITS, "independent_results": results,
        "preserved_zero_call_rejections": rejections, "derived_axes": axes, "review_training_calls": 0, "review_rank_calls": 0,
        "review_kernel_query_calls": 0, "review_native_calls": 0, "repository_modules_imported": [], "quality_gate": None,
        "review_helper_sha256": auth.sha(Path(__file__).read_bytes()), "authentication_helper_sha256": AUTH_SHA,
        "scope": "Independent bounded input/blocker/history/context/weighted-S4 orbit verification conditional on exported public graph, plus unchanged physical certificate shape screens only. No solver, ranking, production cursor, physical quality oracle, independent legal betting-tree proof, performance claim, or production row merging."}
    receipt.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"outcome": "accepted", "receipt_sha256": auth.sha(receipt.read_bytes()), "independently_counted_cases": len(results), "preserved_resource_rejections": len(rejections)}))


if __name__ == "__main__":
    main()
