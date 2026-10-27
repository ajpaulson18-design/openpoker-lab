"""Fixed paired complete-call study of Python vs native selected operator.

The protocol is three untraced T100 calls plus one separate traced T100 call
per backend, then one untraced T1000 call per backend. Backend order alternates
and there are no retries. Source and native build identity are checked before
and after the full batch. Results remain specific to the frozen selected game.
"""
import argparse
import hashlib
import json
from math import isfinite
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc

from pokerlab.native_selected_operator import executable_identity
from pokerlab.selected_operator_solver import solve_four_street_operator
from scripts.benchmark_selected_operator import (
    ROOT, _identity, _request, _rss, _write, verify_saved,
)


RANK_CACHE_BOARDS = 64
STRATEGY_STORAGE = "packed"
BACKENDS = ("python", "native")


def child(backend, iterations, traced, native_executable=None):
    if backend not in BACKENDS:
        raise ValueError("backend must be python or native")
    if type(iterations) is not int or iterations not in (100, 1000):
        raise ValueError("iterations must be 100 or 1000")
    if backend == "native" and not native_executable:
        raise ValueError("native backend requires an explicit executable")
    case = json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text(
        encoding="utf-8"))["case"]
    request = _request(case, iterations)
    if traced:
        tracemalloc.start()
    before = time.perf_counter()
    if backend == "native":
        payload = solve_four_street_operator(
            request, strategy_storage=STRATEGY_STORAGE,
            rank_cache_boards=RANK_CACHE_BOARDS,
            native_executable=str(Path(native_executable).resolve(strict=True)))
    else:
        payload = solve_four_street_operator(
            request, strategy_storage=STRATEGY_STORAGE,
            rank_cache_boards=RANK_CACHE_BOARDS)
    elapsed = time.perf_counter() - before
    python_peak = tracemalloc.get_traced_memory()[1] if traced else None
    if traced:
        tracemalloc.stop()
    return {
        "backend": backend, "iterations": iterations,
        "strategy_storage": STRATEGY_STORAGE,
        "rank_cache_boards": RANK_CACHE_BOARDS,
        "traced": bool(traced), "seconds": elapsed,
        "python_tracemalloc_peak_bytes": python_peak,
        "python_process_lifetime_peak_working_set_bytes": _rss(),
        "native_process_lifetime_peak_working_set_bytes": (
            payload.get("native_training", {}).get(
                "native_process_lifetime_peak_working_set_bytes")
            if backend == "native" else None),
        "payload": payload,
    }


def _native_identity(executable):
    return executable_identity(executable)


def _safe_identity_snapshot(executable):
    source = None
    native = None
    errors = []
    try:
        source = _identity()
    except Exception as exc:
        errors.append({"identity": "source", "error_type": type(exc).__name__,
                       "error": str(exc)})
    try:
        native = _native_identity(executable)
    except Exception as exc:
        errors.append({"identity": "native", "error_type": type(exc).__name__,
                       "error": str(exc)})
    return source, native, errors


def _child_error(exc):
    def decode(value):
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        return str(value)

    return {"error_type": type(exc).__name__, "error": str(exc),
            "child_stdout": decode(getattr(exc, "stdout", None)),
            "child_stderr": decode(getattr(exc, "stderr", None))}


def _strategy_equal(left, right):
    return left.get("strategy") == right.get("strategy")


def _audit_metrics_equal(audit):
    rows = audit.get("audits", ())
    return (len(rows) == 2 and all(type(row) is dict and
            type(row.get("exact_metrics")) is dict and row["exact_metrics"]
            and type(row.get("exact_target_met")) is bool
            for row in rows) and
            rows[0]["exact_metrics"] == rows[1]["exact_metrics"])


def _numeric_replay_pass(audit):
    rows = audit.get("audits", ())
    if len(rows) != 2:
        return False
    expected_fields = {"value_sb", "value_bb", "sb_best_response_value",
                       "bb_best_response_value", "nash_conv"}
    for row in rows:
        if type(row) is not dict or type(row.get("numeric_differences")) is not dict:
            return False
        gaps = row["numeric_differences"]
        if set(gaps) != expected_fields or any(type(value) not in (int, float) or not isfinite(value) or
                           value < 0 or value > 1e-10 for value in gaps.values()):
            return False
    return True


def _paired_strategy_results(payloads, iterations):
    if iterations == 100:
        pairs = [(sample, False) for sample in range(3)] + [("traced", True)]
    else:
        pairs = [(0, False)]
    return all(_strategy_equal(payloads[(iterations, "python", sample, traced)],
                               payloads[(iterations, "native", sample, traced)])
               for sample, traced in pairs)


def _schedule():
    schedule = []
    for sample in range(3):
        order = BACKENDS if sample % 2 == 0 else tuple(reversed(BACKENDS))
        schedule.extend((100, backend, sample, False) for backend in order)
    # Keep allocation tracing in a separate call after untraced T100 calls.
    schedule.extend((100, backend, "traced", True) for backend in reversed(BACKENDS))
    schedule.extend((1000, backend, 0, False) for backend in BACKENDS)
    return tuple(schedule)


def _sample_name(iterations, backend, sample, traced):
    label = "traced" if traced else str(sample)
    return f"t{iterations}-{backend}-{label}.json"


def run(output, native_executable):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Use a fresh output directory outside the source checkout.")
    if output.exists():
        raise FileExistsError("Benchmark output directory must be new.")
    if not native_executable:
        raise ValueError("An explicit native executable path is required.")
    native_executable = Path(native_executable).resolve(strict=True)
    source_before = _identity()
    if source_before["status"]:
        raise ValueError("Commit and clean the source before the fixed study.")
    binary_before = _native_identity(native_executable)
    output.mkdir(parents=True)
    protocol = {
        "version": "native-selected-operator-complete-call-v1",
        "source_commit": source_before["commit"],
        "case": "four-street-weighted-shared-future-v1",
        "iterations": {"t100": 100, "t1000": 1000},
        "schedule": [
            {"iterations": t, "backend": b, "sample": s, "traced": tr}
            for t, b, s, tr in _schedule()],
        "strategy_storage": STRATEGY_STORAGE,
        "rank_cache_boards": RANK_CACHE_BOARDS,
        "retry_policy": "none; retain first errors and every completed raw result",
        "acceptance": ["complete strategy rows identical per iteration",
                       "independent numeric and exact audits for sample zero",
                       "exact audit metrics identical across backends"],
        "memory_scope": "Python tracemalloc, Python process peak working set, and native child process peak working set are separate observations; never sum peaks.",
        "scope": "One bounded globally conditioned selected game; no full-deck, general speed, or RSS guarantee.",
    }
    _write(output / "protocol.json", protocol)
    _write(output / "source.json", source_before)
    _write(output / "native-identity-before.json", binary_before)
    samples = []
    failures = []
    payloads = {}
    for iterations, backend, sample, traced in _schedule():
        name = _sample_name(iterations, backend, sample, traced)
        command = [sys.executable, "-B", "-m", "scripts.benchmark_native_selected_operator",
                   "--child", backend, "--iterations", str(iterations)]
        if traced:
            command.append("--traced")
        if backend == "native":
            command.extend(("--native-executable", str(native_executable)))
        started = time.time_ns()
        timer = time.perf_counter()
        try:
            proc = subprocess.run(command, cwd=ROOT, capture_output=True,
                                  text=True, check=True)
            raw_bytes = proc.stdout.encode("utf-8")
            with (output / name).open("xb") as stream:
                stream.write(raw_bytes)
            raw = json.loads(proc.stdout)
            payload = raw["payload"]
            payloads[(iterations, backend, sample, traced)] = payload
            row = {key: value for key, value in raw.items() if key != "payload"}
            row.update({"sample": sample, "artifact": name,
                        "started_at_unix_ns": started,
                        "child_elapsed_wall_seconds": time.perf_counter() - timer,
                        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                        "complete_strategy_rows": len(payload.get("strategy", ())),
                        "operator_statistics_python_scope": payload.get("operator_statistics"),
                        "native_training_counters": payload.get("native_training")})
            samples.append(row)
            print(f"T{iterations} {backend} sample={sample} traced={traced} "
                  f"seconds={raw['seconds']:.6f}", flush=True)
        except Exception as exc:
            failure = {"artifact": name, "backend": backend,
                       "iterations": iterations, "sample": sample,
                       "traced": traced, **_child_error(exc)}
            failures.append(failure)
            _write(output / (name[:-5] + "-failure.json"), failure)
            source_failed, native_failed, identity_errors = _safe_identity_snapshot(native_executable)
            _write(output / "partial-report.json", {
                "outcome": "failed-first-sample", "protocol": protocol,
                "samples": samples, "failures": failures,
                "source_before": source_before,
                "source_after": source_failed,
                "native_identity_before": binary_before,
                "native_identity_after": native_failed,
                "identity_errors": identity_errors,
            })
            return {"outcome": "failed-first-sample", "failures": failures}

    # Freeze both identities immediately after the complete batch, before audits.
    source_after, binary_after, identity_errors = _safe_identity_snapshot(native_executable)
    _write(output / "source-after.json", source_after)
    _write(output / "native-identity-after.json", binary_after)
    if identity_errors:
        failures.extend({"stage": "post-batch-identity", **error} for error in identity_errors)
    if source_after != source_before:
        failures.append({"stage": "source-after", "error": "Source identity changed during batch."})
    if binary_after != binary_before:
        failures.append({"stage": "native-identity-after",
                         "error": "Native source/build identity changed during batch."})
    if failures:
        _write(output / "partial-report.json", {
            "outcome": "source-or-binary-changed-before-audit", "protocol": protocol,
            "samples": samples, "failures": failures,
            "source_before": source_before, "source_after": source_after,
            "native_identity_before": binary_before,
            "native_identity_after": binary_after,
            "identity_errors": identity_errors,
        })
        return {"outcome": "source-or-binary-changed-before-audit", "failures": failures}

    audits = {}
    manifest_hashes = {}
    for iterations in (100, 1000):
        directory = output / f"audit-t{iterations}"
        directory.mkdir()
        _write(directory / "source.json", source_before)
        _write(directory / "protocol.json", protocol | {"audit_iterations": iterations})
        _write(directory / "native-identity-before.json", binary_before)
        selected_samples = [row["artifact"] for row in samples
                            if row["iterations"] == iterations]
        for sample_name in selected_samples:
            (directory / sample_name).write_bytes((output / sample_name).read_bytes())
        aliases = []
        for backend, alias in (("python", "reference-0.json"),
                               ("native", "operator-0.json")):
            source_name = _sample_name(iterations, backend, 0, False)
            (directory / alias).write_bytes((output / source_name).read_bytes())
            aliases.append(alias)
        audited = ["source.json", "protocol.json", "native-identity-before.json",
                   *selected_samples, *aliases]
        _write(directory / "manifest.json", {"sha256": {
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in audited}})
        digest = hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest()
        manifest_hashes[str(iterations)] = digest
        try:
            audits[str(iterations)] = verify_saved(directory, digest)
        except Exception as exc:
            failure = {"stage": f"saved-audit-t{iterations}",
                       "error_type": type(exc).__name__, "error": str(exc)}
            _write(output / "partial-report.json", {
                "outcome": "audit-failed", "protocol": protocol,
                "samples": samples, "completed_audits": audits,
                "failed_audit": failure,
                "source_before": source_before, "source_after": source_after,
                "native_identity_before": binary_before,
                "native_identity_after": binary_after,
                "manifest_sha256": manifest_hashes,
            })
            return {"outcome": "audit-failed", "completed_audits": audits,
                    "failure": failure}
    quality = {"t100": {"complete_strategy_rows_identical": _paired_strategy_results(payloads, 100),
                         "sample_zero_numeric_replay_passed": _numeric_replay_pass(audits["100"]),
                         "sample_zero_exact_metrics_identical": _audit_metrics_equal(audits["100"])},
               "t1000": {"sample_zero_numeric_replay_passed": _numeric_replay_pass(audits["1000"]),
                         "sample_zero_exact_metrics_identical": _audit_metrics_equal(audits["1000"]),
                         "sample_zero_exact_targets_met": (
                             len(audits["1000"].get("audits", ())) == 2 and
                             all(type(row) is dict and row.get("exact_target_met") is True
                                 for row in audits["1000"].get("audits", ()))),
                         "complete_strategy_rows_identical": _paired_strategy_results(payloads, 1000)}}
    quality_pass = all(
        row["complete_strategy_rows_identical"] and
        row["sample_zero_numeric_replay_passed"] and
        row["sample_zero_exact_metrics_identical"] and
        (row.get("sample_zero_exact_targets_met", True))
        for row in quality.values())

    medians = {}
    for iterations in (100, 1000):
        medians[str(iterations)] = {}
        for backend in BACKENDS:
            times = [row["seconds"] for row in samples
                     if row["iterations"] == iterations and row["backend"] == backend
                     and not row["traced"]]
            medians[str(iterations)][backend] = statistics.median(times)
    report = {
        "outcome": ("source-or-binary-changed" if failures else
                    "complete" if quality_pass else "quality-miss"),
        "protocol": protocol, "source_before": source_before,
        "source_after": source_after,
        "native_identity_before": binary_before,
        "native_identity_after": binary_after,
        "samples": samples, "medians_seconds": medians,
        "native_over_python_median_ratio": {
            key: values["native"] / values["python"]
            for key, values in medians.items()},
        "saved_independent_audit": audits, "quality": quality,
        "externally_pinnable_manifest_sha256": manifest_hashes,
        "failures": failures,
        "platform": platform.platform(), "python": sys.version,
        "scope": protocol["scope"],
    }
    _write(output / "report.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--native-executable", type=Path,
                        default=os.environ.get("OPENPOKER_NATIVE_SELECTED_EXE"))
    parser.add_argument("--child", choices=BACKENDS)
    parser.add_argument("--iterations", type=int, choices=(100, 1000))
    parser.add_argument("--traced", action="store_true")
    args = parser.parse_args(argv)
    if args.child:
        if args.iterations is None:
            parser.error("--iterations is required with --child")
        if args.child == "native" and args.native_executable is None:
            parser.error("--native-executable or OPENPOKER_NATIVE_SELECTED_EXE is required")
        print(json.dumps(child(args.child, args.iterations, args.traced,
                               args.native_executable), allow_nan=False))
        return 0
    if args.output is None:
        parser.error("--output is required for a full fixed study")
    if args.native_executable is None:
        parser.error("--native-executable or OPENPOKER_NATIVE_SELECTED_EXE is required")
    report = run(args.output, args.native_executable)
    print(json.dumps({"outcome": report["outcome"],
                      "report": str(args.output.resolve() / "report.json"),
                      "manifest_sha256": report.get("externally_pinnable_manifest_sha256")},
                     sort_keys=True))
    return 0 if report["outcome"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
