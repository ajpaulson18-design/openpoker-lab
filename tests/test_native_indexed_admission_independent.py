"""Independent boundaries for the opt-in native indexed admission contract."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from pokerlab import exact_selected_solver as solver
from pokerlab import native_exact_four_street as native
from pokerlab.exact_selected_float_adapter import ExactSelectedFloatAdapter
from scripts.benchmark_suit_quotient_solver import case_for, request_for

OPTIONS = dict(rank_cache_boards=64, pair_diagnostics="compact", exact_arithmetic="dyadic",
    training_reduction="suit-equivariant", strategy_storage="suit-quotient", quotient_lookup="per-decision")

class IndexedAdmissionIndependentTests(unittest.TestCase):
    def request(self):
        return request_for(case_for("payoff-varied-t10"), 10)

    def test_reduced_budget_rejects_before_group_search_or_native_invoke(self):
        prepared = solver._prepare_exact_selected(self.request(), execution_profile="native-indexed-v1", **OPTIONS)
        initial = prepared.admission["combined_modeled_work_upper"]
        prepared.admission["whole_request_limit"] = initial + 1
        with patch("pokerlab.suit_quotient_plan._group", side_effect=AssertionError("group entered")), \
             patch.object(native, "_invoke", side_effect=AssertionError("native entered")):
            with self.assertRaisesRegex(ValueError, "host group/I/O admission"):
                native.admit(prepared)
        self.assertEqual(prepared.admission["combined_modeled_work_upper"], initial)
        self.assertNotIn("native_additional_admission", prepared.admission)

    def test_native_allowance_transferred_to_every_v3_work_field(self):
        prepared = solver._prepare_exact_selected(self.request(), execution_profile="native-indexed-v1", **OPTIONS)
        receipt = native.admit(prepared)
        remaining = prepared.admission["whole_request_limit"] - prepared.admission["combined_modeled_work_upper"]
        remaining_entries = prepared.admission["retained_storage"]["entry_limit"] - prepared.admission["retained_storage"]["whole_request_peak_upper"]
        self.assertEqual(receipt["native_work_limit"], remaining)
        self.assertEqual(receipt["native_entries_limit"], min(remaining_entries, 2_000_000))
        wire = native.wire(prepared, 10, rank_cache_boards=64, routing="indexed", native_work=remaining,
                           native_entries=receipt["native_entries_limit"])
        lines = wire.decode("ascii").splitlines()
        self.assertEqual(lines[0], native.INDEXED_PROTOCOL)
        limits = list(map(int, lines[2].split()))
        self.assertEqual([limits[i] for i in (1, 4, 7)], [remaining] * 3)
        self.assertEqual([limits[i] for i in (2, 5, 8)], [receipt["native_entries_limit"]] * 3)
        with self.assertRaises(ValueError):
            native.wire(prepared, 10, routing="indexed", native_work=0)
        with self.assertRaises(ValueError):
            native.wire(prepared, 10, routing="shadow", native_work=remaining)

    def test_direct_v3_transport_requires_the_original_host_reservation(self):
        prepared = solver._prepare_exact_selected(self.request(), execution_profile="native-indexed-v1", **OPTIONS)
        with patch.object(native, "executable_identity", side_effect=AssertionError("source accessed")), \
             patch.object(native, "_invoke", side_effect=AssertionError("native entered")):
            with self.assertRaisesRegex(ValueError, "reserved host remainder"):
                native.train(prepared, executable="unused", routing="indexed")
        with self.assertRaisesRegex(ValueError, "reserved host remainder"):
            native.wire(prepared, 10, routing="indexed", native_work=1, native_entries=1)
        reservation = native.admit(prepared)
        budget, entries = reservation["native_work_limit"], reservation["native_entries_limit"]
        native.wire(prepared, 10, routing="indexed", native_work=budget, native_entries=entries)
        with self.assertRaisesRegex(ValueError, "reserved host remainder"):
            native.wire(prepared, 10, routing="indexed", native_work=budget + 1, native_entries=entries)
        if entries < 2_000_000:
            with self.assertRaisesRegex(ValueError, "reserved host remainder"):
                native.wire(prepared, 10, routing="indexed", native_work=budget, native_entries=entries + 1)
        with patch.object(native, "executable_identity", side_effect=AssertionError("source accessed")):
            with self.assertRaisesRegex(ValueError, "reserved host remainder"):
                native.train(prepared, executable="unused", routing="indexed", reservation=dict(reservation))

    def test_real_v3_executes_once_and_never_enters_python_training(self):
        supplied = os.environ.get("OPENPOKER_NATIVE_EXACT_FOUR_STREET_EXE")
        if not supplied:
            self.skipTest("explicit authenticated native executable not supplied")
        executable = str(Path(supplied).resolve(strict=True))
        invoke = native._invoke
        calls = []
        observed = {"marginal": 0, "terminal": 0}
        original_marginal, original_terminal = ExactSelectedFloatAdapter.joint_marginals, ExactSelectedFloatAdapter.values
        def count_marginal(instance, *args, **kwargs):
            observed["marginal"] += 1
            return original_marginal(instance, *args, **kwargs)
        def count_terminal(instance, *args, **kwargs):
            observed["terminal"] += 1
            return original_terminal(instance, *args, **kwargs)
        def observe(path, request):
            calls.append(request)
            return invoke(path, request)
        with patch.object(ExactSelectedFloatAdapter, "joint_marginals", new=count_marginal), \
             patch.object(ExactSelectedFloatAdapter, "values", new=count_terminal), \
             patch.object(native, "_invoke", side_effect=observe), \
             patch("pokerlab.suit_quotient_plan.SuitQuotientPlan.__init__", side_effect=AssertionError("Python Q plan")), \
             patch("pokerlab.suit_quotient_cfr.train_suit_quotient", side_effect=AssertionError("Python Q trainer")), \
             patch("pokerlab.equivariant_packed_cfr.train_equivariant_packed", side_effect=AssertionError("Python trainer")), \
             patch.object(solver, "train_packed", side_effect=AssertionError("Python packed trainer")):
            result = solver.solve_four_street_exact_selected(self.request(), native_executable=executable,
                native_routing="indexed", native_admission="indexed-v1", **OPTIONS)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith(native.INDEXED_PROTOCOL.encode() + b"\n"))
        self.assertTrue(result["strategy"])
        owner = result["operator_census"]["whole_request_admission"]
        proof = result["operator_census"]["native_exact"]
        self.assertGreater(observed["terminal"], 0)
        self.assertLessEqual(observed["terminal"], owner["kernel"]["terminal_calls_upper"])
        self.assertLessEqual(observed["marginal"], owner["kernel"]["marginal_calls_upper"])
        self.assertLessEqual(owner["combined_modeled_work_upper"], owner["whole_request_limit"])
        self.assertLessEqual(proof["modeled_work_upper"], owner["native_additional_admission"]["native_work_limit"])
        self.assertEqual(proof["indexed_routing"]["legacy_rows"], 0)
        self.assertEqual(proof["indexed_routing"]["legacy_extensions"], 0)
        self.assertEqual(proof["indexed_routing"]["legacy_prefixes"], 0)

if __name__ == "__main__":
    unittest.main()
