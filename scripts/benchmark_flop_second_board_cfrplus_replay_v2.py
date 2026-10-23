"""Separate frozen pilot for the corrected numeric replay boundary contract."""
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import hashlib
import importlib
import json
import math
from pathlib import Path
import platform
import re
import sys
import time
import traceback
from unittest.mock import patch

from scripts import benchmark_flop_second_board_cfrplus as base
from scripts import verify_flop_second_board_equivalence_publication as publication


ROOT = base.ROOT
SPEC = ROOT / "benchmarks/flop-second-board-cfrplus-replay-v2.json"
SPEC_SHA256 = "efe8af15bec9fc9d45f2344c0583d7a3a538ba4f2ba9f05289798ed998e787be"
PROTOCOL = "fixed-flop-second-board-cfrplus-replay-v2"
SOURCE_COUNT = 58
_need = base._need


def _adapter():
    return importlib.import_module("scripts.flop_second_board_cfrplus_replay_v2")


def expected_protocol():
    spec = deepcopy(base.expected_protocol())
    spec["protocol_id"] = PROTOCOL
    spec["limits"]["source_files"] = SOURCE_COUNT
    spec["acceptance"]["source"] = (
        "Clean identical committed HEAD/status and 58 named LF hashes before/after; "
        "preserve the original failed v1 source and evidence.")
    spec["replay_boundary"] = {
        "maximum_calls_per_case": 1,
        "raw_result_keys": 13,
        "finite_metric_fields": 8,
        "finite_scalar_gap_fields": 8,
        "maximum_scalar_gap": 1e-10,
        "checked_counts": {"checked_information_sets": 16912,
                           "checked_physical_worlds": 5940,
                           "checked_public_nodes": 9512,
                           "checked_public_states": 30812},
        "retention": "Retain the full raw replay result before validation; expose only its eight metrics to the preserved v1 adapter and restore the wrapper on every exit.",
        "meaning": "Bounded result-schema checks, separate from the unchanged named logical training forecast; not all arithmetic or a performance/memory bound.",
    }
    spec["failed_v1_prerequisite"] = {
        "source_revision": "0106c521fffffdb407f193b4295da6ff2e35759d",
        "raw_index_sha256": "6923789f8847b79326c37906875ae3f658d15762e52c8d6fb37ae89f46ba9afd",
        "index_sha256": "237d9f30d80b13d9e89fee71121ca750438dcd8e34c330a0276dfdbd4b2a5fba",
        "status": "error",
        "qualification": "One stopped T140 attempt; no T560, completed numeric verification or quality-gate result. Never relabel or retry the frozen v1 batch.",
    }
    return spec


def _protocol():
    _need(not SPEC.is_symlink() and SPEC.stat().st_size <= base.MAX_SOURCE_BYTES,
          "Replay-v2 protocol exceeds its source bound")
    with SPEC.open("rb") as stream:
        raw = stream.read(base.MAX_SOURCE_BYTES + 1)
    _need(len(raw) <= base.MAX_SOURCE_BYTES and
          hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == SPEC_SHA256,
          "Replay-v2 protocol differs from its frozen pin")
    spec = publication._json(raw)
    _need(base.proof._typed(spec) == base.proof._typed(expected_protocol()),
          "Replay-v2 protocol differs")
    return raw, spec


def _preflight(spec):
    _need(base.proof._typed(spec) == base.proof._typed(expected_protocol()),
          "Full replay-v2 request differs")
    admission = base._preflight(base.expected_protocol(), _adapter())
    return {**admission, "replay_boundary": spec["replay_boundary"],
            "source_files": SOURCE_COUNT}


def _snapshot():
    state = _adapter()._source_snapshot()
    _need(type(state) is dict and set(state) == {"revision", "status", "source_lf_sha256"}
          and type(state["revision"]) is str and re.fullmatch(r"[0-9a-f]{40}", state["revision"])
          and state["status"] == "" and type(state["source_lf_sha256"]) is dict
          and len(state["source_lf_sha256"]) == SOURCE_COUNT
          and all(type(path) is str and type(digest) is str and
                  re.fullmatch(r"[0-9a-f]{64}", digest)
                  for path, digest in state["source_lf_sha256"].items()),
          "Replay-v2 source snapshot must contain exactly 58 clean identities")
    return state


def _validate_replay_receipt(report):
    _need(type(report) is dict and report.get("schema_version") ==
          "fixed-second-board-cfrplus-replay-v2", "Completed case omitted its v2 identity")
    raw = report.get("numeric_replay_raw_receipt")
    counts = expected_protocol()["replay_boundary"]["checked_counts"]
    names = set(base.proof.METRICS)
    _need(type(raw) is dict and set(raw) == names | {"scalar_absolute_gaps"} | set(counts),
          "Completed case omitted its full 13-field replay receipt")
    _need(all(type(raw[name]) is float and math.isfinite(raw[name]) for name in names),
          "Completed replay metrics are not eight finite floats")
    gaps = raw["scalar_absolute_gaps"]
    _need(type(gaps) is dict and set(gaps) == names and
          all(type(value) is float and math.isfinite(value) and 0 <= value <= 1e-10
              for value in gaps.values()), "Completed replay scalar gaps differ")
    _need(all(type(raw[name]) is int and raw[name] == value for name, value in counts.items()),
          "Completed replay checked counts differ")
    receipt = {"numeric_metrics": {key: raw[key] for key in base.proof.METRICS},
               "scalar_absolute_gaps": dict(gaps), "counts": dict(counts),
               "raw_result_key_count": 13}
    _need(base.proof._typed(report.get("numeric_replay_v2_receipt")) ==
          base.proof._typed(receipt), "Completed raw/projected replay receipts differ")


def _run_case(adapter, iterations, directory, report):
    before = report["boundaries"]["numeric_replay_calls"]
    first_error = None
    replay_attempts = 0
    original_replay = base.proof.physical.replay

    def case_replay(*args, **kwargs):
        nonlocal replay_attempts
        replay_attempts += 1
        _need(replay_attempts <= 1, "Replay-v2 case exceeded its one-replay allowance")
        return original_replay(*args, **kwargs)

    try:
        with patch.object(base.proof.physical, "replay", case_replay):
            result = base._run_case(adapter, iterations, directory, report)
        _validate_replay_receipt(result)
        return result
    except BaseException as exc:
        first_error = exc
        if report["cases"]:
            report["cases"][-1].update(status="error", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        after = report["boundaries"]["numeric_replay_calls"]
        if report["cases"]:
            report["cases"][-1].update(numeric_replay_calls_before=before,
                                        numeric_replay_calls_after=after,
                                        numeric_replay_calls_in_case=after - before,
                                        numeric_replay_attempts_in_case=replay_attempts)
        if not (0 <= after - before <= 1 and (first_error is not None or after - before == 1)):
            message = "Replay-v2 case exceeded or omitted its one-replay allowance"
            if first_error is not None:
                report["errors"].append({"phase": "case-replay-count", "message": message})
            else:
                if report["cases"]:
                    report["cases"][-1].update(status="error", error=message)
                raise ValueError(message)


def run(output_dir):
    report = {
        "schema_version": 2, "protocol_id": PROTOCOL,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "finished_at_utc": None, "status": "not-started",
        "protocol_sha256": None, "admission": None, "case_admissions": None,
        "source_before": None, "source_after": None,
        "boundaries": {}, "cases": [], "errors": [], "index_sha256": None,
        "runtime": {"python": sys.version, "implementation": platform.python_implementation(),
                    "platform": platform.platform()},
        "execution_state": {"mode": "ordinary-process", "system_required": False},
        "execution_receipts": {"wall_seconds": None, "process_cpu_seconds": None,
                               "interpretation": "Execution receipt only; no controlled performance claim."},
    }
    directory, first_error = None, None
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    try:
        raw, spec = _protocol()
        report["admission"] = _preflight(spec)
        directory = base.previous.previous._output_directory(output_dir)
        report["protocol_sha256"] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
        report["case_admissions"] = report["admission"]["cases"]
        report["source_before"] = _snapshot()
        report["status"] = "running"
        base._write_index(directory, report)
        adapter = _adapter()
        with base._instrument(report["boundaries"], adapter):
            for iterations in base.ITERATIONS:
                try:
                    _run_case(adapter, iterations, directory, report)
                    base._write_index(directory, report)
                except BaseException as exc:
                    first_error = {"phase": "case-execution", "message": f"{type(exc).__name__}: {exc}",
                                   "traceback": traceback.format_exc()}
                    break
            if first_error is None:
                base._validate_completion(report)
    except BaseException as exc:
        error = {"phase": "setup-or-completion", "message": f"{type(exc).__name__}: {exc}",
                 "traceback": traceback.format_exc()}
        if first_error is None:
            first_error = error
        else:
            report["errors"].append(error)
    finally:
        report["execution_receipts"].update(base._time_receipt(start_wall, start_cpu))
        if report["source_before"] is not None:
            try:
                report["source_after"] = _snapshot()
                _need(base.proof._typed(report["source_before"]) ==
                      base.proof._typed(report["source_after"]), "Replay-v2 source changed")
            except BaseException as exc:
                report["errors"].append({"phase": "source-finalization",
                                         "message": f"{type(exc).__name__}: {exc}"})
        if first_error is not None:
            report["errors"].insert(0, first_error)
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["status"] = "error" if report["errors"] else (
            "verified-quality-pass" if all(c.get("quality_target_met") is True for c in report["cases"])
            else "verified-quality-miss")
        if directory is not None:
            try:
                base._write_index(directory, report)
            except BaseException as exc:
                report["errors"].append({"phase": "final-index-write",
                                         "message": f"{type(exc).__name__}: {exc}"})
                report.update(status="error", index_sha256=None)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(args.output_dir)
    print(json.dumps({k: report[k] for k in ("status", "errors", "boundaries", "index_sha256")}, sort_keys=True))
    return 0 if report["status"].startswith("verified-") else 1


if __name__ == "__main__":
    raise SystemExit(main())
