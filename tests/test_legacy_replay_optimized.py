"""Adversarial acceptance controls for legacy independent replay boundaries.

Synthetic trusted W/T/L counts test validation mechanics, not physical ranking
or solver quality. Policies and their scalar values are written by hand.
"""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts import flop_checkdown_validation as flop
from scripts import preflop_monetary_validation as monetary
from scripts import preflop_push_fold_validation as push


def _must_reject(call, label):
    try:
        call()
    except AssertionError:
        return
    raise RuntimeError(f"Malformed legacy evidence was accepted: {label}")


def _action(name, amount=0.0, target=0.0, probability=1.0):
    token = name if name != "all_in" else "all_in@2"
    return {"name": name, "amount": amount, "raise_to": target,
            "history_key": token, "probability": probability}


def run_adversarial_controls():
    config = {"pot": 10, "effective_stack": 5, "bet_sizes": [],
              "raise_sizes": [], "max_raises": 0, "include_all_in": False}
    counts = [{"oop_hand": "AdAs", "ip_hand": "KdKs", "wins": 0,
               "ties": 1980, "losses": 0, "ordered_outcomes": 1980}]
    prepared = flop.prepare_oracle_from_counts(
        "2c3d4h", "AsAd", "KsKd", config, counts)
    pair = {**counts[0], "pair_probability": 1.0}
    flop_result = {
        "strategy": [
            {"player": "oop", "hand": "AdAs", "street": "flop",
             "board": ["2c", "3d", "4h"], "history": [],
             "actions": [_action("check")]},
            {"player": "ip", "hand": "KdKs", "street": "flop",
             "board": ["2c", "3d", "4h"], "history": ["check"],
             "actions": [_action("check")]},
        ],
        "info_sets": 2, "public_nodes": 2, "public_states": 3,
        "physical_worlds": 1980, "pair_equities": [pair],
        **{key: 0.0 for key in ("value_oop", "value_ip",
                               "oop_best_response_value", "ip_best_response_value",
                               "nash_conv", "exploitability")},
    }
    flop.replay(flop_result, prepared)
    malformed_flop = []
    for kind in ("board", "money", "probability", "duplicate", "missing",
                 "count", "metric"):
        bad = deepcopy(flop_result)
        if kind == "board":
            bad["strategy"][0]["board"] = ["2c", "3d", "4h", "5c"]
        elif kind == "money":
            bad["strategy"][0]["actions"][0]["amount"] = 1.0
        elif kind == "probability":
            bad["strategy"][0]["actions"][0]["probability"] = float("nan")
        elif kind == "duplicate":
            bad["strategy"].append(deepcopy(bad["strategy"][0]))
        elif kind == "missing":
            bad["strategy"].pop()
        elif kind == "count":
            bad["pair_equities"][0]["wins"] = 1
        else:
            bad["value_oop"] = 1.0
        malformed_flop.append((kind, bad))
    for kind, bad in malformed_flop:
        _must_reject(lambda: flop.replay(bad, prepared), "flop:" + kind)

    push_config = {"small_blind": 0.5, "big_blind": 1.0,
                   "starting_stack": 2.0}
    push_counts = [{"sb_hand": "AdAs", "bb_hand": "KdKs", "wins": 0,
                    "ties": push.BOARDS, "losses": 0, "boards": push.BOARDS}]
    push_result = {
        "solver_version": "preflop-push-fold-v1",
        "strategy_schema": "preflop-strategy-v1",
        "runout_mode": "full-deck-unordered-final-boards",
        "config": push_config,
        "compatible_pairs": 1, "physical_boards": push.BOARDS, "info_sets": 2,
        "pair_equities": [{**push_counts[0], "pair_probability": 1.0}],
        "strategy": [
            {"player": "sb", "hand": "AdAs", "street": "preflop",
             "revealed_board": [], "history": [],
             "actions": [_action("fold"), _action("all_in", 1.5, 2.0, 0.0)]},
            {"player": "bb", "hand": "KdKs", "street": "preflop",
             "revealed_board": [], "history": ["all_in@2"],
             "actions": [_action("fold"), _action("call", 1.0, 2.0, 0.0)]},
        ],
        "value_sb": -0.5, "value_bb": 0.5,
        "sb_best_response_value": 1.0, "bb_best_response_value": 0.5,
        "nash_conv": 1.5, "exploitability": 0.75,
        "sb_best_response_gain": 1.5, "bb_best_response_gain": 0.0,
    }
    push.replay(push_result, "AsAd", "KsKd", push_config, push_counts)
    malformed_push = []
    for kind in ("scope", "board", "money", "probability", "duplicate",
                 "missing", "count", "metric"):
        bad = deepcopy(push_result)
        if kind == "scope":
            bad["runout_mode"] = "selected-boards"
        elif kind == "board":
            bad["strategy"][0]["revealed_board"] = ["Ac"]
        elif kind == "money":
            bad["strategy"][0]["actions"][1]["amount"] = 2.0
        elif kind == "probability":
            bad["strategy"][0]["actions"][0]["probability"] = float("nan")
        elif kind == "duplicate":
            bad["strategy"].append(deepcopy(bad["strategy"][0]))
        elif kind == "missing":
            bad["strategy"].pop()
        elif kind == "count":
            bad["pair_equities"][0]["wins"] = 1
        else:
            bad["value_sb"] = float("nan")
        malformed_push.append((kind, bad))
    for kind, bad in malformed_push:
        _must_reject(lambda: push.replay(bad, "AsAd", "KsKd", push_config,
                                        push_counts), "push:" + kind)
    _must_reject(lambda: push.weighted_equilibrium_certificate(push_result, ()),
                 "push:wrong-certificate-support")
    anchor = monetary.midpoint_anchor()
    if anchor["configured_whole_hand_target"] != 1.293095146:
        raise RuntimeError("Configured monetary midpoint anchor changed")
    with patch.object(monetary, "Fraction", return_value=Fraction(0)):
        _must_reject(monetary.midpoint_anchor, "monetary:corrupted-reference")
    return {"valid_synthetic_payloads": 2, "rejected_payloads": 17,
            "configured_midpoint_target": anchor["configured_whole_hand_target"]}


class LegacyReplayOptimizedTests(unittest.TestCase):
    def test_malformed_evidence_rejects_in_normal_and_optimized_subprocesses(self):
        root = Path(__file__).resolve().parents[1]
        code = ("import json; from tests.test_legacy_replay_optimized import "
                "run_adversarial_controls; print(json.dumps(run_adversarial_controls()))")
        for flags in ([], ["-O"]):
            with self.subTest(flags=flags):
                result = subprocess.run([sys.executable, "-B", *flags, "-c", code],
                                        cwd=root, capture_output=True, text=True,
                                        timeout=60, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout), {
                    "valid_synthetic_payloads": 2, "rejected_payloads": 17,
                    "configured_midpoint_target": 1.293095146})


if __name__ == "__main__":
    unittest.main()
