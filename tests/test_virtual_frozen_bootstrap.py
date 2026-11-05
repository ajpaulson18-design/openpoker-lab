from pathlib import Path
import hashlib,importlib,importlib.util,json,marshal,os,struct,subprocess,sys,tempfile,unittest,uuid
from scripts.run_virtual_frozen_source_only import install_source_loader,scan_project_caches,source_only_command

class SourceOnlyBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd().parent);self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def bootstrap_fixture(self):
        directory=self.root/'scripts';directory.mkdir();(directory/'__init__.py').write_text('')
        script=directory/'run_virtual_frozen_source_only.py'
        script.write_bytes((Path.cwd()/'scripts/run_virtual_frozen_source_only.py').read_bytes())
        target=directory/'build_native_exact_four_street.py'
        target.write_text('import sys\nif not (sys.flags.isolated and sys.flags.no_site):raise RuntimeError("unsafe")\nprint("SOURCE_ONLY_ENTRY")\n')
        return script,target
    def test_isolated_source_only_front_door_records_exact_compiled_bytes(self):
        script,target=self.bootstrap_fixture();receipt=self.root/'receipt.json'
        result=subprocess.run(source_only_command(script,hashlib.sha256(script.read_bytes()).hexdigest(),'scripts.build_native_exact_four_street',receipt,[]),capture_output=True,check=False)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn(b'SOURCE_ONLY_ENTRY',result.stdout)
        record=json.loads(receipt.read_bytes())
        self.assertEqual(record['compiled']['scripts/build_native_exact_four_street.py'],hashlib.sha256(target.read_bytes()).hexdigest())
        self.assertEqual(record['interpreter']['isolated'],1)
        self.assertEqual(record['final_cache_scan']['project_bytecode_files'],0)
    def test_dyadic_controller_and_reviewer_have_named_source_only_entries(self):
        script,_=self.bootstrap_fixture()
        for module in ('scripts.run_virtual_dyadic_training_cohort','scripts.verify_virtual_dyadic_training'):
            with self.subTest(module=module):
                name=module.replace('.','/')+'.py';target=self.root/name
                target.write_text('print("SOURCE_ONLY_DYADIC")\n')
                receipt=self.root/(target.stem+'.json')
                result=subprocess.run(source_only_command(script,hashlib.sha256(script.read_bytes()).hexdigest(),
                    module,receipt,[]),capture_output=True,check=False)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn(b'SOURCE_ONLY_DYADIC',result.stdout)
                self.assertEqual(json.loads(receipt.read_bytes())['compiled'][name],hashlib.sha256(target.read_bytes()).hexdigest())
    def test_ignored_cache_rejects_before_any_project_module(self):
        script,target=self.bootstrap_fixture();cache=self.root/'__pycache__';cache.mkdir();(cache/'hidden.pyc').write_bytes(b'x')
        target.write_text('raise RuntimeError("PROJECT_ENTRY_MUST_NOT_RUN")\n')
        result=subprocess.run(source_only_command(script,hashlib.sha256(script.read_bytes()).hexdigest(),'scripts.build_native_exact_four_street',self.root/'receipt',[]),capture_output=True,check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'bytecode cache rejected',result.stderr)
        self.assertNotIn(b'PROJECT_ENTRY_MUST_NOT_RUN',result.stderr)
    def test_first_stage_rejects_changed_bootstrap_before_project_entry(self):
        script,target=self.bootstrap_fixture()
        command=source_only_command(script,hashlib.sha256(script.read_bytes()).hexdigest(),
                                    'scripts.build_native_exact_four_street',self.root/'receipt',[])
        script.write_bytes(script.read_bytes()+b'\n# changed\n')
        result=subprocess.run(command,capture_output=True,check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'trusted bootstrap byte mismatch',result.stderr)
        self.assertNotIn(b'SOURCE_ONLY_ENTRY',result.stdout)
    def test_source_loader_ignores_a_valid_but_false_bytecode_cache(self):
        name='source_fixture_'+uuid.uuid4().hex;path=self.root/(name+'.py');raw=b'VALUE=7\n';path.write_bytes(raw)
        cached=Path(importlib.util.cache_from_source(str(path)));cached.parent.mkdir()
        header=importlib.util.MAGIC_NUMBER+struct.pack('<III',0,int(path.stat().st_mtime)&0xffffffff,len(raw))
        cached.write_bytes(header+marshal.dumps(compile('VALUE=99\n',str(path),'exec')))
        sys.path.insert(0,str(self.root));finder=None
        try:
            ordinary=importlib.import_module(name);self.assertEqual(ordinary.VALUE,99)
            del sys.modules[name]
            state={'compiled':{}};finder=install_source_loader(self.root,state)
            actual=importlib.import_module(name)
            self.assertEqual(actual.VALUE,7)
            self.assertEqual(state['compiled'][name+'.py'],hashlib.sha256(raw).hexdigest())
            with self.assertRaisesRegex(ValueError,'bytecode cache rejected'):scan_project_caches(self.root)
        finally:
            sys.modules.pop(name,None);sys.path.remove(str(self.root))
            if finder is not None:sys.meta_path.remove(finder)

if __name__ == '__main__':unittest.main()
