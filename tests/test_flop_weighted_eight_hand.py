"""Cheap structural regressions for the frozen eight-hand benchmark."""
import copy
import inspect
import json
import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pokerlab import flop_checkdown_solver as solver
from pokerlab import flop_checkdown_worlds as worlds
from scripts import benchmark_flop_weighted_eight_hand as benchmark

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "benchmarks" / "flop-weighted-eight-hand-v1.json"

# Keep this literal census independent of the benchmark parser/expansion.
OOP_HANDS = ("AsAd", "QhJh", "7s6s", "Tc9c", "KsQd", "Ac5c", "8h8d", "ThTs")
OOP_UNITS = (8, 4, 2, 6, 3, 5, 7, 1)
IP_HANDS = ("KsKd", "AhKh", "8s7s", "QcQd", "AdJd", "6h5h", "9d8d", "JcTc")
IP_UNITS = (6, 8, 4, 2, 3, 5, 7, 1)
EXPECTED_COLLISIONS = ((0, 4, 24), (2, 2, 8), (3, 7, 6),
                       (4, 0, 18), (4, 3, 6), (6, 6, 49))


def _cards(combo):
    return {combo[:2], combo[2:]}


def _independent_prior_census():
    collisions = []
    marginals_oop = [0] * len(OOP_HANDS)
    marginals_ip = [0] * len(IP_HANDS)
    total = 0
    compatible = 0
    for i, oop in enumerate(OOP_HANDS):
        for j, ip in enumerate(IP_HANDS):
            product = OOP_UNITS[i] * IP_UNITS[j]
            if _cards(oop).intersection(_cards(ip)):
                collisions.append((i, j, product))
                continue
            compatible += 1
            total += product
            marginals_oop[i] += product
            marginals_ip[j] += product
    return collisions, compatible, total, marginals_oop, marginals_ip


def _action(name, target=0.0, amount=0.0):
    token = f"{name}@{target:g}" if name in {"bet", "raise", "all_in"} else name
    return {"name": name, "amount": amount, "raise_to": target,
            "history_key": token, "probability": 1.0}


def _row(player, hand, history, actions, *, street="flop", board=None):
    return {"player": player, "hand": hand, "street": street,
            "board": list(board or ("2c", "3c", "4d")),
            "history": list(history), "actions": actions}


def _complete_raise_rows(*, street="flop"):
    oop, ip = "AdAs", "KdKs"
    return [
        _row("oop", oop, (), [_action("check"), _action("bet", 3.0, 3.0)], street=street),
        _row("ip", ip, ("bet@3",), [_action("raise", 9.0, 9.0)], street=street),
        _row("oop", oop, ("bet@3", "raise@9"), [_action("raise", 21.0, 18.0)], street=street),
        _row("ip", ip, ("check",), [_action("bet", 3.0, 3.0)], street=street),
        _row("oop", oop, ("check", "bet@3"), [_action("raise", 9.0, 9.0)], street=street),
        _row("ip", ip, ("check", "bet@3", "raise@9"), [_action("raise", 21.0, 18.0)], street=street),
    ]


class WeightedEightHandBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))

    def test_duplicate_pair_cannot_replace_an_expected_pair_before_ranking(self):
        fixture = self.spec['fixtures'][0]
        real = worlds.prepare_flop_worlds(fixture['board'], fixture['oop_range'], fixture['ip_range'])
        changed = list(real.pairs)
        changed[-1] = changed[0]
        forged = SimpleNamespace(hands=real.hands, budget=real.budget, pairs=changed)
        with patch.object(benchmark, 'prepare_flop_worlds', return_value=forged):
            with self.assertRaisesRegex(ValueError, 'private-pair support'):
                benchmark.validate_spec(self.spec)

    def test_policy_files_are_published_only_after_clean_source_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            checkout = workspace / 'checkout'
            checkout.mkdir()
            policy_dir = checkout / 'policies'
            report = checkout / 'report.json'
            stage = workspace / 'staged-policies'
            checks = []

            def clean_source():
                clean = not policy_dir.exists() and not report.exists()
                checks.append(clean)
                return clean

            preflights = [{'fixture_id': fixture['id'], 'iterations': count,
                           'status': 'admitted', 'solver_budget': {}}
                          for fixture in self.spec['fixtures']
                          for count in self.spec['checkpoints']]

            def measured(fixture, spec, oracle, iterations, expected_budget, **kwargs):
                row = {'iterations': iterations, 'target_met': True,
                       'complete_call_plus_json_seconds': 1., 'payload_sha256': 'same',
                       'verification': {'nash_conv': 0.02 if iterations == 100 else 0.001},
                       'work_budget': expected_budget}
                if kwargs.get('preserve_result'):
                    row['serialized_policy_result'] = {'strategy': [], 'fixture': fixture['id']}
                if kwargs.get('include_coverage'):
                    row['action_coverage'] = {'all_required_covered': True}
                return row

            oracle = {'counts': [{'ordered_outcomes': 1980} for _ in range(58)]}
            with patch.object(benchmark, 'ROOT', checkout), \
                 patch.object(benchmark, 'POLICY_DIR', policy_dir), \
                 patch.object(benchmark, 'POLICY_STAGING_DIR', stage), \
                 patch.object(benchmark, 'OUTPUT_PATH', report), \
                 patch.object(benchmark, 'LIVE_PATH', workspace / 'live.json'), \
                 patch.object(benchmark, '_is_clean', side_effect=clean_source), \
                 patch.object(benchmark, '_revision', return_value=self.spec['baseline_main']), \
                 patch.object(benchmark, '_hashes', return_value={}), \
                 patch.object(benchmark.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                 patch.object(benchmark, 'preflight_all', return_value=preflights), \
                 patch.object(benchmark, 'prepare_oracle', return_value=oracle), \
                 patch.object(benchmark, '_measured', side_effect=measured):
                benchmark.run(copy.deepcopy(self.spec))
            self.assertEqual(checks, [True, True])
            self.assertEqual(len(list(policy_dir.glob('*.json'))), 2)
            self.assertTrue(report.exists())
            self.assertNotIn(b'\r\n', report.read_bytes())
            for policy in policy_dir.glob('*.json'):
                self.assertNotIn(b'\r\n', policy.read_bytes())

    def test_fixture_spec_and_independent_blocker_prior_census(self):
        census = benchmark.validate_spec(self.spec)
        collisions, compatible, total, oop_marginals, ip_marginals = _independent_prior_census()
        self.assertEqual(collisions, list(EXPECTED_COLLISIONS))
        self.assertEqual(compatible, 58)
        self.assertEqual(total, 1185)
        self.assertEqual(oop_marginals, [264, 144, 64, 210, 84, 180, 203, 36])
        self.assertEqual(ip_marginals, [198, 288, 136, 66, 84, 180, 203, 30])
        expected = self.spec["expected_chance"]
        self.assertEqual(expected["candidate_pairs"], 64)
        self.assertEqual(expected["compatible_pairs"], compatible)
        self.assertEqual(expected["unordered_boards"], compatible * 990)
        self.assertEqual(expected["ordered_future_worlds"], compatible * 1980)
        self.assertEqual(expected["compatible_weight_unit_total"], total)
        self.assertEqual(expected["oop_marginal_numerators"], oop_marginals)
        self.assertEqual(expected["ip_marginal_numerators"], ip_marginals)
        self.assertEqual(census["compatible_pairs"], compatible)
        self.assertEqual(census["compatible_weight_normalizer"], "1185/64")
        self.assertEqual([len(OOP_HANDS), len(IP_HANDS)], [8, 8])
        self.assertEqual(len(self.spec["fixtures"]), 2)
        self.assertEqual([f["id"] for f in self.spec["fixtures"]], [
            "weighted-8x8-stack12-raises1", "weighted-8x8-stack24-raises2"])
        self.assertEqual([f["config"]["effective_stack"] for f in self.spec["fixtures"]], [12, 24])
        self.assertEqual([f["config"]["max_raises"] for f in self.spec["fixtures"]], [1, 2])
        self.assertTrue(all(f["required_4000_admission"] and f["required_4000_accuracy"]
                            for f in self.spec["fixtures"]))
        self.assertEqual(self.spec["fixtures"][1]["required_action_coverage"], [
            "oop-lead-bet-ip-raise-oop-reraise",
            "oop-check-ip-bet-oop-checkraise-ip-reraise",
        ])

        mutated = copy.deepcopy(self.spec)
        mutated["expected_chance"]["compatible_pairs"] -= 1
        with self.assertRaises(ValueError):
            benchmark.validate_spec(mutated)

    def test_all_six_preflights_stop_before_ranking_or_training(self):
        self.assertEqual(self.spec["checkpoints"], [100, 1000, 4000])
        outcomes = []
        with patch.object(worlds, "rank_hand", side_effect=AssertionError("ranking in preflight")) as rank, \
             patch.object(solver, "train_public_batched", side_effect=AssertionError("training in preflight")) as train:
            for fixture in self.spec["fixtures"]:
                for iterations in self.spec["checkpoints"]:
                    outcomes.append(benchmark.preflight(fixture, iterations, "cfrplus"))
            rank.assert_not_called()
            train.assert_not_called()
        self.assertEqual(len(outcomes), 6)
        self.assertTrue(all(outcome["ranking_started"] is False for outcome in outcomes))
        for outcome in outcomes:
            self.assertIn(outcome["status"], {"admitted", "rejected"})
            if outcome["status"] == "admitted":
                self.assertLessEqual(outcome["solver_budget"]["total_loop_entries_upper_bound"],
                                     500_000_000)
                self.assertLessEqual(outcome["tree"]["public_states"], 25_000)
                self.assertLessEqual(outcome["tree"]["information_action_slots"], 1_000_000)
                self.assertEqual(outcome["plan_budget"]["candidate_pairs"], 64)
                self.assertEqual(outcome["plan_budget"]["compatible_pairs"], 58)
                self.assertEqual(outcome["plan_budget"]["unordered_boards"], 57_420)
        for fixture in self.spec["fixtures"]:
            if fixture.get("required_4000_admission"):
                outcome = next(item for item in outcomes
                               if item["fixture_id"] == fixture["id"]
                               and item["iterations"] == 4000)
                self.assertEqual(outcome["status"], "admitted")

    def test_existing_direct_solver_signature_is_unchanged(self):
        self.assertEqual(
            str(inspect.signature(solver.solve_flop_checkdown)),
            "(board, oop_range, ip_range, *, config=None, iterations=1000, algorithm='cfrplus')",
        )

    def test_action_coverage_requires_flop_rows_and_full_ordered_histories(self):
        pair = {"oop_hand": "AdAs", "ip_hand": "KdKs"}
        result = {"board": ["2c", "3c", "4d"],
                  "config": {"effective_stack": 24},
                  "pair_equities": [pair], "strategy": _complete_raise_rows()}
        coverage = benchmark.action_coverage(result)
        self.assertTrue(coverage["all_required_covered"])
        self.assertEqual(set(coverage["required_sequences"]), {
            "oop-lead-bet-ip-raise-oop-reraise",
            "oop-check-ip-bet-oop-checkraise-ip-reraise",
        })
        for sequence_id, item in coverage["required_sequences"].items():
            self.assertTrue(item["covered"])
            expected_path = (
                [("oop", ()), ("ip", ("bet@3",)),
                 ("oop", ("bet@3", "raise@9"))]
                if sequence_id == "oop-lead-bet-ip-raise-oop-reraise"
                else [("oop", ()), ("ip", ("check",)),
                      ("oop", ("check", "bet@3")),
                      ("ip", ("check", "bet@3", "raise@9"))]
            )
            self.assertEqual(
                [(step["player"], tuple(step["history"]))
                 for step in item["witness"]],
                expected_path,
            )
            self.assertTrue(all(step["player"] in {"oop", "ip"} for step in item["witness"]))

        preflop_rows = _complete_raise_rows(street="preflop")
        false_positive = benchmark.action_coverage({**result, "strategy": preflop_rows})
        self.assertFalse(false_positive["all_required_covered"])
        self.assertTrue(all(not item["covered"]
                            for item in false_positive["required_sequences"].values()))

        # A one-raise tree has no final re-raise row on either line.
        one_raise = _complete_raise_rows()[:2] + _complete_raise_rows()[3:5]
        max_one_result = {**result, "config": {"effective_stack": 24, "max_raises": 1},
                          "strategy": one_raise}
        one_raise_coverage = benchmark.action_coverage(max_one_result)
        self.assertFalse(one_raise_coverage["all_required_covered"])

        # A raise at the wrong public history cannot fill the missing response.
        wrong_history = _complete_raise_rows()
        wrong_history[2] = _row("oop", "AdAs", ("raise@9", "bet@3"),
                                [_action("raise", 18.0, 9.0)])
        wrong_history_coverage = benchmark.action_coverage({**result, "strategy": wrong_history})
        self.assertFalse(wrong_history_coverage["required_sequences"][
            "oop-lead-bet-ip-raise-oop-reraise"]["covered"])


if __name__ == "__main__":
    unittest.main()
