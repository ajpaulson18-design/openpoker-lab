import json
import math
import unittest
from dataclasses import FrozenInstanceError

from pokerlab.preflop_tree import PreflopConfig
from pokerlab.solver_contracts import (
    FourStreetSolveRequest,
    FourStreetSolveResult,
    PostflopActions,
)


def valid_payload(**overrides):
    payload = {
        "solver_version": "preflop-strategy-v1",
        "strategy_schema": "preflop-strategy-v1",
        "runout_mode": "conditioned-ordered-selected-runouts",
        "strategy": [],
        "value_sb": 0.125,
    }
    payload.update(overrides)
    return payload


class PostflopActionsTests(unittest.TestCase):
    def test_action_iterables_are_normalized_and_copied(self):
        bets = [0.75, 0.25, 0.75]
        raises = (size for size in (0.5, 0.25))
        actions = PostflopActions(bet_sizes=bets, raise_sizes=raises)
        bets.append(0.1)
        self.assertEqual(actions.bet_sizes, (0.25, 0.75))
        self.assertEqual(actions.raise_sizes, (0.25, 0.5))

    def test_defaults_and_serialization_are_exact_and_detached(self):
        actions = PostflopActions()
        self.assertEqual(actions.bet_sizes, (0.5,))
        self.assertEqual(actions.raise_sizes, ())
        self.assertEqual(actions.max_raises, 0)
        self.assertIs(actions.include_all_in, True)
        serialized = actions.to_dict()
        self.assertEqual(serialized, {
            "bet_sizes": [0.5], "raise_sizes": [], "max_raises": 0,
            "include_all_in": True,
        })
        serialized["bet_sizes"].append(9)
        self.assertEqual(actions.bet_sizes, (0.5,))
        with self.assertRaises(FrozenInstanceError):
            actions.max_raises = 2


class FourStreetSolveRequestTests(unittest.TestCase):
    def test_defaults_and_none_inherit_whole_flop_action_spec(self):
        request = FourStreetSolveRequest("AsAd", "KsKd", ("invalid-but-unparsed",))
        self.assertIsInstance(request.preflop_config, PreflopConfig)
        self.assertEqual(request.flop_actions, PostflopActions())
        self.assertIsNone(request.turn_actions)
        self.assertIsNone(request.river_actions)
        self.assertEqual(request.iterations, 1000)
        self.assertEqual(request.algorithm, "vanilla")
        self.assertEqual(request.traversal, "recursive")
        self.assertEqual(request.diagnostics, "recursive")
        self.assertEqual(request.resource_model, "world")

        receipt = request.to_dict()
        self.assertEqual(set(receipt), {
            "schema_version", "sb_range", "bb_range", "runouts",
            "preflop_config", "flop_actions", "turn_actions", "river_actions",
            "iterations", "algorithm", "traversal", "diagnostics",
            "resource_model",
        })
        self.assertEqual(receipt["schema_version"], "four-street-request-v1")
        self.assertIsNone(receipt["turn_actions"])
        self.assertIsNone(receipt["river_actions"])
        self.assertEqual(receipt["runouts"], ["invalid-but-unparsed"])

    def test_later_stage_is_a_complete_override_and_receipts_are_detached(self):
        request = FourStreetSolveRequest(
            "AsAd", "KsKd", ("2c3c4d7h8h",),
            flop_actions=PostflopActions(bet_sizes=(0.5, 1.0), max_raises=1),
            turn_actions=PostflopActions(bet_sizes=(0.25,), include_all_in=False),
        )
        self.assertEqual(request.to_dict()["flop_actions"]["bet_sizes"], [0.5, 1.0])
        self.assertEqual(request.to_dict()["turn_actions"], {
            "bet_sizes": [0.25], "raise_sizes": [], "max_raises": 0,
            "include_all_in": False,
        })
        receipt = request.to_dict()
        receipt["runouts"].append("extra")
        receipt["preflop_config"]["raise_sizes"].clear()
        self.assertEqual(request.runouts, ("2c3c4d7h8h",))
        self.assertEqual(request.preflop_config.raise_sizes, (1.0,))

    def test_rejects_wrong_types_blank_values_and_unbounded_runout_containers(self):
        good = {"sb_range": "AsAd", "bb_range": "KsKd", "runouts": ("2c3c4d7h8h",)}
        for field_name, value in (
            ("sb_range", None), ("bb_range", 4), ("runouts", "2c3c4d7h8h"),
            ("runouts", ["2c3c4d7h8h"]), ("runouts", ([],)),
            ("preflop_config", {}), ("flop_actions", {}),
            ("turn_actions", {}), ("river_actions", ()), ("iterations", True),
            ("algorithm", 1), ("traversal", None), ("diagnostics", False),
            ("resource_model", 0),
        ):
            with self.subTest(field=field_name, value=value):
                args = dict(good)
                args[field_name] = value
                with self.assertRaises(TypeError):
                    FourStreetSolveRequest(**args)

        for field_name, value in (
            ("sb_range", "  "), ("bb_range", ""), ("runouts", ()),
            ("runouts", ("  ",)), ("algorithm", "chance-sampled"),
            ("traversal", "chance-sampled"), ("resource_model", "chance-sampled"),
        ):
            with self.subTest(field=field_name, value=value):
                args = dict(good)
                args[field_name] = value
                with self.assertRaises(ValueError):
                    FourStreetSolveRequest(**args)

    def test_runout_cap_is_checked_without_parsing_or_iteration(self):
        too_many = ("x",) * 300_001
        with self.assertRaises(ValueError):
            FourStreetSolveRequest("A", "B", too_many)


class FourStreetSolveResultTests(unittest.TestCase):
    def setUp(self):
        self.request = FourStreetSolveRequest("AsAd", "KsKd", ("2c3c4d7h8h",))

    def test_complete_payload_and_deterministic_finite_envelope_json(self):
        payload = valid_payload(extra={"nested": [1, {"retained": 0.1}]})
        result = FourStreetSolveResult._from_payload(self.request, payload)
        envelope = result.to_dict()
        self.assertEqual(envelope["schema_version"], "four-street-solve-v1")
        self.assertEqual(envelope["request"], self.request.to_dict())
        self.assertEqual(envelope["identities"], {
            "seats": "sb-button-0-bb-1",
            "scope": "all-streets",
            "numerical_model": "binary64-local-nine-decimal-whole-hand-v1",
            "chance_model": "conditioned-ordered-selected-runouts",
            "range_model": "physical-combo-product-blocker-conditioned-v1",
            "reach_model": "global-joint-law-separated-sequence-reach-v1",
        })
        self.assertEqual(envelope["source_identity"], {
            "entry_point": "pokerlab.preflop_solver.solve_preflop",
            "solver_version": "preflop-strategy-v1",
            "source_revision": None,
            "source_verification": "not-recorded",
        })
        self.assertEqual(envelope["payload"], payload)
        self.assertEqual(result.to_json(), result.to_json())
        self.assertEqual(json.loads(result.to_json()), envelope)
        self.assertNotIn("source_revision", envelope["payload"])

    def test_detached_payload_and_envelope_mutations_do_not_change_result(self):
        original_payload = valid_payload(extra={"nested": [1, {"x": 2}]})
        result = FourStreetSolveResult._from_payload(self.request, original_payload)
        original_json = result.to_json()
        original_payload["extra"]["nested"][1]["x"] = 88
        self.assertEqual(result.to_json(), original_json)
        detached = result.to_dict()
        detached["payload"]["extra"]["nested"][1]["x"] = 99
        detached["request"]["runouts"].clear()
        detached["identities"]["scope"] = "other"
        self.assertEqual(result.to_json(), original_json)
        with self.assertRaises(TypeError):
            FourStreetSolveResult(self.request, valid_payload())
        with self.assertRaises(FrozenInstanceError):
            result.request = self.request

    def test_factory_rejects_wrong_scope_schema_and_nonfinite_json(self):
        bad_payloads = (
            (valid_payload(solver_version="old"), ValueError),
            (valid_payload(strategy_schema="old"), ValueError),
            (valid_payload(runout_mode="unconditioned"), ValueError),
            (valid_payload(extra=math.nan), ValueError),
            (valid_payload(extra=object()), ValueError),
        )
        for payload, error in bad_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(error):
                    FourStreetSolveResult._from_payload(self.request, payload)
        with self.assertRaises(TypeError):
            FourStreetSolveResult._from_payload(self.request, [])
        with self.assertRaises(TypeError):
            FourStreetSolveResult._from_payload({}, valid_payload())

    def test_empty_strategy_zero_decision_result_is_valid(self):
        result = FourStreetSolveResult._from_payload(
            self.request, valid_payload(strategy=[], decision_count=0))
        self.assertEqual(result.to_dict()["payload"]["strategy"], [])


if __name__ == "__main__":
    unittest.main()
