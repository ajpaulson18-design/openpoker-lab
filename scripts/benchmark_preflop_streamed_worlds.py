"""Frozen complete-call storage comparison on the verified expanded game."""
from __future__ import annotations
import gc, hashlib, json, platform, re, statistics, subprocess, time, tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from pokerlab import preflop_solver as solver
from scripts import benchmark_preflop_expanded_range as expanded
from scripts import benchmark_preflop_weighted_range_coverage as weighted
from scripts.benchmark_preflop_flop_checkdown import verify
from scripts.preflop_validation import compare_result

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/preflop-streamed-worlds-v1.json"
GAME = ROOT / "benchmarks/preflop-expanded-range-v1.json"
PRIOR = ROOT / "benchmarks/results/preflop-expanded-range-v1.json"
OUTPUT = ROOT / "benchmarks/results/preflop-streamed-worlds-v1.json"
CHANGED_PRIOR = {"pokerlab/preflop_solver.py", "pokerlab/preflop_vector_budget.py", "pokerlab/preflop_future_groups.py"}


def normalized_payload(result):
    """Remove only documented opt-in storage metadata; preserve all game data."""
    if result.get("world_storage") == "streamed-flop-sign":
        result = dict(result)
        storage = result.pop("world_storage_metadata")
        result.pop("world_storage")
        budget = dict(result["vector_work_budget"])
        if budget.pop("streamed_world_construction") != storage:
            raise AssertionError("Streaming construction records disagree")
        budget["total_loop_entries_upper_bound"] -= storage["additional_loop_entries_upper_bound"]
        budget["budget_version"] = budget.pop("streamed_world_reference_budget_version")
        result["vector_work_budget"] = budget
    return json.dumps(result, allow_nan=False, separators=(",", ":"))


def _paths():
    return tuple(dict.fromkeys((*expanded._manifest_paths(), "AGENTS.md",
        "pokerlab/preflop_streamed_worlds.py", "tests/test_preflop_streamed_budget.py",
        "tests/test_preflop_streamed_worlds.py", "scripts/benchmark_preflop_streamed_worlds.py",
        "benchmarks/preflop-streamed-worlds-v1.json", "benchmarks/results/preflop-expanded-range-v1.json")))


def _run(spec, game, checkpoint, candidate, expected, label, trace=False, legacy_payload_sha256=None, replay_cache=None):
    kwargs = weighted._solve_kwargs(game, checkpoint)
    if candidate:
        kwargs["world_storage"] = "streamed-flop-sign"
    print(f"starting {label}", flush=True)
    gc.collect()
    if trace:
        tracemalloc.start()
    start = time.perf_counter()
    try:
        result = solver.solve_preflop(game["sb_range"], game["bb_range"], **kwargs)
        payload = json.dumps(result, allow_nan=False, separators=(",", ":"))
    finally:
        elapsed = time.perf_counter() - start
        peak = None
        if trace:
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
    normalized = normalized_payload(result)
    legacy_hash = hashlib.sha256(json.dumps(json.loads(normalized), allow_nan=False).encode()).hexdigest()
    if legacy_payload_sha256 is not None and legacy_hash != legacy_payload_sha256:
        raise AssertionError("Complete game payload differs from the frozen verified-game report")
    normalized_hash = hashlib.sha256(normalized.encode()).hexdigest()
    fixture_hash = hashlib.sha256(json.dumps(game, sort_keys=True).encode()).hexdigest()
    cache_key = (fixture_hash, normalized_hash)
    cached = replay_cache.get(cache_key) if replay_cache is not None else None
    if cached is None:
        checked = verify(result, {**game, "sb": game["sb_range"], "bb": game["bb_range"],
                         "expected_worlds": game["expected_physical_worlds"]}, weighted._options(game))
        origin = label
        if replay_cache is not None:
            replay_cache[cache_key] = (label, checked)
    else:
        origin, original_checked = cached
        checked = dict(original_checked)
        checked["vector_work_budget"] = result["vector_work_budget"]
        checked["metric_absolute_gaps"] = compare_result(result, checked["configured_replay"])
    posterior = weighted._assert_report_pair_posteriors(result, checked, weighted._independent_pair_audit(game))
    budget = result["vector_work_budget"]
    if budget["iterations"] != checkpoint["iterations"] or budget["total_loop_entries_upper_bound"] != expected:
        raise AssertionError("Actual full-requested-T admission differs from preflight")
    gap = checked["configured_replay"]["nash_conv"]
    row = {"candidate": candidate, **checkpoint, "complete_call_plus_json_seconds": elapsed,
        "raw_payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "legacy_verified_game_payload_sha256": legacy_hash,
        "normalized_payload_sha256": normalized_hash,
        "independent_replay_performed": cached is None, "replay_origin_label": origin,
        "replay_fixture_sha256": fixture_hash,
        "nash_conv": gap, "target_met": gap + spec["target_padding"] <= spec["target_nash_conv"],
        "verification": checked, "posterior_audit": posterior, "vector_work_budget": budget,
        "world_storage_metadata": result.get("world_storage_metadata"),
        "future_indexing_metadata": result["future_indexing_metadata"]}
    if trace:
        row["traced_peak_bytes"] = peak
    del result, payload, normalized, checked
    print(f"finished {label}; seconds={elapsed:.6f}; gap={gap:.12g}; target={row['target_met']}", flush=True)
    return row


def _gates(spec, rows, allocation):
    pairs = []
    for index in range(3):
        a, b = rows[2 * index:2 * index + 2]
        baseline, candidate = (b, a) if a["candidate"] else (a, b)
        ratio = candidate["complete_call_plus_json_seconds"] / baseline["complete_call_plus_json_seconds"]
        pairs.append({"pair": index + 1, "baseline_seconds": baseline["complete_call_plus_json_seconds"],
                      "candidate_seconds": candidate["complete_call_plus_json_seconds"],
                      "runtime_ratio": ratio, "reduction": 1 - ratio})
    median = statistics.median(p["reduction"] for p in pairs)
    peak_reduction = 1 - allocation[1]["traced_peak_bytes"] / allocation[0]["traced_peak_bytes"]
    failures = []
    if len({r["normalized_payload_sha256"] for r in rows}) != 1:
        failures.append("normalized complete payloads differ across timing arms")
    if allocation[0]["normalized_payload_sha256"] != allocation[1]["normalized_payload_sha256"]:
        failures.append("allocation normalized complete payloads differ")
    if not all(r["target_met"] for r in rows):
        failures.append("timing accuracy target missed")
    if any(p["runtime_ratio"] > spec["maximum_pair_runtime_ratio"] for p in pairs):
        failures.append("a paired runtime exceeded the frozen nonregression margin")
    if median < spec["minimum_median_runtime_reduction"]:
        failures.append("median runtime regressed")
    if peak_reduction < spec["minimum_traced_peak_reduction"]:
        failures.append("traced peak reduction missed frozen target")
    return {"paired_results": pairs, "median_runtime_reduction": median,
            "traced_peak_reduction": peak_reduction, "failures": failures, "promotion_gate_met": not failures}


def main():
    try:
        from pokerlab.preflop_streamed_worlds import estimate_streamed_construction
    except ModuleNotFoundError as exc:
        if exc.name != "pokerlab.preflop_streamed_worlds":
            raise
        raise RuntimeError(
            "Research candidate was not adopted. Reproduce in a clean worktree at "
            "ec12cba69f90df08c5c251678b45318e127cec12 using "
            "python -m scripts.benchmark_preflop_streamed_worlds_v2."
        ) from exc
    spec, game, prior = (json.loads(p.read_text(encoding="utf-8-sig")) for p in (SPEC, GAME, PRIOR))
    revision = weighted.git_revision(None)
    if weighted.worktree_dirty() is not False or not re.fullmatch(r"[0-9a-f]{40}", revision or ""):
        raise RuntimeError("Freeze source/spec in a clean commit before measurement")
    if spec["game_spec"] != GAME.relative_to(ROOT).as_posix() or spec["prior_verified_report"] != PRIOR.relative_to(ROOT).as_posix():
        raise ValueError("Fixture provenance paths changed")
    if (spec["checkpoint"] != {"iterations": 500, "delay": 250}
            or spec["allocation_checkpoint"] != {"iterations": 10, "delay": 5}
            or spec["pair_order"] != ["materialized", "streamed", "streamed", "materialized", "materialized", "streamed"]):
        raise ValueError("This harness implements only the frozen eight-arm plan")
    if spec["target_nash_conv"] != game["target_nash_conv"] or spec["target_padding"] != game["target_padding"]:
        raise ValueError("Quality target differs from verified game")
    for ancestor in (prior["source_revision"], spec["baseline_main"]):
        if subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, revision], cwd=ROOT, check=False).returncode:
            raise ValueError("Required baseline source is not an ancestor")
    changed = {path for path, digest in prior["source_hashes"].items() if weighted.file_sha256(ROOT / path) != digest}
    if changed != CHANGED_PRIOR:
        raise ValueError(f"Unexpected changed prior sources: {sorted(changed)}")
    hashes = expanded._hashes(_paths())
    audit = weighted._independent_pair_audit(game)
    blockers = expanded._extra_card_audit(game)
    preflights = []
    for checkpoint in (spec["checkpoint"], spec["allocation_checkpoint"]):
        admission = weighted._preflight(game, checkpoint)
        if admission["status"] != "admitted":
            raise RuntimeError("Frozen fixture rejected before any training")
        stream = estimate_streamed_construction(audit["physical_worlds"], audit["selected_outcomes"], len(audit["compatible_private_pair_keys"]))
        candidate_total = admission["combined_modeled_loop_entries"] + stream["additional_loop_entries_upper_bound"]
        if candidate_total > solver.MAX_TOTAL_LOOP_ENTRIES:
            raise RuntimeError("Additional streamed construction rejected before training")
        preflights.append({**checkpoint, "baseline": admission, "streamed_construction": stream, "candidate_combined_loop_entries": candidate_total})
    anchor = next(row for row in prior["results"] if row["iterations"] == spec["checkpoint"]["iterations"])
    if not anchor["target_met"]:
        raise ValueError("Verified-game quality anchor is unavailable")
    rows, allocation, replay_cache = [], [], {}
    progress_path = ROOT.parent / "preflop-streamed-worlds-live.json"
    def save_progress():
        progress_path.write_text(json.dumps({"source_revision": revision,
            "source_hashes": hashes, "specification": spec, "preflight": preflights,
            "timing_arms": rows, "allocation_arms": allocation,
            "complete": False}, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    save_progress()
    for index, arm in enumerate(spec["pair_order"]):
        candidate = arm == "streamed"
        expected = preflights[0]["candidate_combined_loop_entries"] if candidate else preflights[0]["baseline"]["combined_modeled_loop_entries"]
        rows.append(_run(spec, game, spec["checkpoint"], candidate, expected, f"timing {index + 1}/6 {arm}",
                         legacy_payload_sha256=anchor["full_payload_sha256"], replay_cache=replay_cache))
        save_progress()
    for candidate in (False, True):
        expected = preflights[1]["candidate_combined_loop_entries"] if candidate else preflights[1]["baseline"]["combined_modeled_loop_entries"]
        allocation.append(_run(spec, game, spec["allocation_checkpoint"], candidate, expected,
                               f"allocation {'streamed' if candidate else 'materialized'}", trace=True, replay_cache=replay_cache))
        save_progress()
    gate = _gates(spec, rows, allocation)
    if hashes != expanded._hashes(_paths()) or weighted.git_revision(None) != revision or weighted.worktree_dirty() is not False:
        raise RuntimeError("Frozen source/revision changed during measurement")
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"], "source_revision": revision,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "source_hashes": hashes,
        "worktree_dirty_at_start": False, "specification": spec, "python": platform.python_version(),
        "platform": platform.platform(), "changed_prior_sources": sorted(changed),
        "independent_pair_audit": audit, "blocker_audit": blockers, "preflight": preflights,
        "timing_arms": rows, "allocation_arms": allocation, **gate,
        "timing_scope": "Three alternating complete solves plus raw JSON, including construction, full requested-T training and exact diagnostics; inputs/GC precede measurement, parity normalization and original-world independent replay follow it. No prior policies retained between arms.",
        "quality_scope": spec["replay_reuse"],
        "unique_independently_replayed_payloads": len(replay_cache),
        "allocation_scope": "Separate 10/delay5 complete calls plus raw JSON under tracemalloc. Python-traced allocations, not RSS or high-iteration memory. Both short-arm quality results retained.",
        "parity_scope": "Complete payload comparison after removing only top-level world_storage/world_storage_metadata and vector streamed_world_construction/reference-version, subtracting its declared extra loops and restoring the original budget version. No policy, count, posterior, utility or accuracy fields removed.",
        "model_limits": game["model_limits"]}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"saved {OUTPUT}; gate={gate['promotion_gate_met']}; median={gate['median_runtime_reduction']:.4%}; peak={gate['traced_peak_reduction']:.4%}", flush=True)
    if gate["failures"]:
        raise AssertionError("Report saved; " + "; ".join(gate["failures"]))

if __name__ == "__main__":
    main()
