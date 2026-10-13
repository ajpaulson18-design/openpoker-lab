"""Compare isolated adapter payloads against supplied historical adapter files.

Shared dependencies use the current checkout. This measures only the isolated
adapter change; use a checkout where shared dependencies match the baseline.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from pokerlab.matrix_free_turn import solve_matrix_free_turn
from pokerlab.matrix_free_river import solve_matrix_free_river
from scripts.turn_river_validation import replay_policy, compare_result

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "431db6f261a3df21c1ccf5be17b96af485c1770c"
BASELINE_SOURCE = {
    "turn": "a76ad53d45fbeca8b6f52807b641979c58ac0b02e5a3b9ad4deef479bc1d5f4f",
    "river": "fd5fd29c40750413a85c93bb4dbd225847cc8e33d9702426044f606c011af709",
}


def load(directory, street):
    path = directory / ("baseline_matrix_free_" + street + ".py")
    canonical = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != BASELINE_SOURCE[street]:
        raise ValueError("Historical adapter source does not match the frozen baseline")
    name = "pokerlab._baseline_matrix_free_" + street
    spec = importlib.util.spec_from_file_location(
        name, directory / ("baseline_matrix_free_" + street + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return getattr(module, "solve_matrix_free_" + street)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    old_turn, old_river = load(args.baseline_dir, "turn"), load(args.baseline_dir, "river")
    paths = list((ROOT / "pokerlab").glob("*.py")) + [
        ROOT / "scripts/turn_river_validation.py",
        ROOT / "scripts/preflop_validation.py", Path(__file__),
        ROOT / "benchmarks/turn-river-quality-v1.json"]
    source_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(paths)}
    cases = json.loads((ROOT / "benchmarks/turn-river-quality-v1.json").read_text())["scenarios"]
    rows = []
    for case in cases:
        turn = len(case["board"]) == 8
        current, baseline = ((solve_matrix_free_turn, old_turn) if turn
                             else (solve_matrix_free_river, old_river))
        opts = {key: case[key] for key in ("runouts", "river_config") if key in case}
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            for target in (False, True):
                stopping = {"target_exploitability": 0.0, "check_interval": 10} if target else {}
                old = baseline(case["board"], case["oop"], case["ip"], case["config"],
                               iterations=20, algorithm=algorithm, **opts, **stopping)
                new = current(case["board"], case["oop"], case["ip"], case["config"],
                              iterations=20, algorithm=algorithm, **opts, **stopping)
                if old != new:
                    raise RuntimeError("Ordinary complete payload changed: " + case["id"])
                oracle = replay_policy(new, case["oop"], case["ip"], board=case["board"],
                                       config=case["config"], **opts)
                delta = compare_result(new, oracle)
                rows.append({"scenario": case["id"], "algorithm": algorithm,
                             "mode": "target" if target else "fixed", "iterations": new["iterations"],
                             "complete_payload_identical": True,
                             "max_scalar_difference": max(map(abs, delta.values()))})
                print(case["id"], algorithm, rows[-1]["mode"], "identical", flush=True)
    if any(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != h
           for p, h in source_hashes.items()):
        raise RuntimeError("Source changed during validation")
    report = {"baseline_commit": BASELINE, "source_sha256": source_hashes,
              "baseline_file_sha256": {street: hashlib.sha256(
                  (args.baseline_dir / ("baseline_matrix_free_" + street + ".py")).read_bytes()).hexdigest()
                  for street in ("turn", "river")},
              "scope": "Current shared dependencies; isolated adapter parity over four fixtures, all algorithms, fixed/zero-target modes at20; no performance claim.",
              "results": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
