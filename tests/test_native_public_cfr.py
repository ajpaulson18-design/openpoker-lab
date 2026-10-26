"""Compiled public-CFR differential controls and four-street replay checks.

The native cases run only when OPENPOKER_NATIVE_PUBLIC_EXE points to an
explicitly built, manifest-matched executable. The test module remains
importable on machines without a C++ toolchain.
"""
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from pokerlab import native_public_cfr, public_cfr, preflop_solver
from pokerlab.four_street_solver import solve_four_street
from pokerlab.postflop_solver import _Chance
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions
from scripts.preflop_validation import compare_result, replay_policy
from tests.test_public_cfr import _fixture as _public_fixture
from pokerlab.river_tree import _Node, _Terminal


_EXE = os.environ.get("OPENPOKER_NATIVE_PUBLIC_EXE")
_COMPILED = bool(_EXE and Path(_EXE).is_file())
_ROOT = Path(__file__).resolve().parents[1]
_BOUNDARY = json.loads(
    (_ROOT / "benchmarks/preflop-rounding-boundary-v1.json").read_text(
        encoding="utf-8"))


def _actions(raw):
    return PostflopActions(
        bet_sizes=tuple(raw.get("bet_sizes", (0.5,))),
        raise_sizes=tuple(raw.get("raise_sizes", ())),
        max_raises=raw.get("max_raises", 0),
        include_all_in=raw.get("include_all_in", False),
    )


def _request(case, *, iterations=10):
    return FourStreetSolveRequest(
        case["sb"], case["bb"], tuple(case["runouts"]),
        preflop_config=PreflopConfig.from_dict(case["config"]),
        flop_actions=_actions(case["flop_config"]),
        turn_actions=(None if case.get("turn_config") is None else
                      _actions(case["turn_config"])),
        river_actions=(None if case.get("river_config") is None else
                       _actions(case["river_config"])),
        iterations=iterations,
        algorithm="cfrplus",
        traversal="public-batched",
        diagnostics="public-batched",
        resource_model="public-vector",
    )


def _replay(result, case):
    payload = result.to_dict()["payload"]
    oracle = replay_policy(
        payload, case["sb"], case["bb"], config=case["config"],
        runouts=case["runouts"], flop_config=case["flop_config"],
        turn_config=case.get("turn_config"),
        river_config=case.get("river_config"),
    )
    compare_result(payload, oracle)
    return payload


def _probability_delta(left, right):
    def rows(payload):
        return {
            (row["player"], row["hand"], tuple(row["history"])):
                {action["history_key"]: action["probability"] for action in row["actions"]}
            for row in payload["strategy"]
        }

    lhs, rhs = rows(left), rows(right)
    if lhs.keys() != rhs.keys():
        raise AssertionError("Native and Python emitted different information rows")
    maximum = 0.0
    for key in lhs:
        if lhs[key].keys() != rhs[key].keys():
            raise AssertionError(f"Native and Python action sets differ at {key!r}")
        for action in lhs[key]:
            maximum = max(maximum, abs(lhs[key][action] - rhs[key][action]))
    return maximum


def _minimal_game():
    root = _Node(("root",), 0, ("check", "bet"), (
        _Terminal("fold", (0.0, 0.0), winner=1),
        _Terminal("showdown", (0.0, 0.0)),
    ))
    worlds = [(0, 0, 1.0, 1)]
    infos = {(0, 0, ("root",)): 2}
    pot = 2.0
    return root, worlds, infos, pot


def _minimal_wire():
    root, worlds, infos, pot = _minimal_game()
    prepared = native_public_cfr._prepare(root, worlds, infos, 10, pot, _Chance)
    wire, _, _ = native_public_cfr._wire(prepared, infos, 10)
    return wire.decode("ascii").rstrip("\n")


def _chance_wire():
    decision = _Node(("after-reveal",), 0, ("check", "bet"), (
        _Terminal("fold", (0.0, 0.0), winner=1),
        _Terminal("showdown", (0.0, 0.0)),
    ))
    root = _Chance((), {"2c": decision}, 4, "river")
    worlds = [(0, 0, 1.0, 1, "2c")]
    infos = {(0, 0, ("after-reveal",)): 2}
    prepared = native_public_cfr._prepare(root, worlds, infos, 10, 2.0, _Chance)
    wire, _, _ = native_public_cfr._wire(prepared, infos, 10)
    return wire.decode("ascii").rstrip("\n")


def _deep_wire():
    decisions = 65
    nodes = [
        f"1 {index % 2} 0 {index} 1 {index} -1 0x0.0p+0"
        for index in range(decisions)
    ]
    nodes.append(f"0 -1 0 {decisions} 0 {decisions} 1 0x1.0p+0")
    children = [str(index + 1) for index in range(decisions)]
    rows = [f"1 {index}" for index in range(decisions)]
    maps = [str(index) for index in range(decisions)]
    return "\n".join((
        native_public_cfr.PROTOCOL,
        f"{decisions + 1} {decisions} 1 1 {decisions} {decisions} {decisions} 1 1 1 1 1 {decisions} {decisions} 0 {decisions} 0x1.0p+1",
        *nodes, *children, "0 1", "0 0 0x1.0p+0 0x1.0p+0",
        *rows, *maps, "",
    ))


class NativePublicCFRPureTests(unittest.TestCase):
    def test_protocol_identity_is_explicit(self):
        self.assertEqual(native_public_cfr.PROTOCOL, "OPENPOKER_PUBLIC_CFR_V1")
        self.assertEqual(native_public_cfr.WORK_MODEL, "native-public-cfr-work-v2")
        self.assertEqual(native_public_cfr.MAX_DEPTH, 64)

    def test_handcrafted_valid_protocol_wire_is_accepted(self):
        wire = _minimal_wire()
        self.assertEqual(wire.splitlines()[0], native_public_cfr.PROTOCOL)
        self.assertEqual(len(wire.splitlines()[1].split()), 17)

    def test_adapter_rejects_bad_worlds_infos_and_node_shapes_without_binary(self):
        _, worlds, root, infos, _, config, _ = _public_fixture()
        with self.assertRaises(ValueError):
            native_public_cfr._prepare(
                root, [("bad", 0, 1.0, 0)], infos, 10,
                config.pot, _Chance)
        with self.assertRaises(ValueError):
            native_public_cfr._prepare(
                root, worlds, {(0, 0, ()): True}, 10,
                config.pot, _Chance)
        with self.assertRaisesRegex(ValueError, "shape"):
            native_public_cfr._prepare(
                object(), worlds, {}, 10, config.pot, _Chance)

    def test_native_failure_propagates_without_python_fallback(self):
        options = {
            "runouts": ("2c3c4d7h8h",),
            "flop_config": {"bet_sizes": (0.5,), "raise_sizes": (),
                            "max_raises": 0, "include_all_in": False},
            "iterations": 10,
            "algorithm": "cfrplus",
            "traversal": "public-batched",
            "diagnostics": "public-batched",
            "resource_model": "public-vector",
            "native_executable": "explicit-native-path",
        }
        with patch.object(native_public_cfr, "executable_identity", return_value={}), \
                patch.object(native_public_cfr, "train_native_public",
                             side_effect=RuntimeError("native first failure")), \
                patch.object(preflop_solver, "train_public_batched") as python_trainer:
            with self.assertRaisesRegex(RuntimeError, "native first failure"):
                preflop_solver.solve_preflop(
                    "AsAd", "KsKd", PreflopConfig(max_raises=0), **options)
        python_trainer.assert_not_called()


@unittest.skipUnless(_COMPILED, "Set OPENPOKER_NATIVE_PUBLIC_EXE to a built native trainer")
class NativePublicCFRCompiledTests(unittest.TestCase):
    def test_handcrafted_valid_wire_returns_complete_normalized_policy(self):
        completed = subprocess.run(
            [str(Path(_EXE).resolve())],
            input=(_minimal_wire() + "\n").encode("ascii"),
            capture_output=True, timeout=10, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors="replace"))
        fields = completed.stdout.decode("ascii").split()
        self.assertEqual(fields[:2], [native_public_cfr.PROTOCOL, "2"])
        probabilities = [float.fromhex(value) for value in fields[2:]]
        self.assertEqual(len(probabilities), 2)
        self.assertAlmostEqual(sum(probabilities), 1.0, places=14)

    def test_weighted_chance_tree_matches_python_and_keeps_zero_reach_row(self):
        _, worlds, root, infos, _, config, _ = _public_fixture()
        zero_reach = (0, 0, ("unreached-control",))
        infos[zero_reach] = 3
        expected = public_cfr.train_public_batched(
            root, worlds, infos, 10, "cfrplus", pot=config.pot,
            chance_type=_Chance,
        )
        actual = native_public_cfr.train_native_public(
            root, worlds, infos, 10, pot=config.pot, chance_type=_Chance,
            executable=_EXE,
        )
        self.assertEqual(actual.keys(), expected.keys())
        for key in expected:
            self.assertEqual(len(actual[key]), len(expected[key]))
            for native, python in zip(actual[key], expected[key]):
                self.assertAlmostEqual(native, python, delta=1e-6, msg=repr(key))
        self.assertEqual(actual[zero_reach], [1 / 3] * 3)

    def test_native_four_street_weighted_blocker_shared_prefix(self):
        case = {
            "sb": "AsAd:0.5,QsQd:0.25",
            "bb": "KsKd:0.75,JhJd:0.25",
            "config": {"small_blind": 0.5, "big_blind": 1,
                       "starting_stack": [8, 7], "raise_sizes": [0.5],
                       "max_raises": 1, "include_all_in": False},
            "runouts": ["2c3c4d7h8h", "2c3c4d7hKc", "2c3c4dKc8h",
                        "2c3c4dQd8h", "5c6d7s8c9h", "5c6d7s8cJc"],
            "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                            "max_raises": 0, "include_all_in": False},
            "turn_config": {"bet_sizes": [0.5], "raise_sizes": [],
                            "max_raises": 0, "include_all_in": False},
            "river_config": {"bet_sizes": [0.5], "raise_sizes": [],
                             "max_raises": 0, "include_all_in": False},
        }
        request = _request(case)
        python = solve_four_street(request)
        native = solve_four_street(request, native_executable=_EXE)
        python_payload = _replay(python, case)
        native_payload = _replay(native, case)
        self.assertEqual(native_payload["worlds"], 22)
        self.assertEqual(native_payload["private_pair_probabilities"],
                         python_payload["private_pair_probabilities"])
        self.assertLessEqual(_probability_delta(python_payload, native_payload), 1e-6)
        self.assertEqual(native_payload["execution_backend"], "public-batched-cpp")
        self.assertEqual(native_payload["native_training"]["protocol"],
                         native_public_cfr.PROTOCOL)
        self.assertTrue(any(row["street"] == "river" for row in native_payload["strategy"]))

    def test_native_four_street_fractional_money_replay(self):
        case = {
            "sb": _BOUNDARY["sb"], "bb": _BOUNDARY["bb"],
            "config": _BOUNDARY["config"], "runouts": _BOUNDARY["runouts"],
            "flop_config": _BOUNDARY["flop_config"],
        }
        request = _request(case)
        payload = _replay(solve_four_street(request, native_executable=_EXE), case)
        self.assertTrue(any(
            action["history_key"] == "raise@1.293095146"
            for row in payload["strategy"] for action in row["actions"]))

    def test_native_four_street_board_ties_unequal_stacks_and_off_path_rows(self):
        case = {
            "sb": "2d3d:1,6d7d:0.5",
            "bb": "4d5d:1,8d9d:0.5",
            "config": {"small_blind": 0.5, "big_blind": 1,
                       "starting_stack": [5, 7], "raise_sizes": [0.5],
                       "max_raises": 1, "include_all_in": False},
            "runouts": ["AcKcQcJcTc", "AcKcQcJc9c"],
            "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                            "max_raises": 0, "include_all_in": False},
        }
        request = _request(case)
        payload = _replay(solve_four_street(request, native_executable=_EXE), case)
        self.assertGreater(payload["worlds"], 1)
        self.assertTrue(payload["strategy"])
        self.assertTrue(all(
            abs(sum(action["probability"] for action in row["actions"]) - 1) < 1e-9
            for row in payload["strategy"]))
        self.assertTrue(any(row["street"] == "river" for row in payload["strategy"]))

    def test_native_four_street_early_all_in_terminal_preserves_future_cards(self):
        case = {
            "sb": "AsAd", "bb": "KsKd",
            "config": {"small_blind": 0.5, "big_blind": 1,
                       "starting_stack": [1, 1], "raise_sizes": [],
                       "max_raises": 0, "include_all_in": False},
            "runouts": ["2c3d4h5s7c"],
            "flop_config": {"bet_sizes": [0.5], "raise_sizes": [],
                            "max_raises": 0, "include_all_in": True},
        }
        request = _request(case)
        python = solve_four_street(request)
        native = solve_four_street(request, native_executable=_EXE)
        python_payload = _replay(python, case)
        native_payload = _replay(native, case)
        self.assertEqual(native_payload["public_states"], 3)
        self.assertEqual(native_payload["worlds"], 1)
        self.assertEqual(len(native_payload["strategy"]), 1)
        self.assertEqual(_probability_delta(python_payload, native_payload), 0.0)
        self.assertEqual(native_payload["nash_conv"], 0.0)

    def test_rejects_truncated_native_wire_without_policy_output(self):
        completed = subprocess.run(
            [str(Path(_EXE).resolve())],
            input=(native_public_cfr.PROTOCOL + "\n").encode("ascii"),
            capture_output=True, timeout=10, check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, b"")

    def test_rejects_mutated_valid_wires_without_policy_output(self):
        original = _minimal_wire().splitlines()
        cases = {}
        out_of_range = list(original)
        out_of_range[5] = "999999"
        cases["out-of-range-child"] = out_of_range
        cycle = list(original)
        cycle[5] = "0"
        cases["cycle-to-root"] = cycle
        nonfinite = list(original)
        edge = nonfinite[8].split()
        edge[2] = "nan"
        nonfinite[8] = " ".join(edge)
        cases["nonfinite-mass"] = nonfinite
        cases["trailing-junk"] = original + ["unexpected"]

        header_limit = list(original)
        header = header_limit[1].split()
        header[0] = "250001"
        header_limit[1] = " ".join(header)
        cases["header-node-cap"] = header_limit
        iteration_limit = list(original)
        header = iteration_limit[1].split()
        header[9] = "100001"
        iteration_limit[1] = " ".join(header)
        cases["iteration-cap"] = iteration_limit
        cases["depth-cap"] = _deep_wire().splitlines()

        for name, lines in cases.items():
            with self.subTest(case=name):
                completed = subprocess.run(
                    [str(Path(_EXE).resolve())],
                    input=("\n".join(lines) + "\n").encode("ascii"),
                    capture_output=True, timeout=10, check=False,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertEqual(completed.stdout, b"")

    def test_rejects_terminal_visit_underreservation_and_repeated_edge_span(self):
        underreserved = _minimal_wire().splitlines()
        header = underreserved[1].split()
        header[11] = "1"
        underreserved[1] = " ".join(header)

        repeated_span = _chance_wire().splitlines()
        header = repeated_span[1].split()
        node_count, child_count, prefix_count = map(int, header[:3])
        span_start = 2 + node_count + child_count
        self.assertGreaterEqual(prefix_count, 2)
        second_span = repeated_span[span_start + 1].split()
        second_span[0] = "0"
        repeated_span[span_start + 1] = " ".join(second_span)

        for name, lines in (("terminal-underreservation", underreserved),
                            ("repeated-edge-span", repeated_span)):
            with self.subTest(case=name):
                completed = subprocess.run(
                    [str(Path(_EXE).resolve())],
                    input=("\n".join(lines) + "\n").encode("ascii"),
                    capture_output=True, timeout=10, check=False,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertEqual(completed.stdout, b"")

    def test_rejects_malformed_build_manifest_and_executable_hash_mismatch(self):
        manifest_path = (Path(_EXE).resolve().parent /
                         "native-public-manifest.json")
        original_read_text = Path.read_text

        def malformed_manifest(path, *args, **kwargs):
            if path == manifest_path:
                return json.dumps({"protocol": native_public_cfr.PROTOCOL})
            return original_read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", new=malformed_manifest):
            with self.assertRaisesRegex(ValueError, "manifest"):
                native_public_cfr.executable_identity(_EXE)
        with patch.object(native_public_cfr, "_sha", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "changed"):
                native_public_cfr.executable_identity(_EXE)


if __name__ == "__main__":
    unittest.main()
