from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import verify_flop_second_board_reference_publication as saved


class SecondBoardPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index_raw, cls.gzip_raw, cls.report, cls.payload = saved._read(saved.PUBLICATION)
        _, cls.spec = saved.evidence._protocol()

    def current(self):
        return {**deepcopy(self.report["source_before"]), "revision": "b" * 40}

    def repaired_index_rejects(self, mutate, message):
        report = deepcopy(self.report)
        mutate(report)
        unsigned = {key: value for key, value in report.items() if key != "index_sha256"}
        report["index_sha256"] = saved.proof._digest(unsigned)
        with mock.patch.object(saved, "INDEX_SHA256", report["index_sha256"]):
            with self.assertRaisesRegex(ValueError, message):
                saved._validate(report, self.payload, self.current(), self.spec)

    def test_saved_authentication_performs_no_physical_work(self):
        forbidden = AssertionError("authentication must use only saved data")
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(saved.evidence, "_snapshot", return_value=self.current()))
            for module, name in ((saved.evidence.reference, "prepare_reference"),
                                 (saved.evidence.reference.physical, "prepare_oracle"),
                                 (saved.evidence.reference.physical, "independent_rank"),
                                 (saved.evidence.reference, "_rank_recheck"),
                                 (saved.evidence.reference.candidate, "build_candidate"),
                                 (saved.evidence.previous, "fingerprint")):
                stack.enter_context(mock.patch.object(module, name, side_effect=forbidden))
            result = saved.verify()
        self.assertEqual(result["status"], "saved-second-board-reference-authenticated")
        self.assertEqual(result["recorded_physical_builds"], 1)
        self.assertEqual(result["recorded_preparation_rank_calls"], 4134)
        for key in ("physical_builds", "ranking_calls", "training_calls", "best_response_calls"):
            self.assertEqual(result[key], 0)
        self.assertIs(result["full_equivalence_proved"], False)

    def test_raw_archive_tamper_rejects_before_decompression(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            (target / "index.json").write_bytes(self.index_raw)
            changed = bytes([self.gzip_raw[0] ^ 1]) + self.gzip_raw[1:]
            (target / "reference.json.gz").write_bytes(changed)
            with mock.patch.object(saved.gzip, "GzipFile", side_effect=AssertionError("early decompression")):
                with self.assertRaisesRegex(ValueError, "raw hash"):
                    saved._read(target)

    def test_raw_index_tamper_rejects(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            (target / "index.json").write_bytes(b" " + self.index_raw[1:])
            with self.assertRaisesRegex(ValueError, "raw hash"):
                saved._read(target)

    def test_json_rejects_duplicate_and_nonfinite_fields(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    saved._json(raw)

    def test_repaired_index_still_rejects_source_checkpoint_and_lf_drift(self):
        self.repaired_index_rejects(
            lambda report: report["source_before"].update(revision="0" * 40), "checkpoint")
        path = next(iter(self.report["source_before"]["source_lf_sha256"]))
        self.repaired_index_rejects(
            lambda report: report["source_before"]["source_lf_sha256"].update({path: "0" * 64}),
            "identities")

    def test_repaired_index_still_rejects_extra_attempts_and_bool_aliases(self):
        self.repaired_index_rejects(
            lambda report: report["progress"].update(physical_builds_attempted=2), "counts")
        self.repaired_index_rejects(
            lambda report: report["progress"].update(candidate_builds_completed=True), "counts")

    def test_repaired_index_still_requires_all_41_exact_zero_authorities(self):
        key = next(iter(self.report["authority_calls"]))
        self.repaired_index_rejects(lambda report: report["authority_calls"].pop(key), "authority")
        self.repaired_index_rejects(lambda report: report["authority_calls"].update({key: False}), "authority")
        self.repaired_index_rejects(lambda report: report["authority_calls"].update({key: 1}), "authority")

    def test_repaired_index_requires_utc_and_prerequisite_zero_current_work(self):
        self.repaired_index_rejects(
            lambda report: report.update(finished_at_utc=report["created_at_utc"].replace("+00:00", "")),
            "UTC")
        self.repaired_index_rejects(
            lambda report: report["prerequisite"].update(fingerprint_calls=6), "prerequisite")

    def test_saved_flat_view_requires_full_flop_root_and_no_cycles(self):
        view = deepcopy(self.payload["physical"]["tree_view"])
        view[0]["street"] = "river"
        with self.assertRaisesRegex(ValueError, "flop-start"):
            saved._flat_structure(view)
        view[0] = deepcopy(self.payload["physical"]["tree_view"][0])
        view[0]["children"][0] = 0
        with self.assertRaisesRegex(ValueError, "cycle"):
            saved._flat_structure(view)

    def test_payload_cannot_silently_claim_equivalence_or_drop_tree_nodes(self):
        payload = {**self.payload, "claims": {**self.payload["claims"],
                                             "class_or_tree_equivalence_proved": True}}
        with self.assertRaisesRegex(ValueError, "claim scope"):
            saved.evidence._completion(payload, self.report["progress"])
        payload = {**self.payload, "physical": {**self.payload["physical"], "tree_view": []}}
        with self.assertRaisesRegex(ValueError, "view sizes"):
            saved.evidence._completion(payload, self.report["progress"])


if __name__ == "__main__":
    unittest.main()
