"""Independent integration checks for opt-in alternating flop trainers."""

from contextlib import ExitStack, contextmanager
import copy
import gzip
import hashlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from pokerlab import alternating_public_cfr as alternating
from pokerlab import postflop_solver as solver
from pokerlab import preflop_delayed_cfrplus as delayed
from pokerlab.river_config import RiverConfig
from scripts import flop_multistreet_validation as independent
from scripts.benchmark_weighted_full_deck_flop import independent_guard as base_guard


ROOT = Path(__file__).resolve().parents[1]
BOARD = "2c3d4h"
OOP = "AsAd:1,QsQd:0.5"
IP = "AsKh:0.25,KsKd:1"
OOP_HANDS = (("AdAs", "1"), ("QdQs", "1/2"))
IP_HANDS = (("AsKh", "1/4"), ("KdKs", "1"))
BASE = {"pot": 10, "effective_stack": 5, "bet_sizes": [0.5],
        "raise_sizes": [], "max_raises": 0, "include_all_in": False}
METRICS = (
    "value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value",
    "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability",
)
ALGORITHMS = {
    "lcfr": {
        "average_schedule": "linear-pre-sweep-own-reach",
        "regret_schedule": "linear-weighted-unfloored",
    },
    "dcfr-alternating": {
        "average_schedule": "quadratic-pre-sweep-own-reach",
        "regret_schedule": "discounted-3/2-0-2-unfloored",
    },
}


@contextmanager
def independent_guard():
    """Keep both independent replay and its inputs away from production code."""
    with base_guard() as calls, ExitStack() as stack:
        for module, name in (
            (delayed, "train_delayed_public_cfrplus"),
            (alternating, "train_public_lcfr"),
            (alternating, "train_public_alternating_dcfr"),
            (alternating, "_train_alternating"),
            (alternating, "_weighted_average_sweep"),
            (alternating, "_cfrplus_target_deltas"),
            (alternating, "_aggregate_prefixes"),
        ):
            key = module.__name__ + "." + name
            calls[key] = 0

            def forbidden(*args, _key=key, **kwargs):
                calls[_key] += 1
                raise AssertionError("Independent replay called a production trainer: " + _key)

            stack.enter_context(patch.object(module, name, side_effect=forbidden))
        yield calls


def assert_replay(testcase, result, oracle):
    with independent_guard() as calls:
        checked = independent.replay(result, oracle, tolerance=1e-10)
    testcase.assertFalse(any(calls.values()), calls)
    testcase.assertEqual(checked["checked_physical_worlds"], len(oracle["worlds"]))
    testcase.assertLessEqual(max(checked["scalar_absolute_gaps"].values()), 1e-10)
    return checked


def assert_strategy_equal(testcase, left, right):
    testcase.assertEqual(left["strategy"], right["strategy"])


def _legacy_source():
    path = ROOT / "benchmarks/sources/postflop-before-alternating-flop-v1.py.gz"
    if path.stat().st_size != 8213:
        raise ValueError("Frozen pre-alternating adapter archive size changed")
    with gzip.open(path, "rb") as stream:
        source = stream.read(256 * 1024 + 1)
    if (len(source) != 33524 or b"\r" in source or
            hashlib.sha256(source).hexdigest() !=
            "35a00f29f1d86d95dae218f8880f697822fac3fc6563c01824677b428f9d7891"):
        raise ValueError("Frozen pre-alternating adapter source changed")
    return source.decode("utf-8")


class ReachedTrainer(Exception):
    pass


class FlopAlternatingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with independent_guard() as calls:
            cls.full_oracle = independent.prepare_oracle(
                BOARD, OOP_HANDS, IP_HANDS, BASE)
        if any(calls.values()):
            raise AssertionError("Independent oracle preparation called production code")
        if len(cls.full_oracle["worlds"]) != 5940:
            raise AssertionError("Full physical fixture census changed")

    def _assert_metadata(self, result, algorithm):
        self.assertEqual(result["algorithm"], algorithm)
        self.assertEqual(result["solver_version"], "configured-postflop-alternating-v1")
        self.assertEqual(result["training_passes_per_iteration"], 3)
        self.assertEqual(result["update_schedule"], "alternating-oop-then-ip")
        self.assertEqual(result["average_schedule"], ALGORITHMS[algorithm]["average_schedule"])
        self.assertEqual(result["regret_schedule"], ALGORITHMS[algorithm]["regret_schedule"])
        self.assertEqual(result["training_kernel"], algorithm + "-public-batched-python")
        self.assertIs(result["regret_floor"], False)
        self.assertEqual(result["execution_backend"], "public-batched-python")

    def test_full_5940_world_profiles_replay_all_eight_metrics(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                result = solver.solve_postflop(
                    BOARD, OOP, IP, config=BASE, iterations=10,
                    algorithm=algorithm, traversal="public-batched")
                replay = assert_replay(self, result, self.full_oracle)
                self.assertEqual(replay["checked_physical_worlds"], 5940)
                self.assertEqual(set(replay["scalar_absolute_gaps"]), set(METRICS))
                self.assertTrue(any(row["street"] == "turn" for row in result["strategy"]))
                self.assertTrue(any(row["street"] == "river" for row in result["strategy"]))
                self._assert_metadata(result, algorithm)

    def test_selected_raises_refunds_and_street_sizing_replay(self):
        config = {"pot": 10, "effective_stack": [12, 20], "bet_sizes": [0.5],
                  "raise_sizes": [0.5], "max_raises": 1, "include_all_in": True}
        turn = dict(config, bet_sizes=[0.75])
        river = dict(config, bet_sizes=[0.25])
        runouts = [("As", "5c"), ("5c", "As"), ("5c", "9h")]
        with independent_guard() as calls:
            oracle = independent.prepare_oracle(
                BOARD, OOP_HANDS, IP_HANDS, config,
                turn_config=turn, river_config=river, runouts=runouts)
        self.assertFalse(any(calls.values()), calls)

        for algorithm in ALGORITHMS:
            results = {}
            for diagnostics in ("recursive", "public-batched"):
                with self.subTest(algorithm=algorithm, diagnostics=diagnostics):
                    result = solver.solve_postflop(
                        BOARD, OOP, IP, config=config, turn_config=turn,
                        river_config=river, runouts=runouts, iterations=10,
                        algorithm=algorithm, traversal="public-batched",
                        diagnostics=diagnostics)
                    assert_replay(self, result, oracle)
                    self._assert_metadata(result, algorithm)
                    results[diagnostics] = result
            assert_strategy_equal(self, results["recursive"], results["public-batched"])
            self.assertEqual(results["public-batched"]["diagnostics_backend"],
                             "public-batched-python")
            self.assertTrue(any(
                action["name"] == "all_in"
                for row in results["recursive"]["strategy"]
                for action in row["actions"]))

    def test_scope_guards_reject_before_world_enumeration(self):
        invalid = [
            (BOARD, "recursive", 0, {}),
            (BOARD, "planned", 0, {}),
            ("2c3d4h5c", "public-batched", 0, {}),
            ("2c3d4h5c9h", "public-batched", 0, {}),
            (BOARD, "public-batched", 1, {}),
            (BOARD, "public-batched", 0, {"target_exploitability": 0.01}),
        ]
        for board, traversal, delay, extra in invalid:
            for algorithm in ALGORITHMS:
                with self.subTest(board=board, traversal=traversal,
                                  delay=delay, extra=extra, algorithm=algorithm):
                    with patch.object(solver, "_enumerate_worlds",
                                      side_effect=AssertionError("enumerated before scope guard")) as enum:
                        with self.assertRaises(ValueError):
                            solver.solve_postflop(
                                board, OOP, IP, config=BASE, iterations=10,
                                algorithm=algorithm, traversal=traversal,
                                averaging_delay=delay, **extra)
                        enum.assert_not_called()

    def test_three_pass_full_request_boundary_precedes_alternating_trainers(self):
        hands, worlds, selected, pairs = solver._enumerate_worlds(
            tuple(BOARD[i:i + 2] for i in range(0, len(BOARD), 2)),
            OOP, IP, None, 140)
        root, nodes, chance, visits, ops = solver._build_postflop_tree(
            tuple(BOARD[i:i + 2] for i in range(0, len(BOARD), 2)),
            RiverConfig.from_dict(BASE),
            worlds=worlds)
        self.assertEqual(len(worlds), 5940)
        self.assertEqual(len(worlds) * visits * 140 * 3, 29_937_600)
        self.assertGreater(len(worlds) * visits * 141 * 3, solver._MAX_WORLD_NODE_WORK)
        admission_rows = (hands, worlds, selected, pairs)
        tree_rows = (root, nodes, chance, visits, ops)

        for algorithm, trainer_name in (
            ("lcfr", "train_public_lcfr"),
            ("dcfr-alternating", "train_public_alternating_dcfr"),
        ):
            trainer = getattr(alternating, trainer_name)
            for iterations, should_reject in ((140, False), (141, True)):
                with self.subTest(algorithm=algorithm, iterations=iterations):
                    with patch.object(solver, "_enumerate_worlds", return_value=admission_rows), \
                         patch.object(solver, "_build_postflop_tree", return_value=tree_rows), \
                         patch.object(alternating, trainer_name,
                                      side_effect=ReachedTrainer) as call:
                        if should_reject:
                            with self.assertRaisesRegex(ValueError, "30 million world-node"):
                                solver.solve_postflop(
                                    BOARD, OOP, IP, config=BASE, iterations=iterations,
                                    algorithm=algorithm, traversal="public-batched")
                            call.assert_not_called()
                        else:
                            with self.assertRaises(ReachedTrainer):
                                solver.solve_postflop(
                                    BOARD, OOP, IP, config=BASE, iterations=iterations,
                                    algorithm=algorithm, traversal="public-batched")
                            call.assert_called_once()
                            self.assertEqual(call.call_args.args[3], 140)

    def test_prefix_edge_limit_is_enforced_before_tree_and_dispatch(self):
        board = tuple(BOARD[i:i + 2] for i in range(0, len(BOARD), 2))
        runouts = (("5c", "6c"), ("6c", "5c"))
        worlds = solver._enumerate_worlds(board, OOP, IP, runouts, 10)[1]
        edge_count = solver._reserve_flop_diagnostic_prefix_edges(worlds)
        self.assertGreater(edge_count, 0)

        for algorithm, trainer_name in (
            ("lcfr", "train_public_lcfr"),
            ("dcfr-alternating", "train_public_alternating_dcfr"),
        ):
            with self.subTest(algorithm=algorithm):
                with ExitStack() as stack:
                    tree = stack.enter_context(patch.object(
                        solver, "_build_postflop_tree",
                        side_effect=AssertionError("tree built before prefix cap")))
                    trainer = stack.enter_context(patch.object(
                        alternating, trainer_name,
                        side_effect=AssertionError("trainer called before prefix cap")))
                    stack.enter_context(patch.object(solver, "MAX_PREFIX_EDGES", edge_count - 1))
                    with self.assertRaisesRegex(ValueError, "prefix/hand edges"):
                        solver.solve_postflop(
                            BOARD, OOP, IP, config=BASE, iterations=10,
                            algorithm=algorithm, traversal="public-batched",
                            runouts=runouts)
                    tree.assert_not_called()
                    trainer.assert_not_called()

                with patch.object(alternating, trainer_name,
                                  side_effect=ReachedTrainer) as trainer, \
                     patch.object(solver, "MAX_PREFIX_EDGES", edge_count):
                    with self.assertRaises(ReachedTrainer):
                        solver.solve_postflop(
                            BOARD, OOP, IP, config=BASE, iterations=10,
                            algorithm=algorithm, traversal="public-batched",
                            runouts=runouts)
                    trainer.assert_called_once()

    def test_independent_replay_rejects_forged_alternating_metadata(self):
        result = solver.solve_postflop(
            BOARD, OOP, IP, config=BASE, iterations=10,
            algorithm="lcfr", traversal="public-batched")
        mutations = (
            ("solver_version", "configured-postflop-v1"),
            ("training_passes_per_iteration", 1),
            ("training_passes_per_iteration", True),
            ("execution_backend", "recursive-python"),
            ("averaging_delay", 0),
            ("convergence", {}),
            ("update_schedule", "simultaneous"),
            ("average_schedule", "linear-post-sweep-own-reach"),
            ("regret_schedule", "discounted-3/2-0-2-unfloored"),
            ("training_kernel", "vanilla-public-batched-python"),
            ("regret_floor", True),
            ("algorithm", "unknown"),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                forged = copy.deepcopy(result)
                forged[key] = value
                with independent_guard():
                    with self.assertRaises(ValueError):
                        independent.replay(forged, self.full_oracle, tolerance=1e-10)

    def test_pre_alternating_archive_preserves_every_legacy_dispatch_payload(self):
        source = _legacy_source()
        legacy = types.ModuleType("pokerlab._postflop_before_alternating")
        legacy.__package__ = "pokerlab"
        with patch.dict(sys.modules, {legacy.__name__: legacy}):
            exec(compile(source, "frozen-postflop-before-alternating", "exec"),
                 legacy.__dict__)
            cases = [
                (BOARD, (("5c", "6c"), ("6c", "5c")), ("vanilla", "dcfr", "cfrplus")),
                ("2c3d4h5c", ("9h", "Tc"), ("vanilla", "dcfr", "cfrplus")),
                ("2c3d4h5c9h", None, ("vanilla", "dcfr", "cfrplus")),
            ]
            for board, runouts, algorithms in cases:
                for algorithm in algorithms:
                    delays = (0, 2) if algorithm == "cfrplus" and board == BOARD else (0,)
                    for delay in delays:
                        traversals = (("recursive", "public-batched")
                                      if algorithm == "cfrplus" else
                                      ("recursive", "planned", "public-batched"))
                        for traversal in traversals:
                            for diagnostics in ("recursive", "public-batched"):
                                with self.subTest(board=board, algorithm=algorithm,
                                                  delay=delay, diagnostics=diagnostics,
                                                  traversal=traversal):
                                    options = dict(
                                        config=BASE, runouts=runouts, iterations=10,
                                        algorithm=algorithm, traversal=traversal,
                                        diagnostics=diagnostics, averaging_delay=delay)
                                    expected = legacy.solve_postflop(board, OOP, IP, **options)
                                    actual = solver.solve_postflop(board, OOP, IP, **options)
                                    self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
