"""Frozen native-vs-Python full-board preflop preparation evidence.

The runner is opt-in, builds no executable, performs no work on import and
refuses to measure unless the checkout is clean and an explicit native build is
provided. Run only after source and fixture review:
    python -m scripts.benchmark_native_preflop --build-dir ../native-preflop
"""
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import argparse
import gc
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from time import perf_counter
import tracemalloc

from pokerlab import native_preflop_equity as native
from pokerlab import preflop_full_board_equity as equity
from pokerlab.preflop_push_fold import (
    MAX_MODELED_LOOP_ENTRIES, _admit, _options,
    prepare_preflop_equities, solve_prepared_push_fold,
)
from scripts.preflop_push_fold_validation import (
    replay, weighted_equilibrium_certificate,
)
from scripts.preflop_push_fold_equilibrium import equilibrium

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "benchmarks/native-preflop-v1.json"
RESULTS = ROOT / "benchmarks/results"
PREFIX = "native-preflop-v1"
SPEC_SHA256 = "99ece3e543ab873e6cdf739a965f45f4d7513a9c75ffb913a01e6b75e5000e16"
PINNED = "a5e1b75ab424c97673f5126796b9d7eae14b0706"
PINNED_BLOBS = {
    "benchmarks/results/preflop-push-fold-v1-oracle-pair-0.json":
        "cc510379eed9484f30e59e428917a9e55ba027a7",
    "benchmarks/results/preflop-push-fold-v1-oracle-pair-1.json":
        "d639fecaee1c9f1ca1eaec95bb29e3162ddd00ff",
    "benchmarks/results/preflop-push-fold-v1-oracle-pair-2.json":
        "864c80c32739f6665b6010c200ad31bcb32e439f",
}


def checksum(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()


def validate_spec(config):
    if checksum(config) != SPEC_SHA256 or "artifact_sha256" in config:
        raise ValueError("Runner requires the exact native-preflop-v1 fixture")
    if (config["schema_version"] != 1 or config["benchmark_id"] != PREFIX
            or config["iterations"] != 2000 or config["algorithm"] != "cfrplus"
            or config["repeats"] != 3 or len(config["case_definitions"]) != 4
            or [case["id"] for case in config["case_definitions"]] != [
                "base-sb-deep", "base-symmetric-two",
                "base-bb-deep", "split-four-pairs"]
            or [case["compatible_pairs"] for case in config["case_definitions"]] != [3, 3, 3, 4]
            or config["acceptance"] != {
                "final_exploitability_chip_limit": 0.005,
                "final_known_value_error_chip_limit": 0.005,
                "metric_absolute_tolerance": 1e-10,
                "gate_padding": 1e-10
            }):
        raise ValueError("Native fixture identities or gates changed")
    if set(config["historical_source"]["pairs"][i]["blob_sha1"]
           for i in range(3)) != set(PINNED_BLOBS.values()):
        raise ValueError("Pinned historical pair blob set changed")
    return config


def _lf(data):
    return data.replace(b"\r\n", b"\n")


def source_hashes():
    paths = set((ROOT / "pokerlab").glob("*.py"))
    paths.update((ROOT / "tests").glob("test_*.py"))
    paths.update((ROOT / "native").glob("*.c"))
    paths.update(ROOT / name for name in (
        "AGENTS.md",
        "scripts/preflop_validation.py",
        "scripts/preflop_push_fold_validation.py",
        "scripts/preflop_push_fold_equilibrium.py",
        "scripts/build_native_preflop.py",
        "scripts/benchmark_native_preflop.py",
        "benchmarks/native-preflop-v1.json",
    ))
    result = {}
    for path in sorted(paths):
        if not path.is_file():
            raise FileNotFoundError(path)
        raw = path.read_bytes()
        rel = path.relative_to(ROOT).as_posix()
        result[rel] = {
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "lf_sha256": hashlib.sha256(_lf(raw)).hexdigest(),
        }
    return result


def _git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def git_snapshot():
    return {
        "revision": _git("rev-parse", "HEAD"),
        "status": _git("status", "--porcelain", "--untracked-files=all").splitlines(),
    }


def _canonical_hand(value):
    return "".join(value)


def preflight_cases(config):
    """Admit every fixture before reading the build manifest or counting boards."""
    cases = []
    for case in config["case_definitions"]:
        money = _options(case["config"], config["iterations"],
                         config["algorithm"], 0)
        plan = equity.plan_preflop_equities(case["sb_range"], case["bb_range"])
        budget = _admit(plan, config["iterations"], config["algorithm"])
        if (plan.budget["candidate_pairs"] != case["candidate_pairs"]
                or plan.budget["compatible_pairs"] != case["compatible_pairs"]
                or plan.budget["board_evaluations_upper_bound"]
                    != case["compatible_pairs"] * config["pair_count"]
                or plan.budget["rank_calls_upper_bound"]
                    != 2 * case["compatible_pairs"] * config["pair_count"]
                or budget["total_loop_entries_upper_bound"] > MAX_MODELED_LOOP_ENTRIES):
            raise AssertionError(f"Preflight census changed for {case['id']}")
        expected = config["expected_pair_priors"][
            "split" if case["id"] == "split-four-pairs" else "base"
        ]
        actual = [
            [f"{_canonical_hand(plan.hands[0][i])}|{_canonical_hand(plan.hands[1][j])}",
             [prior.numerator, prior.denominator]]
            for i, j, prior in plan.pairs
        ]
        if actual != expected:
            raise AssertionError(f"Pair identities/priors changed for {case['id']}")
        cases.append({
            "case": case, "plan": plan, "money": money, "budget": budget,
            "pair_priors": actual,
        })
    return cases


def _load_pinned_oracles(config):
    expected_pairs = {
        (row["sb_hand"], row["bb_hand"])
        for row in config["historical_source"]["pairs"]
    }
    result, metadata = {}, []
    for reference in config["historical_source"]["pairs"]:
        path = reference["path"]
        blob = _git("rev-parse", f"{PINNED}:{path}")
        if blob != reference["blob_sha1"]:
            raise ValueError(f"Pinned PR125 blob identity changed: {path}")
        raw = subprocess.check_output(["git", "show", f"{PINNED}:{path}"], cwd=ROOT)
        row = json.loads(raw.decode("utf-8"))
        actual_artifact = checksum({k: v for k, v in row.items() if k != "artifact_sha256"})
        if actual_artifact != reference["artifact_sha256"] or row.get("artifact_sha256") != actual_artifact:
            raise ValueError(f"Pinned PR125 artifact checksum failed: {path}")
        if (row.get("phase") != "independent-full-board-oracle"
                or row.get("benchmark_id") != "preflop-push-fold-v1"
                or row.get("provenance", {}).get("git_revision") != "151c35a6739251bb280b5be4373c35a05daa2950"):
            raise ValueError(f"Pinned PR125 oracle identity failed: {path}")
        counts = row.get("counts")
        identity = (counts.get("sb_hand"), counts.get("bb_hand"))
        if identity != (reference["sb_hand"], reference["bb_hand"]):
            raise ValueError(f"Pinned pair identity differs: {path}")
        wins, ties, losses = (counts.get(name) for name in ("wins", "ties", "losses"))
        if (any(type(x) is not int or x < 0 for x in (wins, ties, losses))
                or counts.get("boards") != config["pair_count"]
                or wins + ties + losses != config["pair_count"]):
            raise ValueError(f"Pinned W/T/L census failed: {path}")
        key = identity
        if key in result:
            raise ValueError("Duplicate pinned pair identity")
        expected_priors = {
            ("AdAs", "KdKs"): Fraction(8, 13),
            ("QdQs", "AsKh"): Fraction(1, 13),
            ("QdQs", "KdKs"): Fraction(4, 13),
        }
        if abs(counts.get("pair_probability") - float(expected_priors[key])) > 1e-15:
            raise ValueError(f"Pinned oracle prior changed: {path}")
        result[key] = (wins, ties, losses)
        metadata.append({
            "path": path, "git_blob_sha1": blob,
            "artifact_sha256": actual_artifact,
            "pair": list(identity), "counts": [wins, ties, losses],
            "boards": counts["boards"],
            "pair_probability_binary64": counts["pair_probability"],
        })
    if set(result) != expected_pairs or len(result) != 3:
        raise ValueError("Pinned oracle pair coverage changed")
    return result, metadata


def _count_for_target(sb, bb, source_counts):
    key = (_canonical_hand(sb), _canonical_hand(bb))
    if key in source_counts:
        return source_counts[key], None
    if key == ("QdQs", "AsKc"):
        return source_counts[("QdQs", "AsKh")], {
            "source_pair": ["QdQs", "AsKh"],
            "target_pair": ["QdQs", "AsKc"],
            "global_suit_map": {"c": "h", "d": "d", "h": "c", "s": "s"},
            "derivation": "Apply one global c<->h suit bijection to every legal unordered board and both hands. It maps AsKh to AsKc while leaving QdQs fixed, so the complete W/T/L census is identical; no fresh enumeration is claimed.",
        }
    raise ValueError(f"No pinned physical count or declared suit derivation for {key}")


def reference_table(preflight, source_counts):
    plan = preflight["plan"]
    counts, derivations = [], []
    for i, j, _ in plan.pairs:
        values, derivation = _count_for_target(
            plan.hands[0][i], plan.hands[1][j], source_counts
        )
        counts.append(values)
        if derivation is not None:
            derivations.append(derivation)
    worlds = []
    for (i, j, prior), (wins, ties, losses) in zip(plan.pairs, counts):
        for sign, count in zip((-1, 0, 1), (losses, ties, wins)):
            if count:
                mass = prior * Fraction(count, config_board_count())
                worlds.append((i, j, equity._as_positive_float(mass, "categorical mass"), sign))
    table = equity.FullBoardEquities(
        plan.hands, plan.pairs, tuple(counts), tuple(worlds), plan._budget_items
    )
    table.validate()
    rows = []
    for (i, j, prior), (wins, ties, losses) in zip(plan.pairs, counts):
        rows.append({
            "sb_hand": _canonical_hand(plan.hands[0][i]),
            "bb_hand": _canonical_hand(plan.hands[1][j]),
            "wins": wins, "ties": ties, "losses": losses,
            "boards": config_board_count(), "pair_probability": float(prior),
        })
    return table, rows, derivations


def config_board_count():
    return math.comb(48, 5)


def _payload_sha(value):
    return checksum(value)


def _jsonable_exact(value):
    if isinstance(value, Fraction):
        return [value.numerator, value.denominator]
    if isinstance(value, dict):
        return {str(k): _jsonable_exact(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable_exact(v) for v in value]
    return value


def _certificate(case, result, counts):
    if case["id"] != "split-four-pairs":
        candidate, exact = weighted_equilibrium_certificate(result, counts)
        return candidate, _jsonable_exact(exact), "weighted_equilibrium_certificate"
    witness = equilibrium(case["sb_range"], case["bb_range"],
                          case["config"], counts)
    candidate = deepcopy(result)
    value = Fraction(*witness["value_sb_fraction"])
    for row in candidate["strategy"]:
        player = 0 if row["player"] == "sb" else 1
        shove_call = witness["behavioral_probabilities"][(player, row["hand"])]
        probability = float(shove_call)
        row["actions"][1]["probability"] = probability
        row["actions"][0]["probability"] = 1.0 - probability
    candidate.update(
        value_sb=float(value), value_bb=float(-value),
        sb_best_response_value=float(value), bb_best_response_value=float(-value),
        nash_conv=0.0, exploitability=0.0,
        sb_best_response_gain=0.0, bb_best_response_gain=0.0,
    )
    return candidate, _jsonable_exact(witness), "exact_zero_sum_witness"


def quality(result, case, counts, config):
    try:
        measured = replay(
            result, case["sb_range"], case["bb_range"], case["config"],
            counts, config["acceptance"]["metric_absolute_tolerance"],
        )
        certificate, exact, method = _certificate(case, result, counts)
        certified = replay(
            certificate, case["sb_range"], case["bb_range"], case["config"],
            counts, config["acceptance"]["metric_absolute_tolerance"],
        )
        value_error = abs(measured["value_sb"] - certified["value_sb"])
        gaps = measured["scalar_absolute_gaps"]
        max_gap = max(gaps.values(), default=0.0)
        padding = config["acceptance"]["gate_padding"]
        exp_limit = config["acceptance"]["final_exploitability_chip_limit"]
        value_limit = config["acceptance"]["final_known_value_error_chip_limit"]
        return {
            "independent_replay": measured, "certificate_replay": certified,
            "certificate_method": method, "exact_certificate": exact,
            "known_value_error": value_error,
            "max_scalar_absolute_gap": max_gap,
            "metric_parity_passed": max_gap <= config["acceptance"]["metric_absolute_tolerance"],
            "exploitability_passed": measured["exploitability"] + padding <= exp_limit,
            "known_value_passed": value_error + padding <= value_limit,
            "passed": (max_gap <= config["acceptance"]["metric_absolute_tolerance"]
                       and measured["exploitability"] + padding <= exp_limit
                       and value_error + padding <= value_limit),
        }
    except Exception as exc:
        return {"quality_error": f"{type(exc).__name__}: {exc}", "passed": False}


def _invoke_native(case, build_directory):
    prepared = native.prepare_native_preflop_equities(
        case["sb_range"], case["bb_range"], build_directory=build_directory
    )
    result = solve_prepared_push_fold(
        prepared.equities, config=case["config"], iterations=2000,
        algorithm="cfrplus",
    )
    serialized = json.dumps(
        {"result": result, "equity_preparation": prepared.metadata},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    return prepared, result, serialized


def _invoke_python(case):
    table = prepare_preflop_equities(
        case["sb_range"], case["bb_range"]
    )
    result = solve_prepared_push_fold(
        table, config=case["config"], iterations=2000, algorithm="cfrplus"
    )
    serialized = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return table, result, serialized


def _forbid_python_ranking():
    from contextlib import ExitStack
    from unittest.mock import patch
    from pokerlab import cards as cards_module

    stack = ExitStack()
    stack.enter_context(patch.object(
        cards_module, "rank_hand",
        side_effect=AssertionError("native call entered shared Python ranker")
    ))
    for target in ("rank_hand", "_board_combinations"):
        stack.enter_context(patch.object(
            equity, target, side_effect=AssertionError("native call entered Python board evaluator")
        ))
    stack.enter_context(patch.object(
        equity.PreflopEquityPlan, "build",
        side_effect=AssertionError("native call entered Python board plan build")
    ))
    return stack


def _result_summary(result, counts, case, config):
    check = quality(result, case, counts, config)
    return {
        "result_sha256": _payload_sha(result),
        "result": result,
        "quality": check,
    }


def _write_live(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline='\n')
    tmp.replace(path)


def _write_report(path, report, frozen_hashes, frozen_git):
    if source_hashes() != frozen_hashes or git_snapshot() != frozen_git:
        report["source_unchanged"] = False
        report["failures"].append("Source or Git state changed before publication")
        report["passed"] = False
    else:
        report["source_unchanged"] = True
    path.parent.mkdir(parents=True, exist_ok=True)
    report["artifact_sha256"] = checksum({
        key: value for key, value in report.items() if key != "artifact_sha256"
    })
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline='\n')
    temporary.replace(path)


def _emit(live_path, live, message):
    print(message, flush=True)
    live["last_event"] = {"utc": datetime.now(timezone.utc).isoformat(), "message": message}
    _write_live(live_path, live)


def _check_result(actual, reference, table, expected_table, preflight):
    checks = {
        "counts_match_reference": table.counts == expected_table.counts,
        "equity_table_exact": table == expected_table,
        "work_budget_matches_preflight": actual["work_budget"] == preflight["budget"],
        "solver_payload_exact": actual == reference,
    }
    return checks


def _trace_native(case, build_directory):
    gc.collect()
    tracemalloc.start()
    try:
        with _forbid_python_ranking():
            prepared, result, serialized = _invoke_native(case, build_directory)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return prepared, result, serialized, peak


def run(config, build_directory, output, live_path):
    config = validate_spec(config)
    output = Path(output).resolve()
    live_path = Path(live_path).resolve()
    build_directory = Path(build_directory).resolve(strict=True)
    if (live_path == ROOT or ROOT in live_path.parents
            or live_path == build_directory or build_directory in live_path.parents):
        raise ValueError('Live progress must stay outside the frozen repository')
    if (output == live_path or build_directory == output or build_directory in output.parents
            or output.suffix != '.json'
            or ((output == ROOT or ROOT in output.parents)
                and RESULTS not in output.parents)):
        raise ValueError('Report must be a separate JSON artifact, never source/build/progress')
    start_git = git_snapshot()
    if start_git["status"]:
        raise RuntimeError("Formal native benchmark requires a clean checkout")
    frozen_hashes = source_hashes()
    preflights = preflight_cases(config)
    live = {
        "schema_version": 1, "benchmark_id": PREFIX, "status": "running",
        "phase": "preflight-complete", "git_revision": start_git["revision"],
        "calls_completed": [], "failures": [],
    }
    _write_live(live_path, live)

    # Physical inputs are authenticated by pinned Git blob and artifact hashes,
    # then checked against exact current range support before any native call.
    pinned_counts, pinned_artifacts = _load_pinned_oracles(config)
    reference_inputs = {}
    for item in preflights:
        table, count_rows, derivations = reference_table(item, pinned_counts)
        case = item["case"]
        expected_result = solve_prepared_push_fold(
            table, config=case["config"], iterations=config["iterations"],
            algorithm=config["algorithm"],
        )
        if expected_result["work_budget"] != item["budget"]:
            raise AssertionError("Pinned-count reference work budget differs from preflight")
        quality_result = quality(expected_result, case, count_rows, config)
        if not quality_result["passed"]:
            live["failures"].append(f"{case['id']}: pinned-reference quality gate failed")
        reference_inputs[case["id"]] = {
            "table": table, "counts": count_rows, "derivations": derivations,
            "result": expected_result, "quality": quality_result,
        }
    live["phase"] = "references-ready"
    _write_live(live_path, live)
    if live["failures"]:
        live.update(status="failed", phase="reference-quality-precheck")
        _write_live(live_path, live)
        raise RuntimeError("Pinned-reference quality precheck failed; full-board measurement was not started")

    build_directory = Path(build_directory).resolve(strict=True)
    if build_directory == ROOT or ROOT in build_directory.parents:
        raise ValueError("Native build directory must be outside the repository")
    executable, manifest = native._backend(build_directory)
    live["native_build"] = manifest
    live["phase"] = "measuring"
    _write_live(live_path, live)
    samples = []
    failures = list(live["failures"])
    baseline_id = config["baseline_python_case"]
    cases = [item["case"] for item in preflights]
    repetitions = config["repeats"]

    for repeat in range(repetitions):
        offset = repeat % len(cases)
        ordered = cases[offset:] + cases[:offset]
        for case in ordered:
            expected = reference_inputs[case["id"]]
            backends = ["native"]
            if case["id"] == baseline_id:
                backends = ["native", "python"] if repeat % 2 == 0 else ["python", "native"]
            for backend in backends:
                label = f"{case['id']} {backend} repeat {repeat + 1}/{repetitions}"
                _emit(live_path, live, "START " + label)
                gc.collect()
                started = perf_counter()
                try:
                    if backend == "native":
                        with _forbid_python_ranking():
                            prepared, result, serialized = _invoke_native(case, build_directory)
                        table = prepared.equities
                        metadata = prepared.metadata
                        if metadata['build'] != manifest:
                            raise RuntimeError('Native build identity changed during measurement')
                    else:
                        table, result, serialized = _invoke_python(case)
                        metadata = {"backend": "python-reference"}
                    elapsed = perf_counter() - started
                    checks = _check_result(
                        result, expected["result"], table, expected["table"],
                        next(item for item in preflights if item["case"]["id"] == case["id"]),
                    )
                    quality_result = quality(result, case, expected["counts"], config)
                    if not all(checks.values()):
                        failures.append(f"{label}: exact reference/work parity failed")
                    if not quality_result["passed"]:
                        failures.append(f"{label}: independent quality gate failed")
                    sample = {
                        "case_id": case["id"], "backend": backend, "repeat": repeat + 1,
                        "complete_call_seconds": elapsed,
                        "serialized_result_sha256": _payload_sha(result),
                        "serialized_complete_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
                        "equity_metadata": metadata,
                        "checks": checks, "quality": quality_result,
                        "serialized_json_bytes": len(serialized.encode("utf-8")),
                    }
                except Exception as exc:
                    elapsed = perf_counter() - started
                    failures.append(f"{label}: {type(exc).__name__}: {exc}")
                    sample = {
                        "case_id": case["id"], "backend": backend, "repeat": repeat + 1,
                        "complete_call_seconds": elapsed,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                samples.append(sample)
                live["calls_completed"] = samples
                live["failures"] = failures
                _emit(live_path, live, "DONE " + label)

    baseline_case = next(case for case in cases if case["id"] == baseline_id)
    _emit(live_path, live, "START native Python-allocation trace")
    trace_started = perf_counter()
    try:
        traced_prepared, traced_result, traced_serialized, traced_peak = _trace_native(
            baseline_case, build_directory
        )
        traced_identity = {
            "result_sha256": _payload_sha(traced_result),
            "equity_table_counts": [list(row) for row in traced_prepared.equities.counts],
            "serialized_complete_sha256": hashlib.sha256(traced_serialized.encode()).hexdigest(),
        }
        base_native = next(s for s in samples
                           if s["case_id"] == baseline_id and s["backend"] == "native")
        trace_matches = (
            traced_identity["result_sha256"] == base_native["serialized_result_sha256"]
            and traced_identity["serialized_complete_sha256"]
                == base_native["serialized_complete_sha256"]
        )
        if not trace_matches:
            failures.append("Allocation trace payload differs from the measured baseline fixture")
    except Exception as exc:
        traced_peak = None
        traced_identity = {"error": f"{type(exc).__name__}: {exc}"}
        trace_matches = False
        failures.append(f"Allocation trace: {type(exc).__name__}: {exc}")
    trace_seconds = perf_counter() - trace_started
    live["calls_completed"] = samples
    live["failures"] = failures
    live["phase"] = "verifying-source"
    _write_live(live_path, live)

    end_git = git_snapshot()
    end_hashes = source_hashes()
    try:
        end_executable, end_manifest = native._backend(build_directory)
        build_unchanged = end_executable == executable and end_manifest == manifest
    except Exception as exc:
        build_unchanged = False
        failures.append(f'Final native build identity check: {type(exc).__name__}: {exc}')
    if not build_unchanged:
        failures.append('Native build identity changed during benchmark')
    source_unchanged = start_git == end_git and frozen_hashes == end_hashes
    if not source_unchanged:
        failures.append("Source/Git state changed during benchmark")
    timing = {}
    for case in cases:
        for backend in ('native', 'python'):
            group = [sample for sample in samples
                     if sample['case_id'] == case['id'] and sample['backend'] == backend]
            if group and (any('error' in sample for sample in group)
                          or len({sample['serialized_complete_sha256'] for sample in group
                                  if 'error' not in sample}) != 1):
                failures.append(f"{case['id']}:{backend}: repeated complete payloads differ or failed")
        for backend in ("native", "python"):
            elapsed = [s["complete_call_seconds"] for s in samples
                       if s["case_id"] == case["id"] and s["backend"] == backend
                       and "error" not in s]
            if elapsed:
                timing[f"{case['id']}:{backend}"] = {
                    "samples_seconds": elapsed,
                    "median_seconds": statistics.median(elapsed),
                }
    speed = None
    native_times = timing.get(f"{baseline_id}:native", {}).get("samples_seconds", [])
    python_times = timing.get(f"{baseline_id}:python", {}).get("samples_seconds", [])
    if len(native_times) == len(python_times) == repetitions and all(t > 0 for t in native_times):
        speed = {
            "python_median_seconds": statistics.median(python_times),
            "native_median_seconds": statistics.median(native_times),
            "median_ratio_python_over_native":
                statistics.median(python_times) / statistics.median(native_times),
            "sample_gain_ratios": [p / n for p, n in zip(python_times, native_times)],
            "scope": "Only this paired base fixture and this recorded machine/build; no universal native speed claim.",
        }
    report = {
        "schema_version": 1, "benchmark_id": PREFIX,
        "provenance": {
            "git_start": start_git, "git_end": end_git,
            "source_hashes_start": frozen_hashes, "source_hashes_end": end_hashes,
            "source_unchanged": source_unchanged,
            "python": sys.version, "executable": sys.executable,
            "platform": platform.platform(),
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "native_build_directory": str(build_directory),
            "native_build_manifest": manifest,
            "native_executable_sha256": manifest["executable_sha256"],
            "native_build_identity_unchanged": build_unchanged,
        },
        "config": config,
        "pinned_physical_oracle": pinned_artifacts,
        "preflights": [{
            "case_id": item["case"]["id"], "plan_budget": item["plan"].budget,
            "solve_admission": item["budget"], "pair_priors": item["pair_priors"],
            "reference_table_counts": [
                {k: v for k, v in row.items() if k != "pair_probability"}
                for row in reference_inputs[item["case"]["id"]]["counts"]
            ],
            "count_derivations": reference_inputs[item["case"]["id"]]["derivations"],
            "reference_result_sha256": _payload_sha(reference_inputs[item["case"]["id"]]["result"]),
            "reference_quality": reference_inputs[item["case"]["id"]]["quality"],
        } for item in preflights],
        "samples": samples,
        "timings": timing,
        "paired_baseline_comparison": speed,
        "native_python_traced_peak_bytes": traced_peak,
        "native_complete_call_seconds_under_tracemalloc": trace_seconds,
        "tracemalloc_identity": traced_identity,
        "tracemalloc_matches_measured_native_call": trace_matches,
        "memory_scope": config["trace_scope"],
        "methodology": config["method"],
        "failures": failures,
        "passed": not failures and source_unchanged and trace_matches
            and len(samples) == sum(
                repetitions * (2 if case["id"] == baseline_id else 1)
                for case in cases
            ),
    }
    _write_report(Path(output), report, frozen_hashes, end_git)
    live.update(status="complete" if report["passed"] else "failed",
                phase="published", output=str(Path(output).resolve()),
                passed=report["passed"], failures=failures)
    _write_live(live_path, live)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True,
                        help="Existing native build directory; the runner never compiles")
    parser.add_argument("--output", default=str(RESULTS / f"{PREFIX}.json"))
    parser.add_argument("--live-output", default=str(ROOT.parent / "native-preflop-live.json"))
    args = parser.parse_args(argv)
    config = validate_spec(json.loads(CONFIG.read_text(encoding="utf-8")))
    live_path = Path(args.live_output)
    try:
        report = run(config, args.build_dir, args.output, live_path)
    except Exception as exc:
        try:
            failed = json.loads(live_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            failed = {}
        failed.update({
            "schema_version": 1, "benchmark_id": PREFIX, "status": "failed",
            "phase": "aborted", "error": f"{type(exc).__name__}: {exc}",
            "updated_utc": datetime.now(timezone.utc).isoformat(),
        })
        try:
            _write_live(live_path, failed)
        except Exception:
            pass
        raise
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
