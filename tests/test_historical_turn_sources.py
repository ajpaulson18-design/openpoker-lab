"""Exact provenance migrations, with every unknown or re-signed source rejected."""
import hashlib
from pathlib import Path
import unittest
from scripts import historical_turn_sources as provenance

ROOT=Path(__file__).resolve().parents[1]


class HistoricalTurnSourceTests(unittest.TestCase):
    def test_transition_current_files_have_the_exact_reviewed_bytes(self):
        self.assertEqual(len(provenance.TRANSITIONS),5)
        for name,(old,new) in provenance.TRANSITIONS.items():
            with self.subTest(name=name):
                raw=(ROOT/name).read_bytes().replace(b'\r\n',b'\n')
                self.assertEqual(hashlib.sha256(raw).hexdigest(),new)
                self.assertNotEqual(old,new)
                self.assertTrue(provenance.compatible_source(name,old,new))
                self.assertFalse(provenance.compatible_source(name,new,old))
                self.assertFalse(provenance.compatible_source(name,'0'*64,new))
                self.assertFalse(provenance.compatible_source(name,old,'0'*64))
                self.assertFalse(provenance.compatible_source('unknown/'+name,old,new))

    def test_maps_do_not_drop_extra_missing_or_unknown_mismatched_sources(self):
        old={name:row[0] for name,row in provenance.TRANSITIONS.items()}
        new={name:row[1] for name,row in provenance.TRANSITIONS.items()}
        self.assertTrue(provenance.compatible_source_maps(old,new))
        self.assertTrue(provenance.compatible_source_maps(new,new))
        for changed in (dict(new,extra='0'*64),{k:v for k,v in new.items() if k!=next(iter(new))},
                        dict(new,**{'pokerlab/postflop_solver.py':'0'*64})):
            self.assertFalse(provenance.compatible_source_maps(old,changed))
        self.assertFalse(provenance.compatible_source_maps(None,new))


if __name__=='__main__':
    unittest.main()
