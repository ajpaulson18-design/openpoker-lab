"""One frozen no-training full equivalence batch on the second flop board."""
from contextlib import contextmanager, ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import traceback
from unittest.mock import patch

from scripts import benchmark_flop_second_board_reference as previous
from scripts import flop_second_board_equivalence as proof


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/flop-second-board-equivalence-v1.json"
SPEC_SHA256 = "f27d10e7f23968d5d8a6826e098b7fa5cbb643b2263f9b73077c98e4878e2198"
SOURCE_COUNT = 49
MAX_SOURCE_BYTES = previous.MAX_SOURCE_BYTES
MAX_MODEL_PROOFS = 10
MAX_ROW_TABLES = 100
PROOF_PASS_RESERVATION = 250000 + 250000 + 100000 + 5940 + 170 + (5940 + 170) * 33
EXACT_TERM_RESERVATION = 4 * 3 * (5940 + 170) * 33
NUMERIC_TERM_RESERVATION = 4 * 3 * 5940 * 33
ROW_SLOT_RESERVATION = MAX_ROW_TABLES * 20000 * 2
NAMED_RESERVATION = (MAX_MODEL_PROOFS * PROOF_PASS_RESERVATION + EXACT_TERM_RESERVATION
                     + NUMERIC_TERM_RESERVATION + ROW_SLOT_RESERVATION)
_need = proof._need


def expected_protocol():
    return {
        "protocol_id": "fixed-flop-second-board-equivalence-v1",
        "request": {"model": proof.admission(), "controls": list(proof.MODES),
                    "negative_controls": ["within-class-card-variation", "near-normalized"],
                    "full_model_proofs": MAX_MODEL_PROOFS, "exact_metric_calls": 8,
                    "numeric_replays": 4, "projection_attempts": 6, "training_calls": 0},
        "limits": {"named_cap": 20000000, "named_reservation": NAMED_RESERVATION,
                   "proof_pass_reservation": PROOF_PASS_RESERVATION,
                   "exact_world_node_terms": EXACT_TERM_RESERVATION,
                   "numeric_world_node_terms": NUMERIC_TERM_RESERVATION,
                   "expected_row_tables": MAX_ROW_TABLES, "row_action_slots": ROW_SLOT_RESERVATION,
                   "partition_items": 100000, "mass_integer_bits": 384,
                   "source_files": SOURCE_COUNT, "source_file_bytes": MAX_SOURCE_BYTES,
                   "payload_files": 6, "index_bytes": previous.MAX_INDEX_BYTES,
                   "failure_fallback_raw_files": 1,
                   "failure_fallback_raw_bytes": previous.MAX_PAYLOAD_BYTES,
                   "raw_payload_bytes_each": previous.MAX_PAYLOAD_BYTES,
                   "gzip_bytes_each": previous.MAX_GZIP_BYTES,
                   "aggregate_raw_payload_bytes": 6 * previous.MAX_PAYLOAD_BYTES,
                   "aggregate_gzip_bytes": 6 * previous.MAX_GZIP_BYTES},
        "prerequisite": {"publication_pr": 212,
                         "index_raw_sha256": proof.prerequisite.RAW_INDEX_SHA256,
                         "index_sha256": proof.prerequisite.INDEX_SHA256,
                         "worlds_sha256": proof.prerequisite.WORLDS_SHA256,
                         "tree_sha256": proof.prerequisite.TREE_SHA256},
        "acceptance": {
            "structure": "Fresh physical anchors, exact joint support/masses/signs, both reveal layers and complete numeric betting subtrees agree; all model proofs complete.",
            "positive_controls": "Check-call, bet-fold, across-class-varying and zero-reach retain every row and action, exact lift/project identity and all eight exact compact/unrestricted-own-hand metrics with numeric replay gap <=1e-10.",
            "negative_controls": "Within-class physical-card variation and near-normalized binary64 probabilities reject projection; preserve both complete intentionally invalid policies and original errors.",
            "source": "Clean identical committed HEAD/status and 49 named dependency LF hashes before/after the single batch.",
            "failure": "Retain first error, cleanup errors, partial boundary counters and completed/partial payloads; no retries or discarded observations.",
            "authority": "All 41 guarded production authorities remain zero; no training."},
        "scope": {
            "bounds": "Named model/tree/partition/path/row reservations and separate rank/source/output limits only; not all internal loops, arithmetic, allocation, runtime or RSS.",
            "method": "Independent project-owned joint-mass auditor and complete tree collapse; unchanged generic rational own-hand best responses and separate numeric physical replay for the fixed pot10 game.",
            "claims": "One finite second-board game and four exactly normalized class-constant controls; no trained policy, convergence, speed, memory or unrestricted NLHE claim. Candidate-only flags remain unchanged.",
            "provenance": "Project-owned standard-library additions; no third-party source/dependency, shared turn/river kernel, default or Coach change."}}


def _protocol():
    _need(SPEC.stat().st_size <= MAX_SOURCE_BYTES, "Protocol exceeds source bound")
    with SPEC.open("rb") as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    _need(len(raw) <= MAX_SOURCE_BYTES and hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
          == SPEC_SHA256, "Equivalence protocol differs from frozen pin")
    spec = json.loads(raw, object_pairs_hook=previous.previous._pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    _need(proof._typed(spec) == proof._typed(expected_protocol()), "Equivalence protocol differs")
    return raw, spec


def _preflight(spec):
    _need(proof._typed(spec) == proof._typed(expected_protocol()) and NAMED_RESERVATION == 16849200
          and NAMED_RESERVATION <= spec["limits"]["named_cap"]
          and proof.partition_proof.MAX_PARTITION_ITEMS == 100000
          and proof.partition_proof.MAX_INTEGER_BITS == 384,
          "Full requested equivalence admission differs")
    return {"request": spec["request"], "limits": spec["limits"],
            "interpretation": spec["scope"]["bounds"]}


def _snapshot():
    state = previous._snapshot()
    hashes = dict(state["source_lf_sha256"])
    additions = ((Path(__file__), "scripts/benchmark_flop_second_board_equivalence.py"),
                 (Path(proof.__file__), "scripts/flop_second_board_equivalence.py"),
                 (Path(proof.partition_proof.__file__), "scripts/flop_second_board_partition_proof.py"),
                 (Path(proof.prerequisite.__file__),
                  "scripts/verify_flop_second_board_reference_publication.py"),
                 (SPEC, "benchmarks/flop-second-board-equivalence-v1.json"))
    for path, relative in additions:
        _need(path.stat().st_size <= MAX_SOURCE_BYTES, "Named source exceeds byte bound")
        with path.open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        _need(len(raw) <= MAX_SOURCE_BYTES, "Named source changed beyond byte bound")
        hashes[relative] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    _need(state["status"] == "" and len(hashes) == SOURCE_COUNT,
          "Equivalence source inventory differs or checkout is dirty")
    return {**state, "source_lf_sha256": dict(sorted(hashes.items()))}


def _write_index(directory, report):
    """Keep a failed output policy in the returned API report, outside JSON limits."""
    saved = {key: value for key, value in report.items() if key != "unserialized_policy"}
    if "unserialized_policy" in report:
        receipt = {"available_in_returned_api_report": True, "durably_saved": False,
                   "reason": "Both admitted policy output paths failed; available policy remains in memory only."}
        saved["unserialized_policy_retention"] = receipt
        report["unserialized_policy_retention"] = receipt
    previous._write_index(directory, saved)
    report["index_sha256"] = saved["index_sha256"]


@contextmanager
def _instrument(observed):
    """Bound named call families and restore every wrapper on every exit."""
    observed.update(full_model_proofs=0, exact_metric_calls=0, numeric_replays=0,
                    projection_attempts=0, expected_row_tables=0, row_action_slots=0,
                    exact_world_node_terms=0, numeric_world_node_terms=0)

    def counted(module, name, counter, limit, *, family=None):
        original = getattr(module, name)

        def wrapper(*args, **kwargs):
            observed[counter] += 1
            _need(observed[counter] <= limit, f"Boundary allowance exceeded: {counter}")
            if family == "exact":
                worlds = args[1]
                _need(type(worlds) is tuple and len(worlds) in (170, 5940),
                      "Exact world support is unadmitted")
                observed["exact_world_node_terms"] += 3 * len(worlds) * 33
                _need(observed["exact_world_node_terms"] <= EXACT_TERM_RESERVATION,
                      "Exact world-node term reservation exceeded")
            elif family == "numeric":
                observed["numeric_world_node_terms"] += 3 * 5940 * 33
                _need(observed["numeric_world_node_terms"] <= NUMERIC_TERM_RESERVATION,
                      "Numeric world-node term reservation exceeded")
            result = original(*args, **kwargs)
            if family == "rows":
                _need(type(result) is dict and len(result) <= 20000, "Observed row table exceeds bound")
                observed["row_action_slots"] += 2 * len(result)
                _need(observed["row_action_slots"] <= ROW_SLOT_RESERVATION,
                      "Observed row-action reservation exceeded")
            return result
        return patch.object(module, name, wrapper)

    with ExitStack() as stack:
        stack.enter_context(counted(proof, "_make_model", "full_model_proofs", MAX_MODEL_PROOFS))
        stack.enter_context(counted(proof.shared, "_exact_metrics", "exact_metric_calls", 8, family="exact"))
        stack.enter_context(counted(proof.physical, "replay", "numeric_replays", 4, family="numeric"))
        stack.enter_context(counted(proof, "_project", "projection_attempts", 6))
        stack.enter_context(counted(proof, "_expected_rows", "expected_row_tables", MAX_ROW_TABLES, family="rows"))
        yield observed


def _payload(directory, name, payload):
    target = directory / name
    target.mkdir()
    receipt = previous._write_payload(target, payload)
    return {**receipt, "path": name + "/" + receipt["path"]}


def _raw_fallback(directory, name, payload):
    """Retain available policy bytes after a gzip failure; never rerun an audit."""
    target = directory / name
    target.mkdir(exist_ok=True)
    partial = target / "physical-policy.raw.json.partial"
    final = target / "physical-policy.raw.json"
    digest, total = hashlib.sha256(), 0
    with partial.open("xb") as stream:
        encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)
        for chunk in encoder.iterencode(payload):
            raw = chunk.encode("utf-8")
            _need(total + len(raw) <= previous.MAX_PAYLOAD_BYTES, "Raw failure fallback exceeds bound")
            stream.write(raw)
            digest.update(raw)
            total += len(raw)
        _need(total + 1 <= previous.MAX_PAYLOAD_BYTES, "Raw failure fallback exceeds bound")
        stream.write(b"\n")
        digest.update(b"\n")
        total += 1
    partial.replace(final)
    return {"path": name + "/" + final.name, "raw_bytes": total,
            "raw_sha256": digest.hexdigest(), "format": "raw-json-failure-fallback"}


def _positive(model, mode, directory, records):
    observation, first_error = {}, None
    record = {"mode": mode, "status": "running"}
    records.append(record)
    try:
        proof.audit_control(model, mode, observation=observation)
    except BaseException as exc:
        first_error = exc
        record.update(status="error", error=f"{type(exc).__name__}: {exc}",
                      traceback=traceback.format_exc())
    record.update({key: value for key, value in observation.items() if key != "physical_policy"})
    if "physical_policy" in observation:
        try:
            record["payload"] = _payload(directory, mode, observation["physical_policy"])
        except BaseException as exc:
            record.update(status="error", serialization_error=f"{type(exc).__name__}: {exc}")
            if first_error is None:
                first_error = exc
            try:
                record["fallback_payload"] = _raw_fallback(directory, mode, observation["physical_policy"])
            except BaseException as fallback_error:
                record["fallback_error"] = f"{type(fallback_error).__name__}: {fallback_error}"
                record["retained_partial_paths"] = [
                    mode + "/reference.json.gz.partial", mode + "/physical-policy.raw.json.partial"]
                first_error.second_board_unserialized_policy = observation["physical_policy"]
    if first_error is not None:
        record["status"] = "error"
        raise first_error
    _need(record.get("status") == "complete" and record.get("final_model_validation") == "passed",
          "Positive control did not complete unchanged model validation")
    return observation["physical_policy"]


def _negative(model, original, mode, directory, records):
    _need(type(original) is dict and type(original.get("strategy")) is list
          and 0 < len(original["strategy"]) <= proof.MAX_POLICY_ROWS,
          "Negative-policy source exceeds admitted rows")
    payload = deepcopy(original)
    selected = None
    if mode == "within-class-card-variation":
        seen = {}
        for index, row in enumerate(payload["strategy"]):
            key = (row["player"], row["hand"], proof.shared._mapped_history(
                tuple(row["history"]), model.turns, model.rivers))
            if key in seen:
                selected = index
                break
            seen[key] = index
        _need(selected is not None, "No physical-card members share a compact own-hand row")
        replacement = (0.75, 0.25)
        fragment = "Within-class physical-card probabilities differ bitwise"
    else:
        _need(mode == "near-normalized", "Unknown negative control")
        selected, replacement = 0, (1.0, 2.0 ** -54)
        fragment = "Exact audit requires binary64 probabilities summing exactly to one"
    row = payload["strategy"][selected]
    before = [action["probability"] for action in row["actions"]]
    for action, value in zip(row["actions"], replacement):
        action["probability"] = value
    record = {"mode": mode, "status": "running", "physical_row_index": selected,
              "player": row["player"], "hand": row["hand"], "history": row["history"],
              "before_probabilities": before, "after_probabilities": list(replacement),
              "qualification": "Intentionally invalid projection control; metric headers remain from the original zero-reach policy."}
    records.append(record)
    try:
        record["payload"] = _payload(directory, mode, payload)  # preserve unexpected acceptance too
    except BaseException as exc:
        record.update(status="error", serialization_error=f"{type(exc).__name__}: {exc}")
        try:
            record["fallback_payload"] = _raw_fallback(directory, mode, payload)
        except BaseException as fallback_error:
            record["fallback_error"] = f"{type(fallback_error).__name__}: {fallback_error}"
            record["retained_partial_paths"] = [
                mode + "/reference.json.gz.partial", mode + "/physical-policy.raw.json.partial"]
            exc.second_board_unserialized_policy = payload
        raise
    try:
        proof._project(payload, model)
    except ValueError as exc:
        record["rejection"] = f"{type(exc).__name__}: {exc}"
        record["status"] = "error"
        _need(fragment in str(exc), "Negative policy failed for an unexpected reason")
        record["status"] = "expected-rejection"
    else:
        record["status"] = "unexpected-acceptance"
        raise ValueError("Intentionally invalid physical policy was accepted")


def _completed(report):
    observed = report["boundaries"]
    _need(all(type(observed.get(key)) is int and observed[key] == value for key, value in {
        "full_model_proofs": 10, "exact_metric_calls": 8, "numeric_replays": 4,
        "projection_attempts": 6, "exact_world_node_terms": EXACT_TERM_RESERVATION,
        "numeric_world_node_terms": NUMERIC_TERM_RESERVATION}.items()),
        "Completed equivalence boundary counts differ")
    _need(type(observed.get("expected_row_tables")) is int
          and 0 < observed["expected_row_tables"] <= MAX_ROW_TABLES
          and 0 < observed["row_action_slots"] <= ROW_SLOT_RESERVATION,
          "Completed row-family counts differ")
    progress = report["preparation"]
    _need(all(type(progress.get(key)) is int and progress[key] == value for key, value in {
        "physical_builds_attempted": 1, "physical_builds_completed": 1,
        "preparation_ranker_attempts": 4134, "preparation_rank_calls": 4134}.items()),
        "Completed physical preparation counters differ")
    _need(len(report["controls"]) == 4 and tuple(row["mode"] for row in report["controls"]) == proof.MODES
          and all(row["status"] == "complete" for row in report["controls"])
          and len(report["negative_controls"]) == 2
          and all(row["status"] == "expected-rejection" for row in report["negative_controls"]),
          "Complete positive/negative control inventory differs")
    receipts = [row["payload"] for row in report["controls"] + report["negative_controls"]]
    _need(len({row["path"] for row in receipts}) == 6
          and sum(row["raw_bytes"] for row in receipts) <= 6 * previous.MAX_PAYLOAD_BYTES
          and sum(row["gzip_bytes"] for row in receipts) <= 6 * previous.MAX_GZIP_BYTES,
          "Complete lossless payload inventory/reservation differs")


def run(output, *, execution_state=None):
    directory, first_error, guard_calls = None, None, None
    report = {"schema_version": 1, "protocol_id": "fixed-flop-second-board-equivalence-v1",
              "created_at_utc": datetime.now(timezone.utc).isoformat(), "finished_at_utc": None,
              "status": "not-started", "protocol_sha256": None, "admission": None,
              "source_before": None, "source_after": None, "preparation": {}, "boundaries": {},
              "census": None, "partition": None, "compact_worlds": None,
              "controls": [], "negative_controls": [], "authority_calls": None,
              "training_calls": 0, "errors": [], "index_sha256": None,
              "execution_state": None, "runtime": {"python": sys.version,
                  "implementation": platform.python_implementation(), "platform": platform.platform()}}
    try:
        raw, spec = _protocol()
        report["admission"] = _preflight(spec)  # full batch before authentication/model preparation
        directory = previous._output_directory(output)
        report["execution_state"] = previous.previous.diagnostic.evidence._execution_state(execution_state)
        report["protocol_sha256"] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
        report["source_before"] = _snapshot()
        report["status"] = "running"
        _write_index(directory, report)
        with proof.shared.independent_guard() as calls, _instrument(report["boundaries"]):
            guard_calls = calls
            try:
                model = proof.build_model(progress=report["preparation"])
                report["census"], report["partition"] = model.census, model.partition
                report["compact_worlds"] = proof.shared._world_rows(model.worlds)
                _write_index(directory, report)
                last_policy = None
                for mode in proof.MODES:
                    last_policy = _positive(model, mode, directory, report["controls"])
                    _write_index(directory, report)
                for mode in spec["request"]["negative_controls"]:
                    _negative(model, last_policy, mode, directory, report["negative_controls"])
                    _write_index(directory, report)
                proof.validate_model(model)
                _completed(report)
            except BaseException as exc:
                if hasattr(exc, "second_board_unserialized_policy"):
                    report["unserialized_policy"] = exc.second_board_unserialized_policy
                first_error = {"message": f"{type(exc).__name__}: {exc}",
                               "traceback": traceback.format_exc(),
                               "control_cleanup_error": getattr(exc, "second_board_cleanup_error", None)}
        report["authority_calls"] = previous.previous._raw_guard_receipt(guard_calls)
        previous.previous._guard_receipt(guard_calls)
    except BaseException as exc:
        if hasattr(exc, "second_board_unserialized_policy"):
            report["unserialized_policy"] = exc.second_board_unserialized_policy
        error = {"message": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
        if first_error is None:
            first_error = error
        else:
            report["errors"].append({"phase": "after-first-error", **error})
    finally:
        if guard_calls is not None:
            report["authority_calls"] = dict(sorted(guard_calls.items()))
        if report["source_before"] is not None:
            try:
                report["source_after"] = _snapshot()
                _need(proof._typed(report["source_before"]) == proof._typed(report["source_after"]),
                      "Source changed during equivalence batch")
            except BaseException as exc:
                report["errors"].append({"phase": "source-finalization",
                                         "message": f"{type(exc).__name__}: {exc}"})
        if first_error is not None:
            report["errors"].insert(0, first_error)
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["status"] = "error" if report["errors"] else "no-training-equivalence-verified"
        if directory is not None:
            try:
                _write_index(directory, report)
            except BaseException as exc:
                report["errors"].append({"phase": "final-index-write",
                                         "message": f"{type(exc).__name__}: {exc}"})
                report.update(status="error", index_sha256=None)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(args.output, execution_state={"mode": "ordinary-process", "system_required": False})
    print(json.dumps({"status": report["status"], "errors": report["errors"],
                      "boundaries": report["boundaries"], "index_sha256": report["index_sha256"]}, sort_keys=True))
    return 0 if report["status"] == "no-training-equivalence-verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
