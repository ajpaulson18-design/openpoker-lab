"""Hash-pinned exact-arithmetic audit for the six saved selected-turn policies."""
import argparse
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from scripts.historical_foundation_sources import (BRIDGE_INPUTS, historical_preflop_rank_source_matches)

from pokerlab.cards import expand_range
from scripts import turn_river_validation as validator
from scripts.benchmark_turn_river_independent import CONFIG, ROOT, source_hashes
from scripts.benchmark_turn_selected_accuracy import frozen_case
from scripts.turn_rational_certificate import evaluate_exact


PARENT_REPORT_CANONICAL_SHA256 = "96d53995f45c6f07d43a35ae871fac6ca97c6d9dca6a8de067e8b46e15392b78"
EXPECTED_BASELINE = "182d6b68704fd8f301c722b1c1d35ffd93542374"
EXPECTED_POLICY_HASHES = {
    ("materialized", 1_000): ("two-conditioned-runouts-asymmetric-multisize-materialized-1000.json",
                               "c05a633b62977c3e11ae6afc92bae29dc64029ec9a7772e5b8a18ff22312dc79"),
    ("materialized", 3_000): ("two-conditioned-runouts-asymmetric-multisize-materialized-3000.json",
                               "a3e0d01a75ea42cebb2883897ff695011308a05c4bdc11dab63832fc43bbf2a2"),
    ("materialized", 10_000): ("two-conditioned-runouts-asymmetric-multisize-materialized-10000.json",
                                "831c819e63165b62f43cfc1c075e7d89dccbd632f34fc5bc5858380565ea2b20"),
    ("matrix-free", 1_000): ("two-conditioned-runouts-asymmetric-multisize-matrix-free-1000.json",
                              "9392d017c8ac7c8e1328c9e996282192660c65b97d6dd2e248eed3271054ffec"),
    ("matrix-free", 3_000): ("two-conditioned-runouts-asymmetric-multisize-matrix-free-3000.json",
                              "c72bbdbc112513adcfcf678b78adf1c18aa1e17cfe7f970bf651a9fe98172efc"),
    ("matrix-free", 10_000): ("two-conditioned-runouts-asymmetric-multisize-matrix-free-10000.json",
                               "b2e4565437f5b705d0e1ece325129f8b75ec1f6d7eb1fe6879061a70d3a43f09"),
}
METRIC_FIELDS = (
    "value_oop", "value_ip", "oop_best_response_value",
    "ip_best_response_value", "oop_best_response_gain",
    "ip_best_response_gain", "nash_conv", "exploitability",
)
FLOAT_TOLERANCE = 1e-9


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _pinned_report(path):
    report = json.loads(path.read_text(encoding="utf-8"))
    parent_digest = _sha256(_canonical(report))
    if parent_digest != PARENT_REPORT_CANONICAL_SHA256:
        raise ValueError("Parent accuracy report differs from its pinned canonical digest")
    if report.get("baseline_git_commit") != EXPECTED_BASELINE:
        raise ValueError("Parent accuracy report has the wrong baseline revision")
    if report.get("benchmark_id") != "turn-selected-accuracy-v1":
        raise ValueError("Parent report is not the selected-turn accuracy benchmark")
    if report.get("fixture") != frozen_case():
        raise ValueError("Parent report fixture differs from the frozen input model")
    expected_rows = set(EXPECTED_POLICY_HASHES)
    by_identity = {}
    for row in report.get("results", ()):
        identity = (row.get("backend"), row.get("iterations_completed"))
        if identity in by_identity:
            raise ValueError("Parent report contains duplicate profile identity")
        by_identity[identity] = row
    if set(by_identity) != expected_rows:
        raise ValueError("Parent report does not contain exactly the six approved profiles")
    for identity, (name, policy_digest) in EXPECTED_POLICY_HASHES.items():
        row = by_identity[identity]
        if (row.get("policy_file") != name or row.get("policy_sha256") != policy_digest or
                row.get("algorithm") != "cfrplus" or
                row.get("iterations_requested") != identity[1] or
                row.get("configured_solver_target_exploitability") is not None):
            raise ValueError("Parent report row differs from the pinned profile identity")
    return report, by_identity, parent_digest


def _source_fingerprints():
    values = source_hashes()
    for name in ("benchmark_turn_selected_accuracy.py",
                 "turn_rational_certificate.py", "audit_turn_rational_certificate.py"):
        path = ROOT / "scripts" / name
        values[path.relative_to(ROOT).as_posix()] = _sha256(path.read_bytes())
    for path in BRIDGE_INPUTS:
        values[path.relative_to(ROOT).as_posix()] = _sha256(path.read_bytes())
    return dict(sorted(values.items()))


def _source_hash_candidates(path):
    raw = path.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    return {_sha256(raw), _sha256(lf), _sha256(crlf)}


def _source_fingerprint_matches_report(report_hashes):
    """Match only exact-model dependencies, allowing CRLF/LF conversion.

    The parent report inventories the whole solver checkout. Historical model
    identity depends on the independent card/rule/rank helpers and frozen
    fixture inputs; unrelated solver files remain covered by this audit's
    strict current-run before/after fingerprints instead of being frozen forever.
    """
    current_paths = [ROOT / "pokerlab" / "cards.py"]
    current_paths += [ROOT / "scripts" / name for name in (
        "turn_river_validation.py", "preflop_validation.py",
        "benchmark_turn_river_independent.py", "benchmark_turn_selected_accuracy.py")]
    current_paths.append(CONFIG)
    actual = {path.relative_to(ROOT).as_posix(): _source_hash_candidates(path)
              for path in current_paths}
    archived = {str(name).replace("\\", "/"): digest
                for name, digest in report_hashes.items()}
    return all(name in archived and (archived[name] in candidates or
               historical_preflop_rank_source_matches(ROOT / name, archived[name]))
               for name, candidates in actual.items())


def _independent_model(result, case):
    board = validator.cards(case["board"])
    config = validator._config(case["config"], "config")
    river_config = validator._config(case["river_config"], "river_config")
    ranges = (expand_range(case["oop"], board), expand_range(case["ip"], board))
    if any(weight <= 0 for side in ranges for weight in side.values()):
        ranges = tuple({hand: weight for hand, weight in side.items() if weight > 0}
                       for side in ranges)
    worlds, selected = validator._worlds(board, ranges, case["runouts"])
    root = validator._public_tree(board, config, river_config, selected, worlds)
    nodes = validator._collect_nodes(root)
    policies = validator._validate_policy(
        result, root, nodes, worlds, board, selected,
        runouts_were_omitted=False,
    )
    return board, config, river_config, worlds, root, policies


def _float_metrics(exact_metrics):
    return {name: float(value) for name, value in exact_metrics.items()}


def audit(report_path, policies_dir):
    report, report_rows, parent_digest = _pinned_report(report_path)
    case = report["fixture"]
    # Check current benchmark inputs against the exact source fingerprint
    # archived by the parent report before any expensive independent replay.
    if not _source_fingerprint_matches_report(report.get("source_sha256", {})):
        raise ValueError("Parent report's original source fingerprint no longer matches checkout")

    source_before = _source_fingerprints()
    rows = []
    for identity in sorted(EXPECTED_POLICY_HASHES,
                           key=lambda item: (item[0], item[1])):
        filename, expected_hash = EXPECTED_POLICY_HASHES[identity]
        path = policies_dir / filename
        payload = path.read_bytes()
        raw_hash = _sha256(payload)
        if raw_hash != expected_hash:
            raise ValueError("Saved policy bytes differ from the pinned approved policy")
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise ValueError("Saved policy must be a complete result object")
        original_bytes = _canonical(result)

        # Mandatory unchanged floating replay and serialized-diagnostic comparison.
        float_oracle = validator.replay_policy(
            result, case["oop"], case["ip"], board=case["board"],
            config=case["config"], river_config=case["river_config"],
            runouts=case["runouts"],
        )
        serialized_deltas = validator.compare_result(
            result, float_oracle, tolerance=FLOAT_TOLERANCE)

        board, config, river_config, worlds, root, policies = _independent_model(result, case)
        exact = evaluate_exact(root, worlds, policies, config.pot, result=result)
        exact_floats = _float_metrics(exact["metrics"])
        exact_deltas = {name: exact_floats[name] - float(float_oracle[name])
                        for name in METRIC_FIELDS}
        if any(abs(delta) > FLOAT_TOLERANCE for delta in exact_deltas.values()):
            raise ValueError("Exact normalized-profile metrics differ from floating replay")
        if _canonical(result) != original_bytes:
            raise RuntimeError("Exact audit mutated the saved profile input")

        parent_row = report_rows[identity]
        exact_target = exact["threshold_met"]
        if exact_target is not parent_row["benchmark_threshold_met"]:
            raise ValueError("Exact normalized-profile threshold decision changed")
        if exact["worlds"] != 8 or exact["tree_nodes"] != 188:
            raise ValueError("Whitelisted selected-turn model dimensions changed")
        normalized_bytes = _canonical(exact["normalized_policy_rows"])
        rows.append({
            "scenario": case["id"], "backend": identity[0],
            "iterations": identity[1], "policy_file": filename,
            "raw_policy_sha256": raw_hash,
            "normalized_policy_sha256": _sha256(normalized_bytes),
            "normalized_policy_scope": "exact row-normalized probabilities from the serialized binary64 policy",
            "normalization_ledger": exact["normalization_ledger"],
            "maximum_row_adjustment_fraction": str(exact["max_row_adjustment"]),
            "parent_report_row_nash_conv": parent_row["metrics"]["nash_conv"],
            "serialized_vs_float_replay_deltas": serialized_deltas,
            "exact_metrics": {name: str(value) for name, value in exact["metrics"].items()},
            "lower_value_bound_fraction": str(exact["lower_value_bound"]),
            "upper_value_bound_fraction": str(exact["upper_value_bound"]),
            "exact_float_metrics": exact_floats,
            "exact_vs_float_replay_deltas": exact_deltas,
            "exact_nash_conv_threshold_fraction": "1/1000",
            "exact_nash_conv_threshold_met": exact_target,
            "verified_worlds": len(worlds),
            "verified_public_tree_nodes": exact["tree_nodes"],
            "verified_tree_depth": exact["tree_depth"],
            "work": exact["work"], "work_by_kind": exact["work_by_kind"],
            "maximum_fraction_bits": exact["maximum_fraction_bits"],
            "resource_limits": {
                "maximum_work": exact["work_limit"],
                "maximum_depth": exact["depth_limit"],
                "maximum_fraction_bits": exact["fraction_bit_limit"],
            },
        })

    source_after = _source_fingerprints()
    if source_after != source_before:
        raise RuntimeError("Source files changed during rational audit")
    if _sha256(_canonical(json.loads(report_path.read_text(encoding="utf-8")))) != parent_digest:
        raise RuntimeError("Pinned parent report changed during rational audit")
    for identity, (filename, expected_hash) in EXPECTED_POLICY_HASHES.items():
        if _sha256((policies_dir / filename).read_bytes()) != expected_hash:
            raise RuntimeError("Pinned policy bytes changed during rational audit")
    return {
        "schema_version": 1,
        "certificate_id": "turn-rational-certificate-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "python": platform.python_version(),
        "parent_report_canonical_sha256": parent_digest,
        "floating_replay_tolerance_chips": FLOAT_TOLERANCE,
        "scope": "Six pinned complete policies on one fixed two-runout selected-turn model; exact arithmetic audits the unchanged independent numeric model and separately row-normalized profiles.",
        "limitations": "The interval bounds the game value for each exactly normalized supplied profile in this configured binary64-terminal model. It is not a raw-float-profile certificate, equilibrium computation, or unrestricted Hold'em claim.",
        "source_sha256": source_after,
        "results": rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "benchmarks" / "results" /
                        "turn-selected-accuracy-v1.json")
    parser.add_argument("--policies-dir", type=Path, default=ROOT / "benchmarks" / "results" /
                        "turn-selected-accuracy-policies-v1")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks" / "results" /
                        "turn-rational-certificate-v1.json")
    args = parser.parse_args(argv)
    certificate = audit(args.report, args.policies_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(certificate, indent=2, sort_keys=True, allow_nan=False) +
               "\n").encode("utf-8")
    args.output.write_bytes(payload)
    print("Verified exact rational interval for", len(certificate["results"]), "profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
