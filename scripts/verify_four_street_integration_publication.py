"""Authenticate a frozen four-street attempt and independently replay saved bytes.

The externally supplied index digest pins report.json, including a miss or a
failure. This module never trains, resumes an attempt, or changes saved files.
Its bootstrap uses only the standard library; source authentication precedes
imports of the runner and the independent numeric/exact mathematical models.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_LIMIT = 16 * 1024 * 1024
JSON_LIMIT = 32 * 1024 * 1024
SMALL_JSON_LIMIT = 1024 * 1024
TOTAL_LIMIT = 256 * 1024 * 1024
MAX_JSON_NODES = 1_000_000
MAX_JSON_DEPTH = 80
SOURCE_FILE_LIMIT = 4096
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
BENCHMARK_ID = "four-street-integration-v1"
INVENTORY_POLICY = ("all committed pokerlab and scripts Python, plus pinned U5 "
                    "fixture/protocol and reused river protocol")
DATA_SOURCES = frozenset({
    "benchmarks/four-street-integration-v1.json",
    "docs/four-street-integration-protocol.md",
    "docs/river-heldout-quality-protocol.md",
})
REQUIRED_SOURCES = frozenset({
    "pokerlab/__init__.py",
    "scripts/benchmark_four_street_integration.py",
    "scripts/verify_four_street_integration_publication.py",
})
ARTIFACT_NAMES = frozenset({
    "attempt.json", "claim.json", "source-before.json", "production-admission.json",
    "exact-admission.json", "raw-envelope.json", "raw-receipt.json",
    "numeric-replay.json", "exact-certificate.json", "source-after.json",
    "report.json", "failure.json", "status.json",
})
CAPACITY_ERRORS = (
    "forecast exceeds its hard work limit",
    "Exact rational certificate exceeds its work limit", "65536-bit limit",
    "Exact rational certificate exceeds the depth limit",
    "Exact rational certificate exceeds the node limit",
)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def _same(actual, expected, label):
    # JSON equality distinguishes True from 1, and integer metadata from floats.
    if _json_bytes(actual) != _json_bytes(expected):
        raise ValueError(f"{label} differs from the authenticated/recomputed value")


def _strict_json(data, *, max_bytes=JSON_LIMIT):
    if type(data) is not bytes or len(data) > max_bytes:
        raise ValueError("JSON artifact exceeds its byte limit")

    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("JSON artifact contains a duplicate object key")
            result[key] = item
        return result

    def nonfinite(_item):
        raise ValueError("JSON artifact contains a nonfinite number")

    try:
        result = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                            parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError) as exc:
        raise ValueError("JSON artifact is malformed or exceeds parser depth") from exc
    pending = [(result, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if count > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise ValueError("JSON artifact exceeds bounded node count or nesting")
        if type(item) is dict:
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is float and not math.isfinite(item):
            raise ValueError("JSON artifact contains a nonfinite number")
    return result


def _no_alias(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("artifact/source paths must be absolute without parent traversal")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        metadata = current.lstat()
        if (stat.S_ISLNK(metadata.st_mode) or
                getattr(metadata, "st_file_attributes", 0) &
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("artifact/source paths must not traverse symlinks or junctions")


def _read(path, limit):
    _no_alias(path)
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
        raise ValueError("artifact/source file is not regular or exceeds its byte limit")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) != metadata.st_size or len(data) > limit:
        raise ValueError("artifact/source file changed during bounded read")
    return data


def _artifact_limit(name):
    if name == "raw-envelope.json":
        return RAW_LIMIT
    if name in {"attempt.json", "claim.json", "failure.json", "status.json"}:
        return SMALL_JSON_LIMIT
    return JSON_LIMIT


def _load_artifacts(directory, expected_index_sha256):
    if type(expected_index_sha256) is not str or not SHA256.fullmatch(expected_index_sha256):
        raise ValueError("expected index SHA256 must be 64 lowercase hexadecimal characters")
    directory = Path(directory)
    _no_alias(directory)
    if not directory.is_dir():
        raise ValueError("attempt directory is not a directory")
    entries = list(directory.iterdir())
    if len(entries) > 14 or {path.name for path in entries} - ARTIFACT_NAMES:
        raise ValueError("attempt has unexpected files or exceeds its fixed file inventory")
    # Authenticate the external pin before parsing any untrusted JSON or math.
    raw_report = _read(directory / "report.json", JSON_LIMIT)
    if _sha256(raw_report) != expected_index_sha256:
        raise ValueError("report.json does not match the expected index SHA256")
    raw = {"report.json": raw_report}
    total = len(raw_report)
    for path in sorted(entries):
        if path.name == "report.json":
            continue
        raw[path.name] = _read(path, _artifact_limit(path.name))
        total += len(raw[path.name])
        if total > TOTAL_LIMIT:
            raise ValueError("attempt exceeds its 256 MiB aggregate byte limit")
    # A failed serialization may leave partial raw bytes: parse those only when
    # an outcome actually claims a complete serialized return.
    report = _strict_json(raw_report)
    if type(report) is not dict:
        raise ValueError("report must be a JSON object")
    parse_names = set(raw) - {"raw-envelope.json"}
    if report.get("outcome") in {"failed", "preparation-failed"}:
        parse_names = {"report.json", "attempt.json", "status.json", "failure.json"}
        receipts = report.get("receipts")
        if type(receipts) is dict and any(
                type(receipt) is dict and receipt.get("path") == "source-before.json"
                for receipt in receipts.values()):
            parse_names.add("source-before.json")
    records = {name: _strict_json(raw[name], max_bytes=_artifact_limit(name))
               for name in parse_names if name in raw}
    return directory, raw, records


def _relative_source(name):
    if (type(name) is not str or not name or "\\" in name or ":" in name or
            any(ord(char) < 32 for char in name)):
        raise ValueError("source inventory has an invalid relative path")
    parsed = PurePosixPath(name)
    if parsed.is_absolute() or str(parsed) != name or any(part in {".", ".."} for part in parsed.parts):
        raise ValueError("source inventory has an invalid relative path")
    return name


def _git(*args, input_data=None):
    return subprocess.check_output(["git", "-C", str(REPO_ROOT), *args],
                                   input=input_data, stderr=subprocess.PIPE)


def _authenticate_source(state, expected_commit):
    if type(state) is not dict or set(state) != {"head", "status", "files", "inventory_policy"}:
        raise ValueError("saved source state has an unsupported shape")
    _same(state["head"], expected_commit, "source commit")
    _same(state["status"], "clean", "recorded source status")
    _same(state["inventory_policy"], INVENTORY_POLICY, "source inventory policy")
    if not GIT_SHA.fullmatch(expected_commit):
        raise ValueError("saved source commit is malformed")
    if _git("cat-file", "-t", expected_commit) != b"commit\n":
        raise ValueError("saved source identity is not a Git commit")
    # Derive the closure from the immutable Git tree, not caller-chosen rows.
    tree = _git("ls-tree", "-r", "-l", "-z", expected_commit, "--",
                "pokerlab", "scripts", *sorted(DATA_SOURCES))
    if len(tree) > 2 * 1024 * 1024:
        raise ValueError("Git source inventory exceeds its metadata bound")
    inventory = {}
    total = 0
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        header, separator, name_bytes = entry.partition(b"\t")
        if not separator:
            raise ValueError("Git tree entry is malformed")
        name = _relative_source(name_bytes.decode("utf-8"))
        if name not in DATA_SOURCES and not (
                name.startswith(("pokerlab/", "scripts/")) and name.endswith(".py")):
            continue
        fields = header.split()
        if (len(fields) != 4 or fields[0] not in {b"100644", b"100755"} or
                fields[1] != b"blob" or not fields[3].isdigit()):
            raise ValueError("frozen source is not a regular Git blob")
        blob = fields[2].decode("ascii")
        size = int(fields[3])
        if not GIT_SHA.fullmatch(blob) or size > JSON_LIMIT or name in inventory:
            raise ValueError("Git source blob has an invalid identity or size")
        inventory[name] = (blob, size)
        total += size
        if total > TOTAL_LIMIT or len(inventory) > SOURCE_FILE_LIMIT:
            raise ValueError("frozen source closure exceeds its bounded inventory")
    if not (DATA_SOURCES | REQUIRED_SOURCES).issubset(inventory):
        raise ValueError("frozen source inventory is incomplete")
    saved = state["files"]
    if type(saved) is not dict or set(saved) != set(inventory):
        raise ValueError("saved source inventory differs from the frozen Git tree")
    current_python = set()
    for package in ("pokerlab", "scripts"):
        for path in (REPO_ROOT / package).rglob("*.py"):
            _no_alias(path)
            current_python.add(path.relative_to(REPO_ROOT).as_posix())
            if len(current_python) > SOURCE_FILE_LIMIT:
                raise ValueError("current source Python inventory exceeds its bound")
    if current_python != set(inventory) - DATA_SOURCES:
        raise ValueError("current Python inventory differs from frozen source")
    request = "".join(f"{blob}\n" for blob, _size in inventory.values()).encode("ascii")
    batch = _git("cat-file", "--batch", input_data=request)
    if len(batch) > total + len(inventory) * 128:
        raise ValueError("Git source batch exceeds its declared bound")
    offset = 0
    current_total = 0
    for name, (blob, size) in inventory.items():
        end = batch.find(b"\n", offset)
        expected_header = f"{blob} blob {size}".encode("ascii")
        if end < 0 or batch[offset:end] != expected_header:
            raise ValueError("Git source batch object header differs")
        offset = end + 1
        committed = batch[offset:offset + size]
        offset += size
        if batch[offset:offset + 1] != b"\n" or len(committed) != size:
            raise ValueError("Git source batch object boundary differs")
        offset += 1
        if hashlib.sha1(f"blob {size}\0".encode("ascii") + committed).hexdigest() != blob:
            raise ValueError("Git source blob content does not match its identity")
        row = saved[name]
        if (type(row) is not dict or set(row) !=
                {"bytes", "raw_sha256", "normalized_lf_sha256", "git_blob"} or
                type(row["bytes"]) is not int or not 0 <= row["bytes"] <= JSON_LIMIT or
                type(row["raw_sha256"]) is not str or not SHA256.fullmatch(row["raw_sha256"])):
            raise ValueError("saved source receipt is malformed")
        normalized = committed.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        _same(row["git_blob"], blob, "saved source Git blob")
        _same(row["normalized_lf_sha256"], _sha256(normalized), "saved source LF digest")
        working = _read(REPO_ROOT / name, JSON_LIMIT)
        current_total += len(working)
        if current_total > TOTAL_LIMIT:
            raise ValueError("working source closure exceeds its aggregate bound")
        if working.replace(b"\r\n", b"\n").replace(b"\r", b"\n") != normalized:
            raise ValueError(f"current source differs from frozen source: {name}")
    if offset != len(batch):
        raise ValueError("Git source batch has trailing bytes")
    # The pinned snapshot binds original raw size/hash. Git and the current
    # checkout independently authenticate LF content, permitting CRLF checkout.
    return len(inventory)


def _load_math():
    from scripts import benchmark_four_street_integration as runner
    from scripts import four_street_certificate as certificate
    from scripts import four_street_validation as numeric
    return runner, numeric, certificate


def _record(records, name, schema, attempt_id):
    record = records.get(name)
    if type(record) is not dict or record.get("schema") != schema:
        raise ValueError(f"{name} has a missing/unsupported record schema")
    _same(record.get("attempt_id"), attempt_id, f"{name} attempt identity")
    return record


def _receipt(raw, receipt):
    if type(receipt) is not dict or type(receipt.get("path")) is not str:
        raise ValueError("saved artifact receipt is malformed")
    name = receipt["path"]
    if name not in raw or name not in ARTIFACT_NAMES:
        raise ValueError("saved artifact receipt refers to a missing/unknown file")
    _same(receipt.get("bytes"), len(raw[name]), f"{name} byte count")
    _same(receipt.get("sha256"), _sha256(raw[name]), f"{name} digest")


def _source_checks(checks, state, stages=None):
    if type(checks) is not list or len(checks) > 16:
        raise ValueError("source check sequence is malformed")
    if stages is not None:
        _same([row.get("stage") for row in checks if type(row) is dict], stages,
              "source check stage sequence")
    expected_hash = _sha256(_json_bytes(state))
    for index, row in enumerate(checks):
        if type(row) is not dict or type(row.get("stage")) is not str:
            raise ValueError("source check row is malformed")
        expected = {"stage": row["stage"], "state_sha256": expected_hash,
                    "matches_expected": None if index == 0 else True}
        _same(row, expected, "source check")


def _base_records(records):
    report = records.get("report.json")
    if type(report) is not dict or report.get("schema") != "four-street-attempt-report-v1":
        raise ValueError("report has a missing/unsupported schema")
    attempt_id = report.get("attempt_id")
    try:
        if str(uuid.UUID(attempt_id)) != attempt_id:
            raise ValueError("noncanonical attempt identity")
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("report attempt identity is malformed") from exc
    _same(report.get("benchmark_id"), BENCHMARK_ID, "benchmark identity")
    attempt = _record(records, "attempt.json", "four-street-attempt-v1", attempt_id)
    status = _record(records, "status.json", "four-street-attempt-status-v1", attempt_id)
    commit = attempt.get("source_commit")
    if type(commit) is not str or not GIT_SHA.fullmatch(commit):
        raise ValueError("attempt source commit is malformed")
    _same(attempt.get("benchmark_id"), BENCHMARK_ID, "attempt benchmark")
    _same(attempt.get("retry_permitted"), False, "attempt retry policy")
    _same(attempt.get("lifecycle"), "preparing", "initial attempt lifecycle")
    for record in (attempt, report):
        _same(record.get("execution_mode"), "frozen-production", "execution mode")
    runtime = attempt.get("runtime")
    runtime_keys = {"python_executable", "python_version", "python_implementation",
                    "platform", "sys_flags", "started_at_unix_ns"}
    if (type(runtime) is not dict or set(runtime) != runtime_keys or
            type(runtime["started_at_unix_ns"]) is not int or runtime["started_at_unix_ns"] <= 0 or
            any(type(runtime[key]) is not str or not runtime[key] for key in runtime_keys - {"started_at_unix_ns"})):
        raise ValueError("runtime provenance is malformed")
    _same(report.get("runtime"), runtime, "report runtime")
    _same(attempt.get("created_at_unix_ns"), runtime["started_at_unix_ns"], "attempt creation time")
    if type(status.get("updated_at_unix_ns")) is not int or status["updated_at_unix_ns"] < runtime["started_at_unix_ns"]:
        raise ValueError("status timestamp is malformed")
    outcome = report.get("outcome")
    if outcome not in {"completed-met", "completed-missed", "completed-unknown", "failed", "preparation-failed"}:
        raise ValueError("report outcome is unsupported")
    _same(status.get("lifecycle"), outcome, "final lifecycle")
    _same(status.get("quality_gate"), report.get("quality_gate"), "final quality gate")
    calls = status.get("production_calls_entered")
    if type(calls) is not int or calls not in {0, 1}:
        raise ValueError("original production call count is malformed")
    return report, attempt, status, commit, attempt_id


def _failed_record(raw, records, report, attempt, status, commit, attempt_id):
    failure = _record(records, "failure.json", "four-street-attempt-failure-v1", attempt_id)
    _same(report.get("quality_gate"), None, "failed quality gate")
    _same(failure.get("quality_gate"), None, "failure quality gate")
    first = report.get("first_failure")
    if (type(first) is not dict or set(first) != {"stage", "type", "message"} or
            any(type(value) is not str for value in first.values())):
        raise ValueError("first failure is malformed")
    _same(failure.get("failure"), first, "original first failure")
    _same(status.get("first_error"), first, "status first failure")
    for record in (report, failure):
        _same(record.get("production_calls_entered"), status["production_calls_entered"], "failed call count")
    if (report["outcome"] == "preparation-failed") != (status["production_calls_entered"] == 0):
        raise ValueError("failed lifecycle disagrees with original call count")
    receipts = report.get("receipts")
    if type(receipts) is not dict:
        raise ValueError("failed report omitted available receipts")
    _same(failure.get("receipts_so_far"), receipts, "failure available receipts")
    for receipt in receipts.values():
        if type(receipt) is dict and "path" in receipt:
            _receipt(raw, receipt)
    _same(failure.get("source_checks"), report.get("source_checks"), "failure source checks")
    source_verified = False
    if "source-before.json" in records:
        before = _record(records, "source-before.json", "four-street-source-state-v1", attempt_id)
        state = before.get("source_state")
        checks = report.get("source_checks")
        if not checks or checks[0].get("stage") != "source-before":
            raise ValueError("failed source snapshot is unbound")
        _same(checks[0], {"stage": "source-before", "state_sha256": _sha256(_json_bytes(state)),
                          "matches_expected": None}, "initial failed source check")
        _authenticate_source(state, commit)
        source_verified = True
    if status["production_calls_entered"] == 0 and any(
            name in raw for name in ("raw-envelope.json", "raw-receipt.json",
                                     "numeric-replay.json", "exact-certificate.json")):
        raise ValueError("preparation failure contains artifacts claiming training")
    return {"outcome": report["outcome"], "quality_gate": None,
            "source_verified": source_verified, "policy_replayed": False,
            "first_failure": first,
            "unreceipted_artifacts": {
                name: {"bytes": len(data), "sha256": _sha256(data),
                       "authentication": "observed bytes without an original saved receipt"}
                for name, data in raw.items()
                if name not in {"report.json", "attempt.json", "status.json", "failure.json"}
                and not any(type(receipt) is dict and receipt.get("path") == name
                            for receipt in receipts.values())}}


def _production_record(receipt, request):
    if type(receipt) is not dict:
        raise ValueError("production admission is malformed")
    for key, value in {"schema": "four-street-production-admission-v1", "admitted": True,
                       "attempted_training": False, "request": request.to_dict(),
                       "training_request": {"iterations_requested": 1000, "algorithm": "cfrplus",
                       "modeled_expected_training_passes": 3000,
                       "actual_training_passes_observed": None}}.items():
        _same(receipt.get(key), value, f"production admission {key}")
    counts = receipt.get("counts", {})
    fixed = {"candidate_private_pairs": 4, "compatible_private_pairs": 4, "worlds": 22,
             "pair_runout_preflight_checks": 24, "public_states": 1462, "decisions": 628,
             "information_sets": 1200, "information_set_action_slots": 2402,
             "world_decision_work": 8448000, "positive_pot_training_view_states": 1462,
             "positive_pot_training_anchor": 0.5}
    for key, value in fixed.items():
        _same(counts.get(key), value, f"production admission census {key}")
    for key in ("temporary_template_peak_states", "temporary_template_peak_decisions"):
        if type(counts.get(key)) is not int or not 0 < counts[key] <= 250000:
            raise ValueError("production temporary-template census is malformed")
    caps = receipt.get("caps", {})
    from pokerlab import preflop_solver as solver
    expected_caps = {
        "candidate_pair_iterations": solver._MAX_CANDIDATE_HAND_ITERATIONS,
        "world_iterations": solver._MAX_WORLD_ITERATIONS,
        "pair_runout_preflight_checks": solver._MAX_PAIR_RUNOUT_PREFLIGHT_CHECKS,
        "world_decision_work": solver._MAX_WORLD_NODE_WORK,
        "public_states": solver._MAX_PUBLIC_STATES, "decision_nodes": solver._MAX_PUBLIC_NODES,
        "information_set_action_slots": solver.MAX_INFO_ACTION_SLOTS,
        "vector_prefix_edges": 250000,
    }
    _same(caps, expected_caps, "fixed production admission caps")
    vector = receipt.get("vector_budget", {})
    if type(vector) is not dict:
        raise ValueError("production vector budget is malformed")
    for charge, cap in (("prefix_edges", "prefix_edge_limit"),
                        ("dense_prefix_slots", "dense_prefix_slot_limit"),
                        ("total_loop_entries_upper_bound", "total_loop_entry_limit")):
        if (type(vector.get(charge)) is not int or type(vector.get(cap)) is not int or
                not 0 <= vector[charge] <= vector[cap]):
            raise ValueError("production vector admission exceeded or omitted a guard")
    for key, value in {"prefix_edge_limit": 250000, "dense_prefix_slot_limit": 2000000,
                       "information_set_action_slot_limit": 1000000,
                       "total_loop_entry_limit": 500000000}.items():
        _same(vector.get(key), value, f"production vector cap {key}")
    _same(vector["total_loop_entries_upper_bound"], 167280468, "fixed full-request vector work")


def _completed_record(raw, records, report, attempt, status, commit, attempt_id):
    unknown = report["outcome"] == "completed-unknown"
    expected_files = ARTIFACT_NAMES - ({"exact-certificate.json"} if unknown else {"failure.json"})
    _same(sorted(raw), sorted(expected_files), "complete attempt artifact inventory")
    _same(status["production_calls_entered"], 1, "complete original call count")
    before = _record(records, "source-before.json", "four-street-source-state-v1", attempt_id)
    after = _record(records, "source-after.json", "four-street-source-state-v1", attempt_id)
    state = before.get("source_state")
    _same(after.get("source_state"), state, "final frozen source state")
    stages = ["source-before", "after-production-admission", "after-exact-admission",
              "before-claim", "immediately-before-solve", "source-after-raw",
              "after-numeric-replay", "after-exact-capacity-failure" if unknown else "source-after-audit"]
    _source_checks(report.get("source_checks"), state, stages)
    _same(after.get("source_checks"), report["source_checks"], "final source checks")
    source_files = _authenticate_source(state, commit)
    # All mathematical imports occur below the report, source and closure gates.
    runner, numeric, certificate = _load_math()
    case, request = runner._literal_case(), runner._literal_request()
    manifest = _strict_json(_read(REPO_ROOT / "benchmarks/four-street-integration-v1.json", JSON_LIMIT))
    _same(manifest.get("case"), case, "committed literal case")
    _same(manifest.get("quality_run"), runner._fixed_selectors(), "committed fixed selectors")
    production = _record(records, "production-admission.json", "four-street-production-admission-record-v1", attempt_id)["receipt"]
    exact = _record(records, "exact-admission.json", "four-street-exact-admission-record-v1", attempt_id)["receipt"]
    _production_record(production, request)
    fresh_admission = runner._independent_admission(case)
    fresh_admission["production_support_comparison"] = runner._compare_admission_support(production, fresh_admission)
    _same(exact, fresh_admission, "fresh independent admission/support")
    claim = _record(records, "claim.json", "four-street-training-claim-v1", attempt_id)
    expected_claim = {
        "schema": "four-street-training-claim-v1", "attempt_id": attempt_id,
        "benchmark_id": BENCHMARK_ID, "source_commit": commit,
        "execution_mode": "frozen-production", "runtime": attempt["runtime"],
        "source_state_sha256": _sha256(_json_bytes(state)), "case_sha256": _sha256(_json_bytes(case)),
        "request": request.to_dict(), "selectors": runner._fixed_selectors(),
        "omitted_request_defaults": {"averaging_delay": 0, "tree_admission": "decision-count",
            "private_indexing": "original", "future_indexing": "original", "world_admission": "world-iterations"},
        "production_admission": production, "exact_admission": exact,
        "production_calls_allowed": 1, "iterations_requested": 1000, "retry_permitted": False,
    }
    _same(claim, expected_claim, "frozen pre-training claim")
    raw_receipt = report.get("raw_receipt")
    _receipt(raw, raw_receipt)
    _same(raw_receipt, {"path": "raw-envelope.json", "bytes": len(raw["raw-envelope.json"]),
        "sha256": _sha256(raw["raw-envelope.json"]),
        "serialization": "original FourStreetSolveResult.to_json UTF-8 bytes"}, "raw serialization receipt")
    saved_receipt = _record(records, "raw-receipt.json", "four-street-raw-receipt-v1", attempt_id)
    _same(saved_receipt, {"schema": "four-street-raw-receipt-v1", "attempt_id": attempt_id,
                          **raw_receipt}, "first saved raw receipt")
    envelope = _strict_json(raw["raw-envelope.json"], max_bytes=RAW_LIMIT)
    # Canonical comparison also enforces metadata types the compatibility
    # runner historically compared using ordinary Python object equality.
    _same(envelope.get("request"), request.to_dict(), "raw request")
    payload = runner._assert_envelope(envelope, request)
    for key, expected in {"iterations": 1000, "training_passes": 3000,
                          "training_passes_per_iteration": 3}.items():
        _same(payload.get(key), expected, f"raw execution metadata {key}")
    runner._assert_payload_matches_admission(payload, production)
    identity = {"raw_sha256": raw_receipt["sha256"],
                "payload_canonical_sha256": _sha256(_json_bytes(payload)),
                "source_identity": envelope["source_identity"]}
    metrics = numeric.replay_policy(payload, case)
    comparison = runner._compare_numeric_metrics(payload, metrics)
    if not comparison["all_within_tolerance"]:
        raise ValueError("fresh numeric replay disagrees with production scalars")
    fresh_numeric = runner._fraction_strings({"schema": "four-street-numeric-replay-v1",
        "attempt_id": attempt_id, **identity, "metrics": metrics,
        "numeric_counts": metrics.get("numeric_counts"), "production_comparison": comparison})
    saved_numeric = _record(records, "numeric-replay.json", "four-street-numeric-replay-v1", attempt_id)
    _same(saved_numeric, fresh_numeric, "fresh full numeric replay")
    _same(report.get("numeric_replay"), fresh_numeric, "report numeric replay")
    _same(report.get("training"), runner._training_metadata(payload), "reported training metadata")
    if unknown:
        failure = _record(records, "failure.json", "four-street-capacity-unknown-v1", attempt_id)
        first = report.get("first_failure")
        if (type(first) is not dict or first.get("stage") != "exact-certificate" or
                first.get("type") != "ValueError" or type(first.get("message")) is not str or
                not any(marker in first["message"] for marker in CAPACITY_ERRORS)):
            raise ValueError("capacity-unknown first failure is malformed")
        _same(failure.get("stage"), "exact-certificate", "capacity failure stage")
        _same(failure.get("error"), first["message"], "saved capacity failure")
        _same(failure.get("raw_receipt"), raw_receipt, "capacity raw receipt")
        _receipt(raw, failure.get("numeric_replay"))
        _same(status.get("first_error"), first, "capacity status error")
        for record in (failure, report):
            _same(record.get("quality_gate"), None, "unknown exact quality gate")
        _same(report.get("exact_certificate"), None, "unknown certificate")
        try:
            certificate.evaluate_exact(case, payload)
        except ValueError as exc:
            if not any(marker in str(exc) for marker in CAPACITY_ERRORS):
                raise ValueError("fresh replay failed outside saved capacity scope") from exc
            _same(str(exc), first["message"], "fresh exact capacity failure")
        else:
            raise ValueError("saved capacity failure is not reproduced by frozen-source replay")
        gate, exact_metrics = None, None
    else:
        fresh_exact = runner._fraction_strings(certificate.evaluate_exact(case, payload))
        saved_exact = _record(records, "exact-certificate.json", "four-street-exact-certificate-record-v1", attempt_id)
        _same(saved_exact, {"schema": "four-street-exact-certificate-record-v1", "attempt_id": attempt_id,
                           **identity, "certificate": fresh_exact}, "fresh complete exact certificate/ledger")
        _same(report.get("exact_certificate"), runner._exact_report_summary(fresh_exact), "report exact summary")
        gate = fresh_exact["threshold_met"]
        if type(gate) is not bool:
            raise ValueError("fresh exact gate is malformed")
        _same(report.get("quality_gate"), gate, "exact quality decision")
        _same(report["outcome"], "completed-met" if gate else "completed-missed", "saved exact outcome")
        _same(status.get("exact_nash_conv"), fresh_exact["metrics"]["nash_conv"], "status exact gap")
        _same(status.get("first_error"), None, "successful status error")
        for key, value in {"source_commit": commit, "case_sha256": _sha256(_json_bytes(case)),
                           "target_nash_conv_big_blinds": "1/1000", "production_calls_entered": 1,
                           "first_failure": None, "admissions": {"production": production, "exact": exact}}.items():
            _same(report.get(key), value, f"completed report {key}")
        exact_metrics = fresh_exact["metrics"]
    return {"outcome": report["outcome"], "quality_gate": gate,
            "source_verified": True, "source_files_verified": source_files,
            "policy_replayed": True, "numeric_metrics": metrics, "exact_metrics": exact_metrics}


def verify_publication(directory, expected_index_sha256):
    """Replay one externally pinned saved attempt; never enter production solve."""
    directory, raw, records = _load_artifacts(directory, expected_index_sha256)
    report, attempt, status, commit, attempt_id = _base_records(records)
    if report["outcome"] in {"failed", "preparation-failed"}:
        result = _failed_record(raw, records, report, attempt, status, commit, attempt_id)
    else:
        result = _completed_record(raw, records, report, attempt, status, commit, attempt_id)
    # Detect edits during verification as well as edits before it.
    for name, original in raw.items():
        if _read(directory / name, _artifact_limit(name)) != original:
            raise ValueError("saved artifacts changed during verification")
    if {path.name for path in directory.iterdir()} != set(raw):
        raise ValueError("saved artifact inventory changed during verification")
    return {"schema": "four-street-publication-verification-v1", "attempt_id": attempt_id,
            "source_commit": commit, "index_sha256": expected_index_sha256,
            "saved_only": True, "verifier_production_calls": 0,
            "production_calls_entered": status["production_calls_entered"], **result}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--expected-index-sha256", required=True)
    args = parser.parse_args(argv)
    result = verify_publication(args.directory, args.expected_index_sha256)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
