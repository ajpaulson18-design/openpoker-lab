"""Literal physical Fraction and independent best-five controls for native vectors."""
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
from tempfile import TemporaryDirectory
import unittest

from scripts import build_native_exact_four_street as builder
from scripts.preflop_validation import independent_rank

DECK = tuple(r + s for r in '23456789TJQKA' for s in 'cdhs')
PROTOCOL = 'OPENPOKER_EXACT_SELECTED_VECTORS_V1'
LIMITS = (1326, 64, 65536, 500_000_000, 2_000_000)

def bits(value):
    return struct.unpack('>Q', struct.pack('>d', float(value)))[0]

def cards(text):
    return tuple(text[i:i + 2] for i in range(0, len(text), 2))

def board(text):
    values = cards(text)
    return tuple(sorted(values[:3], key=DECK.index)) + values[3:]

def wire(hands, boards, queries, *, cache=1, limits=LIMITS, payload_limit=1 << 30):
    rows = [PROTOCOL, ' '.join(map(str, (*map(len, hands), len(boards), cache, len(queries)))),
            ' '.join(map(str, (*limits, payload_limit)))]
    for side in hands:
        for hand, weight in side:
            rows.append(f'{DECK.index(hand[0])} {DECK.index(hand[1])} {bits(weight):016x}')
    rows.extend(' '.join(str(DECK.index(card)) for card in value) for value in boards)
    for kind, player, indexes, payoff, reach in queries:
        row = [kind, str(player), str(len(indexes)), *map(str, indexes)]
        if kind in ('F', 'D'):
            row += [f'{bits(payoff):016x}', *(f'{bits(value):016x}' for value in reach)]
        rows.append(' '.join(row))
    return ('\n'.join(rows) + '\n').encode('ascii')

def physical(hands, boards):
    worlds = []
    total = Fraction()
    for i, (hand0, weight0) in enumerate(hands[0]):
        for j, (hand1, weight1) in enumerate(hands[1]):
            if set(hand0) & set(hand1):
                continue
            for k, outcome in enumerate(boards):
                if (set(hand0) | set(hand1)) & set(outcome):
                    continue
                mass = Fraction(float(weight0)) * Fraction(float(weight1))
                worlds.append((i, j, k, mass))
                total += mass
    return worlds, total

def oracle(hands, boards, query):
    kind, player, indexes, payoff, reach = query
    worlds, total = physical(hands, boards)
    answer = [[Fraction() for _ in side] for side in hands]
    for i, j, k, mass in worlds:
        if k not in indexes:
            continue
        if kind in ('M', 'S'):
            answer[0][i] += mass / total
            answer[1][j] += mass / total
        else:
            own, other = (i, j) if player == 0 else (j, i)
            value = Fraction(float(payoff))
            if kind == 'F':
                if player == 1:
                    value = -value
            else:
                left = independent_rank(hands[player][own][0] + boards[k])
                right = independent_rank(hands[1 - player][other][0] + boards[k])
                value *= (left > right) - (left < right)
            answer[player][own] += mass / total * Fraction(float(reach[other])) * value
    return answer if kind in ('M', 'S') else [answer[player]]

class NativeExactSelectedVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = TemporaryDirectory(prefix='opl-native-exact-vectors-')
        provided = os.environ.get('OPENPOKER_NATIVE_EXACT_SELECTED_VECTORS_EXE')
        if provided:
            cls.executable = Path(provided).resolve(strict=True)
            manifest = json.loads((cls.executable.parent / 'native-exact-build-manifest.json').read_bytes())
            dependency, headers = builder._dependency()
            sources = (*builder.TARGETS['kernel'][1], 'scripts/build_native_exact_four_street.py',
                'third_party/boost-multiprecision-1.92.0/manifest.json',
                'third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt',
                'third_party/boost-multiprecision-1.92.0/headers.zip')
            expected = {name: hashlib.sha256((builder.ROOT / name).read_bytes()).hexdigest() for name in sources}
            if (manifest.get('contract') != 'native-exact-build-v1' or manifest.get('target') != 'kernel' or
                    manifest.get('source_sha256') != expected or
                    manifest.get('dependency_commit') != dependency['commit'] or
                    manifest.get('dependency_archive_sha256') != builder.HEADER_ARCHIVE_SHA256 or
                    manifest.get('dependency_manifest_sha256') != builder.DEPENDENCY_MANIFEST_SHA256 or
                    manifest.get('dependency_headers') != len(headers) or manifest.get('license') != 'BSL-1.0' or
                    Path(manifest.get('executable', '')).resolve() != cls.executable or
                    manifest.get('executable_sha256') != hashlib.sha256(cls.executable.read_bytes()).hexdigest()):
                raise AssertionError('native vector binary/source provenance mismatch')
            cls.build_manifest = manifest
        else:
            if shutil.which('cl' if os.name == 'nt' else 'c++') is None:
                cls.temporary.cleanup()
                raise unittest.SkipTest('no installed compiler and no explicitly selected native vector binary')
            cls.build_manifest = builder.build(cls.temporary.name, target='kernel')
            cls.executable = Path(cls.build_manifest['executable'])

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def invoke(self, raw, *, success=True):
        result = subprocess.run([str(self.executable)], input=raw, capture_output=True, timeout=30)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout.decode('ascii') + result.stderr.decode('ascii'))
            self.assertEqual(result.stderr, b'')
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'ERR\t', result.stdout)
        return result.stdout.decode('ascii').splitlines()

    def compare(self, hands, boards, queries, *, cache=1):
        lines = self.invoke(wire(hands, boards, queries, cache=cache))
        self.assertEqual(lines.pop(0), 'READY\t' + PROTOCOL)
        tag, z, exponent0, exponent1 = lines.pop(0).split('\t')
        self.assertEqual(tag, 'Z')
        integer = int(z, 16)
        exponent = int(exponent0) + int(exponent1)
        exact_z = Fraction(integer << max(0, exponent), 1 << max(0, -exponent))
        self.assertEqual(exact_z, physical(hands, boards)[1])
        for index, query in enumerate(queries):
            kind, player, *_ = query
            answer = oracle(hands, boards, query)
            for side, values in zip((0, 1) if kind in ('M', 'S') else (player,), answer):
                fields = lines.pop(0).split('\t')
                self.assertEqual(fields[:3], [kind, str(index), str(side)])
                if kind == 'S':
                    self.assertEqual(fields[3:], [str(int(value > 0)) for value in values])
                else:
                    self.assertEqual(fields[3:], [f'{bits(value):016x}' for value in values])
        self.assertEqual(len(lines), 1)
        fields = lines[0].split('\t')
        self.assertEqual(fields[0], 'COUNTS')
        counters = list(map(int, fields[1:]))
        self.assertLessEqual(counters[0], 500_000_000)
        self.assertLessEqual(counters[1], 2_000_000)
        self.assertLessEqual(counters[3], 65536)
        self.assertLessEqual(counters[9], 1 << 30)
        self.assertLessEqual(counters[10], 65589)
        return counters

    def test_weighted_blockers_shared_futures_empty_prefix_and_both_seat_payoffs(self):
        hands = ([(cards('AsAh'), .7), (cards('KsKh'), .3), (cards('9s9h'), .2)],
                 [(cards('AsAh'), .4), (cards('KdKc'), .6), (cards('8s8h'), .5)])
        boards = list(map(board, ('2c3d4h5s6c', '2c3d4h7s8c', '2c3d4h7s9c')))
        queries = []
        for indexes in ((), (0, 1, 2), (1, 2), (2,)):
            queries.extend((kind, 0, indexes, 0, ()) for kind in ('M', 'S'))
            for player in (0, 1):
                for kind in ('F', 'D'):
                    queries.append((kind, player, indexes, -1.5 if kind == 'F' else 1.5, (.25, .75, 0.0)))
        counts = self.compare(hands, boards, queries)
        self.assertGreater(counts[4], 0)
        self.assertGreater(counts[7], 0)
        cached = self.compare(hands, boards, queries, cache=64)
        self.assertEqual(cached[7], 0)
        self.assertLess(cached[4], counts[4])

    def test_private_flush_both_seats_and_same_holding_addback_ties(self):
        hands = ([(cards('AcQc'), 1.), (cards('AdQd'), .5)],
                 [(cards('KcJc'), .75), (cards('KdJd'), 1.)])
        boards = list(map(board, ('2c3c7c9hTs', '2d3d7d9hTs')))
        queries = [('M', 0, (0, 1), 0, ())]
        queries += [('D', player, indexes, 2.75, (.125, .875))
                    for player in (0, 1) for indexes in ((0,), (1,), (0, 1))]
        self.compare(hands, boards, queries)
        ties = ([(cards('2c3c'), 1.), (cards('2d3d'), .5)],
                [(cards('2c3c'), .3), (cards('4d5d'), .7)])
        self.compare(ties, [board('AcKcQcJcTc')], [('M', 0, (0,), 0, ()),
            ('D', 0, (0,), 3., (1., .5)), ('D', 1, (0,), 3., (.25, 1.))])

    def test_seeded_native_ranking_against_independent_best_five(self):
        rng = random.Random(713259)
        for _ in range(32):
            chosen = rng.sample(DECK, 13)
            hands = ([(tuple(chosen[:2]), .3), (tuple(chosen[2:4]), .7)],
                     [(tuple(chosen[4:6]), .4), (tuple(chosen[6:8]), .6)])
            boards = [tuple(sorted(chosen[8:11], key=DECK.index)) + tuple(chosen[11:13])]
            self.compare(hands, boards, [('D', 0, (0,), 1.25, (.125, .875)),
                ('D', 1, (0,), 1.25, (.25, .75))])

    def test_malformed_duplicates_nonfinite_and_tiny_output_reject_explicitly(self):
        hands = ([(cards('AsAh'), 1.)], [(cards('KsKh'), 1.)])
        boards = [board('2c3d4h7s8c')]
        query = [('D', 0, (0,), 1., (1.,))]
        for modified_hands, modified_boards, modified_queries, limits in (
            ((hands[0] * 2, hands[1]), boards, query, LIMITS),
            (hands, boards * 2, query, LIMITS),
            (hands, boards, [('D', 0, (0, 0), 1., (1.,))], LIMITS),
            (hands, boards, [('D', 0, (0,), 1., (float('nan'),))], LIMITS),
            (hands, boards, query, (1326, 64, 16, 500_000_000, 2_000_000)),
            (hands, boards, query, (1326, 64, 65536, 1, 2_000_000)),
        ):
            self.invoke(wire(modified_hands, modified_boards, modified_queries, limits=limits), success=False)
        self.invoke(wire(hands, boards, query) + b'foreign', success=False)
        for payload_limit in (0, 1, (1 << 30) + 1):
            rejected = self.invoke(wire(hands, boards, query, payload_limit=payload_limit), success=False)
            self.assertFalse(any(line.startswith('READY') for line in rejected))
        tiny = ([(cards('AsAh'), 5e-324), (cards('AdAc'), 1.)], hands[1])
        self.compare(tiny, boards, [('S', 0, (0,), 0, ())])
        self.invoke(wire(tiny, boards, [('M', 0, (0,), 0, ())]), success=False)

    def test_direct_api_limits_and_invalid_reaches_reject_before_ranking(self):
        # Terra authored this separate API-level control. The process facade
        # cannot report cache state after rejecting a malformed query.
        directory = Path(self.temporary.name)
        source = builder.ROOT / 'tests/native/exact_selected_kernel_admission.cpp'
        manifest = self.build_manifest
        executable = directory / ('api-control.exe' if os.name == 'nt' else 'api-control')
        if os.name == 'nt':
            args = [manifest['compiler'], *manifest['flags'], '/I' + str(builder.ROOT / 'native'),
                str(source), '/Fo' + str(directory / 'api-control.obj'), '/Fe' + str(executable)]
        else:
            args = [manifest['compiler'], *manifest['flags'], '-I' + str(builder.ROOT / 'native'),
                str(source), '-o', str(executable)]
        compiled = subprocess.run(args, cwd=directory, capture_output=True, timeout=180)
        self.assertEqual(compiled.returncode, 0, (compiled.stdout + compiled.stderr).decode('utf-8', 'replace'))
        checked = subprocess.run([str(executable)], capture_output=True, timeout=30)
        self.assertEqual(checked.returncode, 0, checked.stderr.decode('utf-8', 'replace'))
        self.assertEqual(checked.stdout.decode().strip(),
            '5 direct API rejection checks passed; rank_calls and rank_cache_size remained zero')

if __name__ == '__main__':
    unittest.main()
