"""Independent boundary checks for exact selected float conversion."""
import unittest
from fractions import Fraction
from sys import float_info

from pokerlab.exact_selected_float_adapter import ExactSelectedFloatAdapter
from pokerlab.exact_selected_kernel import ExactSelectedRunoutKernel
from pokerlab.river_tree import _Terminal
from pokerlab.shared_public_topology import compile_shared_public_topology
from pokerlab.shared_topology_view import SharedPublicView


def setup(kind='showdown', winner=None):
    original = _Terminal(kind, (0.345678901, 1.234567891), winner)
    view = SharedPublicView(compile_shared_public_topology(original))
    kernel = ExactSelectedRunoutKernel('AsAd', 'KsKd', ('2c3c4d7h8h',))
    return kernel, view, ExactSelectedFloatAdapter(kernel, view)


class IndependentExactFloatAdapterTests(unittest.TestCase):
    def test_original_non_dyadic_money_for_both_players(self):
        _, view, adapter = setup()
        self.assertEqual(adapter.values(view.root, (1.0,), 0), [0.345678901])
        self.assertEqual(adapter.values(view.root, (1.0,), 1), [-0.345678901])
        _, view, adapter = setup('fold', 1)
        self.assertEqual(adapter.values(view.root, (1.0,), 0), [-0.345678901])
        self.assertEqual(adapter.values(view.root, (1.0,), 1), [0.345678901])

    def test_strict_signed_underflow_and_exact_zero(self):
        _, _, adapter = setup()
        self.assertEqual(adapter._convert(Fraction(0)), 0.0)
        tiny = Fraction.from_float(float_info.min) / 2
        for value in (tiny, -tiny, Fraction(1, 2**2000), -Fraction(1, 2**2000)):
            with self.assertRaises(ValueError):
                adapter._convert(value)
        self.assertEqual(adapter._convert(Fraction.from_float(float_info.min)), float_info.min)

    def test_foreign_equal_value_and_changed_view_reject(self):
        _, view, adapter = setup()
        foreign = _Terminal(view.root.kind, view.root.contributions, view.root.winner)
        self.assertEqual(foreign, view.root)
        with self.assertRaises(ValueError):
            adapter.values(foreign, (1.0,), 0)
        view._terminals = tuple(list(view._terminals))
        with self.assertRaises(ValueError):
            adapter.values(view.root, (1.0,), 0)

    def test_mapping_admission_before_snapshot(self):
        kernel, view, _ = setup()
        with self.assertRaises(ValueError):
            ExactSelectedFloatAdapter(kernel, view, max_storage=1)
        with self.assertRaises(ValueError):
            ExactSelectedFloatAdapter(kernel, view, max_work=1)
