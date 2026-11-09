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

    def test_bounded_lifecycle_integer_oracle(self):
        lifecycle = [line.split() for line in self.lines if line.startswith('LIFECYCLE ')]
        self.assertEqual([x[2] for x in lifecycle if x[1]=='GUARD'],
                         ['io-cap','flush-cap','missing-row','early-export','max-sweeps','second-export'])
        lines = iter(x for x in lifecycle if x[1]!='GUARD')
        for total in (1, 2, 3, 4, 8):
            regrets = [None] * 4
            averages = [None] * 4
            profiles = []
            for sweep in range(total):
                profiles.append([])
                for row in range(4):
                    tag, kind, n, generation, index, count, *payload = next(lines)
                    count = int(count)
                    self.assertEqual((tag, kind, int(n), int(generation), int(index)),
                                     ('LIFECYCLE', 'ROW', total, sweep, row))
                    units = list(map(int, payload[:-1:2]))
                    coefficients = list(map(int, payload[1:-1:2]))
                    if regrets[row] is None:
                        regrets[row] = [0] * count
                        averages[row] = [0] * count
                    self.assertEqual(units, allocation(regrets[row])[0])
                    profiles[-1].append(units)
                    self.assertEqual(coefficients, [(3*a+2*row+5*sweep)%11-5 for a in range(count)])
                    values = [coefficient << (190+52) for coefficient in coefficients]
                    mixed = sum(unit * value for unit, value in zip(units, values)) // Q
                    self.assertEqual(int(payload[-1]), mixed)
                    regrets[row] = [max(0, old+value-mixed) for old,value in zip(regrets[row],values)]
                    averages[row] = [old+(unit<<190) for old,unit in zip(averages[row],units)]
                tag, kind, n, generation, count, *words = next(lines)
                self.assertEqual((tag,kind,int(n),int(generation)), ('LIFECYCLE','IMAGE',total,sweep))
                words = list(map(int, words))
                self.assertEqual(len(words), int(count))
                expected = []
                for family in (averages, regrets):
                    for row_values in family:
                        for value in row_values:
                            compact = value >> 190
                            expected.extend((compact & ((1<<64)-1), compact >> 64))
                self.assertEqual(words, expected)
            for sweep, profile in enumerate(profiles):
                tag, kind, n, generation, *fields = next(lines)
                self.assertEqual((tag,kind,int(n),int(generation)), ('LIFECYCLE','SPILL',total,sweep))
                uniform = pure = mixed = extent = mixed_words = written = offset = 0
                for units in profile:
                    size = len(units)
                    canonical = [Q//size + (i < Q%size) for i in range(size)]
                    offset += size - 1
                    if units == canonical:
                        uniform += 1
                    elif Q in units:
                        pure += 1
                    else:
                        mixed += 1
                        extent = offset
                        written += size - 1
                        mixed_words += 2 * (size - 1)
                self.assertEqual(list(map(int, fields)),
                                 [uniform,pure,mixed,extent,written,8,2*mixed,mixed_words])
            for row in range(4):
                tag, kind, n, count, *units = next(lines)
                expected, _ = allocation(averages[row], average=True)
                self.assertEqual((tag,kind,int(n),int(count),list(map(int,units))),
                                 ('LIFECYCLE','EXPORT',total,len(expected),expected))
            tag,kind,n,*flags = next(lines)
            self.assertEqual((tag,kind,int(n),list(map(int,flags))),
                             ('LIFECYCLE','FLAGS',total,[int(not any(x)) for x in averages]))
            self.assertEqual(next(lines), ['LIFECYCLE','DONE',str(total)])
        self.assertEqual(list(lines), [])

    def test_proof10_phase_payload_breakdown_and_legacy_parity(self):
        rows=[line.split() for line in self.lines if line.startswith('PHASE_PAYLOAD ')]
        self.assertEqual(len(rows),1)
        _, old_entries, old_bits, new_entries, new_bits=rows[0]
        self.assertEqual((int(old_entries),int(new_entries)),(200_886,200_886))
        self.assertEqual(int(old_bits),1_168_510_748)
        self.assertEqual(int(new_bits),8*(16_384+36_864+(410+388)*16+591_008+
                                          119_196+1_024+88+256*11*8))
        self.assertEqual(int(new_bits),6_398_880)
        self.assertIn('PHASE_PAYLOAD_GUARDS PASS',self.lines)

    def test_two_sweeps_exact_mix_committed_masses_and_tagged_export(self):
        reference = build_reference_template(_template_case())
        root = reference.nodes[reference.root]
        nodes = (root, root, reference.nodes[root.edges[1].child], reference.nodes[root.edges[2].child])
        holdings = (0, 1, 0, 0)
        menus = [tuple(edge.token for edge in node.edges) for node in nodes]
        self.assertEqual(self.lines[0], 'VIRTUAL_DYADIC_STATE_V1')
        separate_controls = ('REJECT ', 'ACTION_STORAGE ', 'PACKED_AVERAGE ', 'PACKED_DUAL ',
                             'SCALED_AVERAGE ', 'PAGED_IMAGE ', 'LIFECYCLE ', 'PROOF9_T4_GUARDS ',
                             'PROOF9_Q32_STATE ', 'PROOF9_Q32_GUARDS ', 'PROOF9_Q32_PAGER ',
                             'PHASE_PAYLOAD ' , 'PHASE_PAYLOAD_GUARDS ')
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

    def test_proof9_t4_pager_profile_and_storage_delta(self):
        self.assertEqual([line for line in self.lines if line.startswith('PROOF9_T4_GUARDS ')],
                         ['PROOF9_T4_GUARDS 7 2 8 512'])

    def test_proof9_q32_state_storage_and_page_crossing(self):
        self.assertEqual([line.split() for line in self.lines if line.startswith('PROOF9_Q32_STATE ')],
                         [['PROOF9_Q32_STATE','106399','241969528','PASS']])
        pager=[line.split() for line in self.lines if line.startswith('PROOF9_Q32_PAGER ')]
        self.assertEqual(len(pager),1)
        self.assertEqual(pager[0][-1],'PASS')
        self.assertEqual((int(pager[0][1]),int(pager[0][2]),int(pager[0][3])),(16384,4,151))
        self.assertIn('PROOF9_Q32_GUARDS 8 PASS',self.lines)

    def test_paged_images_preserve_the_committed_sweep_until_complete(self):
        self.assertEqual([line for line in self.lines if line.startswith('PAGED_IMAGE ')],
                         ['PAGED_IMAGE exact_transaction', 'PAGED_IMAGE buffered_transaction',
                          'PAGED_IMAGE virtual_initial_epoch',
                          'PAGED_IMAGE compact_directory', 'PAGED_IMAGE ordered_directory',
                          'PAGED_IMAGE paged_directory', 'PAGED_IMAGE row_coverage', 'PAGED_IMAGE shared_policy'])

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
