"""Independent compiled trainer controls, using authenticated engine build inputs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

from scripts import build_native_exact_four_street as builder


class NativeActiveFrameIndependentTests(unittest.TestCase):
    def test_symmetry_initial_history_terminal_and_exception_controls(self):
        compiler = shutil.which("cl" if os.name == "nt" else "c++")
        if compiler is None:
            self.skipTest("installed C++20 compiler unavailable")
        supplied = (os.environ.get("OPENPOKER_NATIVE_ACTIVE_FRAMES_ENGINE_EXE") or
                    os.environ.get("OPENPOKER_NATIVE_EXACT_FOUR_STREET_EXE"))
        if not supplied:
            self.skipTest("explicit authenticated engine required for independent build flags")
        executable = Path(supplied).resolve(strict=True)
        manifest_path = executable.parent / "native-exact-build-manifest.json"
        manifest_raw = builder._bounded_read(manifest_path, 128 * 1024)
        manifest = json.loads(manifest_raw)
        engine_names = (*builder.TARGETS["engine"][1], "scripts/build_native_exact_four_street.py",
            "third_party/boost-multiprecision-1.92.0/manifest.json",
            "third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt",
            "third_party/boost-multiprecision-1.92.0/headers.zip")
        sources = {name: builder._bounded_read(builder.ROOT / name, 2 * 1024 * 1024)
                   for name in engine_names}
        self.assertEqual(manifest.get("contract"), "native-exact-build-v1")
        self.assertEqual(manifest.get("target"), "engine")
        self.assertEqual(manifest.get("source_sha256"),
                         {name: builder._hash(raw) for name, raw in sources.items()})
        self.assertEqual(manifest.get("executable_sha256"), builder._hash(executable.read_bytes()))
        self.assertEqual(Path(compiler).resolve(), Path(manifest["compiler"]).resolve())
        dependency_include = ("/I" if os.name == "nt" else "-I") + str(executable.parent / "boost-include")
        if os.name == "nt":
            expected_flags = ["/nologo", "/std:c++20", "/O2", "/W4", "/WX", "/EHsc", "/MT", "/fp:strict",
                              "/DBOOST_MP_STANDALONE", dependency_include]
            self.assertEqual(manifest["flags"], expected_flags)
        else:
            sanitized = "-fsanitize=address,undefined" in manifest["flags"]
            expected_flags = ["-std=c++20", "-O1" if sanitized else "-O3", "-Wall", "-Wextra", "-Werror",
                              "-pedantic", "-ffp-contract=off", "-fno-fast-math", "-DBOOST_MP_STANDALONE",
                              dependency_include]
            if sanitized:
                expected_flags += ["-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
            self.assertEqual(manifest["flags"], expected_flags)
        if os.environ.get("OPENPOKER_NATIVE_ACTIVE_REQUIRE_SANITIZER") == "1":
            self.assertIn("-fsanitize=address,undefined", manifest["flags"])
        # Authenticate pinned dependency contents, not only the containing archive.
        dependency, headers = builder._dependency()
        self.assertEqual(dependency["header_count"], 198)
        for name in ("tests/native/exact_selected_cfr_controls.cpp",
                     "tests/native/exact_active_cfr_extra_controls.cpp"):
            sources[name] = builder._bounded_read(builder.ROOT / name, 2 * 1024 * 1024)
        environment = os.environ.copy()
        for key in ("CL", "_CL_", "LINK", "_LINK_", "CPATH", "CPLUS_INCLUDE_PATH", "C_INCLUDE_PATH"):
            environment.pop(key, None)
        retained = os.environ.get("OPENPOKER_NATIVE_ACTIVE_CONTROL_DIR")
        with TemporaryDirectory(prefix="opl-active-independent-") as temporary:
            directory = Path(retained) if retained else Path(temporary)
            if retained:
                directory.mkdir(parents=True, exist_ok=False)
            include = builder._extract(directory, headers)
            # Preserve strict floating-point, warning and sanitizer flags from the
            # authenticated engine; replace only its dependency include location.
            flags = [flag for flag in manifest["flags"]
                     if not flag.startswith("/I" if os.name == "nt" else "-I")]
            flags += [("/I" if os.name == "nt" else "-I") + str(include),
                      ("/I" if os.name == "nt" else "-I") + str(builder.ROOT / "native")]
            control = directory / ("active-cfr-extra.exe" if os.name == "nt" else "active-cfr-extra")
            command = [compiler, *flags, str(builder.ROOT / "tests/native/exact_active_cfr_extra_controls.cpp")]
            command += (["/Fo" + str(directory / "controls.obj"), "/Fe" + str(control)]
                        if os.name == "nt" else ["-o", str(control)])
            environment["TEMP"] = environment["TMP"] = str(directory)
            (directory / "source-before.json").write_text(json.dumps(
                {name: builder._hash(raw) for name, raw in sources.items()}, sort_keys=True), encoding="utf-8")
            (directory / "command.json").write_text(json.dumps(command), encoding="utf-8")
            def invoke(stage, arguments, timeout):
                try:
                    result = subprocess.run(arguments, cwd=directory, env=environment,
                                            capture_output=True, timeout=timeout)
                except subprocess.TimeoutExpired as error:
                    (directory / (stage + ".log")).write_bytes((error.stdout or b"") + (error.stderr or b""))
                    (directory / (stage + "-status.json")).write_text(json.dumps(
                        {"error": "TimeoutExpired", "timeout_seconds": timeout}), encoding="utf-8")
                    raise
                (directory / (stage + ".log")).write_bytes(result.stdout + result.stderr)
                (directory / (stage + "-status.json")).write_text(json.dumps(
                    {"returncode": result.returncode}), encoding="utf-8")
                return result
            try:
                compiled = invoke("compile", command, 180)
                self.assertEqual(compiled.returncode, 0, (compiled.stdout + compiled.stderr).decode("utf-8", "replace"))
                result = invoke("run", [str(control)], 120)
                self.assertEqual(result.returncode, 0, (result.stdout + result.stderr).decode("utf-8", "replace"))
                self.assertIn(b"ALL EXTRA ACTIVE CFR CONTROLS PASSED", result.stdout)
            finally:
                after = {name: builder._hash(builder._bounded_read(builder.ROOT / name, 2 * 1024 * 1024))
                         for name in sources}
                (directory / "source-after.json").write_text(json.dumps(after, sort_keys=True), encoding="utf-8")
                self.assertEqual(after, {name: builder._hash(raw) for name, raw in sources.items()})
                self.assertEqual(manifest_path.read_bytes(), manifest_raw)
                self.assertEqual(builder._hash(executable.read_bytes()), manifest["executable_sha256"])


if __name__ == "__main__":
    unittest.main()
