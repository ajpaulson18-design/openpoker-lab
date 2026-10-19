"""Tests for deterministic, lossless global suit transport."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

from scripts import turn_suit_transport as transport

FIXTURE = {
    "id": "turn-blocker-selected-sequence-equilibrium",
    "board": "2c7d9hJs",
    "oop": "AsAh:0.25,Th6h:0.75",
    "ip": "QhQs:1,AdAs:1",
    "runouts": ["8d", "Kd"],
    "config": {
        "bet_sizes": [0.5], "effective_stack": [100, 100],
        "include_all_in": False, "max_raises": 0, "pot": 100,
        "raise_sizes": [],
    },
}

RESULTS = ROOT / "benchmarks" / "results"
WITNESS_PATH = RESULTS / "turn-blocker-sequence-equilibrium-v1.json"
PROFILE_PATH = (RESULTS / "turn-blocker-cfrplus-policies-v1" /
                "turn-blocker-matrix-free-1000.json")


class SuitTransportTests(unittest.TestCase):
    def test_all_24_permutations_are_bijections_with_exact_inverses(self):
        self.assertEqual(len(transport.SUIT_PERMUTATIONS), 24)
        self.assertEqual(len(set(transport.SUIT_PERMUTATIONS)), 24)
        for target in transport.SUIT_PERMUTATIONS:
            mapping = transport.permutation_map(target)
            self.assertEqual(tuple(mapping), tuple("cdhs"))
            self.assertEqual(tuple(mapping.values()), tuple(target))
            self.assertEqual(transport.inverse_target(target),
                             "".join("cdhs"[target.index(s)] for s in "cdhs"))
            self.assertEqual(transport.map_card(transport.map_card("As", target),
                                                transport.inverse_target(target)), "As")

    def test_fixture_preserves_raw_range_order_weights_and_bytes_after_inverse(self):
        source = json.loads(json.dumps(FIXTURE))
        before = transport.canonical_json(source)
        for target in transport.SUIT_PERMUTATIONS:
            mapped = transport.transform_fixture(source, target)
            self.assertIsNot(mapped, source)
            self.assertEqual(mapped["oop"].split(",")[0].split(":")[1], "0.25")
            restored = transport.transform_fixture(mapped, transport.inverse_target(target))
            self.assertEqual(transport.canonical_json(restored), before)
        self.assertEqual(transport.canonical_json(source), before)

    def test_range_rejects_abstract_duplicate_and_invalid_weight_inputs(self):
        for bad in ("AKs", "AsAh,AhAs", "AsAh:nan", "AsAh:1.1", "AsAh, Th6h"):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                transport.map_explicit_range(bad, "cdhs")

    def test_invalid_permutations_and_cards_are_rejected(self):
        for bad in ("cdh", "cdds", "CDHS", "xxxx", "cdhsx"):
            with self.subTest(target=bad), self.assertRaises(ValueError):
                transport.permutation_map(bad)
        for bad in ("1s", "AsX", "AsAh", "river@As", "AS"):
            with self.subTest(card=bad), self.assertRaises((ValueError, TypeError)):
                transport.map_card(bad, "cdhs")

    def test_fixture_rejects_noncanonical_card_spelling(self):
        for bad in ("asAh:1", "AsAH:1"):
            with self.subTest(range=bad), self.assertRaises(ValueError):
                transport.map_explicit_range(bad, "cdhs")
        bad_fixture = dict(FIXTURE, board="2C7d9hJs")
        with self.assertRaises(ValueError):
            transport.transform_fixture(bad_fixture, "shdc")

    def test_branch_blocked_hand_remains_available_on_another_selected_river(self):
        from scripts import turn_river_validation as rules
        from pokerlab.cards import expand_range

        fixture = json.loads(json.dumps(FIXTURE))
        fixture["oop"] = "8dAs:1"
        fixture["ip"] = "QhQs:1"
        mapped = transport.transform_fixture(fixture, "shdc")
        restored = transport.transform_fixture(mapped, transport.inverse_target("shdc"))
        self.assertEqual(transport.canonical_json(restored), transport.canonical_json(fixture))

        def legal_worlds(candidate):
            board = rules.cards(candidate["board"])
            ranges = tuple(expand_range(candidate[side], board) for side in ("oop", "ip"))
            worlds, _selected = rules._worlds(board, ranges, candidate["runouts"])
            return worlds

        worlds = legal_worlds(fixture)
        mapped_worlds = legal_worlds(mapped)
        self.assertEqual(len(worlds), 1)
        self.assertEqual([world["river"] for world in worlds], ["Kd"])
        self.assertEqual(len(mapped_worlds), 1)
        self.assertEqual([world["river"] for world in mapped_worlds],
                         [transport.map_card("Kd", "shdc")])

    def test_saved_witness_fixture_and_full_rational_strategy_roundtrip(self):
        witness = json.loads(WITNESS_PATH.read_text(encoding="utf-8"))
        row = witness["results"][0]
        source_fixture = row["fixture"]
        source_rows = row["rational_strategy"]
        before_fixture = transport.canonical_json(source_fixture)
        before_rows = transport.canonical_json(source_rows)
        target = "shdc"
        mapped_fixture = transport.transform_fixture(source_fixture, target)
        mapped_rows = transport.transform_rows(source_rows, target)
        self.assertEqual(mapped_fixture["config"], source_fixture["config"])
        restored_fixture = transport.transform_fixture(mapped_fixture,
                                                       transport.inverse_target(target))
        restored_rows = transport.transform_rows(mapped_rows,
                                                 transport.inverse_target(target))
        self.assertEqual(transport.canonical_json(restored_fixture), before_fixture)
        self.assertEqual(transport.canonical_json(restored_rows), before_rows)
        self.assertEqual(transport.canonical_json(source_fixture), before_fixture)
        self.assertEqual(transport.canonical_json(source_rows), before_rows)

    def test_complete_saved_profile_roundtrips_all_supported_card_fields(self):
        profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        before = transport.canonical_json(profile)
        mapped = transport.transform_result(profile, "hscd")
        self.assertEqual(mapped["iterations"], profile["iterations"])
        self.assertEqual(mapped["config"], profile["config"])
        self.assertEqual(len(mapped["strategy"]), len(profile["strategy"]))
        self.assertEqual(mapped["strategy"][0]["actions"], profile["strategy"][0]["actions"])
        restored = transport.transform_result(mapped, transport.inverse_target("hscd"))
        self.assertEqual(transport.canonical_json(restored), before)
        self.assertEqual(transport.canonical_json(profile), before)

    def test_rows_remap_only_card_identities_and_river_markers(self):
        row = {
            "hand": "AhAs", "board": ["2c", "7d", "9h", "Js", "8d"],
            "history": ["bet@50", "call", "river@8d"], "player": "oop",
            "street": "river", "actions": [{"name": "bet", "amount": 50,
                         "raise_to": 100, "probability": 0.125,
                         "history_key": "bet@50"}],
        }
        mapped = transport.transform_rows([row], "shdc")[0]
        self.assertEqual(mapped["history"][:2], row["history"][:2])
        self.assertEqual(mapped["actions"], row["actions"])
        self.assertEqual(row["board"], ["2c", "7d", "9h", "Js", "8d"])
        self.assertNotEqual(mapped["board"], row["board"])
        malformed = dict(row, history=["river@not-a-card"])
        with self.assertRaises(ValueError):
            transport.transform_rows([malformed], "shdc")

    def test_unrecognized_card_bearing_profile_fields_and_keys_are_rejected(self):
        base = {"board": ["2c", "7d", "9h", "Js"], "strategy": [],
                "runouts": ["8d"]}
        with self.subTest(field="card array"):
            profile = dict(base, future_cards=["Kd"])
            with self.assertRaises(ValueError):
                transport.transform_result(profile, "shdc")
        with self.subTest(field="card dictionary key"):
            profile = dict(base, future_map={"Kd": 0.5})
            with self.assertRaises(ValueError):
                transport.transform_result(profile, "shdc")


if __name__ == "__main__":
    unittest.main()
