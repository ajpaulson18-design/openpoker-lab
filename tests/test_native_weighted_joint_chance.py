"""Independent conformance of the shared compact weighted ticket purpose."""
from hashlib import sha256
from itertools import combinations
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest

from tests.test_native_exact_reach import authenticate
from tests.virtual_frozen_run_control import run_bounded_child
from tests.virtual_weighted_joint_reference import build_law
from tests.full_deck_public_chance_reference import PROOF9

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'prepared-weighted-joint-controls'
ENV = 'OPENPOKER_NATIVE_WEIGHTED_JOINT_EXE'
OUT = 'OPENPOKER_NATIVE_WEIGHTED_JOINT_DIR'


def bits(number):
    return int.from_bytes(struct.pack('>d', number), 'big')


def encode(deck, ranges, selectors):
    values = [len(deck), *map(len, ranges), len(selectors)]
    for side in ranges:
        for hand, raw in side:
            values.extend((*hand, raw))
    for pair in selectors:
        values.extend(pair)
    return (' '.join(map(str, values)) + '\n').encode('ascii')


@unittest.skipUnless(os.environ.get(ENV), 'explicit source-built weighted joint candidate required')
class NativeWeightedJointChanceTests(unittest.TestCase):
    def test_weighted_original_ids_boards_signs_and_resource_receipts(self):
        executable = Path(os.environ[ENV]).resolve()
        identity = authenticate(executable, ROOT, TARGET)
        output = Path(os.environ[OUT]).resolve()
        self.assertEqual(output.parent, ROOT.parent.resolve())
        output.mkdir(exist_ok=False)
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        # Capture every tracked Python raw hash before importing/executing a
        # numerical case; native closure is separately source-build attested.
        self.assertEqual(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no', '--',
                                                 '*.py', *identity[1]['source_sha256']], cwd=ROOT), b'')
        names = tuple(name for name in subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
                      if name.endswith('.py'))
        hashes = {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
        native_source = {name: (ROOT / name).read_bytes() for name in identity[1]['source_sha256']}
        for name, raw in native_source.items():
            path = output / 'source' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        (output / 'source-identity.json').write_text(json.dumps({'head': head, 'python_version': sys.version,
            'tracked_python_raw_sha256': hashes,
            'native_raw_sha256': {name: sha256(raw).hexdigest() for name, raw in native_source.items()}}, indent=2) + '\n')
        (output / 'native-build-manifest.json').write_bytes(identity[0])
        process_records = []

        def run(label, data, expected_exit=0):
            directory = output / label
            self.assertLessEqual(len(data), 98304)
            fixture = output / (label + '.input')
            with fixture.open('xb') as stream:
                stream.write(data)
            observation = run_bounded_child([str(executable), str(fixture)], b'', directory, stdout_limit=131072, timeout=180)
            self.assertEqual(fixture.read_bytes(), data)
            (directory / 'range-input.json').write_text(json.dumps({'path': fixture.name, 'bytes': len(data),
                'sha256': sha256(data).hexdigest(), 'stdin_bytes': 0}, indent=2) + '\n')
            process_records.append({'case': label, 'expected_exit': expected_exit, 'observation': observation})
            self.assertEqual(observation['failures'], [])
            self.assertEqual((observation['status'], observation['returncode'], observation['actual_exit_observed']),
                             ('exited', expected_exit, True))
            raw = (directory / 'stdout.bin').read_bytes()
            if expected_exit:
                self.assertEqual(raw, b'')
            else:
                self.assertEqual((directory / 'stderr.bin').read_bytes(), b'')
            return raw.decode('ascii').splitlines()

        summaries = []
        def accepted(label, deck, ranges, selectors, signed_count):
            law = build_law(deck, ranges)
            private_checks = 0; signed_checks = 0
            for batch, start in enumerate(range(0, len(selectors), 512)):
                selected = selectors[start:start + 512]
                lines = run(label + '-' + str(batch), encode(deck, ranges, selected))
                self.assertEqual(lines[0], f'WEIGHTED_JOINT_V1 {law.normalizer} {len(ranges[0])} {len(ranges[1])} {len(selected)}')
                for seat in (0, 1):
                    tag, actor, power, common = lines[seat + 1].split()
                    self.assertEqual((tag, int(actor)), ('SCALE', seat))
                    # Different independent normalization algorithms may choose
                    # different aligned denominator/gcd; exact scale must match.
                    from fractions import Fraction
                    scale = Fraction(int(common)) * (Fraction(2) ** int(power))
                    self.assertEqual(scale, law.normalization[seat].scale)
                self.assertEqual(len(lines), len(selected) + 4)
                for offset, ((ticket, rank), line) in enumerate(zip(selected, lines[3:-1])):
                    parts = line.split(); self.assertEqual(parts[0], 'WORLD')
                    values = tuple(map(int, parts[1:])); self.assertEqual(len(values), 14)
                    pair = law.select_pair(ticket)
                    self.assertEqual(values[:4], (ticket, rank, *pair.holding_indices))
                    self.assertEqual(values[4:8], (*pair.holdings[0], *pair.holdings[1]))
                    board = values[8:13]
                    self.assertEqual(len(set(board)), 5)
                    self.assertTrue(set(board) <= set(deck))
                    self.assertTrue(set(board).isdisjoint((*pair.holdings[0], *pair.holdings[1])))
                    self.assertEqual(tuple(sorted(board[:3])), board[:3]); self.assertIn(values[13], (-1, 0, 1))
                    private_checks += 1
                    if start + offset < signed_count:
                        expected = law.decode(ticket, rank)
                        self.assertEqual((board, values[13]), (expected.board, expected.showdown_sign)); signed_checks += 1
                receipt = tuple(map(int, lines[-1].split()[1:])); self.assertTrue(lines[-1].startswith('RECEIPT '))
                h0, h1 = map(len, ranges); h = h0 + h1
                setup = 65536 + 16384 * h
                per = 12288 + 64 * h1 + 256 * h0.bit_length()
                retained = 3 * h + 256 + 1326 + h0 + 4 * 53
                payload = 80 * h + 64 * h0 + 16 * 1326 + 53 * 75 + 8192
                self.assertEqual(receipt, (setup + len(selected) * per, retained, 256, retained + 256,
                                          payload, payload + 8192, 150, 2 * len(selected), 0, 0))
                self.assertLessEqual(receipt[0], 110_000_000)
                self.assertLessEqual(receipt[3], 12000); self.assertLessEqual(receipt[5], 1 << 20)
            summaries.append({'case': label, 'normalizer': law.normalizer, 'original_pair_checks': private_checks,
                              'independent_board_sign_checks': signed_checks, 'reference_receipt': law.receipt()})

        n9 = ((((43, 48), bits(.125)), ((32, 43), bits(.75))),
              (((24, 37), bits(.375)), ((16, 32), bits(1.))))
        accepted('n9', tuple(PROOF9), n9, tuple((i, j) for i in range(29) for j in range(20)), 580)
        hands = tuple(combinations(range(52), 2))
        for weighted in (False, True):
            side = tuple((hand, bits(float(index % 7 + 1) if weighted else 1.)) for index, hand in enumerate(hands))
            # First 31 queries independently check unranking+payoff signs;
            # all 2652 CDF boundary queries check original private IDs.
            law = build_law(tuple(range(52)), (side, side))
            witnesses = tuple(((law.normalizer - 1) * i // 30, (34246080 - 1) * i // 30) for i in range(31))
            boundaries = []; previous = 0
            for end in law.cdf:
                boundaries.extend(((previous, 0), (end - 1, 0))); previous = end
            accepted('full52-weighted' if weighted else 'full52-uniform', tuple(range(52)), (side, side),
                     (*witnesses, *boundaries), 31)
        for label, ranges in (
            ('dead-original-row', ((((0, 1), bits(float(1 << 63))), ((2, 3), bits(1.))), (((0, 4), bits(1.)),))),
            ('subnormal', tuple(tuple((hand, 1) for hand, _ in seat) for seat in n9)),
            ('odd-reordered', ((((32, 43), bits(15.)), ((43, 48), bits(3.))),
                               (((16, 32), bits(21.)), ((24, 37), bits(7.)))))):
            deck = tuple(range(52)) if label == 'dead-original-row' else tuple(PROOF9)
            accepted(label, deck, ranges, ((0, 0),), 1)
        invalid = {
            'zero-weight': ((((0, 1), 0),), (((4, 5), bits(1.)),)),
            'negative': ((((0, 1), bits(-1.)),), (((4, 5), bits(1.)),)),
            'nan': ((((0, 1), 0x7ff8000000000001),), (((4, 5), bits(1.)),)),
            'duplicate': ((((0, 1), bits(1.)), ((0, 1), bits(2.))), (((4, 5), bits(1.)),)),
            'no-compatible': ((((0, 1), bits(1.)),), (((1, 2), bits(1.)),)),
            'wide-weight': ((((0, 1), bits(1.)), ((2, 3), bits(float(1 << 64)))), (((4, 5), bits(1.)),)),
            'wide-normalizer': ((((0, 1), bits(float(1 << 63))), ((2, 3), bits(1.))),
                                (((4, 5), bits(float(1 << 63))), ((6, 7), bits(1.))))}
        for label, ranges in invalid.items():
            run('reject-' + label, encode(tuple(range(52)), ranges, ((0, 0),)), 2)
        run('reject-ticket', encode(tuple(PROOF9), n9, ((29, 0),)), 2)
        run('reject-board', encode(tuple(PROOF9), n9, ((0, 20),)), 2)
        self.assertEqual(authenticate(executable, ROOT, TARGET), identity)
        self.assertEqual(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), head)
        self.assertTrue(all(sha256((ROOT / name).read_bytes()).hexdigest() == before for name, before in hashes.items()))
        self.assertTrue(all((ROOT / name).read_bytes() == raw for name, raw in native_source.items()))
        (output / 'result.json').write_text(json.dumps({'status': 'weighted-joint-component-exact', 'cases': summaries,
            'processes': process_records, 'rng_calls': 0, 'training_iterations': 0, 'quality_gate': None,
            'scope': 'Exact compact weighted chance owner only; no full52 walk, longer learning, speed or solver admission.'}, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
