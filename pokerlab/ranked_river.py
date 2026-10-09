"""Rank-sweep terminal payoffs for fixed-board, heads-up river ranges.

This module provides a standalone payoff evaluator for the public-tree river
case. It uses rank ordering plus card-blocker inclusion-exclusion to avoid
examining every private-hand pair at each terminal.
"""
import math
from numbers import Real

from .cards import DECK, cards, rank_hand
from .river_tree import _Terminal

_CARD_ID = {card: index for index, card in enumerate(DECK)}


def _normalize_weights(values, label):
    normalized_input = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{label} weights must be finite positive real numbers.")
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{label} weights must be finite positive real numbers.") from exc
        if not math.isfinite(number) or number <= 0:
            raise ValueError(f"{label} weights must be finite positive real numbers.")
        normalized_input.append(number)
    if not normalized_input:
        raise ValueError(f"{label} must contain at least one holding.")
    maximum = max(normalized_input)
    scaled = [weight / maximum for weight in normalized_input]
    total = math.fsum(scaled)
    result = tuple(weight / total for weight in scaled)
    if any(weight == 0 for weight in result):
        raise ValueError(f"{label} weights have too much dynamic range to normalize safely.")
    return result


def _validate_hands(raw_hands, board, label):
    if isinstance(raw_hands, (str, bytes)):
        raise TypeError(f"{label} hands must be a sequence of two-card holdings.")
    result = []
    seen = set()
    for holding in raw_hands:
        try:
            hand = cards(holding, 2)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} holdings must contain two valid cards.") from exc
        if tuple(sorted(hand)) != hand:
            raise ValueError(f"{label} holdings must use canonical sorted card tuples.")
        if set(hand) & set(board):
            raise ValueError(f"{label} holdings cannot overlap the board.")
        if hand in seen:
            raise ValueError(f"{label} holdings must be unique.")
        seen.add(hand)
        result.append(hand)
    if not result:
        raise ValueError(f"{label} must contain at least one holding.")
    return tuple(result)


def _rank_groups(hands, board):
    ranked = sorted((rank_hand(board + hand), index)
                    for index, hand in enumerate(hands))
    ranks = []
    groups = []
    for rank, index in ranked:
        if not ranks or ranks[-1] != rank:
            ranks.append(rank)
            groups.append([])
        groups[-1].append(index)
    return tuple(ranks), tuple(tuple(group) for group in groups)


def _accumulate(accumulator, value):
    """Add a nonnegative float with Neumaier compensation, in place."""
    total, correction = accumulator
    updated = total + value
    if abs(total) >= abs(value):
        correction += (total - updated) + value
    else:
        correction += (value - updated) + total
    accumulator[0] = updated
    accumulator[1] = correction


def _acc_value(accumulator):
    return (0.0, 0.0) if accumulator is None else (accumulator[0], accumulator[1])


def _rank_card_mass(group_indexes, weighted_reach, card_ids):
    terms = {}
    for index in group_indexes:
        mass = weighted_reach[index]
        first, second = card_ids[index]
        terms.setdefault(first, []).append(mass)
        terms.setdefault(second, []).append(mass)
    return {card_id: math.fsum(values) for card_id, values in terms.items()}


class RankedRiverPayoffs:
    """Evaluate river terminal values in chip units for fixed weighted ranges.

    ``hands`` and ``weights`` are pairs ``(oop, ip)`` of parallel sequences.
    Each holding is a canonical, sorted two-card tuple. Inputs require a
    complete five-card board, positive finite range weights, and a finite
    positive starting pot. The joint range mass is normalized over compatible
    private-hand pairs once during construction.
    """

    def __init__(self, board, hands, weights, *, pot):
        self.board = cards(board, 5)
        if isinstance(pot, bool) or not isinstance(pot, Real):
            raise ValueError("Pot must be a finite positive real number.")
        try:
            self.pot = float(pot)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Pot must be a finite positive real number.") from exc
        if not math.isfinite(self.pot) or self.pot <= 0:
            raise ValueError("Pot must be a finite positive real number.")
        if not isinstance(hands, (tuple, list)) or len(hands) != 2:
            raise ValueError("hands must contain OOP and IP holding sequences.")
        if not isinstance(weights, (tuple, list)) or len(weights) != 2:
            raise ValueError("weights must contain OOP and IP weight sequences.")
        self.hands = (_validate_hands(hands[0], self.board, "OOP"),
                      _validate_hands(hands[1], self.board, "IP"))
        self.weights = (_normalize_weights(weights[0], "OOP"),
                        _normalize_weights(weights[1], "IP"))
        if tuple(map(len, self.hands)) != tuple(map(len, self.weights)):
            raise ValueError("Each weight sequence must match its holding sequence.")
        self.card_ids = tuple(
            tuple(tuple(_CARD_ID[card] for card in hand) for hand in side)
            for side in self.hands
        )
        self.holding_index = tuple({hand: index for index, hand in enumerate(side)}
                                   for side in self.hands)
        self._rank_by_index = []
        self._own_rank_groups = []
        for side in self.hands:
            ranks, groups = _rank_groups(side, self.board)
            self._own_rank_groups.append((ranks, groups))
            by_index = [None] * len(side)
            for rank, indexes in zip(ranks, groups):
                for index in indexes:
                    by_index[index] = rank
            self._rank_by_index.append(tuple(by_index))
        self._rank_by_index = tuple(self._rank_by_index)
        self._own_rank_groups = tuple(self._own_rank_groups)
        self.rank_groups = self._own_rank_groups
        ip_card_terms = [[] for _ in DECK]
        for index, pair in enumerate(self.card_ids[1]):
            ip_card_terms[pair[0]].append(self.weights[1][index])
            ip_card_terms[pair[1]].append(self.weights[1][index])
        ip_card_mass = [math.fsum(terms) for terms in ip_card_terms]
        shared_holding_count = sum(hand in self.holding_index[1] for hand in self.hands[0])
        oop_card_count = [0] * len(DECK)
        ip_card_count = [0] * len(DECK)
        for pair in self.card_ids[0]:
            oop_card_count[pair[0]] += 1
            oop_card_count[pair[1]] += 1
        for pair in self.card_ids[1]:
            ip_card_count[pair[0]] += 1
            ip_card_count[pair[1]] += 1
        compatible_pair_count = (len(self.hands[0]) * len(self.hands[1]) -
                                 sum(a * b for a, b in zip(oop_card_count, ip_card_count)) +
                                 shared_holding_count)
        if compatible_pair_count <= 0:
            raise ValueError("Ranges contain no compatible positive-mass private-hand pair.")
        compatible_by_oop = []
        for index, hand in enumerate(self.hands[0]):
            same = self.holding_index[1].get(hand)
            compatible = math.fsum((
                1.0,
                -ip_card_mass[self.card_ids[0][index][0]],
                -ip_card_mass[self.card_ids[0][index][1]],
                0.0 if same is None else self.weights[1][same],
            ))
            tolerance = 1e-12
            if compatible < 0:
                if compatible >= -tolerance:
                    compatible = 0.0
                else:
                    raise ArithmeticError("Compatible range mass became materially negative.")
            compatible_by_oop.append(self.weights[0][index] * compatible)
        compatible_mass = math.fsum(compatible_by_oop)
        if compatible_mass <= 1e-12:
            compatible_mass = math.fsum(
                self.weights[0][i] * self.weights[1][j]
                for i, hand0 in enumerate(self.hands[0])
                for j, hand1 in enumerate(self.hands[1])
                if not (set(hand0) & set(hand1))
            )
        if not math.isfinite(compatible_mass) or compatible_mass <= 0:
            raise ValueError("Ranges contain no compatible positive-mass private-hand pair.")
        self.factor = 1.0 / compatible_mass
        if not math.isfinite(self.factor):
            raise ValueError("Compatible range mass is too small to normalize safely.")
        self.compatible_pair_count = compatible_pair_count

    @staticmethod
    def _reach(values, expected):
        try:
            if len(values) != expected:
                raise ValueError("opponent_reach must have one entry per opponent holding.")
        except TypeError as exc:
            raise TypeError("opponent_reach must be a sized sequence.") from exc
        result = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError("opponent_reach values must be finite and nonnegative.")
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("opponent_reach values must be finite and nonnegative.") from exc
            if not math.isfinite(number) or number < 0:
                raise ValueError("opponent_reach values must be finite and nonnegative.")
            result.append(number)
        return result

    def _terminal(self, node):
        if not isinstance(node, _Terminal) or node.kind not in ("fold", "showdown"):
            raise ValueError("Ranked river payoffs support only fold and showdown terminals.")
        if not isinstance(node.contributions, (tuple, list)) or len(node.contributions) != 2:
            raise ValueError("Terminal contributions must contain two values.")
        contributions = []
        for value in node.contributions:
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError("Terminal contributions must be finite nonnegative numbers.")
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Terminal contributions must be finite nonnegative numbers.") from exc
            if not math.isfinite(number) or number < 0:
                raise ValueError("Terminal contributions must be finite nonnegative numbers.")
            contributions.append(number)
        if node.kind == "fold" and (type(node.winner) is not int or node.winner not in (0, 1)):
            raise ValueError("A fold terminal must identify player 0 or 1 as winner.")
        return min(contributions), contributions

    def values(self, node, opponent_reach, player):
        """Return own-hand joint-weighted values against opponent reach mass.

        Reach is measured at the terminal public state but is not range-normalized.
        OOP values use positive utility for OOP; IP values use positive utility
        for IP. Runtime is linear in both range sizes plus card/rank group work.
        """
        if type(player) is not int or player not in (0, 1):
            raise ValueError("player must be 0 (OOP) or 1 (IP).")
        matched, _contributions = self._terminal(node)
        opponent = 1 - player
        reach = self._reach(opponent_reach, len(self.hands[opponent]))
        weighted_reach = [weight * probability for weight, probability
                          in zip(self.weights[opponent], reach)]
        scale = self.pot / 2.0 + matched
        if not math.isfinite(scale):
            raise ValueError("Terminal payoff scale must be finite.")
        own_hands = self.hands[player]
        own_weights = self.weights[player]
        opponent_hands = self.hands[opponent]
        opponent_cards = self.card_ids[opponent]
        if not any(weighted_reach):
            return [0.0] * len(own_hands)
        total_reach = math.fsum(weighted_reach)
        card_reach_terms = [[] for _ in DECK]
        for index, pair in enumerate(opponent_cards):
            card_reach_terms[pair[0]].append(weighted_reach[index])
            card_reach_terms[pair[1]].append(weighted_reach[index])
        card_reach = [math.fsum(terms) for terms in card_reach_terms]

        def compatible_mass(own_index):
            pair = self.card_ids[player][own_index]
            same = self.holding_index[opponent].get(own_hands[own_index])
            approximate = math.fsum((
                total_reach, -card_reach[pair[0]], -card_reach[pair[1]],
                0.0 if same is None else weighted_reach[same],
            ))
            if approximate <= 1e-12 * total_reach:
                # Rare cancellation path: direct physical filtering preserves
                # tiny valid residual mass and identifies truly empty support.
                return math.fsum(
                    weighted_reach[index]
                    for index, other in enumerate(opponent_hands)
                    if not (set(own_hands[own_index]) & set(other))
                )
            return approximate

        if node.kind == "fold":
            sign = 1.0 if node.winner == player else -1.0
            answer = []
            for own_index, _pair in enumerate(self.card_ids[player]):
                compatible = compatible_mass(own_index)
                value = own_weights[own_index] * self.factor * compatible * sign * scale
                if not math.isfinite(value):
                    raise ValueError("Ranked river payoff must be finite.")
                answer.append(value)
            return answer

        ranks, groups = self.rank_groups[opponent]
        group_mass = []
        group_cards = []
        for group_index, indexes in enumerate(groups):
            group_mass.append(math.fsum(weighted_reach[index] for index in indexes))
            group_cards.append(_rank_card_mass(indexes, weighted_reach, opponent_cards))

        own_ranks, own_groups = self._own_rank_groups[player]
        own_group_by_rank = dict(zip(own_ranks, own_groups))
        lower_snapshots = {}
        lower_total = [0.0, 0.0]
        lower_cards = {}
        opponent_group = 0
        for own_rank in own_ranks:
            while (opponent_group < len(ranks) and
                   ranks[opponent_group] < own_rank):
                _accumulate(lower_total, group_mass[opponent_group])
                for card_id, mass in group_cards[opponent_group].items():
                    _accumulate(lower_cards.setdefault(card_id, [0.0, 0.0]), mass)
                opponent_group += 1
            lower_snapshots[own_rank] = (
                tuple(lower_total),
                {card_id: tuple(lower_cards.get(card_id, (0.0, 0.0)))
                 for hand_index in own_group_by_rank[own_rank]
                 for card_id in self.card_ids[player][hand_index]},
            )

        higher_snapshots = {}
        higher_total = [0.0, 0.0]
        higher_cards = {}
        opponent_group = len(ranks) - 1
        for own_rank in reversed(own_ranks):
            while (opponent_group >= 0 and ranks[opponent_group] > own_rank):
                _accumulate(higher_total, group_mass[opponent_group])
                for card_id, mass in group_cards[opponent_group].items():
                    _accumulate(higher_cards.setdefault(card_id, [0.0, 0.0]), mass)
                opponent_group -= 1
            own_group = own_group_by_rank[own_rank]
            higher_snapshots[own_rank] = (
                tuple(higher_total),
                {card_id: tuple(higher_cards.get(card_id, (0.0, 0.0)))
                 for hand_index in own_group
                 for card_id in self.card_ids[player][hand_index]},
            )

        answer = [0.0] * len(own_hands)
        opponent_rank_by_index = self._rank_by_index[opponent]
        for own_rank, own_group in zip(own_ranks, own_groups):
            low_total, low_cards = lower_snapshots[own_rank]
            high_total, high_cards = higher_snapshots[own_rank]
            for own_index in own_group:
                pair = self.card_ids[player][own_index]
                terms = [low_total[0], low_total[1], -high_total[0], -high_total[1]]
                for card_id in pair:
                    low = low_cards.get(card_id, (0.0, 0.0))
                    high = high_cards.get(card_id, (0.0, 0.0))
                    terms.extend((-low[0], -low[1], high[0], high[1]))
                net_mass = math.fsum(terms)
                compatible = compatible_mass(own_index)
                non_tie_mass = math.fsum(abs(value) for value in
                                         (low_total[0], low_total[1],
                                          high_total[0], high_total[1]))
                if (non_tie_mass > 0 and
                        abs(net_mass) <= 1e-12 * max(compatible, 1e-300)):
                    own_hand = own_hands[own_index]
                    own_rank = self._rank_by_index[player][own_index]
                    net_mass = math.fsum(
                        weighted_reach[index] *
                        ((own_rank > opponent_rank_by_index[index]) -
                         (own_rank < opponent_rank_by_index[index]))
                        for index, other in enumerate(opponent_hands)
                        if not (set(own_hand) & set(other))
                    )
                value = own_weights[own_index] * self.factor * net_mass * scale
                if not math.isfinite(value):
                    raise ValueError("Ranked river payoff must be finite.")
                answer[own_index] = value
        return answer
