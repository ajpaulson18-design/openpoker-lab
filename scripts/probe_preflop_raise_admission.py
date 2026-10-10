"""Reproduce the bounded preflop-raise structural admission probe (never trains)."""
import argparse
import json
import math
from pathlib import Path
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from pokerlab.preflop_tree import PreflopConfig, build_preflop_tree
from scripts.benchmark_preflop_two_flops import futures
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "benchmarks/results/preflop-raise-admission-probe-v1.json"
MODULES = tuple(sorted(path.relative_to(ROOT).as_posix()
                       for path in (ROOT / "pokerlab").glob("*.py")))
HELPER = "scripts/benchmark_preflop_two_flops.py"
IMPORTED_SOURCES = (HELPER, "scripts/benchmark_turn_solver.py",
                    "scripts/preflop_validation.py",
                    "tests/test_preflop_delayed_cfrplus.py")
SCRIPT = "scripts/probe_preflop_raise_admission.py"
SOURCE_PATHS = (*MODULES, *IMPORTED_SOURCES, SCRIPT)
SB_RANGE = "AsAd,QsQd"
BB_RANGE = "KsKd,JhJc"
FLOPS = (("2c", "3c", "4d"), ("5h", "6s", "Jc"))
def make_config(starting_stack):
    return PreflopConfig(starting_stack=starting_stack, raise_sizes=(0.5,),
                         max_raises=1, include_all_in=False)
STAGES = {"flop": {"bet_sizes": [0.5], "raise_sizes": [],
                   "max_raises": 0, "include_all_in": True},
          "turn": {"bet_sizes": [0.5], "raise_sizes": [],
                   "max_raises": 0, "include_all_in": True},
          "river": {"bet_sizes": [0.5], "raise_sizes": [],
                    "max_raises": 0, "include_all_in": True}}


class StopAfterAdmission(Exception):
    pass


def action_record(action):
    return {"name": action.name, "token": action.token, "amount": action.amount,
            "raise_to": action.raise_to}


def boundary_record(boundary):
    return {"street": boundary.street,
            "matched_contributions": list(boundary.matched_contributions),
            "pot": boundary.pot, "refunds": list(boundary.refunds),
            "remaining_stacks": list(boundary.remaining_stacks),
            "all_in": list(boundary.all_in), "next_player": boundary.next_player}


def preflop_boundary(config):
    tree = build_preflop_tree(config)
    root = tree.root
    root_call = next(i for i, action in enumerate(root.actions)
                     if action.name == "call")
    bb_limp = root.children[root_call]
    bb_raise = next(i for i, action in enumerate(bb_limp.actions)
                    if action.name == "raise")
    sb_facing_limp_raise = bb_limp.children[bb_raise]
    root_raise = next(i for i, action in enumerate(root.actions)
                      if action.name == "raise" and action.raise_to == 2.0)
    bb_facing_open = root.children[root_raise]
    bb_call = next(i for i, action in enumerate(bb_facing_open.actions)
                   if action.name == "call")
    bb_check = next(i for i, action in enumerate(bb_limp.actions)
                    if action.name == "check")
    return {
        "root_actions": [action_record(a) for a in root.actions],
        "tree_counts": tree.counts,
        "after_limp_actions": [action_record(a) for a in bb_limp.actions],
        "limp_check_boundary": boundary_record(bb_limp.children[bb_check]),
        "sb_after_limp_raise_actions":
            [action_record(a) for a in sb_facing_limp_raise.actions],
        "sb_reraise_available_after_limp_raise":
            any(a.name in ("raise", "allin") for a in sb_facing_limp_raise.actions),
        "bb_after_open_actions": [action_record(a) for a in bb_facing_open.actions],
        "open_call_boundary": boundary_record(bb_facing_open.children[bb_call]),
    }


def probe(label, runouts, config):
    captured = {}
    original_estimator = solver.estimate_vector_budget
    original_enumerator = solver._enumerate_physical_worlds

    def capture_enumeration(*args, **kwargs):
        result = original_enumerator(*args, **kwargs)
        captured["enumeration"] = {
            "expanded_private_hands": [len(result[0][0]), len(result[0][1])],
            "materialized_worlds": len(result[1]),
            "compatible_private_pairs": result[2],
            "pair_probabilities": result[3],
            "selected_outcomes": len(result[4]),
            "preflight_checks": result[5],
        }
        return result

    def stop_after_estimate(root, worlds, infos, iterations, algorithm, **kwargs):
        captured["vector_estimator_reached"] = True
        budget = original_estimator(root, worlds, infos, iterations, algorithm, **kwargs)
        captured.update(root=root, worlds=worlds, infos=infos,
                        chance_type=kwargs["chance_type"], budget=budget)
        raise StopAfterAdmission()

    def forbidden(*args, **kwargs):
        raise AssertionError("Training or vector view allocation was reached.")

    call = {"config": config, "runouts": runouts, "flop_config": STAGES["flop"],
            "turn_config": STAGES["turn"], "river_config": STAGES["river"],
            "iterations": 10, "averaging_delay": 5, "algorithm": "cfrplus",
            "traversal": "public-batched", "diagnostics": "public-batched",
            "resource_model": "public-vector", "tree_admission": "vector",
            "private_indexing": "original"}
    record = {"fixture": label, "selected_flops": len({tuple(row[:3]) for row in runouts}),
              "selected_outcomes": len(runouts), "requested_iterations": 10,
              "averaging_delay": 5}
    try:
        with patch.object(solver, "_enumerate_physical_worlds", capture_enumeration), \
             patch.object(solver, "estimate_vector_budget", stop_after_estimate), \
             patch.object(solver, "train_delayed_public_cfrplus", forbidden), \
             patch.object(solver, "_positive_pot_training_view", forbidden):
            solver.solve_preflop(SB_RANGE, BB_RANGE, **call)
    except StopAfterAdmission:
        record.update(status="admitted_stopped_after_estimator_before_view_or_training",
                      vector_estimator_reached=True,
                      training_and_view_forbidden_by_probe=True)
    except ValueError as exc:
        record.update(status=("rejected_by_vector_estimator" if captured.get("vector_estimator_reached")
                             else "rejected_before_vector_estimator"),
                      vector_estimator_reached=bool(captured.get("vector_estimator_reached")),
                      training_and_view_forbidden_by_probe=True,
                      error_type=type(exc).__name__, error=str(exc))
        if "enumeration" in captured:
            record["physical_preflight"] = captured["enumeration"]
        return record
    if "budget" not in captured:
        raise AssertionError("solve_preflop returned without the expected admission stop.")
    record["physical_preflight"] = captured["enumeration"]
    record["information_sets"] = len(captured["infos"])
    record["base_budget"] = captured["budget"]
    record["actual_counts"] = {
        "materialized_worlds": len(captured["worlds"]),
        "information_sets": len(captured["infos"]),
        "decision_nodes": captured["budget"]["decision_nodes"],
        "public_states": (captured["budget"]["decision_nodes"] +
                          captured["budget"]["chance_nodes"] +
                          captured["budget"]["terminal_nodes"]),
    }
    record["additional_iteration_estimates"] = {}
    for iterations, delay in ((20, 10), (40, 20), (90, 45)):
        try:
            budget = original_estimator(
                captured["root"], captured["worlds"], captured["infos"],
                iterations, "cfrplus", chance_type=captured["chance_type"],
                averaging_delay=delay)
            record["additional_iteration_estimates"][str(iterations)] = {
                "delay": delay, "budget": budget,
                "admitted": budget["total_loop_entries_upper_bound"]
                            <= budget["total_loop_entry_limit"],
            }
        except ValueError as exc:
            record["additional_iteration_estimates"][str(iterations)] = {
                "delay": delay, "admitted": False,
                "error_type": type(exc).__name__, "error": str(exc)}
    return record


def positive_stack(value):
    try:
        amount = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("stack must be a finite number greater than 2") from None
    if not math.isfinite(amount) or amount <= 2.0:
        raise argparse.ArgumentTypeError("stack must be a finite number greater than 2")
    return amount


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--starting-stack", type=positive_stack, default=3.0)
    parser.add_argument("--output", type=Path, default=ARTIFACT)
    args = parser.parse_args(argv)
    if args.starting_stack != 3.0 and args.output == ARTIFACT:
        parser.error("custom starting stacks require an explicit --output path")
    config = make_config(args.starting_stack)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if ARTIFACT.exists():
        report = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    else:
        report = {"schema_version": 1,
                  "probe_id": "preflop-raise-admission-probe-v1",
                  "source_revision": "907103806edb97efac81b9fe46eb2b212027130e",
                  "worktree_dirty_at_probe_start": False,
                  "source_hashes": {}}
    prior_revision = report["source_revision"]
    prior_dirty = report["worktree_dirty_at_probe_start"]
    prior_fixtures = report.get("fixtures", [])
    revision, dirty = git_revision(None), worktree_dirty()
    current_hashes = {path: file_sha256(ROOT / path) for path in SOURCE_PATHS}
    outcomes = [futures(FLOPS[:1]), futures(FLOPS)]
    reproduced = [probe("one-flop", outcomes[0], config),
                  probe("two-flop", outcomes[1], config)]
    if [row["selected_outcomes"] for row in reproduced] != [2352, 4704]:
        raise AssertionError("Selected-outcome counts differ from the frozen fixture.")
    if args.starting_stack == 3.0 and any(
            row["status"] != "rejected_before_vector_estimator" or
            row.get("error") != "Postflop solver public tree exceeds 10,000 decision nodes."
            for row in reproduced):
        raise AssertionError("The default-stack result differs from the frozen probe.")
    if any(not row.get("training_and_view_forbidden_by_probe") for row in reproduced):
        raise AssertionError("Training or vector-view allocation was not forbidden.")
    if any(row["physical_preflight"]["materialized_worlds"] <= 0 for row in reproduced):
        raise AssertionError("Physical worlds were not constructed before template rejection.")
    if current_hashes != {path: file_sha256(ROOT / path) for path in SOURCE_PATHS}:
        raise RuntimeError("Source files changed during the probe.")
    report.update({
        "source_revision": prior_revision,
        "worktree_dirty_at_probe_start": prior_dirty,
        "config": config.to_dict(),
        "requested_starting_stack": args.starting_stack,
        "sb_range": SB_RANGE,
        "bb_range": BB_RANGE,
        "stage_configs": STAGES,
        "preflop_tree_boundary": preflop_boundary(config),
        "fixtures": reproduced,
        "reproduction": {
            "script": SCRIPT,
            "execution_revision": revision,
            "execution_worktree_dirty": dirty,
            "source_hashes": current_hashes,
            "script_sha256": current_hashes[SCRIPT],
            "completed_at_utc": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc).isoformat(),
            "preserved_base_revision": prior_revision,
            "preserved_base_fixture_count": len(prior_fixtures),
        },
        "scope": ("Structural admission only. If vector admission is reached, the estimator is "
                  "intercepted and training/vector-view allocation is forbidden. The default 3.0-stack "
                  "fixtures reject at the unchanged per-flop template decision limit before the estimator; "
                  "custom stacks may be admitted and report the full structural budgets. No policy quality, "
                  "runtime, or convergence claim."),
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n",
                      encoding="utf-8")
    print(json.dumps({"probe_base_revision": prior_revision,
                      "execution_revision": revision, "dirty": dirty,
                      "source_hashes": current_hashes,
                      "fixtures": [{"fixture": row["fixture"],
                                    "status": row["status"],
                                    "selected_outcomes": row["selected_outcomes"],
                                    "physical_preflight": row.get("physical_preflight"),
                                    "error": row.get("error")}
                                   for row in reproduced],
                      "artifact": str(output.resolve())}, indent=2))


if __name__ == "__main__":
    main()

