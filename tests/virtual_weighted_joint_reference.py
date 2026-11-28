"""Independent exact weighted ticket law, not a sampler or solver admission.

Float decoding uses struct and Fraction.from_float. Compatible masses use a
literal streamed double loop, never the candidate's bucket/index algorithm.
Only O(H) range/CDF data is retained; no pair table or board product is built.
"""
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import combinations, islice, permutations
from math import comb, gcd, isfinite, lcm
import struct

from scripts.matrix_free_certificate_budget import Budget
from scripts.preflop_validation import independent_rank
from tests.full_deck_public_chance_reference import PROOF9, card_name

U64_MAX = (1 << 64) - 1
MAX_HANDS = 1326
MAX_PRIVATE_QUERIES = 3072
LIMITS = {'work': 500_000_000, 'entries': 8_000_000,
          'created_bits': 16_000_000_000, 'integer_bits': 4096}


def require(value, message):
    if not value:
        raise ValueError(message)


def dense_hand_index(hand):
    """Candidate's declared representation formula, used only by its unit gate.

    The numeric law below does not use this index or a candidate card bucket.
    """
    require(type(hand) is tuple and len(hand) == 2 and all(type(c) is int for c in hand) and
            0 <= hand[0] < hand[1] < 52, 'weighted dense physical hand')
    a, b = hand
    return a * (103 - a) // 2 + b - a - 1


def forecast(deck_size, counts):
    require(type(deck_size) is int and deck_size in (9, 52) and type(counts) is tuple and len(counts) == 2 and
            all(type(n) is int and 1 <= n <= MAX_HANDS for n in counts), 'weighted oracle geometry')
    h0, h1 = counts; h = h0 + h1; pairs = h0 * h1
    remaining = deck_size - 4
    flops = comb(remaining, 3); tails = (remaining - 3) * (remaining - 4)
    worlds = 640 if deck_size == 9 else 64
    prefixes = 4 if deck_size == 9 else 1
    # Prepaid complete request, including optional one second literal product
    # census, <=3072 linear pair selections, bounded board/rank queries and
    # prefix scans. Operations are logical reference charges, not CPU promises.
    work = (65536 + 65536 * h + 64 * pairs + MAX_PRIVATE_QUERIES * (8 * h + 256) +
            worlds * (32 * flops + 16 * tails + 8192 + 4096) + prefixes * 32 * pairs)
    # Fraction binary64 denominators <=1075 bits; aligned integers <=2150.
    # 2304 covers unreduced normalization-scale products. Products after width
    # admission <=128, compatible sums <=75, row products <=139, total Z<=150.
    # Every family reserves operand/intermediate/output bit cells before math.
    bits = (1_000_000 + 131072 * h + 3072 * pairs + 512 * MAX_PRIVATE_QUERIES * h +
            worlds * (1024 * flops + 512 * tails + 262144) + prefixes * 2048 * pairs)
    entries = 4096 + 64 * h + 16 * h0 + 64 * worlds + 4 * MAX_PRIVATE_QUERIES + 16 * prefixes + 1024
    return {'work': work, 'entries': entries, 'created_bits': bits, 'integer_bits': 2304,
            'pair_cells_retained': 0, 'streamed_pairs_per_census': pairs,
            'private_query_limit': MAX_PRIVATE_QUERIES, 'world_query_limit': worlds,
            'prefix_query_limit': prefixes, 'board_count': flops * tails,
            'scope': 'Complete independent law-reference reservation; no RNG/native/training/full52 solver admission.'}


class _Meter:
    def __init__(self, plan, limits):
        chosen = dict(LIMITS)
        require(limits is None or type(limits) is dict and set(limits) <= set(LIMITS), 'weighted reduce-only limits')
        for key, value in (limits or {}).items():
            require(type(value) is int and 0 < value <= LIMITS[key], 'weighted limits are reduce-only')
            chosen[key] = value
        require(all(plan[key] <= chosen[key] for key in LIMITS), 'weighted complete reference admission rejected')
        self.plan = plan; self.budget = Budget(chosen)
        self.budget.charge('weighted_complete_request_reserved', plan['work'])
        self.budget.entries(plan['entries'] - 2, 'weighted source/CDF/returned-world/scratch reservation')
        self.budget.created_bits = plan['created_bits']; self.budget.max_forecast_bits = plan['integer_bits']
        self.decoded_rows = self.pair_visits = self.audit_calls = self.private_queries = self.world_queries = self.prefix_queries = 0

    def begin(self, family, maximum):
        used = getattr(self, family)
        require(used < maximum, 'weighted prepaid ' + family + ' limit')
        setattr(self, family, used + 1)


@dataclass(frozen=True)
class Normalization:
    denominator_lcm: int
    aligned_gcd: int
    scale: Fraction


@dataclass(frozen=True)
class Pair:
    holding_indices: tuple
    holdings: tuple
    integer_mass: int
    probability: Fraction


@dataclass(frozen=True)
class World:
    private_ticket: int
    board_rank: int
    holding_indices: tuple
    holdings: tuple
    board: tuple
    integer_mass: int
    probability: Fraction
    showdown_sign: object


def _board(deck, private, rank):
    # Deliberately different from native count-and-skip combinatorial unranking:
    # stream the stdlib combinations iterator to the requested rank.
    remaining = tuple(card for card in deck if card not in private)
    tail_count = (len(remaining) - 3) * (len(remaining) - 4)
    flop_rank, tail_rank = divmod(rank, tail_count)
    flop = next(islice(combinations(remaining, 3), flop_rank, None))
    tail_cards = tuple(card for card in remaining if card not in flop)
    tail = next(islice(permutations(tail_cards, 2), tail_rank, None))
    return (*flop, *tail)


@dataclass(frozen=True)
class Law:
    deck: tuple
    ranges: tuple
    weights: tuple
    compatible_masses: tuple
    cdf: tuple
    normalizer: int
    normalization: tuple
    _meter: object = field(repr=False, compare=False)
    _origin: tuple = field(repr=False, compare=False)

    def _check(self):
        require(type(self._origin) is tuple and len(self._origin) == 7 and
                all(a is b for a, b in zip((self.deck, self.ranges, self.weights, self.compatible_masses,
                                           self.cdf, self.normalization), self._origin[:6])) and
                self.normalizer == self._origin[6], 'weighted immutable law snapshot changed')

    def select_pair(self, private_ticket):
        self._check()
        require(type(private_ticket) is int and 0 <= private_ticket < self.normalizer, 'weighted private ticket')
        self._meter.begin('private_queries', MAX_PRIVATE_QUERIES)
        before = 0
        for own, cumulative in enumerate(self.cdf):
            if private_ticket < cumulative:
                break
            before = cumulative
        else:
            raise ValueError('weighted linear own CDF exhausted')
        # Repeated prefixes retain zero-compatible original rows, never select
        # them, and never reconstruct an original weight from a CDF difference.
        require(self.compatible_masses[own] > 0, 'weighted zero-compatible row selected')
        opposite_ticket = (private_ticket - before) // self.weights[0][own]
        own_hand = self.ranges[0][own][0]
        own_cards = frozenset(own_hand)
        for other, (opposite_hand, _raw_bits) in enumerate(self.ranges[1]):
            if own_cards.isdisjoint(opposite_hand):
                weight = self.weights[1][other]
                if opposite_ticket < weight:
                    break
                opposite_ticket -= weight
        else:
            raise ValueError('weighted linear opponent CDF exhausted')
        mass = self.weights[0][own] * self.weights[1][other]
        return Pair((own, other), (own_hand, opposite_hand), mass, Fraction(mass, self.normalizer))

    def decode(self, private_ticket, board_rank, *, with_sign=True):
        self._check()
        require(type(board_rank) is int and 0 <= board_rank < self._meter.plan['board_count'] and
                type(with_sign) is bool, 'weighted board rank or rank option')
        require(type(private_ticket) is int and 0 <= private_ticket < self.normalizer, 'weighted private ticket')
        self._meter.begin('world_queries', self._meter.plan['world_query_limit'])
        pair = self.select_pair(private_ticket)
        board = _board(self.deck, (*pair.holdings[0], *pair.holdings[1]), board_rank)
        sign = None
        if with_sign:
            ranks = tuple(independent_rank(tuple(card_name(c) for c in (*hand, *board))) for hand in pair.holdings)
            sign = (ranks[0] > ranks[1]) - (ranks[0] < ranks[1])
        return World(private_ticket, board_rank, pair.holding_indices, pair.holdings, board, pair.integer_mass,
                     Fraction(pair.integer_mass, self.normalizer * self._meter.plan['board_count']), sign)

    def pair_product_sum(self):
        """A separately prepaid literal product census, never a pair table."""
        self._check(); self._meter.begin('audit_calls', 1)
        total = 0
        for i, (own, _raw) in enumerate(self.ranges[0]):
            own_cards = frozenset(own)
            for j, (opposite, _bits) in enumerate(self.ranges[1]):
                self._meter.pair_visits += 1
                if own_cards.isdisjoint(opposite):
                    total += self.weights[0][i] * self.weights[1][j]
        require(total.bit_length() <= 150, 'weighted literal product census width')
        return total

    def prefix_probability(self, prefix, *, actor=None, holding=None):
        self._check()
        require(type(prefix) is tuple and len(prefix) in (0, 3, 4, 5) and
                all(type(card) is int for card in prefix) and len(set(prefix)) == len(prefix) and
                set(prefix) <= set(self.deck) and (len(prefix) < 3 or tuple(sorted(prefix[:3])) == prefix[:3]),
                'weighted visible prefix')
        require((actor is None and holding is None) or
                (type(actor) is int and actor in (0, 1) and type(holding) is int and
                 0 <= holding < len(self.ranges[actor])), 'weighted prefix original holding')
        self._meter.begin('prefix_queries', self._meter.plan['prefix_query_limit'])
        blocked = frozenset(prefix); total = 0
        for i, (own, _raw) in enumerate(self.ranges[0]):
            own_cards = frozenset(own)
            for j, (opposite, _bits) in enumerate(self.ranges[1]):
                self._meter.pair_visits += 1
                if ((actor is None or (i, j)[actor] == holding) and own_cards.isdisjoint(opposite) and
                        own_cards.isdisjoint(blocked) and blocked.isdisjoint(opposite)):
                    total += self.weights[0][i] * self.weights[1][j]
        n = len(self.deck); k = len(prefix)
        divisor = 1 if not k else comb(n - 4, 3) * (n - 7 if k >= 4 else 1) * (n - 8 if k == 5 else 1)
        return Fraction(total, self.normalizer * divisor)

    def receipt(self):
        return {**self._meter.budget.receipt(), 'forecast': dict(self._meter.plan),
                'decoded_rows': self._meter.decoded_rows, 'literal_pair_visits': self._meter.pair_visits,
                'pair_product_audits': self._meter.audit_calls, 'private_queries': self._meter.private_queries,
                'world_queries': self._meter.world_queries, 'prefix_queries': self._meter.prefix_queries,
                'retained_pair_table': False, 'rng_calls': 0, 'native_calls': 0,
                'scope': 'Exact weighted chance-law reference only; no full52 native/solver/training admission or quality claim.'}


def build_law(deck, ranges, limits=None):
    require(type(deck) is tuple and all(type(card) is int for card in deck) and
            (deck == tuple(PROOF9) or deck == tuple(range(52))),
            'weighted deck must be exact PROOF9 or full52')
    require(type(ranges) is tuple and len(ranges) == 2 and all(type(side) is tuple and 1 <= len(side) <= MAX_HANDS
                                                           for side in ranges), 'weighted ordered range shape')
    plan = forecast(len(deck), tuple(map(len, ranges)))
    meter = _Meter(plan, limits)  # Entire request admitted before decoding or pair scans.
    for side in ranges:
        seen = set()
        for row in side:
            require(type(row) is tuple and len(row) == 2 and type(row[0]) is tuple and len(row[0]) == 2 and
                    all(type(card) is int for card in row[0]) and 0 <= row[0][0] < row[0][1] < 52 and
                    set(row[0]) <= set(deck), 'weighted canonical declared holding')
            require(row[0] not in seen, 'weighted duplicate physical holding')
            seen.add(row[0])
            require(type(row[1]) is int and 0 <= row[1] <= U64_MAX, 'weighted binary64 input bits')
    normalized = []; normalization = []
    for side in ranges:
        exact = []
        for _hand, raw_bits in side:
            meter.decoded_rows += 1
            number = struct.unpack('>d', raw_bits.to_bytes(8, 'big'))[0]
            require(isfinite(number) and number > 0, 'weighted positive finite binary64 required')
            value = Fraction.from_float(number)
            require(value.numerator.bit_length() <= 1024 and value.denominator.bit_length() <= 1075,
                    'weighted binary64 exact rational bounds')
            exact.append(value)
        denominator = lcm(*(value.denominator for value in exact))
        require(denominator.bit_length() <= 1075, 'weighted dyadic denominator LCM')
        aligned = []
        common = 0
        for value in exact:
            integer = value.numerator * (denominator // value.denominator)
            require(integer > 0 and integer.bit_length() <= 2150, 'weighted aligned rational width')
            aligned.append(integer); common = gcd(common, integer)
        values = tuple(integer // common for integer in aligned)
        require(all(0 < value <= U64_MAX for value in values), 'weighted normalized prior exceeds64bits')
        normalized.append(values); normalization.append(Normalization(denominator, common, Fraction(common, denominator)))
    weights = tuple(normalized)
    compatibles = []; row_masses = []; total = 0
    # Literal compatibility is the independent authority, not candidate card
    # buckets, masks, pair codes, UInt128 normalization or binary CDF search.
    for i, (own, _raw) in enumerate(ranges[0]):
        compatible = 0; own_cards = frozenset(own)
        for j, (opposite, _bits) in enumerate(ranges[1]):
            meter.pair_visits += 1
            if own_cards.isdisjoint(opposite):
                compatible += weights[1][j]
        require(compatible.bit_length() <= 75, 'weighted compatible mass width')
        product = weights[0][i] * compatible
        require(product.bit_length() <= 139, 'weighted own row mass width')
        compatibles.append(compatible); row_masses.append(product); total += product
        require(total.bit_length() <= 150, 'weighted total normalizer pre-check width')
    require(0 < total <= U64_MAX, 'weighted normalizer zero or exceeds64bits')
    cdf = []; cumulative = 0
    for mass in row_masses:
        cumulative += mass; cdf.append(cumulative)
    compatible_tuple, cdf_tuple, normalization_tuple = tuple(compatibles), tuple(cdf), tuple(normalization)
    origin = (deck, ranges, weights, compatible_tuple, cdf_tuple, normalization_tuple, total)
    return Law(deck, ranges, weights, compatible_tuple, cdf_tuple, total, normalization_tuple, meter, origin)
