"""All saved mixed trainer policies retain strict bounds around the exact value."""
from pathlib import Path
import json
import unittest
from scripts.verify_preflop_mixed_anchor import derive

ROOT=Path(__file__).resolve().parents[1]
class MixedExactAnchorTests(unittest.TestCase):
    def test_actual_published_profiles_reproduce_every_derived_anchor_check(self):
        expected=json.loads((ROOT/'benchmarks/results/preflop-mixed-training-exact-anchor-v1.json').read_bytes())
        actual=derive();self.assertEqual(actual,expected)
        self.assertEqual(actual['exact_value_sb_fraction'],'61612/75655')
        self.assertEqual(len(actual['policies']),10)
        self.assertTrue(all(r['exact_anchor_contained'] and r['value_error_within_nash_conv'] for r in actual['policies']))
        self.assertFalse(actual['policies'][0]['original_quality_target_met'])
