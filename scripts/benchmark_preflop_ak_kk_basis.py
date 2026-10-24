"""One frozen seven-stage AK/KK source-count observation using original counters.

The stream adapter reuses the project's JJ harness extraction/storage code.
Its callback is the same bounded retention algorithm with this module's seven
explicit stages; the measured JJ harness and its five-stage globals are untouched.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

from pokerlab import native_preflop_equity as native
from scripts import benchmark_preflop_jj_kk_basis as retained
from scripts import preflop_ak_kk_basis_plan as planner
from scripts import preflop_five_count_reference as reference
from scripts import validate_preflop_five_reference as five

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/preflop-ak-kk-basis-v1.json"
SPEC_SHA256 = "73f99d04785a203b6ea3c5498889d96e7cc105f65608556ca98d4ef91eefbec8"
EXPECTED_STAGES = ("reference-all-five", "reference-aa-calibration", "native-aa-calibration",
                   "reference-ak-suited", "native-ak-suited", "reference-ak-offsuit", "native-ak-offsuit")
AA = ROOT / "benchmarks/results/preflop-five-basis-v1.json"
AA_SHA = "2ae377e0af6d55491c667d574f41482f2ea6911ba8565ade3b9c8406b54010f7"
_need = retained._need


def expected_protocol(admission):
    return {"schema_version": 1, "benchmark_id": "preflop-ak-kk-basis-v1",
            "request": planner.expected_request(), "admission": admission,
            "required_stage_order": list(EXPECTED_STAGES),
            "basis_report": {"path": "benchmarks/results/preflop-five-basis-v1.json",
                             "artifact_sha256": AA_SHA},
            "limits": {"protocol_bytes": 65_536, "basis_bytes": 1_000_000,
                       "numerical_subprocess_calls": 7, "raw_stdout_bytes": 16_777_216,
                       "raw_stderr_bytes": 65_536, "report_bytes": 4_194_304},
            "acceptance": {"current_build_all_five_and_aa_calibration": True,
                           "published_aa_counts_match": True, "all_three_ak_censuses_agree": True,
                           "complete_raw_stream_receipts": True,
                           "unchanged_clean_source_and_both_builds": True, "no_retry_or_fallback": True},
            "scope": "Three AK/KK count sources only; no transported equity or strategy claim",
            "third_party_source_or_dependencies_added": False}


def _protocol(admission):
    raw = retained._read_bounded(SPEC, 65_536)
    data = retained._json(raw)
    expected = expected_protocol(admission)
    _need(retained._checksum(data) == SPEC_SHA256 and planner._typed_equal(data, expected),
          "Requires the entire frozen AK/KK count protocol")
    return data, retained._checksum(data)


def snapshot():
    result = five.snapshot()
    hashes = dict(result["source_hashes"])
    for relative in ("scripts/preflop_ak_kk_basis_plan.py", "scripts/benchmark_preflop_ak_kk_basis.py",
                     "tests/test_preflop_ak_kk_basis_plan.py", "tests/test_benchmark_preflop_ak_kk_basis.py",
                     "benchmarks/preflop-ak-kk-basis-v1.json", "docs/preflop-ak-kk-basis.md"):
        raw = retained._read_bounded(ROOT / relative, 1_048_576)
        row = {"raw_sha256": hashlib.sha256(raw).hexdigest(),
               "lf_sha256": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()}
        if relative in hashes:
            _need(hashes[relative] == row, "Inherited AK source identity differs")
        hashes[relative] = row
    return {**result, "source_hashes": dict(sorted(hashes.items()))}


class SevenStageCapture(retained._NumericalCapture):
    def _stage(self, executable, command):
        if executable == self.reference_executable:
            if "--all-five" in command:
                return "reference-all-five"
            if "--count-basis" in command:
                return "reference-aa-calibration"
            if "--count-pairs" in command:
                stage = getattr(self, "native_stage", "reference-unexpected")
                return stage if stage.startswith("reference-ak-") else "reference-unexpected"
        if executable == self.native_executable:
            stage = getattr(self, "native_stage", "native-unexpected")
            return stage if stage.startswith("native-") else "native-unexpected"
        return None

    def _run(self, *args, **kwargs):
        command = args[0] if args else kwargs.get("args")
        executable = self._target(command)
        if executable not in (self.reference_executable, self.native_executable):
            return self._original(*args, **kwargs)
        _need(not self.stopped, "Numerical subprocess capture stopped after an earlier failure")
        stage = self._stage(executable, command)
        position = len(self.calls)
        if position >= len(EXPECTED_STAGES) or stage != EXPECTED_STAGES[position]:
            raise ValueError(f"Unexpected or repeated numerical subprocess stage: {stage}")
        _need(self._supported_stream(kwargs.get("stdout")) and
              self._supported_stream(kwargs.get("stderr")),
              "Numerical subprocess must use retainable bounded stdout/stderr routes")
        record = {"ordinal": position + 1, "stage": stage, "status": "running"}
        self.calls.append(record)
        primary = completed = failure = None
        try:
            completed = self._original(*args, **kwargs)
            record["returncode"] = completed.returncode
            record["status"] = "returned"
            return completed
        except BaseException as exc:
            primary = failure = exc
            self.stopped = True
            record["status"] = "raised"
            record["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            try:
                out = getattr(completed, "stdout", None)
                err = getattr(completed, "stderr", None)
                if failure is not None:
                    if out is None:
                        out = getattr(failure, "stdout", getattr(failure, "output", None))
                    if err is None:
                        err = getattr(failure, "stderr", None)
                out, out_route = self._extract_stream(kwargs.get("stdout"), out, self.stdout_limit)
                err, err_route = self._extract_stream(kwargs.get("stderr"), err, self.stderr_limit)
                record["stdout"] = self._store(stage, "stdout", out, self.stdout_limit, out_route)
                record["stderr"] = self._store(stage, "stderr", err, self.stderr_limit, err_route)
                if record["stdout"]["over_bound"] or record["stderr"]["over_bound"]:
                    record["status"] = "over-bound"
                    self.stopped = True
                    if primary is None:
                        raise ValueError("Numerical subprocess output exceeded its raw stream cap")
            except BaseException as exc:
                record["capture_error"] = f"{type(exc).__name__}: {exc}"
                self.capture_errors.append(record["capture_error"])
                self.stopped = True
                if primary is None:
                    raise


def _rows(rows, expected):
    _need(type(rows) is list and len(rows) == len(expected) and 1 <= len(expected) <= 4,
          "Physical source row count differs from its ordinary request")
    by_pair = {}
    for row in rows:
        _need(type(row) is dict and set(row) == {"sb_hand", "bb_hand", "wins", "ties", "losses", "boards"},
              "Physical source row schema differs")
        _need(type(row["sb_hand"]) is str and type(row["bb_hand"]) is str,
              "Physical endpoint type differs")
        key = (row["sb_hand"], row["bb_hand"])
        _need(key not in by_pair and key in expected, "Duplicate or unknown physical source endpoint")
        _need(all(type(row[k]) is int and row[k] >= 0 for k in ("wins", "ties", "losses", "boards"))
              and row["boards"] == 1_712_304
              and sum(row[k] for k in ("wins", "ties", "losses")) == row["boards"],
              "Physical source counts have invalid integer coverage")
        by_pair[key] = dict(row)
    _need(set(by_pair) == set(expected), "Physical source support differs")
    return [by_pair[pair] for pair in expected]


def _native_rows(prepared, expected):
    table = prepared.equities
    _need(len(table.pairs) == len(table.counts) == len(expected), "Native row census differs")
    rows = []
    for (i, j, _), (wins, ties, losses) in zip(table.pairs, table.counts):
        _need(type(i) is int and type(j) is int and i >= 0 and j >= 0,
              "Native private-hand indices must be exact nonnegative integers")
        rows.append({"sb_hand": "".join(table.hands[0][i]), "bb_hand": "".join(table.hands[1][j]),
                     "wins": wins, "ties": ties, "losses": losses, "boards": 1_712_304})
    return _rows(rows, expected)


def _authenticate_aa():
    raw = retained._read_bounded(AA, 1_000_000)
    report = retained._json(raw)
    _need(report.get("artifact_sha256") == AA_SHA and retained._checksum(
        {key: value for key, value in report.items() if key != "artifact_sha256"}) == AA_SHA,
        "Published AA basis canonical pin differs")
    verified = five.verify_saved(AA)
    _need(verified.get("status") == "passed", "Published AA basis authentication failed")
    return {"artifact_sha256": AA_SHA, "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "verification": verified}, report["independent_physical_count_rows"]


def run(reference_build, candidate_build, output_directory, request=None):
    admission = planner.admit_plan(request)  # Whole schedule before any path or source lookup.
    spec, spec_sha = _protocol(admission)
    aa_receipt, aa_rows = _authenticate_aa()
    directory = retained._fresh_output(output_directory)
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
              "specification": spec, "protocol_sha256": spec_sha, "admission": admission,
              "basis_authentication": aa_receipt, "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "runtime": {"python": sys.version, "platform": platform.platform()},
              "errors": [], "source_before": None, "source_after": None,
              "reference_build_before": None, "reference_build_after": None,
              "candidate_build_before": None, "candidate_build_after": None,
              "profiles": [], "numerical_subprocess_calls": [], "native_capture_errors": []}
    capture = None
    try:
        report["source_before"] = snapshot()
        _need(report["source_before"]["status"] == [], "AK count requires clean committed source")
        ref_exe, report["reference_build_before"] = five.backend(reference_build)
        native_exe, _ = native._backend(candidate_build)
        report["candidate_build_before"] = retained._candidate_identity(candidate_build)
        capture = SevenStageCapture(directory, ref_exe, native_exe, spec)
        with capture:
            with capture.stage("native-aa-calibration"):
                conformance_path, conformance = five.run(reference_build, candidate_build,
                                                        directory / "aa-conformance")
            report["current_build_conformance"] = conformance
            _need(conformance.get("status") == "passed"
                  and five.verify_saved(conformance_path).get("status") == "passed",
                  "Current-build all-five/AA conformance failed")
            _need(conformance["independent_physical_count_rows"] == aa_rows,
                  "Current-build AA counts differ from the published basis")
            report["aa_calibration_match"] = True
            for query in admission["count_requests"][1:]:
                row = {"id": query["id"], "reference": None, "native": None}
                report["profiles"].append(row)
                expected = [tuple(pair) for pair in query["ordered_pairs"]]
                with capture.stage("reference-" + query["id"]):
                    independent = reference.reference_preflop_counts(
                        query["sb_range"], query["bb_range"], build_directory=reference_build,
                        conformance_report=conformance_path,
                        observation_directory=directory / (query["id"] + "-reference"))
                row["reference"] = {"raw_order_rows": independent.rows,
                                     "ordered_rows": _rows(independent.rows, expected),
                                     "metadata": independent.metadata}
                with capture.stage("native-" + query["id"]):
                    prepared = native.prepare_native_preflop_equities(
                        query["sb_range"], query["bb_range"], build_directory=candidate_build)
                row["native"] = {"ordered_rows": _native_rows(prepared, expected),
                                  "equity_table": prepared.equities.metadata(), "metadata": prepared.metadata}
                _need(row["reference"]["ordered_rows"] == row["native"]["ordered_rows"],
                      "AK reference/native physical counts disagree")
            report["independent_physical_count_rows"] = [item for row in report["profiles"]
                                                         for item in row["reference"]["ordered_rows"]]
            _need(len(report["independent_physical_count_rows"]) == 3,
                  "Complete AK source result did not contain three rows")
    except Exception as exc:
        error = {"phase": "setup-or-count", "type": type(exc).__name__, "message": str(exc)}
        if hasattr(exc, "observation"):
            error["observation"] = exc.observation
        report["errors"].append(error)
    finally:
        if capture is not None:
            report["numerical_subprocess_calls"] = capture.calls
            report["native_capture_errors"] = capture.capture_errors
            if not report["errors"]:
                try:
                    _need([row["stage"] for row in capture.calls] == list(EXPECTED_STAGES)
                          and all(row["status"] == "returned" and row["returncode"] == 0
                                  and not row.get("capture_error") for row in capture.calls)
                          and not capture.capture_errors, "Complete seven-stage raw receipt census failed")
                except Exception as exc:
                    report["errors"].append({"phase": "capture-finalization", "message": str(exc)})
        for key, getter in (("source", snapshot),
                            ("reference_build", lambda: five.backend(reference_build)[1]),
                            ("candidate_build", lambda: retained._candidate_identity(candidate_build))):
            if report[key + "_before"] is None:
                continue
            try:
                report[key + "_after"] = getter()
                _need(report[key + "_before"] == report[key + "_after"], key + " identity changed")
            except Exception as exc:
                report["errors"].append({"phase": key + "-finalization", "type": type(exc).__name__,
                                         "message": str(exc)})
    for key in ("source", "reference_build", "candidate_build"):
        report[key + "_unchanged"] = (report[key + "_before"] is not None
                                       and report[key + "_before"] == report[key + "_after"])
    report["status"] = "passed" if not report["errors"] else "error"
    path = directory / "report.json"
    retained._save_report(path, report, spec["limits"]["report_bytes"])
    return path, report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-build", required=True)
    parser.add_argument("--candidate-build", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    path, report = run(args.reference_build, args.candidate_build, args.output_dir)
    print(json.dumps({"path": str(path), "status": report["status"], "artifact_sha256": report["artifact_sha256"],
                      "errors": report["errors"]}), flush=True)
    raise SystemExit(0 if report["status"] == "passed" else 1)
