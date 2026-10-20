"""Fixed two-fixture direct river-tail evidence bundle.

Generation performs exactly two T=10,000/D=3,000 solver calls. Verification is
read-only and rebuilds each independent numeric/exact audit from saved policies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from fractions import Fraction


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks" / "results"
REPORT = RESULTS / "river-direct-tail-v1.json"
POLICIES = {
    "river-polarised-bluffcatcher": RESULTS / "river-direct-tail-v1-polarised.json",
    "river-weighted-raises": RESULTS / "river-direct-tail-v1-weighted-raises.json",
}
SCHEMA = "river-direct-tail-v1"
ITERATIONS = 10_000
DISCARD = 3_000
TARGET = Fraction(1, 1000)
REPORT_CAP = 8_000_000
POLICY_CAP = 2_000_000
OLD_TAIL_REPORT = RESULTS / "river-cfrplus-tail-realization-v1.json"
OLD_TAIL_REPORT_SHA256 = "44c17cced492a5bcf7a9f2622bde060bb98a47f60539ee2ca997ebd1e421b1ce"
OLD_POLICIES = {
    "river-polarised-bluffcatcher": (
        RESULTS / "river-cfrplus-tail-policies-v1" / "river-polarised-bluffcatcher-materialized-tail.json",
        "67761d6b0c37b0edce22984583c14aaeabd36507ab426939e58753be050a1344",
    ),
    "river-weighted-raises": (
        RESULTS / "river-cfrplus-tail-policies-v1" / "river-weighted-raises-materialized-tail.json",
        "cfff9bba2fd253e0701d37eb5c845399c6643f344cf11565a7a2e5b598514b62",
    ),
}
FIXTURES = {
    "river-polarised-bluffcatcher": {
        "board": "2c7d9hJsKd",
        "config": {"pot": 100, "effective_stack": 100, "bet_sizes": [1.0],
                    "include_all_in": False},
        "id": "river-polarised-bluffcatcher", "ip": "QsQh",
        "oop": "AsAh,3c4c",
        "purpose": "Nuts/air versus bluffcatcher, pot-size bet, finite tree",
    },
    "river-weighted-raises": {
        "board": "Js8d4c2h2s",
        "config": {"pot": 100, "effective_stack": [220, 120],
                    "bet_sizes": [0.33, 0.75], "raise_sizes": [0.5, 1.0],
                    "max_raises": 2, "include_all_in": True},
        "id": "river-weighted-raises", "ip": "AcAd:1,KcKd:0.75",
        "oop": "AsAh:0.5,KsKh:1",
        "purpose": "Weighted river range, two opening sizes, raises and unequal stacks",
    },
}
RESOURCE_KEYS = {
    "full_requested_world_node_work", "full_requested_world_node_work_limit",
    "full_requested_dense_hand_state_pass_work",
    "full_requested_dense_hand_state_pass_work_limit", "info_action_slots",
    "info_action_slots_limit", "prefix_hand_edges", "prefix_hand_edge_limit",
}
PRODUCER_EXTRA = (
    "pokerlab/river_tail_adapter.py",
    "tests/test_river_tail_adapter.py",
    "scripts/benchmark_river_direct_tail.py",
    "tests/test_benchmark_river_direct_tail.py",
)
VERIFY_PATHS = (
    "pokerlab/cards.py",
    "scripts/preflop_validation.py",
    "scripts/turn_river_validation.py",
    "scripts/turn_rational_certificate.py",
    "scripts/river_tail_realization.py",
    "scripts/river_analytical.py",
    "scripts/replay_river_accuracy_extension.py",
    "scripts/benchmark_river_direct_tail.py",
    "tests/test_benchmark_river_direct_tail.py",
)
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def _pretty(value):
    return _canonical(value)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read_bounded(path, limit):
    size = path.stat().st_size
    if size < 0 or size > limit:
        raise ValueError(f"File exceeds byte cap: {path}")
    raw = path.read_bytes()
    if len(raw) != size or len(raw) > limit:
        raise ValueError(f"File changed while reading or exceeded byte cap: {path}")
    return raw


def _py_source_bytes(path):
    return path.read_bytes().replace(b"\r\n", b"\n")


def _verification_hashes(root=ROOT):
    return {name: _sha(_py_source_bytes(root / name)) for name in VERIFY_PATHS}


def _producer_paths(root=ROOT):
    paths = sorted((root / "pokerlab").glob("*.py"))
    names = {p.relative_to(root).as_posix() for p in paths}
    names.update(PRODUCER_EXTRA)
    return tuple(sorted(names))


def _producer_hashes(root=ROOT):
    return {name: _sha(_py_source_bytes(root / name)) for name in _producer_paths(root)}


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True).stdout.strip()


def _head(root=ROOT):
    head = _git(root, "rev-parse", "HEAD")
    if not GIT_RE.fullmatch(head):
        raise ValueError("Expected a full historical Git commit id")
    return head


def _require_committed_producer(root=ROOT):
    head = _head(root)
    hashes = _producer_hashes(root)
    _require_committed(root, hashes, head=head)
    return head, hashes


def _require_committed(root, hashes, *, head=None):
    head = _head(root) if head is None else head
    for name, digest in hashes.items():
        committed = subprocess.run(["git", "show", f"{head}:{name}"], cwd=root,
                                   check=True, capture_output=True).stdout
        if _sha(committed.replace(b"\r\n", b"\n")) != digest:
            raise ValueError(f"Committed source differs from working bytes: {name}")


def _bundle_identity(path):
    stat = path.stat()
    return (stat.st_dev, stat.st_ino)


def _fixed_targets(root=ROOT):
    results = root / "benchmarks" / "results"
    return {
        "report": results / "river-direct-tail-v1.json",
        "river-polarised-bluffcatcher": results / "river-direct-tail-v1-polarised.json",
        "river-weighted-raises": results / "river-direct-tail-v1-weighted-raises.json",
    }


def _load_inputs(root=ROOT):
    """Load and hash-check only the two accepted old-tail policies and report."""
    report_path = root / OLD_TAIL_REPORT.relative_to(ROOT)
    report_raw = _read_bounded(report_path, REPORT_CAP)
    if _sha(report_raw) != OLD_TAIL_REPORT_SHA256:
        raise ValueError("Pinned prior tail report bytes changed")
    old_report = json.loads(report_raw)
    if type(old_report) is not dict or old_report.get("benchmark_id") != "river-cfrplus-tail-realization-v1":
        raise ValueError("Unexpected prior tail report identity")
    fixtures = {row.get("id"): row for row in old_report.get("fixtures", [])}
    if fixtures != FIXTURES:
        raise ValueError("Prior report fixed fixture metadata differs")
    result_rows = old_report.get("results")
    if type(result_rows) is not list:
        raise ValueError("Prior tail report has no result list")
    loaded = {}
    for fixture_id, (fixed_path, expected_sha) in OLD_POLICIES.items():
        path = root / fixed_path.relative_to(ROOT)
        raw = _read_bounded(path, POLICY_CAP)
        if _sha(raw) != expected_sha:
            raise ValueError(f"Pinned prior tail policy changed: {fixture_id}")
        payload = json.loads(raw)
        matches = [row for row in result_rows if row.get("scenario") == fixture_id
                   and row.get("backend") == "materialized"
                   and row.get("profile_kind") == "tail"]
        if len(matches) != 1:
            raise ValueError(f"Prior report does not identify exactly one materialized tail: {fixture_id}")
        row = matches[0]
        if (row.get("policy_file") != path.name or row.get("policy_sha256") != expected_sha
                or row.get("iterations") != 10_000 or row.get("source_requested_iterations") != 10_000
                or row.get("source_iteration_window") != [3001, 10_000]
                or row.get("target_met") is not (row.get("metrics", {}).get("nash_conv", math.inf) <= 0.001)):
            raise ValueError(f"Prior tail policy provenance mismatch: {fixture_id}")
        if payload.get("board") != list(_cards(fixture_id)) or payload.get("config") != _config_dict(fixture_id):
            raise ValueError(f"Prior tail policy game metadata mismatch: {fixture_id}")
        loaded[fixture_id] = {"raw": raw, "payload": payload, "path": path,
                              "sha256": expected_sha, "report_row": row}
    return {"report_raw": report_raw, "report_sha256": OLD_TAIL_REPORT_SHA256,
            "report_path": report_path, "report": old_report, "policies": loaded}


def _cards(fixture_id):
    from pokerlab.cards import cards
    return cards(FIXTURES[fixture_id]["board"])


def _config_dict(fixture_id):
    from scripts import turn_river_validation as validator
    return validator._config(FIXTURES[fixture_id]["config"], "config").to_dict()


def _guard_inputs(root, inputs):
    current = _load_inputs(root)
    if current["report_raw"] != inputs["report_raw"]:
        raise RuntimeError("Pinned prior report changed during operation")
    for fixture_id in FIXTURES:
        if current["policies"][fixture_id]["raw"] != inputs["policies"][fixture_id]["raw"]:
            raise RuntimeError(f"Pinned prior policy changed during operation: {fixture_id}")


def _guard_math(root, expected):
    if _verification_hashes(root) != expected:
        raise RuntimeError("Independent verification source bytes changed during operation")


def _guard_generation(root, head, producer, verification, inputs):
    if _head(root) != head:
        raise RuntimeError("Git HEAD changed during generation")
    if _producer_hashes(root) != producer:
        raise RuntimeError("Producer source changed during generation")
    _guard_math(root, verification)
    _guard_inputs(root, inputs)


def _guard_replay(root, head, verification, inputs, bundle_guard=None):
    if _head(root) != head:
        raise RuntimeError("Current Git HEAD changed during replay")
    _guard_math(root, verification)
    _guard_inputs(root, inputs)
    if bundle_guard is not None:
        bundle_guard()


def _checkpoint(guard):
    if guard is not None:
        guard()


def _expected_preflight(fixture_id):
    return {
        "river-polarised-bluffcatcher": {
            "worlds": 2, "compatible_pairs": 2, "public_states": 9,
            "public_nodes": 4, "chance_nodes": 0, "world_traversal_nodes": 4,
            "terminal_nodes": 5,
            "info_sets": 6, "tree_actions": 8, "info_action_slots": 12,
            "prefix_hand_edges": 2, "full_requested_world_node_work": 240_000,
            "full_requested_dense_hand_state_pass_work": 540_054,
        },
        "river-weighted-raises": {
            "worlds": 4, "compatible_pairs": 4, "public_states": 51,
            "public_nodes": 18, "chance_nodes": 0, "world_traversal_nodes": 18,
            "terminal_nodes": 33,
            "info_sets": 36, "tree_actions": 50, "info_action_slots": 100,
            "prefix_hand_edges": 4, "full_requested_world_node_work": 2_160_000,
            "full_requested_dense_hand_state_pass_work": 3_060_306,
        },
    }[fixture_id]


def _validate_profile_metadata(payload, fixture_id, *, iterations=ITERATIONS, discard=DISCARD):
    if type(payload) is not dict:
        raise ValueError("Policy must be an object")
    expected = _expected_preflight(fixture_id)
    config = _config_dict(fixture_id)
    expected_fields = {
        "method": "Direct original-weight CFR+ river tail averaging",
        "algorithm": "cfrplus", "solver_version": "research-river-tail-adapter-v1",
        "strategy_schema": "postflop-strategy-v1", "backend": "exact-public-chance-tree",
        "execution_backend": "direct-original-weight-river-tail-python",
        "diagnostics_backend": "public-batched-python", "board": list(_cards(fixture_id)),
        "config": config, "street_configs": {"river": config}, "turn_config": None,
        "pot": config["pot"], "effective_stack": config["effective_stack"],
        "river_config": config, "runouts": [], "reachable_runouts": [], "runout_mode": "none",
        "iterations": iterations, "requested_iterations": iterations, "discard": discard,
        "source_iteration_window": [discard + 1, iterations],
        "averaged_sweeps": iterations - discard,
        "average_weight_sum": (iterations * (iterations + 1) - discard * (discard + 1)) // 2,
        "average_schedule": "direct-original-linear-sweep-weight-own-reach-tail",
        "update_schedule": "alternating-oop-then-ip",
        "requested_regret_passes": 2 * iterations,
        "requested_average_passes": iterations - discard,
        "requested_total_traversal_passes": 3 * iterations - discard,
        "deals": expected["compatible_pairs"], "worlds_materialized": expected["worlds"],
        "public_state_limit": 250_000, "public_node_limit": 10_000,
        "public_batch_edge_limit": 250_000,
        "training_calls": 1,
    }
    for key, value in expected.items():
        if key not in RESOURCE_KEYS:
            expected_fields[key] = value
    for key, value in expected_fields.items():
        if (type(payload.get(key)) is not type(value) or
                _canonical(payload.get(key)) != _canonical(value)):
            raise ValueError(f"Policy metadata mismatch for {fixture_id}.{key}")
    if payload.get("chance_note") != "Compatible private-pair range products normalized once; board is complete.":
        raise ValueError("River physical-world conditioning note is missing")
    if payload.get("scope") != "Research profile for a configured heads-up river game; no preflop, multiway play, rake, or general exact-equilibrium claim.":
        raise ValueError("Unexpected direct-tail scope")
    if payload.get("diagnostic_provenance") != "Metrics recomputed from this direct original-weight river-tail policy using public-batched diagnostics; numeric convergence diagnostics are not an exact equilibrium certificate.":
        raise ValueError("Unexpected direct-tail diagnostic provenance")

    resources = payload.get("resource_usage")
    if type(resources) is not dict or set(resources) != RESOURCE_KEYS:
        raise ValueError("Resource metadata key set differs")
    expected_resources = {
        "full_requested_world_node_work": expected["worlds"] * expected["world_traversal_nodes"] * iterations * 3,
        "full_requested_world_node_work_limit": 30_000_000,
        "full_requested_dense_hand_state_pass_work": 2 * expected["public_states"] * (3 * iterations + 3),
        "full_requested_dense_hand_state_pass_work_limit": 30_000_000,
        "info_action_slots": expected["info_action_slots"],
        "info_action_slots_limit": 1_000_000,
        "prefix_hand_edges": expected["prefix_hand_edges"],
        "prefix_hand_edge_limit": 250_000,
    }
    for key, value in expected_resources.items():
        if type(resources.get(key)) is not int or resources[key] != value:
            raise ValueError(f"Resource metadata mismatch for {fixture_id}.{key}")
    if type(payload.get("strategy")) is not list or len(payload["strategy"]) != expected["info_sets"]:
        raise ValueError("Strategy rows do not match complete information-set census")
    metrics = ("value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value",
               "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability")
    for key in metrics:
        number = payload.get(key)
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
            raise ValueError(f"Nonfinite or nonnumeric profile metric {key}")


def _fraction(value):
    if isinstance(value, Fraction):
        return value
    raise TypeError("Exact certificate metric must be a Fraction")


def _jsonable(value):
    if isinstance(value, Fraction):
        return str(value)
    if type(value) is dict:
        return {str(key): _jsonable(item) for key, item in value.items()}
    if type(value) in (list, tuple):
        return [_jsonable(item) for item in value]
    return value


def _independent_model(payload, fixture_id):
    from pokerlab.cards import expand_range
    from scripts import turn_river_validation as validator

    fixture = FIXTURES[fixture_id]
    board = validator.cards(fixture["board"])
    config = validator._config(fixture["config"], "config")
    ranges = (expand_range(fixture["oop"], board), expand_range(fixture["ip"], board))
    worlds, selected = validator._worlds(board, ranges, None)
    if selected:
        raise ValueError("Fixed river game unexpectedly has future runouts")
    root = validator._public_tree(board, config, config, selected, worlds)
    pending = [root]
    chance_nodes = 0
    while pending:
        node = pending.pop()
        if isinstance(node, validator._Chance):
            chance_nodes += 1
            pending.extend(node.branches.values())
        elif isinstance(node, validator._Decision):
            pending.extend(node.children)
    if chance_nodes:
        raise ValueError("Complete river game unexpectedly has public chance nodes")
    nodes = validator._collect_nodes(root)
    policies = validator._validate_policy(payload, root, nodes, worlds, board, selected,
                                          runouts_were_omitted=True)
    return board, config, worlds, root, nodes, policies


def _assert_exact_identities(metrics):
    value = metrics["value_oop"]
    if metrics["value_ip"] != -value:
        raise ValueError("Exact profile values are not zero-sum")
    lower, upper = -metrics["ip_best_response_value"], metrics["oop_best_response_value"]
    if not lower <= value <= upper:
        raise ValueError("Exact legal-response interval does not contain profile value")
    if metrics["nash_conv"] != upper - lower:
        raise ValueError("Exact NashConv differs from response interval width")
    if metrics["nash_conv"] != metrics["oop_best_response_gain"] + metrics["ip_best_response_gain"]:
        raise ValueError("Exact NashConv differs from unilateral gains")
    if metrics["nash_conv"] != 2 * metrics["exploitability"]:
        raise ValueError("Exact NashConv differs from twice exploitability")
    if metrics["oop_best_response_gain"] != upper - value or metrics["ip_best_response_gain"] != value - lower:
        raise ValueError("Exact unilateral gains do not match response interval")
    if min(metrics["oop_best_response_gain"], metrics["ip_best_response_gain"]) < 0:
        raise ValueError("Exact best-response gain is negative")
    return lower, upper


def _old_flow_map(rows):
    from scripts import river_tail_realization as realization
    keyed, order, probabilities, _adjustment = realization._snapshot(rows, "tail policy")
    reaches = realization._own_reaches(keyed, order, probabilities)
    return keyed, order, probabilities, {
        (key, index): reaches[key] * probability
        for key in order for index, probability in enumerate(probabilities[key])
    }


def _metadata_rows(rows):
    return [{**row, "actions": [{k: v for k, v in action.items() if k != "probability"}
                                 for action in row["actions"]]}
            for row in rows]


def _audit_new_policy(payload, fixture_id, *, iterations=ITERATIONS,
                      discard=DISCARD, guard=None):
    from scripts import turn_river_validation as validator
    from scripts.turn_rational_certificate import (
        MAX_EXACT_DEPTH, MAX_EXACT_WORK, MAX_FRACTION_BITS, evaluate_exact,
    )

    _checkpoint(guard)
    _validate_profile_metadata(payload, fixture_id, iterations=iterations, discard=discard)
    fixture = FIXTURES[fixture_id]
    float_replay = validator.replay_policy(payload, fixture["oop"], fixture["ip"],
                                           board=fixture["board"], config=fixture["config"])
    float_deltas = validator.compare_result(payload, float_replay, tolerance=1e-9)
    if any(not math.isfinite(delta) or abs(delta) > 1e-9 for delta in float_deltas.values()):
        raise ValueError("Saved profile differs from independent numeric replay")
    _checkpoint(guard)
    model = _independent_model(payload, fixture_id)
    _board, config, worlds, game_root, _nodes, policies = model
    _checkpoint(guard)
    exact = evaluate_exact(game_root, worlds, policies, config.pot, result=payload,
                           max_work=100_000, max_depth=64, max_bits=65_536)
    _checkpoint(guard)
    if (exact["work_limit"], exact["depth_limit"], exact["fraction_bit_limit"]) != (
            MAX_EXACT_WORK, MAX_EXACT_DEPTH, MAX_FRACTION_BITS):
        raise RuntimeError("Exact auditor limits changed")
    metrics = exact["metrics"]
    lower, upper = _assert_exact_identities(metrics)
    exact_float_deltas = {
        key: float(metrics[key]) - float(float_replay[key]) for key in metrics
    }
    if any(abs(delta) > 1e-9 for delta in exact_float_deltas.values()):
        raise ValueError("Exact and numeric independent replay metrics diverge")
    known = Fraction(25) if fixture_id == "river-polarised-bluffcatcher" else Fraction(-43_339, 2_163)
    if not lower <= known <= upper:
        raise ValueError("Known game reference value is outside exact legal-response interval")

    polarized_witness = None
    if fixture_id == "river-polarised-bluffcatcher":
        from scripts.replay_river_accuracy_extension import rational_polarised
        polarized_witness = rational_polarised(payload, fixture)
        witness_value = Fraction(polarized_witness["value_oop_fraction"])
        witness_oop = Fraction(polarized_witness["oop_br_fraction"])
        witness_ip = Fraction(polarized_witness["ip_br_fraction"])
        witness_metrics = {
            "value_oop": witness_value, "value_ip": -witness_value,
            "oop_best_response_value": witness_oop, "ip_best_response_value": witness_ip,
            "oop_best_response_gain": witness_oop - witness_value,
            "ip_best_response_gain": witness_value + witness_ip,
            "nash_conv": witness_oop + witness_ip,
            "exploitability": (witness_oop + witness_ip) / 2,
        }
        if witness_metrics != metrics:
            raise ValueError("Independent 16/4 exact-history result differs from generic certificate")
    _checkpoint(guard)
    return {
        "fixture": fixture_id,
        "numeric_replay_deltas": float_deltas,
        "exact_float_replay_deltas": exact_float_deltas,
        "exact_metrics_fractions": {key: str(value) for key, value in metrics.items()},
        "exact_threshold": str(TARGET),
        "exact_threshold_met": metrics["nash_conv"] <= TARGET,
        "exact_nash_conv_zero": metrics["nash_conv"] == 0,
        "known_game_reference_fraction": str(known),
        "known_game_reference_in_response_interval": True,
        "lower_value_bound_fraction": str(lower),
        "upper_value_bound_fraction": str(upper),
        "exact_certificate": _jsonable({
            "work": exact["work"], "work_by_kind": exact["work_by_kind"],
            "tree_nodes": exact["tree_nodes"], "tree_depth": exact["tree_depth"],
            "worlds": exact["worlds"], "maximum_fraction_bits": exact["maximum_fraction_bits"],
            "work_limit": exact["work_limit"], "depth_limit": exact["depth_limit"],
            "fraction_bit_limit": exact["fraction_bit_limit"],
            "max_row_adjustment": exact["max_row_adjustment"],
            "normalization_ledger": exact["normalization_ledger"],
        }),
        "polarized_16x4_witness": polarized_witness,
    }


def _compare_prior_tail(payload, fixture_id, inputs, *, guard=None):
    from scripts import turn_river_validation as validator

    _checkpoint(guard)
    fixture = FIXTURES[fixture_id]
    old = inputs["policies"][fixture_id]["payload"]
    replay = validator.replay_policy(old, fixture["oop"], fixture["ip"],
                                     board=fixture["board"], config=fixture["config"])
    differences = validator.compare_result(old, replay, tolerance=1e-9)
    if any(not math.isfinite(delta) or abs(delta) > 1e-9 for delta in differences.values()):
        raise ValueError("Prior tail diagnostics differ from independent replay")
    _checkpoint(guard)
    if _metadata_rows(old["strategy"]) != _metadata_rows(payload["strategy"]):
        raise ValueError("Direct and prior tail legal row/action metadata differ")
    _old_keyed, old_order, _old_prob, old_flows = _old_flow_map(old["strategy"])
    _new_keyed, new_order, _new_prob, new_flows = _old_flow_map(payload["strategy"])
    if old_order != new_order or set(old_flows) != set(new_flows):
        raise ValueError("Direct and prior tail realization flow identities differ")
    max_flow_error = max((abs(old_flows[key] - new_flows[key]) for key in old_flows), default=Fraction(0))
    if max_flow_error > Fraction(1, 10**11):
        raise ValueError("Direct tail own-action flow differs from pinned realization tail")
    _checkpoint(guard)
    return {
        "prior_tail_policy_sha256": inputs["policies"][fixture_id]["sha256"],
        "prior_tail_report_sha256": inputs["report_sha256"],
        "prior_tail_nash_conv": inputs["policies"][fixture_id]["report_row"]["metrics"]["nash_conv"],
        "own_action_flow_max_error_fraction": str(max_flow_error),
        "own_action_flow_max_error": float(max_flow_error),
        "old_tail_flow_scope": "Exact row-normalized binary64 probabilities and own-action reach only; opponent and chance reach excluded.",
    }


def _audit_policy(payload, fixture_id, inputs, *, guard=None):
    # Public generation and replay always enforce the complete fixed experiment.
    return {**_audit_new_policy(payload, fixture_id, guard=guard),
            **_compare_prior_tail(payload, fixture_id, inputs, guard=guard)}


def _expected_map_shape(mapping, *, exact_keys=None):
    if type(mapping) is not dict:
        raise ValueError("Source map must be an object")
    if exact_keys is not None and set(mapping) != set(exact_keys):
        raise ValueError("Source map path set differs")
    if exact_keys is None and not set(PRODUCER_EXTRA) <= set(mapping):
        raise ValueError("Historical producer context lacks required sources")
    for path, digest in mapping.items():
        if type(path) is not str or type(digest) is not str or not SHA_RE.fullmatch(digest):
            raise ValueError("Source map has an invalid path or digest")
        if (exact_keys is None and path not in PRODUCER_EXTRA and
                re.fullmatch(r"pokerlab/[A-Za-z_][A-Za-z_0-9]*\.py", path) is None):
            raise ValueError("Unexpected historical producer path")


def _verify_bundle(report_raw, policy_raws, *, root=ROOT, expected_math=None,
                   expected_inputs=None, current_head=None, bundle_guard=None):
    if type(report_raw) is not bytes or len(report_raw) > REPORT_CAP:
        raise ValueError("Report exceeds cap or is not bytes")
    report = json.loads(report_raw)
    if _pretty(report) != report_raw:
        raise ValueError("Report is not canonical LF JSON")
    if (type(report) is not dict or type(report.get("schema_version")) is not int or
            report.get("schema_version") != 1 or report.get("benchmark_id") != SCHEMA):
        raise ValueError("Unsupported direct-tail report")
    if type(report.get("historical_producer_head")) is not str or not GIT_RE.fullmatch(report["historical_producer_head"]):
        raise ValueError("Invalid historical producer commit context")
    _expected_map_shape(report.get("historical_producer_source_sha256"))
    _expected_map_shape(report.get("verification_source_sha256"), exact_keys=VERIFY_PATHS)
    if expected_math is None:
        expected_math = _verification_hashes(root)
    if report["verification_source_sha256"] != expected_math:
        raise ValueError("Current independent verification sources differ from saved report pins")
    if expected_inputs is None:
        expected_inputs = _load_inputs(root)
    if current_head is None:
        current_head = _head(root)

    def guard():
        _guard_replay(root, current_head, expected_math, expected_inputs, bundle_guard)

    guard()
    if report.get("prior_tail_report_sha256") != expected_inputs["report_sha256"]:
        raise ValueError("Saved report prior-tail report pin differs")
    expected_payload_hashes = report.get("policy_sha256")
    if type(expected_payload_hashes) is not dict or set(expected_payload_hashes) != set(FIXTURES):
        raise ValueError("Saved policy hash map is incomplete")
    if set(policy_raws) != set(FIXTURES):
        raise ValueError("Policy bundle is incomplete")
    recorded_rows = report.get("results")
    if type(recorded_rows) is not dict or set(recorded_rows) != set(FIXTURES):
        raise ValueError("Saved result rows do not cover both fixtures")
    outputs = {}
    for fixture_id in FIXTURES:
        raw = policy_raws[fixture_id]
        if type(raw) is not bytes or len(raw) > POLICY_CAP:
            raise ValueError(f"Policy exceeds cap: {fixture_id}")
        if _sha(raw) != expected_payload_hashes[fixture_id]:
            raise ValueError(f"Saved policy hash mismatch: {fixture_id}")
        payload = json.loads(raw)
        if _canonical(payload) != raw:
            raise ValueError(f"Policy bytes are not canonical JSON: {fixture_id}")
        guard()
        if type(recorded_rows[fixture_id]) is not dict:
            raise ValueError("Saved result row is not an object")
        elapsed = recorded_rows[fixture_id].get("actual_complete_call_seconds")
        row = _audit_policy(payload, fixture_id, expected_inputs, guard=guard)
        row.update(_metadata_only_report_row(payload, elapsed))
        outputs[fixture_id] = row
        guard()
    rebuilt = _build_report(report["historical_producer_head"],
                            report["historical_producer_source_sha256"],
                            expected_math, expected_inputs, outputs, policy_raws)
    if _canonical(rebuilt) != report_raw:
        raise ValueError("Saved report differs from complete no-training reconstruction")
    guard()
    return report


def _metadata_only_report_row(result, elapsed):
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("Complete-call time must be finite and nonnegative")
    return {
        "actual_complete_call_seconds": elapsed,
        "requested_iterations": ITERATIONS, "discard": DISCARD,
        "averaged_sweeps": 7_000, "average_weight_sum": 45_503_500,
        "requested_regret_passes": 20_000, "requested_average_passes": 7_000,
        "requested_total_traversal_passes": 27_000,
        "training_calls": 1,
        "worlds": result["worlds"], "compatible_pairs": result["compatible_pairs"],
        "public_states": result["public_states"], "public_nodes": result["public_nodes"],
        "visited_nodes": result["world_traversal_nodes"],
        "info_sets": result["info_sets"], "tree_actions": result["tree_actions"],
        "info_action_slots": result["resource_usage"]["info_action_slots"],
        "prefix_hand_edges": result["resource_usage"]["prefix_hand_edges"],
        "world_node_work": result["resource_usage"]["full_requested_world_node_work"],
        "dense_hand_state_pass_work": result["resource_usage"]["full_requested_dense_hand_state_pass_work"],
    }


def _source_context(root=ROOT):
    head, producer = _require_committed_producer(root)
    verification = _verification_hashes(root)
    _require_committed(root, verification, head=head)
    return head, producer, verification


def _build_report(head, producer, verification, inputs, results, policy_raws):
    return {
        "schema_version": 1, "benchmark_id": SCHEMA,
        "historical_producer_head": head,
        "historical_producer_source_sha256": producer,
        "verification_source_sha256": verification,
        "iterations": ITERATIONS, "discard": DISCARD,
        "target_nash_conv_fraction": str(TARGET),
        "prior_tail_report_sha256": inputs["report_sha256"],
        "prior_tail_policy_sha256": {key: inputs["policies"][key]["sha256"] for key in FIXTURES},
        "fixtures": FIXTURES,
        "completed_training_calls": 2,
        "target_meet_count": sum(row["exact_threshold_met"] for row in results.values()),
        "target_miss_count": sum(not row["exact_threshold_met"] for row in results.values()),
        "results": results,
        "policy_sha256": {key: _sha(raw) for key, raw in policy_raws.items()},
        "scope": "Two fixed configured river games; exact audits apply to each serialized binary64 policy after exact row normalization and do not certify general solver convergence.",
    }


def _guard_targets_absent(targets):
    existing = [str(path) for path in targets.values() if path.exists()]
    if existing:
        raise FileExistsError("Refusing to overwrite accepted target(s): " + ", ".join(existing))


def _owned_write(path, raw, owned):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stat = os.fstat(stream.fileno())
        owned[path] = (stat.st_dev, stat.st_ino)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _rollback_owned(owned):
    for path, identity in reversed(list(owned.items())):
        try:
            if path.exists() and _bundle_identity(path) == identity:
                path.unlink()
        except OSError as error:
            print(f"Owned-file cleanup failed for {path}: {error}", file=sys.stderr)


def _publish_staged(staged, targets, owned):
    for key, target in targets.items():
        stage = staged[key]
        stage_identity = owned[stage]
        os.link(stage, target)
        owned[target] = stage_identity
        if _bundle_identity(target) != stage_identity:
            raise RuntimeError("Published target identity differs from registered staged inode")


def _preserve_rejected(root, fixture_id, payload, head, producer, elapsed, reason,
                       *, verification=None):
    folder = root / "work" / "river_direct_experiment_rejected"
    folder.mkdir(parents=True, exist_ok=True)
    record = {"fixture": fixture_id, "generation_head": head,
              "producer_source_sha256": producer, "elapsed_seconds": elapsed,
              "verification_source_sha256": verification,
              "prior_tail_report_sha256": OLD_TAIL_REPORT_SHA256,
              "rejection": str(reason), "raw_policy": payload}
    try:
        raw = _canonical(record)
    except (TypeError, ValueError):
        raw = (json.dumps(record, indent=2, sort_keys=True, allow_nan=True,
                          default=repr) + "\n").encode("utf-8")
    target = folder / f"{fixture_id}-{uuid.uuid4().hex}.json"
    with target.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return target


def _read_bundle(paths):
    report_raw = _read_bounded(paths["report"], REPORT_CAP)
    policy_raws = {key: _read_bounded(paths[key], POLICY_CAP) for key in FIXTURES}
    return report_raw, policy_raws


def _publish_bundle(report_raw, policy_raws, *, root, head, producer, verification, inputs):
    targets = _fixed_targets(root)
    _guard_targets_absent(targets)
    stages, owned = {}, {}
    try:
        for key in (*FIXTURES, "report"):
            target = targets[key]
            stage = target.with_name(f".{target.name}.{uuid.uuid4().hex}.stage")
            stages[key] = stage
            raw = report_raw if key == "report" else policy_raws[key]
            _owned_write(stage, raw, owned)

        def staged_guard():
            _guard_generation(root, head, producer, verification, inputs)
            _final_bundle_guard(stages, owned, report_raw, policy_raws)

        staged_guard()
        actual_report, actual_policies = _read_bundle(stages)
        _verify_bundle(actual_report, actual_policies, root=root,
                       expected_math=verification, expected_inputs=inputs,
                       current_head=head, bundle_guard=staged_guard)
        staged_guard()
        _guard_targets_absent(targets)
        _publish_staged(stages, targets, owned)

        def published_guard():
            _guard_generation(root, head, producer, verification, inputs)
            _final_bundle_guard(targets, owned, report_raw, policy_raws)

        published_guard()
        actual_report, actual_policies = _read_bundle(targets)
        _verify_bundle(actual_report, actual_policies, root=root,
                       expected_math=verification, expected_inputs=inputs,
                       current_head=head, bundle_guard=published_guard)
        published_guard()
    except BaseException:
        _rollback_owned(owned)
        raise
    finally:
        # Published targets survive success; only stages are removed here.
        _rollback_owned({path: owned[path] for path in stages.values() if path in owned})


def generate(root=ROOT):
    targets = _fixed_targets(root)
    _guard_targets_absent(targets)
    head, producer, verification = _source_context(root)
    inputs = _load_inputs(root)
    returned, results, policy_raws = {}, {}, {}

    def guard():
        _guard_generation(root, head, producer, verification, inputs)

    try:
        guard()
        for fixture_id, fixture in FIXTURES.items():
            _guard_targets_absent(targets)
            guard()
            print(f"START {fixture_id} T=10000 D=3000", flush=True)
            start = time.perf_counter()
            # The producer import is lazy and included in the first call interval.
            from pokerlab.river_tail_adapter import solve_river_tail
            result = solve_river_tail(fixture["board"], fixture["oop"], fixture["ip"],
                                      fixture["config"], iterations=ITERATIONS,
                                      discard=DISCARD)
            elapsed = time.perf_counter() - start
            returned[fixture_id] = (result, elapsed)
            guard()
            _validate_profile_metadata(result, fixture_id)
            raw_policy = _canonical(result)
            if len(raw_policy) > POLICY_CAP:
                raise ValueError("Generated policy exceeds two-megabyte cap")
            row = _audit_policy(result, fixture_id, inputs, guard=guard)
            row.update(_metadata_only_report_row(result, elapsed))
            results[fixture_id] = row
            policy_raws[fixture_id] = raw_policy
            guard()
            print(f"AUDITED {fixture_id} target_met={row['exact_threshold_met']} "
                  f"nash_conv={float(Fraction(row['exact_metrics_fractions']['nash_conv']))}",
                  flush=True)
        report = _build_report(head, producer, verification, inputs, results, policy_raws)
        report_raw = _canonical(report)
        if len(report_raw) > REPORT_CAP:
            raise ValueError("Generated report exceeds eight-megabyte cap")
        guard()
        _publish_bundle(report_raw, policy_raws, root=root, head=head, producer=producer,
                        verification=verification, inputs=inputs)
        return report
    except BaseException as error:
        # Any returned actual policy remains recoverable, including on late failure.
        for fixture_id, (payload, elapsed) in returned.items():
            try:
                path = _preserve_rejected(root, fixture_id, payload, head, producer,
                                          elapsed, error, verification=verification)
                print(f"Unaccepted raw policy preserved at {path}", file=sys.stderr)
            except Exception as save_error:
                print(f"Raw-policy preservation failed for {fixture_id}: {save_error}",
                      file=sys.stderr)
        raise


def _final_bundle_guard(targets, owned, expected_report, expected_policies):
    for key, target in targets.items():
        if not target.exists() or _bundle_identity(target) != owned[target]:
            raise RuntimeError(f"Published bundle inode changed: {key}")
    if _read_bounded(targets["report"], REPORT_CAP) != expected_report:
        raise RuntimeError("Published report bytes changed during final guard")
    for key in FIXTURES:
        if _read_bounded(targets[key], POLICY_CAP) != expected_policies[key]:
            raise RuntimeError(f"Published policy bytes changed during final guard: {key}")


def verify(root=ROOT):
    current_head = _head(root)
    expected_math = _verification_hashes(root)
    _require_committed(root, expected_math, head=current_head)
    inputs = _load_inputs(root)
    targets = _fixed_targets(root)
    report_raw, policy_raws = _read_bundle(targets)
    identities = {path: _bundle_identity(path) for path in targets.values()}

    def bundle_guard():
        _final_bundle_guard(targets, identities, report_raw, policy_raws)

    result = _verify_bundle(report_raw, policy_raws, root=root, expected_math=expected_math,
                            expected_inputs=inputs, current_head=current_head,
                            bundle_guard=bundle_guard)
    _guard_replay(root, current_head, expected_math, inputs, bundle_guard)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--generate", action="store_true")
    action.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if args.generate:
        generate()
        print("Generated and verified the fixed two-game direct river-tail bundle")
    else:
        verify()
        print("Verified the fixed two-game direct river-tail bundle without training")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
