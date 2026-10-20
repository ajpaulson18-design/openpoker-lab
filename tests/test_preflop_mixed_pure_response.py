"""Focused adversarial tests for the independent mixed exact-response oracle."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import preflop_mixed_pure_response as oracle


def signed_candidate(rows, value="-1/2"):
    candidate = {
        "schema_version": 1,
        "certificate_id": "preflop-mixed-physical-exact-v1",
        "status": "candidate-only",
        "value_candidate_fraction": value,
        "policies": rows,
    }
    candidate["artifact_sha256"] = hashlib.sha256(oracle._canonical(candidate)).hexdigest()
    return candidate


def all_fold_rows(game):
    rows = []
    for player, hands in ((0, game["sb_hands"]), (1, game["bb_hands"])):
        for hand in hands:
            for history, actions in oracle._player_infos(player):
                chosen = "check" if player == 1 and history == ("call",) else "fold"
                rows.append({
                    "player": player,
                    "hand": hand,
                    "history": list(history),
                    "actions": list(actions),
                    "probabilities": ["1" if action == chosen else "0" for action in actions],
                })
    return rows


class MixedPureResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = oracle._build_game()
        cls.rows = all_fold_rows(cls.game)
        cls.candidate = signed_candidate(cls.rows)

    def verify_cached_game(self, candidate):
        with patch.object(oracle, "_build_game", return_value=self.game):
            return oracle.verify_candidate(candidate)

    def test_independent_source_mapping_covers_all_72_physical_pairs(self):
        game = self.game
        self.assertEqual(len(game["pairs"]), 72)
        self.assertEqual(game["raw_weight_normalizer"], 54)
        self.assertEqual(game["class_counts"], {
            "A": {0: 6, 1: 24, 2: 6},
            "Q": {0: 6, 1: 24, 2: 6},
        })
        self.assertEqual(sum((row["prior"] for row in game["pairs"]), 0), 1)
        self.assertEqual(len({row["sb_hand"] for row in game["pairs"]}), 12)
        self.assertEqual(len({row["bb_hand"] for row in game["pairs"]}), 6)
        self.assertTrue(all(row["counts"][3] == 1_712_304 for row in game["pairs"]))
        self.assertTrue(all(row["prior"].denominator in (54, 108) for row in game["pairs"]))

    def test_legal_non_equilibrium_policy_is_audited_but_not_certified(self):
        summary = self.verify_cached_game(self.candidate)
        self.assertEqual(summary["status"], "failed")
        self.assertFalse(summary["exact_mutual_response_verified"])
        self.assertTrue(summary["claimed_profile_value_matches"])
        self.assertEqual(summary["profile_value_sb_fraction"], "-1/2")
        self.assertNotEqual(summary["nash_conv_fraction"], "0")
        self.assertEqual(summary["pure_response_policies_enumerated"],
                         {"sb": 576, "bb": 216, "total": 792})
        self.assertTrue(summary["illegal_clairvoyant_control"]["sb_at_least_legal_response"])
        self.assertTrue(summary["illegal_clairvoyant_control"]["bb_at_least_legal_response"])

    def test_rejects_candidate_hash_row_menu_and_rational_tampering(self):
        wrong_hash = deepcopy(self.candidate)
        wrong_hash["value_candidate_fraction"] = "0"
        with patch.object(oracle, "_build_game", return_value=self.game):
            with self.assertRaisesRegex(ValueError, "checksum"):
                oracle.verify_candidate(wrong_hash)

        missing = deepcopy(self.candidate)
        missing["policies"].pop()
        missing["artifact_sha256"] = hashlib.sha256(
            oracle._canonical({k: v for k, v in missing.items() if k != "artifact_sha256"})
        ).hexdigest()
        with patch.object(oracle, "_build_game", return_value=self.game):
            with self.assertRaisesRegex(ValueError, "72 policy rows"):
                oracle.verify_candidate(missing)

        menu = deepcopy(self.candidate)
        menu["policies"][0]["actions"][0] = "call@cheat"
        menu["artifact_sha256"] = hashlib.sha256(
            oracle._canonical({k: v for k, v in menu.items() if k != "artifact_sha256"})
        ).hexdigest()
        with patch.object(oracle, "_build_game", return_value=self.game):
            with self.assertRaisesRegex(ValueError, "action menu"):
                oracle.verify_candidate(menu)

        malformed = deepcopy(self.candidate)
        malformed["policies"][0]["probabilities"][0] = "01/1"
        malformed["artifact_sha256"] = hashlib.sha256(
            oracle._canonical({k: v for k, v in malformed.items() if k != "artifact_sha256"})
        ).hexdigest()
        with patch.object(oracle, "_build_game", return_value=self.game):
            with self.assertRaisesRegex(ValueError, "Noncanonical"):
                oracle.verify_candidate(malformed)

    def test_rejects_information_leaks_and_boolean_probability(self):
        leak = deepcopy(self.candidate)
        leak["policies"][0]["opponent_hand"] = "KdKs"
        leak["artifact_sha256"] = hashlib.sha256(
            oracle._canonical({k: v for k, v in leak.items() if k != "artifact_sha256"})
        ).hexdigest()
        with patch.object(oracle, "_build_game", return_value=self.game):
            with self.assertRaisesRegex(ValueError, "information-leaking"):
                oracle.verify_candidate(leak)

        boolean = deepcopy(self.candidate)
        boolean["policies"][0]["probabilities"][0] = True
        boolean["artifact_sha256"] = hashlib.sha256(
            oracle._canonical({k: v for k, v in boolean.items() if k != "artifact_sha256"})
        ).hexdigest()
        with patch.object(oracle, "_build_game", return_value=self.game):
            with self.assertRaisesRegex(ValueError, "rational string"):
                oracle.verify_candidate(boolean)

    def test_bounded_loader_rejects_duplicate_nonfinite_and_oversized_input(self):
        cases = (
            (b'{"a":1,"a":2}', "Duplicate JSON"),
            (b'{"a":NaN}', "Nonfinite JSON"),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.json"
            for raw, message in cases:
                with self.subTest(message=message):
                    path.write_bytes(raw)
                    with self.assertRaisesRegex(ValueError, message):
                        oracle.load_bounded(path)
            path.write_bytes(b" " * (oracle.MAX_CANDIDATE_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "byte limit"):
                oracle.load_bounded(path)

    def test_resigned_source_count_report_still_fails_pinned_authentication(self):
        original = oracle.FIVE_REPORT
        report = json.loads(original.read_text(encoding="utf-8"))
        report["independent_physical_count_rows"][0]["wins"] += 1
        unsigned = {key: value for key, value in report.items() if key != "artifact_sha256"}
        report["artifact_sha256"] = hashlib.sha256(oracle._canonical(unsigned)).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forged-five-report.json"
            path.write_text(json.dumps(report, allow_nan=False), encoding="utf-8")
            with patch.object(oracle, "FIVE_REPORT", path):
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    oracle._physical_source_classes()


if __name__ == "__main__":
    unittest.main()
