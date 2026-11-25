"""Portable protocol and real-recorder synthetic clock controls."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import unittest

from tests.test_native_lazy_joint import capture as earlier_capture, unchanged
from tests.virtual_frozen_run_control import run_bounded_child
from tests.virtual_joint_cycle_reference import decode

ROOT = Path(__file__).resolve().parents[1]
EXTRA = ('tests/virtual_joint_cycle_reference.py', 'tests/test_joint_cycle_reference.py',
         'scripts/benchmark_joint_cycles.py')


def capture(executable, target, output, *, extra=()):
    identity, head, source = earlier_capture(executable, target, output)
    names = (*EXTRA, *extra)
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all', '--', *names], cwd=ROOT):
        raise ValueError('cycle controller source must be committed clean')
    record_path = output / 'source-identity.json'; record = json.loads(record_path.read_bytes())
    for name in names:
        raw = (ROOT / name).read_bytes(); source[name] = raw
        path = output / 'source' / name; path.parent.mkdir(exist_ok=True, parents=True); path.write_bytes(raw)
        record['raw_sha256'][name] = sha256(raw).hexdigest()
        record['committed_blobs'][name] = subprocess.check_output(['git', 'rev-parse', head + ':' + name], cwd=ROOT, text=True).strip()
    if len(source) > 128 or sum(map(len, source.values())) > 64 << 20:
        raise ValueError('cycle source closure cap')
    record_path.write_text(json.dumps(record, indent=2) + '\n')
    return identity, head, source


@unittest.skipUnless(os.environ.get('OPENPOKER_NATIVE_JOINT_CYCLE_CONTROLS_EXE'), 'explicit source-built recorder controls required')
class NativeJointCycleTests(unittest.TestCase):
    def test_complete_synthetic_cycle_census_and_failures(self):
        executable = Path(os.environ['OPENPOKER_NATIVE_JOINT_CYCLE_CONTROLS_EXE']).resolve()
        output = Path(os.environ['OPENPOKER_NATIVE_JOINT_CYCLE_CONTROLS_DIR']).resolve(); target = 'joint-thread-cycle-controls'
        identity, head, source = capture(executable, target, output)
        receipt = run_bounded_child([str(executable)], b'', output / 'native', stdout_limit=32768, timeout=30)
        self.assertEqual((receipt['status'], receipt['actual_exit_observed'], receipt['returncode'], receipt['failures']), ('exited', True, 0, []))
        self.assertEqual((output / 'native/stderr.bin').read_bytes(), b'')
        lines = (output / 'native/stdout.bin').read_bytes().splitlines(keepends=True)
        self.assertEqual(len(lines), 18)
        reports = []
        for offset, raw in enumerate(lines[:4]):
            report = decode(raw, offset, synthetic=True); reports.append(report)
            self.assertEqual(report['raw']['empty_pair_cycles'], [1000] * 16)
            self.assertEqual(report['raw']['events'][-1][2], 6564000)
            self.assertEqual(report['sampled_read_cycles'], 1736000)
            self.assertEqual(sum(report['walk_cycles']), 6512000)
            self.assertEqual(report['empirical_full_read_cycles_proxy'], 6076000)
            self.assertEqual(report['empirical_walk_cycles_proxy'], 6076000)
            self.assertEqual(report['empirical_read_share_proxy'], 1)
            for key, changed in (('cycle_queries', 490), ('epoch_sampled_calls', [108, 109]),
                                 ('units', 'nanoseconds'), ('extra_work', 524289)):
                value = json.loads(raw[len(b'JOINT_THREAD_CYCLES '):]); value[key] = changed
                # Offsets 2/3 legitimately have [108,109]; force the opposite.
                if key == 'epoch_sampled_calls': value[key] = [109,108] if offset >= 2 else [108,109]
                with self.assertRaises(ValueError):
                    decode(b'JOINT_THREAD_CYCLES ' + json.dumps(value).encode() + b'\n', offset, synthetic=True)
        labels = ('offset', 'missing-observer', 'nested-install', 'wrong-phase', 'read-context', 'incomplete',
                  'foreign-thread', 'clock-failure', 'nonmonotone', 'nested-read', 'phase-during-read', 'double-close', 'abandoned')
        self.assertEqual([line.rstrip(b'\r\n') for line in lines[4:]],
                         [*(('GUARD ' + label + ' PASS').encode() for label in labels), b'JOINT_THREAD_CYCLE_GUARDS_V1 PASS 13'])
        unchanged(executable, target, identity, head, source)
        (output / 'result.json').write_text(json.dumps({'status': 'synthetic-real-recorder-census-exact',
            'offsets': reports, 'native_guards': 13, 'parser_mutations': 16, 'observed_native_calls': 1,
            'scope': 'Synthetic clock exercises the actual recorder and read scope; no solver timing or CPU attribution.'}, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
