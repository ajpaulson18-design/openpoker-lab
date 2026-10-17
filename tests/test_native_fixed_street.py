import json
import math
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from pokerlab import cfr, cfr_plus
from pokerlab.native_fixed_street import train_native_fixed_street
from pokerlab.river_tree import _Action, _Node, _Terminal


BUILD_DIRECTORY = os.environ.get("OPENPOKER_NATIVE_TRAIN_BUILD_DIR")
NATIVE_AVAILABLE = bool(BUILD_DIRECTORY and Path(BUILD_DIRECTORY).is_dir())


def _trees():
    """Return tiny affine fixed-tree fixtures and their normalized hidden worlds."""
    root_action = _Action("check")
    lead = _Action("bet", 1.0, 1.0)
    respond = _Node(
        history=(lead.token,), player=1,
        actions=(_Action("fold"), _Action("call", 1.0, 1.0)),
        children=(_Terminal("fold", (1.0, 0.0), winner=0),
                  _Terminal("showdown", (1.0, 1.0))),
    )
    weighted = _Node(
        history=(), player=0, actions=(root_action, lead),
        children=(_Terminal("showdown", (0.0, 0.0)), respond),
    )
    weighted_worlds = ((3, 20, 0.25, 0.375), (7, 41, 0.75, -0.625))
    weighted_infos = {
        (0, 3, ()): 2, (0, 7, ()): 2,
        (1, 20, (lead.token,)): 2, (1, 41, (lead.token,)): 2,
    }

    jam = _Action("all_in", 1.5, 1.5)
    short_response = _Node(
        history=(jam.token,), player=1,
        actions=(_Action("fold"), _Action("call", 1.0, 1.0)),
        children=(_Terminal("fold", (1.5, 0.0), winner=0),
                  _Terminal("showdown", (1.5, 1.0))),
    )
    refund = _Node(
        history=(), player=0, actions=(_Action("check"), jam),
        children=(_Terminal("showdown", (0.0, 0.0)), short_response),
    )
    refund_worlds = ((13, 71, 1.0, 1.0),)
    refund_infos = {(0, 13, ()): 2, (1, 71, (jam.token,)): 2}
    return ((weighted, weighted_worlds, weighted_infos, 6.0),
            (refund, refund_worlds, refund_infos, 6.0))


def _payoff(pot):
    def value(node, world):
        return (1 if node.winner == 0 else -1) * (pot / 2 + min(node.contributions)) \
            if node.kind == "fold" else world[3] * (pot / 2 + min(node.contributions))
    return value


def _python_train(root, worlds, infos, iterations, algorithm, pot):
    node_key = lambda node, world: (node.player, world[node.player], node.history)
    terminal_value = _payoff(pot)
    if algorithm == "cfrplus":
        averages = cfr_plus.train(root, worlds, infos, iterations, "cfrplus",
                                  terminal_value=terminal_value, node_key=node_key)
    else:
        averages = cfr.train(root, worlds, infos, iterations, algorithm,
                             terminal_value=terminal_value, node_key=node_key)
    value = cfr.evaluate(root, worlds, averages, terminal_value, node_key)
    br0 = cfr.best_response(0, root, worlds, averages, terminal_value, node_key)
    br1 = cfr.best_response(1, root, worlds, averages, terminal_value, node_key)
    return averages, (value, br0, br1)


def _independent_metrics(root, worlds, policy, pot):
    """Direct small-tree value and information-set response calculation."""
    def payoff(node, world):
        matched = pot / 2 + min(node.contributions)
        if node.kind == "fold":
            return matched if node.winner == 0 else -matched
        return matched * world[3]

    def profile(node, world):
        if type(node) is _Terminal:
            return payoff(node, world)
        probabilities = policy[(node.player, world[node.player], node.history)]
        return sum(probability * profile(child, world)
                   for probability, child in zip(probabilities, node.children))

    value = sum(world[2] * profile(root, world) for world in worlds)

    def response(player):
        total = 0.0
        for hand in sorted({world[player] for world in worlds}):
            grouped = [world for world in worlds if world[player] == hand]

            def visit(node, weighted_worlds):
                if not weighted_worlds:
                    return 0.0
                if type(node) is _Terminal:
                    sign = 1.0 if player == 0 else -1.0
                    return sum(world[2] * sign * payoff(node, world)
                               for world in weighted_worlds)
                if node.player == player:
                    return max(visit(child, weighted_worlds) for child in node.children)
                result = 0.0
                for index, child in enumerate(node.children):
                    branched = []
                    for world in weighted_worlds:
                        probability = policy[(node.player, world[node.player], node.history)][index]
                        if probability:
                            branched.append((world[0], world[1], world[2] * probability, world[3]))
                    result += visit(child, branched)
                return result

            total += visit(root, grouped)
        return total

    return value, response(0), response(1)


class NativeFixedStreetAdapterTests(unittest.TestCase):
    def test_invalid_shapes_and_admission_fail_before_build_lookup(self):
        root, worlds, infos, pot = _trees()[0]
        hidden_key_infos = dict(infos)
        hidden_key_infos.pop((0, 3, ()))
        hidden_key_infos[(0, 3, ("turn@As",))] = 2
        bad_cases = [
            (root, worlds, hidden_key_infos, pot),
            (root, ((3, 20, 0.25, 0.375, "public"), (7, 41, 0.75, -0.625, "public")), infos, pot),
            (root, ((True, 20, 1.0, 0.0),), {(0, True, ()): 2, (1, 20, ("bet@1",)): 2}, pot),
            (root, ((3, 20, 0.5, 1.01), (7, 41, 0.5, -0.625)), infos, pot),
            (root, ((3, 20, 0.2, 0.375), (7, 41, 0.75, -0.625)), infos, pot),
            (root, worlds, infos, float("nan")),
        ]
        with patch("pokerlab.native_fixed_street._backend", side_effect=AssertionError("build lookup ran before validation")):
            for tree, invalid_worlds, invalid_infos, invalid_pot in bad_cases:
                with self.subTest(worlds=invalid_worlds, pot=invalid_pot):
                    with self.assertRaises((ValueError, TypeError)):
                        train_native_fixed_street(tree, invalid_worlds, invalid_infos, 10,
                                                  "vanilla", pot=invalid_pot, build_directory=None)
            with self.assertRaises(ValueError):
                train_native_fixed_street(root, worlds, infos, 10, "invalid",
                                          pot=pot, build_directory=None)
            with self.assertRaises(ValueError):
                train_native_fixed_street(root, worlds, infos, True, "vanilla",
                                          pot=pot, build_directory=None)

    def test_chance_like_nodes_are_rejected_before_backend(self):
        class Chance:
            pass
        worlds = ((3, 20, 1.0, 0.25),)
        root = Chance()
        infos = {}
        with patch("pokerlab.native_fixed_street._backend", side_effect=AssertionError("backend lookup ran")):
            with self.assertRaisesRegex(ValueError, "chance|tree|arborescence"):
                train_native_fixed_street(root, worlds, infos, 10, "vanilla",
                                          pot=6.0, build_directory=None)

    def test_missing_explicit_build_directory_never_compiles_implicitly(self):
        root, worlds, infos, pot = _trees()[0]
        with patch("pokerlab.native_fixed_street.subprocess.run",
                   side_effect=AssertionError("native process must not compile itself")) as run:
            with self.assertRaisesRegex(ValueError, "explicit native training build directory"):
                train_native_fixed_street(root, worlds, infos, 10, "vanilla",
                                          pot=pot, build_directory=None)
        run.assert_not_called()

    def test_zero_mean_single_terminal_skips_native_process_after_admission(self):
        worlds = ((0, 1, 1.0, 0.0),)
        root = _Terminal("showdown", (0.0, 0.0))
        with patch("pokerlab.native_fixed_street._backend", side_effect=AssertionError("zero-info game launched native")):
            policy, metadata = train_native_fixed_street(
                root, worlds, {}, 10, "cfrplus", pot=6.0, build_directory=None)
        self.assertEqual(policy, {})
        self.assertEqual(metadata["backend"], "native-fixed-street-v1")
        self.assertEqual(metadata["execution_skipped"], "no-information-sets")
        self.assertEqual(metadata["native_world_rows"], 1)
        self.assertEqual(metadata["admission"]["requested_iterations"], 10)

    @unittest.skipUnless(NATIVE_AVAILABLE, "Set OPENPOKER_NATIVE_TRAIN_BUILD_DIR to an explicit source-built trainer")
    def test_all_algorithms_and_checkpoints_match_python_on_weighted_and_refund_trees(self):
        for root, worlds, infos, pot in _trees():
            for algorithm in ("vanilla", "dcfr", "cfrplus"):
                for iterations in (10, 100, 1000):
                    with self.subTest(algorithm=algorithm, iterations=iterations,
                                      worlds=len(worlds), states="refund" if worlds[0][3] == 1.0 else "weighted"):
                        expected_policy, expected_metrics = _python_train(
                            root, worlds, infos, iterations, algorithm, pot)
                        self.assertEqual(set(expected_policy), set(infos))
                        direct_metrics = _independent_metrics(root, worlds, expected_policy, pot)
                        for got, want in zip(expected_metrics, direct_metrics):
                            self.assertAlmostEqual(got, want, delta=1e-12)
                        actual_policy, metadata = train_native_fixed_street(
                            root, worlds, infos, iterations, algorithm,
                            pot=pot, build_directory=BUILD_DIRECTORY)
                        self.assertEqual(set(actual_policy), set(infos))
                        for key in infos:
                            self.assertEqual(len(actual_policy[key]), infos[key])
                            self.assertTrue(all(math.isfinite(p) and 0 <= p <= 1 for p in actual_policy[key]))
                            self.assertAlmostEqual(sum(actual_policy[key]), 1.0, delta=1e-9)
                            for got, want in zip(actual_policy[key], expected_policy[key]):
                                self.assertAlmostEqual(got, want, delta=1e-8)
                        for got, want in zip(expected_metrics, direct_metrics):
                            self.assertAlmostEqual(got, want, delta=1e-8)
                        self.assertEqual(metadata["backend"], "native-fixed-street-v1")
                        self.assertEqual(metadata["native_world_rows"], len(worlds))
                        self.assertEqual(metadata["admission"]["requested_iterations"], iterations)
                        self.assertEqual(metadata["admission"]["algorithm"], algorithm)
                        self.assertTrue(metadata["build"]["source_lf_sha256"])
                        self.assertTrue(metadata["input_sha256"])
                        self.assertTrue(metadata["output_sha256"])


class PreparedSolverNativeIntegrationTests(unittest.TestCase):
    def test_default_and_explicit_python_backend_payloads_match_exactly(self):
        from pokerlab.preflop_checkdown_solver import solve_prepared_preflop_checkdown
        from tests.test_preflop_checkdown_solver import SB_RANGE, BB_RANGE, prepared_table
        table, _ = prepared_table()
        config = {"small_blind": 0.5, "big_blind": 1.0, "starting_stack": [2.0, 2.0],
                  "raise_sizes": [], "max_raises": 1, "include_all_in": True}
        omitted = solve_prepared_preflop_checkdown(
            table, config=config, iterations=10, algorithm="cfrplus", world_indexing="pair-mean")
        explicit = solve_prepared_preflop_checkdown(
            table, config=config, iterations=10, algorithm="cfrplus", world_indexing="pair-mean",
            training_backend="python")
        self.assertEqual(omitted, explicit)
        with self.assertRaises(ValueError):
            solve_prepared_preflop_checkdown(table, config=config, iterations=10,
                                             training_backend="unknown")

    def test_flop_default_and_explicit_python_payloads_match_exactly(self):
        from fractions import Fraction
        from pokerlab.flop_checkdown_equity import FlopCheckdownEquities
        from pokerlab.flop_checkdown_solver import solve_prepared_flop_checkdown
        from pokerlab.flop_checkdown_worlds import prepare_flop_worlds
        plan = prepare_flop_worlds("2c3c4d", "AsAd", "KsKd")
        table = FlopCheckdownEquities(
            board=tuple(plan.board), hands=tuple(tuple(tuple(h) for h in player) for player in plan.hands),
            pairs=((plan.pairs[0][0], plan.pairs[0][1], Fraction(1)),),
            counts=((1782, 48, 150),), _budget_items=tuple(plan.budget.items()))
        config = {"pot": 2, "effective_stack": 1, "bet_sizes": [0.5],
                  "raise_sizes": [], "max_raises": 0, "include_all_in": True}
        omitted = solve_prepared_flop_checkdown(table, config=config, iterations=10)
        explicit = solve_prepared_flop_checkdown(table, config=config, iterations=10,
                                                 training_backend="python")
        self.assertEqual(omitted, explicit)
        with self.assertRaises(ValueError):
            solve_prepared_flop_checkdown(table, config=config, iterations=10,
                                          training_backend="unknown")

    def test_native_admission_precedes_executable_lookup(self):
        from fractions import Fraction
        from pokerlab import native_fixed_street
        from pokerlab import preflop_checkdown_solver as preflop_solver
        from pokerlab import flop_checkdown_solver as flop_solver
        from pokerlab.flop_checkdown_equity import FlopCheckdownEquities
        from pokerlab.flop_checkdown_worlds import prepare_flop_worlds
        from tests.test_preflop_checkdown_solver import prepared_table
        table, _ = prepared_table()
        pre_config = {"small_blind": 0.5, "big_blind": 1.0, "starting_stack": [2.0, 2.0],
                      "raise_sizes": [], "max_raises": 1, "include_all_in": True}
        with patch.object(native_fixed_street, "admit_native_shape",
                          side_effect=ValueError("test native admission")), \
             patch.object(native_fixed_street, "_backend",
                          side_effect=AssertionError("backend lookup preceded admission")):
            with self.assertRaisesRegex(ValueError, "test native admission"):
                preflop_solver.solve_prepared_preflop_checkdown(
                    table, config=pre_config, iterations=10, algorithm="cfrplus",
                    world_indexing="pair-mean", training_backend="native", build_directory=Path.cwd())

        plan = prepare_flop_worlds("2c3c4d", "AsAd", "KsKd")
        flop_table = FlopCheckdownEquities(
            board=tuple(plan.board), hands=tuple(tuple(tuple(h) for h in player) for player in plan.hands),
            pairs=((plan.pairs[0][0], plan.pairs[0][1], Fraction(1)),),
            counts=((1782, 48, 150),), _budget_items=tuple(plan.budget.items()))
        flop_config = {"pot": 2, "effective_stack": 1, "bet_sizes": [0.5],
                       "raise_sizes": [], "max_raises": 0, "include_all_in": True}
        with patch.object(native_fixed_street, "admit_native_shape",
                          side_effect=ValueError("test native admission")), \
             patch.object(native_fixed_street, "_backend",
                          side_effect=AssertionError("backend lookup preceded admission")):
            with self.assertRaisesRegex(ValueError, "test native admission"):
                flop_solver.solve_prepared_flop_checkdown(
                    flop_table, config=flop_config, iterations=10, algorithm="cfrplus",
                    training_backend="native", build_directory=Path.cwd())

    @unittest.skipUnless(NATIVE_AVAILABLE, "Set OPENPOKER_NATIVE_TRAIN_BUILD_DIR to an explicit source-built trainer")
    def test_prepared_native_solvers_match_python_and_independent_count_replay(self):
        from fractions import Fraction
        from pokerlab.flop_checkdown_equity import FlopCheckdownEquities
        from pokerlab.flop_checkdown_solver import solve_prepared_flop_checkdown
        from pokerlab.flop_checkdown_worlds import prepare_flop_worlds
        from pokerlab.preflop_checkdown_solver import solve_prepared_preflop_checkdown
        from scripts.flop_checkdown_validation import prepare_oracle_from_counts, replay as replay_flop
        from scripts.preflop_checkdown_validation import replay as replay_preflop
        from tests.test_preflop_checkdown_solver import SB_RANGE, BB_RANGE, prepared_table

        pre_table, pre_counts = prepared_table()
        pre_config = {"small_blind": 0.5, "big_blind": 1.0, "starting_stack": [2.0, 2.0],
                      "raise_sizes": [], "max_raises": 1, "include_all_in": True}
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(game="weighted-preflop", algorithm=algorithm):
                py = solve_prepared_preflop_checkdown(
                    pre_table, config=pre_config, iterations=20, algorithm=algorithm,
                    world_indexing="pair-mean")
                native = solve_prepared_preflop_checkdown(
                    pre_table, config=pre_config, iterations=20, algorithm=algorithm,
                    world_indexing="pair-mean", training_backend="native",
                    build_directory=BUILD_DIRECTORY)
                self.assertEqual(native["training_backend"], "native")
                self.assertEqual(native["native_training"]["backend"], "native-fixed-street-v1")
                self.assertEqual(native["world_indexing"], "pair-mean")
                self.assertEqual(native["training_world_rows"], len(pre_table.pairs))
                self.assertEqual(native["physical_boards"], py["physical_boards"])
                for field in ("value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value",
                              "sb_best_response_gain", "bb_best_response_gain", "nash_conv", "exploitability"):
                    self.assertAlmostEqual(native[field], py[field], delta=1e-8, msg=field)
                self._assert_policy_close(native["strategy"], py["strategy"])
                # The shared QQ private hand must have one row per public history even though
                # it faces distinct hidden AK and KK opponent hands.
                qq_rows = [row for row in native["strategy"] if row["player"] == "sb" and row["hand"] == "QdQs"]
                self.assertTrue(qq_rows)
                self.assertEqual(len({tuple(row["history"]) for row in qq_rows}), len(qq_rows))
                self.assertTrue(all(set(row) == {"player", "hand", "street", "revealed_board", "history", "actions"}
                                    for row in qq_rows))
                replay = replay_preflop(native, SB_RANGE, BB_RANGE, pre_config, pre_counts, tolerance=1e-10)
                self.assertTrue(replay["exact_fraction_replay"])
                self.assertLessEqual(max(replay["scalar_absolute_gaps"].values()), 1e-10)

        plan = prepare_flop_worlds("2c3c4d", "AsAd", "KsKd")
        flop_table = FlopCheckdownEquities(
            board=tuple(plan.board), hands=tuple(tuple(tuple(h) for h in player) for player in plan.hands),
            pairs=((plan.pairs[0][0], plan.pairs[0][1], Fraction(1)),),
            counts=((1782, 48, 150),), _budget_items=tuple(plan.budget.items()))
        flop_config = {"pot": 2, "effective_stack": 1, "bet_sizes": [0.5],
                       "raise_sizes": [], "max_raises": 0, "include_all_in": True}
        count_row = [{"oop_hand": "AdAs", "ip_hand": "KdKs", "wins": 1782,
                      "ties": 48, "losses": 150, "ordered_outcomes": 1980}]
        flop_oracle = prepare_oracle_from_counts("2c3c4d", "AsAd", "KsKd", flop_config, count_row)
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(game="one-pair-flop-checkdown", algorithm=algorithm):
                py = solve_prepared_flop_checkdown(
                    flop_table, config=flop_config, iterations=20, algorithm=algorithm)
                native = solve_prepared_flop_checkdown(
                    flop_table, config=flop_config, iterations=20, algorithm=algorithm,
                    training_backend="native", build_directory=BUILD_DIRECTORY)
                self.assertEqual(native["execution_backend"], "native-fixed-street-v1")
                self.assertEqual(native["native_training"]["backend"], "native-fixed-street-v1")
                self.assertEqual(native["training_world_rows"], py["training_world_rows"])
                self.assertEqual(native["physical_worlds"], 1980)
                for field in ("value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value",
                              "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability"):
                    self.assertAlmostEqual(native[field], py[field], delta=1e-8, msg=field)
                self._assert_policy_close(native["strategy"], py["strategy"])
                replay = replay_flop(native, flop_oracle, tolerance=1e-10)
                self.assertLessEqual(max(replay["scalar_absolute_gaps"].values()), 1e-10)

    def _assert_policy_close(self, native_rows, python_rows):
        key = lambda row: (row["player"], row["hand"], tuple(row.get("history", ())))
        left, right = {key(row): row for row in native_rows}, {key(row): row for row in python_rows}
        self.assertEqual(set(left), set(right))
        for ident, native in left.items():
            python = right[ident]
            self.assertEqual(len(native["actions"]), len(python["actions"]))
            for got, want in zip(native["actions"], python["actions"]):
                self.assertEqual((got["name"], got["history_key"]), (want["name"], want["history_key"]))
                self.assertAlmostEqual(got["probability"], want["probability"], delta=1e-8)



class NativeFixedStreetClientProtocolTests(unittest.TestCase):
    """Exercise the Python response boundary without executing native code."""

    @staticmethod
    def _response(tokens, *, header="OPENPOKER_FIXED_TRAIN_V1 POLICY 8"):
        return (header + "\n" + "\n".join(tokens) + "\n").encode("ascii")

    def _invoke_stubbed(self, payload, *, backend_side_effect=None,
                        returncode=0, stderr=b""):
        from types import SimpleNamespace
        from pokerlab import native_fixed_street as native

        root, worlds, infos, pot = _trees()[0]
        executable = Path("stub-native-trainer.exe")
        manifest = {"build": "stable"}
        backend = patch.object(native, "_backend", side_effect=backend_side_effect
                               if backend_side_effect is not None else
                               [(executable, manifest), (executable, manifest)])

        def fake_run(command, **kwargs):
            self.assertEqual(command, [str(executable)])
            kwargs["stdout"].write(payload)
            if stderr:
                kwargs["stderr"].write(stderr)
            return SimpleNamespace(returncode=returncode)

        with backend as backend_mock, patch.object(native.subprocess, "run", side_effect=fake_run) as run:
            try:
                result = train_native_fixed_street(root, worlds, infos, 10, "vanilla",
                                                   pot=pot, build_directory=Path("stub-build"))
            except Exception as error:
                result = error
        return result, backend_mock, run

    def test_client_rejects_malformed_policy_responses(self):
        half = "3fe0000000000000"
        cases = {
            "wrong header": self._response([half] * 8, header="WRONG POLICY 8"),
            "wrong slot census": self._response([half] * 8, header="OPENPOKER_FIXED_TRAIN_V1 POLICY 7"),
            "trailing token": self._response([half] * 8 + [half]),
            "nonfinite probability": self._response(["7ff0000000000000"] + [half] * 7),
            "negative probability": self._response(["bfe0000000000000"] + [half] * 7),
            "unnormalized row": self._response(["3fd999999999999a"] * 8),
        }
        for label, payload in cases.items():
            with self.subTest(response=label):
                result, backend, run = self._invoke_stubbed(payload)
                self.assertIsInstance(result, ValueError)
                self.assertEqual(backend.call_count, 2)
                run.assert_called_once()

    def test_nonzero_exit_and_timeout_propagate_without_fallback(self):
        from subprocess import TimeoutExpired
        from pokerlab import native_fixed_street as native

        root, worlds, infos, pot = _trees()[0]
        executable = Path("stub-native-trainer.exe")
        manifest = {"build": "stable"}
        with patch.object(native, "_backend", return_value=(executable, manifest)) as backend, \
             patch.object(native.subprocess, "run", return_value=type("Done", (), {"returncode": 3})()) as run:
            with self.assertRaisesRegex(RuntimeError, "Native training failed \\(3\\)"):
                train_native_fixed_street(root, worlds, infos, 10, "vanilla", pot=pot,
                                          build_directory=Path("stub-build"))
            backend.assert_called_once()
            run.assert_called_once()

        with patch.object(native, "_backend", return_value=(executable, manifest)) as backend, \
             patch.object(native.subprocess, "run", side_effect=TimeoutExpired("native", 120)) as run:
            with self.assertRaises(TimeoutExpired):
                train_native_fixed_street(root, worlds, infos, 10, "vanilla", pot=pot,
                                          build_directory=Path("stub-build"))
            backend.assert_called_once()
            run.assert_called_once()

    def test_build_identity_must_be_stable_across_native_call(self):
        half = "3fe0000000000000"
        payload = self._response([half] * 8)
        executable = Path("stub-native-trainer.exe")
        result, backend, run = self._invoke_stubbed(
            payload, backend_side_effect=[(executable, {"build": "before"}),
                                          (executable, {"build": "after"})])
        self.assertIsInstance(result, RuntimeError)
        self.assertIn("build identity changed", str(result))
        self.assertEqual(backend.call_count, 2)
        run.assert_called_once()

    def test_manifest_rejects_bad_shape_work_model_source_and_executable_hash(self):
        from pokerlab import native_fixed_street as native

        raw_hash, lf_hash = native._source_hashes()
        mutations = (
            ("shape", lambda data: data.update(extra="unexpected")),
            ("work model", lambda data: data.update(work_model="other")),
            ("source identity", lambda data: data.update(source_lf_sha256="0" * 64)),
            ("executable hash", lambda data: data.update(executable_sha256="0" * 64)),
        )
        for label, mutate in mutations:
            with self.subTest(manifest=label), tempfile.TemporaryDirectory() as folder:
                directory = Path(folder)
                executable_name = "native-fixed-street-train.exe"
                executable = directory / executable_name
                executable.write_bytes(b"not executed by this test")
                manifest = {
                    "schema_version": 1, "protocol": native.PROTOCOL,
                    "work_model": native.WORK_MODEL, "source_sha256": raw_hash,
                    "source_lf_sha256": lf_hash, "executable": executable_name,
                    "executable_sha256": native._sha(executable), "compiler": "test",
                    "compiler_version": "test", "flags": [], "platform": "test",
                }
                mutate(manifest)
                (directory / "native-train-manifest.json").write_text(
                    json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(ValueError):
                    native._backend(directory)

if __name__ == "__main__":
    unittest.main()