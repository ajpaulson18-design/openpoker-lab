"""Independent saved-value census for the named packed-policy shortcut."""
from pathlib import Path
import unittest

from scripts.verify_virtual_dyadic_training import (
    check_packed_policy_ledger, packed_policy_schedule, replay,
)


class PackedPolicyReceiptTests(unittest.TestCase):
    def schedule(self, values, *, shift=0, field=0):
        return packed_policy_schedule({'row': tuple(values)}, [('row', len(values))],
                                      [(shift, shift)], field)

    def test_zero_and_pure_rows_scan_every_retained_limb_without_imports(self):
        for values, kind in (((0, 0, 0, 0), 'zero_rows'),
                             ((7, 0, 0, 0), 'pure_rows'),
                             ((0, 0, 0, 7), 'pure_rows')):
            with self.subTest(values=values):
                self.assertEqual(self.schedule(values), {
                    'rows': 1, 'zero_rows': int(kind == 'zero_rows'),
                    'pure_rows': int(kind == 'pure_rows'), 'equal_rows': 0,
                    'mixed_rows': 0, 'words_scanned': 44,
                    'imported_slots': 0, 'scan_work': 208})

    def test_equal_ties_cover_positive_subsets_and_full_support(self):
        for values in ((3, 3), (0, 3, 3), (3, 0, 3, 0), (3, 3, 3, 3)):
            with self.subTest(values=values):
                result = self.schedule(values)
                self.assertEqual((result['equal_rows'], result['mixed_rows'],
                                  result['imported_slots']), (1, 0, 0))

    def test_mixed_rows_import_the_entire_menu_including_zero_slots(self):
        for values in ((2, 3), (0, 3, 2), (3, 3, 0, 2)):
            with self.subTest(values=values):
                result = self.schedule(values)
                self.assertEqual((result['equal_rows'], result['mixed_rows'],
                                  result['imported_slots']), (0, 1, len(values)))

    def test_exact_shift_and_fixed_width_schedule_in_both_fields(self):
        ordered = [('average', 3), ('regret', 2)]
        scales = [(580, 579), (643, 0)]
        values = {'average': (0, 1 << 580, 1 << 580),
                  'regret': (1 << 643, 0)}
        average = packed_policy_schedule(values, ordered, scales, 0)
        regret = packed_policy_schedule(values, ordered, scales, 1)
        self.assertEqual((average['words_scanned'], average['scan_work']), (5, 72))
        self.assertEqual((regret['words_scanned'], regret['scan_work']), (28, 164))
        for result in (average, regret):
            self.assertEqual((result['rows'], result['pure_rows'], result['equal_rows'],
                              result['imported_slots']), (2, 1, 1, 0))

    def test_stride_boundaries_and_maximum_value_are_exact(self):
        for shift, stride in ((0, 11), (3, 11), (4, 10), (579, 2), (580, 1), (643, 1)):
            with self.subTest(shift=shift):
                result = self.schedule((0, ((1 << (644-shift))-1) << shift), shift=shift)
                self.assertEqual(result['words_scanned'], 2*stride)
                self.assertEqual(result['scan_work'], 16+8*(stride+1))
                self.assertEqual(result['pure_rows'], 1)

    def test_nonnegative_exact_scale_and_width_guards(self):
        for values, shift in (((-1, 0), 0), ((True, 0), 0), ((1.0, 0), 0),
                              ((1, 0), 1), ((1 << 644, 0), 0)):
            with self.subTest(values=values, shift=shift), self.assertRaises(ValueError):
                self.schedule(values, shift=shift)
        for shift in (-1, 644, True, 1.0):
            with self.subTest(shift=shift), self.assertRaises(ValueError):
                self.schedule((0, 0), shift=shift)
        for field in (-1, 2, True, 0.0):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.schedule((0, 0), field=field)

    def test_menu_and_row_inventory_guards(self):
        for ordered, scales in (([('row', 3)], [(0, 0)]),
                                ([('row', 0)], [(0, 0)]),
                                ([('row', 1)], [(0, 0)]),
                                ([('row', 5)], [(0, 0)]),
                                ([('row', True)], [(0, 0)]),
                                ([('row', 2)], [])):
            with self.subTest(ordered=ordered, scales=scales), self.assertRaises(ValueError):
                packed_policy_schedule({'row': (0, 0)}, ordered, scales, 0)

    def test_named_forecast_adds_full_scan_without_retiring_old_work(self):
        receipt = dict(rows=238_392, words_scanned=2_962_722, scan_work=17_913_688)
        arguments = (119_196, 281_066, 2_962_722*8, 335_766_944)
        check_packed_policy_ledger(receipt, *arguments)
        for field in receipt:
            bad = dict(receipt)
            bad[field] += 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                check_packed_policy_ledger(bad, *arguments)
        for index in range(len(arguments)):
            bad = list(arguments)
            bad[index] += 8 if index == 2 else 1
            with self.subTest(argument=index), self.assertRaises(ValueError):
                check_packed_policy_ledger(receipt, *bad)
        with self.assertRaises(ValueError):
            check_packed_policy_ledger(receipt, *arguments[:-1], 317_853_256)

    def test_packed_selector_rejects_invalid_types_and_non_named_lifecycles(self):
        options = dict(paired=True, rank_sets=True, ten_card=True,
                       checkpoint_digests=['0'*64]*2, count_policy_divisions=True,
                       phase_payload=True, row_batched=True, indexed_cache=True,
                       complement=True, equal_quantizer=True, zero_policy_bootstrap=True,
                       first_regret_bound=True, pair_complement=True, packed_policy=True)
        for field, value in (('packed_policy', 1), ('packed_policy', None),
                             ('pair_complement', False), ('first_regret_bound', False),
                             ('ten_card', False), ('ten_card', 1), ('proof9_t3', True),
                             ('proof9_t4', True), ('proof9_quality32', True),
                             ('proof9_linear32', True)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                replay(Path('missing-packed-policy.bin'), '0'*64, **dict(options, **{field: value}))


if __name__ == '__main__':
    unittest.main()
