"""Source-frozen per-board raw candidate versus the independent Q52 oracle."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts.replay_native_frozen_policy_state import ORACLE_SOURCES
from tests.test_native_exact_reach import authenticate,sha
from tests.virtual_frozen_run_control import run_bounded_child
from tests.virtual_dyadic_training_reference import Fixture
from tests.virtual_frozen_policy_input_reference import encode_snapshot,profile
from tests.virtual_grid_update_reference import build_sampled_reference_context
from tests.virtual_native_grid_raw_reference import verify_raw_wire

ROOT=Path(__file__).resolve().parents[1]
ENV='OPENPOKER_NATIVE_FROZEN_GRID_RAW_EXE';OUT='OPENPOKER_NATIVE_FROZEN_GRID_RAW_DIR'
SCOPE='Fixed-policy Q52 per-board raw values/regrets/averages study only; no clipping, State update, sampled training, quality or wider capacity acceptance.'


@unittest.skipUnless(os.environ.get(ENV),'explicit source-built raw candidate required')
class NativeRawTests(unittest.TestCase):
    def test_one_positive_board_complete_rows_and_request_accounting(self):
        exe=Path(os.environ[ENV]).resolve();identity=authenticate(exe,ROOT,'virtual-frozen-grid-raw-update')
        self.assertEqual(identity[1]['scope'],SCOPE)
        names=sorted(set(identity[1]['source_sha256'])|set(ORACLE_SOURCES)|{
            'scripts/replay_native_frozen_policy_state.py','tests/virtual_frozen_policy_input_reference.py',
            'tests/virtual_frozen_grid_preflight_reference.py','tests/virtual_frozen_grid_envelope_reference.py',
            'tests/virtual_grid_update_reference.py','tests/virtual_frozen_sample_reference.py',
            'tests/virtual_native_grid_raw_reference.py','tests/test_native_frozen_grid_raw.py'})
        self.assertLessEqual(len(names),128)
        self.assertFalse(subprocess.check_output(['git','status','--porcelain','--untracked-files=all','--',*names],cwd=ROOT))
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        source={n:(ROOT/n).read_bytes() for n in names}
        self.assertLessEqual(sum(map(len,source.values())),64<<20)
        fixture=Fixture();context=build_sampled_reference_context();policy=profile(fixture,'uniform')
        board=fixture.worlds[0].board;law='uniform'
        data,_,_=encode_snapshot(fixture,policy)
        with TemporaryDirectory(dir=ROOT.parent) as temporary:
            directory=Path(os.environ.get(OUT,str(Path(temporary)/'observed')));directory.mkdir(parents=True,exist_ok=False)
            path=directory/'snapshot.input.bin';path.write_bytes(data);digest=sha(path)
            command=[str(exe),str(path),law,*map(str,board)]
            (directory/'command.json').write_text(json.dumps(command)+'\n')
            child=directory/'candidate'
            observed=run_bounded_child(command,b'',child,stdout_limit=2_100_000,timeout=180)
            for name,raw in source.items():
                self.assertEqual((ROOT/name).read_bytes(),raw)
                target=directory/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            (directory/'source-identity.json').write_text(json.dumps({'head':head,'raw_sha256':{n:sha256(raw).hexdigest() for n,raw in source.items()},
                'python_version':sys.version,'python_executable_sha256':sha256(Path(sys.executable).read_bytes()).hexdigest()},indent=2)+'\n')
            (directory/'native-build-manifest.json').write_bytes(identity[0])
            (directory/'input-identity.json').write_text(json.dumps({'bytes':len(data),'sha256':digest})+'\n')
            self.assertEqual(sha(path),digest)
            self.assertEqual(authenticate(exe,ROOT,'virtual-frozen-grid-raw-update'),identity)
            self.assertEqual((observed['status'],observed['returncode'],observed['actual_exit_observed']),('exited',0,True))
            self.assertEqual((child/'stderr.bin').read_bytes(),b'')
            result=verify_raw_wire(fixture,context,policy,board,law,(child/'stdout.bin').read_bytes())
            (directory/'independent-rows.json').write_text(json.dumps(result,indent=2)+'\n')
            self.assertEqual(result['status'],'all-raw-rows-exact')


if __name__=='__main__':unittest.main()
