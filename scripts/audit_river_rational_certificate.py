"""Exact normalized-profile audits for pinned river CFR+ policies.

This script evaluates saved policies only. It is not a solver, and exactness is
with respect to the already independently validated binary64 numeric model.
"""
import argparse
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

from pokerlab.cards import expand_range
from scripts import turn_river_validation as validator
from scripts.benchmark_turn_river_independent import ROOT, source_hashes
from scripts.replay_river_accuracy_extension import rational_polarised
from scripts.turn_rational_certificate import (
    MAX_EXACT_DEPTH as EXACT_DEPTH_LIMIT,
    MAX_EXACT_WORK as EXACT_WORK_LIMIT,
    MAX_FRACTION_BITS as EXACT_FRACTION_BIT_LIMIT,
    evaluate_exact,
)


EXTENSION_REPORT = ROOT / "benchmarks" / "results" / "river-cfrplus-accuracy-extension-v1.json"
LONG_REPORT = ROOT / "benchmarks" / "results" / "river-cfrplus-long-budget-v1.json"
HARDENED_REPLAY_BRIDGE = ROOT / "benchmarks" / "results" / "river-cfrplus-accuracy-hardened-replay-v1.json"
EXTENSION_POLICIES = ROOT / "benchmarks" / "results" / "river-cfrplus-accuracy-policies-v1"
LONG_POLICIES = ROOT / "benchmarks" / "results" / "river-cfrplus-long-budget-policies-v1"
OUTPUT_PATH = ROOT / "benchmarks" / "results" / "river-rational-certificate-v1.json"

PARENT_CANONICAL_SHA256 = {
    "river-cfrplus-accuracy-extension-v1":
        "9e36db27df5c313a5aa5f83fc71bacda74a775c8da50a66a787a7430f281ff8d",
    "river-cfrplus-long-budget-v1":
        "8c93c4f71b2634feea662941f422e16a6cb20d3ab098ca88b90b68a50becf257",
}
HARDENED_REPLAY_BRIDGE_SHA256 = "696c946ad7a2427de3bd49c0b16a593b26de0c946d00412a3671c51f8f6ce9e2"
HARDENED_VALIDATOR_SHA256 = "818a2a5a7b0f8ad8ce9891ec0d6df2e8cf62d7faf8df8b5e136472596e0a2ea1"
HARDENED_REPLAY_SCRIPT_SHA256 = "305c2d93bbccc020a75b479a9ec449521a96ca79f07c835f0e92ee3898388cb3"

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

# (archive, scenario, backend, iterations): (filename, immutable raw-byte digest)
POLICY_PINS = {
    ("river-cfrplus-accuracy-extension-v1", "river-polarised-bluffcatcher", "materialized", 1000):
        ("river-polarised-bluffcatcher-materialized-1000.json", "20fa65838ae0756f03d0269f89ff997a3998dd7d39513b5297578cf951d9427d"),
    ("river-cfrplus-accuracy-extension-v1", "river-polarised-bluffcatcher", "matrix-free", 1000):
        ("river-polarised-bluffcatcher-matrix-free-1000.json", "15c20fb27dfb3a530aa1cb873888376d2c88f31b7c3db051a9d61ef2725e47a1"),
    ("river-cfrplus-accuracy-extension-v1", "river-polarised-bluffcatcher", "materialized", 3000):
        ("river-polarised-bluffcatcher-materialized-3000.json", "d91594cb2893956df4b25ceecbd8d854379d9e96a7372a87fcdfdd603242ddba"),
    ("river-cfrplus-accuracy-extension-v1", "river-polarised-bluffcatcher", "matrix-free", 3000):
        ("river-polarised-bluffcatcher-matrix-free-3000.json", "7814dd26d01f2e0f91614f1a0314f6b89b324c852ef18cafb2141fa51c4cc6a1"),
    ("river-cfrplus-accuracy-extension-v1", "river-polarised-bluffcatcher", "materialized", 10000):
        ("river-polarised-bluffcatcher-materialized-10000.json", "743b79ea931b2ae3022e345b17b514c4cf739e82989d8a0d45e710f459a280a7"),
    ("river-cfrplus-accuracy-extension-v1", "river-polarised-bluffcatcher", "matrix-free", 10000):
        ("river-polarised-bluffcatcher-matrix-free-10000.json", "c8d3087316d955c5b00e6de0a96893c529676b3318d276e15881d1273dd828ca"),
    ("river-cfrplus-accuracy-extension-v1", "river-weighted-raises", "materialized", 1000):
        ("river-weighted-raises-materialized-1000.json", "40b846d00232908aaa44f89c9025fd3fe03144494b09abb367dcb1a44e2b4a35"),
    ("river-cfrplus-accuracy-extension-v1", "river-weighted-raises", "matrix-free", 1000):
        ("river-weighted-raises-matrix-free-1000.json", "17b057ba7bda9d95fc2cb60ccf1af7adedc6b2dce251813481c2dbb8d6ad1aff"),
    ("river-cfrplus-accuracy-extension-v1", "river-weighted-raises", "materialized", 3000):
        ("river-weighted-raises-materialized-3000.json", "2ad420241a001299cea720b441715c6155935ff85f53f36eb7cec08b57f71bac"),
    ("river-cfrplus-accuracy-extension-v1", "river-weighted-raises", "matrix-free", 3000):
        ("river-weighted-raises-matrix-free-3000.json", "29c99ad55df4170fc67a3612bc42cabe18a0186c9da17d060cf081110b96d57c"),
    ("river-cfrplus-accuracy-extension-v1", "river-weighted-raises", "materialized", 10000):
        ("river-weighted-raises-materialized-10000.json", "499a460b566f40ca4ed23f7d6f9567e1bd41fd43984284438b6807643dddb8e0"),
    ("river-cfrplus-accuracy-extension-v1", "river-weighted-raises", "matrix-free", 10000):
        ("river-weighted-raises-matrix-free-10000.json", "0619ce135a3d960f0065ef359edf29a0ff94cb04c6ce7274b6e3afdbb3925605"),
    ("river-cfrplus-long-budget-v1", "river-polarised-bluffcatcher", "matrix-free", 10000):
        ("river-polarised-bluffcatcher-matrix-free-10000.json", "c2774cedac0f1c365eca9e2c4492ef103c2df0c82fa376d4a0a91e821d49fdef"),
    ("river-cfrplus-long-budget-v1", "river-polarised-bluffcatcher", "matrix-free", 30000):
        ("river-polarised-bluffcatcher-matrix-free-30000.json", "0b8a3d0f4eb211c5564a8ba6765778658f3fc6d2bf1906d6823ee14a59f33bb0"),
    ("river-cfrplus-long-budget-v1", "river-polarised-bluffcatcher", "matrix-free", 100000):
        ("river-polarised-bluffcatcher-matrix-free-100000.json", "cc5862bf0c3bfa2536dd7fe4e4ccd90d3b21d40628ed9fa08eb64a41f09fc3b5"),
}

ARCHIVES = {
    "river-cfrplus-accuracy-extension-v1": {
        "report_path": EXTENSION_REPORT, "policy_dir": EXTENSION_POLICIES,
    },
    "river-cfrplus-long-budget-v1": {
        "report_path": LONG_REPORT, "policy_dir": LONG_POLICIES,
    },
}
METRIC_NAMES = (
    "value_oop", "value_ip", "oop_best_response_value",
    "ip_best_response_value", "oop_best_response_gain",
    "ip_best_response_gain", "nash_conv", "exploitability",
)
FLOAT_TOLERANCE = 1e-9
BENCHMARK_THRESHOLD = "1/1000"
EXPECTED_MEETS = 5
EXPECTED_MISSES = 10


def _sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _assert_unchanged(before, after, what):
    if before != after:
        raise RuntimeError(f"A pinned {what} changed during river rational audit")


def _normalized_path(value):
    return str(value).replace("\\", "/")


def _source_hash_candidates(path):
    raw = path.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    return {_sha256(raw), _sha256(lf), _sha256(crlf)}


def _validate_parent_document(source, report):
    expected_digest = PARENT_CANONICAL_SHA256[source]
    if _sha256(_canonical(report)) != expected_digest:
        raise ValueError(f"{source} parent report differs from its pinned canonical digest")
    if report.get("benchmark_id") != source:
        raise ValueError(f"{source} report has the wrong benchmark identity")
    expected_fixtures = ([FIXTURES["river-polarised-bluffcatcher"],
                          FIXTURES["river-weighted-raises"]]
                         if source == "river-cfrplus-accuracy-extension-v1" else
                         [FIXTURES["river-polarised-bluffcatcher"]])
    actual_fixtures = (report.get("fixtures") if source ==
                       "river-cfrplus-accuracy-extension-v1" else
                       [report.get("fixture")])
    if actual_fixtures != expected_fixtures:
        raise ValueError(f"{source} fixtures differ from the frozen inputs")
    expected_keys = {key for key in POLICY_PINS if key[0] == source}
    found = {}
    for row in report.get("results", ()):
        iteration_key = ("iterations" if source ==
                         "river-cfrplus-accuracy-extension-v1" else
                         "iterations_completed")
        if source == "river-cfrplus-long-budget-v1":
            if row.get("iterations_requested") != row.get("iterations_completed"):
                raise ValueError("Long-budget row did not complete its requested fixed sweeps")
        key = (source, row.get("scenario"), row.get("backend"),
               row.get(iteration_key))
        if key in found:
            raise ValueError(f"{source} contains a duplicate profile identity")
        found[key] = row
    if set(found) != expected_keys:
        raise ValueError(f"{source} rows differ from the exact pinned profile set")
    for key, (filename, policy_hash) in POLICY_PINS.items():
        if key[0] != source:
            continue
        row = found[key]
        if (row.get("algorithm") != "cfrplus" or
                row.get("policy_file") != filename or
                row.get("policy_sha256") != policy_hash):
            raise ValueError(f"{source} row differs from pinned identity {key[1:]}")
        if source == "river-cfrplus-accuracy-extension-v1":
            if row.get("iterations") != key[3]:
                raise ValueError("Accuracy-extension row has the wrong iteration count")
        elif (row.get("iterations_requested") != key[3] or
              row.get("iterations_completed") != key[3] or
              row.get("configured_solver_target_exploitability") is not None):
            raise ValueError("Long-budget row is not its fixed-iteration profile")
    if source == "river-cfrplus-long-budget-v1":
        baseline = report.get("archived_10k_baseline")
        if (not isinstance(baseline, dict) or
                baseline.get("policy_file") != (
                    "benchmarks/results/river-cfrplus-accuracy-policies-v1/"
                    "river-polarised-bluffcatcher-matrix-free-10000.json") or
                baseline.get("policy_sha256") != POLICY_PINS[(
                    "river-cfrplus-accuracy-extension-v1",
                    "river-polarised-bluffcatcher", "matrix-free", 10000)][1]):
            raise ValueError("Long-budget report does not point to the pinned extension 10k archive")
    return found


def _load_parent_reports():
    reports = {}
    indexed = {}
    for source, info in ARCHIVES.items():
        report = json.loads(info["report_path"].read_text(encoding="utf-8"))
        indexed[source] = _validate_parent_document(source, report)
        reports[source] = report
    return reports, indexed


def _validate_hardened_replay_bridge(reports):
    payload = HARDENED_REPLAY_BRIDGE.read_bytes()
    bridge = json.loads(payload)
    if _sha256(_canonical(bridge)) != HARDENED_REPLAY_BRIDGE_SHA256:
        raise ValueError("Hardened-replay bridge differs from its pinned canonical digest")
    if (bridge.get("schema_version") != 1 or
            bridge.get("extension_report_canonical_sha256") !=
            PARENT_CANONICAL_SHA256["river-cfrplus-accuracy-extension-v1"] or
            bridge.get("hardened_validator_sha256") != HARDENED_VALIDATOR_SHA256 or
            bridge.get("replay_script_sha256") != HARDENED_REPLAY_SCRIPT_SHA256):
        raise ValueError("Hardened-replay bridge provenance fields differ from the approved pins")

    extension_source = "river-cfrplus-accuracy-extension-v1"
    bridge_result_rows = bridge.get("results")
    if not isinstance(bridge_result_rows, list) or len(bridge_result_rows) != 12:
        raise ValueError("Hardened-replay bridge must contain exactly twelve profile rows")
    extension_rows = {
        (row.get("scenario"), row.get("backend"), row.get("iterations")): row
        for row in bridge_result_rows
    }
    expected = {key[1:]: (filename, digest)
                for key, (filename, digest) in POLICY_PINS.items()
                if key[0] == extension_source}
    if len(extension_rows) != 12 or set(extension_rows) != set(expected):
        raise ValueError("Hardened-replay bridge does not cover exactly the twelve extension profiles")
    for identity, (filename, digest) in expected.items():
        row = extension_rows[identity]
        if row.get("policy_sha256") != digest:
            raise ValueError(f"Hardened-replay bridge policy identity/hash differs: {identity}")

    current_validator = ROOT / "scripts" / "turn_river_validation.py"
    if HARDENED_VALIDATOR_SHA256 not in _source_hash_candidates(current_validator):
        raise ValueError("Current validator is not the bridge-approved hardened whole-file version")
    long_sources = {_normalized_path(path): digest
                    for path, digest in reports["river-cfrplus-long-budget-v1"].get(
                        "source_sha256", {}).items()}
    validator_rel = "scripts/turn_river_validation.py"
    if long_sources.get(validator_rel) not in _source_hash_candidates(current_validator):
        raise ValueError("Long-budget validator pin differs from the bridge-approved hardened validator")
    return {
        "path": HARDENED_REPLAY_BRIDGE.relative_to(ROOT).as_posix(),
        "canonical_sha256": HARDENED_REPLAY_BRIDGE_SHA256,
        "hardened_validator_sha256": HARDENED_VALIDATOR_SHA256,
        "replay_script_sha256": HARDENED_REPLAY_SCRIPT_SHA256,
        "verified_extension_policy_identities": len(extension_rows),
    }


def _check_historical_model_sources(reports):
    """Require historical matches only for the independent numeric model."""
    relevant = (
        ROOT / "pokerlab" / "cards.py",
        ROOT / "scripts" / "preflop_validation.py",
        ROOT / "scripts" / "benchmark_turn_river_independent.py",
        ROOT / "benchmarks" / "turn-river-quality-v1.json",
    )
    for source, report in reports.items():
        archived = {_normalized_path(path): digest
                    for path, digest in report.get("source_sha256", {}).items()}
        for path in relevant:
            relative = path.relative_to(ROOT).as_posix()
            digest = archived.get(relative)
            if digest is None or digest not in _source_hash_candidates(path):
                raise ValueError(
                    f"{source} historical numeric-model source differs at {relative}")
def _source_fingerprints():
    values = {_normalized_path(path): digest
              for path, digest in source_hashes().items()}
    extra = [
        ROOT / "scripts" / "turn_rational_certificate.py",
        ROOT / "scripts" / "river_analytical.py",
        ROOT / "scripts" / "replay_river_accuracy_extension.py",
        ROOT / "scripts" / "audit_river_rational_certificate.py",
        ROOT / "tests" / "test_audit_river_rational_certificate.py",
        ROOT / "tests" / "test_river_rational_review.py",
    ]
    for info in ARCHIVES.values():
        extra.append(info["report_path"])
    extra.append(HARDENED_REPLAY_BRIDGE)
    for key, (filename, _) in POLICY_PINS.items():
        source = key[0]
        extra.append(ARCHIVES[source]["policy_dir"] / filename)
    for path in extra:
        if not path.is_file():
            raise ValueError(f"Required fingerprint input is missing: {path}")
        values[path.relative_to(ROOT).as_posix()] = _sha256(path.read_bytes())
    return dict(sorted(values.items()))


def _policy_paths(source, filename):
    # Filename is pinned and must remain a simple leaf; never allow report data
    # to redirect a read outside its immutable archive directory.
    if Path(filename).name != filename:
        raise ValueError("Pinned policy filename must be a path leaf")
    return ARCHIVES[source]["policy_dir"] / filename


def _read_policy(source, key):
    filename, expected_hash = POLICY_PINS[key]
    path = _policy_paths(source, filename)
    payload = path.read_bytes()
    raw_hash = _sha256(payload)
    if raw_hash != expected_hash:
        raise ValueError(f"Saved policy bytes differ from pinned SHA-256: {key}")
    result = json.loads(payload)
    if not isinstance(result, dict) or result.get("iterations") != key[3]:
        raise ValueError(f"Saved complete policy has wrong iteration metadata: {key}")
    if result.get("algorithm") != "cfrplus":
        raise ValueError(f"Saved complete policy has wrong algorithm: {key}")
    return result, payload, raw_hash, path


def _independent_model(result, fixture):
    board = validator.cards(fixture["board"])
    config = validator._config(fixture["config"], "config")
    ranges = (expand_range(fixture["oop"], board),
              expand_range(fixture["ip"], board))
    if any(weight <= 0 for side in ranges for weight in side.values()):
        ranges = tuple({hand: weight for hand, weight in side.items()
                        if weight > 0} for side in ranges)
    worlds, selected = validator._worlds(board, ranges, None)
    if selected:
        raise ValueError("Complete river fixture unexpectedly produced future runouts")
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
        raise ValueError("Complete river numeric tree unexpectedly contains chance nodes")
    nodes = validator._collect_nodes(root)
    policies = validator._validate_policy(
        result, root, nodes, worlds, board, selected,
        runouts_were_omitted=True,
    )
    return board, config, worlds, root, nodes, policies


def _check_exact_identities(exact):
    metrics = exact["metrics"]
    value = metrics["value_oop"]
    if metrics["value_ip"] != -value:
        raise ValueError("Exact river profile values are not zero-sum")
    lower = -metrics["ip_best_response_value"]
    upper = metrics["oop_best_response_value"]
    if not lower <= value <= upper:
        raise ValueError("Exact legal-response interval does not contain profile EV")
    if metrics["nash_conv"] != upper - lower:
        raise ValueError("Exact NashConv differs from legal BR interval width")
    if metrics["nash_conv"] != (metrics["oop_best_response_gain"] +
                                metrics["ip_best_response_gain"]):
        raise ValueError("Exact NashConv differs from the sum of unilateral gains")
    if metrics["nash_conv"] != 2 * metrics["exploitability"]:
        raise ValueError("Exact NashConv differs from twice exploitability")
    if metrics["oop_best_response_gain"] != upper - value:
        raise ValueError("Exact OOP gain differs from U - V")
    if metrics["ip_best_response_gain"] != value - lower:
        raise ValueError("Exact IP gain differs from V - L")
    if metrics["oop_best_response_gain"] < 0 or metrics["ip_best_response_gain"] < 0:
        raise ValueError("Exact unilateral gains must be nonnegative")
    if not isinstance(lower, Fraction) or not isinstance(upper, Fraction):
        raise TypeError("Exact response interval must contain Fractions")
    return lower, upper


def _polarised_witness(result, fixture, exact):
    from fractions import Fraction

    witness = rational_polarised(result, fixture)
    value = Fraction(witness["value_oop_fraction"])
    br_oop = Fraction(witness["oop_br_fraction"])
    br_ip = Fraction(witness["ip_br_fraction"])
    witness_metrics = {
        "value_oop": value,
        "value_ip": -value,
        "oop_best_response_value": br_oop,
        "ip_best_response_value": br_ip,
        "oop_best_response_gain": br_oop - value,
        "ip_best_response_gain": value + br_ip,
        "nash_conv": br_oop + br_ip,
        "exploitability": (br_oop + br_ip) / 2,
    }
    if exact["metrics"] != witness_metrics:
        raise ValueError("General exact river audit differs from explicit-history witness")
    if not -br_ip <= Fraction(25) <= br_oop:
        raise ValueError("Polarized exact interval does not contain the known value 25")
    if witness.get("known_game_value_fraction") != "25" or not witness.get("known_value_in_interval"):
        raise ValueError("Explicit-history witness did not certify known value 25")
    return {
        "method": "river_analytical explicit-history oracle (5 histories, 16 OOP / 4 IP pure responses)",
        "metrics_fractions": {name: str(value) for name, value in witness_metrics.items()},
        "lower_value_bound_fraction": str(-br_ip),
        "upper_value_bound_fraction": str(br_oop),
        "known_value_fraction": "25",
        "known_value_in_interval": True,
    }


def _audit_profile(source, key, parent_row, reports):
    result, payload, raw_hash, policy_path = _read_policy(source, key)
    fixture = FIXTURES[key[1]]
    if (result.get("board") != list(validator.cards(fixture["board"])) or
            result.get("config") != validator._config(fixture["config"], "config").to_dict()):
        raise ValueError(f"Serialized policy model metadata differs from pinned fixture: {key}")
    original_canonical = _canonical(result)

    float_oracle = validator.replay_policy(
        result, fixture["oop"], fixture["ip"], board=fixture["board"],
        config=fixture["config"],
    )
    float_differences = validator.compare_result(
        result, float_oracle, tolerance=FLOAT_TOLERANCE)
    board, config, worlds, root, nodes, policies = _independent_model(result, fixture)
    exact = evaluate_exact(
        root, worlds, policies, config.pot, result=result,
        max_work=EXACT_WORK_LIMIT, max_depth=EXACT_DEPTH_LIMIT,
        max_bits=EXACT_FRACTION_BIT_LIMIT,
    )
    if (exact["work_limit"], exact["depth_limit"], exact["fraction_bit_limit"]) != (
            EXACT_WORK_LIMIT, EXACT_DEPTH_LIMIT, EXACT_FRACTION_BIT_LIMIT):
        raise RuntimeError("Exact evaluator returned unexpected resource limits")
    lower, upper = _check_exact_identities(exact)
    exact_float_metrics = {name: float(value)
                           for name, value in exact["metrics"].items()}
    exact_float_differences = {
        name: exact_float_metrics[name] - float(float_oracle[name])
        for name in METRIC_NAMES
    }
    if any(abs(delta) > FLOAT_TOLERANCE
           for delta in exact_float_differences.values()):
        raise ValueError(f"Exact normalized-profile metrics exceed floating tolerance: {key}")
    if _canonical(result) != original_canonical:
        raise RuntimeError("Exact audit mutated a pinned policy")

    normalized_sha = _sha256(_canonical(exact["normalized_policy_rows"]))
    witness = (_polarised_witness(result, fixture, exact)
               if key[1] == "river-polarised-bluffcatcher" else None)
    exact_threshold = exact["threshold_met"]
    if exact_threshold != (exact["metrics"]["nash_conv"] <= Fraction(1, 1000)):
        raise ValueError("Exact benchmark threshold does not match exact NashConv")
    if parent_row.get("benchmark_threshold_met", parent_row.get("target_met")) != exact_threshold:
        raise ValueError(f"Exact threshold decision differs from pinned report: {key}")
    return {
        "archive": source,
        "scenario": key[1], "backend": key[2], "iterations": key[3],
        "policy_file": policy_path.relative_to(ROOT).as_posix(),
        "raw_policy_sha256": raw_hash,
        "complete_policy_payload_scope": "complete decoded serialized solver result",
        "fixture_canonical_sha256": _sha256(_canonical(fixture)),
        "row_normalized_policy_sha256": normalized_sha,
        "normalized_policy_scope": "exact row-normalized probabilities from serialized binary64 action probabilities",
        "normalization_ledger": exact["normalization_ledger"],
        "maximum_row_adjustment_fraction": str(exact["max_row_adjustment"]),
        "parent_report_metrics": parent_row.get("metrics"),
        "serialized_vs_float_replay_deltas": float_differences,
        "exact_metrics_fractions": {
            name: str(value) for name, value in exact["metrics"].items()},
        "exact_float_metrics": exact_float_metrics,
        "exact_vs_float_replay_deltas": exact_float_differences,
        "lower_value_bound_fraction": str(lower),
        "upper_value_bound_fraction": str(upper),
        "benchmark_nash_conv_threshold_fraction": BENCHMARK_THRESHOLD,
        "benchmark_threshold_met": exact_threshold,
        "verified_worlds": len(worlds),
        "verified_compatible_pairs": float_oracle["compatible_pair_count"],
        "verified_information_sets": float_oracle["checked_information_sets"],
        "verified_decision_nodes": len(nodes),
        "verified_public_tree_nodes": exact["tree_nodes"],
        "verified_tree_depth": exact["tree_depth"],
        "chance_nodes": 0,
        "work": exact["work"], "work_by_kind": exact["work_by_kind"],
        "maximum_fraction_bits": exact["maximum_fraction_bits"],
        "resource_limits": {
            "maximum_work": exact["work_limit"],
            "maximum_depth": exact["depth_limit"],
            "maximum_fraction_bits": exact["fraction_bit_limit"],
        },
        "polarised_explicit_history_witness": witness,
    }


def _index_result_rows(rows):
    if not isinstance(rows, list):
        raise ValueError("Certificate results must be a list of profile rows")
    indexed = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Certificate profile row must be an object")
        key = (row.get("archive"), row.get("scenario"), row.get("backend"),
               row.get("iterations"))
        if (key[0] not in ARCHIVES or key[1] not in FIXTURES or
                key[2] not in ("materialized", "matrix-free") or
                type(key[3]) is not int):
            raise ValueError("Certificate profile row has an invalid identity")
        if key in indexed:
            raise ValueError(f"Certificate contains duplicate profile row {key}")
        indexed[key] = row
    if set(indexed) != set(POLICY_PINS):
        raise ValueError("Certificate rows do not cover exactly the fifteen pinned profiles")
    return indexed


def _archive_rows(reports, indexed, expected_rows=None):
    expected_by_key = (_index_result_rows(expected_rows)
                       if expected_rows is not None else None)
    output = []
    for key in sorted(POLICY_PINS, key=lambda item: (item[0], item[1], item[3], item[2])):
        parent_row = indexed[key[0]][key]
        if expected_by_key is not None:
            row = _verify_saved_profile_row(
                expected_by_key[key], key[0], key, indexed, reports)
        else:
            row = _audit_profile(key[0], key, parent_row, reports)
        output.append(row)
    if len(output) != 15 or len({(row["archive"], row["scenario"], row["backend"],
                                   row["iterations"]) for row in output}) != 15:
        raise ValueError("Expected exactly fifteen distinct archive profile records")
    meets = sum(row["benchmark_threshold_met"] for row in output)
    if meets != EXPECTED_MEETS or len(output) - meets != EXPECTED_MISSES:
        raise ValueError("Exact benchmark meet/miss counts differ from the frozen expected census")
    return output


def _verify_saved_profile_row(saved, source, key, indexed, reports):
    """Rebuild one archived row from its pinned policy bytes, then compare."""
    recomputed = _audit_profile(source, key, indexed[source][key], reports)
    _verify_saved_row_matches_recomputation(saved, recomputed)
    return recomputed


def _verify_duplicate_10k(reports=None):
    extension_key = ("river-cfrplus-accuracy-extension-v1",
                     "river-polarised-bluffcatcher", "matrix-free", 10000)
    long_key = ("river-cfrplus-long-budget-v1",
                "river-polarised-bluffcatcher", "matrix-free", 10000)
    ext_result, ext_bytes, ext_sha, _ = _read_policy(extension_key[0], extension_key)
    long_result, long_bytes, long_sha, _ = _read_policy(long_key[0], long_key)
    raw_bytes_equal = ext_bytes == long_bytes
    complete_payload_equal = ext_result == long_result
    if raw_bytes_equal or not complete_payload_equal:
        raise ValueError("The two archived polarised 10k records lost their expected distinct-byte/equal-payload relation")
    return {
        "extension_archive_policy_sha256": ext_sha,
        "long_budget_policy_sha256": long_sha,
        "raw_policy_bytes_equal": raw_bytes_equal,
        "decoded_complete_payloads_equal": complete_payload_equal,
        "note": "The two archives retain different serialized bytes but decode to the same complete result object.",
    }


def audit(generation_baseline=None, expected_results=None):
    baseline_before = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                              text=True).strip()
    if generation_baseline is not None and generation_baseline != baseline_before:
        raise RuntimeError("Generation baseline changed before audit began")
    reports, indexed = _load_parent_reports()
    bridge = _validate_hardened_replay_bridge(reports)
    _check_historical_model_sources(reports)
    source_before = _source_fingerprints()
    profiles = _archive_rows(reports, indexed, expected_results)
    duplicate_10k = _verify_duplicate_10k(reports)
    source_after = _source_fingerprints()
    _assert_unchanged(source_before, source_after, "source or policy input")
    baseline_after = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                             text=True).strip()
    _assert_unchanged(baseline_before, baseline_after, "Git HEAD")
    return {
        "schema_version": 1,
        "certificate_id": "river-rational-certificate-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_git_commit": baseline_before,
        "python": platform.python_version(),
        "parent_canonical_sha256": dict(PARENT_CANONICAL_SHA256),
        "source_sha256": source_after,
        "floating_replay_tolerance_chips": FLOAT_TOLERANCE,
        "exact_work_limit": 100_000,
        "exact_depth_limit": 64,
        "exact_fraction_bit_limit": 65_536,
        "benchmark_nash_conv_threshold_fraction": BENCHMARK_THRESHOLD,
        "expected_meet_count": EXPECTED_MEETS,
        "expected_miss_count": EXPECTED_MISSES,
        "observed_meet_count": sum(row["benchmark_threshold_met"] for row in profiles),
        "observed_miss_count": sum(not row["benchmark_threshold_met"] for row in profiles),
        "duplicate_polarised_10k_archive_relation": duplicate_10k,
        "hardened_replay_bridge": bridge,
        "scope": "Fifteen pinned complete river policies from two historical CFR+ archives; each saved binary64 policy is exactly row-normalized as Fractions and replayed on the unchanged independent configured numeric model.",
        "limitations": "Exact intervals apply to the separately normalized serialized policy in the configured binary64 terminal model. They do not certify the raw unnormalized float profile, an equilibrium for the weighted raised game, or unrestricted Hold'em.",
        "methodology": {
            "independent_replay": "Original turn_river_validation replay and compare_result run before exact arithmetic for every pinned policy.",
            "exact_model": "Existing turn_rational_certificate helper; complete river trees have no chance nodes; default chance grouping remains scan.",
            "normalization": "Each serialized binary64 action probability is converted with Fraction.from_float and each row is exactly normalized; original float inputs and raw policy files are never mutated.",
            "polarised_crosscheck": "All eight Fraction metrics are compared exactly with the separate river_analytical five-history, 16/4 legal pure-response witness; each interval must contain value 25.",
            "weighted_scope": "The weighted raised fixture receives exact profile EV and legal own-information BR bounds only; no known equilibrium value is asserted.",
            "archive_identity": "The duplicate matrix-free polarised 10k result remains two source-report rows: distinct raw serialized bytes, equal decoded complete payloads.",
            "provenance": "Parent canonical reports, the approved hardened-replay bridge, and all fifteen raw policy SHA-256 values are pinned. The bridge binds the earlier extension report to the hardened whole-file validator and its exact twelve policy identities. Other historical checks cover only actual numeric-model dependencies with path/line-ending normalization; current-run source fingerprints are strict raw hashes before and after.",
            "resource_scope": "Unchanged helper limits: 100,000 logical work units, depth 64, and 65,536 Fraction bits. These are audit work/operand limits, not CPU, memory, or RSS bounds.",
        },
        "results": profiles,
    }


def _verify_saved_row_matches_recomputation(saved, recomputed):
    if _canonical(saved) != _canonical(recomputed):
        raise ValueError("Saved river certificate row differs from fresh policy replay and exact recomputation")


def _validate_saved_provenance(saved):
    baseline = saved.get("baseline_git_commit")
    if (not isinstance(baseline, str) or len(baseline) != 40 or
            any(char not in "0123456789abcdef" for char in baseline)):
        raise ValueError("Saved generation baseline is not a full Git commit id")
    inventory = saved.get("source_sha256")
    if not isinstance(inventory, dict) or not inventory:
        raise ValueError("Saved source provenance inventory is missing")
    for name, digest in inventory.items():
        if (not isinstance(name, str) or not name or not isinstance(digest, str) or
                len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)):
            raise ValueError("Saved source provenance inventory is malformed")
    required = {
        "scripts/turn_rational_certificate.py",
        "scripts/audit_river_rational_certificate.py",
        "tests/test_audit_river_rational_certificate.py",
        "tests/test_river_rational_review.py",
        "pokerlab/cards.py",
        "scripts/preflop_validation.py",
        "scripts/turn_river_validation.py",
        "scripts/benchmark_turn_river_independent.py",
        "benchmarks/turn-river-quality-v1.json",
        HARDENED_REPLAY_BRIDGE.relative_to(ROOT).as_posix(),
    }
    required.update(path.relative_to(ROOT).as_posix()
                    for path in (EXTENSION_REPORT, LONG_REPORT))
    required.update(ARCHIVES[source]["policy_dir"].relative_to(ROOT).as_posix() + "/" + filename
                    for source, filename in ((key[0], value[0])
                                             for key, value in POLICY_PINS.items()))
    if not required.issubset(inventory):
        raise ValueError("Saved source provenance omits required pinned audit inputs")
    relevant = [
        ROOT / "scripts" / "turn_rational_certificate.py",
        ROOT / "scripts" / "audit_river_rational_certificate.py",
        ROOT / "tests" / "test_audit_river_rational_certificate.py",
        ROOT / "tests" / "test_river_rational_review.py",
        ROOT / "pokerlab" / "cards.py",
        ROOT / "scripts" / "preflop_validation.py",
        ROOT / "scripts" / "turn_river_validation.py",
        ROOT / "scripts" / "benchmark_turn_river_independent.py",
        ROOT / "benchmarks" / "turn-river-quality-v1.json",
        HARDENED_REPLAY_BRIDGE, EXTENSION_REPORT, LONG_REPORT,
    ]
    relevant.extend(_policy_paths(key[0], POLICY_PINS[key][0]) for key in POLICY_PINS)
    for path in relevant:
        rel = path.relative_to(ROOT).as_posix()
        if inventory[rel] not in _source_hash_candidates(path):
            raise ValueError(f"Saved provenance differs for a pinned audit input: {rel}")
    return baseline


def _compare_saved_to_fresh(saved, fresh):
    fields = (
        "certificate_id", "parent_canonical_sha256", "floating_replay_tolerance_chips",
        "exact_work_limit", "exact_depth_limit", "exact_fraction_bit_limit",
        "benchmark_nash_conv_threshold_fraction", "expected_meet_count",
        "expected_miss_count", "observed_meet_count", "observed_miss_count",
        "duplicate_polarised_10k_archive_relation", "hardened_replay_bridge",
        "scope", "limitations", "methodology", "results",
    )
    for field in fields:
        if _canonical(saved.get(field)) != _canonical(fresh.get(field)):
            raise ValueError(f"Saved river certificate differs from fresh recomputation at {field}")


def verify_saved_artifact(path):
    saved = json.loads(path.read_text(encoding="utf-8"))
    _validate_saved_provenance(saved)
    if saved.get("schema_version") != 1:
        raise ValueError("Saved river certificate has an unsupported schema")
    fresh = audit(expected_results=saved.get("results"))
    _compare_saved_to_fresh(saved, fresh)
    # The generation commit is retained as historical provenance. Verification
    # may occur after the artifact's commit, so it need not equal current HEAD.
    return saved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--verify", action="store_true",
                        help="Recompute and verify an existing all-profile artifact")
    args = parser.parse_args(argv)
    if args.verify:
        verify_saved_artifact(args.output)
        print("Verified exact rational certificate for all fifteen saved policies")
        return 0
    certificate = audit()
    payload = (json.dumps(certificate, indent=2, sort_keys=True,
                          allow_nan=False) + "\n").encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    verify_saved_artifact(args.output)
    print("Audited, saved and recomputed", len(certificate["results"]), "river policies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
