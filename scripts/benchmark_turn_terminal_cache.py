"""Research-only measurement of the opt-in matrix-free turn terminal cache.

The short preflight checks complete-payload parity without timing. The measure
phase requires explicit opt-in and records uncontrolled complete-call timings;
it does not promote the cache to a default or make a hardware-independent claim.
"""
import argparse
import copy
import gc
import hashlib
import json
import math
import platform
import statistics
import subprocess
import time
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

from pokerlab.matrix_free_turn import solve_matrix_free_turn
from pokerlab.turn_terminal_cache import (
    CACHE_SLOTS_PER_CALL,
    FIXED_SETUP_SLOTS,
    MAX_CACHE_ENTRIES,
    MAX_CACHE_SLOT_WORK,
    SETUP_SLOTS_PER_BRANCH,
)
from scripts import audit_turn_rational_certificate as rational_audit
from scripts import benchmark_turn_river_independent as independent_runner
from scripts import benchmark_turn_terminal_memoization as old_benchmark
from scripts import turn_rational_certificate
from scripts import turn_river_validation as validator


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "benchmarks" / "results" / "turn-terminal-cache-v1.json"
POLICY_DIR = ROOT / "benchmarks" / "results" / "turn-terminal-cache-policies-v1"
SELECTED_ID = old_benchmark.SELECTED_ID
FULL_ID = old_benchmark.FULL_ID
SCENARIOS = (SELECTED_ID, FULL_ID)
METRICS = old_benchmark.METRICS
TOLERANCE = 1e-9
REPORTING_THRESHOLD = 0.001
MEASURE_ITERATIONS = 300
PAIRED_ORDERS = (("baseline", "ranked-lru"),
                 ("ranked-lru", "baseline"),
                 ("baseline", "ranked-lru"))

SELECTED_PARENT_REPORT_SHA256 = (
    "96d53995f45c6f07d43a35ae871fac6ca97c6d9dca6a8de067e8b46e15392b78"
)
SELECTED_3K_POLICY_NAME = (
    "two-conditioned-runouts-asymmetric-multisize-matrix-free-3000.json"
)
SELECTED_3K_POLICY_SHA256 = (
    "c72bbdbc112513adcfcf678b78adf1c18aa1e17cfe7f970bf651a9fe98172efc"
)
RATIONAL_REPORT_NAME = "turn-rational-certificate-v1.json"
RATIONAL_REPORT_CANONICAL_SHA256 = (
    "fbab93a963a9dfdbd681ec63f8401cf572cad6cfcabd9dbeaf0e10b81cc03fa7"
)
RATIONAL_CERTIFICATE_INPUT = (
    ROOT / "benchmarks" / "results" / RATIONAL_REPORT_NAME
)
SELECTED_REPORT = ROOT / "benchmarks" / "results" / "turn-selected-accuracy-v1.json"
SELECTED_POLICY_DIR = ROOT / "benchmarks" / "results" / "turn-selected-accuracy-policies-v1"
RATIONAL_EXPECTED_NORMALIZED_SHA256 = (
    "44852dd624c2cbd7f04e728210c3d143e786794cab45b4bcd0fe170d74ce33e2"
)


def _json_bytes(value, *, pretty=False):
    if pretty:
        return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _canonical_digest(path):
    return _sha256(_json_bytes(json.loads(path.read_text(encoding="utf-8"))))


def _path_hash(path):
    return _sha256(path.read_bytes())


def _git_commit():
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    )
    commit = completed.stdout.strip()
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit.lower()):
        raise RuntimeError("Could not read the current repository commit identity.")
    return commit


def _parent_accuracy_row(report, backend, iterations):
    rows = [row for row in report["results"]
            if row.get("backend") == backend and
            row.get("iterations_completed") == iterations and
            row.get("iterations_requested") == iterations]
    if len(rows) != 1:
        raise ValueError("Pinned selected-turn accuracy report lacks one exact profile row.")
    return rows[0]


def _verify_pinned_inputs():
    """Verify historical data without freezing current production source."""
    old_reports = old_benchmark._verify_parent_archive()
    selected_report = json.loads(SELECTED_REPORT.read_text(encoding="utf-8"))
    if _canonical_digest(SELECTED_REPORT) != SELECTED_PARENT_REPORT_SHA256:
        raise ValueError("Pinned selected accuracy report canonical hash changed.")
    row = _parent_accuracy_row(selected_report, "matrix-free", 3_000)
    if (row.get("policy_file") != SELECTED_3K_POLICY_NAME or
            row.get("policy_sha256") != SELECTED_3K_POLICY_SHA256):
        raise ValueError("Pinned selected 3k row differs from its exact policy identity.")
    selected_policy = SELECTED_POLICY_DIR / SELECTED_3K_POLICY_NAME
    if _path_hash(selected_policy) != SELECTED_3K_POLICY_SHA256:
        raise ValueError("Pinned selected 3k policy bytes changed.")

    rational_report = json.loads(RATIONAL_CERTIFICATE_INPUT.read_text(encoding="utf-8"))
    if _canonical_digest(RATIONAL_CERTIFICATE_INPUT) != RATIONAL_REPORT_CANONICAL_SHA256:
        raise ValueError("Pinned rational certificate report changed.")
    rational_rows = [item for item in rational_report["results"]
                     if item.get("backend") == "matrix-free" and
                     item.get("iterations") == 3_000]
    if len(rational_rows) != 1:
        raise ValueError("Pinned rational report lacks the selected 3k certificate.")
    rational_row = rational_rows[0]
    if (rational_row.get("raw_policy_sha256") != SELECTED_3K_POLICY_SHA256 or
            rational_row.get("exact_nash_conv_threshold_fraction") != "1/1000" or
            rational_row.get("exact_nash_conv_threshold_met") is not True or
            rational_row.get("normalized_policy_sha256") != RATIONAL_EXPECTED_NORMALIZED_SHA256):
        raise ValueError("Pinned selected 3k normalized-profile certificate changed.")
    return {
        "old_matrix_free_1k_reports": old_reports,
        "selected_accuracy_report": selected_report,
        "selected_3k_row": row,
        "rational_report": rational_report,
        "rational_3k_row": rational_row,
    }


def _source_fingerprints():
    hashes = {
        str(path).replace("\\", "/"): digest
        for path, digest in independent_runner.source_hashes().items()
    }
    extra_paths = [
        Path(__file__).resolve(),
        ROOT / "pokerlab" / "turn_terminal_cache.py",
        ROOT / "scripts" / "benchmark_turn_terminal_memoization.py",
        ROOT / "scripts" / "turn_terminal_memoization.py",
        ROOT / "scripts" / "turn_rational_certificate.py",
        ROOT / "scripts" / "audit_turn_rational_certificate.py",
        ROOT / "tests" / "test_turn_terminal_cache.py",
        ROOT / "tests" / "test_matrix_free_turn_cache.py",
        ROOT / "tests" / "test_turn_terminal_cache_review.py",
        ROOT / "tests" / "test_matrix_free_turn_cache_review.py",
        ROOT / "tests" / "test_benchmark_turn_terminal_cache.py",
        ROOT / "tests" / "test_benchmark_turn_terminal_memoization.py",
        ROOT / "tests" / "test_turn_terminal_memoization_review.py",
        POLICY_DIR / ".gitattributes",
        SELECTED_REPORT,
        RATIONAL_CERTIFICATE_INPUT,
    ]
    for parent in old_benchmark.PARENTS.values():
        extra_paths.append(parent["report"])
        parent_row = old_benchmark._baseline_row(parent)
        extra_paths.append(parent["policy_directory"] / parent_row["policy_file"])
    extra_paths.extend((
        SELECTED_POLICY_DIR / SELECTED_3K_POLICY_NAME,
    ))
    for path in extra_paths:
        if not path.is_file():
            raise ValueError("A pinned code or input file is missing: " + str(path))
        hashes[path.resolve().relative_to(ROOT).as_posix()] = _path_hash(path)
    return dict(sorted(hashes.items()))


def _case(case_id):
    return old_benchmark._frozen_case(case_id)


def _solve(case, iterations, *, cached):
    options = {key: case[key] for key in ("river_config", "runouts") if key in case}
    return solve_matrix_free_turn(
        case["board"], case["oop"], case["ip"], case["config"],
        iterations=iterations, algorithm="cfrplus",
        terminal_cache="ranked-lru" if cached else "none", **options,
    )


def _legacy_payload(result):
    payload = copy.deepcopy(result)
    payload.pop("terminal_cache", None)
    return payload


def _independent_terminal_count(case):
    board = validator.cards(case["board"])
    config = validator._config(case["config"], "config")
    river_config = validator._config(case.get("river_config", case["config"]), "river_config")
    ranges = (validator.expand_range(case["oop"], board),
              validator.expand_range(case["ip"], board))
    worlds, selected = validator._worlds(board, ranges, case.get("runouts"))
    tree = validator._public_tree(board, config, river_config, selected, worlds)
    pending = [tree]
    terminals = 0
    while pending:
        node = pending.pop()
        if isinstance(node, validator._Terminal):
            terminals += 1
        elif isinstance(node, validator._Decision):
            pending.extend(node.children)
        elif isinstance(node, validator._Chance):
            pending.extend(node.branches.values())
    reachable = {world["river"] for world in worlds
                 if world["river"] is not None and world["weight"] > 0}
    return terminals, len(reachable)


def _validate_profile(result, case, iterations, *, cached):
    if (type(result.get("algorithm")) is not str or result["algorithm"] != "cfrplus" or
            type(result.get("iterations")) is not int or result["iterations"] != iterations):
        raise ValueError("Cache acceptance profile did not complete its fixed sweep count.")
    if "convergence" in result or "checkpoints" in result:
        raise ValueError("Cache acceptance profiles must not use a solver stopping target.")
    board = validator.cards(case["board"])
    if result.get("board") != list(board):
        raise ValueError("Profile public board differs from the frozen fixture.")
    if "runouts" in case:
        if result.get("runouts") != case["runouts"]:
            raise ValueError("Profile runouts differ from the frozen fixture.")
        expected_mode = "conditioned-subset"
    else:
        expected_mode = "full-deck"
    if result.get("runout_mode") != expected_mode:
        raise ValueError("Profile runout mode differs from the frozen fixture.")
    if type(result.get("worlds_materialized")) is not int or result["worlds_materialized"] != 0:
        raise ValueError("Matrix-free cache profile unexpectedly materialized worlds.")
    if type(result.get("strategy")) is not list:
        raise ValueError("Profile strategy must be a complete serialized row list.")
    if not cached:
        if "terminal_cache" in result:
            raise ValueError("Default profile unexpectedly emitted terminal-cache metadata.")
        return
    stats = result.get("terminal_cache")
    if type(stats) is not dict:
        raise ValueError("Opt-in profile is missing terminal-cache metadata.")
    terminal_count, branch_count = _independent_terminal_count(case)
    calls = terminal_count * (2 * iterations + 4)
    setup_slots = SETUP_SLOTS_PER_BRANCH * branch_count + FIXED_SETUP_SLOTS
    reserved_slots = calls * CACHE_SLOTS_PER_CALL + setup_slots
    integer_fields = (
        "terminal_count", "branch_count", "requested_iterations", "reserved_calls",
        "setup_slots", "reserved_slots", "actual_calls", "actual_slots", "hits",
        "misses", "evictions", "output_values_copied", "maximum_entries",
        "entries_before_cleanup", "entries_after_cleanup", "current_entries",
        "cache_entry_limit", "logical_slots_per_call", "logical_slot_limit",
        "logical_payload_bytes_upper_bound",
    )
    for field in integer_fields:
        if type(stats.get(field)) is not int or stats[field] < 0:
            raise ValueError("Terminal-cache counter is not a nonnegative exact integer: " + field)
    expected = {
        "terminal_count": terminal_count,
        "branch_count": branch_count,
        "requested_iterations": iterations,
        "reserved_calls": calls,
        "setup_slots": setup_slots,
        "reserved_slots": reserved_slots,
        "logical_slots_per_call": CACHE_SLOTS_PER_CALL,
        "logical_slot_limit": MAX_CACHE_SLOT_WORK,
        "cache_entry_limit": MAX_CACHE_ENTRIES,
        "logical_payload_bytes_upper_bound": MAX_CACHE_ENTRIES * 5 * 8,
        "entries_after_cleanup": 0,
        "current_entries": 0,
    }
    if stats.get("mode") != "ranked-lru" or stats.get("version") != "turn-terminal-cache-v1":
        raise ValueError("Terminal-cache metadata identifies an unexpected implementation.")
    if any(stats.get(field) != value for field, value in expected.items()):
        raise ValueError("Terminal-cache admission or cleanup metadata differs from its model.")
    if (stats["actual_calls"] > calls or
            stats["actual_slots"] != setup_slots + stats["actual_calls"] * CACHE_SLOTS_PER_CALL or
            stats["actual_slots"] > reserved_slots or
            stats["hits"] + stats["misses"] != stats["actual_calls"] or
            stats["evictions"] > stats["misses"] or
            stats["maximum_entries"] > MAX_CACHE_ENTRIES or
            stats["entries_before_cleanup"] > stats["maximum_entries"]):
        raise ValueError("Terminal-cache runtime counters violate the admitted envelope.")


def _replay(result, case):
    options = {key: case[key] for key in ("river_config", "runouts") if key in case}
    oracle = validator.replay_policy(
        result, case["oop"], case["ip"], board=case["board"],
        config=case["config"], **options,
    )
    differences = validator.compare_result(result, oracle, tolerance=TOLERANCE)
    if set(differences) != set(METRICS):
        raise ValueError("Independent turn replay did not compare all eight metrics.")
    if any(not math.isfinite(delta) or abs(delta) > TOLERANCE
           for delta in differences.values()):
        raise ValueError("Turn terminal-cache profile failed independent replay.")
    if result.get("compatible_world_count") != oracle["world_count"]:
        raise ValueError("Serialized compatible-world count differs from physical replay.")
    if result.get("info_sets") != oracle["checked_information_sets"]:
        raise ValueError("Serialized information-set count differs from independent replay.")
    expected_reachable = list(oracle["river_probabilities"])
    if sorted(result.get("reachable_runouts", [])) != sorted(expected_reachable):
        raise ValueError("Serialized reachable rivers differ from physical replay.")
    if result.get("public_nodes") != oracle["public_node_count"]:
        raise ValueError("Serialized public-decision count differs from independent replay.")
    return oracle, differences


def _profile_evidence(result, oracle, differences, case_id, iterations, profile_kind):
    return {
        "scenario": case_id,
        "profile_kind": profile_kind,
        "iterations": iterations,
        "configured_solver_target_exploitability": None,
        "benchmark_nash_conv_threshold": REPORTING_THRESHOLD,
        "independent_metrics": {field: oracle[field] for field in METRICS},
        "benchmark_nash_conv_threshold_met": oracle["nash_conv"] <= REPORTING_THRESHOLD,
        "scalar_differences": differences,
        "physical_counts": {
            "worlds": oracle["world_count"],
            "compatible_pairs": oracle["compatible_pair_count"],
            "information_sets": oracle["checked_information_sets"],
            "public_nodes": oracle["public_node_count"],
            "reachable_runouts": sorted(oracle["river_probabilities"]),
        },
        "production_counts": {
            "info_sets": result["info_sets"],
            "public_nodes": result["public_nodes"],
            "public_states": result["public_states"],
            "terminal_nodes": result["terminal_nodes"],
            "worlds_materialized": result["worlds_materialized"],
        },
    }


def _policy_name(case_id, iterations, profile_kind):
    return f"{case_id}-matrix-free-cfrplus-{iterations}-{profile_kind}.json"


def _save_and_replay(case_id, iterations, profile_kind, result, case):
    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    path = POLICY_DIR / _policy_name(case_id, iterations, profile_kind)
    raw = _json_bytes(result, pretty=True)
    path.write_bytes(raw)
    digest = _sha256(raw)
    loaded_raw = path.read_bytes()
    if loaded_raw != raw or _sha256(loaded_raw) != digest:
        raise RuntimeError("Saved cache profile bytes failed immediate hash reload.")
    loaded = json.loads(loaded_raw.decode("utf-8"))
    if _json_bytes(loaded) != _json_bytes(result):
        raise RuntimeError("Saved cache profile changed complete-payload content.")
    _validate_profile(loaded, case, iterations,
                      cached=(profile_kind != "baseline-300"))
    oracle, differences = _replay(loaded, case)
    return {
        "policy_file": path.name,
        "policy_sha256": digest,
        "policy_saved_reloaded_and_replayed": True,
        "independent_metrics": {field: oracle[field] for field in METRICS},
        "benchmark_nash_conv_threshold": REPORTING_THRESHOLD,
        "benchmark_nash_conv_threshold_met": oracle["nash_conv"] <= REPORTING_THRESHOLD,
        "scalar_differences": differences,
        "physical_counts": {
            "worlds": oracle["world_count"],
            "compatible_pairs": oracle["compatible_pair_count"],
            "information_sets": oracle["checked_information_sets"],
            "public_nodes": oracle["public_node_count"],
            "reachable_runouts": sorted(oracle["river_probabilities"]),
        },
    }


def _preflight():
    _verify_pinned_inputs()
    source_before = _source_fingerprints()
    rows = []
    for case_id in SCENARIOS:
        case = _case(case_id)
        baseline = _solve(case, 10, cached=False)
        candidate = _solve(case, 10, cached=True)
        _validate_profile(baseline, case, 10, cached=False)
        _validate_profile(candidate, case, 10, cached=True)
        if _json_bytes(baseline) != _json_bytes(_legacy_payload(candidate)):
            raise RuntimeError("10-sweep opt-in profile differs from the complete default payload.")
        oracle, differences = _replay(candidate, case)
        rows.append({
            "scenario": case_id,
            "iterations": 10,
            "default_complete_payload_sha256": _sha256(_json_bytes(baseline)),
            "opt_in_legacy_payload_sha256": _sha256(_json_bytes(_legacy_payload(candidate))),
            "exact_legacy_payload_match": True,
            **_profile_evidence(candidate, oracle, differences, case_id, 10,
                                "short-opt-in-preflight"),
            "cache": candidate["terminal_cache"],
        })
        print(case_id, "10-sweep payload parity/replay passed;",
              f"calls={candidate['terminal_cache']['actual_calls']},",
              f"hits={candidate['terminal_cache']['hits']},",
              f"max_entries={candidate['terminal_cache']['maximum_entries']}", flush=True)
    if _source_fingerprints() != source_before:
        raise RuntimeError("A pinned source or input changed during short preflight.")
    return {
        "status": "passed",
        "source_fingerprints_before_after_equal": True,
        "profiles": rows,
    }


def _exact_selected_3k(candidate, case, pinned):
    board, config, _river_config, worlds, tree, policies = rational_audit._independent_model(
        candidate, case)
    exact = turn_rational_certificate.evaluate_exact(
        tree, worlds, policies, config.pot, result=candidate)
    exact_metrics = {name: str(value) for name, value in exact["metrics"].items()}
    certificate = pinned["rational_3k_row"]
    if exact_metrics != certificate["exact_metrics"]:
        raise ValueError("Selected 3k exact Fraction metrics differ from the archived certificate.")
    normalized_digest = _sha256(_json_bytes(exact["normalized_policy_rows"]))
    if normalized_digest != certificate["normalized_policy_sha256"]:
        raise ValueError("Selected 3k exact normalized policy differs from its archived certificate.")
    if (exact["threshold_met"] is not True or
            exact["lower_value_bound"] != Fraction(
                certificate["lower_value_bound_fraction"]) or
            exact["upper_value_bound"] != Fraction(
                certificate["upper_value_bound_fraction"])):
        raise ValueError("Selected 3k exact threshold/value interval differs from its certificate.")
    return {
        "normalized_policy_sha256": normalized_digest,
        "exact_metrics": exact_metrics,
        "lower_value_bound_fraction": str(exact["lower_value_bound"]),
        "upper_value_bound_fraction": str(exact["upper_value_bound"]),
        "exact_nash_conv_threshold_fraction": "1/1000",
        "exact_nash_conv_threshold_met": True,
        "exact_audit_work": exact["work"],
        "exact_audit_maximum_fraction_bits": exact["maximum_fraction_bits"],
    }


def _load_archived_policy(parent, case_id, iterations):
    row = _parent_accuracy_row(parent, "matrix-free", iterations)
    path = SELECTED_POLICY_DIR / row["policy_file"] if case_id == SELECTED_ID else (
        old_benchmark.PARENTS[case_id]["policy_directory"] / row["policy_file"]
    )
    expected_hash = row["policy_sha256"]
    raw = path.read_bytes()
    if _sha256(raw) != expected_hash:
        raise ValueError("Archived matrix-free complete policy hash changed.")
    return json.loads(raw.decode("utf-8")), row, expected_hash


def _timed_call(case, iterations, *, cached):
    gc.collect()
    started = time.perf_counter()
    result = _solve(case, iterations, cached=cached)
    payload = _json_bytes(result)
    elapsed = time.perf_counter() - started
    return result, payload, elapsed


def _run_paired_calls(case, iterations, orders):
    """Run fixed paired calls and retain first complete result per mode."""
    timing_rows = []
    digests = {mode: set() for mode in ("baseline", "ranked-lru")}
    samples = {mode: [] for mode in digests}
    first_results = {}
    for pair_number, order in enumerate(orders, 1):
        pair_results = {}
        for mode in order:
            result, payload, elapsed = _timed_call(
                case, iterations, cached=(mode == "ranked-lru"))
            digest = _sha256(payload)
            digests[mode].add(digest)
            samples[mode].append(elapsed)
            _validate_profile(result, case, iterations, cached=(mode == "ranked-lru"))
            if mode in first_results:
                if digest != first_results[mode]["sha256"]:
                    raise RuntimeError("A paired full call changed its complete payload.")
            else:
                first_results[mode] = {"result": result, "sha256": digest}
            pair_results[mode] = {
                "result": result,
                "seconds_uncontrolled": elapsed,
                "payload_sha256": digest,
                "cache": result.get("terminal_cache"),
            }
            print(case["id"], f"{iterations}-sweep pair", pair_number, mode,
                  f"{elapsed:.4f}s", f"payload={digest[:12]}", flush=True)
        if (_json_bytes(_legacy_payload(pair_results["ranked-lru"]["result"])) !=
                _json_bytes(pair_results["baseline"]["result"])):
            raise RuntimeError("Paired opt-in payload differs from the complete default payload.")
        timing_rows.append({
            "scenario": case["id"],
            "pair": pair_number,
            "order": list(order),
            "baseline_seconds_uncontrolled": pair_results["baseline"]["seconds_uncontrolled"],
            "ranked_lru_seconds_uncontrolled": pair_results["ranked-lru"]["seconds_uncontrolled"],
            "baseline_over_candidate_ratio": (
                pair_results["baseline"]["seconds_uncontrolled"] /
                pair_results["ranked-lru"]["seconds_uncontrolled"]
            ),
            "baseline_payload_sha256": pair_results["baseline"]["payload_sha256"],
            "ranked_lru_payload_sha256": pair_results["ranked-lru"]["payload_sha256"],
            "cache": pair_results["ranked-lru"]["cache"],
        })
    if any(len(values) != 1 for values in digests.values()):
        raise RuntimeError("Repeated paired calls did not reproduce their payload hashes.")
    return timing_rows, first_results, samples


def run_measurement():
    pinned = _verify_pinned_inputs()
    baseline_commit = _git_commit()
    sources_before = _source_fingerprints()
    cases = {case_id: _case(case_id) for case_id in SCENARIOS}
    preflight = _preflight()
    if _source_fingerprints() != sources_before:
        raise RuntimeError("Source fingerprints changed during warmup.")

    profile_rows = []
    # Fixed 1k archived parity candidates, plus the already-certified selected 3k.
    for case_id in SCENARIOS:
        case = cases[case_id]
        candidate = _solve(case, 1_000, cached=True)
        _validate_profile(candidate, case, 1_000, cached=True)
        archived, parent_row, parent_hash = _load_archived_policy(
            pinned["selected_accuracy_report"] if case_id == SELECTED_ID else
            json.loads(old_benchmark.PARENTS[case_id]["report"].read_text(encoding="utf-8")),
            case_id, 1_000,
        )
        if _json_bytes(_legacy_payload(candidate)) != _json_bytes(archived):
            raise RuntimeError("1k cache candidate differs from pinned complete archived policy.")
        oracle, differences = _replay(candidate, case)
        row = {
            **_profile_evidence(candidate, oracle, differences, case_id, 1_000,
                                "candidate-1000"),
            "archived_policy_sha256": parent_hash,
            "exact_archived_legacy_payload_match": True,
            "cache": candidate["terminal_cache"],
            **_save_and_replay(case_id, 1_000, "candidate-1000", candidate, case),
        }
        profile_rows.append(row)
        print(case_id, "1k candidate exact archived parity/replay passed;",
              f"NashConv={oracle['nash_conv']:.12g}", flush=True)

    selected_case = cases[SELECTED_ID]
    selected_3k = _solve(selected_case, 3_000, cached=True)
    _validate_profile(selected_3k, selected_case, 3_000, cached=True)
    archived_3k_path = SELECTED_POLICY_DIR / SELECTED_3K_POLICY_NAME
    archived_3k = json.loads(archived_3k_path.read_bytes().decode("utf-8"))
    if _json_bytes(_legacy_payload(selected_3k)) != _json_bytes(archived_3k):
        raise RuntimeError("Selected 3k cache profile differs from the pinned complete policy.")
    selected_3k_oracle, selected_3k_differences = _replay(selected_3k, selected_case)
    exact_evidence = _exact_selected_3k(selected_3k, selected_case, pinned)
    profile_rows.append({
        **_profile_evidence(selected_3k, selected_3k_oracle, selected_3k_differences,
                            SELECTED_ID, 3_000, "candidate-3000"),
        "archived_policy_sha256": SELECTED_3K_POLICY_SHA256,
        "exact_archived_legacy_payload_match": True,
        "cache": selected_3k["terminal_cache"],
        "rational_profile_certificate": exact_evidence,
        **_save_and_replay(SELECTED_ID, 3_000, "candidate-3000",
                           selected_3k, selected_case),
    })
    print(SELECTED_ID, "3k candidate exact archived parity/replay and Fraction certificate passed;",
          f"NashConv={selected_3k_oracle['nash_conv']:.12g}", flush=True)

    timing_rows = []
    for case_id, case in cases.items():
        fixture_timings, first_results, samples = _run_paired_calls(
            case, MEASURE_ITERATIONS, PAIRED_ORDERS)
        timing_rows.extend(fixture_timings)
        for mode in ("baseline", "ranked-lru"):
            first = first_results[mode]["result"]
            _validate_profile(first, case, MEASURE_ITERATIONS, cached=(mode == "ranked-lru"))
            oracle, differences = _replay(first, case)
            kind = "baseline-300" if mode == "baseline" else "candidate-300"
            saved = _save_and_replay(case_id, MEASURE_ITERATIONS, kind, first, case)
            profile_rows.append({
                **_profile_evidence(first, oracle, differences, case_id,
                                    MEASURE_ITERATIONS, kind),
                "complete_call_seconds_uncontrolled": samples[mode],
                "complete_call_median_seconds_uncontrolled": statistics.median(samples[mode]),
                "payload_sha256": first_results[mode]["sha256"],
                "cache": first.get("terminal_cache"),
                **saved,
            })

    for case_id in SCENARIOS:
        fixture_rows = [row for row in timing_rows if row["scenario"] == case_id]
        baseline_median = statistics.median(
            row["baseline_seconds_uncontrolled"] for row in fixture_rows)
        candidate_median = statistics.median(
            row["ranked_lru_seconds_uncontrolled"] for row in fixture_rows)
        ratio = baseline_median / candidate_median
        timing_rows.append({
            "scenario": case_id,
            "summary": True,
            "baseline_median_seconds_uncontrolled": baseline_median,
            "ranked_lru_median_seconds_uncontrolled": candidate_median,
            "baseline_over_candidate_median_ratio": ratio,
            "predeclared_runtime_research_gate": 1.10,
            "runtime_research_gate_met": ratio >= 1.10,
        })

    if len([row for row in profile_rows if row.get("policy_saved_reloaded_and_replayed")]) != 7:
        raise RuntimeError("The acceptance artifact must retain exactly seven saved/replayed policies.")
    source_after = _source_fingerprints()
    if source_after != sources_before:
        raise RuntimeError("A pinned source/input changed during cache measurements.")
    if _git_commit() != baseline_commit:
        raise RuntimeError("Repository HEAD changed during cache measurements.")
    report = {
        "schema_version": 1,
        "benchmark_id": "turn-terminal-cache-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_git_commit": baseline_commit,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "current_source_sha256_before_after_equal": True,
        "current_source_sha256": sources_before,
        "pinned_inputs": {
            "selected_accuracy_report_canonical_sha256": SELECTED_PARENT_REPORT_SHA256,
            "selected_3k_policy_sha256": SELECTED_3K_POLICY_SHA256,
            "rational_certificate_report_canonical_sha256": RATIONAL_REPORT_CANONICAL_SHA256,
            "rational_3k_normalized_policy_sha256": RATIONAL_EXPECTED_NORMALIZED_SHA256,
        },
        "methodology": {
            "research_only": True,
            "opt_in_mode": "solve_matrix_free_turn(..., terminal_cache='ranked-lru')",
            "default_mode": "terminal_cache='none'; all legacy fields and complete-policy bytes must match opt-in after removing only terminal_cache metadata",
            "models": "Two frozen matrix-free turn fixtures; selected/full CFR+ fixed sweeps; no convergence target or checkpoint callback.",
            "cache_scope": "Per-solve LRU on private ranked-river branch kernels; only successful zero-fallback calls are cached. Original outer turn kernel and ordinary exact root-fold paths are retained.",
            "admission": "All independent action-tree terminal nodes times (2*T+4), 20 logical slot units per call, plus 16 per branch and 64 fixed setup slots; full requested iterations are reserved before information rows or proxy/cache allocation; 30,000,000 cache slot ceiling.",
            "runtime_accounting": "Cache slot units bound only the declared logical validation/key/copy/LRU work model. They are not Python instruction, CPU, allocator, or RSS bounds.",
            "logical_payload": "At most 655,360 logical bytes for five numeric float slots per entry (two reach, two returned values, matched contribution); Python headers, key-container representation, references, LRU internals, temporaries and allocator overhead are excluded.",
            "preflight": "Both fixtures receive exact 10-sweep default/opt-in complete-payload comparison and independent all-eight-metric replay.",
            "archive_checks": "Both 1k opt-in candidates must match pinned complete legacy payloads exactly; selected 3k must match its pinned full payload and normalized Fraction certificate exactly.",
            "saved_profiles": "Seven complete UTF-8 LF JSON payloads, each byte-hashed, reloaded, and independently replayed across eight metrics and physical counts.",
            "timing": "Three paired 300-sweep complete calls per fixture in baseline/candidate, candidate/baseline, baseline/candidate order. Construction, training, diagnostics, cache cleanup, and result serialization are inside each timer; independent replay and file/hash work are outside. Timings are uncontrolled observations.",
            "runtime_research_gate": "Predeclared reporting gate: median baseline/candidate ratio at least 1.10 in both fixtures. All misses remain in the report; this is not a promotion or default-change gate.",
            "limitations": "Configured heads-up turn/river abstractions only. No general mutable-kernel cache, cross-river reuse, performance guarantee, memory/RSS claim, or unrestricted Hold'em claim.",
        },
        "short_preflight": preflight,
        "profiles": profile_rows,
        "paired_timings": timing_rows,
        "accuracy_misses_retained": True,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(_json_bytes(report, pretty=True))
    print("Saved and replayed cache policies:", 7, flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("preflight", "measure"), default="preflight")
    arguments = parser.parse_args(argv)
    if arguments.phase == "preflight":
        _preflight()
    else:
        run_measurement()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
