"""Census six private fingerprints of one independently validated model.

This is a no-training structural experiment. It neither authenticates a model
through fingerprints nor bypasses the existing full validation calls.
"""
from contextlib import contextmanager
from contextlib import nullcontext
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import traceback

from scripts import flop_class_reweight_cfrplus as trainer
from scripts import diagnose_flop_class_reweight_baseline as diagnostic
from scripts import flop_class_reweight_proof as reweighted
from scripts import flop_public_classes as proof
from scripts import flop_class_owned_fingerprint as owned_fingerprint
from scripts import verify_flop_class_reweight_baseline_diagnostic_publication as prerequisite
from scripts import benchmark_weighted_full_deck_flop as power
from scripts.flop_class_owned_fingerprint import Limits, fingerprint


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/flop-class-owned-fingerprint-v1.json"
SPEC_SHA256 = "dc3f92ddfe0ed1c4f1e9006683d1b1b2ae9726ab425776b3bc36b1f7ab94ef56"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_REPORT_BYTES = 2 * 1024 * 1024
SAMPLES = ("stable", "stable-repeat", "root-action-amount",
           "root-action-restored", "node-index-alias", "node-index-restored")


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _need(key not in result, "Duplicate JSON field")
        result[key] = value
    return result


def _protocol():
    _need(SPEC.stat().st_size <= MAX_SOURCE_BYTES, "Fingerprint protocol exceeds bound")
    with SPEC.open("rb") as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    _need(len(raw) <= MAX_SOURCE_BYTES and hashlib.sha256(
        raw.replace(b"\r\n", b"\n")).hexdigest() == SPEC_SHA256,
        "Fingerprint protocol bytes differ from frozen pin")
    spec = json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    expected = {
        "acceptance": {
            "authority": "Complete existing 41-production-authority guard inventory remains zero, including shared training.",
            "failure": "Retain the first original error and completed/partial census, stop later work and do not retry or discard a run.",
            "source": "Clean identical committed HEAD/status/39 LF hashes before and after the single batch.",
            "stable": "Initial repeat and both restored graph digests and censuses exactly match.",
            "tamper": "Root action-value and rooted node-index alias mutations change the fingerprint, and originals always restore in finally.",
            "validity": "Unchanged full independent model validation before and after all probes; fingerprints alone never establish validity or authorize reuse.",
        },
        "limits": {"depth": 256, "edges": 6_000_000, "integer_bits": 4096,
                   "objects": 2_000_000, "output_bytes": 268_435_456,
                   "set_bytes": 65_536, "stack": 1024, "string_chars": 16_384},
        "preflight": {
            "batch_named_cap": 50_000_000,
            "interpretation": "Named traversal reservations plus separate physical/source census bounds only; not all arithmetic, elapsed time, allocation, bytes or RSS.",
            "maximum_live_physical_oracles_reference": 2,
            "named_objects_and_edges_per_fingerprint": 8_000_000,
            "physical_oracle_builds_reference": 2,
            "physical_world_rows_reference": 11_880,
            "report_bytes": MAX_REPORT_BYTES,
            "source_file_bytes": MAX_SOURCE_BYTES,
            "source_files": 39,
            "total_named_objects_and_edges": 48_000_000,
        },
        "prerequisite": {
            "diagnostic_index_raw_sha256": prerequisite.RAW_INDEX_SHA256,
            "diagnostic_index_sha256": prerequisite.INDEX_SHA256,
            "publication_pr": 209,
        },
        "protocol_id": "fixed-flop-owned-fingerprint-v1",
        "request": {"case_id": "baseline", "fingerprint_calls": 6,
                     "full_validations": 2, "physical_model_builds": 1,
                     "training_calls": 0},
        "samples": list(SAMPLES),
        "scope": {
            "evidence": "One fresh baseline fixed-support model and six fingerprints are census/integrity evidence only. No policy, quality, speed, RSS, memory advantage or broader card/action support claim.",
            "limits": "Fingerprints detect changes between traversals; they do not prevent concurrent mutation, mutation-and-restoration, or prove poker semantics. No cache or validator bypass.",
            "method": "Type-preserving streaming graph digest with traversal-local reference ordinals and bounded atomic set ordering.",
            "provenance": "Project-owned standard-library implementation only; no third-party source or dependencies, shared kernels, defaults or Coach changes.",
        },
    }
    _need(proof._typed(spec) == proof._typed(expected),
          "Fingerprint protocol schema or admission differs")
    return raw, spec


def _preflight(spec):
    request, limits, preflight = spec["request"], spec["limits"], spec["preflight"]
    _need(proof._typed(request) == proof._typed({
        "case_id": "baseline", "fingerprint_calls": 6,
        "full_validations": 2, "physical_model_builds": 1, "training_calls": 0}),
        "Fingerprint request differs")
    limits_obj = Limits(**limits)
    reservations = (limits_obj.objects + limits_obj.edges) * request["fingerprint_calls"]
    _need(type(reservations) is int and reservations == 48_000_000 and
          reservations == preflight["total_named_objects_and_edges"] and
          reservations <= preflight["batch_named_cap"] and
          proof._typed(preflight) == proof._typed({
              "batch_named_cap": 50_000_000,
              "interpretation": preflight["interpretation"],
              "maximum_live_physical_oracles_reference": 2,
              "named_objects_and_edges_per_fingerprint": 8_000_000,
              "physical_oracle_builds_reference": 2,
              "physical_world_rows_reference": 11_880,
              "report_bytes": MAX_REPORT_BYTES,
              "source_file_bytes": MAX_SOURCE_BYTES,
              "source_files": 39,
              "total_named_objects_and_edges": 48_000_000,
          }) and type(preflight["interpretation"]) is str,
          "Full fingerprint/source/physical admission differs")
    return {"limits": {key: getattr(limits_obj, key) for key in Limits.__slots__},
            "fingerprint_calls": 6, "full_validations": 2,
            "training_calls": 0, "physical_oracle_builds_reference": 2,
            "physical_world_rows_reference": 11_880,
            "maximum_live_physical_oracles_reference": 2,
            "objects_and_edges_per_call_reservation": 8_000_000,
            "total_named_objects_and_edges": reservations,
            "batch_named_cap": 50_000_000,
            "interpretation": preflight["interpretation"]}


def _snapshot():
    state = diagnostic._snapshot()
    hashes = dict(state["source_lf_sha256"])
    additions = (
        (Path(__file__), "scripts/benchmark_flop_class_owned_fingerprint.py"),
        (Path(owned_fingerprint.__file__),
         "scripts/flop_class_owned_fingerprint.py"),
        (SPEC, "benchmarks/flop-class-owned-fingerprint-v1.json"),
        (Path(prerequisite.__file__),
         "scripts/verify_flop_class_reweight_baseline_diagnostic_publication.py"),
    )
    for path, relative in additions:
        _need(path.stat().st_size <= MAX_SOURCE_BYTES, f"Source exceeds bound: {relative}")
        with path.open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        _need(len(raw) <= MAX_SOURCE_BYTES, f"Source exceeds bound: {relative}")
        hashes[relative] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    _need(len(hashes) == 39 and state.get("status") == "" and
          type(state.get("revision")) is str and len(state["revision"]) == 40 and
          all(ch in "0123456789abcdef" for ch in state["revision"]),
          "Fingerprint source snapshot is dirty or has an unexpected inventory")
    return {**state, "source_lf_sha256": dict(sorted(hashes.items()))}


def _write_report(directory, report):
    unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
    report["report_sha256"] = proof._digest(unsigned)
    raw = json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    _need(len(raw) <= MAX_REPORT_BYTES, "Fingerprint report exceeds bound")
    temp = directory / "report.json.tmp"
    with temp.open("xb") as stream:
        stream.write(raw)
    temp.replace(directory / "report.json")


def _output_directory(path):
    original = Path(path).absolute()
    _need(not original.exists() and not original.is_symlink(),
          "Fingerprint output must be a new directory")
    _need(all(not parent.is_symlink() for parent in original.parents),
          "Fingerprint output cannot traverse symlinks")
    target = original.resolve()
    root = ROOT.resolve()
    _need(not target.is_relative_to(root) and not root.is_relative_to(target),
          "Fingerprint output must be outside and separate from the source checkout")
    target.mkdir(parents=True)
    return target


def _raw_guard_receipt(calls):
    _need(type(calls) is dict and len(calls) == 41 and
          all(type(name) is str and type(value) is int for name, value in calls.items()),
          "The complete 41-entry production authority guard inventory is malformed")
    return dict(sorted(calls.items()))


def _guard_receipt(calls):
    result = _raw_guard_receipt(calls)
    _need(all(value == 0 for value in result.values()),
          "The complete 41-entry production authority guard is not zero")
    return result


def _fingerprint_record(sample_id, model, report, limits):
    report["fingerprint_calls"] += 1
    try:
        digest, census = fingerprint(model, limits=limits)
    except BaseException as exc:
        report["fingerprints"].append({
            "sample_id": sample_id, "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "partial_census": getattr(exc, "partial_census", None),
        })
        raise
    report["fingerprints"].append({
        "sample_id": sample_id, "status": "complete", "sha256": digest,
        "census": census,
    })
    return digest, census


def run(output, *, execution_state=None):
    """Run one admitted no-training census; tests replace all external work."""
    directory = None
    report = {"schema_version": 1, "protocol_id": "fixed-flop-owned-fingerprint-v1",
              "status": "not-started", "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "finished_at_utc": None, "protocol_sha256": None, "admission": None,
              "source_before": None, "source_after": None, "prerequisite": None,
              "physical_model_census": None, "fingerprints": [], "fingerprint_calls": 0,
              "full_validations": 0, "training_calls": 0, "authority_calls": None,
              "runtime": {"python": sys.version,
                          "implementation": platform.python_implementation(),
                          "platform": platform.platform()},
              "execution_state": None,
              "errors": [], "report_sha256": None}
    first_error = None
    cleanup_errors = []
    model = None
    action_mutation = None
    alias_mutation = None
    guard_calls = None
    guard_receipt_source = None
    limits = None
    initial_validation_succeeded = False
    try:
        protocol_raw, spec = _protocol()
        admission = _preflight(spec)  # complete admission before D029 auth/model creation
        directory = _output_directory(output)
        limits = Limits(**admission["limits"])
        report["execution_state"] = diagnostic.evidence._execution_state(execution_state)
        report.update(status="running", protocol_sha256=hashlib.sha256(
            protocol_raw.replace(b"\r\n", b"\n")).hexdigest(), admission=admission)
        report["source_before"] = _snapshot()
        _write_report(directory, report)

        receipt = prerequisite.verify()
        _need(type(receipt) is dict and
              receipt.get("status") == "saved-baseline-diagnostic-authenticated" and
              receipt.get("samples") == 2 and receipt.get("recorded_training_calls") == 2 and
              receipt.get("training_calls") == 0 and receipt.get("phase_events") == 13 and
              receipt.get("index_sha256") == spec["prerequisite"]["diagnostic_index_sha256"],
              "Saved D029 prerequisite authentication differs")
        report["prerequisite"] = {
            "publication_pr": 209,
            "index_raw_sha256": prerequisite.RAW_INDEX_SHA256,
            "index_sha256": prerequisite.INDEX_SHA256,
            "status": receipt["status"], "recorded_training_calls": 2,
            "verification_training_calls": 0, "phase_events": receipt["phase_events"]}
        auth_after = _snapshot()
        _need(proof._typed(auth_after) == proof._typed(report["source_before"]),
              "Source changed during D029 authentication")
        _write_report(directory, report)

        plan = trainer.case_plan("baseline")
        with proof.independent_guard() as calls:
            guard_receipt_source = calls
            try:
                model = reweighted.build_model(plan)
                _need(type(model) is reweighted.WeightedClassModel and
                      model.baseline is not model.physical and
                      len(model.baseline["worlds"]) == len(model.physical["worlds"]) == 5_940 and
                      len(model.physical["nodes"]) > 0 and model.physical["root"] is not None,
                      "Prepared model differs from fixed baseline census")
                _need(all(model.census.get(key) == value
                          for key, value in reweighted.EXPECTED_CENSUS.items()),
                      "Prepared compact census differs from fixed baseline")
                report["physical_model_census"] = {
                    "physical_oracle_builds": 2,
                    "baseline_physical_worlds": len(model.baseline["worlds"]),
                    "weighted_physical_worlds": len(model.physical["worlds"]),
                    "physical_world_rows_reference":
                        len(model.baseline["worlds"]) + len(model.physical["worlds"]),
                    "maximum_live_physical_oracles_reference": 2,
                    "baseline_public_states": model.baseline["public_states"],
                    "weighted_public_states": model.physical["public_states"],
                    "compact_census": dict(model.census),
                }
                report["full_validations"] += 1
                reweighted.validate_model(model)
                initial_validation_succeeded = True
                stable, stable_census = _fingerprint_record("stable", model, report, limits)
                repeated, repeated_census = _fingerprint_record(
                    "stable-repeat", model, report, limits)
                _need((stable, stable_census) == (repeated, repeated_census),
                      "Repeated stable fingerprints differ")

                root = model.physical["root"]
                _need(type(root.actions) is tuple and bool(root.actions) and
                      type(root.actions[0]) is dict and type(root.actions[0].get("amount")) in
                      (int, float) and math.isfinite(root.actions[0]["amount"]),
                      "Physical root does not expose a finite action amount")
                action = root.actions[0]
                original_amount = action["amount"]
                action_mutation = (action, original_amount)
                try:
                    action["amount"] = original_amount + 1.0
                    changed_action, _ = _fingerprint_record(
                        "root-action-amount", model, report, limits)
                finally:
                    action["amount"] = original_amount
                    action_mutation = None
                restored_action, restored_action_census = _fingerprint_record(
                    "root-action-restored", model, report, limits)
                _need(changed_action != stable and (restored_action, restored_action_census) ==
                      (stable, stable_census), "Root-action mutation was not detected/restored")

                nodes = model.physical["nodes"]
                key = (root.player, root.history)
                original_node = nodes.get(key)
                _need(original_node is root, "Physical node index is not aliased to rooted node")
                alias_mutation = (nodes, key, original_node)
                try:
                    replacement = type(root)(root.history, root.player, root.street,
                                             root.board, root.actions, root.children)
                    nodes[key] = replacement
                    changed_alias, _ = _fingerprint_record(
                        "node-index-alias", model, report, limits)
                finally:
                    nodes[key] = original_node
                    alias_mutation = None
                restored_alias, restored_alias_census = _fingerprint_record(
                    "node-index-restored", model, report, limits)
                _need(changed_alias not in (stable, changed_action) and
                      (restored_alias, restored_alias_census) == (stable, stable_census),
                      "Node-index alias mutation was not detected/restored")
            except BaseException as exc:
                if first_error is None:
                    first_error = {"message": f"{type(exc).__name__}: {exc}",
                                   "traceback": traceback.format_exc()}
            finally:
                if action_mutation is not None:
                    action_mutation[0]["amount"] = action_mutation[1]
                    action_mutation = None
                if alias_mutation is not None:
                    alias_mutation[0][alias_mutation[1]] = alias_mutation[2]
                    alias_mutation = None
                if model is not None and initial_validation_succeeded:
                    report["full_validations"] += 1
                    try:
                        reweighted.validate_model(model)
                    except BaseException as exc:
                        cleanup_errors.append({"phase": "final-model-validation",
                            "message": f"{type(exc).__name__}: {exc}",
                            "traceback": traceback.format_exc()})
        report["authority_calls"] = _raw_guard_receipt(guard_receipt_source)
        _guard_receipt(guard_receipt_source)
        if first_error is None:
            _need(report["fingerprint_calls"] == 6 and report["full_validations"] == 2 and
                  report["training_calls"] == 0 and len(report["fingerprints"]) == 6,
                  "Fingerprint or full-validation call census differs")
    except BaseException as exc:
        if first_error is None:
            first_error = {"message": f"{type(exc).__name__}: {exc}",
                           "traceback": traceback.format_exc()}
    finally:
        if action_mutation is not None:
            try:
                action_mutation[0]["amount"] = action_mutation[1]
            except BaseException as exc:
                cleanup_errors.append({"phase": "restore-action",
                    "message": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()})
        if alias_mutation is not None:
            try:
                alias_mutation[0][alias_mutation[1]] = alias_mutation[2]
            except BaseException as exc:
                cleanup_errors.append({"phase": "restore-node-index",
                    "message": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()})
        try:
            if report["source_before"] is not None:
                report["source_after"] = _snapshot()
                _need(proof._typed(report["source_after"]) ==
                      proof._typed(report["source_before"]),
                      "Source changed during owned-model census")
        except BaseException as exc:
            cleanup_errors.append({"phase": "final-source-snapshot",
                "message": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()})
        if guard_receipt_source is not None and report["authority_calls"] is None:
            try:
                report["authority_calls"] = _raw_guard_receipt(guard_receipt_source)
                _guard_receipt(guard_receipt_source)
            except BaseException as exc:
                if report["authority_calls"] is None:
                    try:
                        report["authority_calls"] = dict(sorted(guard_receipt_source.items()))
                    except BaseException:
                        pass
                cleanup_errors.append({"phase": "authority-guard-receipt",
                    "message": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc()})
        if first_error is not None:
            report["errors"].append({"phase": "run", **first_error})
        report["errors"].extend(cleanup_errors)
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["status"] = ("complete" if first_error is None and not cleanup_errors and
                             report["fingerprint_calls"] == 6 and
                             report["full_validations"] == 2 and
                             report["training_calls"] == 0 and
                             report["authority_calls"] is not None else "error")
        if directory is not None:
            try:
                _write_report(directory, report)
            except BaseException:
                if first_error is None:
                    raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    context = (power.measurement_execution_state() if sys.platform == "win32" else
               nullcontext({"mode": "ordinary-process", "system_required": False}))
    with context as state:
        report = run(args.output, execution_state=state)
    print(json.dumps({"status": report["status"],
                      "fingerprint_calls": report["fingerprint_calls"],
                      "full_validations": report["full_validations"],
                      "training_calls": report["training_calls"],
                      "report_sha256": report.get("report_sha256")}, sort_keys=True))
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
