"""Frozen cold-preparation and warm-reweight evidence for direct flop equity counts.

The complete physical count table is prepared once. All four 4,000-iteration
resource preflights finish before any physical board ranking or independent
oracle enumeration starts. Warm calls are instrumented to reject all ranking.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import platform
import statistics
import subprocess
import time
import tracemalloc
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

from pokerlab.cards import expand_range
from pokerlab.flop_checkdown_equity import (
    prepare_flop_checkdown_equities,
    reweight_flop_checkdown_equities,
)
from pokerlab.flop_checkdown_solver import (
    solve_flop_checkdown,
    solve_prepared_flop_checkdown,
)
from pokerlab import flop_checkdown_worlds as worlds_module
from pokerlab.flop_checkdown_worlds import FlopCheckdownPlan
from scripts.benchmark_flop_weighted_eight_hand import preflight
from scripts.flop_checkdown_validation import prepare_oracle, replay

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "benchmarks/flop-equity-reuse-v1.json"
OUTPUT_PATH = ROOT / "benchmarks/results/flop-equity-reuse-v1.json"
LIVE_PATH = ROOT.parent / "flop-equity-reuse-live.json"
EXPECTED_BASELINE = "8b06547beb0db2468af52730dd80a7ba02d6fc71"
EXPECTED_SPEC_SHA256 = "5983f14bd04225aba16300a2b464ee25c9d334376b76924fae74cd38c26ff79c"
EXPECTED_FIXTURES = (
    ("base-8x8-stack12-raises1", "base_oop_range", "base_ip_range", 12, 1,
     58, 114_840, "1185/64", 1185),
    ("base-8x8-stack24-raises2", "base_oop_range", "base_ip_range", 24, 2,
     58, 114_840, "1185/64", 1185),
    ("reversed-weights-8x8-stack24-raises2", "reversed_oop_range", "reversed_ip_range", 24, 2,
     58, 114_840, "1195/64", 1195),
    ("subset-4x4-stack12-raises1", "subset_oop_range", "subset_ip_range", 12, 1,
     15, 29_700, "49/8", 392),
)
HISTORICAL_COMMIT = "8b06547beb0db2468af52730dd80a7ba02d6fc71"
HISTORICAL_PATH = "benchmarks/results/flop-weighted-eight-hand-v1.json"
HISTORICAL_BLOB = "610ac4e8d272db495936119c60f731b7a1061032"


def _canonical_hash(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _sha_file(path):
    raw = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def _source_paths():
    paths = {path.relative_to(ROOT).as_posix() for path in (ROOT / "pokerlab").glob("*.py")}
    paths.update({
        "AGENTS.md",
        "scripts/preflop_validation.py",
        "scripts/flop_checkdown_validation.py",
        "scripts/benchmark_flop_weighted_eight_hand.py",
        "scripts/benchmark_flop_equity_reuse.py",
        "benchmarks/flop-equity-reuse-v1.json",
        "benchmarks/flop-weighted-eight-hand-v1.json",
        "tests/test_flop_checkdown_equity.py",
        "tests/test_flop_checkdown_solver.py",
        "tests/test_flop_checkdown_worlds.py",
        "tests/test_flop_equity_reuse_benchmark.py",
        "tests/test_flop_weighted_eight_hand.py",
    })
    return tuple(sorted(paths))


def _hashes():
    return {path: _sha_file(path) for path in _source_paths()}


def _revision():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _status():
    return subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")
    temp.replace(path)


def _ranges(spec, fixture):
    return (spec[fixture["oop_range"]], spec[fixture["ip_range"]])


def _case(spec, fixture):
    oop_range, ip_range = _ranges(spec, fixture)
    return {"id": fixture["id"], "board": spec["board"],
            "oop_range": oop_range, "ip_range": ip_range,
            "config": {"pot": 6, "effective_stack": fixture["effective_stack"],
                       "bet_sizes": [0.5, 1], "raise_sizes": [0.5],
                       "max_raises": fixture["max_raises"], "include_all_in": True},
            "target_nash_conv": spec["target_nash_conv"]}


def _independent_pair_census(board, oop_range, ip_range):
    """Exact blocker-conditioned weights from the represented input floats."""
    expanded = [expand_range(text, board) for text in (oop_range, ip_range)]
    products = []
    for i, (oop_hand, oop_weight) in enumerate(expanded[0].items()):
        for j, (ip_hand, ip_weight) in enumerate(expanded[1].items()):
            if set(oop_hand).isdisjoint(ip_hand):
                products.append((i, j, oop_hand, ip_hand,
                                 Fraction.from_float(oop_weight) * Fraction.from_float(ip_weight)))
    normalizer = sum((row[4] for row in products), Fraction())
    if normalizer <= 0:
        raise ValueError("Fixture has no positive compatible pair mass")
    return expanded, products, normalizer


def validate_spec(spec):
    if not isinstance(spec, dict) or spec.get("schema_version") != 1:
        raise ValueError("Unsupported flop equity reuse specification")
    if _canonical_hash(spec) != EXPECTED_SPEC_SHA256:
        raise ValueError("Frozen specification hash changed")
    if (spec.get("benchmark_id") != "flop-equity-reuse-v1"
            or spec.get("baseline_main") != EXPECTED_BASELINE
            or spec.get("algorithm") != "cfrplus"
            or spec.get("iterations") != 4000
            or spec.get("timed_repeats") != 3
            or spec.get("allocation_iterations") != 4000
            or spec.get("target_nash_conv") != 0.005
            or spec.get("target_padding") != 1e-9
            or spec.get("scalar_tolerance") != 1e-10
            or spec.get("board") != "2c3c4d"):
        raise ValueError("Frozen benchmark id, solver settings, or gate changed")
    if spec.get("historical_count_source") != {
            "commit": HISTORICAL_COMMIT, "path": HISTORICAL_PATH, "blob": HISTORICAL_BLOB}:
        raise ValueError("Pinned historical physical-count source changed")
    fixtures = spec.get("fixtures")
    if not isinstance(fixtures, list) or len(fixtures) != len(EXPECTED_FIXTURES):
        raise ValueError("Frozen fixture set changed")
    for fixture, expected in zip(fixtures, EXPECTED_FIXTURES):
        (fixture_id, oop_key, ip_key, stack, raises, pair_count, worlds,
         normalizer_text, units) = expected
        if (fixture.get("id") != fixture_id or fixture.get("oop_range") != oop_key
                or fixture.get("ip_range") != ip_key
                or fixture.get("effective_stack") != stack
                or fixture.get("max_raises") != raises
                or fixture.get("expected_compatible_pairs") != pair_count
                or fixture.get("expected_ordered_worlds") != worlds
                or fixture.get("expected_normalizer") != normalizer_text
                or fixture.get("expected_normalizer_units") != units):
            raise ValueError(f"Frozen fixture definition changed: {fixture_id}")
        oop_range, ip_range = _ranges(spec, fixture)
        expanded, pairs, normalizer = _independent_pair_census(spec["board"], oop_range, ip_range)
        if len(expanded[0]) * len(expanded[1]) != (64 if pair_count == 58 else 16):
            raise ValueError(f"Unexpected candidate hand support in {fixture_id}")
        if len(pairs) != pair_count or normalizer != Fraction(units, 64):
            raise ValueError(f"Independent exact pair census mismatch in {fixture_id}")
        if worlds != pair_count * 1980:
            raise ValueError(f"Physical outcome count changed in {fixture_id}")
    if spec.get("expected_pair_census") != {
            "base_candidates": 64, "base_compatible_pairs": 58,
            "base_ordered_worlds": 114840, "base_unordered_boards": 57420,
            "base_normalizer": "1185/64", "base_normalizer_units": 1185,
            "reversed_normalizer": "1195/64", "reversed_normalizer_units": 1195,
            "subset_candidates": 16, "subset_compatible_pairs": 15,
            "subset_ordered_worlds": 29700, "subset_unordered_boards": 14850,
            "subset_normalizer": "49/8", "subset_normalizer_units": 392}:
        raise ValueError("Frozen independent pair census changed")
    return True


def _historical_counts():
    actual_blob = subprocess.check_output(
        ["git", "rev-parse", f"{HISTORICAL_COMMIT}:{HISTORICAL_PATH}"],
        cwd=ROOT, text=True).strip()
    if actual_blob != HISTORICAL_BLOB:
        raise ValueError("Pinned PR130 benchmark blob identity mismatch")
    raw = subprocess.check_output(["git", "show", f"{HISTORICAL_COMMIT}:{HISTORICAL_PATH}"], cwd=ROOT)
    report = json.loads(raw)
    found = None
    for fixture in report.get("results", []):
        if fixture.get("fixture_id") == "weighted-8x8-stack12-raises1":
            found = fixture.get("oracle_pair_counts")
            break
    if not isinstance(found, list) or len(found) != 58:
        raise ValueError("Pinned historical report lacks the expected 58 pair counts")
    return found


def _rows_by_hand(table):
    result = {}
    for (i, j, prior), counts in zip(table.pairs, table.counts):
        key = ("".join(table.hands[0][i]), "".join(table.hands[1][j]))
        result[key] = {"wins": counts[0], "ties": counts[1], "losses": counts[2],
                       "ordered_outcomes": 1980, "pair_probability": float(prior)}
    return result


def _verify_exact_priors(table, board, oop_range, ip_range, expected_normalizer):
    _, products, normalizer = _independent_pair_census(board, oop_range, ip_range)
    if normalizer != Fraction(expected_normalizer):
        raise AssertionError("Independent represented-weight normalizer differs from fixed spec")
    expected = {(oop, ip): weight / normalizer for _, _, oop, ip, weight in products}
    actual = {(table.hands[0][i], table.hands[1][j]): prior for i, j, prior in table.pairs}
    if actual != expected:
        raise AssertionError("Prepared table exact joint priors differ from independent blocker census")

def _verify_table_against_rows(table, rows):
    actual = _rows_by_hand(table)
    expected = {(row["oop_hand"], row["ip_hand"]): {
        "wins": row["wins"], "ties": row["ties"], "losses": row["losses"],
        "ordered_outcomes": row["ordered_outcomes"]} for row in rows}
    if set(actual) != set(expected):
        raise AssertionError("Physical compatible-pair identity differs from independent counts")
    for key, values in expected.items():
        if any(actual[key][name] != values[name] for name in ("wins", "ties", "losses", "ordered_outcomes")):
            raise AssertionError(f"Physical W/T/L count mismatch for {key}")
    return actual


def _guard_warm_rank_calls(fn):
    calls = {"rank_hand": 0, "combinations": 0, "plan_build": 0}
    def forbidden(name):
        def call(*args, **kwargs):
            calls[name] += 1
            raise AssertionError(f"Warm path unexpectedly called {name}")
        return call
    with patch.object(worlds_module, "rank_hand", forbidden("rank_hand")), \
         patch.object(worlds_module, "combinations", forbidden("combinations")), \
         patch.object(FlopCheckdownPlan, "build", forbidden("plan_build")):
        result = fn()
    if calls != {"rank_hand": 0, "combinations": 0, "plan_build": 0}:
        raise AssertionError(f"Warm rank guard count changed: {calls}")
    return result, calls


def _serialize(result):
    return json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _time_fresh(case):
    started = time.perf_counter()
    result = solve_flop_checkdown(case["board"], case["oop_range"], case["ip_range"],
                                  config=case["config"], iterations=4000, algorithm="cfrplus")
    payload = _serialize(result)
    return result, payload, time.perf_counter() - started


def _time_warm(table, case):
    def run_call():
        cached = reweight_flop_checkdown_equities(table, case["oop_range"], case["ip_range"])
        result = solve_prepared_flop_checkdown(cached, config=case["config"],
                                               iterations=4000, algorithm="cfrplus")
        payload = _serialize(result)
        return cached, result, payload
    started = time.perf_counter()
    (cached, result, payload), guards = _guard_warm_rank_calls(run_call)
    return cached, result, payload, time.perf_counter() - started, guards


def _without_preparation(result):
    copy = dict(result)
    copy.pop("equity_preparation", None)
    return copy


def _verify_result(result, oracle, spec, fixture, expected_budget):
    if result.get("work_budget") != expected_budget:
        raise AssertionError("Measured solver work budget differs from the prebuild census")
    replayed = replay(result, oracle, spec["scalar_tolerance"])
    target_met = replayed["nash_conv"] + spec["target_padding"] <= spec["target_nash_conv"]
    return {"replay": replayed, "target_met": target_met,
            "target_limit_with_padding": spec["target_nash_conv"],
            "work_budget_matches_preflight": True}


def _fixture_budget(preflight_row):
    if preflight_row.get("status") != "admitted" or preflight_row.get("ranking_started") is not False:
        raise AssertionError("Required 4,000-iteration fixture preflight failed")
    return preflight_row["solver_budget"]


def _run_frozen(spec=None):
    if spec is None:
        spec = json.loads(SPEC_PATH.read_text(encoding="utf-8-sig"))
    validate_spec(spec)
    if _status():
        raise RuntimeError("Freeze and commit the benchmark source/config before measurement")
    revision = _revision()
    if subprocess.run(["git", "merge-base", "--is-ancestor", spec["baseline_main"], revision],
                      cwd=ROOT, check=False).returncode:
        raise ValueError("Prepared-equity benchmark baseline is not an ancestor")
    before = _hashes()
    status_before = _status()
    live = {"benchmark_id": spec["benchmark_id"], "source_revision": revision,
            "phase": "starting", "complete": False, "preflights": [], "results": []}
    _atomic_json(LIVE_PATH, live)

    # Resource census for every fixed configuration precedes any table/oracle ranking.
    cases = [_case(spec, fixture) for fixture in spec["fixtures"]]
    preflights = []
    for case in cases:
        row = preflight(case, spec["iterations"], spec["algorithm"])
        row["fixture_id"] = case["id"]
        preflights.append(row)
        live["preflights"] = preflights[:]
        _atomic_json(LIVE_PATH, live)
    if len(preflights) != 4 or any(row.get("status") != "admitted" for row in preflights):
        if _hashes() != before or _revision() != revision or _status() != status_before:
            raise RuntimeError("Frozen source changed during no-ranking preflight")
        report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
                  "source_revision": revision, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                  "specification_sha256": _canonical_hash(spec), "source_hashes_lf_normalized": before,
                  "worktree_clean_at_start_and_before_publication": True,
                  "specification": spec, "preflights_complete_before_ranking": True,
                  "preflights": preflights, "results": [], "ranking_started": False,
                  "acceptance_gate_met": False, "quality_misses": [],
                  "rejection_scope": "Preflight rejection is preserved; no oracle ranking or training ran.",
                  "artifact_sha256": ""}
        report["artifact_sha256"] = _canonical_hash({k: v for k, v in report.items() if k != "artifact_sha256"})
        _atomic_json(OUTPUT_PATH, report)
        live.update({"phase": "preflight-rejected", "complete": True,
                     "known_resource_failures": preflights, "report": OUTPUT_PATH.as_posix()})
        _atomic_json(LIVE_PATH, live)
        raise AssertionError("One or more required 4,000-iteration preflights rejected; no ranking was started")

    base_case = cases[0]
    live["phase"] = "cold-source-preparation"
    _atomic_json(LIVE_PATH, live)
    gc.collect()
    started = time.perf_counter()
    source_table = prepare_flop_checkdown_equities(
        spec["board"], base_case["oop_range"], base_case["ip_range"])
    cold_seconds = time.perf_counter() - started
    source_table.validate()
    _verify_exact_priors(source_table, spec["board"], base_case["oop_range"],
                         base_case["ip_range"], "1185/64")
    if (len(source_table.pairs) != 58 or source_table.budget["physical_worlds"] != 114840
            or source_table.budget["unordered_boards"] != 57420):
        raise AssertionError("Cold source table shape differs from the fixed physical census")

    historical = _historical_counts()
    historical_by_key = {(r["oop_hand"], r["ip_hand"]): r for r in historical}
    source_counts = _rows_by_hand(source_table)
    if set(source_counts) != set(historical_by_key):
        raise AssertionError("Prepared source table differs from pinned PR130 pair identities")
    for key, row in historical_by_key.items():
        actual = source_counts[key]
        if any(actual[field] != row[field] for field in ("wins", "ties", "losses", "ordered_outcomes")):
            raise AssertionError(f"Prepared counts differ from pinned PR130 row {key}")

    failures = []
    results = []
    for case, fixture, admission in zip(cases, spec["fixtures"], preflights):
        live.update({"phase": "independent-oracle", "active_fixture": case["id"]})
        _atomic_json(LIVE_PATH, live)
        oracle = prepare_oracle(case["board"], case["oop_range"], case["ip_range"], case["config"])
        oracle_counts = oracle.get("counts", [])
        expected_pairs = fixture["expected_compatible_pairs"]
        if len(oracle_counts) != expected_pairs or sum(r["ordered_outcomes"] for r in oracle_counts) != fixture["expected_ordered_worlds"]:
            raise AssertionError(f"Independent oracle physical census mismatch for {case['id']}")
        if case["id"] == cases[0]["id"]:
            _verify_table_against_rows(source_table, oracle_counts)
        cached = reweight_flop_checkdown_equities(source_table, case["oop_range"], case["ip_range"])
        cached.validate()
        _verify_exact_priors(cached, case["board"], case["oop_range"],
                             case["ip_range"], fixture["expected_normalizer"])
        _verify_table_against_rows(cached, oracle_counts)
        if (len(cached.pairs) != expected_pairs
                or cached.budget["physical_worlds"] != fixture["expected_ordered_worlds"]):
            raise AssertionError(f"Reweighted table support differs from spec for {case['id']}")
        expected_budget = _fixture_budget(admission)

        # Run the three declared paired calls, alternating which arm goes first.
        fresh_records, warm_records = [], []
        for repeat in range(spec["timed_repeats"]):
            live.update({"phase": "timing", "active_fixture": case["id"],
                         "repeat": repeat + 1, "repeat_total": spec["timed_repeats"]})
            _atomic_json(LIVE_PATH, live)
            if repeat % 2 == 0:
                fresh = _time_fresh(case)
                warm = _time_warm(source_table, case)
            else:
                warm = _time_warm(source_table, case)
                fresh = _time_fresh(case)
            fresh_result, fresh_json, fresh_seconds = fresh
            cached_result, warm_result, warm_json, warm_seconds, rank_guards = warm
            if _without_preparation(warm_result) != fresh_result:
                raise AssertionError(f"Fresh/prepared serialized result mismatch for {case['id']} repeat {repeat+1}")
            if fresh_result.get("work_budget") != expected_budget or warm_result.get("work_budget") != expected_budget:
                raise AssertionError(f"Measured work budget differs from preflight for {case['id']}")
            if warm_result.get("equity_preparation") != {
                    "mode": "prepared-counts", "current_rank_calls": 0,
                    "current_unordered_board_evaluations": 0,
                    "source_inclusive_admission": True,
                    "validation": "Structural consistency only; supplied counts require trusted provenance."}:
                raise AssertionError("Prepared solver metadata changed")
            fresh_verification = _verify_result(fresh_result, oracle, spec, fixture, expected_budget)
            warm_verification = _verify_result(warm_result, oracle, spec, fixture, expected_budget)
            if fresh_verification["replay"] != warm_verification["replay"]:
                raise AssertionError("Independent replay differs between identical serialized payloads")
            if not fresh_verification["target_met"] or not warm_verification["target_met"]:
                failures.append({"fixture_id": case["id"], "repeat": repeat + 1,
                                 "fresh_target_met": fresh_verification["target_met"],
                                 "prepared_target_met": warm_verification["target_met"],
                                 "fresh_nash_conv": fresh_verification["replay"]["nash_conv"],
                                 "prepared_nash_conv": warm_verification["replay"]["nash_conv"]})
            print(f"{case['id']} repeat={repeat+1}/3 fresh={fresh_seconds:.6f}s warm={warm_seconds:.6f}s", flush=True)
            fresh_records.append({"repeat": repeat + 1, "complete_solve_plus_json_seconds": fresh_seconds,
                                  "payload_sha256": hashlib.sha256(fresh_json.encode()).hexdigest(),
                                  "work_budget_matches_preflight": fresh_result["work_budget"] == expected_budget,
                                  "verification": fresh_verification})
            comparison_json = _serialize(_without_preparation(warm_result))
            warm_records.append({"repeat": repeat + 1, "reweight_solve_plus_json_seconds": warm_seconds,
                                 "complete_payload_sha256": hashlib.sha256(warm_json.encode()).hexdigest(),
                                 "comparison_payload_sha256": hashlib.sha256(comparison_json.encode()).hexdigest(),
                                 "comparison_payload_matches_fresh": comparison_json == fresh_json,
                                 "verification": warm_verification, "ranking_guards": rank_guards,
                                 "work_budget_matches_preflight": warm_result["work_budget"] == expected_budget,
                                 "pair_rows_match_fresh": cached_result.counts == tuple(
                                     (r["wins"], r["ties"], r["losses"]) for r in fresh_result["pair_equities"])})
            if not warm_records[-1]["pair_rows_match_fresh"]:
                raise AssertionError("Cached W/T/L rows differ from fresh solver pair rows")
        if len({r["payload_sha256"] for r in fresh_records}) != 1 or len({r["complete_payload_sha256"] for r in warm_records}) != 1:
            raise AssertionError(f"Repeated payload is nondeterministic for {case['id']}")
        if any(not row["comparison_payload_matches_fresh"] for row in warm_records):
            raise AssertionError("Fresh/prepared payloads differ after removing only equity_preparation")
        if any(row["comparison_payload_sha256"] != fresh_records[0]["payload_sha256"] for row in warm_records):
            raise AssertionError("Fresh/prepared parity payload hashes differ")

        results.append({"fixture_id": case["id"], "physical_pair_count": len(oracle_counts),
                        "physical_ordered_worlds": sum(r["ordered_outcomes"] for r in oracle_counts),
                        "preflight": admission, "fresh_calls": fresh_records,
                        "prepared_calls": warm_records,
                        "fresh_median_seconds": statistics.median(r["complete_solve_plus_json_seconds"] for r in fresh_records),
                        "prepared_median_seconds": statistics.median(r["reweight_solve_plus_json_seconds"] for r in warm_records),
                        "oracle_pair_counts": [{k: row[k] for k in ("oop_hand", "ip_hand", "wins", "ties", "losses", "ordered_outcomes")}
                                               for row in oracle_counts],
                        "work_budget_matches_preflight": all(
                            call.get("work_budget_matches_preflight", False) for call in fresh_records + warm_records)})
        live["results"] = results[:]
        _atomic_json(LIVE_PATH, live)
        del oracle, cached

    # A separate whole-call Python allocation trace excludes the cached source table and oracle.
    allocation_case = cases[1]
    live.update({"phase": "allocation-trace", "active_fixture": allocation_case["id"]})
    _atomic_json(LIVE_PATH, live)
    print(f"starting allocation trace for {allocation_case['id']}", flush=True)
    gc.collect()
    tracemalloc.start()
    try:
        cached, allocation_result, allocation_json, allocation_seconds, allocation_guards = _time_warm(
            source_table, allocation_case)
        _, allocation_peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    allocation_comparison_json = _serialize(_without_preparation(allocation_result))
    reference_warm = results[1]["prepared_calls"][0]
    if hashlib.sha256(allocation_comparison_json.encode()).hexdigest() != reference_warm["comparison_payload_sha256"]:
        raise AssertionError("Allocation call profile differs from the independently verified prepared call")
    allocation = {"fixture_id": allocation_case["id"], "iterations": 4000,
                  "reweight_solve_plus_json_seconds_under_tracemalloc": allocation_seconds,
                  "traced_peak_bytes": allocation_peak,
                  "includes": "Reweight, prepared solve and complete JSON serialization.",
                  "excludes": "Cached source table, cold source preparation, independent oracle, and process RSS.",
                  "ranking_guards": allocation_guards,
                  "complete_payload_sha256": hashlib.sha256(allocation_json.encode()).hexdigest(),
                  "comparison_payload_sha256": hashlib.sha256(allocation_comparison_json.encode()).hexdigest(),
                  "matches_previously_verified_prepared_payload": True,
                  "verification_reference": reference_warm["verification"]}

    if _hashes() != before or _revision() != revision or _status() != status_before:
        raise RuntimeError("Frozen source, revision, or worktree state changed during measurement")
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
              "source_revision": revision, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "specification_sha256": _canonical_hash(spec), "source_hashes_lf_normalized": before,
              "worktree_clean_at_start_and_before_publication": True,
              "python": platform.python_version(), "platform": platform.platform(),
              "specification": spec, "cold_source_preparation_seconds": cold_seconds,
              "source_table": {"compatible_pairs": len(source_table.pairs),
                               "ordered_worlds": source_table.budget["physical_worlds"],
                               "unordered_boards": source_table.budget["unordered_boards"],
                               "rank_calls_upper_bound": source_table.budget["rank_calls_upper_bound"],
                               "pinned_historical_report_commit": HISTORICAL_COMMIT,
                               "pinned_historical_report_path": HISTORICAL_PATH,
                               "pinned_historical_report_blob": HISTORICAL_BLOB,
                               "counts_match_pinned_report": True,
                               "counts_match_independent_oracle": True},
              "preflights_complete_before_ranking": True, "preflights": preflights,
              "results": results, "allocation": allocation, "quality_misses": failures,
              "acceptance_gate_met": not failures,
              "timing_scope": "Each timed fresh arm includes full source preparation, tree construction, training, diagnostics and JSON serialization. Each prepared arm includes reweighting, tree construction, training, diagnostics and JSON serialization. Three calls per arm are alternated in order; oracle replay is outside timed intervals.",
              "allocation_scope": "Separate Python tracemalloc trace around reweighting, prepared solve and JSON serialization for the base 8x8 stack-24 case; excludes cached source counts, cold preparation, independent oracle and RSS.",
              "accuracy_scope": "Every fresh and prepared payload is checked by independent ordered-board/best-five numeric-rule replay and own-hand information-set best responses. Exact payload parity is required after removing only equity_preparation from the prepared result. Target is independent NashConv plus 1e-9 at most 0.005 chips; misses are retained."}
    report["artifact_sha256"] = _canonical_hash(report)
    _atomic_json(OUTPUT_PATH, report)
    live.update({"phase": "complete", "complete": True,
                 "acceptance_gate_met": not failures, "report": OUTPUT_PATH.as_posix()})
    _atomic_json(LIVE_PATH, live)
    print(f"Saved {OUTPUT_PATH}; acceptance={not failures}", flush=True)
    if failures:
        raise AssertionError("Report saved with target misses")
    return report


def run(spec=None):
    """Run the frozen protocol and preserve unexpected phase failures in live state."""
    try:
        return _run_frozen(spec)
    except Exception as exc:
        try:
            state = {}
            if LIVE_PATH.exists():
                state = json.loads(LIVE_PATH.read_text(encoding="utf-8-sig"))
            state.update({"phase": "failed", "complete": True,
                          "error_type": type(exc).__name__, "error": str(exc)})
            _atomic_json(LIVE_PATH, state)
        except Exception:
            pass
        raise

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8-sig"))
    validate_spec(spec)
    if args.preflight_only:
        outcomes = []
        for fixture in spec["fixtures"]:
            outcome = preflight(_case(spec, fixture), spec["iterations"], spec["algorithm"])
            outcomes.append(outcome)
        print(json.dumps(outcomes, indent=2, allow_nan=False))
        return
    run(spec)


if __name__ == "__main__":
    main()
