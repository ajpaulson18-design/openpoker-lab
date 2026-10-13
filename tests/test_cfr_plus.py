import unittest
from types import SimpleNamespace

from pokerlab.cfr_plus import train


class CFRPlusTests(unittest.TestCase):
    def setUp(self):
        self.root = SimpleNamespace(
            player=0, actions=("left", "right"),
            children=(SimpleNamespace(payoff=0), SimpleNamespace(payoff=0)),
        )
        self.infos = {(0, 0, ()): 2}
        self.key = lambda node, world: (0, world[0], ())
        self.terminal = lambda node, world: (
            node.payoff(world) if callable(node.payoff) else node.payoff[world[1]])
        self.worlds = [
            (0, 0, .5, 0, (1., -1.)),
            (0, 1, .5, 0, (-1., 1.)),
        ]

    def solve(self, **kwargs):
        return train(self.root, self.worlds, self.infos, 1,
                     terminal_value=self.terminal, node_key=self.key, **kwargs)

    def test_hidden_world_regrets_aggregate_before_cfr_plus_clipping(self):
        # The two hidden worlds cancel exactly at the shared information set.
        # Clipping each world separately would incorrectly favor left.
        self.root.children = (SimpleNamespace(payoff=lambda w: w[4][0]),
                              SimpleNamespace(payoff=lambda w: w[4][1]))
        result = self.solve()
        self.assertEqual(result[(0, 0, ())], [.5, .5])

    def test_linear_average_delay_yields_uniform_before_delay_and_strategy_after(self):
        self.root.children = (SimpleNamespace(payoff=1), SimpleNamespace(payoff=0))
        result = train(self.root, [(0, 0, 1., 0)], self.infos, 2,
                       terminal_value=lambda node, world: node.payoff,
                       node_key=self.key, delay=1)
        # Sweep 1 has zero average weight; sweep 2's completed profile favors left.
        self.assertEqual(result[(0, 0, ())], [1., 0.])

    def test_delay_at_or_beyond_iteration_count_returns_uniform(self):
        self.root.children = (SimpleNamespace(payoff=1), SimpleNamespace(payoff=0))
        for delay in (2, 7):
            with self.subTest(delay=delay):
                result = train(self.root, [(0, 0, 1., 0)], self.infos, 2,
                               terminal_value=lambda node, world: node.payoff,
                               node_key=self.key, delay=delay)
                self.assertEqual(result[(0, 0, ())], [.5, .5])

    def test_lock_validation_and_fixed_policy(self):
        self.root.children = (SimpleNamespace(payoff=1), SimpleNamespace(payoff=0))
        result = train(self.root, [(0, 0, 1., 0)], self.infos, 2,
                       terminal_value=lambda node, world: node.payoff,
                       node_key=self.key, locks={(0, 0, ()): [.25, .75]})
        self.assertEqual(result[(0, 0, ())], [.25, .75])
        for bad in ([.2, .2], [float("nan"), 0], [-1, 2], [1]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                train(self.root, [(0, 0, 1., 0)], self.infos, 1,
                      terminal_value=lambda node, world: node.payoff,
                      node_key=self.key, locks={(0, 0, ()): bad})

    def test_input_guards(self):
        call = lambda **kw: train(self.root, [(0, 0, 1., 0)], self.infos, 1,
                                  terminal_value=lambda node, world: 0,
                                  node_key=self.key, **kw)
        with self.assertRaises(ValueError):
            call(algorithm="vanilla")
        with self.assertRaises(ValueError):
            call(delay=-1)
        with self.assertRaises(ValueError):
            train(self.root, [(0, 0, float("inf"), 0)], self.infos, 1,
                  terminal_value=lambda node, world: 0, node_key=self.key)
        with self.assertRaises(ValueError):
            train(self.root, [(0, 0, 0., 0)], self.infos, 1,
                  terminal_value=lambda node, world: 0, node_key=self.key)
        for bad_mass in (True, 1e308):
            worlds = ([(0, 0, bad_mass, 0)] if bad_mass is True else
                      [(0, 0, bad_mass, 0), (0, 0, bad_mass, 0)])
            with self.subTest(bad_mass=bad_mass), self.assertRaises(ValueError):
                train(self.root, worlds, self.infos, 1,
                      terminal_value=lambda node, world: 0, node_key=self.key)
        with self.assertRaises(ValueError):
            train(self.root, [(0, 0, 1., 0)], {(True, 0): 2}, 1,
                  terminal_value=lambda node, world: 0, node_key=self.key)

    def test_world_generator_is_materialized_once(self):
        self.root.children = (SimpleNamespace(payoff=1), SimpleNamespace(payoff=0))
        consumed = []
        def worlds():
            consumed.append(True)
            yield (0, 0, 1., 0)
        result = train(self.root, worlds(), self.infos, 3,
                       terminal_value=lambda node, world: node.payoff,
                       node_key=self.key)
        self.assertEqual(len(consumed), 1)
        self.assertEqual(result[(0, 0, ())], [1., 0.])

    def test_lock_probability_generator_is_materialized_once(self):
        self.root.children = (SimpleNamespace(payoff=1), SimpleNamespace(payoff=0))
        consumed = []
        def probabilities():
            consumed.append(True)
            yield .25
            yield .75
        result = train(self.root, [(0, 0, 1., 0)], self.infos, 1,
                       terminal_value=lambda node, world: node.payoff,
                       node_key=self.key, locks={(0, 0, ()): probabilities()})
        self.assertEqual(len(consumed), 1)
        self.assertEqual(result[(0, 0, ())], [.25, .75])

    def test_world_masses_reject_boolean_and_overflowing_total(self):
        for worlds in ([(0, 0, True, 0)],
                       [(0, 0, 1e308, 0), (0, 0, 1e308, 0)]):
            with self.subTest(worlds=worlds), self.assertRaises(ValueError):
                train(self.root, worlds, self.infos, 1,
                      terminal_value=lambda node, world: 0, node_key=self.key)


if __name__ == "__main__":
    unittest.main()
