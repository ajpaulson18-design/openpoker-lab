"""Independent arithmetic oracle checks for the factored dyadic value type."""

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

from scripts import build_native_exact_four_street as builder


_ROOT = Path(__file__).resolve().parents[1]
_TARGET = "factored-dyadic-controls"
_ENV = "OPENPOKER_NATIVE_FACTORED_DYADIC_EXE"


def _source_hashes():
    dependency = builder.DEPENDENCY.relative_to(_ROOT).as_posix()
    names = (*builder.TARGETS[_TARGET][1], "scripts/build_native_exact_four_street.py",
             f"{dependency}/manifest.json", f"{dependency}/LICENSE_1_0.txt",
             f"{dependency}/headers.zip")
    caps = {"scripts/build_native_exact_four_street.py": 2 * 1024 * 1024,
            f"{dependency}/manifest.json": 128 * 1024,
            f"{dependency}/LICENSE_1_0.txt": 16 * 1024,
            f"{dependency}/headers.zip": 1024 * 1024}
    return {name: hashlib.sha256(builder._bounded_read(_ROOT / name,
                                                       caps.get(name, 2 * 1024 * 1024))).hexdigest()
            for name in names}


def _authenticate(executable):
    executable = Path(executable).resolve(strict=True)
    manifest_path = executable.parent / "native-exact-build-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("contract") != "native-exact-build-v1"
            or manifest.get("target") != _TARGET
            or Path(manifest.get("executable", "")).resolve() != executable
            or manifest.get("executable_sha256") != hashlib.sha256(executable.read_bytes()).hexdigest()
            or manifest.get("source_sha256") != _source_hashes()):
        raise AssertionError("provided factored dyadic build lacks matching source provenance")
    return executable


class FactoredDyadicControls(unittest.TestCase):
    def test_controls_and_fraction_oracle(self):
        with tempfile.TemporaryDirectory(prefix="opl-factored-dyadic-") as tmp:
            provided = os.environ.get(_ENV)
            if provided:
                executable = _authenticate(provided)
            else:
                if shutil.which("cl" if os.name == "nt" else "c++") is None:
                    self.skipTest(f"no installed native compiler; provide {_ENV}")
                build = builder.build(Path(tmp) / "build", target=_TARGET)
                executable = Path(build["executable"])
            identity = _authenticate(executable)
            before = hashlib.sha256(executable.read_bytes()).hexdigest()
            run = subprocess.run([str(executable)], capture_output=True, timeout=30, check=False)
            self.assertEqual(_authenticate(executable), identity)
            self.assertEqual(hashlib.sha256(executable.read_bytes()).hexdigest(), before)
            self.assertEqual(run.returncode, 0, run.stderr.decode("utf-8", "replace"))
            fields = run.stdout.decode("ascii").splitlines()
            self.assertEqual(fields[-1], "controls=pass")
            label, coefficient, shift = fields[0].split("\t")
            self.assertEqual(label, "weighted")
            actual = Fraction(int(coefficient) << int(shift), 1)
            grid = 1 << 52
            expected = (Fraction(3 << 52, 1) * Fraction(grid // 4, grid)
                        + Fraction(-2 << 53, 1) * Fraction(grid // 4, grid)
                        + Fraction(98, 1) * Fraction(grid // 2, grid))
            self.assertEqual(actual, expected)
            self.assertEqual(expected.denominator, 1)


if __name__ == "__main__":
    unittest.main()
