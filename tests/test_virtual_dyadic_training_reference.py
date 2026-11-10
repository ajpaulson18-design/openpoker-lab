"""Cross-check the literal replay against the accepted frozen q-free oracle."""
import hashlib
import json
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fractions import Fraction
from types import SimpleNamespace as NS
from zipfile import ZipFile

from tests.virtual_dyadic_training_reference import D, Q, Fixture
from tests.virtual_frozen_reference_artifact import artifact_allowance, read_reference
from tests.virtual_frozen_update_reference import scaled_proof9_ranges


ROOT = Path(__file__).resolve().parents[1]


class IndependentDyadicTrainingReferenceTests(unittest.TestCase):
    def test_linear_averaging_uses_one_based_weights_and_own_reach(self):
        # Two distinct supplied policies, with a second decision reached only
        # through the first root action. All arithmetic is independently exact.
        from tests.virtual_dyadic_training_reference import World
        f=Fixture.__new__(Fixture)
        edge=lambda child,token:NS(child=child,token=token)
        f.nodes=[NS(phase='decision',state=NS(player=0),edges=(edge(1,'a'),edge(3,'b'))),
                 NS(phase='decision',state=NS(player=0),edges=(edge(2,'x'),edge(3,'y'))),
                 NS(phase='showdown'),NS(phase='showdown')]
        f.template=NS(root=0)
        f.menus={(0,0,()):('a','b'),(0,0,('a',)):('x','y')}
        f.worlds=(World((0,0),(),Fraction(1),1),)
        f.stakes={2:Fraction(1),3:Fraction(-1)}
        f.denominator=Q*Q
        f.value_bits=644
        first={(0,0,()):(Q,0),(0,0,('a',)):(Q,0)}
        second={(0,0,()):(0,Q),(0,0,('a',)):(0,Q)}
        r1,a1,_=f.sweep(first,average_weight=1)
        r2,a2,_=f.sweep(second,r1,a1,average_weight=2)
        equal_r,equal_a,_=f.sweep(second,r1,a1,average_weight=1)
        self.assertEqual(r2,equal_r)
        self.assertEqual(a2[(0,0,())],(Q*Q,2*Q*Q))
        self.assertEqual(a2[(0,0,('a',))],(Q*Q,0))
        self.assertEqual(equal_a[(0,0,())],(Q*Q,Q*Q))
        grid=f.grid(a2,average=True)
        self.assertEqual(grid[(0,0,())],(Q//3,Q-Q//3))
        self.assertEqual(grid[(0,0,('a',))],(Q,0))
        zero={(0,0,()):(0,Q),(0,0,('a',)):(Q,0)}
        _,zero_a,_=f.sweep(zero,average_weight=32)
        self.assertEqual(zero_a[(0,0,('a',))],(0,0))
        self.assertEqual(f.grid(zero_a,average=True)[(0,0,('a',))],(Q//2,Q//2))
        for invalid in (True,False,0,33,1.0):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                f.sweep(first,average_weight=invalid)

    def test_linear_checkpoint_hashes_and_framed_wire_reconstruction(self):
        from scripts.verify_virtual_dyadic_training import digest_compact_checkpoint
        ordered=[('row',2)]
        scales=[(4,3)]
        wire=hashlib.sha256()
        literal=bytearray()
        for t in range(1,33):
            # Independent little-endian layout: averages first, then regrets.
            avg={'row':(16*t*(t+1)//2,16*3*t)}
            regrets={'row':(8*t,16*t)}
            image=b''.join(x.to_bytes(width,'little') for x,width in
                ((avg['row'][0]>>4,80),(avg['row'][1]>>4,80),
                 (regrets['row'][0]>>3,88),(regrets['row'][1]>>3,88)))
            frame=struct.pack('<8sQQQ',b'OPLCPG01',t,t%2,len(image))
            literal.extend(frame+image)
            wire.update(frame)
            digest=digest_compact_checkpoint(ordered,scales,regrets,avg,len(image),
                                               value_bits=644,byte_sink=wire.update)
            self.assertEqual(digest,hashlib.sha256(image).hexdigest())
        self.assertEqual(wire.digest(),hashlib.sha256(literal).digest())
        with self.assertRaises(ValueError):
            digest_compact_checkpoint(ordered,scales,regrets,{'row':(1,0)},336,value_bits=644)

    def test_linear_profile_rejects_incompatible_lifecycles_before_reading(self):
        from scripts.verify_virtual_dyadic_training import replay
        for flag in ('proof9_t3','proof9_t4','proof9_quality32'):
            with self.subTest(flag=flag),self.assertRaises(ValueError):
                replay('missing','0'*64,proof9_linear32=True,**{flag:True})
        for flag in ('phase_payload','row_batched','indexed_cache'):
            with self.subTest(flag=flag),self.assertRaises(ValueError):
                replay('missing','0'*64,proof9_linear32=True,**{flag:True})
        for flag in ('ten_card',):
            with self.subTest(flag=flag),self.assertRaises(ValueError):
                replay('missing','0'*64,paired=True,rank_sets=True,
                       checkpoint_digests=['0'*64]*32,proof9_linear32=True,**{flag:True})
        for flag in (1,None):
            with self.subTest(flag=flag),self.assertRaises(ValueError):
                replay('missing','0'*64,proof9_linear32=flag)

    def test_exact_first_sweep_matches_accepted_frozen_profile(self):
        directory=ROOT/'benchmarks/results/virtual-frozen-complete-v1'
        manifest=json.loads((directory/'manifest.json').read_bytes())
        archive=next(x for x in manifest['archives'] if x['path']=='producer.zip')
        path=directory/archive['path']
        self.assertEqual(path.stat().st_size,archive['bytes'])
        self.assertLess(path.stat().st_size,10<<20)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),archive['sha256'])
        with ZipFile(path) as zipped, TemporaryDirectory(prefix='opl-dyadic-oracle-') as temp:
            member=zipped.getinfo('study/expected.jsonl')
            self.assertEqual(member.file_size,5_470_756)
            raw=zipped.read(member)
            file=Path(temp)/'expected.jsonl';file.write_bytes(raw)
            frozen=read_reference(file,byte_limit=artifact_allowance('expected',24420,58164)['bytes'])
        self.assertEqual(frozen.receipt['body_sha256'],'2152c9136aef5b4d84a1d1559b3168968425c95bdd5203148ddc941a66e49ebd')
        fixture=Fixture()
        self.assertEqual(fixture.terminal_completion_counts(),(18180,22168))
        ranges=scaled_proof9_ranges()
        index=[{hand:i for i,(hand,_) in enumerate(side)} for side in ranges]
        rows={(row.actor,index[row.actor][row.hand_ids],row.history):row for row in frozen.rows.values()}
        self.assertEqual(rows.keys(),fixture.menus.keys())
        policy={}
        for key,row in rows.items():
            self.assertEqual(row.actions,fixture.menus[key])
            policy[key]=tuple(0 if e==-1 else Q>>e for e in row.action_exponents)
        regrets,averages,root=fixture.sweep(policy)
        self.assertTrue(any(v for row in regrets.values() for v in row))
        for key,row in rows.items():
            r=tuple(max(0,value)*D for value in row.regret_masses)
            a=tuple(value*D for value in row.average_action_masses)
            self.assertEqual(regrets[key],r,key)
            self.assertEqual(averages[key],a,key)
        quality=fixture.quality(policy)
        self.assertEqual(quality['profile_sb'],root)
        self.assertGreater(quality['exploitability'],0)


if __name__=='__main__':
    unittest.main()
