"""Authenticate the saved seven-stage AK/KK source-count observation.

This checks immutable saved bytes and invokes only the published saved-AA and
five-card report verifiers. It does not rebuild either counter or enumerate,
rank, train, or claim an equity/strategy result.
"""
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

from scripts import benchmark_preflop_ak_kk_basis as evidence
from scripts import benchmark_preflop_jj_kk_basis as retained
from scripts import preflop_ak_kk_basis_plan as planner
from scripts import preflop_five_count_reference as reference
from scripts import validate_preflop_five_reference as five


ROOT = evidence.ROOT
PUBLICATION = ROOT / "benchmarks/results/preflop-ak-kk-basis-v1"
INDEX_BYTES = 6_080
INDEX_RAW_SHA256 = "fb08e891b9879d1fb17671a6c71c6019cd0bbb1fdc21fc120737773a9c47ffad"
INDEX_ARTIFACT_SHA256 = "2424f97058a3be821e5e53a9aaaabcf6e832fc1fee23af5e4c97173bac043ea0"
REPORT_BYTES = 807_681
REPORT_RAW_SHA256 = "89f2720092e659ccd982665cf4fdaa1d33448e30bb25a9321f9111410942e7a7"
REPORT_ARTIFACT_SHA256 = "4f64aea64d85a77153187dfb0b8c537b173674cc542d38200133c5e01aaed982"
CONFORMANCE_BYTES = 379_343
CONFORMANCE_RAW_SHA256 = "4287737d17713847ee9d58b3dbeb83c1da40adaf06456859d04e3b88c7e9497c"
CONFORMANCE_ARTIFACT_SHA256 = "3f490292c996068004f5918da4afa2bd7d7b1dd8f0dc1fdc1ef612e486185e8a"
FROZEN_REVISION = "4aac2c22fa7066fa2d0a896cbd8b0c77800ccd1b"
AA_RAW_SHA256 = "bb906c0dac2deca79753e48548b5c3c1b7b9cedd92ba3574da934154713b5419"
AA_ARTIFACT_SHA256 = "2ae377e0af6d55491c667d574f41482f2ea6911ba8565ade3b9c8406b54010f7"
ALL_FIVE_BYTES = 15_593_760
ALL_FIVE_SHA256 = "7dfd1ff4ed2761fef77db70b170fdae750cf7c162932087e30163037e4e78e52"
MAX_INDEX_BYTES = 65_536
MAX_REPORT_BYTES = 4_194_304
MAX_BASIS_BYTES = 1_000_000
MAX_STDOUT_BYTES = 16_777_216
MAX_STDERR_BYTES = 65_536
MAPPED_BYTES = 1_188_501
CORPUS_TOTAL_BYTES = 1_194_581

STAGES = evidence.EXPECTED_STAGES
CONTEXT = {
    "AGENTS.md": ("ceb9c16b5e46078e0126eb8b3070eb8d145bd059b76ab4c52632fc0dba23216a",
                  "benchmarks/sources/preflop-ak-kk-context-freeze-v1/AGENTS.md.txt", 46_689),
    "docs/engineering/CURRENT_STATE.md": (
        "15683e6e74cab038affd55b7f4a1256ff60aedd704ca9379bf37de056d8d52ac",
        "benchmarks/sources/preflop-ak-kk-context-freeze-v1/CURRENT_STATE.md.txt", 41_003),
    "docs/solver-progress.md": (
        "d385413dcb8e6e8022a4ca2b0d6e38f1cd1b11b46ae79a84314d4df649c72566",
        "benchmarks/sources/preflop-ak-kk-context-freeze-v1/solver-progress.md.txt", 109_685),
    "docs/turn-class-tail.md": (
        "15d7b146d082df2727783c429eeb37980988db0639bb4630847755650d574b6b",
        "benchmarks/sources/preflop-ak-kk-context-freeze-v1/turn-class-tail.md.txt", 8_615),
}
REPORT_KEYS = {
    "aa_calibration_match", "admission", "artifact_sha256", "basis_authentication",
    "benchmark_id", "candidate_build_after", "candidate_build_before",
    "candidate_build_unchanged", "created_at_utc", "current_build_conformance",
    "errors", "independent_physical_count_rows", "native_capture_errors",
    "numerical_subprocess_calls", "profiles", "protocol_sha256", "reference_build_after",
    "reference_build_before", "reference_build_unchanged", "runtime", "schema_version",
    "source_after", "source_before", "source_unchanged", "specification", "status",
}
INDEX_KEYS = {"artifact_sha256", "benchmark_id", "conformance_artifact_sha256",
              "excluded_all_five_stdout", "files", "report_artifact_sha256",
              "schema_version", "source_revision", "streams"}


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Nonfinite JSON value: {value}")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Nonfinite JSON number")
    return number


def _json(raw):
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_reject_constant,
                      parse_float=_finite_float)


def _typed_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(
            _typed_equal(left[key], value) for key, value in right.items())
    if type(left) is list:
        return len(left) == len(right) and all(
            _typed_equal(a, b) for a, b in zip(left, right))
    return left == right


def _read(path, limit, *, size=None, sha256=None):
    path = Path(path)
    _need(not path.is_symlink() and path.is_file(), f"Missing or symlinked file: {path.name}")
    _need(path.stat().st_size <= limit and (size is None or path.stat().st_size == size),
          f"File size differs or exceeds bound: {path.name}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    _need(len(raw) <= limit and (size is None or len(raw) == size),
          f"File grew beyond bound while reading: {path.name}")
    if sha256 is not None:
        _need(hashlib.sha256(raw).hexdigest() == sha256, f"Raw file pin differs: {path.name}")
    return raw


def _digest(value):
    return retained._checksum(value)


def _artifact(value):
    return _digest({key: item for key, item in value.items() if key != "artifact_sha256"})


def _expected_files():
    expected = {"report.json": "report.json",
                "aa-conformance-report.json": "aa-conformance/report.json"}
    for stage in STAGES:
        for label, suffix in (("stderr", "stderr.txt"), ("stdout", "stdout.json")):
            if stage == "reference-all-five" and label == "stdout":
                continue
            expected[f"streams/{stage}.{suffix}"] = f"captured-native-streams/{stage}-{label}.bin"
    return expected


def _expected_stream_manifest():
    result = []
    for stage in STAGES:
        for label, suffix in (("stdout", "stdout.json"), ("stderr", "stderr.txt")):
            if stage == "reference-all-five" and label == "stdout":
                continue
            result.append({"label": label, "saved_path": f"streams/{stage}.{suffix}",
                           "stage": stage})
    return result


def _validate_index(root):
    raw = _read(root / "index.json", MAX_INDEX_BYTES,
                size=INDEX_BYTES, sha256=INDEX_RAW_SHA256)
    index = _json(raw)
    _need(type(index) is dict and set(index) == INDEX_KEYS and
          type(index.get("artifact_sha256")) is str and
          index["artifact_sha256"] == INDEX_ARTIFACT_SHA256 and
          _artifact(index) == INDEX_ARTIFACT_SHA256,
          "AK/KK index schema or canonical checksum differs")
    _need(type(index["schema_version"]) is int and index["schema_version"] == 1 and
          index["benchmark_id"] == "preflop-ak-kk-basis-v1" and
          index["source_revision"] == FROZEN_REVISION and
          index["report_artifact_sha256"] == REPORT_ARTIFACT_SHA256 and
          index["conformance_artifact_sha256"] == CONFORMANCE_ARTIFACT_SHA256,
          "AK/KK index generation or artifact links differ")
    dump = index["excluded_all_five_stdout"]
    _need(type(dump) is dict and set(dump) == {
          "bytes_observed_at_most_limit_plus_one", "bytes_retained", "capture_source",
          "over_bound", "path", "sha256"} and
          type(dump["bytes_retained"]) is int and dump["bytes_retained"] == ALL_FIVE_BYTES and
          type(dump["bytes_observed_at_most_limit_plus_one"]) is int and
          dump["bytes_observed_at_most_limit_plus_one"] == ALL_FIVE_BYTES and
          dump["capture_source"] == "file-backed-stream" and dump["over_bound"] is False and
          dump["path"] == "captured-native-streams/reference-all-five-stdout.bin" and
          dump["sha256"] == ALL_FIVE_SHA256,
          "External all-five binary exclusion receipt differs")
    files = index["files"]
    expected = _expected_files()
    _need(type(files) is dict and set(files) == set(expected),
          "AK/KK mapped artifact inventory differs")
    total = 0
    for relative, original in expected.items():
        row = files[relative]
        limit = MAX_REPORT_BYTES if relative in ("report.json", "aa-conformance-report.json") else (
            MAX_STDERR_BYTES if relative.endswith(".stderr.txt") else MAX_STDOUT_BYTES)
        _need(type(row) is dict and set(row) == {"bytes", "original_path", "sha256"} and
              type(row["bytes"]) is int and 0 <= row["bytes"] <= limit and
              type(row["original_path"]) is str and row["original_path"] == original and
              type(row["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is not None,
              f"Malformed mapped index entry: {relative}")
        total += row["bytes"]
    _need(total == MAPPED_BYTES and INDEX_BYTES + total == CORPUS_TOTAL_BYTES,
          "AK/KK corpus byte census differs")
    _need(_typed_equal(index["streams"], _expected_stream_manifest()),
          "AK/KK stream manifest order or mapping differs")
    return raw, index


def _inventory(root, index):
    _need(not root.is_symlink() and root.is_dir(), "AK/KK publication root is missing or symlinked")
    _need({entry.name for entry in root.iterdir()} ==
          {"index.json", "report.json", "aa-conformance-report.json", "streams"},
          "AK/KK publication root has unexpected entries")
    streams = root / "streams"
    _need(not streams.is_symlink() and streams.is_dir() and
          {entry.name for entry in streams.iterdir()} ==
          {Path(path).name for path in _expected_files() if path.startswith("streams/")},
          "AK/KK stream directory inventory differs")
    raw_files = {}
    for relative, row in index["files"].items():
        limit = MAX_REPORT_BYTES if relative in ("report.json", "aa-conformance-report.json") else (
            MAX_STDERR_BYTES if relative.endswith(".stderr.txt") else MAX_STDOUT_BYTES)
        raw_files[relative] = _read(root / relative, limit,
                                    size=row["bytes"], sha256=row["sha256"])
    _need(len(raw_files) == 15, "Expected exactly fifteen mapped AK/KK files")
    return raw_files


def _source_record(value):
    _need(type(value) is dict and set(value) == {"revision", "source_hashes", "status"} and
          type(value["revision"]) is str and value["revision"] == FROZEN_REVISION and
          type(value["status"]) is list and value["status"] == [],
          "AK/KK generation source checkpoint differs")
    hashes = value["source_hashes"]
    _need(type(hashes) is dict and len(hashes) == 783,
          "AK/KK historical source map must contain all 783 files")
    for relative, record in hashes.items():
        _need(type(relative) is str and type(record) is dict and
              set(record) == {"raw_sha256", "lf_sha256"} and
              all(type(record[key]) is str and re.fullmatch(r"[0-9a-f]{64}", record[key])
                  for key in ("raw_sha256", "lf_sha256")),
              "Malformed AK/KK historical source entry")
    for relative, (lf_hash, _archive, _size) in CONTEXT.items():
        _need(hashes.get(relative, {}).get("lf_sha256") == lf_hash,
              f"Historical context source differs: {relative}")
    return value


def _current_source_check(historical):
    current = evidence.snapshot()
    _need(type(current) is dict and type(current.get("revision")) is str and
          re.fullmatch(r"[0-9a-f]{40}", current["revision"]) is not None and
          type(current.get("status")) is list and current["status"] == [],
          "Current source checkout must be clean and committed")
    current_map = current.get("source_hashes")
    _need(type(current_map) is dict and set(historical) <= set(current_map),
          "Current source map omits files from the generation map")
    current_lf = {}
    current_context = {}
    unmeasured = {}
    transitions = {}
    for relative in current_map:
        expected = historical.get(relative)
        path = ROOT / relative
        raw = _read(path, 32 * 1024 * 1024)
        row = {"raw_sha256": hashlib.sha256(raw).hexdigest(),
               "lf_sha256": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()}
        _need(_typed_equal(current_map[relative], row),
              f"Current identity snapshot differs for {relative}")
        context = CONTEXT.get(relative)
        if expected is None:
            unmeasured[relative] = row["lf_sha256"]
        elif context is None:
            if row["lf_sha256"] != expected["lf_sha256"]:
                try:
                    from scripts import preflop_publication_source_history as history
                except ImportError as exc:
                    raise ValueError(f"Frozen measured source changed: {relative}") from exc
                receipt = history.authenticate_transition(relative, expected["lf_sha256"],
                                                          row["lf_sha256"])
                _need(type(receipt) is dict and set(receipt) == {
                      "historical_lf_sha256", "current_lf_sha256", "archive"} and
                      receipt["historical_lf_sha256"] == expected["lf_sha256"] and
                      receipt["current_lf_sha256"] == row["lf_sha256"] and
                      type(receipt["archive"]) is str and receipt["archive"],
                      f"Frozen measured source transition is not sealed: {relative}")
                transitions[relative] = receipt
        else:
            old_lf, archive_relative, size = context
            _need(expected["lf_sha256"] == old_lf,
                  f"Historical context source pin differs: {relative}")
            archived = _read(ROOT / archive_relative, size, size=size)
            _need(hashlib.sha256(archived).hexdigest() == old_lf and
                  hashlib.sha256(archived.replace(b"\r\n", b"\n")).hexdigest() == old_lf,
                  f"Historical context archive does not authenticate {relative}")
            current_context[relative] = row["lf_sha256"]
        current_lf[relative] = row["lf_sha256"]
    return {"revision": current["revision"], "status": current["status"],
            "source_lf_sha256": _digest(current_lf), "current_context_lf_sha256": current_context,
            "unmeasured_current_lf_sha256": unmeasured, "sealed_transitions": transitions}


def _validate_build(build, expected_source, historical):
    _need(type(build) is dict and set(build) == {"executable_sha256", "manifest", "manifest_sha256"},
          "AK/KK build receipt schema differs")
    manifest = build["manifest"]
    manifest_keys = {"compiler", "compiler_version", "executable", "executable_sha256",
                     "flags", "platform", "protocol", "schema_version", "source_lf_sha256",
                     "source_sha256"}
    _need(type(manifest) is dict and set(manifest) == manifest_keys and
          type(manifest["schema_version"]) is int and manifest["schema_version"] == 1 and
          type(manifest["flags"]) is list and type(manifest["compiler"]) is str and
          type(manifest["compiler_version"]) is str and type(manifest["platform"]) is str and
          type(build["executable_sha256"]) is str and
          re.fullmatch(r"[0-9a-f]{64}", build["executable_sha256"]) is not None and
          manifest["executable_sha256"] == build["executable_sha256"] and
          type(build["manifest_sha256"]) is str and
          re.fullmatch(r"[0-9a-f]{64}", build["manifest_sha256"]) is not None,
          "AK/KK build manifest receipt or fields differ")
    source = historical.get(expected_source)
    _need(type(source) is dict and manifest["source_sha256"] == source["raw_sha256"] and
          manifest["source_lf_sha256"] == source["lf_sha256"],
          f"AK/KK build source linkage differs: {expected_source}")
    expected_protocol, expected_executable = (
        ("PREFLOP_FIVE_REFERENCE_V2", {"preflop-five-reference", "preflop-five-reference.exe"})
        if expected_source == "native/preflop_five_card_reference.c" else
        ("OPENPOKER_NATIVE_V1", {"native-preflop-equity", "native-preflop-equity.exe"}))
    _need(manifest["protocol"] == expected_protocol and
          manifest["executable"] in expected_executable,
          f"AK/KK build protocol or executable identity differs: {expected_source}")


def _validate_count_rows(rows, expected_pairs, label):
    _need(type(rows) is list and len(rows) == len(expected_pairs), f"{label} row count differs")
    for row, (sb, bb) in zip(rows, expected_pairs):
        _need(type(row) is dict and set(row) == {
              "sb_hand", "bb_hand", "wins", "ties", "losses", "boards"} and
              type(row["sb_hand"]) is str and row["sb_hand"] == sb and
              type(row["bb_hand"]) is str and row["bb_hand"] == bb and
              all(type(row[k]) is int and row[k] >= 0 for k in ("wins", "ties", "losses", "boards")) and
              row["boards"] == 1_712_304 and
              row["wins"] + row["ties"] + row["losses"] == row["boards"],
              f"{label} exact physical row differs")


def _json_stream(raw, label):
    try:
        data = _json(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ValueError(f"Invalid bounded {label} JSON stream") from exc
    _need(type(data) is dict, f"{label} stream must be an object")
    return data


def _rows_from_named(rows):
    return tuple((row["sb_hand"], row["bb_hand"], row["wins"], row["ties"],
                  row["losses"], row["boards"]) for row in rows)


def _validate_reference_stream(parsed, expected_pairs, expected_rows, label):
    pairs = tuple((tuple(sb[i:i + 2] for i in (0, 2)),
                   tuple(bb[i:i + 2] for i in (0, 2))) for sb, bb in expected_pairs)
    rows = reference.verify_rows(parsed, pairs)
    _need(rows == _rows_from_named(expected_rows), f"{label} parsed W/T/L rows differ from report")


def _validate_native_stream(parsed, expected_rows, label):
    pair_count = len(expected_rows)
    _need(set(parsed) == {"schema_version", "mode", "counts", "boards_per_pair", "rank_calls"} and
          type(parsed.get("schema_version")) is int and parsed["schema_version"] == 1 and
          parsed.get("mode") == "count" and
          type(parsed.get("boards_per_pair")) is int and parsed["boards_per_pair"] == 1_712_304 and
          type(parsed.get("rank_calls")) is int and parsed["rank_calls"] == 3_424_608 * pair_count and
          type(parsed.get("counts")) is list and len(parsed["counts"]) == pair_count and
          all(type(row) is list and len(row) == 3 and
              all(type(value) is int and value >= 0 for value in row) for row in parsed["counts"]),
          f"{label} native stream schema/census differs")
    expected = [[row[k] for k in ("wins", "ties", "losses")] for row in expected_rows]
    _need(parsed["counts"] == expected, f"{label} native W/T/L stream differs from report")


def _validate_calls(report, raw_files, admission, conformance):
    calls = report["numerical_subprocess_calls"]
    _need(type(calls) is list and len(calls) == 7,
          "AK/KK observation must retain exactly seven stage calls")
    query_by_stage = {
        "reference-aa-calibration": ("aa-calibration",),
        "native-aa-calibration": ("aa-calibration",),
        "reference-ak-suited": ("ak-suited",), "native-ak-suited": ("ak-suited",),
        "reference-ak-offsuit": ("ak-offsuit",), "native-ak-offsuit": ("ak-offsuit",),
    }
    report_profiles = {item["id"]: item for item in report["profiles"]}
    _need(set(report_profiles) == {"ak-suited", "ak-offsuit"},
          "AK/KK profile inventory differs")
    requests = {item["id"]: item for item in admission["count_requests"]}
    for ordinal, (call, stage) in enumerate(zip(calls, STAGES), 1):
        _need(type(call) is dict and type(call.get("ordinal")) is int and
              call["ordinal"] == ordinal and call.get("stage") == stage and
              call.get("status") == "returned" and type(call.get("returncode")) is int and
              call["returncode"] == 0 and "capture_error" not in call,
              f"AK/KK stage order or subprocess result differs at {stage}")
        for label, ext, cap in (("stdout", "stdout.json", MAX_STDOUT_BYTES),
                                ("stderr", "stderr.txt", MAX_STDERR_BYTES)):
            receipt = call.get(label)
            _need(type(receipt) is dict and set(receipt) == {
                  "bytes_observed_at_most_limit_plus_one", "bytes_retained", "capture_source",
                  "over_bound", "path", "sha256"} and
                  type(receipt["bytes_retained"]) is int and
                  type(receipt["bytes_observed_at_most_limit_plus_one"]) is int and
                  receipt["bytes_observed_at_most_limit_plus_one"] == receipt["bytes_retained"] and
                  0 <= receipt["bytes_retained"] <= cap and receipt["over_bound"] is False and
                  receipt["capture_source"] in ("captured-pipe", "seekable-stream", "file-backed-stream") and
                  type(receipt["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", receipt["sha256"]) and
                  type(receipt["path"]) is str,
                  f"Incomplete or malformed {stage} {label} receipt")
            if stage == "reference-all-five" and label == "stdout":
                _need(receipt["bytes_retained"] == ALL_FIVE_BYTES and
                      receipt["sha256"] == ALL_FIVE_SHA256 and
                      receipt["path"] == "captured-native-streams/reference-all-five-stdout.bin" and
                      receipt["capture_source"] == "file-backed-stream",
                      "External all-five binary receipt differs")
                continue
            relative = f"streams/{stage}.{ext}"
            raw_size = len(raw_files[relative])
            _need(receipt["bytes_retained"] == raw_size and
                  receipt["sha256"] == hashlib.sha256(raw_files[relative]).hexdigest() and
                  receipt["path"] == f"captured-native-streams/{stage}-{label}.bin",
                  f"{stage} {label} receipt does not link to its captured raw stream")
            if label == "stderr":
                _need(raw_files[relative] == b"", f"{stage} stderr should be empty")
                continue
            parsed = _json_stream(raw_files[relative], stage)
            if stage == "reference-aa-calibration":
                expected_raw = conformance["reference_raw_counts"]
                _need(_typed_equal(parsed, expected_raw), "AA reference stdout differs from conformance")
                rows = five.verify_count_result(parsed)
                _need(_typed_equal(rows, conformance["independent_physical_count_rows"]),
                      "AA reference stdout differs from independent conformance rows")
            elif stage == "native-aa-calibration":
                expected_rows = conformance["candidate_equity_table"]["counts"]
                _validate_native_stream(parsed, expected_rows, stage)
            else:
                qid = query_by_stage[stage][0]
                profile = report_profiles[qid]
                rows = profile["reference"]["ordered_rows"]
                request = requests[qid]
                expected_pairs = [tuple(pair) for pair in request["ordered_pairs"]]
                _validate_count_rows(rows, expected_pairs, stage)
                if stage.startswith("reference-"):
                    _need(_typed_equal(parsed, profile["reference"]["metadata"]["raw_reference_result"]),
                          f"{stage} stdout differs from embedded raw reference result")
                    raw_rows = profile["reference"]["raw_order_rows"]
                    _validate_reference_stream(parsed, expected_pairs, raw_rows, stage)
                    _need(_typed_equal(raw_rows, rows), f"{stage} raw/normalized row order differs")
                else:
                    native_rows = profile["native"]["ordered_rows"]
                    _validate_count_rows(native_rows, expected_pairs, stage)
                    _validate_native_stream(parsed, native_rows, stage)
                    _need(_typed_equal(native_rows, rows), f"{stage} native/reference rows differ")
    _need(type(report["native_capture_errors"]) is list and report["native_capture_errors"] == [],
          "AK/KK capture contains errors")


def _validate_conformance(conformance, report, raw, raw_files, root):
    _need(type(conformance) is dict and conformance.get("benchmark_id") == "preflop-five-basis-v1" and
          conformance.get("status") == "passed" and conformance.get("errors") == [] and
          type(conformance.get("artifact_sha256")) is str and
          conformance["artifact_sha256"] == CONFORMANCE_ARTIFACT_SHA256 and
          _artifact(conformance) == CONFORMANCE_ARTIFACT_SHA256 and
          _typed_equal(conformance, report["current_build_conformance"]),
          "Embedded and separately saved AA conformance reports differ")
    _need(hashlib.sha256(raw).hexdigest() == CONFORMANCE_RAW_SHA256,
          "AA conformance raw checksum differs")
    saved_path = root / "aa-conformance-report.json"
    saved = five.verify_saved(saved_path)
    _need(saved.get("status") == "passed" and
          _typed_equal(conformance.get("saved_verification"), saved),
          "Current AA conformance saved authentication failed")
    rows = five.verify_count_result(conformance["reference_raw_counts"])
    _need(_typed_equal(rows, conformance["independent_physical_count_rows"]),
          "AA reference stream and conformance rows differ")
    candidate_counts = conformance["candidate_equity_table"]["counts"]
    expected_native = [[row["wins"], row["ties"], row["losses"]] for row in candidate_counts]
    native_raw = _json_stream(raw_files["streams/native-aa-calibration.stdout.json"],
                               "native AA calibration")
    _validate_native_stream(native_raw, candidate_counts, "native AA calibration")
    _need(native_raw["counts"] == expected_native,
          "Native AA calibration differs from candidate conformance table")
    return saved


def _validate_profile_metadata(profile, query, reference_build, candidate_build,
                               conformance_sha256):
    ref = profile["reference"]
    native = profile["native"]
    expected_pairs = query["ordered_pairs"]
    ref_meta = ref.get("metadata")
    native_meta = native.get("metadata")
    _need(type(ref_meta) is dict and type(native_meta) is dict and
          _typed_equal(ref_meta.get("admission"), query["admission"]) and
          _typed_equal(ref_meta.get("build"), reference_build) and
          ref_meta.get("conformance_report_sha256") == conformance_sha256 and
          _typed_equal(native_meta.get("build"), candidate_build) and
          type(native_meta.get("compatible_pairs")) is int and
          native_meta["compatible_pairs"] == len(expected_pairs) and
          type(native_meta.get("rank_calls")) is int and
          native_meta["rank_calls"] == 3_424_608 * len(expected_pairs) and
          type(native_meta.get("board_evaluations")) is int and
          native_meta["board_evaluations"] == 1_712_304 * len(expected_pairs) and
          native_meta.get("backend") == "native-full-board-v1" and
          native_meta.get("source_inclusive_admission") is True,
          f"{profile['id']} source/build/query linkage differs")


def _validate_report(report, index, raw_files, conformance, root):
    _need(type(report) is dict and set(report) == REPORT_KEYS and
          type(report["artifact_sha256"]) is str and
          report["artifact_sha256"] == REPORT_ARTIFACT_SHA256 and
          _artifact(report) == REPORT_ARTIFACT_SHA256,
          "AK/KK report schema or canonical digest differs")
    _need(type(report["schema_version"]) is int and report["schema_version"] == 1 and
          report["benchmark_id"] == "preflop-ak-kk-basis-v1" and
          report["status"] == "passed" and report["protocol_sha256"] == evidence.SPEC_SHA256 and
          report["errors"] == [] and report["native_capture_errors"] == [],
          "AK/KK report identity, protocol or error status differs")
    _need(report["source_unchanged"] is True and report["reference_build_unchanged"] is True and
          report["candidate_build_unchanged"] is True and report["aa_calibration_match"] is True,
          "AK/KK completion gates differ")
    admission = planner.admit_plan()
    _need(_typed_equal(report["admission"], admission) and
          _typed_equal(index["benchmark_id"], report["benchmark_id"]),
          "AK/KK full preflight/admission differs")
    specification, spec_sha = evidence._protocol(admission)
    _need(spec_sha == evidence.SPEC_SHA256 and
          _typed_equal(report["specification"], specification),
          "AK/KK frozen protocol/schema differs")
    _need(type(report["created_at_utc"]) is str,
          "AK/KK generation timestamp is malformed")
    timestamp = datetime.fromisoformat(report["created_at_utc"].replace("Z", "+00:00"))
    _need(timestamp.tzinfo is not None and timestamp.utcoffset().total_seconds() == 0,
          "AK/KK generation timestamp must be UTC")
    _need(type(report["runtime"]) is dict and
          all(type(report["runtime"].get(key)) is str and report["runtime"][key]
              for key in ("python", "platform")),
          "AK/KK runtime receipt is malformed")
    before = _source_record(report["source_before"])
    after = _source_record(report["source_after"])
    _need(_typed_equal(before, after) and
          _typed_equal(index["source_revision"], before["revision"]),
          "AK/KK generation source snapshots differ")
    historical = before["source_hashes"]
    _validate_build(report["reference_build_before"], "native/preflop_five_card_reference.c", historical)
    _validate_build(report["reference_build_after"], "native/preflop_five_card_reference.c", historical)
    _validate_build(report["candidate_build_before"], "native/preflop_equity.c", historical)
    _validate_build(report["candidate_build_after"], "native/preflop_equity.c", historical)
    _need(_typed_equal(report["reference_build_before"], report["reference_build_after"]) and
          _typed_equal(report["candidate_build_before"], report["candidate_build_after"]),
          "AK/KK reference or native build changed during observation")
    _need(_typed_equal(conformance["reference_build_before"], report["reference_build_before"]) and
          _typed_equal(conformance["reference_build_after"], report["reference_build_after"]) and
          _typed_equal(conformance["candidate_metadata"]["build"],
                       report["candidate_build_before"]["manifest"]),
          "AA conformance source/build linkage differs")
    basis = report["basis_authentication"]
    _need(type(basis) is dict and set(basis) == {"artifact_sha256", "raw_sha256", "verification"} and
          basis["artifact_sha256"] == AA_ARTIFACT_SHA256 and basis["raw_sha256"] == AA_RAW_SHA256,
          "AK/KK published AA basis linkage differs")
    aa_path = ROOT / "benchmarks/results/preflop-five-basis-v1.json"
    aa_raw = _read(aa_path, MAX_BASIS_BYTES, sha256=AA_RAW_SHA256)
    aa_report = _json(aa_raw)
    _need(aa_report.get("artifact_sha256") == AA_ARTIFACT_SHA256 and
          _typed_equal(basis["verification"], five.verify_saved(aa_path)),
          "Published AA saved-count authentication differs")
    _need(_typed_equal(aa_report["independent_physical_count_rows"],
                       conformance["independent_physical_count_rows"]),
          "AK/KK AA calibration differs from the published AA basis")
    _validate_conformance(conformance, report, raw_files["aa-conformance-report.json"],
                          raw_files, root)

    _need(type(report["profiles"]) is list and len(report["profiles"]) == 2,
          "AK/KK profile count differs")
    profile_ids = [profile.get("id") if type(profile) is dict else None for profile in report["profiles"]]
    _need(profile_ids == ["ak-suited", "ak-offsuit"], "AK/KK profile order differs")
    expected_queries = {row["id"]: row for row in admission["count_requests"]}
    all_rows = []
    for profile in report["profiles"]:
        query = expected_queries[profile["id"]]
        expected_pairs = [tuple(pair) for pair in query["ordered_pairs"]]
        ref = profile["reference"]
        native = profile["native"]
        _need(type(ref) is dict and set(ref) == {"metadata", "ordered_rows", "raw_order_rows"} and
              type(native) is dict and set(native) == {"equity_table", "metadata", "ordered_rows"},
              f"{profile['id']} profile schema differs")
        _validate_count_rows(ref["ordered_rows"], expected_pairs, f"{profile['id']} reference")
        _validate_count_rows(native["ordered_rows"], expected_pairs, f"{profile['id']} native")
        _need(_typed_equal(ref["ordered_rows"], native["ordered_rows"]) and
              _typed_equal(ref["ordered_rows"], ref["raw_order_rows"]),
              f"{profile['id']} reference/native or raw/normalized counts differ")
        _validate_profile_metadata(profile, query, report["reference_build_before"],
                                    report["candidate_build_before"]["manifest"],
                                    CONFORMANCE_ARTIFACT_SHA256)
        table = native["equity_table"]
        _need(type(table) is dict and type(table.get("counts")) is list and
              len(table["counts"]) == len(expected_pairs),
              f"{profile['id']} native equity table census differs")
        for row, pair, expected_row in zip(table["counts"], expected_pairs, native["ordered_rows"]):
            _need(type(row) is dict and set(row) == {
                  "bb_hand", "board_outcomes", "losses", "pair_probability", "sb_hand", "ties", "wins"} and
                  row["sb_hand"] == pair[0] and row["bb_hand"] == pair[1] and
                  type(row["board_outcomes"]) is int and row["board_outcomes"] == 1_712_304 and
                  type(row["pair_probability"]) is float and
                  row["pair_probability"] == 1.0 / len(expected_pairs) and
                  all(type(row[key]) is int and row[key] == expected_row[key]
                      for key in ("wins", "ties", "losses")),
                  f"{profile['id']} native weighted table row differs")
        all_rows.extend(ref["ordered_rows"])
    _validate_count_rows(report["independent_physical_count_rows"],
                         [(row["sb_hand"], row["bb_hand"]) for row in all_rows],
                         "AK/KK combined reference")
    _need(_typed_equal(report["independent_physical_count_rows"], all_rows),
          "AK/KK combined physical rows differ from profiles")
    _validate_calls(report, raw_files, admission, conformance)
    return before


def verify(directory=None):
    """Authenticate the pinned corpus, AA prerequisite and source receipts."""
    root = Path(directory) if directory is not None else PUBLICATION
    _need(not root.is_symlink(), "AK/KK publication root cannot be a symlink")
    raw_index, index = _validate_index(root)
    raw_files = _inventory(root, index)
    _need(hashlib.sha256(raw_index).hexdigest() == INDEX_RAW_SHA256,
          "AK/KK index changed after inventory")
    report_raw = raw_files["report.json"]
    conformance_raw = raw_files["aa-conformance-report.json"]
    _need(len(report_raw) == REPORT_BYTES and hashlib.sha256(report_raw).hexdigest() == REPORT_RAW_SHA256 and
          index["report_artifact_sha256"] == REPORT_ARTIFACT_SHA256 and
          len(conformance_raw) == CONFORMANCE_BYTES and
          hashlib.sha256(conformance_raw).hexdigest() == CONFORMANCE_RAW_SHA256 and
          index["conformance_artifact_sha256"] == CONFORMANCE_ARTIFACT_SHA256,
          "AK/KK report or AA conformance raw identity differs")
    report = _json(report_raw)
    conformance = _json(conformance_raw)
    generation = _source_record(report.get("source_before"))
    current_before = _current_source_check(generation["source_hashes"])
    historical = _validate_report(report, index, raw_files, conformance, root)
    _need(_typed_equal(generation, historical),
          "AK/KK source generation changed during metadata validation")
    final_files = _inventory(root, index)
    _need(final_files == raw_files and _read(root / "index.json", MAX_INDEX_BYTES,
          size=INDEX_BYTES, sha256=INDEX_RAW_SHA256) == raw_index,
          "AK/KK publication bytes changed during authentication")
    final_report = _json(final_files["report.json"])
    final_conformance = _json(final_files["aa-conformance-report.json"])
    _need(_typed_equal(final_report, report) and _typed_equal(final_conformance, conformance),
          "AK/KK parsed evidence changed during authentication")
    current_after = _current_source_check(historical["source_hashes"])
    _need(_typed_equal(current_before, current_after),
          "AK/KK current source changed during saved authentication")
    return {
        "status": "authenticated-saved-counts-only",
        "benchmark_id": "preflop-ak-kk-basis-v1",
        "source_revision": FROZEN_REVISION,
        "index_artifact_sha256": INDEX_ARTIFACT_SHA256,
        "report_artifact_sha256": REPORT_ARTIFACT_SHA256,
        "conformance_artifact_sha256": CONFORMANCE_ARTIFACT_SHA256,
        "source_files_authenticated": 783,
        "numerical_subprocesses_recorded": 7,
        "current_numerical_subprocesses": 0,
        "five_card_tuples_recorded": five.FIVE_TOTAL,
        "current_five_card_tuples": 0,
        "physical_count_rows_authenticated": 3,
        "counts_generated": False,
        "equities_claimed": False,
        "solver_or_training_claimed": False,
        "current_source_attestation": current_after,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", default=str(PUBLICATION))
    args = parser.parse_args()
    print(json.dumps(verify(args.directory), sort_keys=True), flush=True)
