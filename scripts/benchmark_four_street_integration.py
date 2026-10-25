"""One frozen four-street quality attempt with saved-only audit evidence.

This command never retries or resumes an attempt. Training is entered at most
once, and only after a clean committed-source snapshot plus both independent
and production full-request admission receipts have been saved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from fractions import Fraction
import platform
import re
import stat
import subprocess
import sys
import time
import uuid

from pokerlab.four_street_solver import solve_four_street
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions
from scripts import benchmark_river_heldout_quality as source_helper
from scripts import four_street_certificate as certificate
from scripts import four_street_validation as numeric


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ID = "four-street-integration-v1"
SOURCE_IDENTITY = "four-street-frozen-runner-v1"
ITERATIONS = 1000
TARGET_NASH_CONV = "1/1000"
EXPECTED_SOURCE_RE = re.compile(r"^[0-9a-f]{40}$")
RAW_LIMIT = 16 * 1024 * 1024
JSON_LIMIT = 32 * 1024 * 1024
SMALL_JSON_LIMIT = 1024 * 1024
TOTAL_LIMIT = 256 * 1024 * 1024
FILE_LIMIT = 14
MAX_JSON_NODES = 1_000_000
MAX_JSON_DEPTH = 80
BENCHMARK_RELATIVE = "benchmarks/four-street-integration-v1.json"
PROTOCOL_RELATIVE = "docs/four-street-integration-protocol.md"
RIVER_PROTOCOL_RELATIVE = "docs/river-heldout-quality-protocol.md"
U5_VERIFIER_RELATIVE = "scripts/verify_four_street_integration_publication.py"
ARTIFACT_NAMES = frozenset({
    "attempt.json", "claim.json", "source-before.json", "production-admission.json",
    "exact-admission.json", "raw-envelope.json", "raw-receipt.json",
    "numeric-replay.json", "exact-certificate.json", "source-after.json",
    "report.json", "failure.json", "status.json",
})


def _literal_case():
    return {
        "id": "four-street-weighted-shared-future-v1",
        "sb_range": "AsAd:0.5,QsQd:0.25",
        "bb_range": "KsKd:0.75,JhJd:0.25",
        "config": {"small_blind": 0.5, "big_blind": 1,
                   "starting_stack": [8, 8], "raise_sizes": [0.5],
                   "max_raises": 1, "include_all_in": False},
        "runouts": ["2c3c4d7h8h", "2c3c4d7hKc", "2c3c4dKc8h",
                    "2c3c4dQd8h", "5c6d7s8c9h", "5c6d7s8cJc"],
        "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                         "max_raises": 0, "include_all_in": False},
        "turn_config": {"bet_sizes": [0.5], "raise_sizes": [],
                         "max_raises": 0, "include_all_in": False},
        "river_config": {"bet_sizes": [0.5], "raise_sizes": [],
                          "max_raises": 0, "include_all_in": False},
    }


def _literal_request():
    case = _literal_case()
    stage = lambda value: PostflopActions(
        bet_sizes=tuple(value["bet_sizes"]), raise_sizes=tuple(value["raise_sizes"]),
        max_raises=value["max_raises"], include_all_in=value["include_all_in"])
    return FourStreetSolveRequest(
        sb_range=case["sb_range"], bb_range=case["bb_range"],
        runouts=tuple(case["runouts"]),
        preflop_config=PreflopConfig.from_dict(case["config"]),
        flop_actions=stage(case["flop_config"]),
        turn_actions=stage(case["turn_config"]),
        river_actions=stage(case["river_config"]), iterations=ITERATIONS,
        algorithm="cfrplus", traversal="public-batched",
        diagnostics="public-batched", resource_model="public-vector")


def _fixed_selectors():
    return {
        "calls": 1, "iterations": ITERATIONS, "algorithm": "cfrplus",
        "traversal": "public-batched", "diagnostics": "public-batched",
        "resource_model": "public-vector", "postflop_scope": "all-streets",
        "averaging_delay": 0, "tree_admission": "decision-count",
        "target_nash_conv_big_blinds": TARGET_NASH_CONV,
        "criterion": "exact-normalized-complete-policy-whole-game-gap",
        "early_stopping": False, "retries": 0,
    }


def _strict_json(data: bytes, *, max_bytes: int):
    if type(data) is not bytes or len(data) > max_bytes:
        raise ValueError("JSON artifact exceeds its byte limit")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("JSON artifact contains a duplicate object key")
            result[key] = value
        return result

    def bad_constant(_value):
        raise ValueError("JSON artifact contains a nonfinite number")

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=bad_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("JSON artifact is malformed or exceeds parser depth") from exc
    count = 0
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        count += 1
        if count > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise ValueError("JSON artifact exceeds bounded node count or nesting")
        if type(item) is dict:
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is float and not math.isfinite(item):
            raise ValueError("JSON artifact contains a nonfinite number")
    return value


def _json_bytes(value, *, pretty=False):
    if pretty:
        return (json.dumps(value, sort_keys=True, indent=2,
                           allow_nan=False) + "\n").encode("utf-8")
    return source_helper._canonical_json_bytes(value)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _check_script_inventory(expected_commit):
    result = subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), "ls-tree", "-r", "--name-only",
         expected_commit, "--", "scripts"], text=True, stderr=subprocess.STDOUT)
    committed = {name for name in result.splitlines() if name.endswith(".py")}
    working = {path.relative_to(REPO_ROOT).as_posix()
               for path in (REPO_ROOT / "scripts").rglob("*.py")}
    if committed != working:
        raise RuntimeError("Committed and working scripts Python inventories differ")
    required = {"scripts/benchmark_four_street_integration.py",
                U5_VERIFIER_RELATIVE}
    if not required.issubset(committed):
        raise RuntimeError(f"Frozen U5 Python inventory is incomplete: {sorted(required - committed)}")


def _capture_source_state(expected_commit):
    """Reuse the river's original snapshot, then authenticate the added closure."""
    _check_script_inventory(expected_commit)
    state = source_helper._capture_source_state(expected_commit)
    existing = set(state["files"])
    extras = {path.relative_to(REPO_ROOT).as_posix(): path
              for path in sorted((REPO_ROOT / "scripts").rglob("*.py"))}
    for relative in (BENCHMARK_RELATIVE, PROTOCOL_RELATIVE):
        extras[relative] = REPO_ROOT / relative
    extras = {name: path for name, path in extras.items() if name not in existing}
    missing = [name for name, path in extras.items() if not path.is_file()]
    if missing:
        raise ValueError(f"Frozen U5 inventory is incomplete: {missing}")
    names = sorted(extras)
    request = "".join(f"{expected_commit}:{name}\n" for name in names)
    batch = subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), "cat-file", "--batch"],
        input=request.encode("utf-8"), stderr=subprocess.PIPE)
    offset = 0
    for name in names:
        raw = extras[name].read_bytes()
        normalized = source_helper._normalized_lf(raw)
        header_end = batch.find(b"\n", offset)
        header = batch[offset:header_end].split()
        if header_end < 0 or len(header) != 3 or header[1] != b"blob" or not header[2].isdigit():
            raise RuntimeError(f"Expected committed source blob is missing: {name}")
        blob, size = header[0].decode("ascii"), int(header[2])
        offset = header_end + 1
        committed = batch[offset:offset + size]
        offset += size
        if len(committed) != size or batch[offset:offset + 1] != b"\n":
            raise RuntimeError("Committed source batch has an invalid object boundary")
        offset += 1
        if normalized != source_helper._normalized_lf(committed):
            raise RuntimeError(f"Working source differs from expected commit: {name}")
        state["files"][name] = {
            "bytes": len(raw), "raw_sha256": source_helper._sha256(raw),
            "normalized_lf_sha256": source_helper._sha256(normalized), "git_blob": blob,
        }
    if offset != len(batch):
        raise RuntimeError("Committed source batch has unexpected trailing data")
    head, status = source_helper._git_info()
    if head != expected_commit or status.strip():
        raise RuntimeError("Source checkout changed while extending frozen inventory")
    state["inventory_policy"] = "all committed pokerlab and scripts Python, plus pinned U5 fixture/protocol and reused river protocol"
    return state


def _same_source_state(expected, observed):
    if observed != expected:
        raise RuntimeError("Frozen source, HEAD, or clean worktree state changed during attempt")


def _check_fixture():
    path = REPO_ROOT / BENCHMARK_RELATIVE
    manifest = _strict_json(path.read_bytes(), max_bytes=JSON_LIMIT)
    if (manifest.get("benchmark_id") != BENCHMARK_ID or
            manifest.get("case") != _literal_case() or
            manifest.get("quality_run") != _fixed_selectors()):
        raise RuntimeError("Committed benchmark differs from the fixed U5 literal manifest/selectors")
    return manifest


def _independent_admission(case):
    forecast = certificate.forecast_exact(case)
    model = numeric.build_model(case)
    expected = {"worlds": 22, "public_states": 1414, "decisions": 628,
                "information_rows": 1200}
    model_receipt = forecast["preparation_receipts"]["independent_model_build"]
    for key, value in expected.items():
        observed = model_receipt.get(key)
        if observed != value:
            raise ValueError(f"Independent exact admission {key} differs from the fixed support: {observed}")
    if (model.counts["worlds"] != forecast["worlds"] or
            model.counts["public_states"] != forecast["tree_nodes"] or
            model.counts["infos"] != forecast["information_rows"] or
            model.counts["slots"] != forecast["action_slots"]):
        raise ValueError("Independent exact admission census changed between fresh preparations")
    if not forecast.get("admitted"):
        raise ValueError(f"Exact certificate forecast exceeds its hard work limit: {forecast!r}")
    sign_counts = {"sb_win": 0, "tie": 0, "bb_win": 0}
    for world in model.worlds:
        sign_counts[{1: "sb_win", 0: "tie", -1: "bb_win"}[world["sign"]]] += 1
    return {"schema": "four-street-exact-admission-v1", "forecast": forecast,
            "world_sign_counts": sign_counts,
            "pair_probabilities": model.counts["pair_probabilities"],
            "world_support": [
                {"hands": ["".join(hand) for hand in world["hands"]],
                 "board": list(world["board"]), "sign": world["sign"],
                 "weight": str(world["weight"])}
                for world in model.worlds],
            "admitted": True, "attempted_training": False}


def _production_admission(request):
    """Mirror fixed production setup and all relevant admissions; never train."""
    from pokerlab import preflop_solver as solver
    from pokerlab.public_cfr import MAX_PREFIX_EDGES

    case = _literal_case()
    config = request.preflop_config
    specs = solver._stage_configs(case["flop_config"], case["turn_config"], case["river_config"])
    hands, worlds, compatible_pairs, pair_probabilities, selected, preflight_checks = \
        solver._enumerate_physical_worlds(
            request.sb_range, request.bb_range, request.runouts, request.iterations)
    preflop_tree = solver.build_preflop_tree(config)
    (root, public_states, decisions, world_decision_work, plan_ops,
     max_template_states, max_template_decisions) = solver._merge_preflop_tree(
        preflop_tree, worlds, specs, request.traversal,
        request.iterations * 3, "all-streets", enforce_world_work=False)
    legal = solver._legal_private_hands(worlds, "all-streets")
    infos = {}
    info_action_slots = 0
    for node in solver._all_nodes(root):
        prefix = solver._revealed_board(node.history)
        for hand_index in sorted(legal.get((node.player, prefix), ())):
            info_action_slots += len(node.actions)
            if info_action_slots > solver.MAX_INFO_ACTION_SLOTS:
                raise ValueError("Public-vector information-set action slots exceed 1,000,000.")
            infos[(node.player, hand_index, node.history)] = len(node.actions)
    vector = solver.estimate_vector_budget(
        root, worlds, infos, request.iterations, request.algorithm,
        chance_type=solver._Chance)
    from pokerlab.preflop_vector_budget import MAX_DENSE_PREFIX_SLOTS
    if ("prefix_edges" not in vector or "dense_prefix_slots" not in vector or
            "prefix_edge_limit" not in vector or
            "dense_prefix_slot_limit" not in vector or
            "information_set_action_slot_limit" not in vector or
            "total_loop_entries_upper_bound" not in vector or
            "total_loop_entry_limit" not in vector):
        raise ValueError("production vector admission receipt omitted required guard counters")
    if (vector["prefix_edge_limit"] != MAX_PREFIX_EDGES or
            vector["dense_prefix_slot_limit"] != MAX_DENSE_PREFIX_SLOTS or
            vector["information_set_action_slot_limit"] != solver.MAX_INFO_ACTION_SLOTS or
            vector["total_loop_entry_limit"] != solver.MAX_TOTAL_LOOP_ENTRIES):
        raise ValueError("production vector admission limits differ from the fixed solver caps")
    if vector["prefix_edges"] > solver.MAX_PREFIX_EDGES:
        raise ValueError("Public-vector training prefix edges exceed 250,000.")
    if vector["dense_prefix_slots"] > MAX_DENSE_PREFIX_SLOTS:
        raise ValueError("Public-vector dense prefix slots exceed 2,000,000.")

    # Training view construction is a separate pre-allocation bound in the
    # entry point. It is safe in preparation: this only clones and validates.
    training_root, anchor, view_states = solver._positive_pot_training_view(root)
    if view_states > solver._MAX_PUBLIC_STATES:
        raise ValueError("Public-batched training view exceeds 250,000 public states.")
    prefix_edges = MAX_PREFIX_EDGES
    sign_counts = {"sb_win": 0, "tie": 0, "bb_win": 0}
    production_world_support = []
    for world in worlds:
        sign_counts[{1: "sb_win", 0: "tie", -1: "bb_win"}[world[3]]] += 1
        production_world_support.append({
            "hands": ["".join(hands[0][world[0]]), "".join(hands[1][world[1]])],
            "board": [world[4][index:index + 2] for index in (0, 2, 4)] + list(world[5:7]),
            "sign": world[3], "weight": world[2]})
    result = {
        "schema": "four-street-production-admission-v1",
        "admitted": True,
        "attempted_training": False,
        "request": request.to_dict(),
        "counts": {"candidate_private_pairs": len(hands[0]) * len(hands[1]),
                   "compatible_private_pairs": compatible_pairs,
                   "worlds": len(worlds), "pair_runout_preflight_checks": preflight_checks,
                   "public_states": public_states, "decisions": decisions,
                   "information_sets": len(infos), "information_set_action_slots": info_action_slots,
                   "world_decision_work": world_decision_work,
                   "temporary_template_peak_states": max_template_states,
                   "temporary_template_peak_decisions": max_template_decisions,
                   "positive_pot_training_view_states": view_states,
                   "positive_pot_training_anchor": anchor},
        "physical_pair_probabilities": pair_probabilities,
        "world_sign_counts": sign_counts,
        "world_support": production_world_support,
        "vector_budget": vector,
        "caps": {"candidate_pair_iterations": solver._MAX_CANDIDATE_HAND_ITERATIONS,
                 "world_iterations": solver._MAX_WORLD_ITERATIONS,
                 "pair_runout_preflight_checks": solver._MAX_PAIR_RUNOUT_PREFLIGHT_CHECKS,
                 "world_decision_work": solver._MAX_WORLD_NODE_WORK,
                 "public_states": solver._MAX_PUBLIC_STATES,
                 "decision_nodes": solver._MAX_PUBLIC_NODES,
                 "information_set_action_slots": solver.MAX_INFO_ACTION_SLOTS,
                 "vector_prefix_edges": prefix_edges},
        "training_request": {"iterations_requested": request.iterations,
                             "algorithm": request.algorithm,
                             "modeled_expected_training_passes": 3 * request.iterations,
                             "actual_training_passes_observed": None},
    }
    # Release all large prepared trees immediately after the receipt is built.
    training_root = root = preflop_tree = None
    worlds = hands = infos = legal = None
    return result


def _assert_envelope(envelope, request):
    if type(envelope) is not dict:
        raise ValueError("raw solve envelope must be an object")
    if envelope.get("schema_version") != "four-street-solve-v1":
        raise ValueError("raw solve envelope has an unsupported schema")
    if envelope.get("request") != request.to_dict():
        raise ValueError("raw solve envelope request differs from the frozen request")
    identities = envelope.get("identities")
    expected_identities = {
        "seats": "sb-button-0-bb-1", "scope": "all-streets",
        "numerical_model": "binary64-local-nine-decimal-whole-hand-v1",
        "chance_model": "conditioned-ordered-selected-runouts",
        "range_model": "physical-combo-product-blocker-conditioned-v1",
        "reach_model": "global-joint-law-separated-sequence-reach-v1",
    }
    if identities != expected_identities:
        raise ValueError("raw solve envelope identities differ from the frozen game")
    source_identity = envelope.get("source_identity")
    if (type(source_identity) is not dict or
            source_identity.get("entry_point") != "pokerlab.preflop_solver.solve_preflop" or
            source_identity.get("solver_version") != "preflop-strategy-v1" or
            source_identity.get("source_revision") is not None or
            source_identity.get("source_verification") != "not-recorded"):
        raise ValueError("raw facade source metadata was not preserved")
    payload = envelope.get("payload")
    if type(payload) is not dict:
        raise ValueError("raw solve envelope payload is missing")
    required = {"solver_version": "preflop-strategy-v1",
                "strategy_schema": "preflop-strategy-v1",
                "runout_mode": "conditioned-ordered-selected-runouts",
                "algorithm": "cfrplus", "execution_backend": "public-batched-python",
                "iterations": ITERATIONS}
    for key, value in required.items():
        if payload.get(key) != value:
            raise ValueError(f"raw payload {key} differs from the fixed run")
    completed = payload.get("completed_iterations")
    if completed is not None and completed != ITERATIONS:
        raise ValueError("fixed-iteration training did not report all requested iterations")
    if payload.get("postflop_scope", "all-streets") != "all-streets":
        raise ValueError("raw payload does not describe the all-streets scope")
    if (payload.get("training_passes") != 3 * ITERATIONS or
            payload.get("training_passes_per_iteration") != 3 or
            payload.get("training_schedule") !=
            "alternating-player-0-then-player-1; linear-own-reach-average-after-each-sweep"):
        raise ValueError("raw training metadata differs from fixed 1000-sweep CFR+")
    if (payload.get("diagnostics_backend") != "public-batched-python" or
            "private_indexing" in payload or "future_indexing" in payload or
            "averaging_delay" in payload or "tree_admission" in payload or
            "world_admission" in payload or "convergence_checkpoints" in payload or
            payload.get("resource_model") != "public-vector"):
        raise ValueError("raw payload reports unsupported or nonliteral execution options")
    return payload


def _assert_payload_matches_admission(payload, production_receipt):
    counts = production_receipt["counts"]
    vector = production_receipt["vector_budget"]
    expected_payload_counts = {
        "candidate_private_pairs": counts["candidate_private_pairs"],
        "compatible_private_pairs": counts["compatible_private_pairs"],
        "worlds": counts["worlds"], "pair_runout_preflight_checks": counts["pair_runout_preflight_checks"],
        "public_states": counts["public_states"], "decisions": counts["decisions"],
        "info_sets": counts["information_sets"],
        "world_decision_work": counts["world_decision_work"],
        "public_batched_training_view_states": counts["positive_pot_training_view_states"],
        "public_batched_training_pot_anchor": counts["positive_pot_training_anchor"],
        "public_batched_prefix_edge_limit": production_receipt["caps"]["vector_prefix_edges"],
        "public_diagnostics_prefix_edge_limit": production_receipt["caps"]["vector_prefix_edges"],
        "public_diagnostics_view_states": counts["positive_pot_training_view_states"],
        "public_diagnostics_view_pot_anchor": counts["positive_pot_training_anchor"],
    }
    for key, expected in expected_payload_counts.items():
        if key not in payload or payload[key] != expected:
            raise ValueError(f"raw payload {key} differs from its production admission receipt")
    if payload.get("vector_work_budget") != vector:
        raise ValueError("raw public-vector budget differs from the pre-training admission receipt")
    if payload.get("public_diagnostics_view_source") != "training-view-reused":
        raise ValueError("raw diagnostics did not reuse the admitted positive-pot training view")
    limits = payload.get("limits")
    expected_limits = {"candidate_pair_iterations": production_receipt["caps"]["candidate_pair_iterations"],
                       "world_iterations": production_receipt["caps"]["world_iterations"],
                       "pair_runout_preflight_checks": production_receipt["caps"]["pair_runout_preflight_checks"],
                       "public_states": production_receipt["caps"]["public_states"],
                       "decision_nodes": production_receipt["caps"]["decision_nodes"]}
    if type(limits) is not dict or any(limits.get(key) != value
                                      for key, value in expected_limits.items()):
        raise ValueError("raw payload legacy limits differ from production admission")
    if (limits.get("world_decision_work") is not None or
            limits.get("reference_world_decision_work") !=
            production_receipt["caps"]["world_decision_work"] or
            payload.get("world_decision_work_enforced") is not False):
        raise ValueError("raw payload world-work guard semantics differ from public-vector admission")


def _compare_numeric_metrics(payload, numeric_metrics):
    """Reject material mismatch between returned scalars and independent replay."""
    fields = ("value_sb", "value_bb", "sb_best_response_value",
              "bb_best_response_value", "nash_conv", "exploitability")
    differences = {}
    failures = []
    for field in fields:
        replay_field = "nash_conv" if field == "exploitability" else field
        if field not in payload or replay_field not in numeric_metrics:
            failures.append(f"missing scalar {field}")
            continue
        left, right = payload[field], numeric_metrics[replay_field]
        if (isinstance(left, bool) or isinstance(right, bool) or
                not isinstance(left, (int, float)) or not isinstance(right, (int, float)) or
                not math.isfinite(float(left)) or not math.isfinite(float(right))):
            failures.append(f"malformed scalar {field}")
            continue
        if field == "exploitability":
            # The preserved numeric oracle returns NashConv; the zero-sum
            # exploitability convention is its half, not a new oracle field.
            right = right / 2
        differences[field] = abs(float(left) - float(right))
        if differences[field] > 1e-9:
            failures.append(f"production and independent numeric replay differ at {field}")
    return {"absolute_differences": differences, "absolute_tolerance": 1e-9,
            "all_within_tolerance": not failures, "failures": failures}


def _safe_output_directory(value):
    supplied = Path(value)
    if not supplied.is_absolute():
        raise ValueError("attempt directory must be an absolute path")
    if ".." in supplied.parts:
        raise ValueError("attempt directory cannot contain parent traversal")
    _assert_no_reparse_points(supplied)
    target = supplied.resolve(strict=False)
    _assert_no_reparse_points(target)
    repo = REPO_ROOT.resolve(strict=True)
    if target == repo or repo in target.parents or target in repo.parents:
        raise ValueError("attempt directory must be external to the source checkout")
    if target.exists():
        raise FileExistsError("attempt directory already exists; attempts cannot resume or retry")
    if not target.parent.is_dir():
        raise ValueError("attempt directory parent must already exist")
    return target


def _assert_no_reparse_points(path):
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        attributes = getattr(metadata, "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(metadata.st_mode) or attributes & reparse:
            raise ValueError("attempt path must not traverse a symlink or junction")


def _artifact_limit(name):
    if name == "raw-envelope.json":
        return RAW_LIMIT
    if name in {"attempt.json", "claim.json", "failure.json", "status.json"}:
        return SMALL_JSON_LIMIT
    return JSON_LIMIT


def _compare_admission_support(production, exact):
    """Cross-check independent physical pairs, world support, and rank signs."""
    pc = production["counts"]
    forecast = exact["forecast"]
    expected_counts = {"worlds": forecast["worlds"],
                       "information_sets": forecast["information_rows"],
                       "information_set_action_slots": forecast["action_slots"]}
    for key, expected in expected_counts.items():
        if pc[key] != expected:
            raise ValueError(f"production and independent admission {key} counts differ")
    prod_pairs = {(row["sb_hand"], row["bb_hand"]): float(row["probability"])
                  for row in production["physical_pair_probabilities"]}
    exact_pairs = {(row["sb_hand"], row["bb_hand"]): float(Fraction(row["fraction"]))
                   for row in exact["pair_probabilities"]}
    if set(prod_pairs) != set(exact_pairs) or any(
            abs(prod_pairs[key] - exact_pairs[key]) > 1e-12 for key in prod_pairs):
        raise ValueError("production and independent private-pair masses differ")
    prod_worlds = production["world_support"]
    exact_worlds = exact["world_support"]

    def identity(row):
        return tuple(row["hands"]), tuple(row["board"]), row["sign"]

    prod_index = {identity(row): row for row in prod_worlds}
    exact_index = {identity(row): row for row in exact_worlds}
    if len(prod_index) != len(prod_worlds) or set(prod_index) != set(exact_index):
        raise ValueError("production and independent physical world/sign support differs")
    for key, exact_row in exact_index.items():
        if abs(float(prod_index[key]["weight"]) - float(Fraction(exact_row["weight"]))) > 1e-12:
            raise ValueError("production and independent physical world weights differ")
    if production["world_sign_counts"] != exact["world_sign_counts"]:
        raise ValueError("production and independent showdown-sign totals differ")
    return {"worlds_compared": len(prod_worlds), "pairs_compared": len(prod_pairs),
            "independent_numeric_tree_nodes": forecast["tree_nodes"],
            "production_public_states": pc["public_states"],
            "collapsed_chance_structure_counted_separately": True,
            "sign_counts": exact["world_sign_counts"], "mass_tolerance": 1e-12,
            "support_matches": True}


def _check_artifact_room(directory, name, data):
    if name not in ARTIFACT_NAMES:
        raise ValueError("attempt contains an artifact outside the fixed inventory")
    if len(data) > _artifact_limit(name):
        raise ValueError(f"{name} exceeds its fixed artifact byte limit")
    entries = list(directory.iterdir())
    for path in entries:
        _assert_no_reparse_points(path)
        if not path.is_file():
            raise ValueError("attempt directory contains a non-file artifact")
    existing = entries
    unexpected = {path.name for path in existing} - ARTIFACT_NAMES
    if unexpected:
        raise ValueError(f"attempt directory contains unexpected artifact names: {sorted(unexpected)}")
    if name not in {path.name for path in existing} and len(existing) >= FILE_LIMIT:
        raise ValueError("attempt exceeds the 14-file artifact limit")
    if sum(path.stat().st_size for path in existing) + len(data) > TOTAL_LIMIT:
        raise ValueError("attempt exceeds the 256 MiB aggregate artifact limit")


def _write_json(directory, name, value, *, exclusive=True, small=False):
    data = _json_bytes(value, pretty=True)
    _check_artifact_room(directory, name, data)
    path = directory / name
    if exclusive:
        digest = _write_exclusive_preserving(path, data)
    else:
        digest = source_helper._write_atomic(path, data)
    return {"path": name, "bytes": len(data), "sha256": digest}


def _write_raw(directory, data):
    if type(data) is not bytes:
        raise TypeError("facade to_json() must encode as UTF-8 bytes")
    _check_artifact_room(directory, "raw-envelope.json", data)
    digest = _write_exclusive_preserving(directory / "raw-envelope.json", data)
    return {"path": "raw-envelope.json", "bytes": len(data), "sha256": digest,
            "serialization": "original FourStreetSolveResult.to_json UTF-8 bytes"}


def _write_exclusive_preserving(path, data):
    """Create once; retain a partial file if any write/flush/fsync step fails."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return _sha256(data)


def _verify_raw_receipt(directory, receipt):
    path = directory / "raw-envelope.json"
    data = path.read_bytes()
    if len(data) != receipt["bytes"] or _sha256(data) != receipt["sha256"]:
        raise ValueError("saved raw envelope bytes differ from the first raw receipt")
    return {"bytes": len(data), "sha256": _sha256(data), "verified": True}


def _fraction_strings(value):
    if isinstance(value, dict):
        return {key: _fraction_strings(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_fraction_strings(item) for item in value]
    try:
        from fractions import Fraction
        if isinstance(value, Fraction):
            return str(value)
    except Exception:
        pass
    return value


def _production_service(request):
    return _production_admission(request)


def _run_services():
    return {
        "capture": _capture_source_state,
        "fixture": _check_fixture,
        "exact_prepare": _independent_admission,
        "production_prepare": _production_service,
        "solve": solve_four_street,
        "numeric_replay": numeric.replay_policy,
        "exact_audit": certificate.evaluate_exact,
    }


def _runtime_provenance(started_at_unix_ns):
    return {"python_executable": sys.executable,
            "python_version": sys.version,
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "sys_flags": str(sys.flags),
            "started_at_unix_ns": started_at_unix_ns}


def _attempt_record(directory, record):
    return _write_json(directory, record["path"], record["value"],
                       exclusive=record.get("exclusive", True))


def run_attempt(expected_source_commit: str, attempt_directory: str | os.PathLike,
                *, _services=None):
    """Run one exclusive fixed attempt; underscored services exist for inert tests."""
    if type(expected_source_commit) is not str or not EXPECTED_SOURCE_RE.fullmatch(expected_source_commit):
        raise ValueError("expected source commit must be a 40-character lowercase Git SHA")
    directory = _safe_output_directory(attempt_directory)
    directory.mkdir(exist_ok=False)
    attempt_id = str(uuid.uuid4())
    request = _literal_request()
    case = _literal_case()
    services = _run_services() if _services is None else _services
    started_ns = time.time_ns()
    injected_services = _services is not None
    runtime = _runtime_provenance(started_ns)
    status = {"schema": "four-street-attempt-status-v1", "attempt_id": attempt_id,
              "lifecycle": "preparing", "quality_gate": None,
              "production_calls_entered": 0, "first_error": None}
    source_checks = []
    receipts = {}
    first_failure = None
    current_stage = "attempt-created"

    def write_status(lifecycle):
        status["lifecycle"] = lifecycle
        status["updated_at_unix_ns"] = time.time_ns()
        _write_json(directory, "status.json", status, exclusive=False)

    def capture(label, expected=None):
        observed = services["capture"](expected_source_commit)
        matches = None if expected is None else observed == expected
        source_checks.append({"stage": label, "state_sha256": _sha256(_json_bytes(observed)),
                              "matches_expected": matches})
        if matches is False:
            try:
                _write_json(directory, "source-after.json", {
                    "schema": "four-street-source-state-v1", "attempt_id": attempt_id,
                    "source_state": observed, "source_checks": source_checks}, exclusive=True)
            except Exception:
                pass
            _same_source_state(expected, observed)
        return observed

    def fail(stage, exc, *, preparation=False):
        nonlocal first_failure
        if first_failure is None:
            first_failure = {"stage": stage, "type": type(exc).__name__, "message": str(exc)}
        status["first_error"] = first_failure
        status["quality_gate"] = None
        status["production_calls_entered"] = status.get("production_calls_entered", 0)
        status["lifecycle"] = "preparation-failed" if preparation else "failed"
        try:
            _write_json(directory, "failure.json", {
                "schema": "four-street-attempt-failure-v1", "attempt_id": attempt_id,
                "failure": first_failure, "quality_gate": None,
                "production_calls_entered": status["production_calls_entered"],
                "receipts_so_far": receipts, "source_checks": source_checks},
                exclusive=True)
        except Exception:
            pass
        try:
            write_status(status["lifecycle"])
            _write_json(directory, "report.json", {
                "schema": "four-street-attempt-report-v1", "attempt_id": attempt_id,
                "benchmark_id": BENCHMARK_ID, "outcome": status["lifecycle"],
                "execution_mode": ("injected-test-services" if injected_services
                                   else "frozen-production"), "runtime": runtime,
                "quality_gate": None, "first_failure": first_failure,
                "production_calls_entered": status["production_calls_entered"],
                "receipts": receipts, "source_checks": source_checks}, exclusive=True)
        except Exception:
            pass
        return {"attempt_id": attempt_id, "directory": str(directory),
                "outcome": status["lifecycle"], "quality_gate": None,
                "production_calls_entered": status["production_calls_entered"],
                "first_failure": first_failure}

    try:
        _write_json(directory, "attempt.json", {
            "schema": "four-street-attempt-v1", "attempt_id": attempt_id,
            "benchmark_id": BENCHMARK_ID, "source_commit": expected_source_commit,
            "retry_permitted": False, "lifecycle": "preparing",
            "execution_mode": ("injected-test-services" if injected_services
                               else "frozen-production"),
            "runtime": runtime, "created_at_unix_ns": started_ns}, exclusive=True)
        write_status("preparing")

        current_stage = "source-before"
        source_before = capture(current_stage)
        receipts["source_before"] = _write_json(directory, "source-before.json", {
            "schema": "four-street-source-state-v1", "attempt_id": attempt_id,
            "source_state": source_before}, exclusive=True)

        current_stage = "fixture"
        manifest = services["fixture"]()
        if manifest["case"] != case or manifest["quality_run"] != _fixed_selectors():
            raise RuntimeError("fixed committed manifest/selectors differ from runner constants")
        case_sha256 = _sha256(_json_bytes(case))

        current_stage = "production-admission"
        production_receipt = services["production_prepare"](request)
        if production_receipt.get("admitted") is not True or production_receipt.get("attempted_training") is not False:
            raise ValueError("production preflight did not return a complete no-training admission")
        receipts["production_admission"] = _write_json(directory, "production-admission.json", {
            "schema": "four-street-production-admission-record-v1",
            "attempt_id": attempt_id, "receipt": production_receipt}, exclusive=True)
        capture("after-production-admission", source_before)

        current_stage = "exact-admission"
        exact_receipt = services["exact_prepare"](case)
        if exact_receipt.get("admitted") is not True or exact_receipt.get("attempted_training") is not False:
            raise ValueError("independent exact preflight did not admit the complete request")
        support_comparison = _compare_admission_support(production_receipt, exact_receipt)
        exact_receipt["production_support_comparison"] = support_comparison
        receipts["exact_admission"] = _write_json(directory, "exact-admission.json", {
            "schema": "four-street-exact-admission-record-v1",
            "attempt_id": attempt_id, "receipt": exact_receipt}, exclusive=True)
        capture("after-exact-admission", source_before)

        current_stage = "claim"
        source_claim = capture("before-claim", source_before)
        claim = {"schema": "four-street-training-claim-v1", "attempt_id": attempt_id,
                 "benchmark_id": BENCHMARK_ID, "source_commit": expected_source_commit,
                 "execution_mode": ("injected-test-services" if injected_services
                                    else "frozen-production"),
                 "runtime": runtime,
                 "source_state_sha256": _sha256(_json_bytes(source_claim)),
                 "case_sha256": case_sha256, "request": request.to_dict(),
                 "selectors": _fixed_selectors(),
                 "omitted_request_defaults": {"averaging_delay": 0,
                                              "tree_admission": "decision-count",
                                              "private_indexing": "original",
                                              "future_indexing": "original",
                                              "world_admission": "world-iterations"},
                 "production_admission": production_receipt,
                 "exact_admission": exact_receipt, "production_calls_allowed": 1,
                 "iterations_requested": ITERATIONS, "retry_permitted": False}
        receipts["claim"] = _write_json(directory, "claim.json", claim, exclusive=True)

        capture("immediately-before-solve", source_before)

        current_stage = "solve-entered"
        status["production_calls_entered"] = 1
        write_status("solve-entered")
        returned = services["solve"](request)

        current_stage = "raw-envelope"
        raw_json = returned.to_json()
        if type(raw_json) is not str:
            raise TypeError("facade to_json() must return a string")
        raw_bytes = raw_json.encode("utf-8")
        raw_receipt = _write_raw(directory, raw_bytes)
        receipts["raw_envelope"] = raw_receipt
        receipts["raw_receipt"] = _write_json(directory, "raw-receipt.json", {
            "schema": "four-street-raw-receipt-v1", "attempt_id": attempt_id,
            **raw_receipt}, exclusive=True)

        current_stage = "source-after-raw"
        final_source = capture(current_stage, source_before)
        receipts["raw_recheck"] = _verify_raw_receipt(directory, raw_receipt)

        current_stage = "raw-validate"
        envelope = _strict_json(raw_bytes, max_bytes=RAW_LIMIT)
        payload = _assert_envelope(envelope, request)
        _assert_payload_matches_admission(payload, production_receipt)
        raw_identity = {"raw_sha256": raw_receipt["sha256"],
                        "payload_canonical_sha256": _sha256(_json_bytes(payload)),
                        "source_identity": envelope["source_identity"]}

        current_stage = "numeric-replay"
        numeric_metrics = services["numeric_replay"](payload, case)
        numeric_comparison = _compare_numeric_metrics(payload, numeric_metrics)
        numeric_receipt = {"schema": "four-street-numeric-replay-v1",
                           "attempt_id": attempt_id, **raw_identity,
                           "metrics": numeric_metrics,
                           "numeric_counts": numeric_metrics.get("numeric_counts"),
                           "production_comparison": numeric_comparison}
        receipts["numeric_replay"] = _write_json(directory, "numeric-replay.json",
                                                  _fraction_strings(numeric_receipt), exclusive=True)
        if not numeric_comparison["all_within_tolerance"]:
            raise ValueError(f"numeric replay guard failed: {numeric_comparison['failures']!r}")
        capture("after-numeric-replay", source_before)

        current_stage = "exact-certificate"
        try:
            exact_result = services["exact_audit"](case, payload)
        except ValueError as exc:
            text = str(exc)
            capacity_errors = (
                "forecast exceeds its hard work limit",
                "Exact rational certificate exceeds its work limit",
                "65536-bit limit", "Exact rational certificate exceeds the depth limit",
                "Exact rational certificate exceeds the node limit",
            )
            if any(marker in text for marker in capacity_errors):
                final_source = capture("after-exact-capacity-failure", source_before)
                receipts["raw_recheck"] = _verify_raw_receipt(directory, raw_receipt)
                receipts["exact_certificate"] = None
                status["quality_gate"] = None
                status["lifecycle"] = "completed-unknown"
                status["first_error"] = {"stage": current_stage,
                                          "type": type(exc).__name__, "message": text}
                _write_json(directory, "source-after.json", {
                    "schema": "four-street-source-state-v1", "attempt_id": attempt_id,
                    "source_state": final_source, "source_checks": source_checks}, exclusive=True)
                _write_json(directory, "failure.json", {
                    "schema": "four-street-capacity-unknown-v1", "attempt_id": attempt_id,
                    "stage": current_stage, "error": str(exc), "quality_gate": None,
                    "raw_receipt": raw_receipt, "numeric_replay": receipts["numeric_replay"]},
                    exclusive=True)
                write_status("completed-unknown")
                report = {"schema": "four-street-attempt-report-v1", "attempt_id": attempt_id,
                          "benchmark_id": BENCHMARK_ID, "outcome": "completed-unknown",
                          "execution_mode": ("injected-test-services" if injected_services
                                             else "frozen-production"), "runtime": runtime,
                          "quality_gate": None, "first_failure": {"stage": current_stage,
                          "type": type(exc).__name__, "message": str(exc)},
                          "raw_receipt": raw_receipt, "numeric_replay": numeric_receipt,
                          "exact_certificate": None, "source_checks": source_checks,
                          "training": _training_metadata(payload)}
                _write_json(directory, "report.json", _fraction_strings(report), exclusive=True)
                return {"attempt_id": attempt_id, "directory": str(directory),
                        "outcome": "completed-unknown", "quality_gate": None,
                        "production_calls_entered": 1}
            raise
        receipts["exact_certificate"] = _write_json(directory, "exact-certificate.json", {
            "schema": "four-street-exact-certificate-record-v1", "attempt_id": attempt_id,
            **raw_identity, "certificate": _fraction_strings(exact_result)}, exclusive=True)
        current_stage = "source-after-audit"
        final_source = capture(current_stage, source_before)
        receipts["raw_recheck_after_audit"] = _verify_raw_receipt(directory, raw_receipt)
        _write_json(directory, "source-after.json", {
            "schema": "four-street-source-state-v1", "attempt_id": attempt_id,
            "source_state": final_source, "source_checks": source_checks}, exclusive=True)

        gate = exact_result.get("threshold_met")
        if type(gate) is not bool:
            raise ValueError("exact certificate threshold decision is malformed")
        outcome = "completed-met" if gate else "completed-missed"
        status["quality_gate"] = gate
        status["exact_nash_conv"] = exact_result.get("metrics", {}).get("nash_conv")
        write_status(outcome)
        report = {
            "schema": "four-street-attempt-report-v1", "attempt_id": attempt_id,
            "benchmark_id": BENCHMARK_ID, "outcome": outcome, "quality_gate": gate,
            "execution_mode": ("injected-test-services" if injected_services
                               else "frozen-production"), "runtime": runtime,
            "target_nash_conv_big_blinds": TARGET_NASH_CONV,
            "case_sha256": case_sha256, "source_commit": expected_source_commit,
            "raw_receipt": raw_receipt, "numeric_replay": numeric_receipt,
            "exact_certificate": _fraction_strings(_exact_report_summary(exact_result)),
            "admissions": {"production": production_receipt, "exact": exact_receipt},
            "training": _training_metadata(payload), "source_checks": source_checks,
            "production_calls_entered": 1, "first_failure": None,
        }
        _write_json(directory, "report.json", _fraction_strings(report), exclusive=True)
        return {"attempt_id": attempt_id, "directory": str(directory),
                "outcome": outcome, "quality_gate": gate,
                "production_calls_entered": 1,
                "raw_receipt": raw_receipt}
    except Exception as exc:
        return fail(current_stage, exc, preparation=status["production_calls_entered"] == 0)


def _training_metadata(payload):
    completed = payload.get("completed_iterations")
    if completed is not None and (type(completed) is not int or completed < 0):
        raise ValueError("payload completed_iterations metadata is malformed")
    returned_passes = payload.get("training_passes")
    passes_per_iteration = payload.get("training_passes_per_iteration")
    if returned_passes is not None and (type(returned_passes) is not int or returned_passes < 0):
        raise ValueError("payload training_passes metadata is malformed")
    if (passes_per_iteration is not None and
            (type(passes_per_iteration) is not int or passes_per_iteration < 0)):
        raise ValueError("payload training_passes_per_iteration metadata is malformed")
    return {"iterations_requested": ITERATIONS,
            "completed_iterations_returned": completed,
            "training_passes_returned": returned_passes,
            "training_passes_per_iteration_returned": passes_per_iteration,
            "training_schedule_returned": payload.get("training_schedule"),
            "modelled_expected_training_passes": 3 * ITERATIONS,
            "training_pass_count_status": ("returned-by-solver" if returned_passes is not None else
                                           "not-returned; 3000 is modelled from fixed request"),
            "fixed_iteration_source_inference": (
                "the pinned fixed-iteration path implies 1000 completed iterations"
                if completed is None else None)}


def _exact_report_summary(exact_result):
    """Keep report.json concise; exact-certificate.json retains the full ledger."""
    summary = {key: exact_result[key] for key in (
        "source_identity", "budget_schedule_version", "model_sha256",
        "input_case_canonical_sha256", "input_policy_canonical_sha256",
        "normalized_policy_sha256", "threshold_met", "metrics", "forecast",
        "actual_work", "actual_work_by_kind", "maximum_row_adjustment",
        "floating_comparison") if key in exact_result}
    summary["normalized_policy_row_count"] = len(exact_result.get("normalized_policy_rows", ()))
    summary["normalization_ledger_row_count"] = len(exact_result.get("normalization_ledger", ()))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--attempt-directory", required=True)
    args = parser.parse_args(argv)
    result = run_attempt(args.expected_source_commit, args.attempt_directory)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result.get("outcome") in {"completed-met", "completed-missed", "completed-unknown"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
