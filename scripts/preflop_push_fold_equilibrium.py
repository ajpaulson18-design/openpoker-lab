"""Independent bounded exact equilibrium witnesses for explicit preflop shove/fold ranges."""
from fractions import Fraction
from itertools import combinations, product
from math import comb, isfinite

_BOARD_COUNT = comb(48, 5)
_RANKS = "23456789TJQKA"
_SUITS = "cdhs"
_MAX_POLICY_DIMENSIONS = (4, 8)
_MAX_SUPPORT_CANDIDATES = sum(comb(4, size) * comb(8, size)
                              for size in range(1, 5))


class NoEquilibriumWitness(ValueError):
    """The bounded support search did not certify an equilibrium."""


def _fraction(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return Fraction.from_float(number)


def _parse_range(expression):
    """Parse explicit nonnegative relative weights without production helpers."""
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("Expected explicit weighted private-hand combos")
    result = {}
    for token in expression.replace(",", " ").split():
        hand_text, separator, weight_text = token.partition(":")
        if len(hand_text) != 4:
            raise ValueError(f"Expected explicit four-card-code hand: {hand_text}")
        cards = (hand_text[:2].title(), hand_text[2:].title())
        if any(card[0] not in _RANKS or card[1] not in _SUITS for card in cards):
            raise ValueError(f"Invalid card in hand: {hand_text}")
        if cards[0] == cards[1]:
            raise ValueError(f"Duplicate card in hand: {hand_text}")
        hand = tuple(sorted(cards))
        weight = _fraction(weight_text if separator else 1.0, "Range weight")
        if weight < 0:
            raise ValueError("Relative range weights must be nonnegative")
        # Preserve explicitly named zero-weight combos so full-support count
        # tables can be reused after a range reweight removes their mass.
        result[hand] = weight
    if not any(result.values()):
        raise ValueError("Range must contain at least one positive-weight hand")
    if sum(weight > 0 for weight in result.values()) > 3:
        raise ValueError("Exact witness supports at most three active hands per player")
    return result


def _money(value, label):
    try:
        number = round(float(value), 9)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be finite positive chip amount") from exc
    if not isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be finite positive chip amount")
    return Fraction.from_float(number)


def _config_money(config):
    if not isinstance(config, dict):
        raise TypeError("Config must be a mapping")
    sb = _money(config.get("small_blind", 0.5), "Small blind")
    bb = _money(config.get("big_blind", 1), "Big blind")
    raw = config.get("starting_stack", 100)
    if isinstance(raw, (list, tuple)):
        if len(raw) != 2:
            raise ValueError("Starting stack must be a scalar or player pair")
        stacks = tuple(_money(value, "Starting stack") for value in raw)
    else:
        stack = _money(raw, "Starting stack")
        stacks = (stack, stack)
    if sb >= bb or any(stack <= bb for stack in stacks):
        raise ValueError("Blinds and stacks are outside the shove/fold model")
    return sb, bb, min(stacks)


def _solve_square(matrix, rhs):
    n = len(rhs)
    augmented = [list(map(Fraction, row)) + [Fraction(value)]
                 for row, value in zip(matrix, rhs)]
    if any(len(row) != n + 1 for row in augmented):
        raise ValueError("Expected a square linear system")
    for column in range(n):
        pivot = next((row for row in range(column, n)
                      if augmented[row][column]), None)
        if pivot is None:
            return None
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(n):
            if row != column and augmented[row][column]:
                scale = augmented[row][column]
                augmented[row] = [left - scale * right
                                  for left, right in zip(augmented[row], augmented[column])]
    return tuple(augmented[row][-1] for row in range(n))


def exact_zero_sum_witness(payoffs):
    """Find a bounded exact saddle witness for up to a 4-by-8 matrix.

    Search enumerates equal-cardinality supports only (at most 494 support
    pairs); it is deliberately not a complete solver for arbitrary matrices.
    """
    try:
        row_count = len(payoffs)
        rows = payoffs
    except TypeError:
        rows = tuple(payoffs)
        row_count = len(rows)
    if row_count == 0:
        raise ValueError("Payoff matrix must be nonempty")
    try:
        first_row = rows[0]
        col_count = len(first_row)
    except (IndexError, TypeError) as exc:
        raise ValueError("Payoff matrix must be a nonempty rectangular sequence") from exc
    if col_count == 0:
        raise ValueError("Payoff matrix must be nonempty")
    if (min(row_count, col_count) > _MAX_POLICY_DIMENSIONS[0]
            or max(row_count, col_count) > _MAX_POLICY_DIMENSIONS[1]):
        raise ValueError("Exact support search is limited to rectangular matrices up to 4x8")
    try:
        if any(len(row) != col_count for row in rows):
            raise ValueError("Exact support search requires a rectangular matrix")
    except TypeError as exc:
        raise ValueError("Exact support search requires a rectangular matrix") from exc
    matrix = tuple(tuple(Fraction(value) for value in row) for row in rows)

    for size in range(1, min(row_count, col_count) + 1):
        for row_support in combinations(range(row_count), size):
            for col_support in combinations(range(col_count), size):
                q_system = [
                    [matrix[i][j] for j in col_support] + [Fraction(-1)]
                    for i in row_support
                ] + [[Fraction(1)] * size + [Fraction(0)]]
                q_solution = _solve_square(q_system, [Fraction(0)] * size + [Fraction(1)])
                if q_solution is None:
                    continue
                q_inner, value = q_solution[:-1], q_solution[-1]
                if any(prob <= 0 for prob in q_inner):
                    continue

                p_system = [
                    [matrix[i][j] for i in row_support] + [Fraction(-1)]
                    for j in col_support
                ] + [[Fraction(1)] * size + [Fraction(0)]]
                p_solution = _solve_square(p_system, [Fraction(0)] * size + [Fraction(1)])
                if p_solution is None:
                    continue
                p_inner, p_value = p_solution[:-1], p_solution[-1]
                if p_value != value or any(prob <= 0 for prob in p_inner):
                    continue
                p = [Fraction(0)] * row_count
                q = [Fraction(0)] * col_count
                for index, probability in zip(row_support, p_inner):
                    p[index] = probability
                for index, probability in zip(col_support, q_inner):
                    q[index] = probability
                if sum(p, Fraction()) != 1 or sum(q, Fraction()) != 1:
                    continue
                # P0 maximizes, so no pure row exceeds value; P1 minimizes,
                # so no pure column pays less than value.
                if any(sum(matrix[i][j] * q[j] for j in range(col_count)) > value
                       for i in range(row_count)):
                    continue
                if any(sum(p[i] * matrix[i][j] for i in range(row_count)) < value
                       for j in range(col_count)):
                    continue
                if sum(p[i] * matrix[i][j] * q[j]
                       for i in range(row_count) for j in range(col_count)) != value:
                    continue
                return {
                    "row_probabilities": tuple(p),
                    "column_probabilities": tuple(q),
                    "value": value,
                    "row_support": row_support,
                    "column_support": col_support,
                    "search_method": "equal-cardinality exact support enumeration",
                }
    raise NoEquilibriumWitness(
        "No witness found by bounded equal-cardinality support enumeration")


def _canonical_hand(text):
    if not isinstance(text, str) or len(text) != 4:
        raise ValueError("Count hand must contain two card codes")
    cards = text[:2].title(), text[2:].title()
    if any(card[0] not in _RANKS or card[1] not in _SUITS for card in cards):
        raise ValueError("Count hand contains an invalid card")
    if cards[0] == cards[1]:
        raise ValueError("Count hand contains a duplicate card")
    return tuple(sorted(cards))


def equilibrium(sb_range, bb_range, config, counts, *, pair_subset=None,
                board_count=_BOARD_COUNT):
    """Return a certified equilibrium for reweighted explicit hands and W/T/L data.

    The bounded search is not a generic complete LP algorithm. It searches
    equal-cardinality supports of size at most min(rows, columns), and only
    returns a candidate after exact pure unilateral-response inequalities pass.
    """
    if type(board_count) is not int or board_count <= 0:
        raise ValueError("board_count must be a positive integer")
    ranges = _parse_range(sb_range), _parse_range(bb_range)
    subset = None
    if pair_subset is not None:
        subset = set()
        for pair in pair_subset:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError("pair_subset entries must be two hand strings")
            subset.add((_canonical_hand(pair[0]), _canonical_hand(pair[1])))
        if not subset:
            raise ValueError("pair_subset must not be empty")

    pair_weights = {}
    available_pairs = set()
    for sb_hand, sb_weight in ranges[0].items():
        for bb_hand, bb_weight in ranges[1].items():
            key = sb_hand, bb_hand
            if set(sb_hand).isdisjoint(bb_hand):
                available_pairs.add(key)
                joint_weight = sb_weight * bb_weight
                if joint_weight and (subset is None or key in subset):
                    pair_weights[key] = joint_weight
    if subset is not None and set(pair_weights) != subset:
        raise ValueError("pair_subset is not exactly compatible with supplied ranges")
    if not pair_weights:
        raise ValueError("No compatible private pairs remain")
    active_hands = tuple(tuple(sorted({pair[player] for pair in pair_weights}))
                         for player in (0, 1))
    hand_counts = tuple(map(len, active_hands))
    if max(hand_counts) > 3 or min(hand_counts) > 2:
        raise ValueError("Exact witness supports at most three active hands on one side and two on the other")

    counts_by_pair = {}
    for row in counts:
        try:
            key = (_canonical_hand(row["sb_hand"]), _canonical_hand(row["bb_hand"]))
            wins, ties, losses, boards = (
                row["wins"], row["ties"], row["losses"], row["boards"])
        except (KeyError, TypeError, IndexError) as exc:
            raise ValueError("Each count row needs hands, W/T/L and boards") from exc
        if key in counts_by_pair:
            raise ValueError("Duplicate W/T/L pair row")
        if key not in available_pairs:
            raise ValueError("W/T/L rows include a pair outside supplied ranges")
        if any(type(value) is not int or value < 0
               for value in (wins, ties, losses, boards)):
            raise ValueError("W/T/L and boards must be nonnegative integers")
        if boards != board_count or wins + ties + losses != board_count:
            raise ValueError("W/T/L row must cover the full declared board count")
        if key in pair_weights:
            counts_by_pair[key] = Fraction(wins - losses, boards)
    if set(counts_by_pair) != set(pair_weights):
        raise ValueError("Missing W/T/L data for a selected pair")

    normalizer = sum(pair_weights.values(), Fraction())
    priors = {pair: weight / normalizer for pair, weight in pair_weights.items()}
    sb_blind, bb_blind, matched_stack = _config_money(config)
    sb_hands, bb_hands = active_hands
    row_policies = tuple(product((0, 1), repeat=len(sb_hands)))
    column_policies = tuple(product((0, 1), repeat=len(bb_hands)))
    # The hand-count guard above guarantees at most a 4x8 or 8x4 matrix.
    # Keep this assertion immediately before allocation as a regression guard.
    policy_dimensions = len(row_policies), len(column_policies)
    if (min(policy_dimensions) > _MAX_POLICY_DIMENSIONS[0]
            or max(policy_dimensions) > _MAX_POLICY_DIMENSIONS[1]):
        raise ValueError("Exact witness policy matrix exceeds the bounded 4x8 limit")
    sb_index = {hand: index for index, hand in enumerate(sb_hands)}
    bb_index = {hand: index for index, hand in enumerate(bb_hands)}

    matrix = []
    for sb_policy in row_policies:
        row_payoffs = []
        for bb_policy in column_policies:
            payoff = Fraction()
            for (sb_hand, bb_hand), prior in priors.items():
                sb_action = sb_policy[sb_index[sb_hand]]
                bb_action = bb_policy[bb_index[bb_hand]]
                if sb_action == 0:
                    transfer = -sb_blind
                elif bb_action == 0:
                    transfer = bb_blind
                else:
                    transfer = matched_stack * counts_by_pair[(sb_hand, bb_hand)]
                payoff += prior * transfer
            row_payoffs.append(payoff)
        matrix.append(tuple(row_payoffs))

    witness = exact_zero_sum_witness(matrix)
    p, q, value = witness["row_probabilities"], witness["column_probabilities"], witness["value"]
    behavioral = {}
    for player, hands, policies, mixture in (
        (0, sb_hands, row_policies, p),
        (1, bb_hands, column_policies, q),
    ):
        for hand_index, hand in enumerate(hands):
            nonfold = sum((prob for policy, prob in zip(policies, mixture)
                           if policy[hand_index] == 1), Fraction())
            behavioral[player, "".join(hand)] = nonfold

    search_limit = {"row_policies": len(row_policies),
                    "column_policies": len(column_policies)}
    if max(hand_counts) <= 2:
        # Preserve the original metadata shape for all pre-extension 2x2 cases.
        search_limit["max_active_hands_per_player"] = 2
    else:
        search_limit["active_hands_by_player"] = list(hand_counts)
        search_limit["max_active_hands_on_larger_side"] = 3
        search_limit["max_active_hands_on_smaller_side"] = 2
        search_limit["max_support_candidates"] = _MAX_SUPPORT_CANDIDATES

    return {
        "value_sb_fraction": [value.numerator, value.denominator],
        "behavioral_probabilities": behavioral,
        "pure_policy_weights": {
            "sb": [
                {"policy": tuple("shove" if action else "fold" for action in policy),
                 "probability": [probability.numerator, probability.denominator]}
                for policy, probability in zip(row_policies, p) if probability
            ],
            "bb": [
                {"policy": tuple("call" if action else "fold" for action in policy),
                 "probability": [probability.numerator, probability.denominator]}
                for policy, probability in zip(column_policies, q) if probability
            ],
        },
        "pair_priors": {
            f"{''.join(a)}|{''.join(b)}": [prior.numerator, prior.denominator]
            for (a, b), prior in sorted(priors.items())
        },
        "pair_showdown_signs": {
            f"{''.join(a)}|{''.join(b)}": [sign.numerator, sign.denominator]
            for (a, b), sign in sorted(counts_by_pair.items())
        },
        "pure_policy_payoff_matrix": tuple(matrix),
        "search_method": witness["search_method"],
        "search_limit": search_limit,
    }

