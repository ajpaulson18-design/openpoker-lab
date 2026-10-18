"""Structural and frozen-reference tests for the bounded turn-blocker model."""
import hashlib
import json
import unittest
from fractions import Fraction
from unittest.mock import patch

from scripts import turn_blocker_sequence_equilibrium as producer
from scripts.turn_blocker_sequence_fixture import FIXTURE

ROOT = producer.ROOT
MODEL = ROOT / "benchmarks/results/turn-blocker-sequence-model-v1.json"
LEGACY = ROOT / "benchmarks/results/turn-blocker-sequence-legacy-preflight.json"
HIDDEN = ROOT / "benchmarks/results/turn-blocker-sequence-hidden-information-v1.json"


class TurnBlockerSequenceModelTests(unittest.TestCase):
    def test_model_matches_frozen_physical_reference(self):
        model = producer._build_model(FIXTURE)
        reference = json.loads(MODEL.read_text(encoding="utf-8"))[0]
        self.assertEqual(model["fixture"], FIXTURE)
        self.assertEqual(model["census"], {
            "nodes": 63, "depth_levels": 8, "decision": 28,
            "chance": 3, "terminal": 32,
        })
        self.assertEqual([len(model["infos"][p]) for p in (0, 1)], [28, 28])
        self.assertEqual([len(model["sequences"][p]) for p in (0, 1)], [57, 57])
        self.assertEqual([len(model["flows"][:29]), len(model["flows"][29:])], [29, 29])
        self.assertEqual(len(model["A_terms"]), 102)
        self.assertEqual([[str(v) for v in row] for row in model["A"]], reference["A"])
        for candidate_rows, reference_rows in (
            (model["flows"][:29], reference["E"]),
            (model["flows"][29:], reference["F"]),
        ):
            candidate = [[str(v) for v in row] for row in candidate_rows]
            self.assertEqual(candidate[0], reference_rows[0], "root flow row differs")
            candidate_infos = [tuple(row) for row in candidate[1:]]
            reference_infos = [tuple(row) for row in reference_rows[1:]]
            self.assertEqual(len(candidate_infos), len(set(candidate_infos)))
            self.assertEqual(len(reference_infos), len(set(reference_infos)))
            self.assertEqual(set(candidate_infos), set(reference_infos))
        for player in (0, 1):
            keys = [None if row["hand"] is None else
                    [row["hand"], row["history"], row["action_token"]]
                    for row in model["sequences"][player]]
            self.assertEqual(keys, reference["sequence_keys"][player])
        worlds = {(r["oop_hand"], r["ip_hand"], r["river"]):
                  (Fraction(r["mass"]), r["showdown_sign_oop"])
                  for r in producer._literal_world_rows(model)}
        self.assertEqual(worlds, producer.EXPECTED_WORLD_SIGNS)
        self.assertEqual(model["legacy_preflight"]["oop_guarantee"], {
            "rows": 86, "columns": 258,
            "tableau_cells_including_rhs_and_objective": 22533,
        })
        self.assertEqual(model["preflight"]["oop_guarantee"], {
            "rows": 85, "columns": 256,
            "tableau_cells_including_rhs_and_objective": 22102,
        })
        self.assertEqual(model["preflight"]["ip_ceiling"], model["preflight"]["oop_guarantee"])
        self.assertEqual(model["uniform_metrics"], reference["uniform_metrics"])
        self.assertEqual(model["uniform_metrics"], {
            "value": "4175/224", "lower": "-200/7",
            "upper": "400/7", "nash_conv": "600/7",
        })
        self.assertEqual(reference["check_call_ip_reference"], {
            "legal_oop_br": "300/7", "illegal_future_peek": "450/7",
            "illicit_gain": "150/7",
        })

    def test_frozen_inputs_and_hashes_are_pinned(self):
        expected = {
            MODEL: "4ac32d6eb0103695d9137982a5c82f52e1a5c595491940b33e8993b96776d832",
            LEGACY: "87600bb1e7a8c99675203e2ddbc3352adc2bbace48d30a0db94977160533e909",
            HIDDEN: "80b0d161b9943e4fbcd0e5c609febdcefafc15d2665d895bd01400da264ab5b3",
        }
        for path, digest in expected.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
        sources = producer._source_fingerprints()
        self.assertEqual(sources["benchmarks/results/turn-blocker-sequence-model-v1.json"], producer.REFERENCE_SHA256)
        self.assertEqual(sources["benchmarks/results/turn-blocker-sequence-legacy-preflight.json"], producer.LEGACY_REFERENCE_SHA256)
        self.assertEqual(sources["benchmarks/results/turn-blocker-sequence-hidden-information-v1.json"], producer.HIDDEN_REFERENCE_SHA256)

    def test_source_and_head_drift_abort_publication(self):
        with patch.object(producer, "_head", return_value="a" * 40):
            with self.assertRaisesRegex(ValueError, "HEAD changed"):
                producer._assert_unchanged("b" * 40, {})
        with patch.object(producer, "_head", return_value="a" * 40), \
             patch.object(producer, "_source_fingerprints", return_value={"changed": "digest"}):
            with self.assertRaisesRegex(ValueError, "source changed"):
                producer._assert_unchanged("a" * 40, {"pinned": "digest"})


if __name__ == "__main__":
    unittest.main()
