"""Authenticate a retained native benchmark sample and certify it without training."""
import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path, *, limit=32 * 1024 * 1024):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Evidence must be a bounded regular file")
    return path.read_bytes()


def verify(directory, report_sha256, output):
    """Check externally pinned bytes before importing the independent oracle."""
    if (type(report_sha256) is not str or len(report_sha256) != 64 or
            any(c not in "0123456789abcdef" for c in report_sha256)):
        raise ValueError("An external lowercase report SHA256 is required")
    directory = Path(directory).resolve(strict=True)
    raw_report = _read(directory / "report.json")
    if hashlib.sha256(raw_report).hexdigest() != report_sha256:
        raise ValueError("Report hash disagrees with external pin")
    report = json.loads(raw_report)
    if (report.get("benchmark_id") != "native-four-street-v1" or
            report.get("outcome") != "complete" or report.get("failures") or
            report.get("policy_compatibility") != "pass"):
        raise ValueError("Benchmark did not complete its declared controls")
    before, after = report["source_before"], report["source_after"]
    if before != after or before["status_porcelain"]:
        raise ValueError("Benchmark source was not clean and stable")
    for name, digest in before["source_sha256"].items():
        path = (ROOT / name).resolve(strict=True)
        if ROOT not in path.parents or hashlib.sha256(
                _read(path).replace(b"\r\n", b"\n")).hexdigest() != digest:
            raise ValueError("Current source disagrees with benchmark source: " + name)
    manifest = json.loads(_read(ROOT / "benchmarks/native-four-street-v1.json"))
    sample_id = "repeat-1-native"
    matches = [row for row in report["runs"] if row.get("sample_id") == sample_id]
    if len(matches) != 1:
        raise ValueError("First native sample is missing or duplicated")
    sample = matches[0]
    if sample["raw_path"] != sample_id + "-raw-envelope.json":
        raise ValueError("Unexpected native sample path")
    raw = _read(directory / sample["raw_path"])
    if len(raw) != sample["raw_bytes"] or hashlib.sha256(raw).hexdigest() != sample["raw_sha256"]:
        raise ValueError("Native sample bytes disagree with benchmark")
    payload = json.loads(raw)["payload"]
    if (payload.get("execution_backend") != "public-batched-cpp" or
            payload.get("algorithm") != "cfrplus" or payload.get("iterations") != 1000):
        raise ValueError("Unexpected native sample selectors")
    # Authentication above must finish before loading mathematical code.
    from scripts.four_street_certificate import evaluate_exact
    certificate = evaluate_exact(manifest["case"], payload)
    receipt = {"schema_version": 1, "verifier": "native-four-street-saved-exact-v1",
               "report_sha256": report_sha256, "sample_id": sample_id,
               "raw_sha256": sample["raw_sha256"],
               "source_commit": before["head"], "production_calls": 0,
               "native_calls": 0, "training_calls": 0,
               "certificate": certificate}
    data = json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    with Path(output).open("xb") as stream:
        stream.write(data)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    receipt = verify(args.directory, args.report_sha256, args.output)
    certificate = receipt["certificate"]
    print(json.dumps({"threshold_met": certificate["threshold_met"],
                      "nash_conv": certificate["metrics"]["nash_conv"],
                      "sample": receipt["sample_id"]}))
    return 0 if certificate["threshold_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
