"""One instrumented 560-sweep compact fixed-flop call; profiling only."""
from datetime import datetime, timezone
import argparse
import gc
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

from scripts import benchmark_flop_class_cost as runner
from scripts import benchmark_weighted_full_deck_flop as power
from scripts import flop_class_call_measurement as measurement
from scripts import flop_class_compact_cfrplus as compact
from scripts import flop_class_policy as policy
from scripts import flop_public_classes as proof
from pokerlab import cfr_plus


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/flop-class-phase-profile-v1.json"
PROTOCOL_SHA256 = "3d7209efb1c3cd0c8e0efd70695a2b692ed45eb4c949296e21ee27d6476db0e1"
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_RAW_BYTES = 24 * 1024 * 1024
MAX_GZIP_BYTES = 8 * 1024 * 1024
MAX_EVENTS = 1000


def _protocol():
    if SPEC.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Phase profile protocol exceeds bound")
    raw = SPEC.read_bytes()
    if len(raw) > MAX_FILE_BYTES or hashlib.sha256(
            raw.replace(b"\r\n", b"\n")).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("Phase profile protocol bytes changed")
    spec = json.loads(raw)
    phases = [item[0] for item in _targets()]
    if (type(spec) is not dict or spec.get("protocol_id") !=
            "fixed-flop-class-phase-profile-v1" or
            spec.get("request") != {
                "method": "class-560",
                "entry": "scripts.flop_class_compact_cfrplus.solve_fixed_compact",
                "iterations": 560, "calls": 1} or
            spec.get("instrumented_boundaries") != phases or
            spec.get("event_limit") != MAX_EVENTS or
            type(spec.get("instrumentation_overhead")) is not str):
        raise ValueError("Phase profile protocol dimensions differ")
    return spec


def _snapshot():
    snapshot = runner._source_snapshot()
    name = "scripts/profile_flop_class_phases.py"
    for path, key in ((Path(__file__), name), (SPEC, "benchmarks/flop-class-phase-profile-v1.json")):
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("Phase profile source exceeds bound")
        raw = path.read_bytes()
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError("Phase profile source exceeds bound")
        snapshot["source_lf_sha256"][key] = hashlib.sha256(
            raw.replace(b"\r\n", b"\n")).hexdigest()
    return snapshot


def _targets():
    return (("compact.publication.verify", compact.publication, "verify"),
            ("proof.build_model", proof, "build_model"),
            ("base._training_inputs", compact.base, "_training_inputs"),
            ("cfr_plus.train", cfr_plus, "train"),
            ("policy.canonicalize_binary_rows", policy, "canonicalize_binary_rows"),
            ("proof.lift_policy", proof, "lift_policy"),
            ("proof.audit_policy", proof, "audit_policy"))


def _instrument(targets, events):
    originals = []
    stack = []
    next_id = 0
    try:
        for name, owner, attribute in targets:
            original = getattr(owner, attribute)
            originals.append((owner, attribute, original))

            def wrapped(*args, __name=name, __original=original, **kwargs):
                nonlocal next_id
                if len(events) >= MAX_EVENTS:
                    raise RuntimeError("Phase profile event limit exceeded")
                next_id += 1
                event_id = next_id
                row = {"event_id": event_id, "parent_event_id": stack[-1] if stack else None,
                       "phase": __name, "started_at_utc": datetime.now(timezone.utc).isoformat(),
                       "wall_start": time.perf_counter(), "cpu_start": time.process_time(),
                       "status": "running"}
                events.append(row)
                stack.append(event_id)
                try:
                    return __original(*args, **kwargs)
                except BaseException as exc:
                    row["status"] = "error"
                    row["error"] = f"{type(exc).__name__}: {exc}"
                    raise
                finally:
                    row["process_seconds"] = time.process_time() - row.pop("cpu_start")
                    row["wall_seconds"] = time.perf_counter() - row.pop("wall_start")
                    row["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
                    if row["status"] == "running":
                        row["status"] = "complete"
                    stack.pop()
            setattr(owner, attribute, wrapped)
    except BaseException:
        for owner, attribute, original in reversed(originals):
            setattr(owner, attribute, original)
        raise

    def restore():
        for owner, attribute, original in reversed(originals):
            setattr(owner, attribute, original)
    return restore


def _write_index(directory, report):
    report["index_sha256"] = proof._digest(
        {key: value for key, value in report.items() if key != "index_sha256"})
    raw = json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Phase profile index exceeds bound")
    temp = directory / "index.json.tmp"
    temp.write_bytes(raw)
    temp.replace(directory / "index.json")


def run(output, *, execution_state=None):
    output, root = Path(output).resolve(), ROOT.resolve()
    if output.exists() or output == root or root in output.parents or output in root.parents:
        raise ValueError("Phase profile output must be new and outside the checkout")
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": 1, "protocol_id": "fixed-flop-class-phase-profile-v1",
              "execution_state": execution_state or {"mode": "direct-call",
                                                       "system_required": False},
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "events": [], "errors": [], "status": "preparing", "request": {"method": "class-560",
                                                                   "iterations": 560}}
    _write_index(output, report)
    raw = compressed = None
    restore = None
    before = None

    def retain_error(phase, exc, detail=None):
        entry = {"phase": phase,
                 "error": f"{type(exc).__name__}: {exc}" if exc is not None else detail}
        if exc is not None:
            entry["traceback"] = traceback.format_exc()
        report["errors"].append(entry)
        report["status"] = "error"
        report.setdefault("error", entry["error"])
        if "traceback" in entry:
            report.setdefault("traceback", entry["traceback"])

    try:
        spec = _protocol()
        admission = compact.budget.admit_compact_request(560)
        if admission.get("requested_iterations") != 560:
            raise ValueError("Compact full-request admission differs")
        before = _snapshot()
        expected = runner._pilot_expectations()
        report.update(protocol=spec, admission=admission, source_before=before,
                      instrumentation_overhead=spec["instrumentation_overhead"])
        report["active_request"] = dict(report["request"])
        report["status"] = "active"
        _write_index(output, report)
        if _snapshot() != before:
            raise ValueError("Source snapshot changed before profiled call")
        restore = _instrument(_targets(), report["events"])
        gc.collect()
        raw, metadata = measurement.measure_call(lambda: compact.solve_fixed_compact(560))
    except BaseException as exc:
        retain_error("call", exc)
    finally:
        if restore is not None:
            try:
                restore()
            except BaseException as exc:
                retain_error("restore-instrumentation", exc)
    try:
        if raw is not None:
            if len(raw) > MAX_RAW_BYTES:
                raise ValueError("Profiled raw report exceeds bound")
            compressed = gzip.compress(raw, mtime=0)
            if len(compressed) > MAX_GZIP_BYTES:
                raise ValueError("Profiled gzip report exceeds bound")
            path = output / "class-560-profiled.json.gz"
            with path.open("xb") as stream:
                stream.write(compressed)
            report.update(raw_file=path.name, raw_sha256=hashlib.sha256(raw).hexdigest(),
                          gzip_sha256=hashlib.sha256(compressed).hexdigest(),
                          measurement=metadata)
            runner._validate_raw(raw, "class-560", expected)
            if not report["errors"]:
                report["status"] = "complete"
    except BaseException as exc:
        retain_error("persist-or-validate-result", exc)
    finally:
        try:
            report["source_after"] = _snapshot()
            if before is not None and report["source_after"] != before:
                retain_error("final-source-check", None,
                             "Source snapshot changed during profiled call")
        except BaseException as exc:
            report["source_after"] = None
            retain_error("final-source-check", exc)
    report.pop("active_request", None)
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    _write_index(output, report)
    raw = compressed = None
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    from contextlib import nullcontext
    context = (power.measurement_execution_state() if sys.platform == "win32" else
               nullcontext({"mode": "ordinary-process", "system_required": False}))
    with context as state:
        report = run(args.output, execution_state=state)
    print(json.dumps({"status": report["status"], "events": len(report["events"]),
                      "index_sha256": report["index_sha256"]}, sort_keys=True))
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
