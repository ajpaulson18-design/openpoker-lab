"""Exact, bounded chance-partition regressions for the rational auditor."""
import unittest
from fractions import Fraction as F

from scripts import turn_rational_certificate as exact_core
from scripts import turn_river_validation as validator
from tests.test_turn_rational_certificate import (
    _chance_toy, _hidden_hand_toy,
)


class _GuardedSequence:
    def __init__(self, length):
        self.length = length
        self.iterations = 0

    def __len__(self):
        return self.length

    def __iter__(self):
        self.iterations += 1
        raise AssertionError("partition iterated before reserving complete work")


class TurnRationalPartitionTests(unittest.TestCase):
    def test_partition_matches_scan_exact_metrics_ledgers_and_counts(self):
        for factory, pot in ((_chance_toy, 10),
                             (lambda: _hidden_hand_toy(0), 10),
                             (lambda: _hidden_hand_toy(1), 10)):
            with self.subTest(factory=factory):
                root, worlds, policies, result = factory()
                before = (worlds.copy(), policies.copy(), result.copy())
                scan = exact_core.evaluate_exact(
                    root, worlds, policies, pot, result=result)
                partition = exact_core.evaluate_exact(
                    root, worlds, policies, pot, result=result,
                    chance_grouping="partition")
                self.assertEqual(partition["metrics"], scan["metrics"])
                self.assertEqual(partition["lower_value_bound"],
                                 scan["lower_value_bound"])
                self.assertEqual(partition["upper_value_bound"],
                                 scan["upper_value_bound"])
                self.assertEqual(partition["threshold_met"], scan["threshold_met"])
                self.assertEqual(partition["normalization_ledger"],
                                 scan["normalization_ledger"])
                self.assertEqual(partition["max_row_adjustment"],
                                 scan["max_row_adjustment"])
                self.assertEqual(partition["normalized_policy_rows"],
                                 scan["normalized_policy_rows"])
                for field in ("tree_nodes", "tree_depth", "worlds"):
                    self.assertEqual(partition[field], scan[field])
                self.assertEqual(partition["chance_grouping"], "partition")
                self.assertNotIn("chance_grouping", scan)
                self.assertEqual((worlds, policies, result), before)

    def test_partition_stably_preserves_original_entries_and_ignores_unknown_rivers(self):
        first = ({"river": "L"}, F(1, 3))
        unmatched = ({"river": "X"}, F(1, 3))
        last = ({"river": "L"}, F(1, 3))
        group = (first, unmatched, last)
        branches = {"L": object(), "R": object()}
        budget = exact_core._Budget(100, 64, 65_536)
        buckets = exact_core._partition_chance_group(group, branches, budget)
        self.assertEqual(buckets["L"], [first, last])
        self.assertIs(buckets["L"][0], first)
        self.assertIs(buckets["L"][1], last)
        self.assertEqual(buckets["R"], [])
        self.assertEqual(group, (first, unmatched, last))
        self.assertIsNot(buckets["L"], buckets["R"])
        self.assertEqual(budget.work, 2 * len(branches) + 3 * len(group))
        self.assertEqual(budget.counters, {
            "chance_partition_branch_map_bucket_slots": 2 * len(branches),
            "chance_partition_entries_scanned": len(group),
            "chance_partition_river_lookups": len(group),
            "chance_partition_bucket_reference_slots": len(group),
        })

    def test_lowered_budget_rejects_before_bucket_allocation_or_input_iteration(self):
        # The final one-unit reservation fails. Neither branches nor group may
        # be iterated until all 2*B+3*N units have been charged.
        group = _GuardedSequence(1)
        branches = _GuardedSequence(2)
        budget = exact_core._Budget(6, 64, 65_536)
        with self.assertRaisesRegex(ValueError, "work limit"):
            exact_core._partition_chance_group(group, branches, budget)
        self.assertEqual(group.iterations, 0)
        self.assertEqual(branches.iterations, 0)
        self.assertEqual(budget.work, 6)

    def test_empty_partition_bucket_is_still_visited_and_chance_precedes_max(self):
        root, worlds, policies, result = _chance_toy()
        # Retain only the L world. The R child is a physically empty bucket;
        # the decision response must still be chosen after the chance sum.
        worlds = [worlds[0]]
        worlds[0] = dict(worlds[0], weight=F(1))
        scan = exact_core.evaluate_exact(root, worlds, policies, 10, result=result)
        partition = exact_core.evaluate_exact(
            root, worlds, policies, 10, result=result, chance_grouping="partition")
        self.assertEqual(partition["metrics"], scan["metrics"])
        self.assertEqual(partition["metrics"]["oop_best_response_value"], F(15))
        self.assertEqual(partition["work_by_kind"]["best_response_node_group_visits"],
                         scan["work_by_kind"]["best_response_node_group_visits"])

    def test_invalid_mode_and_hard_cap_overrides_reject_early(self):
        for bad_mode in (True, None, "Partition", "bucketed"):
            with self.subTest(mode=bad_mode), self.assertRaisesRegex(
                    ValueError, "chance_grouping"):
                exact_core.evaluate_exact(None, [], {}, object(),
                                          result={}, chance_grouping=bad_mode)
        root, worlds, policies, result = _hidden_hand_toy(0)
        for limit in ({"max_work": exact_core.MAX_EXACT_WORK + 1},
                      {"max_depth": exact_core.MAX_EXACT_DEPTH + 1},
                      {"max_bits": exact_core.MAX_FRACTION_BITS + 1}):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                exact_core.evaluate_exact(
                    root, worlds, policies, 10, result=result,
                    chance_grouping="partition", **limit)

    def test_partition_keeps_intermediate_fraction_width_guard(self):
        # The final EV is 20 (five bits), while the first exact contribution
        # is 40/3 (six bits). Width enforcement is per intermediate Fraction.
        root = validator._Terminal("showdown", (10.0, 10.0))
        worlds = [
            {"hands": (("Ah", "As"), ("Kh", "Ks")), "river": None,
             "weight": F(2, 3), "sign": 1},
            {"hands": (("Ah", "As"), ("Qh", "Qs")), "river": None,
             "weight": F(1, 3), "sign": 1},
        ]
        with self.assertRaisesRegex(ValueError, "bit limit"):
            exact_core.evaluate_exact(root, worlds, {}, 20, result={"strategy": []},
                                      chance_grouping="partition", max_bits=5)


if __name__ == "__main__":
    unittest.main()
