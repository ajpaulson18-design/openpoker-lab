from pathlib import Path
import subprocess,tempfile,unittest
from unittest.mock import patch
from tests.virtual_frozen_source_guard import capture_source,verify_source
from tests.virtual_frozen_whole_study import SOURCE

class SourceGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd().parent)
        self.base=Path(self.temp.name);self.repo=self.base/'repo';self.repo.mkdir()
        self.git('init');self.git('config','user.name','Source Guard Test')
        self.git('config','user.email','source-guard@example.invalid')
        self.git('config','core.autocrlf','false')
        (self.repo/'.gitattributes').write_bytes(b'*.txt text eol=lf\nraw.bin -text\n')
        (self.repo/'a.txt').write_bytes(b'one\ntwo\n')
        (self.repo/'raw.bin').write_bytes(b'raw\r\nbytes\x00\n')
        self.git('add','.');self.git('commit','-m','fixture')
    def tearDown(self):self.temp.cleanup()
    def git(self,*args,data=None):
        p=subprocess.run(['git',*args],cwd=self.repo,input=data,capture_output=True,check=True)
        return p.stdout
    def test_complete_raw_capture_external_copy_and_recheck(self):
        result=capture_source(self.repo,snapshot_directory=self.base/'saved')
        checked=verify_source(self.repo,result)
        self.assertEqual(checked['files'],3)
        for name,record in result['files'].items():
            self.assertEqual((self.base/'saved'/name).read_bytes(),(self.repo/name).read_bytes())
            self.assertEqual(record['bridge'],'raw')
    def test_explicit_lf_bridge_then_raw_byte_drift_rejects(self):
        (self.repo/'a.txt').write_bytes(b'one\r\ntwo\r\n')
        self.git('add','a.txt')
        result=capture_source(self.repo)
        self.assertEqual(result['files']['a.txt']['bridge'],'explicit_lf')
        verify_source(self.repo,result)
        (self.repo/'a.txt').write_bytes(b'one\ntwo\n')
        self.git('update-index','--assume-unchanged','a.txt')
        with self.assertRaisesRegex(ValueError,'raw frozen source drift'):verify_source(self.repo,result)
    def test_binary_and_untracked_changes_reject(self):
        (self.repo/'raw.bin').write_bytes(b'raw\nbytes\x00\n')
        with self.assertRaises(ValueError):capture_source(self.repo)
        self.git('checkout','--','raw.bin')
        (self.repo/'unexpected.py').write_text('pass\n')
        with self.assertRaisesRegex(ValueError,'clean'):capture_source(self.repo)
    def test_commit_drift_rejects_even_with_identical_raw_files(self):
        result=capture_source(self.repo)
        self.git('commit','--allow-empty','-m','new head')
        with self.assertRaisesRegex(ValueError,'cohort changed'):verify_source(self.repo,result)
    def test_source_filters_reject_before_dirty_status_can_run(self):
        (self.repo/'.gitattributes').write_bytes(b'*.txt text filter=forbidden\nraw.bin -text\n')
        with patch('tests.virtual_frozen_source_guard._clean',side_effect=AssertionError('dirty status entered before filter guard')):
            with self.assertRaisesRegex(ValueError,'unsupported executable'):capture_source(self.repo)
    def test_linked_git_object_rejects_without_filesystem_symlink_privilege(self):
        oid=self.git('hash-object','-w','--stdin',data=b'../outside').strip().decode()
        self.git('update-index','--add','--cacheinfo','120000,'+oid+',link')
        self.git('commit','-m','link fixture')
        with self.assertRaisesRegex(ValueError,'unsupported source tree object'):capture_source(self.repo)
    def test_crlf_normalization_spans_stream_chunk_boundary(self):
        raw=b'A'*(SOURCE['stream_chunk_bytes']-1)+b'\r\n'
        (self.repo/'a.txt').write_bytes(raw)
        self.git('add','a.txt');self.git('commit','-m','boundary')
        result=capture_source(self.repo)
        self.assertEqual(result['files']['a.txt']['bridge'],'explicit_lf')
        verify_source(self.repo,result)

if __name__ == '__main__':unittest.main()
