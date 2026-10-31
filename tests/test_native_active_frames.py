"""Compile and authenticate active traversal-frame conformance controls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import build_native_exact_four_street as builder
from scripts.benchmark_equivariant_selected_solver import METRICS
from scripts.benchmark_suit_quotient_solver import case_for, request_for, _protected_verification
from pokerlab import exact_selected_solver as solver
from pokerlab import native_exact_four_street as native


class _AuthenticatedControls:
    target = ""
    environment = ""
    marker = b""
    prefix = ""

    @classmethod
    def setUpClass(cls):
        cls.temporary = TemporaryDirectory(prefix=cls.prefix)
        try:
            provided = os.environ.get(cls.environment)
            if provided:
                cls.executable = Path(provided).resolve(strict=True)
            else:
                if shutil.which("cl" if os.name == "nt" else "c++") is None:
                    raise unittest.SkipTest("no installed compiler or explicitly selected active control helper")
                cls.executable = Path(builder.build(cls.temporary.name, target=cls.target)["executable"])
            cls.manifest_path = cls.executable.parent / "native-exact-build-manifest.json"
            cls.manifest_raw = builder._bounded_read(cls.manifest_path, 128 * 1024)
            cls.manifest = json.loads(cls.manifest_raw)
            names = (*builder.TARGETS[cls.target][1], "scripts/build_native_exact_four_street.py",
                "third_party/boost-multiprecision-1.92.0/manifest.json",
                "third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt",
                "third_party/boost-multiprecision-1.92.0/headers.zip")
            cls.sources = {name: builder._hash(builder._bounded_read(builder.ROOT / name, 2 * 1024 * 1024))
                for name in names}
            if (cls.manifest.get("contract") != "native-exact-build-v1" or
                    cls.manifest.get("target") != cls.target or
                    cls.manifest.get("source_sha256") != cls.sources or
                    cls.manifest.get("executable_sha256") != builder._hash(cls.executable.read_bytes())):
                raise ValueError("Active control helper source/build changed; rebuild explicitly")
        except BaseException:
            cls.temporary.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            if (cls.manifest_path.read_bytes() != cls.manifest_raw or
                    any(builder._hash((builder.ROOT / name).read_bytes()) != expected
                        for name, expected in cls.sources.items()) or
                    builder._hash(cls.executable.read_bytes()) != cls.manifest["executable_sha256"]):
                raise ValueError("Active control source/build changed during conformance")
        finally:
            cls.temporary.cleanup()


class NativeActiveFrameControls(_AuthenticatedControls, unittest.TestCase):
    target = "active-frame"
    environment = "OPENPOKER_NATIVE_ACTIVE_FRAME_EXE"
    marker = b"ALL ACTIVE FRAME CONTROLS PASSED"
    prefix = "opl-native-active-frame-"

    def test_active_workspace_matches_history_cursor_controls(self):
        result = subprocess.run([str(self.executable)], capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr).decode("utf-8", "replace"))
        self.assertIn(self.marker, result.stdout)


class NativeActiveRoutingControls(_AuthenticatedControls, unittest.TestCase):
    target = "active-routing"
    environment = "OPENPOKER_NATIVE_ACTIVE_ROUTING_EXE"
    marker = b"ALL ACTIVE ROUTING CONTROLS PASSED"
    prefix = "opl-native-active-routing-"

    def test_active_frame_routing_matches_indexed_value_cursor(self):
        result = subprocess.run([str(self.executable)], capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr).decode("utf-8", "replace"))
        self.assertIn(self.marker, result.stdout)


class NativeActiveFrameEngineTests(unittest.TestCase):
    """Authenticate V4 end-to-end against the unchanged indexed value-cursor path."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = TemporaryDirectory(prefix="opl-native-active-engine-")
        supplied = (os.environ.get("OPENPOKER_NATIVE_ACTIVE_FRAMES_ENGINE_EXE") or
                    os.environ.get("OPENPOKER_NATIVE_EXACT_FOUR_STREET_EXE"))
        if supplied:
            cls.executable = Path(supplied).resolve(strict=True)
        else:
            if shutil.which("cl" if os.name == "nt" else "c++") is None:
                cls.temporary.cleanup()
                raise unittest.SkipTest("no installed compiler or explicitly selected active-frame engine")
            cls.executable = Path(builder.build(cls.temporary.name, target="engine")["executable"])
        cls.manifest_path = cls.executable.parent / "native-exact-build-manifest.json"
        cls.manifest_raw = builder._bounded_read(cls.manifest_path, 128 * 1024)
        cls.manifest = json.loads(cls.manifest_raw)
        names = (*builder.TARGETS["engine"][1], "scripts/build_native_exact_four_street.py",
            "third_party/boost-multiprecision-1.92.0/manifest.json",
            "third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt",
            "third_party/boost-multiprecision-1.92.0/headers.zip")
        cls.sources = {name: builder._hash(builder._bounded_read(builder.ROOT / name, 2 * 1024 * 1024))
            for name in names}
        if (cls.manifest.get("contract") != "native-exact-build-v1" or
                cls.manifest.get("target") != "engine" or
                cls.manifest.get("source_sha256") != cls.sources or
                cls.manifest.get("executable_sha256") != builder._hash(cls.executable.read_bytes())):
            cls.temporary.cleanup()
            raise ValueError("Active-frame engine source/build changed; rebuild explicitly")

    @classmethod
    def tearDownClass(cls):
        try:
            if (cls.manifest_path.read_bytes() != cls.manifest_raw or
                    any(builder._hash((builder.ROOT / name).read_bytes()) != expected
                        for name, expected in cls.sources.items()) or
                    builder._hash(cls.executable.read_bytes()) != cls.manifest["executable_sha256"]):
                raise ValueError("Active-frame engine source/build changed during conformance")
        finally:
            cls.temporary.cleanup()

    def test_v4_complete_policies_metrics_and_independent_replay(self):
        options = dict(rank_cache_boards=64, pair_diagnostics="compact", exact_arithmetic="dyadic",
            training_reduction="suit-equivariant", strategy_storage="suit-quotient",
            quotient_lookup="per-decision", native_executable=self.executable,
            native_routing="indexed", native_admission="indexed-v1")
        observed_groups = set()
        for name in ("payoff-varied-t10", "blocker-18", "asymmetric-weighted",
                     "mixed-stabilizer", "original-22-t10"):
            with self.subTest(case=name):
                case = case_for(name)
                request = request_for(case, 10)
                value_cursor = solver.solve_four_street_exact_selected(request, **options)
                old_reservation = value_cursor["operator_census"]["whole_request_admission"]["native_additional_admission"]
                for added in ("traversal", "active_frame_parser_work_upper",
                              "active_frame_parser_entries_upper", "active_frame_record_bytes_upper"):
                    self.assertNotIn(added, old_reservation)
                with patch("pokerlab.suit_quotient_cfr.train_suit_quotient",
                           side_effect=AssertionError("Python Q fallback")), \
                     patch("pokerlab.equivariant_packed_cfr.train_equivariant_packed",
                           side_effect=AssertionError("Python CFR fallback")), \
                     patch("pokerlab.native_selected_dag.train_native_selected_dag",
                           side_effect=AssertionError("legacy native fallback")), \
                     patch("pokerlab.native_public_cfr.train_native_public",
                           side_effect=AssertionError("legacy native fallback")):
                    active = solver.solve_four_street_exact_selected(request, **options,
                        native_traversal="active-frames")
                self.assertEqual(active["training_backend"],
                    "native-exact-four-street-active-frames-v4")
                self.assertEqual(active["native_traversal"], "active-frames")
                self.assertEqual(active["native_routing"], "indexed")
                self.assertEqual(active["native_admission"], "indexed-v1")
                self.assertEqual(active["strategy"], value_cursor["strategy"])
                self.assertEqual([active[key].hex() for key in METRICS],
                    [value_cursor[key].hex() for key in METRICS])
                frame = active["operator_census"]["native_exact"]["active_frames"]
                observed_groups.add(frame["group_size"])
                self.assertEqual(frame["mode"], "active-v1")
                self.assertEqual(frame["value_cursor_learning_calls"], 0)
                self.assertEqual(frame["final_active_frames"], 0)
                self.assertEqual(frame["release_calls"], frame["activations"])
                self.assertTrue(_protected_verification(case, active)["payload_metrics_within_tolerance"])
        self.assertTrue({1, 2}.issubset(observed_groups), observed_groups)

    def test_v4_physical_s3_game_deduplicates_q_members_and_replays(self):
        case = dict(case_for("original-22-t10"), id="active-frame-physical-s3-v1",
            sb_range="AdAh,AdAs,AhAs", bb_range="KdKh,KdKs,KhKs",
            runouts=["2c3c4c7c8c"])
        options = dict(rank_cache_boards=64, pair_diagnostics="compact", exact_arithmetic="dyadic",
            training_reduction="suit-equivariant", strategy_storage="suit-quotient",
            quotient_lookup="per-decision", native_executable=self.executable,
            native_routing="indexed", native_admission="indexed-v1")
        request = request_for(case, 10)
        value_cursor = solver.solve_four_street_exact_selected(request, **options)
        active = solver.solve_four_street_exact_selected(request, **options,
            native_traversal="active-frames")
        self.assertEqual(active["strategy"], value_cursor["strategy"])
        self.assertEqual([active[key].hex() for key in METRICS],
            [value_cursor[key].hex() for key in METRICS])
        exact = active["operator_census"]["native_exact"]
        self.assertEqual(exact["active_frames"]["group_size"], 6)
        self.assertEqual(exact["quotient_rows"], exact["indexed_routing"]["q_rows"])
        self.assertLess(exact["quotient_rows"], exact["expanded_rows"])
        self.assertEqual(exact["member_checks"], exact["expected_member_checks"])
        self.assertTrue(_protected_verification(case, active)["payload_metrics_within_tolerance"])

    def test_v4_wire_rejects_missing_forged_and_wrong_host_frame_proofs(self):
        case = case_for("mixed-stabilizer")
        request = request_for(case, 10)
        prepared = solver._prepare_exact_selected(request, rank_cache_boards=64,
            pair_diagnostics="compact", exact_arithmetic="dyadic",
            training_reduction="suit-equivariant", strategy_storage="suit-quotient",
            quotient_lookup="per-decision", execution_profile="native-indexed-v1")
        reservation = native.admit(prepared, traversal="active-frames")
        before = native.executable_identity(self.executable)
        wire = native.wire(prepared, prepared.iterations, rank_cache_boards=64,
            native_work=reservation["native_work_limit"],
            native_entries=reservation["native_entries_limit"], routing="indexed",
            traversal="active-frames")
        raw = native._invoke(before["executable"], wire)
        self.assertEqual(native.executable_identity(self.executable), before)
        native.parse_policy(raw, prepared, routing="indexed", traversal="active-frames")
        lines = raw.splitlines()
        self.assertEqual(lines[-1].split(b"\t", 2)[:2], [b"FRAME", b"active-v1"])
        forged_field = lines[-1].replace(b"activations=", b"activations=9", 1)
        wrong_depth = lines[-1].replace(b"frames=", b"frames=9", 1)
        invalid = (
            b"\n".join(lines[:-1]) + b"\n",
            b"\n".join([*lines[:-1], forged_field]) + b"\n",
            b"\n".join([*lines[:-1], wrong_depth]) + b"\n",
        )
        for bad in invalid:
            with self.subTest(frame=bad.splitlines()[-1][-100:]), self.assertRaises(ValueError):
                native.parse_policy(bad, prepared, routing="indexed", traversal="active-frames")
        self.assertEqual(native.executable_identity(self.executable), before)

    def test_v4_zero_decision_game_still_reports_complete_cleanup(self):
        case = dict(case_for("payoff-varied-t10"), config={"starting_stack": [0.5, 1.0]})
        options = dict(rank_cache_boards=64, pair_diagnostics="compact", exact_arithmetic="dyadic",
            training_reduction="suit-equivariant", strategy_storage="suit-quotient",
            quotient_lookup="per-decision", native_executable=self.executable,
            native_routing="indexed", native_admission="indexed-v1")
        result = solver.solve_four_street_exact_selected(request_for(case, 10), **options,
            native_traversal="active-frames")
        self.assertEqual(result["strategy"], [])
        self.assertEqual(result["info_sets"], 0)
        frame = result["operator_census"]["native_exact"]["active_frames"]
        self.assertEqual(frame["activations"], frame["release_calls"])
        self.assertEqual(frame["value_cursor_learning_calls"], 0)
        self.assertEqual((frame["final_active_frames"], frame["final_workspace_entries"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
