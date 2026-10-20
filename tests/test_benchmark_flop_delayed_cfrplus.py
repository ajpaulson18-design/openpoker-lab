"""Rank-free protocol and selected-runout checks for delayed-CFR+ evidence."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from pokerlab import postflop_solver
from pokerlab.river_config import RiverConfig
from scripts import benchmark_flop_delayed_cfrplus as bench
from scripts import flop_multistreet_validation as independent


BOARD = "2c3d4h"
OOP = "AsAd:1,QsQd:0.5"
IP = "AsKh:0.25,KsKd:1"
RUNOUTS = (("5c", "6c"), ("6c", "5c"))
CONFIG = {
    "pot": 10, "effective_stack": 5, "bet_sizes": [0.5],
    "raise_sizes": [], "max_raises": 0, "include_all_in": False,
}


def _selected_results():
    config = RiverConfig.from_dict(CONFIG)
    oracle = independent.prepare_oracle(
        ("2c", "3d", "4h"), (("AdAs", "1"), ("QdQs", "1/2")),
        (("AsKh", "1/4"), ("KdKs", "1")), CONFIG, runouts=RUNOUTS)
    results = {}
    for traversal in ("recursive", "public-batched"):
        results[traversal] = postflop_solver.solve_postflop(
            BOARD, OOP, IP, config, runouts=RUNOUTS, iterations=10,
            algorithm="cfrplus", traversal=traversal, averaging_delay=2)
    return oracle, results


class DelayedCFRPlusBenchmarkTests(unittest.TestCase):
    def test_frozen_spec_and_full_request_preflight_are_rank_free(self):
        spec = bench.load_spec()
        self.assertEqual(bench.validate_spec(spec), spec)
        tampered = deepcopy(spec)
        tampered["delays"] = [0, 1]
        with self.assertRaisesRegex(ValueError, "frozen"):
            bench.validate_spec(tampered)

        with patch.object(bench.base.production, "rank_hand",
                          side_effect=AssertionError("ranking")), \
             patch.object(bench.base.production, "_enumerate_worlds",
                          side_effect=AssertionError("world enumeration")), \
             patch.object(bench.base.production, "solve_postflop",
                          side_effect=AssertionError("training")):
            census = bench._rank_free_preflight(140)
            protocol = bench.preflight(spec)
        self.assertEqual(census["worlds"], 5940)
        self.assertEqual(census["max_world_node_iterations"], 29937600)
        self.assertEqual(census["public_prefix_hand_edges"], 6078)
        self.assertTrue(protocol["rank_free"])
        self.assertEqual(len(protocol["requests"]), 8)
        self.assertEqual({r["training_passes_per_iteration"] for r in protocol["requests"]}, {3})
        self.assertEqual({r["averaging_delay"] for r in protocol["requests"]}, {0, 1, 70, 100})
        with self.assertRaisesRegex(ValueError, "cap"):
            bench._rank_free_preflight(141)

    def test_selected_runout_payloads_replay_and_compare_all_rows(self):
        oracle, results = _selected_results()
        spec = bench.load_spec()
        rows = {}
        for traversal, payload in results.items():
            row = {"algorithm": "cfrplus", "iterations": 10, "averaging_delay": 2,
                   "traversal": traversal}
            bench._check_candidate(payload, row, spec)
            checked, guarded = bench._assess(payload, oracle, spec)
            self.assertEqual(checked["checked_physical_worlds"], 6)
            self.assertFalse(any(guarded["delayed_trainer_calls"].values()))
            self.assertEqual(payload["averaging_positive_sweeps"], 8)
            rows[traversal] = payload
        comparison = bench._cross_compare(
            rows["recursive"], rows["public-batched"], spec, oracle)
        self.assertLessEqual(comparison["maximum_scalar_absolute_gap"], 1e-8)
        self.assertLessEqual(comparison["maximum_action_realization_absolute_gap"], 1e-8)
        self.assertFalse(comparison["raw_conditional_probability_gap_gated"])
        self.assertLessEqual(len(comparison["largest_raw_conditional_probability_gap_examples"]), 10)

    def test_realization_gap_is_gated_but_zero_reach_conditional_gap_is_recorded(self):
        oracle, results = _selected_results()
        spec = bench.load_spec()
        original = results["recursive"]
        bad_realization = deepcopy(original)
        root = next(row for row in bad_realization["strategy"]
                    if row["player"] == "oop" and not row["history"] and len(row["actions"]) == 2)
        root["actions"][0]["probability"], root["actions"][1]["probability"] = 0.9, 0.1
        with self.assertRaisesRegex(ValueError, "realization"):
            bench._cross_compare(original, bad_realization, spec, oracle)

        # Create a shared zero-own-reach prefix in both copies, then vary only a
        # downstream conditional row. The raw difference remains visible while
        # its action realization is zero and is not used as a quality gate.
        left, right = deepcopy(original), deepcopy(original)
        rows = {(row["player"], row["hand"], tuple(row["history"])): row
                for row in left["strategy"]}
        target = None
        for row in left["strategy"]:
            player = row["player"]
            hand = row["hand"]
            history = tuple(row["history"])
            path = bench._decision_paths(oracle)[(0 if player == "oop" else 1, history)]
            for ancestor_player, ancestor_history, action_index in path:
                if ancestor_player == (0 if player == "oop" else 1):
                    ancestor = rows[(player, hand, ancestor_history)]
                    if len(ancestor["actions"]) > 1:
                        target = (row, ancestor, action_index)
                        break
            if target:
                break
        self.assertIsNotNone(target)
        target_row, ancestor, action_index = target
        for payload in (left, right):
            ancestor_copy = next(row for row in payload["strategy"]
                                 if row["player"] == target_row["player"]
                                 and row["hand"] == target_row["hand"]
                                 and tuple(row["history"]) == tuple(ancestor["history"]))
            chosen = action_index
            ancestor_copy["actions"][chosen]["probability"] = 0.0
            sibling = next(i for i in range(len(ancestor_copy["actions"])) if i != chosen)
            ancestor_copy["actions"][sibling]["probability"] = 1.0
        changed = next(row for row in right["strategy"]
                       if row["player"] == target_row["player"]
                       and row["hand"] == target_row["hand"]
                       and tuple(row["history"]) == tuple(target_row["history"]))
        if len(changed["actions"]) < 2:
            self.skipTest("selected fixture has no multi-action downstream row")
        changed["actions"][0]["probability"], changed["actions"][1]["probability"] = 1.0, 0.0
        original_target = next(row for row in left["strategy"]
                               if row["player"] == target_row["player"]
                               and row["hand"] == target_row["hand"]
                               and tuple(row["history"]) == tuple(target_row["history"]))
        original_target["actions"][0]["probability"], original_target["actions"][1]["probability"] = 0.0, 1.0
        comparison = bench._cross_compare(left, right, spec, oracle)
        self.assertGreaterEqual(comparison["maximum_raw_conditional_probability_gap"], 1.0)
        self.assertGreater(comparison["nonzero_raw_conditional_probability_gap_count"], 0)
        self.assertEqual(comparison["maximum_action_realization_absolute_gap"], 0.0)

    def test_full_saved_controls_cover_all_blocked_public_prefixes_without_training(self):
        import json
        spec = bench.load_spec()
        with patch.object(postflop_solver, "solve_postflop",
                          side_effect=AssertionError("production training")):
            oracle, guard = bench._guarded_reference(spec)
            report = json.loads((bench.baseline_publication.PUBLICATION/"index.json").read_bytes())
            payloads = []
            for traversal in spec["traversals"]:
                record = next(row for row in report["samples"]
                              if row["iterations"] == 140 and row["repeat"] == 1
                              and row["traversal"] == traversal)
                payloads.append(bench.base.read_payload(bench.baseline_publication.PUBLICATION,record))
            frozen = deepcopy(spec)
            physical = bench._compare_physical_worlds(spec,oracle)
            self.assertEqual(physical['worlds'],5940)
            self.assertEqual(physical['pairs'],3)
            self.assertLessEqual(physical['maximum_mass_absolute_gap'],1e-15)
            bench.base._check_physical_record(physical,oracle,spec)
            self.assertEqual(spec,frozen)
            comparison = bench._cross_compare(*payloads,spec,oracle)
        self.assertEqual(len(oracle["worlds"]),5940)
        self.assertEqual(len(payloads[0]["strategy"]),16912)
        self.assertGreater(comparison["nonzero_raw_conditional_probability_gap_count"],10)
        self.assertEqual(len(comparison["largest_raw_conditional_probability_gap_examples"]),10)
        self.assertEqual(comparison["largest_raw_conditional_probability_gap_examples"][0]["absolute_gap"],
                         comparison["maximum_raw_conditional_probability_gap"])
        self.assertLessEqual(comparison["maximum_action_realization_absolute_gap"],1e-8)
        self.assertLessEqual(comparison["maximum_raw_conditional_probability_gap"],1e-8)
        self.assertFalse(any(guard["delayed_trainer_calls"].values()))

    def test_realization_masses_use_independent_private_and_public_chance(self):
        oracle, results = _selected_results()
        payload = results["recursive"]
        paths = bench._decision_paths(oracle)
        reaches = bench._own_reach_masses(payload,oracle,paths)
        self.assertAlmostEqual(reaches[(0,"AdAs",())],8/13,delta=1e-15)
        self.assertAlmostEqual(reaches[(0,"QdQs",())],5/13,delta=1e-15)
        root = next(row for row in payload["strategy"]
                    if row["player"] == "oop" and row["hand"] == "AdAs" and not row["history"])
        check = next(action["probability"] for action in root["actions"]
                     if action["history_key"] == "check")
        self.assertAlmostEqual(reaches[(0,"AdAs",("check","check","turn@5c"))],
                               4/13*check,delta=1e-15)

    def test_first_startup_failure_is_immutable_and_rejected_as_completed_study(self):
        import hashlib
        import json
        directory = bench.ROOT/'benchmarks/results/weighted-full-deck-flop-delayed-cfrplus-initial-v1'
        raw = (directory/'index.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'bdecdfad71411b776360d94680e9c1f4fd109ffb3c11f24fe4c8c05ab818c740')
        report = json.loads(raw)
        self.assertEqual(report['status'],'error')
        self.assertEqual(report['samples'],[])
        self.assertEqual(report['separate_allocation_calls'],[])
        self.assertEqual(report['source_before'],report['source_after'])
        self.assertEqual(report['source_before']['revision'],'4f1f23be294012fac072f9e38fc40e4e5c9eb2ef')
        self.assertEqual(report['validation_errors'],["TypeError: 'int' object is not iterable"])
        self.assertEqual({p.name for p in directory.iterdir()},
                         {'index.json','independent-physical-worlds.json.gz'})
        physical = bench.base.read_payload(directory,report['oracle_physical_evidence'])
        self.assertEqual(len(physical['worlds']),5940)
        with self.assertRaisesRegex(ValueError,'checksum/specification/validation'):
            bench.verify_saved(directory,bench.baseline_publication.PUBLICATION)

    def test_candidate_metadata_and_finite_values_are_strict(self):
        spec = bench.load_spec()
        bench._check_zero_control_hash(
            spec["baseline"]["zero_delay_140_payload_sha256"]["recursive"],
            "recursive", spec)
        with self.assertRaisesRegex(ValueError, "immutable control"):
            bench._check_zero_control_hash("0" * 64, "recursive", spec)
        _, results = _selected_results()
        recursive = results["recursive"]
        row = {"algorithm": "cfrplus", "iterations": 10, "averaging_delay": 2, "traversal": "recursive"}
        wrong = dict(recursive, averaging_positive_sweeps=7)
        with self.assertRaisesRegex(ValueError, "schedule metadata"):
            bench._check_candidate(wrong, row, spec)
        public = results["public-batched"]
        bad = deepcopy(public)
        bad["nash_conv"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            bench._cross_compare(public, bad, spec, _selected_results()[0])


if __name__ == "__main__":
    unittest.main()
