"""Historical publication provenance must survive only sealed transitions."""
from copy import deepcopy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import preflop_publication_source_history as history
from scripts import verify_preflop_jj_kk_basis_publication as jj
from scripts import verify_preflop_three_rank_transport_publication as transport
from scripts import verify_preflop_three_rank_sequence_publication as witness


class PublicationSourceHistoryTests(unittest.TestCase):
    def test_exact_archived_sources_authenticate_without_calculation(self):
        for name, (old, new, archive) in history.TRANSITIONS.items():
            with self.subTest(source=name):
                result = history.authenticate_transition(name, old, new)
                self.assertEqual(result, {"historical_lf_sha256": old,
                                          "current_lf_sha256": new, "archive": archive})

    def test_unknown_calculation_source_has_no_exception(self):
        self.assertIsNone(history.authenticate_transition("pokerlab/cards.py", "0" * 64, "1" * 64))

    def test_changed_current_or_original_identity_rejects(self):
        for name, (old, new, _) in history.TRANSITIONS.items():
            for left, right in (("0" * 64, new), (old, "0" * 64)):
                with self.subTest(source=name, historical=left), self.assertRaisesRegex(ValueError, "Unrecognized"):
                    history.authenticate_transition(name, left, right)

    def test_changed_archive_and_symlink_reject(self):
        name, (old, new, relative) = next(iter(history.TRANSITIONS.items()))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / relative
            path.parent.mkdir(parents=True)
            path.write_bytes(b"changed archive\n")
            with patch.object(history, "ROOT", root), self.assertRaisesRegex(ValueError, "archive differs"):
                history.authenticate_transition(name, old, new)
            with patch.object(Path, "is_symlink", return_value=True), self.assertRaisesRegex(ValueError, "source archive"):
                history.authenticate_transition(name, old, new)

    def test_transport_and_witness_return_the_sealed_jj_transition(self):
        report = transport.independent._load_json((transport.PUBLICATION / "report.json").read_bytes())
        snap = transport.audit.snapshot()
        snap["status"] = []  # Metadata only during uncommitted publication edits.
        with patch.object(transport.audit, "snapshot", return_value=snap):
            receipt = transport._current_source_attestation(report["source_before"])
        self.assertEqual(set(receipt["publication_source_transitions"]),
                         {"scripts/verify_preflop_jj_kk_basis_publication.py"})
        report = witness.independent.sources._load_json((witness.PUBLICATION / "report.json").read_bytes())
        snap = witness.formal._snapshot()
        snap["status"] = []
        with patch.object(witness.formal, "_snapshot", return_value=snap):
            result = witness._current_source(report["source_before"])
        self.assertEqual(result["publication_source_transitions"], receipt["publication_source_transitions"])
        changed = deepcopy(snap)
        changed["source_hashes"]["scripts/verify_preflop_jj_kk_basis_publication.py"]["lf_sha256"] = "0" * 64
        with patch.object(witness.formal, "_snapshot", return_value=changed), self.assertRaisesRegex(ValueError, "Unrecognized"):
            witness._current_source(report["source_before"])

    def test_ci_workflow_accepts_only_original_or_one_exact_revision(self):
        name = ".github/workflows/native-fixed-street.yml"
        old, new, _ = history.TRANSITIONS[name]
        historical = {name: {"raw_sha256": old, "lf_sha256": old}}
        with patch.object(jj.five, "snapshot", return_value={"status": [], "source_hashes": {}}):
            result = jj._current_source_check(historical)
            self.assertEqual(result["publication_source_transitions"][name]["current_lf_sha256"], new)
            read = jj._read
            def changed(path, limit):
                return b"unapproved next CI edit\n" if path == jj.evidence.ROOT / name else read(path, limit)
            with patch.object(jj, "_read", side_effect=changed), self.assertRaisesRegex(ValueError, "Unrecognized historical CI"):
                jj._current_source_check(historical)


if __name__ == "__main__":
    unittest.main()
