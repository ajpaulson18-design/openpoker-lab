"""Native backend selection preserves the existing immutable request boundary."""
import unittest
from unittest.mock import patch

from pokerlab import preflop_solver
from pokerlab.four_street_solver import solve_four_street
from pokerlab.solver_contracts import FourStreetSolveRequest


class NativeSelectionTests(unittest.TestCase):
    def test_facade_passes_explicit_native_path_once(self):
        request = FourStreetSolveRequest(
            "AsAd", "KsKd", ("2c3c4d7h8h",), algorithm="cfrplus",
            traversal="public-batched", diagnostics="public-batched",
            resource_model="public-vector")
        payload = {"solver_version": "preflop-strategy-v1",
                   "strategy_schema": "preflop-strategy-v1",
                   "runout_mode": "conditioned-ordered-selected-runouts",
                   "strategy": []}
        with patch.object(preflop_solver, "solve_preflop", return_value=payload) as engine:
            solve_four_street(request, native_executable="source-built-native")
        self.assertEqual(engine.call_count, 1)
        self.assertEqual(engine.call_args.kwargs["native_executable"],
                         "source-built-native")

    def test_unsupported_native_options_reject_before_world_preparation(self):
        base = dict(iterations=10, algorithm="cfrplus",
                    traversal="public-batched", diagnostics="public-batched",
                    resource_model="public-vector", native_executable="unused")
        variants = [dict(algorithm="vanilla"), dict(traversal="recursive"),
                    dict(diagnostics="recursive"), dict(resource_model="world"),
                    dict(averaging_delay=1)]
        for changes in variants:
            with self.subTest(changes=changes):
                options = dict(base, **changes)
                with patch.object(preflop_solver, "_enumerate_physical_worlds") as prepare:
                    with self.assertRaises(ValueError):
                        preflop_solver.solve_preflop("AsAd", "KsKd", **options)
                    prepare.assert_not_called()

    def test_original_admission_precedes_native_loading(self):
        with patch.object(preflop_solver, "_enumerate_physical_worlds",
                          side_effect=ValueError("original admission rejection")):
            with self.assertRaisesRegex(ValueError, "original admission rejection"):
                preflop_solver.solve_preflop(
                    "AsAd", "KsKd", iterations=10, algorithm="cfrplus",
                    traversal="public-batched", diagnostics="public-batched",
                    resource_model="public-vector", native_executable="does-not-exist")


if __name__ == "__main__":
    unittest.main()
