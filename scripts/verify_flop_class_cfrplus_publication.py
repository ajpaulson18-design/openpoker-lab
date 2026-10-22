"""Authenticate and independently replay the immutable fixed-flop class CFR+ pilot."""
import argparse
import hashlib
import json
from pathlib import Path

from scripts import verify_flop_class_cfrplus as replay
from scripts import flop_public_classes as proof


PUBLICATION = Path(__file__).resolve().parents[1] / "benchmarks/results/flop-class-cfrplus-pilot-v1.json"
RAW_SHA256 = "1992b8041a17478f3708e8fa6ac38aa5c9ddb7217cba1611c24008b4910d77cc"
ARTIFACT_SHA256 = "36ddb38bcd9cadd9892fe99d0ba40ab2b1b0d6ae4d31e66f3fc5ec2b08c51209"
MAX_REPORT_BYTES = 24 * 1024 * 1024
EXPECTED_ITERATIONS = 140
EXPECTED_RAW_ROWS = 466
EXPECTED_PHYSICAL_ROWS = 16_912
EXPECTED_NASH_CONV = 0.012537880082162792


def _validate_bytes(raw):
    proof._need(type(raw) is bytes and len(raw) <= MAX_REPORT_BYTES,
                "Pilot report exceeds size bound")
    proof._need(hashlib.sha256(raw).hexdigest() == RAW_SHA256,
                "Immutable pilot report bytes changed")
    report = json.loads(raw, object_pairs_hook=replay._pairs,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    proof._need(type(report) is dict and report.get("schema_version") ==
                "fixed-flop-class-cfrplus-v1" and report.get("status") ==
                "trained-policy-physically-verified",
                "Immutable pilot report scope or status differs")
    unsigned = {key: value for key, value in report.items() if key != "artifact_sha256"}
    artifact_sha256 = proof._digest(unsigned)
    proof._need(report.get("artifact_sha256") == artifact_sha256 == ARTIFACT_SHA256,
                "Immutable pilot report artifact checksum differs")
    payload = report.get("physical_policy")
    proof._need(type(payload) is dict and type(payload.get("iterations")) is int and
                payload["iterations"] == EXPECTED_ITERATIONS and
                payload.get("algorithm") == "cfrplus" and
                type(payload.get("averaging_delay")) is int and payload["averaging_delay"] == 0 and
                payload.get("research_adapter") == "fixed-flop-public-classes-cfrplus-v1",
                "Immutable pilot request or training scope differs")
    raw_rows = report.get("raw_class_policy")
    strategy = payload.get("strategy")
    proof._need(type(raw_rows) is list and len(raw_rows) == EXPECTED_RAW_ROWS and
                type(strategy) is list and len(strategy) == EXPECTED_PHYSICAL_ROWS,
                "Immutable pilot policy row counts differ")
    proof._need(type(report.get("quality_target")) is float and
                report["quality_target"] == 0.005 and
                type(report.get("quality_target_met")) is bool and
                report["quality_target_met"] is False,
                "Immutable pilot quality miss differs")
    return report


def _read(path):
    path = Path(path)
    proof._need(not path.is_symlink() and path.is_file() and
                path.stat().st_size <= MAX_REPORT_BYTES,
                "Invalid bounded immutable pilot report")
    raw = path.read_bytes()
    _validate_bytes(raw)
    return path, raw


def verify_saved(path=PUBLICATION):
    path, raw = _read(path)
    checked = replay.verify_saved(path)
    proof._need(type(checked) is dict and
                checked.get("status") == "saved-trained-policy-physically-verified" and
                type(checked.get("iterations")) is int and
                checked["iterations"] == EXPECTED_ITERATIONS and
                type(checked.get("class_rows")) is int and
                checked["class_rows"] == EXPECTED_RAW_ROWS and
                type(checked.get("physical_rows")) is int and
                checked["physical_rows"] == EXPECTED_PHYSICAL_ROWS and
                type(checked.get("quality_target_met")) is bool and
                checked["quality_target_met"] is False and
                type(checked.get("nash_conv")) is float and
                checked["nash_conv"] == EXPECTED_NASH_CONV and
                checked.get("artifact_sha256") == ARTIFACT_SHA256 and
                type(checked.get("training_calls")) is int and checked["training_calls"] == 0,
                "Generic replay differs from immutable pilot result")
    _, after = _read(path)
    proof._need(after == raw, "Immutable pilot report changed during replay")
    return dict(checked, publication_raw_sha256=RAW_SHA256,
                publication_artifact_sha256=ARTIFACT_SHA256)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=PUBLICATION)
    args = parser.parse_args()
    print(json.dumps(verify_saved(args.path), sort_keys=True))


if __name__ == "__main__":
    main()
