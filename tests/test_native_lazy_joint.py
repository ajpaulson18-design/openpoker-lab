"""Shared lazy Catalog whole-walk parity and explicit Store binding controls."""
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import zipfile

from scripts.replay_native_grid_raw import MATH
from scripts.replay_joint_two_epoch import NEW_MATH
from tests.test_native_exact_reach import authenticate
from tests.virtual_frozen_run_control import run_bounded_child
from tests.virtual_native_single_pass_reference import verify as eager_verify
from tests.virtual_native_lazy_joint_reference import verify
from tests.virtual_lazy_joint_forecast_reference import forecast
from tests.virtual_joint_witness_cases import cases, validate_sign_witnesses

ROOT = Path(__file__).resolve().parents[1]
EXTRA = ('tests/virtual_weighted_joint_reference.py', 'tests/virtual_weighted_joint_raw_reference.py',
         'tests/virtual_weighted_joint_forecast_reference.py', 'tests/virtual_native_weighted_joint_reference.py',
         'tests/virtual_single_pass_forecast_reference.py', 'tests/virtual_native_single_pass_reference.py',
         'tests/virtual_lazy_catalog_reference.py', 'tests/virtual_lazy_joint_forecast_reference.py',
         'tests/virtual_native_lazy_joint_reference.py', 'tests/virtual_joint_witness_cases.py',
         'tests/test_native_lazy_joint.py', 'tests/test_lazy_joint_forecast.py',
         'scripts/replay_native_grid_raw.py', 'scripts/replay_joint_two_epoch.py')


def capture(executable, target, output):
    identity = authenticate(executable, ROOT, target)
    names = sorted({*identity[1]['source_sha256'], *MATH, *NEW_MATH, *EXTRA})
    if len(names) > 128 or subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all', '--', *names], cwd=ROOT):
        raise ValueError('lazy complete introduced source must be committed and clean')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    source = {name: (ROOT / name).read_bytes() for name in names}
    if sum(map(len, source.values())) > 64 << 20 or any(len(raw) > 2 << 20 for raw in source.values()):
        raise ValueError('lazy introduced source byte boundary')
    tree = {line.split('\t', 1)[1]: line.split('\t', 1)[0].split()[2]
            for line in subprocess.check_output(['git', 'ls-tree', '-r', head], cwd=ROOT, text=True).splitlines()}
    if output.parent != ROOT.parent.resolve():
        raise ValueError('external sibling lazy evidence required')
    output.mkdir(exist_ok=False)
    for name, raw in source.items():
        path = output / 'source' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    (output / 'source-identity.json').write_text(json.dumps({'head': head, 'python_version': sys.version,
        'raw_sha256': {name: sha256(raw).hexdigest() for name, raw in source.items()},
        'committed_blobs': {name: tree[name] for name in names}}, indent=2) + '\n')
    (output / 'native-build-manifest.json').write_bytes(identity[0])
    return identity, head, source


def unchanged(executable, target, identity, head, source):
    if (authenticate(executable, ROOT, target) != identity or
        subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != head or
        any((ROOT / name).read_bytes() != raw for name, raw in source.items())):
        raise ValueError('lazy execution source/binary drift')


@unittest.skipUnless(os.environ.get('OPENPOKER_NATIVE_LAZY_EPOCH_EXE'), 'explicit source-built lazy epoch controls required')
class NativeLazyEpochTests(unittest.TestCase):
    def test_storage_contract_binding_and_valid_commit(self):
        executable = Path(os.environ['OPENPOKER_NATIVE_LAZY_EPOCH_EXE']).resolve()
        target = 'virtual-lazy-epoch-controls'; output = Path(os.environ['OPENPOKER_NATIVE_LAZY_EPOCH_DIR']).resolve()
        identity, head, source = capture(executable, target, output)
        result = run_bounded_child([str(executable)], b'', output / 'native', stdout_limit=16384, timeout=180)
        self.assertEqual((result['status'], result['actual_exit_observed'], result['returncode'], result['failures']), ('exited', True, 0, []))
        self.assertEqual((output / 'native/stderr.bin').read_bytes(), b'')
        lines = (output / 'native/stdout.bin').read_text().splitlines()
        old = ('legacy-one-read', 'weighted-v1-one-read', 'single-mode-two-reads', 'zero-read-contract',
               'duplicate-read', 'wrong-seal-read-count', 'abandoned-stage', 'old-mode-still-needs-two',
               'unobserved-stage-row', 'public-proposal')
        new = ('eager-store-lazy-catalog', 'lazy-store-eager-catalog', 'invalid-storage-contract')
        self.assertEqual(lines, [*['GUARD ' + label + ' PASS' for label in old], 'SINGLE_PASS_EPOCH_GUARDS_V1 PASS 10 1',
                                 *['GUARD ' + label + ' PASS' for label in new], 'LAZY_EPOCH_GUARDS_V1 PASS 3 1'])
        unchanged(executable, target, identity, head, source)
        (output / 'result.json').write_text(json.dumps({'status': 'lazy-store-storage-contract-guards-exact',
            'old_guards': 10, 'new_guards': 3, 'valid_commits': 2, 'observed_native_calls': 1,
            'scope': 'Synthetic explicit storage/read/owner guards only; no whole-game or quality claim.'}, indent=2) + '\n')


@unittest.skipUnless(os.environ.get('OPENPOKER_NATIVE_LAZY_JOINT_EXE'), 'explicit source-built lazy whole-walk candidate required')
class NativeLazyJointTests(unittest.TestCase):
    def test_all_rows_storage_and_explicit_eager_baseline(self):
        resource = forecast(); self.assertTrue(resource['forecast_passes_caps']); self.assertTrue(resource['reference_combined_passes_caps'])
        executable = Path(os.environ['OPENPOKER_NATIVE_LAZY_JOINT_EXE']).resolve()
        baseline = Path(os.environ['OPENPOKER_NATIVE_LAZY_JOINT_BASELINE_EXE']).resolve()
        target = 'virtual-weighted-joint-single-pass-lazy'; output = Path(os.environ['OPENPOKER_NATIVE_LAZY_JOINT_DIR']).resolve()
        identity, head, source = capture(executable, target, output)
        baseline_identity = authenticate(baseline, ROOT, 'virtual-weighted-joint-single-pass')
        (output / 'baseline-native-build-manifest.json').write_bytes(baseline_identity[0])
        (output / 'forecast.json').write_text(json.dumps(resource, indent=2) + '\n')
        (output / 'independent-sign-witnesses.json').write_text(json.dumps(validate_sign_witnesses(), indent=2) + '\n')
        # Preserve the published single-pass wires as an additional default-
        # path regression. Never execute a source or binary from the archive.
        archived = (ROOT / 'benchmarks/results/joint-single-pass-v1/candidate-normal.zip').read_bytes()
        self.assertEqual((len(archived), sha256(archived).hexdigest()),
                         (2928893, '000cb834ad44db49f5c9eff2286f270ade6bf284b1a55ffa0dbc200761b6b079'))
        reports = []; first = None; calls = 0
        def run(path, label, arguments, expected_exit):
            nonlocal calls
            child = output / label
            result = run_bounded_child([str(path), *arguments], b'', child,
                stdout_limit=resource['components']['output_bytes'], timeout=180)
            calls += 1
            self.assertEqual((result['status'], result['actual_exit_observed'], result['returncode'], result['failures']),
                             ('exited', True, expected_exit, []))
            raw = (child / 'stdout.bin').read_bytes()
            if expected_exit:
                self.assertEqual(raw, b'')
            else:
                self.assertEqual((child / 'stderr.bin').read_bytes(), b'')
            return raw
        with zipfile.ZipFile(BytesIO(archived)) as archive:
            for label, profile, pair in cases():
                arguments = [str(profile), *[str(value) for item in pair for value in item]]
                raw = run(executable, label, arguments, 0); report = verify(profile, pair, raw)
                old = run(baseline, 'baseline-' + label, arguments, 0); eager_verify(profile, pair, old)
                golden = archive.read('whole-2/' + label + '/stdout.bin')
                self.assertEqual(old, golden)
                self.assertEqual(report['canonical_eager_stdout_sha256'], sha256(old).hexdigest())
                (output / label / 'independent-rows-storage.json').write_text(json.dumps(report, indent=2) + '\n')
                reports.append({'case': label, **report})
                if first is None:
                    first = profile, pair, raw
        invalid = {'arity': ['0', '0', '0'], 'profile': ['2', '0', '0', '0', '0'],
            'uniform-ticket': ['0', '1624350', '0', '0', '0'], 'weighted-ticket': ['1', '25908876', '0', '0', '0'],
            'board': ['0', '0', '34246080', '0', '0'], 'negative': ['0', '-1', '0', '0', '0'],
            'plus': ['0', '+0', '0', '0', '0'], 'too-long': ['0', '000000000', '0', '0', '0']}
        for label, args in invalid.items():
            run(executable, 'reject-' + label, args, 2)
        profile, pair, raw = first
        corruptions = {'truncation': raw[:-1]}
        for label, offset in (('root', 368 + 168), ('bitmap', len(raw) - 16), ('occupied', len(raw) - 8), ('contract', 8 + 23 * 8)):
            changed = bytearray(raw); changed[offset] ^= 1; corruptions[label] = bytes(changed)
        for label, changed in corruptions.items():
            (output / ('corrupt-' + label + '.bin')).write_bytes(changed)
            with self.assertRaises(ValueError):
                verify(profile, pair, changed)
        unchanged(executable, target, identity, head, source)
        self.assertEqual(authenticate(baseline, ROOT, 'virtual-weighted-joint-single-pass'), baseline_identity)
        (output / 'matrix-result.json').write_text(json.dumps({'status': 'lazy-full52-matrix-exact', 'cases': reports,
            'successful_candidate_requests': 10, 'rejected_candidate_requests': 8, 'baseline_requests': 10,
            'observed_native_calls': calls, 'corruption_controls': len(corruptions), 'quality_gate': None,
            'scope': 'Named full52 uniform/1..7 fixed-tree T2 storage and arithmetic only; no longer learning, CPU/RSS or quality admission.'}, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
