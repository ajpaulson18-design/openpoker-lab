"""Research-only parity and paired-call timing for turn terminal memoization.

The default phase is a short 10-sweep parity preflight. The full 1,000/300
measurement phase requires an explicit ``--phase measure`` argument and is not
a production solver or performance claim.
"""
import argparse
import gc
import hashlib
import json
import math
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.benchmark_turn_river_independent import CONFIG, ROOT, solve, source_hashes
from scripts.turn_river_validation import compare_result, replay_policy
from scripts.turn_terminal_memoization import (
    CACHE_SLOTS_PER_CALL,
    MAX_CACHE_ENTRIES,
    MAX_CACHE_SLOT_WORK,
    call_ceiling,
    patched_turn_memoizer,
)


SELECTED_ID = "two-conditioned-runouts-asymmetric-multisize"
FULL_ID = "full44-blocked-runouts"
ITERATION_LIMIT = 1_000
BENCHMARK_NASH_CONV_THRESHOLD = 0.001
PAIRED_ITERATIONS = 300
PAIRS = 3
POLICY_DIR = ROOT / "benchmarks" / "results" / "turn-terminal-memoization-policies-v1"
OUTPUT = ROOT / "benchmarks" / "results" / "turn-terminal-memoization-v1.json"

EXPECTED_CASES = {
    SELECTED_ID: {
        "id": SELECTED_ID,
        "purpose": "Condition jointly on two selected rivers while exercising asymmetric stacks, multiple sizes, raises and all-in actions.",
        "runout_scope": "selected-conditioned-subset",
        "oop": "AsAh:0.5,KsKh:1",
        "ip": "AcAd:1,KcKd:0.75",
        "config": {
            "pot": 100, "effective_stack": [220, 120],
            "bet_sizes": [0.5, 1.0], "raise_sizes": [0.5],
            "max_raises": 1, "include_all_in": True,
        },
        "river_config": {
            "pot": 100, "effective_stack": [220, 120],
            "bet_sizes": [0.75, 1.25], "raise_sizes": [0.5],
            "max_raises": 1, "include_all_in": True,
        },
        "runouts": ["3c", "5h"],
        "board": "Js8d4c2h",
    },
    FULL_ID: {
        "id": FULL_ID,
        "purpose": "Enumerate every river remaining after each compatible pair of private hands on a four-card board using a small no-raise tree.",
        "runout_scope": "all-compatible-runouts",
        "oop": "AsAh:0.5,KsKh:1",
        "ip": "AcAd:1,KcKd:0.75",
        "config": {
            "pot": 100, "effective_stack": 220, "bet_sizes": [0.75],
            "raise_sizes": [], "max_raises": 0, "include_all_in": False,
        },
        "river_config": {
            "pot": 100, "effective_stack": 220, "bet_sizes": [0.75],
            "raise_sizes": [], "max_raises": 0, "include_all_in": False,
        },
        "board": "Js8d4c2h",
    },
}

PARENTS = {
    SELECTED_ID: {
        "report": ROOT / "benchmarks" / "results" / "turn-selected-accuracy-v1.json",
        "report_sha256": "96d53995f45c6f07d43a35ae871fac6ca97c6d9dca6a8de067e8b46e15392b78",
        "policy_sha256": "9392d017c8ac7c8e1328c9e996282192660c65b97d6dd2e248eed3271054ffec",
        "policy_directory": ROOT / "benchmarks" / "results" / "turn-selected-accuracy-policies-v1",
    },
    FULL_ID: {
        "report": ROOT / "benchmarks" / "results" / "full-deck-turn-accuracy-v1.json",
        "report_sha256": "aef2b520593b68b6717adfe677fb5a9c87a362df8ae61816a53d1c930c412b63",
        "policy_sha256": "9da96f3480a41a02cf67141d5f25e41d2b3c43b58f48173b075d9c8d0c19c4d3",
        "policy_directory": ROOT / "benchmarks" / "results" / "full-deck-turn-accuracy-policies-v1",
    },
}

MODEL_SOURCE_PATHS = (
    "pokerlab/cards.py", "pokerlab/cfr.py", "pokerlab/cfr_plus.py",
    "pokerlab/matrix_free_turn.py", "pokerlab/postflop_solver.py",
    "pokerlab/public_cfr.py", "pokerlab/public_diagnostics.py",
    "pokerlab/ranked_river.py", "pokerlab/river_config.py",
    "pokerlab/river_tree.py", "pokerlab/turn_range_kernel.py",
    "benchmarks/turn-river-quality-v1.json",
    "scripts/benchmark_turn_river_independent.py",
    "scripts/preflop_validation.py", "scripts/turn_river_validation.py",
)

METRICS = (
    "value_oop", "value_ip", "oop_best_response_value",
    "ip_best_response_value", "oop_best_response_gain",
    "ip_best_response_gain", "nash_conv", "exploitability",
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


def _source_fingerprints():
    hashes = source_hashes()
    extra_paths = [
        Path(__file__).resolve(),
        Path(__file__).with_name("turn_terminal_memoization.py").resolve(),
        ROOT / "tests" / "test_turn_terminal_memoization.py",
        ROOT / "tests" / "test_benchmark_turn_terminal_memoization.py",
        ROOT / "tests" / "test_turn_terminal_memoization_review.py",
        POLICY_DIR / ".gitattributes",
    ]
    for parent in PARENTS.values():
        extra_paths.extend((parent["report"],))
        baseline = _baseline_row(parent)
        extra_paths.append(parent["policy_directory"] / baseline["policy_file"])
    for path in extra_paths:
        if path.exists():
            hashes[path.resolve().relative_to(ROOT).as_posix()] = _sha256(path.read_bytes())
        else:
            raise ValueError("A pinned benchmark/source file is missing: " + str(path))
    return dict(sorted(hashes.items()))


def _source_bytes_match(path, expected_sha256):
    data = path.read_bytes()
    candidates = {
        _sha256(data),
        _sha256(data.replace(b"\r\n", b"\n")),
        _sha256(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")),
    }
    return expected_sha256 in candidates


def _verify_parent_sources(parent_reports):
    normalized_reports = {}
    for model_id, report in parent_reports.items():
        normalized_reports[model_id] = {
            key.replace("\\", "/"): value
            for key, value in report["source_sha256"].items()
        }
    for path_string in MODEL_SOURCE_PATHS:
        left = normalized_reports[SELECTED_ID].get(path_string)
        right = normalized_reports[FULL_ID].get(path_string)
        if not left or left != right:
            raise ValueError("Pinned parent source dependency differs: " + path_string)
        if not _source_bytes_match(ROOT / Path(path_string), left):
            raise ValueError("Current model dependency differs from pinned parent: " + path_string)


def _baseline_row(parent):
    report = json.loads(parent["report"].read_text(encoding="utf-8"))
    matches = [row for row in report["results"]
               if row.get("backend") == "matrix-free" and
               row.get("algorithm") == "cfrplus" and
               row.get("iterations_completed") == 1_000 and
               row.get("iterations_requested") == 1_000]
    if len(matches) != 1:
        raise ValueError("Pinned parent report must contain exactly one matrix-free 1k profile.")
    return matches[0]


def _frozen_case(case_id):
    if case_id not in EXPECTED_CASES:
        raise ValueError("Unknown memoizer fixture.")
    specification = json.loads(CONFIG.read_text(encoding="utf-8"))
    matches = [case for case in specification["scenarios"]
               if case.get("id") == case_id]
    if len(matches) != 1:
        raise ValueError("The memoizer fixture changed from its frozen canonical model.")
    return _validate_case(matches[0])


def _validate_case(case):
    if not isinstance(case, dict) or case.get("id") not in EXPECTED_CASES:
        raise ValueError("The memoizer accepts only its two frozen fixture objects.")
    case_id = case["id"]
    if _json_bytes(case) != _json_bytes(EXPECTED_CASES[case_id]):
        raise ValueError("The memoizer fixture changed from its frozen canonical model.")
    return case


def _verify_parents():
    reports = {}
    for case_id, parent in PARENTS.items():
        if _canonical_digest(parent["report"]) != parent["report_sha256"]:
            raise ValueError("Pinned parent report canonical hash changed: " + case_id)
        report = json.loads(parent["report"].read_text(encoding="utf-8"))
        row = _baseline_row(parent)
        policy_path = parent["policy_directory"] / row["policy_file"]
        raw = policy_path.read_bytes()
        if _sha256(raw) != parent["policy_sha256"] or row["policy_sha256"] != parent["policy_sha256"]:
            raise ValueError("Pinned parent policy hash changed: " + case_id)
        payload = json.loads(raw.decode("utf-8"))
        if payload.get("iterations") != 1_000 or payload.get("algorithm") != "cfrplus":
            raise ValueError("Pinned parent policy has unexpected solver metadata: " + case_id)
        for field in METRICS:
            report_value = row["metrics"].get(field)
            policy_value = payload.get(field)
            if (isinstance(report_value, bool) or isinstance(policy_value, bool) or
                    not isinstance(report_value, (int, float)) or
                    not isinstance(policy_value, (int, float)) or
                    not math.isfinite(float(report_value)) or
                    not math.isfinite(float(policy_value)) or
                    abs(float(policy_value) - float(report_value)) > 1e-9):
                raise ValueError("Pinned parent report/policy metric differs: " + field)
        _frozen_case(case_id)
        reports[case_id] = report
    _verify_parent_sources(reports)
    return reports


def _replay(result, case):
    options = {key: case[key] for key in ("river_config", "runouts") if key in case}
    oracle = replay_policy(
        result, case["oop"], case["ip"], board=case["board"],
        config=case["config"], **options,
    )
    differences = compare_result(result, oracle, tolerance=1e-9)
    if set(differences) != set(METRICS):
        raise ValueError("Independent replay did not compare all eight required metrics.")
    if any(not math.isfinite(float(value)) or abs(float(value)) > 1e-9
           for value in differences.values()):
        raise ValueError("Memoization candidate failed independent numeric replay.")
    return oracle, differences


def _payload_hash(result):
    return _sha256(_json_bytes(result))


def _solve_baseline(case, iterations):
    return solve(case, "matrix-free", "cfrplus", iterations)


def _solve_memoized(case, iterations):
    # The full requested ceiling is reserved before solver construction or
    # patching; no convergence target or checkpoint callback is supplied.
    with patched_turn_memoizer(case["id"], iterations) as stats:
        result = _solve_baseline(case, iterations)
    serialized_stats = stats.to_dict()
    _validate_memoizer_stats(case, serialized_stats, iterations)
    return result, serialized_stats


def _validate_memoizer_stats(case, stats, iterations):
    """Validate the actual per-solve counters without trusting their types."""
    expected_calls = call_ceiling(case["id"], iterations)
    integer_fields = (
        "inner_values_calls", "cache_hits", "cache_misses", "evictions",
        "output_values_copied", "maximum_entries", "current_entries",
        "entries_before_cleanup", "entries_after_cleanup", "cache_entry_limit",
        "logical_slot_work", "logical_slot_limit", "logical_slots_per_call",
        "reserved_call_ceiling", "logical_payload_bytes_upper_bound",
    )
    if any(type(stats.get(field)) is not int or stats[field] < 0
           for field in integer_fields):
        raise ValueError("Memoizer counters and limits must be nonnegative exact integers.")
    calls = stats["inner_values_calls"]
    if (calls > expected_calls or calls > stats["reserved_call_ceiling"] or
            stats["reserved_call_ceiling"] != expected_calls):
        raise ValueError("Memoizer calls exceed or misstate the full-request reservation.")
    if (stats["logical_slots_per_call"] != CACHE_SLOTS_PER_CALL or
            stats["logical_slot_work"] != calls * CACHE_SLOTS_PER_CALL or
            stats["logical_slot_work"] > stats["logical_slot_limit"] or
            stats["logical_slot_limit"] != MAX_CACHE_SLOT_WORK):
        raise ValueError("Memoizer logical cache-slot work is inconsistent or over cap.")
    if (stats["cache_entry_limit"] != MAX_CACHE_ENTRIES or
            stats["maximum_entries"] > stats["cache_entry_limit"] or
            stats["entries_before_cleanup"] > stats["maximum_entries"] or
            stats["entries_after_cleanup"] != 0 or stats["current_entries"] != 0):
        raise ValueError("Memoizer entry cap or cleanup counters are inconsistent.")
    if (stats["cache_hits"] + stats["cache_misses"] != calls or
            stats["evictions"] > stats["cache_misses"] or
            stats["logical_payload_bytes_upper_bound"] !=
            MAX_CACHE_ENTRIES * 5 * 8):
        raise ValueError("Memoizer hit, miss, eviction or payload counters are inconsistent.")


def _validate_fixed_result(result, case, iterations):
    if (result.get("algorithm") != "cfrplus" or
            type(result.get("iterations")) is not int or
            result.get("iterations") != iterations):
        raise ValueError("Fixed memoization profile did not complete its requested sweeps.")
    if "convergence" in result or "checkpoints" in result:
        raise ValueError("Memoization benchmark unexpectedly used a convergence checkpoint.")
    expected_board = [case["board"][index:index + 2] for index in range(0, 8, 2)]
    if result.get("board") != expected_board:
        raise ValueError("Memoization profile board differs from the frozen fixture.")
    if "runouts" in case and result.get("runouts") != case["runouts"]:
        raise ValueError("Memoization profile river conditioning differs from the fixture.")
    expected_mode = "conditioned-subset" if "runouts" in case else "full-deck"
    if result.get("runout_mode") != expected_mode:
        raise ValueError("Memoization profile runout mode differs from the fixture.")


def _policy_filename(case_id, iterations, mode):
    return f"{case_id}-matrix-free-{iterations}-{mode}.json"


def _independent_profile_fields(oracle):
    return {
        "independent_metrics": {field: oracle[field] for field in METRICS},
        "independent_worlds": oracle["worlds"],
        "checked_information_sets": oracle["checked_information_sets"],
        "benchmark_nash_conv_threshold": BENCHMARK_NASH_CONV_THRESHOLD,
        "benchmark_nash_conv_threshold_met": (
            oracle["nash_conv"] <= BENCHMARK_NASH_CONV_THRESHOLD
        ),
    }


def _save_and_replay(case_id, iterations, mode, result, case):
    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    path = POLICY_DIR / _policy_filename(case_id, iterations, mode)
    raw = _json_bytes(result, pretty=True)
    path.write_bytes(raw)
    digest = _sha256(raw)
    loaded = json.loads(path.read_bytes().decode("utf-8"))
    if _json_bytes(loaded) != _json_bytes(result):
        raise RuntimeError("Saved memoization profile changed complete-payload content.")
    oracle, differences = _replay(loaded, case)
    return {
        "policy_file": path.name,
        "policy_sha256": digest,
        "saved_policy_replayed": True,
        "saved_policy_metrics": {field: oracle[field] for field in METRICS},
        **_independent_profile_fields(oracle),
        "scalar_differences": differences,
    }


def _preflight():
    parent_reports = _verify_parents()
    fingerprints = _source_fingerprints()
    rows = []
    for case_id in (SELECTED_ID, FULL_ID):
        case = _frozen_case(case_id)
        baseline = _solve_baseline(case, 10)
        candidate, stats = _solve_memoized(case, 10)
        _validate_fixed_result(baseline, case, 10)
        _validate_fixed_result(candidate, case, 10)
        if _json_bytes(baseline) != _json_bytes(candidate):
            raise RuntimeError("10-sweep memoized output differs from the unwrapped complete payload.")
        oracle, differences = _replay(candidate, case)
        row = {
            "scenario": case_id,
            "iterations": 10,
            "baseline_payload_sha256": _payload_hash(baseline),
            "candidate_payload_sha256": _payload_hash(candidate),
            "exact_complete_payload_match": True,
            "inner_call_ceiling": call_ceiling(case_id, 10),
            "memoizer": stats,
            "independent_worlds": oracle["worlds"],
            "checked_information_sets": oracle["checked_information_sets"],
            "scalar_differences": differences,
        }
        rows.append(row)
        print(case_id, "10-sweep exact payload parity passed;",
              f"calls={stats['inner_values_calls']}, hits={stats['cache_hits']},",
              f"entries={stats['maximum_entries']}", flush=True)
    if _source_fingerprints() != fingerprints:
        raise RuntimeError("Source or pinned input changed during short preflight.")
    return {
        "preflight": "passed",
        "pinned_parent_report_hashes": {
            case_id: PARENTS[case_id]["report_sha256"] for case_id in PARENTS
        },
        "parent_report_count": len(parent_reports),
        "source_sha256_before_after_equal": True,
        "profiles": rows,
    }


def _timed_call(case, iterations, mode):
    gc.collect()
    started = time.perf_counter()
    if mode == "baseline":
        result = _solve_baseline(case, iterations)
        stats = None
    else:
        result, stats = _solve_memoized(case, iterations)
    payload = _json_bytes(result)
    elapsed = time.perf_counter() - started
    return result, payload, elapsed, stats


def run_measurement():
    parent_reports = _verify_parents()
    before = _source_fingerprints()
    cases = {case_id: _frozen_case(case_id) for case_id in (SELECTED_ID, FULL_ID)}

    # Explicit, unmeasured warmups. The exact payload comparisons here are the
    # short parity preflight requested before any longer measured calls.
    warmup = _preflight()
    if _source_fingerprints() != before:
        raise RuntimeError("Source hashes changed during memoization warmup.")

    rows = []
    for case_id, case in cases.items():
        parent = PARENTS[case_id]
        baseline_row = _baseline_row(parent)
        baseline_path = parent["policy_directory"] / baseline_row["policy_file"]
        archived_baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        candidate, candidate_stats = _solve_memoized(case, 1_000)
        _validate_fixed_result(candidate, case, 1_000)
        if _json_bytes(candidate) != _json_bytes(archived_baseline):
            raise RuntimeError("1k memoized policy differs from the pinned archived complete payload.")
        candidate_oracle, candidate_differences = _replay(candidate, case)
        baseline_oracle, baseline_differences = _replay(archived_baseline, case)
        candidate_save = _save_and_replay(case_id, 1_000, "memoized", candidate, case)
        row = {
            "scenario": case_id,
            "iterations": 1_000,
            "profile_kind": "memoized-candidate",
            "configured_solver_target_exploitability": None,
            "parent_report_canonical_sha256": parent["report_sha256"],
            "parent_policy_sha256": parent["policy_sha256"],
            "candidate_payload_sha256": _payload_hash(candidate),
            "exact_archived_payload_match": True,
            **_independent_profile_fields(candidate_oracle),
            "scalar_differences": candidate_differences,
            "archived_policy_scalar_differences": baseline_differences,
            "memoizer": candidate_stats,
            **candidate_save,
        }
        rows.append(row)
        print(case_id, "1k candidate exact archived parity and independent replay passed",
              f"NashConv={candidate_oracle['nash_conv']:.12g}", flush=True)

    timing_rows = []
    order = (("baseline", "memoized"), ("memoized", "baseline"),
             ("baseline", "memoized"))
    for case_id, case in cases.items():
        payload_hashes = {mode: set() for mode in ("baseline", "memoized")}
        samples = {mode: [] for mode in ("baseline", "memoized")}
        mode_stats = {mode: [] for mode in ("baseline", "memoized")}
        first_results = {}
        for pair_index, pair_order in enumerate(order, 1):
            pair_results = {}
            for mode in pair_order:
                result, payload, seconds, stats = _timed_call(case, PAIRED_ITERATIONS, mode)
                digest = _sha256(payload)
                payload_hashes[mode].add(digest)
                samples[mode].append(seconds)
                if stats is not None:
                    mode_stats[mode].append(stats)
                if mode in first_results and first_results[mode]["sha256"] != digest:
                    raise RuntimeError("Repeated paired profile changed complete-payload hash.")
                if mode not in first_results:
                    first_results[mode] = {"result": result, "sha256": digest}
                    _replay(result, case)
                    _validate_fixed_result(result, case, PAIRED_ITERATIONS)
                pair_results[mode] = {"seconds": seconds, "payload_sha256": digest,
                                      "memoizer": stats}
                print(case_id, "pair", pair_index, mode,
                      f"{seconds:.4f}s", f"payload={digest[:12]}", flush=True)
            ratio = pair_results["baseline"]["seconds"] / pair_results["memoized"]["seconds"]
            timing_rows.append({
                "scenario": case_id,
                "pair": pair_index,
                "order": list(pair_order),
                "baseline_seconds_uncontrolled": pair_results["baseline"]["seconds"],
                "memoized_seconds_uncontrolled": pair_results["memoized"]["seconds"],
                "baseline_over_candidate_ratio": ratio,
                "baseline_payload_sha256": pair_results["baseline"]["payload_sha256"],
                "memoized_payload_sha256": pair_results["memoized"]["payload_sha256"],
                "memoizer": pair_results["memoized"]["memoizer"],
            })
        if any(len(payload_hashes[mode]) != 1 for mode in payload_hashes):
            raise RuntimeError("Three paired repeats did not reproduce one payload hash per mode.")

        for mode in ("baseline", "memoized"):
            result = first_results[mode]["result"]
            saved = _save_and_replay(case_id, PAIRED_ITERATIONS,
                                     "baseline" if mode == "baseline" else "memoized",
                                     result, case)
            row = {
                "scenario": case_id,
                "iterations": PAIRED_ITERATIONS,
                "profile_kind": mode,
                "configured_solver_target_exploitability": None,
                "payload_sha256": first_results[mode]["sha256"],
                "complete_call_seconds_uncontrolled": samples[mode],
                "complete_call_median_seconds_uncontrolled": statistics.median(samples[mode]),
                "memoizer_samples": mode_stats[mode],
                **saved,
            }
            rows.append(row)

    for case_id in (SELECTED_ID, FULL_ID):
        group = [row for row in timing_rows if row["scenario"] == case_id]
        baseline_median = statistics.median(
            row["baseline_seconds_uncontrolled"] for row in group
        )
        candidate_median = statistics.median(
            row["memoized_seconds_uncontrolled"] for row in group
        )
        ratio = baseline_median / candidate_median
        timing_rows.append({
            "scenario": case_id,
            "summary": True,
            "baseline_median_seconds_uncontrolled": baseline_median,
            "memoized_median_seconds_uncontrolled": candidate_median,
            "baseline_over_candidate_median_ratio": ratio,
            "runtime_research_gate": 1.10,
            "runtime_research_gate_met": ratio >= 1.10,
        })

    if _source_fingerprints() != before:
        raise RuntimeError("Source/archive fingerprints changed during memoization measurements.")
    report = {
        "schema_version": 1,
        "benchmark_id": "turn-terminal-memoization-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_git_commit": "b08f264fde392af18ad4a3b7c5b97ee106dbed1e",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "source_sha256_before_after_equal": True,
        "source_sha256": before,
        "pinned_parent_reports": {
            case_id: {
                "canonical_sha256": PARENTS[case_id]["report_sha256"],
                "matrix_free_1k_policy_sha256": PARENTS[case_id]["policy_sha256"],
            } for case_id in PARENTS
        },
        "methodology": {
            "research_only": True,
            "experimental_execution_mode": (
                "Per-solve context-managed subclasses of matrix_free_turn.TurnRangePayoffs "
                "and turn_range_kernel.RankedRiverPayoffs; original evaluator/trainer/math unchanged."
            ),
            "fixed_profiles": "Matrix-free CFR+ only; 1,000-sweep exact archived parity candidates and three paired 300-sweep complete calls per fixture.",
            "memoizer_scope": "Two canonical pinned fixtures, at most two hands per side, at most 48 branches, one per-solve LRU capped at 16,384 entries; only successful zero-fallback inner calls are cached.",
            "cache_slot_model": "20 logical slot units are charged before each inner call; full conservative call ceiling is admitted before patching/construction. This is not a Python instruction, CPU, RSS or allocated-memory bound.",
            "call_bound": "Independent numeric tree terminal counts times (2*requested iterations+4) as a conservative ceiling; actual observed calls must not exceed it.",
            "numeric_payload": "At most 655,360 logical numeric payload bytes at the entry cap, excluding object headers, references, LRU internals, fixed key fields, temporary copies and allocator overhead; no memory/RSS claim.",
            "timing": "Three paired 300-sweep full calls per fixture in AB/BA/AB order; construction, training, exact diagnostics, result serialization and memoizer cleanup included. Warmup 10-sweep parity calls are unmeasured. Shared-host timings are uncontrolled observations.",
            "runtime_gate": "Predeclared shape-specific median baseline/candidate ratio >=1.10 in BOTH fixtures; misses retained and do not imply a production optimization.",
            "correctness": "Candidate 1k payloads must exactly equal the pinned complete archived payloads. All six saved profiles are hash/reload checked and replayed by the independent physical turn validator across all eight metrics.",
            "limitations": "No production API change, default change, general mutable-kernel cache, cross-river reuse, memory gain, or unrestricted Hold'em claim.",
        },
        "short_preflight": warmup,
        "profiles": rows,
        "paired_timings": timing_rows,
        "all_accuracy_misses_retained": True,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(_json_bytes(report, pretty=True))
    print("Verified and saved memoization profiles:", len(rows), flush=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("preflight", "measure"), default="preflight")
    args = parser.parse_args(argv)
    if args.phase == "preflight":
        _preflight()
    else:
        run_measurement()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
