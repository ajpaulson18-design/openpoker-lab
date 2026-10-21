"""Draft controls for isolated public LCFR and alternating DCFR.

The abstract matrix and weighted-world controls are independent of legal
Hold'em game integration and finite-iteration equilibrium-quality evidence.
"""

from fractions import Fraction
import math
import unittest
from unittest.mock import patch

from pokerlab import alternating_public_cfr as lcfr_public
from pokerlab.river_tree import _Node, _Terminal


def _rm(regrets):
    positive = [max(Fraction(0), value) for value in regrets]
    total = sum(positive)
    if total:
        return [value / total for value in positive]
    return [Fraction(1, len(regrets))] * len(regrets)


def _float_rm(regrets):
    positive = [max(0.0, value) for value in regrets]
    total = sum(positive)
    return ([value / total for value in positive] if total else
            [1.0 / len(regrets)] * len(regrets))


def _matrix_lcfr(matrix, iterations):
    """Independent exact normal-form reference for alternating LCFR."""
    row_regrets = [Fraction(0), Fraction(0)]
    col_regrets = [Fraction(0), Fraction(0)]
    row_sums = [Fraction(0), Fraction(0)]
    col_sums = [Fraction(0), Fraction(0)]

    for t in range(1, iterations + 1):
        row = _rm(row_regrets)
        col = _rm(col_regrets)
        for action in range(2):
            row_sums[action] += t * row[action]
            col_sums[action] += t * col[action]

        row_values = [sum(matrix[i][j] * col[j] for j in range(2))
                      for i in range(2)]
        row_value = sum(row[i] * row_values[i] for i in range(2))
        row_regrets = [row_regrets[i] + t * (row_values[i] - row_value)
                       for i in range(2)]
        # The public trainer alternates updates within a sweep: rematch OOP
        # before computing IP's counterfactual values.
        row = _rm(row_regrets)

        col_values = [-sum(row[i] * matrix[i][j] for i in range(2))
                      for j in range(2)]
        col_value = sum(col[j] * col_values[j] for j in range(2))
        col_regrets = [col_regrets[j] + t * (col_values[j] - col_value)
                       for j in range(2)]

    return (
        [x / sum(row_sums) for x in row_sums],
        [x / sum(col_sums) for x in col_sums],
    )


def _literal_weighted_reference(root, worlds, infos, iterations, chance_type,
                                algorithm="lcfr"):
    """Per-physical-world reference; no production trainer helpers are called."""
    if algorithm not in ("lcfr", "dcfr-alternating"):
        raise ValueError("unknown reference algorithm")
    exact = algorithm == "lcfr"
    zero = Fraction(0) if exact else 0.0
    uniform = lambda count: ([Fraction(1, count)] * count if exact else
                             [1.0 / count] * count)
    regret_matching = _rm if exact else _float_rm
    regrets = {key: [zero] * count for key, count in infos.items()}
    sums = {key: [zero] * count for key, count in infos.items()}

    def select_world_branch(node, world):
        return node.branches[world[4]]

    for t in range(1, iterations + 1):
        current = {key: regret_matching(row) for key, row in regrets.items()}
        average_weight = t if exact else t * t

        # Literal own-reach average, enumerating each weighted world separately.
        def average_walk(node, world, reach):
            if isinstance(node, chance_type):
                average_walk(select_world_branch(node, world), world, reach)
                return
            if isinstance(node, _Terminal):
                return
            player = node.player
            key = (player, world[player], node.history)
            sigma = current.get(key, uniform(len(node.actions)))
            if key in sums:
                for action, probability in enumerate(sigma):
                    sums[key][action] += (world[2] * reach[player] * probability *
                                          average_weight)
            for action, child in enumerate(node.children):
                next_reach = list(reach)
                next_reach[player] *= sigma[action]
                average_walk(child, world, next_reach)

        for world in worlds:
            average_walk(root, world, [Fraction(1), Fraction(1)])

        for target in (0, 1):
            deltas = {key: [zero] * count for key, count in infos.items()
                      if key[0] == target}

            def counterfactual_walk(node, world, opponent_reach):
                if isinstance(node, chance_type):
                    return counterfactual_walk(select_world_branch(node, world),
                                               world, opponent_reach)
                if isinstance(node, _Terminal):
                    matched = (min(map(Fraction, node.contributions)) if exact else
                               min(map(float, node.contributions)))
                    if node.kind == "fold":
                        payoff0 = (1 if node.winner == 0 else -1) * (1 + matched)
                    else:
                        sign = world[3] if exact else float(world[3])
                        payoff0 = sign * (1 + matched)
                    return payoff0 if target == 0 else -payoff0

                player = node.player
                key = (player, world[player], node.history)
                sigma = current.get(key, uniform(len(node.actions)))
                if player == target:
                    action_values = [counterfactual_walk(child, world, opponent_reach)
                                     for child in node.children]
                    expected = sum(sigma[a] * action_values[a]
                                   for a in range(len(action_values)))
                    if key in deltas:
                        for action, value in enumerate(action_values):
                            deltas[key][action] += world[2] * opponent_reach * (value - expected)
                    return expected

                value = zero
                for action, child in enumerate(node.children):
                    value += sigma[action] * counterfactual_walk(
                        child, world, opponent_reach * sigma[action])
                return value

            for world in worlds:
                counterfactual_walk(root, world, Fraction(1) if exact else 1.0)
            for key in deltas:
                if exact:
                    regrets[key] = [old + t * delta
                                    for old, delta in zip(regrets[key], deltas[key])]
                else:
                    positive_discount = t ** 1.5 / (t ** 1.5 + 1.0)
                    raw = [old + delta for old, delta in
                           zip(regrets[key], deltas[key])]
                    regrets[key] = [value * (positive_discount if value > 0 else 0.5)
                                    for value in raw]
                current[key] = regret_matching(regrets[key])

    profile = {}
    for key, row in sums.items():
        total = sum(row)
        profile[key] = ([value / total for value in row] if total else
                        uniform(len(row)))
    return profile, sums


def _literal_world_profile_value(node, world, profile, chance_type):
    """Independent expected OOP utility for one physical world."""
    if isinstance(node, chance_type):
        return _literal_world_profile_value(
            node.branches[world[4]], world, profile, chance_type)
    if isinstance(node, _Terminal):
        matched = min(map(Fraction, node.contributions))
        if node.kind == "fold":
            return Fraction(1 if node.winner == 0 else -1) * (1 + matched)
        return Fraction(world[3]) * (1 + matched)
    key = (node.player, world[node.player], node.history)
    sigma = profile.get(key, [Fraction(1, len(node.actions))] * len(node.actions))
    return sum(sigma[action] * _literal_world_profile_value(
        child, world, profile, chance_type)
        for action, child in enumerate(node.children))


class LinearCFRControlTests(unittest.TestCase):
    def test_exact_three_sweep_unfloored_reference(self):
        row, col = _matrix_lcfr(
            [[Fraction(1), Fraction(-1)],
             [Fraction(0), Fraction(2)]],
            3,
        )
        self.assertEqual(row, [Fraction(11, 24), Fraction(13, 24)])
        self.assertEqual(col, [Fraction(2, 3), Fraction(1, 3)])

    def test_alternating_dcfr_controls_and_fourth_sweep_alpha(self):
        matrix = [[1.0, -1.0], [0.0, 2.0]]

        def run_matrix(iterations):
            class Chance:
                pass

            cells = (
                _Terminal("fold", (0.0, 0.0), winner=0),
                _Terminal("fold", (0.0, 0.0), winner=1),
                _Terminal("showdown", (0.0, 0.0)),
                _Terminal("fold", (1.0, 1.0), winner=0),
            )
            left = _Node((), 1, (object(), object()), cells[:2])
            right = _Node((), 1, (object(), object()), cells[2:])
            root = _Node((), 0, (object(), object()), (left, right))
            profile = lcfr_public.train_public_alternating_dcfr(
                root, [(0, 0, 1.0, 0.0)],
                {(0, 0, ()): 2, (1, 0, ()): 2}, iterations,
                pot=2.0, chance_type=Chance,
            )
            return profile[(0, 0, ())], profile[(1, 0, ())]

        row3, col3 = run_matrix(3)
        for actual, expected in zip(row3, (29 / 56, 27 / 56)):
            self.assertAlmostEqual(actual, expected, places=14)
        for actual, expected in zip(col3, (9 / 14, 5 / 14)):
            self.assertAlmostEqual(actual, expected, places=14)

        # An independent closed-form fourth-sweep control catches the
        # positive-regret discount exponent alpha=3/2. The first two sweeps
        # lead to the stated mixed OOP row; the third sweep's common positive
        # discount cancels in regret matching.
        a = 2 * math.sqrt(2) / (2 * math.sqrt(2) + 1)
        q = (3 * a - 1) / (4 * a + 2)
        row4, col4 = run_matrix(4)
        self.assertAlmostEqual(row4[0], (29 / 4 + 16 * q) / 30, places=13)
        self.assertAlmostEqual(row4[1], 1 - row4[0], places=13)
        self.assertAlmostEqual(col4[0], 5 / 6, places=13)
        self.assertAlmostEqual(col4[1], 1 / 6, places=13)

    def test_pre_sweep_weighting_control(self):
        # At the third sweep, ordinary regret matching on [1, -1] is [1, 0].
        # The first three pre-sweep profiles therefore average to [11/12,1/12].
        policies = [
            [Fraction(1, 2), Fraction(1, 2)],
            [Fraction(1), Fraction(0)],
            [Fraction(1), Fraction(0)],
        ]
        mass = sum(range(1, 4))
        average = [
            sum(Fraction(t) * policy[a]
                for t, policy in enumerate(policies, 1)) / mass
            for a in range(2)
        ]
        self.assertEqual(average, [Fraction(11, 12), Fraction(1, 12)])

    def test_public_loop_matches_exact_reference_with_scripted_deltas(self):
        # The low-level traversal is replaced with the independently derived
        # matrix counterfactual values. This checks LCFR's update ordering,
        # linear regret weights, and averaging schedule without treating the
        # production traversal as its own mathematical oracle.
        key0 = (0, 0, ())
        key1 = (1, 0, ())
        infos = {key0: 2, key1: 2}
        matrix = [[1.0, -1.0], [0.0, 2.0]]
        expected_row, expected_col = _matrix_lcfr(
            [[Fraction(1), Fraction(-1)],
             [Fraction(0), Fraction(2)]],
            3,
        )

        def scripted_deltas(_root, _edges, _infos, current, player,
                            _hand_counts, _half_pot, _chance_type,
                            terminal_kernel=None, prefix_kernel=None):
            self.assertIsNone(terminal_kernel)
            self.assertIsNone(prefix_kernel)
            row = current[key0]
            col = current[key1]
            if player == 0:
                values = [sum(matrix[a][b] * col[b] for b in range(2))
                          for a in range(2)]
                expected = sum(row[a] * values[a] for a in range(2))
                return {key0: [value - expected for value in values]}
            values = [-sum(row[a] * matrix[a][b] for a in range(2))
                      for b in range(2)]
            expected = sum(col[b] * values[b] for b in range(2))
            return {key1: [value - expected for value in values]}

        # Supply one fixed unit-mass world and a trivial tree. Patched delta
        # generation means no production tree/payoff traversal is involved.
        class Chance:
            pass

        leaves = (_Terminal("fold", (0.0, 0.0), winner=0),
                  _Terminal("fold", (0.0, 0.0), winner=1))
        hidden_response = _Node((), 1, (object(), object()), leaves)
        root = _Node((), 0, (object(), object()),
                     (hidden_response, hidden_response))
        worlds = [(0, 0, 1.0, 0.0)]
        with patch.object(lcfr_public, "_cfrplus_target_deltas", scripted_deltas):
            actual = lcfr_public.train_public_lcfr(
                root, worlds, infos, 3, pot=2.0, chance_type=Chance,
            )
        self.assertAlmostEqual(actual[key0][0], float(expected_row[0]), places=14)
        self.assertAlmostEqual(actual[key0][1], float(expected_row[1]), places=14)
        self.assertAlmostEqual(actual[key1][0], float(expected_col[0]), places=14)
        self.assertAlmostEqual(actual[key1][1], float(expected_col[1]), places=14)

    def test_unpatched_target_traversal_matches_matrix_control(self):
        # This abstract matrix game is represented by actual terminal nodes:
        # fold/showdown utilities at pot=2 yield [[1,-1],[0,2]]. Two distinct
        # responder nodes share one information set, hiding OOP's first move.
        class Chance:
            pass

        cells = (
            _Terminal("fold", (0.0, 0.0), winner=0),
            _Terminal("fold", (0.0, 0.0), winner=1),
            _Terminal("showdown", (0.0, 0.0)),
            _Terminal("fold", (1.0, 1.0), winner=0),
        )
        response0 = _Node((), 1, (object(), object()), cells[:2])
        response1 = _Node((), 1, (object(), object()), cells[2:])
        root = _Node((), 0, (object(), object()), (response0, response1))
        infos = {(0, 0, ()): 2, (1, 0, ()): 2}
        actual = lcfr_public.train_public_lcfr(
            root, [(0, 0, 1.0, 0.0)], infos, 3,
            pot=2.0, chance_type=Chance,
        )
        expected = _matrix_lcfr(
            [[Fraction(1), Fraction(-1)],
             [Fraction(0), Fraction(2)]], 3,
        )
        self.assertAlmostEqual(actual[(0, 0, ())][0], float(expected[0][0]), places=14)
        self.assertAlmostEqual(actual[(0, 0, ())][1], float(expected[0][1]), places=14)
        self.assertAlmostEqual(actual[(1, 0, ())][0], float(expected[1][0]), places=14)
        self.assertAlmostEqual(actual[(1, 0, ())][1], float(expected[1][1]), places=14)

        # An independently enumerated nonuniform responder policy must be
        # probability-weighted, not summed unweighted across its branches.
        mixed = {
            (0, 0, ()): [Fraction(1, 2), Fraction(1, 2)],
            (1, 0, ()): [Fraction(1, 4), Fraction(3, 4)],
        }
        self.assertEqual(
            _literal_world_profile_value(root, (0, 0, Fraction(1), Fraction(0)),
                                         mixed, Chance),
            Fraction(1, 2),
        )

    def test_chance_weighted_own_reach_average_against_literal_world_walk(self):
        class Chance:
            def __init__(self, branches):
                self.branches = branches

        leaf = _Terminal("fold", (0.0, 0.0), winner=0)

        def decision(player, history, children):
            return _Node(history, player, (object(), object()), children)

        a_deep = decision(0, ("A", "next"), (leaf, leaf))
        b_deep = decision(0, ("B", "next"), (leaf, leaf))
        a_root = decision(0, ("A",), (a_deep, leaf))
        b_root = decision(0, ("B",), (b_deep, leaf))
        root = Chance({"A": a_root, "B": b_root})
        worlds = [
            (0, 0, 0.25, 0.0, "A"),
            (1, 0, 0.75, 0.0, "B"),
        ]
        infos = {
            (0, 0, ("A",)): 2,
            (0, 0, ("A", "next")): 2,
            (0, 1, ("B",)): 2,
            (0, 1, ("B", "next")): 2,
        }
        current = {
            (0, 0, ("A",)): [0.25, 0.75],
            (0, 0, ("A", "next")): [0.6, 0.4],
            (0, 1, ("B",)): [0.4, 0.6],
            (0, 1, ("B", "next")): [0.2, 0.8],
        }
        hand_counts = (2, 1)
        # Independently sum raw joint-world mass times this hand's own
        # probability of the public history and current action.
        literal = {key: [0.0, 0.0] for key in infos}

        def visit_world(node, world, own_reach):
            if isinstance(node, Chance):
                visit_world(node.branches[world[4]], world, own_reach)
                return
            if isinstance(node, _Terminal):
                return
            key = (node.player, world[node.player], node.history)
            sigma = current.get(key, [0.5, 0.5])
            if key in literal:
                for action in range(2):
                    literal[key][action] += world[2] * own_reach * 2 * sigma[action]
            for action, child in enumerate(node.children):
                visit_world(child, world, own_reach * sigma[action])

        for world in worlds:
            visit_world(root, world, 1.0)

        sums = {key: [0.0, 0.0] for key in infos}
        marginals = {}
        for world in worlds:
            future = world[4:]
            for length in range(len(future) + 1):
                prefix = future[:length]
                if prefix not in marginals:
                    marginals[prefix] = ([0.0] * hand_counts[0],
                                         [0.0] * hand_counts[1])
                marginals[prefix][0][world[0]] += world[2]
                marginals[prefix][1][world[1]] += world[2]
        lcfr_public._weighted_average_sweep(
            root, current, sums, infos, hand_counts, marginals, 2.0, Chance,
        )
        self.assertEqual(sums, literal)

    def test_weighted_multiplayer_traversal_matches_independent_world_reference(self):
        class Chance:
            def __init__(self, branches):
                self.branches = branches

        cards = ("A", "B", "C")
        exact_worlds = [
            (0, 0, Fraction(1, 7), Fraction(1), "A"),
            (2, 0, Fraction(2, 7), Fraction(-1), "B"),
            (0, 2, Fraction(4, 7), Fraction(0), "C"),
        ]
        worlds = [(i, j, float(mass), float(sign), card)
                  for i, j, mass, sign, card in exact_worlds]
        root_branches = {}
        infos = {}
        branches = (
                ("A", 0, 0, Fraction(1, 7), Fraction(1), "A"),
                ("B", 2, 0, Fraction(2, 7), Fraction(-1), "B"),
                ("C", 0, 2, Fraction(4, 7), Fraction(0), "C"))
        for branch_index, (card, oop_hand, ip_hand, _mass, _sign, _token) in enumerate(branches):
            first_history = (card, "oop-first")
            infos[(0, oop_hand, first_history)] = 2
            if card == "A":
                # A legal-shaped but unsupported private row tests the dense
                # index hole: it must remain an explicit uniform fallback.
                infos[(0, 1, first_history)] = 2
            first_children = []
            for oop_action in range(2):
                ip_history = (card, "ip-response", f"oop{oop_action}")
                infos[(1, ip_hand, ip_history)] = 2
                ip_children = []
                for ip_action in range(2):
                    second_history = (
                        card, "oop-second", f"oop{oop_action}", f"ip{ip_action}")
                    infos[(0, oop_hand, second_history)] = 2
                    # Abstract finite zero-sum terminal utilities vary across
                    # actions. OOP's first action affects the outcome mix so
                    # exact zero regrets do not hinge on float cancellation.
                    second_children = []
                    for last_action in range(2):
                        code = (branch_index + 2 * oop_action +
                                ip_action + last_action) % 4
                        if code == 0:
                            terminal = _Terminal("fold", (0.0, 0.0), winner=0)
                        elif code == 1:
                            terminal = _Terminal("fold", (1.0, 1.0), winner=1)
                        elif code == 2:
                            terminal = _Terminal("showdown", (0.0, 0.0))
                        else:
                            terminal = _Terminal("fold", (0.5, 0.5), winner=0)
                        second_children.append(terminal)
                    ip_children.append(_Node(
                        second_history, 0, (object(), object()), tuple(second_children)))
                first_children.append(_Node(
                    ip_history, 1, (object(), object()), tuple(ip_children)))
            root_branches[card] = _Node(
                first_history, 0, (object(), object()), tuple(first_children))
        root = Chance(root_branches)

        # Six weighted sweeps exercise repeated positive and nonpositive
        # discounting, while the matrix control above isolates alpha=3/2.
        for algorithm, iterations in (("lcfr", 3), ("dcfr-alternating", 6)):
            expected, exact_sums = _literal_weighted_reference(
                root, exact_worlds, infos, iterations, Chance, algorithm,
            )
            if algorithm == "lcfr":
                actual = lcfr_public.train_public_lcfr(
                    root, worlds, infos, iterations, pot=2.0, chance_type=Chance,
                )
            else:
                actual = lcfr_public.train_public_alternating_dcfr(
                    root, worlds, infos, iterations, pot=2.0, chance_type=Chance,
                )
            for key, row in expected.items():
                self.assertAlmostEqual(actual[key][0], float(row[0]), places=12,
                                       msg=f"{algorithm} {key}")
                self.assertAlmostEqual(actual[key][1], float(row[1]), places=12,
                                       msg=f"{algorithm} {key}")
            self.assertEqual(expected[(0, 1, ("A", "oop-first"))],
                             ([Fraction(1, 2), Fraction(1, 2)] if algorithm == "lcfr"
                              else [0.5, 0.5]))
            self.assertEqual(exact_sums[(0, 1, ("A", "oop-first"))],
                             ([Fraction(0), Fraction(0)] if algorithm == "lcfr"
                              else [0.0, 0.0]))

    def test_zero_marginal_row_uses_uniform_fallback(self):
        # The production input validator admits sparse private-hand indices;
        # an infoset with no world mass remains legal and receives a uniform
        # average if no own-reach mass ever reaches it.
        key = (0, 1, ())
        key0 = (0, 0, ())
        self.assertEqual(_rm([Fraction(-3), Fraction(-1)]),
                         [Fraction(1, 2), Fraction(1, 2)])
        class Decision:
            history = ()
            player = 0
            actions = (object(), object())
            children = (_Terminal("fold", (0.0, 0.0), winner=0),
                        _Terminal("fold", (0.0, 0.0), winner=1))

        class Chance:
            pass

        infos = {key0: 2, key: 2}
        worlds = [(0, 0, 1.0, 0.0)]

        def zero_delta(_root, _edges, _infos, _current, player,
                       _hand_counts, _half_pot, _chance_type):
            return ({key: [0.0, 0.0] for key in infos if key[0] == 0} if player == 0 else
                    {key: [0.0, 0.0] for key in infos if key[0] == 1})

        with patch.object(
                lcfr_public, "_cfrplus_target_deltas", zero_delta):
            actual = lcfr_public.train_public_lcfr(
                Decision(), worlds, infos, 2, pot=2.0, chance_type=Chance,
            )
        self.assertEqual(actual[key], [0.5, 0.5])


if __name__ == "__main__":
    unittest.main()
