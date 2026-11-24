"""Opt-in single-global-pass full52 T2 conformance on named explicit range profiles."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import zipfile

from tests.test_native_exact_reach import authenticate
from tests.virtual_frozen_run_control import run_bounded_child
from tests.virtual_native_single_pass_reference import verify
from tests.virtual_native_weighted_joint_reference import verify as baseline_verify
from tests.virtual_joint_numeric_projection import project
from tests.virtual_single_pass_forecast_reference import forecast

ROOT = Path(__file__).resolve().parents[1]
ENV = 'OPENPOKER_NATIVE_WEIGHTED_SINGLE_PASS_EXE'
OUT = 'OPENPOKER_NATIVE_WEIGHTED_SINGLE_PASS_DIR'
TARGET = 'virtual-weighted-joint-single-pass'


def cases():
    for profile, normalizer in enumerate((1624350, 25908876)):
        for label, pair in (
            ('same-world', ((0, 0), (0, 0))),
            ('boundaries', ((normalizer - 1, 34246079), (0, 0))),
            ('shared-flop-future', ((0, 0), (0, 1)))):
            yield f'profile-{profile}-{label}', profile, pair


@unittest.skipUnless(os.environ.get(ENV), 'explicit source-built weighted whole-game candidate required')
class NativeSinglePassEpochTests(unittest.TestCase):
    def test_all_retained_signed_rows_and_implicit_policy_contract(self):
        resource = forecast(); self.assertTrue(resource['forecast_passes_caps'])
        executable = Path(os.environ[ENV]).resolve()
        identity = authenticate(executable, ROOT, TARGET)
        output = Path(os.environ[OUT]).resolve(); self.assertEqual(output.parent, ROOT.parent.resolve())
        output.mkdir(exist_ok=False)
        self.assertEqual(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no', '--',
                                                 '*.py', *identity[1]['source_sha256']], cwd=ROOT), b'')
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        python_names = tuple(name for name in subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
                             if name.endswith('.py'))
        python_hashes = {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in python_names}
        native_source = {name: (ROOT / name).read_bytes() for name in identity[1]['source_sha256']}
        for name, raw in native_source.items():
            path = output / 'source' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        (output / 'source-identity.json').write_text(json.dumps({'head': head, 'python_version': sys.version,
            'tracked_python_raw_sha256': python_hashes,
            'native_raw_sha256': {name: sha256(raw).hexdigest() for name, raw in native_source.items()}}, indent=2) + '\n')
        (output / 'native-build-manifest.json').write_bytes(identity[0])
        (output / 'whole-forecast.json').write_text(json.dumps(resource, indent=2) + '\n')
        observations = []; images = {}; first = None
        def run(label, arguments, expected_exit):
            child = output / label
            observation = run_bounded_child([str(executable), *arguments], b'', child,
                stdout_limit=resource['components']['output_bytes'], timeout=180)
            self.assertEqual(observation['failures'], [])
            self.assertEqual((observation['status'], observation['returncode'], observation['actual_exit_observed']),
                             ('exited', expected_exit, True))
            raw = (child / 'stdout.bin').read_bytes()
            if expected_exit:
                self.assertEqual(raw, b'')
            else:
                self.assertEqual((child / 'stderr.bin').read_bytes(), b'')
            return raw
        baseline = ROOT / 'benchmarks/results/weighted-joint-foundation-v1/whole-normal.zip'
        archived = baseline.read_bytes()
        self.assertEqual((len(archived), sha256(archived).hexdigest()),
                         (1003611, '221d66b1b2380c2ad8d0c35b45fa1704561273c2c680094df5fd7f275b67dfc7'))
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(archived)) as packet:
            baseline_images = {label: packet.read(label + '/stdout.bin') for label, _profile, _pair in cases()}
        for label, profile, pair in cases():
            arguments = [str(profile), *[str(value) for item in pair for value in item]]
            raw = run(label, arguments, 0)
            report = verify(profile, pair, raw)
            baseline_verify(profile, pair, baseline_images[label])
            self.assertEqual(project(raw), project(baseline_images[label]))
            report['baseline_numeric_projection_sha256'] = sha256(project(baseline_images[label])).hexdigest()
            (output / label / 'independent-rows.json').write_text(json.dumps(report, indent=2) + '\n')
            observations.append({'case': label, **report}); images[label] = sha256(raw).hexdigest()
            if first is None:
                first = profile, pair, raw
        invalid = {
            'arity': ['0', '0', '0'], 'profile': ['2', '0', '0', '0', '0'],
            'uniform-ticket': ['0', '1624350', '0', '0', '0'],
            'weighted-ticket': ['1', '25908876', '0', '0', '0'],
            'board': ['0', '0', '34246080', '0', '0'],
            'negative': ['0', '-1', '0', '0', '0'], 'plus': ['0', '+0', '0', '0', '0'],
            'too-long': ['0', '000000000', '0', '0', '0']}
        for label, arguments in invalid.items():
            run('reject-' + label, arguments, 2)
        profile, pair, raw = first
        changed = bytearray(raw); changed[368 + 168] ^= 1
        for label, corrupted in (('corrupt-root', bytes(changed)), ('corrupt-truncation', raw[:-1])):
            (output / (label + '.bin')).write_bytes(corrupted)
            with self.assertRaises(ValueError):
                verify(profile, pair, corrupted)
        self.assertEqual(authenticate(executable, ROOT, TARGET), identity)
        self.assertEqual(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), head)
        self.assertTrue(all(sha256((ROOT / name).read_bytes()).hexdigest() == before for name, before in python_hashes.items()))
        self.assertTrue(all((ROOT / name).read_bytes() == before for name, before in native_source.items()))
        (output / 'matrix-result.json').write_text(json.dumps({'status': 'single-pass-six-complete-requests-exact',
            'cases': observations, 'stdout_sha256': images, 'successful_requests': 6, 'rejected_requests': len(invalid),
            'observed_native_invocations': 6 + len(invalid), 'rng_calls': 0, 'quality_gate': None,
            'corruption_controls': 2,
            'scope': 'Opt-in single-global-pass uniform/1..7 full52 finite-tree T2 witness only; no long learning, convergence or unrestricted NLHE.'}, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
