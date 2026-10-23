"""Record one no-training source-transport audit and fresh saved-file replay."""
import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

from scripts import preflop_three_rank_transport as candidate
from scripts import preflop_three_rank_transport_validation as independent

ROOT = Path(__file__).resolve().parents[1]
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
FORBIDDEN = (
    "pokerlab.preflop_full_board_equity.rank_hand",
    "pokerlab.native_preflop_equity.prepare_native_preflop_equities",
    "scripts.preflop_five_count_reference.reference_preflop_counts",
    "scripts.validate_preflop_five_reference.validate_five_dump",
    "scripts.build_preflop_five_reference.build",
    "scripts.build_native_preflop.build",
    "pokerlab.cfr.train",
    "pokerlab.cfr_plus.train",
)


def snapshot():
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, check=True, timeout=15).stdout.decode().strip()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                            capture_output=True, check=True, timeout=15).stdout.decode().splitlines()
    hashes = {}
    for relative in SOURCE_PATHS:
        path = ROOT / relative
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_048_576:
            raise ValueError("Audit source path is missing, symlinked or over bound")
        raw = path.read_bytes()
        hashes[relative] = {"raw_sha256": hashlib.sha256(raw).hexdigest(),
                            "lf_sha256": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()}
    return {"revision": revision, "status": status, "source_hashes": hashes}


@contextmanager
def no_calculation(calls, *, independent_phase=False):
    targets = list(FORBIDDEN)
    if independent_phase:
        targets += ["scripts.preflop_three_rank_transport.build_candidate",
                    "pokerlab.preflop_covered_equity.pool_preflop_equities_by_suit",
                    "pokerlab.preflop_covered_equity._ranges"]
    with ExitStack() as stack:
        for target in targets:
            calls.setdefault(target, 0)
            def fail(*_args, _target=target, **_kwargs):
                calls[_target] += 1
                raise AssertionError("Forbidden calculation during transport audit: " + _target)
            stack.enter_context(patch(target, side_effect=fail))
        yield


def _save(path, value, limit):
    encoded = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    if len(encoded) > limit:
        raise ValueError("Transport output exceeds its admitted byte limit")
    with path.open("xb") as stream:
        stream.write(encoded)


def run(output_directory, request=None):
    candidate.admit(request)  # Entire literal target before path or source lookup.
    directory = Path(output_directory).resolve()
    if directory.exists() or directory == ROOT or ROOT in directory.parents:
        raise ValueError("Use a fresh external transport observation directory")
    directory.mkdir(parents=True)
    report = {"schema_version": 1, "benchmark_id": "preflop-three-rank-transport-audit-v1",
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "errors": [], "source_before": None, "source_after": None,
              "candidate_attempts": 0, "independent_attempts": 0,
              "forbidden_calculation_calls": {}}
    try:
        report["source_before"] = snapshot()
        if report["source_before"]["status"]:
            raise ValueError("Transport audit requires clean committed source")
        with no_calculation(report["forbidden_calculation_calls"]):
            report["candidate_attempts"] += 1
            produced = candidate.build_candidate(request)
        _save(directory / "candidate.json", produced, candidate.MAX_REPORT_BYTES)
        report["candidate_artifact_sha256"] = produced["artifact_sha256"]
        with no_calculation(report["forbidden_calculation_calls"], independent_phase=True):
            report["independent_attempts"] += 1
            report["independent_memory_verification"] = independent.verify_candidate_report(produced)
            report["independent_attempts"] += 1
            report["fresh_saved_file_verification"] = independent.verify_candidate_report(directory / "candidate.json")
        if report["independent_memory_verification"] != report["fresh_saved_file_verification"]:
            raise ValueError("Fresh saved transport verification differs")
        if any(report["forbidden_calculation_calls"].values()):
            raise ValueError("Forbidden computation was attempted")
    except Exception as exc:
        report["errors"].append({"phase": "audit", "type": type(exc).__name__, "message": str(exc)})
    finally:
        if report["source_before"] is not None:
            try:
                report["source_after"] = snapshot()
                if report["source_before"] != report["source_after"]:
                    raise ValueError("Transport audit source changed")
            except Exception as exc:
                report["errors"].append({"phase": "source-finalization", "type": type(exc).__name__,
                                         "message": str(exc)})
    report["source_unchanged"] = report["source_before"] is not None and report["source_before"] == report["source_after"]
    report["status"] = "transport-verified" if not report["errors"] else "error"
    report["scope"] = "108 physical pair counts and exact priors; no strategy, equilibrium, runtime or memory claim"
    report["artifact_sha256"] = independent._artifact(report)
    _save(directory / "report.json", report, 1_048_576)
    return directory / "report.json", report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    path, report = run(args.output_dir)
    print(json.dumps({"path": str(path), "status": report["status"], "errors": report["errors"]}), flush=True)
    return 0 if report["status"] == "transport-verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
