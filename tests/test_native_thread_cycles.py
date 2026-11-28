"""Source-authenticated own-thread API probe; no solver/performance acceptance."""
from hashlib import sha256
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import unittest

from tests.test_native_exact_reach import authenticate
from tests.virtual_frozen_run_control import run_bounded_child

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('OPENPOKER_NATIVE_THREAD_CYCLE_EXE'), 'explicit Windows own-thread counter probe required')
class NativeThreadCycleProbeTests(unittest.TestCase):
    def test_current_thread_counter_shape_and_original_exit(self):
        executable = Path(os.environ['OPENPOKER_NATIVE_THREAD_CYCLE_EXE']).resolve()
        target = 'current-thread-cycle-probe'; identity = authenticate(executable, ROOT, target)
        names = sorted({*identity[1]['source_sha256'], 'tests/test_native_thread_cycles.py',
                        'tests/test_native_exact_reach.py', 'tests/virtual_frozen_run_control.py'})
        self.assertEqual(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all', '--', *names], cwd=ROOT), b'')
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        source = {name: (ROOT / name).read_bytes() for name in names}
        output = Path(os.environ['OPENPOKER_NATIVE_THREAD_CYCLE_DIR']).resolve()
        self.assertEqual(output.parent, ROOT.parent.resolve()); output.mkdir(exist_ok=False)
        for name, raw in source.items():
            path = output / 'source' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        (output / 'source-identity.json').write_text(json.dumps({'head': head, 'python_version': sys.version,
            'raw_sha256': {name: sha256(raw).hexdigest() for name, raw in source.items()}}, indent=2) + '\n')
        (output / 'native-build-manifest.json').write_bytes(identity[0])
        process = run_bounded_child([str(executable)], b'', output / 'native', stdout_limit=32768, timeout=30)
        self.assertEqual((process['status'], process['actual_exit_observed'], process['returncode'], process['failures']), ('exited', True, 0, []))
        self.assertEqual((output / 'native/stderr.bin').read_bytes(), b'')
        saved = json.loads((output / 'native/stdout.bin').read_bytes())
        self.assertEqual(saved['schema'], 'current-thread-cycle-probe-v1'); self.assertEqual(saved['units'], 'cpu_clock_cycles')
        self.assertEqual((saved['queries'], saved['maximum_queries'], saved['pair_count'], saved['warmup_queries'], saved['measured_queries']),
                         (2082, 4096, 1024, 32, 2049))
        self.assertEqual(saved['limits'], {'entries': 65536, 'payload_bits': 1048576, 'stdout_bytes': 32768})
        self.assertFalse(saved['solver_constructed']); self.assertFalse(saved['system_profiler_started'])
        deltas = saved['pair_deltas']; self.assertEqual(len(deltas), 1024)
        self.assertTrue(all(type(value) is int and 0 <= value < 1 << 64 for value in deltas))
        self.assertTrue(type(saved['thread_id']) is int and saved['thread_id'] > 0)
        self.assertTrue(0 <= saved['first'] <= saved['last'] < 1 << 64 and saved['wall_nanoseconds'] > 0)
        self.assertLessEqual(sum(deltas), saved['last'] - saved['first'])
        self.assertEqual(authenticate(executable, ROOT, target), identity)
        self.assertEqual(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), head)
        self.assertTrue(all((ROOT / name).read_bytes() == raw for name, raw in source.items()))
        report = {'status': 'own-thread-counter-capability-observed',
            'median_pair_delta_cycles': statistics.median(deltas), 'minimum_pair_delta_cycles': min(deltas),
            'maximum_pair_delta_cycles': max(deltas), 'probe_wall_ns_per_measured_query': saved['wall_nanoseconds'] / saved['measured_queries'],
            'observed_native_calls': 1, 'quality_gate': None,
            'scope': 'One current-thread API microprobe. Wall measurement includes loop/storage overhead; cycles are not converted to time. No solver, system collection or profiling acceptance.'}
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
