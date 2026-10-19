"""Full physical range construction and admissible exact one-chip bounds."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import preflop_aa_kk_reference as ref
from scripts import benchmark_preflop_aa_kk_range as bench

class PhysicalRangeReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=json.loads(ref.SPEC.read_bytes());cls.table,cls.counts,cls.source=ref.load_inputs(cls.spec)

    def test_full_physical_range_has_all_three_suit_classes_and_exact_bounds(self):
        proof=ref.constructive_value(self.spec,self.counts)
        self.assertEqual(len(self.table.pairs),36)
        self.assertEqual(proof['suit_overlap_class_counts'],{'0':6,'1':24,'2':6})
        self.assertEqual(proof['lower_bound_fraction'],proof['upper_bound_fraction'])
        self.assertEqual(proof['exact_value_sb_fraction'],'1')
        self.assertGreater(Fraction(proof['minimum_conditional_mean_fraction']),Fraction(1,3))
        self.assertLess(Fraction(proof['maximum_conditional_mean_fraction']),1)
        self.assertEqual(self.table.budget['physical_worlds_upper_bound'],61642944)
        self.assertTrue(all(p==Fraction(1,36) for _,_,p in self.table.pairs))

    def test_bound_rejects_missing_pair_or_non_dominating_showdown_mean(self):
        with self.assertRaises(ValueError):ref.constructive_value(self.spec,self.counts[:-1])
        altered=deepcopy(self.counts);altered[0].update(wins=500000,ties=12304,losses=1200000)
        with self.assertRaisesRegex(ValueError,'payoff inequalities'):ref.constructive_value(self.spec,altered)
        with self.assertRaises(ValueError):ref.constructive_value({**self.spec,'bb_range':'QQ'},self.counts)

    def test_all_requests_admit_before_lookup_and_four_pair_preparation_stays_closed(self):
        from pokerlab import native_fixed_street as native
        from pokerlab.preflop_full_board_equity import plan_preflop_equities
        with patch.object(native,'_backend',side_effect=AssertionError('native before all admissions')):
            rows=[bench.core.preflight(self.table,self.spec,n) for n in self.spec['checkpoints']]
        self.assertEqual(len(rows),3)
        self.assertLessEqual(max(x['python']['total_loop_entries_upper_bound'] for x in rows),500000000)
        self.assertLessEqual(max(x['native']['total_loop_entries_upper_bound'] for x in rows),500000000)
        with self.assertRaises(ValueError):plan_preflop_equities('AA','KK')

    def test_dirty_source_never_resolves_inputs_or_native_build(self):
        with (patch.object(bench,'snapshot',return_value={'status':['dirty']}),
              patch.object(ref,'load_inputs') as inputs,
              patch.object(bench.core.native,'_build_identity') as lookup):
            report=bench.run(self.spec,'unused')
        self.assertEqual(report['status'],'error');inputs.assert_not_called();lookup.assert_not_called()

    def test_saved_metadata_addition_updates_the_actual_checksum(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'report.json';report={'status':'test-only'}
            bench.save_report(path,report)
            report['saved_verification']={'status':'test-only'};bench.save_report(path,report)
            data=json.loads(path.read_bytes());digest=data.pop('artifact_sha256')
            self.assertEqual(digest,bench.core.checksum(data))
