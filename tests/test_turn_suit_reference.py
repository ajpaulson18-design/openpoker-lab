"""Independent physical suit-reference and hidden-information admission regressions."""
import copy,hashlib,json,unittest
from fractions import Fraction as F
from unittest.mock import patch
from scripts import turn_suit_reference as reference
from scripts import verify_turn_blocker_sequence as base

class SuitReferenceTests(unittest.TestCase):
    def test_all24_frozen_exact_policies_without_candidate_or_evaluator(self):
        with patch('scripts.turn_sequence_compact_lp.solve_lp',side_effect=AssertionError('LP called')),patch('scripts.turn_rational_certificate.evaluate_exact',side_effect=AssertionError('Exact helper called')),patch('scripts.turn_suit_transport.transform_rows',side_effect=AssertionError('Candidate transport called')):
            result=reference.reconstruct()
        raw=json.dumps(result,sort_keys=True,indent=2,allow_nan=False).encode()+b'\n'
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'8b70ad5460061cbbe479c135a33eec69f9a80ec66b3e9d19c24f6ee919635ced')
        self.assertEqual(reference.REFERENCE.read_bytes(),raw)
        self.assertEqual(len(result['results']),24)
        self.assertTrue(all(r['metrics']['value_oop']=='115/7' and r['metrics']['nash_conv']=='0' for r in result['results']))

    def test_one_sided_mapping_adds_a_physically_new_pair(self):
        f=copy.deepcopy(reference.FIXTURE);f['oop']='AcAh:0.25,Th6h:0.75'
        board=base.rules.cards(f['board'])
        worlds,_=base.rules._worlds(board,tuple(base.rules.expand_range(f[p],board) for p in ('oop','ip')),f['runouts'])
        self.assertEqual(len(worlds),8)
        pairs={w['hands'] for w in worlds}
        self.assertEqual(len(pairs),4)
        new=[w for w in worlds if ''.join(w['hands'][0])=='AcAh' and ''.join(w['hands'][1])=='AdAs']
        self.assertEqual(sum((w['weight'] for w in new),F(0)),F(1,8))
        self.assertEqual([w['sign'] for w in new],[0,0])
        with self.assertRaisesRegex(ValueError,'Fixed physical support'):reference.game(f)
        raw=(reference.ROOT/'benchmarks/results/turn-suit-negative-reference-v1.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'5781e203b988bf330b2ad9f8cc91320704fc96e0987616408a4c78ffd370f8f0')

    def test_missing_rows_and_noncanonical_probabilities_reject_before_response(self):
        source=json.loads(base.OUTPUT.read_bytes())['results'][0]['rational_strategy']
        for mode in ('missing','fraction'):
            rows=copy.deepcopy(source)
            if mode=='missing':rows.pop()
            else:rows[0]['actions'][0]['probability_fraction']='0/2'
            with patch.object(base,'profile',side_effect=AssertionError('Profile math ran')),patch.object(base,'response',side_effect=AssertionError('Response math ran')):
                with self.assertRaises(ValueError):reference.replay(rows,reference.FIXTURE)

    def test_stale_river_history_rejects_transformed_policy(self):
        source=json.loads(base.OUTPUT.read_bytes())['results'][0]['rational_strategy']
        target='hscd';rows=reference.policy_rows(source,target)
        row=next(r for r in rows if r['street']=='river')
        marker=next(i for i,t in enumerate(row['history']) if t.startswith('river@'))
        row['history'][marker]='river@8d'
        with self.assertRaises(ValueError):reference.replay(rows,reference.fixture(target))

if __name__=='__main__':unittest.main()
