"""Training must release per-call state without relying on cyclic collection."""
import gc
import platform
from types import SimpleNamespace
import unittest
import weakref

from pokerlab.cfr import train as recursive
from pokerlab.planned_cfr import train as planned


class _Payoff:
    def __call__(self, node, world):
        return node.payoff


@unittest.skipUnless(platform.python_implementation() == "CPython",
                     "Immediate release checks CPython reference-count finalization.")
class CFRLifetimeTests(unittest.TestCase):
    def test_static_callbacks_are_released_after_training_without_cyclic_gc(self):
        root = SimpleNamespace(player=0, history=(), actions=("a", "b"), children=(
            SimpleNamespace(payoff=0.), SimpleNamespace(payoff=1.)))
        worlds, infos = [(0, 0, 1., 0)], {(0, 0, ()): 2}
        key = lambda node, world: (node.player, world[node.player], node.history)
        enabled = gc.isenabled()
        gc.disable()
        try:
            for trainer in (recursive, planned):
                with self.subTest(trainer=trainer.__module__):
                    callback = _Payoff()
                    reference = weakref.ref(callback)
                    profile = trainer(root, worlds, infos, 10, "vanilla", callback, key)
                    self.assertEqual(profile[(0, 0, ())], [.05, .95])
                    del callback
                    self.assertIsNone(reference())
        finally:
            if enabled:
                gc.enable()
            gc.collect()

    def test_failed_plan_budget_releases_callback_without_cyclic_gc(self):
        root = SimpleNamespace(player=0, history=(), actions=("a", "b"), children=(
            SimpleNamespace(payoff=0.), SimpleNamespace(payoff=1.)))
        callback = _Payoff()
        reference = weakref.ref(callback)
        enabled = gc.isenabled()
        gc.disable()
        try:
            with self.assertRaisesRegex(ValueError, "operation limit"):
                planned(root, [(0, 0, 1., 0)], {(0, 0, ()): 2}, 10, "vanilla",
                        callback, lambda node, world: (0, 0, ()), max_plan_ops=1)
            del callback
            self.assertIsNone(reference())
        finally:
            if enabled:
                gc.enable()
            gc.collect()
