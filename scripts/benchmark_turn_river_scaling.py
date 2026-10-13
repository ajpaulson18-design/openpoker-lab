"""Measure exact physical-world turn/river solver scaling on synthetic ranges.

Ranges are deterministic, nonuniform selections of concrete two-card hands.
This is a structural/runtime benchmark at deliberately small iteration counts,
not an equilibrium-accuracy or commercial-solver comparison.
"""
import argparse
import gc
import hashlib
import itertools
import json
import platform
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

from pokerlab.cards import DECK
from pokerlab.postflop_solver import solve_postflop
from scripts.benchmark_turn_solver import git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
ALGORITHMS = ("dcfr", "cfrplus")
BOARD_BY_STREET = {"turn": "2c7d9hJs", "river": "2c7d9hJsKd"}
SIZES_BY_STREET = {"turn": (4, 8, 16), "river": (16, 64, 128)}
ITERATIONS_BY_STREET = {"turn": 10, "river": 20}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def spread_range(board, count, offset, side):
    """Pick evenly spaced legal combos with reproducible, varying weights."""
    dead = set(board)
    combos = [pair for pair in itertools.combinations(
        (card for card in DECK if card not in dead), 2)]
    # Different coprime strides and offsets distribute the two ranges broadly,
    # while retaining some overlapping card blockers by design.
    stride = 37 if side == 0 else 53
    start = offset + (0 if side == 0 else 19)
    picked = [combos[(start + i * stride) % len(combos)] for i in range(count)]
    # Concrete-hand expressions are supported by the public range parser.
    weights = [1.0, 0.5, 0.75, 0.25]
    tokens = ["".join(pair) + ":" + str(weights[(i + side) % len(weights)])
              for i, pair in enumerate(picked)]
    return ",".join(tokens), tokens


def make_cases():
    cases = []
    for street in ("river", "turn"):
        board = BOARD_BY_STREET[street]
        for size in SIZES_BY_STREET[street]:
            oop, oop_tokens = spread_range(board, size, offset=7 * size, side=0)
            ip, ip_tokens = spread_range(board, size, offset=7 * size, side=1)
            cases.append({
                "id": f"{street}-{size}x{size}", "street": street,
                "board": board, "range_size_per_player": size,
                "iterations": ITERATIONS_BY_STREET[street],
                "oop": oop, "ip": ip,
                "range_hands": {"oop": oop_tokens, "ip": ip_tokens},
                "weights_cycle": [1.0, 0.5, 0.75, 0.25],
                "runouts": None,
            })
    return cases


def solve_case(case, algorithm, iterations=None):
    return solve_postflop(
        case["board"], case["oop"], case["ip"], iterations=iterations or case["iterations"],
        algorithm=algorithm, traversal="public-batched", diagnostics="public-batched")


def measure(case, algorithm):
    gc.collect()
    start = time.perf_counter()
    result = solve_case(case, algorithm)
    seconds = time.perf_counter() - start
    return result, seconds


def memory_peak(case, algorithm):
    gc.collect()
    tracemalloc.start()
    try:
        result = solve_case(case, algorithm, iterations=10)
        peak = tracemalloc.get_traced_memory()[1]
        return peak, result
    finally:
        tracemalloc.stop()


def run(cases):
    results = []
    for case in cases:
        for algorithm in ALGORITHMS:
            item = {"case_id": case["id"], "street": case["street"],
                    "range_size_per_player": case["range_size_per_player"],
                    "iterations": case["iterations"], "algorithm": algorithm,
                    "status": "pending"}
            try:
                result, seconds = measure(case, algorithm)
            except ValueError as exc:
                item.update(status="rejected", rejection_reason=str(exc),
                            whole_call_seconds=None, peak_tracemalloc_bytes=None)
                print(case["id"], algorithm, "rejected:", str(exc), flush=True)
            else:
                peak, memory_result = memory_peak(case, algorithm)
                item.update(status="admitted", whole_call_seconds=seconds,
                            peak_tracemalloc_bytes=peak,
                            memory_iterations=10,
                            memory_tracing_note="Separate one-call tracemalloc run at 10 iterations; timing above is untraced.",
                            actual_iterations=result["iterations"],
                            candidate_hand_pairs=result["deals"],
                            candidate_pair_iteration_work=(
                                case["range_size_per_player"] ** 2 * case["iterations"]),
                            physical_worlds=result["worlds"],
                            world_iteration_work=result["worlds"] * case["iterations"],
                            public_states=result["public_states"],
                            public_nodes=result["public_nodes"],
                            info_sets=result["info_sets"],
                            chance_nodes=result["chance_nodes"],
                            world_traversal_nodes=result["world_traversal_nodes"],
                            world_node_iteration_work=(
                                result["worlds"] * result["world_traversal_nodes"] *
                                case["iterations"] * (3 if algorithm == "cfrplus" else 1)),
                            exploitability_chips=result["exploitability"],
                            nash_conv_chips=result["nash_conv"],
                            exploitability_fraction_of_100_chip_pot=result["exploitability"] / 100.0,
                            tracing_run_worlds=memory_result["worlds"],
                            tracing_run_exploitability_chips=memory_result["exploitability"],
                            resource_limits={"candidate_pair_iteration_limit": 3_000_000,
                                             "world_iteration_limit": 3_000_000,
                                             "world_node_iteration_limit": 30_000_000,
                                             "public_states": 250_000,
                                             "public_decision_nodes": 10_000})
                print(case["id"], algorithm, f"{seconds:.3f}s",
                      f"worlds={result['worlds']}", f"states={result['public_states']}",
                      f"peak={peak}", flush=True)
            results.append(item)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks/results/turn-river-scaling-v1.json")
    args = parser.parse_args(argv)
    cases = make_cases()
    source_files = [Path(__file__).resolve(), ROOT / "scripts/benchmark_turn_solver.py"]
    source_files.extend(ROOT / "pokerlab" / (module + ".py") for module in (
        "postflop_solver", "turn_solver", "cards", "cfr", "cfr_plus",
        "planned_cfr", "public_cfr", "public_diagnostics", "river_config",
        "river_tree"))
    before = {str(path.relative_to(ROOT)): sha256(path) for path in source_files}
    results = run(cases)
    after = {str(path.relative_to(ROOT)): sha256(path) for path in source_files}
    if before != after:
        raise RuntimeError("Calculation source changed during benchmark; discard this result.")
    report = {
        "schema_version": 1, "benchmark_id": "turn-river-scaling-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "metadata": {"revision": git_revision(None), "worktree_dirty": worktree_dirty(),
                     "python": sys.version, "python_version": platform.python_version(),
                     "platform": platform.platform(),
                     "command": "python -m scripts.benchmark_turn_river_scaling",
                     "configuration": {"algorithms": ALGORITHMS,
                                       "traversal": "public-batched",
                                       "diagnostics": "public-batched",
                                       "river_iterations": 20, "turn_iterations": 10,
                                       "timing_runs_per_case": 1,
                                       "memory_runs_per_admitted_case": 1,
                                       "memory_iterations": 10},
                     "input_specification": "Deterministic combinations from pokerlab.cards.DECK after board removal; OOP/IP use distinct offsets and stride selection; nonuniform repeating weights [1,.5,.75,.25]. Exact concrete hands recorded below.",
                     "source_sha256": before},
        "methodology": {"timing": "One untraced complete solve_postflop call per admitted algorithm/case, including world enumeration, training, exact public-batched diagnostics, and result assembly.",
                        "memory": "Separate one-call tracemalloc peak at 10 iterations; excludes process RSS and is not a timing run.",
                        "accuracy": "All reported gaps are finite-iteration diagnostics at 10 turn / 20 river iterations; no equilibrium or backend parity claim.",
                        "limitations": "Synthetic small-range sizes, one run per case, machine-specific runtime and allocator-dependent traced memory. Unit tests ran concurrently, so timing samples are descriptive rather than controlled comparisons."},
        "cases": cases, "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(f"Wrote {len(results)} measurements to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
