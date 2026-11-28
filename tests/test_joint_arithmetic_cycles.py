"""Actual arithmetic recorder under synthetic clocks and independent schedules."""
import json
import os
from pathlib import Path
import unittest
from tests.test_joint_cycle_reference import capture as earlier_capture
from tests.test_native_lazy_joint import unchanged
from tests.virtual_frozen_run_control import run_bounded_child
from tests.virtual_joint_arithmetic_cycle_reference import COUNTS, FAMILIES, decode, grouped_sequence, numeric_sequence

ROOT = Path(__file__).resolve().parents[1]
EXTRA = ('tests/test_joint_arithmetic_cycles.py', 'tests/virtual_joint_arithmetic_cycle_reference.py',
         'scripts/benchmark_joint_arithmetic_cycles.py')


def capture(executable, target, output): return earlier_capture(executable, target, output, extra=EXTRA)


class ArithmeticScheduleTests(unittest.TestCase):
    def test_numeric_rule_schedule_covers_every_family_once_across_offsets(self):
        sequence = numeric_sequence(); self.assertEqual(len(sequence), 2513)
        self.assertEqual(tuple(sequence.count(i) for i in range(4)), COUNTS)
        sampled = [[(sequence * 2)[offset::32].count(i) for i in range(4)] for offset in range(32)]
        self.assertEqual(tuple(sum(row[i] for row in sampled) for i in range(4)), tuple(2 * n for n in COUNTS))
        self.assertEqual([sum(row) for row in sampled], [158] * 2 + [157] * 30)


@unittest.skipUnless(os.environ.get('OPENPOKER_NATIVE_ARITHMETIC_CYCLE_EXE'), 'explicit source-built arithmetic recorder controls required')
class NativeArithmeticRecorderTests(unittest.TestCase):
    def test_all_offsets_and_exact_balanced_body_accounting(self):
        executable = Path(os.environ['OPENPOKER_NATIVE_ARITHMETIC_CYCLE_EXE']).resolve()
        output = Path(os.environ['OPENPOKER_NATIVE_ARITHMETIC_CYCLE_DIR']).resolve(); target = 'joint-arithmetic-cycle-controls'
        identity, head, source = capture(executable, target, output)
        receipt = run_bounded_child([str(executable)], b'', output / 'native', stdout_limit=131072, timeout=30)
        self.assertEqual((receipt['status'], receipt['actual_exit_observed'], receipt['returncode'], receipt['failures']), ('exited', True, 0, []))
        self.assertEqual((output / 'native/stderr.bin').read_bytes(), b'')
        lines = (output / 'native/stdout.bin').read_bytes().splitlines(keepends=True); self.assertEqual(len(lines), 47)
        reports = []; bodies = (3000, 5000, 7000, 11000)
        for offset in range(32):
            report = decode(lines[offset], offset, synthetic=True, sequence=grouped_sequence()); reports.append(report)
            value = report['raw']; counts = value['epoch_sampled_calls']; cycles = value['epoch_sampled_helper_cycles']
            self.assertEqual(value['empty_pair_cycles'], [1000] * 16)
            for epoch in range(2):
                for family in range(4): self.assertEqual(cycles[epoch][family], counts[epoch][family] * (bodies[family] + 1000))
            self.assertEqual(report['empirical_walk_cycles_proxy'], 27918000)
            self.assertEqual(value['events'][-1][2], 27918000 + 1000 * (value['cycle_queries'] - 1))
            for key, changed in (('cycle_queries', 372), ('units', 'nanoseconds'), ('families', list(reversed(FAMILIES)))):
                altered = dict(value); altered[key] = changed
                with self.assertRaises(ValueError):
                    decode(b'JOINT_ARITHMETIC_CYCLES ' + json.dumps(altered).encode() + b'\n', offset, synthetic=True, sequence=grouped_sequence())
        for family, name in enumerate(FAMILIES):
            self.assertEqual(sum(r['empirical_full_helper_cycles_proxies'][name] for r in reports), 32 * 2 * COUNTS[family] * bodies[family])
        labels = ('offset', 'lazy', 'missing-observer', 'nested-install', 'wrong-phase', 'read-context', 'incomplete',
                  'foreign-thread', 'clock-failure', 'nonmonotone', 'invalid-family', 'nested-scope', 'double-close', 'abandoned')
        self.assertEqual([line.rstrip(b'\r\n') for line in lines[32:]],
                         [*(('GUARD ' + label + ' PASS').encode() for label in labels), b'JOINT_ARITHMETIC_CYCLE_GUARDS_V1 PASS 14'])
        unchanged(executable, target, identity, head, source)
        (output / 'result.json').write_text(json.dumps({'status': 'arithmetic-recorder-synthetic-census-exact', 'offsets': reports,
            'native_guards': 14, 'parser_mutations': 96, 'observed_native_calls': 1,
            'scope': 'Actual recorder with grouped synthetic calls; independent numeric-rule schedule checked separately. No measured solver CPU or quality.'}, indent=2) + '\n')


if __name__ == '__main__': unittest.main()
