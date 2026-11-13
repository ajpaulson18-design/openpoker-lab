"""Independent literal numeric-rule histories versus compact native keys."""
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests.test_native_exact_reach import authenticate, sha
from tests.virtual_betting_template_reference import build_reference_template
from tests.virtual_frozen_run_control import run_bounded_child
from tests.virtual_frozen_update_reference import _template_case

ROOT = Path(__file__).resolve().parents[1]
BOARDS = ((16,17,24,32,33),(16,17,24,32,35),(16,17,24,33,32),
          (16,17,24,48,43),(17,24,32,33,35))
PHASE = {'decision': 0, 'reveal': 1, 'fold': 2, 'showdown': 3}
RANKS = '23456789TJQKA'
SUITS = 'cdhs'


def expected_walk(template, board):
    def visit(node_id, history, visible):
        node = template.nodes[node_id]
        yield (history, visible, PHASE[node.phase])
        for edge in node.edges:
            if edge.kind == 'reveal':
                count = node.state.board_length
                cards = board[:3] if count == 3 else board[count-1:count]
                label = {3: 'flop', 4: 'turn', 5: 'river'}[count]
                token = label + '@' + ''.join(RANKS[c//4]+SUITS[c%4] for c in cards)
                yield from visit(edge.child, (*history, token), count)
            else:
                yield from visit(edge.child, (*history, edge.token), visible)
    return list(visit(template.root, (), 0))


@unittest.skipUnless(os.environ.get('OPENPOKER_NATIVE_VIRTUAL_DYADIC_HISTORY_EXE'),
                     'explicit source-built compact history controls required')
class CompactHistoryControls(unittest.TestCase):
    def test_full_literal_paths_and_ordered_visible_prefix_keys(self):
        exe = Path(os.environ['OPENPOKER_NATIVE_VIRTUAL_DYADIC_HISTORY_EXE']).resolve()
        identity = authenticate(exe, ROOT, 'virtual-dyadic-history-controls')
        temporary = None
        destination = os.environ.get('OPENPOKER_NATIVE_VIRTUAL_DYADIC_HISTORY_CONTROL_DIR')
        if destination is None:
            temporary = TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            destination = temporary.name
        output = Path(destination)
        before = sha(exe)
        observed = run_bounded_child([str(exe)], b'', output, stdout_limit=2_100_000)
        after = sha(exe)
        (output/'native-identity.json').write_text(json.dumps({'before_sha256':before,'after_sha256':after,
            'manifest_sha256':hashlib.sha256(identity[0]).hexdigest()})+'\n')
        self.assertEqual((before,after),(identity[1]['executable_sha256'],)*2)
        self.assertEqual(authenticate(exe, ROOT, 'virtual-dyadic-history-controls'), identity)
        self.assertEqual((observed['status'],observed['returncode'],observed['actual_exit_observed']),('exited',0,True),
                         (output/'stderr.bin').read_text())
        self.assertEqual((output/'stderr.bin').read_bytes(),b'')
        lines = (output/'stdout.bin').read_text(encoding='ascii').splitlines()
        template = build_reference_template(_template_case())
        expected = [expected_walk(template, board) for board in BOARDS]
        size = len(expected[0])
        self.assertEqual(size,1105)
        self.assertEqual(lines[0],f'COMPACT_HISTORY_V1 {size} {len(template.nodes)}')
        key_to_history,history_to_key,by_source = {},{},{}
        offset = 1
        for variant, rows in enumerate(expected):
            literals = set()
            for history,visible,phase in rows:
                tag,b,key,literal,source,k,p,n,*tokens = lines[offset].split()
                self.assertEqual((tag,int(b),int(k),int(p),int(n),tuple(tokens)),
                                 ('ROW',variant,visible,phase,len(history),history))
                key,literal,source = int(key),int(literal),int(source)
                expected_key=(literal<<33)|(visible<<30)|sum(
                    card<<(6*i) for i,card in enumerate(BOARDS[variant][:visible]))
                self.assertEqual(key,expected_key)
                self.assertEqual(history_to_key.setdefault(history,key),key)
                self.assertEqual(key_to_history.setdefault(key,history),history)
                literals.add(literal)
                by_source.setdefault(source,set()).add(literal)
                offset += 1
            self.assertEqual(literals,set(range(size)))
        self.assertTrue(any(len(paths)>1 for paths in by_source.values()))
        receipt=lines[offset].split();self.assertEqual(receipt[0],'RECEIPT')
        work,nodes,entries,owned,depth,scratch,peak=map(int,receipt[1:])
        self.assertEqual(nodes,size)
        self.assertLess(work,500_000_000)
        self.assertLess(entries+scratch,2_000_000)
        self.assertLessEqual(owned,peak)
        self.assertLess(peak,32<<20)
        self.assertEqual(depth,max(len(h) for h in key_to_history.values()))
        names = ('raised_work','literal_nodes','literal_entries','literal_bytes','source_depth','construction_work',
                 'default_cursor','foreign_cursor','action_menu','poisoned_root','reveal_phase','export_scratch',
                 'noncanonical_flop','foreign_flop','changed_turn_prefix','foreign_turn_card','duplicate_turn_card')
        self.assertEqual(lines[offset+1:], [*(f'REJECT {name}' for name in names),'END'])


if __name__ == '__main__':
    unittest.main()
