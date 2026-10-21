"""Opt-in CFR+ research adapter for the independently proved fixed flop game.

This module is deliberately outside production solver APIs. Admission retains
both historical physical-work ceilings; it does not infer a larger budget from
the compact representation. No convergence or performance claim is automatic.
"""
import argparse
from fractions import Fraction
import hashlib
import json
import math
import platform
from pathlib import Path

from pokerlab import cfr_plus
from scripts import flop_class_policy as policy
from scripts import flop_public_classes as proof
from scripts import verify_flop_public_classes_publication as publication


MAX_ITERATIONS = 140
MAX_WORLD_ITERATIONS = 3_000_000
MAX_DECISION_WORLD_ITERATIONS = 30_000_000
MAX_COMPACT_PATH_STATES = 64
EXPECTED_CENSUS = {
    "compact_public_states": 1001, "compact_decisions": 316,
    "compact_chance_nodes": 58, "compact_terminals": 627,
    "physical_policy_rows": 16912, "compact_policy_rows": 466,
    "physical_action_slots": 33824, "compact_action_slots": 932,
    "compact_worlds": 126, "turn_classes": 11, "river_signatures": 19,
}
ROOT = Path(__file__).resolve().parents[1]


def admit_request(iterations):
    """Reject the full requested work before proof, ranking or tree allocation."""
    if type(iterations) is not int or not 1 <= iterations <= MAX_ITERATIONS:
        raise ValueError("Fixed flop CFR+ requires integer iterations in [1, 140].")
    passes = 3 * iterations  # Two regret passes and one completed-profile average.
    physical_work = 5940 * passes
    physical_decision_work = 12 * physical_work
    if (physical_work > MAX_WORLD_ITERATIONS or
            physical_decision_work > MAX_DECISION_WORLD_ITERATIONS):
        raise ValueError("Full requested physical reference work exceeds the retained cap.")
    return {
        "version": "fixed-flop-class-cfrplus-admission-v1",
        "requested_iterations": iterations, "training_passes": passes,
        "retained_physical_world_iterations": physical_work,
        "retained_physical_decision_world_iterations": physical_decision_work,
        "compact_world_iterations": 126 * passes,
        "compact_state_visit_upper_bound": 126 * passes * MAX_COMPACT_PATH_STATES,
        "compact_action_slots": 932,
        "meaning": "Logical traversal counts and action slots, not time, bytes or RSS bounds.",
    }


def _source_hashes():
    hashes = proof._source_hashes()
    for name in ("scripts/flop_class_cfrplus.py", "scripts/flop_class_policy.py",
                 "scripts/verify_flop_public_classes_publication.py",
                 "scripts/verify_flop_class_cfrplus.py",
                 "pokerlab/cfr_plus.py", "pokerlab/cfr.py",
                 "benchmarks/flop-class-cfrplus-pilot-v1.json"):
        raw = (ROOT / name).read_bytes()
        proof._need(len(raw) <= 2 * 1024 * 1024, "Adapter source exceeds bound")
        hashes[name] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    return hashes


def _node_key(node, world):
    return node.player, world[node.player], node.history


def _chance_child(node, world):
    if isinstance(node, proof.physical._Chance):
        return node.branches[world[4][node.card_index]]
    return None


def _terminal_value(node, world):
    sign = (1 if node.winner == 0 else -1) if node.kind == "fold" else world[3]
    return float(sign * (Fraction(5) + min(Fraction(v) for v in node.contributions)))


def _training_inputs(model):
    """Validate the proof-owned model, then translate only rational joint mass."""
    census = proof.validate_model(model)
    proof._need(all(census.get(key) == value for key, value in EXPECTED_CENSUS.items()),
                "Fixed compact census differs from admitted dimensions")
    proof._need(len(model.worlds) == 126 and
                sum((w[2] for w in model.worlds), Fraction()) == 1 and
                all(type(w[2]) is Fraction and w[2] > 0 for w in model.worlds),
                "Fixed class joint masses differ")
    infos = {key: len(node.actions) for key, node in proof._class_rows(model).items()}
    proof._need(len(infos) == 466 and all(count == 2 for count in infos.values()),
                "Fixed compact policy dimensions differ")
    max_visits = 0
    for world in model.worlds:
        stack = [model.root]
        visits = 0
        while stack:
            node = stack.pop()
            visits += 1
            proof._need(visits <= MAX_COMPACT_PATH_STATES,
                        "Compact per-world traversal exceeds admitted bound")
            child = _chance_child(node, world)
            if child is not None:
                stack.append(child)
            elif isinstance(node, proof.physical._Decision):
                proof._need(_node_key(node, world) in infos,
                            "Compact decision exposes an unadmitted information set")
                stack.extend(node.children)
        max_visits = max(max_visits, visits)
    worlds = tuple((w[0], w[1], float(w[2]), w[3], w[4]) for w in model.worlds)
    proof._need(all(math.isfinite(w[2]) and w[2] > 0 for w in worlds),
                "Binary64 conversion loses positive chance support")
    return worlds, infos, max_visits


def solve_fixed(iterations=140):
    """Reconstruct proof, train, lift and independently audit one complete call.

    Proof reconstruction and final physical diagnostics are included. Raw average
    rows are retained before explicit output-grid normalization. Only this fixed
    game and zero averaging delay are supported.
    """
    admission = admit_request(iterations)
    sources = _source_hashes()
    receipt = publication.verify()
    with proof.independent_guard() as preparation_calls:
        model = proof.build_model()
        worlds, infos, max_visits = _training_inputs(model)
    # Training must be outside the independent oracle's forbidden-call guard.
    raw_rows = cfr_plus.train(model.root, worlds, infos, iterations,
                              terminal_value=_terminal_value, node_key=_node_key,
                              chance_child=_chance_child)
    proof._need(type(raw_rows) is dict and set(raw_rows) == set(infos),
                "Trainer output does not cover every compact information set")
    rows, normalization = policy.canonicalize_binary_rows(raw_rows)
    with proof.independent_guard() as diagnostic_calls:
        payload = proof.lift_policy(rows, model)
        payload.update(algorithm="cfrplus", iterations=iterations,
                       research_adapter="fixed-flop-public-classes-cfrplus-v1",
                       averaging_delay=0)
        audit = proof.audit_policy(payload, model)
    proof._need(_source_hashes() == sources, "Source changed during fixed flop solve")
    report = {
        "schema_version": "fixed-flop-class-cfrplus-v1",
        "status": "trained-policy-physically-verified",
        "source_lf_sha256": sources, "proof_receipt": receipt,
        "runtime": {"python": platform.python_version(),
                    "implementation": platform.python_implementation()},
        "admission": admission, "maximum_world_path_states": max_visits,
        "census": dict(model.census), "normalization": normalization,
        "raw_class_policy": [[p, hand, list(history), list(values)]
                             for (p, hand, history), values in sorted(raw_rows.items())],
        "physical_policy": payload, "audit": audit,
        "preparation_forbidden_calls": preparation_calls,
        "diagnostic_forbidden_calls": diagnostic_calls,
        "quality_target": 0.005,
        "quality_target_met": Fraction(audit["exact_metrics"]["nash_conv"]) <= Fraction(1, 200),
        "scope": "One fixed weighted full-deck flop game. Output-grid policy has exact physical own-hand responses. No unrestricted NLHE, raw-policy parity, new convergence or performance claim.",
    }
    report["artifact_sha256"] = proof._digest(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=140)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    admit_request(args.iterations)
    proof._need(not args.output.exists(), "Output already exists; preserve prior evidence")
    report = solve_fixed(args.iterations)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps({"status": report["status"], "iterations": args.iterations,
                      "nash_conv": report["physical_policy"]["nash_conv"],
                      "quality_target_met": report["quality_target_met"],
                      "artifact_sha256": report["artifact_sha256"]}))


if __name__ == "__main__":
    main()
