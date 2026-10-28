"""Pinned build inputs and extraction failure boundaries for native exact work."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import build_native_exact_four_street as build


class NativeExactBuildInputTests(unittest.TestCase):
    def test_full_portable_header_inventory_and_license_are_authenticated(self):
        manifest, headers = build._dependency()
        self.assertEqual(manifest["commit"], "1f7acd34fe929573c131e869867dc1d12b8080b6")
        self.assertEqual(len(headers), 198)
        self.assertEqual(sum(map(len, headers.values())), 3_057_611)
        self.assertIn("boost/config/platform/linux.hpp", headers)
        self.assertIn("boost/config/compiler/visualc.hpp", headers)
        self.assertIn("boost/multiprecision/cpp_int.hpp", headers)

    def test_tampered_dependency_rejects_before_archive_parse(self):
        with TemporaryDirectory() as folder:
            target = Path(folder)
            (target / "manifest.json").write_bytes(b"tampered")
            (target / "LICENSE_1_0.txt").write_bytes(b"tampered")
            (target / "headers.zip").write_bytes(b"tampered")
            with patch.object(build, "DEPENDENCY", target), \
                 patch.object(build.zipfile, "ZipFile", side_effect=AssertionError("archive parser")):
                with self.assertRaisesRegex(ValueError, "Pinned native dependency"):
                    build._dependency()

    def test_changed_existing_cache_rejects_without_overwriting(self):
        with TemporaryDirectory() as folder:
            target = Path(folder)
            headers = {"boost/test.hpp": b"pinned"}
            include = build._extract(target, headers)
            self.assertEqual(build._extract(target, headers), include)
            (include / "boost/test.hpp").write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "Existing native header cache changed"):
                build._extract(target, headers)
            self.assertEqual((include / "boost/test.hpp").read_bytes(), b"modified")

    def test_foreign_cache_file_rejects(self):
        with TemporaryDirectory() as folder:
            target = Path(folder)
            include = build._extract(target, {"boost/test.hpp": b"pinned"})
            (include / "foreign.hpp").write_bytes(b"foreign")
            with self.assertRaisesRegex(ValueError, "Unexpected native header"):
                build._extract(target, {"boost/test.hpp": b"pinned"})

    def test_extraction_escape_rejects_before_writing(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / "build"
            target.mkdir()
            with self.assertRaisesRegex(ValueError, "escaped build directory"):
                build._extract(target, {"../../outside.hpp": b"untrusted"})
            self.assertFalse((Path(folder) / "outside.hpp").exists())

    def test_unsupported_target_and_checkout_build_reject_before_compiler_or_dependency(self):
        with patch.object(build.shutil, "which", side_effect=AssertionError("compiler lookup")), \
             patch.object(build, "_dependency", side_effect=AssertionError("dependency")):
            for target in (None, True, "solver"):
                with self.subTest(target=target), self.assertRaisesRegex(ValueError, "Unsupported native exact"):
                    build.build(build.ROOT.parent / "build-reject", target=target)
            with self.assertRaisesRegex(ValueError, "outside the source"):
                build.build(build.ROOT / "build")


if __name__ == "__main__":
    unittest.main()
