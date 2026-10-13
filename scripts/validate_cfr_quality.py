"""Validate production CFR kernels against independently known Kuhn quality."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import sys

from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty
from scripts.cfr_quality import training_report, verify_known_equilibrium_family


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "benchmarks/cfr-quality-v1.json"
SOURCE_FILES = tuple("pokerlab/" + name for name in (
    "postflop_solver.py", "turn_solver.py", "cfr.py", "planned_cfr.py",
    "public_cfr.py", "river_tree.py", "river_config.py", "cards.py",
)) + ("scripts/cfr_quality.py", "scripts/validate_cfr_quality.py",
      "scripts/benchmark_turn_solver.py")


def _validate_config(config):
    expected_game = {
        "ranks": ["J", "Q", "K"], "ante_per_player": 1, "bet": 1,
        "ordered_distinct_deals": 6, "public_decision_nodes": 4,
        "information_sets": 12, "known_value_first_player": "-1/18",
    }
    if any(config["game"].get(key) != value for key, value in expected_game.items()):
        raise ValueError("Config must describe the implemented three-card Kuhn game.")
    iterations = config["iterations"]
    if (not isinstance(iterations, list) or len(iterations) < 2 or
            any(type(value) is not int or not 1 <= value <= 10000
                for value in iterations) or
            iterations != sorted(set(iterations))):
        raise ValueError("Use at least two increasing checkpoints within 1–10,000.")
    for field, allowed in (
        ("algorithms", {"vanilla", "dcfr"}),
        ("backends", {"recursive", "planned", "public-batched"}),
    ):
        values = config[field]
        if (not isinstance(values, list) or not values or
                any(value not in allowed for value in values) or
                len(set(values)) != len(values)):
            raise ValueError(f"Config {field} must be unique supported names.")
    gates = config["gates"]
    if gates["final_iterations"] != iterations[-1]:
        raise ValueError("The final quality gate must match the last checkpoint.")
    limits = [gates[key] for key in (
        "max_value_error", "max_shared_oracle_metric_difference",
        "max_rational_replay_difference", "max_final_to_initial_gap_ratio",
    )] + [gates["max_nash_conv"][algorithm] for algorithm in config["algorithms"]]
    if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
           for value in limits):
        raise ValueError("Quality limits must be finite positive numbers.")
    if gates["max_final_to_initial_gap_ratio"] >= 1:
        raise ValueError("The gap-reduction ratio must be below one.")


def check_gates(rows, config):
    """Apply explicit empirical gates to independently measured metrics."""
    gates = config["gates"]
    failures = []
    for row in rows:
        label = f"{row['backend']}/{row['algorithm']}/{row['iterations']}"
        metrics = ("value_p1", "value_error", "nash_conv", "p1_gain", "p2_gain",
                   "shared_metric_max_abs_difference", "rational_replay_float_delta")
        if any(not math.isfinite(row[key]) for key in metrics):
            failures.append(label + ": non-finite metric")
            continue
        if row["shared_metric_max_abs_difference"] > gates["max_shared_oracle_metric_difference"]:
            failures.append(label + ": production metrics disagree with independent oracle")
        if abs(row["rational_replay_float_delta"]) > gates["max_rational_replay_difference"]:
            failures.append(label + ": float/rational replay difference exceeds limit")

    indexed = {(row["backend"], row["algorithm"], row["iterations"]): row for row in rows}
    for backend in config["backends"]:
        for algorithm in config["algorithms"]:
            first = indexed[(backend, algorithm, config["iterations"][0])]
            final = indexed[(backend, algorithm, gates["final_iterations"])]
            label = f"{backend}/{algorithm}"
            if final["nash_conv"] >= gates["max_nash_conv"][algorithm]:
                failures.append(label + ": final NashConv exceeds limit")
            if final["value_error"] >= gates["max_value_error"]:
                failures.append(label + ": final value error exceeds limit")
            if final["nash_conv"] >= first["nash_conv"] * gates["max_final_to_initial_gap_ratio"]:
                failures.append(label + ": insufficient gap reduction from first checkpoint")
    return failures


def _hashes(config_path):
    result = {name: file_sha256(ROOT / name) for name in SOURCE_FILES}
    result["config"] = file_sha256(config_path)
    if any(value is None for value in result.values()):
        raise ValueError("A required validation source or config file is missing.")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    try:
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        _validate_config(config)
        before = _hashes(config_path)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    revision = git_revision(None)
    dirty = worktree_dirty()
    proof = verify_known_equilibrium_family()
    rows = []
    for iterations in config["iterations"]:
        for algorithm in config["algorithms"]:
            for backend in config["backends"]:
                row = training_report(iterations, algorithm, backend)
                rows.append(row)
                print(f"{backend} {algorithm} {iterations}: "
                      f"NashConv {row['nash_conv']:.6g}, "
                      f"value error {row['value_error']:.6g}", flush=True)
    after = _hashes(config_path)
    if before != after:
        raise RuntimeError("Validation source/config changed; discard this run.")
    failures = check_gates(rows, config)
    report = {
        "schema_version": 1, "benchmark_id": config["benchmark_id"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "provenance": {
            "git_revision": revision, "worktree_dirty": dirty,
            "python_version": platform.python_version(),
            "python_executable": sys.executable, "platform": platform.platform(),
            "source_sha256": before, "source_unchanged": True,
        },
        "methodology": {
            "oracle": "Direct Kuhn terminal-history payoffs; exhaustive 64 private-hand-contingent pure policies per responder",
            "analytic_check": "Exact rational policies and worlds at three published equilibrium-family points",
            "training_time": "Single selected-trainer wall time, excluding adapter setup, oracle work and production metric checks",
            "rational_replay": "Represented float probabilities converted to exact ratios and each row renormalized before exact chance integration",
            "scope": "Known small-game kernel validation; no Hold'em equilibrium accuracy certificate",
        },
        "known_equilibrium_checks": proof, "results": rows,
        "passed": not failures, "failures": failures,
    }
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
                      encoding="utf-8")
    print(f"Wrote {len(rows)} quality checkpoints to {output}; "
          f"{'PASS' if not failures else 'FAIL'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
