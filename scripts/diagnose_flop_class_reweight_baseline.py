"""Two bounded, single-call diagnostics for the fixed baseline range prior."""
from contextlib import nullcontext
from datetime import datetime, timezone
import argparse
import gc
import gzip
import hashlib
import json
from pathlib import Path
import platform
import sys
import traceback
from unittest.mock import patch

from pokerlab import cfr_plus
from scripts import benchmark_flop_class_reweight as evidence
from scripts import benchmark_flop_class_reweight_cfrplus as trainer
from scripts import benchmark_weighted_full_deck_flop as power
from scripts import flop_class_call_measurement as measurement
from scripts import flop_class_policy as policy
from scripts import flop_class_reweight_cfrplus as adapter
from scripts import flop_public_classes as proof
from scripts import profile_flop_class_phases as profiler
from scripts import verify_flop_class_reweight_cfrplus_publication as publication

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/flop-class-reweight-baseline-diagnostic-v1.json"
SPEC_SHA256 = "54d2773c8046923727985c4714a766ceca3b28d61739c743bdff1a9e6b2cbbe7"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_RAW_BYTES = 24 * 1024 * 1024
MAX_GZIP_BYTES = 8 * 1024 * 1024
MAX_INDEX_BYTES = 2 * 1024 * 1024


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _protocol():
    _need(SPEC.stat().st_size <= MAX_SOURCE_BYTES, "Diagnostic protocol exceeds bound")
    with SPEC.open("rb") as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    _need(len(raw) <= MAX_SOURCE_BYTES and hashlib.sha256(
        raw.replace(b"\r\n", b"\n")).hexdigest() == SPEC_SHA256,
        "Diagnostic protocol bytes differ")
    spec = json.loads(raw, object_pairs_hook=evidence._pairs,
                      parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    expected_samples = [
        {"sample_id": "phase-profile", "phase_instrumentation": True,
         "allocation_trace": False},
        {"sample_id": "python-allocation", "phase_instrumentation": False,
         "allocation_trace": True},
    ]
    _need(type(spec) is dict and spec.get("protocol_id") ==
          "fixed-flop-prior-baseline-diagnostic-v1" and
          type(spec.get("request")) is dict and spec["request"] == {
              "calls": 2, "case_id": "baseline", "iterations": 560} and
          spec.get("samples") == expected_samples and spec.get("event_limit") == 1000 and
          profiler.MAX_EVENTS == spec.get("event_limit") and
          spec.get("limits") == {"gzip_file_bytes": MAX_GZIP_BYTES,
                                  "index_bytes": MAX_INDEX_BYTES,
                                  "raw_file_bytes": MAX_RAW_BYTES,
                                  "source_bytes": MAX_SOURCE_BYTES} and
          spec.get("instrumented_boundaries") == [row[0] for row in _targets()] and
          spec.get("pilot") == {
              "baseline_artifact_sha256": "a3f94b109cff3ce8e4b487b4a376160f152d4114ec39173a31f8db6e1a51983d",
              "baseline_raw_sha256": "902420ca04f52e1b64fda5127adc074357e41151e07565488d3d859399147cf9",
              "index_raw_sha256": publication.INDEX_RAW_SHA256,
              "index_sha256": publication.INDEX_SHA256},
          "Frozen diagnostic dimensions or pilot identity differ")
    return raw, spec


def _targets():
    weighted = adapter.reweighted
    return (
        ("weighted.publication.verify", adapter.publication, "verify"),
        ("weighted.compact_publication._read", adapter.compact_publication, "_read"),
        ("weighted.build_model", weighted, "build_model"),
        ("weighted._training_inputs", adapter, "_training_inputs"),
        ("cfr_plus.train", cfr_plus, "train"),
        ("policy.canonicalize_binary_rows", policy, "canonicalize_binary_rows"),
        ("weighted.lift_policy", weighted, "lift_policy"),
        ("weighted.audit_policy", weighted, "audit_policy"),
        ("weighted.validate_model", weighted, "validate_model"),
    )


def _preflight(spec):
    requests = [adapter.admit_request("baseline", 560) for _ in spec["samples"]]
    total = sum(item["total_admitted_work"] for item in requests)
    preflight = spec["preflight"]
    _need(type(preflight.get("batch_logical_cap")) is int and
          preflight["batch_logical_cap"] == 153_000_000 and
          type(preflight.get("logical_work_per_call")) is int and
          preflight["logical_work_per_call"] == 75_107_956 and
          type(preflight.get("total_logical_work")) is int and
          total == preflight["total_logical_work"] == 150_215_912 and
          total <= preflight["batch_logical_cap"] and
          type(preflight.get("physical_oracle_builds_reference")) is int and
          preflight["physical_oracle_builds_reference"] == 4 and
          type(preflight.get("enumerated_physical_world_rows_reference")) is int and
          preflight["enumerated_physical_world_rows_reference"] == 23_760 and
          type(preflight.get("maximum_live_physical_oracles_reference")) is int and
          preflight["maximum_live_physical_oracles_reference"] == 2 and
          all(item["total_admitted_work"] == preflight["logical_work_per_call"]
              for item in requests), "Two-call logical/physical preflight differs")
    return requests, total


def _runtime_gate(spec):
    gate = spec["runtime_admission"]
    _need(type(gate) is dict and gate.get("implementation") == platform.python_implementation() and
          gate.get("implementation") == "CPython" and
          gate.get("python_version") == platform.python_version(),
          "Runtime differs from the raw-pilot identity; measured calls are not admitted")


def _snapshot():
    state = trainer._snapshot()
    files = (
        (Path(__file__), "scripts/diagnose_flop_class_reweight_baseline.py"),
        (SPEC, "benchmarks/flop-class-reweight-baseline-diagnostic-v1.json"),
        (Path(profiler.__file__), "scripts/profile_flop_class_phases.py"),
        (Path(publication.__file__), "scripts/verify_flop_class_reweight_cfrplus_publication.py"),
    )
    hashes = dict(state["source_lf_sha256"])
    for path, name in files:
        _need(path.stat().st_size <= MAX_SOURCE_BYTES, f"Bounded source exceeds limit: {name}")
        with path.open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        _need(len(raw) <= MAX_SOURCE_BYTES, f"Bounded source exceeds limit: {name}")
        hashes[name] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    _need(len(hashes) == 35 and type(state.get("revision")) is str and
          len(state["revision"]) == 40 and all(ch in "0123456789abcdef" for ch in state["revision"]) and
          state.get("status") == "" and
          all(type(name) is str and type(digest) is str and len(digest) == 64
              and all(ch in "0123456789abcdef" for ch in digest)
              for name, digest in hashes.items()),
          "Diagnostic source manifest or clean Git snapshot differs")
    return {**state, "source_lf_sha256": dict(sorted(hashes.items()))}


def _authenticate_baseline():
    raw_index, index = publication._read_index(publication.PUBLICATION / "index.json")
    _need(hashlib.sha256(raw_index).hexdigest() == publication.INDEX_RAW_SHA256 and
          index.get("index_sha256") == publication.INDEX_SHA256,
          "Historical pilot index identity differs")
    entry = next((row for row in index.get("files", [])
                  if row.get("path") == "baseline-560.json.gz"), None)
    expected = _protocol()[1]["pilot"]
    _need(entry is not None and entry.get("raw_sha256") == expected["baseline_raw_sha256"],
          "Historical baseline report pointer differs")
    raw, report = publication._read_gzip(publication.PUBLICATION, entry)
    _need(hashlib.sha256(raw).hexdigest() == expected["baseline_raw_sha256"] and
          report.get("artifact_sha256") == expected["baseline_artifact_sha256"] and
          report.get("quality_target_met") is True and
          report.get("case_id") == "baseline" and
          report.get("physical_policy", {}).get("iterations") == 560,
          "Historical baseline report differs from the frozen diagnostic target")
    baseline = {"raw_sha256": hashlib.sha256(raw).hexdigest(),
                "artifact_sha256": report["artifact_sha256"],
                "quality_target_met": report["quality_target_met"]}
    del raw, report, index, raw_index
    return baseline


def _write_index(directory, index):
    unsigned = {key: value for key, value in index.items() if key != "index_sha256"}
    index["index_sha256"] = proof._digest(unsigned)
    raw = json.dumps(index, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    _need(len(raw) <= MAX_INDEX_BYTES, "Diagnostic index exceeds size bound")
    tmp = directory / "index.json.tmp"
    tmp.write_bytes(raw)
    tmp.replace(directory / "index.json")


def _persist_raw(directory, sample_id, raw):
    _need(type(raw) is bytes and len(raw) <= MAX_RAW_BYTES, "Diagnostic report exceeds raw bound")
    compressed = gzip.compress(raw, mtime=0)
    _need(len(compressed) <= MAX_GZIP_BYTES, "Diagnostic report exceeds gzip bound")
    name = f"{sample_id}.json.gz"
    with (directory / name).open("xb") as stream:
        stream.write(compressed)
    return {"path": name, "raw_bytes": len(raw), "gzip_bytes": len(compressed),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "gzip_sha256": hashlib.sha256(compressed).hexdigest()}


def run(output, *, execution_state=None):
    output = Path(output).resolve()
    root = ROOT.resolve()
    _need(not output.exists() and output != root and root not in output.parents and
          output not in root.parents, "Diagnostic output must be new and outside source")
    output.mkdir(parents=True, exist_ok=False)
    index = {"schema_version": 1, "protocol_id": "fixed-flop-prior-baseline-diagnostic-v1",
             "status": "preparing", "created_at_utc": _utc(), "finished_at_utc": None,
             "execution_state": evidence._execution_state(execution_state),
             "runtime": {"python": sys.version, "implementation": platform.python_implementation(),
                         "platform": platform.platform()},
             "protocol": None, "preflight": None, "source_before": None, "source_after": None,
             "baseline": None, "samples": [], "training_calls": 0, "errors": []}
    _write_index(output, index)
    source_before = None
    original_train = cfr_plus.train
    calls = {"count": 0}

    def counted_train(*args, **kwargs):
        calls["count"] += 1
        return original_train(*args, **kwargs)

    try:
        protocol_raw, spec = _protocol()
        requests, total = _preflight(spec)
        _runtime_gate(spec)
        source_before = _snapshot()
        _need(source_before["status"] == "", "Diagnostic source must be clean and committed")
        baseline = _authenticate_baseline()
        _need(_snapshot() == source_before, "Source changed during historical baseline authentication")
        index.update(protocol=spec, protocol_sha256=hashlib.sha256(
            protocol_raw.replace(b"\r\n", b"\n")).hexdigest(),
            preflight={**spec["preflight"], "requests": requests},
            source_before=source_before, baseline=baseline, status="active")
        del protocol_raw, requests
        _write_index(output, index)
        index["samples"] = [{"sample_id": row["sample_id"], "status": "not-run",
                             "phase_instrumentation": row["phase_instrumentation"],
                             "allocation_trace": row["allocation_trace"], "events": [],
                             "error": None} for row in spec["samples"]]
        with patch.object(cfr_plus, "train", counted_train):
            for spec_row in spec["samples"]:
                sample = next(row for row in index["samples"]
                              if row["sample_id"] == spec_row["sample_id"])
                sample.update(status="active", source_before=_snapshot())
                index["active_sample"] = sample["sample_id"]
                _need(sample["source_before"] == source_before,
                      "Source changed before diagnostic sample")
                before_calls = calls["count"]
                _write_index(output, index)
                restore = None
                raw = None
                try:
                    gc.collect()
                    call = lambda: adapter.solve_reweighted("baseline", 560)
                    if sample["phase_instrumentation"]:
                        restore = profiler._instrument(_targets(), sample["events"])
                    raw, metadata = measurement.measure_call(
                        call, allocation=sample["allocation_trace"])
                    sample["evidence_file"] = _persist_raw(output, sample["sample_id"], raw)
                    sample["training_calls"] = calls["count"] - before_calls
                    _need(sample["training_calls"] == 1,
                          "Each diagnostic sample must invoke shared CFR+ exactly once")
                    sample["measurement"] = metadata
                    _need(type(metadata.get("allocation_trace")) is bool and
                          metadata["allocation_trace"] is sample["allocation_trace"] and
                          (metadata.get("python_traced_peak_bytes") is None
                           if not sample["allocation_trace"] else
                           type(metadata.get("python_traced_peak_bytes")) is int and
                           metadata["python_traced_peak_bytes"] > 0),
                          "Measurement allocation metadata differs from the sample")
                    if sample["phase_instrumentation"]:
                        _need(0 < len(sample["events"]) <= spec["event_limit"] and
                              all(row.get("status") == "complete"
                                  for row in sample["events"]),
                              "Phase event inventory is empty, incomplete, errored, or oversized")
                    else:
                        _need(sample["events"] == [],
                              "Allocation sample unexpectedly contains phase events")
                    sample["report_matches_pilot"] = (
                        hashlib.sha256(raw).hexdigest() == baseline["raw_sha256"] and
                        metadata.get("raw_sha256") == baseline["raw_sha256"] and
                        metadata.get("artifact_sha256") == baseline["artifact_sha256"] and
                        metadata.get("quality_target_met") is True)
                    _need(sample["report_matches_pilot"],
                          "Diagnostic report differs from the authenticated baseline pilot")
                    sample["status"] = "complete"
                except BaseException as exc:
                    sample["status"] = "error"
                    sample["error"] = {"message": f"{type(exc).__name__}: {exc}",
                                        "traceback": traceback.format_exc()}
                    index["errors"].append({"sample_id": sample["sample_id"], **sample["error"]})
                    raise
                finally:
                    if restore is not None:
                        try:
                            restore()
                        except BaseException as exc:
                            index["errors"].append({"sample_id": sample["sample_id"],
                                "phase": "restore-instrumentation",
                                "message": f"{type(exc).__name__}: {exc}",
                                "traceback": traceback.format_exc()})
                            sample["status"] = "error"
                    try:
                        sample["source_after"] = _snapshot()
                        source_mismatch = sample["source_after"] != source_before
                    except BaseException as exc:
                        sample["source_after"] = None
                        source_mismatch = True
                        index["errors"].append({"sample_id": sample["sample_id"],
                            "phase": "source-check",
                            "message": f"{type(exc).__name__}: {exc}",
                            "traceback": traceback.format_exc()})
                    if source_mismatch:
                        index["errors"].append({"sample_id": sample["sample_id"],
                                                  "phase": "source-check",
                                                  "message": "Source changed during sample"})
                        sample["status"] = "error"
                    sample["training_calls"] = calls["count"] - before_calls
                    index["training_calls"] = calls["count"]
                    index.pop("active_sample", None)
                    raw = None
                    gc.collect()
                    _write_index(output, index)
                _need(sample["status"] == "complete", "Diagnostic sample failed")
    except BaseException as exc:
        if not index["errors"]:
            index["errors"].append({"phase": "run", "message": f"{type(exc).__name__}: {exc}",
                                    "traceback": traceback.format_exc()})
        for sample in index["samples"]:
            if sample["status"] == "active":
                sample["status"] = "error"
            elif sample["status"] == "not-run":
                sample["not_run_reason"] = "stopped-after-earlier-failure"
    finally:
        cfr_plus.train = original_train
        try:
            index["source_after"] = _snapshot()
            if source_before is not None and index["source_after"] != source_before:
                index["errors"].append({"phase": "final-source-check",
                                         "message": "Source changed during diagnostic"})
        except BaseException as exc:
            index["errors"].append({"phase": "final-source-check",
                "message": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()})
        index["training_calls"] = calls["count"]
        index["finished_at_utc"] = _utc()
        index["status"] = ("complete" if len(index["samples"]) == 2 and
                            all(row["status"] == "complete" for row in index["samples"])
                            and all(row.get("training_calls") == 1 for row in index["samples"])
                            and calls["count"] == 2 and not index["errors"] else "error")
        _write_index(output, index)
    return index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    context = (power.measurement_execution_state() if sys.platform == "win32" else
               nullcontext({"mode": "ordinary-process", "system_required": False}))
    with context as state:
        result = run(args.output, execution_state=state)
    print(json.dumps({"status": result["status"], "training_calls": result["training_calls"],
                      "samples": len(result["samples"]), "index_sha256": result["index_sha256"]},
                     sort_keys=True))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
