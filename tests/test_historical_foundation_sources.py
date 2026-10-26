import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import historical_foundation_sources as bridge


class HistoricalFoundationSourceTests(unittest.TestCase):
    def test_reviewed_transition_and_scope(self):
        receipt = bridge.authenticate_preflop_rank_transition()
        self.assertIn('rank-functions-only', receipt['scope'])
        self.assertTrue(bridge.historical_preflop_rank_source_matches(
            bridge.PREFLOP_SOURCE, bridge.OLD_PREFLOP_LF_SHA256))
        self.assertFalse(bridge.historical_preflop_rank_source_matches(
            bridge.PREFLOP_SOURCE, '0' * 64))
        self.assertFalse(bridge.historical_preflop_rank_source_matches(
            bridge.ARCHIVED_PREFLOP_SOURCE, bridge.OLD_PREFLOP_LF_SHA256))

    def test_rejects_altered_current_and_archived_bytes(self):
        old = bridge.ARCHIVED_PREFLOP_SOURCE.read_bytes()
        current = bridge.PREFLOP_SOURCE.read_bytes()
        original = Path.read_bytes
        def read_bad_old(path):
            return old + b"\n# changed\n" if path == bridge.ARCHIVED_PREFLOP_SOURCE else original(path)
        def read_bad_current(path):
            return current + b"\n# changed\n" if path == bridge.PREFLOP_SOURCE else original(path)
        for read in (read_bad_old, read_bad_current):
            with patch.object(Path, "read_bytes", read):
                self.assertFalse(bridge.historical_preflop_rank_source_matches(
                    bridge.PREFLOP_SOURCE, bridge.OLD_PREFLOP_LF_SHA256))

    def test_river_audit_transition_is_specific_and_pinned(self):
        self.assertTrue(bridge.historical_river_audit_source_matches(
            bridge.RIVER_AUDIT_SOURCE, bridge.OLD_RIVER_AUDIT_LF_SHA256))
        self.assertFalse(bridge.historical_river_audit_source_matches(
            bridge.RIVER_AUDIT_SOURCE, "0" * 64))
        self.assertFalse(bridge.historical_river_audit_source_matches(
            bridge.PREFLOP_SOURCE, bridge.OLD_RIVER_AUDIT_LF_SHA256))
        original = Path.read_bytes
        def altered(path):
            data = original(path)
            return data + b"\n# modified\n" if path == bridge.RIVER_AUDIT_SOURCE else data
        with patch.object(Path, "read_bytes", altered):
            self.assertFalse(bridge.historical_river_audit_source_matches(
                bridge.RIVER_AUDIT_SOURCE, bridge.OLD_RIVER_AUDIT_LF_SHA256))

    def test_raised_source_map_and_operation_guards(self):
        import json
        from scripts import full_deck_raised_reference as reference
        from scripts import audit_full_deck_raised_exact as audit
        for module, paths in ((reference, reference.SOURCE_PATHS), (audit, audit.SOURCES)):
            current = module.fingerprints()
            historical = json.loads(module.REPORT.read_text(encoding="utf-8"))["source_sha256"]
            self.assertTrue(bridge.compatible_historical_reference_sources(historical, current, paths))
            for key in ("scripts/preflop_validation.py", "scripts/full_deck_raised_reference.py"):
                bad = dict(historical)
                bad[key] = "0" * 64
                self.assertFalse(bridge.compatible_historical_reference_sources(bad, current, paths))
            dropped = dict(historical)
            dropped.pop(next(iter(paths)))
            self.assertFalse(bridge.compatible_historical_reference_sources(dropped, current, paths))
            added = dict(historical, unknown="0" * 64)
            self.assertFalse(bridge.compatible_historical_reference_sources(added, current, paths))
            before = bridge.operation_fingerprints(paths)
            original = Path.read_bytes
            def altered(path):
                data = original(path)
                return data + b"\n# drift\n" if path == bridge.ARCHIVED_RAISED_REFERENCE else data
            with patch.object(Path, "read_bytes", altered):
                self.assertNotEqual(before, bridge.operation_fingerprints(paths))
                self.assertFalse(bridge.compatible_historical_reference_sources(historical, current, paths))

    def test_exact_audit_rejects_source_drift_before_reconstruction(self):
        from scripts import audit_full_deck_raised_exact as audit
        bad_sources = audit.fingerprints()
        bad_sources["pokerlab/cards.py"] = "0" * 64
        with patch.object(audit, "fingerprints", return_value=bad_sources), \
             patch.object(audit, "reconstruct") as reconstruct:
            with self.assertRaisesRegex(ValueError, "Exact audit source pin differs"):
                audit.verify_saved_artifact()
            reconstruct.assert_not_called()

    def test_public_transition_matcher_rejects_unknown_equal_digests(self):
        for name, (_, old, current) in bridge.RAISED_TRANSITIONS.items():
            path = bridge.ROOT / name
            self.assertTrue(bridge.historical_foundation_source_matches(path, old))
            self.assertTrue(bridge.historical_foundation_source_matches(path, current))
            self.assertFalse(bridge.historical_foundation_source_matches(path, "0" * 64))
        self.assertTrue(bridge.historical_foundation_source_matches(
            bridge.PREFLOP_SOURCE, bridge.CURRENT_PREFLOP_LF_SHA256))
        self.assertFalse(bridge.historical_foundation_source_matches(
            bridge.ARCHIVED_PREFLOP_SOURCE, bridge.OLD_PREFLOP_LF_SHA256))

    def test_turn_verifier_transitions_accept_both_line_endings_and_reject_drift(self):
        import hashlib
        original_read = Path.read_bytes
        for name, (old, new, _allowed) in bridge.TURN_VERIFIER_TRANSITIONS.items():
            path = bridge.ROOT / name
            archive = bridge.ROOT / "tests/fixtures" / (Path(name).name + ".before_foundation.txt")
            old_crlf = hashlib.sha256(archive.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")).hexdigest()
            self.assertTrue(bridge.foundation_source_accepts(path, old, set()))
            self.assertTrue(bridge.foundation_source_accepts(path, old_crlf, set()))
            self.assertTrue(bridge.foundation_source_accepts(path, new, set()))
            self.assertFalse(bridge.foundation_source_accepts(path, "0" * 64, {"0" * 64}))
            def altered(candidate):
                raw = original_read(candidate)
                return raw + b"\n# unreviewed\n" if candidate == path else raw
            with patch.object(Path, "read_bytes", altered):
                self.assertFalse(bridge.foundation_source_accepts(path, old, set()))
        for path in (bridge.PREFLOP_SOURCE, bridge.RIVER_AUDIT_SOURCE):
            archive = bridge.ARCHIVED_PREFLOP_SOURCE if path == bridge.PREFLOP_SOURCE else bridge.ARCHIVED_RIVER_AUDIT
            raw = archive.read_bytes().replace(b"\r\n", b"\n")
            old_crlf = hashlib.sha256(raw.replace(b"\n", b"\r\n")).hexdigest()
            self.assertTrue(bridge.foundation_source_accepts(path, old_crlf, set()))
            self.assertFalse(bridge.foundation_source_accepts(path, "0" * 64, {"0" * 64}))

    def test_witness_rejects_unknown_source_before_building_model(self):
        import json
        from scripts import verify_turn_blocker_sequence as verify
        report = json.loads(verify.OUTPUT.read_text(encoding="utf-8"))
        report["source_sha256"]["scripts/preflop_validation.py"] = "0" * 64
        with patch.object(verify, "load", return_value=report), patch.object(verify, "model") as model:
            with self.assertRaisesRegex(ValueError, "Source provenance differs"):
                verify.verify_saved_artifact()
            model.assert_not_called()

    def test_direct_replay_maps_reject_drift_before_policy_audit(self):
        import json
        from scripts import benchmark_river_direct_tail as direct
        target = direct._fixed_targets(direct.ROOT)["report"]
        report = json.loads(target.read_text(encoding="utf-8"))
        current = direct._verification_hashes(direct.ROOT)
        saved = report["verification_source_sha256"]
        self.assertTrue(bridge.compatible_exact_source_maps(saved, current, direct.ROOT))
        for changed in (dict(saved, **{"scripts/preflop_validation.py": "0" * 64}),
                        {k: v for k, v in saved.items() if k != "scripts/preflop_validation.py"},
                        dict(saved, unknown="0" * 64)):
            self.assertFalse(bridge.compatible_exact_source_maps(changed, current, direct.ROOT))
        bad = dict(saved, **{"scripts/preflop_validation.py": "0" * 64})
        equally_bad = dict(current, **{"scripts/preflop_validation.py": "0" * 64})
        self.assertFalse(bridge.compatible_exact_source_maps(bad, equally_bad, direct.ROOT))
        report["verification_source_sha256"] = bad
        with patch.object(direct, "_audit_policy") as audit:
            with self.assertRaisesRegex(ValueError, "verification sources differ"):
                direct._verify_bundle(direct._pretty(report), {}, root=direct.ROOT,
                                      expected_math=current)
            audit.assert_not_called()

    def test_rank_dependencies_detect_changes(self):
        source = bridge.PREFLOP_SOURCE.read_bytes()
        reference = bridge._rank_asts(source)
        for altered in (source.replace(b'from collections import Counter, defaultdict', b'from collections import defaultdict'),
                        source.replace(b'from itertools import combinations', b'from itertools import permutations as combinations'),
                        source.replace(b'return max(_five_rank(five)', b'return min(_five_rank(five)')):
            with self.subTest(altered=altered != source):
                self.assertNotEqual(altered, source)
                try:
                    candidate = bridge._rank_asts(altered)
                except ValueError:
                    continue
                self.assertNotEqual(candidate, reference)


if __name__ == '__main__':
    unittest.main()
