"""No-training integration test for the native river quality runner.

The public APIs, enumerators, tree builders, diagnostics and independent
numeric/exact replay run normally. Only the trainer calls and native backend
lookup are replaced, so this exercises contract wiring without training or
launching/looking up a native executable. The generated policies are synthetic
uniform profiles and are not quality evidence.
"""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import benchmark_native_river_range_quality as runner

ROOT = Path(__file__).resolve().parents[1]
CONTROLS = ROOT / "benchmarks" / "results" / "native-river-controls-v1"


def _uniform(infos):
    return {key: [1.0 / count] * count for key, count in infos.items()}


class _SyntheticRuntime:
    """ProductionRuntime methods bound to real modules with fixed test snapshots."""

    def __init__(self):
        from scripts import benchmark_river_heldout_quality as baseline
        from scripts import preflop_validation as ranks
        from scripts import turn_rational_certificate as exact
        from scripts import turn_river_validation as rules
        from pokerlab import native_river_solver as native
        from pokerlab import native_fixed_street as fixed
        from pokerlab import postflop_solver as post
        from pokerlab import public_cfr as public
        from pokerlab import turn_tail_adapter as turn
        from pokerlab import river_tail_adapter as river
        from pokerlab import river_config as rc

        self.root = ROOT.resolve()
        self.build = (ROOT.parent / "synthetic-native-build-no-lookup").resolve()
        self.baseline, self.ranks, self.exact, self.rules = baseline, ranks, exact, rules
        self.native, self.fixed, self.post, self.public = native, fixed, post, public
        self.turn, self.river = turn, river
        self.river_config = rc.RiverConfig
        self._source = {"status": "clean", "head": "synthetic-no-training-test"}
        report = json.loads((CONTROLS / "report.json").read_text(encoding="utf-8"))
        self._build = copy.deepcopy(report["build_snapshot"])

    def source_snapshot(self, _expected_head):
        return copy.deepcopy(self._source)

    def build_snapshot(self):
        return copy.deepcopy(self._build)


def _bind_production_methods(runtime):
    runtime.preflight = runner.ProductionRuntime.preflight.__get__(runtime, _SyntheticRuntime)
    runtime.call = runner.ProductionRuntime.call.__get__(runtime, _SyntheticRuntime)
    runtime.audit = runner.ProductionRuntime.audit.__get__(runtime, _SyntheticRuntime)
    runtime._rank_census = runner.ProductionRuntime._rank_census.__get__(runtime, _SyntheticRuntime)


class NativeRiverRangeQualityIntegrationTests(unittest.TestCase):
    def test_preflight_rejects_duplicate_production_physical_pairs(self):
        runtime=_SyntheticRuntime()
        _bind_production_methods(runtime)
        manifest=json.loads(runner.CASE_MANIFEST.read_text(encoding="utf-8"))
        original=runtime.native._enumerate_worlds

        def duplicated(*args, **kwargs):
            hands,worlds,selected,pairs=original(*args,**kwargs)
            worlds=list(worlds)
            worlds[1]=worlds[0]
            return hands,worlds,selected,pairs

        with patch.object(runtime.native,"_enumerate_worlds",duplicated):
            with self.assertRaisesRegex(AssertionError,"duplicate physical pairs"):
                runtime.preflight(manifest["cases"][0],10000)

    def test_four_profile_lifecycle_runs_real_apis_and_independent_audits_without_training(self):
        runtime = _SyntheticRuntime()
        _bind_production_methods(runtime)
        manifest = json.loads(runner.CASE_MANIFEST.read_text(encoding="utf-8"))
        calls = {"python_stub": 0, "native_stub": 0, "backend_lookup": 0,
                 "real_native": 0, "real_python": 0}
        latest_native_admission = {}
        original_admit = runtime.fixed.admit_native_shape

        def capture_admission(*args, **kwargs):
            value = original_admit(*args, **kwargs)
            latest_native_admission["value"] = value
            return value

        def python_uniform(root, worlds, infos, iterations, discard, **kwargs):
            calls["python_stub"] += 1
            self.assertEqual(iterations, 10_000)
            self.assertEqual(discard, 0)
            return _uniform(infos)

        def native_uniform(root, worlds, infos, iterations, algorithm="cfrplus", *,
                           pot, build_directory, reduction="scalar"):
            calls["native_stub"] += 1
            self.assertEqual(iterations, 10_000)
            self.assertEqual(algorithm, "cfrplus")
            self.assertEqual(reduction, "public-batched")
            self.assertEqual(build_directory, runtime.build)
            build = runtime._build["manifest"]
            return _uniform(infos), {
                "backend": "native-fixed-street-v1",
                "reduction": reduction,
                "build": copy.deepcopy(build),
                "admission": copy.deepcopy(latest_native_admission["value"]),
                "native_world_rows": len(worlds),
                "input_sha256": hashlib.sha256(b"synthetic-untrained-input").hexdigest(),
                "output_sha256": hashlib.sha256(b"synthetic-untrained-output").hexdigest(),
                "scope": "Synthetic uniform policy; no native executable launched; hashes are sentinels.",
            }

        def forbidden_real_native(*_args, **_kwargs):
            calls["real_native"] += 1
            raise AssertionError("real native training/process must not run")

        def forbidden_real_python(*_args, **_kwargs):
            calls["real_python"] += 1
            raise AssertionError("real Python CFR+ trainer must not run")

        def no_backend_lookup(*_args, **_kwargs):
            calls["backend_lookup"] += 1
            return None

        with patch.object(runtime.fixed, "admit_native_shape", capture_admission), \
             patch.object(runtime.fixed, "validate_backend", no_backend_lookup), \
             patch.object(runtime.fixed, "train_native_fixed_street", native_uniform), \
             patch("pokerlab.turn_tail_adapter._train_original_weight_tail", python_uniform), \
             patch("pokerlab.river_tail_adapter._train_original_weight_tail", python_uniform), \
             patch("pokerlab.public_cfr._train_prepared", forbidden_real_python), \
             patch("pokerlab.native_fixed_street.subprocess.run", forbidden_real_native):
            with tempfile.TemporaryDirectory(prefix="native-range-quality-no-training-",
                                             dir=ROOT.parent) as temp:
                output = Path(temp) / "attempt"
                report = runner.run_with_runtime(
                    runtime, manifest, output, "synthetic-no-training-test",
                    runtime.build, {"synthetic_test_fixture": True},
                )

                failures = [
                    (p.get("case"), p.get("backend"),
                     p.get("independent_audit", {}).get("failure"))
                    for p in report.get("profiles", [])
                ]
                self.assertEqual(report["status"], "completed", failures)
                self.assertEqual(len(report["profiles"]), 4)
                self.assertEqual((calls["python_stub"], calls["native_stub"]), (2, 2))
                self.assertEqual(calls["backend_lookup"], 2)
                self.assertEqual(calls["real_native"], 0)
                self.assertEqual(calls["real_python"], 0)
                self.assertEqual(len(report["parity"]), 2)
                self.assertTrue(all(p["independent_audit"]["replay_status"] == "valid"
                                    for p in report["profiles"]))
                self.assertTrue(all(p["independent_audit"]["blocked_production_helper_calls"] == []
                                    for p in report["profiles"]))

                for profile in report["profiles"]:
                    raw = (output / profile["file"]).read_bytes()
                    saved = json.loads(raw.decode("utf-8"))
                    case = next(c for c in manifest["cases"] if c["id"] == profile["case"])
                    expected_board = [case["board"][i:i + 2]
                                      for i in range(0, len(case["board"]), 2)]
                    self.assertEqual(saved["board"], expected_board)
                    self.assertEqual(saved["iterations"], 10_000)
                    runner._validate_return(saved, case, profile["backend"], 10_000)
                    self.assertEqual(profile["independent_audit"]["world_count"],
                                     profile["independent_audit"]["compatible_pairs"])

                stored = json.loads((output / "report.json").read_text(encoding="utf-8"))
                self.assertEqual(stored["claim_id"], report["claim_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
