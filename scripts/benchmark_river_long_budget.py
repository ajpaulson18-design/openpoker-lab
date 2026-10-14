"""Fixed-budget matrix-free CFR+ accuracy extension for the polarised river.

This is a quality experiment, not a runtime or memory comparison. Each saved
complete policy is replayed by the independent numeric/legal-BR validator.
"""
import argparse
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

from pokerlab.matrix_free_river import solve_matrix_free_river
from scripts.benchmark_turn_river_independent import CONFIG, ROOT, source_hashes
from scripts.replay_river_accuracy_extension import rational_polarised
from scripts.turn_river_validation import compare_result, replay_policy


ITERATIONS = (10_000, 30_000, 100_000)
BENCHMARK_THRESHOLD = 0.001
ARCHIVE_REPORT = ROOT / "benchmarks" / "results" / "river-cfrplus-accuracy-extension-v1.json"
ARCHIVE_POLICIES = ROOT / "benchmarks" / "results" / "river-cfrplus-accuracy-policies-v1"
OUTPUT_POLICY_DIR = ROOT / "benchmarks" / "results" / "river-cfrplus-long-budget-policies-v1"


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _portable_json(value):
    return (json.dumps(value, allow_nan=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _fixture():
    scenarios = json.loads(CONFIG.read_text(encoding="utf-8"))["scenarios"]
    matches = [case for case in scenarios if case.get("id") == "river-polarised-bluffcatcher"]
    if len(matches) != 1:
        raise ValueError("Expected one frozen polarised river fixture")
    case = matches[0]
    expected = {
        "board": "2c7d9hJsKd", "oop": "AsAh,3c4c", "ip": "QsQh",
        "config": {"pot": 100, "effective_stack": 100, "bet_sizes": [1.0],
                   "include_all_in": False},
    }
    if any(case.get(key) != value for key, value in expected.items()):
        raise ValueError("Polarised fixture differs from the predeclared specification")
    return case


def _baseline(case):
    report_bytes = ARCHIVE_REPORT.read_bytes()
    report = json.loads(report_bytes)
    matches = [row for row in report["results"]
               if row.get("scenario") == case["id"]
               and row.get("backend") == "matrix-free"
               and row.get("algorithm") == "cfrplus"
               and row.get("iterations") == 10_000]
    if len(matches) != 1:
        raise ValueError("Archived report must identify exactly one matrix-free 10k CFR+ policy")
    row = matches[0]
    expected_name = "river-polarised-bluffcatcher-matrix-free-10000.json"
    if row.get("policy_file") != expected_name:
        raise ValueError("Archived 10k policy filename differs from the frozen artifact")
    policy_path = ARCHIVE_POLICIES / row["policy_file"]
    payload = policy_path.read_bytes()
    if _digest(payload) != row["policy_sha256"]:
        raise ValueError("Archived 10k policy byte hash differs from its report")
    source_hash = report.get("source_sha256", {}).get("pokerlab\\matrix_free_river.py")
    if not source_hash:
        raise ValueError("Archived report lacks the matrix-free river source fingerprint")
    return json.loads(payload), {
        "report_sha256": _digest(report_bytes),
        "policy_file": policy_path.relative_to(ROOT).as_posix(),
        "policy_sha256": row["policy_sha256"],
        "matrix_free_river_source_sha256": source_hash,
    }


def _fingerprints():
    result = source_hashes()
    extra = (
        Path(__file__),
        ROOT / "scripts" / "replay_river_accuracy_extension.py",
        ROOT / "scripts" / "river_analytical.py",
        ARCHIVE_REPORT,
        ARCHIVE_POLICIES / "river-polarised-bluffcatcher-matrix-free-10000.json",
    )
    for path in extra:
        result[path.relative_to(ROOT).as_posix()] = _digest(path.read_bytes())
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks" / "results" /
                        "river-cfrplus-long-budget-v1.json")
    parser.add_argument("--policies-dir", type=Path, default=OUTPUT_POLICY_DIR)
    args = parser.parse_args(argv)

    case = _fixture()
    archived_policy, archive_provenance = _baseline(case)
    before = _fingerprints()
    args.policies_dir.mkdir(parents=True, exist_ok=True)
    (args.policies_dir / ".gitattributes").write_bytes(b"*.json text eol=lf\n")
    rows = []
    for iterations in ITERATIONS:
        started = time.perf_counter()
        result = solve_matrix_free_river(
            case["board"], case["oop"], case["ip"], case["config"],
            iterations=iterations, algorithm="cfrplus",
        )
        complete_call_seconds = time.perf_counter() - started
        if result["iterations"] != iterations:
            raise ValueError("Fixed-iteration call completed an unexpected sweep count")
        if iterations == 10_000 and result != archived_policy:
            raise ValueError("Fresh 10k complete payload differs from the hash-checked archived policy")

        oracle = replay_policy(result, case["oop"], case["ip"],
                               board=case["board"], config=case["config"])
        scalar_differences = compare_result(result, oracle, tolerance=1e-9)
        witness = rational_polarised(result, case)
        filename = f"river-polarised-bluffcatcher-matrix-free-{iterations}.json"
        payload = _portable_json(result)
        policy_path = args.policies_dir / filename
        policy_path.write_bytes(payload)

        # Re-read the committed-format bytes before the final replay.
        saved = policy_path.read_bytes()
        policy_hash = _digest(saved)
        if saved != payload:
            raise RuntimeError("Saved policy bytes differ from the serialized solve")
        loaded = json.loads(saved)
        post_save_oracle = replay_policy(
            loaded, case["oop"], case["ip"], board=case["board"],
            config=case["config"],
        )
        post_save_differences = compare_result(loaded, post_save_oracle, tolerance=1e-9)
        if loaded != result:
            raise ValueError("Saved policy payload differs from its complete solve")
        if post_save_differences != scalar_differences:
            raise ValueError("Saved-policy replay differs from the in-memory replay")

        rows.append({
            "scenario": case["id"], "backend": "matrix-free",
            "algorithm": "cfrplus", "iterations_requested": iterations,
            "iterations_completed": result["iterations"],
            "configured_solver_target_exploitability": None,
            "benchmark_nash_conv_threshold": BENCHMARK_THRESHOLD,
            "benchmark_threshold_met": oracle["nash_conv"] <= BENCHMARK_THRESHOLD,
            "metrics": {field: oracle[field] for field in (
                "value_oop", "value_ip", "oop_best_response_value",
                "ip_best_response_value", "oop_best_response_gain",
                "ip_best_response_gain", "nash_conv", "exploitability")},
            "scalar_differences": scalar_differences,
            "verified_worlds": oracle["worlds"],
            "verified_compatible_pairs": oracle["compatible_pair_count"],
            "verified_information_sets": oracle["checked_information_sets"],
            "public_states": result["public_states"],
            "hand_state_pass_work": result["resource_usage"]["hand_state_pass_work"],
            "complete_call_seconds_uncontrolled": complete_call_seconds,
            "policy_file": filename, "policy_sha256": policy_hash,
            "saved_policy_replayed": True,
            "matches_archived_10k_complete_payload": (
                result == archived_policy if iterations == 10_000 else None
            ),
            "exact_normalized_rational_witness": witness,
        })
        print(iterations, f"nash_conv={oracle['nash_conv']:.12g}", flush=True)

    if _fingerprints() != before:
        raise RuntimeError("Production/helper/config/archive source changed during benchmark")
    report = {
        "schema_version": 1,
        "benchmark_id": "river-cfrplus-long-budget-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": platform.platform(),
        "source_sha256": before,
        "archived_10k_baseline": archive_provenance,
        "fixture": case,
        "methodology": {
            "selection": "One predeclared existing polarised bluff-catcher river fixture; matrix-free CFR+ only.",
            "budget": "Fixed complete calls at 10000, 30000 and 100000 sweeps; no target-based early stopping and no adaptive extension.",
            "accuracy": "Every complete policy independently replayed for numeric rules, physical worlds, all eight diagnostics and exact legal visible-information best responses.",
            "baseline": "The 10000-sweep fresh result must exactly equal the decoded complete payload whose raw bytes are hash-checked against the prior extension report.",
            "rational_witness": "The existing normalized-binary64 Fraction witness independently enumerates five terminal histories and 16 OOP / 4 IP legal pure responses; it requires known value 25 in the BR interval and records row-normalization adjustment and witness NashConv.",
            "threshold": "The 0.001-chip NashConv value is the predeclared reporting benchmark threshold; configured solver stop target is null for every fixed call.",
            "timing": "One complete-call observation per fixed budget on this host; uncontrolled, with no speed, runtime-generalization or RSS claim.",
        },
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_portable_json(report))
    print("Verified and saved", len(rows), "fixed-budget policies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
