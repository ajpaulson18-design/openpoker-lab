"""Authenticated native numeric Q/prefix routing conformance."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

from scripts import build_native_exact_four_street as builder


class NativeIndexedRoutingCompiledTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = TemporaryDirectory(prefix='opl-native-indexed-routing-')
        try:
            provided = os.environ.get('OPENPOKER_NATIVE_INDEXED_ROUTING_EXE')
            if provided:
                cls.executable = Path(provided).resolve(strict=True)
            else:
                if shutil.which('cl' if os.name == 'nt' else 'c++') is None:
                    raise unittest.SkipTest('no installed compiler or explicitly selected indexed-routing helper')
                cls.executable = Path(builder.build(cls.temporary.name, target='indexed-routing')['executable'])
            cls.manifest_path = cls.executable.parent / 'native-exact-build-manifest.json'
            cls.manifest_raw = builder._bounded_read(cls.manifest_path, 128 * 1024)
            cls.manifest = json.loads(cls.manifest_raw)
            names = (*builder.TARGETS['indexed-routing'][1], 'scripts/build_native_exact_four_street.py',
                'third_party/boost-multiprecision-1.92.0/manifest.json',
                'third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt',
                'third_party/boost-multiprecision-1.92.0/headers.zip')
            cls.sources = {name: builder._hash(builder._bounded_read(builder.ROOT / name, 2 * 1024 * 1024))
                for name in names}
            if (cls.manifest.get('target') != 'indexed-routing' or cls.manifest.get('contract') != 'native-exact-build-v1' or
                    cls.manifest.get('source_sha256') != cls.sources or
                    builder._hash(cls.executable.read_bytes()) != cls.manifest.get('executable_sha256')):
                raise ValueError('Indexed-routing helper source/build changed; rebuild explicitly')
        except BaseException:
            cls.temporary.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            if cls.manifest_path.read_bytes() != cls.manifest_raw or any(
                    builder._hash((builder.ROOT / name).read_bytes()) != expected
                    for name, expected in cls.sources.items()) or (
                    builder._hash(cls.executable.read_bytes()) != cls.manifest['executable_sha256']):
                raise ValueError('Indexed-routing source/build changed during conformance')
        finally:
            cls.temporary.cleanup()

    def test_complete_numeric_row_prefix_and_resource_controls(self):
        checked = subprocess.run([str(self.executable)], capture_output=True, timeout=90)
        self.assertEqual(checked.returncode, 0, (checked.stdout + checked.stderr).decode('utf-8', 'replace'))
        self.assertIn(b'ALL INDEXED ROUTING CONTROLS PASSED', checked.stdout)


if __name__ == '__main__':
    unittest.main()
