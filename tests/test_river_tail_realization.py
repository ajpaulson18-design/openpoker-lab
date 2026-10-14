"""Independent exact proofs and adversarial checks for river tail conversion."""
from copy import deepcopy
from fractions import Fraction as F
import math
import unittest

from scripts.river_tail_realization import (
    REALIZATION_TOLERANCE,
    reconstruct_tail,
)


def _action(name, token, amount=0.0, raise_to=0.0):
    return {"name": name, "amount": amount, "raise_to": raise_to,
            "history_key": token, "probability": F(0)}


def _row(player, hand, history, action_specs, board=("2c", "7d", "9h", "Js", "Kd")):
    return {"player": player, "hand": hand, "street": "river",
            "board": list(board), "history": list(history),
            "actions": [_action(*spec) for spec in action_specs]}


def _average(probabilities, own_reaches, own_mass, iteration_count):
    weights = range(1, iteration_count + 1)
    denominator = sum((F(weight) * own_mass * own_reaches[index]
                       for index, weight in enumerate(weights)), F(0))
    return tuple(
        sum((F(weight) * own_mass * own_reaches[index] * probabilities[index][action]
             for index, weight in enumerate(range(1, iteration_count + 1))), F(0)) /
        denominator
        for action in range(len(probabilities[0]))
    )


def _independent_snapshots(*, include_hand_mass=True):
    """Build averages directly from iteration flows; no tail helper calls."""
    # Root probabilities for the first player. The specified A sequence gives
    # the exact after-A counterexample; C is reached in the prefix but not t=3.
    roots = {
        "H1": ((F(1, 5), F(3, 5), F(1, 5)),
               (F(4, 5), F(1, 10), F(1, 10)),
               (F(1, 2), F(1, 2), F(0))),
        "H2": ((F(1, 5), F(3, 5), F(1, 5)),
               (F(4, 5), F(1, 10), F(1, 10)),
               (F(1, 2), F(1, 2), F(0))),
    }
    branch_x = {
        ("H1", "A"): (F(9, 10), F(1, 10), F(7, 10)),
        ("H2", "A"): (F(3, 10), F(4, 10), F(1, 5)),
        ("H1", "C"): (F(3, 10), F(8, 10), F(6, 10)),
        ("H2", "C"): (F(2, 10), F(7, 10), F(4, 10)),
    }
    opponent_l = (F(1, 10), F(9, 10), F(1, 5))
    opponent_l_after_c = (F(7, 10), F(2, 10), F(9, 10))
    chance_l = (F(1, 3), F(2, 3), F(1, 4))
    masses = {"H1": F(1, 5), "H2": F(4, 5), "IP": F(1, 3)}

    def rows_at(iteration_count):
        rows = []
        for hand in ("H1", "H2"):
            mass = masses[hand] if include_hand_mass else F(1)
            root_profiles = roots[hand][:iteration_count]
            root_avg = _average(root_profiles,
                                (F(1),) * iteration_count, mass, iteration_count)
            root_row = _row("oop", hand, (), (("a", "A", 0.0, 0.0),
                                                 ("b", "B", 0.0, 0.0),
                                                 ("c", "C", 0.0, 0.0)))
            for action, probability in zip(root_row["actions"], root_avg):
                action["probability"] = probability
            rows.append(root_row)

            for branch, opponent_profile, chance_token in (
                    ("A", opponent_l, "chance@c0"),
                    ("C", opponent_l_after_c, "chance@c1")):
                # Opponent and chance choices deliberately vary over t. Neither
                # is part of this player's own sequence reach.
                del opponent_profile
                p_branch = tuple(profile[0 if branch == "A" else 2]
                                 for profile in root_profiles)
                x = branch_x[(hand, branch)][:iteration_count]
                second_profiles = tuple((value, 1 - value) for value in x)
                second_avg = _average(second_profiles, p_branch, mass, iteration_count)
                row = _row("oop", hand,
                           (branch, "L", chance_token),
                           (("x", "X", 0.0, 0.0), ("y", "Y", 0.0, 0.0)))
                for action, probability in zip(row["actions"], second_avg):
                    action["probability"] = probability
                rows.append(row)

        for branch, profile, chance_token in (
                ("A", opponent_l, "chance@c0"),
                ("C", opponent_l_after_c, "chance@c1")):
            rows.append(_row("ip", "IP", (branch,),
                             (("left", "L", 0.0, 0.0),
                              ("right", "R", 0.0, 0.0))))
            row = rows[-1]
            reaches = (F(1),) * iteration_count
            mass = masses["IP"] if include_hand_mass else F(1)
            p_left = tuple(profile[:iteration_count])
            row_avg = _average(tuple((p, 1 - p) for p in p_left), reaches,
                               mass, iteration_count)
            for action, probability in zip(row["actions"], row_avg):
                action["probability"] = probability
        return rows

    return rows_at(1), rows_at(2), rows_at(3), branch_x, roots, opponent_l, chance_l


def _as_map(rows):
    return {(row["player"], row["hand"], tuple(row["history"])): row
            for row in rows}


class RiverTailRealizationTests(unittest.TestCase):
    def setUp(self):
        (self.one_iteration, self.prefix, self.full, self.branch_x, self.roots,
         self.opponent_l, self.chance_l) = _independent_snapshots()

    def test_exact_tail_reconstruction_ignores_opponent_chance_and_cancels_hand_mass(self):
        tail, ledger = reconstruct_tail(self.prefix, self.full, 2, 3)
        by_key = _as_map(tail)
        first = by_key[("oop", "H1", ("A", "L", "chance@c0"))]
        self.assertEqual(first["actions"][0]["probability"], F(7, 10))
        self.assertEqual(first["actions"][1]["probability"], F(3, 10))
        second_hand = by_key[("oop", "H2", ("A", "L", "chance@c0"))]
        self.assertEqual(second_hand["actions"][0]["probability"], F(1, 5))

        # Every positively reached output row equals its one-iteration tail
        # policy, for both private hands, both chance/opponent branches, and
        # both players. The two C descendants have zero own tail reach and use
        # their explicit full-snapshot fallback instead.
        for hand in ("H1", "H2"):
            root = by_key[("oop", hand, ())]
            self.assertEqual(tuple(a["probability"] for a in root["actions"]),
                             self.roots[hand][2])
            for branch, token in (("A", "chance@c0"), ("C", "chance@c1")):
                key = ("oop", hand, (branch, "L", token))
                actual = tuple(a["probability"] for a in by_key[key]["actions"])
                if branch == "A":
                    expected = (self.branch_x[(hand, "A")][2],
                                1 - self.branch_x[(hand, "A")][2])
                    self.assertEqual(actual, expected)
                else:
                    full_row = _as_map(self.full)[key]
                    self.assertEqual(actual, tuple(a["probability"]
                                                   for a in full_row["actions"]))
        for branch, profile in (("A", self.opponent_l),
                                ("C", (F(7, 10), F(2, 10), F(9, 10)))):
            ip_row = by_key[("ip", "IP", (branch,))]
            self.assertEqual(tuple(a["probability"] for a in ip_row["actions"]),
                             (profile[2], 1 - profile[2]))

        # The naive subtraction of normalized conditional rows is wrong because
        # it loses the prefix-vs-tail own reach of action A.
        prefix_row = _as_map(self.prefix)[("oop", "H1", ("A", "L", "chance@c0"))]
        full_row = _as_map(self.full)[("oop", "H1", ("A", "L", "chance@c0"))]
        naive = (6 * full_row["actions"][0]["probability"] -
                 3 * prefix_row["actions"][0]["probability"]) / 3
        self.assertNotEqual(naive, F(7, 10))

        # With a two-iteration tail, own reach weights the conditional row but
        # varying opponent/chance reach still must not enter that own sequence.
        p_a = tuple(profile[0] for profile in self.roots["H1"])
        x = self.branch_x[("H1", "A")]
        two_iteration_tail, _ = reconstruct_tail(self.one_iteration, self.full, 1, 3)
        expected_own = sum((F(t) * p_a[t - 1] * x[t - 1]
                            for t in (2, 3)), F(0)) / sum(
            (F(t) * p_a[t - 1] for t in (2, 3)), F(0))
        wrong_with_other_reach = sum((F(t) * p_a[t - 1] * x[t - 1] *
                                      self.opponent_l[t - 1] * self.chance_l[t - 1]
                                      for t in (2, 3)), F(0)) / sum(
            (F(t) * p_a[t - 1] * self.opponent_l[t - 1] * self.chance_l[t - 1]
             for t in (2, 3)), F(0))
        two_iteration_row = _as_map(two_iteration_tail)[
            ("oop", "H1", ("A", "L", "chance@c0"))]
        self.assertEqual(two_iteration_row["actions"][0]["probability"], expected_own)
        self.assertNotEqual(wrong_with_other_reach, expected_own)

        _, without_mass_prefix, without_mass_full, *_ = _independent_snapshots(
            include_hand_mass=False)
        no_mass_tail, _ = reconstruct_tail(without_mass_prefix, without_mass_full, 2, 3)
        self.assertEqual(tail, no_mass_tail)

        fallback_key = ("oop", "H1", ("C", "L", "chance@c1"))
        fallback = [row for row in ledger["fallback_rows"] if row["row"] == fallback_key]
        self.assertEqual(len(fallback), 1)
        self.assertEqual(fallback[0]["full_snapshot_fallback_probabilities"], tuple(
            action["probability"] for action in _as_map(self.full)[fallback_key]["actions"]))
        self.assertIn("actual_output_parent_flow", fallback[0])
        self.assertIn("parent_flow_discrepancy", fallback[0])
        self.assertEqual(ledger["maximum_reconstruction_discrepancy"], 0)
        self.assertEqual(sum(action["probability"] for action in
                             by_key[("oop", "H1", ())]["actions"]), 1)

    def test_rows_metadata_and_action_order_are_preserved(self):
        tail, _ = reconstruct_tail(self.prefix, self.full, 2, 3)
        self.assertEqual([tuple(row["history"]) for row in tail],
                         [tuple(row["history"]) for row in self.full])
        for actual, expected in zip(tail, self.full):
            for field in ("player", "hand", "street", "board", "history"):
                self.assertEqual(actual[field], expected[field])
            self.assertEqual([action["history_key"] for action in actual["actions"]],
                             [action["history_key"] for action in expected["actions"]])
            self.assertTrue(all(isinstance(action["probability"], F)
                                for action in actual["actions"]))

    def test_float_round_trip_passes_exact_ledger_gates(self):
        def to_float(rows):
            result = deepcopy(rows)
            for row in result:
                for action in row["actions"]:
                    action["probability"] = float(action["probability"])
            return result

        tail, ledger = reconstruct_tail(to_float(self.prefix), to_float(self.full), 2, 3)
        self.assertLessEqual(ledger["prefix_max_normalization_adjustment"], F(1, 10**12))
        self.assertLessEqual(ledger["full_max_normalization_adjustment"], F(1, 10**12))
        self.assertLessEqual(ledger["maximum_reconstruction_discrepancy"], F(1, 10**11))
        self.assertTrue(all(math.isfinite(float(action["probability"]))
                            and 0 <= float(action["probability"]) <= 1
                            for row in tail for action in row["actions"]))

    def test_tiny_negative_child_is_counted_projected_and_not_silently_clipped(self):
        tiny = F(1, 2 * 10**12)
        prefix = [_row("oop", "H", (), (("a", "A", 0.0, 0.0),
                                         ("b", "B", 0.0, 0.0))) ]
        prefix[0]["actions"][0]["probability"] = F(1)
        prefix[0]["actions"][1]["probability"] = F(0)
        full_a = (1 - 2 * tiny) / 3
        full = deepcopy(prefix)
        full[0]["actions"][0]["probability"] = full_a
        full[0]["actions"][1]["probability"] = 1 - full_a

        tail, ledger = reconstruct_tail(prefix, full, 1, 2)
        self.assertEqual(tuple(action["probability"] for action in tail[0]["actions"]),
                         (F(0), F(1)))
        self.assertEqual(ledger["raw_negative_child_count"], 1)
        self.assertEqual(ledger["projected_negative_child_count"], 1)
        self.assertEqual(ledger["maximum_negative_child_magnitude"], tiny)
        self.assertEqual(ledger["maximum_projected_mass_moved"], 2 * tiny)
        self.assertEqual(ledger["changed_rows"][0]["projected_mass_moved"], 2 * tiny)
        self.assertLessEqual(ledger["maximum_reconstruction_discrepancy"],
                             F(1, 10**11))

    def test_negative_children_in_zero_parent_fallback_are_also_ledgered(self):
        tiny = F(1, 2 * 10**12)
        prefix = [_row("oop", "H", (), (("a", "A", 0.0, 0.0),
                                         ("b", "B", 0.0, 0.0))),
                  _row("oop", "H", ("A",), (("x", "X", 0.0, 0.0),
                                              ("y", "Y", 0.0, 0.0)))]
        prefix[0]["actions"][0]["probability"] = F(1)
        prefix[0]["actions"][1]["probability"] = F(0)
        prefix[1]["actions"][0]["probability"] = F(1, 2)
        prefix[1]["actions"][1]["probability"] = F(1, 2)
        full = deepcopy(prefix)
        full_a = (1 - 2 * tiny) / 3
        full[0]["actions"][0]["probability"] = full_a
        full[0]["actions"][1]["probability"] = 1 - full_a

        tail, ledger = reconstruct_tail(prefix, full, 1, 2)
        self.assertEqual(ledger["raw_negative_child_count"], 3)
        self.assertEqual(ledger["projected_negative_child_count"], 1)
        self.assertEqual(ledger["fallback_negative_child_count"], 2)
        self.assertEqual(ledger["maximum_negative_child_magnitude"], tiny)
        self.assertEqual(len(ledger["fallback_rows"]), 1)
        fallback = ledger["fallback_rows"][0]
        self.assertEqual(fallback["raw_parent_flow"], -tiny)
        self.assertEqual(fallback["raw_child_flows"], (-tiny / 2, -tiny / 2))
        self.assertEqual(fallback["actual_output_parent_flow"], 0)
        self.assertEqual(fallback["actual_output_child_flows"], (F(0), F(0)))
        self.assertEqual(tuple(action["probability"] for action in tail[1]["actions"]),
                         (F(1, 2), F(1, 2)))
        self.assertLessEqual(ledger["maximum_reconstruction_discrepancy"],
                             REALIZATION_TOLERANCE)

    def test_material_negative_tail_is_rejected(self):
        prefix = deepcopy(self.prefix)
        full = deepcopy(self.full)
        row_key = ("oop", "H1", ())
        prefix_row, full_row = _as_map(prefix)[row_key], _as_map(full)[row_key]
        for row, a in ((prefix_row, F(9, 10)), (full_row, F(1, 10))):
            row["actions"][0]["probability"] = a
            row["actions"][1]["probability"] = 1 - a
            row["actions"][2]["probability"] = F(0)
        with self.assertRaisesRegex(ValueError, "child flow outside tolerance"):
            reconstruct_tail(prefix, full, 1, 2)

    def test_checkpoint_bounds_are_strict_integer_inputs(self):
        for discard, total in ((True, 3), (2, False), (0, 3), (3, 3), (2, 1),
                               (1.0, 3), (1, 10_001)):
            with self.subTest(discard=discard, total=total):
                with self.assertRaises(ValueError):
                    reconstruct_tail(self.prefix, self.full, discard, total)

    def test_duplicate_missing_and_reordered_rows_are_rejected(self):
        duplicate = deepcopy(self.full)
        duplicate.append(deepcopy(duplicate[0]))
        with self.assertRaisesRegex(ValueError, "Duplicate information-set"):
            reconstruct_tail(self.prefix, duplicate, 2, 3)
        with self.assertRaisesRegex(ValueError, "identical keys and order"):
            reconstruct_tail(self.prefix[:-1], self.full, 2, 3)
        with self.assertRaisesRegex(ValueError, "identical keys and order"):
            reconstruct_tail(self.prefix, list(reversed(self.full)), 2, 3)

    def test_action_metadata_history_and_complete_row_metadata_must_match(self):
        mutate_cases = ("amount", "history_key", "board")
        for field in mutate_cases:
            with self.subTest(field=field):
                corrupt = deepcopy(self.full)
                if field == "board":
                    corrupt[0]["board"][0] = "3c"
                elif field == "history_key":
                    corrupt[0]["actions"][0]["history_key"] = "wrong-action"
                else:
                    corrupt[0]["actions"][0]["amount"] = 5.0
                with self.assertRaises(ValueError):
                    reconstruct_tail(self.prefix, corrupt, 2, 3)

        bad_history = deepcopy(self.full)
        bad_history[2]["history"][0] = "not-an-ancestor-action"
        prefix_bad_history = deepcopy(self.prefix)
        prefix_bad_history[2]["history"][0] = "not-an-ancestor-action"
        with self.assertRaisesRegex(ValueError, "ancestor.*history_key"):
            reconstruct_tail(prefix_bad_history, bad_history, 2, 3)

    def test_duplicate_actions_and_changed_action_order_are_rejected(self):
        duplicate = deepcopy(self.full)
        duplicate[0]["actions"][1]["history_key"] = duplicate[0]["actions"][0]["history_key"]
        with self.assertRaisesRegex(ValueError, "Duplicate action history key"):
            reconstruct_tail(self.prefix, duplicate, 2, 3)

        reordered = deepcopy(self.full)
        reordered[0]["actions"].reverse()
        with self.assertRaisesRegex(ValueError, "metadata differs"):
            reconstruct_tail(self.prefix, reordered, 2, 3)

    def test_boolean_nonfinite_out_of_range_and_bad_sum_probabilities_are_rejected(self):
        for invalid in (True, float("nan"), float("inf"), float("-inf"), F(-1, 10), F(11, 10)):
            with self.subTest(probability=invalid):
                corrupt = deepcopy(self.full)
                corrupt[0]["actions"][0]["probability"] = invalid
                with self.assertRaises(ValueError):
                    reconstruct_tail(self.prefix, corrupt, 2, 3)

        bad_sum = deepcopy(self.full)
        bad_sum[0]["actions"][0]["probability"] += F(2, 10**12)
        with self.assertRaisesRegex(ValueError, "does not sum to one"):
            reconstruct_tail(self.prefix, bad_sum, 2, 3)


if __name__ == "__main__":
    unittest.main()
