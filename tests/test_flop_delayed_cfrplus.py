"""Opt-in delayed averaging for flop-start alternating CFR+."""

import unittest
from unittest.mock import patch

from pokerlab import postflop_solver
from pokerlab.postflop_solver import solve_postflop
from pokerlab.river_config import RiverConfig
from scripts import flop_multistreet_validation as independent


BOARD = ("2c", "3d", "4h")
OOP = "AsAd:1,QsQd:0.5"
IP = "AsKh:0.25,KsKd:1"
OOP_HANDS = (("AsAd", "1"), ("QsQd", "1/2"))
IP_HANDS = (("AsKh", "1/4"), ("KsKd", "1"))
RUNOUTS = (("5c", "6c"), ("6c", "5c"))
CONFIG = {
    "pot": 10,
    "effective_stack": [12, 20],
    "bet_sizes": [0.5],
    "raise_sizes": [0.5],
    "max_raises": 1,
    "include_all_in": True,
}
ANCHOR_CONFIG = {
    "pot": 10,
    "effective_stack": 5,
    "bet_sizes": [0.5],
    "raise_sizes": [],
    "max_raises": 0,
    "include_all_in": False,
}


def _realization_rows(result):
    # Each visible history includes action keys and public-card reveals. For a
    # fixed own hand, multiply only that player's earlier action probabilities.
    # No production tree/value helpers, reach thresholds, or omitted rows.
    rows = {(row["player"], row["hand"], tuple(row["history"])): row
            for row in result["strategy"]}
    reaches = {}
    for key in rows:
        player, hand, history = key
        reach = 1.
        for length in range(len(history)):
            prior = rows.get((player, hand, history[:length]))
            if prior is not None:
                actions = [action for action in prior["actions"]
                           if action["history_key"] == history[length]]
                if len(actions) != 1:
                    raise AssertionError("Visible history has no unique prior own action")
                reach *= actions[0]["probability"]
        reaches[key] = reach
    return rows, reaches


def _assert_same_profiles(test, left, right):
    left_rows, left_reaches = _realization_rows(left)
    right_rows, right_reaches = _realization_rows(right)
    test.assertEqual(set(left_rows), set(right_rows))
    max_probability_gap = 0.
    for key, left_row in left_rows.items():
        right_row = right_rows[key]
        test.assertEqual(len(left_row["actions"]), len(right_row["actions"]))
        for left_action, right_action in zip(left_row["actions"], right_row["actions"]):
            for field in ("name", "amount", "raise_to", "history_key"):
                test.assertEqual(left_action[field], right_action[field], (key, field))
            lp, rp = left_action["probability"], right_action["probability"]
            max_probability_gap = max(max_probability_gap, abs(lp-rp))
            # Conditional rows can differ at zero/tiny own reach: retain the
            # raw discrepancy and compare EVERY action's realization weight.
            test.assertAlmostEqual(left_reaches[key]*lp, right_reaches[key]*rp,
                                   delta=1e-12, msg=f"realization at {key}")
    for metric in ("value_oop", "value_ip", "oop_best_response_value",
                   "ip_best_response_value", "oop_best_response_gain",
                   "ip_best_response_gain", "nash_conv", "exploitability"):
        test.assertAlmostEqual(left[metric], right[metric], delta=1e-10,
                               msg=metric)
    return max_probability_gap


class FlopDelayedCFRPlusTests(unittest.TestCase):
    def test_delay_validation_precedes_world_enumeration(self):
        invalid = (
            ({"averaging_delay": True}, "integer"),
            ({"averaging_delay": 1.0}, "integer"),
            ({"averaging_delay": -1}, "integer"),
            ({"averaging_delay": 10, "iterations": 10}, r"\[0, iterations\)"),
            ({"averaging_delay": 1, "algorithm": "vanilla"}, "requires the cfrplus"),
            ({"averaging_delay": 1, "algorithm": "dcfr"}, "requires the cfrplus"),
            ({"averaging_delay": 1, "board": "2c3d4h5s"}, "flop starts"),
            ({"averaging_delay": 1, "traversal": "planned"}, "requires recursive"),
        )
        with patch.object(postflop_solver, "_enumerate_worlds",
                          side_effect=AssertionError("enumeration started")):
            for overrides, message in invalid:
                options = {"iterations": 10, "algorithm": "cfrplus",
                           "traversal": "recursive", "averaging_delay": 1}
                options.update(overrides)
                board = options.pop("board", "".join(BOARD))
                with self.subTest(options=overrides):
                    with self.assertRaisesRegex(ValueError, message):
                        solve_postflop(board, OOP, IP, runouts=RUNOUTS, **options)

    def test_default_omitted_and_explicit_zero_keep_identical_payload(self):
        config = RiverConfig.from_dict(CONFIG)
        kwargs = dict(runouts=RUNOUTS, iterations=10, algorithm="cfrplus")
        omitted = solve_postflop("".join(BOARD), OOP, IP, config, **kwargs)
        explicit_zero = solve_postflop(
            "".join(BOARD), OOP, IP, config, averaging_delay=0, **kwargs)
        self.assertEqual(omitted, explicit_zero)
        self.assertNotIn("averaging_delay", omitted)
        self.assertEqual(omitted["average_schedule"], "linear-post-sweep-own-reach")

    def test_positive_delay_independent_replay_both_training_backends(self):
        oracle = independent.prepare_oracle(
            BOARD, OOP_HANDS, IP_HANDS, CONFIG, runouts=RUNOUTS)
        recursive = solve_postflop(
            "".join(BOARD), OOP, IP, RiverConfig.from_dict(CONFIG),
            runouts=RUNOUTS, iterations=10, algorithm="cfrplus",
            traversal="recursive", averaging_delay=2)
        public = solve_postflop(
            "".join(BOARD), OOP, IP, RiverConfig.from_dict(CONFIG),
            runouts=RUNOUTS, iterations=10, algorithm="cfrplus",
            traversal="public-batched", averaging_delay=2)

        self.assertEqual(recursive["worlds"], 6)
        self.assertEqual(public["worlds"], 6)
        for result in (recursive, public):
            self.assertEqual(result["averaging_delay"], 2)
            self.assertEqual(result["averaging_positive_sweeps"], 8)
            self.assertEqual(result["average_schedule"],
                             "delayed-linear-post-sweep-own-reach")
            self.assertEqual(result["update_schedule"], "alternating-oop-then-ip")
            self.assertEqual(result["training_passes_per_iteration"], 3)
            checked = independent.replay(result, oracle)
            self.assertEqual(checked["checked_physical_worlds"], 6)
            for metric, gap in checked["scalar_absolute_gaps"].items():
                self.assertLessEqual(gap, 1e-10, metric)
        self.assertEqual(recursive["execution_backend"], "recursive-python")
        self.assertEqual(public["cfrplus_kernel"],
                         "delayed-public-batched-cfrplus-python")
        max_probability_gap = _assert_same_profiles(self, recursive, public)
        self.assertGreaterEqual(max_probability_gap, 0.5)

    def test_delay_does_not_reduce_three_pass_admission(self):
        config = RiverConfig.from_dict(CONFIG)
        hands, worlds, _, _ = postflop_solver._enumerate_worlds(
            BOARD, OOP, IP, RUNOUTS, 10)
        root, _, _, visited, _ = postflop_solver._build_postflop_tree(
            BOARD, config, worlds=worlds)
        requested_work = len(worlds) * visited * 10 * 3
        self.assertGreater(requested_work, 0)
        from pokerlab import preflop_delayed_cfrplus
        class AdmittedTrainer(Exception):
            pass
        for traversal in ("recursive", "public-batched"):
            with self.subTest(traversal=traversal), patch.object(
                    postflop_solver, "train_plus", side_effect=AdmittedTrainer) as recursive, patch.object(
                    preflop_delayed_cfrplus, "train_delayed_public_cfrplus",
                    side_effect=AdmittedTrainer) as public:
                kwargs = dict(runouts=RUNOUTS, iterations=10, algorithm="cfrplus",
                              traversal=traversal, averaging_delay=9)
                with patch.object(postflop_solver, "_MAX_WORLD_NODE_WORK", requested_work-1):
                    with self.assertRaisesRegex(ValueError, "30 million"):
                        solve_postflop("".join(BOARD), OOP, IP, config, **kwargs)
                recursive.assert_not_called()
                public.assert_not_called()
                with patch.object(postflop_solver, "_MAX_WORLD_NODE_WORK", requested_work):
                    with self.assertRaises(AdmittedTrainer):
                        solve_postflop("".join(BOARD), OOP, IP, config, **kwargs)
                trainer = recursive if traversal == "recursive" else public
                trainer.assert_called_once()
                self.assertEqual(trainer.call_args.args[3], 10)
                delay_key = "delay" if traversal == "recursive" else "averaging_delay"
                self.assertEqual(trainer.call_args.kwargs[delay_key], 9)

    def test_full_deck_three_pair_positive_delay_regression(self):
        # Intentionally not part of the local focused command while the separate
        # frozen full-deck benchmark is timing. CI/lead validation can run it.
        oracle = independent.prepare_oracle(
            BOARD, OOP_HANDS, IP_HANDS, ANCHOR_CONFIG)
        config = RiverConfig.from_dict(ANCHOR_CONFIG)
        results = {
            traversal: solve_postflop(
                "".join(BOARD), OOP, IP, config, iterations=10,
                algorithm="cfrplus", traversal=traversal, averaging_delay=2)
            for traversal in ("recursive", "public-batched")
        }
        for traversal, result in results.items():
            self.assertEqual(result["worlds"], 5_940)
            self.assertEqual(result["averaging_delay"], 2)
            self.assertEqual(result["averaging_positive_sweeps"], 8)
            self.assertEqual(result["iterations"], 10)
            checked = independent.replay(result, oracle)
            self.assertEqual(checked["checked_physical_worlds"], 5_940)
            for metric, gap in checked["scalar_absolute_gaps"].items():
                self.assertLessEqual(gap, 1e-10, (traversal, metric))
        self.assertEqual(results["public-batched"]["cfrplus_kernel"],
                         "delayed-public-batched-cfrplus-python")
        _assert_same_profiles(self, results["recursive"], results["public-batched"])


if __name__ == "__main__":
    unittest.main()
