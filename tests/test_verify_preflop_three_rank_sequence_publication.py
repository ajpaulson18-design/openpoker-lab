from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_preflop_three_rank_sequence_publication as publication


class ThreeRankSequencePublicationTests(unittest.TestCase):
    def _report(self):
        return publication.independent.sources._load_json(
            (publication.PUBLICATION / "report.json").read_bytes())

    def _clean_snapshot(self):
        source = publication.formal._snapshot()
        source["status"] = []
        return source

    def _copy(self, destination):
        for name in publication.PINS:
            shutil.copyfile(publication.PUBLICATION / name, destination / name)

    def test_actual_corpus_replays_with_candidate_tree_lp_rank_and_training_forbidden(self):
        # Local publication work is untracked here. Only clean-checkout metadata
        # is isolated; actual saved counts and all physical response work remain.
        with patch.object(publication.formal, "_snapshot", return_value=self._clean_snapshot()), \
                patch.object(publication.independent.sources.jj, "_current_source_check"):
            result = publication.verify()
        self.assertEqual(result["status"], "authenticated-saved-exact-witness")
        self.assertEqual(result["exact_value_sb_fraction"], "1464215/2330174")
        self.assertEqual(result["nash_conv_fraction"], "0")
        self.assertEqual(result["legal_own_hand_responses"], 1080)
        self.assertEqual((result["policy_rows"], result["action_slots"]), (96, 258))

    def test_altered_raw_bytes_reject_before_json_parsing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._copy(root)
            raw = bytearray((root / "candidate.json").read_bytes())
            raw[-2] ^= 1
            (root / "candidate.json").write_bytes(raw)
            with patch.object(publication.independent.sources, "_load_json",
                              side_effect=AssertionError("parsed")):
                with self.assertRaisesRegex(ValueError, "raw saved bytes"):
                    publication.verify(root)

    def test_extra_file_rejects_before_authentication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._copy(root)
            (root / "extra.txt").write_text("extra")
            with patch.object(publication.independent, "verify_candidate",
                              side_effect=AssertionError("replayed")):
                with self.assertRaisesRegex(ValueError, "inventory"):
                    publication.verify(root)

    def test_resigned_attempt_alias_and_false_response_fail_semantics(self):
        for field, value, message in (("lp_solve_calls", True, "attempt/call"),
                                     ("quality_target_met", False, "quality")):
            report = self._report()
            report[field] = value
            report["artifact_sha256"] = publication._artifact(report)
            pins = deepcopy(publication.PINS)
            pins["report.json"]["artifact"] = report["artifact_sha256"]
            with self.subTest(field=field), patch.object(publication, "PINS", pins):
                with self.assertRaisesRegex(ValueError, message):
                    publication._report(json.dumps(report).encode())
        receipt = self._report()["memory_verification"]
        receipt["nash_conv_fraction"] = "1/100"
        with self.assertRaisesRegex(ValueError, "response gain"):
            publication._quality(receipt)

    def test_later_clean_head_accepts_same_sources_and_rejects_lf_drift(self):
        source = self._report()["source_before"]
        current = self._clean_snapshot()
        current["revision"] = "a" * 40
        with patch.object(publication.formal, "_snapshot", return_value=current):
            self.assertEqual(publication._current_source(source)["revision"], "a" * 40)
        current["source_hashes"][publication.SOURCES[0]]["lf_sha256"] = "0" * 64
        with patch.object(publication.formal, "_snapshot", return_value=current):
            with self.assertRaisesRegex(ValueError, "LF source differs"):
                publication._current_source(source)

    def test_current_source_change_during_replay_rejects(self):
        source = self._clean_snapshot()
        changed = deepcopy(source)
        changed["revision"] = "b" * 40
        receipt = self._report()["memory_verification"]
        with patch.object(publication, "_current_source", side_effect=(source, changed)), \
                patch.object(publication.independent, "verify_candidate", return_value=receipt):
            with self.assertRaisesRegex(ValueError, "source changed during"):
                publication.verify()

    def test_saved_corpus_change_during_replay_rejects(self):
        receipt = self._report()["memory_verification"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._copy(root)

            def mutate(_path):
                path = root / "report.json"
                path.write_bytes(path.read_bytes() + b" ")
                return receipt

            with patch.object(publication, "_current_source", return_value=self._clean_snapshot()), \
                    patch.object(publication.independent, "verify_candidate", side_effect=mutate):
                with self.assertRaisesRegex(ValueError, "size differs"):
                    publication.verify(root)


if __name__ == "__main__":
    unittest.main()
