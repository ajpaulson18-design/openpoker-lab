"""Authenticate a saved two-call diagnostic; this module performs no solve or replay."""
import gzip
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import re

from scripts import diagnose_flop_class_reweight_baseline as diagnostic
from scripts import benchmark_flop_class_reweight as evidence
from scripts import flop_public_classes as proof

ROOT = diagnostic.ROOT
PUBLICATION = ROOT / "benchmarks/results/flop-class-reweight-baseline-diagnostic-v1"
# Frozen completed diagnostic identities; current clean HEAD may advance.
RAW_INDEX_SHA256 = "aa18563a9f01c30faa52d8f2c72188892f3a838a9d25cb6c3bb663a28fda74d8"
INDEX_SHA256 = "919a16138442300a6125159fdc7a72767903896570c556396a0b8984a7a16a07"
EXPECTED_SOURCE_REVISION = "602a37eac96dfd146069e361f2501efff15b3576"
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_RAW_BYTES = 24 * 1024 * 1024
MAX_GZIP_BYTES = 8 * 1024 * 1024
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _need(key not in result, "Duplicate JSON field")
        result[key] = value
    return result


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8") + b"\n"


def _read_index(path):
    path = Path(path).absolute()
    _need(not path.is_symlink() and path.is_file() and
          all(not parent.is_symlink() for parent in path.parents),
          "Index must be a regular non-symlink file")
    _need(path.stat().st_size <= MAX_INDEX_BYTES, "Index exceeds size bound")
    with path.open("rb") as stream:
        raw = stream.read(MAX_INDEX_BYTES + 1)
    _need(len(raw) <= MAX_INDEX_BYTES and hashlib.sha256(raw).hexdigest() == RAW_INDEX_SHA256,
          "Index raw bytes differ from immutable pin")
    value = json.loads(raw, object_pairs_hook=_pairs,
                       parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    _need(type(value) is dict and value.get("index_sha256") == INDEX_SHA256 and
          proof._digest({key: item for key, item in value.items() if key != "index_sha256"}) ==
          INDEX_SHA256 and
          json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n" == raw,
          "Index canonical self-hash differs")
    return raw, value


def _read_gzip(directory, row):
    _need(type(row) is dict and set(row) ==
          {"path", "raw_bytes", "gzip_bytes", "raw_sha256", "gzip_sha256"},
          "Malformed gzip-file record")
    name = row["path"]
    _need(type(name) is str and Path(name).name == name and name.endswith(".json.gz") and
          type(row["raw_bytes"]) is int and 0 <= row["raw_bytes"] <= MAX_RAW_BYTES and
          type(row["gzip_bytes"]) is int and 0 <= row["gzip_bytes"] <= MAX_GZIP_BYTES and
          type(row["raw_sha256"]) is str and HEX64.fullmatch(row["raw_sha256"]) and
          type(row["gzip_sha256"]) is str and HEX64.fullmatch(row["gzip_sha256"]),
          "Unsafe or invalid gzip-file record")
    path = Path(directory) / name
    _need(not path.is_symlink() and path.is_file() and
          path.stat().st_size <= MAX_GZIP_BYTES, "Compressed evidence is unsafe or oversized")
    with path.open("rb") as stream:
        compressed = stream.read(MAX_GZIP_BYTES + 1)
    _need(len(compressed) <= MAX_GZIP_BYTES and len(compressed) == row["gzip_bytes"] and
          hashlib.sha256(compressed).hexdigest() == row["gzip_sha256"],
          "Compressed evidence size or digest differs")
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
        raw = stream.read(MAX_RAW_BYTES + 1)
    _need(len(raw) <= MAX_RAW_BYTES and len(raw) == row["raw_bytes"] and
          hashlib.sha256(raw).hexdigest() == row["raw_sha256"],
          "Raw report size or digest differs")
    report = json.loads(raw, object_pairs_hook=_pairs,
                        parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    _need(_canonical(report) == raw, "Raw report is not canonical JSON")
    return raw, report


def _utc(value):
    _need(type(value) is str, "Timestamp must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Malformed UTC timestamp") from None
    _need(parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed),
          "Timestamp must be timezone-aware UTC")
    return parsed


def _source(value, *, historical):
    _need(type(value) is dict and set(value) == {"revision", "status", "source_lf_sha256"} and
          type(value.get("revision")) is str and HEX40.fullmatch(value["revision"]) and
          (not historical or value["revision"] == EXPECTED_SOURCE_REVISION) and
          value.get("status") == "" and type(value.get("source_lf_sha256")) is dict and
          len(value["source_lf_sha256"]) == 35 and
          all(type(key) is str and type(digest) is str and HEX64.fullmatch(digest)
              for key, digest in value["source_lf_sha256"].items()),
          "Malformed or dirty 35-source snapshot")


def _runtime(index, protocol):
    runtime = index.get("runtime")
    gate = protocol["runtime_admission"]
    _need(type(runtime) is dict and set(runtime) == {"python", "implementation", "platform"} and
          all(type(value) is str and value for value in runtime.values()) and
          runtime["implementation"] == gate["implementation"] and
          runtime["python"].startswith(gate["python_version"]),
          "Recorded runtime differs from protocol admission")
    try:
        evidence._execution_state(index.get("execution_state"))
    except (TypeError, ValueError):
        raise ValueError("Recorded execution state is malformed") from None


def _duration(value, name, *, positive=False):
    _need(type(value) in (int, float) and math.isfinite(value) and
          (value > 0 if positive else value >= 0), f"Invalid {name}")


def _validate_events(events, sample_start, sample_end, protocol):
    targets = set(protocol["instrumented_boundaries"])
    _need(type(events) is list and 0 < len(events) <= protocol["event_limit"],
          "Phase-event inventory is empty or oversized")
    stack = []
    seen = {}
    times = {}
    sibling_groups = {}
    for expected_id, event in enumerate(events, 1):
        _need(type(event) is dict and set(event) == {
            "event_id", "parent_event_id", "phase", "started_at_utc", "finished_at_utc",
            "wall_seconds", "process_seconds", "status"} and
            type(event["event_id"]) is int and event["event_id"] == expected_id and
            event["phase"] in targets and event["status"] == "complete",
            "Malformed, unexpected, or failed phase event")
        started, finished = _utc(event["started_at_utc"]), _utc(event["finished_at_utc"])
        _need(started <= finished and sample_start <= started <= finished <= sample_end,
              "Phase interval is reversed or outside its sample")
        _duration(event["wall_seconds"], "phase wall duration")
        _duration(event["process_seconds"], "phase process duration")
        parent = event["parent_event_id"]
        if parent is None:
            stack.clear()
        else:
            _need(type(parent) is int and parent < expected_id,
                  "Phase parent ID is not an earlier event")
            while stack and stack[-1] != parent:
                stack.pop()
            _need(bool(stack) and stack[-1] == parent and parent in seen,
                  "Phase parent is not an active ancestor")
            ancestor = seen[parent]
            _need(event["wall_seconds"] <= ancestor["wall_seconds"] + 1e-9 and
                  event["process_seconds"] <= ancestor["process_seconds"] + 1e-9 and
                  times[parent][0] <= started <= finished <= times[parent][1],
                  "Child escapes parent interval or inclusive duration is shorter")
        sibling_groups.setdefault(parent, []).append((started, finished))
        times[expected_id] = (started, finished)
        seen[expected_id] = event
        stack.append(expected_id)
    for intervals in sibling_groups.values():
        for previous, current in zip(intervals, intervals[1:]):
            _need(previous[1] <= current[0],
                  "Independent sibling/root phase intervals overlap or reverse order")
    _need({event["phase"] for event in events} == targets,
          "Phase profile omitted a preregistered boundary")


def _validate_sample(sample, expected, protocol, source_before, file_row, report, index_runtime,
                     run_start, run_finish):
    required = {"sample_id", "status", "phase_instrumentation", "allocation_trace", "events",
                "error", "source_before", "evidence_file", "training_calls", "measurement",
                "report_matches_pilot", "source_after"}
    _need(type(sample) is dict and set(sample) == required and
          sample["sample_id"] == expected["sample_id"] and sample["status"] == "complete" and
          sample["phase_instrumentation"] is expected["phase_instrumentation"] and
          sample["allocation_trace"] is expected["allocation_trace"] and sample["error"] is None and
          type(sample["training_calls"]) is int and sample["training_calls"] == 1 and
          sample["report_matches_pilot"] is True and
          proof._typed(sample["source_before"]) == proof._typed(source_before) and
          proof._typed(sample["source_after"]) == proof._typed(source_before) and
          file_row.get("path") == f"{expected['sample_id']}.json.gz" and
          proof._typed(sample["evidence_file"]) == proof._typed(file_row),
          "Sample scope, call count, source, or file pointer differs")
    measurement = sample["measurement"]
    fields = {"started_at_utc", "finished_at_utc", "wall_seconds", "process_seconds",
              "raw_sha256", "artifact_sha256", "quality_target_met", "allocation_trace",
              "python_traced_peak_bytes", "runtime"}
    _need(type(measurement) is dict and set(measurement) == fields and
          measurement["allocation_trace"] is expected["allocation_trace"] and
          measurement["raw_sha256"] == protocol["pilot"]["baseline_raw_sha256"] and
          measurement["artifact_sha256"] == protocol["pilot"]["baseline_artifact_sha256"] and
          measurement["quality_target_met"] is True and
          type(measurement.get("runtime")) is dict and
          proof._typed(measurement["runtime"]) == proof._typed(index_runtime) and
          proof._typed(measurement["runtime"]) == proof._typed({
              "python": measurement["runtime"].get("python"),
              "implementation": protocol["runtime_admission"]["implementation"],
              "platform": measurement["runtime"].get("platform")}) and
          measurement["runtime"].get("python", "").startswith(
              protocol["runtime_admission"]["python_version"]),
          "Measurement metadata or exact baseline parity differs")
    _duration(measurement["wall_seconds"], "sample wall duration", positive=True)
    _duration(measurement["process_seconds"], "sample CPU duration", positive=True)
    started, finished = _utc(measurement["started_at_utc"]), _utc(measurement["finished_at_utc"])
    _need(run_start <= started <= finished <= run_finish,
          "Sample interval is reversed or outside the diagnostic run")
    peak = measurement["python_traced_peak_bytes"]
    if expected["allocation_trace"]:
        _need(type(peak) is int and peak > 0, "Allocation sample lacks a positive traced peak")
        _need(sample["events"] == [], "Allocation sample contains phase events")
    else:
        _need(peak is None, "Phase sample must not carry an allocation trace peak")
        _validate_events(sample["events"], started, finished, protocol)
    _need(report.get("artifact_sha256") == protocol["pilot"]["baseline_artifact_sha256"] and
          file_row["raw_sha256"] == protocol["pilot"]["baseline_raw_sha256"],
          "Full saved report does not equal the authenticated baseline pilot")
    return started, finished


def verify(directory=PUBLICATION):
    original = Path(directory).absolute()
    _need(not original.is_symlink() and all(not item.is_symlink() for item in original.parents),
          "Publication path cannot traverse symlinks")
    directory = original.resolve()
    _need(directory.is_dir(), "Diagnostic publication directory is missing")
    index_path = directory / "index.json"
    raw_index, index = _read_index(index_path)
    _need(set(index) == {"schema_version", "protocol_id", "status", "created_at_utc",
          "finished_at_utc", "execution_state", "runtime", "protocol", "protocol_sha256",
          "preflight", "source_before", "source_after", "baseline", "samples", "training_calls",
          "errors", "index_sha256"} and type(index.get("schema_version")) is int and
          index["schema_version"] == 1 and
          index.get("protocol_id") == "fixed-flop-prior-baseline-diagnostic-v1" and
          index.get("status") == "complete" and index.get("errors") == [] and
          type(index.get("training_calls")) is int and index["training_calls"] == 2,
          "Diagnostic index is incomplete or has an unexpected schema")
    protocol_raw, protocol = diagnostic._protocol()
    requests, total = diagnostic._preflight(protocol)
    _need(proof._typed(index.get("protocol")) == proof._typed(protocol) and
          index.get("protocol_sha256") == hashlib.sha256(
              protocol_raw.replace(b"\r\n", b"\n")).hexdigest() and
          proof._typed(index.get("preflight")) == proof._typed(
              {**protocol["preflight"], "requests": requests}) and
          total == 150_215_912,
          "Saved frozen protocol or full-request preflight differs")
    _runtime(index, protocol)
    run_start, run_finish = _utc(index.get("created_at_utc")), _utc(index.get("finished_at_utc"))
    _need(run_start <= run_finish, "Diagnostic run UTC interval is reversed")
    source_before, source_after = index.get("source_before"), index.get("source_after")
    _source(source_before, historical=True)
    _source(source_after, historical=True)
    _need(proof._typed(source_before) == proof._typed(source_after),
          "Historical source snapshots differ")
    current_before = diagnostic._snapshot()
    _source(current_before, historical=False)
    _need(current_before["status"] == "" and
          current_before["source_lf_sha256"] == source_before["source_lf_sha256"],
          "Current clean source map differs from historical diagnostic")
    expected_base = {"raw_sha256": protocol["pilot"]["baseline_raw_sha256"],
                     "artifact_sha256": protocol["pilot"]["baseline_artifact_sha256"],
                     "quality_target_met": True}
    _need(proof._typed(index.get("baseline")) == proof._typed(expected_base),
          "Authenticated baseline receipt differs")
    expected_samples = protocol["samples"]
    _need(type(index.get("samples")) is list and len(index["samples"]) == 2 and
          [row.get("sample_id") for row in index["samples"]] ==
          [row["sample_id"] for row in expected_samples], "Sample inventory/order differs")
    expected_files = {f"{row['sample_id']}.json.gz" for row in expected_samples}
    _need({item.name for item in directory.iterdir()} == {"index.json", *expected_files},
          "Diagnostic artifact inventory differs")
    file_rows = [sample.get("evidence_file") for sample in index["samples"]]
    _need({row.get("path") for row in file_rows if type(row) is dict} == expected_files,
          "Diagnostic gzip pointer inventory differs")
    report_hashes = []
    previous_sample_finish = run_start
    for sample, expected, file_row in zip(index["samples"], expected_samples, file_rows):
        raw, report = _read_gzip(directory, file_row)
        sample_start, sample_finish = _validate_sample(
            sample, expected, protocol, source_before, file_row, report, index["runtime"],
            run_start, run_finish)
        _need(previous_sample_finish <= sample_start,
              "Samples are not sequential in the recorded order")
        previous_sample_finish = sample_finish
        report_hashes.append((hashlib.sha256(raw).hexdigest(), report["artifact_sha256"]))
        del raw, report
    _need(all(raw_sha == protocol["pilot"]["baseline_raw_sha256"] and
              artifact_sha == protocol["pilot"]["baseline_artifact_sha256"]
              for raw_sha, artifact_sha in report_hashes),
          "A complete diagnostic policy differs from the baseline pilot bytes")
    _need(previous_sample_finish <= run_finish,
          "Final sample finishes after the diagnostic run")
    final_raw, _ = _read_index(index_path)
    _need(final_raw == raw_index, "Diagnostic index changed during authentication")
    for file_row in file_rows:
        _read_gzip(directory, file_row)
    current_after = diagnostic._snapshot()
    _source(current_after, historical=False)
    _need(proof._typed(current_after) == proof._typed(current_before),
          "Current source HEAD/status/map changed during authentication")
    return {"status": "saved-baseline-diagnostic-authenticated", "samples": 2,
            "training_calls": 0, "recorded_training_calls": 2,
            "phase_events": len(index["samples"][0]["events"]),
            "allocation_peak_bytes": index["samples"][1]["measurement"][
                "python_traced_peak_bytes"],
            "index_sha256": INDEX_SHA256,
            "interpretation": "Saved single-call observations only; no speed, RSS, or memory-advantage claim."}


def main():
    print(json.dumps(verify(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
