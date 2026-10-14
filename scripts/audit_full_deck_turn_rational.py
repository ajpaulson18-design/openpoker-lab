"""Pinned exact-rational audit of six saved full-deck turn policies.

This development auditor first requires the unchanged floating numeric replay,
then evaluates exactly row-normalized policies with the bounded partitioned
chance scan. It is not a solver or a raw-binary64 interval proof.
"""
import argparse
import hashlib
import json
import math
import platform
import subprocess
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

from pokerlab.cards import expand_range
from scripts import turn_river_validation as validator
from scripts.benchmark_full_deck_turn_accuracy import (
    EXPECTED_CANDIDATE_RUNOUTS, EXPECTED_INFORMATION_SETS,
    EXPECTED_PAIRS, EXPECTED_PUBLIC_DECISION_NODES, EXPECTED_PUBLIC_STATES,
    EXPECTED_REACHABLE_RUNOUTS, EXPECTED_WORLDS, FLOAT_TOLERANCE,
    ROOT, _full_deck_candidates, _replay, frozen_case, validate_profile_metadata,
)
from scripts.benchmark_turn_river_independent import CONFIG, source_hashes
from scripts.turn_rational_certificate import (
    MAX_EXACT_DEPTH, MAX_EXACT_WORK, MAX_FRACTION_BITS, evaluate_exact,
)


PARENT_REPORT = ROOT / "benchmarks" / "results" / "full-deck-turn-accuracy-v1.json"
POLICY_DIRECTORY = ROOT / "benchmarks" / "results" / "full-deck-turn-accuracy-policies-v1"
OUTPUT = ROOT / "benchmarks" / "results" / "full-deck-turn-rational-certificate-v1.json"
PARENT_REPORT_CANONICAL_SHA256 = (
    "aef2b520593b68b6717adfe677fb5a9c87a362df8ae61816a53d1c930c412b63"
)
EXPECTED_BASELINE = "825ae45fcf8b9b858be8b4dd422b1645f11e7cbb"
EXPECTED_CASE_ID = "full44-blocked-runouts"
METRIC_FIELDS = (
    "value_oop", "value_ip", "oop_best_response_value",
    "ip_best_response_value", "oop_best_response_gain",
    "ip_best_response_gain", "nash_conv", "exploitability",
)
EXPECTED_POLICIES = {
    ("materialized", 1_000): (
        "full44-blocked-runouts-materialized-1000.json",
        "096cad1c3f1895da3be46f96df35f15c351f32485f42dbb291ac16240d3e4ece",
    ),
    ("materialized", 1_500): (
        "full44-blocked-runouts-materialized-1500.json",
        "1b936605ef947900336c171d775694ac9526fce3cd07c4a3ccfcaf50d32220e8",
    ),
    ("materialized", 3_000): (
        "full44-blocked-runouts-materialized-3000.json",
        "c925678035c505073110362ed5cf97ed60d8255cb63d56d14f5cf7b270624302",
    ),
    ("matrix-free", 1_000): (
        "full44-blocked-runouts-matrix-free-1000.json",
        "9da96f3480a41a02cf67141d5f25e41d2b3c43b58f48173b075d9c8d0c19c4d3",
    ),
    ("matrix-free", 1_500): (
        "full44-blocked-runouts-matrix-free-1500.json",
        "f2385c0ffbbaa09ae78e0c45925860882001c0e63421aec501d2b9fbe1c12a09",
    ),
    ("matrix-free", 3_000): (
        "full44-blocked-runouts-matrix-free-3000.json",
        "1ba44c39cec6fa313c5816baf9c02f40ef028854654d66fc1b5d77d7f8cc79e1",
    ),
}

# Historical source identity is limited to dependencies of the independent
# numeric model and frozen fixture; unrelated solver changes are covered by
# strict per-audit before/after fingerprints instead.
MODEL_SOURCE_PATHS = (
    "pokerlab/cards.py", "pokerlab/river_config.py",
    "scripts/turn_river_validation.py", "scripts/preflop_validation.py",
    "scripts/benchmark_turn_river_independent.py",
    "scripts/benchmark_full_deck_turn_accuracy.py",
    "benchmarks/turn-river-quality-v1.json",
)


def _sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _pretty_lf(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) +
            "\n").encode("utf-8")


def _source_hash_candidates(path):
    raw = path.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    return {_sha256(raw), _sha256(lf), _sha256(crlf)}


def _source_fingerprint_matches_report(report_hashes):
    archived = {str(name).replace("\\", "/"): digest
                for name, digest in report_hashes.items()}
    return all(
        path_string in archived and
        archived[path_string] in _source_hash_candidates(ROOT / Path(path_string))
        for path_string in MODEL_SOURCE_PATHS
    )


def _source_fingerprints():
    values = source_hashes()
    paths = [
        Path(__file__).resolve(),
        Path(__file__).with_name("turn_rational_certificate.py").resolve(),
        ROOT / "tests" / "test_turn_rational_partition.py",
        ROOT / "tests" / "test_audit_full_deck_turn_rational.py",
        ROOT / "tests" / "test_turn_rational_partition_review.py",
        PARENT_REPORT,
        ROOT / "benchmarks" / "results" / ".gitattributes",
    ]
    paths.extend(POLICY_DIRECTORY / filename for filename, _ in
                 EXPECTED_POLICIES.values())
    for path in paths:
        if not path.is_file():
            raise ValueError("A pinned source or policy file is missing: " + str(path))
        values[path.relative_to(ROOT).as_posix()] = _sha256(path.read_bytes())
    return dict(sorted(values.items()))


def _pinned_parent(report_path):
    raw = report_path.read_bytes()
    report = json.loads(raw.decode("utf-8"))
    digest = _sha256(_canonical(report))
    if digest != PARENT_REPORT_CANONICAL_SHA256:
        raise ValueError("Full-deck parent report differs from its pinned canonical digest")
    if report.get("baseline_git_commit") != EXPECTED_BASELINE:
        raise ValueError("Full-deck parent report has the wrong baseline revision")
    if report.get("benchmark_id") != "full-deck-turn-accuracy-v1":
        raise ValueError("Parent report is not the frozen full-deck turn benchmark")
    case = frozen_case()
    if report.get("fixture") != case:
        raise ValueError("Parent report fixture differs from the frozen full-deck input")
    rows = report.get("results")
    if type(rows) is not list or len(rows) != len(EXPECTED_POLICIES):
        raise ValueError("Parent report must contain exactly six policy identities")
    by_identity = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Parent report result rows must be objects")
        identity = (row.get("backend"), row.get("iterations_completed"))
        if identity in by_identity:
            raise ValueError("Parent report contains duplicate policy identities")
        if identity not in EXPECTED_POLICIES:
            raise ValueError("Parent report contains an unpinned policy identity")
        filename, digest_expected = EXPECTED_POLICIES[identity]
        if (row.get("scenario") != EXPECTED_CASE_ID or
                row.get("algorithm") != "cfrplus" or
                type(row.get("iterations_requested")) is not int or
                row.get("iterations_requested") != identity[1] or
                row.get("configured_solver_target_exploitability") is not None or
                row.get("policy_file") != filename or
                row.get("policy_sha256") != digest_expected or
                type(row.get("benchmark_threshold_met")) is not bool):
            raise ValueError("Parent report row metadata differs from its pinned identity")
        metrics = row.get("metrics")
        if (not isinstance(metrics, dict) or set(metrics) != set(METRIC_FIELDS) or
                any(isinstance(metrics[name], bool) or
                    type(metrics[name]) not in (int, float) or
                    not math.isfinite(float(metrics[name]))
                    for name in METRIC_FIELDS)):
            raise ValueError("Parent report row must contain all eight finite metrics")
        by_identity[identity] = row
    if set(by_identity) != set(EXPECTED_POLICIES):
        raise ValueError("Parent report policy identity set is incomplete")
    return report, by_identity, digest, case


def _pinned_policy(identity, policies_dir):
    filename, expected_hash = EXPECTED_POLICIES[identity]
    path = policies_dir / filename
    raw = path.read_bytes()
    digest = _sha256(raw)
    if digest != expected_hash:
        raise ValueError("Saved policy bytes differ from the pinned full-deck policy")
    result = json.loads(raw.decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Saved full-deck policy must be a complete result object")
    if (result.get("iterations") != identity[1] or
            result.get("algorithm") != "cfrplus"):
        raise ValueError("Pinned policy has unexpected requested solver metadata")
    return path, raw, result, digest


def _independent_model(result, case):
    board = validator.cards(case["board"])
    config = validator._config(case["config"], "config")
    river_config = validator._config(case["river_config"], "river_config")
    ranges = (expand_range(case["oop"], board), expand_range(case["ip"], board))
    if any(weight <= 0 for side in ranges for weight in side.values()):
        ranges = tuple({hand: weight for hand, weight in side.items() if weight > 0}
                       for side in ranges)
    worlds, selected = validator._worlds(board, ranges, None)
    root = validator._public_tree(board, config, river_config, selected, worlds)
    nodes = validator._collect_nodes(root)
    policies = validator._validate_policy(
        result, root, nodes, worlds, board, selected,
        runouts_were_omitted=True,
    )
    return board, config, river_config, worlds, selected, root, nodes, policies


def _validate_independent_counts(result, oracle, worlds, selected, nodes, policies):
    if (len(worlds) != EXPECTED_WORLDS or
            oracle["worlds"] != EXPECTED_WORLDS or
            oracle["compatible_pair_count"] != EXPECTED_PAIRS or
            oracle["checked_information_sets"] != EXPECTED_INFORMATION_SETS or
            oracle["public_node_count"] != EXPECTED_PUBLIC_DECISION_NODES or
            len(selected) != EXPECTED_CANDIDATE_RUNOUTS or
            len(result["reachable_runouts"]) != EXPECTED_REACHABLE_RUNOUTS or
            len(policies) != EXPECTED_INFORMATION_SETS):
        raise ValueError("Independent full-deck world/tree/policy dimensions changed")
    pair_counts = Counter((world["hands"][0], world["hands"][1]) for world in worlds)
    if len(pair_counts) != EXPECTED_PAIRS or set(pair_counts.values()) != {44}:
        raise ValueError("Each compatible private pair must have exactly 44 river worlds")
    return pair_counts


def _normalized_policy_digest(exact):
    return _sha256(_canonical(exact["normalized_policy_rows"]))


def _run_profile(identity, case, report_row, policies_dir):
    policy_path, raw, result, raw_hash = _pinned_policy(identity, policies_dir)
    original_policy = _canonical(result)
    validate_profile_metadata(result, case, identity[0], identity[1])
    float_oracle = _replay(result, case)
    serialized_deltas = validator.compare_result(
        result, float_oracle, tolerance=FLOAT_TOLERANCE)
    if (set(serialized_deltas) != set(METRIC_FIELDS) or
            any(abs(float(value)) > FLOAT_TOLERANCE
                for value in serialized_deltas.values())):
        raise ValueError("Pinned full-deck policy fails all-eight-metric floating replay")

    board, config, river_config, worlds, selected, root, nodes, policies = (
        _independent_model(result, case))
    pair_counts = _validate_independent_counts(
        result, float_oracle, worlds, selected, nodes, policies)
    exact = evaluate_exact(root, worlds, policies, config.pot, result=result,
                           chance_grouping="partition")
    if (exact["chance_grouping"] != "partition" or
            exact["work"] > MAX_EXACT_WORK or
            exact["tree_depth"] > MAX_EXACT_DEPTH or
            exact["maximum_fraction_bits"] > MAX_FRACTION_BITS):
        raise ValueError("Partitioned exact replay exceeded a fixed certificate cap")
    exact_floats = {name: float(value) for name, value in exact["metrics"].items()}
    exact_deltas = {name: exact_floats[name] - float(float_oracle[name])
                    for name in METRIC_FIELDS}
    if (set(exact_deltas) != set(METRIC_FIELDS) or
            any(abs(value) > FLOAT_TOLERANCE for value in exact_deltas.values())):
        raise ValueError("Partitioned exact metrics differ from independent floating replay")
    if _canonical(result) != original_policy:
        raise RuntimeError("Exact audit mutated the pinned serialized policy")

    parent_meet = report_row["benchmark_threshold_met"]
    if type(parent_meet) is not bool or exact["threshold_met"] != parent_meet:
        raise ValueError("Exact full-deck threshold decision differs from parent report")
    normalized_hash = _normalized_policy_digest(exact)
    ledger_hash = _sha256(_canonical(exact["normalization_ledger"]))
    return {
        "scenario": EXPECTED_CASE_ID,
        "backend": identity[0],
        "iterations": identity[1],
        "policy_file": policy_path.name,
        "raw_policy_sha256": raw_hash,
        "normalized_policy_sha256": normalized_hash,
        "normalization_ledger_sha256": ledger_hash,
        "normalized_policy_scope": "exact row-normalized probabilities from the serialized binary64 policy",
        "normalization_ledger": exact["normalization_ledger"],
        "maximum_row_adjustment_fraction": str(exact["max_row_adjustment"]),
        "parent_report_nash_conv": report_row["metrics"]["nash_conv"],
        "serialized_vs_float_replay_deltas": serialized_deltas,
        "exact_metrics": {name: str(value) for name, value in exact["metrics"].items()},
        "lower_value_bound_fraction": str(exact["lower_value_bound"]),
        "upper_value_bound_fraction": str(exact["upper_value_bound"]),
        "exact_float_metrics": exact_floats,
        "exact_vs_float_replay_deltas": exact_deltas,
        "exact_nash_conv_threshold_fraction": "1/1000",
        "exact_nash_conv_threshold_met": exact["threshold_met"],
        "verified_worlds": len(worlds),
        "verified_compatible_pairs": len(pair_counts),
        "worlds_per_compatible_pair": 44,
        "candidate_runout_count": len(selected),
        "reachable_runout_count": len(result["reachable_runouts"]),
        "verified_information_sets": len(policies),
        "independent_public_decision_nodes": len(nodes),
        "exact_tree_nodes": exact["tree_nodes"],
        "verified_tree_depth": exact["tree_depth"],
        "work": exact["work"],
        "work_by_kind": exact["work_by_kind"],
        "maximum_fraction_bits": exact["maximum_fraction_bits"],
        "resource_limits": {
            "maximum_work": exact["work_limit"],
            "maximum_depth": exact["depth_limit"],
            "maximum_fraction_bits": exact["fraction_bit_limit"],
        },
        "chance_grouping": exact["chance_grouping"],
        "partition_work_model": "For each BR chance group reserve 2*branch_count + 3*group_entries before allocation/iteration; this is modeled bookkeeping, not CPU or memory.",
    }


def _verify_fraction_row(row):
    metrics = {name: Fraction(row["exact_metrics"][name])
               for name in METRIC_FIELDS}
    lower = Fraction(row["lower_value_bound_fraction"])
    upper = Fraction(row["upper_value_bound_fraction"])
    if not lower <= metrics["value_oop"] <= upper:
        raise ValueError("Saved exact interval does not contain the saved profile value")
    expected = {
        "value_ip": -metrics["value_oop"],
        "oop_best_response_value": upper,
        "ip_best_response_value": -lower,
        "oop_best_response_gain": upper - metrics["value_oop"],
        "ip_best_response_gain": metrics["value_oop"] - lower,
        "nash_conv": upper - lower,
        "exploitability": (upper - lower) / 2,
    }
    if any(metrics[name] != value for name, value in expected.items()):
        raise ValueError("Saved exact metric fractions violate the interval identities")
    threshold = (upper - lower) <= Fraction(1, 1_000)
    if row["exact_nash_conv_threshold_met"] is not threshold:
        raise ValueError("Saved exact threshold decision does not match rational width")
    max_adjustment = Fraction(0)
    for ledger_row in row["normalization_ledger"]:
        inputs = []
        normalized = []
        for action in ledger_row["actions"]:
            before = Fraction(action["input_fraction"])
            after = Fraction(action["normalized_fraction"])
            delta = Fraction(action["adjustment_fraction"])
            if after - before != delta:
                raise ValueError("Saved normalization ledger adjustment is inconsistent")
            inputs.append(before)
            normalized.append(after)
            max_adjustment = max(max_adjustment, abs(delta))
        if (not inputs or sum(inputs, Fraction(0)) !=
                Fraction(ledger_row["input_row_sum_fraction"]) or
                sum(normalized, Fraction(0)) != 1):
            raise ValueError("Saved normalization ledger row mass is inconsistent")
    if max_adjustment != Fraction(row["maximum_row_adjustment_fraction"]):
        raise ValueError("Saved normalization maximum does not match its ledger")
    if _sha256(_canonical(row["normalization_ledger"])) != row[
            "normalization_ledger_sha256"]:
        raise ValueError("Saved normalization ledger hash does not match its contents")


def _verify_saved_row_matches_recomputation(row, recomputed):
    """Reject internally consistent but stale or altered saved certificates."""
    if _canonical(row) != _canonical(recomputed):
        raise ValueError(
            "Saved exact row differs from fresh replay and exact recomputation")


def audit(report_path=PARENT_REPORT, policies_dir=POLICY_DIRECTORY):
    parent, report_rows, parent_digest, case = _pinned_parent(report_path)
    if not _source_fingerprint_matches_report(parent.get("source_sha256", {})):
        raise ValueError("Pinned full-deck report's independent-model source identity changed")
    source_before = _source_fingerprints()
    rows = []
    for identity in sorted(EXPECTED_POLICIES, key=lambda key: (key[0], key[1])):
        row = _run_profile(identity, case, report_rows[identity], policies_dir)
        rows.append(row)
        print(identity[0], identity[1],
              f"exact_nash_conv={float(Fraction(row['exact_metrics']['nash_conv'])):.12g}",
              f"work={row['work']}/{MAX_EXACT_WORK}", flush=True)

    lowers = [Fraction(row["lower_value_bound_fraction"]) for row in rows]
    uppers = [Fraction(row["upper_value_bound_fraction"]) for row in rows]
    common_lower, common_upper = max(lowers), min(uppers)
    if common_lower > common_upper:
        raise ValueError("The six same-game exact legal-response intervals do not intersect")
    source_after = _source_fingerprints()
    if source_after != source_before:
        raise RuntimeError("Sources, parent report or pinned policies changed during exact audit")
    if _sha256(_canonical(json.loads(report_path.read_text(encoding="utf-8")))) != parent_digest:
        raise RuntimeError("Pinned full-deck parent report changed during exact audit")
    for identity, (filename, expected_hash) in EXPECTED_POLICIES.items():
        if _sha256((policies_dir / filename).read_bytes()) != expected_hash:
            raise RuntimeError("Pinned full-deck policy changed during exact audit")
    return {
        "schema_version": 1,
        "certificate_id": "full-deck-turn-rational-certificate-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "python": platform.python_version(),
        "parent_report_canonical_sha256": parent_digest,
        "floating_replay_tolerance_chips": FLOAT_TOLERANCE,
        "scope": "Six pinned complete full-deck turn policies; exact arithmetic audits the unchanged independent numeric model and separately row-normalized strategies.",
        "limitations": "Exact bounds apply to normalized serialized policies in the configured binary64-terminal model. This is not a raw-float interval proof, a new equilibrium solve, or an unrestricted Hold'em claim.",
        "chance_grouping": "stable-ordered-per-public-river-partition-v1",
        "source_sha256": source_after,
        "common_game_value_interval_intersection": {
            "lower_fraction": str(common_lower),
            "upper_fraction": str(common_upper),
        },
        "results": rows,
    }


def _verify_saved_artifact(report_path, expected, policies_dir=POLICY_DIRECTORY):
    raw = report_path.read_bytes()
    if b"\r" in raw:
        raise ValueError("Exact certificate artifact must use LF bytes")
    loaded = json.loads(raw.decode("utf-8"))
    if _canonical(loaded) != _canonical(expected):
        raise ValueError("Reloaded exact certificate differs from the produced artifact")
    parent, report_rows, parent_digest, case = _pinned_parent(PARENT_REPORT)
    if loaded.get("parent_report_canonical_sha256") != parent_digest:
        raise ValueError("Saved certificate lost its pinned parent identity")
    for row in loaded.get("results", []):
        _verify_fraction_row(row)
        identity = (row["backend"], row["iterations"])
        if identity not in report_rows:
            raise ValueError("Saved exact artifact contains an unpinned policy identity")
        recomputed = _run_profile(identity, case, report_rows[identity], policies_dir)
        _verify_saved_row_matches_recomputation(row, recomputed)
    if len(loaded.get("results", [])) != len(EXPECTED_POLICIES):
        raise ValueError("Saved exact artifact is missing pinned policy rows")
    if _source_fingerprints() != loaded.get("source_sha256"):
        raise RuntimeError("Source fingerprints changed during saved-artifact recheck")
    return loaded


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=PARENT_REPORT)
    parser.add_argument("--policies-dir", type=Path, default=POLICY_DIRECTORY)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    certificate = audit(args.report, args.policies_dir)
    payload = _pretty_lf(certificate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    _verify_saved_artifact(args.output, certificate, args.policies_dir)
    print("Verified exact rational full-deck certificate for",
          len(certificate["results"]), "profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
