"""Literal physical-pair controls for visible-prefix fold transport; no trainer claim."""
from collections import Counter
from fractions import Fraction
from itertools import combinations
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import math
import os
import unittest
from tests.virtual_frozen_run_control import run_bounded_child

ROOT = Path(__file__).resolve().parents[1]
DECK = (16,17,24,32,33,35,37,43,48)
RANGES = ((((43,48), Fraction(1,8)), ((32,43), Fraction(3,4))),
          (((24,37), Fraction(3,8)), ((16,32), Fraction(1))))
# Independent original global collision-conditioned prior, never a per-prefix
# or per-player renormalization and never a production kernel query.
NORMALIZER = sum(w0*w1 for h0,w0 in RANGES[0] for h1,w1 in RANGES[1]
                 if set(h0).isdisjoint(h1))


def reaches(profile):
    if profile == 0:
        return Fraction(1,4), Fraction(3,4)
    if profile == 1:
        return Fraction(((1<<53)-1)**2,1<<106), Fraction(((1<<52)+1)**3,1<<159)
    if profile == 2:
        d = ((1<<89)-1)*((1<<83)-1)
        return Fraction(d//3+1,d), Fraction(d-7,d)
    if profile == 3:
        return Fraction(0), Fraction(0)
    if profile == 4:
        return Fraction(1,1<<2200), Fraction(3,1<<2200)
    if profile == 5:
        return Fraction(1), Fraction(1)
    raise ValueError('unknown fixed prefix reach fixture')


def prefixes():
    yield ()
    for flop in combinations(DECK,3):
        yield flop
        for turn in DECK:
            if turn in flop:
                continue
            yield (*flop,turn)
            for river in DECK:
                if river not in (*flop,turn):
                    yield (*flop,turn,river)


def literal(player, prefix, mode, reach):
    """Direct ordered private-pair sum; no ranker or future board enumeration."""
    payoff = (Fraction(-3,4),Fraction(5,2),Fraction(0),Fraction(1<<200))[mode]
    # Every compatible private pair leaves exactly five physical cards.
    # Prefix probability is 1 / C(5,3) / 2 / 1 at flop/turn/river.
    k = len(prefix)
    d_k = 1 if k == 0 else math.comb(len(DECK)-4,3)
    if k >= 4:
        d_k *= len(DECK)-7
    if k == 5:
        d_k *= len(DECK)-8
    values = []
    blocked = set(prefix)
    for own,wi in RANGES[player]:
        value = Fraction(0)
        if set(own).isdisjoint(blocked):
            for (opponent,wj),sequence in zip(RANGES[1-player],reach):
                if set(opponent).isdisjoint(blocked | set(own)):
                    value += wi*wj*sequence*payoff
        values.append(value/(NORMALIZER*d_k))
    return values


def sha(path):
    path = Path(path)
    size = path.stat().st_size
    if size > 64 << 20:
        raise AssertionError('component hash input size bound')
    h = hashlib.sha256()
    total = 0
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(65536), b''):
            total += len(chunk)
            if total > 64 << 20:
                raise AssertionError('component hash input grew past bound')
            h.update(chunk)
    if total != size or path.stat().st_size != size:
        raise AssertionError('component hash input size drift')
    return h.hexdigest()


def authenticate(exe, root, target):
    from scripts.build_native_exact_four_street import TARGETS
    exe,root = Path(exe).resolve(),Path(root).resolve()
    path = exe.parent/'native-exact-build-manifest.json'
    raw = path.read_bytes()
    manifest = json.loads(raw)
    required = {*TARGETS[target][1], 'scripts/build_native_exact_four_street.py',
                'third_party/boost-multiprecision-1.92.0/manifest.json',
                'third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt',
                'third_party/boost-multiprecision-1.92.0/headers.zip'}
    if (manifest.get('target') != target or set(manifest['source_sha256']) != required or
            Path(manifest['executable']).resolve() != exe or sha(exe) != manifest['executable_sha256'] or
            sha(manifest['compiler']) != manifest['compiler_sha256']):
        raise AssertionError('explicit prefix-fold build identity differs')
    for name,value in manifest['source_sha256'].items():
        if sha(root/name) != value:
            raise AssertionError('prefix-fold source/build drift: '+name)
    dependency = json.loads((root/'third_party/boost-multiprecision-1.92.0/manifest.json').read_bytes())
    for name,value in dependency['headers_sha256'].items():
        if sha(exe.parent/'boost-include'/name) != value:
            raise AssertionError('extracted prefix-fold header drift')
    return raw,manifest


class PrefixFoldReferenceTests(unittest.TestCase):
    def test_declared_prefixes_and_independent_normalizer(self):
        self.assertEqual(NORMALIZER,Fraction(29,64))
        self.assertEqual(Counter(map(len,prefixes())),{0:1,3:84,4:504,5:2520})
        self.assertEqual(len(set(prefixes())),3109)
        for value in reaches(1):
            self.assertGreater(value.numerator.bit_length(),53)
            self.assertNotEqual(value,Fraction.from_float(float(value)))
        self.assertEqual(reaches(2)[0].denominator % 2,1)
        self.assertGreater(reaches(4)[0],0)
        self.assertEqual(float(reaches(4)[0]),0.0)
        # Positive prior physical support must survive zero opponent reach.
        for player in (0,1):
            self.assertTrue(all(x>0 for x in literal(player,(),1,reaches(5))))
            self.assertEqual(literal(player,(),1,reaches(3)),[0,0])


@unittest.skipUnless(os.environ.get('OPENPOKER_NATIVE_PREFIX_FOLD_EXECUTABLE'),
                     'explicit source-built prefix-fold controls required')
class NativePrefixFoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = Path(os.environ['OPENPOKER_NATIVE_PREFIX_FOLD_EXECUTABLE']).resolve()
        cls.identity = authenticate(cls.exe,ROOT,'full-deck-prefix-fold-controls')
        cls.temp = None
        destination = os.environ.get('OPENPOKER_NATIVE_PREFIX_FOLD_CONTROL_DIR')
        if destination is None:
            cls.temp = TemporaryDirectory()
            destination = cls.temp.name
        cls.output = Path(destination)
        cls.output.mkdir(parents=True,exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if authenticate(cls.exe,ROOT,'full-deck-prefix-fold-controls') != cls.identity:
            raise AssertionError('prefix-fold build/source changed during controls')
        if cls.temp is not None:
            cls.temp.cleanup()

    def invoke(self, name, selectors, *, cap=2_100_000):
        directory = self.output/name
        expected = self.identity[1]['executable_sha256']
        before = sha(self.exe)
        self.assertEqual(before,expected,'prefix-fold executable changed before launch')
        observed = run_bounded_child([str(self.exe),*selectors],b'',directory,stdout_limit=cap)
        after = sha(self.exe)
        (directory/'native-identity.json').write_text(json.dumps({'expected_sha256':expected,
            'before_sha256':before,'after_sha256':after,
            'captured_manifest_sha256':hashlib.sha256(self.identity[0]).hexdigest()})+'\n')
        self.assertEqual(after,expected,'prefix-fold executable changed after launch')
        self.assertEqual(observed['status'],'exited')
        self.assertTrue(observed['actual_exit_observed'])
        self.assertEqual(observed['returncode'],0,(directory/'stderr.bin').read_bytes())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        return (directory/'stdout.bin').read_text(encoding='ascii').splitlines()

    def test_all_declared_prefixes_six_exact_reaches_both_seats_signed_payoffs(self):
        count = 0
        for profile in range(6):
            reach = reaches(profile)
            for player in (0,1):
                for mode in range(4):
                    name = f'p{profile}-seat{player}-mode{mode}'
                    lines = self.invoke(name,list(map(str,(profile,player,mode))))
                    self.assertEqual(lines[0],f'PREFIX_FOLD_CASES_V1 {profile} {player} {mode}')
                    self.assertEqual(len(lines),3111)
                    total_work = 0
                    for index,(prefix,line) in enumerate(zip(prefixes(),lines[1:-1])):
                        self.assertLessEqual(len(line)+1,1024)
                        values = line.split()
                        self.assertEqual(len(values),8)
                        self.assertEqual(int(values[0]),index)
                        d = int(values[1],16)
                        self.assertGreater(d,0)
                        actual = [Fraction(int(x,16),d) for x in values[2:4]]
                        self.assertEqual(actual,literal(player,prefix,mode,reach),
                                         (profile,player,mode,prefix))
                        work,bits,payload,ranks = map(int,values[4:])
                        self.assertLessEqual(work,500_000_000)
                        self.assertLessEqual(bits,65536)
                        self.assertLessEqual(payload,1<<30)
                        self.assertEqual(ranks,0)
                        total_work += work
                        count += 1
                    self.assertEqual(lines[-1],f'END 3109 {total_work}')
        self.assertEqual(count,149232)

    def test_invalid_prefixes_blocked_reaches_and_resources_reject_before_completion(self):
        lines = self.invoke('guards',['guards'],cap=65536)
        self.assertEqual(len(lines),22)
        for line in lines:
            fields = line.split()
            self.assertEqual(fields[0],'GUARD')
            self.assertEqual(fields[2],'PASS',line)
            self.assertEqual(fields[-2:],['0','0'])

    def test_zero_reach_does_not_remove_positive_prior_physical_support(self):
        self.assertEqual(self.invoke('support',['support'],cap=65536),
                         ['PHYSICAL_SUPPORT_WITH_ZERO_REACH PASS'])
