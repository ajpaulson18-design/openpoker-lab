"""Independent certificate-verifier checks using a frozen serialized witness."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from scripts.verify_preflop_sequence import _canonical, _check_json_envelope, verify_certificate


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/preflop-weighted-sequence-candidate-v1.json"


def _witness():
    return json.loads(FIXTURE.read_bytes())


def _resign(witness):
    payload = {key: value for key, value in witness.items() if key != "artifact_sha256"}
    witness["artifact_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    return witness


class TestWeightedPreflopSequenceVerifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FIXTURE.is_file():
            raise unittest.SkipTest("Root-owned frozen candidate fixture has not been installed")
        cls.witness = _witness()

    def test_frozen_witness_reconstructs_tree_matrix_lp_and_legal_responses(self):
        summary = verify_certificate(copy.deepcopy(self.witness))
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["verified_count_pairs"], 3)
        self.assertEqual(summary["verified_physical_boards"], 5_136_912)
        self.assertEqual(summary["raw_compatible_pair_weight_normalizer"], "13/8")
        self.assertEqual(summary["blocked_private_pair"], ["AdAs", "AsKh", "1/4"])
        self.assertEqual(summary["public_states"], 19)
        self.assertEqual(summary["information_sets"], [6, 8])
        self.assertEqual(summary["sequences"], [19, 19])
        self.assertEqual(summary["payoff_matrix_shape"], [19, 19])
        self.assertEqual(summary["value_fraction"], "100107990869/130471452826")
        self.assertEqual(summary["value_sb_fraction"], summary["value_fraction"])
        from fractions import Fraction
        self.assertEqual(Fraction(summary["value_bb_fraction"]), -Fraction(summary["value_fraction"]))
        self.assertEqual(summary["sb_best_response_fraction"], summary["value_fraction"])
        self.assertEqual(summary["bb_best_response_fraction"], "-100107990869/130471452826")
        self.assertEqual(summary["bb_best_response_sb_value_fraction"], summary["value_fraction"])
        self.assertEqual(summary["nash_conv_fraction"], "0")
        self.assertEqual((summary["rank_calls"], summary["board_enumerations"]), (0, 0))

    def test_zero_reach_information_set_accepts_any_normalized_legal_fallback(self):
        candidate = copy.deepcopy(self.witness)
        row = next(item for item in candidate["policies"]
                   if item["zero_realization_fallback"])
        self.assertEqual(len(row["probabilities"]), 2)
        row["probabilities"] = ["1", "0"]
        verify_certificate(_resign(candidate))

    def test_recomputed_self_checksum_does_not_hide_semantic_tampering(self):
        mutations = []

        def count_row(w):
            w["count_provenance"]["rows"][0]["wins"] += 1
        mutations.append(("pinned count", count_row))

        def prior(w):
            w["pair_priors"][0]["prior_fraction"] = "1/2"
        mutations.append(("conditioned prior", prior))

        def action_history(w):
            w["census"]["public_tree"]["actions"][2]["token"] = "raise@2.25"
        mutations.append(("legal root action", action_history))

        def limp_option(w):
            w["census"]["public_tree"]["children"][1]["actions"].pop(0)
        mutations.append(("limp BB option", limp_option))

        def matrix_payoff(w):
            old = w["census"]["payoff_matrix"]["fractions"][0][0]
            from fractions import Fraction
            w["census"]["payoff_matrix"]["fractions"][0][0] = str(Fraction(old) + 1)
        mutations.append(("payoff cell", matrix_payoff))

        def flow(w):
            w["census"]["flow_constraints"][0]["rhs"] = "0"
        mutations.append(("flow equation", flow))

        def dual_slack(w):
            current = w["oop_lp"]["inequality_slacks"]["fractions"][0]
            from fractions import Fraction
            w["oop_lp"]["inequality_slacks"]["fractions"][0] = str(Fraction(current) + 1)
        mutations.append(("lower dual slack", dual_slack))

        def hidden_hand(w):
            w["policies"][0]["hand"] = "AsKh"
        mutations.append(("own-hand information key", hidden_hand))

        def policy_zero_marker(w):
            next(row for row in w["policies"] if row["zero_realization_fallback"])[
                "zero_realization_fallback"] = False
        mutations.append(("zero-realization marker", policy_zero_marker))

        def false_value(w):
            w["equilibrium"]["profile_value_fraction"] = "0"
        mutations.append(("profile value", false_value))

        for label, mutate in mutations:
            with self.subTest(tampering=label):
                candidate = copy.deepcopy(self.witness)
                mutate(candidate)
                with self.assertRaises(ValueError):
                    verify_certificate(_resign(candidate))

    def test_bad_digest_and_unbounded_matrix_shape_are_rejected(self):
        bad_hash = copy.deepcopy(self.witness)
        bad_hash["artifact_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "self-checksum"):
            verify_certificate(bad_hash)

        bad_shape = copy.deepcopy(self.witness)
        bad_shape["census"]["payoff_matrix"]["fractions"].append(["0"] * 19)
        with self.assertRaisesRegex(ValueError, "matrix dimensions"):
            verify_certificate(_resign(bad_shape))

        bad_fraction = copy.deepcopy(self.witness)
        bad_fraction["census"]["payoff_matrix"]["fractions"][0][0] = "9" * 5000
        with self.assertRaisesRegex(ValueError, "string exceeds"):
            verify_certificate(_resign(bad_fraction))

        with self.assertRaisesRegex(ValueError, "key exceeds"):
            _check_json_envelope({"k" * 5000: 0})
        with self.assertRaisesRegex(ValueError, "string exceeds"):
            _check_json_envelope("x" * 5000)

        bool_count = copy.deepcopy(self.witness)
        bool_count["census"]["tree_counts"]["decision_nodes"] = True
        with self.assertRaisesRegex(ValueError, "tree census"):
            verify_certificate(_resign(bool_count))


if __name__ == "__main__":
    unittest.main()
