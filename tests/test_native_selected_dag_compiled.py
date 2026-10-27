"""Compiled native DAG equivalence and physical replay controls."""
import json
import math
import os
from pathlib import Path
import random
import subprocess
import unittest
from fractions import Fraction
from unittest.mock import patch
from pokerlab.native_selected_dag import prepare, wire, executable_identity
from pokerlab.selected_operator_solver import solve_four_street_operator
from scripts.preflop_validation import replay_policy, compare_result
from scripts.four_street_certificate_v3 import evaluate_exact
from tests.test_selected_operator_solver import CASE, request
from tests.test_native_selected_dag import direct_prepared

EXECUTABLE = os.environ.get("OPENPOKER_NATIVE_SELECTED_DAG_EXE")
def fixture():
    return json.loads((Path(__file__).resolve().parents[1] / "benchmarks/four-street-integration-v1.json").read_text())["case"]

@unittest.skipUnless(EXECUTABLE, "Build and set OPENPOKER_NATIVE_SELECTED_EXE for compiled controls")
class NativeSelectedDagCompiledTests(unittest.TestCase):
    def check_case(self, case):
        req = request(case)
        reference = solve_four_street_operator(req, strategy_storage="packed", rank_cache_boards=64)
        with patch("pokerlab.packed_operator_cfr.train_packed", side_effect=AssertionError("Python training")), \
             patch("pokerlab.preflop_solver._enumerate_physical_worlds", side_effect=AssertionError("worlds")):
            actual = solve_four_street_operator(req, strategy_storage="packed", native_executable=EXECUTABLE, public_topology="direct")
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
        self.assertEqual(actual["native_training"]["vertices"] < actual["public_states"], True)

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
        self.assertEqual(executable_identity(EXECUTABLE)["protocol"], "OPENPOKER_SELECTED_DAG_V1")
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
            req, operator, view, infos = direct_prepared(case)
            # All named private cards and this board are disjoint. Compare the
            # rounded raw binary64 masses with a separate exact integer ratio.
            exact = sum((Fraction.from_float(w / denominator) for w in weights), Fraction())
            self.assertEqual(operator.normalizer, float(exact))
            plan, _ = prepare(view, infos, req.iterations, operator)
            data, _, _ = wire(plan)
            process = subprocess.run([EXECUTABLE], input=data, capture_output=True, timeout=10)
            self.assertEqual(process.returncode, 0, process.stderr.decode(errors="replace"))
        self.assertEqual(float(sum((Fraction.from_float(w / denominator) for w in cases[0]), Fraction())), 2.0**-26)
        self.assertEqual(float(sum((Fraction.from_float(w / denominator) for w in cases[1]), Fraction())), math.nextafter(2.0**-26, math.inf))


    def test_malformed_declared_and_recomputed_dag_reject_before_training(self):
        req, operator, view, infos = direct_prepared()
        plan, _ = prepare(view, infos, req.iterations, operator)
        payload, _, _ = wire(plan)
        lines = payload.decode().splitlines()
        header = list(map(int, lines[1].split()))
        node_start = 3 + header[6] + header[7] + 2 * header[8]
        edge_start = node_start + header[0]
        variants = []
        for field in (2, 3, 4, 5, 9, 13, 14, 15, 16, 17, 18, 19, 20):
            modified = lines.copy()
            fields = header.copy(); fields[field] += 1
            modified[1] = " ".join(map(str, fields)); variants.append(modified)
        for normalizer in ("0x1p+0", math.nextafter(operator.normalizer, math.inf).hex(), "0x1p-1074"):
            modified = lines.copy(); modified[2] = normalizer; variants.append(modified)
        modified = lines.copy(); modified[3] = "1 0x1p+0"; variants.append(modified)
        # A strict postorder violation must reject, as must a valid reveal partition in wrong order.
        for vertex_id in range(header[0]):
            node = lines[node_start + vertex_id].split()
            kind, first, count = int(node[0]), int(node[2]), int(node[3])
            if count:
                modified = lines.copy()
                edge = modified[edge_start + first].split(); edge[0] = str(vertex_id)
                modified[edge_start + first] = " ".join(edge); variants.append(modified)
                break
        for vertex_id in range(header[0]):
            node = lines[node_start + vertex_id].split()
            if int(node[0]) == 2 and int(node[3]) >= 2:
                first = edge_start + int(node[2])
                modified = lines.copy(); modified[first], modified[first+1] = modified[first+1], modified[first]
                variants.append(modified)
                modified = lines.copy(); modified[first+1] = modified[first]; variants.append(modified)
                modified = lines.copy(); fields = modified[node_start+vertex_id].split()
                fields[4] = str(1 + int(fields[4]) % 3)
                modified[node_start+vertex_id] = " ".join(fields); variants.append(modified)
                break
        else:
            self.fail("fixture needs a multi-branch chance")
        variants.append(lines + ["unexpected"])
        for index, modified in enumerate(variants):
            with self.subTest(index=index):
                result = subprocess.run([EXECUTABLE], input=("\n".join(modified)+"\n").encode(), capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0, result.stdout[:100])
                self.assertEqual(result.stdout, b"")

    def test_reused_context_native_rows_remain_separate(self):
        req, operator, view, infos = direct_prepared(dict(CASE, sb_range="AsAd", bb_range="KsKd",
            config={"starting_stack": [.5, 1]}, runouts=["2c3c4d7h8h"]))
        plan, _ = prepare(view, infos, req.iterations, operator)
        data, _, _ = wire(plan)
        lines = data.decode().splitlines()
        # A root with two histories reaching the same opponent decision context.
        lines[1] = "3 4 3 4 3 6 1 1 1 4 10 1 2 7 3 4 3 6 6 0 6"
        lines = lines[:7] + ["0 -1 0 0 0 0 0x1p+0", "1 1 0 2 0 -1 0x0.0p+0",
            "1 0 2 2 0 -1 0x0.0p+0", "0 0", "0 0", "1 0", "1 0"]
        result = subprocess.run([EXECUTABLE], input=("\n".join(lines)+"\n").encode(), capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        tokens = result.stdout.decode().split()
        self.assertEqual(int(tokens[1]), 6)
        self.assertEqual([float.fromhex(x) for x in tokens[5:-2]], [.5]*6)

    def test_native_failure_never_retries_python_training(self):
        with patch("pokerlab.native_selected_dag.subprocess.run", return_value=subprocess.CompletedProcess([], 2, b"", b"intentional failure")), \
             patch("pokerlab.packed_operator_cfr.train_packed", side_effect=AssertionError("fallback")):
            with self.assertRaisesRegex(RuntimeError, "intentional failure"):
                solve_four_street_operator(request(CASE), strategy_storage="packed",
                    public_topology="direct", native_executable=EXECUTABLE)
