from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import flop_multistreet_validation as physical
from scripts import flop_public_classes as shared
from scripts import flop_second_board_equivalence as eq


BOARD = ("7c", "8d", "9h")


def terminal(history=(), *, kind="showdown", winner=None, contributions=(0, 0)):
    return physical._Terminal(history, kind, contributions, winner)


def action(name, amount=0, history_key=None):
    return {"name": name, "amount": amount, "raise_to": None,
            "history_key": history_key or name}


def mirrored_reveal_tree():
    def river_chance(turn, action_name):
        history = ("turn@" + turn, action_name)
        branches = {}
        for river in ("2d", "3d"):
            h = history + ("river@" + river,)
            children = (terminal(h, kind="fold", winner=1),
                        terminal(h + ("call",), kind="showdown"))
            branches[river] = physical._Decision(
                h, 0, "river", BOARD + (turn, river),
                (action("fold"), action("call")), children)
        return physical._Chance(history, 4, "river", branches)

    def turn_decision(turn):
        history = ("turn@" + turn,)
        return physical._Decision(
            history, 0, "turn", BOARD + (turn,),
            (action("check"), action("bet", 5)),
            (river_chance(turn, "check"), river_chance(turn, "bet")))

    return physical._Chance((), 3, "turn",
                            {"Tc": turn_decision("Tc"), "Jc": turn_decision("Jc")})


def reveal_maps():
    turns = {"Tc": "T00", "Jc": "T00"}
    rivers = {(turn, river): "R%02d" % i
              for turn in ("Tc", "Jc")
              for i, river in enumerate(("2d", "3d"))}
    return turns, rivers


def tiny_oracle(root, hands=("AdAs",)):
    return {"root": root, "active_hands_by_prefix": {(0, ()): set(hands)}}


class CollapseTests(unittest.TestCase):
    def test_compares_complete_descendants_at_turn_and_river_layers(self):
        root = mirrored_reveal_tree()
        turns, rivers = reveal_maps()
        _, census = eq._collapse(root, turns, rivers, expected_nodes=len(eq._walk(root)))
        self.assertEqual(census["physical_nodes_checked"], len(eq._walk(root)))
        self.assertEqual(census["physical_branch_subtrees_compared"], 10)
        self.assertEqual(len(census["compact_tree_sha256"]), 64)

    def test_rejects_action_payoff_history_and_winner_differences(self):
        mutations = (
            lambda root: root.branches["Jc"].actions[0].__setitem__("amount", 4),
            lambda root: setattr(root.branches["Jc"].children[0].branches["2d"].children[1],
                                 "contributions", (1, 0)),
            lambda root: setattr(root.branches["Jc"].children[0].branches["2d"],
                                 "history", ("turn@Jc", "other")),
            lambda root: setattr(root.branches["Jc"].children[0].branches["2d"].children[0],
                                 "winner", 0),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                root = mirrored_reveal_tree()
                mutate(root)
                turns, rivers = reveal_maps()
                with self.assertRaises(ValueError):
                    eq._collapse(root, turns, rivers, expected_nodes=len(eq._walk(root)))


class DimensionAndPolicyTests(unittest.TestCase):
    def test_full_own_hand_rows_and_20k_row_guard(self):
        root = physical._Decision((), 0, "flop", BOARD,
                                  (action("check"), action("bet", 5)),
                                  (terminal(), terminal()))
        oracle = tiny_oracle(root, ("AdAs", "QdQs"))
        rows = eq._expected_rows(oracle)
        self.assertEqual(set(rows), {(0, "AdAs", ()), (0, "QdQs", ())})
        with patch.object(eq, "MAX_POLICY_ROWS", 1):
            with self.assertRaisesRegex(ValueError, "rows exceed"):
                eq._expected_rows(oracle)

    def test_maximum_33_world_path_guard(self):
        root = physical._Decision((), 0, "flop", BOARD,
                                  (action("check"), action("bet", 5)),
                                  (terminal(), terminal()))
        world = ("AdAs", "KdKs", Fraction(1), 1, BOARD + ("Tc", "2d"))
        self.assertEqual(eq._path_bound(root, (world,)), (3, 3))
        with patch.object(eq, "MAX_WORLD_PATH_STATES", 2):
            with self.assertRaisesRegex(ValueError, "path"):
                eq._path_bound(root, (world,))

    def test_within_class_policy_mismatch_rejects_signed_zero(self):
        rows = {
            (0, "AdAs", ("turn@Tc",)): (0.0, 1.0),
            (0, "AdAs", ("turn@Jc",)): (-0.0, 1.0),
        }
        turns, _ = reveal_maps()
        model = SimpleNamespace(turns=turns, rivers={}, physical={})
        mapped = (0, "AdAs", ("turn@T00",))
        with patch.object(eq.physical, "_validate_policy", return_value=rows), \
             patch.object(eq, "_class_rows", return_value={mapped: object()}):
            with self.assertRaisesRegex(ValueError, "bitwise"):
                eq._project({}, model)

    def test_varying_between_classes_is_valid_and_zero_reach_keeps_all_rows(self):
        rows = {
            (0, "AdAs", ("turn@Tc",)): (1.0, 0.0),
            (0, "AdAs", ("turn@Jc",)): (0.0, 1.0),
        }
        model = SimpleNamespace(turns={"Tc": "T00", "Jc": "T01"}, rivers={}, physical={})
        mapped = {(0, "AdAs", ("turn@T00",)): object(),
                  (0, "AdAs", ("turn@T01",)): object()}
        with patch.object(eq.physical, "_validate_policy", return_value=rows), \
             patch.object(eq, "_class_rows", return_value=mapped):
            projected, _ = eq._project({}, model)
        self.assertEqual(len(projected), 2)
        self.assertEqual(projected[(0, "AdAs", ("turn@T00",))], (1.0, 0.0))
        self.assertEqual(projected[(0, "AdAs", ("turn@T01",))], (0.0, 1.0))

        keys = [(0, "AdAs", ("turn@T00",)), (0, "AdAs", ("turn@T01",))]
        model = SimpleNamespace()
        with patch.object(eq, "_class_rows", return_value={key: SimpleNamespace(
                actions=(action("check"), action("bet"))) for key in keys}):
            zero_reach = eq.control_rows(model, "zero-reach")
        self.assertEqual(set(zero_reach), set(keys))
        self.assertTrue(all(value == (1.0, 0.0) for value in zero_reach.values()))

    def test_class_varying_control_is_complete_and_can_vary_across_classes(self):
        keys = [(0, "AdAs", ("turn@T00",)), (0, "AdAs", ("turn@T01",))]
        model = SimpleNamespace()
        nodes = {key: SimpleNamespace(actions=(action("check"), action("bet"))) for key in keys}
        with patch.object(eq, "_class_rows", return_value=nodes), \
             patch.object(eq, "_digest", side_effect=("00000000", "00000004")):
            rows = eq.control_rows(model, "class-varying")
        self.assertEqual(set(rows), set(keys))
        self.assertNotEqual(rows[keys[0]], rows[keys[1]])

    def test_validate_model_rejects_mutated_rebuilt_attributes(self):
        root = terminal()
        original = eq.SecondBoardModel({}, {}, {}, {}, (), root, {"x": 1}, 4134)
        mutated = replace(original, worlds=(("AdAs", "KdKs", Fraction(1), 1, BOARD),))
        with patch.object(eq, "_make_model", return_value=original):
            with self.assertRaisesRegex(ValueError, "reconstruction"):
                eq.validate_model(mutated)


class BuilderAndAuditTests(unittest.TestCase):
    def test_builder_runs_admission_before_authentication_or_rank(self):
        with patch.object(eq, "admission", side_effect=ValueError("not admitted")), \
             patch.object(eq.prerequisite, "verify") as verify, \
             patch.object(eq.physical, "prepare_oracle") as prepare:
            with self.assertRaisesRegex(ValueError, "not admitted"):
                eq.build_model()
        verify.assert_not_called()
        prepare.assert_not_called()

    def test_rank_attempt_wrapper_restores_original_on_prepare_error(self):
        calls = []
        original = lambda key: calls.append(key) or 7
        progress = {}

        def failing_prepare(*args):
            self.assertEqual(eq.physical.independent_rank(("synthetic",)), 7)
            raise RuntimeError("synthetic preparation failure")

        receipt = {"status": "saved-second-board-reference-authenticated",
                   "physical_builds": 0, "ranking_calls": 0}
        with patch.object(eq, "admission", return_value={}), \
             patch.object(eq.prerequisite, "verify", return_value=receipt), \
             patch.object(eq.physical, "independent_rank", original), \
             patch.object(eq.physical, "prepare_oracle", side_effect=failing_prepare):
            with self.assertRaisesRegex(RuntimeError, "synthetic preparation"):
                eq.build_model(progress=progress)
            self.assertIs(eq.physical.independent_rank, original)
        self.assertEqual(calls, [("synthetic",)])
        self.assertEqual(progress["preparation_ranker_attempts"], 1)
        self.assertEqual(progress["preparation_rank_calls"], 1)
        self.assertEqual(progress["physical_builds_attempted"], 1)
        self.assertEqual(progress["physical_builds_completed"], 0)

    def test_audit_control_validates_on_entry_and_finally(self):
        model = SimpleNamespace(root=terminal(), worlds=(), physical={"root": terminal(), "worlds": ()})
        rows = {(0, "AdAs", ()): (1.0, 0.0)}
        exact = {key: Fraction(0) for key in eq.METRICS}
        numeric = {key: 0.0 for key in eq.METRICS}
        validations = []
        def validate(_):
            validations.append("validate")
            return {}

        with patch.object(eq, "validate_model", side_effect=validate), \
             patch.object(eq, "control_rows", return_value=rows), \
             patch.object(eq.shared, "_exact_metrics", return_value=exact), \
             patch.object(eq, "_lift", return_value={"synthetic": True}), \
             patch.object(eq, "_project", return_value=(rows, rows)), \
             patch.object(eq.physical, "replay", return_value=numeric):
            report = eq.audit_control(model, "check-call")
        self.assertEqual(validations, ["validate", "validate"])
        self.assertEqual(report["mode"], "check-call")
        self.assertEqual(report["maximum_numeric_gap"], 0.0)

    def test_audit_preserves_first_error_and_records_cleanup_failure(self):
        model = SimpleNamespace()
        primary = ValueError("primary control failure")
        cleanup = RuntimeError("cleanup reconstruction failure")
        with patch.object(eq, "validate_model", side_effect=(None, cleanup)) as validate, \
             patch.object(eq, "control_rows", side_effect=primary):
            with self.assertRaisesRegex(ValueError, "primary control") as raised:
                eq.audit_control(model, "check-call")
        self.assertIs(raised.exception, primary)
        self.assertEqual(primary.second_board_cleanup_error,
                         "RuntimeError: cleanup reconstruction failure")
        self.assertEqual(validate.call_count, 2)


class ExactMetricTests(unittest.TestCase):
    def test_hidden_turn_is_summed_before_the_flop_action_max(self):
        turns = ("Tc", "Jc")
        worlds = tuple(("AdAs", "KdKs", Fraction(1, 2), 1,
                        BOARD + (turn, "2d")) for turn in turns)
        left = physical._Chance((), 3, "turn", {
            "Tc": terminal(kind="showdown", contributions=(5, 5)),
            "Jc": terminal(kind="showdown", contributions=(5, 5)),
        })
        right = physical._Chance((), 3, "turn", {
            "Tc": terminal(kind="fold", winner=0),
            "Jc": terminal(kind="fold", winner=0),
        })
        # Action one wins 10 or loses 10 with the hidden turn sign. Action two
        # wins 5 on either turn. The legal flop response averages each action
        # over both turns before choosing: max(0, 5) = 5. A max before chance
        # would incorrectly return (10 + 5) / 2 = 7.5.
        worlds = (worlds[0][:3] + (1,) + worlds[0][4:],
                 worlds[1][:3] + (-1,) + worlds[1][4:])
        root = physical._Decision((), 0, "flop", BOARD,
                                  (action("check"), action("bet", 5)), (left, right))
        metrics = shared._exact_metrics(root, worlds, {(0, "AdAs", ()): (0.5, 0.5)})
        self.assertEqual(metrics["value_oop"], Fraction(5, 2))
        self.assertEqual(metrics["oop_best_response_value"], Fraction(5))
        self.assertEqual(metrics["nash_conv"], Fraction(5, 2))

    def test_private_hands_get_separate_own_hand_best_responses(self):
        worlds = (("AdAs", "KdKs", Fraction(1, 2), 1, BOARD + ("Tc", "2d")),
                  ("QdQs", "KdKs", Fraction(1, 2), -1, BOARD + ("Tc", "2d")))
        root = physical._Decision((), 0, "flop", BOARD,
                                  (action("showdown"), action("fold")),
                                  (terminal(kind="showdown", contributions=(5, 5)),
                                   terminal(kind="fold", winner=0)))
        rows = {(0, "AdAs", ()): (1.0, 0.0),
                (0, "QdQs", ()): (0.0, 1.0)}
        metrics = shared._exact_metrics(root, worlds, rows)
        self.assertEqual(metrics["value_oop"], Fraction(15, 2))
        self.assertEqual(metrics["oop_best_response_value"], Fraction(15, 2))
        self.assertEqual(metrics["nash_conv"], Fraction(0))


if __name__ == "__main__":
    unittest.main()
