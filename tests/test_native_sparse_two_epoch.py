"""Source-frozen changing-policy native walk versus independent exact rules."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts.replay_native_grid_raw import MATH, CONTROLLERS
from tests.test_native_exact_reach import authenticate, sha
from tests.test_native_frozen_grid_raw import case_boards
from tests.virtual_dyadic_training_reference import Fixture
from tests.virtual_frozen_grid_preflight_reference import boards, census
from tests.virtual_grid_update_reference import build_sampled_reference_context
from tests.virtual_native_sparse_two_epoch_reference import verify_sparse_wire
from tests.virtual_sparse_two_epoch_forecast_reference import forecast
from tests.virtual_frozen_run_control import run_bounded_child

ROOT = Path(__file__).resolve().parents[1]
ENV = 'OPENPOKER_NATIVE_SPARSE_TWO_EPOCH_EXE'
OUT = 'OPENPOKER_NATIVE_SPARSE_TWO_EPOCH_DIR'
TARGET = 'virtual-sparse-two-epoch'
SCOPE = 'Uniform PROOF9 two-board sparse signed-regret epochs only; no RNG, convergence, solved quality or wider capacity acceptance.'
NEW_SOURCES = ('tests/virtual_sparse_epoch_reference.py', 'tests/virtual_sparse_two_epoch_reference.py',
               'tests/virtual_sparse_two_epoch_forecast_reference.py',
               'tests/virtual_native_sparse_two_epoch_reference.py', 'tests/test_native_sparse_two_epoch.py',
               'scripts/replay_sparse_two_epoch.py', 'scripts/replay_native_grid_raw.py')


def selectors(fixture, context):
    selected = dict(case_boards(fixture, context))
    a, b = selected['positive-0'], selected['positive-1']
    maximum = max(boards(), key=lambda board: census(board)['supported_rows'] + census(board)['supported_action_slots'])
    return (('different-pairs', (a, b)), ('reversed', (b, a)), ('same-board', (a, a)),
            ('zero-shared-turn', (a, selected['zero-shared-turn'])),
            ('zero-flop-first', (selected['zero-at-flop'], b)),
            ('maximum-stage', (maximum, maximum)))


@unittest.skipUnless(os.environ.get(ENV), 'explicit source-built sparse two-epoch candidate required')
class NativeSparseTwoEpochTests(unittest.TestCase):
    def test_whole_requests_and_fail_closed_selectors(self):
        exe = Path(os.environ[ENV]).resolve()
        identity = authenticate(exe, ROOT, TARGET)
        self.assertEqual(identity[1]['scope'], SCOPE)
        names = sorted(set(identity[1]['source_sha256']) | set(MATH) | set(CONTROLLERS) | set(NEW_SOURCES))
        self.assertLessEqual(len(names), 128)
        self.assertFalse(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all', '--', *names], cwd=ROOT))
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
                target = directory / 'source' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
            (directory / 'source-identity.json').write_text(json.dumps({
                'version': 'native-sparse-two-epoch-sources-v1', 'head': head,
                'raw_sha256': {n: sha256(v).hexdigest() for n, v in source.items()}, 'committed_blobs': tree,
                'python_version': sys.version, 'python_executable_sha256': sha(Path(sys.executable))}, indent=2) + '\n')
            (directory / 'native-build-manifest.json').write_bytes(identity[0])
            (directory / 'native-identity.json').write_text(json.dumps({
                'manifest_sha256': sha256(identity[0]).hexdigest(),
                'executable_sha256': identity[1]['executable_sha256']}) + '\n')
            # Independent complete-domain admission precedes candidate launch.
            budget = forecast()
            self.assertTrue(budget['forecast_passes_caps'])
            fixture = Fixture()
            context = build_sampled_reference_context()
            plan = selectors(fixture, context)
            (directory / 'case-plan.json').write_text(json.dumps({
                'scope': SCOPE, 'cases': plan, 'automatic_retries': 0,
                'per_request_forecast': budget, 'native_requests': len(plan),
                'sum_request_work_forecasts': len(plan) * budget['components']['total_work']}, indent=2) + '\n')

            def command(pair):
                return [str(exe), *[value for board in pair for value in ('uniform', *map(str, board))]]

            def observe(label, args):
                (directory / (label + '.command.json')).write_text(json.dumps(args) + '\n')
                child = directory / label
                outcome = run_bounded_child(args, b'', child, stdout_limit=619152, timeout=180)
                return child, outcome

            results = []
            first = None
            for label, pair in plan:
                child, outcome = observe(label, command(pair))
                self.assertEqual((outcome['status'], outcome['returncode'], outcome['actual_exit_observed']),
                                 ('exited', 0, True), label)
                self.assertEqual((child / 'stderr.bin').read_bytes(), b'', label)
                raw = (child / 'stdout.bin').read_bytes()
                check = verify_sparse_wire(fixture, context, pair, raw)
                (child / 'independent-rows.json').write_text(json.dumps(check, indent=2) + '\n')
                results.append({'case': label, **check})
                if first is None:
                    first = (pair, raw)
            good = command(plan[0][1])
            invalid = {
                'reject-second-law': good[:7] + ['river_weighted', *good[8:]],
                'reject-second-duplicate': good[:-1] + [good[-2]],
                'reject-second-foreign': good[:8] + ['0', *good[9:]],
                'reject-second-unsorted': good[:8] + [good[9], good[8], *good[10:]],
                'reject-arity': good[:-1],
                'reject-third-selector': good + good[1:7],
                'reject-negative-card': good[:2] + ['-1', *good[3:]],
            }
            for label, args in invalid.items():
                child, outcome = observe(label, args)
                self.assertEqual((outcome['status'], outcome['returncode'], outcome['actual_exit_observed']),
                                 ('exited', 2, True), label)
                self.assertEqual((child / 'stdout.bin').read_bytes(), b'', label)
            # Numerical corruption has valid framing and is rejected by the
            # independent rules, beyond transport/process digest checks.
            pair, raw = first
            bad = bytearray(raw)
            bad[336 + 136] ^= 1
            with self.assertRaises(ValueError):
                verify_sparse_wire(fixture, context, pair, bytes(bad))
            with self.assertRaises(ValueError):
                verify_sparse_wire(fixture, context, pair, raw[:-1])
            (directory / 'matrix-results.json').write_text(json.dumps({
                'status': 'all-two-epoch-rows-exact', 'cases': results,
                'successful_observed_requests': len(plan), 'rejected_observed_requests': len(invalid),
                'epochs_per_request': 2, 'rng_calls': 0, 'scope': SCOPE}, indent=2) + '\n')
        self.assertEqual(authenticate(exe, ROOT, TARGET), identity)
        self.assertEqual({name: (ROOT / name).read_bytes() for name in names}, source)


if __name__ == '__main__':
    unittest.main()
