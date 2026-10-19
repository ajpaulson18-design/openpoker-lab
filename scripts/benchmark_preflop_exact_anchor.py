"""Profile Python and native trainers against the proved weighted preflop game.

This runner uses pinned physical W/T/L counts and never ranks cards or enumerates
boards. Its timing observations cover complete prepared solves, serialization,
and payload hashing; the exact certificate and physical-count replay remain the
accuracy authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

from scripts import benchmark_native_fixed_street as native_profile
from scripts import benchmark_fixed_street_profile as profile


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "benchmarks" / "preflop-exact-anchor-v1.json"
WITNESS_PATH = ROOT / "tests" / "fixtures" / "preflop-weighted-sequence-candidate-v1.json"
EXPECTED_SPEC_SHA256 = "bea35d1db0606c486202d5a356f016b1049a25db55085355b2b3446a9c97dd6c"
EXPECTED_BASELINE = "a67c0a29631cd20615c77d71a985b4d3d817d53c"
BACKENDS = ("python", "native")
ALGORITHMS = ("vanilla", "dcfr", "cfrplus")


def _canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def checksum(value):
    return _sha(_canonical_bytes(value))


def _git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def validate_spec(spec):
    if type(spec) is not dict or checksum(spec) != EXPECTED_SPEC_SHA256:
        raise ValueError("Exact-anchor runner requires the frozen benchmark specification")
    if (spec.get("schema_version") != 1
            or spec.get("benchmark_id") != "preflop-exact-anchor-v1"
            or spec.get("baseline_commit") != EXPECTED_BASELINE):
        raise ValueError("Frozen exact-anchor identity changed")
    if spec.get("algorithms") != list(ALGORITHMS) or spec.get("checkpoints") != [10, 100, 1000, 8000]:
        raise ValueError("Frozen algorithm/checkpoint set changed")
    if (spec.get("early_repeats") != 1 or spec.get("final_repeats") != 3
            or spec.get("paired_orders") != [["python", "native"], ["native", "python"], ["python", "native"]]):
        raise ValueError("Frozen paired-repeat schedule changed")
    if spec.get("fixture") != {
        "sb_range": "AsAd:1,QsQd:0.5", "bb_range": "AsKh:0.25,KsKd:1",
        "config": {"small_blind": 0.5, "big_blind": 1,
                    "starting_stack": [4, 3], "raise_sizes": [0.5, 1],
                    "max_raises": 1, "include_all_in": True},
        "compatible_pairs": 3, "physical_boards": 5_136_912,
        "public_states": 19, "resource_model": "prepared-counts",
        "world_indexing": "pair-mean",
    }:
        raise ValueError("Frozen exact-anchor fixture changed")
    return spec


def _source_hashes():
    # Inherit the broader source census from the existing fixed-street runner,
    # then add every exact-anchor fixture and physical-count input explicitly.
    hashes = native_profile._source_hashes()
    paths = [SPEC_PATH, ROOT / "benchmarks" / "preflop-weighted-sequence-v1.json",
             ROOT / "benchmarks" / "results" / "preflop-weighted-sequence-v1.json",
             WITNESS_PATH]
    from scripts.preflop_sequence_fixture import ARTIFACTS
    paths.extend(ROOT / relative for relative, *_ in ARTIFACTS)
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        raw = path.read_bytes()
        hashes[path.relative_to(ROOT).as_posix()] = {
            "raw_sha256": _sha(raw), "lf_sha256": _sha(raw.replace(b"\r\n", b"\n"))}
    return hashes


def _identity():
    return {"revision": _git("rev-parse", "HEAD"),
            "status": _git("status", "--porcelain", "--untracked-files=all").splitlines(),
            "source_hashes": _source_hashes()}


def _require_baseline_ancestor(commit):
    result = subprocess.run(["git", "merge-base", "--is-ancestor", EXPECTED_BASELINE, commit],
                            cwd=ROOT, capture_output=True, check=False)
    if result.returncode:
        raise ValueError("Frozen exact-anchor baseline is not an ancestor of HEAD")


def _load_inputs(spec, reference=None):
    """Build the immutable table from already pinned counts, never ranking."""
    from fractions import Fraction
    from pokerlab.preflop_full_board_equity import (
        BOARDS_PER_PAIR, FullBoardEquities, plan_preflop_equities)
    from scripts import preflop_exact_anchor_validation as validation

    reference = validation.load_reference() if reference is None else reference
    fixture = reference["fixture"]
    if fixture["sb_range"] != spec["fixture"]["sb_range"] or fixture["bb_range"] != spec["fixture"]["bb_range"]:
        raise ValueError("Exact witness ranges differ from the benchmark fixture")
    plan = plan_preflop_equities(fixture["sb_range"], fixture["bb_range"])
    plan.validate()
    rows = reference["counts"]
    by_key = {(row["sb_hand"], row["bb_hand"]): row for row in rows}
    pair_rows = []
    counts = []
    worlds = []
    for sb_index, bb_index, prior in plan.pairs:
        key = ("".join(plan.hands[0][sb_index]), "".join(plan.hands[1][bb_index]))
        row = by_key.get(key)
        if row is None or row["boards"] != BOARDS_PER_PAIR:
            raise ValueError("Pinned physical count rows do not cover the planned pair set")
        wins, ties, losses = row["wins"], row["ties"], row["losses"]
        if (any(type(value) is not int for value in (wins, ties, losses))
                or min(wins, ties, losses) < 0 or wins + ties + losses != BOARDS_PER_PAIR):
            raise ValueError("Pinned physical counts are invalid")
        pair_rows.append({"sb_hand": key[0], "bb_hand": key[1], "wins": wins,
                          "ties": ties, "losses": losses, "boards": BOARDS_PER_PAIR})
        counts.append((wins, ties, losses))
        for sign, count in zip((-1, 0, 1), (losses, ties, wins)):
            if count:
                mass = float(prior * Fraction(count, BOARDS_PER_PAIR))
                if not mass > 0:
                    raise ValueError("Pinned positive category mass underflows binary64")
                worlds.append((sb_index, bb_index, mass, sign))
    if len(pair_rows) != spec["fixture"]["compatible_pairs"] or set(by_key) != {
            (row["sb_hand"], row["bb_hand"]) for row in pair_rows}:
        raise ValueError("Pinned physical count pair set differs from the fixed fixture")
    table = FullBoardEquities(
        hands=plan.hands, pairs=plan.pairs, counts=tuple(counts), worlds=tuple(worlds),
        _budget_items=plan._budget_items)
    table.validate()
    return {"case": {"sb_range": fixture["sb_range"], "bb_range": fixture["bb_range"],
                      "config": fixture["config"]},
            "table": table, "counts": pair_rows,
            "pinned_provenance": {"reference": reference["identity"],
                                  "reference_verification": reference["verification"],
                                  "physical_count_rows": pair_rows}}


def _preflight(item, algorithm, iterations):
    return native_profile._preflight_preflop(item, algorithm, iterations)


def _preflight_all(spec, item):
    rows = []
    for algorithm in spec["algorithms"]:
        for iterations in spec["checkpoints"]:
            profile_id = f"preflop-{algorithm}-{iterations}"
            try:
                result = _preflight(item, algorithm, iterations)
                rows.append({"profile_id": profile_id, "algorithm": algorithm,
                             "iterations": iterations, "status": "admitted", **result})
            except Exception as exc:
                rows.append({"profile_id": profile_id, "algorithm": algorithm,
                             "iterations": iterations, "status": "rejected",
                             "error": f"{type(exc).__name__}: {exc}"})
    trace = spec["traces"]
    for backend in trace["backends"]:
        profile_id = f"trace-{trace['algorithm']}-{trace['iterations']}-{backend}"
        try:
            result = _preflight(item, trace["algorithm"], trace["iterations"])
            rows.append({"profile_id": profile_id, "algorithm": trace["algorithm"],
                         "iterations": trace["iterations"], "backend": backend,
                         "status": "admitted", **result})
        except Exception as exc:
            rows.append({"profile_id": profile_id, "algorithm": trace["algorithm"],
                         "iterations": trace["iterations"], "backend": backend,
                         "status": "rejected", "error": f"{type(exc).__name__}: {exc}"})
    return rows


def _assess(payload, reference, spec):
    from scripts.preflop_exact_anchor_validation import assess
    return assess(payload, reference,
                  tolerance=spec["acceptance"]["independent_metric_absolute_tolerance"],
                  target_nash_conv=spec["acceptance"]["final_nash_conv_chip_limit"])


def _sample(item, reference, spec, algorithm, iterations, backend, build_directory,
            *, repeat, kind, trace=False):
    if trace:
        row = native_profile._trace_call(item, algorithm, iterations, backend, build_directory)
    else:
        row = native_profile._profile_call(item, "preflop", algorithm, iterations,
                                           backend, build_directory)
    row.update({"backend": backend, "repeat": repeat, "sample_kind": kind})
    row["phase_call_census_passed"] = native_profile._phase_count_passed(
        "preflop", backend, algorithm, row)
    if not row["phase_call_census_passed"]:
        row["phase_call_census_error"] = "Unexpected top-level trainer/evaluator/BR call census"
    if row.get("payload") is not None:
        try:
            row["independent_assessment"] = _assess(row["payload"], reference, spec)
        except Exception as exc:
            row["independent_assessment_error"] = f"{type(exc).__name__}: {exc}"
    return row


def _paired_comparison(left, right, spec):
    return native_profile._compare_payloads("preflop", left, right, spec)


def _run_profile(spec, item, reference, algorithm, iterations, build_directory, errors):
    profile_id = f"preflop-{algorithm}-{iterations}"
    final_checkpoint = iterations == max(spec["checkpoints"])
    repeat_count = spec["final_repeats"] if final_checkpoint else spec["early_repeats"]
    orders = spec["paired_orders"][:repeat_count]
    samples, pairs = [], []
    for repeat, order in enumerate(orders, 1):
        paired = {}
        for backend in order:
            print(f"START {profile_id} repeat={repeat} backend={backend}", flush=True)
            row = _sample(item, reference, spec, algorithm, iterations, backend,
                          build_directory, repeat=repeat, kind="final" if final_checkpoint else "early")
            samples.append(row)
            paired[backend] = row.get("payload")
            if row.get("error") or row.get("phase_call_census_error") or row.get("independent_assessment_error"):
                errors.append({"profile_id": profile_id, "backend": backend, "repeat": repeat,
                               "phase": "sample", "error": row.get("error") or row.get("phase_call_census_error")
                               or row.get("independent_assessment_error")})
            print(f"DONE {profile_id} repeat={repeat} backend={backend} seconds={row['complete_seconds']:.6f}", flush=True)
        if all(type(paired.get(backend)) is dict for backend in BACKENDS):
            try:
                comparison = _paired_comparison(paired["python"], paired["native"], spec)
                comparison["status"] = "passed" if (comparison["meets_metric_gate"]
                                                     and comparison["meets_policy_gate"]) else "missed"
            except Exception as exc:
                comparison = {"status": "error", "error": f"{type(exc).__name__}: {exc}",
                              "meets_metric_gate": False, "meets_policy_gate": False}
        else:
            comparison = {"status": "error", "error": "Missing backend payload",
                          "meets_metric_gate": False, "meets_policy_gate": False}
        comparison["repeat"] = repeat
        pairs.append(comparison)
        if comparison["status"] != "passed":
            errors.append({"profile_id": profile_id, "repeat": repeat,
                           "phase": "cross-backend-comparison", "error": comparison.get("error", "Tolerance missed")})
    deterministic, medians = {}, {}
    for backend in BACKENDS:
        backend_samples = [row for row in samples if row["backend"] == backend]
        hashes = [row.get("payload_sha256") for row in backend_samples]
        deterministic[backend] = (final_checkpoint and len(hashes) == 3
                                  and all(hashes) and len(set(hashes)) == 1)
        medians[backend] = (statistics.median(row["complete_seconds"] for row in backend_samples)
                            if final_checkpoint and len(backend_samples) == 3
                            and all(row.get("payload_sha256") for row in backend_samples)
                            else None)
    if final_checkpoint and not all(deterministic.values()):
        errors.append({"profile_id": profile_id, "phase": "determinism",
                       "error": "Final checkpoint payloads differ within a backend"})
    target_pass = {
        backend: bool([row for row in samples if row["backend"] == backend]) and all(
            row.get("independent_assessment", {}).get("quality_pass") is True
            for row in samples if row["backend"] == backend)
        for backend in BACKENDS}
    mandatory = algorithm == spec["acceptance"]["final_quality_algorithm"] and final_checkpoint
    if mandatory and not all(target_pass.values()):
        errors.append({"profile_id": profile_id, "phase": "final-quality",
                       "error": "Final CFR+ exact NashConv target missed"})
    return {"profile_id": profile_id, "algorithm": algorithm, "iterations": iterations,
            "mandatory_quality": mandatory, "samples": samples,
            "paired_comparisons": pairs, "deterministic_final_payloads": deterministic,
            "median_complete_seconds": medians,
            "quality_passed_by_backend": target_pass}


def _run_traces(spec, item, reference, build_directory, errors):
    trace_spec = spec["traces"]
    rows = {}
    for backend in trace_spec["backends"]:
        row = _sample(item, reference, spec, trace_spec["algorithm"],
                      trace_spec["iterations"], backend, build_directory,
                      repeat=1, kind="separate-trace", trace=True)
        row["trace_scope"] = ("Python tracemalloc covers Python-process allocations only; native child allocations and RSS are excluded.")
        rows[backend] = row
        if row.get("error") or row.get("independent_assessment_error") or not row.get("phase_call_census_passed"):
            errors.append({"phase": "trace", "backend": backend,
                           "error": row.get("error") or row.get("independent_assessment_error")
                           or row.get("phase_call_census_error")})
    if all(type(rows.get(b, {}).get("payload")) is dict for b in BACKENDS):
        try:
            comparison = _paired_comparison(rows["python"]["payload"], rows["native"]["payload"], spec)
            comparison["status"] = "passed" if comparison["meets_metric_gate"] and comparison["meets_policy_gate"] else "missed"
        except Exception as exc:
            comparison = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    else:
        comparison = {"status": "error", "error": "Missing trace payload"}
    rows["cross_backend_comparison"] = comparison
    if comparison["status"] != "passed":
        errors.append({"phase": "trace-comparison", "error": comparison.get("error", "Tolerance missed")})
    return rows


def run(spec, build_directory):
    """Execute the complete preregistered run and retain all observations."""
    validate_spec(spec)
    errors, preflights, profiles, traces = [], [], [], {}
    before = after = build_before = build_after = None
    reference_identity = reference = item = None
    try:
        from scripts import preflop_exact_anchor_validation as validation
        reference = validation.load_reference()
        reference_identity = reference["identity"]
        before = _identity()
        _require_baseline_ancestor(before["revision"])
        if before["status"]:
            raise ValueError("Benchmark requires clean committed source")
        item = _load_inputs(spec, reference)
        if (item["table"].budget["compatible_pairs"] != spec["fixture"]["compatible_pairs"]
                or item["table"].budget["physical_worlds_upper_bound"] != spec["fixture"]["physical_boards"]):
            raise ValueError("Prepared exact-anchor physical census changed")
        preflights = _preflight_all(spec, item)
        if len(preflights) != 14 or any(row.get("status") != "admitted" for row in preflights):
            raise ValueError("All 12 profile and 2 trace requests must be admitted before native lookup/training")
        # The explicit build identity lookup is deliberately after every full
        # request's Python/reference and native admission has completed.
        build_before = native_profile._build_identity(build_directory)
        for algorithm in spec["algorithms"]:
            for iterations in spec["checkpoints"]:
                profiles.append(_run_profile(spec, item, reference, algorithm, iterations,
                                             build_directory, errors))
        traces = _run_traces(spec, item, reference, build_directory, errors)
        after = _identity()
        build_after = native_profile._build_identity(build_directory)
        if before != after:
            errors.append({"phase": "source-integrity", "error": "Source identity changed during run"})
        if build_before != build_after:
            errors.append({"phase": "build-integrity", "error": "Native build identity changed during run"})
    except Exception as exc:
        errors.append({"phase": "runner", "error": f"{type(exc).__name__}: {exc}"})
        try:
            if before is not None:
                after = _identity()
            if build_before is not None:
                build_after = native_profile._build_identity(build_directory)
        except Exception as nested:
            errors.append({"phase": "final-identity", "error": f"{type(nested).__name__}: {nested}"})

    preflight_pass = len(preflights) == 14 and all(x.get("status") == "admitted" for x in preflights)
    final_cfrplus = next((row for row in profiles if row["algorithm"] == "cfrplus" and row["iterations"] == 8000), None)
    final_quality = bool(final_cfrplus and all(final_cfrplus["quality_passed_by_backend"].values()))
    final_brackets = all(
        sample.get("independent_assessment", {}).get("exact_anchor_contained") is True
        for row in profiles for sample in row["samples"])
    final_brackets = final_brackets and all(
        traces.get(backend, {}).get("independent_assessment", {}).get("exact_anchor_contained") is True
        for backend in BACKENDS)
    all_comparisons = all(
        comparison.get("status") == "passed"
        for row in profiles for comparison in row["paired_comparisons"])
    expected_profile_calls = all(
        len(row["samples"]) == (6 if row["iterations"] == max(spec["checkpoints"]) else 2)
        and len(row["paired_comparisons"]) == (3 if row["iterations"] == max(spec["checkpoints"]) else 1)
        for row in profiles)
    profile_coverage = len(profiles) == len(spec["algorithms"]) * len(spec["checkpoints"]) and expected_profile_calls
    traces_ok = all(type(traces.get(b, {}).get("payload")) is dict for b in BACKENDS) and traces.get("cross_backend_comparison", {}).get("status") == "passed"
    status = "passed" if (not errors and preflight_pass and profile_coverage and final_quality
                           and final_brackets and all_comparisons and traces_ok) else "error"
    report = {
        "schema_version": 1, "benchmark_id": spec["benchmark_id"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "specification": spec, "spec_sha256": checksum(spec),
        "status": status, "errors": errors,
        "source_before": before, "source_after": after,
        "source_unchanged": before is not None and before == after,
        "reference_identity": reference_identity,
        "physical_count_provenance": item.get("pinned_provenance") if item else None,
        "prepared_table_budget": item["table"].budget if item else None,
        "native_build_before": build_before, "native_build_after": build_after,
        "native_build_unchanged": build_before is not None and build_before == build_after,
        "runtime": {"python": sys.version, "executable": sys.executable,
                    "platform": __import__("platform").platform()},
        "preflights": preflights, "all_fourteen_preflights_passed": preflight_pass,
        "profiles": profiles, "separate_traces": traces,
        "gates": {"all_preflights_passed": preflight_pass,
                  "all_profile_calls_and_comparisons_retained": profile_coverage,
                  "every_sample_exact_bracket_passed": final_brackets,
                  "final_cfrplus_quality_passed_both_backends": final_quality,
                  "all_paired_backend_comparisons_passed": all_comparisons,
                  "separate_trace_comparison_passed": traces_ok,
                  "early_and_nonmandatory_quality_misses_are_nonfatal": True,
                  "no_speed_or_equilibrium_policy_distance_gate": True},
        "method": {
            "timing_boundary": spec["timing_boundary"],
            "candidate_world_indexing": "pair-mean for both backends; physical W/T/L counts remain the independent replay authority",
            "replay": "Exact certificate and physical counts are reverified outside timed calls. Every retained payload is independently replayed and bracketed; the report is reopened and replayed before completion.",
            "trace_scope": spec["traces"]["scope"],
            "scope": spec["scope"],
        },
        "serialized_report_verification": {"status": "pending-main-reopen"},
    }
    report["artifact_sha256"] = checksum(report)
    return report


def _verify_serialized_report(path):
    from scripts.preflop_exact_anchor_validation import assess, load_reference
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    digest = data.get("artifact_sha256")
    unsigned = {key: value for key, value in data.items() if key != "artifact_sha256"}
    if digest != checksum(unsigned):
        raise ValueError("Serialized benchmark report checksum mismatch")
    validate_spec(data.get("specification"))
    ref = load_reference()
    checked = 0
    accepted = data["specification"]["acceptance"]
    for profile_row in data.get("profiles", []):
        expected_repeats = (3 if profile_row.get("iterations") == max(data["specification"]["checkpoints"])
                            else 1)
        expected_samples = 2 * expected_repeats
        if len(profile_row.get("samples", [])) != expected_samples:
            if data.get("status") == "passed":
                raise ValueError("Passed report has an incomplete profile sample set")
        for sample in profile_row.get("samples", []):
            payload = sample.get("payload")
            if payload is not None:
                encoded = _canonical_bytes(payload)
                if (sample.get("payload_sha256") != _sha(encoded)
                        or sample.get("serialized_bytes_utf8") != len(encoded)):
                    raise ValueError("Serialized payload bytes or digest changed after timing")
                assessment = assess(payload, ref,
                                    tolerance=accepted["independent_metric_absolute_tolerance"],
                                    target_nash_conv=accepted["final_nash_conv_chip_limit"])
                if assessment != sample.get("independent_assessment"):
                    raise ValueError("Fresh exact replay differs from saved sample assessment")
                checked += 1
    for backend in BACKENDS:
        sample = data.get("separate_traces", {}).get(backend, {})
        if sample.get("payload") is not None:
            encoded = _canonical_bytes(sample["payload"])
            if (sample.get("payload_sha256") != _sha(encoded)
                    or sample.get("serialized_bytes_utf8") != len(encoded)):
                raise ValueError("Serialized trace payload bytes or digest changed after timing")
            assessment = assess(sample["payload"], ref,
                                tolerance=accepted["independent_metric_absolute_tolerance"],
                                target_nash_conv=accepted["final_nash_conv_chip_limit"])
            if assessment != sample.get("independent_assessment"):
                raise ValueError("Fresh exact replay differs from saved trace assessment")
            checked += 1
    complete = checked == 38
    if data.get("status") == "passed" and not complete:
        raise ValueError("Passed report must retain all 38 timed profile and trace payloads")

    # Recompute all paired tolerances from serialized payloads rather than
    # trusting the summaries written during the measurement run.
    comparisons_checked = 0
    for profile_row in data.get("profiles", []):
        samples = profile_row.get("samples", [])
        repeats = sorted({sample.get("repeat") for sample in samples})
        for repeat in repeats:
            by_backend = {sample.get("backend"): sample.get("payload") for sample in samples
                          if sample.get("repeat") == repeat}
            saved = next((row for row in profile_row.get("paired_comparisons", [])
                          if row.get("repeat") == repeat), None)
            if set(by_backend) == set(BACKENDS) and all(type(by_backend[x]) is dict for x in BACKENDS):
                fresh = _paired_comparison(by_backend["python"], by_backend["native"], data["specification"])
                if saved is None:
                    raise ValueError("Serialized paired comparison is missing")
                for key in ("metric_absolute_gaps", "maximum_metric_absolute_gap",
                            "maximum_policy_probability_gap", "meets_metric_gate", "meets_policy_gate"):
                    if fresh.get(key) != saved.get(key):
                        raise ValueError("Fresh cross-backend comparison differs from saved summary")
                if data.get("status") == "passed" and not (fresh["meets_metric_gate"] and fresh["meets_policy_gate"]):
                    raise ValueError("Passed report contains a cross-backend tolerance miss")
                comparisons_checked += 1
    trace_rows = data.get("separate_traces", {})
    if all(type(trace_rows.get(b, {}).get("payload")) is dict for b in BACKENDS):
        fresh = _paired_comparison(trace_rows["python"]["payload"], trace_rows["native"]["payload"],
                                   data["specification"])
        saved = trace_rows.get("cross_backend_comparison", {})
        for key in ("metric_absolute_gaps", "maximum_metric_absolute_gap",
                    "maximum_policy_probability_gap", "meets_metric_gate", "meets_policy_gate"):
            if fresh.get(key) != saved.get(key):
                raise ValueError("Fresh trace comparison differs from saved summary")
        comparisons_checked += 1
    if data.get("status") == "passed":
        expected_profiles = [(a, n) for a in ALGORITHMS for n in (10, 100, 1000, 8000)]
        actual_profiles = [(row.get("algorithm"), row.get("iterations"))
                           for row in data.get("profiles", [])]
        if actual_profiles != expected_profiles or data.get("errors") != []:
            raise ValueError("Passed report profile census or error list is invalid")
        if (data.get("source_before") != data.get("source_after")
                or data["source_before"].get("status") != []
                or data.get("native_build_before") != data.get("native_build_after")
                or len(data.get("preflights", [])) != 14
                or any(row.get("status") != "admitted" for row in data["preflights"])):
            raise ValueError("Passed report source/build/preflight evidence disagrees")
        for profile_row in data["profiles"]:
            final_checkpoint = profile_row["iterations"] == 8000
            orders = data["specification"]["paired_orders"][:3 if final_checkpoint else 1]
            expected_order = [(repeat, backend) for repeat, order in enumerate(orders, 1)
                              for backend in order]
            samples = profile_row["samples"]
            if [(x.get("repeat"), x.get("backend")) for x in samples] != expected_order:
                raise ValueError("Passed report paired sample order changed")
            for sample in samples:
                if (sample.get("error") or sample.get("independent_assessment_error")
                        or sample.get("phase_call_census_passed") is not True
                        or any(sample.get("rank_guard_calls", {}).values())
                        or not native_profile._phase_count_passed(
                            "preflop", sample["backend"], profile_row["algorithm"], sample)
                        or sample["payload"].get("algorithm") != profile_row["algorithm"]
                        or sample["payload"].get("iterations") != profile_row["iterations"]):
                    raise ValueError("Passed report sample identity or execution census failed")
            expected_quality = {backend: all(x["independent_assessment"]["quality_pass"]
                                for x in samples if x["backend"] == backend)
                                for backend in BACKENDS}
            expected_medians = {backend: statistics.median(x["complete_seconds"] for x in samples
                                if x["backend"] == backend) if final_checkpoint else None
                                for backend in BACKENDS}
            if (profile_row.get("quality_passed_by_backend") != expected_quality
                    or profile_row.get("median_complete_seconds") != expected_medians):
                raise ValueError("Passed report quality or timing summaries differ from samples")
        for backend in BACKENDS:
            sample = trace_rows[backend]
            if (sample.get("phase_call_census_passed") is not True
                    or any(sample.get("rank_guard_calls", {}).values())
                    or not native_profile._phase_count_passed("preflop", backend, "cfrplus", sample)
                    or sample["payload"].get("algorithm") != "cfrplus"
                    or sample["payload"].get("iterations") != 1000):
                raise ValueError("Passed report trace identity or execution census failed")
        if (data.get("all_fourteen_preflights_passed") is not True
                or data.get("source_unchanged") is not True
                or data.get("native_build_unchanged") is not True):
            raise ValueError("Passed report is missing a successful preflight or integrity gate")
        if comparisons_checked != 19:
            raise ValueError("Passed report does not retain all 18 profile repeat and one trace comparison")
        for profile_row in data["profiles"]:
            if profile_row.get("iterations") != max(data["specification"]["checkpoints"]):
                continue
            for backend in BACKENDS:
                backend_samples = [x for x in profile_row["samples"] if x.get("backend") == backend]
                hashes = [x.get("payload_sha256") for x in backend_samples]
                if (len(hashes) != 3 or not all(hashes) or len(set(hashes)) != 1
                        or profile_row.get("deterministic_final_payloads", {}).get(backend) is not True):
                    raise ValueError("Passed report has non-deterministic final payloads")
        final = next((row for row in data["profiles"]
                      if row.get("algorithm") == "cfrplus"
                      and row.get("iterations") == max(data["specification"]["checkpoints"])), None)
        if final is None or not all(final.get("quality_passed_by_backend", {}).get(b) is True for b in BACKENDS):
            raise ValueError("Passed report does not meet the final CFR+ exact NashConv gate")
    return {"status": "passed", "reopened_payloads_replayed": checked,
            "complete_payload_census": complete, "fresh_comparisons_checked": comparisons_checked,
            "serialized_artifact_sha256": digest}


def _atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")
    temp.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True,
                        help="Explicit external native V2 build directory")
    parser.add_argument("--output", type=Path,
                        default=ROOT.parent / "preflop-exact-anchor-v1-report.json")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error("Output must be outside the source checkout")
    if output.exists():
        parser.error("Refusing to overwrite an existing benchmark report")
    if output.with_name(output.name + ".tmp").exists():
        parser.error("Refusing to overwrite an existing temporary benchmark report")
    spec = validate_spec(json.loads(SPEC_PATH.read_text(encoding="utf-8-sig")))
    report = run(spec, args.build_dir)
    _atomic_json(output, report)
    try:
        verified = _verify_serialized_report(output)
    except Exception as exc:
        verified = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        report["errors"].append({"phase": "serialized-report-replay", "error": verified["error"]})
        report["status"] = "error"
    report["serialized_report_verification"] = verified
    report.pop("artifact_sha256", None)
    report["artifact_sha256"] = checksum(report)
    _atomic_json(output, report)
    final_check = _verify_serialized_report(output)
    final_identity_error = None
    try:
        if report.get("source_after") is not None and _identity() != report["source_after"]:
            final_identity_error = "Source identity changed after serialized report verification"
        if report.get("native_build_after") is not None:
            build_after_check = native_profile._build_identity(args.build_dir)
            if build_after_check != report["native_build_after"]:
                final_identity_error = "Native build identity changed after serialized report verification"
    except Exception as exc:
        final_identity_error = f"{type(exc).__name__}: {exc}"
    if final_identity_error:
        report["errors"].append({"phase": "final-integrity", "error": final_identity_error})
        report["status"] = "error"
        report.pop("artifact_sha256", None)
        report["artifact_sha256"] = checksum(report)
        _atomic_json(output, report)
        final_check = _verify_serialized_report(output)
    report["final_serialized_verification"] = {
        key: value for key, value in final_check.items() if key != "serialized_artifact_sha256"}
    report.pop("artifact_sha256", None)
    report["artifact_sha256"] = checksum(report)
    _atomic_json(output, report)
    final_check = _verify_serialized_report(output)
    print(json.dumps({"status": report["status"], "artifact_sha256": report["artifact_sha256"],
                      "errors": report["errors"], "output": str(output)}, sort_keys=True), flush=True)
    return 0 if report["status"] == "passed" and verified.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
