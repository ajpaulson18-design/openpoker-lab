"""Source-authenticated offline build of the new exact native prerequisites.

The converter target is a boundary test helper, not an accepted poker backend.
All third-party headers are pinned source bytes; no package/system install or
network fetch occurs. Builds and extracted headers must stay outside the repo.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCY = ROOT / "third_party/boost-multiprecision-1.92.0"
DEPENDENCY_MANIFEST_SHA256 = "4d6f33341887e35a0c29e9dc5da2a326d546427940c2b16b485db0c61b042555"
HEADER_ARCHIVE_SHA256 = "33c422ab3ebfa9e86c62f41f372ec2b9c2cefa303f1885391aa4d8250ef2f831"
LICENSE_SHA256 = "c9bff75738922193e67fa726fa225535870d2aa1059f91452c411736284ad566"
TARGETS = {"converter": ("native-exact-binary64-probe", (
    "native/exact_binary64_probe.cpp", "native/exact_binary64.hpp")),
    "kernel": ("native-exact-selected-vectors", (
        "native/exact_selected_kernel_probe.cpp", "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "engine": ("native-exact-four-street-train", (
        "native/exact_four_street_train.cpp", "native/exact_public_graph.hpp", "native/exact_selected_cfr.hpp",
        "native/exact_public_history_index.hpp", "native/exact_indexed_routing.hpp",
        "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "indexed-routing": ("native-exact-indexed-routing-controls", (
        "tests/native/exact_indexed_routing_controls.cpp", "native/exact_indexed_routing.hpp",
        "native/exact_public_history_index.hpp", "native/exact_public_graph.hpp",
        "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "history-index": ("native-exact-history-index-controls", (
        "tests/native/exact_public_history_index_controls.cpp", "native/exact_public_history_index.hpp",
        "tests/native/exact_history_index_schedule_controls.cpp",
        "native/exact_public_graph.hpp", "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp"))}


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _bounded_read(path, ceiling):
    _need(path.is_file() and not path.is_symlink() and path.stat().st_size <= ceiling,
          "Missing, linked or oversized native build input: " + str(path))
    raw = path.read_bytes()
    _need(len(raw) <= ceiling, "Native build input grew during reading")
    return raw


def _dependency():
    manifest_raw = _bounded_read(DEPENDENCY / "manifest.json", 128 * 1024)
    license_raw = _bounded_read(DEPENDENCY / "LICENSE_1_0.txt", 16 * 1024)
    archive_raw = _bounded_read(DEPENDENCY / "headers.zip", 1024 * 1024)
    _need(_hash(manifest_raw) == DEPENDENCY_MANIFEST_SHA256 and _hash(archive_raw) == HEADER_ARCHIVE_SHA256 and
          _hash(license_raw) == LICENSE_SHA256, "Pinned native dependency/license changed")
    manifest = json.loads(manifest_raw)
    _need(manifest["contract"] == "pinned-boost-multiprecision-header-package-v1" and
          manifest["license"] == "BSL-1.0" and manifest["header_count"] == 198 and
          manifest["header_bytes"] == 3_057_611, "Native dependency inventory changed")
    headers = {}
    from io import BytesIO
    with zipfile.ZipFile(BytesIO(archive_raw)) as archive:
        entries = archive.infolist()
        _need(len(entries) == manifest["header_count"] and len(entries) <= 256, "Header inventory capacity exceeded")
        _need(sum(item.file_size for item in entries) == manifest["header_bytes"] <= 4 * 1024 * 1024,
              "Header expanded-byte capacity exceeded")
        lowered = set()
        for item in entries:
            name = item.filename
            _need(not item.is_dir() and name.startswith("boost/") and not PurePosixPath(name).is_absolute() and
                  ".." not in PurePosixPath(name).parts and "\\" not in name and ":" not in name and
                  name not in headers and name.lower() not in lowered and
                  (item.external_attr >> 16) & 0o170000 != 0o120000, "Unsafe/duplicate native header path")
            raw = archive.read(item)
            _need(len(raw) == item.file_size and _hash(raw) == manifest["headers_sha256"].get(name),
                  "Header byte identity changed: " + name)
            headers[name] = raw
            lowered.add(name.lower())
    _need(set(headers) == set(manifest["headers_sha256"]), "Incomplete native header closure")
    return manifest, headers


def _extract(directory, headers):
    include = directory / "boost-include"
    _need(not include.is_symlink(), "Refusing linked native header cache")
    include.mkdir(exist_ok=True)
    root = include.resolve()
    for name, raw in headers.items():
        target = include / name
        _need(root in target.resolve().parents, "Native header escaped build directory")
        parent = target.parent
        while parent != include:
            _need(not parent.is_symlink(), "Linked native include subdirectory")
            parent = parent.parent
        target.parent.mkdir(parents=True, exist_ok=True)
        _need(not target.is_symlink(), "Refusing linked native header file")
        if target.exists():
            _need(_bounded_read(target, 512 * 1024) == raw, "Existing native header cache changed")
        else:
            with target.open("xb") as stream:
                stream.write(raw)
    for count, path in enumerate(include.rglob("*"), 1):
        _need(count <= 512, "Native include cache entry capacity exceeded")
        _need(not path.is_symlink(), "Linked native include cache entry")
        if path.is_file():
            _need(path.relative_to(include).as_posix() in headers, "Unexpected native header cache entry")
    return include


def build(output_directory, *, target="converter", sanitize=False):
    _need(type(target) is str and target in TARGETS, "Unsupported native exact build target")
    _need(type(sanitize) is bool, "Native exact sanitize selection must be boolean")
    directory = Path(output_directory).resolve()
    _need(directory != ROOT and ROOT not in directory.parents, "Native exact builds must be outside the source checkout")
    if sanitize and os.name == "nt":
        raise ValueError("Native exact sanitizers require a POSIX compiler")
    compiler = shutil.which("cl" if os.name == "nt" else "c++")
    if compiler is None:
        raise RuntimeError("Installed C++20 compiler unavailable; no automatic installation")
    compiler = str(Path(compiler).resolve())
    helper, sources = TARGETS[target]
    source_names = (*sources, "scripts/build_native_exact_four_street.py",
        "third_party/boost-multiprecision-1.92.0/manifest.json",
        "third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt",
        "third_party/boost-multiprecision-1.92.0/headers.zip")
    raw_sources = {name: _bounded_read(ROOT / name, 2 * 1024 * 1024) for name in source_names}
    dependency, headers = _dependency()
    directory.mkdir(parents=True, exist_ok=True)
    include = _extract(directory, headers)
    executable = directory / (helper + (".exe" if os.name == "nt" else ""))
    _need(not executable.is_symlink(), "Refusing linked native executable")
    environment = os.environ.copy()
    for key in ("CL", "_CL_", "LINK", "_LINK_", "CPATH", "CPLUS_INCLUDE_PATH", "C_INCLUDE_PATH"):
        environment.pop(key, None)
    environment["TEMP"] = environment["TMP"] = str(directory)
    if os.name == "nt":
        flags = ["/nologo", "/std:c++20", "/O2", "/W4", "/WX", "/EHsc", "/MT", "/fp:strict",
                 "/DBOOST_MP_STANDALONE", "/I" + str(include)]
        command = [compiler, *flags, str(ROOT / sources[0]),
                   "/Fo" + str(directory / (helper + ".obj")), "/Fe" + str(executable)]
        version_command = [compiler]
    else:
        flags = ["-std=c++20", "-O1" if sanitize else "-O3", "-Wall", "-Wextra", "-Werror", "-pedantic",
                 "-ffp-contract=off", "-fno-fast-math", "-DBOOST_MP_STANDALONE", "-I" + str(include)]
        if sanitize:
            flags.extend(("-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"))
        command = [compiler, *flags, str(ROOT / sources[0]), "-o", str(executable)]
        version_command = [compiler, "--version"]
    version = subprocess.run(version_command, capture_output=True, env=environment, timeout=30)
    (directory / "compiler-version.log").write_bytes(version.stdout + version.stderr)
    try:
        result = subprocess.run(command, capture_output=True, env=environment, cwd=directory, timeout=180)
    except subprocess.TimeoutExpired as exc:
        (directory / "build.log").write_bytes((exc.stdout or b"") + (exc.stderr or b""))
        (directory / "build-failure.json").write_text(json.dumps({"target": target,
            "error": "TimeoutExpired", "timeout_seconds": 180, "command": command}, indent=2), encoding="utf-8")
        raise RuntimeError("Native exact compilation timed out; partial build log preserved") from exc
    (directory / "build.log").write_bytes(result.stdout + result.stderr)
    if result.returncode:
        (directory / "build-failure.json").write_text(json.dumps({"target": target,
            "returncode": result.returncode, "command": command}, indent=2), encoding="utf-8")
        raise RuntimeError("Native exact compilation failed; preserved build.log and build-failure.json")
    _need(all(_bounded_read(ROOT / name, 2 * 1024 * 1024) == raw for name, raw in raw_sources.items()),
          "Native exact source changed during compilation")
    manifest = {"contract": "native-exact-build-v1", "target": target,
        "scope": ("Converter boundary test helper only; not a poker kernel/trainer or accepted native solving backend."
                  if target == "converter" else "Exact selected vector test helper only; not a trainer or accepted native solving backend."
                  if target == "kernel" else "Graph-only public-history index conformance helper; no trainer integration or capacity admission."
                  if target == "history-index" else "Numeric Q/prefix routing conformance helper; no trainer or larger-capacity acceptance."
                  if target == "indexed-routing" else "Explicit native exact four-street engine candidate; acceptance requires whole-game policy proof."),
        "source_sha256": {name: _hash(raw) for name, raw in raw_sources.items()},
        "source_lf_sha256": {name: _hash(raw.replace(b"\r\n", b"\n")) for name, raw in raw_sources.items() if not name.endswith(".zip")},
        "dependency_commit": dependency["commit"], "dependency_archive_sha256": HEADER_ARCHIVE_SHA256,
        "dependency_manifest_sha256": DEPENDENCY_MANIFEST_SHA256, "dependency_headers": len(headers),
        "license": "BSL-1.0", "compiler": compiler,
        "compiler_version": (version.stdout + version.stderr).decode(errors="replace"),
        "flags": flags, "platform": platform.platform(), "command": command,
        "executable": str(executable), "executable_sha256": _hash(executable.read_bytes())}
    path = directory / "native-exact-build-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**manifest, "manifest_path": str(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target", choices=tuple(TARGETS), default="converter")
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir, target=args.target, sanitize=args.sanitize), indent=2))


if __name__ == "__main__":
    main()
