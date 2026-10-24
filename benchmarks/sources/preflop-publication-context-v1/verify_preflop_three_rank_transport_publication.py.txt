"""Authenticate a saved three-rank transport observation without recounting.

This verifier checks pinned saved bytes and source receipts, then delegates the
candidate table to the independent rank-free transport verifier. It does not
produce a candidate, pool counts, rank hands, enumerate boards, or train.
"""
import hashlib
import json
from pathlib import Path
import re

from scripts import certify_preflop_three_rank_transport as audit
from scripts import preflop_three_rank_transport_validation as independent

ROOT = Path(__file__).resolve().parents[1]
PUBLICATION = ROOT / "benchmarks/results/preflop-three-rank-transport-v1"
MAX_CANDIDATE_BYTES = 1_048_576
MAX_REPORT_BYTES = 1_048_576
FROZEN_REVISION = "2198f1f23ddb9d1d24c08ec4182afeedb60c28b5"
CANDIDATE_BYTES = 37_639
CANDIDATE_RAW_SHA256 = "fdbd5640a53e5f3e9d5ec2ee0756b1ad5cfa658fc4e4747c373b87d088091e90"
CANDIDATE_ARTIFACT_SHA256 = "fc98072bef74e1570a13db5c876d36226bcec1b3a2f7959c361872feb3abdbb9"
REPORT_BYTES = 8_461
REPORT_RAW_SHA256 = "8a061e42337ea2e7931b9877e966f680f02d407c32f7d6fb58fe07e08a53547a"
REPORT_ARTIFACT_SHA256 = "9d73cbc63bda40a4e51afda03d89af79258a350df4ab42960dbe5e1f7a0f16f9"
SOURCE_PATHS = (
    "scripts/preflop_three_rank_transport.py",
    "scripts/preflop_three_rank_transport_validation.py",
    "scripts/certify_preflop_three_rank_transport.py",
    "tests/test_preflop_three_rank_transport.py",
    "tests/test_preflop_three_rank_transport_validation.py",
    "tests/test_certify_preflop_three_rank_transport.py",
    "docs/preflop-three-rank-transport.md",
    "scripts/verify_preflop_jj_kk_basis_publication.py",
)
FORBIDDEN = tuple(audit.FORBIDDEN) + (
    "scripts.preflop_three_rank_transport.build_candidate",
    "pokerlab.preflop_covered_equity.pool_preflop_equities_by_suit",
    "pokerlab.preflop_covered_equity._ranges",
)
REPORT_KEYS = {
    "artifact_sha256", "benchmark_id", "candidate_artifact_sha256",
    "candidate_attempts", "created_at_utc", "errors", "forbidden_calculation_calls",
    "fresh_saved_file_verification", "independent_attempts",
    "independent_memory_verification", "schema_version", "scope", "source_after",
    "source_before", "source_unchanged", "status",
}
EXPECTED_SCOPE = "108 physical pair counts and exact priors; no strategy, equilibrium, runtime or memory claim"
EXPECTED_SOURCE_PINS = {
    "aa": {"path": "benchmarks/results/preflop-five-basis-v1.json",
           "artifact_sha256": "2ae377e0af6d55491c667d574f41482f2ea6911ba8565ade3b9c8406b54010f7"},
    "qq": {"path": "benchmarks/results/preflop-qq-kk-basis-v1.json",
           "artifact_sha256": "d47fcbdca9cb84275adb8902636d8331bca8b6089e1d62e83cc2160ff09503b8"},
    "jj": {"publication_index_sha256": "9022673f0801fa1481af146f66392b2c7ea4d88c8576946735ecb5ced34bf5e1",
           "report_artifact_sha256": "1f80d95da14890be036c72772f6a88228beff936d05355875384dcc34d6d5156"},
}


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


def _bounded_read(path, limit, *, expected_bytes=None, expected_sha256=None):
    path = Path(path)
    _need(not path.is_symlink() and path.is_file(), f"Missing or symlinked saved file: {path.name}")
    size = path.stat().st_size
    _need(size <= limit and (expected_bytes is None or size == expected_bytes),
          f"Saved file size differs or exceeds bound: {path.name}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    _need(len(raw) <= limit and (expected_bytes is None or len(raw) == expected_bytes),
          f"Saved file changed beyond bound: {path.name}")
    if expected_sha256 is not None:
        _need(hashlib.sha256(raw).hexdigest() == expected_sha256,
              f"Pinned raw saved bytes differ: {path.name}")
    return raw


def _inventory(root):
    _need(not root.is_symlink() and root.is_dir(), "Transport publication directory is missing or symlinked")
    _need({path.name for path in root.iterdir()} == {"candidate.json", "report.json"},
          "Transport publication inventory differs")
    return {
        "candidate.json": _bounded_read(root / "candidate.json", MAX_CANDIDATE_BYTES,
                                        expected_bytes=CANDIDATE_BYTES,
                                        expected_sha256=CANDIDATE_RAW_SHA256),
        "report.json": _bounded_read(root / "report.json", MAX_REPORT_BYTES,
                                     expected_bytes=REPORT_BYTES,
                                     expected_sha256=REPORT_RAW_SHA256),
    }


def _source_record(value):
    _need(type(value) is dict and set(value) == {"revision", "source_hashes", "status"},
          "Transport historical source snapshot schema differs")
    _need(type(value["revision"]) is str and value["revision"] == FROZEN_REVISION,
          "Transport source generation differs")
    _need(type(value["status"]) is list and value["status"] == [],
          "Transport observation was not made from clean source")
    hashes = value["source_hashes"]
    _need(type(hashes) is dict and set(hashes) == set(SOURCE_PATHS),
          "Transport historical source inventory differs")
    for relative, record in hashes.items():
        _need(type(record) is dict and set(record) == {"raw_sha256", "lf_sha256"}
              and all(type(record[key]) is str and len(record[key]) == 64
                      and all(char in "0123456789abcdef" for char in record[key])
                      for key in ("raw_sha256", "lf_sha256")),
              f"Malformed historical source digest: {relative}")
    return value


def _current_source_attestation(expected):
    snap = audit.snapshot()
    _need(type(snap) is dict and type(snap.get("revision")) is str
          and re.fullmatch(r"[0-9a-f]{40}", snap["revision"]) is not None,
          "Current source revision is malformed")
    _need(type(snap.get("status")) is list and snap["status"] == [],
          "Current checkout must be clean for saved publication authentication")
    hashes = snap.get("source_hashes")
    _need(type(hashes) is dict and set(hashes) == set(SOURCE_PATHS),
          "Current eight-file source inventory differs")
    for relative in SOURCE_PATHS:
        row = hashes[relative]
        _need(type(row) is dict and set(row) == {"raw_sha256", "lf_sha256"}
              and row.get("lf_sha256") == expected["source_hashes"][relative]["lf_sha256"],
              f"Current LF source differs from frozen transport source: {relative}")
    return {"revision": snap["revision"], "status": snap["status"], "source_hashes": hashes}


def _validate_receipt(receipt):
    expected_keys = {
        "status", "benchmark_id", "candidate_artifact_sha256", "source_basis_pins",
        "physical_pair_rows_authenticated", "board_outcomes_per_pair",
        "represented_board_count_informational_only", "overlap_census_by_rank",
        "exact_global_prior_mass", "rank_calls", "board_enumerations", "training_calls",
        "equilibrium_or_policy_claim", "scope",
    }
    _need(type(receipt) is dict and set(receipt) == expected_keys,
          "Independent transport receipt fields differ")
    _need(receipt["status"] == "transport-authenticated-candidate-only"
          and receipt["benchmark_id"] == "preflop-three-rank-transport-v1"
          and receipt["candidate_artifact_sha256"] == CANDIDATE_ARTIFACT_SHA256,
          "Independent transport receipt identity differs")
    for name, value in (("physical_pair_rows_authenticated", 108),
                        ("board_outcomes_per_pair", 1_712_304),
                        ("represented_board_count_informational_only", 184_928_832),
                        ("rank_calls", 0), ("board_enumerations", 0), ("training_calls", 0)):
        _need(type(receipt[name]) is int and receipt[name] == value,
              f"Independent transport receipt count differs: {name}")
    _need(type(receipt["equilibrium_or_policy_claim"]) is bool
          and receipt["equilibrium_or_policy_claim"] is False
          and receipt["exact_global_prior_mass"] == "1"
          and receipt["scope"] == "authenticated source-orbit count transport only; no board enumeration or solver claim",
          "Independent transport receipt scope or prior differs")
    expected_overlaps = {rank: {"0": 6, "1": 24, "2": 6} for rank in "AQJ"}
    _need(_typed_equal(receipt["overlap_census_by_rank"], expected_overlaps),
          "Independent transport overlap census differs")
    _need(_typed_equal(receipt["source_basis_pins"], EXPECTED_SOURCE_PINS),
          "Independent transport basis pins differ")


def _parse_and_validate_report(raw):
    report = independent._load_json(raw)
    _need(type(report) is dict and set(report) == REPORT_KEYS,
          "Transport observation report fields differ")
    _need(type(report["artifact_sha256"]) is str
          and report["artifact_sha256"] == REPORT_ARTIFACT_SHA256
          and independent._artifact(report) == REPORT_ARTIFACT_SHA256,
          "Transport observation canonical digest differs")
    _need(type(report["schema_version"]) is int and report["schema_version"] == 1
          and report["benchmark_id"] == "preflop-three-rank-transport-audit-v1"
          and type(report["status"]) is str and report["status"] == "transport-verified",
          "Transport observation identity or status differs")
    _need(type(report["created_at_utc"]) is str and 1 <= len(report["created_at_utc"]) <= 64,
          "Transport observation timestamp is malformed")
    _need(type(report["errors"]) is list and report["errors"] == [],
          "Transport observation contains errors")
    _need(type(report["candidate_attempts"]) is int and report["candidate_attempts"] == 1
          and type(report["independent_attempts"]) is int
          and report["independent_attempts"] == 2,
          "Transport observation attempt counts differ")
    _need(type(report["candidate_artifact_sha256"]) is str
          and report["candidate_artifact_sha256"] == CANDIDATE_ARTIFACT_SHA256
          and type(report["source_unchanged"]) is bool and report["source_unchanged"] is True
          and report["scope"] == EXPECTED_SCOPE,
          "Transport observation candidate linkage or scope differs")
    before = _source_record(report["source_before"])
    after = _source_record(report["source_after"])
    _need(_typed_equal(before, after), "Transport observation source snapshots differ")
    counters = report["forbidden_calculation_calls"]
    _need(type(counters) is dict and set(counters) == set(FORBIDDEN)
          and all(type(value) is int and value == 0 for value in counters.values()),
          "Transport observation forbidden-call receipt differs")
    _validate_receipt(report["independent_memory_verification"])
    _validate_receipt(report["fresh_saved_file_verification"])
    _need(_typed_equal(report["independent_memory_verification"],
                       report["fresh_saved_file_verification"]),
          "Transport memory and fresh-file receipts differ")
    return report, before


def verify(directory=None):
    """Authenticate the two pinned saved files and freshly recheck the table."""
    root = Path(directory) if directory is not None else PUBLICATION
    raw_files = _inventory(root)
    report, frozen_source = _parse_and_validate_report(raw_files["report.json"])
    current_before = _current_source_attestation(frozen_source)
    calls = {}
    with audit.no_calculation(calls, independent_phase=True):
        receipt = independent.verify_candidate_report(root / "candidate.json")
    _validate_receipt(receipt)
    _need(_typed_equal(receipt, report["independent_memory_verification"])
          and _typed_equal(receipt, report["fresh_saved_file_verification"]),
          "Fresh independent verification differs from the saved observation receipts")
    _need(set(calls) == set(FORBIDDEN)
          and all(type(value) is int and value == 0 for value in calls.values()),
          "A forbidden calculation was attempted during publication authentication")
    current_after = _current_source_attestation(frozen_source)
    _need(_typed_equal(current_before, current_after),
          "Current source changed during saved publication authentication")
    final_files = _inventory(root)
    _need(final_files == raw_files,
          "Saved transport publication changed during verification")
    report_again, _ = _parse_and_validate_report(final_files["report.json"])
    _need(_typed_equal(report_again, report),
          "Saved transport report changed during verification")
    return {
        "status": "authenticated-saved-transport-only",
        "benchmark_id": "preflop-three-rank-transport-v1",
        "candidate_artifact_sha256": CANDIDATE_ARTIFACT_SHA256,
        "report_artifact_sha256": REPORT_ARTIFACT_SHA256,
        "source_revision": FROZEN_REVISION,
        "physical_pair_rows_authenticated": 108,
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
