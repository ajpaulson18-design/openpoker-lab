"""Certify one finite three-rank candidate against independent exact responses.

This command performs one candidate LP build, saves its complete report, then
audits both the in-memory and saved policies with the independent pure-response
module. It makes no training, ranking, or board-enumeration claim.
"""
import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import time
from unittest.mock import patch

from scripts import preflop_three_rank_sequence_candidate as candidate
from scripts import preflop_three_rank_pure_response as independent
from scripts import certify_preflop_three_rank_transport as transport_run

ROOT = Path(__file__).resolve().parents[1]
MAX_CANDIDATE_BYTES = 512 * 1024
MAX_REPORT_BYTES = 2 * 1024 * 1024
EXTRA_SOURCES = (
    "scripts/preflop_three_rank_sequence_candidate.py",
    "scripts/preflop_three_rank_pure_response.py",
    "scripts/certify_preflop_three_rank_sequence.py",
    "tests/test_preflop_three_rank_sequence_candidate.py",
    "tests/test_preflop_three_rank_pure_response.py",
    "tests/test_certify_preflop_three_rank_sequence.py",
    "docs/preflop-three-rank-exact-witness.md",
)
BASELINE_SHA256 = "8bc482c3867f3e53e1bc6fc03723ae569f5401a66aeb5e1b86cf6bb12d5c9b25"


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _snapshot():
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, check=True, timeout=30).stdout.decode().strip()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                            capture_output=True, check=True, timeout=30).stdout.decode().splitlines()
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("Git revision is not a full lowercase SHA")
    hashes = {}
    for relative in (*transport_run.SOURCE_PATHS, *EXTRA_SOURCES):
        path = ROOT / relative
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_048_576:
            raise ValueError(f"Missing, symlinked, or oversized witness source: {relative}")
        with path.open("rb") as stream:
            raw = stream.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError(f"Witness source grew beyond its bound: {relative}")
        hashes[relative] = {"raw_sha256": _digest(raw),
                            "lf_sha256": _digest(raw.replace(b"\r\n", b"\n"))}
    return {"revision": revision, "status": status, "source_hashes": hashes}


def _validate_admission(request, baseline_commit):
    candidate._validate_request(request)
    if type(baseline_commit) is not str or re.fullmatch(r"[0-9a-f]{40}", baseline_commit) is None:
        raise ValueError("Baseline commit must be a full lowercase 40-character Git SHA")
    if _digest(_canonical(request)) != BASELINE_SHA256:
        raise ValueError("Candidate request differs from the fixed reviewed request")


def _baseline_is_ancestor(commit):
    proc = subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"],
                          cwd=ROOT, capture_output=True, check=False, timeout=30)
    if proc.returncode != 0:
        raise ValueError("Requested baseline commit is not an ancestor of HEAD")


def _save_once(path, raw, limit):
    if len(raw) > limit:
        raise ValueError("Witness output exceeds its admitted size limit")
    with path.open("xb") as stream:
        stream.write(raw)


@contextmanager
def _independent_only_guard(calls):
    """Keep candidate building, tree construction, and LP unavailable on replay."""
    targets = ("scripts.preflop_three_rank_sequence_candidate.build_candidate",
               "scripts.preflop_checkdown_validation._build",
               "scripts.river_sequence_form._solve_lp")
    with ExitStack() as stack:
        for target in targets:
            calls.setdefault(target, 0)
            def fail(*_args, _target=target, **_kwargs):
                calls[_target] += 1
                raise AssertionError("Forbidden candidate construction during independent replay: " + _target)
            stack.enter_context(patch(target, side_effect=fail))
        yield


def _report_sha(report):
    unsigned = {key: value for key, value in report.items() if key != "artifact_sha256"}
    return _digest(_canonical(unsigned))


def run(output_directory, baseline_commit, request=None):
    request = candidate.expected_request() if request is None else request
    _validate_admission(request, baseline_commit)
    directory = Path(output_directory)
    if directory.exists() or directory.is_symlink():
        raise ValueError("Output must be a fresh directory")
    resolved = directory.resolve()
    if resolved == ROOT or ROOT in resolved.parents or resolved in ROOT.parents:
        raise ValueError("Output directory must be external to the source checkout")
    _baseline_is_ancestor(baseline_commit)
    directory.mkdir(parents=True)

    report = {
        "schema_version": 1,
        "benchmark_id": "preflop-three-rank-sequence-witness-v1",
        "status": "error",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": {"python": platform.python_version(), "implementation": platform.python_implementation(),
                    "platform": platform.platform()},
        "baseline_commit": baseline_commit,
        "request_sha256": _digest(_canonical(request)),
        "source_before": None,
        "source_after": None,
        "candidate_attempts": 0,
        "lp_solve_calls": 0,
        "independent_verification_calls": 0,
        "quality_target_met": False,
        "forbidden_calculation_calls": {},
        "candidate": None,
        "memory_verification": None,
        "saved_file_verification": None,
        "errors": [],
        "cleanup_errors": [],
    }
    primary_error = None
    start = time.perf_counter()
    try:
        report["source_before"] = _snapshot()
        if report["source_before"]["status"]:
            raise ValueError("Witness requires a clean committed source tree")
        calls = report["forbidden_calculation_calls"]
        with transport_run.no_calculation(calls):
            original_solve = candidate.lp._solve_lp

            def counted_solve(*args, **kwargs):
                report["lp_solve_calls"] += 1
                return original_solve(*args, **kwargs)

            with patch.object(candidate.lp, "_solve_lp", side_effect=counted_solve):
                report["candidate_attempts"] += 1
                produced = candidate.build_candidate(request)
        encoded = (json.dumps(produced, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
        _save_once(directory / "candidate.json", encoded, MAX_CANDIDATE_BYTES)
        report["candidate"] = {"artifact_sha256": produced["artifact_sha256"],
                                "raw_sha256": _digest(encoded), "bytes": len(encoded),
                                "status": produced["status"]}
        with transport_run.no_calculation(calls, independent_phase=True), _independent_only_guard(calls):
            report["independent_verification_calls"] += 1
            memory_receipt = independent.verify_candidate(produced)
            report["memory_verification"] = memory_receipt
            report["independent_verification_calls"] += 1
            saved_receipt = independent.verify_candidate(directory / "candidate.json")
            report["saved_file_verification"] = saved_receipt
        if memory_receipt != saved_receipt:
            raise ValueError("Memory and fresh saved-file independent receipts differ")
        if report["lp_solve_calls"] != 2 or report["candidate_attempts"] != 1:
            raise ValueError("Candidate LP call inventory differs from the fixed two-solve model")
        if any(type(value) is not int or value != 0 for value in calls.values()):
            raise ValueError("Forbidden calculation was attempted")
        report["quality_target_met"] = (memory_receipt["exact_mutual_response_verified"] is True
                                         and memory_receipt.get("nash_conv_fraction") == "0")
        report["status"] = "physically-verified" if report["quality_target_met"] else "candidate-quality-miss"
    except BaseException as exc:
        primary_error = exc
        report["errors"].append({"phase": "candidate-or-verification", "type": type(exc).__name__,
                                 "message": str(exc)})
    finally:
        report["elapsed_seconds"] = time.perf_counter() - start
        if report["source_before"] is not None:
            try:
                report["source_after"] = _snapshot()
                if report["source_before"] != report["source_after"]:
                    raise ValueError("Witness source changed during complete call")
            except BaseException as exc:
                report["cleanup_errors"].append({"phase": "source-finalization",
                                                  "type": type(exc).__name__, "message": str(exc)})
                if primary_error is None:
                    primary_error = exc
                    report["errors"].append({"phase": "source-finalization", "type": type(exc).__name__,
                                             "message": str(exc)})
    report["source_unchanged"] = (report["source_before"] is not None
                                  and report["source_before"] == report["source_after"])
    if (report["errors"] or report["cleanup_errors"] or not report["source_unchanged"]):
        report["status"] = "error"
    report["scope"] = "finite three-rank preflop game and exact own-hand pure-response audit"
    report["artifact_sha256"] = _report_sha(report)
    raw_report = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    _save_once(directory / "report.json", raw_report, MAX_REPORT_BYTES)
    if primary_error is not None:
        return directory / "report.json", report
    return directory / "report.json", report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--baseline-commit", required=True)
    args = parser.parse_args()
    path, report = run(args.output_dir, args.baseline_commit)
    print(json.dumps({"path": str(path), "status": report["status"],
                      "artifact_sha256": report["artifact_sha256"],
                      "lp_solve_calls": report["lp_solve_calls"],
                      "errors": report["errors"]}, sort_keys=True), flush=True)
    return 0 if report["status"] == "physically-verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
