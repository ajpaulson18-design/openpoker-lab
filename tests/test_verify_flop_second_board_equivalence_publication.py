"""Fast tamper tests for the immutable second-board publication."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from scripts import verify_flop_second_board_equivalence_publication as verifier


INDEX = verifier.PUBLICATION / "index.json"


class SavedEquivalencePublicationTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads(INDEX.read_text(encoding="utf-8"))
        self.before = self.report["source_before"]

    def _directory(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        target = Path(temp.name) / "publication"
        shutil.copytree(verifier.PUBLICATION, target)
        return target

    def _resign(self, directory, report):
        report.pop("index_sha256", None)
        report["index_sha256"] = verifier.proof._digest(report)
        raw = (json.dumps(report, sort_keys=True, separators=(",", ":"),
                          allow_nan=False) + "\n").encode()
        (directory / "index.json").write_bytes(raw)
        return patch.object(verifier, "INDEX_BYTES", len(raw)), patch.object(
            verifier, "RAW_INDEX_SHA256", hashlib.sha256(raw).hexdigest()), patch.object(
            verifier, "INDEX_SHA256", report["index_sha256"])

    def _snapshots(self, after=None):
        return patch.object(verifier.evidence, "_snapshot",
                            side_effect=[self.before, self.before if after is None else after])

    def test_actual_saved_corpus_authenticates_without_expensive_calls(self):
        forbidden = [
            patch.object(verifier.evidence.proof, "_make_model", side_effect=AssertionError("model")),
            patch.object(verifier.evidence.proof.physical, "prepare_oracle", side_effect=AssertionError("prepare")),
            patch.object(verifier.evidence.proof.physical, "independent_rank", side_effect=AssertionError("rank")),
            patch("pokerlab.cfr_plus.train", side_effect=AssertionError("train")),
            patch.object(verifier.evidence.proof, "_project", side_effect=AssertionError("private project")),
            patch.object(verifier.evidence.proof.physical, "replay", side_effect=AssertionError("replay")),
            patch.object(verifier.evidence.proof.shared, "_exact_metrics", side_effect=AssertionError("metrics")),
            patch.object(verifier.evidence.proof, "project_policy", side_effect=AssertionError("project")),
            patch.object(verifier.evidence.proof, "audit_control", side_effect=AssertionError("audit")),
        ]
        later = deepcopy(self.before)
        later["revision"] = "a" * 40
        with ExitStack() as stack:
            stack.enter_context(self._snapshots(after=later))
            for context in forbidden:
                stack.enter_context(context)
            result = verifier.verify()
        self.assertEqual(result["status"], "saved-second-board-equivalence-authenticated")
        self.assertFalse(result["quality_claim"])
        for counter in ("physical_builds", "ranking_calls", "model_projection_calls",
                        "exact_response_calls", "numeric_replay_calls", "training_calls"):
            self.assertEqual(result[counter], 0)

    def test_raw_index_mutation_rejected_before_json_or_payload_work(self):
        directory = self._directory()
        with (directory / "index.json").open("ab") as stream:
            stream.write(b" ")
        with patch.object(verifier, "_load_payloads", side_effect=AssertionError("payloads read")), \
             self._snapshots(), self.assertRaises(ValueError):
            verifier.verify(directory)

    def test_resigned_authority_or_source_tamper_is_rejected(self):
        for mutate in (
            lambda data: data["authority_calls"].__setitem__(next(iter(data["authority_calls"])), 1),
            lambda data: data["source_before"].__setitem__("revision", "0" * 40),
        ):
            with self.subTest(mutate=mutate):
                directory = self._directory()
                changed = deepcopy(self.report)
                mutate(changed)
                pin_contexts = self._resign(directory, changed)
                with pin_contexts[0], pin_contexts[1], pin_contexts[2], self._snapshots(), \
                     self.assertRaises(ValueError):
                    verifier.verify(directory)

    def test_control_claim_tamper_rejected_after_resigned_index(self):
        directory = self._directory()
        changed = deepcopy(self.report)
        changed["census"]["compact_worlds"] = 169
        pin_contexts = self._resign(directory, changed)
        with pin_contexts[0], pin_contexts[1], pin_contexts[2], self._snapshots(), \
             self.assertRaises(ValueError):
            verifier.verify(directory)

    def test_policy_probability_tamper_with_repaired_receipts_is_rejected(self):
        directory = self._directory()
        changed = deepcopy(self.report)
        control = changed["controls"][0]
        relative = control["payload"]["path"]
        payload_path = directory / relative
        with gzip.open(payload_path, "rt", encoding="utf-8") as stream:
            payload = json.load(stream)
        payload["strategy"][0]["actions"][0]["probability"] = 0.875
        payload["strategy"][0]["actions"][1]["probability"] = 0.125
        raw = (json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
        compressed = gzip.compress(raw, mtime=0)
        payload_path.write_bytes(compressed)
        control["payload"].update(raw_bytes=len(raw), raw_sha256=hashlib.sha256(raw).hexdigest(),
                                  gzip_bytes=len(compressed), gzip_sha256=hashlib.sha256(compressed).hexdigest())
        control["physical_policy_sha256"] = verifier.proof._digest(payload)
        pins = self._resign(directory, changed)
        with pins[0], pins[1], pins[2], self._snapshots(), self.assertRaises(ValueError):
            verifier.verify(directory)

    def test_duplicate_and_nonfinite_json_rejected(self):
        with self.assertRaises(ValueError):
            verifier._json(b'{"a":1,"a":2}')
        with self.assertRaises(ValueError):
            verifier._json(b'{"a":NaN}')

    def test_oversized_gzip_receipt_rejected_before_decompression(self):
        control = self.report["controls"][0]
        receipt = deepcopy(control["payload"])
        receipt["gzip_bytes"] = verifier.MAX_GZIP_BYTES + 1
        with patch.object(verifier.gzip, "GzipFile", side_effect=AssertionError("decompressed")), \
             self.assertRaises(ValueError):
            verifier._read_payload(verifier.PUBLICATION, receipt, receipt["path"])

    def test_preparation_bool_aliases_rejected(self):
        spec = verifier.evidence._protocol()[1]
        for field in ("physical_builds_attempted", "physical_builds_completed",
                      "preparation_rank_calls", "preparation_ranker_attempts"):
            with self.subTest(field=field):
                changed = deepcopy(self.report)
                changed["preparation"][field] = True
                changed.pop("index_sha256", None)
                digest = verifier.proof._digest(changed)
                changed["index_sha256"] = digest
                with patch.object(verifier, "INDEX_SHA256", digest), self.assertRaises(ValueError):
                    verifier._validate(changed, {}, self.before, spec)

    def test_negative_action_and_row_tampering_rejected(self):
        turns, rivers = verifier.evidence.proof.shared._maps(self.report["partition"])
        zero_receipt = self.report["controls"][3]["payload"]
        with gzip.open(verifier.PUBLICATION / zero_receipt["path"], "rt", encoding="utf-8") as stream:
            zero = json.load(stream)
        for neg in self.report["negative_controls"]:
            with gzip.open(verifier.PUBLICATION / neg["payload"]["path"], "rt", encoding="utf-8") as stream:
                payload = json.load(stream)
            idx = neg["physical_row_index"]
            bad_action = deepcopy(payload)
            bad_action["strategy"][idx]["actions"][0]["name"] = "tampered-action"
            with self.subTest(mode=neg["mode"], tamper="action"), self.assertRaises(ValueError):
                verifier._validate_negative(neg, bad_action, zero, turns, rivers, neg["mode"])
            bad_identity = deepcopy(neg)
            bad_identity["hand"] = "QdQs"
            with self.subTest(mode=neg["mode"], tamper="key"), self.assertRaises(ValueError):
                verifier._validate_negative(bad_identity, payload, zero, turns, rivers, neg["mode"])
            bad_probability = deepcopy(payload)
            bad_probability["strategy"][idx]["actions"][0]["probability"] = 0.5
            bad_probability["strategy"][idx]["actions"][1]["probability"] = 0.5
            with self.subTest(mode=neg["mode"], tamper="replacement"), self.assertRaises(ValueError):
                verifier._validate_negative(neg, bad_probability, zero, turns, rivers, neg["mode"])

    def test_current_source_map_drift_is_rejected(self):
        bad = deepcopy(self.before)
        path = next(iter(bad["source_lf_sha256"]))
        bad["source_lf_sha256"][path] = "0" * 64
        with patch.object(verifier.evidence, "_snapshot", side_effect=[self.before, bad]), \
             self.assertRaises(ValueError):
            verifier.verify()


if __name__ == "__main__":
    unittest.main()
