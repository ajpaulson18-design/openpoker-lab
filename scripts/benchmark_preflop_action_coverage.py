"""Frozen preflop raise/action-coverage matrix for the finite flop-checkdown game."""
from __future__ import annotations

import gc
import hashlib
import json
import platform
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from pokerlab import preflop_solver as solver
from scripts.benchmark_preflop_flop_checkdown import futures, verify, SOURCES
from scripts.benchmark_preflop_flop_raise_coverage import preflight_case
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/preflop-action-coverage-v1.json"
OUTPUT = ROOT / "benchmarks/results/preflop-action-coverage-v1.json"


def _coverage(rows):
    """Count legal serialized preflop actions; probabilities are not coverage."""
    def aggressive(token):
        return token.startswith(("raise@", "all_in@"))

    def action_exemplar(row, action):
        return {"player": row["player"], "history": list(row["history"]),
                "name": action["name"], "amount": action["amount"],
                "raise_to": action["raise_to"], "history_key": action["history_key"]}

    roots = [row for row in rows if row["street"] == "preflop" and row["player"] == "sb"
             and not row["history"]]
    openings = {}
    for target in (2.0, 3.0):
        matches = [(row, action) for row in roots for action in row["actions"]
                   if action["name"] == "raise" and action["raise_to"] == target]
        openings[str(target)] = action_exemplar(*matches[0]) if matches else None

    three_bets, four_bets, regular_four_bets, all_ins = [], [], [], []
    capped_histories = []
    over_cap_histories = []
    for row in rows:
        if row["street"] != "preflop":
            continue
        aggressive_tokens = [token for token in row["history"] if aggressive(token)]
        count = len(aggressive_tokens)
        actions = row["actions"]
        # Exactly SB's root open, followed by the BB response.
        if (row["player"] == "bb" and len(row["history"]) == 1 and count == 1
                and row["history"][0].startswith("raise@")):
            three_bets.extend(action_exemplar(row, action) for action in actions
                              if action["name"] in ("raise", "all_in"))
        # Two ordinary raises form SB's response after the BB 3-bet.
        if (row["player"] == "sb" and len(row["history"]) == 2 and count == 2
                and all(token.startswith("raise@") for token in row["history"])):
            four_bets.extend(action_exemplar(row, action) for action in actions
                             if action["name"] in ("raise", "all_in"))
            regular_four_bets.extend(action_exemplar(row, action) for action in actions
                                     if action["name"] == "raise")
        all_ins.extend(action_exemplar(row, action) for action in actions
                       if action["name"] == "all_in")
        if count == 3:
            capped_histories.append({"player": row["player"], "history": list(row["history"]),
                "has_raise_or_all_in": any(a["name"] in ("raise", "all_in") for a in actions)})
        elif count > 3:
            over_cap_histories.append({"player": row["player"], "history": list(row["history"])})

    return {
        "serialized_preflop_rows": sum(row["street"] == "preflop" for row in rows),
        "sb_root_opening_raise_exemplars": openings,
        "bb_three_bet_exemplars": three_bets[:8],
        "sb_four_bet_exemplars": four_bets[:8],
        "sb_regular_four_bet_exemplars": regular_four_bets[:8],
        "preflop_all_in_exemplars": all_ins[:8],
        "three_raise_histories_checked": len(capped_histories),
        "histories_over_three_raises_count": len(over_cap_histories),
        "raise_or_all_in_after_three_raises": any(
            row["has_raise_or_all_in"] for row in capped_histories),
        "histories_over_three_raises": over_cap_histories[:8],
        "coverage_flags": {
            "both_sb_open_sizes": all(value is not None for value in openings.values()),
            "bb_three_bet": bool(three_bets),
            "sb_four_bet": bool(four_bets),
            "sb_regular_four_bet": bool(regular_four_bets),
            "preflop_all_in": bool(all_ins),
            "raise_cap_respected": bool(capped_histories) and not over_cap_histories and
                not any(row["has_raise_or_all_in"] for row in capped_histories),
        },
    }

def _options(spec, stack):
    return {"config": {"starting_stack": stack, **spec["preflop_config"]},
            "runouts": futures(spec["flops"]), "flop_config": spec["flop_config"],
            "postflop_scope": spec["postflop_scope"]}


def _kwargs(spec, stack, checkpoint):
    return dict(_options(spec, stack), iterations=checkpoint["iterations"],
        averaging_delay=checkpoint["delay"], algorithm="cfrplus", traversal="public-batched",
        diagnostics="public-batched", resource_model="public-vector", future_indexing="flop-sign")


def _preflight(spec, stack, checkpoint, grouped):
    game = {"sb": spec["sb"], "bb": spec["bb"],
            "preflop_config": dict(spec["preflop_config"]),
            "physical_outcomes": {"flops": spec["flops"]},
            "flop_config": spec["flop_config"], "postflop_scope": spec["postflop_scope"],
            "algorithm": "cfrplus", "traversal": "public-batched",
            "diagnostics": "public-batched", "resource_model": "public-vector",
            "future_indexing": "flop-sign"}
    if not grouped:
        return preflight_case(game, stack, checkpoint)
    original = solver.solve_preflop
    def with_grouped_admission(*args, **kwargs):
        return original(*args, **kwargs, world_admission="grouped-vector")
    with patch.object(solver, "solve_preflop", with_grouped_admission):
        return preflight_case(game, stack, checkpoint)


def _source_paths():
    extra = ("scripts/benchmark_preflop_flop_raise_coverage.py",
        "scripts/benchmark_preflop_grouped_world_admission.py",
        "scripts/benchmark_preflop_action_coverage.py",
        "tests/test_preflop_grouped_world_admission.py",
        "benchmarks/preflop-flop-checkdown-v1.json",
        "benchmarks/preflop-flop-raise-coverage-v1.json",
        "benchmarks/preflop-grouped-world-admission-v1.json",
        "benchmarks/preflop-action-coverage-v1.json")
    return tuple(dict.fromkeys((*SOURCES, *extra)))


def main():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    revision, dirty = git_revision(None), worktree_dirty()
    if dirty is not False or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise RuntimeError("Freeze source/spec in a clean commit before measurement")
    source_paths = _source_paths()
    hashes = {path: file_sha256(ROOT / path) for path in source_paths}
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
           for value in hashes.values()):
        raise RuntimeError("Source hash unavailable")
    if file_sha256(SPEC) != hashes["benchmarks/preflop-action-coverage-v1.json"]:
        raise RuntimeError("Configuration hash mismatch")

    cases = [(stack, checkpoint) for stack in spec["starting_stacks"]
             for checkpoint in spec["checkpoints"]]
    if len(cases) != spec["matrix_cases"]:
        raise ValueError("Frozen matrix case count mismatch")
    admissions = []
    print("Preflighting all six cases before any training", flush=True)
    for stack, checkpoint in cases:
        record = {"starting_stack": stack, **checkpoint}
        for grouped, label in ((False, "world-iterations"), (True, "grouped-vector")):
            outcome = _preflight(spec, stack, checkpoint, grouped)
            record[label] = outcome
            print(f"  stack={stack} {checkpoint['iterations']} {label}: "
                  f"{outcome['status']} {outcome['rejection'] or outcome['combined_modeled_loop_entries']}",
                  flush=True)
        admissions.append(record)

    oracle_spec = dict(spec, expected_worlds=spec["expected_worlds"],
                       expected_selected_outcomes=spec["expected_selected_outcomes"])
    reference_case = (6, spec["checkpoints"][0])
    parity_fields = ("worlds", "selected_runouts", "reachable_runouts", "private_pair_probabilities",
        "public_states", "decisions", "info_sets", "value_sb", "value_bb",
        "sb_best_response_value", "bb_best_response_value", "nash_conv")
    reference_policy = reference_physical_scalars = reference_verification = None
    has_reference = any(stack == reference_case[0] and checkpoint == reference_case[1]
                        and row["world-iterations"]["status"] == "admitted"
                        and row["grouped-vector"]["status"] == "admitted"
                        for (stack, checkpoint), row in zip(cases, admissions))
    if has_reference:
        print("Legacy/grouped stack6 250-sweep exact policy reference start", flush=True)
        ref_stack, ref_checkpoint = reference_case
        reference_result = solver.solve_preflop(spec["sb"], spec["bb"],
            **_kwargs(spec, ref_stack, ref_checkpoint))
        reference_policy = json.dumps(reference_result["strategy"], allow_nan=False)
        reference_physical_scalars = {key: reference_result[key] for key in parity_fields}
        reference_verification = verify(reference_result, oracle_spec, _options(spec, ref_stack))
        del reference_result
    results, coverages = [], []
    for (stack, checkpoint), admission in zip(cases, admissions):
        grouped = admission["grouped-vector"]
        if grouped["status"] != "admitted":
            results.append({"starting_stack": stack, **checkpoint, "status": "rejected",
                            "rejection": grouped["rejection"], "preflight": admission})
            continue
        print(f"Complete call stack={stack}, T={checkpoint['iterations']}, delay={checkpoint['delay']}",
              flush=True)
        options = _options(spec, stack)
        kwargs = _kwargs(spec, stack, checkpoint)
        kwargs["world_admission"] = "grouped-vector"
        gc.collect()
        start = time.perf_counter()
        result = solver.solve_preflop(spec["sb"], spec["bb"], **kwargs)
        serialized = json.dumps(result, allow_nan=False)
        elapsed = time.perf_counter() - start
        checked = verify(result, oracle_spec, options)
        if result.get("world_admission") != "grouped-vector":
            raise AssertionError("Missing explicit grouped-vector mode")
        if result["vector_work_budget"]["iterations"] != checkpoint["iterations"]:
            raise AssertionError("Full requested iteration ceiling not reported")
        if result["vector_work_budget"]["total_loop_entries_upper_bound"] != grouped["combined_modeled_loop_entries"]:
            raise AssertionError("Actual admission differs from preflight")
        coverage = _coverage(result["strategy"])
        coverages.append({"starting_stack": stack, **coverage})
        parity = None
        if has_reference and (stack, checkpoint) == reference_case:
            parity = (json.dumps(result["strategy"], allow_nan=False) == reference_policy and
                      {key: result[key] for key in parity_fields} == reference_physical_scalars)
            if not parity:
                raise AssertionError("Grouped mode changed same-configuration 250 policy/physical/scalar outputs")
            del reference_policy, reference_physical_scalars
        results.append({"starting_stack": stack, **checkpoint, "status": "completed",
            "complete_call_seconds": elapsed,
            "full_payload_sha256": hashlib.sha256(serialized.encode()).hexdigest(),
            "verification": checked, "preflop_action_coverage": coverage,
            "future_indexing_metadata": result["future_indexing_metadata"],
            "world_construction_admission_iterations": result["world_construction_admission_iterations"],
            "limits": result["limits"], "vector_work_budget": result["vector_work_budget"],
            "preflight": admission, "legacy_grouped_250_exact_parity": parity})
        del result, serialized

    union = _coverage_union(coverages)
    if hashes != {path: file_sha256(ROOT / path) for path in source_paths}:
        raise RuntimeError("Source hash changed during measurement")
    if git_revision(None) != revision or worktree_dirty() is not False:
        raise RuntimeError("Source revision/worktree changed during measurement")
    report = {"schema_version": 1, "benchmark_id": spec["benchmark_id"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": revision, "worktree_dirty_at_start": False,
        "source_hashes": hashes, "configuration_sha256": hashes["benchmarks/preflop-action-coverage-v1.json"],
        "specification": spec, "python": platform.python_version(), "platform": platform.platform(),
        "preflight": admissions, "legacy_reference_verification": reference_verification,
        "results": results, "union_action_coverage": union,
        "coverage_scope": "Action existence in serialized legal preflop information sets, not strategy frequency. Exemplars retain whole public history; flop rows never count toward preflop coverage.",
        "timing_scope": "One descriptive complete solve plus JSON serialization per admitted grouped case. Includes physical enumeration/ranking, tree construction, grouping, full requested-T admission, training and exact diagnostics. Preallocated selected runouts, pre-call garbage collection and independent replay excluded. No speedup or statistical timing claim.",
        "quality_scope": "Every completed case independently replays the original physical worlds with numeric betting rules and exact visible-information best responses. The unchanged target is checked per case; all misses and admission rejections remain in the report. No early stopping, action/world simplification or dropped physical outcomes.",
        "provenance": "Luna drafted the isolated benchmark/spec; lead reviewed the fixed matrix, coverage predicates and admission flow. The report contains repository-generated policies and original-world independent replay; no shared kernel, Coach, third-party source or dependency changes.",
        "model_limits": spec["model_limits"]}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    required = ("both_sb_open_sizes", "bb_three_bet", "sb_four_bet",
                "sb_regular_four_bet", "preflop_all_in", "raise_cap_respected")
    if not all(union["coverage_flags"][name] for name in required):
        raise AssertionError(f"Report saved; required action coverage missing: {union}")
    print(f"saved {OUTPUT}; completed={sum(row['status']=='completed' for row in results)}/{len(cases)}",
          flush=True)


def _coverage_union(items):
    openings = {}
    for target in ("2.0", "3.0"):
        openings[target] = next(({"starting_stack": item["starting_stack"],
                                  **item["sb_root_opening_raise_exemplars"][target]}
                                 for item in items
                                 if item["sb_root_opening_raise_exemplars"][target]), None)
    three_bets = [{"starting_stack": item["starting_stack"], **x}
                  for item in items for x in item["bb_three_bet_exemplars"]]
    four_bets = [{"starting_stack": item["starting_stack"], **x}
                 for item in items for x in item["sb_four_bet_exemplars"]]
    regular = [{"starting_stack": item["starting_stack"], **x}
               for item in items for x in item["sb_regular_four_bet_exemplars"]]
    all_ins = [{"starting_stack": item["starting_stack"], **x}
               for item in items for x in item["preflop_all_in_exemplars"]]
    capped = sum(item["three_raise_histories_checked"] for item in items)
    over_cap = sum(item["histories_over_three_raises_count"] for item in items)
    bad_cap = any(item["raise_or_all_in_after_three_raises"] or
                  item["histories_over_three_raises_count"] for item in items)
    return {"sb_root_opening_raise_exemplars": openings,
        "bb_three_bet_exemplars": three_bets[:12], "sb_four_bet_exemplars": four_bets[:12],
        "sb_regular_four_bet_exemplars": regular[:12], "preflop_all_in_exemplars": all_ins[:12],
        "three_raise_histories_checked": capped, "histories_over_three_raises": over_cap,
        "raise_or_all_in_after_three_raises": bad_cap,
        "coverage_flags": {"both_sb_open_sizes": all(value is not None for value in openings.values()),
            "bb_three_bet": bool(three_bets), "sb_four_bet": bool(four_bets),
            "sb_regular_four_bet": bool(regular), "preflop_all_in": bool(all_ins),
            "raise_cap_respected": capped > 0 and not bad_cap}}


if __name__ == "__main__":
    main()
