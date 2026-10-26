"""Compare complete Python and native public-CFR four-street calls.

This runner is a fresh experiment. It never reads, resumes, edits or publishes
the frozen four-street quality artifacts. Each completed raw result is written
before its independent numeric replay. Failures are retained and never retried.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import uuid

from pokerlab.four_street_solver import solve_four_street
from pokerlab.native_public_cfr import executable_identity
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions
from scripts.preflop_validation import compare_result, replay_policy


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks/native-four-street-v1.json"
SOURCE_EXTRA_FILES = (
    "pokerlab/native_public_cfr.py",
    "native/public_tree_train.cpp",
    "scripts/build_native_public.py",
    "scripts/benchmark_native_four_street.py",
    "scripts/preflop_validation.py",
    "benchmarks/native-four-street-v1.json",
)


def _write_json(path: Path, value: object) -> None:
    data = json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    _write_bytes(path, data)


def _write_bytes(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)


def _source_snapshot() -> dict:
    python_files = set()
    for directory in ("pokerlab", "scripts"):
        inventory = subprocess.run(
            ["git", "ls-files", "-z", "--", directory], cwd=ROOT,
            check=True, capture_output=True,
        ).stdout.split(b"\0")
        python_files.update(value.decode("utf-8") for value in inventory
                            if value.endswith(b".py"))
    python_files = sorted(python_files)
    source_files = tuple(dict.fromkeys((*python_files, *SOURCE_EXTRA_FILES)))
    files = {}
    for relative in source_files:
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(f"Benchmark source is missing: {relative}")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.splitlines()
    return {"head": head, "status_porcelain": status, "source_sha256": files}


def _validate_manifest(manifest: dict) -> dict:
    if type(manifest) is not dict or manifest.get("benchmark_id") != "native-four-street-v1":
        raise ValueError("Unexpected native four-street benchmark identity")
    comparison = manifest.get("comparison")
    expected_order = [["python", "native"], ["native", "python"],
                      ["python", "native"]]
    if (type(comparison) is not dict or comparison.get("algorithm") != "cfrplus" or
            type(comparison.get("iterations")) is not int or
            comparison["iterations"] != 1000 or
            type(comparison.get("repeats")) is not int or comparison["repeats"] != 3 or
            comparison.get("order_by_repeat") != expected_order or
            comparison.get("traversal") != "public-batched" or
            comparison.get("diagnostics") != "public-batched" or
            comparison.get("resource_model") != "public-vector"):
        raise ValueError("Manifest selectors or alternating schedule are malformed")
    for value in (comparison.get("policy_probability_tolerance"),
                  comparison.get("diagnostic_tolerance")):
        if (type(value) not in (int, float) or value <= 0 or
                not math.isfinite(value)):
            raise ValueError("Manifest tolerances must be finite positive numbers")
    if type(manifest.get("case")) is not dict:
        raise ValueError("Manifest case must be an object")
    return comparison


def _request(case: dict, comparison: dict) -> FourStreetSolveRequest:
    def actions(value: dict) -> PostflopActions:
        return PostflopActions(
            bet_sizes=tuple(value["bet_sizes"]),
            raise_sizes=tuple(value["raise_sizes"]),
            max_raises=value["max_raises"],
            include_all_in=value["include_all_in"],
        )

    return FourStreetSolveRequest(
        case["sb_range"], case["bb_range"], tuple(case["runouts"]),
        preflop_config=PreflopConfig.from_dict(case["config"]),
        flop_actions=actions(case["flop_config"]),
        turn_actions=actions(case["turn_config"]),
        river_actions=actions(case["river_config"]),
        iterations=comparison["iterations"],
        algorithm=comparison["algorithm"],
        traversal=comparison["traversal"],
        diagnostics=comparison["diagnostics"],
        resource_model=comparison["resource_model"],
    )


def _phase_metadata(payload: dict) -> dict:
    selected = {}

    def visit(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                name = f"{path}.{key}" if path else key
                if any(word in key.lower() for word in ("timing", "seconds", "duration")):
                    selected[name] = item
                visit(item, name)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    visit(payload, "")
    return selected


def _policy_delta(left: dict, right: dict) -> float:
    def keyed(payload):
        return {
            (row["player"], row["hand"], tuple(row["history"])):
                {action["history_key"]: action["probability"] for action in row["actions"]}
            for row in payload["strategy"]
        }

    a, b = keyed(left), keyed(right)
    if a.keys() != b.keys():
        raise ValueError("Python and native policies contain different information rows")
    maximum = 0.0
    for key in a:
        if a[key].keys() != b[key].keys():
            raise ValueError(f"Python and native action identities differ at {key!r}")
        for action in a[key]:
            maximum = max(maximum, abs(a[key][action] - b[key][action]))
    return maximum


def run(output_directory: str | os.PathLike, executable: str | os.PathLike) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    comparison = _validate_manifest(manifest)
    order_by_repeat = comparison["order_by_repeat"]

    output = Path(output_directory).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Use a fresh benchmark output directory outside the checkout")
    if output.exists():
        raise FileExistsError("Benchmark output directory must be new")
    output.mkdir(parents=True)

    started = time.time_ns()
    before = _source_snapshot()
    if before["status_porcelain"]:
        _write_json(output / "failure.json", {
            "stage": "source-preflight",
            "error": "Benchmark requires a clean checkout before the attempt",
            "status_porcelain": before["status_porcelain"],
        })
        _write_json(output / "report.json", {
            "schema_version": 1,
            "benchmark_id": manifest["benchmark_id"],
            "outcome": "rejected-dirty-source",
            "source_before": before,
        })
        return {"outcome": "rejected-dirty-source"}
    native_identity = None
    try:
        native_identity = executable_identity(executable)
    except Exception as exc:
        failure = {
            "stage": "native-identity",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        _write_json(output / "failure.json", failure)
        _write_json(output / "report.json", {
            "schema_version": 1,
            "benchmark_id": manifest["benchmark_id"],
            "outcome": "failed-before-training",
            "source_before": before,
            "native_executable": str(executable),
            "failure": failure,
        })
        return {"outcome": "failed-before-training", "failure": failure}
    _write_json(output / "attempt.json", {
        "schema_version": 1,
        "benchmark_id": manifest["benchmark_id"],
        "attempt_id": str(uuid.uuid4()),
        "started_at_unix_ns": started,
        "platform": platform.platform(),
        "python": sys.version,
        "source_before": before,
        "native_executable_identity": native_identity,
        "selectors": comparison,
    })

    request = _request(manifest["case"], comparison)
    runs = []
    payloads = {}
    failures = []
    for repeat_index, order in enumerate(order_by_repeat, 1):
        for backend in order:
            sample_id = f"repeat-{repeat_index}-{backend}"
            started_ns = time.time_ns()
            timer = time.perf_counter()
            try:
                result = (solve_four_street(request) if backend == "python" else
                          solve_four_street(request, native_executable=str(executable)))
                raw = result.to_json().encode("utf-8")
                elapsed = time.perf_counter() - timer
                raw_path = output / f"{sample_id}-raw-envelope.json"
                _write_bytes(raw_path, raw)
                payload = json.loads(raw)["payload"]
                payloads[sample_id] = payload
                replay = replay_policy(
                    payload, manifest["case"]["sb_range"], manifest["case"]["bb_range"],
                    config=manifest["case"]["config"],
                    runouts=manifest["case"]["runouts"],
                    flop_config=manifest["case"]["flop_config"],
                    turn_config=manifest["case"]["turn_config"],
                    river_config=manifest["case"]["river_config"],
                )
                replay_gaps = compare_result(
                    payload, replay, tolerance=comparison["diagnostic_tolerance"])
                replay_receipt = {
                    "sample_id": sample_id,
                    "oracle": replay,
                    "metric_gaps": replay_gaps,
                    "raw_sha256": hashlib.sha256(raw).hexdigest(),
                }
                _write_json(output / f"{sample_id}-numeric-replay.json", replay_receipt)
                row = {
                    "sample_id": sample_id,
                    "backend": backend,
                    "repeat": repeat_index,
                    "started_at_unix_ns": started_ns,
                    "elapsed_seconds": elapsed,
                    "raw_path": raw_path.name,
                    "raw_bytes": len(raw),
                    "raw_sha256": hashlib.sha256(raw).hexdigest(),
                    "worlds": payload.get("worlds"),
                    "states": payload.get("public_states"),
                    "decisions": payload.get("decisions"),
                    "information_rows": len(payload.get("strategy", [])),
                    "nash_conv": payload.get("nash_conv"),
                    "phase_metadata": _phase_metadata(payload),
                    "native_training": payload.get("native_training"),
                    "numeric_replay": "passed",
                }
                runs.append(row)
            except Exception as exc:  # preserve the first failed sample; never retry it
                failure = {
                    "sample_id": sample_id,
                    "backend": backend,
                    "repeat": repeat_index,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "elapsed_seconds": time.perf_counter() - timer,
                }
                failures.append(failure)
                _write_json(output / f"{sample_id}-failure.json", failure)
                _write_json(output / "report.json", {
                    "schema_version": 1,
                    "benchmark_id": manifest["benchmark_id"],
                    "outcome": "failed-first-sample",
                    "runs": runs,
                    "failures": failures,
                    "source_before": before,
                    "source_after": _source_snapshot(),
                })
                return {"outcome": "failed-first-sample", "failure": failure}

    paired = []
    max_probability_delta = 0.0
    for repeat_index in range(1, comparison["repeats"] + 1):
        python_id = f"repeat-{repeat_index}-python"
        native_id = f"repeat-{repeat_index}-native"
        delta = _policy_delta(payloads[python_id], payloads[native_id])
        max_probability_delta = max(max_probability_delta, delta)
        paired.append({
            "repeat": repeat_index,
            "python_elapsed_seconds": next(row["elapsed_seconds"] for row in runs
                                            if row["sample_id"] == python_id),
            "native_elapsed_seconds": next(row["elapsed_seconds"] for row in runs
                                            if row["sample_id"] == native_id),
            "policy_max_abs_probability_delta": delta,
        })
    after = _source_snapshot()
    if after != before:
        failures.append({"stage": "post-run-source-check",
                         "error": "HEAD, source files, or Git status changed during experiment"})
    report = {
        "schema_version": 1,
        "benchmark_id": manifest["benchmark_id"],
        "outcome": "complete" if not failures else "source-changed-during-run",
        "started_at_unix_ns": started,
        "finished_at_unix_ns": time.time_ns(),
        "source_before": before,
        "source_after": after,
        "native_executable_identity": native_identity,
        "selectors": comparison,
        "runs": runs,
        "paired": paired,
        "python_median_seconds": statistics.median(
            row["elapsed_seconds"] for row in runs if row["backend"] == "python"),
        "native_median_seconds": statistics.median(
            row["elapsed_seconds"] for row in runs if row["backend"] == "native"),
        "native_over_python_median_speedup": (
            statistics.median(row["elapsed_seconds"] for row in runs
                              if row["backend"] == "python") /
            statistics.median(row["elapsed_seconds"] for row in runs
                              if row["backend"] == "native")),
        "policy_max_abs_probability_delta": max_probability_delta,
        "policy_probability_tolerance": comparison["policy_probability_tolerance"],
        "policy_compatibility": (
            "pass" if max_probability_delta <= comparison["policy_probability_tolerance"]
            else "miss"),
        "failures": failures,
        "scope": manifest["scope"],
    }
    _write_json(output / "report.json", report)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--native-executable", default=os.environ.get("OPENPOKER_NATIVE_PUBLIC_EXE"))
    args = parser.parse_args(argv)
    if not args.native_executable:
        parser.error("--native-executable or OPENPOKER_NATIVE_PUBLIC_EXE is required")
    try:
        report = run(args.output_directory, args.native_executable)
    except Exception as exc:
        parser.exit(1, f"benchmark failed before/while starting: {type(exc).__name__}: {exc}\n")
    print(json.dumps({"outcome": report.get("outcome"), "report": str(Path(args.output_directory).resolve() / "report.json")},
                     sort_keys=True))
    return (0 if report.get("outcome") == "complete" and
            report.get("policy_compatibility") == "pass" and
            not report.get("failures") else 1)


if __name__ == "__main__":
    raise SystemExit(main())
