"""Sol's independent diverse-model and overlapping-solve API witnesses."""
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier
import unittest
from unittest.mock import patch

from pokerlab import matrix_free_turn, turn_range_kernel
from pokerlab.ranked_river import RankedRiverPayoffs
from scripts.turn_river_validation import replay_policy, compare_result


def config(pot, stacks, *, bets=(0.5,), raises=(0.5,), max_raises=1, all_in=True):
    return dict(pot=pot, effective_stack=stacks, bet_sizes=list(bets),
                raise_sizes=list(raises), max_raises=max_raises, include_all_in=all_in)


CASES = (
    dict(board="2h7hThKs", oop="AhQh:0.25,AcAd:0.75", ip="KhQd:0.5,TcTd:0.5",
         runouts=["Jh", "3c"], config=config(37, [40, 23], bets=(0.5, 1.0)),
         river_config=config(37, [40, 23], bets=(0.75,))),
    dict(board="9cTdJd2s", oop="QdKd:1,8c8h:1", ip="AsAh:1,QcKh:0.2",
         runouts=["Ad", "7s", "8d"], config=config(64, 80, bets=(1.0,)),
         river_config=config(64, 80, bets=(0.5, 1.0), raises=(), max_raises=0, all_in=False)),
    dict(board="2c5d9hTc", oop="AsAh:1,KsKh:1", ip="QhQs:1,JhJs:1",
         runouts=["As"], config=config(100, 30), river_config=config(100, 30)),
    dict(board="2c7d9hJs", oop="AsAh:0.1,KcKd:0.9", ip="AsKh:0.4,QhQs:0.6",
         runouts=["As", "Kc", "4d"], config=config(23, [50, 37], raises=(1.0,), max_raises=2),
         river_config=config(23, [50, 37], bets=(0.75,), raises=(1.0,), max_raises=2)),
)


def solve(case, mode):
    return matrix_free_turn.solve_matrix_free_turn(
        case["board"], case["oop"], case["ip"], case["config"],
        river_config=case["river_config"], runouts=case["runouts"], iterations=10,
        algorithm="cfrplus", terminal_cache=mode)


def original_fields(result):
    return {key: value for key, value in result.items() if key != "terminal_cache"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class MatrixFreeTurnCacheIndependentReviewTests(unittest.TestCase):
    def test_diagnostic_failure_after_training_restores_actual_branch_objects(self):
        original_factory = matrix_free_turn.install_branch_cache
        installed = []

        def record_context(*args, **kwargs):
            context = original_factory(*args, **kwargs)
            installed.append(context)
            return context

        def fail_after_training(*args, **kwargs):
            kernel = kwargs["terminal_kernel"]
            self.assertTrue(any(type(branch["kernel"]) is not RankedRiverPayoffs
                                for branch in kernel._branches.values()))
            self.assertGreater(installed[0].runtime.calls, 0)
            raise RuntimeError("injected final diagnostic failure")

        classes = (matrix_free_turn.TurnRangePayoffs, turn_range_kernel.RankedRiverPayoffs)
        with patch.object(matrix_free_turn, "install_branch_cache", new=record_context):
            with patch.object(matrix_free_turn, "evaluate_ranked_turn_profile", new=fail_after_training):
                with self.assertRaisesRegex(RuntimeError, "injected final diagnostic failure"):
                    solve(CASES[0], "ranked-lru")
        self.assertEqual(len(installed), 1)
        context = installed[0]
        self.assertEqual(len(context.runtime.cache), 0)
        self.assertEqual(context.runtime.to_dict()["entries_after_cleanup"], 0)
        for branch in context.kernel._branches.values():
            self.assertIs(type(branch["kernel"]), RankedRiverPayoffs)
        self.assertEqual((matrix_free_turn.TurnRangePayoffs,
                          turn_range_kernel.RankedRiverPayoffs), classes)

    def test_flush_straight_orphan_and_correlated_models_replay_all_eight_metrics(self):
        for case in CASES:
            with self.subTest(board=case["board"], runouts=case["runouts"]):
                baseline, cached = solve(case, "none"), solve(case, "ranked-lru")
                self.assertEqual(canonical(baseline), canonical(original_fields(cached)))
                oracle = replay_policy(cached, case["oop"], case["ip"],
                    board=case["board"], config=case["config"],
                    river_config=case["river_config"], runouts=case["runouts"])
                differences = compare_result(cached, oracle, tolerance=1e-9)
                self.assertEqual(len(differences), 8)
                self.assertTrue(all(abs(value) <= 1e-9 for value in differences.values()))
                self.assertEqual(cached["terminal_cache"]["entries_after_cleanup"], 0)

    def test_two_cached_solves_overlap_with_distinct_original_outer_kernels(self):
        cases = (CASES[0], CASES[2])
        expected = [solve(case, "none") for case in cases]
        classes = (matrix_free_turn.TurnRangePayoffs, turn_range_kernel.RankedRiverPayoffs)
        original_train = matrix_free_turn.train_ranked_turn
        both_installed = Barrier(2)
        observed = []

        def overlap(*args, **kwargs):
            observed.append(kwargs["terminal_kernel"])
            both_installed.wait(timeout=30)
            return original_train(*args, **kwargs)

        with patch.object(matrix_free_turn, "train_ranked_turn", new=overlap):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(solve, case, "ranked-lru") for case in cases]
                actual = [future.result(timeout=60) for future in futures]
        self.assertEqual(len(observed), 2)
        self.assertIsNot(observed[0], observed[1])
        for old, new in zip(expected, actual):
            self.assertEqual(canonical(old), canonical(original_fields(new)))
            self.assertEqual(new["terminal_cache"]["current_entries"], 0)
        for kernel in observed:
            self.assertIs(type(kernel), classes[0])
            for branch in kernel._branches.values():
                self.assertIs(type(branch["kernel"]), RankedRiverPayoffs)
        self.assertEqual((matrix_free_turn.TurnRangePayoffs,
                          turn_range_kernel.RankedRiverPayoffs), classes)


if __name__ == "__main__":
    unittest.main()
