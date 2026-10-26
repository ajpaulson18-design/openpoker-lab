"""Frozen-corpus parity for the private exact-operator seam."""
import hashlib
import json
from pathlib import Path
import unittest

from scripts import four_street_certificate as certificate


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmarks" / "results" / "four-street-integration-v1"
PINS = {
    "publication.json": "2d1b572a958629849477aaa09944a48152eb128b53777f16b89149e7fd5a46b7",
    "attempt/report.json": "c2f905ab698b086d96abbaae46b120c6202e95e65990a745a6d1cc703ced9a8e",
    "attempt/raw-envelope.json": "37b3c61cbca982dd44078da22b9c8e1c3acd3ef5171c01272def8cdf4580596e",
    "attempt/exact-certificate.json": "f59a61850f600192f72ab4ac5003f46527b0cf8e03ba66f7ba5a2c9cb40514e3",
}


def _pinned_bytes(relative_path):
    data = (CORPUS / relative_path).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != PINS[relative_path]:
        raise AssertionError(f"frozen artifact pin mismatch: {relative_path}")
    return data


class FourStreetCertificateOperatorSeamTests(unittest.TestCase):
    def test_default_v2_evaluator_matches_complete_published_certificate(self):
        # Authenticate the bytes before parsing any saved result as an oracle.
        publication_bytes = _pinned_bytes("publication.json")
        report_bytes = _pinned_bytes("attempt/report.json")
        raw_bytes = _pinned_bytes("attempt/raw-envelope.json")
        exact_bytes = _pinned_bytes("attempt/exact-certificate.json")

        publication = json.loads(publication_bytes)
        report = json.loads(report_bytes)
        raw_record = json.loads(raw_bytes)
        exact_record = json.loads(exact_bytes)
        published = {item["path"]: item for item in publication["artifacts"]}

        self.assertEqual(publication["report_sha256"], PINS["attempt/report.json"])
        self.assertEqual(published["attempt/report.json"]["sha256"],
                         PINS["attempt/report.json"])
        self.assertEqual(published["attempt/raw-envelope.json"]["sha256"],
                         PINS["attempt/raw-envelope.json"])
        self.assertEqual(published["attempt/exact-certificate.json"]["sha256"],
                         PINS["attempt/exact-certificate.json"])
        self.assertEqual(report["raw_receipt"]["sha256"], PINS["attempt/raw-envelope.json"])
        self.assertEqual(exact_record["raw_sha256"], PINS["attempt/raw-envelope.json"])
        self.assertEqual(report["attempt_id"], publication["attempt_id"])
        self.assertEqual(exact_record["attempt_id"], publication["attempt_id"])

        manifest = json.loads((ROOT / "benchmarks" /
                               "four-street-integration-v1.json").read_bytes())
        actual = certificate.evaluate_exact(manifest["case"], raw_record["payload"])
        self.assertEqual(actual, exact_record["certificate"])

    def test_public_entry_points_reject_operator_and_callback_injection(self):
        case = {"id": "operator-argument-guard"}
        payload = {"strategy": []}
        for name in ("operator", "callback", "terminal_operator", "normalizer"):
            with self.subTest(api="forecast_exact", argument=name):
                with self.assertRaises(TypeError):
                    certificate.forecast_exact(case, **{name: lambda *_: None})
            with self.subTest(api="evaluate_exact", argument=name):
                with self.assertRaises(TypeError):
                    certificate.evaluate_exact(case, payload, **{name: lambda *_: None})


if __name__ == "__main__":
    unittest.main()
