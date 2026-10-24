import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.preflop_validation import compare_result, replay_policy
from pokerlab import preflop_solver
from pokerlab.four_street_solver import solve_four_street
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions


_ROOT = Path(__file__).resolve().parents[1]
_BOUNDARY = json.loads(
    (_ROOT / "benchmarks/preflop-rounding-boundary-v1.json").read_text(
        encoding="utf-8"))
_WEIGHTED = {
    "sb": "AsAd:1,AhAc:0.25",
    "bb": "KsKd:1,KcKh:0.5",
    "config": {"starting_stack": [4, 3], "raise_sizes": [0.5],
                "max_raises": 1, "include_all_in": False},
    "runouts": ("2c3c4d7h8h", "Kc2d3h7s8c", "Ac2d3h7s8c"),
    "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                    "max_raises": 0, "include_all_in": False},
}


def _request_from_fixture(fixture, *, iterations=10, algorithm="vanilla",
                          traversal="recursive", diagnostics="recursive",
                          resource_model="world"):
    return FourStreetSolveRequest(
        fixture["sb"], fixture["bb"], tuple(fixture["runouts"]),
        preflop_config=PreflopConfig.from_dict(fixture["config"]),
        flop_actions=PostflopActions(**fixture["flop_config"]),
        turn_actions=(None if fixture.get("turn_config") is None else
                      PostflopActions(**fixture["turn_config"])),
        river_actions=(None if fixture.get("river_config") is None else
                       PostflopActions(**fixture["river_config"])),
        iterations=iterations,
        algorithm=algorithm,
        traversal=traversal,
        diagnostics=diagnostics,
        resource_model=resource_model,
    )


def _direct_options(request):
    return {
        "config": request.preflop_config,
        "runouts": request.runouts,
        "flop_config": request.flop_actions.to_dict(),
        "turn_config": (None if request.turn_actions is None else
                        request.turn_actions.to_dict()),
        "river_config": (None if request.river_actions is None else
                         request.river_actions.to_dict()),
        "postflop_scope": "all-streets",
        "iterations": request.iterations,
        "algorithm": request.algorithm,
        "traversal": request.traversal,
        "diagnostics": request.diagnostics,
        "resource_model": request.resource_model,
    }


class FourStreetSolverDelegationTests(unittest.TestCase):
    def test_exactly_one_call_with_only_approved_fields(self):
        request = FourStreetSolveRequest("AsAd", "KsKd", ("2c3c4d7h8h",))
        payload = {
            "solver_version": "preflop-strategy-v1",
            "strategy_schema": "preflop-strategy-v1",
            "runout_mode": "conditioned-ordered-selected-runouts",
            "strategy": [],
        }
        with patch.object(preflop_solver, "solve_preflop", return_value=payload) as engine:
            result = solve_four_street(request)
        engine.assert_called_once_with(
            request.sb_range,
            request.bb_range,
            request.preflop_config,
            runouts=request.runouts,
            flop_config={"bet_sizes": [0.5], "raise_sizes": [],
                         "max_raises": 0, "include_all_in": True},
            turn_config=None,
            river_config=None,
            postflop_scope="all-streets",
            iterations=1000,
            algorithm="vanilla",
            traversal="recursive",
            diagnostics="recursive",
            resource_model="world",
        )
        self.assertEqual(result.to_dict()["payload"], payload)

    def test_invalid_request_calls_no_engine_and_engine_errors_are_not_retried(self):
        with patch.object(preflop_solver, "solve_preflop") as engine:
            with self.assertRaises(TypeError):
                solve_four_street(object())
            engine.assert_not_called()

            request = FourStreetSolveRequest("AsAd", "KsKd", ("2c3c4d7h8h",))
            failure = RuntimeError("original engine failure")
            engine.side_effect = failure
            with self.assertRaises(RuntimeError) as raised:
                solve_four_street(request)
            self.assertIs(raised.exception, failure)
            engine.assert_called_once()


class FourStreetSolverIntegrationTests(unittest.TestCase):
    def assert_complete_payload_and_replay(self, fixture, request):
        direct = preflop_solver.solve_preflop(
            fixture["sb"], fixture["bb"], **_direct_options(request))
        wrapped = solve_four_street(request).to_dict()["payload"]
        self.assertEqual(wrapped, direct)
        oracle = replay_policy(
            wrapped, fixture["sb"], fixture["bb"], config=fixture["config"],
            runouts=fixture["runouts"], flop_config=fixture["flop_config"],
            turn_config=fixture.get("turn_config"),
            river_config=fixture.get("river_config"),
        )
        compare_result(wrapped, oracle)
        return wrapped

    def test_shared_prefix_inheritance_preserves_all_rows_and_history_tokens(self):
        fixture = {
            "sb": "AsAd",
            "bb": "KsKd",
            "config": {"starting_stack": 4, "max_raises": 0,
                        "raise_sizes": [], "include_all_in": False},
            "runouts": ("2c3c4d7h8h", "2c3c4d7hKc", "2c3c4dKc8h"),
            "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                            "max_raises": 0, "include_all_in": False},
            "turn_config": {"bet_sizes": [0.25], "raise_sizes": [],
                            "max_raises": 0, "include_all_in": False},
        }
        request = _request_from_fixture(fixture, iterations=10)
        payload = self.assert_complete_payload_and_replay(fixture, request)
        self.assertTrue(any(row["street"] == "flop" for row in payload["strategy"]))
        self.assertTrue(any(row["street"] == "turn" for row in payload["strategy"]))
        self.assertTrue(any(row["street"] == "river" for row in payload["strategy"]))
        self.assertEqual(payload["postflop_action_configs"]["turn"]["bet_sizes"], [0.25])
        self.assertEqual(payload["postflop_action_configs"]["river"]["bet_sizes"], [0.5])
        self.assertTrue(any("flop@2c3c4d" in row["history"] for row in payload["strategy"]))
        self.assertTrue(any("turn@" in token for row in payload["strategy"]
                            for token in row["history"]))

    def test_weighted_asymmetric_fixture_matches_complete_direct_result_and_replays(self):
        fixture = _WEIGHTED
        request = _request_from_fixture(fixture, iterations=10)
        payload = self.assert_complete_payload_and_replay(fixture, request)
        self.assertTrue(payload["private_pair_probabilities"])
        self.assertNotEqual(payload["private_pair_probabilities"][0]["probability"], 1.0)

    def test_fractional_rounding_boundary_matches_complete_result_and_replays(self):
        fixture = _BOUNDARY
        normalized = {
            **fixture,
            "config": fixture["config"],
            "runouts": tuple(fixture["runouts"]),
        }
        request = _request_from_fixture(normalized, iterations=10)
        payload = self.assert_complete_payload_and_replay(normalized, request)
        self.assertTrue(any(
            action["history_key"] == "raise@1.293095146"
            for row in payload["strategy"] for action in row["actions"]))

    def test_public_batched_public_vector_cfrplus_matches_complete_direct_result(self):
        fixture = {
            "sb": "AsAd", "bb": "KsKd",
            "config": {"starting_stack": 4, "max_raises": 0,
                        "raise_sizes": [], "include_all_in": False},
            "runouts": ("2c3c4d7h8h",),
            "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                            "max_raises": 0, "include_all_in": False},
        }
        request = _request_from_fixture(
            fixture, iterations=10, algorithm="cfrplus", traversal="public-batched",
            diagnostics="public-batched", resource_model="public-vector")
        self.assert_complete_payload_and_replay(fixture, request)

    def test_engine_rejects_disallowed_options_and_wrapper_cannot_request_sampling(self):
        request = FourStreetSolveRequest(
            "AsAd", "KsKd", ("2c3c4d7h8h",),
            algorithm="cfrplus", traversal="planned")
        with self.assertRaisesRegex(ValueError, r"CFR\+ supports recursive or public-batched"):
            solve_four_street(request)

        with self.assertRaises(ValueError):
            FourStreetSolveRequest(
                "AsAd", "KsKd", ("2c3c4d7h8h",), traversal="chance-sampled")

    def test_short_blind_all_in_result_is_valid_without_street_rows(self):
        fixture = {
            "sb": "AsAh", "bb": "KsKh",
            "config": {"small_blind": 0.5, "big_blind": 1,
                        "starting_stack": [0.5, 1], "max_raises": 0},
            "runouts": ("2c3d4h5s6c",),
            "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                            "max_raises": 0, "include_all_in": True},
        }
        request = _request_from_fixture(fixture, iterations=10)
        payload = self.assert_complete_payload_and_replay(fixture, request)
        self.assertEqual(payload["decisions"], 0)
        self.assertEqual(payload["strategy"], [])
        self.assertEqual(payload["worlds"], 1)

    def test_mutating_detached_envelope_does_not_change_later_serialization(self):
        fixture = {
            "sb": "AsAd", "bb": "KsKd",
            "config": {"starting_stack": 4, "max_raises": 0,
                        "raise_sizes": [], "include_all_in": False},
            "runouts": ("2c3c4d7h8h",),
            "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                            "max_raises": 0, "include_all_in": False},
        }
        request = _request_from_fixture(fixture, iterations=10)
        result = solve_four_street(request)
        before = result.to_json()
        detached = result.to_dict()
        detached["payload"]["strategy"].clear()
        detached["request"]["runouts"].clear()
        detached["identities"]["scope"] = "changed"
        self.assertEqual(result.to_json(), before)
        self.assertTrue(result.to_dict()["payload"]["strategy"])


if __name__ == "__main__":
    unittest.main()
