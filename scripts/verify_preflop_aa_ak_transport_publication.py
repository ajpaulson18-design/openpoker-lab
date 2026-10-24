"""Authenticate the saved 84-pair AA/AK transport observation without recounting.

This verifier pins the two-file observation, authenticates the recorded clean
source generation, and freshly replays the saved candidate through the
independent rank-free transport verifier. It performs no board enumeration,
ranking, candidate construction, LP, or training.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from scripts import certify_preflop_aa_ak_transport as audit
from scripts import preflop_aa_ak_transport_validation as independent


ROOT = independent.ROOT
PUBLICATION = ROOT / "benchmarks/results/preflop-aa-ak-transport-v1"
FROZEN_REVISION = "573b615aae77c554e58b71f8ff256699f954a66a"
BASELINE_COMMIT = "ed0deba4a08fe3c9bb25f75eb41e73e2b3b4b251"
MAX_CANDIDATE_BYTES = 65_536
MAX_REPORT_BYTES = 65_536
CANDIDATE_BYTES = 38_864
CANDIDATE_RAW_SHA256 = "9033666cf0fe07c43e2484d8b3df5127b59cbf2f079869a7121415949b03e8fb"
CANDIDATE_ARTIFACT_SHA256 = "7bf39179d001c39d7872b28f1f2584820f344ecd631fa75630cbc99e0ced38c4"
REPORT_BYTES = 10_877
REPORT_RAW_SHA256 = "5a4b191e776e6037a0c142aeab42c85d192deb376134916219826c76d25a2284"
REPORT_ARTIFACT_SHA256 = "6ddb80afae0aeb0be152c4ba76e18e675ac2199396b1777d044544f4cb27f9e4"
SOURCE_PATHS = audit.SOURCE_PATHS
FORBIDDEN = tuple(audit.FORBIDDEN) + tuple(audit.INDEPENDENT_FORBIDDEN)
REPORT_KEYS = {
    "artifact_sha256", "baseline_commit", "benchmark_id", "candidate_artifact_sha256",
    "candidate_attempts", "created_at_utc", "errors", "forbidden_calculation_calls",
    "fresh_saved_file_verification", "independent_attempts", "independent_memory_verification",
    "schema_version", "scope", "source_after", "source_before", "source_unchanged", "status",
}
EXPECTED_SCOPE = "84 physical pair counts and exact priors only; no strategy, convergence, runtime or memory claim"
EXPECTED_ORBITS = [
    {"sb_hand": "AcKc", "bb_hand": "KdKh", "members": 12},
    {"sb_hand": "AdAs", "bb_hand": "KcKd", "members": 24},
    {"sb_hand": "AdAs", "bb_hand": "KcKh", "members": 6},
    {"sb_hand": "AdAs", "bb_hand": "KdKs", "members": 6},
    {"sb_hand": "AdKc", "bb_hand": "KdKh", "members": 24},
    {"sb_hand": "AdKc", "bb_hand": "KhKs", "members": 12},
]


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _typed_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(
            _typed_equal(left[key], value) for key, value in right.items())
    if type(left) is list:
        return len(left) == len(right) and all(
            _typed_equal(a, b) for a, b in zip(left, right))
    return left == right


def _read(path, limit, *, size, sha256):
    path = Path(path)
    _need(not path.is_symlink() and path.is_file(), f"Missing or symlinked file: {path.name}")
    _need(path.stat().st_size <= limit and path.stat().st_size == size,
          f"Saved file size differs or exceeds bound: {path.name}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    _need(len(raw) <= limit and len(raw) == size,
          f"Saved file grew beyond its bound: {path.name}")
    _need(hashlib.sha256(raw).hexdigest() == sha256, f"Pinned raw bytes differ: {path.name}")
    return raw


def _inventory(root):
    root = Path(root)
    _need(not root.is_symlink() and root.is_dir(), "AA/AK publication directory is missing or symlinked")
    _need({entry.name for entry in root.iterdir()} == {"candidate.json", "report.json"},
          "AA/AK publication inventory differs")
    candidate = _read(root / "candidate.json", MAX_CANDIDATE_BYTES,
                      size=CANDIDATE_BYTES, sha256=CANDIDATE_RAW_SHA256)
    report = _read(root / "report.json", MAX_REPORT_BYTES,
                   size=REPORT_BYTES, sha256=REPORT_RAW_SHA256)
    return {"candidate.json": candidate, "report.json": report}


def _source_record(value):
    _need(type(value) is dict and set(value) == {"revision", "source_hashes", "status"},
          "Historical source snapshot schema differs")
    _need(type(value["revision"]) is str and value["revision"] == FROZEN_REVISION
          and type(value["status"]) is list and value["status"] == [],
          "Saved generation is not the pinned clean source revision")
    hashes = value["source_hashes"]
    _need(type(hashes) is dict and set(hashes) == set(SOURCE_PATHS),
          "Historical ten-source inventory differs")
    for relative, row in hashes.items():
        _need(type(row) is dict and set(row) == {"raw_sha256", "lf_sha256"}
              and all(type(row[key]) is str and re.fullmatch(r"[0-9a-f]{64}", row[key])
                      for key in ("raw_sha256", "lf_sha256")),
              f"Malformed historical source hash: {relative}")
    return value


def _current_source_attestation(expected):
    snapshot = audit.snapshot()
    _need(type(snapshot) is dict and set(snapshot) == {"revision", "status", "source_hashes"}
          and type(snapshot["revision"]) is str
          and re.fullmatch(r"[0-9a-f]{40}", snapshot["revision"]) is not None,
          "Current source snapshot schema or revision is malformed")
    _need(type(snapshot["status"]) is list and snapshot["status"] == [],
          "Current checkout must be clean for saved publication authentication")
    hashes = snapshot["source_hashes"]
    _need(type(hashes) is dict and set(hashes) == set(SOURCE_PATHS),
          "Current ten-source inventory differs")
    for relative in SOURCE_PATHS:
        current, historical = hashes[relative], expected["source_hashes"][relative]
        _need(type(current) is dict and set(current) == {"raw_sha256", "lf_sha256"}
              and all(type(current[key]) is str and re.fullmatch(r"[0-9a-f]{64}", current[key])
                      for key in ("raw_sha256", "lf_sha256")),
              f"Malformed current source hash: {relative}")
        _need(current["lf_sha256"] == historical["lf_sha256"],
              f"Current measured source differs from the saved generation: {relative}")
    return snapshot


def _json(raw, label):
    try:
        return independent.io._load_json(raw)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"Invalid strict JSON in {label}") from exc


def _validate_candidate(candidate):
    _need(type(candidate) is dict, "Saved candidate must be a JSON object")
    _need(candidate.get("artifact_sha256") == CANDIDATE_ARTIFACT_SHA256
          and independent.io._artifact(candidate) == CANDIDATE_ARTIFACT_SHA256,
          "Saved candidate canonical artifact digest differs")
    # This is the independent rank-free structural/orbit preflight. The fresh
    # saved-file verification below separately authenticates its source rows.
    independent._preflight(candidate)
    _need(type(candidate.get("schema_version")) is int and candidate["schema_version"] == 1
          and candidate.get("benchmark_id") == "preflop-aa-ak-transport-v1"
          and candidate.get("status") == "candidate-only"
          and type(candidate.get("row_count")) is int and candidate["row_count"] == 84
          and type(candidate.get("total_prior")) is str and candidate["total_prior"] == "1",
          "Saved AA/AK candidate identity, census, or global prior differs")
    _need(type(candidate.get("type_pair_counts")) is dict
          and _typed_equal(candidate["type_pair_counts"], {"AA": 36, "AKs": 12, "AKo": 36}),
          "Saved AA/AK candidate type counts differ")
    return candidate


def _expected_receipt():
    return {
        "status": "transport-authenticated-candidate-only",
        "benchmark_id": "preflop-aa-ak-transport-v1",
        "candidate_artifact_sha256": CANDIDATE_ARTIFACT_SHA256,
        "source_basis_pins": independent.SOURCE_PINS,
        "physical_pair_rows_authenticated": 84,
        "source_classes_authenticated": 6,
        "board_outcomes_per_pair": 1_712_304,
        "represented_boards_informational_only": 143_833_536,
        "type_pair_counts": {"AA": 36, "AKs": 12, "AKo": 36},
        "type_prior_masses": {"AA": "3/7", "AKs": "1/7", "AKo": "3/7"},
        "source_orbit_members": EXPECTED_ORBITS,
        "exact_global_prior_mass": "1",
        "rank_calls": 0,
        "board_enumerations": 0,
        "training_calls": 0,
        "equilibrium_or_policy_claim": False,
        "scope": "authenticated blocker-sensitive source count transport only",
    }


def _validate_receipt(receipt):
    expected = _expected_receipt()
    _need(_typed_equal(receipt, expected), "Independent saved transport receipt differs")


def _timestamp(value):
    _need(type(value) is str and 1 <= len(value) <= 64,
          "Saved observation timestamp is malformed")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Saved observation timestamp is malformed") from exc
    _need(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0,
          "Saved observation timestamp must be timezone-aware UTC")


def _parse_report(raw, candidate):
    report = _json(raw, "report.json")
    _need(type(report) is dict and set(report) == REPORT_KEYS,
          "AA/AK report schema differs")
    _need(type(report["artifact_sha256"]) is str
          and report["artifact_sha256"] == REPORT_ARTIFACT_SHA256
          and independent.io._artifact(report) == REPORT_ARTIFACT_SHA256,
          "AA/AK report canonical artifact digest differs")
    _need(type(report["schema_version"]) is int and report["schema_version"] == 1
          and type(report["benchmark_id"]) is str
          and report["benchmark_id"] == "preflop-aa-ak-transport-audit-v1"
          and type(report["status"]) is str and report["status"] == "transport-verified",
          "AA/AK report identity or status differs")
    _need(type(report["baseline_commit"]) is str and report["baseline_commit"] == BASELINE_COMMIT,
          "AA/AK report is not bound to the merged #226 baseline")
    _timestamp(report["created_at_utc"])
    _need(type(report["errors"]) is list and report["errors"] == [],
          "AA/AK report contains errors")
    for key, expected in (("candidate_attempts", 1), ("independent_attempts", 2)):
        _need(type(report[key]) is int and report[key] == expected,
              f"AA/AK report {key} differs")
    _need(type(report["candidate_artifact_sha256"]) is str
          and report["candidate_artifact_sha256"] == CANDIDATE_ARTIFACT_SHA256
          and report["source_unchanged"] is True and type(report["source_unchanged"]) is bool
          and type(report["scope"]) is str and report["scope"] == EXPECTED_SCOPE,
          "AA/AK report candidate linkage, source status, or scope differs")
    _need(report["candidate_artifact_sha256"] == candidate["artifact_sha256"],
          "AA/AK candidate/report artifact linkage differs")
    before, after = _source_record(report["source_before"]), _source_record(report["source_after"])
    _need(_typed_equal(before, after), "AA/AK generation source snapshots differ")
    calls = report["forbidden_calculation_calls"]
    _need(type(calls) is dict and set(calls) == set(FORBIDDEN)
          and all(type(value) is int and value == 0 for value in calls.values()),
          "AA/AK report must retain exactly sixteen zero forbidden-call counters")
    memory = report["independent_memory_verification"]
    saved = report["fresh_saved_file_verification"]
    _validate_receipt(memory)
    _validate_receipt(saved)
    _need(_typed_equal(memory, saved), "AA/AK memory and saved-file receipts differ")
    return report, before


def verify(directory=None):
    """Authenticate the immutable two-file observation and freshly verify its candidate."""
    root = Path(directory) if directory is not None else PUBLICATION
    raw_files = _inventory(root)
    candidate = _validate_candidate(_json(raw_files["candidate.json"], "candidate.json"))
    report, frozen_source = _parse_report(raw_files["report.json"], candidate)

    current_before = _current_source_attestation(frozen_source)
    _need(audit.published_baseline(BASELINE_COMMIT) == BASELINE_COMMIT,
          "Merged AA/AK baseline ancestry check failed")
    calls = {}
    with audit.no_calculation(calls, independent_phase=True):
        receipt = independent.verify_candidate_report(root / "candidate.json")
    _validate_receipt(receipt)
    _need(_typed_equal(receipt, report["independent_memory_verification"])
          and _typed_equal(receipt, report["fresh_saved_file_verification"]),
          "Fresh independent saved-file verification differs from both recorded receipts")
    _need(set(calls) == set(FORBIDDEN)
          and all(type(value) is int and value == 0 for value in calls.values()),
          "A forbidden calculation was attempted during saved publication authentication")
    current_after = _current_source_attestation(frozen_source)
    _need(_typed_equal(current_before, current_after),
          "Current clean source changed during saved publication authentication")
    final_files = _inventory(root)
    _need(final_files == raw_files, "Saved AA/AK corpus changed during verification")
    final_candidate = _validate_candidate(_json(final_files["candidate.json"], "candidate.json"))
    final_report, final_source = _parse_report(final_files["report.json"], final_candidate)
    _need(_typed_equal(final_report, report) and _typed_equal(final_source, frozen_source),
          "Saved AA/AK report or source links changed during verification")
    return {
        "status": "authenticated-saved-transport-only",
        "benchmark_id": "preflop-aa-ak-transport-v1",
        "candidate_artifact_sha256": CANDIDATE_ARTIFACT_SHA256,
        "report_artifact_sha256": REPORT_ARTIFACT_SHA256,
        "generation_revision": FROZEN_REVISION,
        "baseline_commit": BASELINE_COMMIT,
        "physical_pair_rows_authenticated": 84,
        "source_classes_authenticated": 6,
        "exact_global_prior_mass": "1",
        "rank_calls": 0,
        "board_enumerations": 0,
        "training_calls": 0,
        "equilibrium_or_policy_claim": False,
        "current_source_attestation": current_after,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", default=str(PUBLICATION))
    args = parser.parse_args()
    print(json.dumps(verify(args.directory), sort_keys=True), flush=True)
