import unittest
import math
from unittest.mock import patch

from scripts.preflop_validation import compare_result, replay_policy
from pokerlab.preflop_solver import solve_preflop


_WEIGHTED = {
    "sb": "AsAd:1,AhAc:0.25",
    "bb": "KsKd:1,KcKh:0.5",
    "config": {"starting_stack": [4, 3], "raise_sizes": [0.5],
                "max_raises": 1, "include_all_in": False},
    "runouts": ("2c3c4d7h8h", "Kc2d3h7s8c", "Ac2d3h7s8c"),
    "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                    "max_raises": 0, "include_all_in": False},
}
_SHARED_PREFIX = {
    "sb": "AsAd",
    "bb": "KsKd",
    "config": {"starting_stack": 4, "max_raises": 0},
    "runouts": ("2c3c4d7h8h", "2c3c4d7hKc",
                "2c3c4dKc8h", "2c3c4d7s8c"),
}
_ALGORITHMS = ("vanilla", "dcfr", "cfrplus")


def _assert_policy_rows_equal(test, expected, actual):
    test.assertEqual(len(expected), len(actual))
    for left, right in zip(expected, actual):
        for field in ("player", "hand", "street", "revealed_board", "history"):
            test.assertEqual(left[field], right[field])
        test.assertEqual(len(left["actions"]), len(right["actions"]))
        for left_action, right_action in zip(left["actions"], right["actions"]):
            for field in ("name", "amount", "raise_to", "history_key"):
                test.assertEqual(left_action[field], right_action[field])
            test.assertAlmostEqual(left_action["probability"],
                                   right_action["probability"], delta=1e-10)


def _terminal_nodes(root):
    from pokerlab.postflop_solver import _Chance
    from pokerlab.river_tree import _Node, _Terminal

    result = []
    pending = [root]
    while pending:
        node = pending.pop()
        if isinstance(node, _Chance):
            pending.extend(node.branches.values())
        elif isinstance(node, _Node):
            pending.extend(node.children)
        elif isinstance(node, _Terminal):
            result.append(node)
    return result


class PreflopPublicBatchedTests(unittest.TestCase):
    def _assert_backend_parity(self, fixture, algorithm):
        kwargs = {key: value for key, value in fixture.items()
                  if key in {"config", "runouts", "flop_config", "turn_config", "river_config"}}
        positional = fixture["sb"], fixture["bb"]
        recursive = solve_preflop(*positional, iterations=10, algorithm=algorithm,
                                   traversal="recursive", **kwargs)
        vector = solve_preflop(*positional, iterations=10, algorithm=algorithm,
                               traversal="public-batched", **kwargs)
        _assert_policy_rows_equal(self, recursive["strategy"], vector["strategy"])
        for field in ("value_sb", "value_bb", "sb_best_response_value",
                      "bb_best_response_value", "sb_gain", "bb_gain",
                      "nash_conv", "exploitability"):
            self.assertAlmostEqual(recursive[field], vector[field], delta=1e-10)
        for field in ("worlds", "public_states", "decisions", "info_sets",
                      "private_pair_probabilities"):
            self.assertEqual(recursive[field], vector[field])
        oracle = replay_policy(vector, *positional, **kwargs)
        compare_result(vector, oracle)
        self.assertGreater(vector["public_batched_training_pot_anchor"], 0)
        self.assertEqual(vector["public_batched_prefix_edge_limit"], 250_000)
        self.assertGreater(vector["public_batched_training_view_states"], 0)
        return vector

    def test_fractional_blinds_and_sizes_preserve_public_training_translation(self):
        fixture = {
            "sb": "AsAd",
            "bb": "KsKd",
            "config": {
                "small_blind": 0.123456789,
                "big_blind": 0.345678901,
                "starting_stack": [2, 1.5],
                "raise_sizes": [0.5], "max_raises": 1,
                "include_all_in": False,
            },
            "runouts": ("2c3c4d7h8h", "Kc2d3h7s8c"),
            "flop_config": {
                  "bet_sizes": [0.123456781], "raise_sizes": [0.271828182],
                "max_raises": 1, "include_all_in": False,
            },
            "turn_config": {
                  "bet_sizes": [0.314159265], "raise_sizes": [0.271828182],
                "max_raises": 1, "include_all_in": False,
            },
            "river_config": {
                  "bet_sizes": [0.271828183], "raise_sizes": [0.141421356],
                "max_raises": 1, "include_all_in": False,
            },
        }
        vector = self._assert_backend_parity(fixture, "vanilla")
        oracle = replay_policy(
            vector, fixture["sb"], fixture["bb"],
            **{key: value for key, value in fixture.items()
               if key not in {"sb", "bb"}},
        )
        compare_result(vector, oracle)

    def test_large_fractional_terminal_translation_does_not_round(self):
        from pokerlab.river_tree import _Action, _Node, _Terminal, _terminal_value
        from pokerlab.preflop_solver import _positive_pot_training_view

        anchor = 0.1234567894
        large = 999999.8765432107
        root = _Node(
            (), 0, (_Action("fold"), _Action("call")),
            (_Terminal("fold", (anchor, anchor + 0.5), 1),
             _Terminal("showdown", (large, large + 1), None)),
        )
        training_root, actual_anchor, _ = _positive_pot_training_view(root)
        self.assertIsNot(training_root, root)
        expected_anchor = math.ldexp(1.0, math.frexp(anchor)[1] - 1)
        self.assertEqual(actual_anchor, expected_anchor)
        original_large, shifted_large = root.children[1], training_root.children[1]
        self.assertEqual(shifted_large.contributions[0], large - actual_anchor)
        original_value = _terminal_value(original_large, 1, 0)
        shifted_value = _terminal_value(shifted_large, 1, 2 * actual_anchor)
        self.assertLessEqual(abs(original_value - shifted_value), math.ulp(large))
        self.assertEqual(original_value, shifted_value)
        # A nine-decimal cleanup of the shifted amount would move this value
        # by two ULPs and fail the exact utility assertion above.
        self.assertGreater(
            abs(actual_anchor + round((large - actual_anchor), 9) - large),
            math.ulp(large),
        )

    def test_weighted_multiflop_and_shared_prefix_match_all_algorithms(self):
        for algorithm in _ALGORITHMS:
            with self.subTest(fixture="weighted", algorithm=algorithm):
                result = self._assert_backend_parity(_WEIGHTED, algorithm)
                if algorithm == "cfrplus":
                    self.assertEqual(result["training_passes"], 30)
            with self.subTest(fixture="shared-prefix", algorithm=algorithm):
                self._assert_backend_parity(_SHARED_PREFIX, algorithm)

    def test_short_blind_refund_and_root_blind_fold_utilities(self):
        refund = {
            "config": {"starting_stack": [0.5, 20], "max_raises": 0},
            "runouts": ("2c3c4d7h8h",),
            "iterations": 10,
        }
        vector = solve_preflop("AsAd", "KsKd", algorithm="vanilla",
                               traversal="public-batched", **refund)
        vanilla = solve_preflop("AsAd", "KsKd", algorithm="vanilla",
                                traversal="recursive", **refund)
        self.assertEqual(vector["strategy"], [])
        self.assertIsNone(vector["public_batched_training_pot_anchor"])
        for field in ("value_sb", "value_bb", "sb_best_response_value",
                      "bb_best_response_value", "nash_conv"):
            self.assertAlmostEqual(vector[field], vanilla[field], delta=1e-12)
        self.assertAlmostEqual(vector["value_sb"], 0.5, delta=1e-12)
        self.assertAlmostEqual(vector["value_bb"], -0.5, delta=1e-12)

        fold_fixture = {
            "config": {"starting_stack": [2, 1], "max_raises": 0},
            "runouts": ("2c3c4d7h8h", "Kc2d3h7s8c"),
        }
        vector = self._assert_backend_parity(
            {"sb": "AsAd", "bb": "KsKd", **fold_fixture}, "vanilla")
        self.assertEqual(vector["strategy"][0]["actions"][0]["name"], "fold")

    def test_training_view_isolated_when_shared_edge_guard_rejects(self):
        import pokerlab.preflop_solver as solver

        original_converter = solver._positive_pot_training_view
        captured = {}

        def inspect_view(root):
            training_root, anchor, states = original_converter(root)
            captured["root"] = root
            captured["training_root"] = training_root
            captured["original_terms"] = tuple(
                (node.kind, node.contributions, node.winner)
                for node in _terminal_nodes(root))
            captured["anchor"] = anchor
            captured["states"] = states
            return training_root, anchor, states

        with patch.object(solver, "_positive_pot_training_view",
                          side_effect=inspect_view):
            with patch("pokerlab.public_cfr.MAX_PREFIX_EDGES", 1):
                with self.assertRaisesRegex(ValueError, "prefix/hand edges"):
                    solve_preflop(_WEIGHTED["sb"], _WEIGHTED["bb"],
                                  config=_WEIGHTED["config"],
                                  runouts=_WEIGHTED["runouts"],
                                  flop_config=_WEIGHTED["flop_config"],
                                  iterations=10, traversal="public-batched")

        self.assertIsNot(captured["root"], captured["training_root"])
        original_terms = tuple((node.kind, node.contributions, node.winner)
                               for node in _terminal_nodes(captured["root"]))
        self.assertEqual(original_terms, captured["original_terms"])
        shifted_terms = _terminal_nodes(captured["training_root"])
        self.assertEqual(len(shifted_terms), len(original_terms))
        from pokerlab.river_tree import _terminal_value

        for original, shifted in zip(_terminal_nodes(captured["root"]), shifted_terms):
            self.assertEqual(shifted.kind, original.kind)
            self.assertEqual(shifted.winner, original.winner)
            for old, new in zip(original.contributions, shifted.contributions):
                self.assertAlmostEqual(new, old - captured["anchor"], delta=1e-12)
            for sign in (-1, 0, 1):
                self.assertAlmostEqual(
                    _terminal_value(original, sign, 0),
                    _terminal_value(shifted, sign, 2 * captured["anchor"]),
                    delta=1e-12,
                )


if __name__ == "__main__":
    unittest.main()
