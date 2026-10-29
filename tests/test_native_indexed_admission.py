"""Executed-path admission, cross-version policy parity and protected replay."""
from contextlib import ExitStack
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pokerlab import exact_selected_solver as solver
from pokerlab import native_exact_four_street as native
from scripts import build_native_exact_four_street as builder
from scripts.benchmark_equivariant_selected_solver import METRICS
from scripts.benchmark_suit_quotient_solver import case_for, request_for, _protected_verification

OPTIONS = dict(rank_cache_boards=64, pair_diagnostics="compact", exact_arithmetic="dyadic",
    training_reduction="suit-equivariant", strategy_storage="suit-quotient", quotient_lookup="per-decision")


class IndexedHostAdmissionTests(unittest.TestCase):
    def test_modes_reject_before_source_or_preparation(self):
        request = request_for(case_for("original-22-t10"), 10)
        with patch.object(solver, "_prepare_exact_selected", side_effect=AssertionError("prepare")), \
                patch.object(native, "executable_identity", side_effect=AssertionError("source")):
            for value in (None, True, 1, "indexed", "unknown"):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "admission model"):
                    solver.solve_four_street_exact_selected(request, native_admission=value, **OPTIONS)
            for executable, route in ((None, "indexed"), ("missing", "shadow"), ("missing", "full-history")):
                with self.subTest(route=route), self.assertRaisesRegex(ValueError, "explicit native indexed"):
                    solver.solve_four_street_exact_selected(request, native_executable=executable,
                        native_routing=route, native_admission="indexed-v1", **OPTIONS)

    def test_host_census_excludes_only_unexecuted_python_training(self):
        request = request_for(case_for("original-22-t10"), 100)
        old = solver._prepare_exact_selected(request, **OPTIONS)
        with self.assertRaisesRegex(ValueError, "Suit row plan"):
            native.admit(old)
        with ExitStack() as stack:
            for target in ("pokerlab.exact_selected_kernel.rank_hand",
                    "pokerlab.suit_quotient_plan.plan_admission",
                    "pokerlab.suit_quotient_plan.SuitQuotientPlan.__init__",
                    "pokerlab.equivariant_packed_cfr.equivariant_additional_census",
                    "pokerlab.suit_quotient_cfr.train_suit_quotient",
                    "pokerlab.equivariant_packed_cfr.train_equivariant_packed",
                    "pokerlab.native_exact_four_street._invoke"):
                stack.enter_context(patch(target, side_effect=AssertionError(target)))
            new = solver._prepare_exact_selected(request, execution_profile="native-indexed-v1", **OPTIONS)
            reservation = native.admit(new)
        self.assertEqual(old.kernel.hands, new.kernel.hands)
        self.assertEqual(old.kernel.weights, new.kernel.weights)
        self.assertEqual(old.kernel.normalizer, new.kernel.normalizer)
        self.assertEqual(old.topology, new.topology)
        self.assertEqual(new.admission["kernel"]["terminal_calls_upper"], 6 * sum(new.terminal_counts.values()))
        self.assertEqual(new.admission["kernel"]["marginal_calls_upper"], 3 * sum(new.action_hand_queries.values()))
        self.assertEqual(new.layout_upper["python_training_iterations"], 0)
        self.assertEqual(new.admission["combined_modeled_work_upper"] + reservation["native_work_limit"], 500_000_000)
        self.assertLessEqual(reservation["native_entries_limit"], 2_000_000)
        self.assertEqual(native.wire(new, 100, routing="indexed", native_work=reservation["native_work_limit"],
            native_entries=reservation["native_entries_limit"]).splitlines()[0].decode(), native.INDEXED_PROTOCOL)
        with self.assertRaisesRegex(ValueError, "reserved host remainder"):
            native.wire(new, 100, routing="indexed")
        with patch.object(native, "executable_identity", side_effect=AssertionError("source")):
            with self.assertRaisesRegex(ValueError, "reserved host remainder"):
                native.train(new, executable="missing", routing="indexed")
        with self.assertRaisesRegex(ValueError, "another|legacy or shadow"):
            native.wire(new, 100, routing="shadow")
        with self.assertRaisesRegex(ValueError, "already reserved"):
            native.admit(new)


class IndexedAdmissionCompiledTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = TemporaryDirectory(prefix="opl-indexed-admission-")
        supplied = os.environ.get("OPENPOKER_NATIVE_EXACT_FOUR_STREET_EXE")
        if supplied:
            cls.executable = Path(supplied).resolve(strict=True)
        else:
            if shutil.which("cl" if os.name == "nt" else "c++") is None:
                cls.temporary.cleanup()
                raise unittest.SkipTest("no C++20 compiler or selected exact engine")
            cls.executable = Path(builder.build(cls.temporary.name, target="engine")["executable"])
        native.executable_identity(cls.executable)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def solve(self, case, iterations=10, model="indexed-v1"):
        return solver.solve_four_street_exact_selected(request_for(case, iterations), native_executable=self.executable,
            native_routing="indexed", native_admission=model, **OPTIONS)

    def test_five_complete_games_preserve_policy_metric_bits_and_independent_certificates(self):
        for name in ("payoff-varied-t10", "blocker-18", "asymmetric-weighted", "mixed-stabilizer", "original-22-t10"):
            with self.subTest(case=name):
                case = case_for(name)
                old = self.solve(case, model="legacy")
                with patch("pokerlab.suit_quotient_cfr.train_suit_quotient", side_effect=AssertionError("Python Q")), \
                        patch("pokerlab.equivariant_packed_cfr.train_equivariant_packed", side_effect=AssertionError("Python CFR")), \
                        patch("pokerlab.suit_quotient_plan.SuitQuotientPlan.__init__", side_effect=AssertionError("Python plan")):
                    new = self.solve(case)
                self.assertEqual(old["strategy"], new["strategy"])
                self.assertEqual([old[k].hex() for k in METRICS], [new[k].hex() for k in METRICS])
                self.assertTrue(_protected_verification(case, new)["payload_metrics_within_tolerance"])
                owner = new["operator_census"]["whole_request_admission"]
                self.assertLessEqual(owner["combined_modeled_work_upper"], owner["whole_request_limit"])
                self.assertEqual(new["training_backend"], "native-exact-four-street-indexed-admission-v3")
                proof = new["operator_census"]["native_exact"]["indexed_admission"]
                self.assertEqual(proof["marginal_reuse"], 1)
                self.assertLessEqual(proof["marginal_calls_actual"], proof["marginal_calls_upper"])

    def test_real_t1000_callback_limit_still_rejects_without_python_fallback(self):
        with patch("pokerlab.suit_quotient_cfr.train_suit_quotient", side_effect=AssertionError("fallback")), \
                patch("pokerlab.equivariant_packed_cfr.train_equivariant_packed", side_effect=AssertionError("fallback")):
            with self.assertRaisesRegex(native.NativeFailure, "callback-work|modeled-work|modeled work"):
                self.solve(case_for("original-22-qreject"), 1000)

    def test_blind_all_in_counts_terminal_support_without_decision_marginals(self):
        case = dict(case_for("payoff-varied-t10"), config={"starting_stack": [0.5, 1.0]})
        expected = solver.solve_four_street_exact_selected(request_for(case, 10), **OPTIONS)
        result = self.solve(case)
        self.assertEqual(result["strategy"], [])
        self.assertEqual(result["info_sets"], 0)
        self.assertEqual([expected[k].hex() for k in METRICS], [result[k].hex() for k in METRICS])
        proof = result["operator_census"]["native_exact"]["indexed_admission"]
        self.assertEqual(proof["marginal_calls_upper"], 1)
        self.assertEqual(proof["marginal_calls_actual"], 0)
        self.assertTrue(_protected_verification(case, result)["payload_metrics_within_tolerance"])

    def test_twenty_sweeps_preserve_reference_policy_beyond_legacy_native_admission(self):
        case = case_for("original-22-t10")
        with self.assertRaises(ValueError):
            self.solve(case, 20, model="legacy")
        expected = solver.solve_four_street_exact_selected(request_for(case, 20), **OPTIONS)
        result = self.solve(case, 20)
        self.assertEqual(expected["strategy"], result["strategy"])
        self.assertEqual([expected[k].hex() for k in METRICS], [result[k].hex() for k in METRICS])
        self.assertTrue(_protected_verification(case, result)["payload_metrics_within_tolerance"])

    def test_admission_proof_cannot_be_omitted_forged_or_crossed_with_v2(self):
        prepared = solver._prepare_exact_selected(request_for(case_for("payoff-varied-t10"), 10),
            execution_profile="native-indexed-v1", **OPTIONS)
        reservation = native.admit(prepared)
        request = native.wire(prepared, 10, native_work=reservation["native_work_limit"],
            native_entries=reservation["native_entries_limit"], routing="indexed")
        raw = native._invoke(str(self.executable), request)
        native.parse_policy(raw, prepared, routing="indexed")
        lines = raw.splitlines()
        invalid = [b"\n".join(lines[:-1]) + b"\n", raw.replace(native.INDEXED_RESULT.encode(), native.ROUTED_RESULT.encode(), 1)]
        for field in native.ADMISSION_FIELDS:
            cells = lines[-1].split(b"\t")
            for i, cell in enumerate(cells):
                if cell.startswith(field.encode() + b"="):
                    cells[i] = field.encode() + b"=" + str(int(cell.split(b"=")[1]) + 1).encode()
            invalid.append(b"\n".join([*lines[:-1], b"\t".join(cells)]) + b"\n")
        for bad in invalid:
            with self.subTest(tail=bad[-200:]), self.assertRaises(ValueError):
                native.parse_policy(bad, prepared, routing="indexed")


if __name__ == "__main__":
    unittest.main()
