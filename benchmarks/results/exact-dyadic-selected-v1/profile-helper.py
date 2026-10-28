"""Fresh-process query-core profiling; elapsed profiler costs are not benchmarks."""
import argparse
import cProfile
import hashlib
import importlib.util
import json
from pathlib import Path
import pstats
import subprocess
import sys

FROZEN = "9d8a084a08ddf24dded3a4c76b1bb60ba914df3e"
AUTH_SHA = "8171ead3ba108f8200f15e85696f40d109ed894209fa7d77598780b83c1401c5"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--study", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--mode", choices=("fraction", "dyadic"), required=True)
    args = p.parse_args()
    repo, out = args.repo.resolve(), args.output.resolve()
    if out.exists() or repo in out.parents:
        raise ValueError("New external output directory required")
    auth_path = Path(__file__).with_name("exact-selected-independent-review.py")
    if hashlib.sha256(auth_path.read_bytes()).hexdigest() != AUTH_SHA:
        raise ValueError("Source authentication helper changed")
    spec = importlib.util.spec_from_file_location("profile_source_auth", auth_path)
    auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(auth)
    auth.FROZEN = FROZEN
    captured = json.loads((args.study/"source-before.json").read_text())
    identity = auth.source_identity(repo, captured)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(repo))
    from scripts.benchmark_dyadic_selected_solver import case_for, request_for
    from pokerlab.exact_selected_solver import solve_four_street_exact_selected
    request = request_for(case_for("original"), 10)
    profiler = cProfile.Profile()
    result = profiler.runcall(solve_four_street_exact_selected, request,
                             rank_cache_boards=64, pair_diagnostics="compact", exact_arithmetic=args.mode)
    saved = json.loads((args.study/f"original-T10-{args.mode}-0.json").read_text())["payload"]
    for field in ("strategy", "value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value",
                  "sb_gain", "bb_gain", "nash_conv", "exploitability", "chance_input_snapshot"):
        if result[field] != saved[field]:
            raise ValueError("Profiled solve differs from frozen output: " + field)
    if auth.source_identity(repo, captured) != identity:
        raise ValueError("Source changed while profiling")
    out.mkdir(parents=True)
    profiler.dump_stats(str(out/"profile.pstats"))
    with (out/"profile.txt").open("w", encoding="utf-8") as stream:
        stats = pstats.Stats(profiler, stream=stream)
        stats.sort_stats("cumulative").print_stats(40)
        stats.sort_stats("tottime").print_stats(40)
    stats = pstats.Stats(profiler)
    data = [{"file": key[0], "line": key[1], "function": key[2],
             "primitive_calls": values[0], "calls": values[1], "self_seconds": values[2],
             "cumulative_seconds": values[3]} for key, values in stats.stats.items()]
    record = {"source_commit": FROZEN, "mode": args.mode, "iterations": 10,
              "profiled_policy_and_eight_metrics_match_frozen": True,
              "source_unchanged_after": True, "source_files": identity["files"], "functions": data,
              "helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "scope": "One instrumented T10 complete solve. cProfile overhead changes timing; function counts/cumulative attribution are profiling evidence, not a same-work speed benchmark."}
    (out/"profile.json").write_text(json.dumps(record, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps({"outcome": "profiled", "mode": args.mode, "functions": len(data),
                      "profile_json_sha256": hashlib.sha256((out/"profile.json").read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
