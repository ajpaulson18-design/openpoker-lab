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


from tests.virtual_joint_witness_cases import cases, validate_sign_witnesses


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
        sign_witnesses = validate_sign_witnesses()
        (output / 'independent-sign-witnesses.json').write_text(json.dumps(sign_witnesses, indent=2) + '\n')
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
            baseline_images = {label: packet.read(label + '/stdout.bin') for label, _profile, _pair in cases() if label + '/stdout.bin' in packet.namelist()}
        baseline_executable = Path(os.environ['OPENPOKER_NATIVE_SINGLE_PASS_BASELINE_EXE']).resolve()
        baseline_identity = authenticate(baseline_executable, ROOT, 'virtual-weighted-joint-two-epoch')
        baseline_calls = 0
        (output / 'baseline-native-build-manifest.json').write_bytes(baseline_identity[0])
        for label, profile, pair in cases():
            arguments = [str(profile), *[str(value) for item in pair for value in item]]
            raw = run(label, arguments, 0)
            report = verify(profile, pair, raw)
            if label not in baseline_images:
                child = output / ('baseline-' + label)
                observed = run_bounded_child([str(baseline_executable), *arguments], b'', child,
                    stdout_limit=resource['components']['output_bytes'], timeout=180)
                baseline_calls += 1
                self.assertEqual((observed['status'], observed['actual_exit_observed'], observed['returncode'], observed['failures']),
                                 ('exited', True, 0, []))
                self.assertEqual((child / 'stderr.bin').read_bytes(), b'')
                baseline_images[label] = (child / 'stdout.bin').read_bytes()
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
        self.assertEqual(authenticate(baseline_executable, ROOT, 'virtual-weighted-joint-two-epoch'), baseline_identity)
        self.assertEqual(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), head)
        self.assertTrue(all(sha256((ROOT / name).read_bytes()).hexdigest() == before for name, before in python_hashes.items()))
        self.assertTrue(all((ROOT / name).read_bytes() == before for name, before in native_source.items()))
        (output / 'matrix-result.json').write_text(json.dumps({'status': 'single-pass-complete-requests-exact',
            'cases': observations, 'stdout_sha256': images, 'successful_requests': len(observations), 'rejected_requests': len(invalid),
            'observed_native_invocations': len(observations) + len(invalid) + baseline_calls,
            'candidate_native_invocations': len(observations) + len(invalid), 'baseline_native_invocations': baseline_calls,
            'rng_calls': 0, 'quality_gate': None,
            'corruption_controls': 2,
            'scope': 'Opt-in single-global-pass uniform/1..7 full52 finite-tree T2 witness only; no long learning, convergence or unrestricted NLHE.'}, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
