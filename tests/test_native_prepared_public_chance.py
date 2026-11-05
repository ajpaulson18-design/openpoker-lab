"""Independent raw prepared-contraction controls; no cumulative trainer admission."""
from fractions import Fraction
from functools import reduce
from itertools import combinations
from math import comb, gcd, lcm
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import os
import unittest
from scripts.preflop_validation import independent_rank
from tests.full_deck_public_chance_reference import card_name
from tests.virtual_frozen_run_control import run_bounded_child

ROOT = Path(__file__).resolve().parents[1]
DECK = (16,17,24,32,33,35,37,43,48)
RANGES = ((((43,48),Fraction(1,8)),((32,43),Fraction(3,4))),
          (((24,37),Fraction(3,8)),((16,32),Fraction(1))))
SAME_RANGES = ((((43,48),Fraction(1,2)),((16,32),Fraction(1,4)),((24,37),Fraction(1))),
               (((43,48),Fraction(3,4)),((24,37),Fraction(1,8))))


def normalized(ranges):
    answer = []
    for side in ranges:
        denominator = lcm(*(w.denominator for _,w in side))
        integers = [int(w*denominator) for _,w in side]
        common = reduce(gcd,integers)
        answer.append(tuple(n//common for n in integers))
    return tuple(answer)


def normalizer(ranges):
    weights = normalized(ranges)
    return sum(weights[0][i]*weights[1][j] for i,(h0,_) in enumerate(ranges[0])
               for j,(h1,_) in enumerate(ranges[1]) if set(h0).isdisjoint(h1))


def fixture(profile):
    if profile == 0:
        return (1,3),2
    if profile == 1:
        return ((((1<<53)-1)**2)<<53,((1<<52)+1)**3),159
    if profile == 2:
        return (0,0),300
    if profile == 3:
        return (1,3),2200
    if profile == 4:
        return (1,1),0
    if profile == 5:
        return (1<<2200,0),2200
    raise ValueError('unknown fixed prepared fixture')


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


def divisor(prefix):
    n = len(prefix)
    return 1 if n == 0 else comb(len(DECK)-4,3)*(len(DECK)-7 if n >= 4 else 1)*(len(DECK)-8 if n == 5 else 1)


def literal(player, board, showdown, reaches, ranges=RANGES):
    """Physical private-pair sum using independently normalized integer priors."""
    weights = normalized(ranges)
    blocked = set(board)
    answer = []
    for i,(own,_) in enumerate(ranges[player]):
        value = 0
        if set(own).isdisjoint(blocked):
            for j,(other,_) in enumerate(ranges[1-player]):
                if not set(other).isdisjoint(blocked | set(own)):
                    continue
                sign = 1
                if showdown:
                    a = independent_rank(tuple(map(card_name,(*own,*board))))
                    b = independent_rank(tuple(map(card_name,(*other,*board))))
                    sign = (a>b)-(a<b)
                value += weights[player][i]*weights[1-player][j]*reaches[j]*sign
        answer.append(value)
    return answer


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
        raise AssertionError('explicit prepared-chance build identity differs')
    for name,value in manifest['source_sha256'].items():
        if sha(root/name) != value:
            raise AssertionError('prepared-chance source/build drift: '+name)
    dependency = json.loads((root/'third_party/boost-multiprecision-1.92.0/manifest.json').read_bytes())
    for name,value in dependency['headers_sha256'].items():
        if sha(exe.parent/'boost-include'/name) != value:
            raise AssertionError('extracted prepared-chance header drift')
    return raw,manifest


class PreparedReferenceTests(unittest.TestCase):
    def test_normalized_priors_prefixes_and_all_showdown_signs(self):
        self.assertEqual(normalized(RANGES),((1,6),(3,8)))
        self.assertEqual(normalizer(RANGES),29)
        self.assertEqual(normalized(SAME_RANGES),((2,1,4),(6,1)))
        self.assertEqual(normalizer(SAME_RANGES),33)
        self.assertEqual(len(tuple(prefixes())),3109)
        signs = set()
        for board in prefixes():
            if len(board)==5:
                signs.update((v>0)-(v<0) for v in literal(0,board,True,(1,1)))
        self.assertEqual(signs,{-1,0,1})
        for profile in range(6):
            n,e = fixture(profile)
            self.assertTrue(all(0 <= value <= (1<<e) for value in n))
        self.assertEqual(float(Fraction(fixture(3)[0][0],1<<2200)),0.0)


@unittest.skipUnless(os.environ.get('OPENPOKER_NATIVE_PREPARED_PUBLIC_CHANCE_EXE'),
                     'explicit source-built prepared-chance controls required')
class NativePreparedChanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = Path(os.environ['OPENPOKER_NATIVE_PREPARED_PUBLIC_CHANCE_EXE']).resolve()
        cls.identity = authenticate(cls.exe,ROOT,'prepared-public-chance-controls')
        cls.temp = None
        destination = os.environ.get('OPENPOKER_NATIVE_PREPARED_PUBLIC_CHANCE_CONTROL_DIR')
        if destination is None:
            cls.temp = TemporaryDirectory()
            destination = cls.temp.name
        cls.output = Path(destination)
        cls.output.mkdir(parents=True,exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if authenticate(cls.exe,ROOT,'prepared-public-chance-controls') != cls.identity:
            raise AssertionError('prepared source/build changed during controls')
        if cls.temp is not None:
            cls.temp.cleanup()

    def invoke(self,name,selectors,cap=2_100_000):
        directory = self.output/name
        expected = self.identity[1]['executable_sha256']
        before = sha(self.exe)
        self.assertEqual(before,expected)
        observed = run_bounded_child([str(self.exe),*selectors],b'',directory,stdout_limit=cap)
        after = sha(self.exe)
        (directory/'native-identity.json').write_text(json.dumps({'expected_sha256':expected,
            'before_sha256':before,'after_sha256':after,
            'captured_manifest_sha256':hashlib.sha256(self.identity[0]).hexdigest()})+'\n')
        self.assertEqual(after,expected)
        self.assertEqual(observed['status'],'exited')
        self.assertTrue(observed['actual_exit_observed'])
        self.assertEqual(observed['returncode'],0,(directory/'stderr.bin').read_bytes())
        self.assertEqual((directory/'stderr.bin').read_bytes(),b'')
        return (directory/'stdout.bin').read_text(encoding='ascii').splitlines()

    def test_every_full_board_and_prefix_fold_six_exact_dyadic_reaches_both_seats(self):
        count = 0
        for profile in range(6):
            reach,e = fixture(profile)
            for player in (0,1):
                for mode in (0,1):
                    lines = self.invoke(f'p{profile}-seat{player}-mode{mode}',list(map(str,(profile,player,mode))))
                    self.assertEqual(lines[0],f'PREPARED_CASES_V1 {profile} {player} {mode} 1d')
                    boards = [p for p in prefixes() if not mode or len(p)==5]
                    self.assertEqual(len(lines),len(boards)+2)
                    previous_work = 0
                    rank_calls = 0
                    for index,(board,line) in enumerate(zip(boards,lines[1:-1])):
                        self.assertLessEqual(len(line)+1,2048)
                        fields = line.split()
                        self.assertEqual(len(fields),13)
                        self.assertEqual(tuple(map(int,fields[:3])),(index,divisor(board),e))
                        raw = [int(n,16) for n in fields[3:5]]
                        self.assertEqual(raw,literal(player,board,bool(mode),reach),(profile,player,mode,board))
                        work,ranks,hits,misses,evictions,entries,bits,payload = map(int,fields[5:])
                        self.assertGreater(work,previous_work)
                        self.assertLessEqual(work,500_000_000)
                        self.assertLessEqual(entries,2_000_000)
                        self.assertLessEqual(bits,65536)
                        self.assertLessEqual(payload,1<<30)
                        self.assertEqual(hits,0)
                        if mode:
                            rank_calls += sum(set(hand).isdisjoint(board) for side in RANGES for hand,_ in side)
                        self.assertEqual(ranks,rank_calls)
                        self.assertEqual(misses,index+1 if mode else 0)
                        self.assertEqual(evictions,max(0,index+1-64) if mode else 0)
                        previous_work = work
                        count += 1
                    self.assertEqual(lines[-1],f'END {len(boards)} {previous_work}')
        self.assertEqual(count,67548)

    def test_invalid_reaches_prefixes_and_query_resources_poison_before_arrays_or_ranks(self):
        lines = self.invoke('guards',['guards'],65536)
        self.assertEqual(len(lines),19)
        for line in lines:
            fields = line.split()
            self.assertEqual(fields[0],'GUARD')
            self.assertEqual(fields[2],'PASS',line)
            self.assertEqual(fields[-2:],['0','0'])

    def test_ordered_key_lru_cache_hits_and_zero_reach_ranks(self):
        self.assertEqual(self.invoke('cache',['cache'],65536),['CACHE_ORDERED_LRU_ZERO_REACH PASS'])

    def test_owner_aggregates_prior_setup_and_dynamic_work_until_poisoned(self):
        lines = self.invoke('cumulative',['cumulative'],65536)
        self.assertEqual(len(lines),1)
        fields = lines[0].split()
        self.assertEqual(fields[:2],['CUMULATIVE_POISON','PASS'])
        self.assertGreater(int(fields[2]),21504)
        self.assertGreater(int(fields[3]),0)

    def test_initial_snapshot_and_prior_limits_precede_execution(self):
        self.assertEqual(self.invoke('setup',['setup'],65536),[f'SETUP {i} PASS' for i in range(5)])
        self.assertEqual(self.invoke('snapshot',['snapshot'],65536),['SNAPSHOT 1d b 12'])

    def test_asymmetric_original_rows_and_same_holding_blocker_addback(self):
        lines = self.invoke('same',['same'],65536)
        self.assertEqual(len(lines),8)
        for line in lines:
            fields = line.split()
            self.assertEqual(fields[0],'SAME')
            player,k = map(int,fields[1:3])
            self.assertEqual(int(fields[3],16),33)
            board = () if k==0 else (16,17,33) if k==1 else (16,17,32,33,35)
            self.assertEqual(int(fields[4]),divisor(board))
            reach = (3,1) if player==0 else (3,0,4)
            actual = [int(n,16) for n in fields[5:]]
            self.assertEqual(actual,literal(player,board,k==3,reach,SAME_RANGES))
