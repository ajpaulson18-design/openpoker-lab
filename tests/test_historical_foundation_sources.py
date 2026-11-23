import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import historical_foundation_sources as bridge


class HistoricalFoundationSourceTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'win32', 'Windows empty environment values are deleted by _wputenv')
    def test_committed_bridge_authenticates_after_empty_git_env_roundtrip(self):
        child = r'''import json, os
from unittest.mock import patch
from scripts import historical_foundation_sources as bridge

name = "GIT_CONFIG_VALUE_" + os.environ["BRIDGE_EMPTY_CONFIG_INDEX"]
count_before = int(os.environ["GIT_CONFIG_COUNT"])
def authenticated_head():
    try:
        value = bridge.require_committed_bridge().get("__git_head__")
        return value if isinstance(value, str) and len(value) == 40 else None
    except (OSError, ValueError):
        return None

before = authenticated_head()
with patch.dict(os.environ, {"BRIDGE_EMPTY_CONFIG_ROUNDTRIP": "1"}):
    pass
present_after = name in os.environ
empty_after = present_after and os.environ.get(name) == ""
after = authenticated_head()
print(json.dumps({
    "before_authenticated": before is not None,
    "after_authenticated": after is not None,
    "head_unchanged": before is not None and before == after,
    "empty_value_present_after": present_after,
    "empty_value_empty_after": empty_after,
    "config_count_before": count_before,
    "config_count_after": int(os.environ["GIT_CONFIG_COUNT"]),
}, sort_keys=True))
'''
        child_env = os.environ.copy()
        try:
            config_count = int(child_env.get('GIT_CONFIG_COUNT', '0'))
        except ValueError:
            self.fail('GIT_CONFIG_COUNT must be an integer for the isolated probe')
        child_env['GIT_CONFIG_KEY_{}'.format(config_count)] = 'core.pager'
        child_env['GIT_CONFIG_VALUE_{}'.format(config_count)] = ''
        child_env['GIT_CONFIG_COUNT'] = str(config_count + 1)
        child_env['BRIDGE_EMPTY_CONFIG_INDEX'] = str(config_count)
        with TemporaryDirectory(prefix='bridge-current-python-', dir=bridge.ROOT.parent) as cache:
            result = subprocess.run(
                [sys.executable, '-B', '-X', 'pycache_prefix=' + cache, '-c', child],
                cwd=bridge.ROOT, env=child_env,
                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, 'isolated environment probe failed')
        observed = json.loads(result.stdout)
        self.assertEqual(observed, {
            'before_authenticated': True,
            'after_authenticated': True,
            'head_unchanged': True,
            'empty_value_present_after': True,
            'empty_value_empty_after': True,
            'config_count_before': config_count + 1,
            'config_count_after': config_count + 1,
        })

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
                with self.assertRaisesRegex(ValueError, "Committed bridge source differs"):
                    bridge.operation_fingerprints(paths)
                self.assertFalse(bridge.compatible_historical_reference_sources(historical, current, paths))
            self.assertEqual(before, bridge.operation_fingerprints(paths))

    def test_preexisting_bridge_edit_rejects_before_reconstruction(self):
        from scripts import benchmark_river_direct_tail as direct
        original = Path.read_bytes
        helper = Path(bridge.__file__).resolve()
        def altered(path):
            data = original(path)
            return data + b"\n# preexisting uncommitted edit\n" if path.resolve() == helper else data
        with patch.object(Path, "read_bytes", altered), patch.object(direct, "_audit_policy") as audit:
            with self.assertRaisesRegex(ValueError, "Committed bridge source differs"):
                direct._verify_bundle(b"{}", {})
            audit.assert_not_called()

    def test_operation_snapshot_binds_head_and_all_bridge_inputs(self):
        import subprocess
        from scripts import historical_turn_sources as turn
        before = bridge.operation_fingerprints(())
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=bridge.ROOT,
                                       text=True).strip()
        self.assertEqual(before["__git_head__"], head)
        self.assertTrue({path.relative_to(bridge.ROOT).as_posix() for path in bridge.BRIDGE_INPUTS}
                        <= set(before))
        self.assertTrue(set(turn.OPERATION_INPUTS) <= set(before))
        self.assertNotEqual(before, dict(before, __git_head__="0" * 40))

    def test_untracked_bridge_input_and_head_race_reject(self):
        import subprocess
        missing = bridge.ROOT / "tests/fixtures/__untracked_bridge_input__.txt"
        self.assertFalse(missing.exists())
        with patch.object(bridge, "BRIDGE_INPUTS", bridge.BRIDGE_INPUTS + (missing,)):
            with self.assertRaisesRegex(ValueError, "not committed at HEAD"):
                bridge.operation_fingerprints(())
        original = subprocess.run
        head_reads = 0
        def moved_head(args, **kwargs):
            nonlocal head_reads
            result = original(args, **kwargs)
            if args == ["git", "rev-parse", "HEAD"]:
                head_reads += 1
                if head_reads == 2:
                    return subprocess.CompletedProcess(args, 0, "0" * 40 + "\n", "")
            return result
        with patch.object(bridge.subprocess, "run", moved_head):
            with self.assertRaisesRegex(ValueError, "HEAD changed"):
                bridge.operation_fingerprints(())

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

    def test_synthetic_test_transitions_preserve_all_other_ast(self):
        for name, (old_pin, new_pin, count) in bridge.SYNTHETIC_TEST_TRANSITIONS.items():
            path = bridge.ROOT / name
            self.assertGreater(count, 0)
            self.assertTrue(bridge.historical_foundation_source_matches(path, old_pin))
            self.assertTrue(bridge.historical_foundation_source_matches(path, new_pin))
            self.assertFalse(bridge.foundation_source_accepts(path, "0" * 64, {"0" * 64}))
            source = path.read_bytes()
            actual, actual_count = bridge._synthetic_test_ast(source, strip=True)
            self.assertEqual(actual_count, count)
            self.assertNotEqual(actual, bridge._synthetic_test_ast(source + b"\nextra = 1\n", strip=True)[0])

    def test_windows_temp_fixture_transition_is_exact_and_preserves_assertions(self):
        name = "tests/test_benchmark_river_direct_tail.py"
        path = bridge.ROOT / name
        archive_name, middle_pin, current_pin = bridge.WINDOWS_FIXTURE_TRANSITION[name]
        intermediate_path = bridge.ROOT / archive_name
        self.assertIn(intermediate_path, bridge.BRIDGE_INPUTS)
        old_path = bridge.ROOT / "tests/fixtures/test_benchmark_river_direct_tail.py.before_synthetic_bridge.txt"
        versions = (old_path.read_bytes(), intermediate_path.read_bytes(), path.read_bytes())
        self.assertEqual(bridge._sha(bridge._lf(versions[1])), middle_pin)
        self.assertEqual(bridge._sha(bridge._lf(versions[2])), current_pin)
        for raw in versions:
            for digest in bridge._line_ending_hashes(raw):
                self.assertTrue(bridge.historical_foundation_source_matches(path, digest))

        current = versions[2]
        assertion = b'self.assertEqual(targets["report"].read_bytes(), foreign)'
        self.assertIn(assertion, current)
        changed_assertion = current.replace(
            assertion, b'self.assertEqual(targets["report"].read_bytes(), b"forged")', 1)
        added_operation = current + b"\nextra_fixture_operation = True\n"
        for changed in (changed_assertion, added_operation):
            with self.assertRaisesRegex(ValueError, "exact transition pin"):
                bridge._windows_fixture_transition_ast(changed, source_version="current")
            self.assertFalse(bridge._synthetic_test_matches(path, bridge._sha(bridge._lf(changed))))

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
