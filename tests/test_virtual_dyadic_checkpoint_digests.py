"""Independent compact-checkpoint digest and preflight controls."""
import hashlib
import io
import struct
import unittest
from unittest.mock import patch

from scripts.verify_virtual_dyadic_training import Reader, bounded_checkpoint_records, digest_compact_checkpoint, replay


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

    def test_streaming_wire_order_and_compact_sink(self):
        raw=b''.join(x.to_bytes(8,'little') for x in (1,3,5,1,3,7))
        reader=Reader(io.BytesIO(b'preROOTpost'),11)
        reader.wire_digest=hashlib.sha256()
        self.assertEqual(reader.read(7),b'preROOT')
        header=struct.pack('<8sQQQ',b'OPLCPG01',1,1,len(raw))
        reader.wire_digest.update(header)
        observed=[]
        def sink(data):
            observed.append(data)
            reader.wire_digest.update(data)
        digest=digest_compact_checkpoint([('a',2),('b',1)],[(3,7),(2,1)],
            {'a':(128,384),'b':(14,)},{'a':(8,24),'b':(20,)},48,value_bits=64,byte_sink=sink)
        self.assertEqual(b''.join(observed),raw)
        self.assertEqual(digest,hashlib.sha256(raw).hexdigest())
        self.assertEqual(reader.read(4),b'post')
        reader.finish(hashlib.sha256(b'preROOTpost').hexdigest())
        self.assertEqual(reader.wire_digest.digest(),hashlib.sha256(b'preROOT'+header+raw+b'post').digest())
        self.assertNotEqual(reader.wire_digest.digest(),hashlib.sha256(b'pre'+header+raw+b'ROOTpost').digest())

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

    def test_report_keeps_every_epoch_and_last_two_file_roles(self):
        digests=tuple(str(i)*64 for i in range(1,5))
        for count,roles in ((3,('committed.bin','staged.bin')),(4,('staged.bin','committed.bin'))):
            with self.subTest(count=count):
                epochs,images=bounded_checkpoint_records(digests[:count],4_853_840)
                self.assertEqual([(x['sweep'],x['slot'],x['sha256']) for x in epochs],
                                 [(i,i%2,digest) for i,digest in enumerate(digests[:count],1)])
                self.assertEqual([(x['name'],x['sha256']) for x in images],
                                 list(zip(roles,digests[count-2:count],strict=True)))


    def test_quality32_rejects_bad_modes_and_digest_counts_before_read(self):
        d='1'*64
        cases=(dict(proof9_quality32=True),
               dict(proof9_quality32=True,paired=True,rank_sets=True,checkpoint_digests=(d,)*31),
               dict(proof9_quality32=True,paired=True,rank_sets=True,checkpoint_digests=(d,)*31+('A'*64,)),
               dict(proof9_quality32=True,proof9_t4=True,paired=True,rank_sets=True,checkpoint_digests=(d,)*32),
               dict(proof9_quality32=True,ten_card=True,paired=True,rank_sets=True,checkpoint_digests=(d,)*32),
               *(dict(proof9_quality32=True,paired=True,rank_sets=True,checkpoint_digests=(d,)*32,**{flag:True})
                 for flag in ('row_batched','phase_payload','indexed_cache')))
        with patch('scripts.verify_virtual_dyadic_training.authenticated_reader',side_effect=AssertionError('opened')):
            for case in cases:
                with self.subTest(case=case), self.assertRaises(ValueError):
                    replay('absent','0'*64,**case)

    def test_quality32_epoch_roles_and_contract(self):
        digests=tuple(format(i,'064x') for i in range(1,33))
        epochs,images=bounded_checkpoint_records(digests,4_853_840)
        self.assertEqual(len(epochs),32)
        self.assertEqual([(x['sweep'],x['slot'],x['sha256']) for x in epochs],
                         [(i,i%2,d) for i,d in enumerate(digests,1)])
        self.assertEqual([(x['name'],x['sha256']) for x in images],
                         [('staged.bin',digests[-2]),('committed.bin',digests[-1])])


if __name__=='__main__':
    unittest.main()
