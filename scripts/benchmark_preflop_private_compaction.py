"""Frozen complete-call evaluation of opt-in private-index compaction."""
from datetime import datetime, timezone
import gc
import json
from pathlib import Path
import platform
import statistics
import time
import tracemalloc

from pokerlab.preflop_solver import solve_preflop
from scripts.benchmark_preflop_two_flops import futures, verify
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/preflop-private-compaction-v1.json"
OUTPUT = ROOT / "benchmarks/results/preflop-private-compaction-v1.json"
SOURCES = tuple(sorted(str(p.relative_to(ROOT)).replace("\\", "/")
                       for p in (ROOT / "pokerlab").glob("*.py"))) + (
    "scripts/benchmark_preflop_private_compaction.py",
    "scripts/benchmark_preflop_two_flops.py", "scripts/benchmark_turn_solver.py",
    "scripts/preflop_validation.py", "tests/test_preflop_private_indices.py",
    "tests/test_preflop_private_index_budget.py",
    "tests/test_preflop_private_index_integration.py")


def solve(spec, kwargs, checkpoint, mode):
    result = solve_preflop(spec["sb"], spec["bb"], **kwargs,
        iterations=checkpoint["iterations"], averaging_delay=checkpoint["delay"],
        algorithm="cfrplus", traversal="public-batched", diagnostics="public-batched",
        resource_model="public-vector", tree_admission="vector", private_indexing=mode)
    json.dumps(result)
    return result


def check(result, spec, kwargs):
    independent = verify(result, spec, kwargs)
    gap = independent["configured_replay"]["nash_conv"]
    return {"worlds":result["worlds"], "information_sets":result["info_sets"],
            "decisions":result["decisions"], "public_states":result["public_states"],
            "private_pair_probabilities":result["private_pair_probabilities"],
            "target_nash_conv":spec["target_nash_conv"],
            "independent_target_met":gap + 1e-10 <= spec["target_nash_conv"],
            "vector_work_budget":result["vector_work_budget"],
            "private_indexing_metadata":result.get("private_indexing_metadata"),
            **independent}


def parity(first, second):
    for field in ("strategy", "value_sb", "sb_best_response_value", "bb_best_response_value",
                  "nash_conv", "private_pair_probabilities", "reachable_runouts",
                  "worlds", "info_sets", "decisions", "public_states"):
        assert first[field] == second[field], field


def main():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    hashes = {p:file_sha256(ROOT / p) for p in SOURCES}
    specification_hash = file_sha256(SPEC)
    revision, dirty = git_revision(None), worktree_dirty()
    if dirty:
        raise RuntimeError("Freeze source/spec in a clean commit before measuring.")
    kwargs = {"config":spec["config"], "runouts":futures(spec["flops"])}
    pairs = []
    for index in range(spec["paired_timing"]["pairs"]):
        order = ("original", "compact") if index % 2 == 0 else ("compact", "original")
        rows = {}
        first = None
        for mode in order:
            print(f"pair{index+1}: {mode} start", flush=True)
            gc.collect()
            start = time.perf_counter()
            result = solve(spec, kwargs, spec["paired_timing"], mode)
            elapsed = time.perf_counter() - start
            rows[mode] = {"complete_call_seconds":elapsed, **check(result, spec, kwargs)}
            if first is None:
                first = result
            else:
                parity(first, result)
            print(f"  seconds={elapsed:.3f} gap={result['nash_conv']:.12g}", flush=True)
        pairs.append({"pair":index+1, "order":list(order),
                      "policy_row_order_diagnostics_and_physical_priors_exactly_equal":True,
                      "records":rows})
        del result, first
    print("compact high-iteration accuracy checkpoint start", flush=True)
    gc.collect()
    start = time.perf_counter()
    result = solve(spec, kwargs, spec["accuracy"], "compact")
    accuracy = {**spec["accuracy"], "complete_call_seconds":time.perf_counter()-start,
                **check(result, spec, kwargs)}
    print(f"  gap={result['nash_conv']:.12g}; target met={accuracy['independent_target_met']}", flush=True)
    del result
    memory = {}
    first = None
    for mode in ("original", "compact"):
        print(f"separate complete-call allocation trace: {mode} start", flush=True)
        gc.collect()
        tracemalloc.start()
        try:
            result = solve(spec, kwargs, spec["memory"], mode)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        memory[mode] = {"complete_peak_traced_python_bytes":peak, **check(result, spec, kwargs)}
        if first is None:
            first = result
        else:
            parity(first, result)
        print(f"  peak={peak} gap={result['nash_conv']:.12g}", flush=True)
        del result
    del first
    assert hashes == {p:file_sha256(ROOT / p) for p in SOURCES}
    assert specification_hash == file_sha256(SPEC)
    medians = {mode:statistics.median(p["records"][mode]["complete_call_seconds"] for p in pairs)
               for mode in ("original", "compact")}
    reduction = 1 - medians["compact"] / medians["original"]
    report = {"schema_version":1, "benchmark_id":spec["benchmark_id"],
        "generated_at":datetime.now(timezone.utc).isoformat(), "source_revision":revision,
        "worktree_dirty_at_start":dirty, "source_hashes":hashes,
        "configuration_sha256":specification_hash, "specification":spec,
        "python":platform.python_version(), "platform":platform.platform(),
        "paired_timings":pairs, "paired_timing_medians":medians,
        "observed_median_time_reduction":reduction,
        "runtime_gate_met":reduction >= spec["minimum_median_time_reduction"],
        "accuracy":accuracy, "memory":memory,
        "memory_policy_row_order_diagnostics_and_physical_priors_exactly_equal":True,
        "accuracy_scope":"Same fixed iterations/delay for timing/memory arms; all final policies independently replayed from numeric rules and exact visible-information best responses. The compact90/delay45 checkpoint is a single accuracy measurement, with no speed comparison to original90. Unchanged0.005 target misses retained; no accuracy improvement claimed.",
        "timing_scope":"Three alternating pairs of complete two-flop20/delay10 solves plus JSON on one host, including preflight, compact copies, training, exact diagnostics and original-identity restoration. Preallocated runout arguments, pre-call GC and independent replay excluded. Shape-specific observed medians, no universal speed claim.",
        "memory_scope":"Separate complete two-flop10/delay5 solves plus JSON under tracemalloc, including compact copies through diagnostics and restoration. Runout arguments preallocated; independent replay, native allocations and RSS excluded. Original result retained for parity but allocated before compact trace, so peak reports new Python allocations, not all live process memory. No higher-iteration guarantee.",
        "admission_scope":"Independent v4 pre-copy structural census uses actual compact dimensions and reserves additional copy/restoration loop entries and logical reference slots. Original physical world/tree/candidate guards and numerical model unchanged. Logical slots exclude Python headers, allocator effects and RSS.",
        "provenance":"Independently implemented ascending bijection of this repository's own global active-hand indices. No third-party source/dependencies or shared postflop/turn/river changes. Luna owns compaction/integration and independent budget tests/review; lead owns workload admission, independent integration checks, frozen measurement and adoption decision.",
        "model_limits":"Conditioned finite heads-up two-selected-flop game with complete ordered future deals and narrow ranges with twelve globally inactive SB hands. No full-deck preflop, unrestricted NLHE, multiway, broad-range convergence, universal performance or formal floating-point certificate."}
    OUTPUT.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(f"report saved; runtime gate={report['runtime_gate_met']}; reduction={reduction:.3%}", flush=True)


if __name__ == "__main__":
    main()
