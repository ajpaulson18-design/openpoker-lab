"""Bounded independent controls for the generic matrix-free TURN tail.

Only T=10, D=3 is trained. Materialized and matrix-free profiles are checked
through the independent physical-world rules replay, then exact scan/partition
replay under the existing rational caps when admitted. This is not a convergence
or target-quality claim.
"""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
import math
import unittest

from pokerlab import matrix_free_turn_tail
from pokerlab import turn_tail_adapter
from scripts import turn_rational_certificate as exact
from scripts import turn_river_validation as rules


BOARD = ("Js", "8d", "4c", "2c")
TURN_CONFIG = {
    "pot": 100.0,
    "effective_stack": [100.0, 55.0],
    "bet_sizes": [0.5],
    "raise_sizes": [0.5],
    "max_raises": 1,
    "include_all_in": False,
}
RIVER_CONFIG = {
    "pot": 100.0,
    "effective_stack": [100.0, 55.0],
    "bet_sizes": [0.25],
    "raise_sizes": [0.5],
    "max_raises": 0,
    "include_all_in": True,
}
ITERATIONS = 10
DISCARD = 3

# Tc9c can make a flush on 7c and a J-high straight on 7d. As is
# unavailable to OOP's AsKd hand, and the identical AhQh combo is blocked.
SELECTED_CASE = {
    "name": "selected-blockers-distinct-streets-short-stack",
    "oop": "AsKd:1,Tc9c:0.5,AhQh:0.75",
    "ip": "AhQh:0.8,7s6s:1",
    "runouts": ("As", "7c", "7d"),
}
# Full-deck case has 48 requested cards and 44 physically reachable rivers:
# the four private cards cannot also be public river cards.
FULL_DECK_CASE = {
    "name": "full-deck-unpaired-physical-worlds",
    "oop": "Tc9c:1",
    "ip": "AhQh:1",
    "runouts": None,
}
CASES = (SELECTED_CASE, FULL_DECK_CASE)
METRICS = (
    "value_oop", "value_ip", "oop_best_response_value",
    "ip_best_response_value", "oop_best_response_gain",
    "ip_best_response_gain", "nash_conv", "exploitability",
)
EXACT_WORK_CAP = 100_000
EXACT_DEPTH_CAP = 64
EXACT_BITS_CAP = 65_536
TOL = 1e-9


EXACT_CAP_MESSAGES = {
    "Exact rational certificate exceeds its work limit",
    "Exact rational certificate exceeds its depth limit",
    "Exact rational certificate exceeds its node limit",
}


def _is_exact_capacity_error(message):
    if message in EXACT_CAP_MESSAGES:
        return True
    prefix = "Exact rational certificate exceeds the "
    suffix = "-bit limit"
    if message.startswith(prefix) and message.endswith(suffix):
        return message[len(prefix):-len(suffix)].isdecimal()
    return False


def _expand_world_model(case):
    board = rules.cards(BOARD)
    config = rules._config(TURN_CONFIG, "config")
    river_config = rules._config(RIVER_CONFIG, "river_config")
    ranges = (
        rules.expand_range(case["oop"], board),
        rules.expand_range(case["ip"], board),
    )
    worlds, selected = rules._worlds(board, ranges, case["runouts"])
    root = rules._public_tree(board, config, river_config, selected, worlds)
    nodes = rules._collect_nodes(root)
    return board, config, river_config, ranges, worlds, selected, root, nodes


def _policy_and_replay(result, case, model):
    board, config, river_config, ranges, worlds, selected, root, nodes = model
    oracle = rules.replay_policy(
        result,
        case["oop"],
        case["ip"],
        board=board,
        config=TURN_CONFIG,
        river_config=RIVER_CONFIG,
        runouts=case["runouts"],
    )
    rules.compare_result(result, oracle, tolerance=TOL)
    policies = rules._validate_policy(
        result, root, nodes, worlds, board, selected,
        runouts_were_omitted=case["runouts"] is None,
    )
    return oracle, policies


def _all_tree_nodes(root):
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        if isinstance(node, rules._Chance):
            pending.extend(node.branches.values())
        elif isinstance(node, rules._Decision):
            pending.extend(node.children)


def _physical_marginals(worlds):
    """Return exact root, global river, and river-conditional hand masses."""
    total = sum((world["weight"] for world in worlds), Fraction(0))
    if total != 1:
        raise AssertionError("independent physical-world law is not normalized")
    root_mass = [defaultdict(Fraction), defaultdict(Fraction)]
    branch_mass = defaultdict(lambda: [defaultdict(Fraction), defaultdict(Fraction)])
    branch_totals = defaultdict(Fraction)
    for world in worlds:
        river = world["river"]
        for player in (0, 1):
            hand = "".join(world["hands"][player])
            root_mass[player][hand] += world["weight"]
            if river is not None:
                branch_mass[river][player][hand] += world["weight"]
        if river is not None:
            branch_totals[river] += world["weight"]
    root = tuple(dict(side) for side in root_mass)
    global_rivers = {river: tuple(dict(side) for side in sides)
                     for river, sides in branch_mass.items()}
    conditional = {}
    for river, sides in branch_mass.items():
        denominator = branch_totals[river]
        if denominator <= 0:
            raise AssertionError("physical river branch has no positive joint mass")
        conditional[river] = tuple(
            {hand: mass / denominator for hand, mass in side.items()}
            for side in sides
        )
    return root, global_rivers, conditional


def _normal_probabilities(probabilities):
    exact_row = [Fraction.from_float(float(value)) for value in probabilities]
    total = sum(exact_row, Fraction(0))
    if total <= 0:
        raise AssertionError("strategy row has no positive action mass")
    return tuple(value / total for value in exact_row)


def _own_realization(result, policies, model):
    """Traverse the independent public tree, multiplying only own actions."""
    _, _, _, ranges, worlds, _, root, _ = model
    hand_labels = (
        tuple("".join(hand) for hand in sorted(ranges[0])),
        tuple("".join(hand) for hand in sorted(ranges[1])),
    )
    root_reach = (
        {hand: Fraction(1) for hand in hand_labels[0]},
        {hand: Fraction(1) for hand in hand_labels[1]},
    )
    row_reach = {}

    def visit(node, reach):
        if isinstance(node, rules._Chance):
            for child in node.branches.values():
                visit(child, reach)
            return
        if isinstance(node, rules._Terminal):
            return
        if not isinstance(node, rules._Decision):
            raise AssertionError("independent tree has an unknown node")
        player = node.player
        row_keys = []
        for hand in hand_labels[player]:
            key = (player, hand, node.history)
            if key in policies:
                row_reach[key] = reach[player][hand]
                row_keys.append(key)
        for action_index, child in enumerate(node.children):
            next_side = dict(reach[player])
            for key in row_keys:
                probs = _normal_probabilities(policies[key])
                next_side[key[1]] *= probs[action_index]
            updated = list(reach)
            updated[player] = next_side
            visit(child, tuple(updated))

    visit(root, root_reach)
    return row_reach


def _joint_action_realizations(result, policies, row_reach, model):
    _, _, _, _, worlds, _, _, _ = model
    root_marginals, global_rivers, conditional_rivers = _physical_marginals(worlds)
    rows = {}
    for row in result["strategy"]:
        player = 0 if row["player"] == "oop" else 1
        hand = row["hand"]
        history = tuple(row["history"])
        key = (player, hand, history)
        prefix = tuple(token[len("river@"):] for token in history
                       if token.startswith("river@"))
        marginal = (root_marginals if not prefix else
                    global_rivers[prefix[0]])[player].get(hand, Fraction(0))
        probabilities = _normal_probabilities(
            [action["probability"] for action in row["actions"]])
        reach = row_reach[key]
        row_flows = []
        for action, probability in zip(row["actions"], probabilities):
            action_key = key + (action["history_key"],)
            flow = marginal * reach * probability
            rows[action_key] = flow
            row_flows.append(flow)
        if sum(row_flows, Fraction(0)) != marginal * reach:
            raise AssertionError("global own-hand realization flow is not conserved")
    return rows, root_marginals, global_rivers, conditional_rivers


def _compare_action_rows(left, right):
    left_rows = {
        (row["player"], row["hand"], tuple(row["history"])): row
        for row in left["strategy"]
    }
    right_rows = {
        (row["player"], row["hand"], tuple(row["history"])): row
        for row in right["strategy"]
    }
    if set(left_rows) != set(right_rows):
        raise AssertionError(
            f"information row mismatch: {len(set(left_rows) ^ set(right_rows))} rows")
    for key in left_rows:
        a, b = left_rows[key], right_rows[key]
        left_legal = [
            {k: v for k, v in action.items() if k != "probability"}
            for action in a["actions"]
        ]
        right_legal = [
            {k: v for k, v in action.items() if k != "probability"}
            for action in b["actions"]
        ]
        if (a["street"], a["board"], left_legal) != (
                b["street"], b["board"], right_legal):
            raise AssertionError(f"legal row/action identity differs at {key}")
        if len(a["actions"]) != len(b["actions"]):
            raise AssertionError(f"action count differs at {key}")
        for action_a, action_b in zip(a["actions"], b["actions"]):
            if abs(action_a["probability"] - action_b["probability"]) > TOL:
                raise AssertionError(
                    f"action probability differs at {key}/{action_a['history_key']}")


def _assert_close_metric_maps(test, left, right, label):
    for metric in METRICS:
        with test.subTest(label=label, metric=metric):
            test.assertTrue(math.isfinite(float(left[metric])))
            test.assertTrue(math.isfinite(float(right[metric])))
            test.assertLessEqual(abs(float(left[metric]) - float(right[metric])), TOL)


class MatrixFreeTurnTailIndependentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.completed = {}
        cls.exact_admission = {}

    def _run_case(self, case):
        if case["name"] in self.__class__.completed:
            return
        model = _expand_world_model(case)
        board, _, _, _, worlds, selected, _, nodes = model
        matrix_free = matrix_free_turn_tail.solve_matrix_free_turn_tail(
            BOARD, case["oop"], case["ip"], TURN_CONFIG,
            river_config=RIVER_CONFIG, runouts=case["runouts"],
            iterations=ITERATIONS, discard=DISCARD,
        )
        materialized = turn_tail_adapter.solve_turn_tail(
            BOARD, case["oop"], case["ip"], TURN_CONFIG,
            river_config=RIVER_CONFIG, runouts=case["runouts"],
            iterations=ITERATIONS, discard=DISCARD,
        )
        self.assertEqual(matrix_free["worlds_materialized"], 0)
        self.assertEqual(matrix_free["iterations"], ITERATIONS)
        self.assertEqual(matrix_free["discard"], DISCARD)
        self.assertEqual(matrix_free["average_weight_sum"], 49)
        self.assertEqual(materialized["worlds_materialized"], len(worlds))
        self.assertEqual(matrix_free["runouts"], materialized["runouts"])
        self.assertEqual(set(matrix_free["reachable_runouts"]),
                         set(materialized["reachable_runouts"]))
        self.assertEqual(matrix_free["reachable_runouts"],
                         sorted(matrix_free["reachable_runouts"]))

        if case is SELECTED_CASE:
            tree_nodes = tuple(_all_tree_nodes(model[6]))
            self.assertTrue(any(
                action.name == "all_in"
                for node in nodes for action in node.actions))
            self.assertTrue(any(
                isinstance(node, rules._Terminal)
                and node.kind == "fold"
                and node.contributions[0] != node.contributions[1]
                and min(node.contributions) > 0
                for node in tree_nodes))
        oracle_mf, policies_mf = _policy_and_replay(matrix_free, case, model)
        oracle_mat, policies_mat = _policy_and_replay(materialized, case, model)
        _assert_close_metric_maps(
            self, oracle_mf, oracle_mat, case["name"] + "/numeric")
        _compare_action_rows(matrix_free, materialized)

        realization_mf = _own_realization(matrix_free, policies_mf, model)
        realization_mat = _own_realization(materialized, policies_mat, model)
        joint_mf, root_marginals, global_rivers, conditional_rivers = _joint_action_realizations(
            matrix_free, policies_mf, realization_mf, model)
        joint_mat, root_marginals_mat, global_rivers_mat, conditional_rivers_mat = _joint_action_realizations(
            materialized, policies_mat, realization_mat, model)
        self.assertEqual(root_marginals, root_marginals_mat)
        self.assertEqual(global_rivers, global_rivers_mat)
        self.assertEqual(conditional_rivers, conditional_rivers_mat)
        self.assertEqual(set(joint_mf), set(joint_mat))
        for key in joint_mf:
            with self.subTest(case=case["name"], joint_action=key):
                self.assertLessEqual(abs(float(joint_mf[key] - joint_mat[key])), TOL)
        self.assertEqual(set(realization_mf), set(realization_mat))
        for key in realization_mf:
            with self.subTest(case=case["name"], realization=key):
                self.assertLessEqual(
                    abs(float(realization_mf[key] - realization_mat[key])), TOL)

        # The independent world law must account for blockers and normalize
        # each public-river posterior separately.
        for marginal in root_marginals:
            self.assertEqual(sum(marginal.values(), Fraction(0)), 1)
        self.assertEqual(sum((sum(sides[0].values(), Fraction(0))
                              for sides in global_rivers.values()), Fraction(0)), 1)
        for river, sides in global_rivers.items():
            branch_mass = sum(sides[0].values(), Fraction(0))
            self.assertGreater(branch_mass, 0)
            self.assertEqual(sum(sides[1].values(), Fraction(0)), branch_mass)
            for side in conditional_rivers[river]:
                self.assertEqual(sum(side.values(), Fraction(0)), 1)
        self.assertEqual(sum((world["weight"] for world in worlds), Fraction(0)), 1)
        self.assertEqual(matrix_free["worlds"], len(worlds))
        if case["runouts"] is None:
            self.assertEqual(len(selected), 48)
            self.assertEqual(len(worlds), 44)
        else:
            independent_ranges = model[3]
            theoretical = sum(
                1 for left in independent_ranges[0] for right in independent_ranges[1]
                if not (set(left) & set(right))
            ) * len(selected)
            self.assertLess(len(worlds), theoretical)
            # The As branch excludes OOP's AsKd combo but remains reachable
            # through the other OOP hand, so the revealed-card posterior changes.
            self.assertEqual(global_rivers["As"][0].get("AsKd", Fraction(0)), 0)
            self.assertNotEqual(
                root_marginals[0].get("AsKd", Fraction(0)),
                conditional_rivers["As"][0].get("AsKd", Fraction(0)),
            )

        # Exact response replay uses the pre-existing 100k/64/65536 caps.
        # Capacity ValueErrors are retained as explicit admission outcomes.
        exact_outcomes = {}
        for label, result, policies in (
                ("matrix_free", matrix_free, policies_mf),
                ("materialized", materialized, policies_mat)):
            try:
                scans, partitions = _exact_modes(result, case, model, policies)
            except ValueError as exc:
                message = str(exc)
                if not _is_exact_capacity_error(message):
                    raise
                exact_outcomes[label] = {"admission_miss": message}
            else:
                exact_outcomes[label] = {
                    "scan": scans,
                    "partition": partitions,
                }
                self.assertEqual(scans["metrics"], partitions["metrics"])
                _assert_close_metric_maps(
                    self, scans["metrics"], oracle_mf if label == "matrix_free" else oracle_mat,
                    case["name"] + "/" + label + "/exact-vs-independent-numeric")
                _assert_close_metric_maps(
                    self, scans["metrics"], result,
                    case["name"] + "/" + label + "/exact-vs-result")
                for output in (scans, partitions):
                    self.assertLessEqual(output["work"], EXACT_WORK_CAP)
                    self.assertLessEqual(output["tree_depth"], EXACT_DEPTH_CAP)
                    self.assertLessEqual(
                        output["maximum_fraction_bits"], EXACT_BITS_CAP)
        self.__class__.exact_admission[case["name"]] = exact_outcomes
        self.__class__.completed[case["name"]] = {
            "worlds": len(worlds), "public_decisions": len(nodes),
            "exact_admission": exact_outcomes,
        }

    def test_selected_blocker_case_against_materialized_and_independent_rules(self):
        self._run_case(SELECTED_CASE)

    def test_full_deck_case_against_materialized_and_independent_rules(self):
        self._run_case(FULL_DECK_CASE)

    def test_z_exact_oracle_admission_is_retained_for_both_fixtures(self):
        # Test ordering is intentionally not assumed: invoke both controls if
        # this method runs before either per-case test, then require receipts.
        for case in CASES:
            self._run_case(case)
        self.assertEqual(set(self.__class__.exact_admission), {
            SELECTED_CASE["name"], FULL_DECK_CASE["name"]})
        for case_name, backend_results in self.__class__.exact_admission.items():
            self.assertEqual(set(backend_results), {"matrix_free", "materialized"})
            for outcome in backend_results.values():
                self.assertNotIn("admission_miss", outcome, outcome)
                self.assertTrue({"scan", "partition"} <= set(outcome))


def _exact_modes(result, case, model, policies):
    board, config, _, _, worlds, _, root, _ = model
    scans = exact.evaluate_exact(
        root, worlds, policies, config.pot, result=result,
        chance_grouping="scan",
    )
    partitions = exact.evaluate_exact(
        root, worlds, policies, config.pot, result=result,
        chance_grouping="partition",
    )
    return scans, partitions


if __name__ == "__main__":
    unittest.main()
