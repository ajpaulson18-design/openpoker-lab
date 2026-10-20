"""Regression: correct value alone does not certify equilibrium."""
import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[1]

from scripts import full_deck_raised_reference as reference
from scripts import turn_river_validation as numeric_rules
from scripts.full_physical_exact_oracle import METRICS, audit_policy
from scripts.raised_turn_argmax_control import (
    ACCEPTED_INPUT_SHA256,
    MAX_SOURCE_BYTES,
    _first_argmax_index,
    derive_argmax_control,
)


POLICY_DIR = REPO / "benchmarks/results/full-deck-raised-turn-clean-witness-policies-v1"
EXPECTED = {
    "value_oop": "-400/21",
    "value_ip": "400/21",
    "oop_best_response_value": "-200/21",
    "ip_best_response_value": "4475/231",
    "oop_best_response_gain": "200/21",
    "ip_best_response_gain": "25/77",
    "nash_conv": "325/33",
    "exploitability": "325/66",
}


def _direct_pair_terms(policy, worlds, root, config):
    chosen = {}
    for row in policy["strategy"]:
        index = _first_argmax_index([action["probability"] for action in row["actions"]])
        chosen[(0 if row["player"] == "oop" else 1, row["hand"], tuple(row["history"]))] = \
            row["actions"][index]["history_key"]
    pair_totals = defaultdict(Fraction)
    river_counts = defaultdict(int)
    payoff_counts = defaultdict(lambda: defaultdict(int))
    for world in worlds:
        node = root
        while not isinstance(node, numeric_rules._Terminal):
            if isinstance(node, numeric_rules._Chance):
                node = node.branches[world["river"]]
            else:
                hand = "".join(sorted(world["hands"][node.player]))
                token = chosen[(node.player, hand, node.history)]
                node = node.children[next(i for i, action in enumerate(node.actions)
                                          if action.token == token)]
        sign = ((1 if node.winner == 0 else -1)
                if node.kind == "fold" else world["sign"])
        payoff = sign * (Fraction(config.pot) / 2 +
                         min(Fraction(c) for c in node.contributions))
        pair = tuple("".join(sorted(hand)) for hand in world["hands"])
        pair_totals[pair] += world["weight"] * payoff
        river_counts[pair] += 1
        payoff_counts[pair][payoff] += 1
    return dict(pair_totals), dict(river_counts), dict(payoff_counts)


class RaisedTurnArgmaxControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = reference.model()

    def test_argmax_control_preserves_metadata_and_recomputes_all_exact_metrics(self):
        for backend in ("materialized", "matrix-free"):
            with self.subTest(backend=backend):
                path = POLICY_DIR / f"full-deck-raised-turn-clean-witness-v1-{backend}.json"
                source_bytes = path.read_bytes()
                source_sha256 = hashlib.sha256(source_bytes).hexdigest()
                self.assertEqual(source_sha256, ACCEPTED_INPUT_SHA256[backend])
                source = json.loads(source_bytes)
                before_mapping = deepcopy(source)
                before_bytes = source_bytes
                derived, audited = derive_argmax_control(
                    source, source_bytes, expected_backend=backend,
                    model=self.model)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source_sha256)
                self.assertEqual(path.read_bytes(), before_bytes)
                self.assertEqual(source, before_mapping)
                self.assertEqual(len(derived["strategy"]), 2404)
                self.assertEqual(derived["derived_provenance"]["source_policy_sha256"],
                                 source_sha256)
                self.assertEqual(derived["derived_provenance"]["training_calls"], 0)
                self.assertEqual(derived["derived_provenance"]["tie_break"],
                                 "first action in original legal-action order")
                self.assertFalse(derived["derived_provenance"]["exact_zero_required"])
                for stale in ("research_profile", "average_schedule", "iterations",
                              "training_passes_per_iteration", "diagnostics_backend",
                              "argmax_control_provenance"):
                    self.assertNotIn(stale, derived)
                self.assertEqual(derived["method"],
                                 "Deterministic first-action argmax control of a pinned clean witness")
                for original, candidate in zip(source["strategy"], derived["strategy"]):
                    self.assertEqual(set(original), set(candidate))
                    self.assertEqual({k: v for k, v in original.items() if k != "actions"},
                                     {k: v for k, v in candidate.items() if k != "actions"})
                    self.assertEqual(len(original["actions"]), len(candidate["actions"]))
                    selected = max(range(len(original["actions"])),
                                   key=lambda i: original["actions"][i]["probability"])
                    for i, (old, new) in enumerate(zip(original["actions"], candidate["actions"])):
                        self.assertEqual({k: v for k, v in old.items() if k != "probability"},
                                         {k: v for k, v in new.items() if k != "probability"})
                        self.assertEqual(new["probability"], float(i == selected))
                self.assertEqual(set(audited["metrics"]), set(METRICS))
                self.assertEqual({name: str(value) for name, value in audited["metrics"].items()},
                                 EXPECTED)
                self.assertEqual({name: derived[name] for name in METRICS},
                                 {name: float(audited["metrics"][name]) for name in METRICS})
                fixture = self.model[0]
                numeric = numeric_rules.replay_policy(
                    derived, fixture["oop"], fixture["ip"],
                    board=fixture["board"], config=fixture["config"])
                for name in METRICS:
                    self.assertAlmostEqual(numeric[name], float(Fraction(EXPECTED[name])),
                                           delta=1e-9, msg=name)

    def test_source_identity_backend_and_stale_metrics_are_guarded(self):
        path = POLICY_DIR / "full-deck-raised-turn-clean-witness-v1-materialized.json"
        raw = path.read_bytes()
        source = json.loads(raw)
        with self.assertRaisesRegex(ValueError, "accepted backend pin"):
            derive_argmax_control(source, raw, expected_backend="matrix-free",
                                  model=self.model)
        with self.assertRaisesRegex(ValueError, "accepted backend pin"):
            derive_argmax_control(source, raw + b" ", expected_backend="materialized",
                                  model=self.model)
        changed = dict(source)
        changed["value_oop"] = 999
        with self.assertRaisesRegex(ValueError, "does not match"):
            derive_argmax_control(changed, raw, expected_backend="materialized",
                                  model=self.model)
        with self.assertRaisesRegex(ValueError, "unknown accepted witness backend"):
            derive_argmax_control(source, raw, expected_backend="other", model=self.model)
        with self.assertRaisesRegex(ValueError, "2 MB limit"):
            derive_argmax_control(source, raw + b" " * (MAX_SOURCE_BYTES + 1),
                                  expected_backend="materialized", model=self.model)
        with self.assertRaisesRegex(ValueError, "JSON object"):
            derive_argmax_control([], raw, expected_backend="materialized", model=self.model)

    def test_first_action_tie_break_is_deterministic(self):
        self.assertEqual(_first_argmax_index([0.5, 0.5, 0.25]), 0)
        self.assertEqual(_first_argmax_index([0.0, 1.0, 1.0]), 1)

    def test_legal_root_bet_deviation_reaches_the_reported_oop_best_response(self):
        fixture = self.model[0]
        _, _, config, worlds, _, root, _ = self.model
        for backend in ("materialized", "matrix-free"):
            with self.subTest(backend=backend):
                path = POLICY_DIR / f"full-deck-raised-turn-clean-witness-v1-{backend}.json"
                source_bytes = path.read_bytes()
                source = json.loads(source_bytes)
                pure, baseline = derive_argmax_control(
                    source, source_bytes, expected_backend=backend,
                    model=self.model)
                candidate = json.loads(json.dumps(pure))
                row = next(row for row in candidate["strategy"]
                           if row["player"] == "oop" and row["hand"] == "KhKs"
                           and row["history"] == [])
                self.assertEqual([a["history_key"] for a in row["actions"]],
                                 ["check", "bet@50"])
                row["actions"][0]["probability"] = 0.0
                row["actions"][1]["probability"] = 1.0
                changed = [new for old, new in zip(pure["strategy"], candidate["strategy"])
                           if old != new]
                self.assertEqual(len(changed), 1)
                self.assertEqual((changed[0]["player"], changed[0]["hand"],
                                  changed[0]["history"]), ("oop", "KhKs", []))
                deviated = audit_policy(candidate, self.model)
                self.assertEqual(deviated["metrics"]["value_oop"], Fraction(-200, 21))
                self.assertEqual(deviated["metrics"]["value_oop"] -
                                 baseline["metrics"]["value_oop"], Fraction(200, 21))
                numeric = numeric_rules.replay_policy(
                    candidate, fixture["oop"], fixture["ip"],
                    board=fixture["board"], config=fixture["config"])
                self.assertAlmostEqual(numeric["value_oop"], -200 / 21, delta=1e-9)

                # Independent deterministic physical-world walk: no call to the
                # exact oracle's evaluator/BR routines for these literal pair terms.
                baseline_terms, baseline_counts, baseline_payoffs = _direct_pair_terms(
                    pure, worlds, root, config)
                self.assertEqual(baseline_counts, {
                    ("AhAs", "AcAd"): 44, ("AhAs", "KcKd"): 44,
                    ("KhKs", "AcAd"): 44, ("KhKs", "KcKd"): 44,
                })
                self.assertEqual(baseline_terms, {
                    ("AhAs", "AcAd"): Fraction(0),
                    ("AhAs", "KcKd"): Fraction(100, 7),
                    ("KhKs", "AcAd"): Fraction(-400, 21),
                    ("KhKs", "KcKd"): Fraction(-100, 7),
                })
                self.assertEqual(sum(baseline_terms.values()), Fraction(-400, 21))
                self.assertEqual(baseline_payoffs, {
                    ("AhAs", "AcAd"): {Fraction(0): 44},
                    ("AhAs", "KcKd"): {Fraction(100): 44},
                    ("KhKs", "AcAd"): {Fraction(-50): 44},
                    ("KhKs", "KcKd"): {Fraction(-50): 44},
                })
                pair_totals, river_counts, payoff_counts = _direct_pair_terms(
                    candidate, worlds, root, config)
                self.assertEqual(river_counts, baseline_counts)
                self.assertEqual(pair_totals, {
                    ("AhAs", "AcAd"): Fraction(0),
                    ("AhAs", "KcKd"): Fraction(100, 7),
                    ("KhKs", "AcAd"): Fraction(-800, 21),
                    ("KhKs", "KcKd"): Fraction(100, 7),
                })
                self.assertEqual(sum(pair_totals.values()), Fraction(-200, 21))
                self.assertEqual(payoff_counts, {
                    ("AhAs", "AcAd"): {Fraction(0): 44},
                    ("AhAs", "KcKd"): {Fraction(100): 44},
                    ("KhKs", "AcAd"): {Fraction(-100): 44},
                    ("KhKs", "KcKd"): {Fraction(50): 44},
                })


if __name__ == "__main__":
    unittest.main()
