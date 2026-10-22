"""Independently replay a saved explicit compact-budget fixed-flop policy."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import struct

from scripts import flop_class_compact_budget as budget
from scripts import flop_class_compact_cfrplus as trainer
from scripts import flop_class_policy as policy
from scripts import flop_public_classes as proof
from scripts import verify_flop_class_cfrplus as legacy_replay
from scripts import verify_flop_class_cfrplus_publication as baseline
from scripts import verify_flop_public_classes_publication as publication


MAX_REPORT_BYTES = 24 * 1024 * 1024


def verify_saved(path):
    path = Path(path)
    proof._need(path.stat().st_size <= MAX_REPORT_BYTES, "Report exceeds size bound")
    raw = path.read_bytes()
    proof._need(len(raw) <= MAX_REPORT_BYTES, "Report exceeds size bound")
    report = json.loads(raw, object_pairs_hook=legacy_replay._pairs,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    proof._need(type(report) is dict and report.get("schema_version") == trainer.ADAPTER and
                report.get("status") == "trained-policy-physically-verified",
                "Compact report scope/status differs")
    unsigned = {k: v for k, v in report.items() if k != "artifact_sha256"}
    proof._need(proof._digest(unsigned) == report.get("artifact_sha256"),
                "Compact report checksum differs")
    sources = trainer.source_hashes()
    proof._need(report["source_lf_sha256"] == sources, "Compact report source differs")
    payload = report["physical_policy"]
    iterations = payload["iterations"]
    expected_admission = budget.admit_compact_request(iterations)
    proof._need(proof._typed(report["admission"]) == proof._typed(expected_admission) and
                payload["algorithm"] == "cfrplus" and
                type(payload["averaging_delay"]) is int and payload["averaging_delay"] == 0 and
                payload["research_adapter"] == trainer.ADAPTER and
                payload["resource_model"] == expected_admission["version"],
                "Compact report method or admission differs")
    expected_baseline = {"raw_sha256": baseline.RAW_SHA256,
                         "artifact_sha256": baseline.ARTIFACT_SHA256,
                         "nash_conv": baseline.EXPECTED_NASH_CONV, "quality_target_met": False}
    proof._need(proof._typed(report["baseline_pilot"]) == proof._typed(expected_baseline),
                "Historical pilot miss differs")
    rows, normalization = policy.canonicalize_binary_rows(legacy_replay._raw_rows(report["raw_class_policy"]))
    proof._need(proof._typed(normalization) == proof._typed(report["normalization"]),
                "Compact normalization audit differs")
    baseline._read(baseline.PUBLICATION)
    receipt = publication.verify()
    proof._need(proof._typed(receipt) == proof._typed(report["proof_receipt"]),
                "Compact proof receipt differs")
    with proof.independent_guard() as calls:
        model = proof.build_model()
        _, infos, max_visits = trainer.base._training_inputs(model)
        budget.validate_observed_dimensions(model.census, max_visits, infos)
        proof._need(set(rows) == set(infos) and
                    proof._typed(model.census) == proof._typed(report["census"]) and
                    type(report["maximum_world_path_states"]) is int and
                    report["maximum_world_path_states"] == max_visits,
                    "Compact recorded dimensions differ")
        projected = proof.project_policy(payload, model)
        proof._need(all(tuple(struct.pack(">d", v) for v in rows[key]) ==
                        tuple(struct.pack(">d", v) for v in projected[key]) for key in rows),
                    "Compact physical policy differs from normalized raw rows")
        actual = proof.audit_policy(payload, model)
    proof._need(proof._typed(actual) == proof._typed(report["audit"]),
                "Compact saved independent audit differs")
    proof._need(proof._typed(report["preparation_forbidden_calls"]) == proof._typed(calls) and
                proof._typed(report["diagnostic_forbidden_calls"]) == proof._typed(calls) and
                all(type(v) is int and v == 0 for v in calls.values()),
                "Compact independent authority guards differ")
    met = Fraction(actual["exact_metrics"]["nash_conv"]) <= Fraction(1, 200)
    proof._need(type(report["quality_target"]) is float and report["quality_target"] == 0.005 and
                type(report["quality_target_met"]) is bool and report["quality_target_met"] == met,
                "Compact saved quality gate differs")
    proof._need(trainer.source_hashes() == sources, "Source changed during compact saved replay")
    return {"status": "saved-compact-policy-physically-verified", "training_calls": 0,
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
