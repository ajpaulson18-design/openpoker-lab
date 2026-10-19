"""Bounded prepared preflop count pooling under joint global suit bijections.

No board generation is available here. Ordinary four-pair preparation retains
its original limits. A pool copies only covered physical pair counts; callers
remain responsible for authenticating the supplied source tables.
"""
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import re

from .cards import DECK, SUITS, expand_range
from .preflop_full_board_equity import BOARDS_PER_PAIR, FullBoardEquities, _as_positive_float
from .preflop_suit_equity import _canonical_pair_key, _permutation_between, _mapped_hand

MAX_SOURCES = 32
MAX_CANDIDATES = 4096
MAX_PAIRS = 128
MAX_HANDS = 128
MAX_RANGE_CHARS = 32768
_SIGNS = (-1, 0, 1)


def _ranges(sb_range, bb_range):
    expressions = (sb_range, bb_range)
    if any(type(value) is not str or len(value) > MAX_RANGE_CHARS for value in expressions):
        raise ValueError('Covered ranges must be bounded range expressions')
    expanded = tuple(expand_range(value) for value in expressions)
    hands = tuple(tuple(row) for row in expanded)
    if any(len(row) > MAX_HANDS for row in hands):
        raise ValueError('Covered private-hand limit exceeded (128 per player)')
    if len(hands[0]) * len(hands[1]) > MAX_CANDIDATES:
        raise ValueError('Covered private candidate limit exceeded (4096)')
    raw = []
    for i, a in enumerate(hands[0]):
        for j, b in enumerate(hands[1]):
            if set(a).isdisjoint(b):
                if len(raw) >= MAX_PAIRS:
                    raise ValueError('Covered compatible-pair limit exceeded (128)')
                weight = Fraction.from_float(expanded[0][a]) * Fraction.from_float(expanded[1][b])
                raw.append((i, j, weight))
    if not raw:
        raise ValueError('Covered ranges have no compatible private pairs')
    total = sum((w for _, _, w in raw), Fraction())
    pairs = tuple((i, j, w / total) for i, j, w in raw)
    for _, _, prior in pairs:
        _as_positive_float(prior, 'covered pair probability')
    return hands, pairs


def _source_identity(table):
    data = {'hands': table.hands,
            'pairs': [(i, j, counts) for (i, j, _), counts in zip(table.pairs, table.counts)]}
    encoded = json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CoveredPreflopEquities:
    """Immutable prepared data; structural validity does not prove physical counts."""
    hands: tuple
    pairs: tuple
    counts: tuple
    worlds: tuple
    # One immutable (source digest, source SB, source BB, full suit permutation)
    # row per target pair, where hands are two-card tuples and permutation is
    # ordered by the ordinary cdhs suit alphabet.
    coverage: tuple
    source_count: int

    @property
    def budget(self):
        return {'budget_version': 'preflop-covered-equities-v1',
                'candidate_pairs': len(self.hands[0]) * len(self.hands[1]),
                'compatible_pairs': len(self.pairs), 'boards_per_pair': BOARDS_PER_PAIR,
                'physical_worlds_upper_bound': len(self.pairs) * BOARDS_PER_PAIR,
                'board_evaluations_upper_bound': 0, 'rank_calls_upper_bound': 0,
                'categorical_rows_upper_bound': 3 * len(self.pairs),
                'source_tables': self.source_count,
                'limits': {'candidate_pairs': MAX_CANDIDATES, 'compatible_pairs': MAX_PAIRS,
                           'hands_per_player': MAX_HANDS, 'source_tables': MAX_SOURCES},
                'scope': 'Covered prepared counts only; no current enumeration or ranking. '
                         'Source identities and structural checks do not authenticate counts.'}

    def validate(self):
        if (type(self.hands) is not tuple or len(self.hands) != 2
                or any(type(row) is not tuple or not 1 <= len(row) <= MAX_HANDS for row in self.hands)):
            raise ValueError('Covered hand tables must be bounded immutable tuples')
        if len(self.hands[0]) * len(self.hands[1]) > MAX_CANDIDATES:
            raise ValueError('Covered private candidate limit exceeded (4096)')
        for row in self.hands:
            if (any(type(hand) is not tuple or len(hand) != 2 or hand != tuple(sorted(hand))
                    or hand[0] == hand[1] or any(card not in DECK for card in hand) for hand in row)
                    or len(set(row)) != len(row)):
                raise ValueError('Covered hand table has invalid or duplicate cards')
        if (type(self.pairs) is not tuple or not 1 <= len(self.pairs) <= MAX_PAIRS
                or type(self.counts) is not tuple or len(self.counts) != len(self.pairs)
                or type(self.worlds) is not tuple or len(self.worlds) > 3 * len(self.pairs)
                or type(self.coverage) is not tuple or len(self.coverage) != len(self.pairs)
                or type(self.source_count) is not int or not 1 <= self.source_count <= MAX_SOURCES):
            raise ValueError('Covered pair/count/provenance dimensions exceed their bounds')
        keys, priors, expected_worlds = [], [], []
        for pair, counts, proof in zip(self.pairs, self.counts, self.coverage):
            if type(pair) is not tuple or len(pair) != 3:
                raise ValueError('Covered private pair must have indices and a Fraction prior')
            i, j, prior = pair
            if (type(i) is not int or type(j) is not int
                    or not 0 <= i < len(self.hands[0]) or not 0 <= j < len(self.hands[1])
                    or not set(self.hands[0][i]).isdisjoint(self.hands[1][j])
                    or type(prior) is not Fraction or prior <= 0):
                raise ValueError('Invalid covered private pair')
            _as_positive_float(prior, 'covered pair probability')
            keys.append((i, j)); priors.append(prior)
            if (type(counts) is not tuple or len(counts) != 3
                    or any(type(n) is not int or n < 0 for n in counts)
                    or sum(counts) != BOARDS_PER_PAIR):
                raise ValueError('Covered counts must be complete integer W/T/L totals')
            if type(proof) is not tuple or len(proof) != 4:
                raise ValueError('Invalid covered pair provenance')
            digest, source_sb, source_bb, permutation = proof
            if (type(digest) is not str or re.fullmatch('[0-9a-f]{64}', digest) is None
                    or type(permutation) is not tuple or len(permutation) != 4
                    or any(type(suit) is not str for suit in permutation)
                    or set(permutation) != set(SUITS)):
                raise ValueError('Covered source identity or suit permutation is invalid')
            for hand in (source_sb, source_bb):
                if (type(hand) is not tuple or len(hand) != 2 or hand != tuple(sorted(hand))
                        or hand[0] == hand[1] or any(card not in DECK for card in hand)):
                    raise ValueError('Invalid covered source hand')
            mapping = dict(zip(SUITS, permutation))
            if (not set(source_sb).isdisjoint(source_bb)
                    or _mapped_hand(source_sb, mapping) != self.hands[0][i]
                    or _mapped_hand(source_bb, mapping) != self.hands[1][j]):
                raise ValueError('One joint suit map must preserve both ordered endpoints')
            wins, ties, losses = counts
            for sign, n in zip(_SIGNS, (losses, ties, wins)):
                if n:
                    expected_worlds.append((i, j, _as_positive_float(
                        prior * Fraction(n, BOARDS_PER_PAIR), 'covered category mass'), sign))
        expected_keys = [(i, j) for i, a in enumerate(self.hands[0])
                         for j, b in enumerate(self.hands[1]) if set(a).isdisjoint(b)]
        if keys != expected_keys or sum(priors, Fraction()) != 1:
            raise ValueError('Covered pairs must include every compatible pair once with normalized priors')
        if self.worlds != tuple(expected_worlds) or any(
                type(row) is not tuple or len(row) != 4
                or type(row[0]) is not int or type(row[1]) is not int
                or type(row[2]) is not float or type(row[3]) is not int for row in self.worlds):
            raise ValueError('Covered category rows differ from exact priors and counts')

    def provenance(self):
        self.validate()
        return [{'target_sb_hand': ''.join(self.hands[0][i]),
                 'target_bb_hand': ''.join(self.hands[1][j]),
                 'source_identity_sha256': proof[0], 'source_sb_hand': ''.join(proof[1]),
                 'source_bb_hand': ''.join(proof[2]),
                 'suit_permutation': dict(zip(SUITS, proof[3]))}
                for (i, j, _), proof in zip(self.pairs, self.coverage)]


def pool_preflop_equities_by_suit(sources, sb_range, bb_range):
    """Pool bounded ordinary source tables, rejecting every uncovered target pair.

    A single global suit bijection maps both players and every future board.
    We retain private pairs separately; range weights need not be suit symmetric.
    Target pair/hand admission finishes before source orbit work or output rows.
    """
    hands, pairs = _ranges(sb_range, bb_range)
    if type(sources) not in (tuple, list) or not 1 <= len(sources) <= MAX_SOURCES:
        raise ValueError('Covered pooling requires 1 to 32 ordinary source tables')
    orbits = {}
    for table in sources:
        if type(table) is not FullBoardEquities:
            raise TypeError('Covered sources must be ordinary FullBoardEquities tables')
        table.validate()
        digest = _source_identity(table)
        for (i, j, _), counts in zip(table.pairs, table.counts):
            pair = (table.hands[0][i], table.hands[1][j])
            key = _canonical_pair_key(pair)
            if key in orbits and orbits[key][1] != counts:
                raise ValueError('Pooled source counts conflict within a joint suit orbit')
            if key not in orbits:
                orbits[key] = (pair, counts, digest)
    resolved = []
    for i, j, _ in pairs:
        target = (hands[0][i], hands[1][j])
        source = orbits.get(_canonical_pair_key(target))
        if source is None:
            raise ValueError('Target compatible pair is not covered by the pooled source suit orbits')
        pair, counts, digest = source
        mapping = _permutation_between(pair, target)
        resolved.append((counts, (digest, pair[0], pair[1], tuple(suit for _, suit in mapping))))
    # All target orbits resolve before allocating any category rows.
    worlds = []
    for (i, j, prior), (counts, _) in zip(pairs, resolved):
        wins, ties, losses = counts
        for sign, n in zip(_SIGNS, (losses, ties, wins)):
            if n:
                worlds.append((i, j, _as_positive_float(prior * Fraction(n, BOARDS_PER_PAIR),
                                                       'covered category mass'), sign))
    result = CoveredPreflopEquities(hands, pairs, tuple(x[0] for x in resolved), tuple(worlds),
                                   tuple(x[1] for x in resolved), len(sources))
    result.validate()
    return result
