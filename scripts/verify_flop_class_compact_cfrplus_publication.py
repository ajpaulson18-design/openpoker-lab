"""Authenticate and independently replay the immutable compact CFR+ pilot."""
import argparse
import hashlib
import json
from pathlib import Path

from scripts import flop_public_classes as proof
from scripts import verify_flop_class_compact_cfrplus as replay
from scripts import verify_flop_class_cfrplus_publication as baseline


PUBLICATION = (Path(__file__).resolve().parents[1] /
               "benchmarks/results/flop-class-compact-cfrplus-pilot-v1.json")
RAW_SHA256 = "44e4e3a70713d0b7c69e8a20845c66478febe60db8dad854a43c8ecc302e3b4e"
ARTIFACT_SHA256 = "982e90ea073b1dfefa65662945c9b8178683bc4079ca5a9ae0af3a0d5f9c4334"
MAX_REPORT_BYTES = 24 * 1024 * 1024
EXPECTED_ITERATIONS = 560
EXPECTED_RAW_ROWS = 466
EXPECTED_PHYSICAL_ROWS = 16_912
EXPECTED_NASH_CONV = 0.0028924005277596834


def _read(path):
    path = Path(path)
    proof._need(not path.is_symlink() and path.is_file() and
                path.stat().st_size <= MAX_REPORT_BYTES,
                "Invalid bounded compact pilot report")
    raw = path.read_bytes()
    proof._need(type(raw) is bytes and len(raw) <= MAX_REPORT_BYTES,
                "Compact pilot report exceeds size bound")
    proof._need(hashlib.sha256(raw).hexdigest() == RAW_SHA256,
                "Immutable compact pilot report bytes changed")
    report = json.loads(raw, object_pairs_hook=replay.legacy_replay._pairs,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    proof._need(type(report) is dict and
                report.get("schema_version") == replay.trainer.ADAPTER and
                report.get("status") == "trained-policy-physically-verified",
                "Compact pilot report scope or status differs")
    unsigned = {key: value for key, value in report.items() if key != "artifact_sha256"}
    proof._need(proof._digest(unsigned) == report.get("artifact_sha256") == ARTIFACT_SHA256,
                "Compact pilot report artifact checksum differs")
    payload = report.get("physical_policy")
    proof._need(type(payload) is dict and type(payload.get("iterations")) is int and
                payload["iterations"] == EXPECTED_ITERATIONS and
                payload.get("algorithm") == "cfrplus" and
                type(payload.get("averaging_delay")) is int and payload["averaging_delay"] == 0 and
                payload.get("research_adapter") == replay.trainer.ADAPTER and
                payload.get("resource_model") == "fixed-flop-class-cfrplus-logical-work-v1",
                "Compact pilot request or training scope differs")
    raw_rows = report.get("raw_class_policy")
    strategy = payload.get("strategy")
    proof._need(type(raw_rows) is list and len(raw_rows) == EXPECTED_RAW_ROWS and
                type(strategy) is list and len(strategy) == EXPECTED_PHYSICAL_ROWS,
                "Compact pilot policy row counts differ")
    proof._need(type(report.get("quality_target")) is float and
                report["quality_target"] == 0.005 and
                type(report.get("quality_target_met")) is bool and
                report["quality_target_met"] is True,
                "Compact pilot quality pass differs")
    expected_baseline = {
        "raw_sha256": baseline.RAW_SHA256,
        "artifact_sha256": baseline.ARTIFACT_SHA256,
        "nash_conv": baseline.EXPECTED_NASH_CONV,
        "quality_target_met": False,
    }
    proof._need(proof._typed(report.get("baseline_pilot")) == proof._typed(expected_baseline),
                "Historical pilot miss differs")
    return path, raw, report


def verify_saved(path=PUBLICATION):
    path, raw, _ = _read(path)
    checked = replay.verify_saved(path)
    proof._need(type(checked) is dict and
                checked.get("status") == "saved-compact-policy-physically-verified" and
                type(checked.get("training_calls")) is int and checked["training_calls"] == 0 and
                type(checked.get("iterations")) is int and
                checked["iterations"] == EXPECTED_ITERATIONS and
                type(checked.get("class_rows")) is int and
                checked["class_rows"] == EXPECTED_RAW_ROWS and
                type(checked.get("physical_rows")) is int and
                checked["physical_rows"] == EXPECTED_PHYSICAL_ROWS and
                type(checked.get("quality_target_met")) is bool and
                checked["quality_target_met"] is True and
                type(checked.get("nash_conv")) is float and
                checked["nash_conv"] == EXPECTED_NASH_CONV and
                checked.get("artifact_sha256") == ARTIFACT_SHA256,
                "Generic replay differs from immutable compact pilot result")
    _, after, _ = _read(path)
    proof._need(after == raw, "Compact pilot report changed during replay")
    return dict(checked, publication_raw_sha256=RAW_SHA256,
                publication_artifact_sha256=ARTIFACT_SHA256)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=PUBLICATION)
    args = parser.parse_args()
    print(json.dumps(verify_saved(args.path), sort_keys=True))


if __name__ == "__main__":
    main()
