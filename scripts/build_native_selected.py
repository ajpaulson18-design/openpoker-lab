"""Build the opt-in selected-operator C++ CFR+ helper outside the source checkout."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "native" / "selected_operator_train.cpp"
PROTOCOL = "OPENPOKER_SELECTED_OPERATOR_V1"
WORK_MODEL = "native-selected-operator-work-v1"


def build(output_directory, *, sanitize=False):
    directory = Path(output_directory).resolve()
    if directory == ROOT or ROOT in directory.parents:
        raise ValueError("Build the native selected operator trainer outside the source checkout")
    directory.mkdir(parents=True, exist_ok=True)
    executable = directory / ("native-selected-train.exe" if os.name == "nt"
                              else "native-selected-train")
    if executable.is_symlink():
        raise ValueError("Refusing to replace a symlink output")
    compiler_name = "cl" if os.name == "nt" else "c++"
    compiler = shutil.which(compiler_name)
    if compiler is None:
        raise RuntimeError("Installed C++20 compiler unavailable; no automatic installation")
    compiler = str(Path(compiler).resolve())
    if os.name == "nt":
        if sanitize:
            raise ValueError("Sanitized native selected operator build requires a POSIX compiler")
        flags = ["/nologo", "/std:c++20", "/O2", "/W4", "/WX", "/EHsc",
                 "/MT", "/fp:strict", "/D_CRT_SECURE_NO_WARNINGS"]
        command = [compiler, *flags, str(SOURCE),
                   "/Fo" + str(directory / "selected_operator_train.obj"),
                   "/Fe" + str(executable)]
        version_command = [compiler]
    else:
        flags = ["-std=c++20", "-O1" if sanitize else "-O3", "-Wall", "-Wextra",
                 "-Werror", "-pedantic", "-ffp-contract=off", "-fno-fast-math"]
        if sanitize:
            flags.extend(["-g", "-fsanitize=address,undefined",
                          "-fno-omit-frame-pointer"])
        command = [compiler, *flags, str(SOURCE), "-o", str(executable)]
        version_command = [compiler, "--version"]
    environment = os.environ.copy()
    for key in ("CL", "_CL_", "LINK", "_LINK_"):
        environment.pop(key, None)
    # MSVC writes a linker response file in TEMP; keep it in the selected
    # caller-owned build directory rather than an inaccessible system temp.
    environment["TEMP"] = str(directory)
    environment["TMP"] = str(directory)
    version = subprocess.run(version_command, capture_output=True, timeout=30,
                             check=False, env=environment)
    banner = (version.stdout + version.stderr).decode(errors="replace").strip()[:4096]
    source = SOURCE.read_bytes()
    completed = subprocess.run(command, capture_output=True, timeout=120,
                               check=False, cwd=directory, env=environment)
    if completed.returncode:
        raise RuntimeError("Native selected operator compilation failed: " +
                           (completed.stdout + completed.stderr).decode(
                               errors="replace")[:8192])
    if SOURCE.read_bytes() != source:
        raise RuntimeError("Native selected operator source changed during build")
    manifest = {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "work_model": WORK_MODEL,
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "source_lf_sha256": hashlib.sha256(source.replace(b"\r\n", b"\n")).hexdigest(),
        "executable": executable.name,
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "compiler": compiler,
        "compiler_version": banner,
        "flags": flags,
        "platform": platform.platform(),
    }
    path = directory / "native-selected-manifest.json"
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--sanitize", action="store_true",
                        help="POSIX AddressSanitizer and UBSan build")
    args = parser.parse_args()
    print(build(args.output_dir, sanitize=args.sanitize))


if __name__ == "__main__":
    main()
