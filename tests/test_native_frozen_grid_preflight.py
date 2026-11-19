"""Rank-free independent geometry checks for a provisional architecture envelope."""
import os
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from tests.test_native_exact_reach import authenticate
from tests.virtual_frozen_run_control import run_bounded_child
from tests.virtual_frozen_grid_preflight_reference import boards,census,geometry
from scripts.replay_native_frozen_policy_state import ORACLE_SOURCES

ROOT=Path(__file__).resolve().parents[1]
ENV='OPENPOKER_NATIVE_FROZEN_GRID_PREFLIGHT_EXE'
OUT='OPENPOKER_NATIVE_FROZEN_GRID_PREFLIGHT_DIR'


class IndependentGeometryTests(unittest.TestCase):
    def test_complete_support_and_correct_mixture_exponent(self):
        g=geometry()
        self.assertEqual((g['literal_occurrences'],g['max_actor_decisions'],g['max_total_decisions']),(1105,(6,7),12))
        self.assertEqual(g['max_opponent_past_plus_all_future_decisions_excluding_current'],11)
        self.assertEqual(g['max_opponent_past_plus_target_future_excluding_current'],7)
        cases=[census(board) for board in boards()]
        self.assertEqual(len(cases),2520)
        self.assertEqual(sum(x['full_target_positive'] for x in cases),60)
        self.assertEqual(sum(x['zero_full_target_with_positive_prefix'] for x in cases),2460)
        self.assertEqual((sum(x['supported_rows'] for x in cases),sum(x['supported_action_slots'] for x in cases)),(107080,267540))


@unittest.skipUnless(os.environ.get(ENV),'explicit source-built architecture preflight required')
class NativeEnvelopeTests(unittest.TestCase):
    def test_all_outcomes_have_independent_geometry_and_no_update_admission(self):
        exe=Path(os.environ[ENV]).resolve();identity=authenticate(exe,ROOT,'virtual-frozen-grid-update-preflight')
        self.assertEqual(identity[1]['scope'],'Provisional frozen Q52 raw-update architecture envelope only; no policy import, ranking, contraction, update, training or capacity admission.')
        names=sorted(set(identity[1]['source_sha256'])|set(ORACLE_SOURCES)|{
            'scripts/replay_native_frozen_policy_state.py','tests/test_native_frozen_grid_preflight.py',
            'tests/virtual_frozen_grid_preflight_reference.py'})
        self.assertLessEqual(len(names),128)
        self.assertFalse(subprocess.check_output(['git','status','--porcelain','--untracked-files=all','--',*names],cwd=ROOT))
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        source={name:(ROOT/name).read_bytes() for name in names}
        self.assertLessEqual(sum(map(len,source.values())),64<<20)
        raw_hashes={name:hashlib.sha256(raw).hexdigest() for name,raw in source.items()}
        tree={}
        for line in subprocess.check_output(['git','ls-tree','-r',head],cwd=ROOT,text=True).splitlines():
            metadata,name=line.split('\t',1)
            if name in names:tree[name]=metadata.split()[2]
        self.assertEqual(set(tree),set(names))
        with TemporaryDirectory(dir=ROOT.parent) as temporary:
            directory=Path(os.environ.get(OUT,str(Path(temporary)/'observed')))
            observed=run_bounded_child([str(exe)],b'',directory,stdout_limit=2_100_000,timeout=180)
            for name,raw in source.items():
                self.assertEqual((ROOT/name).read_bytes(),raw)
                path=directory/'source'/name;path.parent.mkdir(parents=True,exist_ok=True)
                with path.open('xb') as output:output.write(raw)
            (directory/'source-identity.json').write_text(json.dumps({'head':head,'raw_sha256':raw_hashes,'committed_blobs':tree,
                'python_version':sys.version,'python_executable_sha256':hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()},indent=2)+'\n')
            (directory/'native-build-manifest.json').write_bytes(identity[0])
            (directory/'command.json').write_text(json.dumps([str(exe)])+'\n')
            self.assertEqual((observed['status'],observed['returncode'],observed['actual_exit_observed']),('exited',0,True))
            self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
            lines=(directory/'stdout.bin').read_text(encoding='ascii').splitlines()
        self.assertEqual(lines[0],'FROZEN_GRID_ENVELOPE_V1')
        g=geometry();phases=g['by_street'].values()
        expected=(1105,sum(x['decision_action_slots'] for x in phases),sum(x['reveals'] for x in phases),
                  sum(x['folds'] for x in phases),sum(x['showdowns'] for x in phases),
                  sum(sum(x['decision_occurrences']) for x in phases),6,7,12,11)
        self.assertEqual(tuple(map(int,lines[1].split()[1:])),expected)
        expected_boards=iter((law,board) for board in boards() for law in (0,1))
        all_rows=all_slots=positive=0;maximum_work=maximum_output=0
        for line in lines[2:-1]:
            tag,law,*words=line.split();self.assertEqual(tag,'F')
            law=int(law);values=list(map(int,words));board=tuple(values[:5]);values=values[5:]
            self.assertEqual((law,board),next(expected_boards))
            self.assertEqual(len(values),21)
            rows,slots,reads,state,history,chance,reach,scale,mix,average,stage,walk,work,entries,payload,output,staged_payload,physical,feasible,admitted,bits=values
            independent=census(board)
            self.assertEqual((rows,slots,reads),(independent['supported_rows'],independent['supported_action_slots'],24420+2*rows))
            self.assertEqual(physical,int(independent['full_target_positive']))
            self.assertEqual((admitted,bits),(0,704))
            # These feasibility flags describe a proposed ledger. They do not
            # constitute acceptance of an unimplemented update producer.
            self.assertEqual(feasible,int(work<=500_000_000 and state+1<=75_000_000 and history<=42_000_000 and chance<=110_000_000 and
                entries<=2_000_000 and payload<=1<<30 and output<=2_100_000))
            self.assertGreater(staged_payload,0);self.assertTrue(all(x>=0 for x in (reach,scale,mix,average,stage,walk)))
            all_rows+=rows;all_slots+=slots;positive+=physical;maximum_work=max(maximum_work,work);maximum_output=max(maximum_output,output)
        self.assertEqual(next(expected_boards,None),None)
        self.assertEqual((all_rows,all_slots,positive),(2*107080,2*267540,120))
        self.assertLessEqual(maximum_work,500_000_000);self.assertLessEqual(maximum_output,2_100_000)
        self.assertEqual(lines[-1],'END 5040 0 0 0 0 0')
        self.assertEqual(authenticate(exe,ROOT,'virtual-frozen-grid-update-preflight'),identity)


if __name__=='__main__':unittest.main()
