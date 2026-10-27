"""Independent adversarial controls for shared logical row identity."""
import unittest

from pokerlab.river_tree import _Action, _Node, _Terminal
from pokerlab.shared_public_topology import compile_shared_public_topology
from pokerlab.shared_topology_view import SharedPublicView, layout_census_shared


class SharedLogicalIdentityTests(unittest.TestCase):
    def test_distinct_occurrences_cannot_alias_same_information_row(self):
        leaf = _Terminal('showdown', (1.0, 1.0))
        # Two syntactically equal action tokens produce the same public history.
        # A single stored row must not silently represent both occurrences.
        action = _Action('check')
        left = _Node(('check',), 1, (action,), (leaf,))
        right = _Node(('check',), 1, (action,), (leaf,))
        root = _Node((), 0, (action, action), (left, right))
        view = SharedPublicView(compile_shared_public_topology(root))
        infos = {(0, 0, ()): 2, (1, 0, ('check',)): 1}
        with self.assertRaisesRegex(ValueError, 'occurrence'):
            layout_census_shared(view, infos, (1, 1), 10)

    def test_unknown_history_is_not_accepted_as_a_row(self):
        leaf = _Terminal('fold', (0.5, 1.0), 1)
        root = _Node((), 0, (_Action('fold'),), (leaf,))
        view = SharedPublicView(compile_shared_public_topology(root))
        infos = {(0, 0, ()): 1, (1, 0, ('call',)): 1}
        with self.assertRaisesRegex(ValueError, 'do not match'):
            layout_census_shared(view, infos, (1, 1), 10)

    def test_shifted_terminal_keeps_original_binary_payoff(self):
        from pokerlab.river_tree import _terminal_value
        leaf = _Terminal('showdown', (0.345678901, 1.234567891))
        view = SharedPublicView(compile_shared_public_topology(leaf))
        shifted = view.root
        for sign in (-1, 0, 1):
            self.assertEqual(_terminal_value(leaf, sign, 0.0),
                             _terminal_value(shifted, sign, 2 * view.anchor))

    def test_source_growth_between_precheck_and_snapshot_is_charged(self):
        from unittest.mock import patch
        from pokerlab import shared_public_topology as topology
        from pokerlab.postflop_solver import _Chance

        leaf = _Terminal('showdown', (1.0, 1.0))
        root = _Chance((), {'2c3c4d': leaf}, street='flop')
        limits = topology.TopologyLimits(max_source_edges=1)
        self.assertEqual(topology.compile_shared_public_topology(root, limits=limits)
                         .census.unique_source_edges, 1)
        original = topology._snapshot_node
        def grow_then_capture(node):
            if node is root:
                root.branches['5c6c7d'] = leaf
            return original(node)
        with patch.object(topology, '_snapshot_node', side_effect=grow_then_capture):
            with self.assertRaisesRegex(ValueError, 'source-edge limit'):
                topology.compile_shared_public_topology(root, limits=limits)


if __name__ == '__main__':
    unittest.main()
