"""Exact provenance migrations, with every unknown or re-signed source rejected."""
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import historical_turn_sources as provenance

ROOT=Path(__file__).resolve().parents[1]


class HistoricalTurnSourceTests(unittest.TestCase):
    def test_transition_current_files_have_the_exact_reviewed_bytes(self):
        self.assertEqual(len(provenance.TRANSITIONS),7)
        for name,(old,new) in provenance.TRANSITIONS.items():
            with self.subTest(name=name):
                raw=(ROOT/name).read_bytes().replace(b'\r\n',b'\n')
                current = provenance.FOUNDATION_TRANSITIONS.get(name, new)
                self.assertEqual(hashlib.sha256(raw).hexdigest(),current)
                self.assertNotEqual(old,new)
                self.assertTrue(provenance.compatible_source(name,old,new))
                self.assertTrue(provenance.compatible_source(name,old,old))
                self.assertTrue(provenance.compatible_source(name,new,new))
                self.assertFalse(provenance.compatible_source(name,'0'*64,'0'*64))
                self.assertFalse(provenance.compatible_source(name,new,old))
                self.assertFalse(provenance.compatible_source(name,'0'*64,new))
                self.assertFalse(provenance.compatible_source(name,old,'0'*64))
                self.assertFalse(provenance.compatible_source('unknown/'+name,old,new))
                self.assertTrue(provenance.compatible_source(name,old,current))
                self.assertTrue(provenance.compatible_source(name,new,current))
                if current != new:
                    self.assertFalse(provenance.compatible_source(name,current,new))

    def test_postflop_guard_dependency_and_literal_arithmetic_are_authenticated(self):
        receipt = provenance.authenticate_postflop_transition()
        self.assertEqual(receipt['archived_lf_sha256'], provenance.TRANSITIONS['pokerlab/postflop_solver.py'][1])
        self.assertEqual(receipt['current_lf_sha256'], provenance.POSTFLOP_FOUNDATION_SHA256)
        read = provenance._lf
        for target in ('pokerlab/probability_guard.py', provenance.POSTFLOP_ARCHIVE,
                       'pokerlab/postflop_solver.py'):
            with self.subTest(target=target), patch.object(
                    provenance, '_lf', side_effect=lambda path: b'changed' if path == target else read(path)):
                with self.assertRaisesRegex(ValueError, 'transition|guard'):
                    provenance.authenticate_postflop_transition()

    def test_reviewed_wrapper_transitions_preserve_non_provenance_math(self):
        for name in provenance.WRAPPER_CHANGES:
            with self.subTest(name=name):
                receipt = provenance.authenticate_wrapper_transition(name)
                old = (provenance.TRANSITIONS[name][1] if name in provenance.TRANSITIONS
                       else provenance.PRE_FOUNDATION_TESTS[name][0])
                self.assertEqual(receipt['archived_lf_sha256'], old)
                self.assertEqual(receipt['current_lf_sha256'], provenance.FOUNDATION_TRANSITIONS[name])
                self.assertTrue(provenance.compatible_source(name, receipt['archived_lf_sha256'],
                                                            receipt['current_lf_sha256']))
                self.assertFalse(provenance.compatible_source(name, '0' * 64, '0' * 64))

    def test_current_operation_context_rejects_missing_or_resigned_guard(self):
        from scripts import benchmark_full_deck_raised_turn as benchmark
        current = benchmark.fingerprints()
        provenance.validate_current_context(current)
        for target in provenance.OPERATION_INPUTS:
            with self.subTest(target=target):
                bad = dict(current)
                del bad[target]
                with self.assertRaisesRegex(ValueError, 'Current source differs'):
                    provenance.validate_current_context(bad)
                bad[target] = '0' * 64
                with self.assertRaisesRegex(ValueError, 'Current source differs'):
                    provenance.validate_current_context(bad)

    def test_operation_archive_hashes_ignore_checkout_line_endings(self):
        from scripts import benchmark_full_deck_raised_turn as raised, benchmark_turn_tail as tail
        original = Path.read_bytes
        for module in (raised, tail):
            expected = module.fingerprints()
            def crlf_archives(path):
                raw = original(path)
                if path.suffix == '.txt' and path.relative_to(ROOT).as_posix() in provenance.OPERATION_INPUTS:
                    return raw.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
                return raw
            with self.subTest(module=module.__name__), patch.object(Path, 'read_bytes', crlf_archives):
                self.assertEqual(module.fingerprints(), expected)
                provenance.validate_current_context(expected)

    def test_saved_benchmark_cannot_bypass_protected_check_with_equal_unknown_hashes(self):
        from scripts import benchmark_full_deck_raised_turn as benchmark
        current = benchmark.fingerprints()
        historical = dict(current)
        benchmark._validate_fingerprint_map(historical,current,strict=False)
        current["pokerlab/postflop_solver.py"] = "0"*64
        historical["pokerlab/postflop_solver.py"] = "0"*64
        with self.assertRaisesRegex(ValueError,"Current source differs"):
            benchmark._validate_fingerprint_map(historical,current,strict=False)

    def test_maps_do_not_drop_extra_missing_or_unknown_mismatched_sources(self):
        old={name:row[0] for name,row in provenance.TRANSITIONS.items()}
        new={name:row[1] for name,row in provenance.TRANSITIONS.items()}
        self.assertTrue(provenance.compatible_source_maps(old,new))
        self.assertTrue(provenance.compatible_source_maps(new,new))
        for name in provenance.TRANSITIONS:
            unknown_old = dict(old, **{name:'0'*64})
            unknown_new = dict(new, **{name:'0'*64})
            self.assertFalse(provenance.compatible_source_maps(unknown_old,unknown_new))
        for changed in (dict(new,extra='0'*64),{k:v for k,v in new.items() if k!=next(iter(new))},
                        dict(new,**{'pokerlab/postflop_solver.py':'0'*64})):
            self.assertFalse(provenance.compatible_source_maps(old,changed))
        self.assertFalse(provenance.compatible_source_maps(None,new))


if __name__=='__main__':
    unittest.main()
