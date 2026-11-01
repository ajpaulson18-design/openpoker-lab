"""Independent physical controls for the opt-in native public-chance seam."""
from fractions import Fraction
from itertools import combinations
import hashlib
import json
from math import comb
import os
from pathlib import Path
import struct
import subprocess
import unittest

from pokerlab.full_deck_prefix_mass import FullDeckPrefixMass
from tests.full_deck_public_chance_reference import (
    FULL52, PROOF9, LiteralChance, all_public_boards, proof_ranges, target_boards)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIMITS = (1326, 65536, 500_000_000, 2_000_000, 1 << 30)
RECEIPT_FIELDS = ("modeled_work", "retained_entries", "peak_scratch_entries",
    "peak_integer_bits", "setup_integer_payload_bits", "peak_integer_payload_bits",
    "prefix_queries", "terminal_queries", "rank_calls", "conversion_calls")


def bits(value):
    return struct.pack(">d", value).hex()


def request(ranges, *, deck=None, prefix=None, terminal=None, convert=False,
            limits=DEFAULT_LIMITS):
    fields = ["OPENPOKER_FULL_DECK_PUBLIC_CHANCE_V1", "deck"]
    fields.extend(["FULL52"] if deck is None else ["REDUCED", str(len(deck)), *map(str, deck)])
    fields.extend(["limits", *map(str, limits), "ranges", *map(str, map(len, ranges))])
    for name, side in zip(("sb", "bb"), ranges):
        fields.append(name)
        for hand, weight in side:
            fields.extend([*map(str, hand), bits(weight)])
    mode = "binary64" if convert else "exact"
    if terminal is None:
        fields.extend(["query", "PREFIX", "prefix", mode, str(len(prefix)), *map(str, prefix)])
    else:
        player, board, kind, payoff, reach, proposal = terminal
        fields.extend(["query", "TERMINAL", "terminal", mode, str(player), kind,
            bits(payoff), format(proposal.numerator, "x"), format(proposal.denominator, "x"),
            str(len(reach)), *map(bits, reach), *map(str, board)])
    return " ".join(fields)


class Tokens:
    def __init__(self, text): self.tokens = iter(text.split())
    def get(self): return next(self.tokens)
    def expect(self, expected):
        got = self.get()
        if got != expected: raise AssertionError(f"expected {expected!r}, received {got!r}")
    def integer(self): return int(self.get())
    def hex(self): return int(self.get(), 16)
    def value(self):
        self.expect("value")
        sign, magnitude = self.get(), self.hex()
        if sign not in ("+", "-", "0") or ((sign == "0") != (magnitude == 0)):
            raise AssertionError("noncanonical signed native exact value")
        return -magnitude if sign == "-" else magnitude


def parse_response(reader, convert):
    header = reader.get()
    if header == "ERR": return {"error": reader.get()}
    if header != "OPENPOKER_FULL_DECK_PUBLIC_CHANCE_RESULT_V1":
        raise AssertionError("unexpected native response contract")
    reader.expect("deck_size"); size = reader.integer()
    reader.expect("deck_mode"); deck_mode = reader.get()
    reader.expect("normalizer_hex"); normalizer = reader.hex()
    reader.expect("weight_denominator_exponents"); powers = (reader.integer(), reader.integer())
    reader.expect("probe_receipt"); probe = tuple(reader.integer() for _ in range(4))
    reader.expect("probe_ownership"); ownership = (reader.integer(), reader.integer())
    kind = reader.get()
    if kind == "prefix":
        prefix_length = reader.integer()
        reader.expect("denominator_hex"); denominator = reader.hex()
        reader.expect("total_numerator_hex"); total = reader.hex()
        values, support = [], []
        for side in (0, 1):
            reader.expect("side")
            if reader.integer() != side: raise AssertionError("global seat identity changed")
            count = reader.integer(); vector, possible = [], []
            for _ in range(count):
                vector.append(Fraction(reader.value(), denominator))
                flag = reader.integer()
                if flag not in (0, 1): raise AssertionError("invalid physical support flag")
                possible.append(bool(flag))
            values.append(vector); support.append(possible)
        expected_bits = sum(map(len, values))
        result = {"values": values, "physical_support": support,
                  "total_mass": Fraction(total, denominator), "prefix_length": prefix_length}
    elif kind == "terminal":
        player, count = reader.integer(), reader.integer()
        reader.expect("denominator_hex"); denominator = reader.hex()
        result = {"values": [Fraction(reader.value(), denominator) for _ in range(count)],
                  "player": player}
        expected_bits = count
    else: raise AssertionError("unknown native result kind")
    if convert:
        reader.expect("binary64_bits")
        if reader.integer() != expected_bits: raise AssertionError("binary64 vector dimensions changed")
        result["bits"] = [reader.get() for _ in range(expected_bits)]
    reader.expect("receipt")
    result.update({"receipt": dict(zip(RECEIPT_FIELDS, (reader.integer() for _ in RECEIPT_FIELDS))),
        "kind": kind, "deck_size": size, "deck_mode": deck_mode,
        "root_mass": Fraction(normalizer) * Fraction(2) ** (-sum(powers)),
        "probe_receipt": probe, "probe_ownership": ownership})
    return result


class PhysicalReferenceFixtureTests(unittest.TestCase):
    def test_declared_nine_card_game_has_all_three_showdown_signs(self):
        ranges = proof_ranges(); oracle = LiteralChance(ranges, PROOF9)
        boards = tuple(all_public_boards(PROOF9)); target = target_boards(ranges, PROOF9)
        self.assertEqual(len(boards), 2520)
        self.assertEqual(len(target), 60)
        self.assertEqual(oracle.normalizer, Fraction(29, 16))
        self.assertEqual(oracle.prefix(())["total_mass"], 1)
        signs = set()
        for board in target:
            for value in oracle.terminal(0, board, "SHOWDOWN", 1.0, (1.0, 1.0), Fraction(1, 2520)):
                signs.add((value > 0) - (value < 0))
        self.assertEqual(signs, {-1, 0, 1})


@unittest.skipUnless(os.environ.get("OPENPOKER_NATIVE_FULL_DECK_CHANCE_EXE"),
                     "explicit source-built full-deck chance probe required")
class NativePublicChanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = Path(os.environ["OPENPOKER_NATIVE_FULL_DECK_CHANCE_EXE"]).resolve()
        cls.manifest_path = cls.exe.parent / "native-exact-build-manifest.json"
        cls.manifest_raw = cls.manifest_path.read_bytes()
        cls.manifest = json.loads(cls.manifest_raw)
        if cls.manifest["target"] != "full-deck-chance":
            raise AssertionError("foreign native build target")
        cls.source_before = {}
        for name, expected in cls.manifest["source_sha256"].items():
            raw = (ROOT / name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise AssertionError("source/build drift before native mathematics: " + name)
            cls.source_before[name] = raw
        if hashlib.sha256(cls.exe.read_bytes()).hexdigest() != cls.manifest["executable_sha256"]:
            raise AssertionError("native executable identity changed")

    @classmethod
    def tearDownClass(cls):
        if cls.manifest_path.read_bytes() != cls.manifest_raw:
            raise AssertionError("native build manifest changed")
        if any((ROOT / name).read_bytes() != raw for name, raw in cls.source_before.items()):
            raise AssertionError("native source changed during controls")
        if hashlib.sha256(cls.exe.read_bytes()).hexdigest() != cls.manifest["executable_sha256"]:
            raise AssertionError("native executable changed during controls")

    def run_queries(self, queries, *, convert=False):
        answers = []
        for start in range(0, len(queries), 1024):
            batch = queries[start:start + 1024]
            completed = subprocess.run([str(self.exe)], input="\n".join(batch) + "\n",
                text=True, capture_output=True, timeout=120)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stderr, "")
            reader = Tokens(completed.stdout)
            parsed = [parse_response(reader, convert) for _ in batch]
            for line, result in zip(batch, parsed):
                if "error" in result:
                    continue
                tokens = line.split()
                requested_work = int(tokens[tokens.index("limits") + 3])
                byte_count, token_count, parse_upper, response_upper = result["probe_receipt"]
                self.assertEqual(byte_count, len(line.encode("ascii")))
                self.assertEqual(token_count, len(tokens))
                self.assertEqual(parse_upper, 16384 + 6 * byte_count + 16 * token_count)
                self.assertLessEqual(parse_upper + 8 * response_upper + result["receipt"]["modeled_work"], requested_work)
                requested_entries = int(tokens[tokens.index("limits") + 4])
                requested_payload = int(tokens[tokens.index("limits") + 5])
                self.assertLessEqual(result["probe_ownership"][0] + result["receipt"]["retained_entries"] +
                                     result["receipt"]["peak_scratch_entries"], requested_entries)
                self.assertLessEqual(result["probe_ownership"][1] + result["receipt"]["peak_integer_payload_bits"], requested_payload)
            answers.extend(parsed)
            self.assertEqual(list(reader.tokens), [], "unbound extra native output")
        return answers

    def assert_prefix(self, result, oracle, prefix, *, convert=False):
        self.assertNotIn("error", result)
        expected = oracle.prefix(prefix)
        self.assertEqual(result["values"], expected["hand_masses"])
        self.assertEqual(result["total_mass"], expected["total_mass"])
        self.assertEqual(result["physical_support"], expected["physical_support"])
        self.assertEqual(result["root_mass"], oracle.normalizer)
        self.assertEqual(result["prefix_length"], len(prefix))
        if convert:
            self.assertEqual(result["bits"], [bits(float(v)) for side in expected["hand_masses"] for v in side])

    def test_full52_prefixes_match_literal_pairs_and_separate_python_operator(self):
        ranges = ((((0, 5), 0.25), ((2, 8), 1.5), ((7, 51), 2.0)),
                  (((2, 8), 0.75), ((0, 12), 2.0), ((15, 44), 0.5)))
        oracle = LiteralChance(ranges)
        python = FullDeckPrefixMass(dict(ranges[0]), dict(ranges[1]))
        prefixes = ((), (1, 6, 20), (1, 6, 20, 48), (1, 6, 20, 48, 50),
                    (0, 2, 7), (0, 2, 7, 8, 15), (1, 6, 20, 50, 48))
        results = self.run_queries([request(ranges, prefix=p, convert=True) for p in prefixes], convert=True)
        for prefix, result in zip(prefixes, results):
            with self.subTest(prefix=prefix):
                self.assert_prefix(result, oracle, prefix, convert=True)
                separate = python.at(prefix)
                self.assertEqual(result["total_mass"], separate.total_mass)
                self.assertEqual(result["values"], [[side[hand] for hand, _ in rows]
                    for side, rows in zip(separate.hand_masses, ranges)])

    def test_all_nine_card_prefix_partitions_preserve_one_global_prior(self):
        ranges = proof_ranges(); oracle = LiteralChance(ranges, PROOF9)
        prefixes = [()] + list(combinations(PROOF9, 3))
        flops = prefixes[1:]
        turns = [(*p, c) for p in flops for c in PROOF9 if c not in p]
        rivers = [(*p, c) for p in turns for c in PROOF9 if c not in p]
        prefixes += turns + rivers
        results = self.run_queries([request(ranges, deck=PROOF9, prefix=p) for p in prefixes])
        masses = {}
        for prefix, result in zip(prefixes, results):
            self.assert_prefix(result, oracle, prefix)
            self.assertEqual(result["deck_mode"], "REDUCED")
            masses[prefix] = result["total_mass"]
        self.assertEqual(sum(masses[p] for p in flops), 1)
        for parent in flops + turns:
            self.assertEqual(sum(masses[(*parent, c)] for c in PROOF9 if c not in parent), masses[parent])
        self.assertEqual(sum(masses[p] > 0 for p in rivers), 60)

    def test_complete_1326_by_1326_prefix_uses_combinatorial_anchor(self):
        side = tuple((hand, 1.0) for hand in combinations(FULL52, 2))
        prefixes = ((), (0, 5, 10), (0, 5, 10, 15), (0, 5, 10, 15, 20))
        results = self.run_queries([request((side, side), prefix=p) for p in prefixes])
        for prefix, result in zip(prefixes, results):
            self.assertNotIn("error", result)
            k = len(prefix)
            divisor = 1 if k == 0 else comb(48, 3) * (45 if k >= 4 else 1) * (44 if k == 5 else 1)
            weight = Fraction(comb(50-k, 2), 1326 * comb(50, 2) * divisor)
            expected = [0 if set(hand).intersection(prefix) else weight for hand, _ in side]
            self.assertEqual(result["values"], [expected, expected])
            self.assertEqual(result["total_mass"], sum(expected))
            self.assertEqual(result["root_mass"], 1326 * comb(50, 2))
            self.assertLessEqual(result["receipt"]["modeled_work"], DEFAULT_LIMITS[2])

    def test_terminal_exact_values_and_bits_use_global_prior_and_proposal_once(self):
        ranges = proof_ranges(); oracle = LiteralChance(ranges, PROOF9)
        board_cases = [sorted(target_boards(ranges, PROOF9))[i] for i in (0, 20, 40)]
        board_cases.append(next(b for b in all_public_boards(PROOF9) if oracle.prefix(b)["total_mass"] == 0))
        queries, expected = [], []
        for board in board_cases:
            for player in (0, 1):
                for kind, payoff in (("FOLD", -0.75), ("FOLD", 2.5), ("SHOWDOWN", 1.25)):
                    reach = (0.25, 0.75); proposal = Fraction(2, 7)
                    queries.append(request(ranges, deck=PROOF9, terminal=(player, board, kind, payoff, reach, proposal), convert=True))
                    expected.append(oracle.terminal(player, board, kind, payoff, reach, proposal))
        for result, values in zip(self.run_queries(queries, convert=True), expected):
            self.assertNotIn("error", result)
            self.assertEqual(result["values"], values)
            self.assertEqual(result["bits"], [bits(float(v)) for v in values])

    def test_all_proposal_outcomes_recover_literal_terminal_expectations(self):
        ranges = proof_ranges(); oracle = LiteralChance(ranges, PROOF9)
        boards = tuple(all_public_boards(PROOF9))
        for player in (0, 1):
            for kind, payoff in (("FOLD", -1.5), ("SHOWDOWN", 2.0)):
                reach = (0.25, 0.75)
                literal = {b: oracle.terminal(player, b, kind, payoff, reach, Fraction(1))
                           for b in boards}
                expected = [sum((v[i] for v in literal.values()), Fraction(0)) for i in range(2)]
                for nonuniform in (False, True):
                    proposals = [(Fraction(PROOF9.index(b[-1])+1, 12600) if nonuniform else Fraction(1, 2520)) for b in boards]
                    self.assertEqual(sum(proposals), 1)
                    results = self.run_queries([request(ranges, deck=PROOF9,
                        terminal=(player, b, kind, payoff, reach, q)) for b, q in zip(boards, proposals)])
                    actual = [Fraction(0), Fraction(0)]
                    for board, result, q in zip(boards, results, proposals):
                        self.assertNotIn("error", result)
                        self.assertEqual(result["values"], [value/q for value in literal[board]],
                                         "per-board mismatch must not cancel in an expectation")
                        for i, value in enumerate(result["values"]): actual[i] += q * value
                    self.assertEqual(actual, expected)

    def test_tiny_priors_preserve_exact_support_and_strict_conversion(self):
        ranges = ((((0, 1), 1e-320), ((2, 3), 1.0)), (((4, 5), 1e300),))
        oracle = LiteralChance(ranges)
        exact_result = self.run_queries([request(ranges, prefix=())])[0]
        self.assert_prefix(exact_result, oracle, ())
        self.assertEqual(exact_result["physical_support"][0], [True, True])
        converted = self.run_queries([request(ranges, prefix=(), convert=True)], convert=True)[0]
        self.assertEqual(converted["error"], "conversion_failure")

    def test_large_proposal_scalars_fit_the_predeclared_response_bound(self):
        ranges = ((((0, 1), 1.0),), (((2, 3), 1.0),))
        proposal = Fraction((1 << 60000) + 1, (1 << 60000) + 3)
        terminal = (0, (4, 5, 6, 7, 8), "FOLD", -1.5, (1.0,), proposal)
        line = request(ranges, terminal=terminal)
        completed = subprocess.run([str(self.exe)], input=(line+"\n").encode("ascii"),
            capture_output=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, b"")
        reader = Tokens(completed.stdout.decode("ascii"))
        result = parse_response(reader, False)
        self.assertNotIn("error", result)
        self.assertEqual(list(reader.tokens), [])
        self.assertLessEqual(len(completed.stdout), result["probe_receipt"][3])
        self.assertTrue(result["values"] == LiteralChance(ranges).terminal(*terminal),
                        "large-proposal exact ratio differs from the physical reference")

    def test_invalid_queries_and_reduced_limits_reject(self):
        ranges = proof_ranges(); board = sorted(target_boards(ranges, PROOF9))[0]
        cases = [request(ranges, deck=PROOF9, prefix=(PROOF9[1], PROOF9[0], PROOF9[2])),
                 request(ranges, deck=PROOF9, prefix=(1, 2, 3)),
                 request(ranges, deck=PROOF9, terminal=(0, board, "SHOWDOWN", -1.0, (1.0, 1.0), Fraction(1, 2))),
                 request(ranges, deck=PROOF9, terminal=(0, board, "FOLD", 1.0, (1.1, 0.0), Fraction(1, 2))),
                 request(ranges, deck=PROOF9, prefix=(), limits=(1326, 65536, 1, 2_000_000, 1 << 30)),
                 request(ranges, deck=PROOF9, prefix=(), limits=(1326, 65536, 500_000_000, 1, 1 << 30)),
                 request(ranges, deck=PROOF9, prefix=(), limits=(1326, 1, 500_000_000, 2_000_000, 1 << 30)),
                 request(((*ranges[0], ranges[0][0]), ranges[1]), deck=PROOF9, prefix=()),
                 request(ranges, deck=PROOF9, terminal=(0, board, "FOLD", 1.0, (1.0, 1.0),
                     Fraction((1 << 60000) + 1, (1 << 60000) + 3)),
                     limits=(1326, 65536, 500_000_000, 2_000_000, 1))]
        self.assertTrue(all("error" in r for r in self.run_queries(cases)))


if __name__ == "__main__": unittest.main()
