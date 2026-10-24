from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import preflop_mixed_pure_response as rules
from scripts import preflop_three_rank_pure_response as response
from scripts import preflop_three_rank_sequence_candidate as producer


def _uniform_rows(game):
    rows = []
    for player, hands in ((0, game["sb_hands"]), (1, game["bb_hands"])):
        for hand in hands:
            for (owner, history), actions in rules.INFO_MENUS.items():
                if owner == player:
                    rows.append({"player": player, "hand": hand, "history": list(history),
                                 "actions": list(actions),
                                 "probabilities": [str(Fraction(1, len(actions)))] * len(actions)})
    return rows


def _pure_fold_profile(game):
    rows = _uniform_rows(game)
    for row in rows:
        row["probabilities"] = ["1"] + ["0"] * (len(row["actions"]) - 1)
    return rows


class ThreeRankPureResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The checkout is intentionally dirty before this module is committed;
        # retain real saved-data authentication while isolating only its clean-
        # source prerequisite.
        with patch.object(response.sources.jj, "_current_source_check"):
            cls.game = response._build_game()
            cls.authenticated_classes = response._source_classes()
        cls.valid_rows = _uniform_rows(cls.game)

    def test_literal_support_global_priors_and_authenticated_source_class_mapping(self):
        game = self.game
        self.assertEqual((len(game["sb_hands"]), len(game["bb_hands"]), len(game["pairs"])),
                         (18, 6, 108))
        self.assertEqual(game["raw_weight_normalizer"], Fraction(63))
        self.assertEqual(game["class_counts"], {rank: {0: 6, 1: 24, 2: 6} for rank in "AQJ"})
        self.assertEqual(sum((p["prior"] for p in game["pairs"]), Fraction()), Fraction(1))
        expected = {"A": Fraction(1, 63), "Q": Fraction(1, 126), "J": Fraction(1, 252)}
        for pair in game["pairs"]:
            self.assertEqual(pair["prior"], expected[pair["rank"]])
            self.assertEqual(sum(pair["counts"][:3]), response.BOARD_COUNT)
            self.assertEqual(pair["counts"],
                             self.authenticated_classes[pair["rank"]][pair["overlap"]])
            self.assertEqual(pair["showdown_mean"],
                             Fraction(pair["counts"][0] - pair["counts"][2], response.BOARD_COUNT))
        for rank in "AQJ":
            self.assertEqual({p["overlap"] for p in game["pairs"] if p["rank"] == rank}, {0, 1, 2})

    def test_complete_uniform_policy_is_exactly_scored_and_keeps_miss(self):
        with patch.object(response, "_build_game", return_value=self.game):
            report = response.verify_policy(deepcopy(self.valid_rows))
        self.assertEqual(report["information_set_count"], 96)
        self.assertEqual(report["pure_response_policies_enumerated"],
                         {"sb": 18 * 48, "bb": 6 * 36, "total": 1080})
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["exact_mutual_response_verified"])
        self.assertEqual(report["overlap_class_pair_counts"],
                         {rank: {"0": 6, "1": 24, "2": 6} for rank in "AQJ"})
        self.assertEqual(json.loads(json.dumps(report)), report)
        self.assertEqual(Fraction(report["nash_conv_fraction"]),
                         Fraction(report["sb_best_response_gain_fraction"]) +
                         Fraction(report["bb_best_response_gain_fraction"]))

    def test_non_equilibrium_pure_policy_is_reported_not_rejected(self):
        rows = _pure_fold_profile(self.game)
        with patch.object(response, "_build_game", return_value=self.game):
            report = response.verify_policy(rows, claimed_value="-1/2")
        self.assertEqual(report["status"], "failed")
        self.assertTrue(report["claimed_profile_value_matches"])
        self.assertGreater(Fraction(report["nash_conv_fraction"]), 0)

    def test_rejects_missing_duplicate_and_opponent_information_rows(self):
        with patch.object(response, "_build_game", return_value=self.game):
            with self.assertRaisesRegex(ValueError, "96"):
                response.verify_policy(self.valid_rows[:-1])
            duplicate = deepcopy(self.valid_rows)
            duplicate[-1] = deepcopy(duplicate[0])
            with self.assertRaisesRegex(ValueError, "duplicate"):
                response.verify_policy(duplicate)
            leaked = deepcopy(self.valid_rows)
            leaked[0]["opponent_hand"] = "KdKs"
            with self.assertRaisesRegex(ValueError, "leaking"):
                response.verify_policy(leaked)

    def test_rejects_wrong_own_hand_history_menu_and_boolean_player(self):
        cases = []
        wrong_hand = deepcopy(self.valid_rows); wrong_hand[0]["hand"] = "KdKs"
        cases.append(wrong_hand)
        wrong_history = deepcopy(self.valid_rows); wrong_history[0]["history"] = ["private"]
        cases.append(wrong_history)
        wrong_menu = deepcopy(self.valid_rows); wrong_menu[0]["actions"] = ["call"]
        cases.append(wrong_menu)
        bool_player = deepcopy(self.valid_rows); bool_player[0]["player"] = True
        cases.append(bool_player)
        with patch.object(response, "_build_game", return_value=self.game):
            for rows in cases:
                with self.subTest(row=rows[0]), self.assertRaises(ValueError):
                    response.verify_policy(rows)

    def test_rejects_noncanonical_float_unbounded_and_unnormalized_probabilities(self):
        variants = []
        float_prob = deepcopy(self.valid_rows); float_prob[0]["probabilities"][0] = 0.25
        variants.append(float_prob)
        noncanonical = deepcopy(self.valid_rows); noncanonical[0]["probabilities"][0] = "2/8"
        variants.append(noncanonical)
        unnormalized = deepcopy(self.valid_rows); unnormalized[0]["probabilities"] = ["1"] * len(unnormalized[0]["actions"])
        variants.append(unnormalized)
        zero_divisor = deepcopy(self.valid_rows); zero_divisor[0]["probabilities"][0] = "1/0"
        variants.append(zero_divisor)
        with patch.object(response, "_build_game", return_value=self.game):
            for rows in variants:
                with self.subTest(probabilities=rows[0]["probabilities"]), self.assertRaises(ValueError):
                    response.verify_policy(rows)

    def test_exponent_fraction_is_rejected_before_fraction_parser(self):
        with patch.object(response, "Fraction", side_effect=AssertionError("fraction parser called")):
            with self.assertRaisesRegex(ValueError, "integer/rational token"):
                response._fraction("1e1000000000", "policy probability")

    def test_claimed_value_mismatch_does_not_change_exact_response_metrics(self):
        with patch.object(response, "_build_game", return_value=self.game):
            no_claim = response.verify_policy(deepcopy(self.valid_rows))
            bad_claim = response.verify_policy(deepcopy(self.valid_rows), claimed_value="0")
        self.assertEqual(no_claim["profile_value_sb_fraction"], bad_claim["profile_value_sb_fraction"])
        self.assertFalse(bad_claim["claimed_profile_value_matches"])
        self.assertFalse(bad_claim["exact_mutual_response_verified"])

    @staticmethod
    def _candidate():
        report = {"schema_version": 1, "certificate_id": response.CERTIFICATE_ID,
                  "status": "candidate-only", "request": producer.expected_request(),
                  "transport_artifact_sha256": response.TRANSPORT_ARTIFACT_SHA256,
                  "value_candidate_fraction": "0", "policies": [],
                  "candidate_details": {"note": "bounded synthetic test envelope"}}
        report["artifact_sha256"] = hashlib.sha256(response._canonical_json(report)).hexdigest()
        return report

    def test_candidate_envelope_authenticates_before_policy_source_work(self):
        report = self._candidate()
        expected = {"exact_mutual_response_verified": False, "status": "failed"}
        with patch.object(response, "verify_policy", return_value=expected) as policy:
            receipt = response.verify_candidate(report)
        policy.assert_called_once_with([], "0")
        self.assertEqual(receipt["candidate_artifact_sha256"], report["artifact_sha256"])
        self.assertEqual(receipt["candidate_request_sha256"], response.REQUEST_SHA256)
        self.assertEqual(receipt["status"], "failed")

    def test_candidate_wrong_fixed_request_rejects_before_policy_audit(self):
        report = self._candidate()
        report["request"]["max_raises"] = 1
        report["artifact_sha256"] = hashlib.sha256(response._canonical_json(
            {key: value for key, value in report.items() if key != "artifact_sha256"})).hexdigest()
        with patch.object(response, "verify_policy", side_effect=AssertionError("policy called")):
            with self.assertRaisesRegex(ValueError, "request digest"):
                response.verify_candidate(report)

    def test_candidate_file_rejects_duplicate_and_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "candidate.json"
            for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}'):
                path.write_bytes(raw)
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    response.verify_candidate(path)

    def test_candidate_structural_edge_and_file_size_limits_precede_policy_audit(self):
        over_edges = {"a": [0] * 10_000, "b": [0] * 10_000,
                      "c": [0] * 10_000, "d": [0] * 10_000}
        with self.assertRaisesRegex(ValueError, "edge count"):
            response._bounded_envelope(over_edges)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "large.json"
            path.write_bytes(b" " * (response.MAX_CANDIDATE_BYTES + 1))
            with patch.object(response, "verify_policy", side_effect=AssertionError("policy called")):
                with self.assertRaisesRegex(ValueError, "oversized"):
                    response.verify_candidate(path)

    def test_candidate_file_rechecks_bytes_after_policy_audit(self):
        report = self._candidate()
        raw = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "candidate.json"
            path.write_bytes(raw)
            def mutate(*_args):
                path.write_bytes(raw + b" ")
                return {"exact_mutual_response_verified": False, "status": "failed"}
            with patch.object(response, "verify_policy", side_effect=mutate):
                with self.assertRaisesRegex(ValueError, "changed"):
                    response.verify_candidate(path)


if __name__ == "__main__":
    unittest.main()
