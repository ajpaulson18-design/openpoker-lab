"""Compiled controls for the bounded integer-only binary64 conversion boundary."""

from fractions import Fraction
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tempfile
import unittest

from scripts import build_native_exact_four_street as builder


_ROOT = Path(__file__).resolve().parents[1]
_PROTOCOL = "OPENPOKER_EXACT_BINARY64_V1"
_MIN_NORMAL = float.fromhex("0x1.0p-1022")


def _bits(value):
    return struct.unpack(">Q", struct.pack(">d", value))[0]


def _hex_integer(value):
    return ("-" if value < 0 else "") + format(abs(value), "x")


def _record(numerator, denominator):
    return f"{_hex_integer(numerator)} {_hex_integer(denominator)}"


def _oracle(numerator, denominator):
    if denominator <= 0:
        return ("error", "nonpositive_denominator")
    if numerator == 0:
        return ("ok", 0)
    try:
        value = float(Fraction(numerator, denominator))
    except OverflowError:
        return ("error", "rounded_overflow")
    if not math.isfinite(value):
        return ("error", "rounded_overflow")
    if value == 0.0 or abs(value) < _MIN_NORMAL:
        return ("error", "rounded_below_normal")
    return ("ok", _bits(value))


def _source_names():
    dependency = builder.DEPENDENCY.relative_to(_ROOT).as_posix()
    return (*builder.TARGETS["converter"][1],
            "scripts/build_native_exact_four_street.py",
            f"{dependency}/manifest.json",
            f"{dependency}/LICENSE_1_0.txt",
            f"{dependency}/headers.zip")


def _source_hashes():
    caps = {
        "scripts/build_native_exact_four_street.py": 2 * 1024 * 1024,
        "third_party/boost-multiprecision-1.92.0/manifest.json": 128 * 1024,
        "third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt": 16 * 1024,
        "third_party/boost-multiprecision-1.92.0/headers.zip": 1024 * 1024,
    }
    hashes = {}
    for name in _source_names():
        raw = builder._bounded_read(_ROOT / name, caps.get(name, 2 * 1024 * 1024))
        hashes[name] = hashlib.sha256(raw).hexdigest()
    return hashes


def _authenticate_provided_build(executable, manifest):
    executable = Path(executable).resolve(strict=True)
    def require(condition):
        if not condition:
            raise AssertionError("provided converter lacks matching source/build provenance")

    require(type(manifest) is dict)
    require(manifest.get("contract") == "native-exact-build-v1")
    require(manifest.get("target") == "converter")
    require(manifest.get("scope") ==
            "Converter boundary test helper only; not a poker kernel/trainer or accepted native solving backend.")
    require(Path(manifest.get("executable", "")).resolve() == executable)
    require(manifest.get("executable_sha256") == hashlib.sha256(
        executable.read_bytes()).hexdigest())

    source_hashes = manifest.get("source_sha256")
    expected_hashes = _source_hashes()
    require(type(source_hashes) is dict)
    require(set(source_hashes) == set(expected_hashes))
    require(source_hashes == expected_hashes)

    dependency_raw = builder._bounded_read(builder.DEPENDENCY / "manifest.json", 128 * 1024)
    archive_raw = builder._bounded_read(builder.DEPENDENCY / "headers.zip", 1024 * 1024)
    license_raw = builder._bounded_read(builder.DEPENDENCY / "LICENSE_1_0.txt", 16 * 1024)
    require(hashlib.sha256(dependency_raw).hexdigest() == builder.DEPENDENCY_MANIFEST_SHA256)
    require(hashlib.sha256(archive_raw).hexdigest() == builder.HEADER_ARCHIVE_SHA256)
    require(hashlib.sha256(license_raw).hexdigest() == builder.LICENSE_SHA256)
    dependency = json.loads(dependency_raw)
    require(dependency.get("contract") == "pinned-boost-multiprecision-header-package-v1")
    require(manifest.get("dependency_commit") == dependency.get("commit"))
    require(manifest.get("dependency_archive_sha256") == builder.HEADER_ARCHIVE_SHA256)
    require(manifest.get("dependency_manifest_sha256") == builder.DEPENDENCY_MANIFEST_SHA256)
    require(manifest.get("dependency_headers") == dependency.get("header_count") == 198)
    require(manifest.get("license") == "BSL-1.0")
    require(type(manifest.get("compiler")) is str and manifest["compiler"])
    require(type(manifest.get("compiler_version")) is str and manifest["compiler_version"])
    require(type(manifest.get("flags")) is list and any(
        "BOOST_MP_STANDALONE" in flag for flag in manifest["flags"]))
    require(type(manifest.get("platform")) is str and manifest["platform"])
    return manifest


def _synthetic_manifest(executable):
    dependency = json.loads((builder.DEPENDENCY / "manifest.json").read_text(encoding="utf-8"))
    return {
        "contract": "native-exact-build-v1",
        "target": "converter",
        "scope": "Converter boundary test helper only; not a poker kernel/trainer or accepted native solving backend.",
        "executable": str(Path(executable).resolve()),
        "executable_sha256": hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
        "source_sha256": _source_hashes(),
        "dependency_commit": dependency["commit"],
        "dependency_archive_sha256": builder.HEADER_ARCHIVE_SHA256,
        "dependency_manifest_sha256": builder.DEPENDENCY_MANIFEST_SHA256,
        "dependency_headers": dependency["header_count"],
        "license": "BSL-1.0",
        "compiler": "synthetic-no-compiler-test",
        "compiler_version": "fixture",
        "flags": ["BOOST_MP_STANDALONE"],
        "platform": "fixture",
    }


class ProvidedBuildManifestTests(unittest.TestCase):
    """Metadata checks run independently of any installed C++ compiler."""

    def test_authenticates_entire_current_build_and_dependency_closure(self):
        with tempfile.TemporaryDirectory(prefix="opl-exact-binary64-manifest-") as directory:
            executable = Path(directory) / "probe"
            executable.write_bytes(b"synthetic probe bytes")
            manifest = _synthetic_manifest(executable)
            self.assertIs(_authenticate_provided_build(executable, manifest), manifest)

    def test_rejects_missing_or_changed_source_dependency_and_executable_pins(self):
        with tempfile.TemporaryDirectory(prefix="opl-exact-binary64-manifest-") as directory:
            executable = Path(directory) / "probe"
            executable.write_bytes(b"synthetic probe bytes")
            original = _synthetic_manifest(executable)
            mutations = []

            missing = copy.deepcopy(original)
            del missing["source_sha256"]["third_party/boost-multiprecision-1.92.0/headers.zip"]
            mutations.append(missing)
            changed_source = copy.deepcopy(original)
            changed_source["source_sha256"]["native/exact_binary64.hpp"] = "0" * 64
            mutations.append(changed_source)
            changed_commit = copy.deepcopy(original)
            changed_commit["dependency_commit"] = "0" * 40
            mutations.append(changed_commit)
            changed_header_count = copy.deepcopy(original)
            changed_header_count["dependency_headers"] = 197
            mutations.append(changed_header_count)
            changed_archive = copy.deepcopy(original)
            changed_archive["dependency_archive_sha256"] = "0" * 64
            mutations.append(changed_archive)
            changed_executable = copy.deepcopy(original)
            changed_executable["executable_sha256"] = "0" * 64
            mutations.append(changed_executable)
            for index, manifest in enumerate(mutations):
                with self.subTest(manifest=index):
                    with self.assertRaises(AssertionError):
                        _authenticate_provided_build(executable, manifest)


class ExactBinary64BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        provided_executable = os.environ.get("OPENPOKER_NATIVE_EXACT_BINARY64_EXE")
        cls._temporary = tempfile.TemporaryDirectory(prefix="opl-exact-binary64-")
        cls.build_dir = Path(cls._temporary.name)
        if provided_executable:
            cls.executable = Path(provided_executable).resolve(strict=True)
            manifest_path = cls.executable.parent / "native-exact-build-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cls.build = _authenticate_provided_build(cls.executable, manifest)
        else:
            compiler = shutil.which("cl" if os.name == "nt" else "c++")
            if compiler is None:
                cls._temporary.cleanup()
                raise unittest.SkipTest("no installed native compiler in this environment")
            try:
                cls.build = builder.build(cls.build_dir, target="converter")
            except RuntimeError:
                cls._temporary.cleanup()
                raise
            cls.executable = Path(cls.build["executable"])
        if not cls.executable.is_file():
            raise AssertionError("source-authenticated builder returned a missing executable")

    @classmethod
    def tearDownClass(cls):
        temporary = getattr(cls, "_temporary", None)
        if temporary is not None:
            temporary.cleanup()

    def _run_records(self, records):
        payload = "\n".join((_PROTOCOL, *records, ""))
        completed = subprocess.run(
            [str(self.executable)], input=payload.encode("ascii"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("ascii", "replace"))
        output = completed.stdout.decode("ascii").splitlines()
        self.assertEqual(output[0], f"READY\t{_PROTOCOL}")
        self.assertEqual(len(output), len(records) + 1)
        return [line.split("\t") for line in output[1:]]

    def test_hardcoded_ieee_anchors(self):
        midpoint_min_normal = (2**53 - 1, 2**1075)
        just_below_min_normal_midpoint = (2**54 - 3, 2**1076)
        just_above_min_normal_midpoint = (2**54 - 1, 2**1076)
        max_finite = ((2**53 - 1) << 971, 1)
        overflow_midpoint = ((2**54 - 1) << 970, 1)
        two_midpoint = (2**54 - 1, 2**53)
        max_width_unreduced = (2**65535 + 1, 2**65536 - 1)
        cases = [
            ((1, 3), ("ok", 0x3FD5555555555555)),
            ((-1, 3), ("ok", 0xBFD5555555555555)),
            ((0, 7), ("ok", 0x0000000000000000)),
            ((-(2**53 + 1), 2**53), ("ok", 0xBFF0000000000000)),
            ((2**53 + 3, 2**53), ("ok", 0x3FF0000000000002)),
            (two_midpoint, ("ok", 0x4000000000000000)),
            ((1, 2**1022), ("ok", 0x0010000000000000)),
            ((2**1025, 3), _oracle(2**1025, 3)),
            (midpoint_min_normal, ("ok", 0x0010000000000000)),
            (just_below_min_normal_midpoint, ("error", "rounded_below_normal")),
            (just_above_min_normal_midpoint, ("ok", 0x0010000000000000)),
            ((-midpoint_min_normal[0], midpoint_min_normal[1]),
             ("ok", 0x8010000000000000)),
            ((-just_below_min_normal_midpoint[0], just_below_min_normal_midpoint[1]),
             ("error", "rounded_below_normal")),
            (max_finite, ("ok", 0x7FEFFFFFFFFFFFFF)),
            (overflow_midpoint, ("error", "rounded_overflow")),
            ((-(2**1024), 1), ("error", "rounded_overflow")),
            ((1, 2**1075), ("error", "rounded_below_normal")),
            ((2**65535, 2**65535), ("ok", 0x3FF0000000000000)),
            (max_width_unreduced, ("ok", 0x3FE0000000000000)),
        ]
        responses = self._run_records([_record(n, d) for (n, d), _ in cases])
        for response, ((numerator, denominator), expected) in zip(responses, cases):
            with self.subTest(numerator_bits=abs(numerator).bit_length(),
                              denominator_bits=denominator.bit_length()):
                observed = self._decode_response(response)
                self.assertEqual(observed[:2], expected)
                self.assertEqual(_oracle(numerator, denominator), expected)
                if response[0] == "OK":
                    self.assertLessEqual(int(response[2]), 65536)
                    self.assertLessEqual(int(response[3]), 65589)
                    self.assertGreater(int(response[4]), 0)
                    if numerator == denominator == 2**65535:
                        self.assertEqual(int(response[2]), 65536)
                        self.assertEqual(int(response[3]), 65588)
                    if (numerator, denominator) == max_width_unreduced:
                        self.assertEqual(int(response[2]), 65536)
                        self.assertEqual(int(response[3]), 65589)

    def test_seeded_fraction_differential(self):
        rng = random.Random(0xB16464)
        cases = []
        for _ in range(192):
            numerator = rng.getrandbits(rng.randint(1, 2048))
            if rng.getrandbits(1):
                numerator = -numerator
            denominator = rng.getrandbits(rng.randint(1, 2048)) or 1
            if rng.randrange(5) == 0:
                numerator <<= rng.randint(0, 1100)
            if rng.randrange(5) == 0:
                denominator <<= rng.randint(0, 1100)
            cases.append((numerator, denominator))
        responses = self._run_records([_record(n, d) for n, d in cases])
        for response, (numerator, denominator) in zip(responses, cases):
            with self.subTest(numerator_bits=abs(numerator).bit_length(),
                              denominator_bits=denominator.bit_length()):
                self.assertEqual(self._decode_response(response),
                                 _oracle(numerator, denominator))

    def test_protocol_and_hostile_input_caps(self):
        oversized_token = "0" * (65536 // 4 + 1)
        responses = self._run_records([
            "1 0", "1 -1", "1 2g", "1", "1 2 3", "-0 1",
            f"1 {oversized_token}",
            _record(1, 1),
        ])
        self.assertEqual(responses[0], ["ERR", "nonpositive_denominator"])
        self.assertEqual(responses[1], ["ERR", "invalid_record"])
        self.assertEqual(responses[2], ["ERR", "invalid_record"])
        self.assertEqual(responses[3], ["ERR", "invalid_record"])
        self.assertEqual(responses[4], ["ERR", "invalid_record"])
        self.assertEqual(responses[5][0], "OK")
        self.assertEqual(responses[5][1], "0000000000000000")
        self.assertEqual(responses[6], ["ERR", "input_bit_limit"])
        self.assertEqual(responses[7][0], "OK")
        self.assertEqual(int(responses[7][1], 16), 0x3FF0000000000000)

        oversized_line = "X" * ((1 << 20) + 1)
        payload = f"{_PROTOCOL}\n{oversized_line}"
        completed = subprocess.run(
            [str(self.executable)], input=payload.encode("ascii"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
        self.assertEqual(completed.returncode, 3)
        self.assertEqual(completed.stdout.decode("ascii").splitlines(), [
            f"READY\t{_PROTOCOL}", "ERR\tline_too_long"])

    def test_exact_caller_limit_api_rejects_before_conversion_shifts(self):
        source = self.build_dir / "exact_binary64_limit_control.cpp"
        source.write_text(r'''#include "exact_binary64.hpp"
#include <iostream>
using namespace openpoker::exact_binary64;
int main() {
  Limits limits; limits.max_input_bits = 8; limits.max_scratch_bits = 8;
  try { (void)convert(Integer(256), Integer(1), limits); return 2; }
  catch (const ConversionError& e) { if (e.code() != ErrorCode::input_bit_limit) return 3; }
  try { (void)convert(Integer(128), Integer(1), limits); return 4; }
  catch (const ConversionError& e) { if (e.code() != ErrorCode::scratch_bit_limit) return 5; }
  try { (void)convert(Integer(1), Integer(0)); return 10; }
  catch (const ConversionError& e) { if (e.code() != ErrorCode::nonpositive_denominator) return 11; }
  try { Integer too_wide = Integer(1) << kMaximumInputBits;
        (void)convert(too_wide, Integer(1)); return 12; }
  catch (const ConversionError& e) { if (e.code() != ErrorCode::input_bit_limit) return 13; }
  try { Limits raised; raised.max_input_bits = kMaximumInputBits + 1;
        (void)convert(Integer(1), Integer(1), raised); return 6; }
  catch (const ConversionError& e) { if (e.code() != ErrorCode::invalid_limits) return 7; }
  try { Limits raised; raised.max_scratch_bits = kMaximumScratchBits + 1;
        (void)convert(Integer(1), Integer(1), raised); return 8; }
  catch (const ConversionError& e) { if (e.code() != ErrorCode::invalid_limits) return 9; }
  std::cout << "small_caller_caps_and_nonraising_limits=pass\n";
}
''', encoding="ascii")
        compiler = self.build["compiler"]
        flags = list(self.build["flags"])
        executable = self.build_dir / ("exact-binary64-limit-control.exe" if os.name == "nt"
                                       else "exact-binary64-limit-control")
        if os.name == "nt":
            command = [compiler, *flags, "/I" + str(_ROOT / "native"), str(source),
                       "/Fo" + str(self.build_dir / "exact-binary64-limit-control.obj"),
                       "/Fe" + str(executable)]
        else:
            command = [compiler, *flags, "-I" + str(_ROOT / "native"), str(source),
                       "-o", str(executable)]
        built = subprocess.run(command, cwd=self.build_dir, capture_output=True,
                               timeout=120, check=False)
        self.assertEqual(built.returncode, 0,
                         (built.stdout + built.stderr).decode("utf-8", "replace"))
        run = subprocess.run([str(executable)], capture_output=True, timeout=30, check=False)
        self.assertEqual(run.returncode, 0, run.stderr.decode("ascii", "replace"))
        self.assertEqual(run.stdout.decode("ascii").strip(),
                         "small_caller_caps_and_nonraising_limits=pass")

    @staticmethod
    def _decode_response(fields):
        if fields[0] == "ERR":
            return ("error", fields[1])
        if fields[0] != "OK" or len(fields) != 5:
            raise AssertionError(f"invalid converter response: {fields!r}")
        return ("ok", int(fields[1], 16))


if __name__ == "__main__":
    unittest.main()
