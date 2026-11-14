"""One immutable blocker-sensitive count-transport observation, without ranking."""
import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from unittest.mock import patch

from scripts import preflop_aa_ak_transport as candidate
from scripts import preflop_aa_ak_transport_validation as independent
from scripts import certify_preflop_three_rank_transport as previous

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    "scripts/preflop_aa_ak_transport.py", "scripts/preflop_aa_ak_transport_validation.py",
    "scripts/certify_preflop_aa_ak_transport.py", "tests/test_preflop_aa_ak_transport.py",
    "tests/test_preflop_aa_ak_transport_validation.py", "tests/test_certify_preflop_aa_ak_transport.py",
    "docs/preflop-aa-ak-transport.md", "scripts/verify_preflop_ak_kk_basis_publication.py",
    "tests/test_verify_preflop_ak_kk_basis_publication.py", "scripts/preflop_publication_source_history.py",
)
FORBIDDEN = (*previous.FORBIDDEN, "pokerlab.cards.rank_hand", "scripts.river_sequence_form._solve_lp")
INDEPENDENT_FORBIDDEN = (
    "scripts.preflop_aa_ak_transport.build_candidate",
    "pokerlab.preflop_covered_equity.pool_preflop_equities_by_suit",
    "pokerlab.preflop_covered_equity._ranges",
    "pokerlab.preflop_covered_equity._canonical_pair_key",
    "pokerlab.preflop_covered_equity._permutation_between",
    "pokerlab.preflop_covered_equity._mapped_hand",
)


def snapshot():
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              check=True, timeout=15).stdout.decode().strip()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                            check=True, timeout=15).stdout.decode().splitlines()
    hashes = {}
    for relative in SOURCE_PATHS:
        raw = independent.io._bounded_file(ROOT / relative, 1_048_576)
        hashes[relative] = {"raw_sha256": hashlib.sha256(raw).hexdigest(),
                            "lf_sha256": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()}
    return {"revision": revision, "status": status, "source_hashes": hashes}


def published_baseline(commit):
    """Check the offline ancestor and pinned source corpus; GitHub merge is checked externally."""
    if type(commit) is not str or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("Requires the exact independently verified publication merge commit")
    result = subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=ROOT,
                            capture_output=True, timeout=15)
    if result.returncode:
        raise ValueError("Publication baseline is not a current source ancestor")
    identity = commit + ":benchmarks/results/preflop-ak-kk-basis-v1/index.json"
    size = subprocess.run(["git", "cat-file", "-s", identity], cwd=ROOT, capture_output=True,
                          check=True, timeout=15).stdout.strip()
    if size != b"6080":
        raise ValueError("Publication baseline source index has an unexpected size")
    raw = subprocess.run(["git", "show", identity], cwd=ROOT,
                         capture_output=True, check=True, timeout=15).stdout
    if len(raw) != 6080 or hashlib.sha256(raw).hexdigest() != candidate.AK_INDEX_RAW_SHA256:
        raise ValueError("Publication baseline does not contain the authenticated AK source corpus")
    return commit


@contextmanager
def no_calculation(calls, *, independent_phase=False):
    targets = (*FORBIDDEN, *(INDEPENDENT_FORBIDDEN if independent_phase else ()))
    with ExitStack() as stack:
        for target in targets:
            calls.setdefault(target, 0)
            def fail(*_args, _target=target, **_kwargs):
                calls[_target] += 1
                raise AssertionError("Forbidden calculation during AA/AK transport: " + _target)
            stack.enter_context(patch(target, side_effect=fail))
        yield


def _save(path, value, limit):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    if len(raw) > limit:
        raise ValueError("Transport output exceeds its admitted byte cap")
    with path.open("xb") as stream:
        stream.write(raw)


def run(output_directory, *, baseline_commit, request=None):
    candidate.admit(request)  # Full request/cap validation precedes source, Git and output access.
    baseline = published_baseline(baseline_commit)
    directory = Path(output_directory).resolve()
    if directory.exists() or directory == ROOT or ROOT in directory.parents:
        raise ValueError("Use a fresh external AA/AK observation directory")
    directory.mkdir(parents=True)
    report = {"schema_version": 1, "benchmark_id": "preflop-aa-ak-transport-audit-v1",
              "created_at_utc": datetime.now(timezone.utc).isoformat(), "baseline_commit": baseline,
              "errors": [], "source_before": None, "source_after": None, "candidate_attempts": 0,
              "independent_attempts": 0, "forbidden_calculation_calls": {}}
    try:
        report["source_before"] = snapshot()
        if report["source_before"]["status"]:
            raise ValueError("AA/AK observation requires clean committed source")
        with no_calculation(report["forbidden_calculation_calls"]):
            report["candidate_attempts"] += 1
            produced = candidate.build_candidate(request)
        _save(directory / "candidate.json", produced, candidate.MAX_CANDIDATE_BYTES)
        report["candidate_artifact_sha256"] = produced["artifact_sha256"]
        with no_calculation(report["forbidden_calculation_calls"], independent_phase=True):
            report["independent_attempts"] += 1
            report["independent_memory_verification"] = independent.verify(produced)
            report["independent_attempts"] += 1
            report["fresh_saved_file_verification"] = independent.verify_candidate_report(directory / "candidate.json")
        if not independent.io._typed_json_equal(report["independent_memory_verification"],
                                                 report["fresh_saved_file_verification"]):
            raise ValueError("Independent memory and saved-file receipts differ")
        if any(type(c) is not int or c != 0 for c in report["forbidden_calculation_calls"].values()):
            raise ValueError("Forbidden computation was attempted")
    except Exception as exc:
        report["errors"].append({"phase": "audit", "type": type(exc).__name__, "message": str(exc)})
    finally:
        if report["source_before"] is not None:
            try:
                report["source_after"] = snapshot()
                if not independent.io._typed_json_equal(report["source_before"], report["source_after"]):
                    raise ValueError("AA/AK observation source changed")
            except Exception as exc:
                report["errors"].append({"phase": "source-finalization", "type": type(exc).__name__,
                                         "message": str(exc)})
    report["source_unchanged"] = (report["source_before"] is not None and
        independent.io._typed_json_equal(report["source_before"], report["source_after"]))
    report["status"] = "transport-verified" if not report["errors"] else "error"
    report["scope"] = "84 physical pair counts and exact priors only; no strategy, convergence, runtime or memory claim"
    report["artifact_sha256"] = independent.io._artifact(report)
    _save(directory / "report.json", report, 1_048_576)
    return directory / "report.json", report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--baseline-commit", required=True)
    args = parser.parse_args()
    path, result = run(args.output_dir, baseline_commit=args.baseline_commit)
    print(json.dumps({"path": str(path), "status": result["status"], "errors": result["errors"]}), flush=True)
    raise SystemExit(0 if result["status"] == "transport-verified" else 1)
