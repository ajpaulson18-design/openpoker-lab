import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tests import test_virtual_frozen_source_guard as fixtures
from tests.virtual_frozen_source_guard import capture_source,capture_execution_closure,verify_execution_closure

class ExecutionClosureTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.SourceGuardTests();self.fixture.setUp()
        self.repo=self.fixture.repo;self.git=self.fixture.git
        (self.repo/'pyproject.toml').write_text('[project]\nname="fixture"\n')
        self.git('add','pyproject.toml');self.git('commit','-m','execution inputs')
    def tearDown(self):self.fixture.tearDown()
    def test_declared_execution_input_and_new_import_gate(self):
        source=capture_source(self.repo)
        with patch('tests.virtual_frozen_source_guard.require_source_bootstrap',return_value={'compiled':{},'interpreter':{}}), patch('tests.virtual_frozen_source_guard.loaded_project_sources',return_value={'a.txt'}):
            closure=capture_execution_closure(self.repo,source,{'raw.bin'})
            result=verify_execution_closure(self.repo,source,closure)
            self.assertEqual(result['inputs'],4)
        with patch('tests.virtual_frozen_source_guard.require_source_bootstrap',return_value={'compiled':{},'interpreter':{}}), patch('tests.virtual_frozen_source_guard.loaded_project_sources',return_value={'a.txt','new.py'}):
            with self.assertRaisesRegex(ValueError,'module closure changed'):verify_execution_closure(self.repo,source,closure)
    # Inherited fixture controls are exercised separately; this class only
    # adds the execution-closure case.

if __name__ == '__main__':unittest.main()
