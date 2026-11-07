"""Independent compact-checkpoint digest and preflight controls."""
import hashlib
import unittest
from unittest.mock import patch

from scripts.verify_virtual_dyadic_training import digest_compact_checkpoint, replay


class CheckpointDigestTests(unittest.TestCase):
    def test_independent_little_endian_average_then_regret(self):
        ordered=[('a',2),('b',1)]
        scales=[(3,7),(2,1)]
        average={'a':(8,24),'b':(20,)}
        regret={'a':(128,384),'b':(14,)}
        # widths are all one limb: no production checkpoint codec is used.
        raw=b''.join(x.to_bytes(8,'little') for x in (1,3,5,1,3,7))
        self.assertEqual(digest_compact_checkpoint(ordered,scales,regret,average,48,value_bits=64),
                         hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(hashlib.sha256(raw).digest(),hashlib.sha256(raw[24:]+raw[:24]).digest())

    def test_rejects_nondivisible_negative_overwide_and_bad_length(self):
        for values,extent in (({'a':(9,)},16),({'a':(-8,)},16),({'a':(1<<64,)},16),({'a':(8,)},15)):
            with self.subTest(values=values,extent=extent), self.assertRaises(ValueError):
                digest_compact_checkpoint([('a',1)],[(3,3)],{'a':(8,)},values,extent,value_bits=64)
        with self.assertRaises(ValueError):
            digest_compact_checkpoint([('a',1)],[],{'a':(8,)},{'a':(8,)},16,value_bits=64)

    def test_invalid_transport_and_digest_modes_precede_file_access(self):
        d='0'*64
        cases=(dict(checkpoint_digests=(d,)),dict(checkpoint_digests=(d,'A'*64),paired=True,rank_sets=True),
               dict(checkpoint_digests=(d,d)),dict(checkpoint_digests=(d,d),paired=True),
               dict(checkpoint_digests=(d,d),paired=True,rank_sets=True,images=()),
               dict(checkpoint_digests=(d,d),paired=True,rank_sets=True,packed_images=()))
        with patch('scripts.verify_virtual_dyadic_training.authenticated_reader',side_effect=AssertionError('file opened')):
            for case in cases:
                with self.subTest(case=case), self.assertRaises(ValueError):
                    replay('absent','0'*64,**case)

    def test_t3_requires_exactly_three_ordered_digest_inputs_before_file_access(self):
        d='1'*64
        cases=(dict(proof9_t3=True),
               dict(proof9_t3=True,paired=True,rank_sets=True,checkpoint_digests=(d,d)),
               dict(proof9_t3=True,paired=True,rank_sets=True,checkpoint_digests=(d,d,'A'*64)),
               dict(proof9_t3=True,paired=True,rank_sets=True,ten_card=True,checkpoint_digests=(d,d,d)),
               dict(proof9_t3=True,paired=True,rank_sets=True,images=(),checkpoint_digests=(d,d,d)),
               dict(proof9_t3=True,paired=True,rank_sets=True,packed_images=(),checkpoint_digests=(d,d,d)))
        with patch('scripts.verify_virtual_dyadic_training.authenticated_reader',side_effect=AssertionError('file opened')):
            for case in cases:
                with self.subTest(case=case), self.assertRaises(ValueError):
                    replay('absent','0'*64,**case)



    def test_t4_requires_exact_mode_and_four_lowercase_digests_before_file_access(self):
        d='1'*64
        cases=(dict(proof9_t4=True),
               dict(proof9_t4=True,paired=True,rank_sets=True,checkpoint_digests=(d,d,d)),
               dict(proof9_t4=True,paired=True,rank_sets=True,checkpoint_digests=(d,d,d,'A'*64)),
               dict(proof9_t4=True,proof9_t3=True,paired=True,rank_sets=True,checkpoint_digests=(d,)*4),
               dict(proof9_t4=True,ten_card=True,paired=True,rank_sets=True,checkpoint_digests=(d,)*4),
               dict(proof9_t4=True,paired=True,rank_sets=True,images=(),checkpoint_digests=(d,)*4),
               dict(proof9_t4=True,paired=True,rank_sets=True,packed_images=(),checkpoint_digests=(d,)*4))
        with patch('scripts.verify_virtual_dyadic_training.authenticated_reader',side_effect=AssertionError('file opened')):
            for case in cases:
                with self.subTest(case=case), self.assertRaises(ValueError):
                    replay('absent','0'*64,**case)


if __name__=='__main__':
    unittest.main()
