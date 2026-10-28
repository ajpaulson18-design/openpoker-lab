"""Integer-backed exact arithmetic for the selected-runout reference kernel.

The helper is solve-local and private to ``ExactSelectedRunoutKernel``. Parsed
weights, callback reaches and payoff scales are dyadic Fractions. Each side's
weights therefore share one power-of-two denominator, allowing hand/card
buckets and rank sweeps to use integers and construct Fractions only for the
completed output vector.
"""
from __future__ import annotations

from fractions import Fraction
import math
import weakref

from .cards import DECK

MAX_INTEGER_PAYLOAD_BITS = 1 << 30


class DyadicSelectedArithmeticPlan:
    """Immutable snapshot plan; query counters are mutable private receipts.

    Construction accepts the already parsed exact kernel. The plan does not
    own the kernel strongly, so attaching the plan to that kernel creates no
    reference cycle and cannot retain a completed solve.
    """

    __slots__ = (
        "_sealed", "_kernel_ref", "_hands", "_weights", "_selected",
        "_normalizer", "_hand_masks", "_board_masks", "_limits",
        "_integer_weights", "_card_ids", "_side_exponents", "_z_integer",
        "_z_denominator_exponent", "_retained_entries", "_max_forecast_bits",
        "_counts",
    )

    def __setattr__(self, name, value):
        if getattr(self, "_sealed", False):
            raise AttributeError("Dyadic selected arithmetic snapshots are immutable.")
        object.__setattr__(self, name, value)

    def __init__(self, kernel):
        from .exact_selected_kernel import ExactSelectedRunoutKernel
        if type(kernel) is not ExactSelectedRunoutKernel:
            raise TypeError("Dyadic arithmetic requires an ExactSelectedRunoutKernel.")
        self._sealed = False
        self._kernel_ref = weakref.ref(kernel)
        self._hands = kernel.hands
        self._weights = kernel.weights
        self._selected = kernel.selected
        self._normalizer = kernel.normalizer
        self._hand_masks = kernel._hand_masks
        self._board_masks = kernel._board_masks
        self._limits = kernel.limits

        max_exponents = []
        for side in self._weights:
            exponents = tuple(self._dyadic_exponent(value, "range weight") for value in side)
            max_exponents.append(max(exponents, default=0))
        side_exponents = tuple(max_exponents)
        limit = self._limits.max_integer_bits
        shift_plans = []
        max_bits = 1
        shifts = 0
        for side, exponent in zip(self._weights, side_exponents):
            side_plan = []
            for value in side:
                shift = exponent - self._dyadic_exponent(value, "range weight")
                forecast = abs(value.numerator).bit_length() + shift
                if shift < 0 or forecast > limit:
                    raise ValueError("Dyadic scaled range-weight bit forecast exceeded.")
                max_bits = max(max_bits, forecast)
                shifts += bool(shift)
                side_plan.append(shift)
            shift_plans.append(tuple(side_plan))

        z_exponent = self._dyadic_exponent(self._normalizer, "kernel normalizer")
        common_exponent = side_exponents[0] + side_exponents[1]
        z_shift = common_exponent - z_exponent
        z_bits = abs(self._normalizer.numerator).bit_length() + z_shift
        common_denominator_bits = common_exponent + 1
        if z_shift < 0 or z_bits > limit or common_denominator_bits > limit:
            raise ValueError("Dyadic global normalizer bit forecast exceeded.")
        max_bits = max(max_bits, z_bits, common_denominator_bits)
        hand_total = sum(map(len, self._hands))
        setup_payload_bits = (8 * hand_total + 128) * max(max_bits, 1)
        if setup_payload_bits > MAX_INTEGER_PAYLOAD_BITS:
            raise ValueError("Dyadic setup integer-payload admission exceeded.")

        # All scaled operand and denominator widths have been admitted before
        # the first integer shift or plan-vector allocation.
        scaled = tuple(tuple(value.numerator << shift
                             for value, shift in zip(side, side_plan))
                       for side, side_plan in zip(self._weights, shift_plans))
        z_integer = self._normalizer.numerator << z_shift
        if z_integer <= 0:
            raise ValueError("Dyadic global normalizer must be positive.")
        card_ids = tuple(tuple((DECK.index(hand[0]), DECK.index(hand[1]))
                               for hand in side) for side in self._hands)
        # Two integer weight vectors, two card ids per hand, the fixed card
        # domain, and plan/scale metadata fit the root's reserved 8H+128 setup
        # entries. This is a logical-slot count, not an object-byte estimate.
        retained_entries = (6 * hand_total + 52 + 32)
        reserved = 8 * hand_total + 128
        if retained_entries > reserved:
            raise ValueError("Dyadic plan retained entries exceed the kernel setup reservation.")

        object.__setattr__(self, "_side_exponents", side_exponents)
        object.__setattr__(self, "_integer_weights", tuple(scaled))
        object.__setattr__(self, "_card_ids", card_ids)
        object.__setattr__(self, "_z_integer", z_integer)
        object.__setattr__(self, "_z_denominator_exponent", common_exponent)
        object.__setattr__(self, "_retained_entries", retained_entries)
        object.__setattr__(self, "_max_forecast_bits", max_bits)
        object.__setattr__(self, "_counts", {
            "marginal_queries": 0, "terminal_queries": 0,
            "boards_processed": 0, "rank_vector_requests": 0,
            "integer_additions": 0, "integer_multiplications": 0,
            "integer_shifts": shifts + bool(z_shift) + bool(common_exponent),
            "peak_operand_bits": max_bits, "peak_forecast_bits": max_bits,
            "peak_integer_payload_bits": setup_payload_bits,
            "rational_output_components": 0,
        })
        # Check the scaled normalizer identity without a hand/pair loop.
        if Fraction(z_integer, 1 << common_exponent) != self._normalizer:
            raise ValueError("Dyadic global normalizer identity mismatch.")
        object.__setattr__(self, "_sealed", True)

    @staticmethod
    def _dyadic_exponent(value, label):
        if type(value) is not Fraction or value.denominator <= 0:
            raise TypeError(f"{label} must be an exact Fraction.")
        denominator = value.denominator
        if denominator & (denominator - 1):
            raise ValueError(f"{label} must have a dyadic denominator.")
        return denominator.bit_length() - 1

    def _kernel(self):
        kernel = self._kernel_ref()
        if kernel is None:
            raise ValueError("The exact kernel owning this dyadic plan no longer exists.")
        if (kernel.hands is not self._hands or kernel.weights is not self._weights or
                kernel.selected is not self._selected or kernel.normalizer is not self._normalizer or
                kernel._hand_masks is not self._hand_masks or
                kernel._board_masks is not self._board_masks or kernel.limits is not self._limits):
            raise ValueError("Exact kernel snapshot changed after dyadic plan admission.")
        return kernel

    def _assert_indexes(self, indexes):
        if type(indexes) is not tuple or len(indexes) > len(self._selected):
            raise ValueError("Dyadic arithmetic requires a bounded kernel board-index tuple.")
        if (any(type(index) is not int or not 0 <= index < len(self._selected)
                for index in indexes) or len(set(indexes)) != len(indexes)):
            raise ValueError("Dyadic board indexes must be unique valid selected indexes.")

    def _note_width(self, value):
        bits = abs(value).bit_length()
        if bits > self._counts["peak_operand_bits"]:
            self._counts["peak_operand_bits"] = bits

    def _add(self, left, right):
        result = left + right
        self._counts["integer_additions"] += 1
        self._note_width(result)
        return result

    def _sub(self, left, right):
        return self._add(left, -right)

    def _mul(self, left, right):
        result = left * right
        self._counts["integer_multiplications"] += 1
        self._note_width(result)
        return result

    def _checked_bits(self, forecast, label):
        self._counts["peak_forecast_bits"] = max(self._counts["peak_forecast_bits"], forecast)
        if forecast > self._limits.max_integer_bits:
            raise ValueError(f"Dyadic {label} integer-bit forecast exceeded.")

    def _check_integer_payload(self, forecast_bits, label):
        hand_total = sum(map(len, self._hands))
        payload_bits = ((8 * hand_total + 128) * max(self._max_forecast_bits, 1) +
                        (140 * hand_total + 800) * max(forecast_bits, 1))
        self._counts["peak_integer_payload_bits"] = max(
            self._counts["peak_integer_payload_bits"], payload_bits)
        if payload_bits > MAX_INTEGER_PAYLOAD_BITS:
            raise ValueError(f"Dyadic {label} integer-payload admission exceeded.")

    def _bucket(self, rows, side):
        total, cards, exact = 0, [0] * 52, {}
        for hand_index, hand, value in rows:
            a, b = self._card_ids[side][hand_index]
            total = self._add(total, value)
            cards[a] = self._add(cards[a], value)
            cards[b] = self._add(cards[b], value)
            exact[hand] = value
        return total, cards, exact

    def _compatible(self, hand, ids, bucket):
        total, cards, exact = bucket
        a, b = ids
        return self._add(self._sub(self._sub(total, cards[a]), cards[b]), exact.get(hand, 0))

    def _marginal_forecast(self, indexes):
        h0, h1 = map(len, self._hands)
        max_weights = [max((v.bit_length() for v in side), default=1)
                       for side in self._integer_weights]
        log_h = math.ceil(math.log2(max(1, max(h0, h1))))
        opp0 = max_weights[1] + log_h + 2
        opp1 = max_weights[0] + log_h + 2
        comp0, comp1 = opp0 + 3, opp1 + 3
        out0 = max_weights[0] + comp0 + math.ceil(math.log2(max(1, len(indexes)))) + 2
        out1 = max_weights[1] + comp1 + math.ceil(math.log2(max(1, len(indexes)))) + 2
        self._checked_bits(max(out0, out1, self._z_integer.bit_length()), "marginal")
        self._check_integer_payload(max(out0, out1), "marginal")

    def marginals(self, indexes):
        """Return globally normalized exact marginals for admitted boards."""
        kernel = self._kernel()
        self._assert_indexes(indexes)
        self._marginal_forecast(indexes)
        self._counts["marginal_queries"] += 1
        out = [[0] * len(self._hands[side]) for side in (0, 1)]
        for board_index in indexes:
            self._counts["boards_processed"] += 1
            blocked = self._board_masks[board_index]
            rows = []
            for side in (0, 1):
                rows.append([(i, hand, self._integer_weights[side][i])
                             for i, hand in enumerate(self._hands[side])
                             if not (blocked & self._hand_masks[side][i])])
            bucket0, bucket1 = self._bucket(rows[0], 0), self._bucket(rows[1], 1)
            for side, own_rows, opponent_bucket in ((0, rows[0], bucket1),
                                                    (1, rows[1], bucket0)):
                for own_index, hand, own_weight in own_rows:
                    compatible = self._compatible(
                        hand, self._card_ids[side][own_index], opponent_bucket)
                    value = self._mul(own_weight, compatible)
                    out[side][own_index] = self._add(out[side][own_index], value)
        denominator = self._z_integer
        result = tuple(tuple(Fraction(value, denominator) for value in side) for side in out)
        self._counts["rational_output_components"] += sum(map(len, result))
        return result

    def _terminal_preflight(self, indexes, kind, payoff, player, reach):
        if kind not in ("fold", "showdown"):
            raise ValueError("kind must be 'fold' or 'showdown'.")
        if type(player) is not int or player not in (0, 1):
            raise ValueError("player must be 0 or 1.")
        if type(payoff) is not Fraction:
            raise TypeError("Dyadic terminal payoff must be a snapshotted Fraction.")
        if kind == "showdown" and payoff < 0:
            raise ValueError("Showdown payoff must be nonnegative.")
        if not isinstance(reach, tuple) or len(reach) != len(self._hands[1-player]):
            raise ValueError("Snapshotted opponent reach dimension mismatch.")
        reach_exponents = tuple(self._dyadic_exponent(item, "opponent reach") for item in reach)
        if any(item < 0 or item > 1 for item in reach):
            raise ValueError("Opponent reach must be in [0, 1].")
        reach_exponent = max(reach_exponents, default=0)
        scale_exponent = self._dyadic_exponent(payoff, "terminal payoff")
        reach_bits = max((abs(item.numerator).bit_length() +
                          reach_exponent - exponent
                          for item, exponent in zip(reach, reach_exponents)), default=0)
        opp_side, own_side = 1-player, player
        opp_weight_bits = max((value.bit_length() for value in self._integer_weights[opp_side]), default=1)
        own_weight_bits = max((value.bit_length() for value in self._integer_weights[own_side]), default=1)
        weighted_bits = opp_weight_bits + reach_bits
        opp_sum_bits = weighted_bits + math.ceil(math.log2(max(1, len(reach)))) + 2
        # Card-bucket inclusion/exclusion can transiently exceed its total by
        # a small signed carry. Rank lower/equal/higher partitions are bounded
        # by the same total, with an extra carry for signed subtraction.
        signed_bits = opp_sum_bits + 4
        own_product_bits = own_weight_bits + signed_bits + abs(payoff.numerator).bit_length()
        board_accumulation_bits = own_product_bits + math.ceil(math.log2(max(1, len(indexes)))) + 2
        denominator_bits = (self._z_integer.bit_length() + reach_exponent + scale_exponent)
        forecast = max(reach_bits, weighted_bits, opp_sum_bits, signed_bits,
                       own_product_bits, board_accumulation_bits, denominator_bits,
                       self._z_integer.bit_length())
        self._checked_bits(forecast, "terminal")
        self._check_integer_payload(forecast, "terminal")
        return reach_exponent, reach_exponents, scale_exponent, forecast

    def terminal(self, indexes, *, kind, payoff, player, opponent_reach):
        """Return exact own-hand counterfactual values via integer sweeps."""
        kernel = self._kernel()
        self._assert_indexes(indexes)
        if not isinstance(opponent_reach, tuple):
            raise TypeError("Opponent reach must already be snapshotted as a tuple.")
        reach_exponent, reach_exponents, scale_exponent, _ = self._terminal_preflight(
            indexes, kind, payoff, player, opponent_reach)
        # All shift and multiplication forecasts passed before this integer
        # vector or any rank/cache request is created.
        reach_ints = tuple(value.numerator << (reach_exponent - exponent)
                           for value, exponent in zip(opponent_reach, reach_exponents))
        self._counts["integer_shifts"] += sum(
            reach_exponent > exponent for exponent in reach_exponents)
        for reach_int in reach_ints:
            self._note_width(reach_int)
        payoff_integer = payoff.numerator
        self._note_width(payoff_integer)
        opponent_side, own_side = 1-player, player
        own_weights = self._integer_weights[own_side]
        opponent_weights = self._integer_weights[opponent_side]
        denominator = self._z_integer << (reach_exponent + scale_exponent)
        self._counts["integer_shifts"] += int(reach_exponent + scale_exponent > 0)
        self._note_width(denominator)
        answer = [0] * len(self._hands[own_side])

        for board_index in indexes:
            self._counts["boards_processed"] += 1
            blocked = self._board_masks[board_index]
            opp_rows = []
            for j, hand in enumerate(self._hands[opponent_side]):
                if blocked & self._hand_masks[opponent_side][j]:
                    continue
                weighted_reach = self._mul(opponent_weights[j], reach_ints[j])
                opp_rows.append((j, hand, weighted_reach))
            own_rows = [(i, hand, own_weights[i])
                        for i, hand in enumerate(self._hands[own_side])
                        if not (blocked & self._hand_masks[own_side][i])]

            if kind == "fold":
                bucket = self._bucket(opp_rows, opponent_side)
                for i, hand, own_weight in own_rows:
                    compatible = self._compatible(
                        hand, self._card_ids[own_side][i], bucket)
                    value = self._mul(self._mul(own_weight, compatible), payoff_integer)
                    if player == 1:
                        value = -value
                    answer[i] = self._add(answer[i], value)
                continue

            if not any(value for _j, _hand, value in opp_rows):
                continue
            self._counts["rank_vector_requests"] += 1
            ranks = kernel._rank_vectors(board_index)
            opponent_sorted = sorted(
                ((ranks[opponent_side][j], j, hand, value)
                 for j, hand, value in opp_rows), key=lambda row: row[0])
            own_sorted = sorted(
                ((ranks[own_side][i], i, hand, value)
                 for i, hand, value in own_rows), key=lambda row: row[0])
            all_bucket = self._bucket([(_j, hand, value)
                                       for _rank, _j, hand, value
                                       in opponent_sorted], opponent_side)
            lower_total, lower_cards = 0, [0] * 52
            opponent_pos = own_pos = 0
            while own_pos < len(own_sorted):
                rank = own_sorted[own_pos][0]
                while (opponent_pos < len(opponent_sorted) and
                       opponent_sorted[opponent_pos][0] < rank):
                    _orank, _j, hand, value = opponent_sorted[opponent_pos]
                    a, b = self._card_ids[opponent_side][_j]
                    lower_total = self._add(lower_total, value)
                    lower_cards[a] = self._add(lower_cards[a], value)
                    lower_cards[b] = self._add(lower_cards[b], value)
                    opponent_pos += 1
                equal_total, equal_cards = 0, [0] * 52
                equal_end = opponent_pos
                while (equal_end < len(opponent_sorted) and
                       opponent_sorted[equal_end][0] == rank):
                    _orank, _j, hand, value = opponent_sorted[equal_end]
                    a, b = self._card_ids[opponent_side][_j]
                    equal_total = self._add(equal_total, value)
                    equal_cards[a] = self._add(equal_cards[a], value)
                    equal_cards[b] = self._add(equal_cards[b], value)
                    equal_end += 1
                own_end = own_pos
                while own_end < len(own_sorted) and own_sorted[own_end][0] == rank:
                    _rank, i, hand, own_weight = own_sorted[own_end]
                    a, b = self._card_ids[own_side][i]
                    lower = self._sub(self._sub(lower_total, lower_cards[a]), lower_cards[b])
                    higher_total = self._sub(self._sub(all_bucket[0], lower_total), equal_total)
                    higher_a = self._sub(self._sub(all_bucket[1][a], lower_cards[a]), equal_cards[a])
                    higher_b = self._sub(self._sub(all_bucket[1][b], lower_cards[b]), equal_cards[b])
                    higher = self._sub(self._sub(higher_total, higher_a), higher_b)
                    signed = self._sub(lower, higher)
                    value = self._mul(self._mul(own_weight, signed), payoff_integer)
                    answer[i] = self._add(answer[i], value)
                    own_end += 1
                while opponent_pos < equal_end:
                    _orank, _j, hand, value = opponent_sorted[opponent_pos]
                    a, b = self._card_ids[opponent_side][_j]
                    lower_total = self._add(lower_total, value)
                    lower_cards[a] = self._add(lower_cards[a], value)
                    lower_cards[b] = self._add(lower_cards[b], value)
                    opponent_pos += 1
                own_pos = own_end

        self._counts["terminal_queries"] += 1
        result = tuple(Fraction(value, denominator) for value in answer)
        self._counts["rational_output_components"] += len(result)
        return result

    def receipt(self):
        integer_ops = (self._counts["integer_additions"] +
                       self._counts["integer_multiplications"] +
                       self._counts["integer_shifts"])
        rational_model_ops = 4 * self._counts["rational_output_components"]
        limbs = max(1, (self._counts["peak_operand_bits"] + 63) // 64)
        return {
            "version": "dyadic-selected-arithmetic-v1",
            "integer_operations": {key: self._counts[key] for key in (
                "integer_additions", "integer_multiplications", "integer_shifts")},
            "boards_processed": self._counts["boards_processed"],
            "rank_vector_requests": self._counts["rank_vector_requests"],
            "marginal_queries": self._counts["marginal_queries"],
            "terminal_queries": self._counts["terminal_queries"],
            "rational_output_components": self._counts["rational_output_components"],
            "peak_operand_bits": self._counts["peak_operand_bits"],
            "peak_forecast_bits": self._counts["peak_forecast_bits"],
            "peak_integer_payload_bits": self._counts["peak_integer_payload_bits"],
            "integer_payload_bit_limit": MAX_INTEGER_PAYLOAD_BITS,
            "modeled_limb_work_upper": (integer_ops + rational_model_ops) * limbs * limbs,
            "modeled_integer_and_fraction_output_ops": integer_ops + rational_model_ops,
            "side_weight_max_bits": tuple(
                max((value.bit_length() for value in side), default=1)
                for side in self._integer_weights),
            "side_weight_denominator_exponents": self._side_exponents,
            "side_weight_max_denominator_exponents": self._side_exponents,
            "retained_plan_entries": self._retained_entries,
            "setup_reservation_entries": 8 * sum(map(len, self._hands)) + 128,
            "max_integer_bits": self._limits.max_integer_bits,
            "normalizer_bits": self._z_integer.bit_length(),
            "normalizer_denominator_exponent": self._z_denominator_exponent,
            "scope": "Counted integer query-core and completed Fraction-output subset model using four abstract operations per normalized output; excludes Fraction GCD/LCM input/bit preflights, constructor Fraction normalization/identity checks, independent reference queries, adapter binary64 conversion and library/runtime overhead. This is not a complete arithmetic or CPU upper bound. Existing whole-request kernel logical work caps remain authoritative.",
        }
