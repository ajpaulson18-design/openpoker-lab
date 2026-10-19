"""Independently verify the fixed weighted preflop sequence-form witness.

The checker intentionally does not import the candidate builder, any poker
tree/solver, an LP package, or a production evaluator / best-response routine.
It reconstructs this one small public betting game and exact payoff matrix
from the pinned, independently produced full-board count artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from fractions import Fraction as F
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = "26a3b28bfe566019b3d44b281a24f9497d578ca8"
COUNT_COMMIT = "a5e1b75ab424c97673f5126796b9d7eae14b0706"
BOARDS = 1_712_304
SOURCE_ROWS = (
    ("benchmarks/results/preflop-push-fold-v1-oracle-pair-0.json",
     "599c1360f321d845b335b798468c3c6af216951663e87b6812ecb56321895b40",
     "cc510379eed9484f30e59e428917a9e55ba027a7",
     "AdAs", "KdKs", 1_410_336, 9_308, 292_660),
    ("benchmarks/results/preflop-push-fold-v1-oracle-pair-1.json",
     "61cecc13d773b26496a14ffee1612dfaf5149981e4fcdb12bdbad65db2660160",
     "d639fecaee1c9f1ca1eaec95bb29e3162ddd00ff",
     "QdQs", "AsKh", 968_267, 7_226, 736_811),
    ("benchmarks/results/preflop-push-fold-v1-oracle-pair-2.json",
     "fc6ae5898eac160de79ed4d9c652c632d000966867f1b296bc7dbae682e98e52",
     "864c80c32739f6665b6010c200ad31bcb32e439f",
     "QdQs", "KdKs", 292_846, 9_336, 1_410_122),
)
SPEC_HASH = "5b4a79d0239a42c3911928b0ca5d0f53a54be228e68c62ad9a5f8a2925719fb3"
SPEC_PATH = ROOT / "benchmarks/preflop-weighted-sequence-v1.json"
EXPECTED_PRIORS = (F(8, 13), F(1, 13), F(4, 13))
FIXTURE = {
    "id": "preflop-weighted-three-pair-sequence-equilibrium",
    "sb_range": "AsAd:1,QsQd:0.5",
    "bb_range": "AsKh:0.25,KsKd:1",
    "config": {"small_blind": 0.5, "big_blind": 1,
                "starting_stack": [4, 3], "raise_sizes": [0.5, 1],
                "max_raises": 1, "include_all_in": True},
}


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _same_json(actual, expected):
    """Structural JSON equality that does not treat bools as integers."""
    if type(actual) is not type(expected):
        return False
    if type(actual) is dict:
        return (actual.keys() == expected.keys() and
                all(_same_json(actual[key], expected[key]) for key in expected))
    if type(actual) is list:
        return len(actual) == len(expected) and all(_same_json(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _fraction(value, label):
    _need(type(value) is str and len(value) <= 100, f"{label} must be a bounded Fraction string")
    try:
        result = F(value)
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(f"Invalid {label} Fraction") from exc
    _need(str(result) == value, f"{label} is not canonical")
    _need(result.numerator.bit_length() <= 4096 and result.denominator.bit_length() <= 4096,
          f"{label} exceeds the frozen Fraction bit cap")
    return result


def _check_json_envelope(value):
    """Bound untrusted parsed certificate depth, breadth, strings, and integers."""
    budget = {"nodes": 0, "string_bytes": 0}
    def visit(item, depth):
        _need(depth <= 24, "Certificate nesting exceeds verifier limit")
        budget["nodes"] += 1
        _need(budget["nodes"] <= 20_000, "Certificate has too many JSON values")
        if type(item) is dict:
            _need(len(item) <= 64, "Certificate object exceeds verifier field limit")
            for key, child in item.items():
                _need(type(key) is str, "Certificate object keys must be strings")
                _need(len(key) <= 4096, "Certificate key exceeds verifier length limit")
                budget["string_bytes"] += len(key.encode("utf-8"))
                visit(child, depth + 1)
        elif type(item) is list:
            _need(len(item) <= 256, "Certificate array exceeds verifier length limit")
            for child in item:
                visit(child, depth + 1)
        elif type(item) is str:
            _need(len(item) <= 4096, "Certificate string exceeds verifier length limit")
            budget["string_bytes"] += len(item.encode("utf-8"))
        elif type(item) is int:
            _need(item.bit_length() <= 4096, "Certificate integer exceeds verifier bit limit")
        elif type(item) is float:
            _need(item == item and abs(item) != float("inf"), "Nonfinite certificate number")
        elif item is None or type(item) is bool:
            return
        else:
            raise ValueError("Certificate contains an unsupported JSON value")
        _need(budget["string_bytes"] <= 1_000_000, "Certificate strings exceed verifier byte limit")
    visit(value, 0)


def _pinned_counts():
    """Read the exact committed count artifacts, checking both hashes and rows."""
    output, provenance = [], []
    for rel, digest, blob_hash, sb, bb, wins, ties, losses in SOURCE_ROWS:
        path = ROOT / rel
        local = json.loads(path.read_bytes())
        payload = {k: v for k, v in local.items() if k != "artifact_sha256"}
        _need(hashlib.sha256(_canonical(payload)).hexdigest() == digest == local.get("artifact_sha256"),
              f"Canonical count artifact hash mismatch: {rel}")
        # Git's blob object is computed from the checked-in UTF-8/LF bytes.
        # Normalize checkout CRLF so this verifier also works in shallow CI.
        blob = path.read_bytes().replace(b"\r\n", b"\n")
        git_blob = hashlib.sha1(b"blob " + str(len(blob)).encode("ascii") + b"\0" + blob).hexdigest()
        _need(git_blob == blob_hash, f"Pinned Git count blob mismatch: {rel}")
        pinned = json.loads(blob)
        row = pinned.get("counts")
        _need(type(row) is dict and pinned.get("phase") == "independent-full-board-oracle"
              and pinned.get("benchmark_id") == "preflop-push-fold-v1"
              and pinned.get("provenance", {}).get("git_revision") == "151c35a6739251bb280b5be4373c35a05daa2950",
              f"Count artifact provenance mismatch: {rel}")
        wanted = {"sb_hand": sb, "bb_hand": bb, "wins": wins, "ties": ties,
                  "losses": losses, "boards": BOARDS}
        for key, expected in wanted.items():
            _need(type(row.get(key)) is type(expected) and row.get(key) == expected,
                  f"Pinned count mismatch {rel}:{key}")
        _need(wins + ties + losses == BOARDS, f"Count total mismatch: {rel}")
        output.append({"sb_hand": sb, "bb_hand": bb, "wins": wins, "ties": ties,
                       "losses": losses, "boards": BOARDS})
        provenance.append({"path": rel, "canonical_sha256": digest,
                           "git_blob_sha1": blob_hash, "sb_hand": sb, "bb_hand": bb,
                           "wins": wins, "ties": ties, "losses": losses, "boards": BOARDS})
    return output, provenance


def _fixture_check():
    spec = json.loads(SPEC_PATH.read_bytes())
    _need(hashlib.sha256(_canonical(spec)).hexdigest() == SPEC_HASH,
          "Frozen game specification checksum mismatch")
    _need(spec.get("baseline_commit") == BASELINE and _same_json(spec.get("fixture"), FIXTURE),
          "Frozen game fixture differs")
    return spec


class _Action:
    __slots__ = ("name", "amount", "raise_to", "token")

    def __init__(self, name, amount=F(0), raise_to=F(0), token=None):
        self.name, self.amount, self.raise_to = name, amount, raise_to
        self.token = token or name


class _Node:
    __slots__ = ("player", "history", "actions", "children")

    def __init__(self, player, history, actions, children):
        self.player, self.history = player, tuple(history)
        self.actions, self.children = tuple(actions), tuple(children)


class _Terminal:
    __slots__ = ("kind", "contributions", "winner")

    def __init__(self, kind, contributions, winner=None):
        self.kind, self.contributions, self.winner = kind, tuple(contributions), winner


def _amount_label(amount):
    return format(float(amount), ".9f").rstrip("0").rstrip(".")


def _bet(name, target, committed):
    token = f"{name}@{_amount_label(target)}"
    return _Action(name, target - committed, target, token)


def _configured_raises(player, contributions, previous_full_raise, sizes, stacks):
    """Independent raise sizing from call amount, post-call pot, and min-raise."""
    opponent = 1 - player
    call_target = contributions[opponent]
    call_amount = call_target - contributions[player]
    post_call_pot = sum(contributions, F(0)) + call_amount
    minimum_target = call_target + previous_full_raise
    max_target = stacks[player]
    unique = {}
    for fraction in sizes:
        requested = call_target + fraction * post_call_pot
        target = min(max_target, max(minimum_target, requested))
        if target <= call_target:
            continue
        name = "all_in" if target >= max_target else "raise"
        unique[target] = _bet(name, target, contributions[player])
    if max_target > call_target:
        unique[max_target] = _bet("all_in", max_target, contributions[player])
    return tuple(unique[target] for target in sorted(unique))


def _game():
    """Literal tree for the frozen blinds/stacks/raise-size game."""
    sb_blind, bb_blind = F(1, 2), F(1)
    stacks = (F(4), F(3))
    root_contrib = (sb_blind, bb_blind)

    def showdown(contrib):
        return _Terminal("showdown", contrib)

    def response(player, history, contrib):
        folded = list(contrib)
        called = list(contrib)
        called[player] = min(called[1 - player], (F(4), F(3))[player])
        actions = (_Action("fold"), _Action("call", called[player] - contrib[player],
                                             called[player], "call"))
        return _Node(player, history, actions,
                     (_Terminal("fold", folded, 1 - player), showdown(tuple(called))))

    # BB's posted amount establishes the initial minimum full raise. The root
    # raise menu follows the configured sizing fractions after the call.
    root_actions = [_Action("fold"), _Action("call", F(1, 2), F(1), "call")]
    root_children = [_Terminal("fold", root_contrib, 1)]
    root_children.append(None)
    for action in _configured_raises(0, root_contrib, bb_blind,
                                     (F(1, 2), F(1)), stacks):
        root_actions.append(action)
        contrib = (action.raise_to, bb_blind)
        root_children.append(response(1, (action.token,), contrib))

    # A small-blind call (limp) leaves BB its check/raise option. At a blind
    # raise to 2 or 3, SB can fold or call; the second level is capped at one.
    bb_raise_actions = _configured_raises(1, (F(1), F(1)), bb_blind,
                                          (F(1, 2), F(1)), stacks)
    bb_actions = [_Action("check"), *bb_raise_actions]
    bb_children = [showdown((F(1), F(1)))]
    for action in bb_actions[1:]:
        contrib = (F(1), action.raise_to)
        bb_children.append(response(0, ("call", action.token), contrib))
    root_children[1] = _Node(1, ("call",), bb_actions, bb_children)
    root = _Node(0, (), root_actions, root_children)

    nodes, terminals = [], []
    def walk(node):
        if isinstance(node, _Terminal):
            terminals.append(node)
        else:
            nodes.append(node)
            for child in node.children:
                walk(child)
    walk(root)
    _need((len(nodes), sum(t.kind == "fold" for t in terminals),
           sum(t.kind == "showdown" for t in terminals), len(nodes) + len(terminals))
          == (7, 6, 6, 19), "Literal public-game census changed")
    return root, nodes, terminals


def _game_data():
    _fixture_check()
    counts, provenance = _pinned_counts()
    sb_range = (("AdAs", F(1)), ("QdQs", F(1, 2)))
    bb_range = (("AsKh", F(1, 4)), ("KdKs", F(1)))
    raw_pairs = []
    rejected = []
    for sb_hand, sb_weight in sb_range:
        for bb_hand, bb_weight in bb_range:
            if set((sb_hand[:2], sb_hand[2:])) & set((bb_hand[:2], bb_hand[2:])):
                rejected.append((sb_hand, bb_hand, sb_weight * bb_weight))
            else:
                raw_pairs.append((sb_hand, bb_hand, sb_weight * bb_weight))
    normalizer = sum((weight for _sb, _bb, weight in raw_pairs), F(0))
    prior = tuple(weight / normalizer for _sb, _bb, weight in raw_pairs)
    _need(tuple((sb, bb) for sb, bb, _weight in raw_pairs) ==
          tuple((row["sb_hand"], row["bb_hand"]) for row in counts),
          "Independent weighted-hand grammar gives a different compatible-pair census")
    _need(rejected == [("AdAs", "AsKh", F(1, 4))],
          "Independent collision conditioning rejected a different private pair")
    _need(normalizer == F(13, 8) and prior == EXPECTED_PRIORS,
          "Exact weighted blocker normalizer or conditioned priors changed")
    pair_data = []
    for row, mass in zip(counts, prior):
        pair_data.append({"sb_hand": row["sb_hand"], "bb_hand": row["bb_hand"],
                          "prior": mass,
                          "showdown_mean": F(row["wins"] - row["losses"], row["boards"])})
    _need(sum(prior, F(0)) == 1, "Prior mass does not normalize")
    return pair_data, provenance, normalizer, rejected


def _terminal_payoff(term, pair):
    if term.kind == "fold":
        return term.contributions[1] if term.winner == 0 else -term.contributions[0]
    return min(term.contributions) * pair["showdown_mean"]


def _derive_model():
    """Derive own-hand infosets, sequence flow equations, and exact payoff A."""
    pairs, provenance, prior_normalizer, rejected_pairs = _game_data()
    root, nodes, terminals = _game()
    hands = ({p["sb_hand"] for p in pairs}, {p["bb_hand"] for p in pairs})
    info = [dict(), dict()]
    # A sequence is identified structurally, rather than by candidate-assigned IDs.
    root_seq = (None, None, "root")
    child_seq = [dict(), dict()]
    all_sequences = [{root_seq}, {root_seq}]

    def record(node, pair, parents):
        if isinstance(node, _Terminal):
            return
        actor = node.player
        hand = pair["sb_hand"] if actor == 0 else pair["bb_hand"]
        key = (actor, hand, node.history)
        parent = parents[actor]
        action_structures = []
        for action, child in zip(node.actions, node.children):
            seq = (parent, key, action.token)
            action_structures.append(seq)
            all_sequences[actor].add(seq)
            prior = info[actor].setdefault(key, (parent, []))
            _need(prior[0] == parent, "Own-player recall history is inconsistent")
            if seq not in prior[1]:
                prior[1].append(seq)
        for seq, child in zip(action_structures, node.children):
            next_parents = list(parents)
            next_parents[actor] = seq
            record(child, pair, tuple(next_parents))

    for pair in pairs:
        record(root, pair, (root_seq, root_seq))

    # Canonical structural order makes the independent certificate comparison
    # insensitive to IDs chosen by the witness producer.
    def skey(seq):
        parent, ikey, token = seq
        if seq == root_seq:
            return ("", "", "", "")
        return (str(ikey[1]), "/".join(ikey[2]), token,
                "root" if parent == root_seq else str(parent[1][1]) + "/".join(parent[1][2]) + parent[2])
    ordered_sequences = [sorted(items, key=skey) for items in all_sequences]
    positions = [{seq: i for i, seq in enumerate(side)} for side in ordered_sequences]
    info_equations = []
    for player in (0, 1):
        rows = []
        for key in sorted(info[player], key=lambda k: (k[1], k[2])):
            parent, children = info[player][key]
            rows.append((key, parent, tuple(children)))
        info_equations.append(rows)

    # Track each public leaf by the last own action sequence for each player;
    # this yields A directly by adding each world prior times its terminal mean.
    matrix = [[F(0) for _ in ordered_sequences[1]] for _ in ordered_sequences[0]]
    def payoff_walk(node, pair, parent_sequences):
        if isinstance(node, _Terminal):
            matrix[positions[0][parent_sequences[0]]][positions[1][parent_sequences[1]]] += (
                pair["prior"] * _terminal_payoff(node, pair))
            return
        player = node.player
        key = (player, pair["sb_hand"] if player == 0 else pair["bb_hand"], node.history)
        for action, child in zip(node.actions, node.children):
            next_seq = (parent_sequences[player], key, action.token)
            updated = list(parent_sequences)
            updated[player] = next_seq
            payoff_walk(child, pair, tuple(updated))
    for pair in pairs:
        payoff_walk(root, pair, (root_seq, root_seq))

    # Flow constraints are represented as exact maps keyed by sequence structure.
    flow_rows = []
    for player in (0, 1):
        equations = []
        root_eq = {seq: F(0) for seq in ordered_sequences[player]}
        root_eq[root_seq] = F(1)
        equations.append(("root", root_eq, F(1)))
        for key, parent, children in info_equations[player]:
            equation = {seq: F(0) for seq in ordered_sequences[player]}
            equation[parent] -= 1
            for seq in children:
                equation[seq] += 1
            equations.append((key, equation, F(0)))
        flow_rows.append(equations)

    _need(tuple(map(len, info)) == (6, 8), "Information-set census changed")
    _need(tuple(map(len, ordered_sequences)) == (19, 19), "Sequence census changed")
    result = {
        "pairs": pairs, "provenance": provenance, "prior_normalizer": prior_normalizer,
        "rejected_pairs": rejected_pairs, "root": root, "nodes": nodes,
        "terminals": terminals, "infos": info_equations,
        "sequences": ordered_sequences, "positions": positions,
        "matrix": matrix, "flows": flow_rows,
    }
    seq_rows, _, ids_for_struct = _sequence_rows(result)
    matrix_ordered = []
    for left in seq_rows[0]:
        lstruct = next(seq for seq in ordered_sequences[0]
                       if ids_for_struct[0][seq] == left["id"])
        matrix_ordered.append([
            matrix[positions[0][lstruct]][positions[1][next(
                seq for seq in ordered_sequences[1] if ids_for_struct[1][seq] == right["id"]
            )]] for right in seq_rows[1]
        ])
    aligned_flows = []
    flow_ids = []
    for player in (0, 1):
        side_rows, side_ids, side_flows = [], [], []
        seat = ("sb", "bb")[player]
        for key, equation, rhs in flow_rows[player]:
            if key == "root":
                flow_id = f"{seat}:empty=1"
            else:
                flow_id = f"{seat}:flow:{key[1]}:{'/'.join(key[2]) or 'root'}"
            side_ids.append(flow_id)
            side_rows.append([sum((coefficient * F(seq == candidate)
                                   for seq, coefficient in equation.items()), F(0))
                              for candidate in [
                                  next(seq for seq in ordered_sequences[player]
                                       if ids_for_struct[player][seq] == row["id"])
                                  for row in seq_rows[player]]])
        aligned_flows.append(side_rows)
        flow_ids.append(side_ids)
    result.update({"sequence_rows": seq_rows, "ids_for_struct": ids_for_struct,
                   "row_ids": [row["id"] for row in seq_rows[0]],
                   "column_ids": [row["id"] for row in seq_rows[1]],
                   "matrix_ordered": matrix_ordered, "aligned_flows": aligned_flows,
                   "flow_ids": flow_ids})
    return result


def _sid(player, sequence, root_seq):
    if sequence == root_seq:
        return ("sb", "bb")[player] + ":empty"
    _parent, info, token = sequence
    seat = ("sb", "bb")[player]
    history = "/".join(info[2]) or "root"
    return f"{seat}|{info[1]}|{history}|{token}"


def _sequence_rows(model):
    root_seq = (None, None, "root")
    rows, struct_for_id, ids_for_struct = [], [], []
    for player in (0, 1):
        ids = {}
        for sequence in model["sequences"][player]:
            ids[sequence] = _sid(player, sequence, root_seq)
        order = [root_seq] + sorted((s for s in model["sequences"][player]
                                     if s != root_seq), key=lambda s: ids[s])
        side = []
        for sequence in order:
            sid = ids[sequence]
            if sequence == root_seq:
                row = {"id": sid, "player": player, "hand": None,
                       "history": [], "action_token": None, "parent": None}
            else:
                parent, key, token = sequence
                row = {"id": sid, "player": player, "hand": key[1],
                       "history": list(key[2]), "action_token": token,
                       "parent": ids[parent]}
            side.append(row)
        rows.append(side)
        struct_for_id.append({ids[seq]: seq for seq in order})
        ids_for_struct.append(ids)
    return rows, struct_for_id, ids_for_struct


def _independent_tree_json(model):
    """Serialize our game from an explicit history/contribution walk."""
    def encode(node, contributions):
        if isinstance(node, _Terminal):
            return {"kind": node.kind,
                    "winner": None if node.winner is None else ("sb" if node.winner == 0 else "bb"),
                    "contributions": [str(value) for value in node.contributions]}
        actions, children = [], []
        for action, child in zip(node.actions, node.children):
            actions.append({"name": action.name, "amount": str(action.amount),
                            "raise_to": str(action.raise_to), "token": action.token})
            if action.name in ("raise", "all_in"):
                updated = list(contributions)
                updated[node.player] = action.raise_to
                children.append(encode(child, tuple(updated)))
            elif action.name == "call":
                updated = list(contributions)
                updated[node.player] = action.raise_to
                children.append(encode(child, tuple(updated)))
            else:
                children.append(encode(child, contributions))
        return {"kind": "decision", "player": ("sb", "bb")[node.player],
                "history": list(node.history),
                "contributions": [str(value) for value in contributions],
                "actions": actions, "children": children}
    return encode(model["root"], (F(1, 2), F(1)))


def _expected_infos_and_flows(model, seq_rows, ids_for_struct):
    info_rows, flow_rows = [], []
    for player in (0, 1):
        seat = ("sb", "bb")[player]
        root_id = seat + ":empty"
        flow_rows.append({"id": f"{seat}:empty=1", "player": seat, "seat": seat,
                          "player_index": player, "kind": "root",
                          "parent_sequence": root_id, "child_sequences": [], "rhs": "1"})
        for key, parent, children in model["infos"][player]:
            tokens = [seq[2] for seq in children]
            child_ids = [ids_for_struct[player][seq] for seq in children]
            parent_id = ids_for_struct[player][parent]
            info_rows.append({"player": seat, "hand": key[1], "history": list(key[2]),
                              "parent_sequence": parent_id, "action_tokens": tokens,
                              "child_sequences": child_ids})
            flow_rows.append({"id": f"{seat}:flow:{key[1]}:{'/'.join(key[2]) or 'root'}",
                              "player": seat, "seat": seat, "player_index": player,
                              "kind": "information_set", "parent_sequence": parent_id,
                              "child_sequences": child_ids, "rhs": "0"})
    return info_rows, flow_rows


def _lp_invariants(lp, *, kind, row_ids, col_ids, flow_ids, matrix, flows, preflight):
    """Check the serialized exact primal/dual points against independently built A,E,F."""
    expected_keys = {"objective", "phase_one_objective", "pivots", "logical_cell_updates",
                     "maximum_fraction_bits", "tableau_rows", "tableau_columns",
                     "tableau_cells_including_rhs_and_objective", "lp", "objective_bound_fraction",
                     "variable_labels", "constraint_labels", "own_realization",
                     "dual_flow_values", "inequality_slacks"}
    _need(type(lp) is dict and set(lp) == expected_keys, f"Unexpected {kind} LP witness fields")
    _need(lp["lp"] == kind, f"Wrong LP orientation for {kind}")
    m, n = preflight["rows"], preflight["columns"]
    _need(type(lp["tableau_rows"]) is int and 0 <= lp["tableau_rows"] <= m
          and type(lp["tableau_columns"]) is int and lp["tableau_columns"] == n
          and type(lp["tableau_cells_including_rhs_and_objective"]) is int
          and lp["tableau_cells_including_rhs_and_objective"] ==
          (lp["tableau_rows"] + 1) * (n + 1), f"Invalid {kind} tableau dimensions")
    for field in ("pivots", "logical_cell_updates", "maximum_fraction_bits"):
        _need(type(lp[field]) is int and lp[field] >= 0, f"Invalid {kind} resource counter")
    _need(lp["pivots"] <= 512 and lp["logical_cell_updates"] <= 10_000_000
          and lp["maximum_fraction_bits"] <= 4096, f"{kind} exceeded frozen LP caps")
    _need(_fraction(lp["phase_one_objective"], f"{kind} phase-I objective") == 0,
          f"{kind} phase I is not feasible")
    labels = lp["variable_labels"]
    constraints = lp["constraint_labels"]
    _need(type(labels) is list and len(labels) == n and all(type(x) is str and len(x) < 256 for x in labels),
          f"Invalid {kind} variable labels")
    _need(type(constraints) is list and len(constraints) == m, f"Invalid {kind} constraint labels")
    own, dual, slack = lp["own_realization"], lp["dual_flow_values"], lp["inequality_slacks"]
    for item, expected_labels, name in ((own, row_ids if kind == "oop_guarantee" else col_ids, "own"),
                                        (dual, flow_ids[1] if kind == "oop_guarantee" else flow_ids[0], "dual"),
                                        (slack, col_ids if kind == "oop_guarantee" else row_ids, "slack")):
        _need(type(item) is dict and set(item) == {"sequence_labels" if name != "dual" else "flow_labels", "fractions"},
              f"Invalid {kind} {name} witness shape")
        lfield = "sequence_labels" if name != "dual" else "flow_labels"
        _need(item[lfield] == expected_labels, f"{kind} {name} labels differ from independent model")
    own_count = len(row_ids) if kind == "oop_guarantee" else len(col_ids)
    dual_count = len(flows[1]) if kind == "oop_guarantee" else len(flows[0])
    slack_count = len(col_ids) if kind == "oop_guarantee" else len(row_ids)
    _need(type(own["fractions"]) is list and len(own["fractions"]) == own_count
          and type(dual["fractions"]) is list and len(dual["fractions"]) == dual_count
          and type(slack["fractions"]) is list and len(slack["fractions"]) == slack_count,
          f"Malformed {kind} vector size")
    _need(all(type(value) is str and len(value) <= 100
              for vector in (own["fractions"], dual["fractions"], slack["fractions"])
              for value in vector), f"Malformed {kind} bounded Fraction vector")
    own_values = [_fraction(x, f"{kind} own realization") for x in own["fractions"]]
    dual_values = [_fraction(x, f"{kind} dual flow") for x in dual["fractions"]]
    slack_values = [_fraction(x, f"{kind} slack") for x in slack["fractions"]]
    if kind == "oop_guarantee":
        _need(len(own_values) == len(row_ids) and len(dual_values) == len(flows[1])
              and len(slack_values) == len(col_ids), "Malformed lower LP vector lengths")
        _need(all(x >= 0 for x in own_values), "Negative SB realization weight")
        for equation, rhs in zip(flows[0], [F(1)] + [F(0)] * (len(flows[0]) - 1)):
            _need(sum((a*b for a,b in zip(equation, own_values)), F(0)) == rhs,
                  "SB realization flow is infeasible")
        computed = [sum((matrix[i][j] * own_values[i] for i in range(len(row_ids))), F(0)) -
                    sum((flows[1][r][j] * dual_values[r] for r in range(len(flows[1]))), F(0))
                    for j in range(len(col_ids))]
        bound = dual_values[0]
        expected_objective = bound
    else:
        _need(len(own_values) == len(col_ids) and len(dual_values) == len(flows[0])
              and len(slack_values) == len(row_ids), "Malformed upper LP vector lengths")
        _need(all(x >= 0 for x in own_values), "Negative BB realization weight")
        for equation, rhs in zip(flows[1], [F(1)] + [F(0)] * (len(flows[1]) - 1)):
            _need(sum((a*b for a,b in zip(equation, own_values)), F(0)) == rhs,
                  "BB realization flow is infeasible")
        computed = [sum((flows[0][r][i] * dual_values[r] for r in range(len(flows[0]))), F(0)) -
                    sum((matrix[i][j] * own_values[j] for j in range(len(col_ids))), F(0))
                    for i in range(len(row_ids))]
        bound = dual_values[0]
        expected_objective = -bound
    _need(computed == slack_values and all(x >= 0 for x in computed),
          f"{kind} dual inequality/slack certificate is false")
    _need(_fraction(lp["objective_bound_fraction"], f"{kind} objective bound") == bound
          and _fraction(lp["objective"], f"{kind} objective") == expected_objective,
          f"{kind} reported objective does not match exact dual bound")
    return own_values, dual_values, slack_values


def _expected_lp_labels(kind, row_ids, col_ids, flow_ids):
    if kind == "oop_guarantee":
        labels = ([f"x:{sid}" for sid in row_ids] +
                  [f"q+:{fid}" for fid in flow_ids[1]] +
                  [f"q-:{fid}" for fid in flow_ids[1]] +
                  [f"surplus:{sid}" for sid in col_ids] +
                  [f"artificial:{fid}" for fid in flow_ids[0]] +
                  [f"artificial:cover:{sid}" for sid in col_ids])
        constraints = ([{"id": fid, "sense": "="} for fid in flow_ids[0]] +
                       [{"id": f"cover:{sid}", "sense": ">=", "slack_variable": f"surplus:{sid}"}
                        for sid in col_ids])
    else:
        labels = ([f"y:{sid}" for sid in col_ids] +
                  [f"p+:{fid}" for fid in flow_ids[0]] +
                  [f"p-:{fid}" for fid in flow_ids[0]] +
                  [f"surplus:{sid}" for sid in row_ids] +
                  [f"artificial:{fid}" for fid in flow_ids[1]] +
                  [f"artificial:cover:{sid}" for sid in row_ids])
        constraints = ([{"id": fid, "sense": "="} for fid in flow_ids[1]] +
                       [{"id": f"cover:{sid}", "sense": ">=", "slack_variable": f"surplus:{sid}"}
                        for sid in row_ids])
    return labels, constraints


def _policy_map(witness, model, x, y):
    expected_infos, _ = _expected_infos_and_flows(model, model["sequence_rows"], model["ids_for_struct"])
    expected = {(row["player"], row["hand"], tuple(row["history"])): row
                for row in expected_infos}
    _need(type(witness["policies"]) is list and len(witness["policies"]) == len(expected),
          "Policy information-set coverage differs")
    positions = [{row["id"]: i for i, row in enumerate(side)} for side in model["sequence_rows"]]
    parsed = {}
    for row in witness["policies"]:
        keys = {"player", "hand", "history", "action_tokens", "probabilities",
                "zero_realization_fallback"}
        _need(type(row) is dict and set(row) == keys and row["player"] in ("sb", "bb")
              and type(row["hand"]) is str and type(row["history"]) is list
              and all(type(token) is str for token in row["history"]),
              "Malformed behavioral policy row")
        key = row["player"], row["hand"], tuple(row["history"])
        _need(key in expected and key not in parsed, "Unknown or duplicate information-set policy")
        wanted = expected[key]
        _need(row["action_tokens"] == wanted["action_tokens"],
              "Policy action menu differs from public history")
        _need(type(row["zero_realization_fallback"]) is bool,
              "Invalid zero-reach policy marker")
        probs = row["probabilities"]
        _need(type(probs) is list and len(probs) == len(wanted["action_tokens"]),
              "Policy probability arity differs from action menu")
        exact = tuple(_fraction(value, "policy probability") for value in probs)
        _need(all(value >= 0 for value in exact) and sum(exact, F(0)) == 1,
              "Policy probabilities are not a normalized legal distribution")
        player = 0 if row["player"] == "sb" else 1
        realization = x if player == 0 else y
        mass = realization[positions[player][wanted["parent_sequence"]]]
        _need(row["zero_realization_fallback"] is (mass == 0),
              "Zero-reach fallback marker disagrees with parent realization")
        child_masses = [realization[positions[player][sid]] for sid in wanted["child_sequences"]]
        if mass:
            _need(tuple(child_masses) == tuple(mass * p for p in exact),
                  "Behavioral policy does not induce its certified realization")
        else:
            _need(all(value == 0 for value in child_masses),
                  "Zero parent realization has a positive child realization")
        parsed[key] = exact
    _need(set(parsed) == set(expected), "Missing behavioral policy information set")
    return parsed


def _profile_value(node, pair, policies):
    if isinstance(node, _Terminal):
        return _terminal_payoff(node, pair)
    hand = pair["sb_hand"] if node.player == 0 else pair["bb_hand"]
    key = (("sb" if node.player == 0 else "bb"), hand, node.history)
    return sum((p * _profile_value(child, pair, policies)
                for p, child in zip(policies[key], node.children)), F(0))


def _best_response(model, policies, responder):
    """Exact legal response; hidden opponent hands stay aggregated at each decision."""
    def visit(node, entries):
        if isinstance(node, _Terminal):
            return sum((weight * _terminal_payoff(node, pair) for pair, weight in entries), F(0))
        if node.player == responder:
            by_own_hand = {}
            for pair, weight in entries:
                hand = pair["sb_hand"] if responder == 0 else pair["bb_hand"]
                by_own_hand.setdefault(hand, []).append((pair, weight))
            total = F(0)
            for group in by_own_hand.values():
                values = [visit(child, group) for child in node.children]
                total += max(values) if responder == 0 else min(values)
            return total
        total = F(0)
        seat = "bb" if node.player == 1 else "sb"
        for index, child in enumerate(node.children):
            branch = []
            for pair, weight in entries:
                hand = pair["bb_hand"] if node.player == 1 else pair["sb_hand"]
                probability = policies[(seat, hand, node.history)][index]
                if probability:
                    branch.append((pair, weight * probability))
            if branch:
                total += visit(child, branch)
        return total
    return visit(model["root"], [(pair, pair["prior"]) for pair in model["pairs"]])


def _residual_rows(model, x, y):
    output = []
    for player, realization in ((0, x), (1, y)):
        side = []
        for label, row in zip(model["flow_ids"][player], model["aligned_flows"][player]):
            rhs = F(1) if label.endswith(":empty=1") else F(0)
            lhs = sum((coefficient * value for coefficient, value in zip(row, realization)), F(0))
            side.append({"constraint": label, "lhs": str(lhs), "rhs": str(rhs),
                         "residual": str(lhs - rhs)})
        output.append(side)
    return output


def verify_certificate(witness):
    """Verify one serialized exact sequence-form witness independently.

    Returns a compact verification summary. The candidate certificate is data:
    it is never imported or executed.
    """
    _check_json_envelope(witness)
    _need(type(witness) is dict, "Certificate must be a JSON object")
    required = {"schema_version", "certificate_id", "status", "fixture", "count_provenance",
                "pair_priors", "census", "oop_lp", "ip_lp", "policies", "equilibrium",
                "caps", "scope", "artifact_sha256"}
    _need(set(witness) == required, "Unexpected certificate fields")
    digest = witness.get("artifact_sha256")
    payload = {key: value for key, value in witness.items() if key != "artifact_sha256"}
    _need(type(digest) is str and len(digest) == 64
          and hashlib.sha256(_canonical(payload)).hexdigest() == digest,
          "Certificate self-checksum mismatch")
    _need(type(witness["schema_version"]) is int and witness["schema_version"] == 1
          and witness["certificate_id"] == "preflop-weighted-sequence-feasibility-v1"
          and witness["status"] == "exact-candidate-feasibility", "Unexpected certificate identity/status")
    spec = _fixture_check()
    _need(_same_json(witness["fixture"], FIXTURE) and witness["scope"] == spec["scope"],
          "Certificate fixture or declared scope differs")
    model = _derive_model()

    rows = []
    for pair, source in zip(model["pairs"], model["provenance"]):
        rows.append({"sb_hand": pair["sb_hand"], "bb_hand": pair["bb_hand"],
                     "wins": source["wins"], "ties": source["ties"], "losses": source["losses"],
                     "boards": source["boards"], "prior_fraction": str(pair["prior"]),
                     "showdown_mean_fraction": str(pair["showdown_mean"]),
                     "source_artifact": source["path"],
                     "canonical_artifact_sha256": source["canonical_sha256"],
                     "pinned_git_blob_sha1": source["git_blob_sha1"]})
    provenance = witness["count_provenance"]
    _need(type(provenance) is dict and set(provenance) == {"source_commit", "rows", "physical_boards"}
          and provenance["source_commit"] == COUNT_COMMIT and _same_json(provenance["rows"], rows)
          and type(provenance["physical_boards"]) is int and provenance["physical_boards"] == 3 * BOARDS,
          "Pinned physical count provenance differs")
    priors = [{"sb_hand": pair["sb_hand"], "bb_hand": pair["bb_hand"],
               "prior_fraction": str(pair["prior"]),
               "showdown_mean_fraction": str(pair["showdown_mean"])} for pair in model["pairs"]]
    _need(_same_json(witness["pair_priors"], priors), "Conditioned priors or showdown means differ")

    census = witness["census"]
    census_keys = {"public_tree", "tree_counts", "sequences", "information_sets",
                    "flow_constraints", "payoff_matrix", "lp_preflight", "independent_numeric_counts"}
    _need(type(census) is dict and set(census) == census_keys, "Unexpected independent-model fields")
    _need(_same_json(census["public_tree"], _independent_tree_json(model)),
          "Public tree, action menu, contribution, or amount differs from literal game")
    _need(_same_json(census["tree_counts"], {"decision_nodes": 7, "fold_terminals": 6,
          "showdown_terminals": 6, "public_states": 19, "maximum_depth": 4}),
          "Public tree census mismatch")
    _need(_same_json(census["independent_numeric_counts"], {"decision_nodes": 7, "fold_terminals": 6,
          "continuations": 6, "public_states": 19}), "Independent numeric census mismatch")
    seq_rows = model["sequence_rows"]
    _need(_same_json(census["sequences"], {"sb": seq_rows[0], "bb": seq_rows[1]}),
          "Sequence identities or parent links differ")
    info_rows, flow_rows = _expected_infos_and_flows(model, seq_rows, model["ids_for_struct"])
    _need(_same_json(census["information_sets"], info_rows), "Information-set keys or actions differ")
    _need(_same_json(census["flow_constraints"], flow_rows), "Serialized flow equation labels differ")
    payoff = census["payoff_matrix"]
    _need(type(payoff) is dict and set(payoff) == {"row_sequence_ids", "column_sequence_ids", "fractions"}
          and _same_json(payoff["row_sequence_ids"], model["row_ids"])
          and _same_json(payoff["column_sequence_ids"], model["column_ids"]), "Payoff sequence labels differ")
    raw_matrix = payoff["fractions"]
    _need(type(raw_matrix) is list and len(raw_matrix) == len(model["row_ids"])
          and all(type(row) is list and len(row) == len(model["column_ids"]) for row in raw_matrix),
          "Payoff matrix dimensions exceed or differ from frozen model")
    _need(all(type(value) is str and len(value) <= 100 for row in raw_matrix for value in row),
          "Payoff matrix contains an unbounded Fraction string")
    matrix = [[_fraction(value, "payoff matrix entry") for value in row] for row in raw_matrix]
    _need(matrix == model["matrix_ordered"],
          "Payoff matrix differs from exact pinned showdown means")
    preflight = {"oop_guarantee": {"rows": 26, "columns": 82, "cells": 2241},
                 "ip_ceiling": {"rows": 28, "columns": 80, "cells": 2349}}
    _need(_same_json(census["lp_preflight"], preflight), "LP matrix dimensions changed")

    caps = {"rows": 96, "columns": 256, "cells": 25000, "pivots": 512,
            "updates": 10_000_000, "bits": 4096, "exact_work": 100_000,
            "exact_depth": 64, "exact_bits": 65_536}
    _need(_same_json(witness["caps"], caps), "Existing exact-LP caps were changed")
    flow_ids, flows = model["flow_ids"], model["aligned_flows"]
    x, q, sb_slack = _lp_invariants(witness["oop_lp"], kind="oop_guarantee",
        row_ids=model["row_ids"], col_ids=model["column_ids"], flow_ids=flow_ids,
        matrix=matrix, flows=flows, preflight=preflight["oop_guarantee"])
    y, p, bb_slack = _lp_invariants(witness["ip_lp"], kind="ip_ceiling",
        row_ids=model["row_ids"], col_ids=model["column_ids"], flow_ids=flow_ids,
        matrix=matrix, flows=flows, preflight=preflight["ip_ceiling"])
    for kind, lp in (("oop_guarantee", witness["oop_lp"]), ("ip_ceiling", witness["ip_lp"])):
        labels, constraints = _expected_lp_labels(kind, model["row_ids"], model["column_ids"], flow_ids)
        _need(_same_json(lp["variable_labels"], labels) and _same_json(lp["constraint_labels"], constraints),
              f"{kind} labels differ from original primal/dual inequalities")

    policies = _policy_map(witness, model, x, y)
    matrix_value = sum((x[i] * matrix[i][j] * y[j]
                        for i in range(len(x)) for j in range(len(y))), F(0))
    recursive_value = sum((pair["prior"] * _profile_value(model["root"], pair, policies)
                           for pair in model["pairs"]), F(0))
    _need(matrix_value == recursive_value, "Matrix and public-tree policy values disagree")
    sb_br = _best_response(model, policies, 0)
    bb_br = _best_response(model, policies, 1)
    _need(sb_br == matrix_value == bb_br,
          "Legal own-hand best response exposes nonzero exploitability")

    eq = witness["equilibrium"]
    eq_keys = {"utility_perspective", "lower_bound_fraction", "upper_bound_fraction",
               "profile_value_fraction", "gap_fraction", "nash_conv_fraction", "flow_residuals",
               "complementary_slackness", "policy_normalization"}
    _need(type(eq) is dict and set(eq) == eq_keys and eq["utility_perspective"] == "sb_net_transfer_chips"
          and _fraction(eq["lower_bound_fraction"], "lower bound") == q[0]
          and _fraction(eq["upper_bound_fraction"], "upper bound") == p[0]
          and _fraction(eq["profile_value_fraction"], "profile value") == matrix_value
          and _fraction(eq["gap_fraction"], "primal-dual gap") == p[0] - q[0] == 0
          and _fraction(eq["nash_conv_fraction"], "NashConv") == sb_br - bb_br == 0
          and eq["policy_normalization"] == "exact", "Equilibrium bounds or zero-gap claim is false")
    _need(eq["flow_residuals"] == _residual_rows(model, x, y), "Serialized flow residuals are false")
    _need(eq["complementary_slackness"] == {
          "sb_realization_dot_ip_slack": "0", "bb_realization_dot_oop_slack": "0"}
          and sum((a*b for a,b in zip(x, bb_slack)), F(0)) == 0
          and sum((a*b for a,b in zip(y, sb_slack)), F(0)) == 0,
          "Complementary slackness does not hold")
    return {"status": "passed", "certificate_id": witness["certificate_id"],
            "artifact_sha256": digest, "verified_count_pairs": len(model["pairs"]),
            "verified_physical_boards": 3 * BOARDS,
            "raw_compatible_pair_weight_normalizer": str(model["prior_normalizer"]),
            "blocked_private_pair": [model["rejected_pairs"][0][0],
                                     model["rejected_pairs"][0][1],
                                     str(model["rejected_pairs"][0][2])],
            "public_states": len(model["nodes"]) + len(model["terminals"]),
            "information_sets": [len(model["infos"][0]), len(model["infos"][1])],
            "sequences": [len(model["sequences"][0]), len(model["sequences"][1])],
            "payoff_matrix_shape": [len(matrix), len(matrix[0])],
            "utility_perspective": "sb_net_transfer_chips",
            "value_fraction": str(matrix_value),
            "value_sb_fraction": str(matrix_value), "value_bb_fraction": str(-matrix_value),
            "sb_best_response_fraction": str(sb_br),
            "bb_best_response_fraction": str(-bb_br),
            "bb_best_response_sb_value_fraction": str(bb_br),
            "best_response_utility_perspectives": {
                "sb_best_response_fraction": "sb_own_utility",
                "bb_best_response_fraction": "bb_own_utility",
                "bb_best_response_sb_value_fraction": "sb_net_transfer_value_at_bb_best_response",
            },
            "nash_conv_fraction": str(sb_br - bb_br),
            "rank_calls": 0, "board_enumerations": 0,
            "scope": "One exact finite weighted preflop game with forced showdown/checkdown."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="Candidate witness JSON; the file is only parsed as data")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    limit = 1_000_000
    _need(args.input.stat().st_size <= limit, "Certificate file exceeds 1 MB verifier limit")
    with args.input.open("rb") as source:
        raw = source.read(limit + 1)
    _need(len(raw) <= limit, "Certificate file exceeds 1 MB verifier limit")
    def pairs_no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            _need(key not in result, "Duplicate certificate JSON key")
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError(f"Nonfinite JSON value: {value}")
    parsed = json.loads(raw, object_pairs_hook=pairs_no_duplicates, parse_constant=reject_constant)
    result = verify_certificate(parsed)
    text = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
