import json
import math
import os
from pathlib import Path
import random
import subprocess
import unittest
from fractions import Fraction
from unittest.mock import patch

from pokerlab.cards import DECK, rank_hand
from pokerlab.native_selected_operator import _rank_code, prepare, wire, executable_identity
from pokerlab.preflop_solver import _positive_pot_training_view
from pokerlab.selected_operator_solver import _prepare, solve_four_street_operator
from scripts.preflop_validation import replay_policy, compare_result
from scripts.four_street_certificate_v3 import evaluate_exact
from tests.test_selected_operator_solver import CASE, request


EXECUTABLE = os.environ.get("OPENPOKER_NATIVE_SELECTED_EXE")


def fixture():
    return json.loads((Path(__file__).resolve().parents[1] / "benchmarks/four-street-integration-v1.json").read_text())["case"]


def prepared(case=CASE):
    req = request(case)
    operator, root, infos, *_ = _prepare(req, strategy_storage="packed")
    view, anchor, _ = _positive_pot_training_view(root)
    operator.pot = 2 * anchor
    return req, operator, view, infos


class NativeSelectedAdmissionTests(unittest.TestCase):
    def test_rank_code_preserves_existing_tuple_order(self):
        generator = random.Random(15947)
        ranks = [rank_hand(tuple(generator.sample(DECK, 7))) for _ in range(500)]
        self.assertEqual(sorted(ranks), sorted(ranks, key=_rank_code))
        for rank in ranks:
            self.assertGreater(_rank_code(rank), 0)
            self.assertLess(_rank_code(rank), 1 << 24)

    def test_rank_free_complete_request_admission(self):
        req, operator, root, infos = prepared(fixture())
        with patch("pokerlab.selected_runout_operator.rank_hand", side_effect=AssertionError("ranking")):
            receipt = prepare(root, infos, req.iterations, operator=operator)[-1]
        self.assertEqual(receipt["stored_worlds"], 0)
        self.assertEqual(receipt["stored_prefix_pair_edges"], 0)
        self.assertEqual(receipt["retained_rank_entries"], 24)
        self.assertEqual(receipt["prefix_marginal_cache_entries"], 4)

    def test_native_limits_reject_before_ranking_or_spawn(self):
        req, operator, root, infos = prepared()
        with patch("pokerlab.selected_runout_operator.rank_hand", side_effect=AssertionError("ranking")), \
             patch("pokerlab.native_selected_operator.subprocess.run", side_effect=AssertionError("spawn")):
            with patch("pokerlab.native_selected_operator.MAX_WORK", 1):
                with self.assertRaisesRegex(ValueError, "work/heap"):
                    wire(root, infos, req.iterations, operator=operator)
            with patch("pokerlab.native_selected_operator.MAX_RANK_ENTRIES", 1):
                with self.assertRaisesRegex(ValueError, "rank-vector"):
                    wire(root, infos, req.iterations, operator=operator)

    def test_unsupported_selection_rejects_before_operator_or_binary_access(self):
        with patch("pokerlab.selected_operator_solver.SelectedRunoutOperator", side_effect=AssertionError("operator")):
            with self.assertRaisesRegex(ValueError, "explicit packed"):
                solve_four_street_operator(request(CASE), native_executable="never-read")

    def test_wire_is_private_hands_boards_and_tree_not_pair_worlds(self):
        req, operator, root, infos = prepared(fixture())
        with patch("pokerlab.preflop_solver._enumerate_physical_worlds", side_effect=AssertionError("worlds")), \
             patch("pokerlab.public_cfr._aggregate_prefixes", side_effect=AssertionError("edges")):
            data, keys, receipt = wire(root, infos, req.iterations, operator=operator)
        self.assertLess(len(data), 300_000)
        self.assertEqual(len(keys), 1200)
        self.assertEqual(receipt["action_slots"], 2402)
        self.assertEqual(operator.rank_calls, 23)


@unittest.skipUnless(EXECUTABLE, "Build and set OPENPOKER_NATIVE_SELECTED_EXE for compiled controls")
class NativeSelectedCompiledTests(unittest.TestCase):
    def check_case(self, case):
        req = request(case)
        reference = solve_four_street_operator(req, strategy_storage="packed", rank_cache_boards=64)
        with patch("pokerlab.packed_operator_cfr.train_packed", side_effect=AssertionError("Python training")), \
             patch("pokerlab.preflop_solver._enumerate_physical_worlds", side_effect=AssertionError("worlds")):
            actual = solve_four_street_operator(req, strategy_storage="packed", native_executable=EXECUTABLE)
        self.assertEqual(actual["strategy"], reference["strategy"])
        for field in ("worlds", "info_sets", "value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value", "nash_conv"):
            self.assertEqual(actual[field], reference[field], field)
        oracle = replay_policy(actual, req.sb_range, req.bb_range, config=case["config"], runouts=case["runouts"],
                               flop_config=case["flop_config"], turn_config=case.get("turn_config"), river_config=case.get("river_config"))
        compare_result(actual, oracle)
        return actual

    def test_same_twenty_two_world_four_street_policy(self):
        actual = self.check_case(fixture())
        self.assertEqual(actual["native_training"]["calls"], 1)
        self.assertEqual(actual["native_training"]["stored_prefix_pair_edges"], 0)

    def test_weighted_blockers_shared_futures_and_index_holes(self):
        self.check_case(dict(CASE, sb_range="AsAd:1,AhAc:0.25,2c3c:0.5"))

    def test_short_all_in_tie_and_refund(self):
        self.check_case(dict(CASE, config={"starting_stack": [2.5, 2], "raise_sizes": [0.5],
                                         "max_raises": 1, "include_all_in": True},
                             runouts=["TcJcQcKcAc", "2c3c4d7h8h"]))

    def test_fractional_blinds_and_local_monetary_quantization(self):
        case = dict(CASE, sb_range="AsAd", bb_range="KsKd",
                    config={"small_blind": 0.123456789, "big_blind": 0.345678901,
                            "starting_stack": [2, 1.5], "raise_sizes": [0.5],
                            "max_raises": 1, "include_all_in": False},
                    runouts=["2c3c4d7h8h", "Kc2d3h7s8c"],
                    flop_config={"bet_sizes": [0.123456781], "raise_sizes": [],
                                 "max_raises": 0, "include_all_in": False})
        self.check_case(case)

    def test_no_information_sets_requires_identity_but_no_native_training(self):
        result = self.check_case(dict(CASE, config={"starting_stack": [0.5, 1]}))
        self.assertEqual(result["native_training"]["calls"], 0)

    def test_independent_exact_short_all_in_certificate(self):
        case = dict(CASE, id="native-selected-exact-control", config={"starting_stack": [1, 2]},
                    turn_config=CASE["flop_config"], river_config=CASE["flop_config"])
        actual = self.check_case(case)
        reference = solve_four_street_operator(request(case), strategy_storage="packed")
        self.assertEqual(evaluate_exact(case, actual)["metrics"], evaluate_exact(case, reference)["metrics"])

    def test_manifest_identity_and_malformed_protocol_reject(self):
        self.assertEqual(executable_identity(EXECUTABLE)["protocol"], "OPENPOKER_SELECTED_OPERATOR_V1")
        process = subprocess.run([EXECUTABLE], input=b"WRONG\n", capture_output=True, timeout=10)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn(b"protocol", process.stderr)

    def test_exact_normalizer_midpoints_and_seeded_positive_masses(self):
        denominator = 34246080
        cases = [
            [denominator * 2.0**-26, denominator * 2.0**-79],
            [denominator * 2.0**-26, denominator * 2.0**-79, denominator * 2.0**-79],
            [denominator * 2.0**-51, denominator * 2.0**-51],
        ]
        generator = random.Random(77162)
        cases += [[2.0**-generator.randint(0, 450) for _ in range(3)] for _ in range(12)]
        names = ["AsAd", "QsQd", "JsJd"]
        for weights in cases:
            case = dict(CASE, sb_range=",".join(f"{h}:{w!r}" for h, w in zip(names, weights)),
                        bb_range="KsKd", config={"starting_stack": [0.5, 1]},
                        runouts=["2c3c4d7h8h"])
            req, operator, root, infos = prepared(case)
            # All named private cards and this board are disjoint. Compare the
            # rounded raw binary64 masses with a separate exact integer ratio.
            exact = sum((Fraction.from_float(w / denominator) for w in weights), Fraction())
            self.assertEqual(operator.normalizer, float(exact))
            data, _, _ = wire(root, infos, req.iterations, operator=operator)
            process = subprocess.run([EXECUTABLE], input=data, capture_output=True, timeout=10)
            self.assertEqual(process.returncode, 0, process.stderr.decode(errors="replace"))
        self.assertEqual(float(sum((Fraction.from_float(w / denominator) for w in cases[0]), Fraction())), 2.0**-26)
        self.assertEqual(float(sum((Fraction.from_float(w / denominator) for w in cases[1]), Fraction())), math.nextafter(2.0**-26, math.inf))

    def test_tampered_native_census_support_normalizer_and_topology_reject(self):
        req, operator, root, infos = prepared()
        raw, _, _ = wire(root, infos, req.iterations, operator=operator)
        lines = raw.decode().splitlines()
        variants = []
        changed = lines.copy()
        header = changed[1].split()
        header[11] = str(int(header[11]) + 1)
        changed[1] = " ".join(header)
        variants.append(changed)
        changed = lines.copy(); changed[2] = "0x1.0p+0"; variants.append(changed)
        changed = lines.copy(); changed[2] = math.nextafter(float.fromhex(changed[2]), math.inf).hex(); variants.append(changed)
        # The first hand must contain exactly two distinct cards.
        changed = lines.copy(); changed[3] = "1 0x1.0p+0"; variants.append(changed)
        changed = lines.copy()
        last = changed[-1].split(); last[0] = "-1"; changed[-1] = " ".join(last); variants.append(changed)
        changed = lines.copy()
        last = changed[-1].split(); last[1] = last[0]; changed[-1] = " ".join(last); variants.append(changed)
        variants.append(lines + ["unexpected"])
        for changed in variants:
            process = subprocess.run([EXECUTABLE], input=("\n".join(changed)+"\n").encode(),
                                     capture_output=True, timeout=10)
            self.assertNotEqual(process.returncode, 0)

    def test_native_failure_never_retries_python_training(self):
        with patch("pokerlab.native_selected_operator.subprocess.run", return_value=subprocess.CompletedProcess([], 2, b"", b"intentional failure")), \
             patch("pokerlab.packed_operator_cfr.train_packed", side_effect=AssertionError("fallback")):
            with self.assertRaisesRegex(RuntimeError, "intentional failure"):
                solve_four_street_operator(request(CASE), strategy_storage="packed", native_executable=EXECUTABLE)


if __name__ == "__main__":
    unittest.main()
