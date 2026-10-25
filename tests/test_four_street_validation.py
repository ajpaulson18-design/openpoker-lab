"""Bounded independent four-street support, row and replay controls."""
import copy
import json
from pathlib import Path
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from scripts import four_street_validation as validation


CASE = {
    "id": "four-street-weighted-shared-future-v1",
    "sb_range": "AsAd:0.5,QsQd:0.25",
    "bb_range": "KsKd:0.75,JhJd:0.25",
    "config": {"starting_stack": 8, "small_blind": 0.5, "big_blind": 1,
                "raise_sizes": [0.5], "max_raises": 1, "include_all_in": False},
    "runouts": ["2c3c4d7h8h", "2c3c4d7hKc", "2c3c4dKc8h",
                "2c3c4dQd8h", "5c6d7s8c9h", "5c6d7s8cJc"],
    "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                     "max_raises": 0, "include_all_in": False},
    "turn_config": None,
    "river_config": None,
}


def _uniform_payload(model):
    payload = _payload_metadata(model)
    for (player, hand, history), node in sorted(model.expected_infos.items()):
        street = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(node.board)]
        probability = 1 / len(node.actions)
        payload["strategy"].append({
            "player": "sb" if player == 0 else "bb", "hand": hand,
            "street": street, "revealed_board": list(node.board),
            "history": list(history),
            "actions": [{"name": action.name, "amount": action.amount,
                         "raise_to": action.raise_to, "history_key": action.token,
                         "probability": probability}
                        for action in node.actions],
        })
    return payload


def _prescribed_payload(model, chooser):
    payload = _payload_metadata(model)
    for (player, hand, history), node in sorted(model.expected_infos.items()):
        street = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(node.board)]
        chosen = chooser(player, hand, history, node.actions)
        payload["strategy"].append({
            "player": "sb" if player == 0 else "bb", "hand": hand,
            "street": street, "revealed_board": list(node.board),
            "history": list(history),
            "actions": [{"name": action.name, "amount": action.amount,
                         "raise_to": action.raise_to, "history_key": action.token,
                         "probability": 1.0 if index == chosen else 0.0}
                        for index, action in enumerate(node.actions)],
        })
    return payload


def _payload_metadata(model):
    outcomes = validation._case_inputs(model.case)[6]
    pair_rows = model.counts["pair_probabilities"]
    return {
        "solver_version": "preflop-strategy-v1",
        "strategy_schema": "preflop-strategy-v1",
        "runout_mode": "conditioned-ordered-selected-runouts",
        "selected_runouts": [list(outcome) for outcome in outcomes],
        "reachable_runouts": [list(outcome) for outcome in outcomes
                               if any(world["board"] == outcome for world in model.worlds)],
        "worlds": model.counts["worlds"],
        "compatible_private_pairs": model.counts["compatible_pairs"],
        "info_sets": model.counts["infos"],
        "private_pair_probabilities": [
            {"sb_hand": row["sb_hand"], "bb_hand": row["bb_hand"],
             "probability": float(validation.Fraction(row["fraction"]))}
            for row in pair_rows
        ],
        "strategy": [],
    }


def _check_call_choice(_player, _hand, _history, actions):
    names = [action.name for action in actions]
    return names.index("check") if "check" in names else (
        names.index("call") if "call" in names else names.index("fold") if "fold" in names else 0)


def _river_case(sb_range="AsAd:0.5,QsQd:0.25"):
    return {**CASE, "id": CASE["id"] + "-river-control", "sb_range": sb_range}


def _fractional_boundary_case():
    path = Path(__file__).resolve().parents[1] / "benchmarks" / "preflop-rounding-boundary-v1.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    return {"id": record["fixture_id"], "sb_range": record["sb"], "bb_range": record["bb"],
            "config": record["config"], "runouts": record["runouts"],
            "flop_config": record["flop_config"], "turn_config": record["turn_config"],
            "river_config": record["river_config"]}


class FourStreetValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = validation.build_model(CASE)
        cls.payload = _uniform_payload(cls.model)

    def test_literal_case_matches_physical_and_graph_anchors(self):
        counts = self.model.counts
        self.assertEqual(counts["worlds"], 22)
        self.assertEqual(counts["public_states"], 1414)
        self.assertEqual(counts["decisions"], 628)
        self.assertEqual(counts["infos"], 1200)
        self.assertEqual(counts["slots"], 2402)
        self.assertEqual({(row["sb_hand"], row["bb_hand"]): validation.Fraction(row["fraction"])
                          for row in counts["pair_probabilities"]}, {
            ("AdAs", "KdKs"): validation.Fraction(36, 68),
            ("AdAs", "JdJh"): validation.Fraction(12, 68),
            ("QdQs", "KdKs"): validation.Fraction(15, 68),
            ("QdQs", "JdJh"): validation.Fraction(5, 68),
        })
        self.assertEqual(json.loads(json.dumps(counts)), counts)

    def test_complete_uniform_policy_replays_with_numeric_counts(self):
        checked = validation.validate_policy(self.model, self.payload)
        self.assertEqual(len(checked), 1200)
        replay = validation.replay_policy(self.payload, CASE)
        self.assertEqual(replay["worlds"], 22)
        self.assertEqual(replay["numeric_counts"], self.model.counts)
        for metric in ("value_sb", "value_bb", "sb_best_response_value",
                       "bb_best_response_value", "nash_conv"):
            self.assertIn(metric, replay)

    def test_model_snapshots_nested_case_inputs(self):
        case = copy.deepcopy(CASE)
        model = validation.build_model(case)
        case["config"]["raise_sizes"].append(0.75)
        case["runouts"].clear()
        case["flop_config"]["bet_sizes"].append(0.25)
        self.assertEqual(len(model.case["runouts"]), 6)
        self.assertEqual(model.case["config"]["raise_sizes"], (0.5,))
        self.assertEqual(model.case["flop_config"]["bet_sizes"], (0.5,))

    def test_rows_merge_hidden_worlds_and_retain_zero_reach_rows(self):
        # Every support world contributes to one public graph.  A row key has
        # actor, own hand and history only; no hidden future card appears.
        self.assertEqual(len(self.model.expected_infos), 1200)
        self.assertTrue(any(len(history) and history[-1].startswith("river@")
                            for _, _, history in self.model.expected_infos))
        self.assertEqual(len(validation.validate_policy(self.model, self.payload)), 1200)

    def test_rejects_duplicate_missing_extra_and_actor_rows(self):
        duplicate = copy.deepcopy(self.payload)
        duplicate["strategy"][1] = copy.deepcopy(duplicate["strategy"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validation.validate_policy(self.model, duplicate)
        missing = copy.deepcopy(self.payload)
        missing["strategy"].pop()
        with self.assertRaisesRegex(ValueError, "row count"):
            validation.validate_policy(self.model, missing)
        extra = copy.deepcopy(self.payload)
        bad = copy.deepcopy(extra["strategy"][0])
        bad["history"].append("check")
        extra["strategy"].append(bad)
        with self.assertRaisesRegex(ValueError, "row count"):
            validation.validate_policy(self.model, extra)
        actor = copy.deepcopy(self.payload)
        actor["strategy"][0]["player"] = "unknown"
        with self.assertRaisesRegex(ValueError, "actor"):
            validation.validate_policy(self.model, actor)

    def test_rejects_malformed_scope_counts_chance_and_pair_mass_metadata(self):
        for field, value, match in (
            ("strategy_schema", "wrong-v1", "schema"),
            ("runout_mode", "full-deck", "runout mode"),
            ("worlds", 21, "world count"),
            ("info_sets", 1199, "information-set count"),
            ("postflop_scope", "flop-checkdown", "all four streets"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.payload)
                changed[field] = value
                with self.assertRaisesRegex(ValueError, match):
                    validation.validate_policy(self.model, changed)
        changed = copy.deepcopy(self.payload)
        changed["private_pair_probabilities"][0]["probability"] += 0.01
        with self.assertRaisesRegex(ValueError, "pair mass"):
            validation.validate_policy(self.model, changed)
        changed = copy.deepcopy(self.payload)
        changed["selected_runouts"].pop()
        with self.assertRaisesRegex(ValueError, "selected runouts"):
            validation.validate_policy(self.model, changed)

    def test_rejects_reveal_history_and_whole_hand_amount_corruption(self):
        changed = copy.deepcopy(self.payload)
        postflop = next(row for row in changed["strategy"] if row["street"] == "flop")
        postflop["revealed_board"][0] = "As"
        with self.assertRaisesRegex(ValueError, "incorrect board"):
            validation.validate_policy(self.model, changed)
        changed = copy.deepcopy(self.payload)
        sized = next(action for row in changed["strategy"] for action in row["actions"]
                     if action["name"] in ("bet", "raise", "all_in"))
        sized["raise_to"] += 1
        with self.assertRaisesRegex(ValueError, "raise_to"):
            validation.validate_policy(self.model, changed)

    def test_rejects_bad_probabilities_and_unbounded_inputs_before_ranking(self):
        changed = copy.deepcopy(self.payload)
        changed["strategy"][0]["actions"][0]["probability"] = float("nan")
        with self.assertRaisesRegex(ValueError, "probability"):
            validation.validate_policy(self.model, changed)
        too_many = dict(CASE, runouts=CASE["runouts"] + ["2c3c4d9sTh"] * 3)
        with self.assertRaisesRegex(ValueError, "runouts"):
            validation.build_model(too_many)
        with patch.object(validation.legacy, "independent_rank",
                          side_effect=RuntimeError("rank must not be reached")):
            with self.assertRaisesRegex(ValueError, "runouts"):
                validation.build_model(too_many)
            invalid_numeric = copy.deepcopy(CASE)
            invalid_numeric["config"]["small_blind"] = True
            with self.assertRaisesRegex(ValueError, "small_blind"):
                validation.build_model(invalid_numeric)
            invalid_numeric = copy.deepcopy(CASE)
            invalid_numeric["config"]["starting_stack"] = "8"
            with self.assertRaisesRegex(ValueError, "starting_stack"):
                validation.build_model(invalid_numeric)
            invalid_numeric = copy.deepcopy(CASE)
            invalid_numeric["config"]["starting_stack"] = float("inf")
            with self.assertRaisesRegex(ValueError, "starting_stack"):
                validation.build_model(invalid_numeric)
            invalid_numeric = copy.deepcopy(CASE)
            invalid_numeric["config"]["small_blind"] = 0.5
            invalid_numeric["config"]["big_blind"] = 0.5
            with self.assertRaisesRegex(ValueError, "blinds and their difference"):
                validation.build_model(invalid_numeric)
            invalid_numeric = copy.deepcopy(CASE)
            invalid_numeric["flop_config"]["bet_sizes"] = [True]
            with self.assertRaisesRegex(ValueError, "bet_sizes"):
                validation.build_model(invalid_numeric)
        small_pot = copy.deepcopy(CASE)
        small_pot["config"].update(small_blind=0.002, big_blind=0.004)
        with self.assertRaisesRegex(ValueError, "pot must be within 0.01"):
            validation.build_model(small_pot)
        short_boundary = copy.deepcopy(CASE)
        short_boundary["config"]["starting_stack"] = [2, 1.005]
        with self.assertRaisesRegex(ValueError, "continuation stacks"):
            validation.build_model(short_boundary)

    def test_bounded_text_and_physical_admission_precede_parsing_and_indexing(self):
        with patch.object(validation, "cards",
                          side_effect=RuntimeError("card parser must not be reached")), \
             patch.object(validation, "expand_range",
                          side_effect=RuntimeError("range parser must not be reached")), \
             patch.object(validation.legacy, "independent_rank",
                          side_effect=RuntimeError("ranker must not be reached")):
            oversized = copy.deepcopy(CASE)
            oversized["id"] = "x" * (validation.MAX_CASE_ID_LENGTH + 1)
            with self.assertRaisesRegex(ValueError, "case id exceeds"):
                validation.build_model(oversized)
            oversized = copy.deepcopy(CASE)
            oversized["sb_range"] = "x" * (validation.MAX_RANGE_EXPRESSION_LENGTH + 1)
            with self.assertRaisesRegex(ValueError, "range expression"):
                validation.build_model(oversized)
            oversized = copy.deepcopy(CASE)
            oversized["runouts"] = ["x" * (validation.MAX_RUNOUT_STRING_LENGTH + 1)]
            with self.assertRaisesRegex(ValueError, "runout string"):
                validation.build_model(oversized)

        base_row = {"player": "sb", "hand": "AdAs", "street": "river",
                    "revealed_board": [], "history": [], "actions": []}
        with self.assertRaisesRegex(ValueError, "four characters"):
            validation._row_key({**base_row, "hand": "A" * 5})
        with self.assertRaisesRegex(ValueError, "history exceeds"):
            validation._row_key({**base_row, "history": ["x"] *
                                 (validation.MAX_ROW_HISTORY + 1)})
        with self.assertRaisesRegex(ValueError, "token exceeds"):
            validation._row_key({**base_row, "history": [
                "x" * (validation.MAX_HISTORY_TOKEN_LENGTH + 1)]})

        with patch.object(validation, "MAX_WORLDS", 1):
            with self.assertRaisesRegex(ValueError, "physical world support"):
                validation._physical_support(
                    (validation.expand_range("AsAd"), validation.expand_range("KsKd")),
                    (("2c", "3c", "4d", "7h", "8h"),
                     ("2c", "3c", "4d", "7h", "9h")))

    def test_fixed_policy_river_change_updates_whole_game_and_conditional_value(self):
        model = self.model
        base = _prescribed_payload(model, _check_call_choice)
        baseline = validation.replay_policy(base, CASE)
        target_board = ("2c", "3c", "4d", "7h", "8h")
        target_history = ("call", "check", "flop@2c3c4d", "check", "check",
                          "turn@7h", "check", "check", "river@8h", "check")
        target = next(row for row in base["strategy"]
                      if row["player"] == "sb" and row["hand"] == "AdAs" and
                      tuple(row["revealed_board"]) == target_board and
                      tuple(row["history"]) == target_history)
        bet_index = next(i for i, action in enumerate(target["actions"])
                         if action["name"] == "bet")
        self.assertEqual(target["actions"][bet_index]["amount"], 1.0)
        self.assertEqual(target["actions"][bet_index]["raise_to"], 2.0)
        target["actions"] = [dict(action, probability=1.0 if i == bet_index else 0.0)
                             for i, action in enumerate(target["actions"])]
        changed = validation.replay_policy(base, CASE)
        self.assertAlmostEqual(baseline["value_sb"], 1 / 34, places=12)
        self.assertAlmostEqual(changed["value_sb"], 5 / 34, places=12)
        self.assertAlmostEqual(changed["value_sb"] - baseline["value_sb"], 2 / 17, places=12)

        # Restricting SB to AA makes the value at its root call conditional on
        # that own hand; no opponent/future information is added to a row.
        conditional_case = _river_case("AsAd:0.5")
        conditional_model = validation.build_model(conditional_case)
        conditional_base = _prescribed_payload(conditional_model, _check_call_choice)
        before = validation.replay_policy(conditional_base, conditional_case)
        row = next(row for row in conditional_base["strategy"]
                   if row["player"] == "sb" and tuple(row["revealed_board"]) == target_board and
                   tuple(row["history"]) == target_history)
        chosen = next(i for i, action in enumerate(row["actions"]) if action["name"] == "bet")
        row["actions"] = [dict(action, probability=1.0 if i == chosen else 0.0)
                           for i, action in enumerate(row["actions"])]
        after = validation.replay_policy(conditional_base, conditional_case)
        self.assertAlmostEqual(before["value_sb"], 1 / 4, places=12)
        self.assertAlmostEqual(after["value_sb"], 5 / 12, places=12)
        self.assertAlmostEqual(after["value_sb"] - before["value_sb"], 1 / 6, places=12)

    def test_exact_hand_dependent_reach_preserves_joint_blocker_correlation(self):
        case = {
            "id": "four-street-asymmetric-reach-control",
            "sb_range": "AsAd:1,AhAc:0.25", "bb_range": "KsKd:1,KcKh:0.5",
            "config": {"starting_stack": 8, "small_blind": 0.5, "big_blind": 1,
                        "raise_sizes": [0.5], "max_raises": 1,
                        "include_all_in": False},
            "runouts": ["2c3c4d7h8h", "Kc2d3h7s8c", "Ac2d3h7s8c"],
            "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                             "max_raises": 0, "include_all_in": False},
            "turn_config": None, "river_config": None,
        }
        model = validation.build_model(case)
        self.assertEqual({(row["sb_hand"], row["bb_hand"]): validation.Fraction(row["fraction"])
                          for row in model.counts["pair_probabilities"]}, {
            ("AdAs", "KdKs"): validation.Fraction(24, 37),
            ("AdAs", "KcKh"): validation.Fraction(8, 37),
            ("AcAh", "KdKs"): validation.Fraction(4, 37),
            ("AcAh", "KcKh"): validation.Fraction(1, 37),
        })

        def chooser(player, hand, history, actions):
            names = [action.name for action in actions]
            if player == 0 and not history:
                return names.index("call") if hand == "AdAs" else names.index("fold")
            if player == 1 and history == ("call",):
                return names.index("check")
            return _check_call_choice(player, hand, history, actions)

        payload = _prescribed_payload(model, chooser)
        # Replace only the two hand-dependent mixed rows: SB limps at 1/2 for
        # the second hand; BB checks at 1/2 for the second hand.
        for row in payload["strategy"]:
            if row["player"] == "sb" and row["history"] == [] and row["hand"] == "AcAh":
                call = next(i for i, a in enumerate(row["actions"]) if a["name"] == "call")
                row["actions"] = [dict(a, probability=0.5 if i == call else
                                        (0.5 if a["name"] == "fold" else 0.0))
                                  for i, a in enumerate(row["actions"])]
            if row["player"] == "bb" and row["history"] == ["call"] and row["hand"] == "KcKh":
                check = next(i for i, a in enumerate(row["actions"]) if a["name"] == "check")
                raise_index = next(i for i, a in enumerate(row["actions"]) if a["name"] == "raise")
                row["actions"] = [dict(a, probability=0.5 if i in (check, raise_index) else 0.0)
                                  for i, a in enumerate(row["actions"])]
        policy = validation.validate_policy(model, payload)
        by_pair = {}
        for world in model.worlds:
            sb, bb = ("".join(hand) for hand in world["hands"])
            sb_row = policy[(0, sb, ())]
            root_node = model.expected_infos[(0, sb, ())]
            sb_call = sb_row[next(i for i, a in enumerate(root_node.actions) if a.name == "call")]
            bb_key = (1, bb, ("call",))
            bb_node = model.expected_infos[bb_key]
            bb_row = policy[bb_key]
            bb_check = bb_row[next(i for i, a in enumerate(bb_node.actions) if a.name == "check")]
            by_pair[(sb, bb)] = by_pair.get((sb, bb), validation.Fraction(0)) + \
                world["weight"] * validation.Fraction.from_float(sb_call) * \
                validation.Fraction.from_float(bb_check)
        reached = sum(by_pair.values(), validation.Fraction(0))
        self.assertEqual(reached, validation.Fraction(121, 148))
        posterior = {pair: mass / reached for pair, mass in by_pair.items()}
        expected = {("AdAs", "KdKs"): validation.Fraction(96, 121),
                    ("AdAs", "KcKh"): validation.Fraction(16, 121),
                    ("AcAh", "KdKs"): validation.Fraction(8, 121),
                    ("AcAh", "KcKh"): validation.Fraction(1, 121)}
        self.assertEqual(posterior, expected)
        true_joint = posterior[("AdAs", "KdKs")]
        sb_marginal = sum(m for (sb, _), m in posterior.items() if sb == "AdAs")
        bb_marginal = sum(m for (_, bb), m in posterior.items() if bb == "KdKs")
        factorized = sb_marginal * bb_marginal
        self.assertEqual(true_joint, validation.Fraction(11616, 14641))
        self.assertEqual(factorized, validation.Fraction(11648, 14641))
        self.assertEqual(true_joint - factorized, validation.Fraction(-32, 14641))

    def test_hand_computable_known_value_bounds_and_hidden_future_control(self):
        sure_win = {
            **CASE, "id": "sure-win-four-street-control", "sb_range": "AsAd:1",
            "bb_range": "KsKd:1", "runouts": ["2c3c4d7h8h"],
        }
        model = validation.build_model(sure_win)
        check_call = _prescribed_payload(model, _check_call_choice)
        metrics = validation.replay_policy(check_call, sure_win)
        self.assertAlmostEqual(metrics["value_sb"], 1.0, places=12)
        self.assertAlmostEqual(metrics["sb_best_response_value"], 8.0, places=12)
        self.assertAlmostEqual(metrics["bb_best_response_value"], -1.0, places=12)
        self.assertAlmostEqual(metrics["nash_conv"], 7.0, places=12)

        def fold_facing_bb(player, hand, history, actions):
            names = [action.name for action in actions]
            if player == 1 and "fold" in names and "call" in names:
                return names.index("fold")
            return _check_call_choice(player, hand, history, actions)
        no_bluff = _prescribed_payload(model, fold_facing_bb)
        no_bluff_metrics = validation.replay_policy(no_bluff, sure_win)
        self.assertAlmostEqual(no_bluff_metrics["value_sb"], 1.0, places=12)
        self.assertAlmostEqual(no_bluff_metrics["sb_best_response_value"], 1.0, places=12)
        self.assertAlmostEqual(no_bluff_metrics["bb_best_response_value"], -1.0, places=12)
        self.assertAlmostEqual(no_bluff_metrics["nash_conv"], 0.0, places=12)

        hidden = {
            "id": "hidden-flop-adversarial-control", "sb_range": "AsAd:1",
            "bb_range": "KsKd:1",
            "config": {"starting_stack": [2, 1], "small_blind": 0.5,
                        "big_blind": 1, "max_raises": 0},
            "runouts": ["2c3c4d7h8h", "Kc2d3h7s8c"],
            "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                             "max_raises": 0, "include_all_in": False},
            "turn_config": None, "river_config": None,
        }
        hidden_model = validation.build_model(hidden)

        hidden_payload = _prescribed_payload(hidden_model, _check_call_choice)
        root_row = next(row for row in hidden_payload["strategy"]
                        if row["player"] == "sb" and row["history"] == [])
        fold = next(i for i, a in enumerate(root_row["actions"]) if a["name"] == "fold")
        call = next(i for i, a in enumerate(root_row["actions"]) if a["name"] == "call")
        root_row["actions"] = [dict(a, probability=0.5 if i in (fold, call) else 0.0)
                               for i, a in enumerate(root_row["actions"])]
        hidden_metrics = validation.replay_policy(hidden_payload, hidden)
        self.assertAlmostEqual(hidden_metrics["value_sb"], -0.25, places=12)
        self.assertAlmostEqual(hidden_metrics["sb_best_response_value"], 0.0, places=12)
        self.assertAlmostEqual(hidden_metrics["bb_best_response_value"], 0.25, places=12)
        clairvoyant_sb = 0.5 * 1.0 + 0.5 * -0.5
        self.assertAlmostEqual(clairvoyant_sb, 0.25, places=12)
        self.assertGreater(clairvoyant_sb, hidden_metrics["sb_best_response_value"])

    def test_short_blind_refund_and_fractional_local_boundary(self):
        short = {"id": "short-blind-refund-control", "sb_range": "AsAd:1",
                 "bb_range": "KsKd:1",
                 "config": {"starting_stack": [0.5, 20], "small_blind": 0.5,
                            "big_blind": 1, "max_raises": 0},
                 "runouts": ["2c3c4d7h8h"],
                 "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                                 "max_raises": 0, "include_all_in": False},
                 "turn_config": None, "river_config": None}
        short_model = validation.build_model(short)
        short_payload = _payload_metadata(short_model)
        short_payload["strategy"] = []
        short_metrics = validation.replay_policy(short_payload, short)
        self.assertEqual(short_model.counts["decisions"], 0)
        self.assertAlmostEqual(short_metrics["value_sb"], 0.5, places=12)
        self.assertAlmostEqual(short_metrics["sb_best_response_value"], 0.5, places=12)
        self.assertAlmostEqual(short_metrics["bb_best_response_value"], -0.5, places=12)

        fractional = _fractional_boundary_case()
        fractional_model = validation.build_model(fractional)
        fractional_payload = _prescribed_payload(fractional_model, _check_call_choice)
        fractional_metrics = validation.replay_policy(fractional_payload, fractional)
        self.assertEqual(fractional_metrics["numeric_counts"], fractional_model.counts)
        self.assertAlmostEqual(fractional_metrics["value_sb"],
                               fractional_metrics["value_bb"], places=12)
        row = next(row for row in fractional_payload["strategy"]
                   if row["history"] == ["raise@0.691357802", "call", "flop@2c3c4d",
                                         "check", "bet@0.862063431"] and
                   row["street"] == "flop")
        self.assertTrue(any(action["raise_to"] == 1.293095146 for action in row["actions"]))
        self.assertFalse(any(action["raise_to"] == 1.293095147 for action in row["actions"]))

    def test_quantized_live_boundary_accepts_complete_t10_production_result(self):
        benchmark = json.loads((Path(__file__).resolve().parents[1] /
                                "benchmarks" / "four-street-integration-v1.json")
                               .read_text(encoding="utf-8"))
        case = copy.deepcopy(benchmark["case"])
        case["sb_range"], case["bb_range"] = "AsAd", "KsKd"
        case["runouts"] = ["2c3c4d7h8h"]
        case["config"]["starting_stack"] = [2.01, 2.01]

        model = validation.build_model(case)
        self.assertEqual(len(model.worlds), 1)
        self.assertEqual(validation.legacy._money(2.01 - 2), 0.01)

        from pokerlab.preflop_solver import solve_preflop
        payload = solve_preflop(
            case["sb_range"], case["bb_range"], config=case["config"],
            runouts=case["runouts"], flop_config=case["flop_config"],
            turn_config=case["turn_config"], river_config=case["river_config"],
            iterations=10)
        self.assertEqual(len(validation.validate_policy(model, payload)),
                         model.counts["infos"])
        metrics = validation.replay_policy(payload, case)
        legacy_metrics = validation.legacy.replay_policy(
            payload, case["sb_range"], case["bb_range"], config=case["config"],
            runouts=case["runouts"], flop_config=case["flop_config"],
            turn_config=case["turn_config"], river_config=case["river_config"],
            monetary_mode="configured", postflop_scope="all-streets")
        for key in ("value_sb", "value_bb", "sb_best_response_value",
                    "bb_best_response_value", "nash_conv"):
            self.assertAlmostEqual(metrics[key], legacy_metrics[key], places=12)

        genuinely_short = copy.deepcopy(case)
        genuinely_short["config"]["starting_stack"] = [2.009, 2.009]
        with self.assertRaisesRegex(ValueError, "continuation stacks"):
            validation.build_model(genuinely_short)

    def test_numeric_replay_survives_production_solver_and_oracle_tripwires(self):
        tripwires = (
            "pokerlab.preflop_solver.solve_preflop",
            "pokerlab.preflop_solver._rank_world",
            "pokerlab.postflop_solver._build_public_tree",
            "pokerlab.cards.rank_hand",
            "pokerlab.cfr.evaluate",
            "pokerlab.cfr.best_response",
        )
        from importlib import import_module
        with ExitStack() as stack:
            for dotted in tripwires:
                module_name, _, attribute = dotted.rpartition(".")
                stack.enter_context(patch.object(
                    import_module(module_name), attribute,
                    side_effect=AssertionError(f"production authority called: {dotted}")))
            model = validation.build_model(CASE)
            payload = _uniform_payload(model)
            replay = validation.replay_policy(payload, CASE)
            self.assertEqual(replay["numeric_counts"]["worlds"], 22)


if __name__ == "__main__":
    unittest.main()
