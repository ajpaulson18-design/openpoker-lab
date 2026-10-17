import json
import unittest
from unittest.mock import patch

from pokerlab import flop_checkdown_worlds
from scripts import benchmark_fixed_street_profile as profile
from scripts import flop_checkdown_validation as oracle


CONFIG = {
    "pot": 6,
    "effective_stack": [12, 12],
    "bet_sizes": [0.5, 1],
    "raise_sizes": [0.5],
    "max_raises": 1,
    "include_all_in": True,
}


class FixedStreetProfileTests(unittest.TestCase):
    def test_rank_free_count_oracle_recomputes_exact_collision_priors(self):
        # The AsAd/AsKh collision removes one product before global normalization.
        rows = [
            {"oop_hand": "AdAs", "ip_hand": "KdKs", "wins": 900, "ties": 100, "losses": 980, "ordered_outcomes": 1980},
            {"oop_hand": "JhQh", "ip_hand": "AsKh", "wins": 900, "ties": 100, "losses": 980, "ordered_outcomes": 1980},
            {"oop_hand": "JhQh", "ip_hand": "KdKs", "wins": 900, "ties": 100, "losses": 980, "ordered_outcomes": 1980},
        ]
        with patch.object(oracle, "independent_rank", side_effect=AssertionError("ranking must not run")):
            prepared = oracle.prepare_oracle_from_counts(
                "2c3c4d", "AsAd:1,QhJh:0.5", "AsKh:0.25,KsKd:1", CONFIG, rows)
        expected = [8 / 13, 1 / 13, 4 / 13]
        self.assertEqual([deal[2] for deal in prepared["deals"]], expected)
        self.assertEqual([row["pair_probability"] for row in prepared["counts"]], expected)
        self.assertEqual(prepared["public_states"] > 0, True)

    def test_count_oracle_rejects_missing_or_malformed_rows_without_ranking(self):
        base = [
            {"oop_hand": "AdAs", "ip_hand": "KdKs", "wins": 1000, "ties": 0, "losses": 980, "ordered_outcomes": 1980},
            {"oop_hand": "AdAs", "ip_hand": "JsQs", "wins": 1000, "ties": 0, "losses": 980, "ordered_outcomes": 1980},
            {"oop_hand": "JhQh", "ip_hand": "KdKs", "wins": 1000, "ties": 0, "losses": 980, "ordered_outcomes": 1980},
            {"oop_hand": "JhQh", "ip_hand": "JsQs", "wins": 1000, "ties": 0, "losses": 980, "ordered_outcomes": 1980},
        ]
        invalid = [None, base[:-1], base + [dict(base[-1])], [base[1], base[0], *base[2:]],
                   [{**base[0], "wins": True}, *base[1:]],
                   [{**base[0], "wins": 1001}, *base[1:]]]
        with patch.object(oracle, "independent_rank", side_effect=AssertionError("rank-free helper fell back to enumeration")):
            for rows in invalid:
                with self.subTest(rows=rows):
                    with self.assertRaises(ValueError):
                        oracle.prepare_oracle_from_counts(
                            "2c3c4d", "AsAd:1,QhJh:0.5", "KsKd:1,QsJs:0.5", CONFIG, rows)

    def test_phase_context_times_calls_and_restores_after_exception(self):
        class Target:
            def phase(self, fail=False):
                if fail:
                    raise RuntimeError("expected")
                return "ok"

        owner = Target()
        original = owner.phase
        context = profile._PhaseContext([("phase", owner, "phase")])
        with self.assertRaisesRegex(RuntimeError, "expected"):
            with context as (seconds, calls):
                self.assertEqual(owner.phase(), "ok")
                owner.phase(fail=True)
        self.assertEqual(owner.phase.__func__, original.__func__)
        self.assertEqual(context.calls["phase"], 2)
        self.assertGreaterEqual(context.totals["phase"], 0)

    def test_profile_one_keeps_unwrapped_reference_and_equal_wrapped_payloads(self):
        class Target:
            def phase(self):
                return 7

        owner = Target()

        def solver():
            return {"value": owner.phase(), "array": [1, 2, 3]}

        result = profile._profile_one(solver, [("phase", owner, "phase")], 2)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["unwrapped_reference"]["payload"], solver())
        self.assertEqual(len(result["samples"]), 2)
        self.assertTrue(all(s["payload_equal_unwrapped_reference"] for s in result["samples"]))
        self.assertTrue(all(s["phase_calls"] == {"phase": 1} for s in result["samples"]))
        self.assertTrue(all(s["serialized_bytes_utf8"] == result["unwrapped_reference"]["serialized_bytes_utf8"]
                            for s in result["samples"]))

    def test_real_preflop_payload_is_unchanged_and_independently_replayed(self):
        from tests.test_preflop_checkdown_solver import prepared_table
        from pokerlab.preflop_checkdown_solver import solve_prepared_preflop_checkdown
        from scripts.preflop_checkdown_validation import replay
        table, counts = prepared_table()
        config = {"starting_stack": [4, 3], "raise_sizes": [.5, 1], "max_raises": 2}
        def solve():
            return solve_prepared_preflop_checkdown(table, config=config, iterations=10,
                world_indexing="pair-mean", resource_model="prepared-counts")
        result = profile._profile_one(solve, profile._preflop_targets(), 1)
        self.assertEqual(result["status"], "passed")
        checked = replay(result["unwrapped_reference"]["payload"],
                         "AsAd:1,QsQd:0.5", "AsKh:0.25,KsKd:1",
                         result["unwrapped_reference"]["payload"]["config"], counts)
        self.assertLessEqual(max(checked["scalar_absolute_gaps"].values()), 1e-10)
        self.assertEqual(result["samples"][0]["phase_calls"],
                         {"train_cfrplus": 1, "evaluate": 1, "best_response": 2})
        self.assertTrue(all(value == 0 for value in result["samples"][0]["rank_guard_calls"].values()))

    def test_changed_payload_is_retained_as_failed_measurement(self):
        counter = [0]
        def solve():
            counter[0] += 1
            return {"value": counter[0]}
        result = profile._profile_one(solve, [], 1)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["unwrapped_reference"]["payload"], {"value": 1})
        self.assertEqual(result["samples"][0]["payload"], {"value": 2})
        self.assertIn("error", result["samples"][0])
        self.assertGreaterEqual(result["samples"][0]["complete_seconds"], 0)

    def test_frozen_spec_rejects_mutation(self):
        spec = json.loads(profile.SPEC_PATH.read_text(encoding="utf-8"))
        self.assertIs(profile.validate_spec(spec), spec)
        altered = json.loads(json.dumps(spec))
        altered["flop"]["iterations"] += 1
        with self.assertRaises(ValueError):
            profile.validate_spec(altered)

    def test_flop_table_loader_uses_pinned_counts_without_ranking(self):
        spec = json.loads(profile.SPEC_PATH.read_text(encoding="utf-8"))
        # Unit tests also run in shallow CI checkouts. Mock only historical Git
        # retrieval with the checked-in report; formal profiling verifies the
        # pinned historical Git blob itself before using these physical rows.
        from scripts import benchmark_flop_equity_reuse as reuse
        historical = json.loads((profile.ROOT / reuse.HISTORICAL_PATH).read_text(encoding="utf-8"))
        rows = next(item["oracle_pair_counts"] for item in historical["results"]
                    if item["fixture_id"] == "weighted-8x8-stack12-raises1")
        with patch.object(reuse, "_historical_counts", return_value=rows) as load_counts, \
             patch.object(oracle, "independent_rank", side_effect=AssertionError("rank called")), \
             patch.object(flop_checkdown_worlds, "combinations", side_effect=AssertionError("board enumeration called")), \
             patch.object(flop_checkdown_worlds.FlopCheckdownPlan, "build", side_effect=AssertionError("plan build called")):
            item = profile._load_flop_table(spec)
        load_counts.assert_called_once_with()
        self.assertEqual(len(item["table"].pairs), 58)
        self.assertEqual(len(item["counts"]), 58)
        self.assertEqual(item["table"].budget["physical_worlds"], 114840)


if __name__ == "__main__":
    unittest.main()