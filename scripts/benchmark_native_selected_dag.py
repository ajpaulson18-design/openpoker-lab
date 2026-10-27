"""Paired complete-call study of Python and native direct shared public topology.

The fixed schedule is three alternating untraced T100 pairs, one separate
traced T100 pair, then one untraced T1000 pair. Each call uses the same
22-world request, packed CFR+ storage and rank-cache capacity. The native half
explicitly selects the separately authenticated DAG helper. Results are specific
to this finite game.
"""

import argparse
import hashlib
import json
import os
from math import isfinite
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

from pokerlab.selected_operator_solver import solve_four_street_operator
from pokerlab.native_selected_dag import executable_identity
from scripts.benchmark_selected_operator import (
    ROOT, _identity, _request, _rss, _write, verify_saved,
)


BACKENDS = ("python", "native")
STRATEGY_STORAGE = "packed"
RANK_CACHE_BOARDS = 64
DIAGNOSTIC_FIELDS = (
    "value_sb", "value_bb", "sb_best_response_value",
    "bb_best_response_value", "nash_conv", "sb_gain", "bb_gain",
    "exploitability", "public_batched_training_pot_anchor",
)
NUMERIC_AUDIT_FIELDS = frozenset((
    "value_sb", "value_bb", "sb_best_response_value",
    "bb_best_response_value", "nash_conv",
))
EXACT_METRIC_FIELDS = frozenset((
    "value_sb", "value_bb", "sb_best_response_value",
    "bb_best_response_value", "sb_best_response_gain", "bb_best_response_gain",
    "nash_conv", "exploitability", "lower_value_bound", "upper_value_bound",
))


def child(backend, iterations, traced):
    """Run one complete child call with explicit topology selection."""
    if backend not in BACKENDS:
        raise ValueError("backend must be python or native")
    if type(iterations) is not int or iterations not in (100, 1000):
        raise ValueError("iterations must be 100 or 1000")
    case = json.loads((ROOT / "benchmarks/four-street-integration-v1.json").read_text(
        encoding="utf-8"))["case"]
    request = _request(case, iterations)
    executable = os.environ.get("OPENPOKER_NATIVE_SELECTED_DAG_EXE") if backend == "native" else None
    if backend == "native" and not executable:
        raise ValueError("Set OPENPOKER_NATIVE_SELECTED_DAG_EXE explicitly")
    if traced:
        tracemalloc.start()
    started = time.perf_counter()
    try:
        payload = solve_four_street_operator(
            request, strategy_storage=STRATEGY_STORAGE,
            rank_cache_boards=RANK_CACHE_BOARDS,
            public_topology="direct", native_executable=executable)
        seconds = time.perf_counter() - started
        allocation_peak = tracemalloc.get_traced_memory()[1] if traced else None
    finally:
        if traced and tracemalloc.is_tracing():
            tracemalloc.stop()
    return {
        "backend": backend, "iterations": iterations,
        "strategy_storage": STRATEGY_STORAGE,
        "rank_cache_boards": RANK_CACHE_BOARDS,
        "public_topology": "direct", "traced": bool(traced),
        "seconds": seconds,
        "python_tracemalloc_peak_bytes": allocation_peak,
        "python_process_lifetime_peak_working_set_bytes": _rss(),
        "native_calls": int(backend == "native"),
        "native_process_lifetime_peak_working_set_bytes": (payload.get("native_training") or {}).get("native_process_lifetime_peak_working_set_bytes"),
        "payload": payload,
    }


def _schedule():
    schedule = []
    for sample in range(3):
        order = BACKENDS if sample % 2 == 0 else tuple(reversed(BACKENDS))
        schedule.extend((100, backend, sample, False) for backend in order)
    schedule.extend((100, backend, "traced", True) for backend in BACKENDS)
    schedule.extend((1000, backend, 0, False) for backend in BACKENDS)
    return tuple(schedule)


def _sample_name(iterations, backend, sample, traced):
    label = "traced" if traced else str(sample)
    return f"t{iterations}-{backend}-{label}.json"


def _script_sha256():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _decode(raw):
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return str(raw)


def _paired_samples(iterations):
    if iterations == 100:
        return ((sample, False) for sample in range(3))
    return iter(((0, False),))


def _complete_strategy(payload):
    if type(payload) is not dict or type(payload.get("strategy")) is not list:
        return False
    census = payload.get("operator_census")
    if type(census) is not dict:
        return False
    expected = payload.get("info_sets")
    return (type(expected) is int and expected >= 0 and
            census.get("information_sets") == expected and
            len(payload["strategy"]) == expected)


def _diagnostics(payload):
    result = {}
    for field in DIAGNOSTIC_FIELDS:
        value = payload.get(field)
        if type(value) not in (int, float) or not isfinite(value):
            return None
        result[field] = value
    return result


def _game_checks(payload):
    fields = ("candidate_private_pairs", "compatible_private_pairs", "worlds",
              "pair_runout_preflight_checks", "public_states", "decisions", "info_sets")
    if any(type(payload.get(name)) is not int or payload[name] < 0 for name in fields):
        return None
    census = payload.get("operator_census", {})
    structure = census.get("direct_public_topology")
    layout = census.get("shared_strategy_storage")
    if not isinstance(structure, dict) or not isinstance(layout, dict):
        return None
    return {"counts": {name: payload[name] for name in fields},
            "direct_structure": structure, "packed_layout": layout}


def _comparison(left, right):
    return {
        "complete_strategy_rows": (_complete_strategy(left) and
                                    _complete_strategy(right) and
                                    left["strategy"] == right["strategy"]),
        "diagnostics": (_diagnostics(left) is not None and
                        _diagnostics(left) == _diagnostics(right)),
        "private_pair_probabilities": (
            type(left.get("private_pair_probabilities")) is list and
            left.get("private_pair_probabilities") == right.get("private_pair_probabilities")),
        "game_census": (_game_checks(left) is not None and
                            _game_checks(left) == _game_checks(right)),
    }


def _paired_comparisons(payloads, iterations):
    rows = []
    for sample, traced in _paired_samples(iterations):
        python = payloads.get((iterations, "python", sample, traced))
        native = payloads.get((iterations, "native", sample, traced))
        checks = (_comparison(python, native) if python is not None and native is not None
                  else {name: False for name in (
                      "complete_strategy_rows", "diagnostics",
                      "private_pair_probabilities", "game_census")})
        rows.append({"sample": sample, "traced": traced, **checks})
    if iterations == 100:
        python = payloads.get((100, "python", "traced", True))
        native = payloads.get((100, "native", "traced", True))
        checks = (_comparison(python, native) if python is not None and native is not None
                  else {name: False for name in (
                      "complete_strategy_rows", "diagnostics",
                      "private_pair_probabilities", "game_census")})
        rows.append({"sample": "traced", "traced": True, **checks})
    return rows


def _audit_metrics_equal(audit):
    rows = audit.get("audits", ()) if type(audit) is dict else ()
    if len(rows) != 2:
        return False
    return all(type(row) is dict and type(row.get("exact_metrics")) is dict and
               set(row["exact_metrics"]) == EXACT_METRIC_FIELDS and
               all(type(value) is str and value for value in row["exact_metrics"].values()) and
               type(row.get("exact_target_met")) is bool for row in rows) and \
        rows[0]["exact_metrics"] == rows[1]["exact_metrics"]


def _numeric_replay_pass(audit):
    rows = audit.get("audits", ()) if type(audit) is dict else ()
    if len(rows) != 2:
        return False
    for row in rows:
        if type(row) is not dict or type(row.get("numeric_differences")) is not dict:
            return False
        gaps = row["numeric_differences"]
        if set(gaps) != NUMERIC_AUDIT_FIELDS or any(
                type(value) not in (int, float) or not isfinite(value) or
                value < 0 or value > 1e-10 for value in gaps.values()):
            return False
    return True


def _both_exact_targets_met(audit):
    rows = audit.get("audits", ()) if type(audit) is dict else ()
    return (len(rows) == 2 and all(type(row) is dict and
            row.get("exact_target_met") is True for row in rows))


def _audit_protocol(directory, protocol, source, samples, iterations):
    directory.mkdir()
    _write(directory / "source.json", source)
    _write(directory / "protocol.json", protocol | {"audit_iterations": iterations})
    selected = [row["artifact"] for row in samples if row["iterations"] == iterations]
    for name in selected:
        (directory / name).write_bytes((directory.parent / name).read_bytes())
    aliases = (("python", "reference-0.json"), ("native", "operator-0.json"))
    for backend, alias in aliases:
        source_name = _sample_name(iterations, backend, 0, False)
        (directory / alias).write_bytes((directory.parent / source_name).read_bytes())
    audited = ["source.json", "protocol.json", *selected,
               "reference-0.json", "operator-0.json"]
    _write(directory / "manifest.json", {"sha256": {
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in audited}})
    return hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest()


def _partial(output, outcome, protocol, samples, failures, source_before,
             source_after, completed_audits=None, failed_audit=None,
             manifests=None):
    payload = {
        "outcome": outcome, "protocol": protocol, "samples": samples,
        "failures": failures, "source_before": source_before,
        "source_after": source_after,
        "completed_audits": completed_audits or {},
        "manifest_sha256": manifests or {},
    }
    if failed_audit is not None:
        payload["failed_audit"] = failed_audit
    _write(output / "partial-report.json", payload)


def run(output):
    """Run the fixed paired batch and authenticate saved sample zero audits."""
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Use a fresh output directory outside the source checkout.")
    if output.exists():
        raise FileExistsError("Native DAG study output directory must be new.")
    source_before = _identity()
    if source_before["status"]:
        raise ValueError("Commit and clean the source before the fixed study.")
    executable = os.environ.get("OPENPOKER_NATIVE_SELECTED_DAG_EXE")
    if not executable:
        raise ValueError("Set OPENPOKER_NATIVE_SELECTED_DAG_EXE explicitly")
    native_before = executable_identity(executable)
    output.mkdir(parents=True)
    protocol = {
        "version": "native-selected-dag-complete-call-v1",
        "source_commit": source_before["commit"],
        "source_sha256": source_before["sha256"],
        "runner_sha256": _script_sha256(),
        "case": "four-street-weighted-shared-future-v1",
        "worlds": 22,
        "schedule": [
            {"iterations": t, "backend": b, "sample": s, "traced": traced}
            for t, b, s, traced in _schedule()],
        "strategy_storage": STRATEGY_STORAGE,
        "rank_cache_boards": RANK_CACHE_BOARDS,
        "topology_modes": {"python": "direct", "native": "direct"},
        "native_build_identity": native_before,
        "retry_policy": "none; retain first child or audit failure and all completed raw calls",
        "acceptance": [
            "four T100 paired samples including the traced pair and one T1000 pair have complete identical rows",
            "numeric diagnostics, pair probabilities and game censuses match for every pair",
            "saved independent numeric replay gaps have the exact five fields and are finite <= 1e-10",
            "T1000 exact certificate metrics match and both targets are <= 0.001 BB"],
        "memory_scope": "Python tracemalloc, Python process peak and native process lifetime peak are separate observations, never summed; no general memory claim.",
        "scope": "One conditioned 22-world game and explicit Python/native direct-topology packed CFR+ modes; no universal memory, speed or convergence claim.",
    }
    _write(output / "protocol.json", protocol)
    _write(output / "source-before.json", source_before)
    samples, failures, payloads = [], [], {}
    for iterations, backend, sample, traced in _schedule():
        name = _sample_name(iterations, backend, sample, traced)
        command = [sys.executable, "-B", "-m", "scripts.benchmark_native_selected_dag",
                   "--child", backend, "--iterations", str(iterations)]
        if traced:
            command.append("--traced")
        started = time.time_ns()
        timer = time.perf_counter()
        proc = None
        try:
            proc = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
            stdout = proc.stdout or b""
            stderr = proc.stderr or b""
            # Preserve both streams before checking exit status or parsing JSON.
            (output / name).write_bytes(stdout)
            (output / (name[:-5] + ".stderr.txt")).write_bytes(stderr)
            if proc.returncode != 0:
                raise RuntimeError(f"child exited with status {proc.returncode}")
            raw = json.loads(stdout)
            if (raw.get("backend") != backend or raw.get("iterations") != iterations or
                    raw.get("public_topology") != "direct" or raw.get("native_calls") != int(backend == "native")):
                raise ValueError("Child result identity/mode mismatch.")
            payload = raw["payload"]
            if backend == "native":
                if payload.get("native_training", {}).get("identity") != native_before or payload["native_training"].get("calls") != 1:
                    raise ValueError("Native DAG sample helper identity/call mismatch")
            elif payload.get("native_training") is not None:
                raise ValueError("Python sample unexpectedly called native training")
            payloads[(iterations, backend, sample, traced)] = payload
            row = {key: value for key, value in raw.items() if key != "payload"}
            row.update({"sample": sample, "artifact": name,
                        "started_at_unix_ns": started,
                        "child_elapsed_wall_seconds": time.perf_counter() - timer,
                        "raw_sha256": hashlib.sha256(stdout).hexdigest(),
                        "complete_strategy_rows": len(payload.get("strategy", ())),
                        "operator_statistics": payload.get("operator_statistics"),
                        "rank_cache": payload.get("rank_cache"),
                        "python_layout": (payload.get("operator_census", {}).get("strategy_storage")
                                           if backend == "python" else None),
                        "shared_layout": payload.get("operator_census", {}).get("shared_strategy_storage"),
                        "shared_topology": payload.get("operator_census", {}).get("shared_public_topology"),
                        "direct_construction": payload.get("operator_census", {}).get("direct_public_topology")})
            samples.append(row)
            print(f"T{iterations} {backend} sample={sample} traced={traced} "
                  f"seconds={raw['seconds']:.6f}", flush=True)
        except Exception as exc:
            failure = {
                "artifact": name, "backend": backend, "iterations": iterations,
                "sample": sample, "traced": traced,
                "error_type": type(exc).__name__, "error": str(exc),
                "child_returncode": None if proc is None else proc.returncode,
                "child_stdout": _decode(None if proc is None else proc.stdout),
                "child_stderr": _decode(None if proc is None else proc.stderr),
            }
            failures.append(failure)
            _write(output / (name[:-5] + "-failure.json"), failure)
            try:
                source_after = _identity()
            except Exception as identity_exc:
                source_after = None
                failures.append({"stage": "failure-source-identity",
                                 "error_type": type(identity_exc).__name__,
                                 "error": str(identity_exc)})
            _write(output / "source-after.json", source_after)
            _partial(output, "failed-first-sample", protocol, samples, failures,
                     source_before, source_after)
            return {"outcome": "failed-first-sample", "failures": failures}

    # Freeze the complete batch before any saved-policy replay or exact math.
    try:
        source_after = _identity()
    except Exception as exc:
        source_after = None
        failures.append({"stage": "post-batch-source-identity",
                         "error_type": type(exc).__name__, "error": str(exc)})
    _write(output / "source-after.json", source_after)
    if executable_identity(executable) != native_before:
        failures.append({"stage": "native-after", "error": "Helper identity changed during batch"})
    if source_after != source_before:
        failures.append({"stage": "source-after",
                         "error": "Source identity changed during the complete-call batch."})
    if failures:
        _partial(output, "source-changed-before-audit", protocol, samples, failures,
                 source_before, source_after)
        return {"outcome": "source-changed-before-audit", "failures": failures}

    audits, manifests = {}, {}
    for iterations in (100, 1000):
        directory = output / f"audit-t{iterations}"
        try:
            digest = _audit_protocol(directory, protocol, source_before,
                                     samples, iterations)
            manifests[str(iterations)] = digest
            audits[str(iterations)] = verify_saved(directory, digest)
        except Exception as exc:
            failed_audit = {"stage": f"saved-audit-t{iterations}",
                            "error_type": type(exc).__name__, "error": str(exc)}
            _partial(output, "audit-failed", protocol, samples, failures,
                     source_before, source_after, audits, failed_audit, manifests)
            return {"outcome": "audit-failed", "completed_audits": audits,
                    "failure": failed_audit}

    pair_rows = {str(t): _paired_comparisons(payloads, t) for t in (100, 1000)}
    quality = {}
    for iterations in (100, 1000):
        audit = audits[str(iterations)]
        rows = pair_rows[str(iterations)]
        quality[f"t{iterations}"] = {
            "all_paired_complete_strategy_rows_identical": all(
                row["complete_strategy_rows"] for row in rows),
            "all_paired_diagnostics_identical": all(row["diagnostics"] for row in rows),
            "all_paired_private_pair_probabilities_identical": all(
                row["private_pair_probabilities"] for row in rows),
            "all_paired_game_census_identical": all(row["game_census"] for row in rows),
            "sample_zero_numeric_replay_passed": _numeric_replay_pass(audit),
            "sample_zero_exact_metrics_identical": _audit_metrics_equal(audit),
        }
        if iterations == 1000:
            quality["t1000"]["sample_zero_exact_targets_met"] = _both_exact_targets_met(audit)

    quality_pass = all(
        all(value for name, value in result.items()
            if name != "sample_zero_exact_targets_met") and
        result.get("sample_zero_exact_targets_met", True)
        for result in quality.values())
    medians = {}
    for iterations in (100, 1000):
        medians[str(iterations)] = {}
        for backend in BACKENDS:
            medians[str(iterations)][backend] = statistics.median(
                row["seconds"] for row in samples
                if row["iterations"] == iterations and row["backend"] == backend
                and not row["traced"])
    report = {
        "outcome": "complete" if quality_pass else "quality-miss",
        "protocol": protocol, "source_before": source_before,
        "source_after": source_after, "samples": samples,
        "medians_seconds": medians, "paired_comparisons": pair_rows,
        "saved_independent_audit": audits, "quality": quality,
        "externally_pinnable_manifest_sha256": manifests,
        "failures": failures,
        "platform": platform.platform(), "python": sys.version,
        "training_calls": len(samples), "native_calls": sum(row["native_calls"] for row in samples),
        "scope": protocol["scope"],
    }
    _write(output / "report.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", choices=BACKENDS)
    parser.add_argument("--iterations", type=int, choices=(100, 1000))
    parser.add_argument("--traced", action="store_true")
    args = parser.parse_args(argv)
    if args.child:
        if args.iterations is None:
            parser.error("--iterations is required with --child")
        print(json.dumps(child(args.child, args.iterations, args.traced), allow_nan=False))
        return 0
    if args.output is None:
        parser.error("--output is required for the fixed study")
    report = run(args.output)
    print(json.dumps({"outcome": report["outcome"],
                      "report": str(args.output.resolve() / "report.json"),
                      "manifest_sha256": report.get("externally_pinnable_manifest_sha256")},
                     sort_keys=True))
    return 0 if report["outcome"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
