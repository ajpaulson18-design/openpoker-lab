from pathlib import Path
from unittest.mock import patch
import tempfile,unittest,json,copy
from scripts.run_virtual_frozen_update_study import AllowanceMeter,run_complete_study,_git,validate_build_bootstrap

class ControllerGateTests(unittest.TestCase):
    def test_meter_is_cumulative_and_failure_does_not_reset(self):
        meter=AllowanceMeter({'work':10});meter.reserve('work',7)
        with self.assertRaises(ValueError):meter.reserve('work',4)
        self.assertEqual(meter.used['work'],7)
        meter.reserve('work',3)
        with self.assertRaises(ValueError):meter.reserve('unknown',1)
        with self.assertRaises(ValueError):meter.reserve('work',-1)
    def test_head_mismatch_precedes_claim_or_any_child(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd().parent) as temp:
            output=Path(temp)/'attempt'
            with patch('scripts.run_virtual_frozen_update_study.run_bounded_child',side_effect=AssertionError('child entered')):
                with self.assertRaisesRegex(ValueError,'HEAD'):run_complete_study(output,'0'*40)
            self.assertFalse(output.exists())
    def test_source_gate_failure_retains_first_attempt_and_blocks_retry(self):
        head=_git(Path.cwd(),['rev-parse','HEAD']).decode().strip()
        with tempfile.TemporaryDirectory(dir=Path.cwd().parent) as temp:
            output=Path(temp)/'attempt'
            with patch('scripts.run_virtual_frozen_update_study.capture_source',side_effect=ValueError('source gate witness')):
                with patch('scripts.run_virtual_frozen_update_study.run_bounded_child',side_effect=AssertionError('child entered')), patch('scripts.run_virtual_frozen_update_study.require_source_bootstrap',return_value={}):
                    with self.assertRaisesRegex(ValueError,'source gate witness'):run_complete_study(output,head)
                    with self.assertRaises(FileExistsError):run_complete_study(output,head)
            receipt=json.loads((output/'terminal.json').read_bytes())
            self.assertEqual(receipt['status'],'failed')
            self.assertEqual(receipt['receipt']['native_eval_attempts'],0)
    def test_plain_python_entry_rejects_before_claim(self):
        head=_git(Path.cwd(),['rev-parse','HEAD']).decode().strip()
        with tempfile.TemporaryDirectory(dir=Path.cwd().parent) as temp:
            output=Path(temp)/'unsafe'
            with self.assertRaisesRegex(ValueError,'source-only bootstrap required'):
                run_complete_study(output,head)
            self.assertFalse(output.exists())
    def test_build_bootstrap_requires_exact_compiled_bytes_and_runtime(self):
        names=['scripts/run_virtual_frozen_source_only.py','scripts/build_native_exact_four_street.py']
        source={'files':{name:{'raw_sha256':'a'*64} for name in names}}
        parent={'root':'fixture','interpreter':{'sha256':'b'*64}}
        child={'version':'project-source-only-bootstrap-v1','entry_module':'scripts.build_native_exact_four_street',
               'root':'fixture','interpreter':parent['interpreter'],'compiled':{name:'a'*64 for name in names}}
        validate_build_bootstrap(child,source,parent)
        for mutation in ('empty','source','interpreter'):
            changed=copy.deepcopy(child)
            if mutation=='empty':changed['compiled']={}
            elif mutation=='source':changed['compiled'][names[0]]='c'*64
            else:changed['interpreter']={'sha256':'c'*64}
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):validate_build_bootstrap(changed,source,parent)
    def test_in_checkout_output_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'external'):run_complete_study(Path.cwd()/'forbidden-test-output','0'*40)

if __name__ == '__main__':unittest.main()
