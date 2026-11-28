"""Source-built packed arithmetic controls."""
import os
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory
from tests.test_native_exact_reach import authenticate, sha
from tests.virtual_frozen_run_control import run_bounded_child

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.environ.get("OPENPOKER_NATIVE_PACKED_SIGNED_UPDATE_EXE"),
                     "explicit source-built packed update controls required")
class PackedSignedUpdateTests(unittest.TestCase):
    def test_randomized_and_boundary_controls(self):
        exe = Path(os.environ["OPENPOKER_NATIVE_PACKED_SIGNED_UPDATE_EXE"]).resolve()
        identity = authenticate(exe, ROOT, "packed-signed-update-controls")
        before = sha(exe)
        self.assertEqual(before, identity[1]["executable_sha256"])
        with TemporaryDirectory() as directory:
            output = Path(directory)/'control'
            result = run_bounded_child([str(exe)], b'', output, stdout_limit=4096)
            self.assertEqual(result['status'], 'exited')
            self.assertEqual(result['returncode'], 0)
            self.assertEqual((output/'stderr.bin').read_bytes(), b'')
            self.assertEqual((output/'stdout.bin').read_bytes().splitlines(),
                             [b"packed signed update controls passed"])
        self.assertEqual(sha(exe), before)
        self.assertEqual(authenticate(exe, ROOT, "packed-signed-update-controls"), identity)
