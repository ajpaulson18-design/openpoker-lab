"""Differential checks for public-tree alternating CFR+."""
import unittest

from pokerlab.cfr_plus import train as train_reference
from pokerlab.postflop_solver import (
    _Chance, _build_postflop_tree, _chance_child, _enumerate_worlds, _node_key,
    _prefix_hand_index, _public_reveals,
)
from pokerlab.public_cfr import train_public_batched
from pokerlab.river_config import RiverConfig
from pokerlab.river_tree import _Terminal, _terminal_value


class PublicCFRPlusTests(unittest.TestCase):
    def setUp(self):
        board = "Js8d4c"
        self.config = RiverConfig(pot=20, effective_stack=(35, 55),
                                  bet_sizes=(0.25, 0.75), raise_sizes=(0.5,),
                                  max_raises=1, include_all_in=True)
        self.hands, self.worlds, _, _ = _enumerate_worlds(
            board, "AsAh:0.5,KsKh:1", "AcAd:1,KcKd:0.75",
            (("As", "3c"), ("3c", "As"), ("5h", "9s")), iterations=20,
        )
        self.root, nodes, _, _, _ = _build_postflop_tree(
            board, self.config, worlds=self.worlds,
        )
        legal = _prefix_hand_index(self.worlds)
        self.infos = {}
        for (player, history), node in nodes.items():
            prefix = _public_reveals(history)
            for hand_index in sorted(legal.get((player, prefix), ())):
                self.infos[(player, hand_index, history)] = len(node.actions)

    def test_matches_reference_across_blockers_and_betting_shapes(self):
        def key(node, world):
            return _node_key(node, world)

        def chance(node, world):
            return _chance_child(node, world)

        def payoff(node, world):
            return _terminal_value(node, world[3], self.config.pot)

        expected = train_reference(
            self.root, self.worlds, self.infos, 12,
            terminal_value=payoff, node_key=key, chance_child=chance,
        )
        actual = train_public_batched(
            self.root, self.worlds, self.infos, 12, "cfrplus",
            pot=self.config.pot, chance_type=_Chance,
        )
        self.assertEqual(expected.keys(), actual.keys())
        for info in expected:
            for left, right in zip(expected[info], actual[info]):
                self.assertAlmostEqual(left, right, places=11, msg=repr(info))


if __name__ == "__main__":
    unittest.main()
