"""Independent rational-reach component controls; no training claim."""
from fractions import Fraction
from itertools import combinations, permutations
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import os
import subprocess
import unittest
from scripts.preflop_validation import independent_rank
from tests.virtual_frozen_run_control import run_bounded_child
from tests.full_deck_public_chance_reference import card_name

ROOT = Path(__file__).resolve().parents[1]
DECK = (16,17,24,32,33,35,37,43,48)
RANGES = ((((43,48), Fraction(1,8)), ((32,43), Fraction(3,4))),
          (((24,37), Fraction(3,8)), ((16,32), Fraction(1))))
NORMALIZER = sum(w0*w1 for h0,w0 in RANGES[0] for h1,w1 in RANGES[1] if not set(h0)&set(h1))


def reaches(profile):
    if profile == 0:
        return Fraction(1,4), Fraction(3,4)
    if profile == 1:
        return Fraction(((1<<53)-1)**2, 1<<106), Fraction(((1<<52)+1)**3, 1<<159)
    if profile == 2:
        d = ((1<<89)-1)*((1<<83)-1)
        return Fraction(d//3+1,d), Fraction(d-7,d)
    if profile == 3:
        return Fraction(0), Fraction(0)
    if profile == 4:
        return Fraction(1,1<<2200), Fraction(3,1<<2200)
    if profile == 5:
        return Fraction(1), Fraction(1)
    raise ValueError('unknown exact reach fixture')


def boards():
    for flop in combinations(DECK,3):
        for turn,river in permutations([c for c in DECK if c not in flop],2):
            yield (*flop,turn,river)


def literal(player, board, mode, reach):
    """Physical pair sum with independent best-five rank; never float(reach)."""
    answer = []
    payoff = (Fraction(-3,4), Fraction(5,2), Fraction(5,4), Fraction(1<<200))[mode]
    blocked = set(board)
    denominator = NORMALIZER * 20 * Fraction(1,2520)
    for own,wi in RANGES[player]:
        value = Fraction(0)
        if not set(own)&blocked:
            for (opponent,wj),sequence in zip(RANGES[1-player],reach):
                if sequence == 0 or set(opponent)&(blocked|set(own)):
                    continue
                sign = 1
                if mode >= 2:
                    r0 = independent_rank(tuple(map(card_name,(*own,*board))))
                    r1 = independent_rank(tuple(map(card_name,(*opponent,*board))))
                    sign = (r0>r1)-(r0<r1)
                value += wi*wj*sequence*payoff*sign
        answer.append(value/denominator)
    return answer


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
        raise AssertionError('explicit exact-reach build identity differs')
    for name,value in manifest['source_sha256'].items():
        if sha(root/name) != value:
            raise AssertionError('exact-reach source/build drift: '+name)
    dependency = json.loads((root/'third_party/boost-multiprecision-1.92.0/manifest.json').read_bytes())
    for name,value in dependency['headers_sha256'].items():
        if sha(exe.parent/'boost-include'/name) != value:
            raise AssertionError('extracted exact-reach header drift')
    return raw,manifest


class ExactReachReferenceTests(unittest.TestCase):
    def test_fixture_requires_more_than_binary64_reach_transport(self):
        self.assertEqual(NORMALIZER,Fraction(29,64))
        for value in reaches(1):
            self.assertGreater(value.numerator.bit_length(),53)
            self.assertNotEqual(value,Fraction.from_float(float(value)))
        self.assertGreater(reaches(4)[0],0)
        self.assertEqual(float(reaches(4)[0]),0.0)
        self.assertEqual(len(tuple(boards())),2520)


@unittest.skipUnless(os.environ.get('OPENPOKER_NATIVE_EXACT_REACH_EXE'),
                     'explicit source-built exact-reach component controls required')
class NativeExactReachTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = Path(os.environ['OPENPOKER_NATIVE_EXACT_REACH_EXE']).resolve()
        cls.identity = authenticate(cls.exe,ROOT,'full-deck-exact-reach-controls')
        cls.temp = None
        destination = os.environ.get('OPENPOKER_NATIVE_EXACT_REACH_CONTROL_DIR')
        if destination is None:
            cls.temp = TemporaryDirectory()
            destination = cls.temp.name
        cls.output = Path(destination)
        cls.output.mkdir(parents=True,exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if authenticate(cls.exe,ROOT,'full-deck-exact-reach-controls') != cls.identity:
            raise AssertionError('exact-reach build/source changed during controls')
        if cls.temp is not None:
            cls.temp.cleanup()

    def invoke(self, name, selectors, *, cap=2_100_000):
        directory = self.output/name
        observed = run_bounded_child([str(self.exe),*selectors],b'',directory,stdout_limit=cap)
        self.assertEqual(observed['status'],'exited')
        self.assertTrue(observed['actual_exit_observed'])
        self.assertEqual(observed['returncode'],0,(directory/'stderr.bin').read_bytes())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        return (directory/'stdout.bin').read_text(encoding='ascii').splitlines()

    def test_all_boards_exact_values_for_six_reaches_both_players_and_signed_payoffs(self):
        count = 0
        for profile in range(6):
            reach = reaches(profile)
            for player in (0,1):
                for mode in range(4):
                    name = f'p{profile}-seat{player}-mode{mode}'
                    lines = self.invoke(name,list(map(str,(profile,player,mode))))
                    self.assertEqual(lines[0],f'EXACT_REACH_CASES_V1 {profile} {player} {mode}')
                    self.assertEqual(len(lines),2522)
                    total_work = 0
                    for index,(board,line) in enumerate(zip(boards(),lines[1:-1])):
                        values = line.split()
                        self.assertEqual(len(values),8)
                        self.assertEqual(int(values[0]),index)
                        d = int(values[1],16)
                        self.assertGreater(d,0)
                        actual = [Fraction(int(x,16),d) for x in values[2:4]]
                        self.assertEqual(actual,literal(player,board,mode,reach),(profile,player,mode,board))
                        work,bits,payload,ranks = map(int,values[4:])
                        self.assertLessEqual(work,500_000_000)
                        self.assertLessEqual(bits,65536)
                        self.assertLessEqual(payload,1<<30)
                        expected_ranks = 0
                        if mode >= 2 and any(reach):
                            expected_ranks = sum(not set(h)&set(board) for h,_ in RANGES[player])
                            expected_ranks += sum(r!=0 and not set(h)&set(board)
                                                  for (h,_),r in zip(RANGES[1-player],reach))
                        self.assertEqual(ranks,expected_ranks)
                        total_work += work
                        count += 1
                    self.assertEqual(lines[-1],f'END 2520 {total_work}')
        self.assertEqual(count,120960)

    def test_rejected_inputs_and_resources_enter_no_rank_or_complete_terminal(self):
        lines = self.invoke('guards',['guards'],cap=65536)
        self.assertEqual(len(lines),13)
        for line in lines:
            fields = line.split()
            self.assertEqual(fields[0],'GUARD')
            self.assertEqual(fields[2],'PASS',line)
            self.assertEqual(fields[-2:],['0','0'])


@unittest.skipUnless(all(os.environ.get(k) for k in ('OPENPOKER_NATIVE_FULL_DECK_CHANCE_EXE',
    'OPENPOKER_NATIVE_EXACT_REACH_BASELINE_EXE','OPENPOKER_NATIVE_EXACT_REACH_BASELINE_REPO')),
    'explicit current and active-baseline probes required for raw compatibility')
class LegacyRawParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = Path(os.environ['OPENPOKER_NATIVE_FULL_DECK_CHANCE_EXE']).resolve()
        cls.baseline = Path(os.environ['OPENPOKER_NATIVE_EXACT_REACH_BASELINE_EXE']).resolve()
        cls.baseline_repo = Path(os.environ['OPENPOKER_NATIVE_EXACT_REACH_BASELINE_REPO']).resolve()
        cls.identities = (authenticate(cls.current,ROOT,'full-deck-chance'),
                          authenticate(cls.baseline,cls.baseline_repo,'full-deck-chance'))
        cls.temp = None
        destination = os.environ.get('OPENPOKER_NATIVE_EXACT_REACH_CONTROL_DIR')
        if destination is None:
            cls.temp = TemporaryDirectory()
            destination = cls.temp.name
        cls.output = Path(destination)/'legacy-parity'
        cls.output.mkdir(parents=True,exist_ok=False)

    @classmethod
    def tearDownClass(cls):
        actual = (authenticate(cls.current,ROOT,'full-deck-chance'),
                  authenticate(cls.baseline,cls.baseline_repo,'full-deck-chance'))
        if actual != cls.identities:
            raise AssertionError('raw parity sources/builds changed')
        if cls.temp is not None:
            cls.temp.cleanup()

    def test_raw_outputs_and_receipts_match_active_baseline(self):
        from tests.test_native_full_deck_public_chance import request, Tokens, parse_response
        ranges = tuple(tuple((hand,float(weight)) for hand,weight in side) for side in RANGES)
        queries = []
        for board in boards():
            for player in (0,1):
                for kind,pay in [('FOLD',-1.5),('SHOWDOWN',2.0)]:
                    queries.append((request(ranges,deck=DECK,
                        terminal=(player,board,kind,pay,(0.25,0.75),Fraction(1,2520))),False))
        selected = ((16,17,24,32,33),(16,17,32,33,35),(16,17,33,35,48),(17,24,33,35,37))
        reach_cases = ((0.0,0.0),(-0.0,0.0),(0.25,0.75),(0.0,1.0),
                       (float.fromhex('0x1p-1022'),float.fromhex('0x1p-1074')),
                       (float.fromhex('0x1.fffffffffffffp-1'),float.fromhex('0x1p-500')))
        for board in selected:
            for player in (0,1):
                for reach in reach_cases:
                    for kind,pay in [('FOLD',-0.75),('SHOWDOWN',1.25),('SHOWDOWN',float(1<<200)),('SHOWDOWN',0.0)]:
                        for proposal in (Fraction(2,7),Fraction(3,11)):
                            convert = reach in ((0.0,0.0),(0.25,0.75),(0.0,1.0))
                            queries.append((request(ranges,deck=DECK,
                                terminal=(player,board,kind,pay,reach,proposal),convert=convert),convert))
        for offset in range(0,len(queries),128):
            batch = queries[offset:offset+128]
            raw = ('\n'.join(line for line,_ in batch)+'\n').encode('ascii')
            self.assertLessEqual(len(raw),65536)
            outputs = []
            for label,exe in [('baseline',self.baseline),('current',self.current)]:
                directory = self.output/f'{offset:05d}-{label}'
                directory.mkdir()
                (directory/'request.bin').write_bytes(raw)
                try:
                    completed = subprocess.run([str(exe)],input=raw,capture_output=True,timeout=120)
                except subprocess.TimeoutExpired as error:
                    (directory/'stdout.bin').write_bytes(error.stdout or b'')
                    (directory/'stderr.bin').write_bytes(error.stderr or b'')
                    (directory/'process.json').write_text(json.dumps({'status':'timeout',
                        'actual_exit_observed':False,'automatic_retries':0})+'\n')
                    raise
                (directory/'stdout.bin').write_bytes(completed.stdout)
                (directory/'stderr.bin').write_bytes(completed.stderr)
                (directory/'process.json').write_text(json.dumps({'status':'exited',
                    'actual_exit_observed':True,'returncode':completed.returncode,'automatic_retries':0,
                    'stdout_sha256':hashlib.sha256(completed.stdout).hexdigest()})+'\n')
                self.assertEqual(completed.returncode,0,completed.stderr)
                self.assertEqual(completed.stderr,b'')
                # Fixed four-row inputs and <=1,100-bit old aligned reaches bound
                # each fixture response; cap bytes before decode/parse. This
                # development helper is not a process heap/RSS bound.
                self.assertLessEqual(len(completed.stdout),2_100_000)
                reader = Tokens(completed.stdout.decode('ascii'))
                for _,convert in batch:
                    result = parse_response(reader,convert)
                    self.assertNotIn('error',result)
                with self.assertRaises(StopIteration):
                    reader.get()
                outputs.append(completed.stdout)
            self.assertEqual(outputs[0],outputs[1],f'raw legacy compatibility offset {offset}')
        self.assertEqual(len(queries),10464)


if __name__ == '__main__':
    unittest.main()
