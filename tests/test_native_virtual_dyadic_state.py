"""Exact synthetic row-state feedback and failure controls."""
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests.test_native_dyadic_policy import Q, allocation
from tests.test_native_exact_reach import authenticate, sha
from tests.virtual_betting_template_reference import build_reference_template
from tests.virtual_frozen_run_control import run_bounded_child
from tests.virtual_frozen_update_reference import _template_case


ROOT = Path(__file__).resolve().parents[1]
EXE_ENV = 'OPENPOKER_NATIVE_VIRTUAL_DYADIC_STATE_EXE'
OUTPUT_ENV = 'OPENPOKER_NATIVE_VIRTUAL_DYADIC_STATE_CONTROL_DIR'
GUARDS = (
    'raised_work', 'raised_bits', 'raised_entries', 'raised_payload',
    'zero_sweeps', 'unadmitted_mix_width', 'work_partition',
    'negative_denominator', 'wide_denominator', 'entry_footprint',
    'payload_footprint', 'actor', 'holding', 'foreign_cursor', 'changed_menu',
    'slot_capacity', 'incomplete_freeze', 'incomplete_commit', 'duplicate_stage',
    'nonmember_grid', 'negative_average', 'cumulative_width', 'oversized_input',
    'state_exhaustion', 'quantizer_exhaustion', 'early_export', 'second_export',
    'catalog_dimensions', 'catalog_footprint', 'catalog_key', 'catalog_mode',
    'catalog_requires_key', 'catalog_menu_change', 'catalog_token_capacity', 'catalog_invalid_token',
    'sealed_lookup_after_freeze', 'sealed_generic_registration', 'sealed_foreign_cursor',
    'sealed_invalid_shift', 'sealed_nondecision_cursor',
    'packed_nondivisible', 'packed_cumulative_width', 'packed_limb_census',
    'scaled_wrong_shift', 'scaled_width', 'scaled_dense_mode', 'packed_regret_nondivisible',
)


@unittest.skipUnless(os.environ.get(EXE_ENV), 'explicit source-built dyadic state controls required')
class NativeVirtualDyadicStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        exe = Path(os.environ[EXE_ENV]).resolve()
        identity = authenticate(exe, ROOT, 'virtual-dyadic-state-controls')
        target = os.environ.get(OUTPUT_ENV)
        if target is None:
            temporary = TemporaryDirectory(dir=ROOT.parent)
            cls.addClassCleanup(temporary.cleanup)
            target = Path(temporary.name) / 'observed'
        output = Path(target)
        before = sha(exe)
        observed = run_bounded_child([str(exe),str(output/'page-controls')], b'', output, stdout_limit=2_100_000)
        after = sha(exe)
        (output/'native-identity.json').write_text(json.dumps({
            'before_sha256': before, 'after_sha256': after,
            'manifest_sha256': hashlib.sha256(identity[0]).hexdigest(),
        })+'\n')
        if (before, after) != (identity[1]['executable_sha256'],)*2:
            raise AssertionError('state executable changed during launch')
        if authenticate(exe, ROOT, 'virtual-dyadic-state-controls') != identity:
            raise AssertionError('state build closure changed during controls')
        stderr = (output/'stderr.bin').read_bytes()
        if (observed['status'], observed['returncode'], observed['actual_exit_observed']) != ('exited', 0, True) or stderr:
            raise AssertionError(f'state controls process failed: {stderr!r}')
        cls.lines = (output/'stdout.bin').read_text(encoding='ascii').splitlines()

    def test_two_sweeps_exact_mix_committed_masses_and_tagged_export(self):
        reference = build_reference_template(_template_case())
        root = reference.nodes[reference.root]
        nodes = (root, root, reference.nodes[root.edges[1].child], reference.nodes[root.edges[2].child])
        holdings = (0, 1, 0, 0)
        menus = [tuple(edge.token for edge in node.edges) for node in nodes]
        self.assertEqual(self.lines[0], 'VIRTUAL_DYADIC_STATE_V1')
        separate_controls = ('REJECT ', 'ACTION_STORAGE ', 'PACKED_AVERAGE ', 'PACKED_DUAL ',
                             'SCALED_AVERAGE ', 'PAGED_IMAGE ')
        rows = iter(line.split() for line in self.lines[1:] if not line.startswith(separate_controls))
        for shift in (104, 780, 1800):
            case, exponent, denominator = next(rows)
            self.assertEqual((case, int(exponent), int(denominator)), ('CASE', shift, 580 << (shift+100)))
            offset, keys = 0, []
            for row, (node, menu, holding) in enumerate(zip(nodes, menus, holdings)):
                tag, index, key, actor, original, base, count, *tokens = next(rows)
                self.assertEqual((tag, int(index), int(actor), int(original), int(base), int(count), tuple(tokens)),
                                 ('KEY', row, node.state.player, holding, offset, len(menu), menu))
                keys.append(int(key))
                offset += len(menu)
            self.assertEqual(keys[0], keys[1])
            self.assertEqual(len(set(keys)), 3)
            regrets = [[0]*len(menu) for menu in menus]
            masses = [[0]*len(menu) for menu in menus]
            profiles = []
            for sweep in range(2):
                profiles.append([])
                for row, menu in enumerate(menus):
                    tag, time, index, count, *rest = next(rows)
                    count = int(count)
                    self.assertEqual((tag, int(time), int(index), count, len(rest)), ('ROW', sweep, row, len(menu), 3*len(menu)+1))
                    payload = list(map(int, rest))
                    units = payload[:-1:3]
                    values = payload[1:-1:3]
                    increments = payload[2:-1:3]
                    expected_units, _ = allocation(regrets[row])
                    self.assertEqual(units, expected_units)
                    self.assertEqual(sum(units), Q)
                    profiles[sweep].append(units)
                    coefficients = [(5*(a+row+1) if sweep else 3*(a+2*row+1))%11 - 5 for a in range(count)]
                    sign = -1 if (sweep+row)%2 else 1
                    self.assertEqual(values, [coefficient*sign*(1 << shift) for coefficient in coefficients])
                    self.assertEqual(increments, [0 if row==1 else Q*(sweep+1)*(row+1)*unit for unit in units])
                    mixed = sum(Fraction(unit, Q)*value for unit, value in zip(units, values))
                    self.assertEqual(mixed.denominator, 1)
                    self.assertEqual(payload[-1], mixed.numerator)
                    regrets[row] = [max(0, old+value-mixed.numerator) for old, value in zip(regrets[row], values)]
                    masses[row] = [old+new for old, new in zip(masses[row], increments)]
                for row, menu in enumerate(menus):
                    tag, time, index, count, *pairs = next(rows)
                    self.assertEqual((tag, int(time), int(index), int(count), len(pairs)), ('COMMIT', sweep, row, len(menu), 2*len(menu)))
                    self.assertEqual(list(map(int, pairs[::2])), regrets[row])
                    self.assertEqual(list(map(int, pairs[1::2])), masses[row])
            self.assertNotEqual(profiles[0], profiles[1])
            self.assertTrue(any(regrets[1]), 'zero own average reach must preserve counterfactual update')
            for row, menu in enumerate(menus):
                tag, index, count, fallback, *pairs = next(rows)
                units, total = allocation(masses[row], average=True)
                self.assertEqual((tag, int(index), int(count), int(fallback), len(pairs)),
                                 ('EXPORT', row, len(menu), int(total==0), 2*len(menu)))
                self.assertEqual(list(map(int, pairs[::2])), units)
                self.assertEqual(list(map(int, pairs[1::2])), masses[row])
            tag, *fields = next(rows)
            self.assertEqual(tag, 'RECEIPT')
            work, state_work, quantizer_work, entries, payload, input_bits, arithmetic_bits = map(int, fields)
            self.assertEqual(work, state_work+quantizer_work)
            self.assertTrue(0 < state_work <= 10_000_000 and 0 < quantizer_work <= 20_000_000)
            self.assertTrue(0 < entries <= 2_000_000 and 0 < payload <= 1 << 30)
            self.assertTrue(shift+110 <= input_bits <= shift+256)
            self.assertTrue(input_bits <= arithmetic_bits <= shift+314)
        self.assertEqual(next(rows), ['END'])
        self.assertIsNone(next(rows, None))

    def test_guard_inventory_and_closed_partial_updates(self):
        self.assertEqual([line.split()[1] for line in self.lines if line.startswith('REJECT ')], list(GUARDS))

    def test_paged_images_preserve_the_committed_sweep_until_complete(self):
        self.assertEqual([line for line in self.lines if line.startswith('PAGED_IMAGE ')],
                         ['PAGED_IMAGE exact_transaction', 'PAGED_IMAGE buffered_transaction',
                          'PAGED_IMAGE virtual_initial_epoch',
                          'PAGED_IMAGE compact_directory', 'PAGED_IMAGE ordered_directory',
                          'PAGED_IMAGE row_coverage'])

    def test_packed_average_matches_dense_feedback(self):
        self.assertEqual([line for line in self.lines if line.startswith('PACKED_AVERAGE ')],
                         ['PACKED_AVERAGE exact_feedback'])

    def test_dual_packed_regrets_and_averages_match_dense_feedback(self):
        self.assertEqual([line for line in self.lines if line.startswith('PACKED_DUAL ')],
                         ['PACKED_DUAL exact_feedback'])

    def test_already_scaled_packed_averages_match_dense_and_raw_feedback(self):
        self.assertEqual([line for line in self.lines if line.startswith('SCALED_AVERAGE ')],
                         ['SCALED_AVERAGE exact_feedback'])

    def test_owned_menu_catalog_reduces_exact_sized_action_arrays(self):
        records = [line.split()[1:] for line in self.lines if line.startswith('ACTION_STORAGE ')]
        self.assertEqual([record[0] for record in records], ['PROOF9', 'SMALL'])
        for record, shape in zip(records, [(58164, 410, 388), (8, 4, 2)]):
            original, compact, keys, slot_bytes, key_bytes, before, after = map(int, record[1:])
            self.assertEqual((original, compact, keys), shape)
            self.assertEqual((before, after), (original*slot_bytes, compact*slot_bytes+keys*key_bytes))
            self.assertLess(after, before)


if __name__ == '__main__':
    unittest.main()
