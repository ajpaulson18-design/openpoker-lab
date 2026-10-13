"""Hash-check saved extension policies and replay with the hardened oracle."""
import argparse
import hashlib
import json
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path

from scripts import turn_river_validation as validator
from scripts.river_analytical import serialized_profile, metrics


def rational_polarised(result, case):
    # Explicitly admit only the independently specified one-bet anchor game.
    if (case["board"] != "2c7d9hJsKd" or case["oop"] != "AsAh,3c4c" or
            case["ip"] != "QsQh" or case["config"] != {
                "pot": 100, "effective_stack": 100, "bet_sizes": [1.0],
                "include_all_in": False}):
        raise ValueError("Fixture does not match the exact rational anchor")
    # At stack=bet=100 the configured builder labels the single capped wager
    # all_in. Its terminal histories equal the anchor's one-bet histories.
    witness_input = deepcopy(result)
    for row in witness_input["strategy"]:
        row["history"] = ["bet@100" if token == "all_in@100" else token
                          for token in row["history"]]
    raw = serialized_profile(witness_input)
    binary = {key: tuple(F.from_float(float(p)) for p in row)
              for key, row in raw.items()}
    normalized = {key: tuple(p / sum(row) for p in row)
                  for key, row in binary.items()}
    adjustment = max(abs(float(p - q)) for key, row in binary.items()
                     for p, q in zip(row, normalized[key]))
    value, br0, br1 = metrics(normalized)
    if not -br1 <= F(25) <= br0:
        raise ValueError("Exact rational response interval misses the known game value")
    if any(abs(float(exact) - result[field]) > 1e-9 for field, exact in (
            ("value_oop", value), ("oop_best_response_value", br0),
            ("ip_best_response_value", br1))):
        raise ValueError("Exact rational witness differs materially from learned diagnostics")
    return {"scope": "Exact binary64 probabilities normalized per row as Fractions; five independent terminal histories and 16/4 legal pure responses.",
            "max_probability_normalization_adjustment": adjustment,
            "value_oop_fraction": str(value), "oop_br_fraction": str(br0),
            "ip_br_fraction": str(br1), "value_lower_fraction": str(-br1),
            "value_upper_fraction": str(br0), "nash_conv_fraction": str(br0 + br1),
            "known_game_value_fraction": "25", "known_value_in_interval": True,
            "target_met": br0 + br1 <= F(1, 1000)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--policies-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = json.loads(args.report.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in report["fixtures"]}
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)
    validator_path = Path(validator.__file__)
    validator_hash = hashlib.sha256(validator_path.read_bytes()).hexdigest()
    rows = []
    for row in report["results"]:
        path = args.policies_dir / row["policy_file"]
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != row["policy_sha256"]:
            raise ValueError("Saved policy byte hash differs from its report")
        result = json.loads(payload)
        case = cases[row["scenario"]]
        oracle = validator.replay_policy(result, case["oop"], case["ip"],
                                         board=case["board"], config=case["config"])
        differences = validator.compare_result(result, oracle)
        checked = {"scenario": row["scenario"], "backend": row["backend"],
                   "iterations": row["iterations"], "policy_sha256": row["policy_sha256"],
                   "scalar_differences": differences, "verified_worlds": oracle["worlds"],
                   "verified_information_sets": oracle["checked_information_sets"]}
        if row["scenario"] == "river-polarised-bluffcatcher":
            checked["exact_rational_witness"] = rational_polarised(result, case)
        rows.append(checked)
    if hashlib.sha256(validator_path.read_bytes()).hexdigest() != validator_hash:
        raise RuntimeError("Hardened validator changed during saved-policy replay")
    output = {"schema_version": 1, "extension_report_canonical_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
              "hardened_validator_sha256": validator_hash,
              "replay_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "results": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print("Verified and replayed", len(rows), "saved policies with eight metrics each")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
