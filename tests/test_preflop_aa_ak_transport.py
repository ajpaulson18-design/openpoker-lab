"""Synthetic admission and serialization checks; never build the real candidate."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import preflop_aa_ak_transport as candidate


class AaAkTransportTests(unittest.TestCase):
    def test_fresh_literal_request_and_exact_physical_admission(self):
        first = candidate.expected_request()
        first["target_census"]["pair_cap"] = 999
        self.assertEqual(candidate.expected_request()["target_census"]["pair_cap"], 128)
        hands, pairs = candidate.admit()
        self.assertEqual((len(hands[0]), len(hands[1]), len(hands[0]) * len(hands[1]), len(pairs)),
                         (22, 6, 132, 84))
        self.assertEqual(sum((prior for _, _, prior in pairs), Fraction()), 1)
        type_counts = {kind: sum(candidate._hand_type(hands[0][i]) == kind
                                 for i, _, _ in pairs)
                       for kind in ("AA", "AKs", "AKo")}
        self.assertEqual(type_counts, {"AA": 36, "AKs": 12, "AKo": 36})
        self.assertEqual(candidate.expected_request()["exact_prior"]["type_masses"],
                         {"AA": "3/7", "AKs": "1/7", "AKo": "3/7"})
        self.assertEqual(candidate.expected_request()["hand_counts"],
                         {"AA": 6, "AKs": 4, "AKo": 12, "KK": 6})
        self.assertEqual(candidate.expected_request()["suit_class_census"],
                         {"AA": {"0": 6, "1": 24, "2": 6},
                          "AKs": {"0": 12}, "AKo": {"0": 12, "1": 24}})

    def test_bad_request_and_changed_caps_reject_before_source_lookup(self):
        bad = candidate.expected_request()
        bad["schema_version"] = True
        with patch.object(candidate, "_source_rows", side_effect=AssertionError("source read")):
            with self.assertRaises(ValueError):
                candidate.build_candidate(bad)
        with patch.object(candidate.covered, "MAX_PAIRS", 83), \
                patch.object(candidate, "_source_rows", side_effect=AssertionError("source read")):
            with self.assertRaises(ValueError):
                candidate.build_candidate()

    def test_synthetic_serialization_retains_all_physical_rows_and_provenance(self):
        hands, pairs = candidate.admit()
        coverage = []
        for i, j, _ in pairs:
            coverage.append(("a" * 64, hands[0][i], hands[1][j], tuple(candidate.SUITS)))
        table = SimpleNamespace(
            hands=hands,
            pairs=pairs,
            counts=tuple((1_000_000, 100_000, candidate.BOARDS_PER_PAIR - 1_100_000)
                         for _ in pairs),
            coverage=tuple(coverage),
            validate=lambda: None,
        )
        report = candidate._report_from_table(table, candidate.source_basis())
        self.assertEqual(report["status"], "candidate-only")
        self.assertEqual(report["row_count"], 84)
        self.assertEqual(report["type_pair_counts"], {"AA": 36, "AKs": 12, "AKo": 36})
        self.assertEqual({row["prior_fraction"] for row in report["rows"]}, {"1/84"})
        self.assertTrue(all(row["source_identity_sha256"] in {
                            candidate.AA_REPORT_ARTIFACT_SHA256,
                            candidate.AK_REPORT_ARTIFACT_SHA256} and
                            row["suit_permutation"] == list(candidate.SUITS)
                            for row in report["rows"]))
        for row in report["rows"]:
            expected_source = (candidate.AA_REPORT_ARTIFACT_SHA256
                               if row["sb_hand"][0] == row["sb_hand"][2]
                               else candidate.AK_REPORT_ARTIFACT_SHA256)
            self.assertEqual(row["source_identity_sha256"], expected_source)
        self.assertEqual(report["artifact_sha256"], candidate._artifact(report))
        self.assertLessEqual(len(candidate._canonical(report)), candidate.MAX_CANDIDATE_BYTES)

    def test_source_rows_require_exact_saved_pair_keys_and_integer_counts(self):
        rows = [
            {"sb_hand": "AcKc", "bb_hand": "KdKh", "wins": 10,
             "ties": 2, "losses": candidate.BOARDS_PER_PAIR - 12,
             "boards": candidate.BOARDS_PER_PAIR},
            {"sb_hand": "AdKc", "bb_hand": "KdKh", "wins": 10,
             "ties": 2, "losses": candidate.BOARDS_PER_PAIR - 12,
             "boards": candidate.BOARDS_PER_PAIR},
            {"sb_hand": "AdKc", "bb_hand": "KhKs", "wins": 10,
             "ties": 2, "losses": candidate.BOARDS_PER_PAIR - 12,
             "boards": candidate.BOARDS_PER_PAIR},
        ]
        result = candidate._exact_rows(rows, {
            ("AcKc", "KdKh"), ("AdKc", "KdKh"), ("AdKc", "KhKs")})
        self.assertEqual(len(result), 3)
        malformed = [dict(row) for row in rows]
        malformed[0]["wins"] = True
        with self.assertRaises(ValueError):
            candidate._exact_rows(malformed, {
                ("AcKc", "KdKh"), ("AdKc", "KdKh"), ("AdKc", "KhKs")})

    def test_nonfinite_float_json_is_rejected_during_bounded_parse(self):
        for raw in (b'{"x":1e999}', b'{"x":-1e999}', b'{"x":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                candidate._parse_json(raw)

    def test_synthetic_saved_reports_are_pinned_before_verifier_rows_are_used(self):
        def row(sb, bb, wins):
            return {"sb_hand": sb, "bb_hand": bb, "wins": wins, "ties": 2,
                    "losses": candidate.BOARDS_PER_PAIR - wins - 2,
                    "boards": candidate.BOARDS_PER_PAIR}

        aa_rows = [row("AdAs", bb, 100) for bb in ("KdKs", "KcKd", "KcKh")]
        ak_rows = [row("AcKc", "KdKh", 100), row("AdKc", "KdKh", 101),
                   row("AdKc", "KhKs", 102)]

        def saved_report(rows):
            unsigned = {"independent_physical_count_rows": rows}
            digest = hashlib.sha256(candidate._canonical(unsigned)).hexdigest()
            report = {**unsigned, "artifact_sha256": digest}
            raw = json.dumps(report, sort_keys=True, indent=2).encode("utf-8")
            return raw, digest

        aa_raw, aa_digest = saved_report(aa_rows)
        ak_raw, ak_digest = saved_report(ak_rows)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            aa_path = root / "aa.json"
            pub = root / "ak"
            pub.mkdir()
            ak_path, index_path = pub / "report.json", pub / "index.json"
            aa_path.write_bytes(aa_raw)
            ak_path.write_bytes(ak_raw)
            index_raw = b"synthetic bounded index fixture"
            index_path.write_bytes(index_raw)
            aa_verify, ak_verify = Mock(return_value={"status": "passed"}), Mock(return_value={
                "status": "authenticated-saved-counts-only",
                "report_artifact_sha256": ak_digest})
            fake_ak = SimpleNamespace(PUBLICATION=pub, verify=ak_verify)
            with (patch.object(candidate, "AA_REPORT", aa_path),
                  patch.object(candidate, "AA_REPORT_RAW_SHA256", hashlib.sha256(aa_raw).hexdigest()),
                  patch.object(candidate, "AA_REPORT_ARTIFACT_SHA256", aa_digest),
                  patch.object(candidate, "AK_REPORT_RAW_SHA256", hashlib.sha256(ak_raw).hexdigest()),
                  patch.object(candidate, "AK_REPORT_ARTIFACT_SHA256", ak_digest),
                  patch.object(candidate, "AK_INDEX_RAW_SHA256", hashlib.sha256(index_raw).hexdigest()),
                  patch.object(candidate.five, "verify_saved", aa_verify),
                  patch.object(candidate.importlib, "import_module", return_value=fake_ak)):
                aa, ak, _pins = candidate._source_rows()
            aa_verify.assert_called_once_with(aa_path)
            ak_verify.assert_called_once_with()
            self.assertEqual(set(aa), {(item["sb_hand"], item["bb_hand"]) for item in aa_rows})
            self.assertEqual(set(ak), {(item["sb_hand"], item["bb_hand"]) for item in ak_rows})


if __name__ == "__main__":
    unittest.main()
