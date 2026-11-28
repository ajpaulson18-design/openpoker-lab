"""Authenticated synthetic controls for constructor-bound joint arithmetic."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts.replay_native_frozen_policy_state import ORACLE_SOURCES
from tests.test_native_exact_reach import authenticate, sha
from tests.test_native_dyadic_policy import allocation, Q
from tests.virtual_frozen_run_control import run_bounded_child

ROOT = Path(__file__).resolve().parents[1]
ENV = 'OPENPOKER_NATIVE_JOINT_EPOCH_EXE'
OUT = 'OPENPOKER_NATIVE_JOINT_EPOCH_DIR'
TARGET = 'virtual-joint-epoch-controls'
GUARDS = ('joint-third-epoch', 'legacy-rejects-joint-law', 'joint-rejects-public-law',
          'joint-rejects-weighted-law', 'joint-rejects-unknown-law', 'unknown-arithmetic',
          'joint-rejects-public-R', 'joint-rejects-public-A', 'joint-rejects-divisor-A',
          'legacy-rejects-joint-R', 'joint-uncentered-regret', 'joint-average-proportions',
          'joint-negative-average', 'joint-needs-two-reads', 'joint-missing-stage',
          'joint-duplicate-stage')


@unittest.skipUnless(os.environ.get(ENV), 'explicit source-built joint epoch component required')
class NativeJointEpochTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = Path(os.environ[ENV]).resolve()
        cls.identity = authenticate(cls.exe, ROOT, TARGET)
        names = sorted(set(cls.identity[1]['source_sha256']) | set(ORACLE_SOURCES) |
                       {'tests/test_native_joint_epoch.py', 'tests/test_native_dyadic_policy.py'})
        if len(names) > 128 or subprocess.check_output(
                ['git', 'status', '--porcelain', '--untracked-files=all', '--', *names], cwd=ROOT):
            raise ValueError('joint epoch component source must be committed and clean')
        cls.head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        cls.source = {name: (ROOT / name).read_bytes() for name in names}
        if sum(map(len, cls.source.values())) > 64 << 20:
            raise ValueError('joint epoch source ceiling')
        tree = {}
        for line in subprocess.check_output(['git', 'ls-tree', '-r', cls.head], cwd=ROOT, text=True).splitlines():
            metadata, name = line.split('\t', 1)
            if name in names:
                tree[name] = metadata.split()[2]
        if set(tree) != set(names):
            raise ValueError('joint epoch complete source tree')
        target = os.environ.get(OUT)
        if target is None:
            temporary = TemporaryDirectory(dir=ROOT.parent)
            cls.addClassCleanup(temporary.cleanup)
            target = Path(temporary.name) / 'observed'
        cls.directory = Path(target)
        cls.directory.mkdir(parents=True, exist_ok=False)
        for name, body in cls.source.items():
            if len(body) > 32 << 20:
                raise ValueError('joint epoch source member ceiling')
            path = cls.directory / 'source' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        (cls.directory / 'source-identity.json').write_text(json.dumps({
            'version': 'joint-epoch-component-sources-v1', 'head': cls.head,
            'raw_sha256': {name: sha256(body).hexdigest() for name, body in cls.source.items()},
            'committed_blobs': tree, 'python_version': sys.version,
            'python_executable_sha256': sha(Path(sys.executable))}, indent=2) + '\n')
        (cls.directory / 'native-build-manifest.json').write_bytes(cls.identity[0])
        command = [str(cls.exe)]
        (cls.directory / 'command.json').write_text(json.dumps(command) + '\n')
        cls.process = run_bounded_child(command, b'', cls.directory / 'process', stdout_limit=65536, timeout=180)
        cls.stdout = (cls.directory / 'process/stdout.bin').read_bytes()
        cls.stderr = (cls.directory / 'process/stderr.bin').read_bytes()
        cls.lines = cls.stdout.decode('ascii').splitlines()

    @classmethod
    def tearDownClass(cls):
        if (authenticate(cls.exe, ROOT, TARGET) != cls.identity or
                {name: (ROOT / name).read_bytes() for name in cls.source} != cls.source):
            raise AssertionError('joint epoch component source/build drift')

    def test_process_and_typed_constructor_mode_guards(self):
        self.assertEqual((self.process['status'], self.process['returncode'],
                          self.process['actual_exit_observed']), ('exited', 0, True))
        self.assertFalse(self.stderr)
        self.assertEqual((self.lines[0], self.lines[-1]), ('VIRTUAL_JOINT_EPOCH_COMPONENT_V1', 'END'))
        self.assertEqual([line.split()[1:] for line in self.lines if line.startswith('GUARD ')],
                         [[name, 'PASS'] for name in GUARDS])
        denominators = {parts[1]: tuple(map(int, parts[2:])) for parts in
                        (line.split() for line in self.lines if line.startswith('DENOM '))}
        self.assertEqual(denominators, {'joint': (1 << 625, 1 << 364),
                                        'legacy': (580 << 625, 580 << 364)})

    def test_mode_aware_and_explicit_stage_preserve_exact_signed_state(self):
        rows = {}
        for line in self.lines:
            if line.startswith('ROW '):
                _, label, *cells = line.split()
                self.assertNotIn(label, rows)
                self.assertEqual(len(cells), 12)
                values = list(map(int, cells))
                rows[label] = values[::3], values[1::3], values[2::3]
        self.assertEqual(set(rows), {'E1', 'E2'})
        dr, da = 1 << 625, 1 << 364
        first = [5 * dr, -3 * dr, 0, -2 * dr]
        second = [5 * dr, dr, 2 * dr, -3 * dr]
        self.assertEqual(rows['E1'], (first, [da // 4] * 4, allocation(first)[0]))
        self.assertEqual(rows['E2'], (second, [5 * da // 4, da // 4, da // 4, da // 4], allocation(second)[0]))
        clipped_then_added = [5 * dr, 4 * dr, 2 * dr, -dr]
        self.assertNotEqual(rows['E2'][2], allocation(clipped_then_added)[0])
        self.assertEqual(sum(rows['E1'][2]), Q)
        self.assertEqual(sum(rows['E2'][2]), Q)

    def test_joint_mode_retains_exact_two_read_and_complete_commit_contract(self):
        record = next(line for line in self.lines if line.startswith('RECEIPT '))
        work, quant, reads, staged_rows, slots, commits, quant_rows, rows, current_slots = map(int, record.split()[1:])
        self.assertEqual((reads, staged_rows, slots, commits, quant_rows, rows, current_slots), (4, 2, 8, 2, 2, 1, 4))
        self.assertGreater(work, 0)
        self.assertGreater(quant, 0)
        self.assertLessEqual(work + quant, 1_000_000)


if __name__ == '__main__':
    unittest.main()
