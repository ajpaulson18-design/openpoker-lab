"""Independent controls for the structural carrier induction and its limits."""
from fractions import Fraction
from itertools import product
import unittest
from tests.role_row_depth_reference import depths, convert, matching


class RowDepthControls(unittest.TestCase):
    def test_selected_opponent_and_own_mixtures(self):
        # Two own mixtures separated by a selected opponent edge, plus reveal.
        graph = (('decision', 0, (1, 2)), ('decision', 1, (3, 4)),
                 ('reveal', -1, (3,)), ('decision', 0, (4, 5)),
                 ('fold', -1, ()), ('showdown', -1, ()))
        d = depths(graph)
        self.assertEqual(d[0], (2, 1)); self.assertEqual(d[3], (1, 0))
        checked = 0; strict = False
        for root_units, tail_units, choice, left, right in product(range(5), range(5), range(2), (-3, 1), (-1, 3)):
            terminal = (Fraction(left, 2), Fraction(right, 2))
            tail = sum(p*v for p, v in zip((Fraction(tail_units, 4), Fraction(4-tail_units, 4)), terminal))
            children = (tail if choice == 0 else terminal[0], tail)
            mixed = sum(p*v for p, v in zip((Fraction(root_units, 4), Fraction(4-root_units, 4)), children))
            for value in (*children, mixed, *(v-mixed for v in children)):
                self.assertEqual((value * (2 * 4**d[0][0])).denominator, 1)
            # Omitting the current own mixture is unsound for regret.
            strict |= any((v-mixed).denominator > 2 * 4**(d[0][0]-1) for v in children)
            checked += 1
        self.assertEqual(checked, 200); self.assertTrue(strict)

    def test_exact_accumulation_and_policy(self):
        for power in range(53, 366, 52):
            for first, second in (((1, -1, 0), (2, 1, -2)), ((0, 0, 0), (-1, -1, 0))):
                rr = tuple((x+y) << (625-power) for x, y in zip(first, second))
                aa = (1 << 312, 2 << 312, 0)
                r, a = convert(rr, aa, power)
                self.assertEqual(r, tuple(x+y for x, y in zip(first, second)))
                self.assertEqual(a, (1, 2, 0)); self.assertEqual(matching(rr), matching(r))

    def test_malformed_structures_and_carriers(self):
        bad = ((('decision', 0, (0, 0)),), (('reveal', -1, ()),),
               (('fold', -1, ()), ('showdown', -1, ())),
               (('decision', 2, (1, 1)), ('fold', -1, ())),
               (('decision', 0, (True, 1)), ('fold', -1, ())))
        for graph in bad:
            with self.assertRaises(ValueError): depths(graph)
        for rr, aa, power in (((1, 0), (0, 0), 53), ((0, 0), (1, 0), 53),
                              ((0, 0), (-(1 << 312), 0), 53), ((0, 0), (0, 0), True),
                              ((1 << 632, 0), (0, 0), 365), ((0, 0), (0, 0), 1)):
            with self.assertRaises(ValueError): convert(rr, aa, power)


if __name__ == '__main__': unittest.main()
