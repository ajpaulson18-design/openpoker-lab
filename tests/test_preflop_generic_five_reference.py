"""Bounded generic reference input, provenance and raw failure checks."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from scripts import preflop_five_count_reference as ref
from scripts import validate_preflop_five_reference as base

class GenericReferenceTests(unittest.TestCase):
    def test_admission_and_text_bounds_reject_before_build_or_conformance_lookup(self):
        with (patch.object(ref,'backend') as build,patch.object(ref,'verify_saved') as proof):
            with self.assertRaises(ValueError):
                ref.reference_preflop_counts('AA','KK',build_directory='unused',conformance_report='missing',observation_directory='unused')
        build.assert_not_called();proof.assert_not_called()
        with patch.object(ref,'plan_preflop_equities',side_effect=AssertionError('parsed huge expression')):
            with self.assertRaises(ValueError):ref.pair_admission('AA '*20000,'KK')

    def test_independent_pair_census_keeps_blockers_and_original_rank_caps(self):
        pairs,admission=ref.pair_admission('AdAs:1,QdQs:.5','AsKh:.25,KdKs:1')
        self.assertEqual(len(pairs),3)
        self.assertEqual(admission['boards'],5136912)
        self.assertEqual(admission['five_card_rank_calls'],215750304)
        self.assertTrue(all(set(a).isdisjoint(b) for a,b in pairs))
        self.assertEqual(admission['ordinary_preparation']['rank_calls_upper_bound'],10273824)

    def test_raw_row_verification_rejects_role_changes_bool_and_work_understatement(self):
        pairs,_=ref.pair_admission('AdAs','KdKs')
        # Synthetic complete count totals exercise only the protocol schema.
        data={'schema_version':1,'reference':'preflop-five-card-pairs-v2','pairs':[
             {'sb_ids':[49,51],'bb_ids':[45,47],'wins':1000000,'ties':12304,'losses':700000,'boards':1712304}],
             'boards_total':1712304,'seven_card_rank_calls':3424608,'five_card_rank_calls':71916768}
        self.assertEqual(ref.verify_rows(data,pairs)[0][:2],('AdAs','KdKs'))
        for mutate in (lambda x:x.update(boards_total=True),lambda x:x.update(five_card_rank_calls=1),
                       lambda x:x['pairs'][0].update(sb_ids=[45,47]),
                       lambda x:x['pairs'][0].update(wins=True),lambda x:x['pairs'][0].update(ties=12305)):
            changed=deepcopy(data);mutate(changed)
            with self.assertRaises(ValueError):ref.verify_rows(changed,pairs)

    def test_conformance_for_another_build_blocks_counting(self):
        report=Path(__file__).resolve().parents[1]/'benchmarks/results/preflop-five-basis-v1.json'
        with (patch.object(ref,'backend',return_value=(Path('unused'),{'other':'build'})),
              patch.object(ref.subprocess,'run') as counted):
            with self.assertRaisesRegex(ValueError,'another reference'):
                ref.reference_preflop_counts('AdAs','KdKs',build_directory='unused',conformance_report=report,observation_directory='unused')
        counted.assert_not_called()

    def test_returned_rows_and_metadata_are_detached(self):
        value=ref.ReferencePreflopCounts((('AdAs','KdKs',1000000,12304,700000,1712304),),'{"original":true}')
        rows=value.rows;rows[0]['wins']=0
        metadata=value.metadata;metadata['original']=False
        self.assertEqual(value.rows[0]['wins'],1000000)
        self.assertTrue(value.metadata['original'])

    def test_malformed_count_failure_retains_complete_raw_output_files(self):
        from types import SimpleNamespace
        report_path=Path(__file__).resolve().parents[1]/'benchmarks/results/preflop-five-basis-v1.json'
        report=json.loads(report_path.read_bytes());identity=report['reference_build_before']
        def bad_process(args,*,stdout,stderr,**kwargs):
            stdout.write(b'{malformed raw result');stderr.write(b'raw diagnostic retained')
            return SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'raw'
            with (patch.object(ref,'backend',return_value=(Path('unused'),identity)),
                  patch.object(ref.subprocess,'run',side_effect=bad_process)):
                with self.assertRaises(ref.ReferenceCountFailure) as caught:
                    ref.reference_preflop_counts('AdAs','KdKs',build_directory='unused',
                        conformance_report=report_path,observation_directory=target)
            self.assertEqual((target/'stdout.json').read_bytes(),b'{malformed raw result')
            self.assertEqual((target/'stderr.txt').read_bytes(),b'raw diagnostic retained')
            self.assertEqual(caught.exception.observation['returncode'],0)
            self.assertEqual(caught.exception.observation['stdout_path'],str(target/'stdout.json'))


class GenericNativeProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=os.environ.get('OPENPOKER_FIVE_REFERENCE_BUILD_DIR')
        if not path or not Path(path).is_dir():raise unittest.SkipTest('Explicit independent reference build unavailable')
        cls.executable,_=base.backend(path)

    def test_every_bad_argument_rejects_before_output_or_enumeration(self):
        invalid=[[],['--count-pairs'],['--all-five','extra'],['--count-basis','extra'],
                 ['--count-pairs','49','51','45'],['--count-pairs','49','51','45','52'],
                 ['--count-pairs','49','49','45','47'],['--count-pairs','49','51','51','47'],
                 ['--count-pairs','-1','51','45','47'],['--count-pairs','+1','51','45','47'],
                 ['--count-pairs','1.0','51','45','47'],['--count-pairs','1\x1a','51','45','47'],
                 ['--count-pairs']+['49','51','45','47']*5,
                 ['--count-pairs','49','51','45','47','51','49','47','45']]
        for args in invalid:
            with self.subTest(args=args):
                process=subprocess.run([str(self.executable),*args],capture_output=True,timeout=5,check=False)
                self.assertEqual(process.returncode,2)
                self.assertEqual(process.stdout,b'')

    def test_roles_are_ordered_and_reversal_flips_wins_losses(self):
        values=[]
        for ids in (('49','51','45','47'),('45','47','49','51')):
            process=subprocess.run([str(self.executable),'--count-pairs',*ids],capture_output=True,timeout=120,check=False)
            self.assertEqual(process.returncode,0)
            data=json.loads(process.stdout);self.assertEqual(data['five_card_rank_calls'],71916768)
            row=data['pairs'][0];values.append((row['wins'],row['ties'],row['losses']))
        self.assertEqual(values[0],(1410336,9308,292660))
        self.assertEqual(values[1],(292660,9308,1410336))

    def test_valid_four_pair_boundary_matches_independent_pinned_and_suit_mapped_counts(self):
        pairs=[(('Ad','As'),('Kd','Ks')),(('Qd','Qs'),('Ad','Kc')),
               (('Qd','Qs'),('As','Kh')),(('Qd','Qs'),('Kd','Ks'))]
        ids={card:n for n,card in enumerate(base.DECK)}
        args=[str(self.executable),'--count-pairs',*[str(ids[card]) for a,b in pairs for card in a+b]]
        process=subprocess.run(args,capture_output=True,timeout=120,check=False)
        self.assertEqual(process.returncode,0)
        data=json.loads(process.stdout);rows=ref.verify_rows(data,pairs)
        self.assertEqual(data['boards_total'],6849216)
        self.assertEqual(data['seven_card_rank_calls'],13698432)
        self.assertEqual(data['five_card_rank_calls'],287667072)
        # The AdKc pair is the same QQ/AK source under d<->s and h<->c.
        self.assertEqual([x[2:5] for x in rows],[(1410336,9308,292660),
                    (968267,7226,736811),(968267,7226,736811),(292846,9336,1410122)])
