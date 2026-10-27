"""Independent native DAG support and identity controls."""
from types import SimpleNamespace
import unittest

from pokerlab.native_selected_dag import _prefix_support


class NativeDagIndependentTests(unittest.TestCase):
    def test_prefix_support_uses_hand_indices_not_flags(self):
        # Hand 0 collides with board, hand 1 with the only opponent, hand 2 is live.
        operator = SimpleNamespace(
            hand_counts=(3, 1), selected=((('2c', '3c', '4c'), '5c', '6c'),),
            _board_masks=(1,), _hand_masks=((1, 2, 4), (2,)), world_count=1)
        _, _, prefixes, active = _prefix_support(operator)
        self.assertEqual(len(prefixes), 4)
        self.assertTrue(all(support == ((2,), (0,)) for support in active))

    def test_same_context_has_distinct_history_rows_and_rejects_orphans(self):
        from pokerlab.native_selected_dag import _logical_rows
        from pokerlab.shared_public_topology import ActionRecord, DecisionVertex, TerminalVertex
        check = ActionRecord('check', 0.0, 0.0, False, 'check')
        call = ActionRecord('call', 0.0, 0.0, False, 'call')
        terminal = TerminalVertex('showdown', (1.0, 1.0), None)
        shared = DecisionVertex(1, (check,), (0,))
        root = DecisionVertex(0, (check, call), (1, 1))
        topology = SimpleNamespace(vertices=(terminal, shared, root))
        contexts = [(2, 0, (1, 1), None), (1, 0, (2,), None), (0, 0, (), None)]
        infos = {(0, 0, ()): 2, (1, 0, ('check',)): 1, (1, 0, ('call',)): 1}
        keys, counts = _logical_rows(topology, 0, contexts, ((),), (((0,), (0,)),), infos, (1, 1))
        self.assertEqual(keys, tuple(infos))
        self.assertEqual(counts, (2, 1, 1))
        with self.assertRaisesRegex(ValueError, 'orphan'):
            _logical_rows(topology, 0, contexts, ((),), (((0,), (0,)),),
                          dict(infos, **{} ) | {(1, 0, ('orphan',)): 1}, (1, 1))



if __name__ == '__main__':
    unittest.main()
