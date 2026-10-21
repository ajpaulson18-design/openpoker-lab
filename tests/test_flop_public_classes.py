"""Focused no-training tests for the fixed full-deck flop class audit."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import math
import unittest
from collections import defaultdict
from unittest import mock

from scripts import flop_public_classes as classes
from scripts import flop_multistreet_validation as physical


class FlopPublicClassesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Build the independent model and all controls once under the guard.
        cls.payloads = {}
        cls.audits = {}
        with classes.independent_guard() as calls:
            cls.model = classes.build_model()
            for mode in ("check-call", "bet-fold", "class-varying", "zero-reach"):
                payload = classes.control_policy(cls.model, mode)
                cls.payloads[mode] = payload
                cls.audits[mode] = classes.audit_policy(payload, cls.model)
        cls.guard_calls = dict(calls)
        if any(cls.guard_calls.values()):
            raise AssertionError(f"no-training guard observed production calls: {cls.guard_calls}")

    def test_fixed_physical_and_compact_census(self):
        census = classes.validate_model(self.model)
        self.assertEqual(len(self.model.physical["worlds"]), 5_940)
        self.assertEqual(census["turn_classes"], 11)
        self.assertEqual(census["river_signatures"], 19)
        self.assertEqual(census["compact_worlds"], 126)
        self.assertEqual(census["compact_public_states"], 1_001)
        self.assertEqual(census["compact_decisions"], 316)
        self.assertEqual(census["compact_chance_nodes"], 58)
        self.assertEqual(census["compact_terminals"], 627)
        self.assertEqual(census["physical_nodes_checked"], 30_812)
        self.assertEqual(census["physical_branch_subtrees_compared"], 11_787)
        self.assertEqual(census["physical_policy_rows"], 16_912)
        self.assertEqual(census["compact_policy_rows"], 466)
        self.assertEqual(census["physical_action_slots"], 33_824)
        self.assertEqual(census["compact_action_slots"], 932)
        self.assertFalse(any(self.guard_calls.values()))

    def test_all_four_controls_replay_exactly_against_physical_game(self):
        for mode, audit in self.audits.items():
            with self.subTest(mode=mode):
                self.assertEqual(audit["exact_metric_count"], 8)
                self.assertEqual(audit["class_rows"], 466)
                self.assertEqual(audit["physical_rows_lifted"], 16_912)
                self.assertLessEqual(audit["maximum_numeric_gap"], 1e-10)
                self.assertTrue(math.isfinite(audit["maximum_numeric_gap"]))
                self.assertEqual(set(audit["exact_metrics"]), set(classes.METRICS))
                self.assertEqual(set(audit["independent_numeric_metrics"]), set(classes.METRICS))

    def test_check_call_and_bet_fold_have_closed_form_profile_values(self):
        check_metrics = {key: Fraction(value) for key, value in
                         self.audits["check-call"]["exact_metrics"].items()}
        expected_check = Fraction(602, 429)
        self.assertEqual(check_metrics["value_oop"], expected_check)
        physical_sum = sum((world[2] * world[3]
                            for world in self.model.physical["worlds"]), Fraction())
        self.assertEqual(Fraction(5) * physical_sum, expected_check)

        bet_metrics = {key: Fraction(value) for key, value in
                       self.audits["bet-fold"]["exact_metrics"].items()}
        self.assertEqual(bet_metrics["value_oop"], Fraction(5))

    def test_class_varying_control_uses_distinct_own_hand_history_rows(self):
        with classes.independent_guard() as calls:
            projected = classes.project_policy(self.payloads["class-varying"], self.model)
        self.assertFalse(any(calls.values()))
        self.assertEqual(len(projected), 466)
        self.assertGreater(len(set(projected.values())), 1)
        self.assertGreater(len({(player, hand, history) for player, hand, history in projected}),
                           len({(player, history) for player, hand, history in projected}))

    def test_class_varying_control_preserves_hidden_information_for_best_response(self):
        payload = self.payloads["class-varying"]
        rows = physical._validate_policy(payload, self.model.physical, 1e-10)
        worlds = self.model.physical["worlds"]
        comparisons = []
        with classes.independent_guard() as calls:
            for player in (0, 1):
                information_limited = physical._best_response(
                    self.model.physical["root"], worlds, rows, 10.0, player)
                clairvoyant = sum(
                    physical._best_response(self.model.physical["root"], [world],
                                            rows, 10.0, player)
                    for world in worlds)
                comparisons.append(abs(clairvoyant - information_limited))
        self.assertFalse(any(calls.values()))
        self.assertGreater(max(comparisons), 1e-9)

    def _mapped_policy_groups(self, payload):
        grouped = defaultdict(list)
        for row in payload["strategy"]:
            player = 0 if row["player"] == "oop" else 1
            mapped = classes._mapped_history(tuple(row["history"]),
                                             self.model.turns, self.model.rivers)
            grouped[(player, row["hand"], mapped)].append(row)
        return grouped

    @staticmethod
    def _flip_first_probability(row, reference_row):
        current = reference_row["actions"][0]["probability"]
        row["actions"][0]["probability"] = 0.0 if current == 1.0 else 1.0
        row["actions"][1]["probability"] = 1.0 - row["actions"][0]["probability"]

    def test_card_specific_and_zero_reach_class_deviations_are_rejected(self):
        payload = deepcopy(self.payloads["check-call"])
        group = next(rows for rows in self._mapped_policy_groups(payload).values()
                     if len(rows) > 1 and len(rows[0]["actions"]) == 2)
        self._flip_first_probability(group[0], group[1])
        with self.assertRaisesRegex(ValueError, "class-constant"):
            classes.project_policy(payload, self.model)

        zero_payload = deepcopy(self.payloads["zero-reach"])
        groups = self._mapped_policy_groups(zero_payload)
        # This fixture's flop bet is all-in, so its response branch has no
        # later decision rows. A turn/river facing-bet row is class-duplicated
        # and has zero reach because the all-first-action control never bets.
        zero_group = next(rows for rows in groups.values()
                          if len(rows) > 1 and rows[0]["street"] in ("turn", "river")
                          and rows[0]["actions"][0]["name"] == "fold")
        self._flip_first_probability(zero_group[0], zero_group[1])
        with self.assertRaisesRegex(ValueError, "class-constant"):
            classes.project_policy(zero_payload, self.model)

    def test_missing_extra_reordered_rows_and_invalid_probability_vectors_reject(self):
        original = self.payloads["check-call"]
        missing = deepcopy(original)
        missing["strategy"].pop()
        extra = deepcopy(original)
        extra["strategy"].append(deepcopy(extra["strategy"][0]))
        reordered = deepcopy(original)
        row = next(row for row in reordered["strategy"] if len(row["actions"]) == 2)
        row["actions"].reverse()
        invalid = []
        for value in (True, float("nan"), float("inf"), -0.1, 1.1):
            bad = deepcopy(original)
            first = next(row for row in bad["strategy"] if len(row["actions"]) == 2)
            first["actions"][0]["probability"] = value
            first["actions"][1]["probability"] = 1.0 - value if type(value) is float and math.isfinite(value) else 0.0
            invalid.append(bad)
        bad_sum = deepcopy(original)
        first = next(row for row in bad_sum["strategy"] if len(row["actions"]) == 2)
        first["actions"][0]["probability"] = 0.25
        first["actions"][1]["probability"] = 0.25
        invalid.append(bad_sum)
        for bad in (missing, extra, reordered, *invalid):
            with self.subTest(rows=len(bad["strategy"])), self.assertRaises((ValueError, TypeError)):
                classes.project_policy(bad, self.model)

    def test_fraction_bit_guard_rejects_when_bound_is_exceeded(self):
        payload = self.payloads["check-call"]
        with mock.patch.object(classes, "MAX_FRACTION_BITS", 1):
            with self.assertRaisesRegex(ValueError, "fraction bit bound"):
                classes.audit_policy(payload, self.model)

    def test_mutated_original_physical_world_mass_or_sign_rejects(self):
        for field in ("mass", "sign"):
            bad = deepcopy(self.model)
            worlds = list(bad.physical["worlds"])
            row = list(worlds[0])
            if field == "mass":
                row[2] += Fraction(1, 1_000_000)
            else:
                row[3] = -1 if row[3] != -1 else 1
            worlds[0] = tuple(row)
            bad.physical["worlds"] = tuple(worlds)
            with self.subTest(field=field), self.assertRaises(ValueError):
                classes.validate_model(bad)

    def test_mutated_class_world_mass_or_sign_rejects(self):
        for field in ("mass", "sign"):
            bad = deepcopy(self.model)
            row = bad.partition["class_worlds"][0]
            if field == "mass":
                row["mass"][0] += 1
            else:
                row["sign"] = -1 if row["sign"] != -1 else 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                classes.validate_model(bad)

    def test_mutated_partition_signature_turn_mass_or_transport_rejects(self):
        mutations = (
            ("signature", lambda model: model.partition["river_classes"][0]["signature"][0].__setitem__(
                "sign", -1 if model.partition["river_classes"][0]["signature"][0]["sign"] != -1 else 1)),
            ("turn mass", lambda model: model.partition["turn_classes"][0]["turn_mass_by_pair"][0]["mass"].__setitem__(
                0, model.partition["turn_classes"][0]["turn_mass_by_pair"][0]["mass"][0] + 1)),
            ("transport", lambda model: model.partition["turn_classes"][0]["river_transports"][0].__setitem__(
                "river", "As")),
        )
        for label, mutate in mutations:
            bad = deepcopy(self.model)
            mutate(bad)
            with self.subTest(field=label), self.assertRaises(ValueError):
                classes.validate_model(bad)

    def test_mutated_class_tree_action_terminal_or_visibility_rejects(self):
        def decision(model):
            return next(node for node in classes._walk(model.root)
                        if isinstance(node, physical._Decision))

        def terminal(model):
            return next(node for node in classes._walk(model.root)
                        if isinstance(node, physical._Terminal))

        mutations = (
            ("action", lambda model: decision(model).actions[0].__setitem__(
                "amount", decision(model).actions[0]["amount"] + 0.25)),
            ("terminal", lambda model: setattr(
                terminal(model), "contributions",
                (terminal(model).contributions[0] + 0.25,
                 terminal(model).contributions[1]))),
            ("visibility", lambda model: setattr(
                decision(model), "history", decision(model).history + ("turn@hidden",))),
        )
        for label, mutate in mutations:
            bad = deepcopy(self.model)
            mutate(bad)
            with self.subTest(field=label), self.assertRaises(ValueError):
                classes.validate_model(bad)


if __name__ == "__main__":
    unittest.main()
