"""Authenticate and reconstruct the fixed flop no-training equivalence proof."""
import hashlib
import json
from pathlib import Path

from scripts import flop_public_classes as audit


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "benchmarks/results/flop-public-classes-v1.json"
INTERRUPTION = ROOT / "benchmarks/results/flop-public-classes-initial-interruption-v1.json"
RAW_SHA256 = "c661a01a579b59053e93f7200d68dcda595df858dc5592cf9921e8f7a692e66a"
ARTIFACT_SHA256 = "996cd561cac42c63df41052df7e32168cfe5b1bb194c08bcc5b427c1fec6792d"
INTERRUPTION_SHA256 = "53bd788b0eb7ea1fa0f0fb40aecffd76f6bf5238c9d6bb58a2d87b371c4df55a"


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        audit._need(key not in value, "Duplicate proof-record field")
        value[key] = item
    return value


def _read(path, limit, expected):
    audit._need(path.stat().st_size <= limit, "Proof record exceeds size bound")
    raw = path.read_bytes()
    audit._need(len(raw) <= limit and hashlib.sha256(raw).hexdigest() == expected,
                "Immutable proof-record raw hash differs")
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))


def authenticate():
    report = _read(RESULT, 2*1024*1024, RAW_SHA256)
    interruption = _read(INTERRUPTION, 4096, INTERRUPTION_SHA256)
    unsigned = {k: v for k, v in report.items() if k != "artifact_sha256"}
    audit._need(audit._digest(unsigned) == report["artifact_sha256"] == ARTIFACT_SHA256,
                "Proof artifact checksum differs")
    audit._need(report["schema_version"] == "fixed-flop-public-classes-audit-v1" and
                report["status"] == "no-training-equivalence-verified" and
                type(report["training_calls"]) is int and report["training_calls"] == 0,
                "Proof scope/status differs")
    audit._need(interruption["status"] == "execution-interrupted-no-final-output",
                "Initial execution interruption must remain explicit")
    audit._need(report["physical_worlds_sha256"] == audit.PHYSICAL_WORLDS_SHA256 and
                report["physical_tree_sha256"] == audit.PHYSICAL_TREE_SHA256 and
                report["source_lf_sha256"] == audit._source_hashes(),
                "Frozen proof sources or physical anchors differ")
    audit._need(type(report["forbidden_production_calls"]) is dict and
                len(report["forbidden_production_calls"]) == 41 and
                all(type(v) is int and v == 0 for v in report["forbidden_production_calls"].values()),
                "Frozen proof called production authorities")
    return report


def verify():
    report = authenticate()
    sources = audit._source_hashes()
    with audit.independent_guard() as calls:
        model = audit.build_model()
        audit._need(audit._typed(model.census) == audit._typed(report["census"]) and
                    audit._typed(model.partition) == audit._typed(report["partition"]),
                    "Reconstructed fixed quotient differs")
        for mode in ("check-call", "bet-fold", "class-varying", "zero-reach"):
            actual = audit.audit_policy(audit.control_policy(model, mode), model)
            saved = report["controls"][mode]
            fields = ("exact_metrics", "exact_metric_count", "physical_rows_lifted",
                      "class_rows", "physical_policy_sha256", "physical_strategy_sha256",
                      "class_policy")
            audit._need(all(audit._typed(actual[k]) == audit._typed(saved[k]) for k in fields),
                        "Reconstructed control policy or exact metrics differ: " + mode)
            audit._need(max(abs(actual["independent_numeric_metrics"][k] -
                               saved["independent_numeric_metrics"][k])
                           for k in audit.METRICS) <= 1e-10,
                        "Reconstructed independent numeric metrics differ: " + mode)
    audit._need(calls == report["forbidden_production_calls"] and
                sources == audit._source_hashes(), "Proof verification sources/guards differ")
    return {"status": "verified-no-training-equivalence", "controls_replayed": 4,
            "physical_worlds_reenumerated": 5940, "class_worlds": 126,
            "exact_metrics_per_control": 8, "training_calls": 0,
            "raw_sha256": RAW_SHA256, "artifact_sha256": ARTIFACT_SHA256}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
