"""Source-frozen native joint observations versus all-row independent Q52 math."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts.replay_joint_two_epoch import (
    TARGET, SCOPE, SOURCE_VERSION, MATH_SOURCES, CONTROL_SOURCES,
    selectors, command, invalid_commands, plan_record, matrix_record,
)
from tests.test_native_exact_reach import authenticate, sha
from tests.virtual_frozen_run_control import run_bounded_child

ROOT = Path(__file__).resolve().parents[1]
ENV = 'OPENPOKER_NATIVE_JOINT_TWO_EPOCH_EXE'
OUT = 'OPENPOKER_NATIVE_JOINT_TWO_EPOCH_DIR'


@unittest.skipUnless(os.environ.get(ENV), 'explicit source-built joint two-epoch candidate required')
class NativeJointTwoEpochTests(unittest.TestCase):
    def test_whole_joint_requests_and_fail_closed_selectors(self):
        exe = Path(os.environ[ENV]).resolve()
        identity = authenticate(exe, ROOT, TARGET)
        self.assertEqual(identity[1]['scope'], SCOPE)
        names = sorted(set(identity[1]['source_sha256']) | set(MATH_SOURCES) | set(CONTROL_SOURCES))
        self.assertLessEqual(len(names), 128)
        self.assertFalse(subprocess.check_output(
            ['git', 'status', '--porcelain', '--untracked-files=all', '--', *names], cwd=ROOT))
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        source = {name: (ROOT / name).read_bytes() for name in names}
        self.assertLessEqual(sum(map(len, source.values())), 64 << 20)
        tree = {}
        for line in subprocess.check_output(['git', 'ls-tree', '-r', head], cwd=ROOT, text=True).splitlines():
            metadata, name = line.split('\t', 1)
            if name in names:
                tree[name] = metadata.split()[2]
        self.assertEqual(set(tree), set(names))
        with TemporaryDirectory(dir=ROOT.parent) as temporary:
            directory = Path(os.environ.get(OUT, str(Path(temporary) / 'observed')))
            directory.mkdir(parents=True, exist_ok=False)
            for name, body in source.items():
                self.assertLessEqual(len(body), 32 << 20)
                path = directory / 'source' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
            (directory / 'source-identity.json').write_text(json.dumps({
                'version': SOURCE_VERSION, 'head': head,
                'raw_sha256': {name: sha256(body).hexdigest() for name, body in source.items()},
                'committed_blobs': tree, 'python_version': sys.version,
                'python_executable_sha256': sha(Path(sys.executable))}, indent=2) + '\n')
            (directory / 'native-build-manifest.json').write_bytes(identity[0])
            (directory / 'native-identity.json').write_text(json.dumps({
                'manifest_sha256': sha256(identity[0]).hexdigest(),
                'executable_sha256': identity[1]['executable_sha256']}) + '\n')
            # Independent scalar whole-domain preflight precedes both native
            # launches and any oracle Fixture/range/rank preparation.
            from tests.virtual_joint_two_epoch_forecast_reference import forecast
            from tests.virtual_native_joint_two_epoch_reference import verify_joint_wire
            resource = forecast()
            self.assertTrue(resource['forecast_passes_caps'])
            (directory / 'case-plan.json').write_text(json.dumps(plan_record(resource), indent=2) + '\n')

            def observe(label, args):
                (directory / (label + '.command.json')).write_text(json.dumps(args) + '\n')
                child = directory / label
                outcome = run_bounded_child(args, b'', child,
                                            stdout_limit=resource['components']['output_bytes'], timeout=180)
                return child, outcome

            results = []; first = None
            for label, pair in selectors():
                child, outcome = observe(label, command(exe, pair))
                self.assertEqual((outcome['status'], outcome['returncode'], outcome['actual_exit_observed']),
                                 ('exited', 0, True), label)
                self.assertEqual((child / 'stderr.bin').read_bytes(), b'', label)
                raw = (child / 'stdout.bin').read_bytes()
                checked = verify_joint_wire(pair, raw)
                (child / 'independent-rows.json').write_text(json.dumps(checked, indent=2) + '\n')
                results.append({'case': label, **checked})
                if first is None:
                    first = pair, raw
            invalid = invalid_commands(command(exe, selectors()[0][1]))
            self.assertEqual(len(invalid), 7)
            for label, args in invalid.items():
                child, outcome = observe(label, args)
                self.assertEqual((outcome['status'], outcome['returncode'], outcome['actual_exit_observed']),
                                 ('exited', 2, True), label)
                self.assertEqual((child / 'stdout.bin').read_bytes(), b'', label)
                self.assertTrue((child / 'stderr.bin').read_bytes(), label)
            pair, original = first
            corrupt = bytearray(original); corrupt[336 + 168] ^= 1
            controls = {'corrupt-root': bytes(corrupt), 'corrupt-truncation': original[:-1]}
            corruption_results = []
            for label, changed in controls.items():
                (directory / (label + '.bin')).write_bytes(changed)
                with self.assertRaises(ValueError, msg=label):
                    verify_joint_wire(pair, changed)
                corruption_results.append({'case': label, 'status': 'rejected', 'sha256': sha256(changed).hexdigest()})
            (directory / 'corruption-controls.json').write_text(json.dumps(corruption_results, indent=2) + '\n')
            (directory / 'matrix-results.json').write_text(json.dumps(matrix_record(results), indent=2) + '\n')
        self.assertEqual(authenticate(exe, ROOT, TARGET), identity)
        self.assertEqual({name: (ROOT / name).read_bytes() for name in names}, source)


if __name__ == '__main__':
    unittest.main()
