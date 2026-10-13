"""Independent serialized turn/river policy replay checks."""
from copy import deepcopy
from fractions import Fraction
from itertools import product
import unittest

from pokerlab.matrix_free_river import solve_matrix_free_river
from pokerlab.matrix_free_turn import solve_matrix_free_turn
from pokerlab.postflop_solver import solve_postflop
from pokerlab.river_config import RiverConfig
from pokerlab.cards import DECK
from scripts.river_analytical import (
    equilibrium as polar_equilibrium, metrics as polar_metrics, serialized_profile,
)
from scripts.turn_river_validation import (
    _Chance, _Decision, _Terminal, _best_response,
    _diagnostic_gains, compare_result, replay_policy,
)


class TurnRiverIndependentValidationTests(unittest.TestCase):
    def test_required_metadata_modes_zero_support_and_both_reachable_orders(self):
        board = "2c5d9hJc"
        config = RiverConfig(10, 20, (0.5,), (), 0, False)

        # Explicitly supplying every candidate river is still a conditioned
        # subset request, even though its card set is the full candidate set.
        all_rivers = tuple(card for card in DECK if card not in board)
        full_subset = solve_matrix_free_turn(
            board, "AsAh", "KsKh", config, runouts=all_rivers,
            iterations=10, algorithm="vanilla",
        )
        self.assertEqual(full_subset["runout_mode"], "conditioned-subset")
        full_subset_oracle = replay_policy(
            full_subset, "AsAh", "KsKh", board=board, config=config,
            runouts=all_rivers,
        )
        self.assertTrue(compare_result(full_subset, full_subset_oracle))

        # Kc is in the selected list but blocked by every positive-mass IP
        # holding. It remains requested and has no physical posterior support.
        selected = ("3s", "Kc")
        blocked = solve_matrix_free_turn(
            board, "AsAh", "KcKd", config, runouts=selected,
            iterations=10, algorithm="vanilla",
        )
        blocked_oracle = replay_policy(
            blocked, "AsAh", "KcKd", board=board, config=config,
            runouts=selected,
        )
        self.assertEqual(blocked["runouts"], ["3s", "Kc"])
        self.assertEqual(blocked["reachable_runouts"], ["3s"])
        self.assertEqual(set(blocked_oracle["river_probabilities"]), {"3s"})
        self.assertEqual(blocked_oracle["river_probabilities"]["3s"], 1.0)
        corrupt_blocked = deepcopy(blocked)
        corrupt_blocked["reachable_runouts"].append("Kc")
        with self.assertRaises(ValueError):
            replay_policy(corrupt_blocked, "AsAh", "KcKd", board=board,
                          config=config, runouts=selected)

        # Lexical and DECK orders differ for these mixed ranks. Both existing
        # serializers must replay without harmonizing their output ordering.
        mixed = ("Ac", "Tc", "2d")
        matrix_result = solve_matrix_free_turn(
            board, "AsAh", "KsKh", config, runouts=mixed,
            iterations=10, algorithm="vanilla",
        )
        materialized_result = solve_postflop(
            board, "AsAh", "KsKh", config, runouts=mixed,
            iterations=10, algorithm="vanilla", traversal="public-batched",
            diagnostics="public-batched",
        )
        self.assertEqual(matrix_result["reachable_runouts"], ["2d", "Ac", "Tc"])
        self.assertEqual(materialized_result["reachable_runouts"], ["2d", "Tc", "Ac"])
        for result in (matrix_result, materialized_result):
            oracle = replay_policy(result, "AsAh", "KsKh", board=board,
                                   config=config, runouts=mixed)
            self.assertTrue(compare_result(result, oracle))

    def test_required_metadata_and_reachability_corruptions_are_rejected(self):
        board = "2c5d9hJc"
        oop, ip = "AsAh", "KsKh"
        config = RiverConfig(10, 20, (0.5,), (), 0, False)
        runouts = ("2d", "Tc", "Ac")
        results = [
            solve_matrix_free_turn(board, oop, ip, config, runouts=runouts,
                                   iterations=10, algorithm="vanilla"),
            solve_postflop(board, oop, ip, config, runouts=runouts,
                           iterations=10, algorithm="vanilla",
                           traversal="public-batched", diagnostics="public-batched"),
        ]
        river_board = "2c5d9hJc7s"
        results.extend((
            solve_matrix_free_river(river_board, oop, ip, config,
                                    iterations=10, algorithm="vanilla"),
            solve_postflop(river_board, oop, ip, config, iterations=10,
                           algorithm="vanilla", traversal="public-batched",
                           diagnostics="public-batched"),
        ))
        for result in results:
            replay = replay_policy(result, oop, ip,
                                   board=board if len(result["board"]) == 4 else river_board,
                                   config=config,
                                   runouts=runouts if len(result["board"]) == 4 else None)
            self.assertTrue(compare_result(result, replay))
            for field in ("board", "runouts", "runout_mode", "reachable_runouts"):
                corrupt = deepcopy(result)
                del corrupt[field]
                with self.subTest(solver=result["solver_version"], missing=field), \
                     self.assertRaises(ValueError):
                    replay_policy(corrupt, oop, ip,
                                  board=board if len(result["board"]) == 4 else river_board,
                                  config=config,
                                  runouts=runouts if len(result["board"]) == 4 else None)

        base = results[0]
        mutations = (
            ("runout_mode", "full-deck"),
            ("runout_mode", True),
            ("runouts", "2d,Tc,Ac"),
            ("runouts", ["2d", "2d", "Ac"]),
            ("runouts", ["2d", "Tc", "Ac", "Ks"]),
            ("reachable_runouts", ["Ac", "2d", "Tc"]),
            ("reachable_runouts", ["2d", "Ac"]),
            ("reachable_runouts", ["2d", "Tc", "Ac", "Ks"]),
            ("reachable_runouts", ["2d", "Ac", "Tc", "Ac"]),
            ("reachable_runouts", ["2d", "Tc", 14]),
            ("reachable_runouts", "2d,Tc,Ac"),
            ("board", ["2c", "5d", "9h", "Jc", True]),
        )
        for field, value in mutations:
            corrupt = deepcopy(base)
            corrupt[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                replay_policy(corrupt, oop, ip, board=board, config=config,
                              runouts=runouts)

    def test_required_count_aliases_are_strict_and_all_present_aliases_are_checked(self):
        board = "2c5d9hJc"
        oop, ip = "AsAh", "KsKh"
        config = RiverConfig(10, 20, (0.5,), (), 0, False)
        runouts = ("2d", "Tc", "Ac")
        result = solve_postflop(
            board, oop, ip, config, runouts=runouts, iterations=10,
            algorithm="vanilla", traversal="public-batched",
            diagnostics="public-batched",
        )
        oracle = replay_policy(result, oop, ip, board=board, config=config,
                               runouts=runouts)
        for field in ("info_sets", "worlds", "compatible_pairs", "deals"):
            original = result[field]
            for bad in (True, False, float(original), -1, original + 1):
                corrupt = deepcopy(result)
                corrupt[field] = bad
                with self.subTest(field=field, bad=bad):
                    with self.assertRaises(ValueError):
                        replay_policy(corrupt, oop, ip, board=board,
                                      config=config, runouts=runouts)
                    with self.assertRaises(ValueError):
                        compare_result(corrupt, oracle)

        for missing in (("info_sets",), ("worlds", "compatible_world_count")):
            corrupt = deepcopy(result)
            for field in missing:
                corrupt.pop(field, None)
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                replay_policy(corrupt, oop, ip, board=board,
                              config=config, runouts=runouts)
        optional_pair_aliases_removed = deepcopy(result)
        optional_pair_aliases_removed.pop("compatible_pairs")
        optional_pair_aliases_removed.pop("deals")
        self.assertTrue(compare_result(
            optional_pair_aliases_removed,
            replay_policy(optional_pair_aliases_removed, oop, ip, board=board,
                          config=config, runouts=runouts),
        ))

        river = "2c5d9hJc7s"
        river_result = solve_matrix_free_river(
            river, oop, ip, config, iterations=10, algorithm="vanilla")
        river_oracle = replay_policy(river_result, oop, ip, board=river,
                                     config=config)
        for field in ("info_sets", "compatible_pairs", "deals"):
            original = river_result[field]
            for bad in (True, False, float(original), -1, original + 1):
                corrupt = deepcopy(river_result)
                corrupt[field] = bad
                with self.subTest(river_field=field, bad=bad):
                    with self.assertRaises(ValueError):
                        replay_policy(corrupt, oop, ip, board=river, config=config)
                    with self.assertRaises(ValueError):
                        compare_result(corrupt, river_oracle)
        river_missing = deepcopy(river_result)
        river_missing.pop("compatible_pairs")
        river_missing.pop("deals")
        with self.assertRaises(ValueError):
            replay_policy(river_missing, oop, ip, board=river, config=config)

        matrix_turn = solve_matrix_free_turn(
            board, oop, ip, config, runouts=runouts,
            iterations=10, algorithm="vanilla",
        )
        matrix_turn_oracle = replay_policy(
            matrix_turn, oop, ip, board=board, config=config, runouts=runouts)
        matrix_turn_missing = deepcopy(matrix_turn)
        matrix_turn_missing.pop("compatible_world_count")
        with self.assertRaises(ValueError):
            replay_policy(matrix_turn_missing, oop, ip, board=board,
                          config=config, runouts=runouts)
        for field in ("info_sets", "compatible_world_count"):
            original = matrix_turn[field]
            for bad in (True, False, float(original), -1, original + 1):
                corrupt = deepcopy(matrix_turn)
                corrupt[field] = bad
                with self.subTest(matrix_turn_field=field, bad=bad):
                    with self.assertRaises(ValueError):
                        replay_policy(corrupt, oop, ip, board=board,
                                      config=config, runouts=runouts)
                    with self.assertRaises(ValueError):
                        compare_result(corrupt, matrix_turn_oracle)

        materialized_river = solve_postflop(
            river, oop, ip, config, iterations=10, algorithm="vanilla",
            traversal="public-batched", diagnostics="public-batched",
        )
        materialized_river_oracle = replay_policy(
            materialized_river, oop, ip, board=river, config=config)
        for field in ("info_sets", "worlds", "compatible_pairs", "deals"):
            original = materialized_river[field]
            for bad in (True, False, float(original), -1, original + 1):
                corrupt = deepcopy(materialized_river)
                corrupt[field] = bad
                with self.subTest(materialized_river_field=field, bad=bad):
                    with self.assertRaises(ValueError):
                        replay_policy(corrupt, oop, ip, board=river, config=config)
                    with self.assertRaises(ValueError):
                        compare_result(corrupt, materialized_river_oracle)

    def test_compare_checks_published_gain_fields_and_metric_identities(self):
        board = "2c5d9hJcKd"
        oop, ip = "AsAh", "KsKh"
        config = RiverConfig(10, 20, (0.5,), (), 0, False)
        result = solve_matrix_free_river(board, oop, ip, config,
                                         iterations=10, algorithm="vanilla")
        oracle = replay_policy(result, oop, ip, board=board, config=config)
        differences = compare_result(result, oracle)
        self.assertEqual(set(differences), {
            "value_oop", "value_ip", "oop_best_response_value",
            "ip_best_response_value", "oop_best_response_gain",
            "ip_best_response_gain", "nash_conv", "exploitability",
        })
        for field in ("oop_best_response_gain", "ip_best_response_gain"):
            for bad in (-1e-6, True, float("nan"), float("inf"),
                        -float("inf"), oracle[field] + 0.01):
                corrupt = deepcopy(result)
                corrupt[field] = bad
                with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                    compare_result(corrupt, oracle)
            corrupt = deepcopy(result)
            del corrupt[field]
            with self.subTest(field=field, bad="missing"), self.assertRaises(ValueError):
                compare_result(corrupt, oracle)

        for field, bad in (
            ("nash_conv", result["nash_conv"] + 0.01),
            ("exploitability", result["exploitability"] + 0.01),
            ("value_ip", result["value_ip"] + 0.01),
        ):
            corrupt = deepcopy(result)
            corrupt[field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                compare_result(corrupt, oracle)

        tolerance = 1e-9
        zero_sum = deepcopy(result)
        zero_sum["value_oop"] += 0.75 * tolerance
        zero_sum["value_ip"] += 0.75 * tolerance
        with self.assertRaisesRegex(ValueError, "zero-sum value identity"):
            compare_result(zero_sum, oracle, tolerance)

        nash_identity = deepcopy(result)
        nash_identity["oop_best_response_gain"] += 0.75 * tolerance
        nash_identity["ip_best_response_gain"] += 0.75 * tolerance
        with self.assertRaisesRegex(ValueError, "NashConv identity"):
            compare_result(nash_identity, oracle, tolerance)

        self.assertGreater(result["exploitability"], 2.0 * tolerance)
        exploit_identity = deepcopy(result)
        exploit_identity["nash_conv"] += 0.75 * tolerance
        exploit_identity["exploitability"] -= 0.75 * tolerance
        with self.assertRaisesRegex(ValueError, "exploitability identity"):
            compare_result(exploit_identity, oracle, tolerance)

    def test_independent_response_sanity_guard_precedes_per_player_gain_clamp(self):
        self.assertEqual(_diagnostic_gains(0.0, 1e-9, -1e-9, 100.0),
                         (1e-9, 0.0, 1e-9))
        self.assertEqual(_diagnostic_gains(0.0, -1e-9, 0.0, 100.0),
                         (0.0, 0.0, 0.0))
        self.assertEqual(_diagnostic_gains(0.0, 0.0, -1e-9, 100.0),
                         (0.0, 0.0, 0.0))
        self.assertEqual(_diagnostic_gains(0.0, -1e-9, 1e-9, 100.0),
                         (0.0, 1e-9, 1e-9))
        for diagnostic in ((0.0, -1e-5, 0.0), (0.0, 0.0, -1e-5)):
            with self.subTest(diagnostic=diagnostic), self.assertRaises(ValueError):
                _diagnostic_gains(*diagnostic, 100.0)
        for diagnostic in ((float("nan"), 0.0, 0.0),
                           (0.0, float("inf"), 0.0),
                           (0.0, 0.0, -float("inf"))):
            with self.subTest(diagnostic=diagnostic), self.assertRaises(ValueError):
                _diagnostic_gains(*diagnostic, 100.0)

    def test_river_polarized_anchor_matches_independent_rational_game(self):
        board = "2c7d9hJsKd"
        config = RiverConfig(100, 500, (1.0,), (), 0, False)
        result = solve_matrix_free_river(
            board, "AsAh,3c4c", "QsQh", config,
            iterations=300, algorithm="cfrplus",
        )
        replay = replay_policy(result, "AsAh,3c4c", "QsQh",
                               board=board, config=config)
        known = polar_metrics(serialized_profile(result))
        self.assertEqual(replay["world_count"], 2)
        for field, expected in zip(("value_oop", "oop_best_response_value",
                                    "ip_best_response_value"), known):
            self.assertAlmostEqual(replay[field], float(expected), delta=1e-9)
        self.assertAlmostEqual(replay["nash_conv"], float(known[1] + known[2]), delta=1e-9)
        self.assertTrue(compare_result(result, replay))

    def test_known_rational_equilibrium_profile_has_zero_gap(self):
        board = "2c7d9hJsKd"
        oop, ip = "AsAh,3c4c", "QsQh"
        config = RiverConfig(100, 500, (1.0,), (), 0, False)
        result = solve_matrix_free_river(board, oop, ip, config,
                                         iterations=10, algorithm="vanilla")
        profile, known_value = polar_equilibrium()
        anchored = deepcopy(result)
        for row in anchored["strategy"]:
            player = 0 if row["player"] == "oop" else 1
            label = ("nuts" if row["hand"] == "AhAs" else
                     "air" if row["hand"] == "3c4c" else "catcher")
            history = tuple(token.split("@")[0] for token in row["history"])
            key = (player, label, history)
            expected = profile[key]
            names = tuple(action["name"] for action in row["actions"])
            canonical = ("check", "bet") if "check" in names else ("fold", "call")
            for action, name in zip(row["actions"], names):
                action["probability"] = float(expected[canonical.index(name)])
        replay = replay_policy(anchored, oop, ip, board=board, config=config)
        self.assertAlmostEqual(replay["value_oop"], float(known_value), delta=1e-9)
        self.assertAlmostEqual(replay["nash_conv"], 0.0, delta=1e-9)
        self.assertAlmostEqual(replay["exploitability"], 0.0, delta=1e-9)

    def test_turn_weighted_blocker_replay_for_all_algorithms(self):
        board = "2c5d9hJc"
        oop = "AsAh:0.7,KsKh:0.3,QsQh:0.5"
        ip = "AsKc:0.2,AhKd:0.6,QcQd:1,TcTh:0.4"
        config = RiverConfig(20, (18, 32), (0.5,), (0.5,), 1, True)
        runouts = ("As", "Kc", "7s")
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                result = solve_matrix_free_turn(
                    board, oop, ip, config, runouts=runouts,
                    iterations=10, algorithm=algorithm,
                )
                replay = replay_policy(result, oop, ip, board=board,
                                       config=config, runouts=runouts)
                self.assertTrue(compare_result(result, replay, 1e-9))
                self.assertEqual(replay["world_count"], result["compatible_world_count"])
                self.assertAlmostEqual(sum(replay["river_probabilities"].values()), 1.0)
                self.assertGreater(max(replay["river_probabilities"].values()) -
                                   min(replay["river_probabilities"].values()), 0.0)

    def test_river_weighted_blocker_replay_for_all_algorithms_and_distinct_sizing(self):
        board = "2c7d9hJsKd"
        oop = "AsAh:0.7,KsKh:0.3,QsQh:0.5"
        ip = "AsKc:0.2,QcQd:1,TcTh:0.4"
        config = RiverConfig(17.3, (29.1, 41.7), (0.13, 0.37),
                             (0.41,), 1, True)
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                result = solve_matrix_free_river(
                    board, oop, ip, config, iterations=10, algorithm=algorithm,
                )
                replay = replay_policy(result, oop, ip, board=board, config=config)
                self.assertTrue(compare_result(result, replay, 1e-9))

    def test_turn_all_in_calls_continue_to_river_without_river_decisions(self):
        board = "2c5d9hJc"
        oop, ip = "AsAh", "KsKh"
        config = RiverConfig(20, (5, 10), (0.5,), (), 0, True)
        result = solve_matrix_free_turn(board, oop, ip, config,
                                        iterations=10, algorithm="vanilla")
        replay = replay_policy(result, oop, ip, board=board, config=config)
        self.assertTrue(compare_result(result, replay))
        self.assertEqual(replay["worlds"], 44)
        self.assertFalse(any(row["street"] == "river" and
                             row["history"][:1] == ["all_in@5"]
                             for row in result["strategy"]))

    def test_turn_replay_with_distinct_decimal_river_sizing(self):
        board = "2c5d9hJc"
        oop, ip = "AsAh,KsKh", "QcQd,TcTh"
        config = RiverConfig(17.3, (29.1, 41.7), (0.13, 0.37), (0.41,), 1, True)
        river = RiverConfig(17.3, (29.1, 41.7), (0.23, 0.61), (0.17,), 1, True)
        result = solve_matrix_free_turn(
            board, oop, ip, config, river_config=river,
            runouts=("As", "Kc", "7s"), iterations=10, algorithm="dcfr",
        )
        replay = replay_policy(result, oop, ip, board=board,
                               config=config, river_config=river,
                               runouts=("As", "Kc", "7s"))
        self.assertTrue(compare_result(result, replay))

    def test_short_all_in_raise_does_not_reopen_action(self):
        board = "2c7d9hJsKd"
        oop, ip = "AsAh", "QcQh"
        config = RiverConfig(100, (100, 15), (0.1,), (1.0,), 2, True)
        result = solve_matrix_free_river(board, oop, ip, config,
                                         iterations=10, algorithm="vanilla")
        replay = replay_policy(result, oop, ip, board=board, config=config)
        self.assertTrue(compare_result(result, replay))
        row = next(row for row in result["strategy"]
                   if row["player"] == "oop" and
                   row["history"] == ["bet@10", "all_in@15"])
        self.assertEqual([action["name"] for action in row["actions"]], ["fold", "call"])

    def test_orphan_private_hands_are_checked_only_on_supported_river_prefixes(self):
        board = "2c5d9hJc"
        oop, ip = "AsAh,KsKh", "AsKc,KdTc"
        config = RiverConfig(20, 40, (0.5,), (), 0, False)
        runouts = ("Kd", "Kh")
        result = solve_matrix_free_turn(board, oop, ip, config,
                                        runouts=runouts, iterations=10,
                                        algorithm="vanilla")
        replay = replay_policy(result, oop, ip, board=board,
                               config=config, runouts=runouts)
        self.assertTrue(compare_result(result, replay))
        as_ah = [row for row in result["strategy"] if row["player"] == "oop" and
                 row["hand"] == "AhAs" and row["street"] == "river"]
        ks_kh = [row for row in result["strategy"] if row["player"] == "oop" and
                 row["hand"] == "KhKs" and row["street"] == "river"]
        self.assertEqual({row["board"][-1] for row in as_ah}, {"Kh"})
        self.assertEqual({row["board"][-1] for row in ks_kh}, {"Kd"})

    def test_turn_best_response_sums_hidden_rivers_before_maximizing(self):
        worlds = [
            {"hands": (("As", "Ah"), ("Ks", "Kh")), "river": "2s",
             "weight": Fraction(1, 2), "sign": 1},
            {"hands": (("As", "Ah"), ("Ks", "Kh")), "river": "3s",
             "weight": Fraction(1, 2), "sign": -1},
        ]
        left = _Chance((), {
            "2s": _Terminal("fold", (0.0, 0.0), 0),
            "3s": _Terminal("fold", (0.0, 0.0), 1),
        })
        right = _Chance((), {
            "2s": _Terminal("fold", (0.0, 0.0), 1),
            "3s": _Terminal("fold", (0.0, 0.0), 0),
        })
        root = _Decision(0, (), (), (None, None), (left, right))
        self.assertEqual(_best_response(root, worlds, {}, 0, 2.0), 0.0)

    def test_materialized_turn_result_replays_against_same_independent_oracle(self):
        board = "2c5d9hJc"
        oop, ip = "AsAh:0.7,KsKh:0.3", "AsKc:0.2,QcQd:1"
        config = RiverConfig(30, (28, 37), (0.37,), (0.41,), 1, True)
        runouts = ("As", "Kc", "7s")
        result = solve_postflop(
            board, oop, ip, config, runouts=runouts, iterations=10,
            algorithm="dcfr", traversal="public-batched",
            diagnostics="public-batched",
        )
        replay = replay_policy(result, oop, ip, board=board,
                               config=config, runouts=runouts)
        self.assertTrue(compare_result(result, replay, 1e-9))

    def test_full_deck_single_pair_has_all_44_legal_rivers(self):
        board = "2c5d9hJc"
        oop, ip = "AsAh", "KsKh"
        config = RiverConfig(10, 20, (0.5,), (), 0, False)
        result = solve_matrix_free_turn(board, oop, ip, config,
                                        iterations=10, algorithm="vanilla")
        replay = replay_policy(result, oop, ip, board=board, config=config)
        self.assertEqual(replay["world_count"], 44)
        self.assertEqual(len(replay["river_probabilities"]), 44)
        self.assertTrue(all(abs(value - 1 / 44) < 1e-15
                            for value in replay["river_probabilities"].values()))
        self.assertTrue(compare_result(result, replay))

    def test_tiny_policy_best_responses_match_exhaustive_pure_rows(self):
        board = "2c7d9hJsKd"
        oop, ip = "AsAh,3c4c", "QsQh"
        config = RiverConfig(20, 40, (0.5,), (), 0, False)
        result = solve_matrix_free_river(board, oop, ip, config,
                                         iterations=10, algorithm="vanilla")
        baseline = replay_policy(result, oop, ip, board=board, config=config)
        for player, target in (("oop", "oop_best_response_value"),
                               ("ip", "ip_best_response_value")):
            rows = [index for index, row in enumerate(result["strategy"])
                    if row["player"] == player]
            action_counts = [len(result["strategy"][index]["actions"]) for index in rows]
            values = []
            for choices in product(*(range(count) for count in action_counts)):
                changed = deepcopy(result)
                for index, selected in zip(rows, choices):
                    actions = changed["strategy"][index]["actions"]
                    actions[:] = [dict(action, probability=float(i == selected))
                                  for i, action in enumerate(actions)]
                values.append(replay_policy(changed, oop, ip, board=board,
                                            config=config)["value_oop"])
            expected = max(values) if player == "oop" else -min(values)
            self.assertAlmostEqual(baseline[target], expected, delta=1e-9)

    def test_rejects_policy_and_metric_corruption(self):
        board = "2c5d9hJc"
        oop, ip = "AsAh", "KsKh"
        config = RiverConfig(10, 20, (0.5,), (), 0, False)
        result = solve_matrix_free_turn(board, oop, ip, config,
                                        runouts=("3c",), iterations=10,
                                        algorithm="vanilla")
        replay = replay_policy(result, oop, ip, board=board, config=config,
                               runouts=("3c",))
        mutations = []
        corrupt = deepcopy(result); corrupt["strategy"].pop(); mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"].append(deepcopy(corrupt["strategy"][0])); mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["board"] = ["As"]; mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["street"] = "flop"; mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["history"] = ["future@3c"]; mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["future_card"] = "3c"; mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["actions"].reverse(); mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["actions"][0]["name"] = "future_card"; mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["actions"][0]["amount"] = True; mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["actions"][0]["raise_to"] += 1; mutations.append(corrupt)
        corrupt = deepcopy(result); corrupt["strategy"][0]["actions"][0]["history_key"] = "future@3c"; mutations.append(corrupt)
        for bad_probability in (2.0, 1.1, -0.1, float("nan"), float("inf")):
            corrupt = deepcopy(result)
            corrupt["strategy"][0]["actions"][0]["probability"] = bad_probability
            mutations.append(corrupt)
        for corrupt in mutations:
            with self.subTest(corrupt=corrupt["strategy"][0]):
                with self.assertRaises(ValueError):
                    replay_policy(corrupt, oop, ip, board=board, config=config,
                                  runouts=("3c",))
        corrupt = deepcopy(result)
        corrupt["value_oop"] += 0.01
        with self.assertRaises(ValueError):
            compare_result(corrupt, replay)
        corrupt = deepcopy(result)
        corrupt["nash_conv"] = float("nan")
        with self.assertRaises(ValueError):
            compare_result(corrupt, replay)


if __name__ == "__main__":
    unittest.main()
