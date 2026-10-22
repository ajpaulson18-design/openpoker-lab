"""Authenticate one immutable instrumented fixed-flop phase profile."""
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

from scripts import benchmark_flop_class_cost as cost
from scripts import profile_flop_class_phases as profile
from scripts import flop_class_compact_budget as budget
from scripts import flop_public_classes as proof


PUBLICATION = (Path(__file__).resolve().parents[1] /
               "benchmarks/results/flop-class-phase-profile-v1")
EXPECTED_REVISION = "369436002791813e3983104f63e8131b5d3aa0e1"
INDEX_RAW_SHA256 = "ec839f707af9c03ec1247d4df25f8c6675901b0823f93b19fcb1390e31fea7a4"
INDEX_SHA256 = "58a39f78e9f8f3e18ae91d9e5538369bd259ea962a742c860623b174641e8f8f"
MAX_INDEX_BYTES = 4 * 1024 * 1024
MAX_GZIP_BYTES = 8 * 1024 * 1024
EXPECTED_REQUEST = {"method": "class-560", "iterations": 560}
REQUIRED_ROOT_PHASES = ("compact.publication.verify", "base._training_inputs",
                        "cfr_plus.train", "policy.canonicalize_binary_rows",
                        "proof.audit_policy")


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _need(key not in result, "Duplicate phase-profile JSON field")
        result[key] = value
    return result


def _read_index(directory):
    directory = Path(directory)
    path = directory / "index.json"
    _need(not directory.is_symlink() and not path.is_symlink() and path.is_file() and
          path.stat().st_size <= MAX_INDEX_BYTES,
          "Invalid bounded phase-profile index")
    with path.open("rb") as stream:
        raw = stream.read(MAX_INDEX_BYTES + 1)
    _need(len(raw) <= MAX_INDEX_BYTES, "Phase-profile index exceeds size bound")
    _need(hashlib.sha256(raw).hexdigest() == INDEX_RAW_SHA256,
          "Immutable phase-profile index bytes differ")
    report = json.loads(raw, object_pairs_hook=_pairs,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    _need(type(report) is dict, "Phase-profile index must be an object")
    unsigned = {key: value for key, value in report.items() if key != "index_sha256"}
    digest = proof._digest(unsigned)
    _need(report.get("index_sha256") == INDEX_SHA256 == digest,
          "Phase-profile canonical index checksum differs")
    return raw, report


def _utc(value):
    _need(type(value) is str and bool(value), "Malformed phase-profile UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Malformed phase-profile UTC timestamp") from exc
    _need(parsed.tzinfo is not None and parsed.utcoffset() is not None and
          parsed.utcoffset().total_seconds() == 0,
          "Phase-profile timestamp must be aware UTC")


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _read_gzip(path):
    _need(not path.is_symlink() and path.is_file() and
          path.stat().st_size <= MAX_GZIP_BYTES,
          "Invalid bounded phase-profile gzip")
    with path.open("rb") as stream:
        raw = stream.read(MAX_GZIP_BYTES + 1)
    _need(len(raw) <= MAX_GZIP_BYTES, "Phase-profile gzip exceeds size bound")
    return raw


def _validate_events(events, protocol):
    names = protocol["instrumented_boundaries"]
    _need(type(events) is list and len(events) <= protocol["event_limit"],
          "Phase event ledger is malformed or oversized")
    stack = []
    for expected_id, event in enumerate(events, 1):
        _need(type(event) is dict and type(event.get("event_id")) is int and
              event["event_id"] == expected_id and event.get("phase") in names and
              event.get("status") == "complete" and
              (event.get("parent_event_id") is None or
               type(event.get("parent_event_id")) is int),
              "Malformed phase event identity, parent, phase, or status")
        parent = event["parent_event_id"]
        if parent is None:
            stack.clear()
        else:
            while stack and stack[-1] != parent:
                stack.pop()
            _need(bool(stack), "Phase event parent is not an active ancestor")
        _utc(event.get("started_at_utc"))
        _utc(event.get("finished_at_utc"))
        _need(_number(event.get("wall_seconds")) and
              _number(event.get("process_seconds")),
              "Malformed phase event timing")
        stack.append(expected_id)
    roots = [event["phase"] for event in events if event["parent_event_id"] is None]
    _need(all(roots.count(phase) == 1 for phase in REQUIRED_ROOT_PHASES),
          "Required root phase event inventory differs")
    return [{"phase": event["phase"], "wall_seconds": event["wall_seconds"],
             "process_seconds": event["process_seconds"]}
            for event in events if event["parent_event_id"] is None]


def verify(directory=PUBLICATION):
    directory = Path(directory)
    raw_index, report = _read_index(directory)
    protocol = profile._protocol()
    _need(proof._typed(report.get("protocol")) == proof._typed(protocol),
          "Saved phase-profile protocol differs")
    _need(report.get("protocol_id") == protocol["protocol_id"] and
          report.get("status") == "complete" and report.get("errors") == [],
          "Phase profile is incomplete or has retained errors")
    _need(proof._typed(report.get("request")) == proof._typed(EXPECTED_REQUEST) and
          type(report.get("admission")) is dict and
          proof._typed(report["admission"]) == proof._typed(
              budget.admit_compact_request(560)),
          "Phase-profile request or full-request admission differs")
    _utc(report.get("created_at_utc"))
    _utc(report.get("finished_at_utc"))
    before, after = report.get("source_before"), report.get("source_after")
    _need(type(before) is dict and proof._typed(before) == proof._typed(after) and
          before.get("revision") == EXPECTED_REVISION and before.get("status") == "",
          "Phase-profile source revision or before/after snapshots differ")
    current_before = profile._snapshot()
    _need(proof._typed(current_before["source_lf_sha256"]) ==
          proof._typed(before["source_lf_sha256"]),
          "Current phase-profile source manifest differs")
    state = report.get("execution_state")
    _need(type(state) is dict, "Phase-profile execution state is missing")
    if state.get("mode") in ("ordinary-process", "direct-call"):
        _need(state == {"mode": state["mode"], "system_required": False},
              "Malformed ordinary phase-profile execution state")
    else:
        _need(state.get("mode") == "windows-benchmark-thread" and
              state.get("system_required") is True and
              type(state.get("requested_flags")) is int and
              state["requested_flags"] == 0x80000001 and
              type(state.get("previous_flags")) is int and
              state["previous_flags"] > 0 and
              set(state) == {"mode", "system_required", "previous_flags",
                             "requested_flags"},
              "Malformed Windows phase-profile execution state")
    _need(report.get("instrumentation_overhead") ==
          protocol.get("instrumentation_overhead"),
          "Phase-profile instrumentation overhead differs from protocol")
    _need(type(report.get("measurement")) is dict,
          "Phase-profile measurement metadata is missing")
    metadata = report["measurement"]
    _utc(metadata.get("started_at_utc"))
    _utc(metadata.get("finished_at_utc"))
    _need(_number(metadata.get("wall_seconds")) and
          _number(metadata.get("process_seconds")) and
          metadata.get("allocation_trace") is False and
          metadata.get("python_traced_peak_bytes") is None,
          "Malformed complete-call helper metadata")
    runtime = metadata.get("runtime")
    _need(type(runtime) is dict and set(runtime) ==
          {"python", "implementation", "platform"} and
          all(type(runtime[field]) is str and runtime[field]
              for field in ("python", "implementation", "platform")),
          "Malformed complete-call runtime metadata")
    events_summary = _validate_events(report.get("events"), protocol)
    filename = report.get("raw_file")
    _need(type(filename) is str and filename == "class-560-profiled.json.gz" and
          {item.name for item in directory.iterdir()} == {"index.json", filename},
          "Phase-profile payload inventory differs")
    payload_path = directory / filename
    raw = cost._bounded_gzip(payload_path)
    gzip_bytes = _read_gzip(payload_path)
    _need(hashlib.sha256(gzip_bytes).hexdigest() == report.get("gzip_sha256") and
          hashlib.sha256(raw).hexdigest() == report.get("raw_sha256") ==
          metadata.get("raw_sha256"),
          "Phase-profile raw or compressed payload hash differs")
    expected = cost._pilot_expectations()
    measured = cost._validate_raw(raw, "class-560", expected)
    _need(metadata.get("artifact_sha256") == measured.get("artifact_sha256") and
          metadata.get("quality_target_met") is measured.get("quality_target_met") and
          measured.get("quality_target_met") is True,
          "Profile helper metadata or quality differs from the compact pilot")
    after_index, _ = _read_index(directory)
    after_raw = cost._bounded_gzip(payload_path)
    after_gzip = _read_gzip(payload_path)
    _need(after_index == raw_index and after_raw == raw and
          hashlib.sha256(after_gzip).hexdigest() == report["gzip_sha256"],
          "Phase-profile evidence changed during verification")
    _need(proof._typed(profile._snapshot()) == proof._typed(current_before),
          "Current phase-profile snapshot changed during verification")
    return {"status": "saved-phase-profile-verified", "source_revision": EXPECTED_REVISION,
            "request": EXPECTED_REQUEST, "root_phase_events": events_summary,
            "index_raw_sha256": INDEX_RAW_SHA256, "index_sha256": INDEX_SHA256}


def main():
    print(json.dumps(verify(), sort_keys=True))


if __name__ == "__main__":
    main()
