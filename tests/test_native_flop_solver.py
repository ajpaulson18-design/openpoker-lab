"""Admission and composition checks for the cold native flop solve API."""
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from pokerlab import flop_checkdown_solver as solver
from pokerlab import flop_checkdown_worlds as worlds
from pokerlab import native_fixed_street
from pokerlab import native_flop_equity
from pokerlab import native_preflop_equity
from pokerlab.cards import DECK
from scripts.flop_checkdown_validation import prepare_oracle_from_counts, replay


ROOT = Path(__file__).resolve().parents[1]
COUNT_BUILD = os.environ.get("OPENPOKER_NATIVE_EQUITY_BUILD_DIR")
TRAIN_BUILD = os.environ.get("OPENPOKER_NATIVE_TRAIN_BUILD_DIR")
NATIVE_AVAILABLE = bool(COUNT_BUILD and TRAIN_BUILD
                        and Path(COUNT_BUILD).is_dir() and Path(TRAIN_BUILD).is_dir())
BOARD = "2c3c4d"
DEEP_CONFIG = {
    "pot": 6, "effective_stack": 24, "bet_sizes": [.5, 1.0, 2.0],
    "raise_sizes": [.5, 1.0], "max_raises": 3, "include_all_in": True,
}
CAP8_OOP = "2d2h,2s3d,3h3s,4c4h,4s5c,5d5h,5s6c,6d6h"
CAP8_IP = "6s7c,7d7h,7s8c,8d8h,8s9c,9d9h,9sTc,TdTh,TsJc,JdJh,JsQc,QdQh,QsKc,KdKh,KsAc,AdAh"
TINY_CONFIG = {
    "pot": 2, "effective_stack": 1, "bet_sizes": [.5],
    "raise_sizes": [], "max_raises": 0, "include_all_in": True,
}


def _star_ranges():
    """Two 32-hand ranges with 1,024 candidates but only 63 compatible pairs."""
    excluded = {"2c", "3c", "4d", "5c", "6c", "7c", "8c", "9c"}
    partners = [card for card in DECK if card not in excluded][:31]
    oop = ["5c" + card for card in partners] + ["6c7c"]
    ip = ["5c" + card for card in partners] + ["8c9c"]
    return ",".join(oop), ",".join(ip)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _report_checksum(report):
    unsigned = dict(report)
    unsigned.pop("artifact_sha256", None)
    return hashlib.sha256(_canonical(unsigned)).hexdigest()


def _assert_cross_build_payload_equal(testcase, actual, frozen):
    """Ignore only host-specific build identity and allow binary64 drift."""
    left, right = dict(actual), dict(frozen)
    left.pop("equity_preparation")
    right.pop("equity_preparation")
    left_native, right_native = dict(left["native_training"]), dict(right["native_training"])
    left_native.pop("build")
    right_native.pop("build")
    left["native_training"], right["native_training"] = left_native, right_native

    for key in ("value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value",
                "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability"):
        testcase.assertAlmostEqual(left.pop(key), right.pop(key), delta=1e-8, msg=key)
    left_rows, right_rows = left.pop("strategy"), right.pop("strategy")
    testcase.assertEqual(len(left_rows), len(right_rows))
    for row_a, row_b in zip(left_rows, right_rows):
        testcase.assertEqual({k: v for k, v in row_a.items() if k != "actions"},
                             {k: v for k, v in row_b.items() if k != "actions"})
        testcase.assertEqual(len(row_a["actions"]), len(row_b["actions"]))
        for action_a, action_b in zip(row_a["actions"], row_b["actions"]):
            testcase.assertEqual({k: v for k, v in action_a.items() if k != "probability"},
                                 {k: v for k, v in action_b.items() if k != "probability"})
            testcase.assertAlmostEqual(action_a["probability"], action_b["probability"],
                                       delta=1e-8)
    testcase.assertEqual(left, right)


class NativeFlopSolveAdmissionTests(unittest.TestCase):
    def _solve(self, oop, ip, *, algorithm, iterations, config=DEEP_CONFIG):
        return solver.solve_native_flop_checkdown(
            BOARD, oop, ip, count_build_directory="not-looked-up-count-build",
            training_build_directory="not-looked-up-training-build",
            config=config, iterations=iterations, algorithm=algorithm,
        )

    def _forbid_work_lookups(self):
        return (
            patch.object(worlds, "rank_hand", side_effect=AssertionError("ranked before admission")),
            patch.object(native_flop_equity, "_invoke",
                         side_effect=AssertionError("count helper invoked before admission")),
            patch.object(native_flop_equity, "_prepare_admitted_plan",
                         side_effect=AssertionError("count preparation began before admission")),
            patch.object(native_preflop_equity, "_backend",
                         side_effect=AssertionError("count build lookup before admission")),
            patch.object(native_fixed_street, "_backend",
                         side_effect=AssertionError("trainer build lookup before admission")),
        )

    def test_historical_native_shape_and_combined_limits_reject_before_counting(self):
        cases = (
            # Historical Python vector estimate rejects before the specialized
            # native-shape admission is reached.
            (CAP8_OOP, CAP8_IP, "cfrplus", 10_000,
             "Vector budget estimated loop entries exceed 500,000,000", "history"),
            # Historical bound passes, but the full native trainer shape does
            # not fit its 500M work envelope.
            (CAP8_OOP, CAP8_IP, "cfrplus", 2_000,
             "Full requested native training exceeds 500,000,000", "native-shape"),
            # Historical total (179,341,952) and native shape (499,643,488)
            # each pass; retaining 4,129,080 nontraining units makes the
            # combined solve exceed 500M (503,772,568).
            (*_star_ranges(), "vanilla", 3_000,
             "Complete native solve exceeds 500,000,000", "combined"),
        )
        for oop, ip, algorithm, iterations, message, layer in cases:
            patches = self._forbid_work_lookups()
            with self.subTest(layer=layer), patches[0], patches[1], patches[2], patches[3], patches[4], \
                    self.assertRaisesRegex(ValueError, message):
                self._solve(oop, ip, algorithm=algorithm, iterations=iterations)

    def test_invalid_options_and_ranges_reject_before_either_backend(self):
        cases = [
            {"iterations": True}, {"iterations": 9}, {"iterations": 10001},
            {"algorithm": "unsupported"}, {"config": {"effective_stack": 2e12}},
            {"config": {"pot": 2e12, "effective_stack": 1}},
            {"count_build_directory": None}, {"training_build_directory": None},
            {"board": "2c2c4d"}, {"oop_range": "AsAs"},
            {"oop_range": "random", "ip_range": "random"},
            {"oop_range": "AsAd", "ip_range": "AsKh"},
        ]
        for change in cases:
            options = dict(board=BOARD, oop_range="AsAd", ip_range="KsKd",
                           count_build_directory="missing-count-build",
                           training_build_directory="missing-train-build",
                           config=TINY_CONFIG, iterations=10, algorithm="vanilla")
            options.update(change)
            patches = self._forbid_work_lookups()
            with self.subTest(change=change), patches[0], patches[1], patches[2], patches[3], patches[4], \
                    self.assertRaises(ValueError):
                solver.solve_native_flop_checkdown(**options)

    @unittest.skipUnless(NATIVE_AVAILABLE,
                         "Set both explicit native build directories for end-to-end checks")
    def test_tiny_cold_solve_matches_native_two_step_and_independent_replay(self):
        trusted_counts = [{
            "oop_hand": "AdAs", "ip_hand": "KdKs", "wins": 1782,
            "ties": 48, "losses": 150, "ordered_outcomes": 1980,
        }]
        oracle = prepare_oracle_from_counts(
            BOARD, "AsAd", "KsKd", TINY_CONFIG, trusted_counts)
        for algorithm in ("vanilla", "dcfr", "cfrplus"):
            with self.subTest(algorithm=algorithm):
                cold = solver.solve_native_flop_checkdown(
                    BOARD, "AsAd", "KsKd", count_build_directory=COUNT_BUILD,
                    training_build_directory=TRAIN_BUILD, config=TINY_CONFIG,
                    iterations=10, algorithm=algorithm)
                prepared = native_flop_equity.prepare_native_flop_checkdown_equities(
                    BOARD, "AsAd", "KsKd", build_directory=COUNT_BUILD)
                staged = solver.solve_prepared_flop_checkdown(
                    prepared.equities, config=TINY_CONFIG, iterations=10,
                    algorithm=algorithm, training_backend="native",
                    build_directory=TRAIN_BUILD)
                cold_game = dict(cold)
                staged_game = dict(staged)
                cold_game.pop("equity_preparation")
                staged_game.pop("equity_preparation")
                self.assertEqual(cold_game, staged_game)
                self.assertEqual(cold["pair_equities"][0]["wins"], 1782)
                self.assertEqual(cold["equity_preparation"]["mode"], "native-cold-counts")
                audited = replay(cold, oracle, tolerance=1e-10)
                self.assertLessEqual(max(audited["scalar_absolute_gaps"].values()), 1e-10)

    def test_count_failure_propagates_without_python_ranking_or_training_fallback(self):
        with patch.object(native_flop_equity, "_invoke",
                          side_effect=RuntimeError("native count failure")) as invoke, \
             patch.object(worlds, "rank_hand", side_effect=AssertionError("Python rank fallback")) as rank, \
             patch.object(solver, "train_public_batched",
                          side_effect=AssertionError("Python training fallback")) as train:
            with self.assertRaisesRegex(RuntimeError, "native count failure"):
                self._solve("AsAd", "KsKd", algorithm="vanilla", iterations=10,
                            config=TINY_CONFIG)
        invoke.assert_called_once()
        rank.assert_not_called()
        train.assert_not_called()

    @unittest.skipUnless(NATIVE_AVAILABLE,
                         "Set both explicit native build directories for frozen-profile replay")
    def test_58_pair_4000_sweep_matches_frozen_native_profile_and_replays_independently(self):
        spec_path = ROOT / "benchmarks" / "native-flop-preparation-v1.json"
        report_path = ROOT / "benchmarks" / "results" / "native-flop-preparation-v1.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(_canonical(spec)).hexdigest(),
                         "7dee0d6e7b77686224741fcd9face6f1b508fd8ac4519464e40ffd1ff9230ed9")
        self.assertEqual(report["artifact_sha256"],
                         "86d0215733529b20a174506ccd7ca41c78f4734d43aa49a48d0a07c8b31691b4")
        self.assertEqual(_report_checksum(report), report["artifact_sha256"])
        self.assertEqual(report["spec_sha256"], hashlib.sha256(_canonical(spec)).hexdigest())
        fixture = next(item for item in spec["fixtures"]
                       if item["id"] == "base-8x8-stack24-raises2")
        frozen_stage = next(item for item in next(
            item for item in report["fixtures"] if item["fixture_id"] == fixture["id"]
        )["stages"] if item["stage"] == "complete_call")
        frozen = next(sample["payload"] for sample in frozen_stage["samples"]
                      if sample["preparation_backend"] == "native")
        count_rows = report["trusted_count_rows"]
        self.assertEqual(len(count_rows), 58)
        self.assertTrue(all(row["ordered_outcomes"] == 1980 for row in count_rows))

        result = solver.solve_native_flop_checkdown(
            spec["board"], fixture["oop_range"], fixture["ip_range"],
            count_build_directory=COUNT_BUILD, training_build_directory=TRAIN_BUILD,
            config=spec["config"], iterations=4000, algorithm="cfrplus")
        self.assertEqual(result["compatible_pairs"], 58)
        self.assertEqual(result["iterations"], 4000)
        self.assertEqual(result["physical_worlds"], 58 * 1980)
        _assert_cross_build_payload_equal(self, result, frozen)

        oracle = prepare_oracle_from_counts(
            spec["board"], fixture["oop_range"], fixture["ip_range"],
            spec["config"], count_rows)
        audited = replay(result, oracle, tolerance=1e-10)
        self.assertLessEqual(max(audited["scalar_absolute_gaps"].values()), 1e-10)
        self.assertLessEqual(audited["nash_conv"], 0.005)
        prep = result["equity_preparation"]
        self.assertEqual(prep["current_rank_calls"], 58 * 1980)
        self.assertEqual(prep["current_unordered_board_evaluations"], 58 * 990)
        self.assertEqual(prep["native_preparation"]["compatible_pairs"], 58)
        self.assertTrue(prep["source_inclusive_admission"])
        prepared = native_flop_equity.prepare_native_flop_checkdown_equities(
            spec["board"], fixture["oop_range"], fixture["ip_range"],
            build_directory=COUNT_BUILD)
        staged = solver.solve_prepared_flop_checkdown(
            prepared.equities, config=spec["config"], iterations=4000,
            algorithm="cfrplus", training_backend="native", build_directory=TRAIN_BUILD)
        cold_game, staged_game = dict(result), dict(staged)
        cold_game.pop("equity_preparation")
        staged_game.pop("equity_preparation")
        self.assertEqual(cold_game, staged_game)


if __name__ == "__main__":
    unittest.main()
