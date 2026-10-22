"""Authenticate and verify the immutable fixed-flop call-cost measurement."""
import hashlib
import json
from pathlib import Path

from scripts import benchmark_flop_class_cost as runner


PUBLICATION = (Path(__file__).resolve().parents[1] /
               "benchmarks/results/flop-class-call-cost-v1")
EXPECTED_REVISION = "20a1f1dcf518895dd54ed5a9eb7ddc52fe1d89d4"
INDEX_RAW_SHA256 = "15fa0dd9c90ecacee4337dca2649cdf771f0f46569bf24d1a2d6056e10ef3a7f"
INDEX_SHA256 = "80c95f4ec6f2af7d8797a7eb6de335c625332a75d0cc77e6993feac1c615bc49"
MAX_INDEX_BYTES = 4 * 1024 * 1024


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate measurement index field")
        result[key] = value
    return result


def _read(directory):
    directory = Path(directory)
    index = directory / "index.json"
    if (directory.is_symlink() or index.is_symlink() or not index.is_file() or
            index.stat().st_size > MAX_INDEX_BYTES):
        raise ValueError("Invalid bounded measurement index")
    with index.open("rb") as stream:
        raw = stream.read(MAX_INDEX_BYTES + 1)
    if len(raw) > MAX_INDEX_BYTES:
        raise ValueError("Measurement index exceeds size bound")
    if hashlib.sha256(raw).hexdigest() != INDEX_RAW_SHA256:
        raise ValueError("Immutable measurement index bytes differ")
    report = json.loads(raw, object_pairs_hook=_pairs,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    if type(report) is not dict:
        raise ValueError("Measurement index must be an object")
    unsigned = {key: value for key, value in report.items() if key != "index_sha256"}
    canonical_sha = hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).hexdigest()
    if (report.get("index_sha256") != INDEX_SHA256 or
            canonical_sha != INDEX_SHA256):
        raise ValueError("Immutable measurement index checksum differs")
    if (report.get("status") != "complete" or
            report.get("source_before", {}).get("revision") != EXPECTED_REVISION or
            report.get("source_after", {}).get("revision") != EXPECTED_REVISION):
        raise ValueError("Measurement source revision or status differs")
    rows = report.get("samples")
    if (type(rows) is not list or len(rows) != 8 or
            any(type(row) is not dict or row.get("status") != "complete" for row in rows)):
        raise ValueError("Measurement must contain eight completed calls")
    return raw, report


def verify(directory=PUBLICATION):
    directory = Path(directory)
    raw, report = _read(directory)
    checked = runner.verify_saved(directory)
    after, _ = _read(directory)
    if after != raw:
        raise ValueError("Immutable measurement index changed during saved verification")
    return {"status": "published-measurement-verified",
            "measurement_status": report["status"],
            "call_count": len(report["samples"]),
            "index_raw_sha256": INDEX_RAW_SHA256,
            "index_sha256": INDEX_SHA256,
            "saved_verification": checked}


def main(argv=None):
    print(json.dumps(verify(PUBLICATION), sort_keys=True))


if __name__ == "__main__":
    main()
