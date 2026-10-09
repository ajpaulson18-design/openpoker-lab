"""Prefix-aware matrix-free physical turn-range payoff infrastructure.

This is preparatory payoff infrastructure only; it is not a turn solver and
does not claim equivalence to a commercial or unrestricted Hold'em solver.
"""
import math
from numbers import Real
from types import MappingProxyType

from .cards import DECK, cards
from .ranked_river import RankedRiverPayoffs
from .river_tree import _Terminal


MAX_HAND_SLOTS = 120_000
MAX_FALLBACK_PAIR_CHECKS = 30_000_000
_CARD_ID = {card: index for index, card in enumerate(DECK)}


def _side_hands(values, board, label):
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{label} hands must be a sequence of canonical holdings.")
    result = []
    seen = set()
    for raw in values:
        try:
            hand = cards(raw, 2)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} holdings must contain two valid cards.") from exc
        if tuple(sorted(hand)) != hand:
            raise ValueError(f"{label} holdings must be canonical sorted card tuples.")
        if set(hand) & set(board):
            raise ValueError(f"{label} holdings cannot overlap the turn board.")
        if hand in seen:
            raise ValueError(f"{label} holdings must be unique.")
        seen.add(hand)
        result.append(hand)
    if not result:
        raise ValueError(f"{label} must contain at least one holding.")
    return tuple(result)


def _normalized_weights(values, expected, label):
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{label} weights must be a sequence of positive numbers.")
    try:
        raw = tuple(values)
    except TypeError as exc:
        raise TypeError(f"{label} weights must be a sequence of positive numbers.") from exc
    if len(raw) != expected:
        raise ValueError(f"{label} weights must match the holding sequence.")
    numbers = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{label} weights must be finite positive real numbers.")
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{label} weights must be finite positive real numbers.") from exc
        if not math.isfinite(number) or number <= 0:
            raise ValueError(f"{label} weights must be finite positive real numbers.")
        numbers.append(number)
    if not numbers:
        raise ValueError(f"{label} weights must not be empty.")
    maximum = max(numbers)
    scaled = [number / maximum for number in numbers]
    total = math.fsum(scaled)
    normalized = tuple(number / total for number in scaled)
    if any(number == 0 for number in normalized):
        raise ValueError(f"{label} weights have too much dynamic range to normalize safely.")
    return normalized


def _compatible_pair_count(hands0, hands1):
    counts0 = [0] * len(DECK)
    counts1 = [0] * len(DECK)
    for hand in hands0:
        counts0[_CARD_ID[hand[0]]] += 1
        counts0[_CARD_ID[hand[1]]] += 1
    for hand in hands1:
        counts1[_CARD_ID[hand[0]]] += 1
        counts1[_CARD_ID[hand[1]]] += 1
    shared = len(set(hands0).intersection(hands1))
    return len(hands0) * len(hands1) - sum(a * b for a, b in zip(counts0, counts1)) + shared


class TurnRangePayoffs:
    """Conditioned turn deals with matrix-free terminal payoff branches.

    Original range weights are normalized once per player, before river
    filtering. For each selected river, its physical branch mass is the product
    of filtered side masses times the branch kernel's compatible-hand fraction.
    """

    def __init__(self, board, hands, weights, *, pot, runouts=None,
                 fallback_pair_limit=MAX_FALLBACK_PAIR_CHECKS):
        self.board = cards(board, 4)
        if not isinstance(hands, (tuple, list)) or len(hands) != 2:
            raise ValueError("hands must contain OOP and IP holding sequences.")
        if not isinstance(weights, (tuple, list)) or len(weights) != 2:
            raise ValueError("weights must contain OOP and IP weight sequences.")
        self.hands = (_side_hands(hands[0], self.board, "OOP"),
                      _side_hands(hands[1], self.board, "IP"))
        self.weights = (_normalized_weights(weights[0], len(self.hands[0]), "OOP"),
                        _normalized_weights(weights[1], len(self.hands[1]), "IP"))
        if type(fallback_pair_limit) is not int or fallback_pair_limit < 0:
            raise ValueError("Fallback pair limit must be a nonnegative integer.")
        self.fallback_pair_limit = fallback_pair_limit
        self.fallback_pair_checks = 0
        try:
            if isinstance(pot, bool) or not isinstance(pot, Real):
                raise ValueError("Pot must be a finite positive real number.")
            self.pot = float(pot)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Pot must be a finite positive real number.") from exc
        if not math.isfinite(self.pot) or self.pot <= 0:
            raise ValueError("Pot must be a finite positive real number.")

        legal_rivers = tuple(card for card in DECK if card not in self.board)
        if runouts is None:
            selected = legal_rivers
        else:
            if isinstance(runouts, (str, bytes)):
                selected = cards(runouts)
            else:
                try:
                    selected = tuple(cards((river,), 1)[0] for river in runouts)
                except (TypeError, ValueError) as exc:
                    raise ValueError("Runouts must be unique river cards outside the board.") from exc
            if not selected:
                raise ValueError("Runouts must be a nonempty set of unique river cards.")
            if len(set(selected)) != len(selected) or any(
                    river not in legal_rivers for river in selected):
                raise ValueError("Runouts must be unique river cards outside the board.")

        # Count branch hand slots before creating filtered arrays or rank kernels.
        plans = []
        slot_total = 0
        for river in selected:
            filtered0_count = sum(river not in hand for hand in self.hands[0])
            filtered1_count = sum(river not in hand for hand in self.hands[1])
            slot_total += filtered0_count + filtered1_count
            if slot_total > MAX_HAND_SLOTS:
                raise ValueError("Turn range kernel exceeds 120,000 filtered hand slots.")
            plans.append((river, filtered0_count, filtered1_count))
        self.hand_slots = slot_total

        branches = {}
        for river, _count0, _count1 in plans:
            indexes0 = tuple(i for i, hand in enumerate(self.hands[0]) if river not in hand)
            indexes1 = tuple(i for i, hand in enumerate(self.hands[1]) if river not in hand)
            filtered0 = tuple(self.hands[0][i] for i in indexes0)
            filtered1 = tuple(self.hands[1][i] for i in indexes1)
            if not filtered0 or not filtered1 or _compatible_pair_count(filtered0, filtered1) == 0:
                continue
            branch_weights = (
                tuple(self.weights[0][i] for i in indexes0),
                tuple(self.weights[1][i] for i in indexes1),
            )
            remaining_budget = self.fallback_pair_limit - self.fallback_pair_checks
            kernel = RankedRiverPayoffs(
                self.board + (river,), (filtered0, filtered1), branch_weights,
                pot=self.pot, fallback_pair_limit=remaining_budget,
            )
            if self.fallback_pair_checks + kernel.fallback_pair_checks > self.fallback_pair_limit:
                raise ValueError("Turn range fallback pair-check budget exceeded.")
            self.fallback_pair_checks += kernel.fallback_pair_checks
            mass0 = math.fsum(branch_weights[0])
            mass1 = math.fsum(branch_weights[1])
            branch_mass = (mass0 * mass1) / kernel.factor
            if not math.isfinite(branch_mass) or branch_mass <= 0:
                raise ValueError("Selected river branch mass is not representable.")
            branches[river] = {
                "kernel": kernel, "indexes": (indexes0, indexes1),
                "mass": branch_mass, "pair_count": kernel.compatible_pair_count,
                "marginals": None,
            }
        if not branches:
            raise ValueError("Selected runouts contain no compatible physical deals.")
        total_mass = math.fsum(branch["mass"] for branch in branches.values())
        if not math.isfinite(total_mass) or total_mass <= 0:
            raise ValueError("Selected runout joint mass is not representable.")
        self._branches = branches
        self.branch_probabilities = MappingProxyType({
            river: branch["mass"] / total_mass
            for river, branch in branches.items()
        })
        if any(not math.isfinite(probability) or probability <= 0
               for probability in self.branch_probabilities.values()):
            raise ValueError("A selected river has unrepresentable conditional probability.")
        self.compatible_world_count = sum(branch["pair_count"]
                                          for branch in branches.values())

    def _charge(self, branch, before):
        kernel = branch["kernel"]
        added = kernel.fallback_pair_checks - before
        if added < 0:
            raise RuntimeError("Ranked river fallback counter moved backwards.")
        proposed = self.fallback_pair_checks + added
        if proposed > self.fallback_pair_limit:
            raise ValueError("Turn range fallback pair-check budget exceeded.")
        self.fallback_pair_checks = proposed

    def _prepare_kernel_budget(self, branch):
        kernel = branch["kernel"]
        remaining = self.fallback_pair_limit - self.fallback_pair_checks
        kernel.fallback_pair_limit = kernel.fallback_pair_checks + remaining

    def _marginals(self, branch):
        if branch["marginals"] is None:
            kernel = branch["kernel"]
            self._prepare_kernel_budget(branch)
            before = kernel.fallback_pair_checks
            try:
                compact = kernel.joint_marginals()
            finally:
                self._charge(branch, before)
            result = []
            for player in (0, 1):
                full = [0.0] * len(self.hands[player])
                for compact_index, original_index in enumerate(branch["indexes"][player]):
                    full[original_index] = compact[player][compact_index]
                result.append(tuple(full))
            branch["marginals"] = tuple(result)
        return branch["marginals"]

    def joint_marginals(self, prefix=()):
        """Return full-range joint marginals at root or a selected river prefix."""
        if isinstance(prefix, (str, bytes)):
            raise ValueError("Prefix must be empty or contain one selected river card.")
        try:
            prefix = tuple(prefix)
        except TypeError as exc:
            raise ValueError("Prefix must be empty or contain one selected river card.") from exc
        if len(prefix) > 1:
            raise ValueError("Prefix must be empty or contain one selected river card.")
        if prefix:
            river = cards(prefix, 1)[0]
            if river not in self._branches:
                raise ValueError("Prefix does not identify a compatible selected river.")
            branch = self._branches[river]
            probability = self.branch_probabilities[river]
            conditional = self._marginals(branch)
            result = tuple(tuple(probability * value for value in side)
                           for side in conditional)
            if any(not math.isfinite(value) for side in result for value in side):
                raise ArithmeticError("Turn prefix joint marginals must be finite.")
            if any(not math.isclose(math.fsum(side), probability,
                                    rel_tol=1e-10, abs_tol=1e-12)
                   for side in result):
                raise ArithmeticError("Turn prefix joint marginals do not match branch mass.")
            return result

        answer = [[0.0] * len(self.hands[player]) for player in (0, 1)]
        for river, branch in self._branches.items():
            probability = self.branch_probabilities[river]
            conditional = self._marginals(branch)
            for player in (0, 1):
                for index, value in enumerate(conditional[player]):
                    answer[player][index] += probability * value
        for player in (0, 1):
            if not all(math.isfinite(value) for value in answer[player]):
                raise ArithmeticError("Turn root joint marginals must be finite.")
            if not math.isclose(math.fsum(answer[player]), 1.0,
                                rel_tol=1e-10, abs_tol=1e-12):
                raise ArithmeticError("Turn root joint marginals do not sum to one.")
        return tuple(tuple(side) for side in answer)

    def values(self, node, opponent_reach, player, prefix=()):
        """Return full-range branch-weighted utilities for turn or river leaves.

        At the turn root only folds are defined without a river reveal; those
        fold values integrate across all selected compatible river branches.
        Showdown values require a one-card river prefix.
        """
        if not isinstance(node, _Terminal) or node.kind not in ("fold", "showdown"):
            raise ValueError("Turn range payoffs support only fold and showdown terminals.")
        if type(player) is not int or player not in (0, 1):
            raise ValueError("player must be 0 (OOP) or 1 (IP).")
        opponent_reach = RankedRiverPayoffs._reach(
            opponent_reach, len(self.hands[1 - player]))
        if isinstance(prefix, (str, bytes)):
            raise ValueError("Prefix must be empty or contain one selected river card.")
        try:
            prefix = tuple(prefix)
        except TypeError as exc:
            raise ValueError("Prefix must be empty or contain one selected river card.") from exc
        if len(prefix) > 1:
            raise ValueError("Prefix must be empty or contain one selected river card.")
        if not prefix:
            if node.kind != "fold":
                raise ValueError("Turn-root showdown values require a revealed river card.")
            active = tuple(self._branches)
        else:
            river = cards(prefix, 1)[0]
            if river not in self._branches:
                raise ValueError("Prefix does not identify a compatible selected river.")
            active = (river,)

        answer = [0.0] * len(self.hands[player])
        for river in active:
            branch = self._branches[river]
            kernel = branch["kernel"]
            opponent_indexes = branch["indexes"][1 - player]
            compact_reach = tuple(opponent_reach[index] for index in opponent_indexes)
            self._prepare_kernel_budget(branch)
            before = kernel.fallback_pair_checks
            try:
                compact_values = kernel.values(node, compact_reach, player)
            finally:
                self._charge(branch, before)
            own_indexes = branch["indexes"][player]
            probability = self.branch_probabilities[river]
            for compact_index, original_index in enumerate(own_indexes):
                answer[original_index] += probability * compact_values[compact_index]
        if not all(math.isfinite(value) for value in answer):
            raise ValueError("Turn range payoff values must be finite.")
        return answer
