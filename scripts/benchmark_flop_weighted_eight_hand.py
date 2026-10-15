"""Frozen weighted 8x8 direct-flop checkdown accuracy and work benchmark.

All fixture/checkpoint admissions are intercepted immediately before the
production plan ranks future boards. Only after all six preflights finish may
production calls or the independent replay begin.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import inspect
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

from pokerlab.cards import DECK, cards, expand_range
from pokerlab.flop_checkdown_solver import solve_flop_checkdown
from pokerlab.flop_checkdown_worlds import FlopCheckdownPlan, prepare_flop_worlds
from scripts.flop_checkdown_validation import prepare_oracle, replay

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "benchmarks/flop-weighted-eight-hand-v1.json"
OUTPUT_PATH = ROOT / "benchmarks/results/flop-weighted-eight-hand-v1.json"
POLICY_DIR = ROOT / "benchmarks/results/flop-weighted-eight-hand-v1-policies"
POLICY_STAGING_DIR = ROOT.parent / "flop-weighted-eight-hand-policy-staging"
LIVE_PATH = ROOT.parent / "flop-weighted-eight-hand-live.json"
_EXPECTED_FIXTURE_IDS = (
    "weighted-8x8-stack12-raises1",
    "weighted-8x8-stack24-raises2",
)
_EXPECTED_OOP = "AsAd:1,QhJh:.5,7s6s:.25,Tc9c:.75,KsQd:.375,Ac5c:.625,8h8d:.875,ThTs:.125"
_EXPECTED_IP = "KsKd:.75,AhKh:1,8s7s:.5,QcQd:.25,AdJd:.375,6h5h:.625,9d8d:.875,JcTc:.125"
_EXPECTED_SPEC_SHA256 = "f38d617c931076acce4aca31ad22d48d013d4e3207a949fa65edcb2bc5fde177"
_DECK_ORDER = {card: index for index, card in enumerate(DECK)}
_KNOWN_RESOURCE_ERRORS = (
    "Flop checkdown candidate pair limit exceeded before ranking.",
    "Flop checkdown compatible pair limit exceeded before ranking.",
    "Flop checkdown unordered board evaluation limit exceeded before ranking.",
    "Direct flop tree exceeds the 25,000-state cap",
    "Direct flop information-action cap exceeded",
    "Vector budget information-set action slots exceed 1,000,000",
    "Vector budget prefix edges exceed 250,000",
    "Vector budget dense prefix slots exceed 2,000,000",
    "Vector budget estimated loop entries exceed 500,000,000",
    "Direct flop combined modeled work exceeds 500,000,000",
)


class _ReachedRankingBoundary(Exception):
    """Internal sentinel raised before a FlopCheckdownPlan ranks any board."""

    def __init__(self, census):
        self.census = census


def _raw_chance_census(fixture):
    """Independently recompute represented-float blocker mass without ranking."""
    board = tuple(sorted(cards(fixture["board"], 3), key=_DECK_ORDER.__getitem__))
    ranges = (expand_range(fixture["oop_range"], board),
              expand_range(fixture["ip_range"], board))
    units = []
    for rows in ranges:
        player_units = {}
        for hand, weight in rows.items():
            scaled = Fraction.from_float(weight) * 8
            if scaled.denominator != 1:
                raise AssertionError("Frozen range weights must be eighths")
            player_units[hand] = scaled.numerator
        units.append(player_units)
    raw_total = sum((Fraction.from_float(wa) * Fraction.from_float(wb)
                     for a, wa in ranges[0].items()
                     for b, wb in ranges[1].items()
                     if set(a).isdisjoint(b)), Fraction())
    oop_marginals = []
    for hand, wa in ranges[0].items():
        mass = sum((Fraction.from_float(wa) * Fraction.from_float(wb)
                    for b, wb in ranges[1].items()
                    if set(hand).isdisjoint(b)), Fraction())
        oop_marginals.append(mass / raw_total)
    ip_marginals = []
    for hand, wb in ranges[1].items():
        mass = sum((Fraction.from_float(wa) * Fraction.from_float(wb)
                    for a, wa in ranges[0].items()
                    if set(a).isdisjoint(hand)), Fraction())
        ip_marginals.append(mass / raw_total)
    return {
        "candidate_pairs": len(ranges[0]) * len(ranges[1]),
        "compatible_pairs": sum(1 for a in ranges[0] for b in ranges[1]
                                 if set(a).isdisjoint(b)),
        "raw_compatible_weight_normalizer": raw_total,
        "oop_marginals": tuple(oop_marginals),
        "ip_marginals": tuple(ip_marginals),
        "range_units": units,
    }


def validate_spec(spec):
    """Validate exact fixture shape and blocker census without evaluating boards."""
    if not isinstance(spec, dict) or spec.get("schema_version") != 1:
        raise ValueError("Unsupported weighted eight-hand specification")
    encoded = json.dumps(spec, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if hashlib.sha256(encoded).hexdigest() != _EXPECTED_SPEC_SHA256:
        raise ValueError("Frozen specification hash changed")
    if (spec.get("benchmark_id") != "flop-weighted-eight-hand-v1"
            or spec.get("baseline_main") != "22b754848d7884eb5f63062b3d4e9c7612b771f1"):
        raise ValueError("Unexpected benchmark id")
    if spec.get("algorithm") != "cfrplus" or spec.get("checkpoints") != [100, 1000, 4000]:
        raise ValueError("Frozen algorithm/checkpoints changed")
    if (spec.get("intermediate_timed_repeats") != 1
            or spec.get("final_timed_repeats") != 3
            or spec.get("allocation_iterations") != 4000):
        raise ValueError("Frozen timing and allocation protocol changed")
    fixtures = spec.get("fixtures")
    if not isinstance(fixtures, list) or tuple(f.get("id") for f in fixtures) != _EXPECTED_FIXTURE_IDS:
        raise ValueError("Frozen weighted fixtures are missing, reordered, or renamed")
    expected_chance = spec.get("expected_chance", {})
    expected = {
        "candidate_pairs": 64,
        "compatible_pairs": 58,
        "unordered_boards": 57_420,
        "ordered_future_worlds": 114_840,
        "categorical_rows_upper_bound": 174,
        "compatible_weight_normalizer": "1185/64",
        "compatible_weight_unit_total": 1185,
        "oop_marginal_numerators": [264, 144, 64, 210, 84, 180, 203, 36],
        "ip_marginal_numerators": [198, 288, 136, 66, 84, 180, 203, 30],
    }
    if expected_chance != expected:
        raise ValueError("Frozen physical chance/prior census changed")
    for index, fixture in enumerate(fixtures):
        if (fixture.get("board") != "2c3c4d"
                or fixture.get("oop_range") != _EXPECTED_OOP
                or fixture.get("ip_range") != _EXPECTED_IP):
            raise ValueError("Frozen board or weighted range changed")
        config = fixture.get("config", {})
        wanted_stack = (12, 24)[index]
        wanted_raises = (1, 2)[index]
        if (config.get("pot") != 6
                or config.get("effective_stack") != wanted_stack
                or config.get("bet_sizes") != [0.5, 1]
                or config.get("raise_sizes") != [0.5]
                or config.get("max_raises") != wanted_raises
                or config.get("include_all_in") is not True
                or fixture.get("target_nash_conv") != 0.005
                or fixture.get("required_4000_admission") is not True
                or fixture.get("required_4000_accuracy") is not True
                or (index == 0 and "required_action_coverage" in fixture)
                or (index == 1 and fixture.get("required_action_coverage") != [
                    "oop-lead-bet-ip-raise-oop-reraise",
                    "oop-check-ip-bet-oop-checkraise-ip-reraise"])):
            raise ValueError("Frozen action tree or quality gate changed")
        census = _raw_chance_census(fixture)
        if (census["candidate_pairs"] != expected["candidate_pairs"]
                or census["compatible_pairs"] != expected["compatible_pairs"]
                or census["raw_compatible_weight_normalizer"] != Fraction(1185, 64)):
            raise ValueError("Independent blocker-conditioned prior census mismatch")
        if census["oop_marginals"] != tuple(Fraction(n, 1185) for n in expected["oop_marginal_numerators"]):
            raise ValueError("OOP exact compatible marginal census mismatch")
        if census["ip_marginals"] != tuple(Fraction(n, 1185) for n in expected["ip_marginal_numerators"]):
            raise ValueError("IP exact compatible marginal census mismatch")
        plan = prepare_flop_worlds(fixture["board"], fixture["oop_range"], fixture["ip_range"])
        if (plan.budget["candidate_pairs"] != expected["candidate_pairs"]
                or plan.budget["compatible_pairs"] != expected["compatible_pairs"]
                or plan.budget["unordered_boards"] != expected["unordered_boards"]
                or plan.budget["physical_worlds"] != expected["ordered_future_worlds"]
                or plan.budget["grouped_rows_upper_bound"] != expected["categorical_rows_upper_bound"]):
            raise ValueError("Production plan census differs from the independent no-rank census")
        expected_priors = {
            (i, j): Fraction(census["range_units"][0][a]
                             * census["range_units"][1][b], 1185)
            for i, a in enumerate(plan.hands[0])
            for j, b in enumerate(plan.hands[1])
            if set(a).isdisjoint(b)
        }
        actual_keys = [(i, j) for i, j, _ in plan.pairs]
        if len(actual_keys) != len(expected_priors) or set(actual_keys) != set(expected_priors):
            raise ValueError("Production plan private-pair support differs from independent census")
        if any(prior != expected_priors[(i, j)] for i, j, prior in plan.pairs):
            raise ValueError("Exact joint pair priors differ from the frozen unit census")
    if not isinstance(spec.get("scalar_tolerance"), (int, float)) or spec["scalar_tolerance"] != 1e-10:
        raise ValueError("Independent scalar tolerance changed")
    if spec.get("target_padding") != 1e-10:
        raise ValueError("Target padding changed")
    return {"candidate_pairs": 64, "compatible_pairs": 58,
            "unordered_boards": 57_420, "ordered_future_worlds": 114_840,
            "categorical_rows_upper_bound": 174,
            "compatible_weight_normalizer": "1185/64"}


def _capture_prebuild_census(self):
    frame = inspect.currentframe().f_back
    local = frame.f_locals
    plan = local.get("plan")
    counts = local.get("counts")
    infos = local.get("infos")
    if plan is None or counts is None or infos is None or "budget" not in local:
        raise RuntimeError("Unexpected production plan-build boundary; census locals missing")
    census = {
        "solver_budget": local["budget"],
        "plan_budget": dict(plan.budget),
        "tree": {"decision_nodes": local["decisions"],
                 "decision_states": counts["decision"],
                 "terminal_nodes": counts["terminal"],
                 "public_states": sum(counts.values()),
                 "information_sets": len(infos),
                 "information_action_slots": local["slots"]},
        "ranking_started": False,
        "boundary": "FlopCheckdownPlan.build before any board enumeration",
    }
    raise _ReachedRankingBoundary(census)


def _is_known_resource_failure(exc):
    return any(token in str(exc) for token in _KNOWN_RESOURCE_ERRORS)


def preflight(fixture, iterations, algorithm):
    """Run solver preflights and intercept its exact build boundary before rank."""
    if algorithm != "cfrplus" or type(iterations) is not int or iterations not in (100, 1000, 4000):
        raise ValueError("Preflight requires a frozen CFR+ checkpoint")
    try:
        with patch.object(FlopCheckdownPlan, "build", _capture_prebuild_census):
            solve_flop_checkdown(fixture["board"], fixture["oop_range"], fixture["ip_range"],
                                 config=fixture["config"], iterations=iterations,
                                 algorithm=algorithm)
    except _ReachedRankingBoundary as stopped:
        census = stopped.census
        return {"fixture_id": fixture["id"], "iterations": iterations,
                "algorithm": algorithm, "status": "admitted", **census}
    except ValueError as exc:
        if not _is_known_resource_failure(exc):
            raise
        return {"fixture_id": fixture["id"], "iterations": iterations,
                "algorithm": algorithm, "status": "rejected",
                "resource_failure": str(exc), "ranking_started": False}
    raise RuntimeError("Preflight unexpectedly returned past the ranking boundary")


def preflight_all(spec, progress=None):
    """Finish every fixture/checkpoint preflight before any ranking or training."""
    results = []
    for fixture in spec["fixtures"]:
        for iterations in spec["checkpoints"]:
            outcome = preflight(fixture, iterations, spec["algorithm"])
            results.append(outcome)
            if progress is not None:
                progress({"phase": "preflight", "completed": len(results),
                          "total": len(spec["fixtures"]) * len(spec["checkpoints"]),
                          "latest": outcome, "all_preflights_complete": False})
    if len(results) != 6:
        raise AssertionError("The benchmark must complete exactly six preflights")
    return results


def action_coverage(result):
    """Find ordered non-all-in raise sequences in the serialized public policy."""
    stacks = result.get("config", {}).get("effective_stack", 0)
    oop_stack = float(stacks[0] if isinstance(stacks, (list, tuple)) else stacks)
    pair_rows = result.get("pair_equities", [])
    expected_board = tuple(result.get("board", ()))
    rows = {(row["player"], row["hand"], tuple(row["history"])): row
            for row in result.get("strategy", [])
            if row.get("street") == "flop"
            and tuple(row.get("board", ())) == expected_board}

    def path_for(pair, specs):
        hands = {"oop": pair["oop_hand"], "ip": pair["ip_hand"]}
        history = ()
        witness = []
        for expected_player, action_name, require_nonallin in specs:
            row = rows.get((expected_player, hands[expected_player], history))
            if row is None:
                return None
            chosen = None
            for action in row["actions"]:
                if action["name"] != action_name:
                    continue
                target = action.get("raise_to")
                if require_nonallin and (target is None or float(target) >= oop_stack - 1e-9):
                    continue
                chosen = action
                break
            if chosen is None:
                return None
            witness.append({"player": expected_player, "hand": hands[expected_player],
                            "history": list(history),
                            "action": {k: chosen.get(k) for k in
                                       ("name", "amount", "raise_to", "history_key")}})
            history = history + (chosen["history_key"],)
        return witness

    declarations = {
        "oop-lead-bet-ip-raise-oop-reraise":
            (("oop", "bet", True), ("ip", "raise", True), ("oop", "raise", True)),
        "oop-check-ip-bet-oop-checkraise-ip-reraise":
            (("oop", "check", False), ("ip", "bet", True),
             ("oop", "raise", True), ("ip", "raise", True)),
    }
    found = {}
    for name, specs in declarations.items():
        witness = next((candidate for pair in pair_rows
                        if (candidate := path_for(pair, specs)) is not None), None)
        found[name] = {"covered": witness is not None, "witness": witness}
    return {"required_sequences": found,
            "all_required_covered": all(item["covered"] for item in found.values()),
            "effective_oop_stack": oop_stack}


def _source_paths():
    paths = {path.relative_to(ROOT).as_posix() for path in (ROOT / "pokerlab").glob("*.py")}
    paths.update({
        "AGENTS.md",
        "scripts/preflop_validation.py",
        "scripts/flop_checkdown_validation.py",
        "scripts/benchmark_direct_flop_checkdown.py",
        "scripts/benchmark_flop_weighted_eight_hand.py",
        "benchmarks/flop-weighted-eight-hand-v1.json",
        "tests/test_flop_checkdown_solver.py",
        "tests/test_flop_checkdown_worlds.py",
        "tests/test_flop_weighted_eight_hand.py",
    })
    return tuple(sorted(paths))


def _hashes():
    return {path: __import__("hashlib").sha256((ROOT / path).read_bytes()).hexdigest()
            for path in _source_paths()}


def _revision():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _is_clean():
    return subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip() == ""


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")
    temp.replace(path)


def _canonical_json_sha256(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _measured(fixture, spec, oracle, iterations, expected_budget, trace=False, include_coverage=False, preserve_result=False):
    gc.collect()
    if trace:
        tracemalloc.start()
    started = time.perf_counter()
    try:
        result = solve_flop_checkdown(fixture["board"], fixture["oop_range"], fixture["ip_range"],
                                      config=fixture["config"], iterations=iterations,
                                      algorithm=spec["algorithm"])
        payload = json.dumps(result, allow_nan=False, separators=(",", ":"))
    finally:
        elapsed = time.perf_counter() - started
        peak = None
        if trace:
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
    if result["work_budget"] != expected_budget:
        raise AssertionError("Measured work budget differs from preflight census")
    checked = replay(result, oracle, spec["scalar_tolerance"])
    target_met = checked["nash_conv"] + spec["target_padding"] <= fixture["target_nash_conv"]
    row = {"iterations": iterations, "complete_call_plus_json_seconds": elapsed,
           "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
           "verification": checked, "target_met": target_met,
           "work_budget": result["work_budget"],
           "game": {key: result[key] for key in
                    ("compatible_pairs", "physical_worlds", "training_world_rows",
                     "info_sets", "public_nodes", "public_states", "terminal_nodes")},
           "pair_equities": result["pair_equities"],
           "work_budget_matches_preflight": True}
    if trace:
        row["traced_peak_bytes"] = peak
    if include_coverage:
        row["action_coverage"] = action_coverage(result)
    if preserve_result:
        row["serialized_policy_result"] = result
    print(f"{fixture['id']} T={iterations} trace={trace} seconds={elapsed:.6f} "
          f"gap={checked['nash_conv']:.12g} target={target_met}", flush=True)
    return row


def run(spec=None):
    """Run after freeze: all six no-rank preflights, then oracle and measurements."""
    if spec is None:
        spec = json.loads(SPEC_PATH.read_text(encoding="utf-8-sig"))
    validate_spec(spec)
    if not _is_clean():
        raise RuntimeError("Freeze and commit benchmark source/config before measurement")
    revision = _revision()
    if subprocess.run(["git", "merge-base", "--is-ancestor", spec["baseline_main"], revision],
                      cwd=ROOT, check=False).returncode:
        raise ValueError("Benchmark baseline is not an ancestor of the measured revision")
    before = _hashes()
    progress = {"benchmark_id": spec["benchmark_id"], "source_revision": revision,
                "phase": "starting", "completed_preflights": [], "results": [],
                "complete": False}
    def record_preflight(event):
        progress["completed_preflights"].append(event["latest"])
        _atomic_json(LIVE_PATH, {**progress, **event,
                                 "completed_preflights": progress["completed_preflights"]})
    preflights = preflight_all(spec, record_preflight)
    progress["phase"] = "all-preflights-complete"
    progress["preflights"] = preflights
    _atomic_json(LIVE_PATH, progress)
    by_fixture = {fixture["id"]: [row for row in preflights
                                   if row["fixture_id"] == fixture["id"]]
                  for fixture in spec["fixtures"]}
    failures = []
    for fixture in spec["fixtures"]:
        final_preflight = next(row for row in by_fixture[fixture["id"]]
                               if row["iterations"] == 4000)
        if fixture["required_4000_admission"] and final_preflight["status"] != "admitted":
            failures.append(f"{fixture['id']} required 4,000-iteration preflight rejected: "
                            f"{final_preflight.get('resource_failure')}")
    results = []
    pending_policies = []
    for fixture in spec["fixtures"]:
        admitted = {row["iterations"] for row in by_fixture[fixture["id"]]
                    if row["status"] == "admitted"}
        if not admitted:
            results.append({"fixture_id": fixture["id"],
                            "status": "no-checkpoint-admitted",
                            "resource_failures": [row for row in by_fixture[fixture["id"]]
                                                  if row["status"] == "rejected"]})
            continue
        progress["phase"] = "oracle"
        progress["active_fixture"] = fixture["id"]
        _atomic_json(LIVE_PATH, progress)
        oracle = prepare_oracle(fixture["board"], fixture["oop_range"],
                                fixture["ip_range"], fixture["config"])
        if (len(oracle["counts"]) != spec["expected_chance"]["compatible_pairs"]
                or sum(row["ordered_outcomes"] for row in oracle["counts"])
                != spec["expected_chance"]["ordered_future_worlds"]):
            raise AssertionError("Independent oracle chance census differs from frozen spec")
        checkpoints = []
        for iterations in spec["checkpoints"]:
            if iterations not in admitted:
                checkpoints.append({"iterations": iterations, "status": "resource-rejected",
                                    "resource_failure": next(row["resource_failure"] for row in
                                        by_fixture[fixture["id"]]
                                        if row["iterations"] == iterations)})
                continue
            repeats = (spec["final_timed_repeats"] if iterations == 4000
                       else spec["intermediate_timed_repeats"])
            expected_budget = next(row["solver_budget"] for row in by_fixture[fixture["id"]]
                                   if row["iterations"] == iterations)
            arms = []
            for repeat_index in range(repeats):
                arms.append(_measured(
                    fixture, spec, oracle, iterations, expected_budget,
                    include_coverage=(iterations == 4000 and bool(fixture.get("required_action_coverage"))),
                    preserve_result=(iterations == 4000 and repeat_index == 0)))
            if len({arm["payload_sha256"] for arm in arms}) != 1:
                failures.append(f"{fixture['id']} T={iterations} deterministic payload differs")
            checkpoints.append({"iterations": iterations, "status": "measured", "arms": arms,
                                "median_complete_call_plus_json_seconds": statistics.median(
                                    arm["complete_call_plus_json_seconds"] for arm in arms)})
            progress["phase"] = "training"
            progress["active_fixture"] = fixture["id"]
            progress["completed_checkpoints"] = checkpoints
            _atomic_json(LIVE_PATH, progress)
        final = next((row for row in checkpoints if row["iterations"] == 4000), None)
        allocation = None
        coverage = None
        policy_artifact = None
        if final and final["status"] == "measured":
            first_final_arm = final["arms"][0]
            serialized_policy = first_final_arm.pop("serialized_policy_result", None)
            if serialized_policy is None:
                raise AssertionError("The first 4,000-iteration result was not preserved")
            policy_path = POLICY_DIR / f"{fixture['id']}-t4000.json"
            staged_path = POLICY_STAGING_DIR / policy_path.name
            _atomic_json(staged_path, serialized_policy)
            policy_artifact = {
                "path": policy_path.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(staged_path.read_bytes()).hexdigest(),
            }
            pending_policies.append((staged_path, policy_path))
            del serialized_policy
            progress["phase"] = "allocation"
            progress["active_fixture"] = fixture["id"]
            _atomic_json(LIVE_PATH, progress)
            final_budget = next(row["solver_budget"] for row in by_fixture[fixture["id"]] if row["iterations"] == 4000)
            allocation = _measured(fixture, spec, oracle, 4000, final_budget, trace=True)
            if not all(arm["target_met"] for arm in final["arms"]):
                failures.append(f"{fixture['id']} final NashConv target missed")
            first = next((row for row in checkpoints if row["iterations"] == 100
                          and row["status"] == "measured"), None)
            if first and final["arms"][0]["verification"]["nash_conv"] >= first["arms"][0]["verification"]["nash_conv"]:
                failures.append(f"{fixture['id']} final gap did not improve from 100 iterations")
            if fixture.get("required_action_coverage"):
                coverage = final["arms"][0]["action_coverage"]
                if not coverage["all_required_covered"]:
                    failures.append(f"{fixture['id']} required multi-raise action coverage missed")
        results.append({"fixture_id": fixture["id"], "checkpoints": checkpoints,
                        "allocation": allocation, "action_coverage": coverage,
                        "first_final_policy_artifact": policy_artifact,
                        "oracle_pair_counts": oracle["counts"],
                        "resource_failures": [row for row in by_fixture[fixture["id"]]
                                              if row["status"] == "rejected"]})
        progress["results"] = results
        _atomic_json(LIVE_PATH, progress)
        del oracle
    if _hashes() != before or _revision() != revision or not _is_clean():
        raise RuntimeError("Frozen source or repository state changed during benchmark")
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
              "source_revision": revision,
              "specification_sha256": _canonical_json_sha256(spec),
              "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "source_hashes": before, "worktree_clean_at_start_and_before_publication": True,
              "specification": spec, "python": platform.python_version(),
              "platform": platform.platform(), "preflights": preflights,
              "results": results, "failures": failures,
              "acceptance_gate_met": not failures,
              "timing_scope": "One complete solve plus JSON serialization at 100 and 1,000 iterations; three separate complete solves at 4,000 iterations. Source preparation, tree/work admission, ranking, training, exact diagnostics and serialization are timed; independent replay is outside timing.",
              "allocation_scope": "One separate complete 4,000-iteration solve plus JSON serialization per admitted fixture under tracemalloc. Python traced allocations, not RSS. No 10-iteration substitute.",
              "quality_scope": "Every measured policy is replayed against independently enumerated ordered future boards, independently ranked best-five hands, numeric betting rules, exact physical pair priors and legal own-hand best responses. TexasSolver is configuration inspiration only; no equivalent-game or performance comparison is claimed."}
    report["artifact_sha256"] = _canonical_json_sha256(report)
    # Staging outside the checkout keeps generated policies from invalidating
    # the clean-source check above. Publish only after every source check.
    for staged_path, policy_path in pending_policies:
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.replace(policy_path)
    _atomic_json(OUTPUT_PATH, report)
    progress.update({"phase": "complete", "complete": True,
                     "acceptance_gate_met": not failures, "report": str(OUTPUT_PATH)})
    _atomic_json(LIVE_PATH, progress)
    print(f"Saved {OUTPUT_PATH}; acceptance={not failures}", flush=True)
    if failures:
        raise AssertionError("Report saved; " + "; ".join(failures))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true",
                        help="run the six bounded no-rank admissions and stop before any oracle or training")
    args = parser.parse_args()
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8-sig"))
    validate_spec(spec)
    if args.preflight_only:
        outcomes = preflight_all(spec)
        print(json.dumps(outcomes, indent=2, allow_nan=False))
        return
    run(spec)


if __name__ == "__main__":
    main()
