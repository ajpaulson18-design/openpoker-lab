"""Production solver integration checks for the ranked river terminal backend."""
from math import isfinite
from fractions import Fraction as F
import unittest

from pokerlab.postflop_solver import solve_postflop
from pokerlab.river_config import RiverConfig
from pokerlab.ranked_river import RankedRiverPayoffs
from pokerlab.cards import rank_hand
from pokerlab.river_tree import _Terminal
from pokerlab.postflop_solver import _Chance
from pokerlab.public_cfr import train_public_batched
from pokerlab.river_tree import _Node, _Terminal
from scripts.river_analytical import metrics, serialized_profile


def _cases():
    ranges = ("AsAh:0.75,KcKd:1,QsQh:0.5",
              "JcJd:1,6c7d:0.5,QcQd:0.7")
    return (
        ("2c3d4h5s9c", *ranges,
         RiverConfig(pot=30, effective_stack=(55, 70),
                     bet_sizes=(0.33, 0.8), raise_sizes=(0.5,),
                     max_raises=1, include_all_in=True)),
        ("2c3d4h5s9c", *ranges,
         RiverConfig(pot=20, effective_stack=(12, 35),
                     bet_sizes=(0.5, 1.0), raise_sizes=(0.5,),
                     max_raises=1, include_all_in=True)),
    )


def _solve(case, *, algorithm="vanilla", diagnostics="public-batched",
           iterations=25, backend="sparse", **kwargs):
    board, oop, ip, config = case
    return solve_postflop(board, oop, ip, config, iterations=iterations,
                          algorithm=algorithm, traversal="public-batched",
                          diagnostics=diagnostics, terminal_backend=backend,
                          **kwargs)


def _assert_strategy_valid(test, result):
    for row in result["strategy"]:
        probabilities = [action["probability"] for action in row["actions"]]
        test.assertTrue(probabilities)
        test.assertTrue(all(isfinite(value) and value >= 0 for value in probabilities))
        test.assertAlmostEqual(sum(probabilities), 1.0, places=10)


class RankedRiverSolverIntegrationTests(unittest.TestCase):
    def test_ranked_training_and_both_diagnostic_modes_match_sparse_world_backend(self):
        for case_index, case in enumerate(_cases()):
            for algorithm in ("vanilla", "dcfr", "cfrplus"):
                with self.subTest(case=case_index, algorithm=algorithm):
                    sparse_public = _solve(case, algorithm=algorithm,
                                           diagnostics="public-batched")
                    ranked_public = _solve(case, algorithm=algorithm,
                                           diagnostics="public-batched", backend="ranked")
                    sparse_recursive = _solve(case, algorithm=algorithm,
                                              diagnostics="recursive")
                    ranked_recursive = _solve(case, algorithm=algorithm,
                                              diagnostics="recursive", backend="ranked")
                    self.assertEqual(ranked_public["terminal_backend"],
                                     "ranked-river-python")
                    self.assertNotIn("terminal_backend", sparse_public)
                    self.assertNotIn("terminal_backend", sparse_recursive)
                    for ranked, sparse in ((ranked_public, sparse_public),
                                           (ranked_recursive, sparse_recursive)):
                        for field in ("value_oop", "oop_best_response_value",
                                      "ip_best_response_value", "nash_conv",
                                      "exploitability"):
                            self.assertAlmostEqual(ranked[field], sparse[field],
                                                   delta=1e-8, msg=field)
                        _assert_strategy_valid(self, ranked)

    def test_ranked_target_stopping_uses_same_policy_metrics_as_sparse_reference(self):
        case = _cases()[0]
        sparse = _solve(case, iterations=30, backend="sparse",
                        diagnostics="recursive", target_exploitability=1e9,
                        check_interval=5)
        ranked = _solve(case, iterations=30, backend="ranked",
                        diagnostics="recursive", target_exploitability=1e9,
                        check_interval=5)
        self.assertEqual(sparse["iterations"], ranked["iterations"])
        self.assertEqual(sparse["convergence"]["stop_reason"],
                         ranked["convergence"]["stop_reason"])
        self.assertEqual([entry["iteration"] for entry in sparse["convergence"]["checkpoints"]],
                         [entry["iteration"] for entry in ranked["convergence"]["checkpoints"]])
        for sparse_checkpoint, ranked_checkpoint in zip(
                sparse["convergence"]["checkpoints"],
                ranked["convergence"]["checkpoints"]):
            for field in ("value_oop", "oop_best_response_value",
                          "ip_best_response_value", "nash_conv", "exploitability"):
                self.assertAlmostEqual(sparse_checkpoint[field], ranked_checkpoint[field],
                                       delta=1e-8, msg=field)
        fixed_ranked = _solve(case, iterations=ranked["iterations"], backend="ranked",
                              diagnostics="recursive")
        final = ranked["convergence"]["checkpoints"][-1]
        for field in ("value_oop", "oop_best_response_value",
                      "ip_best_response_value", "nash_conv", "exploitability"):
            self.assertAlmostEqual(final[field], fixed_ranked[field], delta=1e-8,
                                   msg=field)

    def test_polarised_analytical_oracle_checks_ranked_trained_policy(self):
        board = "2c7d9hJsKd"
        config = RiverConfig(100, 500, (1.0,), (), 0, False)
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                result = solve_postflop(
                    board, "AsAh,3c4c", "QsQh", config,
                    iterations=300, algorithm=algorithm, traversal="public-batched",
                    diagnostics="public-batched", terminal_backend="ranked",
                )
                expected = metrics(serialized_profile(result))
                for field, value in zip(("value_oop", "oop_best_response_value",
                                         "ip_best_response_value"), expected):
                    self.assertAlmostEqual(result[field], float(value), places=9, msg=field)
                self.assertAlmostEqual(result["nash_conv"],
                                       float(expected[1] + expected[2]), places=9)
                self.assertLess(result["nash_conv"], 4)

    def test_default_sparse_result_is_unchanged_and_backend_guards_hold(self):
        case = _cases()[0]
        implicit = solve_postflop(case[0], case[1], case[2], case[3],
                                  iterations=10, traversal="public-batched",
                                  diagnostics="public-batched")
        explicit = solve_postflop(case[0], case[1], case[2], case[3],
                                  iterations=10, traversal="public-batched",
                                  diagnostics="public-batched", terminal_backend="sparse")
        self.assertEqual(implicit, explicit)
        with self.assertRaisesRegex(ValueError, "requires a river start"):
            solve_postflop("2c3d4h5s", "AsAh", "KcKd", case[3], iterations=10,
                           traversal="public-batched", terminal_backend="ranked")
        with self.assertRaisesRegex(ValueError, "requires a river start"):
            solve_postflop("2c3d4h", "AsAh", "KcKd", case[3], iterations=10,
                           traversal="public-batched", terminal_backend="ranked")
        for traversal in ("recursive", "planned"):
            with self.subTest(traversal=traversal), self.assertRaisesRegex(
                    ValueError, "public-batched traversal"):
                solve_postflop(case[0], case[1], case[2], case[3], iterations=10,
                               traversal=traversal, terminal_backend="ranked")

    def test_ranked_backend_matches_sparse_when_range_has_orphan_tail_hand(self):
        board = "2c7d9hJsKd"
        config = RiverConfig(40, 70, (0.5,), (), 0, False)
        # The final OOP holding AsKs is blocked by IP's AsQh. AcAd is legal.
        # Hand indices retain the orphan tail even though it has no world.
        oop, ip = "AcAd,AsKs", "AsQh"
        sparse = solve_postflop(board, oop, ip, config, iterations=30,
                                traversal="public-batched", diagnostics="public-batched")
        ranked = solve_postflop(board, oop, ip, config, iterations=30,
                                traversal="public-batched", diagnostics="public-batched",
                                terminal_backend="ranked")
        self.assertAlmostEqual(ranked["value_oop"], sparse["value_oop"], places=10)
        self.assertAlmostEqual(ranked["nash_conv"], sparse["nash_conv"], places=10)
        self.assertEqual(len(ranked["strategy"]), len(sparse["strategy"]))
        self.assertNotIn("AsKs", [row["hand"] for row in ranked["strategy"]])

    def test_tiny_only_compatible_world_matches_sparse_solver_across_algorithms(self):
        board = "2c3d4h5s9c"
        config = RiverConfig(pot=40, effective_stack=80, bet_sizes=(0.5,),
                             max_raises=0, include_all_in=False)
        oop = "AsAh"
        for tiny_weight in (1e-4, 1e-8, 1e-10, 1e-16):
            ip = f"AsKc:1,AhKd:1,KcKd:{tiny_weight}"
            for algorithm in ("vanilla", "dcfr", "cfrplus"):
                with self.subTest(weight=tiny_weight, algorithm=algorithm):
                    sparse = solve_postflop(
                        board, oop, ip, config, iterations=10,
                        algorithm=algorithm, traversal="public-batched",
                        diagnostics="public-batched",
                    )
                    ranked = solve_postflop(
                        board, oop, ip, config, iterations=10,
                        algorithm=algorithm, traversal="public-batched",
                        diagnostics="public-batched", terminal_backend="ranked",
                    )
                    self.assertEqual(sparse["worlds"], 1)
                    self.assertEqual(ranked["worlds"], 1)
                    for field in ("value_oop", "oop_best_response_value",
                                  "ip_best_response_value", "nash_conv",
                                  "exploitability"):
                        self.assertTrue(isfinite(ranked[field]), field)
                        self.assertAlmostEqual(ranked[field], sparse[field], delta=1e-8,
                                               msg=(tiny_weight, algorithm, field))

    def test_fold_reach_keeps_tiny_legal_mass_among_blocked_dominant_reach(self):
        board = ("2c", "3d", "4h", "5s", "9c")
        hands = ((tuple(sorted(("As", "Ah"))),),
                 (tuple(sorted(("As", "Kc"))),
                  tuple(sorted(("Ah", "Kd"))),
                  tuple(sorted(("Kc", "Kd")))))
        kernel = RankedRiverPayoffs(board, hands, ((1,), (1, 1, 1)), pot=40)
        terminal = _Terminal("fold", (F(0), F(0)), winner=0)
        reaches = [1, 1, F(1, 10**8)]
        actual = kernel.values(terminal, reaches, 0)[0]
        expected = F(20, 10**8)
        self.assertAlmostEqual(actual / float(expected), 1.0, places=8)

    def test_rank_kernel_world_validation_rejects_malformed_sparse_world_sets(self):
        board = ("2c", "3d", "4h", "5s", "9c")
        hands = ((tuple(sorted(("As", "Ah"))), tuple(sorted(("Ks", "Kh")))),
                 (tuple(sorted(("Qs", "Qh"))), tuple(sorted(("Jc", "Jd")))))
        weights = ((1, 2), (3, 1))
        kernel = RankedRiverPayoffs(board, hands, weights, pot=20)
        worlds = []
        for i, h0 in enumerate(hands[0]):
            for j, h1 in enumerate(hands[1]):
                mass = kernel.weights[0][i] * kernel.weights[1][j] * kernel.factor
                rank0 = rank_hand(board + h0)
                rank1 = rank_hand(board + h1)
                sign = (rank0 > rank1) - (rank0 < rank1)
                worlds.append((i, j, mass, sign))
        self.assertIsNone(kernel.validate_worlds(worlds, pot=20))
        invalid = []
        invalid.append((worlds[:-1], 20, "complete compatible"))
        invalid.append((worlds[:-1] + [worlds[0]], 20, "duplicate"))
        changed = list(worlds)
        changed[0] = (*changed[0][:2], changed[0][2] + 0.1, changed[0][3])
        invalid.append((changed, 20, "mass"))
        changed = list(worlds)
        changed[0] = (*changed[0][:3], -changed[0][3] if changed[0][3] else 1)
        invalid.append((changed, 20, "sign"))
        invalid.append(([(*world, "5h") for world in worlds], 20, "future cards"))
        changed = list(worlds)
        changed[0] = (len(hands[0]), changed[0][1], *changed[0][2:])
        invalid.append((changed, 20, "indices"))
        for supplied, pot, message in invalid:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                kernel.validate_worlds(supplied, pot=pot)
        with self.assertRaisesRegex(ValueError, "pot"):
            kernel.validate_worlds(worlds, pot=21)
        root = _Node((), 0, ("check", "bet"), (
            _Terminal("showdown", (0, 0)), _Terminal("showdown", (0, 0))))
        infos = {(0, index, ()): 2 for index in range(len(hands[0]))}
        with self.assertRaisesRegex(ValueError, "pot"):
            train_public_batched(
                root, worlds, infos, 1, "vanilla", pot=21, chance_type=_Chance,
                terminal_kernel=kernel,
            )


if __name__ == "__main__":
    unittest.main()
