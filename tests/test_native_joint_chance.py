"""Independent ticket, board and payoff-sign checks for the native certificate."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts.preflop_validation import independent_rank
from scripts.replay_target_board_reference_packet import SOURCE_NAMES
from tests.full_deck_public_chance_reference import card_name
from tests.test_native_exact_reach import authenticate, sha
from tests.virtual_frozen_run_control import run_bounded_child
from tests.virtual_joint_sample_reference import build_law, ticket

ROOT = Path(__file__).resolve().parents[1]
ENV = 'OPENPOKER_NATIVE_JOINT_CHANCE_EXE'
OUT = 'OPENPOKER_NATIVE_JOINT_CHANCE_DIR'
TARGET = 'virtual-joint-chance-controls'
MATH = (*SOURCE_NAMES, 'scripts/replay_target_board_reference_packet.py',
        'tests/virtual_joint_sample_reference.py', 'tests/test_native_joint_chance.py')


@unittest.skipUnless(os.environ.get(ENV), 'explicit source-built joint chance candidate required')
class NativeJointChanceTests(unittest.TestCase):
    def test_every_ticket_board_and_selected_pair_rank_sign(self):
        executable = Path(os.environ[ENV]).resolve()
        identity = authenticate(executable, ROOT, TARGET)
        names = sorted(set(identity[1]['source_sha256']) | set(MATH))
        self.assertLessEqual(len(names), 128)
        self.assertFalse(subprocess.check_output(
            ['git', 'status', '--porcelain', '--untracked-files=all', '--', *names], cwd=ROOT))
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        source = {name: (ROOT / name).read_bytes() for name in names}
        self.assertLessEqual(sum(map(len, source.values())), 64 << 20)
        blobs = {}
        for line in subprocess.check_output(['git', 'ls-tree', '-r', head], cwd=ROOT, text=True).splitlines():
            metadata, name = line.split('\t', 1)
            if name in source:
                blobs[name] = metadata.split()[2]
                canonical = subprocess.check_output(['git', 'show', head + ':' + name], cwd=ROOT)
                self.assertIn(source[name], (canonical, canonical.replace(b'\n', b'\r\n'))
                              if b'\r' not in canonical else (canonical,))
        self.assertEqual(set(blobs), set(names))
        with TemporaryDirectory(dir=ROOT.parent) as temporary:
            output = Path(os.environ.get(OUT, str(Path(temporary) / 'observed')))
            output.mkdir(parents=True, exist_ok=False)
            for name, raw in source.items():
                target = output / 'source' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            (output / 'source-identity.json').write_text(json.dumps({
                'head': head, 'raw_sha256': {name: sha256(raw).hexdigest() for name, raw in source.items()},
                'committed_blobs': blobs, 'python_version': sys.version,
                'python_executable_sha256': sha(Path(sys.executable)),
            }, indent=2) + '\n')
            (output / 'native-build-manifest.json').write_bytes(identity[0])
            outcome = run_bounded_child([str(executable)], b'', output / 'native',
                                        stdout_limit=131072, timeout=180)
            self.assertEqual(outcome['failures'], [])
            self.assertEqual((outcome['status'], outcome['returncode'], outcome['actual_exit_observed']),
                             ('exited', 0, True))
            self.assertEqual((output / 'native/stderr.bin').read_bytes(), b'')
            raw = (output / 'native/stdout.bin').read_bytes()
            lines = raw.decode('ascii').splitlines()
            law = build_law()
            seen = set(); receipts = []
            for line in lines:
                if line.startswith('TICKET '):
                    values = tuple(map(int, line.split()[1:]))
                    self.assertEqual(len(values), 10)
                    private, board_rank, a, b, *suffix = values
                    self.assertNotIn((private, board_rank), seen)
                    seen.add((private, board_rank))
                    selected = ticket(law, private, board_rank)
                    self.assertEqual((a, b), selected.holdings)
                    self.assertEqual(tuple(suffix[:5]), selected.board)
                    ranks = tuple(independent_rank(tuple(card_name(card) for card in
                                    (*law.ranges[seat][holding][0], *selected.board)))
                                  for seat, holding in enumerate(selected.holdings))
                    sign = (ranks[0] > ranks[1]) - (ranks[0] < ranks[1])
                    self.assertEqual(suffix[5], sign)
                elif line.startswith('RECEIPT '):
                    receipts.append(tuple(map(int, line.split()[1:])))
                else:
                    self.assertEqual(line, 'JOINT_CHANCE_CONTROL_V1 PASS 580 60 3 8 18 0')
            self.assertEqual(seen, {(private, rank) for private in range(29) for rank in range(20)})
            self.assertEqual(len(receipts), 1)
            modeled, joint, queries, decodes, board_unranks, rank_calls, contractions = receipts[0]
            self.assertEqual((joint, queries, decodes, board_unranks, rank_calls, contractions),
                             (580 * 16384, 580, 580, 580, 1160, 0))
            self.assertLessEqual(modeled, 500_000_000)
            self.assertGreaterEqual(modeled, joint)
            checks = [line for line in lines if line.startswith('JOINT_CHANCE_CONTROL_V1 ')]
            self.assertEqual(checks, ['JOINT_CHANCE_CONTROL_V1 PASS 580 60 3 8 18 0'])
            self.assertEqual(authenticate(executable, ROOT, TARGET), identity)
            self.assertEqual(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), head)
            for name, before in source.items():
                self.assertEqual((ROOT / name).read_bytes(), before)
            (output / 'result.json').write_text(json.dumps({
                'status': 'all-580-joint-tickets-board-and-sign-exact', 'ticket_records': len(seen),
                'receipt': receipts[0], 'native_guard_results': checks,
                'native_calls': 1, 'training_iterations': 0, 'rng_calls': 0, 'quality_gate': None,
                'stdout_sha256': sha256(raw).hexdigest(),
                'scope': 'Fixed PROOF9 joint chance certificate only; no trainer or full52 admission.',
            }, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
