"""Read-only acceptance of the fixed T6000 turn experiment; never trains.

Physical numeric rules, full-physical rational responses and both generic
class traversals are the mathematical authorities. Producer helpers are not
imported. Python source pins normalize CRLF to LF; all other pins are raw.
"""
from __future__ import annotations

import argparse
import copy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

from pokerlab import turn_class_vector_budget as budget
from scripts import turn_three_hand_classes as classes
from scripts import turn_three_hand_exact_oracle as physical
from scripts import turn_three_hand_reference as reference
from scripts import turn_river_validation as rules

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "turn-class-tail-T6000-v1"
REPORT_NAME = SCHEMA + ".json"
POLICY_NAME = SCHEMA + "-policy.json"
BYTE_CAP = 4_000_000
TARGET = Fraction(1, 1000)
METRICS = tuple(reference.METRICS)
FIXTURE = copy.deepcopy(reference.FIXTURE)
OLD_REPORT = "benchmarks/results/turn-three-hand-direct-tail-v1.json"
OLD_POLICY = "benchmarks/results/turn-three-hand-direct-tail-v1-policy.json"
OLD_IDENTITIES = {
    OLD_REPORT: (33_671, "1827e2163b897c5a1c5274e4a300ee365d8234fdf38235647772d63300953a7a"),
    OLD_POLICY: (2_541_067, "c02e37dedf886f586e8b0ce9a98e86d079a32322d6e2ba4eb5beaab127dd6789"),
}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_RE = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_SOURCES = frozenset({
    ".gitattributes",
    ".gitignore",
    "scripts/benchmark_turn_class_tail.py",
    "scripts/verify_turn_class_tail_experiment.py",
    "scripts/turn_three_hand_reference.py",
    "scripts/turn_three_hand_exact_oracle.py",
    "scripts/turn_three_hand_classes.py",
    "scripts/turn_rational_certificate.py",
    "scripts/turn_river_validation.py",
    "scripts/preflop_validation.py",
    "tests/test_benchmark_turn_class_tail.py",
    "tests/test_verify_turn_class_tail_experiment.py",
    "tests/test_turn_class_adversarial.py",
    "tests/test_turn_class_exact_updates.py",
    "tests/test_turn_class_resource_source.py",
    "tests/test_turn_class_tail_adapter.py",
    "tests/test_turn_class_vector_budget.py",
    "tests/test_turn_three_hand_classes.py",
    "tests/test_turn_three_hand_physical.py",
    "docs/turn-class-tail-T6000-experiment-spec.md",
    OLD_REPORT, OLD_POLICY,
})
REQUEST = {
    "iterations": 6000, "discard": 2000,
    "resource_model": "turn-seven-class-vector-v1",
    "averaged_sweeps": 4000, "average_weight_sum": 16_002_000,
    "regret_passes": 12_000, "average_passes": 4000, "total_passes": 16_000,
}
SCOPE = ("One fixed 396-world configured three-hand TURN CFR+ tail policy trained "
         "through seven exact public-river classes; exact evidence is for the "
         "serialized binary64 policy, with no assumed equilibrium value or "
         "general convergence claim.")
VERIFICATION_SCOPE = (
    "Policy mathematics, fixed configuration/admission metadata and committed "
    "source/input identities are independently checked. Runtime, host, call-count "
    "and observed internal ledger entries are producer-reported observations.")


def need(condition, message):
    if not condition:
        raise ValueError(message)


def jsonable(value):
    if type(value) is Fraction:
        return str(value)
    if type(value) is dict:
        if all(type(key) is str for key in value):
            return {key: jsonable(item) for key, item in value.items()}
        return {"key_value_entries": [
            {"key": jsonable(key), "value": jsonable(item)}
            for key, item in sorted(value.items(), key=lambda pair: canonical(pair[0]))]}
    if type(value) in (tuple, list):
        return [jsonable(item) for item in value]
    if type(value) is float:
        need(math.isfinite(value), "Nonfinite JSON value")
    if type(value) in (str, int, float, bool) or value is None:
        return value
    raise ValueError("Unsupported JSON value")


def canonical(value):
    return (json.dumps(jsonable(value), sort_keys=True, indent=2,
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(path):
    size = path.stat().st_size
    need(0 <= size <= BYTE_CAP, "Artifact exceeds four-megabyte cap")
    with path.open("rb") as handle:
        raw = handle.read(BYTE_CAP + 1)
    need(len(raw) == size and len(raw) <= BYTE_CAP, "Artifact changed during bounded read")
    return raw


def _object(raw):
    need(type(raw) is bytes and len(raw) <= BYTE_CAP, "Bounded bytes required")
    value = json.loads(raw)
    need(type(value) is dict and canonical(value) == raw, "Canonical UTF8/LF JSON object required")
    return value


def _git(root, *arguments):
    return subprocess.check_output(["git", *arguments], cwd=root, stderr=subprocess.STDOUT)


def _head(root):
    value = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    need(bool(GIT_RE.fullmatch(value)), "Malformed current HEAD")
    return value


def source_names_at(root, commit):
    names = _git(root, "ls-tree", "-r", "--name-only", commit, "--", "pokerlab").decode("utf-8").splitlines()
    modules = {name for name in names if re.fullmatch(r"pokerlab/[A-Za-z_][A-Za-z_0-9]*\.py", name)}
    need("pokerlab/turn_class_tail_adapter.py" in modules and
         "pokerlab/turn_class_vector_budget.py" in modules, "Frozen compact source missing")
    return tuple(sorted(modules | REQUIRED_SOURCES))


def _normalized(name, raw):
    return raw.replace(b"\r\n", b"\n") if name.endswith(".py") else raw


def verify_source_map(root, report):
    commit = report.get("training_source_git_commit")
    need(type(commit) is str and bool(GIT_RE.fullmatch(commit)) and
         report.get("generation_head") == commit, "Malformed training source commit")
    need(_git(root, "cat-file", "-t", commit).strip() == b"commit", "Training source is not a commit")
    subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=root, check=True)
    names = source_names_at(root, commit)
    current_modules = {path.relative_to(root).as_posix()
                       for path in (root / "pokerlab").glob("*.py")}
    frozen_modules = {name for name in names if name.startswith("pokerlab/")}
    need(current_modules == frozen_modules, "Current pokerlab module inventory differs")
    pins = report.get("source_sha256")
    need(type(pins) is dict and set(pins) == set(names), "Frozen source inventory differs")
    for name in names:
        digest = pins[name]
        need(type(digest) is str and bool(SHA_RE.fullmatch(digest)), "Malformed source digest")
        frozen = _normalized(name, _git(root, "show", f"{commit}:{name}"))
        need(sha(frozen) == digest, "Frozen Git source digest differs: " + name)
        current = _normalized(name, (root / name).read_bytes())
        need(sha(current) == digest, "Current source/input differs from frozen source: " + name)
    return commit, dict(pins)


def _finite(value, message):
    need(type(value) in (int, float) and math.isfinite(value), message)
    return float(value)


def _equal(actual, expected, message):
    need(canonical(actual) == canonical(expected), message)


def validate_metadata(payload):
    """Check fixed source/admission facts without calling a solver or tree builder."""
    plan = budget.plan_request(6000, 2000, REQUEST["resource_model"])
    config = FIXTURE["config"]
    board = list(rules.cards(FIXTURE["board"]))
    runouts = [card for card in rules.DECK if card not in board]
    expected = {
        "method": "Direct original-weight CFR+ tail averaging on seven exact public-river classes",
        "algorithm": "cfrplus", "solver_version": "research-turn-seven-class-tail-adapter-v1",
        "strategy_schema": "postflop-strategy-v1", "backend": "exact-public-chance-tree",
        "execution_backend": "direct-original-weight-seven-class-tail-python",
        "diagnostics_backend": "public-batched-python", "board": board,
        "config": config, "street_configs": {"turn": config, "river": config},
        "turn_config": config, "river_config": config, "runouts": runouts,
        "reachable_runouts": runouts, "runout_mode": "full-deck",
        "chance_note": "Class masses derive from the original rational joint law; all 48 physical rivers are restored in the output policy.",
        "iterations": 6000, "requested_iterations": 6000, "discard": 2000,
        "source_iteration_window": [2001, 6000], "averaged_sweeps": 4000,
        "average_weight_sum": 16_002_000,
        "average_schedule": "direct-original-linear-sweep-weight-own-reach-tail",
        "update_schedule": "alternating-oop-then-ip", "requested_regret_passes": 12_000,
        "requested_average_passes": 4000, "requested_total_traversal_passes": 16_000,
        "deals": 9, "compatible_pairs": 9, "worlds": 396, "worlds_materialized": 396,
        "info_sets": 3606, "public_nodes": 1254, "public_states": 3039,
        "terminal_nodes": 1780, "chance_nodes": 5, "world_traversal_nodes": 32,
        "tree_actions": 2798, "public_state_limit": 250_000, "public_node_limit": 10_000,
        "public_batch_edge_limit": 250_000, "resource_model": REQUEST["resource_model"],
        "physical_representation": {"worlds": 396, "rivers": 48, "public_states": 3039,
                                    "policy_rows": 3606, "action_slots": 8046},
        "training_representation": {"worlds": 45, "river_classes": 7, "public_states": 456,
                                    "policy_rows": 486, "action_slots": 1086},
        "modeled_rank_inputs": 276, "modeled_rank_loop_cells": plan["modeled_rank_loop_cells"],
        "pot": 100.0, "effective_stack": 220.0, "training_calls": 1,
        "scope": "Fixed three-hand turn game using a globally lossless seven-class public-river representation; full physical policy rows are restored before diagnostics. No preflop, multiway, rake, unrestricted no-limit, or exact-equilibrium claim.",
        "diagnostic_provenance": "Fresh full-physical public-batched profile and best-response diagnostics on the lifted policy; numeric convergence diagnostics are not an exact certificate.",
    }
    need(type(payload) is dict and set(payload) == set(expected) | set(METRICS) | {"strategy", "resource_usage"},
         "Complete policy field set differs")
    for key, value in expected.items():
        _equal(payload[key], value, "Fixed policy metadata differs: " + key)
    for name in METRICS:
        _finite(payload[name], "Nonfinite API diagnostic: " + name)
    need(type(payload["strategy"]) is list and len(payload["strategy"]) == 3606,
         "Full physical policy row count differs")
    usage = payload["resource_usage"]
    expected_usage = {
        "ordinary_physical_reference": {
            "world_node_work": 396 * 32 * 18_000,
            "world_node_work_limit": 30_000_000, "world_node_work_would_admit": False,
            "dense_hand_state_pass_work": 3 * 3039 * 18_003,
            "dense_hand_state_pass_work_limit": 30_000_000,
            "dense_hand_state_pass_work_would_admit": False, "enforced": False},
        "info_action_slots": 8046, "info_action_slots_limit": 1_000_000,
        "prefix_hand_edges": 405, "prefix_hand_edge_limit": 250_000,
        **{key: plan[key] for key in (
            "physical_world_iterations", "candidate_pair_iterations", "compact_world_proxy",
            "compact_dense_proxy", "legacy_physical_world_proxy", "legacy_proxy_enforced",
            "trainer_vector_work", "complete_vector_work", "one_time_work_reserve", "explicit_list_writes")},
        "component_charge_note": "Component allowances are source-derived modeled work reservations; observed counts contain adapter-owned logical traversal counts only. Neither is measured runtime, bytes, or RSS.",
    }
    need(type(usage) is dict and set(usage) == set(expected_usage) | {"resource_accounting"},
         "Resource usage field set differs")
    for key, value in expected_usage.items():
        _equal(usage[key], value, "Resource admission differs: " + key)
    ledger = usage["resource_accounting"]
    need(type(ledger) is dict and set(ledger) == {
        "planned", "reserved", "observed", "storage_caps", "storage_reserved", "storage_observed"},
        "Accounting ledger field set differs")
    _equal(ledger["planned"], plan["components"], "Work component plan differs")
    _equal(ledger["reserved"], plan["components"], "Complete work was not reserved")
    _equal(ledger["storage_caps"], plan["storage_caps"], "Storage ceiling inventory differs")
    for reserved, observed, caps in (("reserved", "observed", plan["components"]),
                                     ("storage_reserved", "storage_observed", plan["storage_caps"])):
        for field in (reserved, observed):
            need(type(ledger[field]) is dict and set(ledger[field]).issubset(caps), "Ledger inventory differs")
            if field == reserved:
                need(set(ledger[field]) == set(caps), "Complete reservation inventory required")
            for key, value in ledger[field].items():
                need(type(value) is int and 0 <= value <= caps[key], "Ledger exceeds literal ceiling")
        for key in caps:
            ceiling = ledger[reserved][key] or caps[key]
            need(ledger[observed].get(key, 0) <= ceiling, "Observed work/storage exceeds reservation")
    need(all(ledger["storage_reserved"][key] >= value
             for key, value in plan["storage_requirements"].items()), "Storage was not fully reserved")
    return plan


def _compare_metrics(exact, numeric):
    need(type(exact) is dict and set(exact) == set(METRICS) and
         all(type(value) is Fraction for value in exact.values()), "Eight exact Fractions required")
    need(exact["value_ip"] == -exact["value_oop"], "Zero-sum identity differs")
    need(exact["oop_best_response_gain"] == exact["oop_best_response_value"] - exact["value_oop"] and
         exact["ip_best_response_gain"] == exact["ip_best_response_value"] - exact["value_ip"],
         "Response gain identity differs")
    need(exact["oop_best_response_gain"] >= 0 and exact["ip_best_response_gain"] >= 0 and
         exact["nash_conv"] == exact["oop_best_response_gain"] + exact["ip_best_response_gain"] and
         exact["exploitability"] * 2 == exact["nash_conv"], "Gap identity differs")
    need(type(numeric) is dict and set(METRICS).issubset(numeric), "Eight numeric metrics required")
    differences = {}
    for key in METRICS:
        value = _finite(numeric[key], "Nonfinite independent metric")
        differences[key] = float(exact[key]) - value
        need(abs(differences[key]) <= 1e-9, "Independent exact/numeric metric differs")
    return differences


def audit_old_baseline(root, game):
    raw = {}
    for name, (size, digest) in OLD_IDENTITIES.items():
        data = _read(root / name)
        need(len(data) == size and sha(data) == digest, "Historical immutable input changed")
        raw[name] = data
    report, payload = (_object(raw[name]) for name in (OLD_REPORT, OLD_POLICY))
    need(report.get("policy_sha256") == OLD_IDENTITIES[OLD_POLICY][1], "Old policy pin differs")
    audited = physical.audit_policy(payload, game)
    exact = audited["metrics"]
    numeric = rules.replay_policy(payload, FIXTURE["oop"], FIXTURE["ip"],
                                  board=FIXTURE["board"], config=FIXTURE["config"])
    _compare_metrics(exact, numeric)
    _equal(report["results"]["exact_metrics_fractions"], jsonable(exact), "Old exact metrics differ")
    need(exact["nash_conv"] > TARGET, "Historical target miss changed")
    return {"report_file": OLD_REPORT, "report_sha256": sha(raw[OLD_REPORT]),
            "policy_file": OLD_POLICY, "policy_sha256": sha(raw[OLD_POLICY]),
            "exact_metrics_fractions": jsonable(exact), "threshold_miss": True,
            "numeric_metrics": numeric, "exact_counters": jsonable(audited["counters"])}


def audit_payload(payload, root=ROOT):
    validate_metadata(payload)
    need(physical.MAX_FRACTION_RESULTS == 1_000_000 and
         physical.MAX_STRUCTURAL_VISITS == 27_351 and
         physical.MAX_FRACTION_BITS == 65_536 and
         classes._MAX_AUDIT_WORK == 100_000 and classes._MAX_AUDIT_DEPTH == 64 and
         classes._MAX_FRACTION_BITS == 65_536, "Original exact audit limits differ")
    game = reference.model()
    reference.validate_model(game)
    audit = classes.audit_policy(payload, classes.build_model(game), chance_grouping="both")
    exact = audit["full_physical_exact_metrics"]
    numeric = rules.replay_policy(payload, FIXTURE["oop"], FIXTURE["ip"],
                                  board=FIXTURE["board"], config=FIXTURE["config"])
    differences = _compare_metrics(exact, numeric)
    for key in METRICS:
        need(abs(payload[key] - numeric[key]) <= 1e-9, "API diagnostic differs from rules")
    for mode in ("scan", "partition"):
        need(audit["generic_class_audits"][mode]["metrics"] == exact, "Class/physical exact metrics differ")
    need(audit["training_calls"] == 0, "Saved audit must never train")
    old = audit_old_baseline(root, game)
    lower, upper = -exact["ip_best_response_value"], exact["oop_best_response_value"]
    need(lower <= exact["value_oop"] <= upper, "Profile outside response interval")
    old_exact = {key: Fraction(value) for key, value in old["exact_metrics_fractions"].items()}
    need(max(lower, -old_exact["ip_best_response_value"]) <=
         min(upper, old_exact["oop_best_response_value"]), "Old/new legal response intervals do not overlap")
    return {"numeric_oracle_metrics": numeric, "exact_numeric_differences": differences,
            "class_audit": jsonable(audit), "exact_metrics_fractions": jsonable(exact),
            "exact_value_interval": {"lower": str(lower), "upper": str(upper)},
            "target_nash_conv_fraction": str(TARGET), "target_met": exact["nash_conv"] <= TARGET,
            "threshold_miss": exact["nash_conv"] > TARGET, "old_baseline": old}


def verify_saved_artifact(*, path, root=None):
    root = ROOT if root is None else Path(root).resolve()
    path = Path(path)
    folder = (root / "benchmarks" / "results").resolve()
    need(path.parent.resolve() == folder and not path.is_symlink(), "Unsafe saved report location")
    report_raw = _read(path)
    report = _object(report_raw)
    need(report.get("schema") == SCHEMA and type(report.get("schema_version")) is int and
         report["schema_version"] == 1, "Unexpected saved experiment schema")
    need(report.get("policy_file") == POLICY_NAME, "Unsafe saved policy filename")
    policy_path = folder / POLICY_NAME
    need(not policy_path.is_symlink(), "Unsafe policy symlink")
    policy_raw = _read(policy_path)
    payload = _object(policy_raw)
    need(type(report.get("policy_bytes")) is int and report["policy_bytes"] == len(policy_raw) and
         report.get("policy_sha256") == sha(policy_raw), "Saved policy byte identity differs")
    before_head = _head(root)
    commit, pins = verify_source_map(root, report)
    for name in ("complete_api_json_seconds", "independent_math_audit_seconds"):
        need(_finite(report.get(name), "Invalid timing observation") >= 0, "Negative timing observation")
    for name in ("python", "platform"):
        need(type(report.get(name)) is str and 0 < len(report[name]) <= 1024, "Invalid host observation")
    observed = audit_payload(payload, root)
    expected = {
        "schema": SCHEMA, "schema_version": 1, "generation_head": commit,
        "training_source_git_commit": commit, "source_sha256": pins,
        "python": report["python"], "platform": report["platform"],
        "fixture_id": FIXTURE["id"], "fixture": FIXTURE, "request": REQUEST,
        "completed_training_calls": 1, "policy_file": POLICY_NAME,
        "policy_sha256": sha(policy_raw), "policy_bytes": len(policy_raw),
        **observed, "complete_api_json_seconds": report["complete_api_json_seconds"],
        "independent_math_audit_seconds": report["independent_math_audit_seconds"], "scope": SCOPE,
        "verification_scope": VERIFICATION_SCOPE,
    }
    _equal(report, expected, "Saved report differs from independent reconstruction")
    need(_head(root) == before_head, "HEAD changed during saved verification")
    need(verify_source_map(root, report) == (commit, pins), "Source changed during saved verification")
    need(_read(path) == report_raw and _read(policy_path) == policy_raw, "Saved bundle changed during verification")
    return expected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=ROOT / "benchmarks" / "results" / REPORT_NAME)
    arguments = parser.parse_args(argv)
    report = verify_saved_artifact(path=arguments.path)
    print(json.dumps({"schema": report["schema"], "target_met": report["target_met"],
                      "exact_nash_conv": report["exact_metrics_fractions"]["nash_conv"],
                      "verification_training_calls": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
