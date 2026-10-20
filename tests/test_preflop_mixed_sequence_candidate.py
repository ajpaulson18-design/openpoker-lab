"""Bounded candidate shape, own-hand lift and formal-source admission."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from scripts import preflop_mixed_sequence_candidate as candidate
from scripts import certify_preflop_mixed_sequence as formal

class MixedSequenceCandidateTests(unittest.TestCase):
    def test_unchanged_lp_shape_and_physical_own_hand_lift(self):
        data=candidate.build_candidate()
        self.assertEqual(data['status'],'candidate-only')
        self.assertEqual(data['candidate_lp_shapes'],{'oop':[20,64],'ip':[28,80]})
        self.assertEqual(len(data['policies']),72)
        self.assertEqual(sum(len(r['actions']) for r in data['policies']),192)
        unsigned=dict(data);digest=unsigned.pop('artifact_sha256')
        self.assertEqual(candidate.checksum(unsigned),digest)
        # A serialized candidate is evidence to check, not an oracle in this test.
        self.assertEqual(json.loads(json.dumps(data)),data)

    def test_modified_spec_and_lp_caps_reject_before_source_or_matrix_allocation(self):
        spec=json.loads(candidate.SPEC.read_bytes());spec['physical_private_pairs']=71
        with patch.object(candidate.reference,'load_inputs') as inputs:
            with self.assertRaisesRegex(ValueError,'frozen'):candidate.build_candidate(spec)
            inputs.assert_not_called()
        caps={**candidate.lp.CAPS,'rows':97}
        with patch.object(candidate.lp,'CAPS',caps),patch.object(candidate.reference,'load_inputs') as inputs:
            with self.assertRaisesRegex(ValueError,'caps changed'):candidate.build_candidate()
            inputs.assert_not_called()

    def test_dirty_formal_source_never_builds_candidate(self):
        spec=json.loads(formal.SPEC.read_bytes())
        with patch.object(formal,'snapshot',return_value={'status':['dirty'],'revision':'test'}),patch.object(candidate,'build_candidate') as build:
            result=formal.run(spec)
        self.assertEqual(result['status'],'error');build.assert_not_called()
        self.assertIn('clean committed source',result['errors'][0]['error'])
