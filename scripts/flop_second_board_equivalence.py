"""No-training tree and own-hand policy proof for the fixed second flop.

All published first-board sources are preserved. This module uses the fresh
second-board reference anchors and admits no training or convergence claim.
"""
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
import struct

from scripts import flop_public_classes as shared
from scripts import flop_second_board_plan as planning
from scripts import flop_second_board_reference as reference
from scripts import flop_second_board_partition_proof as partition_proof
from scripts import verify_flop_second_board_reference_publication as prerequisite


physical, candidate = reference.physical, reference.candidate
_need, _typed, _digest = shared._need, shared._typed, shared._digest
BOARD = ("7c", "8d", "9h")
MODES = ("check-call", "bet-fold", "class-varying", "zero-reach")
MAX_POLICY_ROWS, MAX_WORLD_PATH_STATES, MAX_COMPACT_WORLDS = 20000, 33, 170
METRICS = shared.METRICS


@dataclass(frozen=True)
class SecondBoardModel:
    physical: dict
    partition: dict
    turns: dict
    rivers: dict
    worlds: tuple
    root: object
    census: dict
    preparation_rank_calls: int


def admission():
    plan = planning.admit_plan()
    _need(plan["board"] == list(BOARD) and physical.MAX_PUBLIC_STATES == 250000
          and physical.MAX_DECISIONS == 10000 and candidate.MAX_WORLDS == 5940
          and reference.MAX_PREPARATION_RANK_CALLS == 11880
          and _typed(reference.CONFIG) == _typed({
              "pot": 10, "effective_stack": 5, "bet_sizes": [0.5],
              "raise_sizes": [], "max_raises": 0, "include_all_in": False}),
          "Second-board physical capacity differs")
    return {"fixture": plan, "physical_builds": 1, "preparation_rank_call_limit": 11880,
            "physical_worlds": 5940, "maximum_compact_worlds": MAX_COMPACT_WORLDS,
            "maximum_policy_rows": MAX_POLICY_ROWS,
            "maximum_world_path_states": MAX_WORLD_PATH_STATES, "training_calls": 0,
            "interpretation": "Named model/world/policy/path bounds only, not full-call work, memory or RSS."}


def _walk(root, cap=250000):
    pending, seen, nodes = [(root, 1)], set(), []
    while pending:
        node, depth = pending.pop()
        _need(id(node) not in seen and len(seen) < cap and depth <= reference.MAX_TREE_DEPTH,
              "Tree aliases, cycles or exceeds its node/depth bound")
        seen.add(id(node))
        nodes.append(node)
        if type(node) is physical._Decision:
            _need(type(node.children) is tuple and len(node.children) == len(node.actions) == 2,
                  "Fixed decision choices differ")
            pending.extend((child, depth + 1) for child in node.children)
        elif type(node) is physical._Chance:
            _need(type(node.branches) is dict and 0 < len(node.branches) <= 49,
                  "Chance branch count differs")
            pending.extend((child, depth + 1) for child in node.branches.values())
        else:
            _need(type(node) is physical._Terminal, "Unknown numeric node type")
        _need(len(pending) <= reference.MAX_TREE_STACK, "Tree traversal stack exceeds bound")
    return nodes


def _physical_anchor(oracle, preparation_rank_calls):
    admission()
    plan = planning.plan_second_board()
    _need(type(preparation_rank_calls) is int and preparation_rank_calls == 4134,
          "Fresh preparation rank calls differ from the second-board reference")
    reference._validate_world_rows(plan, oracle)
    _, tree_hash, tree_census = reference._bounded_tree(oracle, BOARD)
    reference._metadata_check(plan, oracle, tree_census, preparation_rank_calls)
    world_view = [[oop, ip, mass.numerator, mass.denominator, sign, list(board)]
                  for oop, ip, mass, sign, board in oracle["worlds"]]
    _need(_digest(world_view) == prerequisite.WORLDS_SHA256 and tree_hash == prerequisite.TREE_SHA256,
          "Fresh physical world/tree differs from published second-board anchors")
    active = defaultdict(set)
    for world in oracle["worlds"]:
        for length in range(3):
            for player in (0, 1):
                active[(player, world[4][3:3 + length])].add(world[player])
    _need(_typed(oracle.get("active_hands_by_prefix")) == _typed(dict(active)),
          "Physical own-hand visibility differs from complete fresh worlds")
    return tree_census


def _collapse(root, turns, rivers, *, expected_nodes):
    """Compare every mapped descendant subtree at both physical reveals."""
    _need(type(expected_nodes) is int and 0 < expected_nodes <= 250000,
          "Expected physical node count is unadmitted")
    visited, compared = 0, 0

    def visit(node, depth):
        nonlocal visited, compared
        _need(visited < expected_nodes and depth <= reference.MAX_TREE_DEPTH,
              "Complete subtree comparison exceeds admitted physical tree")
        visited += 1
        history = shared._mapped_history(node.history, turns, rivers)
        if type(node) is physical._Terminal:
            out = physical._Terminal(history, node.kind, node.contributions, node.winner)
        elif type(node) is physical._Decision:
            out = physical._Decision(history, node.player, node.street,
                                     BOARD + physical._revealed(history), deepcopy(node.actions),
                                     [visit(child, depth + 1)[0] for child in node.children])
        else:
            _need(type(node) is physical._Chance, "Unknown chance node in subtree comparison")
            previous = physical._revealed(node.history)
            branches, structures = {}, {}
            for card, child in sorted(node.branches.items()):
                label = turns[card] if node.card_index == 3 else rivers[(previous[0], card)]
                collapsed, structure = visit(child, depth + 1)
                if label in structures:
                    _need(structure == structures[label],
                          "Entire numeric betting subtree changes within a reveal class")
                else:
                    structures[label], branches[label] = structure, collapsed
                compared += 1
            out = physical._Chance(history, node.card_index, node.street, branches)
        return out, shared._structure(out)

    collapsed_root, structure = visit(root, 1)
    _need(visited == expected_nodes, "Subtree comparison omitted a physical node")
    return collapsed_root, {"physical_nodes_checked": visited,
                            "physical_branch_subtrees_compared": compared,
                            "compact_tree_sha256": _digest(structure)}


def _expected_rows(oracle):
    rows = {}
    for node in _walk(oracle["root"]):
        if type(node) is physical._Decision:
            hands = oracle["active_hands_by_prefix"][(node.player, physical._revealed(node.history))]
            _need(type(hands) is set and 0 < len(hands) <= 2, "Own-hand row support differs")
            for hand in hands:
                _need(len(rows) < MAX_POLICY_ROWS, "Physical policy rows exceed admission")
                key = (node.player, hand, node.history)
                _need(key not in rows, "Duplicate physical own-hand information set")
                rows[key] = node
    return rows


def _path_bound(root, worlds):
    maximum, total = 0, 0
    for world in worlds:
        pending, visits = [root], 0
        while pending:
            node = pending.pop()
            _need(visits < MAX_WORLD_PATH_STATES, "World action traversal exceeds admitted path")
            visits += 1
            if type(node) is physical._Chance:
                pending.append(node.branches[world[4][node.card_index]])
            elif type(node) is physical._Decision:
                pending.extend(node.children)
            else:
                _need(type(node) is physical._Terminal, "Unknown path node")
        maximum, total = max(maximum, visits), total + visits
    return maximum, total


def _make_model(oracle, partition, preparation_rank_calls):
    tree_census = _physical_anchor(oracle, preparation_rank_calls)
    _need(type(partition) is dict and type(partition.get("turn_class_count")) is int
          and partition["turn_class_count"] == 13 and type(partition.get("river_class_count")) is int
          and partition["river_class_count"] == 17 and type(partition.get("class_worlds")) is list
          and len(partition["class_worlds"]) == MAX_COMPACT_WORLDS,
          "Candidate dimensions differ from published second-board reference")
    turns, rivers, worlds, mass_census = partition_proof.verify_partition(
        partition, oracle["worlds"], board=BOARD)
    _need(len(worlds) == MAX_COMPACT_WORLDS, "Compact world support differs from fresh reference")
    root, census = _collapse(oracle["root"], turns, rivers,
                             expected_nodes=tree_census["public_states"])
    physical_rows = _expected_rows(oracle)
    keys = {(p, hand, shared._mapped_history(history, turns, rivers))
            for p, hand, history in physical_rows}
    nodes = _walk(root)
    physical_path, physical_visits = _path_bound(oracle["root"], oracle["worlds"])
    compact_path, compact_visits = _path_bound(root, worlds)
    census.update(compact_public_states=len(nodes),
                  compact_decisions=sum(type(node) is physical._Decision for node in nodes),
                  compact_chance_nodes=sum(type(node) is physical._Chance for node in nodes),
                  compact_terminals=sum(type(node) is physical._Terminal for node in nodes),
                  physical_policy_rows=len(physical_rows), compact_policy_rows=len(keys),
                  physical_action_slots=2 * len(physical_rows), compact_action_slots=2 * len(keys),
                  compact_worlds=len(worlds), turn_classes=13, river_signatures=17,
                  maximum_physical_world_path=physical_path, maximum_compact_world_path=compact_path,
                  physical_world_path_visits=physical_visits, compact_world_path_visits=compact_visits,
                  partition_proof=mass_census)
    return SecondBoardModel(oracle, partition, turns, rivers, tuple(worlds), root,
                            census, preparation_rank_calls)


def build_model(*, progress=None):
    if progress is None:
        progress = {}
    _need(type(progress) is dict, "Expected an exact progress mapping")
    admission()  # model admission precedes saved authentication and fresh ranking
    progress.update(physical_builds_attempted=0, physical_builds_completed=0,
                    preparation_ranker_attempts=0, preparation_rank_calls=0,
                    phase="saved-reference-authentication")
    receipt = prerequisite.verify()
    _need(receipt.get("status") == "saved-second-board-reference-authenticated" and
          receipt.get("physical_builds") == receipt.get("ranking_calls") == 0,
          "Second-board saved prerequisite differs")
    progress["prerequisite"] = receipt
    progress["phase"] = "fresh-physical-preparation"
    plan, original_ranker = planning.plan_second_board(), physical.independent_rank

    def counted_ranker(key):
        progress["preparation_ranker_attempts"] += 1
        _need(progress["preparation_ranker_attempts"] <= 11880, "Preparation rank allowance exceeded")
        progress["preparation_rank_calls"] += 1
        return original_ranker(key)

    rows = lambda values: [[hand, str(weight)] for hand, weight in values]
    physical.independent_rank = counted_ranker
    try:
        progress["physical_builds_attempted"] += 1
        oracle = physical.prepare_oracle(BOARD, rows(plan.oop_ranges), rows(plan.ip_ranges),
                                         deepcopy(reference.CONFIG))
        progress["physical_builds_completed"] += 1
    finally:
        physical.independent_rank = original_ranker
    progress["phase"] = "fresh-candidate-partition"
    partition = candidate.build_candidate(shared._world_rows(oracle["worlds"]), board=BOARD)
    progress["candidate_dimensions"] = {key: partition[key] for key in (
        "turn_class_count", "river_class_count", "physical_world_count")}
    progress["candidate_dimensions"]["class_worlds"] = len(partition["class_worlds"])
    progress["phase"] = "full-model-proof"
    model = _make_model(oracle, partition, progress["preparation_rank_calls"])
    progress["phase"] = "complete"
    return model


def validate_model(model):
    _need(type(model) is SecondBoardModel, "Expected exact second-board model")
    rebuilt = _make_model(model.physical, model.partition, model.preparation_rank_calls)
    _need(all(_typed(getattr(model, key)) == _typed(getattr(rebuilt, key))
              for key in ("turns", "rivers", "worlds", "census"))
          and shared._structure(model.root) == shared._structure(rebuilt.root),
          "Second-board model differs from full independent reconstruction")
    return dict(rebuilt.census)


def _class_rows(model):
    return {(player, hand, shared._mapped_history(history, model.turns, model.rivers)): node
            for (player, hand, history), node in _expected_rows(model.physical).items()}


def _project(payload, model):
    physical_rows = physical._validate_policy(payload, model.physical, 1e-10)
    projected, bits = {}, {}
    for (player, hand, history), values in physical_rows.items():
        shared._probabilities(values)
        key = (player, hand, shared._mapped_history(history, model.turns, model.rivers))
        raw = tuple(struct.pack(">d", value) for value in values)
        _need(key not in bits or bits[key] == raw,
              "Within-class physical-card probabilities differ bitwise")
        projected[key], bits[key] = values, raw
    _need(set(projected) == set(_class_rows(model)), "Projected row support differs")
    return projected, physical_rows


def project_policy(payload, model):
    validate_model(model)
    return _project(payload, model)[0]


def _lift(rows, model, metrics):
    _need(type(rows) is dict and set(rows) == set(_class_rows(model)),
          "Compact policy row support differs")
    oracle, strategy = model.physical, []
    for (player, hand, history), node in sorted(_expected_rows(oracle).items()):
        key = (player, hand, shared._mapped_history(history, model.turns, model.rivers))
        values = shared._probabilities(rows[key])
        actions = [{field: action[field] for field in ("name", "amount", "raise_to", "history_key")}
                   for action in node.actions]
        for action, probability in zip(actions, values):
            action["probability"] = probability
        strategy.append({"player": "oop" if player == 0 else "ip", "hand": hand,
                         "history": list(history), "street": node.street,
                         "board": list(node.board), "actions": actions})
    return {"solver_version": "configured-postflop-v1", "algorithm": "no-training-second-board-control",
            "strategy_schema": "postflop-strategy-v1", "board": list(BOARD),
            "config": deepcopy(oracle["config"]), "street_configs": deepcopy(oracle["street_configs"]),
            "pot": oracle["pot"], "effective_stack": list(oracle["effective_stack"]),
            "runout_mode": "full-deck", "runouts": [list(row) for row in oracle["runouts"]],
            "reachable_runouts": [list(row) for row in oracle["reachable_runouts"]],
            "worlds": len(oracle["worlds"]), "compatible_pairs": 3, "deals": 3,
            "info_sets": len(strategy), "strategy": strategy,
            **{key: oracle[key] for key in ("public_nodes", "public_states", "chance_nodes", "terminal_nodes")},
            **{key: float(value) for key, value in metrics.items()}}


def control_rows(model, mode):
    _need(mode in MODES, "Unknown second-board control")
    rows = {}
    for key, node in sorted(_class_rows(model).items()):
        if mode == "check-call":
            first = 1.0 if node.actions[0]["name"] == "check" else 0.0
        elif mode == "bet-fold":
            first = 0.0 if node.actions[0]["name"] == "check" else 1.0
        elif mode == "zero-reach":
            first = 1.0
        else:
            first = (int(_digest([key[0], key[1], list(key[2])])[:8], 16) % 5) / 4.0
        rows[key] = (first, 1.0 - first)
    return rows


def audit_control(model, mode, *, observation=None):
    """Validate on entry/exit and retain all actions and zero-reach rows."""
    _need(type(mode) is str and mode in MODES, "Unknown second-board control")
    if observation is None:
        observation = {}
    _need(type(observation) is dict, "Expected exact mutable control observation")
    observation.update(mode=mode, phase="entry-model-validation", status="running")
    validate_model(model)
    first_error = None
    try:
        observation["phase"] = "compact-exact-metrics"
        rows = control_rows(model, mode)
        serial_rows = [[p, hand, list(history), list(values)]
                       for (p, hand, history), values in sorted(rows.items())]
        observation.update(class_policy=serial_rows, class_rows=len(rows))
        compact = shared._exact_metrics(model.root, model.worlds, rows)
        observation["exact_compact_metrics"] = {key: str(value) for key, value in compact.items()}
        payload = _lift(rows, model, compact)
        observation.update(physical_policy=payload, phase="physical-policy-projection")
        projected, physical_rows = _project(payload, model)
        observation["physical_rows"] = len(physical_rows)
        _need(_typed(projected) == _typed(rows), "Control lift/project changed compact probabilities")
        observation["phase"] = "unrestricted-physical-exact-metrics"
        full = shared._exact_metrics(model.physical["root"], model.physical["worlds"], physical_rows)
        observation["exact_physical_metrics"] = {key: str(value) for key, value in full.items()}
        _need(compact == full, "Exact compact and unrestricted physical responses differ")
        observation["phase"] = "independent-numeric-replay"
        numeric = physical.replay(payload, model.physical)
        gaps = {key: abs(float(full[key]) - numeric[key]) for key in METRICS}
        observation.update(numeric_metrics={key: numeric[key] for key in METRICS},
                           maximum_numeric_gap=max(gaps.values()))
        _need(max(gaps.values()) <= 1e-10, "Independent numeric physical replay differs")
        observation.update(physical_policy_sha256=_digest(payload),
                           class_policy_sha256=_digest(serial_rows))
        return {"mode": mode, "physical_policy": payload, "class_policy": serial_rows,
                "physical_policy_sha256": observation["physical_policy_sha256"],
                "class_policy_sha256": observation["class_policy_sha256"],
                "physical_rows": len(physical_rows), "class_rows": len(rows),
                "exact_metrics": {key: str(value) for key, value in full.items()},
                "numeric_metrics": {key: numeric[key] for key in METRICS},
                "maximum_numeric_gap": max(gaps.values())}
    except BaseException as exc:
        first_error = exc
        observation.update(status="error", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        try:
            validate_model(model)
            observation["final_model_validation"] = "passed"
            if first_error is None:
                observation.update(status="complete", phase="complete")
        except BaseException as cleanup_error:
            observation["final_model_validation"] = "failed"
            observation["cleanup_error"] = f"{type(cleanup_error).__name__}: {cleanup_error}"
            observation["status"] = "error"
            if first_error is None:
                raise
            first_error.second_board_cleanup_error = f"{type(cleanup_error).__name__}: {cleanup_error}"
