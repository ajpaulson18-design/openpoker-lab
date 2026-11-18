"""Independent full-history Q52 import conformance; no sampled learner."""
import hashlib
import json
import os
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest

from tests.test_native_exact_reach import authenticate,sha
from tests.virtual_dyadic_training_reference import Fixture,Q
from tests.virtual_frozen_run_control import run_bounded_child
from tests.virtual_frozen_policy_input_reference import decode_snapshot,encode_snapshot,profile,verify_snapshot_wire
from scripts.replay_native_frozen_policy_state import capture_sources,save_sources

ROOT=Path(__file__).resolve().parents[1]
EXE_ENV='OPENPOKER_NATIVE_FROZEN_POLICY_STATE_EXE'
OUTPUT_ENV='OPENPOKER_NATIVE_FROZEN_POLICY_STATE_CONTROL_DIR'
GUARDS=('unsealed_read','incomplete','duplicate','out_of_order','wrong_history','foreign_history',
        'wrong_holding','wrong_menu','zero_partition','overflow_partition','read_cap','training',
        'freeze','commit','export','reimport','zero_reads','overflow_reads','lifetime_one_short')


class SnapshotEncodingTests(unittest.TestCase):
    def test_versioned_format_uses_full_complete_history_and_ordered_menus(self):
        fixture=Fixture();data,ordered,_=encode_snapshot(fixture,fixture.grid())
        self.assertEqual(data[:8],b'OPLFGS01')
        self.assertEqual(struct.unpack_from('<6Q',data,8),(24420,58164,249662,1500675,294353,Q))
        self.assertEqual(len(data),3545022)
        self.assertEqual(set(ordered),set(fixture.menus))
        self.assertEqual(decode_snapshot(fixture,data),fixture.grid())
        for changed in (data[:-1],data+b'\0',data[:56]+b'\xff'*8+data[64:]):
            with self.assertRaises(ValueError):decode_snapshot(fixture,changed)


@unittest.skipUnless(os.environ.get(EXE_ENV),'explicit source-built frozen policy controls required')
class NativeFrozenPolicyStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe=Path(os.environ[EXE_ENV]).resolve()
        identity=authenticate(cls.exe,ROOT,'virtual-frozen-policy-state-controls')
        if identity[1]['scope']!='Frozen Q52 policy import/read conformance only; no update, training, solver or capacity acceptance.':
            raise AssertionError('frozen policy build scope differs')
        source_before=capture_sources(identity[1])
        target=os.environ.get(OUTPUT_ENV)
        if target is None:
            temporary=TemporaryDirectory(dir=ROOT.parent);cls.addClassCleanup(temporary.cleanup)
            target=Path(temporary.name)/'observed'
        cls.output=Path(target);cls.output.mkdir(parents=True,exist_ok=False)
        cls.fixture=Fixture();cls.cases={};cls.profiles={}
        def run(name,data=None):
            command=[str(cls.exe)]
            before=None
            if data is not None:
                path=cls.output/(name+'.input.bin');path.write_bytes(data)
                before=sha(path);command.append(str(path))
            directory=cls.output/name
            (cls.output/(name+'.command.json')).write_text(json.dumps(command)+'\n')
            observed=run_bounded_child(command,b'',directory,stdout_limit=2_100_000,timeout=180)
            if data is not None:
                if sha(path)!=before:raise AssertionError('snapshot input drift')
                (directory/'input-identity.json').write_text(json.dumps({'sha256':before,'bytes':len(data)})+'\n')
            cls.cases[name]=(observed,(directory/'stdout.bin').read_bytes(),(directory/'stderr.bin').read_bytes())
        run('guards')
        cls.profiles={name:profile(cls.fixture,name) for name in ('uniform','zero-skew')}
        for name,policy in cls.profiles.items():
            data,cls.ordered,layout=encode_snapshot(cls.fixture,policy);run(name,data)
        data,_,layout=encode_snapshot(cls.fixture,cls.profiles['uniform'])
        changed=bytearray(data);changed[layout['last_units']:layout['last_units']+8*layout['last_width']]=b'\0'*(8*layout['last_width'])
        run('late-zero-partition',changed)
        changed=bytearray(data);struct.pack_into('<Q',changed,56+8,0);run('foreign-holding',changed)
        changed=bytearray(data);changed[layout['menu']+1:layout['menu']+5]=b'call';run('reordered-menu',changed)
        changed=bytearray(data);changed[layout['history']+1]=ord('x');run('foreign-history-token',changed)
        run('truncated',data[:-1])
        changed=bytearray(data);struct.pack_into('<Q',changed,8,24419);run('incomplete-header',changed)
        if sha(cls.exe)!=identity[1]['executable_sha256'] or authenticate(cls.exe,ROOT,'virtual-frozen-policy-state-controls')!=identity:
            raise AssertionError('frozen policy executable/source drift')
        (cls.output/'native-identity.json').write_text(json.dumps({'manifest_sha256':hashlib.sha256(identity[0]).hexdigest(),
            'executable_sha256':identity[1]['executable_sha256']})+'\n')
        if capture_sources(identity[1])!=source_before:raise AssertionError('introduced source drift')
        (cls.output/'native-build-manifest.json').write_bytes(identity[0])
        save_sources(cls.output,source_before)

    def exited(self,name,code):
        observed,stdout,stderr=self.cases[name]
        self.assertEqual((observed['status'],observed['returncode'],observed['actual_exit_observed']),('exited',code,True))
        return stdout,stderr

    def test_compiled_lifetime_guards_and_independent_small_row_keys(self):
        stdout,stderr=self.exited('guards',0);self.assertFalse(stderr)
        lines=stdout.decode('ascii').splitlines();self.assertEqual(lines[0],'FROZEN_POLICY_STATE_V1')
        self.assertEqual([line.split()[1] for line in lines if line.startswith('GUARD ')],list(GUARDS))
        self.assertEqual([line.split()[1] for line in lines if line.startswith('HISTORY_GUARD ')],
            ['unused_root','foreign_path','bad_length','terminal_path','duplicate_card','foreign_card','unsorted_flop','unused_flop'])
        root=self.fixture.nodes[self.fixture.template.root]
        histories=((),(),(root.edges[1].token,),(root.edges[2].token,))
        offset=0
        for index,line in enumerate(line for line in lines if line.startswith('ROW ')):
            _,row,actor,holding,ordinal,position,count,*values=line.split()
            actor,holding,count=int(actor),int(holding),int(count)
            key=self.fixture.compact_key(int(ordinal),actor,holding)
            self.assertEqual(key,((0 if index<2 else 1),(1 if index==1 else 0),histories[index]))
            self.assertEqual((int(row),int(position),count),(index,offset,len(self.fixture.menus[key])))
            expected=[Q-count+1]+[1]*(count-1) if index==0 else ([0,Q]+[0]*(count-2) if index==1 else
                [Q//count+int(a<Q%count) for a in range(count)])
            self.assertEqual(list(map(int,values)),expected);offset+=count
        _,rows,slots,import_work,read_work,history_work,actual,actual_history=next(line.split() for line in lines if line.startswith('READONLY '))
        self.assertEqual((int(rows),int(slots)),(4,13))
        self.assertEqual(int(import_work),1088+130*4+258*13)
        self.assertEqual(int(history_work),56*4+16*13+40*4)
        self.assertLessEqual(int(actual),int(import_work)+int(read_work));self.assertLessEqual(int(actual_history),int(history_work))
        self.assertEqual(lines[-1],'END')

    def test_complete_imports_match_every_original_holding_history_and_grid_unit(self):
        for name,policy in self.profiles.items():
            with self.subTest(profile=name):
                stdout,stderr=self.exited(name,0);self.assertFalse(stderr)
                result=verify_snapshot_wire(self.fixture,policy,stdout)
                self.assertEqual((result['rows'],result['slots']),(24420,58164))
                self.assertTrue(result['all_policy_units_exact'])

    def test_saved_wire_corruptions_are_detected_without_native_calls(self):
        original=self.cases['uniform'][1]
        for name in ('unit','holding','ordinal','scope','truncated'):
            changed=bytearray(original)
            if name=='unit':struct.pack_into('<Q',changed,104,struct.unpack_from('<Q',changed,104)[0]+1)
            elif name=='holding':struct.pack_into('<Q',changed,72,1)
            elif name=='ordinal':struct.pack_into('<Q',changed,80,1)
            elif name=='scope':struct.pack_into('<Q',changed,len(changed)-144+80,1)
            else:changed=changed[:-1]
            with self.subTest(case=name),self.assertRaises(ValueError):
                verify_snapshot_wire(self.fixture,self.profiles['uniform'],bytes(changed))

    def test_bad_complete_inputs_never_expose_partial_policy(self):
        for name in ('late-zero-partition','foreign-holding','reordered-menu','foreign-history-token','truncated','incomplete-header'):
            with self.subTest(case=name):
                stdout,stderr=self.exited(name,2);self.assertFalse(stdout);self.assertTrue(stderr)


if __name__=='__main__':unittest.main()
