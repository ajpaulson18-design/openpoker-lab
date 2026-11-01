"""Independent selected-board exact payoff operator; no world or pair table.

The prior is globally conditioned on the supplied ordered full boards. Vectors
include the responder's prior once. Each future selected board occurs once.
"""
from types import MappingProxyType
from fractions import Fraction
from itertools import islice, groupby
from math import isfinite

from scripts.preflop_validation import independent_rank
from scripts.matrix_free_certificate_budget import Budget

_CARDS = frozenset(r + s for r in '23456789TJQKA' for s in 'cdhs')
_ZERO = Fraction(0)
RANK_CACHE_ENTRIES = 12
# At most 21 five-card candidates, each with <=5 ranks/counts/groups and
# bounded tuple/set/list temporaries. This is a conservative logical-reference
# construction envelope, separate from retained B-by-H rank cache entries.
RANK_TEMP_ENTRIES = 4096

def _card_key(c):
    return ('23456789TJQKA'.index(c[0]), 'cdhs'.index(c[1]))

def _flop_canonical(value):
    return tuple(sorted(value[:3], key=_card_key)) + value[3:]

def _cards(value, n, label):
    if type(value) is not tuple or len(value) != n or any(type(c) is not str or c not in _CARDS for c in value) or len(set(value)) != n:
        raise ValueError(f'{label}: invalid cards')
    return value

class _Bucket:
    def __init__(self, budget):
        self.b = budget
        # At most 32 card-key entries and 16 same-hand entries: two
        # logical references per entry, plus dictionary/total headers.
        budget.entries(128, 'card bucket')
        self.total = _ZERO
        self.cards = {}
        self.same = {}

    def put(self, hand, amount):
        b = self.b
        b.charge('bucket_insert')
        self.total = b.add(self.total, amount, 'bucket total')
        for card in hand:
            self.cards[card] = b.add(self.cards.get(card, _ZERO), amount, 'bucket card')
        self.same[hand] = amount

    def compatible(self, hand):
        b = self.b
        b.charge('bucket_lookup')
        out = b.sub(self.total, self.cards.get(hand[0], _ZERO), 'blocker')
        out = b.sub(out, self.cards.get(hand[1], _ZERO), 'blocker')
        return b.add(out, self.same.get(hand, _ZERO), 'same holding addback')

class PayoffModel:
    """Two ranges (<=16 hands each), at most 64 selected full boards."""
    def __init__(self, ranges, boards, budget):
        if not isinstance(budget, Budget):
            raise TypeError('expected Budget')
        self.budget = budget
        if type(ranges) is not tuple or len(ranges) != 2:
            raise ValueError('two range mappings required')
        # Validate all bounded input before allocating rational/vector state.
        if type(boards) is not tuple or not 1 <= len(boards) <= 64:
            raise ValueError('one to 64 selected boards required')
        budget.charge('input_validation', 128 + 32 * len(boards))
        budget.entries(6 * len(boards) + 64, 'bounded input validation')
        bs = tuple(_flop_canonical(_cards(board, 5, 'board')) for board in boards)
        if len({(frozenset(board[:3]), board[3], board[4]) for board in bs}) != len(bs):
            raise ValueError('duplicate selected board')
        snapshots = []
        for side in ranges:
            if type(side) not in (dict, MappingProxyType) or not 1 <= len(side) <= 16:
                raise ValueError('range size must be between 1 and 16')
            n = len(side)
            budget.charge('input_validation', 32 * n)
            budget.entries(4 * n, 'bounded range validation')
            entries = tuple(islice(side.items(), n + 1))
            if len(entries) != n:
                raise ValueError('inconsistent range length')
            checked, seen = [], set()
            for hand, weight in entries:
                h = tuple(sorted(_cards(hand, 2, 'holding')))
                if h in seen:
                    raise ValueError('duplicate physical holding')
                seen.add(h)
                if type(weight) is not float or not isfinite(weight) or weight <= 0:
                    raise ValueError('range weights must be positive finite binary64 floats')
                checked.append((h, weight))
            snapshots.append(tuple(checked))
        hands = [tuple(hand for hand, _ in side) for side in snapshots]
        weights = [tuple(budget.input(weight, 'weight') for _, weight in side)
                   for side in snapshots]
        self.hands, self.weights, self.boards = tuple(hands), tuple(weights), bs
        self._indexes = tuple({h:i for i,h in enumerate(side)} for side in self.hands)
        budget.entries(sum(map(len, self.hands)), 'holding indexes')
        budget.charge('normalizer_scan', len(self.boards) * (2 + sum(map(len, self.hands))))
        z = _ZERO
        for board in self.boards:
            blocked = set(board)
            bucket = _Bucket(budget)
            for hand, weight in zip(self.hands[1], self.weights[1]):
                if not blocked.intersection(hand):
                    bucket.put(hand, weight)
            for hand, weight in zip(self.hands[0], self.weights[0]):
                if not blocked.intersection(hand):
                    z = budget.add(z, budget.mul(weight, bucket.compatible(hand), 'prior product'), 'normalizer')
        if z.numerator <= 0:
            raise ValueError('selected boards have no compatible physical deal')
        self.normalizerZ = z
        self._support_queries = self._terminal_calls = self._rank_calls = 0
        budget.entries(16, 'rank cache header')
        self._rank_cache = {}
        self._physical_metadata()

    def _physical_metadata(self):
        """Count with board-mask classes and blocker counts; retain no deals."""
        b = self.budget
        h0, h1 = self.hands
        b.charge('physical_census', 128 + 64 * len(self.boards) * (len(h0) + len(h1))
                 + 64 * len(h0) * len(h1))
        b.entries(256 + 8 * (len(h0) + len(h1)) + len(self.boards), 'physical census scratch')
        masks = []
        for side in self.hands:
            masks.append(tuple(sum(1 << k for k, board in enumerate(self.boards)
                                   if not set(hand).intersection(board)) for hand in side))
        groups = {}
        for hand, mask in zip(h1, masks[1]):
            if not mask:
                continue
            total, cards, members = groups.setdefault(mask, [0, {}, set()])
            groups[mask][0] = total + 1
            for card in hand:
                cards[card] = cards.get(card, 0) + 1
            members.add(hand)
        pairs = 0
        for hand, mask in zip(h0, masks[0]):
            for other_mask, (total, cards, members) in groups.items():
                if mask & other_mask:
                    pairs += total - cards.get(hand[0], 0) - cards.get(hand[1], 0) + (hand in members)
        worlds = 0
        reachable = []
        for k, board in enumerate(self.boards):
            cards = {}; members = set(); total = 0
            for hand, mask in zip(h1, masks[1]):
                if mask & (1 << k):
                    total += 1; members.add(hand)
                    for card in hand: cards[card] = cards.get(card, 0) + 1
            board_count = 0
            for hand, mask in zip(h0, masks[0]):
                if mask & (1 << k):
                    board_count += total - cards.get(hand[0], 0) - cards.get(hand[1], 0) + (hand in members)
            if board_count:
                reachable.append(board)
                worlds += board_count
        self.compatible_pairs = pairs
        self.physical_worlds = worlds
        self.reachable_boards = tuple(reachable)

    def receipt(self):
        return {'hands': tuple(map(len, self.hands)), 'selected_boards': len(self.boards),
                'reachable_boards': len(self.reachable_boards), 'physical_worlds': self.physical_worlds,
                'compatible_pairs': self.compatible_pairs, 'rank_calls': self._rank_calls,
                'support_queries': self._support_queries, 'terminal_calls': self._terminal_calls,
                'rank_cache_entries': len(self._rank_cache),
                'stored_pairs': 0, 'stored_worlds': 0, 'budget': self.budget.receipt()}

    def _selected(self, prefix):
        if type(prefix) is not tuple or len(prefix) not in (0, 3, 4, 5):
            raise ValueError('prefix must be a visible ordered board prefix')
        _cards(prefix, len(prefix), 'prefix')
        if prefix:
            prefix = _flop_canonical(prefix)
        self.budget.charge('board_prefix_scan', len(self.boards))
        self.budget.entries(len(self.boards), 'selected board references')
        return tuple(board for board in self.boards if board[:len(prefix)] == prefix)

    def prefix_support(self, prefix):
        boards = self._selected(prefix)
        self._support_queries += 1
        b = self.budget
        b.charge('support_board_scan', len(boards) * (8 + 4 * sum(map(len, self.hands))))
        b.entries(sum(map(len, self.hands)), 'prefix support')
        support = [[False] * len(side) for side in self.hands]
        for board in boards:
            blocked = set(board)
            for player in (0, 1):
                opp = 1 - player
                bucket = _Bucket(b)
                for hand, weight in zip(self.hands[opp], self.weights[opp]):
                    if not blocked.intersection(hand):
                        bucket.put(hand, weight)
                for i, hand in enumerate(self.hands[player]):
                    if not blocked.intersection(hand) and bucket.compatible(hand).numerator > 0:
                        support[player][i] = True
        return tuple(tuple(side) for side in support)

    def terminal(self, player, opponent_reach, prefix, matched, winner=None):
        if type(player) is not int or player not in (0, 1):
            raise ValueError('player must be 0 or 1')
        if winner is not None and (type(winner) is not int or winner not in (0, 1)):
            raise ValueError('winner must be global seat 0, 1, or None')
        opp = 1 - player; b = self.budget
        if not hasattr(opponent_reach, '__len__') or len(opponent_reach) != len(self.hands[opp]):
            raise ValueError('opponent reach size mismatch')
        b.entries(len(self.hands[opp]) * 2 + len(self.hands[player]), 'terminal vectors')
        reach = tuple(b.input(x, 'opponent reach') for x in islice(iter(opponent_reach), len(self.hands[opp]) + 1))
        if len(reach) != len(self.hands[opp]) or any(x.numerator < 0 or x.numerator > x.denominator for x in reach):
            raise ValueError('invalid opponent reach')
        amount = b.input(matched, 'matched contribution')
        if amount.numerator < 0:
            raise ValueError('negative matched contribution')
        boards = self._selected(prefix)
        self._terminal_calls += 1
        b.charge('terminal_board_scan', len(boards) * (8 + 4 * sum(map(len, self.hands))))
        weighted = tuple(b.mul(w, r, 'weighted reach') for w,r in zip(self.weights[opp], reach))
        result = [_ZERO] * len(self.hands[player])
        for board in boards:
            # Fixed five-card set, filtered weighted rows, sorted rank rows and
            # their tuple/list references. Bucket and rank-cache reservations
            # remain separate. This is a logical construction envelope.
            b.entries(64 + 16 * sum(map(len, self.hands)), 'terminal board temporaries')
            blocked = set(board)
            valid_opp = [(h, w) for h,w in zip(self.hands[opp], weighted) if not blocked.intersection(h)]
            if winner is not None:
                bucket = _Bucket(b)
                for hand, weight in valid_opp:
                    bucket.put(hand, weight)
                for i, hand in enumerate(self.hands[player]):
                    if not blocked.intersection(hand):
                        mass = bucket.compatible(hand)
                        if winner != player:
                            mass = b.neg(mass, 'fold sign')
                        result[i] = b.add(result[i], mass, 'fold sum')
            else:
                b.entries(2 * (len(valid_opp) + len(self.hands[player])), 'rank sweep')
                # Two sorts of <=16 keys, each rank key <=6 small integers
                # plus a bounded holding/index tie key. Conservative logical
                # scan/comparison allowance; not CPU instructions.
                b.charge('rank_sort', 128 * (len(valid_opp) + len(self.hands[player])))
                def rank(hand):
                    b.charge('rank_cache_lookup', 64)
                    key = (board, hand)
                    cached = self._rank_cache.get(key)
                    if cached is not None:
                        return cached
                    # Admission precedes independent ranking and cache insertion.
                    b.entries(RANK_CACHE_ENTRIES + RANK_TEMP_ENTRIES,
                              'rank cache and independent best-five temporaries')
                    b.charge('independent_best_five', 4096)
                    self._rank_calls += 1
                    value = independent_rank(hand + board)
                    self._rank_cache[key] = value
                    return value
                opponents = sorted((rank(h), h, w) for h,w in valid_opp)
                own = sorted((rank(h), i, h) for i,h in enumerate(self.hands[player]) if not blocked.intersection(h))
                all_bucket, lower = _Bucket(b), _Bucket(b)
                for _,h,w in opponents: all_bucket.put(h,w)
                pos = 0
                for rank, own_group in groupby(own, key=lambda item: item[0]):
                    while pos < len(opponents) and opponents[pos][0] < rank:
                        _,h,w = opponents[pos]; lower.put(h,w); pos += 1
                    end = pos
                    equal = _Bucket(b)
                    while end < len(opponents) and opponents[end][0] == rank:
                        _,h,w = opponents[end]; equal.put(h,w); end += 1
                    for _,i,h in own_group:
                        low = lower.compatible(h)
                        high = b.sub(b.sub(all_bucket.compatible(h), low, 'higher'), equal.compatible(h), 'higher')
                        result[i] = b.add(result[i], b.sub(low, high, 'showdown sign'), 'showdown sum')
        return tuple(b.div(b.mul(b.mul(v, own_weight, 'own prior'), amount, 'terminal amount'), self.normalizerZ, 'global normalization') for v,own_weight in zip(result, self.weights[player]))
