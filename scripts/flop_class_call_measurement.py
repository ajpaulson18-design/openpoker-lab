"""Measure one complete fixed-flop library call without importing its solver."""
from datetime import datetime, timezone
import gc
import hashlib
import json
import platform
import sys
from time import perf_counter, process_time
import tracemalloc


def measure_call(call, *, allocation=False):
    """Call once, then canonicalize/hash inside the same timing boundary.

    If ``allocation`` is true, this is a separate traced call: GC runs before
    tracing, and solve, serialization, and hashing are inside the trace window.
    The returned peak is Python ``tracemalloc`` data, never RSS. Exceptions
    propagate after tracing is stopped so callers can preserve failure details.
    """
    if not callable(call):
        raise TypeError("call must be callable")
    if type(allocation) is not bool:
        raise TypeError("allocation must be a bool")

    if allocation and tracemalloc.is_tracing():
        raise ValueError("Allocation measurement requires a separate inactive trace.")
    if allocation:
        gc.collect()
    tracing_started = False
    try:
        if allocation:
            tracemalloc.start()
            tracing_started = True
        started_at = datetime.now(timezone.utc).isoformat()
        wall_start = perf_counter()
        cpu_start = process_time()
        report = call()
        if type(report) is not dict:
            raise TypeError("measured library call must return a report dictionary")
        encoded = json.dumps(report, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8") + b"\n"
        raw_sha256 = hashlib.sha256(encoded).hexdigest()
        peak = tracemalloc.get_traced_memory()[1] if allocation else None
        cpu_seconds = process_time() - cpu_start
        wall_seconds = perf_counter() - wall_start
        finished_at = datetime.now(timezone.utc).isoformat()
    finally:
        if tracing_started:
            tracemalloc.stop()

    metadata = {
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
        "wall_seconds": wall_seconds,
        "process_seconds": cpu_seconds,
        "raw_sha256": raw_sha256,
        "artifact_sha256": report.get("artifact_sha256"),
        "quality_target_met": report.get("quality_target_met"),
        "allocation_trace": allocation,
        "python_traced_peak_bytes": peak,
        "runtime": {
            "python": sys.version,
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
    }
    return encoded, metadata
