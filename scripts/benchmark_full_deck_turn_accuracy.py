"""Fixed-budget independent replay for one full-deck turn game.

This bounded benchmark compares six complete CFR+ profiles on the frozen
full44-blocked-runouts fixture. Its NashConv threshold is for reporting only;
the solver receives no convergence target.
"""
import argparse
import hashlib
import json
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from pokerlab.river_config import RiverConfig
from scripts import turn_river_validation as validator
from scripts.benchmark_turn_river_independent import CONFIG, ROOT, solve, source_hashes
from scripts.turn_river_validation import compare_result, replay_policy


ITERATIONS = (1_000, 1_500, 3_000)
BACKENDS = ("materialized", "matrix-free")
ALGORITHM = "cfrplus"
BENCHMARK_NASH_CONV_THRESHOLD = 0.001
EXPECTED_CASE = {
    "id": "full44-blocked-runouts",
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
}
EXPECTED_WORLDS = 176
EXPECTED_PAIRS = 4
EXPECTED_CANDIDATE_RUNOUTS = 48
EXPECTED_REACHABLE_RUNOUTS = 48
EXPECTED_INFORMATION_SETS = 1_112
EXPECTED_PUBLIC_STATES = 1_305
EXPECTED_PUBLIC_DECISION_NODES = 580
EXPECTED_MATERIALIZED_TRAVERSAL_NODES = 16
EXPECTED_MATRIX_HAND_COUNTS = [2, 2]
EXPECTED_MATRIX_HAND_SLOTS = 184
EXPECTED_MATRIX_ACTION_SLOTS = 2_224
EXPECTED_MATRIX_FOLD_TERMINALS = 2
MAX_WORLD_NODE_WORK = 30_000_000
MAX_MATRIX_LIMITS = {
    "hand_state_pass_work": 30_000_000,
    "info_action_slots": 1_000_000,
    "fallback_pair_checks": 30_000_000,
    "hand_slots": 120_000,
    "public_states": 250_000,
    "public_nodes": 10_000,
}
METRIC_FIELDS = (
    "value_oop", "value_ip", "oop_best_response_value",
    "ip_best_response_value", "oop_best_response_gain",
    "ip_best_response_gain", "nash_conv", "exploitability",
)
FLOAT_TOLERANCE = 1e-9


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) +
            "\n").encode("utf-8")


def frozen_case():
    specification = json.loads(CONFIG.read_text(encoding="utf-8"))
    matches = [case for case in specification["scenarios"]
               if case.get("id") == EXPECTED_CASE["id"]]
    if len(matches) != 1:
        raise ValueError("Expected exactly one frozen full-deck turn fixture")
    case = matches[0]
    for field, value in EXPECTED_CASE.items():
        if case.get(field) != value:
            raise ValueError("Full-deck fixture changed from the predeclared case: " + field)
    if "runouts" in case:
        raise ValueError("Full-deck fixture must omit selected runouts")
    return case


def _fingerprints():
    values = source_hashes()
    runner = Path(__file__).resolve()
    values[runner.relative_to(ROOT).as_posix()] = _sha256(runner.read_bytes())
    return dict(sorted(values.items()))


def _full_deck_candidates(case):
    board = validator.cards(case["board"])
    return [card for card in validator.DECK if card not in board]


def expected_work(backend, iterations):
    """Fixed-call modeled work, excluding replay and without target checks."""
    if type(iterations) is not int or iterations <= 0:
        raise ValueError("iterations must be a positive exact integer")
    if backend == "matrix-free":
        # Two original hands at most, 1305 kernel public states, three CFR+
        # passes each sweep, plus three modeled final diagnostic passes.
        return 2 * EXPECTED_PUBLIC_STATES * (3 * iterations + 3)
    if backend == "materialized":
        # 176 physical worlds, 16 visited nodes per world, three CFR+ passes.
        return (EXPECTED_WORLDS * EXPECTED_MATERIALIZED_TRAVERSAL_NODES *
                iterations * 3)
    raise ValueError("Unknown full-deck turn backend")


def validate_profile_metadata(result, case, backend, iterations):
    """Reject a changed fixture, solver mode, traversal count or work model."""
    if backend not in BACKENDS:
        raise ValueError("Unknown full-deck turn backend")
    if type(iterations) is not int or iterations <= 0:
        raise ValueError("iterations must be a positive exact integer")
    if result.get("algorithm") != ALGORITHM:
        raise ValueError("Full-deck profile must use CFR+")
    if type(result.get("iterations")) is not int or result["iterations"] != iterations:
        raise ValueError("Profile did not complete the fixed requested sweep count")
    if "convergence" in result:
        raise ValueError("Fixed-budget profile must not configure a solver stop target")

    board = [case["board"][index:index + 2]
             for index in range(0, len(case["board"]), 2)]
    if result.get("board") != board:
        raise ValueError("Full-deck result board differs from the frozen fixture")
    candidates = _full_deck_candidates(case)
    if result.get("runouts") != candidates:
        raise ValueError("Result must declare the complete canonical DECK-ordered runout list")
    if result.get("runout_mode") != "full-deck":
        raise ValueError("Full-deck result has the wrong runout mode")
    reachable = result.get("reachable_runouts")
    lexical = sorted(candidates)
    if (type(reachable) is not list or
            any(type(card) is not str for card in reachable) or
            len(set(reachable)) != len(reachable) or
            reachable not in (candidates, lexical)):
        raise ValueError("Reachability must use a canonical full 48-card order")
    if len(candidates) != EXPECTED_CANDIDATE_RUNOUTS or len(reachable) != EXPECTED_REACHABLE_RUNOUTS:
        raise ValueError("Full-deck candidate or reachable-river count changed")

    turn = RiverConfig.from_dict(case["config"]).to_dict()
    river = RiverConfig.from_dict(case["river_config"]).to_dict()
    if (result.get("config") != turn or result.get("turn_config") != turn or
            result.get("river_config") != river or
            result.get("street_configs") != {"turn": turn, "river": river}):
        raise ValueError("Full-deck turn/river sizing metadata differs from fixture")
    if type(result.get("info_sets")) is not int or result["info_sets"] != EXPECTED_INFORMATION_SETS:
        raise ValueError("Information-set count differs from the full-deck fixture")
    if type(result.get("public_states")) is not int or result["public_states"] != EXPECTED_PUBLIC_STATES:
        raise ValueError("Aggregate public-state count differs from the full-deck fixture")
    if (type(result.get("public_nodes")) is not int or
            result["public_nodes"] != EXPECTED_PUBLIC_DECISION_NODES):
        raise ValueError("Public decision-node count differs from independent fixture census")
    if type(result.get("training_passes_per_iteration")) is not int or result["training_passes_per_iteration"] != 3:
        raise ValueError("CFR+ training pass metadata differs from the fixed schedule")
    if result.get("update_schedule") != "alternating-oop-then-ip" or result.get(
            "average_schedule") != "linear-post-sweep-own-reach":
        raise ValueError("CFR+ update or average schedule changed")

    if backend == "matrix-free":
        if (result.get("execution_backend") != "matrix-free-ranked-python" or
                result.get("terminal_backend") != "ranked-turn-python"):
            raise ValueError("Matrix-free execution or terminal backend changed")
        if (type(result.get("compatible_world_count")) is not int or
                result["compatible_world_count"] != EXPECTED_WORLDS):
            raise ValueError("Matrix-free compatible-world count differs from fixture")
        if (type(result.get("worlds_materialized")) is not int or
                result["worlds_materialized"] != 0):
            raise ValueError("Matrix-free result must not materialize physical worlds")
        usage = result.get("resource_usage")
        if not isinstance(usage, dict):
            raise ValueError("Matrix-free resource usage is missing")
        expected = expected_work(backend, iterations)
        if type(usage.get("hand_state_pass_work")) is not int or usage[
                "hand_state_pass_work"] != expected:
            raise ValueError("Matrix-free fixed-request work charge differs from model")
        fixed_counts = {
            "hand_slots": EXPECTED_MATRIX_HAND_SLOTS,
            "kernel_public_states": EXPECTED_PUBLIC_STATES,
            "turn_fold_terminals": EXPECTED_MATRIX_FOLD_TERMINALS,
            "info_action_slots": EXPECTED_MATRIX_ACTION_SLOTS,
            "fallback_pair_checks": 0,
            "compatible_world_count": EXPECTED_WORLDS,
        }
        for name, expected_count in fixed_counts.items():
            if type(usage.get(name)) is not int or usage[name] != expected_count:
                raise ValueError("Matrix-free resource count changed: " + name)
        if usage.get("hand_counts") != EXPECTED_MATRIX_HAND_COUNTS:
            raise ValueError("Matrix-free original hand counts differ from fixture")
        limits = usage.get("limits")
        if limits != MAX_MATRIX_LIMITS:
            raise ValueError("Matrix-free resource limits differ from fixed repository caps")
        counts = {
            "hand_state_pass_work": usage["hand_state_pass_work"],
            "info_action_slots": usage["info_action_slots"],
            "fallback_pair_checks": usage["fallback_pair_checks"],
            "hand_slots": usage["hand_slots"],
            "public_states": result["public_states"],
            "public_nodes": result["public_nodes"],
        }
        for name, count in counts.items():
            if type(count) is not int or count < 0 or count > limits[name]:
                raise ValueError("Matrix-free resource cap exceeded: " + name)
        if "stable_root_fold_pair_checks" in usage:
            checks = usage.get("stable_root_fold_pair_checks")
            limit = usage.get("stable_root_fold_pair_limit")
            if (type(checks) is not int or checks < 0 or type(limit) is not int or
                    limit < 0 or checks > limit):
                raise ValueError("Matrix-free stable-root pair cap exceeded")
        if "exceptional_root_fold_pass_work" in usage:
            raise ValueError("Frozen ordinary fixture unexpectedly used exceptional root folds")
    else:
        if (result.get("execution_backend") != "public-batched-python" or
                result.get("diagnostics_backend") != "public-batched-python" or
                "terminal_backend" in result):
            raise ValueError("Materialized public-batched backend metadata changed")
        if type(result.get("worlds")) is not int or result["worlds"] != EXPECTED_WORLDS:
            raise ValueError("Materialized physical-world count differs from fixture")
        if (type(result.get("compatible_pairs")) is not int or
                result["compatible_pairs"] != EXPECTED_PAIRS):
            raise ValueError("Materialized compatible-pair count differs from fixture")
        if (type(result.get("world_traversal_nodes")) is not int or
                result["world_traversal_nodes"] != EXPECTED_MATERIALIZED_TRAVERSAL_NODES):
            raise ValueError("Materialized per-world traversal-node count differs from fixture")
        if type(result.get("public_state_limit")) is not int or result[
                "public_state_limit"] != 250_000:
            raise ValueError("Materialized public-state limit changed")
        work = expected_work(backend, iterations)
        if work > MAX_WORLD_NODE_WORK:
            raise ValueError("Materialized fixed-request work exceeds 30 million")


def _replay(result, case):
    # Intentionally omit runouts: this is the entire remaining river deck.
    return replay_policy(
        result, case["oop"], case["ip"], board=case["board"],
        config=case["config"], river_config=case["river_config"],
    )


def _accepted_replay(result, case, backend, iterations):
    validate_profile_metadata(result, case, backend, iterations)
    original = _canonical_json(result)
    oracle = _replay(result, case)
    differences = compare_result(result, oracle, tolerance=FLOAT_TOLERANCE)
    if (oracle["worlds"] != EXPECTED_WORLDS or
            oracle["compatible_pair_count"] != EXPECTED_PAIRS or
            oracle["checked_information_sets"] != EXPECTED_INFORMATION_SETS or
            oracle["public_node_count"] != 580):
        raise ValueError("Independent replay counts differ from the full-deck fixture")
    if _canonical_json(result) != original:
        raise RuntimeError("Independent replay mutated its complete policy input")
    return oracle, differences


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks" / "results" /
                        "full-deck-turn-accuracy-v1.json")
    parser.add_argument("--policies-dir", type=Path, default=ROOT / "benchmarks" /
                        "results" / "full-deck-turn-accuracy-policies-v1")
    args = parser.parse_args(argv)

    before = _fingerprints()
    case = frozen_case()
    candidates = _full_deck_candidates(case)
    baseline_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    args.policies_dir.mkdir(parents=True, exist_ok=True)
    (args.policies_dir / ".gitattributes").write_bytes(b"*.json text eol=lf\n")

    rows = []
    for backend in BACKENDS:
        for iterations in ITERATIONS:
            started = time.perf_counter()
            # solve() omits the runouts argument because this frozen case has
            # no runouts key; all remaining river cards stay in the game.
            result = solve(case, backend, ALGORITHM, iterations)
            complete_seconds = time.perf_counter() - started
            oracle, differences = _accepted_replay(result, case, backend, iterations)

            filename = f"{case['id']}-{backend}-{iterations}.json"
            path = args.policies_dir / filename
            payload = _canonical_json(result)
            path.write_bytes(payload)
            saved = path.read_bytes()
            policy_hash = _sha256(saved)
            if saved != payload or b"\r" in saved:
                raise RuntimeError("Saved policy is not the exact portable LF solve payload")
            loaded = json.loads(saved)
            saved_oracle, saved_differences = _accepted_replay(
                loaded, case, backend, iterations)
            if loaded != result or saved_differences != differences:
                raise ValueError("Reloaded full policy differs from accepted in-memory replay")

            rows.append({
                "scenario": case["id"], "backend": backend,
                "algorithm": ALGORITHM, "iterations_requested": iterations,
                "iterations_completed": result["iterations"],
                "configured_solver_target_exploitability": None,
                "benchmark_nash_conv_threshold": BENCHMARK_NASH_CONV_THRESHOLD,
                "benchmark_threshold_met": (
                    oracle["nash_conv"] <= BENCHMARK_NASH_CONV_THRESHOLD),
                "metrics": {name: oracle[name] for name in METRIC_FIELDS},
                "scalar_differences": differences,
                "verified_worlds": oracle["worlds"],
                "verified_compatible_pairs": oracle["compatible_pair_count"],
                "verified_information_sets": oracle["checked_information_sets"],
                "independent_public_decision_nodes": oracle["public_node_count"],
                "candidate_runout_count": len(candidates),
                "reachable_runout_count": len(result["reachable_runouts"]),
                "public_states": result["public_states"],
                "public_nodes": result["public_nodes"],
                "world_traversal_nodes": result.get("world_traversal_nodes"),
                "worlds_materialized": result.get(
                    "worlds_materialized", result.get("worlds", 0)),
                "work_charge": expected_work(backend, iterations),
                "work_limit": (MAX_MATRIX_LIMITS["hand_state_pass_work"]
                               if backend == "matrix-free" else MAX_WORLD_NODE_WORK),
                "complete_call_seconds_uncontrolled": complete_seconds,
                "policy_file": filename, "policy_sha256": policy_hash,
                "saved_policy_replayed": True,
            })
            print(backend, iterations,
                  f"nash_conv={oracle['nash_conv']:.12g}", flush=True)

    after = _fingerprints()
    if after != before:
        raise RuntimeError("Production, helper, oracle, fixture or runner changed during full-deck run")
    report = {
        "schema_version": 1,
        "benchmark_id": "full-deck-turn-accuracy-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_git_commit": baseline_commit,
        "python": platform.python_version(), "platform": platform.platform(),
        "source_sha256": before,
        "fixture": case,
        "methodology": {
            "design": "Both existing turn backends, CFR+ only, fixed complete calls at 1000/1500/3000 sweeps; all six profiles retained.",
            "conditioning": "No runouts argument is supplied. Each compatible private pair receives its full remaining 44-card river set; the resulting game has 176 physical worlds over four compatible pairs.",
            "validation": "Every complete policy passes unchanged independent full-deck replay and compare_result for all eight metrics/counts before and after UTF-8 LF saving.",
            "threshold": "The 0.001-chip NashConv value is a predeclared reporting benchmark threshold; fixed calls configure no solver stopping target.",
            "resource_models": "Matrix-free uses max original hand count × 1305 kernel public states × (three CFR+ passes per sweep plus three final diagnostic passes). Materialized uses 176 worlds × 16 per-world traversal nodes × three CFR+ passes. Aggregate public-state counts are not substituted for per-world traversal nodes.",
            "replay_admission": "The independent validator sees 580 public decision nodes; its conservative 580 × 176 × 4 work estimate is 408960, below its 8 million cap.",
            "timing": "One complete-call timing per profile on a shared host; uncontrolled observation only, with no speed, memory or RSS claim.",
            "limitations": "One finite full-deck turn abstraction with the frozen two-by-two weighted ranges and no raises. Results do not establish general convergence, a closed-form equilibrium, unrestricted Hold'em quality or performance improvement.",
        },
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_json(report))
    print("Verified and saved", len(rows), "full-deck turn profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
