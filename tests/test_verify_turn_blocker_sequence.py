"""Independent verifier regressions for the blocked-turn sequence witness."""
import copy
import hashlib
import json
import unittest
import uuid
from fractions import Fraction as F
from pathlib import Path
from unittest.mock import patch

from scripts import turn_rational_certificate as exact_helper
from scripts import turn_sequence_compact_lp as compact
from scripts import turn_blocker_sequence_equilibrium as candidate
from scripts import verify_turn_blocker_sequence as verify
from scripts.turn_blocker_sequence_fixture import FIXTURE

ROOT = Path(__file__).resolve().parents[1]
MODEL_SHA256 = "4ac32d6eb0103695d9137982a5c82f52e1a5c595491940b33e8993b96776d832"


class IndependentBlockerWitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This is intentionally a saved-file test: generation must complete first.
        cls.report = verify.verify_saved_artifact(verify.OUTPUT)

    def reject(self, edit, *, before_model=False):
        report = copy.deepcopy(self.report)
        edit(report)
        target = ROOT / "tests" / ("turn-blocker-verifier-" + uuid.uuid4().hex + ".json")
        try:
            target.write_text(json.dumps(report, sort_keys=True, allow_nan=False), encoding="utf-8")
            if before_model:
                with patch.object(verify, "model", side_effect=AssertionError("model rebuild must not run")):
                    with self.assertRaises((ValueError, KeyError, TypeError, IndexError)):
                        verify.verify_saved_artifact(target)
            else:
                with self.assertRaises((ValueError, KeyError, TypeError, IndexError)):
                    verify.verify_saved_artifact(target)
        finally:
            target.unlink(missing_ok=True)

    def test_frozen_independent_model_and_hidden_information_anchors(self):
        rebuilt = verify.model(FIXTURE)
        raw = json.dumps([rebuilt], indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
        self.assertEqual(hashlib.sha256(raw).hexdigest(), MODEL_SHA256)
        self.assertEqual((ROOT / "benchmarks/results/turn-blocker-sequence-model-v1.json").read_bytes(), raw)
        hidden = verify.verify_hidden_information_reference()
        self.assertEqual(hidden["worlds"], 6)
        self.assertEqual(hidden["information_sets"], 56)
        self.assertEqual(F(hidden["uniform_legal_ip_lower"]), F(-200, 7))
        self.assertEqual(F(hidden["illegal_hidden_opponent_ip_lower"]), F(-1725, 56))
        self.assertEqual(F(hidden["illegal_ip_gain"]), F(125, 56))
        self.assertEqual(F(hidden["product_mass_on_impossible_pair"]), F(3, 49))

    def test_accepts_saved_witness_without_candidate_lp_or_exact_evaluator(self):
        with patch.object(candidate, "_profile_candidate", side_effect=AssertionError("candidate profile search called")), \
             patch.object(compact, "solve_lp", side_effect=AssertionError("compact LP called")), \
             patch.object(exact_helper, "evaluate_exact", side_effect=AssertionError("exact production evaluator called")):
            report = verify.verify_saved_artifact(verify.OUTPUT)
        reach = verify.equilibrium_reach(report)
        self.assertEqual(F(reach["terminal_reach"]), 1)
        self.assertEqual(F(reach["river_decision_reach"]), 1)
        self.assertEqual(F(reach["turn_terminal_reach"])+F(reach["chance_reach"]), 1)

    def test_payoff_cell_and_own_realization_tampering(self):
        self.reject(lambda r: r["results"][0]["payoff_matrix"][0].__setitem__(0, "999"))
        self.reject(lambda r: r["results"][0]["lower_lp"]["own_realization"]["fractions"].__setitem__(1, "999"))

    def test_terminal_ledger_and_admission_tampering(self):
        self.reject(lambda r: r['results'][0]['terminal_ledger'][0].update(weighted_utility='999'))
        self.reject(lambda r: r['results'][0]['lp_admission'].update(legacy_rejected=False))
        self.reject(lambda r: r['results'][0]['lower_lp']['initial_tableau_forecast'].update(columns=255))

    def test_retained_root_free_dual_tampering(self):
        self.reject(lambda r: r["results"][0]["lower_lp"]["dual_flow_values"]["fractions"].__setitem__(0, "999"))
        self.reject(lambda r: r["results"][0]["upper_lp"]["dual_flow_values"]["fractions"].__setitem__(0, "999"))

    def test_raw_affine_rhs_row_sign_and_removed_root_metadata_tampering(self):
        def mutate_raw_rhs(report):
            labels = report["results"][0]["lower_lp"]["constraint_labels"]
            next(item for item in labels if item["id"].startswith("cover:"))["raw_rhs"] = "1"
        def mutate_row_sign(report):
            labels = report["results"][0]["upper_lp"]["constraint_labels"]
            next(item for item in labels if item["id"].startswith("cover:"))["row_sign"] *= -1
        self.reject(mutate_raw_rhs)
        self.reject(mutate_row_sign)
        self.reject(lambda r: r["results"][0]["lower_lp"]["empty_sequence_reduction"].update(removed_root_constraint="not-the-root"))
        self.reject(lambda r: r["results"][0]["upper_lp"]["empty_sequence_reduction"].update(root_free_flow_coordinate_retained=False))

    def test_hidden_own_hand_identity_and_future_leak_are_rejected(self):
        row = next(r for r in self.report["results"][0]["rational_strategy"] if r["street"] == "turn")
        identity = (row["player"], row["hand"], tuple(row["history"]))
        self.reject(lambda r: next(x for x in r["results"][0]["rational_strategy"]
                                   if (x["player"],x["hand"],tuple(x["history"])) == identity).update(hand="KdKd"))
        self.reject(lambda r: next(x for x in r["results"][0]["rational_strategy"]
                                   if (x["player"],x["hand"],tuple(x["history"])) == identity)["history"].append("river@8d"))

    def test_stale_source_and_noncanonical_fraction_reject_before_model_rebuild(self):
        self.reject(lambda r: r["source_sha256"].update({next(iter(r["source_sha256"])): "0" * 64}), before_model=True)
        self.reject(lambda r: r["results"][0]["payoff_matrix"][0].__setitem__(0, "0/2"), before_model=True)


if __name__ == "__main__":
    unittest.main()
