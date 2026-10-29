"""Complete exact four-street native policies, physical replay and rejection gates."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
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

class NativeExactEarlyGateTests(unittest.TestCase):
    def test_unsupported_native_combinations_reject_before_preparation(self):
        request = request_for(case_for("payoff-varied-t10"), 10)
        for name, value in (("pair_diagnostics", "expanded"), ("exact_arithmetic", "fraction"),
                ("training_reduction", "default"), ("strategy_storage", "expanded"), ("quotient_lookup", "per-row")):
            options = dict(OPTIONS, **{name: value})
            with self.subTest(name=name), \
                    patch.object(solver, "_prepare_exact_selected", side_effect=AssertionError("preparation")), \
                    patch.object(native, "executable_identity", side_effect=AssertionError("build")):
                with self.assertRaisesRegex(ValueError, "requires compact"):
                    solver.solve_four_street_exact_selected(request, native_executable="missing", **options)

    def test_explicit_missing_build_rejects_without_fallback_or_preparation(self):
        with TemporaryDirectory() as directory, \
                patch.object(solver, "_prepare_exact_selected", side_effect=AssertionError("preparation")):
            with self.assertRaises(FileNotFoundError):
                solver.solve_four_street_exact_selected(request_for(case_for("payoff-varied-t10"), 10),
                    native_executable=Path(directory) / "missing.exe", **OPTIONS)

class NativeExactFourStreetCompiledTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = TemporaryDirectory(prefix="opl-native-exact-engine-")
        provided = os.environ.get("OPENPOKER_NATIVE_EXACT_FOUR_STREET_EXE")
        if provided:
            cls.executable = Path(provided).resolve(strict=True)
        else:
            if shutil.which("cl" if os.name == "nt" else "c++") is None:
                cls.temporary.cleanup()
                raise unittest.SkipTest("no installed compiler and no explicitly selected exact native engine")
            cls.executable = Path(builder.build(cls.temporary.name, target="engine")["executable"])
        cls.identity = native.executable_identity(cls.executable)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_complete_real_four_street_policies_metrics_and_independent_certificates(self):
        for name in ("payoff-varied-t10", "blocker-18", "asymmetric-weighted", "mixed-stabilizer", "original-22-t10"):
            with self.subTest(case=name):
                request = request_for(case_for(name), 10)
                expected = solver.solve_four_street_exact_selected(request, **OPTIONS)
                # Independent Python mathematics is reserved for diagnostics;
                # prohibit all Python learning and every legacy native backend.
                with patch("pokerlab.suit_quotient_cfr.train_suit_quotient", side_effect=AssertionError("Python trainer")), \
                        patch("pokerlab.equivariant_packed_cfr.train_equivariant_packed", side_effect=AssertionError("Python reference")), \
                        patch("pokerlab.native_selected_dag.train_native_selected_dag", side_effect=AssertionError("legacy native")), \
                        patch("pokerlab.native_public_cfr.train_native_public", side_effect=AssertionError("legacy native")):
                    result = solver.solve_four_street_exact_selected(request, native_executable=self.executable, **OPTIONS)
                self.assertEqual(result["strategy"], expected["strategy"])
                self.assertEqual([result[name].hex() for name in METRICS], [expected[name].hex() for name in METRICS])
                replay = _protected_verification(case_for(name), result)
                self.assertTrue(replay["payload_metrics_within_tolerance"])
                counters = result["operator_census"]["native_exact"]
                self.assertEqual(counters["calls"], 1)
                self.assertEqual(counters["member_checks"], 20 * result["info_sets"])
                self.assertEqual(counters["final_numeric_workspace_slots"], 0)
                old = result["operator_census"]["whole_request_admission"]
                self.assertLessEqual(old["combined_modeled_work_upper"], old["whole_request_limit"])
                self.assertLessEqual(old["retained_storage"]["whole_request_peak_upper"], old["retained_storage"]["entry_limit"])

    def test_old_t1000_rejection_remains_before_native_launch(self):
        with patch.object(native, "_invoke", side_effect=AssertionError("native launch")):
            with self.assertRaises(ValueError):
                solver.solve_four_street_exact_selected(request_for(case_for("original-22-qreject"), 1000),
                    native_executable=self.executable, **OPTIONS)

    def test_raw_result_tampering_rejects_complete_support_and_counters(self):
        request = request_for(case_for("payoff-varied-t10"), 10)
        prepared = solver._prepare_exact_selected(request, **OPTIONS)
        raw = native._invoke(self.executable, native.wire(prepared, 10, rank_cache_boards=64))
        lines = raw.splitlines()
        native.parse_policy(raw, prepared)
        # Delete one whole physical row, duplicate one, forge a member receipt,
        # or replace a probability with negative zero: each must reject.
        forged = []
        forged.append(b"\n".join([lines[0], *lines[2:]]) + b"\n")
        forged.append(b"\n".join([lines[0], lines[1], *lines[1:]]) + b"\n")
        tail = lines[-1].split(b"\t"); tail[6] = b"0"
        forged.append(b"\n".join([*lines[:-1], b"\t".join(tail)]) + b"\n")
        row = lines[1].split(b"\t"); row[-1] = b"8000000000000000"
        forged.append(b"\n".join([lines[0], b"\t".join(row), *lines[2:]]) + b"\n")
        for changed in forged:
            with self.subTest(kind=forged.index(changed)), self.assertRaises(ValueError):
                native.parse_policy(changed, prepared)

    def test_live_pipe_caps_and_timeout_kill_without_retry_and_retain_prefix(self):
        prepared = solver._prepare_exact_selected(request_for(case_for("payoff-varied-t10"), 10), **OPTIONS)
        raw = native.wire(prepared, 10)
        with patch.object(native, "MAX_OUTPUT", 32):
            with self.assertRaises(native.NativeFailure) as caught:
                native._invoke(self.executable, raw)
            self.assertEqual(len(caught.exception.stdout), 32)
        with patch.object(native, "MAX_STDERR", 4):
            with self.assertRaises(native.NativeFailure) as caught:
                native._invoke(self.executable, b"foreign\n")
            self.assertEqual(len(caught.exception.stderr), 4)
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with patch.object(native, "_start_process", return_value=process) as calls, \
                patch.object(native, "TIMEOUT", .01):
            with self.assertRaises(native.NativeFailure):
                native._invoke(self.executable, b"bounded input")
            self.assertEqual(calls.call_count, 1)
            self.assertIsNotNone(process.poll())

    def test_incomplete_chance_wire_rejects_without_result_or_fallback(self):
        request = request_for(case_for("payoff-varied-t10"), 10)
        prepared = solver._prepare_exact_selected(request, **OPTIONS)
        raw = native.wire(prepared, 10, rank_cache_boards=64)
        # Native direct input rejects foreign suffixes even when the graph is legal.
        with self.assertRaises(native.NativeFailure) as caught:
            native._invoke(self.executable, raw + b"foreign\n")
        self.assertNotEqual(caught.exception.returncode, 0)
        self.assertEqual(caught.exception.stdout, b"")
        self.assertIn(b"trailing", caught.exception.stderr)

    def test_direct_graph_adversaries_and_full_cfr_phase_controls(self):
        # Independent reviewers authored these C++ controls. The literal R
        # comparator shares the accepted exact query kernel; the physical
        # certificate above is the separate game/value oracle.
        directory = Path(self.temporary.name)
        manifest_path = self.executable.parent / "native-exact-build-manifest.json"
        self.assertEqual(native._hash(manifest_path.read_bytes()), self.identity["manifest_sha256"])
        manifest = json.loads(manifest_path.read_bytes())
        _, headers = builder._dependency()
        builder._extract(self.executable.parent, headers)
        for name in ("exact_public_graph_adversarial", "exact_selected_cfr_controls"):
            with self.subTest(control=name):
                source = builder.ROOT / ("tests/native/" + name + ".cpp")
                executable = directory / (name + (".exe" if os.name == "nt" else ""))
                flags = list(manifest["flags"])
                if os.name == "nt":
                    command = [manifest["compiler"], *flags, "/I" + str(builder.ROOT / "native"), str(source),
                        "/Fo" + str(directory / (name + ".obj")), "/Fe" + str(executable)]
                else:
                    command = [manifest["compiler"], *flags, "-I" + str(builder.ROOT / "native"), str(source), "-o", str(executable)]
                compiled = subprocess.run(command, cwd=directory, capture_output=True, timeout=180)
                self.assertEqual(compiled.returncode, 0, (compiled.stdout + compiled.stderr).decode("utf-8", "replace"))
                checked = subprocess.run([str(executable)], capture_output=True, timeout=60)
                self.assertEqual(checked.returncode, 0, (checked.stdout + checked.stderr).decode("utf-8", "replace"))
                self.assertIn(b"failures=0" if name.endswith("adversarial") else b"ALL CONTROLS PASSED", checked.stdout)

if __name__ == "__main__":
    unittest.main()
