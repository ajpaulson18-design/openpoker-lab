"""Streaming joint chance and terminal payoff operator for selected boards.

For a compatible private pair and selected board, raw mass is
``w0 * w1 / C(48,3) / 45 / 44``. Each selected ordered physical board has
the same raw mass. The global normalizer is the fsum of that mass repeated
once for every compatible pair/board world. No pair/world table is retained.
"""
from math import fsum, isfinite
from numbers import Real
from collections import OrderedDict

from .cards import DECK, expand_range, rank_hand
from .preflop_solver import (
    _MAX_CANDIDATE_HAND_ITERATIONS, _MAX_PAIR_RUNOUT_PREFLIGHT_CHECKS,
    _MAX_WORLD_ITERATIONS, _OUTCOMES_PER_UNBLOCKED_PAIR, _requested_runouts,
)
from .probability_guard import normal_positive_mass
from .river_tree import _Terminal

_CARD_BIT = {card: 1 << index for index, card in enumerate(DECK)}
MAX_RANK_CACHE_BOARDS = 64
MAX_RANK_CACHE_ENTRIES = 8192


class SelectedRunoutOperator:
    """Matrix-free selected-runout chance/payoff operator.

    Retained input storage is linear in both ranges and selected runouts.
    Pair/runout loops stream through compact card masks. ``pot`` is assigned
    by the enclosing tree builder after its positive-pot shift is established.
    """

    def __init__(self, sb_range, bb_range, runouts, iterations=1, *,
                 rank_cache_boards=1):
        if (type(rank_cache_boards) is not int or
                not 1 <= rank_cache_boards <= MAX_RANK_CACHE_BOARDS):
            raise ValueError("rank_cache_boards must be an integer from 1 through 64.")
        if type(iterations) is not int or iterations < 1:
            raise ValueError("iterations must be a positive integer.")
        ranges = (expand_range(sb_range), expand_range(bb_range))
        self.hands = (tuple(ranges[0]), tuple(ranges[1]))
        self.weights = (tuple(ranges[0][h] for h in self.hands[0]),
                        tuple(ranges[1][h] for h in self.hands[1]))
        self.hand_counts = tuple(map(len, self.hands))
        # Reserve an extra row for list-to-tuple construction references while
        # the oldest retained board is evicted before a new vector is built.
        requested_rank_entries = (rank_cache_boards + 1) * sum(self.hand_counts)
        if rank_cache_boards > 1 and requested_rank_entries > MAX_RANK_CACHE_ENTRIES:
            raise ValueError("Requested board-rank cache exceeds 8,192 retained-plus-active rank entries.")
        self.rank_cache_boards = rank_cache_boards
        self.rank_cache_requested_entries = requested_rank_entries
        self._hand_masks = tuple(tuple(_CARD_BIT[h[0]] | _CARD_BIT[h[1]] for h in side)
                                  for side in self.hands)
        self.selected = _requested_runouts(runouts)
        self._board_masks = tuple(sum(_CARD_BIT[c] for c in flop + (turn, river))
                                  for flop, turn, river in self.selected)
        self._flop_keys = tuple("".join(flop) for flop, _, _ in self.selected)
        self.world_count = 0
        self.compatible_pairs = 0
        self.private_compatible_pairs = 0
        self.preflight_checks = 0
        self.normalizer = 0.0
        self.rank_calls = 0
        self.rank_scratch_peak = 0
        self.rank_cache_hits = 0
        self.rank_cache_misses = 0
        self.rank_cache_evictions = 0
        self.rank_cache_retained_peak_entries = 0
        self._rank_cache_key = None
        self._rank_cache = None
        self._board_rank_lru = OrderedDict() if rank_cache_boards > 1 else None
        self.query_pair_runout_checks = 0
        self.pot = None

        candidate_count = self.hand_counts[0] * self.hand_counts[1]
        if candidate_count * iterations > _MAX_CANDIDATE_HAND_ITERATIONS:
            raise ValueError("Preflop solver exceeds 3 million candidate-pair iterations.")
        if len(self.selected) > _MAX_PAIR_RUNOUT_PREFLIGHT_CHECKS:
            raise ValueError("Preflop physical-world preflight exceeds 30 million pair/runout checks.")
        for i, mask0 in enumerate(self._hand_masks[0]):
            for j, mask1 in enumerate(self._hand_masks[1]):
                if mask0 & mask1:
                    continue
                self.private_compatible_pairs += 1
                supported = False
                for board_mask in self._board_masks:
                    self.preflight_checks += 1
                    if self.preflight_checks > _MAX_PAIR_RUNOUT_PREFLIGHT_CHECKS:
                        raise ValueError("Preflop physical-world preflight exceeds 30 million pair/runout checks.")
                    if not (board_mask & (mask0 | mask1)):
                        supported = True
                        self.world_count += 1
                        if self.world_count * iterations > _MAX_WORLD_ITERATIONS:
                            raise ValueError("Preflop solver exceeds 3 million world iterations.")
                if supported:
                    self.compatible_pairs += 1
        if not self.private_compatible_pairs:
            raise ValueError("Ranges contain no compatible private-card pairs.")
        if not self.world_count:
            raise ValueError("Selected runouts contain no compatible physical deals.")

        # Keep the materialized producer's per-world guard and global fsum.
        self.normalizer = fsum(self._raw_mass(i, j)
                               for i, j, _k in self._iter_worlds())
        if not isfinite(self.normalizer) or self.normalizer <= 0:
            raise ValueError("Selected ranges and runouts have no positive joint mass.")
        normal_positive_mass(self.normalizer / self.world_count)
        self._validate_all_normalized()
        self.query_pair_runout_checks = 0

    def _iter_worlds(self, prefix=()):
        """Yield compatible physical worlds in historical hand/runout order."""
        indexes = self._prefix_indexes(prefix)
        for i, mask0 in enumerate(self._hand_masks[0]):
            for j, mask1 in enumerate(self._hand_masks[1]):
                pair_mask = mask0 | mask1
                if mask0 & mask1:
                    continue
                for k in indexes:
                    self.query_pair_runout_checks += 1
                    if not (self._board_masks[k] & pair_mask):
                        yield i, j, k

    def _raw_mass(self, i, j):
        return normal_positive_mass(
            self.weights[0][i] * self.weights[1][j] / _OUTCOMES_PER_UNBLOCKED_PAIR)

    def _validate_all_normalized(self):
        # Check every world's normalized binary64 mass while retaining O(1) state.
        for i, j, _k in self._iter_worlds():
            normal_positive_mass(self._raw_mass(i, j) / self.normalizer)

    def _prefix_indexes(self, prefix):
        if isinstance(prefix, (str, bytes)):
            raise ValueError("Prefix must be empty, a flop, flop plus turn, or a complete runout.")
        try:
            prefix = tuple(prefix)
        except TypeError as exc:
            raise ValueError("Invalid selected-runout prefix.") from exc
        if not prefix:
            return range(len(self.selected))
        if len(prefix) == 1:
            key = prefix[0]
            return tuple(i for i, value in enumerate(self._flop_keys) if value == key)
        if len(prefix) == 2:
            flop_key, turn = prefix
            return tuple(i for i, (flop, t, _r) in enumerate(self.selected)
                         if "".join(flop) == flop_key and t == turn)
        if len(prefix) == 3:
            flop_key, turn, river = prefix
            return tuple(i for i, (flop, t, r) in enumerate(self.selected)
                         if "".join(flop) == flop_key and t == turn and r == river)
        raise ValueError("Prefix must be empty, a flop, flop plus turn, or a complete runout.")

    def _prefix_world_count(self, prefix):
        return sum(1 for _ in self._iter_worlds(prefix))

    def joint_marginals(self, prefix=()):
        out = [[0.0] * self.hand_counts[p] for p in (0, 1)]
        indexes = self._prefix_indexes(prefix)
        for i, mask0 in enumerate(self._hand_masks[0]):
            for j, mask1 in enumerate(self._hand_masks[1]):
                pair_mask = mask0 | mask1
                if mask0 & mask1:
                    continue
                mass = 0.0
                for k in indexes:
                    self.query_pair_runout_checks += 1
                    if not (self._board_masks[k] & pair_mask):
                        mass += self._raw_mass(i, j) / self.normalizer
                if mass:
                    out[0][i] += mass
                    out[1][j] += mass
        return tuple(tuple(side) for side in out)

    def legal_hands(self, prefix=()):
        seen = (set(), set())
        for i, j, _k in self._iter_worlds(prefix):
            seen[0].add(i)
            seen[1].add(j)
        return tuple(frozenset(side) for side in seen)

    def pair_probabilities(self):
        result = []
        for i, mask0 in enumerate(self._hand_masks[0]):
            for j, mask1 in enumerate(self._hand_masks[1]):
                if mask0 & mask1:
                    continue
                count = 0
                for board in self._board_masks:
                    self.query_pair_runout_checks += 1
                    count += not (board & (mask0 | mask1))
                if count:
                    result.append({
                        "sb_hand": "".join(self.hands[0][i]),
                        "bb_hand": "".join(self.hands[1][j]),
                        "probability": normal_positive_mass(
                            self._raw_mass(i, j) * count / self.normalizer),
                    })
        return result

    def reachable_selected(self):
        support = set()
        for _i, _j, k in self._iter_worlds():
            support.add(k)
        return tuple(self.selected[k] for k in sorted(support))

    def iter_edges(self, prefix=(), signed=False):
        """Yield aggregated (hand0, hand1, mass, signed_mass) edges lazily."""
        indexes = self._prefix_indexes(prefix)
        for i, mask0 in enumerate(self._hand_masks[0]):
            for j, mask1 in enumerate(self._hand_masks[1]):
                pair_mask = mask0 | mask1
                if mask0 & mask1:
                    continue
                raw = None
                mass = signed_mass = 0.0
                for k in indexes:
                    self.query_pair_runout_checks += 1
                    if self._board_masks[k] & pair_mask:
                        continue
                    if raw is None:
                        raw = self._raw_mass(i, j)
                    world_mass = raw / self.normalizer
                    mass += world_mass
                    if signed:
                        signed_mass += world_mass * self._world_sign(i, j, k)
                if raw is not None:
                    yield i, j, mass, signed_mass

    def _world_sign(self, i, j, k):
        if self.rank_cache_boards > 1:
            ranks = self._board_rank_lru.get(k)
            if ranks is None:
                self.rank_cache_misses += 1
                if len(self._board_rank_lru) >= self.rank_cache_boards:
                    self._board_rank_lru.popitem(last=False)
                    self.rank_cache_evictions += 1
                hand_sum = sum(self.hand_counts)
                construction_bound = (len(self._board_rank_lru) + 2) * hand_sum
                if construction_bound > self.rank_cache_requested_entries:
                    raise RuntimeError("Board-rank construction exceeded its admitted entry bound.")
                # Nothing is published if a rank call fails. A successfully
                # evicted old row need not be restored after an exception.
                ranks = self._build_rank_vectors(k)
                self._board_rank_lru[k] = ranks
                self.rank_cache_retained_peak_entries = max(
                    self.rank_cache_retained_peak_entries, len(self._board_rank_lru) * hand_sum)
                self.rank_scratch_peak = max(self.rank_scratch_peak, construction_bound)
            else:
                self.rank_cache_hits += 1
                self._board_rank_lru.move_to_end(k)
            r0, r1 = ranks[0][i], ranks[1][j]
            return (r0 > r1) - (r0 < r1)

        # Preserve the original one-board reduction and ranking schedule.
        if self._rank_cache_key != k:
            flop, turn, river = self.selected[k]
            board = flop + (turn, river)
            board_mask = self._board_masks[k]
            vectors = []
            for player in (0, 1):
                ranks = []
                for hand, mask in zip(self.hands[player], self._hand_masks[player]):
                    if board_mask & mask:
                        ranks.append(None)
                    else:
                        ranks.append(rank_hand(hand + board))
                        self.rank_calls += 1
                vectors.append(tuple(ranks))
            self._rank_cache_key = k
            self._rank_cache = tuple(vectors)
            self.rank_scratch_peak = max(self.rank_scratch_peak, sum(self.hand_counts))
        r0, r1 = self._rank_cache[0][i], self._rank_cache[1][j]
        return (r0 > r1) - (r0 < r1)

    def _build_rank_vectors(self, k):
        flop, turn, river = self.selected[k]
        board = flop + (turn, river)
        board_mask = self._board_masks[k]
        vectors = []
        for player in (0, 1):
            ranks = []
            for hand, mask in zip(self.hands[player], self._hand_masks[player]):
                if board_mask & mask:
                    ranks.append(None)
                else:
                    ranks.append(rank_hand(hand + board))
                    self.rank_calls += 1
            vectors.append(tuple(ranks))
        return tuple(vectors)

    def clear_rank_cache(self):
        """Release retained ranks without changing counters or input snapshots."""
        self._rank_cache_key = None
        self._rank_cache = None
        if self._board_rank_lru is not None:
            self._board_rank_lru.clear()

    def structural_storage_counts(self):
        """Return retained input entry counts, not bytes or a memory estimate."""
        return {
            "hand_entries": sum(self.hand_counts),
            "hand_card_masks": sum(self.hand_counts),
            "selected_runout_entries": len(self.selected),
            "selected_runout_card_masks": len(self._board_masks),
            "flop_prefix_keys": len(self._flop_keys),
        }

    def values(self, node, opponent_reach, target_player, prefix=()):
        if not isinstance(node, _Terminal) or node.kind not in ("fold", "showdown"):
            raise ValueError("Selected runout payoffs support only fold and showdown terminals.")
        if not isinstance(node.contributions, (tuple, list)) or len(node.contributions) != 2:
            raise ValueError("Terminal contributions must contain two values.")
        contributions = []
        for value in node.contributions:
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError("Terminal contributions must be finite nonnegative numbers.")
            try:
                value = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Terminal contributions must be finite nonnegative numbers.") from exc
            if not isfinite(value) or value < 0:
                raise ValueError("Terminal contributions must be finite nonnegative numbers.")
            contributions.append(value)
        if node.kind == "fold" and (type(node.winner) is not int or node.winner not in (0, 1)):
            raise ValueError("A fold terminal must identify player 0 or 1 as winner.")
        if node.kind == "showdown" and node.winner is not None:
            raise ValueError("A showdown terminal cannot identify a fold winner.")
        if type(target_player) is not int or target_player not in (0, 1):
            raise ValueError("target_player must be 0 or 1.")
        if isinstance(opponent_reach, (str, bytes)) or len(opponent_reach) != self.hand_counts[1-target_player]:
            raise ValueError("Opponent reach must match the opponent hand count.")
        reach = []
        for value in opponent_reach:
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError("Opponent reach must contain finite nonnegative values.")
            try:
                value = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Opponent reach must contain finite nonnegative values.") from exc
            if not isfinite(value) or value < 0:
                raise ValueError("Opponent reach must contain finite nonnegative values.")
            reach.append(value)
        try:
            prefix = tuple(prefix)
        except TypeError as exc:
            raise ValueError("Invalid selected-runout prefix.") from exc
        indexes = self._prefix_indexes(prefix)
        try:
            pot = float(self.pot)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Operator pot must be finite and positive.") from exc
        if isinstance(self.pot, bool) or not isinstance(self.pot, Real) or not isfinite(pot) or pot <= 0:
            raise ValueError("Operator pot must be finite and positive.")
        matched = min(contributions)
        scale = pot / 2.0 + matched
        if not isfinite(scale):
            raise ValueError("Terminal payoff scale must be finite.")
        answer = [0.0] * self.hand_counts[target_player]
        for i, mask0 in enumerate(self._hand_masks[0]):
            for j, mask1 in enumerate(self._hand_masks[1]):
                pair_mask = mask0 | mask1
                if mask0 & mask1:
                    continue
                raw = None
                pair_mass = signed_mass = 0.0
                for k in indexes:
                    self.query_pair_runout_checks += 1
                    if self._board_masks[k] & pair_mask:
                        continue
                    if raw is None:
                        raw = self._raw_mass(i, j)
                    world_mass = raw / self.normalizer
                    pair_mass += world_mass
                    if node.kind == "showdown":
                        signed_mass += world_mass * self._world_sign(i, j, k)
                if raw is None:
                    continue
                own, opp = (i, j) if target_player == 0 else (j, i)
                if node.kind == "fold":
                    payoff = (1.0 if node.winner == 0 else -1.0) * scale
                    term = pair_mass * reach[opp] * payoff
                else:
                    term = signed_mass * reach[opp] * scale
                answer[own] += term if target_player == 0 else -term
        if any(not isfinite(value) for value in answer):
            raise ValueError("Selected runout payoff values must be finite.")
        return answer
