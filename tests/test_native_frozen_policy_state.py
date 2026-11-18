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

ROOT=Path(__file__).resolve().parents[1]
EXE_ENV='OPENPOKER_NATIVE_FROZEN_POLICY_STATE_EXE'
OUTPUT_ENV='OPENPOKER_NATIVE_FROZEN_POLICY_STATE_CONTROL_DIR'
GUARDS=('unsealed_read','incomplete','duplicate','out_of_order','wrong_history','foreign_history',
        'wrong_holding','wrong_menu','zero_partition','overflow_partition','read_cap','training',
        'freeze','commit','export','reimport','zero_reads','overflow_reads','lifetime_one_short')


def encode_snapshot(fixture,policy):
    fixture._probabilities(policy)
    ordered=tuple(fixture.ordered_rows())
    if len(ordered)!=24420 or len(set(ordered))!=24420:raise ValueError('snapshot complete row order')
    tokens=sum(len(k[2]) for k in ordered)
    history_bytes=sum(sum(len(t.encode('ascii')) for t in k[2]) for k in ordered)
    action_bytes=sum(sum(len(t.encode('ascii')) for t in fixture.menus[k]) for k in ordered)
    data=bytearray(b'OPLFGS01'+struct.pack('<6Q',24420,58164,tokens,history_bytes,action_bytes,Q))
    layout={}
    hands=(((43,48),(32,43)),((24,37),(16,32)))
    def token(text):
        raw=text.encode('ascii')
        if not 0<len(raw)<=64:raise ValueError('snapshot token bound')
        data.extend(bytes((len(raw),)));data.extend(raw)
    for row,key in enumerate(ordered):
        actor,holding,history=key;menu=fixture.menus[key]
        first,second=hands[actor][holding]
        data.extend(struct.pack('<5Q',actor,first,second,len(history),len(menu)))
        if history and 'history' not in layout:layout['history']=len(data)
        for text in history:token(text)
        if not row:layout['menu']=len(data)
        for text in menu:token(text)
        layout['last_units']=len(data);layout['last_width']=len(menu)
        data.extend(struct.pack('<'+'Q'*len(menu),*policy[key]))
    if len(data)>8<<20:raise ValueError('snapshot byte ceiling')
    return bytes(data),ordered,layout


class SnapshotEncodingTests(unittest.TestCase):
    def test_versioned_format_uses_full_complete_history_and_ordered_menus(self):
        fixture=Fixture();data,ordered,_=encode_snapshot(fixture,fixture.grid())
        self.assertEqual(data[:8],b'OPLFGS01')
        self.assertEqual(struct.unpack_from('<6Q',data,8),(24420,58164,249662,1500675,294353,Q))
        self.assertEqual(len(data),3545022)
        self.assertEqual(set(ordered),set(fixture.menus))


@unittest.skipUnless(os.environ.get(EXE_ENV),'explicit source-built frozen policy controls required')
class NativeFrozenPolicyStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe=Path(os.environ[EXE_ENV]).resolve()
        identity=authenticate(cls.exe,ROOT,'virtual-frozen-policy-state-controls')
        if identity[1]['scope']!='Frozen Q52 policy import/read conformance only; no update, training, solver or capacity acceptance.':
            raise AssertionError('frozen policy build scope differs')
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
            observed=run_bounded_child(command,b'',directory,stdout_limit=2_100_000,timeout=180)
            if data is not None:
                if sha(path)!=before:raise AssertionError('snapshot input drift')
                (directory/'input-identity.json').write_text(json.dumps({'sha256':before,'bytes':len(data)})+'\n')
            cls.cases[name]=(observed,(directory/'stdout.bin').read_bytes(),(directory/'stderr.bin').read_bytes())
        run('guards')
        cls.profiles['uniform']=cls.fixture.grid()
        cls.profiles['zero-skew']={}
        for i,key in enumerate(sorted(cls.fixture.menus)):
            count=len(cls.fixture.menus[key]);units=[0 if i%2 else 1]*count
            units[i%count]=Q-sum(units)+units[i%count]
            cls.profiles['zero-skew'][key]=tuple(units)
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
                self.assertEqual(stdout[:8],b'OPLFGV01')
                rows,slots,work,entries,payload,history_work,state_work=struct.unpack_from('<7Q',stdout,8)
                self.assertEqual((rows,slots),(24420,58164))
                self.assertLessEqual(int(work),500_000_000);self.assertLessEqual(int(entries),2_000_000)
                self.assertLessEqual(int(payload),1<<30);self.assertLessEqual(int(history_work),42_000_000)
                self.assertLessEqual(int(state_work),75_000_000)
                self.assertEqual(len(stdout),1442320);offset=0;position=64
                for row,key in enumerate(self.ordered):
                    actor,holding,ordinal,slot,count=struct.unpack_from('<5Q',stdout,position);position+=40
                    self.assertEqual(count,len(self.fixture.menus[key]))
                    units=struct.unpack_from('<'+'Q'*count,stdout,position);position+=8*count
                    self.assertEqual((int(actor),int(holding),int(slot),int(count)),
                                     (key[0],key[1],offset,len(self.fixture.menus[key])))
                    self.assertEqual(self.fixture.compact_key(int(ordinal),int(actor),int(holding)),key)
                    self.assertEqual(tuple(map(int,units)),policy[key]);offset+=int(count)
                footer=struct.unpack_from('<18Q',stdout,position);position+=144
                rows,slots,actual,actual_history,actual_state=footer[:5]
                template_work,parent_work,chance_work,input_bytes,output_bytes=footer[5:10]
                self.assertEqual(footer[10:15],(0,0,0,0,0))
                self.assertEqual(footer[15:],(24420,24420,1))
                self.assertEqual(output_bytes,len(stdout));self.assertEqual(input_bytes,3545022)
                self.assertEqual(actual,template_work+parent_work+chance_work+actual_history+actual_state+16*input_bytes+16*output_bytes)
                self.assertEqual(position,len(stdout))
                self.assertEqual((int(rows),int(slots),offset),(24420,58164,58164))
                self.assertLessEqual(int(actual),int(work));self.assertLessEqual(int(actual_history),int(history_work))
                self.assertLessEqual(int(actual_state),int(state_work))

    def test_bad_complete_inputs_never_expose_partial_policy(self):
        for name in ('late-zero-partition','foreign-holding','reordered-menu','foreign-history-token','truncated','incomplete-header'):
            with self.subTest(case=name):
                stdout,stderr=self.exited(name,2);self.assertFalse(stdout);self.assertTrue(stderr)


if __name__=='__main__':unittest.main()
