"""Synthetic integration controls for the independent AA/AK transport oracle."""
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import preflop_aa_ak_transport as candidate
from scripts import preflop_aa_ak_transport_validation as oracle
from scripts import verify_preflop_ak_kk_basis_publication as ak_publication


BOARDS = 1_712_304
SOURCE_ROWS = (
    ("aa", "AdAs", "KdKs"), ("aa", "AdAs", "KcKd"), ("aa", "AdAs", "KcKh"),
    ("ak", "AcKc", "KdKh"), ("ak", "AdKc", "KdKh"), ("ak", "AdKc", "KhKs"),
)


def _synthetic_source_rows():
    grouped = {"aa": {}, "ak": {}}
    oracle_rows = {}
    for ordinal, (kind, sb, bb) in enumerate(SOURCE_ROWS):
        wins = 600_000 + ordinal * 31_007
        ties = 101 + ordinal * 17
        row = {"sb_hand": sb, "bb_hand": bb, "wins": wins, "ties": ties,
               "losses": BOARDS - wins - ties, "boards": BOARDS}
        grouped[kind][(sb, bb)] = row
        pin = (candidate.AA_REPORT_ARTIFACT_SHA256 if kind == "aa"
               else candidate.AK_REPORT_ARTIFACT_SHA256)
        oracle_rows[(sb, bb)] = (wins, ties, row["losses"], BOARDS, pin)
    pins = {"aa": candidate.AA_REPORT_ARTIFACT_SHA256,
            "ak": candidate.AK_REPORT_ARTIFACT_SHA256}
    return grouped["aa"], grouped["ak"], pins, oracle_rows


def _candidate_with_synthetic_counts():
    aa, ak, pins, independent = _synthetic_source_rows()
    with patch.object(candidate, "_source_rows", return_value=(aa, ak, pins)):
        report = candidate.build_candidate()
    return report, independent


def _reseal(report):
    report["artifact_sha256"] = candidate._artifact(report)
    return report


class IndependentAaAkTransportTests(unittest.TestCase):
    def test_synthetic_producer_candidate_matches_literal_independent_oracle(self):
        report, independent_rows = _candidate_with_synthetic_counts()
        forbidden = AssertionError("oracle reused a producer or production-pool helper")
        with (patch.object(oracle, "_source_rows", return_value=independent_rows),
              patch.object(candidate, "build_candidate", side_effect=forbidden),
              patch.object(candidate, "_source_rows", side_effect=forbidden),
              patch.object(candidate, "_as_table", side_effect=forbidden),
              patch.object(candidate, "_report_from_table", side_effect=forbidden),
              patch.object(candidate.covered, "_ranges", side_effect=forbidden),
              patch.object(candidate.covered, "pool_preflop_equities_by_suit", side_effect=forbidden)):
            result = oracle.verify(report)

        self.assertEqual(result["status"], "transport-authenticated-candidate-only")
        self.assertEqual(result["physical_pair_rows_authenticated"], 84)
        self.assertEqual(result["type_pair_counts"], {"AA": 36, "AKs": 12, "AKo": 36})
        self.assertEqual(result["type_prior_masses"], {"AA": "3/7", "AKs": "1/7", "AKo": "3/7"})
        self.assertEqual(result["exact_global_prior_mass"], "1")
        self.assertEqual(result["rank_calls"], 0)
        self.assertEqual(result["board_enumerations"], 0)
        self.assertEqual(result["source_orbit_members"], [
            {"sb_hand": "AcKc", "bb_hand": "KdKh", "members": 12},
            {"sb_hand": "AdAs", "bb_hand": "KcKd", "members": 24},
            {"sb_hand": "AdAs", "bb_hand": "KcKh", "members": 6},
            {"sb_hand": "AdAs", "bb_hand": "KdKs", "members": 6},
            {"sb_hand": "AdKc", "bb_hand": "KdKh", "members": 24},
            {"sb_hand": "AdKc", "bb_hand": "KhKs", "members": 12},
        ])
        self.assertTrue(all(row["prior_fraction"] == "1/84" for row in report["rows"]))

    def test_same_board_counts_swapped_between_ako_orbits_fail_source_link(self):
        report, independent_rows = _candidate_with_synthetic_counts()
        first = next(row for row in report["rows"]
                     if (row["source_sb_hand"], row["source_bb_hand"]) == ("AdKc", "KdKh"))
        second = next(row for row in report["rows"]
                      if (row["source_sb_hand"], row["source_bb_hand"]) == ("AdKc", "KhKs"))
        fields = ("wins", "ties", "losses")
        saved = {field: first[field] for field in fields}
        for field in fields:
            first[field] = second[field]
            second[field] = saved[field]
        _reseal(report)
        with patch.object(oracle, "_source_rows", return_value=independent_rows):
            with self.assertRaisesRegex(ValueError, "source counts or source identity"):
                oracle.verify(report)

    def test_bad_admission_pair_support_prior_and_source_identity_reject_before_source_io(self):
        original, _rows = _candidate_with_synthetic_counts()
        mutations = []

        bad_admission = deepcopy(original)
        bad_admission["admission"]["target_census"]["compatible_pairs"] = True
        mutations.append(("bool admission alias", bad_admission))

        duplicate = deepcopy(original)
        duplicate["rows"][1]["sb_hand"] = duplicate["rows"][0]["sb_hand"]
        duplicate["rows"][1]["bb_hand"] = duplicate["rows"][0]["bb_hand"]
        mutations.append(("duplicate physical pair", duplicate))

        extreme_prior = deepcopy(original)
        extreme_prior["rows"][0]["prior_fraction"] = "1e1000000000"
        mutations.append(("unsupported prior spelling", extreme_prior))

        wrong_source = deepcopy(original)
        wrong_source["rows"][0]["source_identity_sha256"] = "0" * 64
        mutations.append(("wrong source identity", wrong_source))

        bad_map = deepcopy(original)
        bad_map["rows"][0]["suit_permutation"] = ["c", "c", "h", "s"]
        mutations.append(("invalid joint suit map", bad_map))

        for label, report in mutations:
            with self.subTest(label=label):
                _reseal(report)
                with patch.object(oracle, "_source_rows",
                                  side_effect=AssertionError("source I/O before preflight")):
                    with self.assertRaises(ValueError):
                        oracle.verify(report)

    def test_wrong_but_valid_global_suit_map_rejects_before_source_io(self):
        report, _rows = _candidate_with_synthetic_counts()
        row = report["rows"][0]
        original = row["suit_permutation"]
        # Keep a real bijection while breaking the joint mapping of both hands.
        row["suit_permutation"] = [original[1], original[0], original[2], original[3]]
        _reseal(report)
        with patch.object(oracle, "_source_rows",
                          side_effect=AssertionError("source I/O before map validation")):
            with self.assertRaisesRegex(ValueError, "suit map does not preserve"):
                oracle.verify(report)

    def test_corrupt_saved_source_bytes_are_rejected_before_json_or_saved_auth(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative in (candidate.AA_REPORT_RELATIVE, candidate.AK_REPORT_RELATIVE,
                             candidate.AK_REPORT_RELATIVE.rsplit("/", 1)[0] + "/index.json"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"corrupted raw source")
            with (patch.object(candidate, "ROOT", root),
                  patch.object(candidate, "AA_REPORT", root / candidate.AA_REPORT_RELATIVE),
                  patch.object(ak_publication, "PUBLICATION",
                               root / candidate.AK_REPORT_RELATIVE.rsplit("/", 1)[0]),
                  patch.object(candidate, "_parse_json",
                               side_effect=AssertionError("parsed source before raw pin")),
                  patch.object(candidate.five, "verify_saved",
                               side_effect=AssertionError("saved auth before raw pin"))):
                with self.assertRaisesRegex(ValueError, "Saved raw count report pin differs"):
                    candidate._source_rows()

    def test_source_file_change_during_authentication_is_detected_on_reread(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for relative in (candidate.AA_REPORT_RELATIVE, candidate.AK_REPORT_RELATIVE,
                             candidate.AK_REPORT_RELATIVE.rsplit("/", 1)[0] + "/index.json"):
                source = candidate.ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            aa_path = root / candidate.AA_REPORT_RELATIVE
            original_read = candidate._bounded_read
            aa_reads = 0

            def change_on_reread(path, limit):
                nonlocal aa_reads
                raw = original_read(path, limit)
                if Path(path) == aa_path:
                    aa_reads += 1
                    if aa_reads == 2:
                        return raw + b" "
                return raw

            with (patch.object(candidate, "ROOT", root),
                  patch.object(candidate, "AA_REPORT", aa_path),
                  patch.object(ak_publication, "PUBLICATION",
                               root / candidate.AK_REPORT_RELATIVE.rsplit("/", 1)[0]),
                  patch.object(candidate, "_bounded_read", side_effect=change_on_reread),
                  patch.object(candidate.five, "verify_saved", return_value={"status": "passed"}),
                  patch.object(ak_publication, "verify", return_value={
                      "status": "authenticated-saved-counts-only",
                      "report_artifact_sha256": candidate.AK_REPORT_ARTIFACT_SHA256})):
                with self.assertRaisesRegex(ValueError, "changed during authentication"):
                    candidate._source_rows()
            self.assertEqual(aa_reads, 2)


if __name__ == "__main__":
    unittest.main()
