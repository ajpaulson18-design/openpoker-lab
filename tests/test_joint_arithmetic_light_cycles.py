"""Real typed-TLS recorder, balanced synthetic costs and foreign-thread refusal."""
import json
import os
from pathlib import Path
import unittest
from tests.test_joint_cycle_reference import capture as original_capture
from tests.test_joint_arithmetic_cycles import EXTRA as ARITHMETIC_SOURCES
from tests.test_native_lazy_joint import unchanged
from tests.virtual_frozen_run_control import run_bounded_child
from tests.virtual_joint_arithmetic_cycle_reference import COUNTS,FAMILIES,grouped_sequence
from tests.virtual_joint_arithmetic_light_reference import decode

ROOT=Path(__file__).resolve().parents[1]
EXTRA=('tests/test_joint_arithmetic_light_cycles.py','tests/virtual_joint_arithmetic_light_reference.py')


def capture(executable,target,output):
    return original_capture(executable,target,output,extra=(*ARITHMETIC_SOURCES,*EXTRA))


@unittest.skipUnless(os.environ.get('OPENPOKER_NATIVE_ARITHMETIC_LIGHT_EXE'),'explicit typed-TLS native controls required')
class NativeArithmeticLightTests(unittest.TestCase):
    def test_typed_tls_all_offsets_exact_bodies_and_guards(self):
        executable=Path(os.environ['OPENPOKER_NATIVE_ARITHMETIC_LIGHT_EXE']).resolve()
        output=Path(os.environ['OPENPOKER_NATIVE_ARITHMETIC_LIGHT_DIR']).resolve();target='joint-arithmetic-light-controls'
        identity,head,source=capture(executable,target,output)
        receipt=run_bounded_child([str(executable)],b'',output/'native',stdout_limit=131072,timeout=30)
        self.assertEqual((receipt['status'],receipt['actual_exit_observed'],receipt['returncode'],receipt['failures']),('exited',True,0,[]))
        self.assertEqual((output/'native/stderr.bin').read_bytes(),b'')
        lines=(output/'native/stdout.bin').read_bytes().splitlines(keepends=True);self.assertEqual(len(lines),48)
        reports=[];bodies=(3000,5000,7000,11000)
        for offset in range(32):
            report=decode(lines[offset],offset,synthetic=True,sequence=grouped_sequence());reports.append(report)
            value=report['raw'];self.assertEqual(value['empty_pair_cycles'],[1000]*16)
            self.assertEqual(report['empirical_walk_cycles_proxy'],27918000)
            self.assertEqual(value['events'][-1][2],27918000+1000*(value['cycle_queries']-1))
            for epoch in range(2):
                for family in range(4):self.assertEqual(value['epoch_sampled_helper_cycles'][epoch][family],value['epoch_sampled_calls'][epoch][family]*(bodies[family]+1000))
            for key,changed in (('cycle_queries',372),('version',1),('observer_mode','virtual-scopes')):
                altered=dict(value);altered[key]=changed
                with self.assertRaises(ValueError):
                    decode(b'JOINT_ARITHMETIC_LIGHT_CYCLES '+json.dumps(altered).encode()+b'\n',offset,synthetic=True,sequence=grouped_sequence())
        for family,name in enumerate(FAMILIES):
            self.assertEqual(sum(r['empirical_full_helper_cycles_proxies'][name] for r in reports),32*2*COUNTS[family]*bodies[family])
        labels=('offset','lazy','missing-observer','nested-install','wrong-phase','read-context','incomplete','foreign-thread',
                'clock-failure','nonmonotone','invalid-family','foreign-tls-thread','nested-scope','double-close','abandoned')
        self.assertEqual([line.rstrip(b'\r\n') for line in lines[32:]],
                         [*(('GUARD '+name+' PASS').encode() for name in labels),b'JOINT_ARITHMETIC_LIGHT_GUARDS_V1 PASS 15'])
        unchanged(executable,target,identity,head,source)
        (output/'result.json').write_text(json.dumps({'status':'typed-tls-synthetic-recorder-exact','offsets':reports,
            'native_guards':15,'parser_mutations':96,'observed_native_calls':1,
            'scope':'Synthetic typed-TLS observer controls, including a real foreign thread. No solver CPU or acceptance claim.'},indent=2)+'\n')


if __name__=='__main__':unittest.main()
