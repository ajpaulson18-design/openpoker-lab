"""Independent full-physical exact oracle checks; no solver/trainer is run."""
import json
from fractions import Fraction
from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[1]

from scripts import full_deck_raised_reference
from scripts import turn_river_validation as numeric_rules
from scripts.full_physical_exact_oracle import (
    METRICS,
    audit_policy,
    future_aware_best_response,
    make_check_call_policy,
)


RESULTS = REPO / "benchmarks" / "results"
EXACT_REPORT = RESULTS / "full-deck-raised-turn-tail-exact-v1.json"
POLICY_DIR = RESULTS / "full-deck-raised-turn-tail-policies-v1"
WITNESS_REPORT = RESULTS / "full-deck-raised-turn-clean-witness-v1.json"
WITNESS_DIR = RESULTS / "full-deck-raised-turn-clean-witness-policies-v1"


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _fraction(value):
    return Fraction(value)


class FullPhysicalExactOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = full_deck_raised_reference.model()

    def test_handwritten_check_call_anchor_and_future_aware_control(self):
        policy = make_check_call_policy(self.model)
        audited = audit_policy(policy, self.model)
        self.assertEqual(audited["metrics"], {
            "value_oop": Fraction(-2500, 231),
            "value_ip": Fraction(2500, 231),
            "oop_best_response_value": Fraction(2350, 231),
            "ip_best_response_value": Fraction(14975, 231),
            "oop_best_response_gain": Fraction(4850, 231),
            "ip_best_response_gain": Fraction(12475, 231),
            "nash_conv": Fraction(75),
            "exploitability": Fraction(75, 2),
        })
        self.assertEqual(future_aware_best_response(policy, self.model, 0),
                         Fraction(2825, 231))
        self.assertEqual(future_aware_best_response(policy, self.model, 1),
                         Fraction(15325, 231))
        self.assertEqual(audited["counters"]["structural_node_visits"], 18_234)

    def test_one_physical_river_deviation_is_not_grouped_or_conditioned(self):
        policy = make_check_call_policy(self.model)
        row = next(row for row in policy['strategy']
                   if row['player'] == 'ip' and row['hand'] == 'KcKd' and
                   row['history'] == ['check', 'check', 'river@2c', 'check'])
        self.assertEqual([action['history_key'] for action in row['actions']], ['check', 'bet@50'])
        for action in row['actions']:
            action['probability'] = float(action['history_key'] == 'bet@50')
        audited = audit_policy(policy, self.model)
        # Only AA-versus-KK gains another matched 50 at this single river:
        # original pair mass 1/7 times one of 44 rivers, with no conditioning.
        self.assertEqual(audited['metrics']['value_oop'],
                         Fraction(-2500, 231) + Fraction(50, 7 * 44))
        fixture = self.model[0]
        numeric = numeric_rules.replay_policy(policy, fixture['oop'], fixture['ip'],
                                               board=fixture['board'], config=fixture['config'])
        for metric in METRICS:
            self.assertAlmostEqual(float(audited['metrics'][metric]), numeric[metric], delta=1e-9)

    def test_original_saved_tails_against_published_exact_metrics(self):
        exact_report = _read_json(EXACT_REPORT)
        by_profile = {(p["backend"], p["profile"]): p
                      for p in exact_report["audit"]["profiles"]}
        for backend in ("materialized", "matrix-free"):
            with self.subTest(backend=backend):
                saved_tail = _read_json(POLICY_DIR /
                                        f"full-deck-raised-turn-tail-v1-{backend}-tail.json")
                audited = audit_policy(saved_tail, self.model)
                self.assertEqual(audited["counters"]["structural_node_visits"], 18_234)
                expected = by_profile[(backend, "tail")]["certificate"]["metrics"]
                self.assertEqual(set(expected), set(METRICS))
                for name in METRICS:
                    with self.subTest(backend=backend, metric=name):
                        self.assertEqual(audited["metrics"][name],
                                         _fraction(expected[name]))

    def test_actual_saved_clean_witnesses_against_witness_report(self):
        witness_report = _read_json(WITNESS_REPORT)
        by_backend = {p["backend"]: p for p in witness_report["results"]}
        for backend in ("materialized", "matrix-free"):
            with self.subTest(backend=backend):
                path = WITNESS_DIR / f"full-deck-raised-turn-clean-witness-v1-{backend}.json"
                policy = _read_json(path)
                audited = audit_policy(policy, self.model)
                self.assertEqual(audited["metrics"]["value_oop"], Fraction(-400, 21))
                self.assertEqual(audited["metrics"]["nash_conv"], Fraction(0))
                self.assertEqual(audited["metrics"]["exploitability"], Fraction(0))
                self.assertEqual(audited["metrics"]["oop_best_response_gain"], Fraction(0))
                self.assertEqual(audited["metrics"]["ip_best_response_gain"], Fraction(0))
                expected = by_backend[backend]["exact_certificate"]["metrics"]
                self.assertEqual(set(expected), set(METRICS))
                for name in METRICS:
                    with self.subTest(backend=backend, metric=name):
                        self.assertEqual(audited["metrics"][name], _fraction(expected[name]))
                self.assertEqual(audited["counters"]["structural_node_visits"], 18_234)


if __name__ == "__main__":
    unittest.main()
