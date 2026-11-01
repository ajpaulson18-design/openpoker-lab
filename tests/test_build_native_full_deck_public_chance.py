"""Build/authentication and bounded-wire controls for the new native seam."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

from scripts import build_native_exact_four_street as shared_builder
from scripts import build_native_full_deck_public_chance as chance_builder


def _prefix_request(mode="exact"):
    return " ".join((
        "OPENPOKER_FULL_DECK_PUBLIC_CHANCE_V1", "deck FULL52",
        "limits 1326 65536 500000000 2000000 1073741824",
        "ranges 1 1", "sb 0 5 3fd0000000000000", "bb 15 20 3fe8000000000000",
        "query PREFIX", "prefix", mode, "0",
    )) + "\n"


def _terminal_request(kind="FOLD", mode="exact"):
    return " ".join((
        "OPENPOKER_FULL_DECK_PUBLIC_CHANCE_V1", "deck FULL52",
        "limits 1326 65536 500000000 2000000 1073741824",
        "ranges 1 1", "sb 0 5 3fd0000000000000", "bb 15 20 3fe8000000000000",
        "query TERMINAL", "terminal", mode, "0", kind, "3ff0000000000000", "1", "1", "1",
        "3ff0000000000000", "24", "28", "32", "36", "40",
    )) + "\n"


def _run(executable, request, **kwargs):
    return subprocess.run([str(executable)], input=request, text=True,
                          capture_output=True, timeout=20, **kwargs)


class NativeFullDeckBuildContractTests(unittest.TestCase):
    def test_explicit_wrapper_delegates_only_to_new_target(self):
        self.assertIn("full-deck-chance", shared_builder.TARGETS)
        self.assertEqual(shared_builder.TARGETS["full-deck-chance"][0],
                         "native-full-deck-public-chance-probe")
        self.assertEqual(shared_builder.TARGETS["converter"][0], "native-exact-binary64-probe")
        self.assertEqual(shared_builder.TARGETS["engine"][0], "native-exact-four-street-train")
        self.assertEqual(shared_builder.TARGETS["full-deck-chance"][1][0],
                         "native/full_deck_public_chance_probe.cpp")
        self.assertIn("scripts/build_native_full_deck_public_chance.py",
                      shared_builder.TARGETS["full-deck-chance"][1])
        self.assertEqual(shared_builder.TARGETS["full-deck-chance-preflight"][0],
                         "native-full-deck-public-chance-preflight-controls")
        self.assertEqual(shared_builder.TARGETS["full-deck-chance-preflight"][1][0],
                         "tests/native/full_deck_public_chance_preflight_controls.cpp")

    def test_wrapper_forwards_exact_target_without_building_on_invalid_path(self):
        with self.assertRaisesRegex(ValueError, "outside the source checkout"):
            chance_builder.build(shared_builder.ROOT / "native-test-build")


@unittest.skipUnless(shutil.which("cl" if os.name == "nt" else "c++"),
                     "native C++20 compiler is not configured in this environment")
class NativeFullDeckProbeBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retained = os.environ.get("OPENPOKER_NATIVE_FULL_DECK_CONTROL_DIR")
        if retained:
            cls.temp = None
            cls.control_root = Path(retained).resolve()
            if cls.control_root.exists():
                raise AssertionError("OPENPOKER_NATIVE_FULL_DECK_CONTROL_DIR must be fresh")
            if cls.control_root == shared_builder.ROOT or shared_builder.ROOT in cls.control_root.parents:
                raise AssertionError("native control output must be outside the source checkout")
            cls.control_root.mkdir(parents=True)
        else:
            # Keep temporary builds under the writable Codex work root; the
            # managed Windows temp directory can deny deletion of test EXEs.
            cls.temp = tempfile.TemporaryDirectory(prefix="openpoker-full-deck-probe-",
                                                   dir=shared_builder.ROOT.parent)
            cls.control_root = Path(cls.temp.name).resolve()
        cls.build = chance_builder.build(cls.control_root / "probe")
        cls.executable = Path(cls.build["executable"])
        cls.preflight_build = shared_builder.build(cls.control_root / "preflight",
                                                   target="full-deck-chance-preflight")
        cls.preflight_executable = Path(cls.preflight_build["executable"])

    @classmethod
    def tearDownClass(cls):
        if cls.temp is None:
            return
        try:
            cls.temp.cleanup()
        except PermissionError:
            # Windows can briefly retain the executed image mapping after the
            # child exits; retry cleanup from the same verified work root.
            time.sleep(0.2)
            target = Path(cls.temp.name).resolve()
            work_root = shared_builder.ROOT.parent.resolve()
            if work_root not in target.parents:
                raise
            shutil.rmtree(target)

    def test_build_manifest_authenticates_exact_probe_closure_and_scope(self):
        manifest_path = Path(self.build["manifest_path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["target"], "full-deck-chance")
        self.assertIn("probability probe only", manifest["scope"])
        self.assertEqual(manifest["executable_sha256"], self.build["executable_sha256"])
        source_hashes = manifest["source_sha256"]
        for name in ("native/full_deck_public_chance_probe.cpp",
                     "native/full_deck_public_chance.hpp",
                     "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp",
                     "scripts/build_native_full_deck_public_chance.py",
                     "scripts/build_native_exact_four_street.py"):
            raw = (shared_builder.ROOT / name).read_bytes()
            self.assertEqual(source_hashes[name], shared_builder._hash(raw), name)
        self.assertEqual(manifest["dependency_headers"], 198)
        self.assertEqual(manifest["license"], "BSL-1.0")
        self.assertTrue(self.executable.is_file())
        self.assertNotIn(shared_builder.ROOT, self.executable.parents)

    def test_preflight_controls_are_source_authenticated_and_pass(self):
        manifest = json.loads(Path(self.preflight_build["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["target"], "full-deck-chance-preflight")
        self.assertIn("preflight controls only", manifest["scope"])
        for name in ("tests/native/full_deck_public_chance_preflight_controls.cpp",
                     "native/full_deck_public_chance_probe.cpp",
                     "native/full_deck_public_chance.hpp",
                     "scripts/build_native_full_deck_public_chance.py"):
            self.assertEqual(manifest["source_sha256"][name],
                             shared_builder._hash((shared_builder.ROOT / name).read_bytes()))
        result = subprocess.run([str(self.preflight_executable)], capture_output=True,
                                text=True, timeout=20)
        (self.control_root / "preflight.stdout.txt").write_bytes(result.stdout.encode())
        (self.control_root / "preflight.stderr.txt").write_bytes(result.stderr.encode())
        (self.control_root / "preflight.status.json").write_text(json.dumps({
            "returncode": result.returncode,
            "expected_stdout": "ALL FULL DECK PUBLIC CHANCE PREFLIGHT CONTROLS PASSED",
        }, indent=2) + "\n", encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(result.stdout.strip(), "ALL FULL DECK PUBLIC CHANCE PREFLIGHT CONTROLS PASSED")

    def test_prefix_exact_and_binary64_keep_rows_and_support(self):
        exact = _run(self.executable, _prefix_request("exact"))
        self.assertEqual(exact.returncode, 0, exact.stderr)
        lines = exact.stdout.splitlines()
        self.assertEqual(lines[0], "OPENPOKER_FULL_DECK_PUBLIC_CHANCE_RESULT_V1")
        self.assertIn("deck_mode FULL52", lines)
        self.assertIn("side 0 1", lines)
        self.assertIn("side 1 1", lines)
        self.assertTrue(any(line.startswith("value + ") and line.endswith(" 1") for line in lines))
        self.assertTrue(lines[-1].startswith("receipt "))
        self.assertEqual(lines[-1].split()[-4:], ["1", "0", "0", "0"])
        probe_receipt = next(line for line in lines if line.startswith("probe_receipt ")).split()
        request_line = _prefix_request("exact").strip()
        self.assertEqual(int(probe_receipt[1]), len(request_line))
        self.assertEqual(int(probe_receipt[2]), len(request_line.split()))
        self.assertEqual(int(probe_receipt[3]),
                         16384 + 6 * int(probe_receipt[1]) + 16 * int(probe_receipt[2]))
        row_digits = (65536 + 3) // 4
        expected_response = 4096 + 2 * (row_digits + 64) + 3 * row_digits
        self.assertEqual(int(probe_receipt[4]), expected_response)
        ownership_receipt = next(line for line in lines if line.startswith("probe_ownership ")).split()
        self.assertEqual(ownership_receipt, ["probe_ownership", "136", "262400"])
        kernel_work = int(lines[-1].split()[1])
        self.assertLessEqual(int(probe_receipt[3]) + 8 * int(probe_receipt[4]) + kernel_work,
                             500_000_000)

        converted = _run(self.executable, _prefix_request("binary64"))
        self.assertEqual(converted.returncode, 0, converted.stderr)
        converted_lines = converted.stdout.splitlines()
        binary = next(i for i, line in enumerate(converted_lines) if line.startswith("binary64_bits "))
        self.assertEqual(converted_lines[binary], "binary64_bits 2")
        self.assertEqual(converted_lines[binary + 1:binary + 3],
                         ["3ff0000000000000", "3ff0000000000000"])
        self.assertTrue(converted_lines[-1].startswith("receipt "))

    def test_terminal_exact_and_binary64_shape_with_q_and_reach(self):
        exact = _run(self.executable, _terminal_request("FOLD", "exact"))
        self.assertEqual(exact.returncode, 0, exact.stderr)
        self.assertIn("terminal 0 1", exact.stdout.splitlines())
        self.assertTrue(exact.stdout.splitlines()[-1].startswith("receipt "))
        converted = _run(self.executable, _terminal_request("FOLD", "binary64"))
        self.assertEqual(converted.returncode, 0, converted.stderr)
        lines = converted.stdout.splitlines()
        binary = next(i for i, line in enumerate(lines) if line.startswith("binary64_bits "))
        self.assertEqual(lines[binary], "binary64_bits 1")
        self.assertEqual(len(lines[binary + 1]), 16)

    def test_malformed_proposal_and_foreign_card_return_bounded_errors(self):
        invalid_q = _terminal_request().replace(" 1 1 1 3ff0000000000000", " 2 1 1 3ff0000000000000")
        result = _run(self.executable, invalid_q)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ERR invalid_query\n")
        foreign = _prefix_request().replace("prefix exact 0", "prefix exact 3 0 5 52")
        result = _run(self.executable, foreign)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ERR invalid_query\n")

    def test_transport_reserve_is_deducted_before_kernel_query(self):
        request = _prefix_request().replace("500000000", "1", 1)
        result = _run(self.executable, request)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ERR modeled_work_limit\n")

    def test_oversized_request_stops_immediately(self):
        result = subprocess.run([str(self.executable)], input=b"x" * ((1 << 20) + 1),
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.replace(b"\r\n", b"\n"), b"ERR request_too_large\n")


if __name__ == "__main__":
    unittest.main()
