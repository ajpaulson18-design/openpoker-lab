"""Authenticated native controls with independent full-history/menu replay."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests.test_native_exact_reach import authenticate, sha
from tests.virtual_dyadic_training_reference import Fixture
from tests.virtual_frozen_run_control import run_bounded_child
from tests.virtual_frozen_value_reference import _reveal_token

ROOT=Path(__file__).resolve().parents[1]
ENV='OPENPOKER_NATIVE_STRATEGY_CATALOG_EXE'
OUT='OPENPOKER_NATIVE_STRATEGY_CATALOG_DIR'
TARGET='virtual-strategy-catalog-controls'
GUARDS=('default-row-id-poisons','foreign-row-id-poisons','foreign-history-poisons',
        'unknown-holding-poisons','wrong-actor-poisons','changed-menu-poisons',
        'row-cap-poisons','metadata-one-short','work-one-short','view-read-cap-poisons',
        'zero-block-limit','holding-limit','work-limit')


def decode_ordinal(fixture,ordinal,actor,holding):
    """Decode ordinal through independent literal occurrence paths, including unsupported hands."""
    occurrence,length=ordinal>>33,(ordinal>>30)&7
    packed=ordinal&((1<<30)-1)
    if occurrence>=len(fixture.paths) or length not in (0,3,4,5):raise AssertionError('ordinal path shape')
    if packed>> (6*length):raise AssertionError('ordinal unused card bits')
    board=tuple((packed>>(6*i))&63 for i in range(length))
    if len(set(board))!=length or not set(board)<=set(fixture.deck):raise AssertionError('ordinal board')
    if length>=3 and tuple(sorted(board[:3]))!=board[:3]:raise AssertionError('ordinal flop order')
    node_id,_,_,street,_=fixture.paths[occurrence]
    if street!=length:raise AssertionError('ordinal board street')
    tokens=[]
    while occurrence:
        _,parent,token,visible,_=fixture.paths[occurrence]
        tokens.append(token if token is not None else _reveal_token(board,visible))
        occurrence=parent
    node=fixture.nodes[node_id]
    if actor!=node.state.player:raise AssertionError('ordinal actor')
    return node_id,tuple(reversed(tokens)),tuple(edge.token for edge in node.edges)


@unittest.skipUnless(os.environ.get(ENV),'explicit source-built catalog controls required')
class NativeStrategyCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe=Path(os.environ[ENV]).resolve()
        cls.identity=authenticate(cls.exe,ROOT,TARGET)
        cls.source_before={name:sha(ROOT/name) for name in cls.identity[1]['source_sha256']}
        target=os.environ.get(OUT)
        if target is None:
            temp=TemporaryDirectory(dir=ROOT.parent);cls.addClassCleanup(temp.cleanup)
            target=Path(temp.name)/'catalog-controls'
        cls.output=Path(target);cls.output.mkdir(parents=True,exist_ok=False)
        command=[str(cls.exe)]
        (cls.output/'command.json').write_text(json.dumps(command)+'\n')
        cls.observed=run_bounded_child(command,b'',cls.output/'process',stdout_limit=65536,timeout=180)
        cls.stdout=(cls.output/'process'/'stdout.bin').read_bytes()
        cls.stderr=(cls.output/'process'/'stderr.bin').read_bytes()
        (cls.output/'native-build-manifest.json').write_bytes(cls.identity[0])
        (cls.output/'native-identity.json').write_text(json.dumps({
            'manifest_sha256':__import__('hashlib').sha256(cls.identity[0]).hexdigest(),
            'executable_sha256':cls.identity[1]['executable_sha256']})+'\n')

    def test_authenticated_process_and_resource_guards(self):
        self.assertEqual((self.observed['status'],self.observed['returncode'],
                          self.observed['actual_exit_observed']),('exited',0,True))
        self.assertFalse(self.stderr)
        lines=self.stdout.decode('ascii').splitlines()
        self.assertEqual(lines[0],'VIRTUAL_STRATEGY_CATALOG_V1')
        self.assertEqual([line.split()[1] for line in lines if line.startswith('GUARD ')],list(GUARDS))
        self.assertEqual(lines[-1],'END')
        self.assertEqual(authenticate(self.exe,ROOT,TARGET),self.identity)
        for name,digest in self.source_before.items():self.assertEqual(sha(ROOT/name),digest)

    def test_native_rows_match_independent_full_history_fixture(self):
        fixture=Fixture()
        rows={}
        for line in self.stdout.decode('ascii').splitlines():
            if not line.startswith('ROW '):continue
            _,label,ordinal,actor,holding,source,count,*actions=line.split()
            ordinal,actor,holding,source,count=map(int,(ordinal,actor,holding,source,count))
            self.assertEqual(len(actions),count)
            node_id,history,menu=decode_ordinal(fixture,ordinal,actor,holding)
            self.assertEqual(node_id,source)
            self.assertEqual(tuple(actions),menu)
            rows[label]=(ordinal,actor,holding,source,tuple(actions),(actor,holding,history))
        self.assertEqual(set(rows),{'root-first','root-last','after-action','flop-a','flop-b'})
        self.assertEqual(rows['root-first'][:2],rows['root-last'][:2])
        self.assertEqual((rows['root-first'][2],rows['root-last'][2]),(0,1325))
        self.assertNotEqual(rows['after-action'][0],rows['root-first'][0])
        self.assertNotEqual(rows['flop-a'][0],rows['flop-b'][0])
        self.assertEqual(rows['flop-a'][3],rows['flop-b'][3])
        self.assertEqual(rows['flop-a'][4],rows['flop-b'][4])

    def test_receipt_counts_only_seen_rows_and_shared_source_menus(self):
        line=next(line for line in self.stdout.decode('ascii').splitlines() if line.startswith('RECEIPT '))
        _,work,lookups,blocks,rows,slots,menus,entries,payload=line.split()
        work,lookups,blocks,rows,slots,menus,entries,payload=map(int,
            (work,lookups,blocks,rows,slots,menus,entries,payload))
        self.assertEqual((blocks,rows,menus),(4,5,3))
        expected_slots=sum(len(row[4]) for row in self._rows().values())
        self.assertEqual(slots,expected_slots)
        self.assertEqual(lookups,16)  # resolves plus emitted borrowed views
        self.assertGreater(work,0)
        self.assertLessEqual(work,75_000_000)
        self.assertLessEqual(entries,2_000_000)
        self.assertEqual(payload,entries*64)
        self.assertLessEqual(payload,1<<30)

    def _rows(self):
        result={}
        for line in self.stdout.decode('ascii').splitlines():
            if line.startswith('ROW '):
                _,label,ordinal,actor,holding,source,count,*actions=line.split()
                result[label]=(int(ordinal),int(actor),int(holding),int(source),tuple(actions))
        return result


if __name__=='__main__':unittest.main()
