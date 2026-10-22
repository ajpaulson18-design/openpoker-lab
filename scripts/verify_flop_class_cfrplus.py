"""Replay a fixed-flop class CFR+ report without retraining or trusting metrics."""
import argparse
import json
from fractions import Fraction
from pathlib import Path
import struct

from scripts import flop_class_cfrplus as trainer
from scripts import flop_class_policy as policy
from scripts import flop_public_classes as proof
from scripts import verify_flop_public_classes_publication as publication


MAX_REPORT_BYTES = 24 * 1024 * 1024


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        proof._need(key not in result, "Duplicate report JSON field")
        result[key] = value
    return result


def _raw_rows(value):
    proof._need(type(value) is list and len(value) == 466,
                "Report must retain all 466 raw compact rows")
    rows = {}
    for row in value:
        proof._need(type(row) is list and len(row) == 4 and type(row[2]) is list,
                    "Malformed raw policy row")
        player, hand, history, probabilities = row
        # Validate types and bounds before constructing a hashable key.
        proof._need(type(player) is int and player in (0, 1) and type(hand) is str and
                    len(hand) == 4 and len(history) <= 32 and
                    all(type(token) is str and len(token) <= 64 for token in history),
                    "Malformed raw policy key")
        key = (player, hand, tuple(history))
        proof._need(key not in rows, "Duplicate raw compact information set")
        rows[key] = probabilities
    return rows


def verify_saved(path):
    path = Path(path)
    proof._need(path.stat().st_size <= MAX_REPORT_BYTES, "Report exceeds size bound")
    raw = path.read_bytes()
    proof._need(len(raw) <= MAX_REPORT_BYTES, "Report exceeds size bound")
    report = json.loads(raw, object_pairs_hook=_pairs,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    proof._need(type(report) is dict and report.get("schema_version") ==
                "fixed-flop-class-cfrplus-v1" and report.get("status") ==
                "trained-policy-physically-verified", "Report scope/status differs")
    unsigned = {k: v for k, v in report.items() if k != "artifact_sha256"}
    proof._need(proof._digest(unsigned) == report.get("artifact_sha256"),
                "Report checksum differs")
    sources = trainer._source_hashes()
    proof._need(report["source_lf_sha256"] == sources, "Report executable sources differ")
    payload = report["physical_policy"]
    iterations = payload["iterations"]
    proof._need(proof._typed(report["admission"]) == proof._typed(trainer.admit_request(iterations)) and
                payload["algorithm"] == "cfrplus" and
                type(payload["averaging_delay"]) is int and payload["averaging_delay"] == 0 and
                payload["research_adapter"] == "fixed-flop-public-classes-cfrplus-v1",
                "Recorded request or training method differs")
    rows, normalization = policy.canonicalize_binary_rows(_raw_rows(report["raw_class_policy"]))
    proof._need(proof._typed(normalization) == proof._typed(report["normalization"]), "Normalization audit differs")
    receipt = publication.verify()
    proof._need(proof._typed(report["proof_receipt"]) == proof._typed(receipt),
                "Saved proof receipt differs")
    with proof.independent_guard() as calls:
        model = proof.build_model()
        _, infos, max_visits = trainer._training_inputs(model)
        proof._need(set(rows) == set(infos) and proof._typed(report["census"]) == proof._typed(model.census) and
                    type(report["maximum_world_path_states"]) is int and
                    report["maximum_world_path_states"] == max_visits,
                    "Recorded compact model differs")
        projected = proof.project_policy(payload, model)
        proof._need(all(tuple(struct.pack(">d", v) for v in rows[key]) ==
                        tuple(struct.pack(">d", v) for v in projected[key]) for key in rows),
                    "Physical policy differs from normalized raw compact rows")
        actual = proof.audit_policy(payload, model)
    proof._need(proof._typed(actual) == proof._typed(report["audit"]), "Saved independent audit differs from replay")
    proof._need(proof._typed(report["preparation_forbidden_calls"]) == proof._typed(calls) and
                proof._typed(report["diagnostic_forbidden_calls"]) == proof._typed(calls) and
                all(type(v) is int and v == 0 for v in calls.values()),
                "Saved independent authority guards differ")
    met = Fraction(actual["exact_metrics"]["nash_conv"]) <= Fraction(1, 200)
    proof._need(type(report["quality_target"]) is float and report["quality_target"] == 0.005 and
                type(report["quality_target_met"]) is bool and report["quality_target_met"] == met,
                "Saved quality gate differs")
    proof._need(trainer._source_hashes() == sources, "Source changed during saved replay")
    return {"status": "saved-trained-policy-physically-verified", "training_calls": 0,
            "iterations": iterations, "class_rows": len(rows),
            "physical_rows": actual["physical_rows_lifted"],
            "nash_conv": float(Fraction(actual["exact_metrics"]["nash_conv"])),
            "quality_target_met": met, "artifact_sha256": report["artifact_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_saved(args.path), sort_keys=True))


if __name__ == "__main__":
    main()
