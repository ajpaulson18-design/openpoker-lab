"""Exact bounded oracle for a PROOF9 target-board proposal.

The proposal first selects one compatible private pair with integer weights
3/8/18, then one of that pair's 20 legal public boards uniformly. The module
uses no RNG or native/production updater; board-conditioned estimates reuse the
independent sampled-grid operator and are checked against literal worlds.
"""
from dataclasses import dataclass
from fractions import Fraction
from math import lcm
from types import MappingProxyType

from scripts.matrix_free_certificate_budget import Budget
from tests.full_deck_public_chance_reference import PROOF9
from tests.virtual_dyadic_training_reference import D, Fixture, Q
from tests.virtual_frozen_sample_reference import admit_sampled_board
from tests.virtual_grid_update_reference import (
    freeze_grid, new_experiment_budget, raw_joint_update, sampled_grid_update,
    validate_grid,
)


TARGET_EXPERIMENTS = 2
BOARDS_PER_EXPERIMENT = 60
NATIVE_CALLS = 0
NORMALIZER = 29
BOARD_DENOMINATOR = 20 * NORMALIZER
PREFIX_C = MappingProxyType({0: 1, 3: 10, 4: 20, 5: 20})
RAW_DENOMINATOR = 72 << 625
AVERAGE_DENOMINATOR = 14_616 << 364
LITERAL_RAW_DENOMINATOR = D
LITERAL_AVERAGE_DENOMINATOR = 580 << 364
Q_UNIFORM_BOARD = Fraction(1, 2520)
SECOND_MOMENT_RATIO_BOUND = Fraction(29, 378)
_BUDGET_LIMITS = {
    "work": 500_000_000,
    "entries": 8_000_000,
    "integer_bits": 4096,
    "created_bits": 16_000_000_000,
}


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _pair_integer_weights(context):
    _need(context.normalizer == Fraction(29, 64), "target law requires pinned Z=29/64 ranges")
    pairs = []
    for i, (hand0, weight0) in enumerate(context.ranges[0]):
        for j, (hand1, weight1) in enumerate(context.ranges[1]):
            if set(hand0).isdisjoint(hand1):
                raw = weight0 * weight1 * 64
                _need(raw.denominator == 1 and raw.numerator > 0,
                      "compatible pair weight is not a positive integer unit")
                pairs.append((i, j, frozenset((*hand0, *hand1)), raw.numerator))
    _need(tuple(sorted(item[3] for item in pairs)) == (3, 8, 18) and
          sum(item[3] for item in pairs) == NORMALIZER and len(pairs) == 3,
          "compatible integer prior pairs must be exactly 3/8/18, total 29")
    return tuple(pairs)


@dataclass(frozen=True)
class TargetBoardLaw:
    board_masses: object
    board_probabilities: object
    prefix_masses: object
    prefix_probabilities: object
    positive_boards: tuple
    mass_counts: object
    prefix_mass_counts: object
    second_moment_ratio_bound: Fraction
    _context_seal: object
    _origin: object

    def receipt(self):
        return {
            "proposal": "compatible integer pair by 3/8/18, then uniform over its 20 boards",
            "normalizer_z_units": NORMALIZER,
            "boards": len(self.board_masses),
            "positive_boards": len(self.positive_boards),
            "board_mass_counts": dict(self.mass_counts),
            "positive_board_mass_lcm": lcm(*(mass for mass in self.mass_counts if mass > 0)),
            "prefix_mass_counts": {length: dict(counts)
                                    for length, counts in self.prefix_mass_counts.items()},
            "positive_prefix_counts": {length: sum(count for mass, count in counts.items()
                                                    if mass > 0)
                                       for length, counts in self.prefix_mass_counts.items()},
            "prefix_c": dict(PREFIX_C),
            "q_uniform_zero_target_fraction": Fraction(2460, 2520),
            "regret_second_moment_ratio_upper_bound": self.second_moment_ratio_bound,
            "rng_calls": 0,
            "native_calls": 0,
            "scope": "exact fixed PROOF9 proposal law; not a sampler or training claim",
        }


def build_target_board_law(context, budget: Budget) -> TargetBoardLaw:
    """Build q(B) and q(P), verifying marginals by separate integer support sums."""
    if not isinstance(budget, Budget):
        raise ValueError("an explicitly bounded experiment Budget is required")
    _need(len(context.physical.proposals) == 2520, "fixed PROOF9 proposal inventory changed")
    pairs = _pair_integer_weights(context)
    prefixes = context.physical.prefixes
    budget.charge("target_law_census_reserve", 2520 * 4096)
    budget.entries(2 * 2520 + sum(len(prefixes[length]) for length in (0, 3, 4, 5)),
                   "target law board and prefix maps")

    board_masses = {}
    board_probabilities = {}
    grouped_prefix = {length: {} for length in (0, 3, 4, 5)}
    mass_counts = {}
    positive = []
    for board in context.physical.proposals:
        blocked = frozenset(board)
        mass = sum(weight for _i, _j, cards, weight in pairs if not (cards & blocked))
        board_masses[board] = mass
        budget.charge("target_board_integer_mass", len(pairs))
        q_board = budget.div(budget.input(mass, "target board mass units"),
                             budget.input(BOARD_DENOMINATOR, "target board denominator"),
                             "target board proposal q")
        board_probabilities[board] = q_board
        mass_counts[mass] = mass_counts.get(mass, 0) + 1
        if mass:
            positive.append(board)
        for length in (0, 3, 4, 5):
            prefix = board[:length]
            existing = grouped_prefix[length].get(prefix, Fraction(0))
            grouped_prefix[length][prefix] = budget.add(existing, q_board,
                                                        "target grouped prefix q")

    expected_prefix_masses = {}
    expected_prefix_q = {}
    prefix_mass_counts = {}
    for length in (0, 3, 4, 5):
        expected_prefix_masses[length] = {}
        expected_prefix_q[length] = {}
        prefix_mass_counts[length] = {}
        for prefix in prefixes[length]:
            blocked = frozenset(prefix)
            mass = sum(weight for _i, _j, cards, weight in pairs if not (cards & blocked))
            q_formula = budget.div(budget.input(mass, "target prefix mass units"),
                                   budget.input(NORMALIZER * PREFIX_C[length],
                                                "target prefix denominator"),
                                   "target prefix formula q")
            q_grouped = grouped_prefix[length].get(prefix, Fraction(0))
            _need(q_grouped == q_formula,
                  "grouped full-board q does not match independent prefix mass/c formula")
            expected_prefix_masses[length][prefix] = mass
            expected_prefix_q[length][prefix] = q_formula
            prefix_mass_counts[length][mass] = prefix_mass_counts[length].get(mass, 0) + 1
        _need(sum(expected_prefix_q[length].values(), Fraction(0)) == 1,
              "target proposal prefix marginal does not normalize")

    _need(sum(board_probabilities.values(), Fraction(0)) == 1 and len(positive) == 60,
          "target board proposal must normalize over exactly 60 boards")
    _need(mass_counts == {0: 2460, 3: 20, 8: 20, 18: 20},
          "target full-board compatible mass census changed")
    _need(lcm(*(mass for mass in mass_counts if mass > 0)) == 72,
          "positive full-board mass denominator lcm changed")
    _need({length: sum(n for mass, n in counts.items() if mass > 0)
           for length, counts in prefix_mass_counts.items()} == {0: 1, 3: 25, 4: 56, 5: 60},
          "target positive visible-prefix support changed")
    _need(lcm(*(mass for counts in prefix_mass_counts.values()
                for mass in counts if mass > 0)) == 14_616,
          "positive target prefix mass denominator lcm changed")

    frozen_board_masses = MappingProxyType(board_masses)
    frozen_board_q = MappingProxyType(board_probabilities)
    frozen_prefix_masses = MappingProxyType({k: MappingProxyType(v)
                                             for k, v in expected_prefix_masses.items()})
    frozen_prefix_q = MappingProxyType({k: MappingProxyType(v)
                                        for k, v in expected_prefix_q.items()})
    frozen_mass_counts = MappingProxyType(mass_counts)
    frozen_prefix_counts = MappingProxyType({k: MappingProxyType(v)
                                             for k, v in prefix_mass_counts.items()})
    frozen_positive = tuple(positive)
    origin = (frozen_board_masses, frozen_board_q, frozen_prefix_masses,
              frozen_prefix_q, frozen_positive, frozen_mass_counts, frozen_prefix_counts)
    return TargetBoardLaw(frozen_board_masses, frozen_board_q, frozen_prefix_masses,
                          frozen_prefix_q, frozen_positive, frozen_mass_counts,
                          frozen_prefix_counts, SECOND_MOMENT_RATIO_BOUND,
                          context._seal, origin)


def validate_target_board_law(context, law):
    _need(type(law) is TargetBoardLaw, "target law must come from the exact proposal census")
    maps = (law.board_masses, law.board_probabilities, law.prefix_masses,
            law.prefix_probabilities, law.positive_boards,
            law.mass_counts, law.prefix_mass_counts)
    _need(len(law._origin) == len(maps) and all(a is b for a, b in zip(law._origin, maps)),
          "target proposal census maps were replaced")
    _need(law._context_seal is context._seal and context.normalizer == Fraction(29, 64) and
          len(law.positive_boards) == 60 and
          len(law.board_probabilities) == 2520,
          "target proposal census identity or geometry changed")
    return True


def new_target_budget(context):
    """Create one explicit bounded budget for one profile's 60-board oracle."""
    return new_experiment_budget(context, dict(_BUDGET_LIMITS))


def target_board_update(context, law, board, grid, budget: Budget):
    """Apply target-law weights to one uniform operator result; zero q rejects first."""
    validate_grid(grid)
    validate_target_board_law(context, law)
    if type(board) is not tuple or board not in law.board_probabilities:
        raise ValueError("board is outside the target proposal inventory")
    q_target = law.board_probabilities[board]
    if q_target <= 0:
        raise ValueError("target proposal has no support for this complete board")
    admission = admit_sampled_board(context, board, "uniform")
    budget.entries(8 * admission.row_count_upper + 8 * admission.action_slots_upper,
                   "target rescaled one-board rows")
    q_uniform = admission.board_probability
    board_scale = budget.div(budget.input(q_uniform, "uniform board proposal"),
                             budget.input(q_target, "target board proposal"),
                             "target board importance ratio")
    budget.charge("target_board_operator_calls", 1)
    uniform_rows, uniform_root = sampled_grid_update(context, admission, grid, budget)
    target_root = budget.mul(uniform_root, board_scale, "target root rescale")
    prefix_scales = {}
    target_rows = {}
    max_regret_bits = 0
    max_average_bits = 0
    for key, (raw, averages) in uniform_rows.items():
        prefix = grid.prefixes[key]
        if board[:len(prefix)] != prefix:
            raise ValueError("sampled row visible prefix does not match selected board")
        q_target_prefix = law.prefix_probabilities[len(prefix)][prefix]
        if q_target_prefix <= 0:
            raise ValueError("sampled average row has no target-prefix proposal support")
        prefix_scale = prefix_scales.get(prefix)
        if prefix_scale is None:
            prefix_scale = budget.div(
                budget.input(context.physical.proposal_laws["uniform"]["prefix"][prefix],
                             "uniform prefix proposal"),
                budget.input(q_target_prefix, "target prefix proposal"),
                "target prefix importance ratio")
            prefix_scales[prefix] = prefix_scale
        target_raw = tuple(budget.mul(value, board_scale, "target raw regret rescale")
                           for value in raw)
        target_avg = tuple(budget.mul(value, prefix_scale, "target average rescale")
                           for value in averages)
        _need(len(target_raw) == len(target_avg) == len(grid.units[key]),
              "target board row/menu width changed")
        for value in target_raw:
            scaled = budget.mul(value, budget.input(RAW_DENOMINATOR, "target regret common denominator"),
                                "target regret integer representation")
            _need(scaled.denominator == 1,
                  "target sample regret is not on the fixed 72*2^625 denominator")
            max_regret_bits = max(max_regret_bits, abs(scaled.numerator).bit_length())
        for value in target_avg:
            scaled = budget.mul(value, budget.input(AVERAGE_DENOMINATOR, "target average common denominator"),
                                "target average integer representation")
            _need(scaled.denominator == 1,
                  "target sample average is not on the fixed 14616*2^364 denominator")
            max_average_bits = max(max_average_bits, abs(scaled.numerator).bit_length())
        units = grid.units[key]
        regret_dot = Fraction(0)
        for value, unit in zip(target_raw, units):
            regret_dot = budget.add(regret_dot,
                budget.mul(value, budget.input(unit, "Q52 policy unit"), "target regret center product"),
                "target regret center sum")
        _need(regret_dot == 0,
              "target raw regret row is not centered on its frozen Q52 policy")
        avg_mass = Fraction(0)
        for value in target_avg:
            avg_mass = budget.add(avg_mass, value, "target average row sum")
        for value, unit in zip(target_avg, units):
            left = budget.mul(value, budget.input(Q, "Q52 average scale"), "target average policy scale")
            right = budget.mul(avg_mass, budget.input(unit, "Q52 policy unit"),
                               "target average policy product")
            _need(left == right,
              "target prefix average row does not follow its frozen Q52 policy")
        target_rows[key] = (target_raw, target_avg)
    return {
        "board": board,
        "q_target": q_target,
        "root": target_root,
        "rows": MappingProxyType(target_rows),
        "uniform_rows": uniform_rows,
        "uniform_root": uniform_root,
        "max_regret_integer_bits": max_regret_bits,
        "max_average_integer_bits": max_average_bits,
    }


def target_board_expectation(fixture: Fixture, context, law, grid, budget: Budget):
    """Sum all 60 target-board estimates and verify their exact score moments."""
    validate_grid(grid)
    validate_target_board_law(context, law)
    # Only complete R/A accumulators are row-shaped. Second moments are
    # checked and reduced pointwise into two scalars, so there are no second
    # full per-row moment tables hidden outside this reservation.
    budget.entries(16 * 58_164 + 16 * 24_420,
                   "target complete R/A row and slot accumulators")
    regrets = {key: [Fraction(0)] * len(menu) for key, menu in grid.menus.items()}
    averages = {key: [Fraction(0)] * len(menu) for key, menu in grid.menus.items()}
    root = Fraction(0)
    max_regret_bits = max_average_bits = 0
    max_expected_regret_bits = max_expected_average_bits = 0
    max_pointwise_regret_second_moment_ratio = Fraction(0)
    total_target_regret_second_moment = Fraction(0)
    total_uniform_regret_second_moment = Fraction(0)

    for board in law.positive_boards:
        sample = target_board_update(context, law, board, grid, budget)
        q = sample["q_target"]
        root = budget.add(root, budget.mul(q, sample["root"], "target expected root"),
                          "target expected root sum")
        for key, (target_raw, target_avg) in sample["rows"].items():
            uniform_raw, uniform_avg = sample["uniform_rows"][key]
            for index, (raw, average) in enumerate(zip(target_raw, target_avg)):
                regrets[key][index] = budget.add(
                    regrets[key][index], budget.mul(q, raw, "target expected regret"),
                    "target expected regret sum")
                averages[key][index] = budget.add(
                    averages[key][index], budget.mul(q, average, "target expected average"),
                    "target expected average sum")
                target_point = budget.mul(q, budget.mul(raw, raw,
                    "target regret square"), "target regret pointwise second moment")
                uniform_square = budget.mul(uniform_raw[index], uniform_raw[index],
                                            "uniform regret square")
                uniform_point = budget.mul(Q_UNIFORM_BOARD, uniform_square,
                                           "uniform regret pointwise second moment")
                if uniform_point:
                    ratio = budget.div(target_point, uniform_point,
                                       "pointwise target/uniform regret second moment ratio")
                    comparison = budget.compare(ratio, SECOND_MOMENT_RATIO_BOUND,
                                                "pointwise regret second moment bound")
                    _need(comparison <= 0,
                          "target pointwise regret second moment exceeded 29/378")
                    if budget.compare(ratio, max_pointwise_regret_second_moment_ratio,
                                      "pointwise moment maximum") > 0:
                        max_pointwise_regret_second_moment_ratio = ratio
                else:
                    _need(target_point == 0,
                          "target regret has positive pointwise moment where uniform is zero")
                total_target_regret_second_moment = budget.add(
                    total_target_regret_second_moment, target_point,
                    "total target regret second moment")
                total_uniform_regret_second_moment = budget.add(
                    total_uniform_regret_second_moment, uniform_point,
                    "total uniform regret second moment")
            max_regret_bits = max(max_regret_bits, sample["max_regret_integer_bits"])
            max_average_bits = max(max_average_bits, sample["max_average_integer_bits"])

    _need(len(law.positive_boards) == BOARDS_PER_EXPERIMENT,
          "target experiment board-call count changed")
    expected_r, expected_a, expected_root = raw_joint_update(fixture, grid)
    _need(root == expected_root, "target expected root differs from literal-world expectation")
    for key, menu in grid.menus.items():
        _need(tuple(regrets[key]) == expected_r[key], "target expected signed R differs from literal oracle")
        _need(tuple(averages[key]) == expected_a[key], "target expected A differs from literal oracle")
        _need(len(regrets[key]) == len(averages[key]) == len(menu),
              "target complete output row/menu mismatch")
        for value in regrets[key]:
            scaled = budget.mul(value, budget.input(LITERAL_RAW_DENOMINATOR,
                "literal expectation raw denominator"), "literal expectation raw integer")
            _need(scaled.denominator == 1,
                  "literal whole-game regret escaped its existing 580*2^625 denominator")
            max_expected_regret_bits = max(max_expected_regret_bits,
                                           abs(scaled.numerator).bit_length())
        for value in averages[key]:
            scaled = budget.mul(value, budget.input(LITERAL_AVERAGE_DENOMINATOR,
                "literal expectation average denominator"), "literal expectation average integer")
            _need(scaled.denominator == 1,
                  "literal whole-game average escaped its existing 580*2^364 denominator")
            max_expected_average_bits = max(max_expected_average_bits,
                                            abs(scaled.numerator).bit_length())

    _need(total_uniform_regret_second_moment > 0,
          "uniform regret second moment is empty for the fixed fixture")
    aggregate_second_moment_ratio = budget.div(
        total_target_regret_second_moment, total_uniform_regret_second_moment,
        "aggregate target/uniform regret second moment ratio")
    _need(budget.compare(aggregate_second_moment_ratio, SECOND_MOMENT_RATIO_BOUND,
                         "aggregate regret second moment bound") <= 0,
          "aggregate target regret second moment exceeded its exact proposal bound")
    return {
        "regrets": MappingProxyType({key: tuple(value) for key, value in regrets.items()}),
        "averages": MappingProxyType({key: tuple(value) for key, value in averages.items()}),
        "root": root,
        "rows": len(regrets),
        "slots": sum(map(len, regrets.values())),
        "board_calls": len(law.positive_boards),
        "maximum_sample_regret_integer_bits": max_regret_bits,
        "maximum_sample_average_integer_bits": max_average_bits,
        "maximum_expected_regret_integer_bits": max_expected_regret_bits,
        "maximum_expected_average_integer_bits": max_expected_average_bits,
        "literal_expectation_match": True,
        "maximum_pointwise_regret_second_moment_ratio": max_pointwise_regret_second_moment_ratio,
        "aggregate_regret_second_moment_ratio": aggregate_second_moment_ratio,
        "second_moment_ratio_bound": SECOND_MOMENT_RATIO_BOUND,
        "resource_accounting": budget.receipt(),
        "native_calls": 0,
        "rng_calls": 0,
        "training_iterations": 0,
        "quality_gate": None,
        "scope": "exact two-sided expectation for one fixed PROOF9 Q52 profile; not stochastic training",
    }


def fixed_profile(fixture: Fixture, name: str):
    """Return the established uniform or deterministic zero-skew grid."""
    if name == "uniform":
        return fixture.grid()
    if name != "zero-skew":
        raise ValueError("target reference profile must be uniform or zero-skew")
    result = {}
    for index, (key, menu) in enumerate(sorted(fixture.menus.items())):
        size = len(menu)
        if index % 2 and size > 1:
            values = [0] * size
            values[index % size] = Q
        else:
            values = [1] * size
            values[index % size] = Q - size + 1
        result[key] = tuple(values)
    return result
