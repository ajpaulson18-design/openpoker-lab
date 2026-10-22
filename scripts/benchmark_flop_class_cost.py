"""Preregistered complete-call cost comparison for fixed-flop class CFR+."""
from datetime import datetime, timezone
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import traceback
from datetime import datetime

from scripts import benchmark_weighted_full_deck_flop as power
from scripts import flop_class_call_measurement as measurement
from scripts import flop_class_cfrplus as legacy
from scripts import flop_class_compact_budget as budget
from scripts import flop_class_compact_cfrplus as compact
from scripts import flop_public_classes as proof
from scripts import verify_flop_class_cfrplus_publication as legacy_publication
from scripts import verify_flop_class_compact_cfrplus_publication as compact_publication


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/flop-class-call-cost-v1.json"
SPEC_LF_SHA256 = "06c652d2e593be70ec0956bacfb323ee76f24d79b22b5f7b7a61487968bf120e"
MAX_SPEC_BYTES = 64 * 1024
MAX_INDEX_BYTES = 4 * 1024 * 1024
MAX_RAW_BYTES = 24 * 1024 * 1024
MAX_GZIP_BYTES = 8 * 1024 * 1024
METHODS = {
    "class-140": {"iterations": 140, "quality_target_met": False,
                  "call": lambda: legacy.solve_fixed(140)},
    "class-560": {"iterations": 560, "quality_target_met": True,
                  "call": lambda: compact.solve_fixed_compact(560)},
}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        proof._need(key not in result, "Duplicate benchmark JSON field")
        result[key] = value
    return result


def _canonical(value, *, newline=False):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    return raw + (b"\n" if newline else b"")


def _validate_utc(value, label):
    proof._need(type(value) is str and bool(value),
                f"Saved {label} timestamp is malformed")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Saved {label} timestamp is malformed") from exc
    proof._need(parsed.tzinfo is not None and parsed.utcoffset() is not None and
                parsed.utcoffset().total_seconds() == 0,
                f"Saved {label} timestamp must be aware UTC")
    return parsed


def _semantic_digest(report):
    semantic = {key: value for key, value in report.items()
                if key not in ("runtime", "artifact_sha256")}
    return hashlib.sha256(_canonical(semantic)).hexdigest()


def load_spec():
    proof._need(SPEC.stat().st_size <= MAX_SPEC_BYTES, "Cost protocol exceeds size bound")
    raw = SPEC.read_bytes()
    proof._need(len(raw) <= MAX_SPEC_BYTES and
                hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == SPEC_LF_SHA256,
                "Frozen cost protocol bytes changed")
    spec = json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    proof._need(spec.get("protocol_id") == "fixed-flop-class-call-cost-v1" and
                spec.get("timed_calls") == 6 and spec.get("allocation_calls") == 2 and
                spec.get("total_calls") == 8 and spec.get("timed_orders") == [
                    ["class-140", "class-560"], ["class-560", "class-140"],
                    ["class-140", "class-560"]] and
                spec.get("allocation_order") == ["class-140", "class-560"],
                "Frozen cost protocol dimensions changed")
    proof._need(spec.get("interpretation", "").find("no same-work speedup") >= 0,
                "Cost comparison qualification changed")
    return spec


def _source_snapshot():
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                              capture_output=True, text=True, timeout=30).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                            cwd=ROOT, check=True, capture_output=True, text=True,
                            timeout=30).stdout
    proof._need(bool(revision) and not status, "Measurement requires committed clean source")
    hashes = compact.source_hashes()
    extra = ("scripts/benchmark_flop_class_cost.py",
             "scripts/flop_class_call_measurement.py",
             "scripts/verify_flop_class_compact_cfrplus_publication.py",
             "scripts/benchmark_weighted_full_deck_flop.py",
             "benchmarks/flop-class-call-cost-v1.json")
    for name in extra:
        path = ROOT / name
        proof._need(path.stat().st_size <= 2 * 1024 * 1024,
                    "Measurement source exceeds size bound")
        raw = path.read_bytes()
        proof._need(len(raw) <= 2 * 1024 * 1024,
                    "Measurement source exceeds size bound")
        hashes[name] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    return {"revision": revision, "status": status,
            "source_lf_sha256": dict(sorted(hashes.items()))}


def _requests(spec):
    requests = []
    for round_number, order in enumerate(spec["timed_orders"], 1):
        for method in order:
            requests.append({"kind": "timed", "round": round_number, "method": method})
    for method in spec["allocation_order"]:
        requests.append({"kind": "allocation", "method": method})
    return requests


def _preflight(spec):
    forecasts = {}
    for request in _requests(spec):
        method = request["method"]
        iterations = METHODS[method]["iterations"]
        if method == "class-140":
            legacy.admit_request(iterations)
        forecast = budget.admit_compact_request(iterations)
        forecasts[f"{request['kind']}:{request.get('round', 'separate')}:{method}"] = forecast
    total = sum(item["total_admitted_work"] for item in forecasts.values())
    proof._need(total == spec["expected_experiment_named_work"] and
                total <= spec["maximum_experiment_named_work"],
                "Full eight-call named-work reservation differs")
    return {"per_request": forecasts, "total_named_work": total,
            "maximum_named_work": spec["maximum_experiment_named_work"]}


def _pilot_expectations():
    _, legacy_raw = legacy_publication._read(legacy_publication.PUBLICATION)
    _, compact_raw, compact_report = compact_publication._read(compact_publication.PUBLICATION)
    legacy_report = json.loads(legacy_raw, object_pairs_hook=_pairs)
    return {"class-140": _semantic_digest(legacy_report),
            "class-560": _semantic_digest(compact_report)}


def _validate_raw(raw, method, expected):
    proof._need(type(raw) is bytes and len(raw) <= MAX_RAW_BYTES,
                "Measured raw report exceeds size bound")
    report = json.loads(raw, object_pairs_hook=_pairs,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    proof._need(type(report) is dict and _canonical(report, newline=True) == raw,
                "Measured report is not canonical JSON")
    unsigned = {key: value for key, value in report.items() if key != "artifact_sha256"}
    proof._need(proof._digest(unsigned) == report.get("artifact_sha256"),
                "Measured report artifact checksum differs")
    proof._need(report.get("quality_target_met") is METHODS[method]["quality_target_met"] and
                _semantic_digest(report) == expected[method],
                "Measured report differs from its independently replayed pilot")
    return report


def _summary(rows):
    result = {}
    for method in METHODS:
        timed = [row for row in rows if row["kind"] == "timed" and row["method"] == method]
        allocation = [row for row in rows if row["kind"] == "allocation" and row["method"] == method]
        seconds = [row["metadata"]["wall_seconds"] for row in timed
                   if row.get("status") == "complete"]
        result[method] = {
            "timed_rows": len(timed),
            "median_wall_seconds": statistics.median(seconds)
            if len(timed) == 3 and len(seconds) == 3 else None,
            "quality_target_met": METHODS[method]["quality_target_met"],
            "allocation_traced_peak_bytes": allocation[0].get("metadata", {}).get(
                "python_traced_peak_bytes") if len(allocation) == 1 else None,
        }
    return result


def _write_index(directory, report):
    unsigned = {key: value for key, value in report.items() if key != "index_sha256"}
    report["index_sha256"] = proof._digest(unsigned)
    raw = json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    proof._need(len(raw) <= MAX_INDEX_BYTES, "Measurement index exceeds size bound")
    temp = directory / "index.json.tmp"
    temp.write_bytes(raw)
    temp.replace(directory / "index.json")


def _record_error(row, exc):
    row["status"] = "error"
    row["error"] = f"{type(exc).__name__}: {exc}"
    row["traceback"] = traceback.format_exc()


def run(output, *, execution_state=None):
    output = Path(output).resolve()
    if (output.exists() or output == ROOT or ROOT in output.parents or
            output in ROOT.parents):
        raise ValueError("Output must be a new directory outside the source checkout")
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": 1, "protocol_id": "fixed-flop-class-call-cost-v1",
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "runtime": {"python": sys.version,
                          "implementation": platform.python_implementation(),
                          "platform": platform.platform()},
              "samples": [], "validation_errors": []}
    before = None
    first_raw_file = {method: None for method in METHODS}
    try:
        spec = load_spec()
        before = _source_snapshot()
        report["specification"] = spec
        report["source_before"] = before
        report["execution_state"] = execution_state or {
            "mode": "direct-call", "system_required": False}
        report["runtime_qualification"] = spec["runtime_qualification"]
        report["preflight"] = _preflight(spec)
        pilot_semantics = _pilot_expectations()
        report["pilot_semantic_sha256"] = pilot_semantics
        start_report = dict(report)
        start_report["phase"] = "pre-call"
        _write_index(output, start_report)

        requests = _requests(spec)
        stop_reason = None
        for index, request in enumerate(requests):
            raw = measured_report = compressed = None
            row = dict(request)
            row["iterations"] = METHODS[request["method"]]["iterations"]
            row["active"] = True
            report["active_request"] = row
            _write_index(output, report)
            try:
                current = _source_snapshot()
                proof._need(current == before, "Source changed before measured call")
                if request["kind"] == "timed":
                    import gc
                    gc.collect()
                call = METHODS[request["method"]]["call"]
                raw, metadata = measurement.measure_call(
                    call, allocation=request["kind"] == "allocation")
                proof._need(len(raw) <= MAX_RAW_BYTES, "Measured raw report exceeds size bound")
                compressed = gzip.compress(raw, mtime=0)
                proof._need(len(compressed) <= MAX_GZIP_BYTES,
                            "Compressed measured report exceeds size bound")
                filename = f"{request['method']}-{request['kind']}-{request.get('round', '1')}.json.gz"
                with (output / filename).open("xb") as payload_file:
                    payload_file.write(compressed)
                row.update(file=filename, raw_bytes=len(raw), gzip_bytes=len(compressed),
                           gzip_sha256=hashlib.sha256(compressed).hexdigest(),
                           metadata=metadata,
                           report_artifact_sha256=metadata["artifact_sha256"],
                           quality_target_met=metadata["quality_target_met"])
                measured_report = _validate_raw(raw, request["method"], pilot_semantics)
                first_file = first_raw_file[request["method"]]
                if first_file is None:
                    first_raw_file[request["method"]] = filename
                else:
                    previous_raw = _bounded_gzip(output / first_file)
                    try:
                        proof._need(previous_raw == raw,
                                    "Repeated raw reports differ within this runtime")
                    finally:
                        previous_raw = None
                row.update(status="complete",
                           report_artifact_sha256=measured_report["artifact_sha256"],
                           quality_target_met=measured_report["quality_target_met"])
            except Exception as exc:
                _record_error(row, exc)
                report["validation_errors"].append(row["error"])
                if "Source changed" in row["error"]:
                    stop_reason = "source-drift"
            finally:
                # Large raw policies are retained on disk, not in the loop's
                # live locals while the next complete call runs.
                raw = measured_report = compressed = None
            try:
                after_call = _source_snapshot()
                row["source_after_call"] = after_call
                if after_call != before:
                    row["status"] = "error"
                    row["error"] = "Source changed during measured call"
                    row["traceback"] = "Source snapshot mismatch after completed call."
                    report["validation_errors"].append(row["error"])
                    stop_reason = "source-drift"
            except Exception as exc:
                _record_error(row, exc)
                report["validation_errors"].append(row["error"])
                stop_reason = "source-drift"
            row.pop("active", None)
            report["samples"].append(row)
            report.pop("active_request", None)
            report["phase"] = "after-call"
            _write_index(output, report)
            if stop_reason:
                for skipped in requests[index + 1:]:
                    report["samples"].append({**skipped,
                        "iterations": METHODS[skipped["method"]]["iterations"],
                        "status": "not-run", "error": "Stopped after source drift"})
                break
        report["summary"] = _summary(report["samples"])
        report["status"] = "complete" if not report["validation_errors"] and len(report["samples"]) == 8 else "error"
        report["method_comparison_limit"] = spec["interpretation"]
    except Exception as exc:
        report["status"] = "error"
        report["validation_errors"].append(f"{type(exc).__name__}: {exc}")
        report["traceback"] = traceback.format_exc()
    finally:
        try:
            report["source_after"] = _source_snapshot()
            if before is not None and report["source_after"] != before:
                report["validation_errors"].append("Source changed during experiment")
                report["status"] = "error"
        except Exception as exc:
            report["source_after"] = None
            report["validation_errors"].append(f"Final source snapshot failed: {type(exc).__name__}: {exc}")
            report["status"] = "error"
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        _write_index(output, report)
    return report


def _bounded_gzip(path):
    proof._need(not path.is_symlink() and path.is_file() and
                path.stat().st_size <= MAX_GZIP_BYTES,
                "Invalid bounded measured gzip report")
    import io
    with path.open("rb") as compressed_file:
        compressed = compressed_file.read(MAX_GZIP_BYTES + 1)
    proof._need(len(compressed) <= MAX_GZIP_BYTES,
                "Compressed measured report exceeds size bound")
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
        raw = stream.read(MAX_RAW_BYTES + 1)
    proof._need(len(raw) <= MAX_RAW_BYTES, "Measured report exceeds raw size bound")
    return raw


def verify_saved(output):
    output = Path(output)
    proof._need(not output.is_symlink(), "Measurement output directory cannot be a symlink")
    index = output / "index.json"
    proof._need(not index.is_symlink() and index.is_file() and
                index.stat().st_size <= MAX_INDEX_BYTES,
                "Invalid bounded measurement index")
    raw_index = index.read_bytes()
    proof._need(len(raw_index) <= MAX_INDEX_BYTES, "Measurement index exceeds size bound")
    report = json.loads(raw_index, object_pairs_hook=_pairs,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    unsigned = {key: value for key, value in report.items() if key != "index_sha256"}
    proof._need(proof._digest(unsigned) == report.get("index_sha256"),
                "Measurement index checksum differs")
    spec = load_spec()
    proof._need(proof._typed(report.get("specification")) == proof._typed(spec) and
                report.get("protocol_id") == spec["protocol_id"],
                "Measurement protocol differs")
    proof._need(report.get("runtime_qualification") == spec["runtime_qualification"],
                "Measurement runtime qualification differs")
    proof._need(proof._typed(report.get("preflight")) == proof._typed(_preflight(spec)),
                "Saved full-call resource admission differs")
    before, after = report.get("source_before"), report.get("source_after")
    proof._need(type(before) is dict and before == after and not before.get("status"),
                "Recorded measurement source was dirty or changed")
    proof._need(type(before.get("revision")) is str and len(before["revision"]) == 40 and
                all(character in "0123456789abcdef" for character in before["revision"]) and
                type(before.get("status")) is str and before["status"] == "",
                "Recorded Git revision or status is malformed")
    current = _source_snapshot()
    proof._need(current["source_lf_sha256"] == before["source_lf_sha256"],
                "Current source manifest differs from measurement")
    expected = _pilot_expectations()
    proof._need(report.get("pilot_semantic_sha256") == expected,
                "Saved independent pilot semantic identities differ")
    rows = report.get("samples")
    proof._need(type(rows) is list and len(rows) == 8,
                "Saved measurement must retain all eight planned calls")
    requests = _requests(spec)
    proof._need(all(type(row) is dict for row in rows), "Saved request row is malformed")
    for row, request in zip(rows, requests):
        proof._need(type(row.get("kind")) is str and row["kind"] == request["kind"] and
                    type(row.get("method")) is str and row["method"] == request["method"] and
                    (type(row.get("round")) is int and row["round"] == request["round"]
                     if request["kind"] == "timed" else "round" not in row) and
                    type(row.get("iterations")) is int and
                    row["iterations"] == METHODS[request["method"]]["iterations"],
                    "Saved call request types or inventory differ")
    proof._need(report.get("method_comparison_limit") == spec["interpretation"],
                "Saved method-comparison limitation differs")
    proof._need([(row["kind"], row.get("round"), row["method"]) for row in rows] ==
                [(row["kind"], row.get("round"), row["method"]) for row in requests],
                "Saved measurement request order differs")
    _validate_utc(report.get("created_at_utc"), "index creation")
    _validate_utc(report.get("finished_at_utc"), "index completion")
    proof._need(type(report.get("validation_errors")) is list and
                all(type(item) is str and item for item in report["validation_errors"]),
                "Saved validation errors are malformed")
    proof._need(type(report.get("runtime")) is dict and
                type(report["runtime"].get("python")) is str and
                type(report["runtime"].get("platform")) is str and
                type(report["runtime"].get("implementation")) is str and
                type(report.get("execution_state")) is dict and
                type(report["execution_state"].get("mode")) is str and
                type(report["execution_state"].get("system_required")) is bool,
                "Saved runtime or execution-state metadata is malformed")
    state = report["execution_state"]
    if state["mode"] in ("ordinary-process", "direct-call"):
        proof._need(state["system_required"] is False and
                    set(state) == {"mode", "system_required"},
                    "Saved ordinary execution-state metadata differs")
    else:
        proof._need(state["mode"] == "windows-benchmark-thread" and
                    state["system_required"] is True and
                    type(state.get("requested_flags")) is int and
                    state["requested_flags"] == 0x80000001 and
                    type(state.get("previous_flags")) is int and
                    state["previous_flags"] > 0 and
                    set(state) == {"mode", "system_required", "requested_flags", "previous_flags"},
                    "Saved Windows execution-state metadata differs")
    first_raw_file = {method: None for method in METHODS}
    for row in rows:
        expected_file = (f"{row.get('method')}-{row.get('kind')}-"
                         f"{row.get('round', '1')}.json.gz")
        if row.get("status") != "complete" and not row.get("file"):
            proof._need(row.get("status") in ("error", "not-run"),
                        "Saved call status is invalid")
            proof._need(type(row.get("error")) is str and bool(row["error"]),
                        "Failed call must retain an error")
            continue
        proof._need(row.get("file") == expected_file and
                    type(row.get("metadata")) is dict,
                    "Saved call evidence path or metadata is malformed")
        raw = _bounded_gzip(output / row["file"])
        with (output / row["file"]).open("rb") as compressed_file:
            compressed = compressed_file.read(MAX_GZIP_BYTES + 1)
        proof._need(len(compressed) <= MAX_GZIP_BYTES and
                    hashlib.sha256(compressed).hexdigest() == row.get("gzip_sha256"),
                    "Saved compressed report hash differs")
        proof._need(row.get("raw_bytes") == len(raw) and
                    row.get("gzip_bytes") == (output / row["file"]).stat().st_size,
                    "Saved call byte counts differ")
        proof._need(hashlib.sha256(raw).hexdigest() == row["metadata"]["raw_sha256"],
                    "Saved measured raw hash differs")
        measured = _validate_raw(raw, row["method"], expected)
        proof._need(row["status"] in ("complete", "error") and
                    row.get("quality_target_met") is measured["quality_target_met"] and
                    row["report_artifact_sha256"] == measured["artifact_sha256"] and
                    row["metadata"]["allocation_trace"] is (row["kind"] == "allocation"),
                    "Saved call metadata differs from raw report")
        metadata = row["metadata"]
        proof._need(type(metadata.get("allocation_trace")) is bool and
                    metadata["allocation_trace"] is (row["kind"] == "allocation") and
                    metadata.get("artifact_sha256") == measured["artifact_sha256"] and
                    metadata.get("quality_target_met") is measured["quality_target_met"] and
                    type(metadata.get("runtime")) is dict and
                    metadata["runtime"].get("python") == report["runtime"]["python"] and
                    metadata["runtime"].get("platform") == report["runtime"]["platform"] and
                    metadata["runtime"].get("implementation") == report["runtime"]["implementation"],
                    "Saved helper metadata disagrees with report or runtime")
        _validate_utc(metadata.get("started_at_utc"), "sample start")
        _validate_utc(metadata.get("finished_at_utc"), "sample completion")
        if row.get("status") == "complete":
            proof._need(row.get("source_after_call") == before,
                        "Completed call source snapshot differs")
        proof._need(type(metadata.get("wall_seconds")) in (int, float) and
                    math.isfinite(metadata["wall_seconds"]) and metadata["wall_seconds"] >= 0 and
                    type(metadata.get("process_seconds")) in (int, float) and
                    math.isfinite(metadata["process_seconds"]) and metadata["process_seconds"] >= 0 and
                    (type(metadata.get("python_traced_peak_bytes")) is int and
                     metadata["python_traced_peak_bytes"] >= 0 if row["kind"] == "allocation" else
                     metadata.get("python_traced_peak_bytes") is None),
                    "Saved time or traced-allocation metrics are malformed")
        first_file = first_raw_file[row["method"]]
        if first_file is None:
            first_raw_file[row["method"]] = row["file"]
        else:
            prior = _bounded_gzip(output / first_file)
            try:
                proof._need(prior == raw, f"Repeated {row['method']} raw reports differ")
            finally:
                prior = None
    expected_files = {row["file"] for row in rows if row.get("file")}
    proof._need({item.name for item in output.iterdir()} == expected_files | {"index.json"},
                "Saved measurement directory contains unexpected evidence files")
    summary = _summary(rows)
    proof._need(proof._typed(report.get("summary")) == proof._typed(summary),
                "Saved timing/allocation summary differs")
    expected_status = ("complete" if not report.get("validation_errors") and
                       all(row.get("status") == "complete" for row in rows) else "error")
    for row in rows:
        if row.get("status") == "error":
            proof._need(row.get("error") in report["validation_errors"],
                        "Saved row error is absent from validation errors")
    if any(row.get("status") == "not-run" for row in rows):
        proof._need(bool(report["validation_errors"]),
                    "Unrun rows lack a retained run failure")
    proof._need(report.get("status") == expected_status,
                "Saved measurement status does not match its retained calls")
    verification_after = _source_snapshot()
    proof._need(verification_after == current and
                verification_after["source_lf_sha256"] == before["source_lf_sha256"],
                "Current source changed during saved verification")
    return {"status": "saved-measurement-verified", "measurement_status": report["status"],
            "call_count": len(rows), "summary": summary,
            "source_revision": before["revision"], "index_sha256": report["index_sha256"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if args.verify:
        result = verify_saved(args.output)
    else:
        from contextlib import nullcontext
        if sys.platform == "win32":
            context = power.measurement_execution_state()
        else:
            context = nullcontext({"mode": "ordinary-process", "system_required": False})
        with context as execution_state:
            result = run(args.output, execution_state=execution_state)
    compact_result = {key: result.get(key) for key in
                      ("status", "measurement_status", "call_count", "summary",
                       "index_sha256") if key in result}
    if "validation_errors" in result:
        compact_result["validation_error_count"] = len(result["validation_errors"])
    print(json.dumps(compact_result, sort_keys=True))
    return 0 if result.get("status") in ("complete", "saved-measurement-verified") else 1


if __name__ == "__main__":
    raise SystemExit(main())
