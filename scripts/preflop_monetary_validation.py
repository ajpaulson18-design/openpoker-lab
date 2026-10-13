"""Verify the configured monetary game and retain a separate historical diagnostic."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path
import platform

from pokerlab.preflop_solver import solve_preflop
from scripts.benchmark_turn_solver import file_sha256, git_revision, worktree_dirty
from scripts.preflop_validation import compare_result, replay_policy

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("pokerlab/preflop_solver.py", "pokerlab/preflop_tree.py",
           "pokerlab/postflop_solver.py", "pokerlab/river_tree.py", "pokerlab/river_config.py",
           "pokerlab/cfr.py", "pokerlab/cfr_plus.py", "pokerlab/planned_cfr.py",
           "pokerlab/public_cfr.py", "pokerlab/cards.py", "pokerlab/analysis.py",
           "scripts/preflop_validation.py", "scripts/preflop_monetary_validation.py",
           "scripts/benchmark_turn_solver.py", "benchmarks/preflop-monetary-replay-v1.json",
           "benchmarks/preflop-rounding-boundary-v1.json")


def midpoint_anchor():
    """Hand-derived local/whole-hand amounts; no production numeric helpers."""
    origin = Decimal("0.691357802")
    pot = 2 * origin
    bet = Decimal("0.170705629")
    exact_local = bet + Decimal("0.25") * (pot + 2 * bet)
    local_binary = float(bet) + .25 * (float(pot) + float(bet) + float(bet))
    local_rounded = round(local_binary, 9)
    whole_hand = round(float(origin) + local_rounded, 9)
    exact_global = origin + exact_local
    historical_global = round(float(Fraction(str(exact_global))), 9)
    assert exact_local == Decimal("0.6017373445")
    assert Decimal.from_float(local_binary) < exact_local
    assert local_rounded == .601737344
    assert whole_hand == 1.293095146
    assert historical_global == 1.293095147
    return {"origin": str(origin), "initial_postflop_pot": str(pot),
            "local_bet": str(bet), "exact_local_midpoint": str(exact_local),
            "local_binary_value": str(Decimal.from_float(local_binary)),
            "rounded_local_target": local_rounded, "configured_whole_hand_target": whole_hand,
            "exact_global_midpoint": str(exact_global),
            "historical_global_binary_quantization": historical_global,
            "scope": "This trace explains the quantization order, not a claim that either binary rounding path is an exact-decimal specification."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "benchmarks/preflop-monetary-replay-v1.json")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/results/preflop-monetary-replay-v1.json")
    args = parser.parse_args()
    specification = json.loads(args.config.read_text(encoding="utf-8"))
    anchor = midpoint_anchor()
    records = []
    for scenario in specification["scenarios"]:
        fixture = (json.loads((ROOT / scenario["fixture_path"]).read_text(encoding="utf-8"))
                   if "fixture_path" in scenario else scenario)
        kwargs = {key: fixture[key] for key in
                  ("config", "runouts", "flop_config", "turn_config", "river_config")
                  if key in fixture}
        peers = []
        for algorithm, traversal in specification["routes"]:
            candidate = solve_preflop(fixture["sb"], fixture["bb"],
                                     algorithm=algorithm, traversal=traversal,
                                     iterations=specification["iterations"], **kwargs)
            checked = replay_policy(candidate, fixture["sb"], fixture["bb"],
                                    monetary_mode="configured", **kwargs)
            gaps = compare_result(candidate, checked)
            assert checked["checked_information_sets"] == len(candidate["strategy"])
            posterior = {(row["sb_hand"], row["bb_hand"]): row["probability"]
                         for row in candidate["private_pair_probabilities"]}
            expected = {(row["sb"], row["bb"]): row["probability"]
                        for row in checked["private_pair_probabilities"]}
            assert posterior.keys() == expected.keys()
            assert max(abs(posterior[key] - expected[key]) for key in posterior) <= 1e-12
            if "known_sb_best_response_value" in scenario:
                assert abs(checked["sb_best_response_value"] - scenario["known_sb_best_response_value"]) <= 1e-12
            if scenario["id"] == "recorded-rounding-boundary":
                matching = [row for row in candidate["strategy"]
                            if row["history"] == fixture["mismatch"]["history_prefix"]]
                assert len(matching) == 1
                assert any(action["history_key"] == "raise@1.293095146"
                           for action in matching[0]["actions"])
            try:
                reference = replay_policy(candidate, fixture["sb"], fixture["bb"],
                                          monetary_mode="global-rational", **kwargs)
                diagnostic = {"outcome": "accepted", "replay": reference}
            except AssertionError as error:
                diagnostic = {"outcome": "rejected", "exception": "AssertionError", "detail": str(error)}
            if "global_reference_expected" in scenario:
                assert diagnostic["outcome"] == scenario["global_reference_expected"], diagnostic
            if scenario["id"] == "recorded-rounding-boundary":
                assert "raise@1.293095146" in diagnostic["detail"], diagnostic
                assert "raise@1.293095147" in diagnostic["detail"], diagnostic
            record = {"scenario": scenario["id"], "algorithm": algorithm, "traversal": traversal,
                      "iterations": specification["iterations"], "worlds": candidate["worlds"],
                      "information_sets": candidate["info_sets"],
                      "configured_replay": checked, "metric_absolute_gaps": gaps,
                      "historical_global_reference": diagnostic}
            records.append(record)
            peers.append((algorithm, candidate))
            print(f'{scenario["id"]} {algorithm}/{traversal}: configured verified; '
                  f'global reference {diagnostic["outcome"]}', flush=True)
        # Same algorithm on another backend must still solve the same game.
        for algorithm in {entry[0] for entry in peers}:
            routes = [candidate for name, candidate in peers if name == algorithm]
            for field in ("value_sb", "nash_conv", "sb_best_response_value", "bb_best_response_value"):
                assert max(item[field] for item in routes) - min(item[field] for item in routes) <= 1e-10
    report = {"schema_version": 1, "benchmark_id": specification["benchmark_id"],
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "source_revision": git_revision(None), "worktree_dirty": worktree_dirty(),
              "source_hashes": {path: file_sha256(ROOT / path) for path in SOURCES},
              "python": platform.python_version(), "platform": platform.platform(),
              "scope": "Independent configured binary64/local-ledger replay, all serialized rows, values and legal best responses in three conditioned finite games. No exact-decimal equivalence or universal rounding proof.",
              "diagnostic_scope": "Historical Fraction/global-ledger replay retains its conversion to binary64 at nine-decimal quantization. It is a separate model diagnostic, not an exact-decimal oracle.",
              "performance_scope": "Correctness evidence only; no runtime or memory comparison was measured.",
              "midpoint_anchor": anchor, "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
