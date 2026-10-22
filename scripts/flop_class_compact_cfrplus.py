"""Explicit compact-work CFR+ research call for the proved fixed flop game.

The legacy 140-sweep adapter and its source-pinned pilot remain unchanged.
This separate entry charges a versioned logical envelope before preparation.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import platform

from pokerlab import cfr_plus
from scripts import flop_class_cfrplus as base
from scripts import flop_class_compact_budget as budget
from scripts import flop_class_policy as policy
from scripts import flop_public_classes as proof
from scripts import verify_flop_class_cfrplus_publication as baseline
from scripts import verify_flop_public_classes_publication as publication


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = "fixed-flop-class-compact-cfrplus-v1"


def source_hashes():
    sources = base._source_hashes()
    for name in ("scripts/flop_class_compact_cfrplus.py",
                 "scripts/flop_class_compact_budget.py",
                 "scripts/verify_flop_class_compact_cfrplus.py",
                 "scripts/verify_flop_class_cfrplus_publication.py",
                 "benchmarks/flop-class-compact-cfrplus-pilot-v1.json"):
        path = ROOT / name
        proof._need(path.stat().st_size <= 2 * 1024 * 1024,
                    "Compact adapter source exceeds bound")
        raw = path.read_bytes()
        proof._need(len(raw) <= 2 * 1024 * 1024, "Compact adapter source exceeds bound")
        sources[name] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    return sources


def solve_fixed_compact(iterations=560):
    """Train within explicit compact admission, preserving physical diagnostics."""
    admission = budget.admit_compact_request(iterations)
    sources = source_hashes()
    baseline._read(baseline.PUBLICATION)
    receipt = publication.verify()
    with proof.independent_guard() as preparation_calls:
        model = proof.build_model()
        worlds, infos, max_visits = base._training_inputs(model)
        budget.validate_observed_dimensions(model.census, max_visits, infos)
    raw_rows = cfr_plus.train(model.root, worlds, infos, iterations,
                              terminal_value=base._terminal_value, node_key=base._node_key,
                              chance_child=base._chance_child)
    proof._need(type(raw_rows) is dict and set(raw_rows) == set(infos),
                "Compact trainer does not cover every information set")
    rows, normalization = policy.canonicalize_binary_rows(raw_rows)
    with proof.independent_guard() as diagnostic_calls:
        payload = proof.lift_policy(rows, model)
        payload.update(algorithm="cfrplus", iterations=iterations,
                       research_adapter=ADAPTER, averaging_delay=0,
                       resource_model=admission["version"])
        audit = proof.audit_policy(payload, model)
    proof._need(source_hashes() == sources, "Source changed during compact solve")
    report = {
        "schema_version": ADAPTER,
        "status": "trained-policy-physically-verified",
        "source_lf_sha256": sources, "proof_receipt": receipt,
        "runtime": {"python": platform.python_version(),
                    "implementation": platform.python_implementation()},
        "baseline_pilot": {"raw_sha256": baseline.RAW_SHA256,
                           "artifact_sha256": baseline.ARTIFACT_SHA256,
                           "nash_conv": baseline.EXPECTED_NASH_CONV,
                           "quality_target_met": False},
        "admission": admission, "maximum_world_path_states": max_visits,
        "census": dict(model.census), "normalization": normalization,
        "raw_class_policy": [[p, hand, list(history), list(values)]
                             for (p, hand, history), values in sorted(raw_rows.items())],
        "physical_policy": payload, "audit": audit,
        "preparation_forbidden_calls": preparation_calls,
        "diagnostic_forbidden_calls": diagnostic_calls,
        "quality_target": 0.005,
        "quality_target_met": Fraction(audit["exact_metrics"]["nash_conv"]) <= Fraction(1, 200),
        "scope": "One independently proved weighted full-deck flop game under explicit compact logical admission. Exact physical own-hand responses describe the normalized output. No broader game, raw-policy parity, general convergence, runtime, bytes or RSS claim.",
    }
    report["artifact_sha256"] = proof._digest(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=560)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    budget.admit_compact_request(args.iterations)
    proof._need(not args.output.exists(), "Output exists; preserve all earlier evidence")
    report = solve_fixed_compact(args.iterations)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps({"status": report["status"], "iterations": args.iterations,
                      "nash_conv": report["physical_policy"]["nash_conv"],
                      "quality_target_met": report["quality_target_met"],
                      "artifact_sha256": report["artifact_sha256"]}))


if __name__ == "__main__":
    main()
