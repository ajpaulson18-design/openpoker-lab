"""Authenticate the saved three-prior CFR+ pilot; performs no replay or training."""
import gzip
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
import re

from scripts import benchmark_flop_class_reweight_cfrplus as runner
from scripts import benchmark_flop_class_reweight as evidence
from scripts import benchmark_flop_class_cost as cost
from scripts import flop_public_classes as proof
from scripts import verify_flop_class_reweight_cfrplus as replay
from scripts import flop_class_policy as policy

ROOT = runner.ROOT
PUBLICATION = ROOT / "benchmarks/results/flop-class-reweight-cfrplus-pilot-v1"
REPLAY_RECEIPT = ROOT / "benchmarks/results/flop-class-reweight-cfrplus-saved-replay-v1.json"
INDEX_RAW_SHA256 = "8ee047f7b7da7f25787abf4f8a8d2f6dcfcb490e543a0b43b11e10a526c93789"
INDEX_SHA256 = "88805b420346575c2991210bd7fc20c4f562962245347d6c128b4071604678e6"
REPLAY_RECEIPT_RAW_SHA256 = "5fec00b8b777056aaabafa960df8e1f45dd51bb16db11dd05bf92d1ebbf85e1e"
REPLAY_RECEIPT_SHA256 = "edae03220d98c65828d9033404c0c9b4fa89217e9d96c4ffb39de482c475fe2e"
EXPECTED_REVISION = "e1a7b1ac3a372b48ba9d3a2d9a6dd6418f4011c5"
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_RAW_BYTES = evidence.MAX_RAW_BYTES
MAX_GZIP_BYTES = evidence.MAX_GZIP_BYTES
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        _need(key not in out, "Duplicate JSON field")
        out[key] = value
    return out


def _canonical(value):
    return cost._canonical(value, newline=True)


def _read_index(path):
    original = Path(path).absolute()
    _need(not original.is_symlink() and original.is_file(), "Index must be a regular file")
    _need(all(not item.is_symlink() for item in original.parents), "Index path traverses symlink")
    _need(original.stat().st_size <= MAX_INDEX_BYTES, "Index exceeds size bound")
    with original.open("rb") as stream:
        raw = stream.read(MAX_INDEX_BYTES + 1)
    _need(len(raw) <= MAX_INDEX_BYTES and hashlib.sha256(raw).hexdigest() == INDEX_RAW_SHA256,
          "Raw index bytes differ from immutable pin")
    value = json.loads(raw, object_pairs_hook=_pairs,
                       parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    _need(type(value) is dict and value.get("index_sha256") == INDEX_SHA256 and
          proof._digest({k: v for k, v in value.items() if k != "index_sha256"}) == INDEX_SHA256 and
          json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n" == raw,
          "Canonical index identity differs")
    return raw, value


def _read_replay_receipt(path):
    path = Path(path).absolute()
    _need(not path.is_symlink() and path.is_file() and
          all(not parent.is_symlink() for parent in path.parents),
          "Replay receipt must be a regular non-symlink file")
    _need(path.stat().st_size <= MAX_INDEX_BYTES, "Replay receipt exceeds size bound")
    with path.open("rb") as stream:
        raw = stream.read(MAX_INDEX_BYTES + 1)
    _need(len(raw) <= MAX_INDEX_BYTES and
          hashlib.sha256(raw).hexdigest() == REPLAY_RECEIPT_RAW_SHA256,
          "Replay receipt raw bytes differ from immutable pin")
    value = json.loads(raw, object_pairs_hook=_pairs,
                       parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    _need(type(value) is dict, "Replay receipt must be a JSON object")
    unsigned = {key: item for key, item in value.items() if key != "receipt_sha256"}
    _need(type(value) is dict and value.get("receipt_sha256") == REPLAY_RECEIPT_SHA256 and
          proof._digest(unsigned) == REPLAY_RECEIPT_SHA256 and
          json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n" == raw,
          "Replay receipt canonical identity differs")
    return raw, value


def _read_gzip(directory, row):
    _need(type(row) is dict and set(row) ==
          {"path", "raw_bytes", "gzip_bytes", "raw_sha256", "gzip_sha256"},
          "Malformed report file record")
    name = row["path"]
    _need(type(name) is str and Path(name).name == name and name.endswith(".json.gz") and
          type(row["raw_bytes"]) is int and 0 <= row["raw_bytes"] <= MAX_RAW_BYTES and
          type(row["gzip_bytes"]) is int and 0 <= row["gzip_bytes"] <= MAX_GZIP_BYTES and
          type(row["raw_sha256"]) is str and HEX64.fullmatch(row["raw_sha256"]) and
          type(row["gzip_sha256"]) is str and HEX64.fullmatch(row["gzip_sha256"]),
          "Unsafe or malformed report file record")
    path = directory / name
    _need(not path.is_symlink() and path.stat().st_size <= MAX_GZIP_BYTES,
          "Compressed report is unsafe or too large")
    with path.open("rb") as stream:
        compressed = stream.read(MAX_GZIP_BYTES + 1)
    _need(len(compressed) <= MAX_GZIP_BYTES and len(compressed) == row["gzip_bytes"] and
          hashlib.sha256(compressed).hexdigest() == row["gzip_sha256"],
          "Compressed report size or hash differs")
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
        raw = stream.read(MAX_RAW_BYTES + 1)
    _need(len(raw) <= MAX_RAW_BYTES and len(raw) == row["raw_bytes"] and
          hashlib.sha256(raw).hexdigest() == row["raw_sha256"],
          "Raw report size or hash differs")
    report = json.loads(raw, object_pairs_hook=_pairs,
                        parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    _need(_canonical(report) == raw, "Report bytes are not canonical JSON")
    return raw, report


def _snapshot(value, *, historical=True):
    _need(type(value) is dict and set(value) == {"revision", "status", "source_lf_sha256"} and
          type(value["revision"]) is str and HEX40.fullmatch(value["revision"]) and
          (not historical or value["revision"] == EXPECTED_REVISION) and value["status"] == "" and
          type(value["source_lf_sha256"]) is dict and
          all(type(k) is str and type(v) is str and HEX64.fullmatch(v)
              for k, v in value["source_lf_sha256"].items()),
          "Malformed, dirty, or unexpected source snapshot")


def _utc(value):
    _need(type(value) is str, "Timestamp must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Malformed UTC timestamp") from None
    _need(parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed),
          "Timestamp must be timezone-aware UTC")
    return parsed


def _runtime(index):
    runtime = index.get("runtime")
    _need(type(runtime) is dict and set(runtime) == {"python", "implementation", "platform"} and
          all(type(v) is str and v for v in runtime.values()), "Malformed runtime metadata")
    state = index.get("execution_state")
    _need(type(state) is dict, "Malformed execution-state metadata")
    if state.get("mode") in ("ordinary-process", "direct-call"):
        _need(state == {"mode": state["mode"], "system_required": False},
              "Malformed ordinary execution-state metadata")
    else:
        _need(state.get("mode") == "windows-benchmark-thread" and
              state.get("system_required") is True and
              type(state.get("requested_flags")) is int and state["requested_flags"] == 0x80000001 and
              type(state.get("previous_flags")) is int and state["previous_flags"] > 0 and
              set(state) == {"mode", "system_required", "requested_flags", "previous_flags"},
              "Malformed Windows execution-state metadata")
    for key in ("wall_seconds", "process_seconds"):
        _need(type(index.get(key)) in (int, float) and math.isfinite(index[key]) and
              index[key] >= 0, "Malformed overall elapsed time")


def _validate_saved_policy(report, receipt):
    _need(type(report.get("training_calls")) is int and report["training_calls"] == 1 and
          proof._typed(report.get("proof_receipt")) == proof._typed(receipt),
          "Saved report trainer count or no-training proof receipt differs")
    payload = report.get("physical_policy")
    _need(type(payload) is dict and type(payload.get("strategy")) is list,
          "Saved full physical policy is malformed")
    raw_rows = replay._raw_rows(report.get("raw_class_policy"))
    rows, normalization = policy.canonicalize_binary_rows(raw_rows)
    _need(proof._typed(report.get("normalization")) == proof._typed(normalization),
          "Saved raw-row normalization record differs")
    exact, _ = replay._audit_shape(report.get("audit"), payload, rows)
    met = exact["nash_conv"] <= Fraction(1, 200)
    _need(type(report.get("quality_target")) is float and report["quality_target"] == 0.005 and
          type(report.get("quality_target_met")) is bool and report["quality_target_met"] is met,
          "Saved quality target flag differs from the full exact audit")
    return met


def _validate_replay_receipt(receipt, pilot_raw, pilot_index, directory):
    """Validate recorded prior replays; never invoke a replay or solver here."""
    _need(type(receipt) is dict and
          receipt.get("schema_version") == "fixed-flop-prior-saved-replay-v1" and
          receipt.get("status") == "complete" and receipt.get("errors") == [] and
          type(receipt.get("blocked_training_attempts")) is int and
          receipt["blocked_training_attempts"] == 0 and
          receipt.get("pilot_index_raw_sha256") == hashlib.sha256(pilot_raw).hexdigest() and
          receipt.get("pilot_index_sha256") == INDEX_SHA256 and
          type(receipt.get("execution_method")) is str and receipt["execution_method"],
          "Replay receipt status, block count, or pilot binding differs")
    _need(type(receipt.get("training_calls")) is int and receipt["training_calls"] == 0,
          "Replay receipt reports a training call")
    runtime = receipt.get("runtime")
    _need(type(runtime) is dict and set(runtime) == {"python", "implementation", "platform"} and
          all(type(value) is str and value for value in runtime.values()) and
          type(receipt.get("wall_seconds")) in (int, float) and
          math.isfinite(receipt["wall_seconds"]) and receipt["wall_seconds"] >= 0,
          "Replay receipt runtime or elapsed metadata differs")
    recorded_source = pilot_index["source_before"]
    replay_before, replay_after = receipt.get("source_before"), receipt.get("source_after")
    _snapshot(replay_before)
    _snapshot(replay_after)
    _need(proof._typed(replay_before) == proof._typed(replay_after) ==
          proof._typed(recorded_source), "Replay receipt source checkpoint differs")
    created, finished = _utc(receipt.get("created_at_utc")), _utc(receipt.get("finished_at_utc"))
    _need(_utc(pilot_index.get("finished_at_utc")) <= created <= finished,
          "Replay receipt chronology must follow the completed pilot")
    replays = receipt.get("replays")
    _need(type(replays) is list and len(replays) == 3 and
          [row.get("case_id") for row in replays] == list(runner.CASES),
          "Replay receipt case inventory differs")
    files = {row["path"]: row for row in pilot_index["files"]}
    prior_finished = created
    for row in replays:
        case_id = row["case_id"]
        _need(row.get("status") == "complete" and
              proof._typed(row.get("source_before")) == proof._typed(recorded_source) and
              proof._typed(row.get("source_after")) == proof._typed(recorded_source),
              "Replay status or per-call source snapshot differs")
        started, ended = _utc(row.get("started_at_utc")), _utc(row.get("finished_at_utc"))
        _need(prior_finished <= started <= ended <= finished,
              "Replay receipt UTC case order differs")
        prior_finished = ended
        for key in ("wall_seconds", "process_seconds"):
            _need(type(row.get(key)) in (int, float) and math.isfinite(row[key]) and
                  row[key] >= 0, "Replay elapsed metadata is malformed")
        expected_file = files.get(f"{case_id}-560.json.gz")
        _need(proof._typed(row.get("input_file")) == proof._typed(expected_file),
              "Replay input file does not bind to the authenticated pilot report")
        _, report = _read_gzip(directory, expected_file)
        result = row.get("result")
        _need(type(result) is dict and type(result.get("training_calls")) is int and
              result["training_calls"] == 0,
              "Saved replay result records a training call")
        _need(type(result) is dict and
              result.get("status") == "saved-reweighted-policy-physically-verified" and
              result.get("case_id") == case_id and
              type(result.get("iterations")) is int and result["iterations"] == 560 and
              type(result.get("class_rows")) is int and result["class_rows"] == 466 and
              type(result.get("physical_rows")) is int and result["physical_rows"] == 16912 and
              type(result.get("nash_conv")) is float and math.isfinite(result["nash_conv"]) and
              result["nash_conv"] == float(Fraction(report["audit"]["exact_metrics"]["nash_conv"])) and
              type(result.get("quality_target_met")) is bool and
              result["quality_target_met"] is report["quality_target_met"] and
              result.get("artifact_sha256") == report.get("artifact_sha256"),
              "Replay result differs from its saved authenticated policy report")
        del report
    return {"status": "saved-replay-receipt-authenticated", "replays": 3,
            "training_calls": 0, "receipt_sha256": receipt["receipt_sha256"]}


def verify(directory=PUBLICATION, replay_receipt_path=REPLAY_RECEIPT):
    """Authenticate pilot and optional saved receipt; performs no replay/model work."""
    original = Path(directory).absolute()
    _need(not original.is_symlink() and all(not p.is_symlink() for p in original.parents),
          "Evidence path cannot traverse symlinks")
    directory = original.resolve()
    _need(directory.is_dir(), "Evidence directory is missing")
    index_path = directory / "index.json"
    _need(not index_path.is_symlink(), "Index cannot be a symlink")
    raw_index, index = _read_index(index_path)
    _need(type(index.get("schema_version")) is int and index["schema_version"] == 1 and
          index.get("protocol_id") == "fixed-flop-prior-cfrplus-pilot-v1" and
          index.get("status") == "complete" and index.get("errors") == [] and
          type(index.get("training_calls")) is int and index["training_calls"] == 3 and
          type(index.get("solve_calls_started")) is int and index["solve_calls_started"] == 3 and
          type(index.get("solve_calls_completed")) is int and index["solve_calls_completed"] == 3,
          "Pilot is incomplete, errored, or has incorrect call counts")
    spec = runner._protocol()
    _need(proof._typed(index.get("protocol")) == proof._typed(spec),
          "Saved frozen protocol differs")
    requests = runner._preflight(spec)
    _need(proof._typed(index.get("preflight")) == proof._typed(spec["preflight"]),
          "Saved preflight differs")
    _need(type(index.get("cases")) is list and len(index["cases"]) == 3 and
          [row.get("case_id") for row in index["cases"]] == list(runner.CASES),
          "Case inventory differs")
    _need(type(index.get("files")) is list and len(index["files"]) == 3 and
          {row.get("path") for row in index["files"]} ==
          {f"{case}-560.json.gz" for case in runner.CASES} and
          {item.name for item in directory.iterdir()} ==
          {"index.json", *(f"{case}-560.json.gz" for case in runner.CASES)},
          "Evidence file inventory differs")

    source_before, source_after = index.get("source_before"), index.get("source_after")
    _snapshot(source_before)
    _snapshot(source_after)
    _need(proof._typed(source_before) == proof._typed(source_after) and
          len(source_before["source_lf_sha256"]) == 31,
          "Overall frozen 31-source snapshots differ")
    current_before = runner._snapshot()
    _snapshot(current_before, historical=False)
    _need(current_before["source_lf_sha256"] == source_before["source_lf_sha256"],
          "Current LF source map differs from historical run")
    created, finished = _utc(index.get("created_at_utc")), _utc(index.get("finished_at_utc"))
    _need(created <= finished, "Run UTC chronology is reversed")
    _runtime(index)
    for key in ("training_calls",):
        _need(type(index.get(key)) is int and index[key] == 3, "Top-level training call count differs")

    world_ids = runner._proof_world_identities()
    old = runner._baseline_reference(spec)
    proof_receipt = runner.publication.verify()
    historical = runner.publication.old_publication.authenticate()
    expected_guards = historical.get("forbidden_production_calls")
    _need(type(expected_guards) is dict and len(expected_guards) == 41 and
          all(type(k) is str and type(v) is int and v == 0
              for k, v in expected_guards.items()),
          "Historical 41-key authority inventory differs")
    filemap = {row["path"]: row for row in index["files"]}
    requests_by_case = {case_id: (iterations, admission)
                        for case_id, iterations, admission in requests}
    prior_finished = created
    for row in index["cases"]:
        case_id = row["case_id"]
        iterations, admission = requests_by_case[case_id]
        _need(type(row.get("iterations")) is int and row["iterations"] == 560 and
              row.get("status") == "complete" and
              type(row.get("training_calls")) is int and row["training_calls"] == 1,
              "Case request, status, or actual call count differs")
        _need(proof._typed(row.get("admission")) == proof._typed(admission),
              "Case logical-work admission differs")
        before, after = row.get("source_before"), row.get("source_after")
        _snapshot(before)
        _snapshot(after)
        _need(proof._typed(before) == proof._typed(after) == proof._typed(source_before),
              "Per-call source snapshots differ")
        started, ended = _utc(row.get("started_at_utc")), _utc(row.get("finished_at_utc"))
        _need(prior_finished <= started <= ended <= finished,
              "Per-call UTC chronology or call order differs")
        prior_finished = ended
        for key in ("wall_seconds", "process_seconds"):
            _need(type(row.get(key)) in (int, float) and math.isfinite(row[key]) and row[key] >= 0,
                  "Malformed per-call elapsed metadata")
        entry = row.get("evidence_file")
        expected_name = f"{case_id}-560.json.gz"
        _need(type(entry) is dict and entry == filemap.get(expected_name),
              "Case evidence pointer differs")
        _, report = _read_gzip(directory, entry)
        met = _validate_saved_policy(report, proof_receipt)
        summary = runner._validate_report(case_id, iterations, admission, report, world_ids[case_id])
        _need(proof._typed(summary) == proof._typed(row.get("audit_summary")),
              "Case summary differs from full saved audit")
        _need(row["audit_summary"].get("quality_target_met") is met,
              "Saved per-case quality outcome differs from full report")
        for guard_key in ("preparation_forbidden_calls", "diagnostic_forbidden_calls"):
            guards = report.get(guard_key)
            _need(type(guards) is dict and set(guards) == set(expected_guards) and
                  all(type(value) is int and value == 0 for value in guards.values()),
                  "Per-call 41-key authority guard differs or is nonzero")
        if case_id == "baseline":
            runner._compare_baseline(report, old, spec)
            _need(row.get("old_baseline_semantics_equal") is True,
                  "Index does not retain successful old-pilot baseline calibration")
        del report

    for row in index["files"]:
        _read_gzip(directory, row)
    final_raw, _ = _read_index(index_path)
    _need(final_raw == raw_index, "Index changed during saved authentication")
    replay_summary = None
    if replay_receipt_path is not None:
        receipt_raw, receipt = _read_replay_receipt(replay_receipt_path)
        replay_summary = _validate_replay_receipt(receipt, raw_index, index, directory)
        final_receipt_raw, _ = _read_replay_receipt(replay_receipt_path)
        _need(final_receipt_raw == receipt_raw, "Replay receipt changed during authentication")
    current_after = runner._snapshot()
    _snapshot(current_after, historical=False)
    _need(proof._typed(current_after) == proof._typed(current_before),
          "Current clean HEAD/status/source snapshot changed during saved authentication")
    return {"status": "saved-reweighted-cfrplus-pilot-authenticated", "cases": 3,
            "training_calls": 0, "recorded_pilot_training_calls": 3,
            "source_revision": source_before["revision"],
            "index_sha256": INDEX_SHA256,
            "replay_receipt": replay_summary,
            "quality_target_met": {row["case_id"]: row["audit_summary"]["quality_target_met"]
                                   for row in index["cases"]}}


def main():
    print(json.dumps(verify(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
