"""Adversarial native chance-partition controls independent of the adapter."""
import os
import subprocess
import unittest

from pokerlab.native_selected_operator import wire
from pokerlab.postflop_solver import _Chance
from pokerlab.river_tree import _Terminal
from pokerlab.selected_runout_operator import SelectedRunoutOperator

EXE = os.environ.get('OPENPOKER_NATIVE_SELECTED_EXE')


def payload():
    operator = SelectedRunoutOperator('AsAd', 'KsKd',
                                      ('2c3c4d7h8h', '5c6c7d8h9h'))
    operator.pot = 1.0
    root = _Chance((), {'2c3c4d': _Terminal('showdown', (1, 1)),
                        '5c6c7d': _Terminal('showdown', (1, 1))})
    raw, _, _ = wire(root, {}, 10, operator=operator)
    return raw.decode().splitlines()


@unittest.skipUnless(EXE, 'Native executable required')
class NativeChancePartitionIndependentTests(unittest.TestCase):
    def run_wire(self, lines):
        return subprocess.run([EXE], input=('\n'.join(lines)+'\n').encode(),
                              capture_output=True, timeout=10)

    def test_duplicate_and_missing_reveals_reject_without_census_mismatch(self):
        valid = payload()
        result = self.run_wire(valid)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Duplicate child prefix: two distinct tree nodes and all original
        # structural counters remain intact, but the second flop is omitted.
        duplicate = valid.copy()
        first, second = duplicate[13].split(), duplicate[14].split()
        second[2] = first[2]
        duplicate[14] = ' '.join(second)
        # One child only: make every node, edge and census count consistent;
        # retain the unused valid prefix declaration and remove the other node.
        missing = valid.copy()
        header = missing[1].split()
        header[0], header[1], header[11], header[15] = '2', '1', '1', '1'
        missing[1] = ' '.join(header)
        node = missing[12].split(); node[4] = '1'; missing[12] = ' '.join(node)
        terminal = missing[13].split(); terminal[3] = '1'; missing[13] = ' '.join(terminal)
        del missing[14]
        missing[14] = '1'
        for label, changed in (('duplicate', duplicate), ('missing', missing)):
            with self.subTest(label=label):
                result = self.run_wire(changed)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(b'partition', result.stderr.lower())


if __name__ == '__main__':
    unittest.main()
