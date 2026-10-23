"""Bounded physical JJ/KK source-count comparison using existing counters."""
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from scripts import benchmark_preflop_qq_kk_basis as qq
from scripts import preflop_five_count_reference as reference
from scripts import preflop_jj_kk_basis_plan as planner
from scripts import validate_preflop_five_reference as five
from pokerlab import native_preflop_equity as native
from pokerlab.preflop_full_board_equity import plan_preflop_equities


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/preflop-jj-kk-basis-v1.json"
SPEC_SHA256 = "303594b6782b111c2c132a61c42bfda551379cb5400f3b2ec34f239ff71ee4e3"
AA_REPORT = ROOT / "benchmarks/results/preflop-five-basis-v1.json"
QQ_REPORT = ROOT / "benchmarks/results/preflop-qq-kk-basis-v1.json"
AA_ARTIFACT_SHA256 = "2ae377e0af6d55491c667d574f41482f2ea6911ba8565ade3b9c8406b54010f7"
QQ_ARTIFACT_SHA256 = "d47fcbdca9cb84275adb8902636d8331bca8b6089e1d62e83cc2160ff09503b8"
EXPECTED_STAGES = ("reference-all-five", "reference-aa-calibration", "native-aa-calibration",
                   "reference-jj", "native-jj")
STREAM_DIR = "captured-native-streams"


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def _json(raw):
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_reject_constant)


def _checksum(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_bounded(path, limit):
    path = Path(path)
    _need(not path.is_symlink() and path.is_file() and path.stat().st_size <= limit,
          "Input is missing, symlinked, or exceeds its bound")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    _need(len(data) <= limit, "Input exceeded its bound while reading")
    return data


def _expected_protocol(admission):
    return {
        "schema_version": 1,
        "benchmark_id": "preflop-jj-kk-basis-v1",
        "request": planner.expected_request(),
        "admission": admission,
        "sb_range": "JdJs",
        "bb_range": "KdKs,KcKd,KcKh",
        "basis_reports": [
            {"path": "benchmarks/results/preflop-five-basis-v1.json",
             "artifact_sha256": AA_ARTIFACT_SHA256},
            {"path": "benchmarks/results/preflop-qq-kk-basis-v1.json",
             "artifact_sha256": QQ_ARTIFACT_SHA256},
        ],
        "limits": {"basis_report_bytes": 1_000_000, "numerical_subprocess_calls": 5,
                   "protocol_bytes": 32_768, "raw_stderr_bytes": 65_536,
                   "raw_stdout_bytes": 16_777_216, "report_bytes": 4_194_304},
        "required_stage_order": list(EXPECTED_STAGES),
        "acceptance": {"aa_calibration_matches_published_basis": True,
                       "all_three_jj_kk_censuses_agree": True,
                       "complete_raw_stream_receipts": True,
                       "current_build_exhaustive_five_card_conformance": True,
                       "no_retry_or_fallback": True,
                       "unchanged_clean_source_and_both_builds": True},
        "provenance": {"implementation": "project-owned existing best-five and independent seven-card counters; new orchestration only",
                       "scope": "three fixed JJ/KK relative-suit source rows; future 108-pair pool remains a forecast until separately authenticated",
                       "third_party_source_or_dependencies_added": False,
                       "training_or_equilibrium_claim": False},
    }


def _protocol(admission):
    raw = _read_bounded(SPEC, 32_768)
    spec = _json(raw)
    _need(_checksum(spec) == SPEC_SHA256,
          "JJ/KK protocol structure differs from the frozen canonical pin")
    _need(planner._typed_equal(spec, _expected_protocol(admission)),
          "JJ/KK protocol differs from the full frozen request/admission")
    return spec, SPEC_SHA256


def _snapshot():
    """Extend the established source snapshot with the new harness slice."""
    state = five.snapshot()
    hashes = dict(state["source_hashes"])
    extra = (
        "scripts/preflop_jj_kk_basis_plan.py",
        "tests/test_preflop_jj_kk_basis_plan.py",
        "scripts/benchmark_preflop_jj_kk_basis.py",
        "tests/test_preflop_jj_kk_basis_benchmark.py",
        "benchmarks/preflop-jj-kk-basis-v1.json",
        "docs/preflop-jj-kk-basis.md",
        "scripts/benchmark_preflop_qq_kk_basis.py",
        "benchmarks/preflop-qq-kk-basis-v1.json",
        "benchmarks/results/preflop-five-basis-v1.json",
        "benchmarks/results/preflop-qq-kk-basis-v1.json",
    )
    for relative in extra:
        path = ROOT / relative
        _need(not path.is_symlink(), f"Source identity path is symlinked: {relative}")
        raw = _read_bounded(path, 32 * 1024 * 1024)
        value = {"raw_sha256": hashlib.sha256(raw).hexdigest(),
                 "lf_sha256": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()}
        if relative in hashes:
            _need(hashes[relative] == value, f"Inherited source identity differs: {relative}")
        hashes[relative] = value
    return {**state, "source_hashes": dict(sorted(hashes.items()))}


def _candidate_identity(build):
    executable, manifest = native._backend(build)
    raw_manifest = _read_bounded(Path(build) / "native-preflop-manifest.json", 32_768)
    executable_raw = _read_bounded(executable, 128 * 1024 * 1024)
    return {"manifest": manifest, "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
            "executable_sha256": hashlib.sha256(executable_raw).hexdigest()}


def _authenticate_bases(spec):
    limits = spec["limits"]
    aa_raw = _read_bounded(AA_REPORT, limits["basis_report_bytes"])
    qq_raw = _read_bounded(QQ_REPORT, limits["basis_report_bytes"])
    aa_data, qq_data = _json(aa_raw), _json(qq_raw)
    _need(aa_data.get("artifact_sha256") == AA_ARTIFACT_SHA256 and
          qq_data.get("artifact_sha256") == QQ_ARTIFACT_SHA256,
          "Published basis artifact identity differs")
    aa_result = five.verify_saved(AA_REPORT)
    qq_result = qq.verify_saved(QQ_REPORT)
    _need(aa_result.get("status") == "passed" and qq_result.get("status") == "passed",
          "Published AA/KK or QQ/KK basis failed saved verification")
    return {"aa": {"path": "benchmarks/results/preflop-five-basis-v1.json",
                    "artifact_sha256": AA_ARTIFACT_SHA256,
                    "raw_sha256": hashlib.sha256(aa_raw).hexdigest(), "verification": aa_result},
            "qq": {"path": "benchmarks/results/preflop-qq-kk-basis-v1.json",
                   "artifact_sha256": QQ_ARTIFACT_SHA256,
                   "raw_sha256": hashlib.sha256(qq_raw).hexdigest(), "verification": qq_result},
            "aa_rows": aa_data["independent_physical_count_rows"],
            "qq_rows": qq_data["independent_physical_count_rows"]}


def _fresh_output(path):
    requested = Path(path)
    _need(not requested.is_symlink(), "Use a new output directory outside the checkout")
    directory = requested.resolve()
    _need(directory != ROOT and ROOT not in directory.parents and not directory.exists(),
          "Use a new output directory outside the checkout")
    directory.mkdir(parents=True)
    return directory


class _NumericalCapture:
    """Gate the five admitted executable calls and retain bounded stream evidence."""
    def __init__(self, directory, reference_executable, native_executable, spec):
        self.directory = Path(directory)
        self.reference_executable = Path(reference_executable).resolve()
        self.native_executable = Path(native_executable).resolve()
        self.stdout_limit = spec["limits"]["raw_stdout_bytes"]
        self.stderr_limit = spec["limits"]["raw_stderr_bytes"]
        self.calls = []
        self.capture_errors = []
        self.stopped = False
        self._original = None
        (self.directory / STREAM_DIR).mkdir()

    def __enter__(self):
        self._original = native.subprocess.run
        native.subprocess.run = self._run
        return self

    def __exit__(self, exc_type, exc, tb):
        native.subprocess.run = self._original
        return False

    @staticmethod
    def _target(command):
        if not isinstance(command, (list, tuple)) or not command:
            return None
        try:
            return Path(str(command[0])).resolve()
        except (OSError, ValueError):
            return None

    def _stage(self, executable, command):
        if executable == self.reference_executable:
            if "--all-five" in command:
                return "reference-all-five"
            if "--count-basis" in command:
                return "reference-aa-calibration"
            if "--count-pairs" in command:
                return "reference-jj"
            return "reference-unexpected"
        if executable == self.native_executable:
            # Native calls are distinguished by the caller-set stage token.
            return getattr(self, "native_stage", "native-unexpected")
        return None

    @staticmethod
    def _supported_stream(value):
        if value is subprocess.PIPE:
            return True
        if value is None or isinstance(value, int):
            return False
        if callable(getattr(value, "seek", None)) and callable(getattr(value, "read", None)):
            return True
        filename = getattr(value, "name", None)
        return isinstance(filename, (str, os.PathLike)) and Path(filename).is_file()

    @contextmanager
    def stage(self, name):
        prior = getattr(self, "native_stage", None)
        self.native_stage = name
        try:
            yield
        finally:
            if prior is None:
                self.__dict__.pop("native_stage", None)
            else:
                self.native_stage = prior

    def _extract_stream(self, value, completed_value, limit):
        if value is None:
            raise ValueError("Inherited stdout/stderr cannot be retained as a raw receipt")
        if value is subprocess.PIPE:
            _need(type(completed_value) is bytes,
                  "Piped stdout/stderr did not return an exact byte stream")
            return completed_value[:limit + 1], "captured-pipe"
        if isinstance(value, int):
            raise ValueError("Unsupported integer stdout/stderr descriptor")
        position = None
        if hasattr(value, "seek") and hasattr(value, "read"):
            try:
                value.flush()
                position = value.tell()
                value.seek(0)
                data = value.read(limit + 1)
                value.seek(position)
                return data, "seekable-stream"
            except (OSError, ValueError, io.UnsupportedOperation):
                if position is not None:
                    try:
                        value.seek(position)
                    except (OSError, ValueError, io.UnsupportedOperation):
                        pass
        filename = getattr(value, "name", None)
        if isinstance(filename, (str, os.PathLike)):
            value.flush()
            path = Path(filename)
            if path.is_file():
                with path.open("rb") as stream:
                    return stream.read(limit + 1), "file-backed-stream"
        raise ValueError("stdout/stderr stream cannot be retained")

    def _store(self, stage, label, data, limit, source):
        truncated = len(data) > limit
        retained = data[:limit]
        relative = f"{STREAM_DIR}/{stage}-{label}.bin"
        destination = self.directory / relative
        with destination.open("xb") as stream:
            stream.write(retained)
        return {"path": relative, "bytes_observed_at_most_limit_plus_one": len(data),
                "bytes_retained": len(retained), "sha256": hashlib.sha256(retained).hexdigest(),
                "over_bound": truncated, "capture_source": source}

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
        primary = None
        completed = None
        failure = None
        try:
            completed = self._original(*args, **kwargs)
            record["returncode"] = completed.returncode
            record["status"] = "returned"
            return completed
        except BaseException as exc:
            primary = exc
            failure = exc
            self.stopped = True
            record["status"] = "raised"
            record["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            try:
                completed_stdout = getattr(completed, "stdout", None)
                completed_stderr = getattr(completed, "stderr", None)
                if failure is not None:
                    if completed_stdout is None:
                        completed_stdout = getattr(failure, "stdout", getattr(failure, "output", None))
                    if completed_stderr is None:
                        completed_stderr = getattr(failure, "stderr", None)
                stdout, stdout_source = self._extract_stream(
                    kwargs.get("stdout"), completed_stdout, self.stdout_limit)
                stderr, stderr_source = self._extract_stream(
                    kwargs.get("stderr"), completed_stderr, self.stderr_limit)
                record["stdout"] = self._store(stage, "stdout", stdout, self.stdout_limit, stdout_source)
                record["stderr"] = self._store(stage, "stderr", stderr, self.stderr_limit, stderr_source)
                if record["stdout"]["over_bound"] or record["stderr"]["over_bound"]:
                    record["status"] = "over-bound"
                    self.stopped = True
                    if primary is None:
                        raise ValueError("Numerical subprocess output exceeded its raw stream cap")
            except BaseException as capture_error:
                record["capture_error"] = f"{type(capture_error).__name__}: {capture_error}"
                self.capture_errors.append(record["capture_error"])
                self.stopped = True
                if primary is None:
                    raise


def _source_row_match(rows, expected):
    by_key = {(row["sb_hand"], row["bb_hand"]): row for row in rows}
    return [by_key.get((a, b)) for a, b in expected]


def _counts_from_native(prepared):
    pairs = prepared.equities.pairs
    counts_rows = prepared.equities.counts
    _need(type(pairs) is tuple and type(counts_rows) is tuple and len(pairs) == len(counts_rows) == 3,
          "Native physical table must contain exactly the three admitted pairs")
    result = []
    for (sb_index, bb_index, _prior), counts in zip(pairs, counts_rows):
        _need(type(sb_index) is int and type(bb_index) is int and
              type(counts) is tuple and len(counts) == 3 and
              all(type(value) is int and value >= 0 for value in counts),
              "Native physical pair/count row is malformed")
        sb = "".join(prepared.equities.hands[0][sb_index])
        bb = "".join(prepared.equities.hands[1][bb_index])
        wins, ties, losses = counts
        _need(wins + ties + losses == 1_712_304,
              "Native W/T/L counts do not cover the admitted physical boards")
        result.append({"sb_hand": sb, "bb_hand": bb, "wins": wins, "ties": ties,
                       "losses": losses, "boards": 1_712_304})
    return result


def _validate_rows(rows, expected):
    _need(type(rows) is list and len(rows) == len(expected) == 3,
          "Physical result must contain exactly three ordered pair rows")
    result = []
    for row, (sb, bb) in zip(rows, expected):
        _need(type(row) is dict and set(row) ==
              {"sb_hand", "bb_hand", "wins", "ties", "losses", "boards"},
              "Physical row has an unexpected shape")
        _need(type(row["sb_hand"]) is str and type(row["bb_hand"]) is str and
              row["sb_hand"] == sb and row["bb_hand"] == bb,
              "Physical row order or hand identity differs from the admitted pairs")
        _need(all(type(row[name]) is int and row[name] >= 0
                  for name in ("wins", "ties", "losses", "boards")) and
              row["boards"] == 1_712_304 and
              row["wins"] + row["ties"] + row["losses"] == 1_712_304,
              "Physical row has invalid integer W/T/L coverage")
        result.append(dict(row))
    return result


def _rows_in_admitted_order(raw_rows, reference_order, admitted_order):
    validated_raw = _validate_rows(raw_rows, reference_order)
    by_key = {(row["sb_hand"], row["bb_hand"]): row for row in validated_raw}
    _need(set(by_key) == set(admitted_order) and len(by_key) == len(admitted_order),
          "Independent reference returned a different JJ/KK pair set")
    return [dict(by_key[key]) for key in admitted_order]


def _save_report(path, report, byte_limit):
    report.pop("artifact_sha256", None)
    report["artifact_sha256"] = five.checksum(report)
    encoded = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    _need(len(encoded) <= byte_limit, "JJ/KK report exceeds its size cap")
    temporary = Path(path).with_name(Path(path).name + ".tmp")
    with temporary.open("xb") as stream:
        stream.write(encoded)
    temporary.replace(path)


def run(reference_build, candidate_build, output_directory, request=None):
    # Admission is deliberately first: malformed requests cannot inspect paths,
    # load reports, create output or resolve either executable.
    admitted = planner.admit_plan(request)
    plan_record = admitted.to_record()
    # Complete all Python-side workload admission before protocol/source/report
    # reads, output creation, and either executable lookup.
    aa_plan = plan_preflop_equities("AdAs", "KdKs,KcKd,KcKh")
    aa_plan.validate()
    _need(len(aa_plan.pairs) == 3, "AA calibration candidate admission changed")
    reference_pairs_raw, reference_admission = reference.pair_admission(
        "JdJs", "KdKs,KcKd,KcKh")
    reference_pairs = tuple(("".join(sb), "".join(bb)) for sb, bb in reference_pairs_raw)
    jj_plan = plan_preflop_equities("JdJs", "KdKs,KcKd,KcKh")
    jj_plan.validate()
    native_pairs = tuple(("".join(jj_plan.hands[0][i]), "".join(jj_plan.hands[1][j]))
                         for i, j, _weight in jj_plan.pairs)
    _need(set(reference_pairs) == set(admitted.ordered_pairs) == set(native_pairs) and
          len(reference_pairs) == len(native_pairs) == 3,
          "Reference/native pre-count admissions differ from the frozen JJ/KK request")
    spec, spec_sha = _protocol(plan_record)
    bases = _authenticate_bases(spec)
    directory = _fresh_output(output_directory)
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
              "protocol_sha256": spec_sha, "specification": spec,
              "admission": plan_record, "basis_authentication": {k: v for k, v in bases.items()
                  if k not in ("aa_rows", "qq_rows")},
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "runtime": {"python": sys.version, "implementation": platform.python_implementation(),
                          "platform": platform.platform()},
              "errors": [], "stage_order": [], "numerical_subprocess_calls": [],
              "native_capture_errors": [], "source_before": None, "source_after": None,
              "reference_build_before": None, "reference_build_after": None,
              "candidate_build_before": None, "candidate_build_after": None}
    report_path = directory / "report.json"
    source_before = ref_before = native_before = None
    capture = None
    primary = None

    def record_error(stage, exc):
        nonlocal primary
        entry = {"phase": stage, "type": type(exc).__name__, "message": str(exc)}
        if primary is None:
            primary = entry
        else:
            report["errors"].append(entry)

    try:
        source_before = _snapshot()
        report["source_before"] = source_before
        _need(not source_before.get("status"), "JJ/KK count requires clean committed source")
        # The complete AA calibration and JJ requests are admitted before either
        # project executable is resolved.
        report["aa_calibration_admission"] = aa_plan.budget
        report["jj_reference_admission"] = reference_admission
        report["jj_native_admission"] = jj_plan.budget
        ref_executable, ref_before = five.backend(reference_build)
        native_executable, _native_manifest = native._backend(candidate_build)
        native_before = _candidate_identity(candidate_build)
        report["reference_build_before"] = ref_before
        report["candidate_build_before"] = native_before
        _need(native_before["manifest"] == _native_manifest,
              "Native executable/manifest identity changed during preflight")
        capture = _NumericalCapture(directory, ref_executable, native_executable, spec)
        with capture:
            conformance_dir = directory / "aa-conformance"
            conformance_path = None
            try:
                with capture.stage("native-aa-calibration"):
                    conformance_path, conformance = five.run(reference_build, candidate_build, conformance_dir)
                report["current_build_conformance"] = conformance
                report["stage_order"] = [row["stage"] for row in capture.calls]
                if conformance.get("status") != "passed":
                    raise ValueError("Current-build all-five/AA calibration failed")
                checked = five.verify_saved(conformance_path)
                _need(checked.get("status") == "passed", "Current-build conformance saved verification failed")
                aa_rows = conformance.get("independent_physical_count_rows")
                expected_aa = bases["aa_rows"]
                _need(aa_rows == expected_aa, "Current-build AA calibration differs from published basis")
                report["aa_calibration_match"] = True
            except Exception as exc:
                if "conformance" in locals():
                    report["current_build_conformance"] = conformance
                record_error("aa-conformance", exc)
            if primary is None:
                ref_dir = directory / "jj-reference-raw"
                try:
                    report["stage_order"] = [row["stage"] for row in capture.calls]
                    result = reference.reference_preflop_counts(
                        spec["sb_range"], spec["bb_range"], build_directory=reference_build,
                        conformance_report=conformance_path,
                        observation_directory=ref_dir)
                    report["reference_physical_count_rows_raw_order"] = _validate_rows(
                        result.rows, reference_pairs)
                    report["independent_physical_count_rows"] = _rows_in_admitted_order(
                        result.rows, reference_pairs, admitted.ordered_pairs)
                    report["reference_metadata"] = result.metadata
                except Exception as exc:
                    if hasattr(exc, "observation"):
                        report["reference_failed_observation"] = exc.observation
                    record_error("reference-jj", exc)
                if primary is None:
                    try:
                        with capture.stage("native-jj"):
                            prepared = native.prepare_native_preflop_equities(
                                spec["sb_range"], spec["bb_range"], build_directory=candidate_build)
                        report["candidate_metadata"] = prepared.metadata
                        report["candidate_equity_table"] = prepared.equities.metadata()
                        native_rows = _validate_rows(_counts_from_native(prepared), admitted.ordered_pairs)
                        expected = list(admitted.ordered_pairs)
                        reference_rows = report["independent_physical_count_rows"]
                        _need(_source_row_match(reference_rows, expected) ==
                              _source_row_match(native_rows, expected),
                              "Best-five reference and native seven-card JJ/KK W/T/L rows differ")
                        report["native_physical_count_rows"] = native_rows
                        report["all_three_jj_kk_censuses_agree"] = True
                    except Exception as exc:
                        record_error("native-jj", exc)
    except Exception as exc:
        record_error("setup-or-count", exc)
    finally:
        if capture is not None:
            report["numerical_subprocess_calls"] = capture.calls
            report["native_capture_errors"] = capture.capture_errors
            report["stage_order"] = [row["stage"] for row in capture.calls]
            if primary is None:
                try:
                    _need(report["stage_order"] == list(EXPECTED_STAGES),
                          "Numerical subprocess stage order or count differs")
                    _need(all(call.get("status") == "returned" and call.get("returncode") == 0 and
                              not call.get("capture_error") and
                              not call.get("stdout", {}).get("over_bound") and
                              not call.get("stderr", {}).get("over_bound") for call in capture.calls),
                          "Numerical subprocess return or raw-stream receipt failed")
                except Exception as exc:
                    record_error("numerical-capture", exc)
        if source_before is not None:
            try:
                report["source_after"] = _snapshot()
                _need(report["source_before"] == report["source_after"],
                      "JJ/KK source identity changed during the batch")
            except Exception as exc:
                record_error("source-finalization", exc)
        if ref_before is not None:
            try:
                report["reference_build_after"] = five.backend(reference_build)[1]
                _need(ref_before == report["reference_build_after"],
                      "Best-five reference source/build changed during the batch")
            except Exception as exc:
                record_error("reference-build-finalization", exc)
        if native_before is not None:
            try:
                report["candidate_build_after"] = _candidate_identity(candidate_build)
                _need(native_before == report["candidate_build_after"],
                      "Native candidate source/build changed during the batch")
            except Exception as exc:
                record_error("candidate-build-finalization", exc)
        if primary is not None:
            report["errors"].insert(0, primary)
        report["source_unchanged"] = report["source_before"] is not None and \
            report["source_before"] == report["source_after"]
        report["reference_build_unchanged"] = report["reference_build_before"] is not None and \
            report["reference_build_before"] == report["reference_build_after"]
        report["candidate_build_unchanged"] = report["candidate_build_before"] is not None and \
            report["candidate_build_before"] == report["candidate_build_after"]
        report["status"] = "passed" if not report["errors"] and \
            report.get("all_three_jj_kk_censuses_agree") is True else "error"
        try:
            _save_report(report_path, report, spec["limits"]["report_bytes"])
        except Exception as exc:
            # Keep the full report and primary error in the returned API. Do not
            # retry with a reduced artifact or overwrite a partial/full report.
            report.pop("artifact_sha256", None)
            report["errors"].append({"phase": "report-finalization", "type": type(exc).__name__,
                                    "message": str(exc)})
            report["status"] = "error"
    return report_path, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-build", required=True)
    parser.add_argument("--candidate-build", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    path, report = run(args.reference_build, args.candidate_build, args.output_dir)
    print(json.dumps({"path": str(path), "status": report["status"],
                      "errors": report["errors"],
                      "artifact_sha256": report.get("artifact_sha256")}, sort_keys=True), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
