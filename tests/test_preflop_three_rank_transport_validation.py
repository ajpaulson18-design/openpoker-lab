import copy
import hashlib
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import preflop_three_rank_transport_validation as validator


def _artifact(report):
    unsigned = {key: value for key, value in report.items() if key != "artifact_sha256"}
    raw = json.dumps(unsigned, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _make_candidate():
    basis = validator._source_rows()
    report = {
        "schema_version": 1,
        "benchmark_id": "preflop-three-rank-transport-v1",
        "status": "candidate-only",
        "source_basis": copy.deepcopy(validator.SOURCE_PINS),
        "admission": copy.deepcopy(validator.EXPECTED_ADMISSION),
        "rows": [],
        "row_count": 108,
        "total_prior": "1",
    }
    for sb, bb in validator._expected_pairs():
        rank = sb[0]
        overlap = len({sb[1], sb[3]} & {bb[1], bb[3]})
        source_bb = {2: "KdKs", 1: "KcKd", 0: "KcKh"}[overlap]
        source_sb = {"A": "AdAs", "Q": "QdQs", "J": "JdJs"}[rank]
        source = basis[rank][(source_sb, source_bb)]
        suit_map = next(list(permutation) for permutation in itertools.permutations(validator.SUITS)
                        if validator._joint_permutation(source_sb, source_bb, sb, bb,
                                                        list(permutation)))
        prior = {"A": "1/63", "Q": "1/126", "J": "1/252"}[rank]
        report["rows"].append({"sb_hand": sb, "bb_hand": bb, **source,
                               "prior_fraction": prior, "source_sb_hand": source_sb,
                               "source_bb_hand": source_bb,
                               "suit_permutation": suit_map})
    report["artifact_sha256"] = _artifact(report)
    return report


class ThreeRankTransportValidationTests(unittest.TestCase):
    def test_fraction_exponent_is_rejected_before_exact_arithmetic(self):
        with patch.object(validator, "Fraction", side_effect=AssertionError("fraction parse")):
            for token in ("1e1000000000", "1E-1000000000", "+1", "0.5"):
                with self.subTest(token=token), self.assertRaisesRegex(ValueError, "plain integer"):
                    validator._fraction(token)

    def setUp(self):
        with patch.object(validator.jj, "_current_source_check", return_value=None):
            self.report = _make_candidate()

    def _verify(self, report=None):
        with patch.object(validator.jj, "_current_source_check", return_value=None):
            return validator.verify_candidate_report(self.report if report is None else report)

    def test_saved_aa_qq_jj_basis_supports_rank_free_full_transport(self):
        with patch.object(validator.jj, "_current_source_check", return_value=None):
            receipt = validator.verify_candidate_report(self.report)
        self.assertEqual(receipt["status"], "transport-authenticated-candidate-only")
        self.assertEqual(receipt["physical_pair_rows_authenticated"], 108)
        self.assertEqual(receipt["exact_global_prior_mass"], "1")
        self.assertEqual(receipt["overlap_census_by_rank"],
                         {rank: {"0": 6, "1": 24, "2": 6} for rank in "AQJ"})
        self.assertEqual(receipt["rank_calls"], 0)
        self.assertEqual(receipt["board_enumerations"], 0)
        self.assertFalse(receipt["equilibrium_or_policy_claim"])

    def test_invalid_full_request_is_rejected_before_source_lookup(self):
        report = copy.deepcopy(self.report)
        report["admission"]["target_pair_count"] = True
        with patch.object(validator, "_source_rows", side_effect=AssertionError("source read")):
            with self.assertRaises(ValueError):
                validator.verify_candidate_report(report)

    def test_unpinned_jj_first_read_is_rejected_before_saved_verifier(self):
        path = validator.jj.PUBLICATION / "report.json"
        original = validator._bounded_file(path, validator.MAX_BASIS_BYTES)
        altered = json.dumps({**validator._load_json(original), "tampered": True},
                             sort_keys=True).encode("utf-8")
        real_read = validator._bounded_file

        def changed_read(target, limit):
            if Path(target) == path:
                return altered
            return real_read(target, limit)

        with patch.object(validator, "_bounded_file", side_effect=changed_read), \
                patch.object(validator.jj, "verify", side_effect=AssertionError("verifier called")):
            with self.assertRaisesRegex(ValueError, "artifact pin"):
                validator._source_rows()

    def test_basis_source_change_during_authentication_is_rejected(self):
        path = validator.ROOT / validator.SOURCE_PINS["aa"]["path"]
        real_read = validator._bounded_file
        reads = 0

        def changing_read(target, limit):
            nonlocal reads
            raw = real_read(target, limit)
            if Path(target) == path:
                reads += 1
                if reads > 1:
                    return raw + b" "
            return raw

        with patch.object(validator, "_bounded_file", side_effect=changing_read), \
                patch.object(validator.jj, "_current_source_check", return_value=None):
            with self.assertRaisesRegex(ValueError, "changed during authentication"):
                validator._source_rows()

    def test_count_tampering_is_rejected(self):
        report = copy.deepcopy(self.report)
        report["rows"][0]["wins"] += 1
        report["artifact_sha256"] = _artifact(report)
        with self.assertRaisesRegex(ValueError, "counts differ"):
            self._verify(report)

    def test_conditional_prior_tampering_is_rejected(self):
        report = copy.deepcopy(self.report)
        report["rows"][40]["prior_fraction"] = "1/63"
        report["artifact_sha256"] = _artifact(report)
        with self.assertRaisesRegex(ValueError, "conditional pair prior"):
            self._verify(report)

    def test_role_order_and_endpoint_tampering_are_rejected(self):
        report = copy.deepcopy(self.report)
        report["rows"][0]["sb_hand"], report["rows"][0]["bb_hand"] = (
            report["rows"][0]["bb_hand"], report["rows"][0]["sb_hand"])
        report["artifact_sha256"] = _artifact(report)
        with self.assertRaisesRegex(ValueError, "endpoint or row order"):
            self._verify(report)

    def test_boolean_count_alias_is_rejected(self):
        report = copy.deepcopy(self.report)
        report["rows"][0]["wins"] = True
        report["artifact_sha256"] = _artifact(report)
        with self.assertRaisesRegex(ValueError, "bounded exact integer"):
            self._verify(report)

    def test_duplicate_and_incomplete_pair_tables_are_rejected(self):
        duplicate = copy.deepcopy(self.report)
        duplicate["rows"][1] = copy.deepcopy(duplicate["rows"][0])
        duplicate["artifact_sha256"] = _artifact(duplicate)
        with self.assertRaisesRegex(ValueError, "endpoint or row order"):
            self._verify(duplicate)
        incomplete = copy.deepcopy(self.report)
        incomplete["rows"].pop()
        incomplete["row_count"] = 107
        incomplete["artifact_sha256"] = _artifact(incomplete)
        with self.assertRaisesRegex(ValueError, "fixed request/admission"):
            self._verify(incomplete)

    def test_nonbijective_or_independently_wrong_suit_mapping_is_rejected(self):
        report = copy.deepcopy(self.report)
        report["rows"][25]["suit_permutation"] = ["c", "c", "h", "s"]
        report["artifact_sha256"] = _artifact(report)
        with self.assertRaisesRegex(ValueError, "jointly map"):
            self._verify(report)
        report = copy.deepcopy(self.report)
        report["rows"][25]["suit_permutation"] = ["d", "c", "h", "s"]
        report["artifact_sha256"] = _artifact(report)
        with self.assertRaisesRegex(ValueError, "jointly map"):
            self._verify(report)

    def test_canonical_digest_and_bounded_path_json_are_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidate.json"
            path.write_text(json.dumps(self.report), encoding="utf-8")
            with patch.object(validator.jj, "_current_source_check", return_value=None):
                self.assertEqual(validator.verify_candidate_report(path)["physical_pair_rows_authenticated"], 108)
            changed = copy.deepcopy(self.report)
            changed["total_prior"] = "2"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fixed request/admission"):
                validator.verify_candidate_report(path)

    def test_saved_candidate_changed_during_source_authentication_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidate.json"
            raw = json.dumps(self.report, sort_keys=True, separators=(",", ":")).encode()
            path.write_bytes(raw)
            original_source_check = validator._source_rows

            def authenticate_then_mutate():
                with patch.object(validator.jj, "_current_source_check", return_value=None):
                    result = original_source_check()
                path.write_bytes(raw + b" ")
                return result

            with patch.object(validator, "_source_rows", side_effect=authenticate_then_mutate):
                with self.assertRaisesRegex(ValueError, "file changed during verification"):
                    validator.verify_candidate_report(path)

    def test_duplicate_json_keys_and_exponent_overflow_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidate.json"
            path.write_text('{"x":1,"x":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                validator.verify_candidate_report(path)
            path.write_text('{"x":1e999}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "nonfinite JSON number"):
                validator.verify_candidate_report(path)


if __name__ == "__main__":
    unittest.main()
