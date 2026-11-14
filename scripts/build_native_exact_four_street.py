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
TARGETS = {
    "dyadic-policy-division-controls": ("native-dyadic-policy-division-controls", (
        "tests/native/dyadic_policy_division_controls.cpp", "native/dyadic_policy_division.hpp", "native/exact_binary64.hpp")),
    "factored-dyadic-controls": ("native-factored-dyadic-controls", (
        "tests/native/factored_dyadic_controls.cpp", "native/factored_dyadic.hpp", "native/factored_execution.hpp", "native/exact_binary64.hpp")),
    "packed-signed-update-controls": ("native-packed-signed-update-controls", (
        "tests/native/packed_signed_update_controls.cpp", "native/packed_signed_update.hpp", "native/exact_binary64.hpp")),
    "converter": ("native-exact-binary64-probe", (
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
    "active-frame": ("native-exact-active-frame-controls", (
        "tests/native/exact_active_frame_controls.cpp",
        "tests/native/exact_public_history_index_controls.cpp",
        "native/exact_public_history_index.hpp", "native/exact_public_graph.hpp",
        "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "active-routing": ("native-exact-active-routing-controls", (
        "tests/native/exact_active_routing_controls.cpp",
        "tests/native/exact_indexed_routing_controls.cpp",
        "native/exact_indexed_routing.hpp", "native/exact_public_history_index.hpp",
        "native/exact_public_graph.hpp", "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "fold-classes": ("native-exact-fold-class-controls", (
        "tests/native/exact_fold_class_controls.cpp", "native/exact_selected_cfr.hpp",
        "native/exact_public_graph.hpp", "native/exact_indexed_routing.hpp",
        "native/exact_public_history_index.hpp", "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "history-index": ("native-exact-history-index-controls", (
        "tests/native/exact_public_history_index_controls.cpp", "native/exact_public_history_index.hpp",
        "tests/native/exact_history_index_schedule_controls.cpp",
        "native/exact_public_graph.hpp", "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "virtual-frozen-update-controls": ("native-virtual-frozen-update-controls", (
        "native/virtual_frozen_update_controls.cpp", "native/virtual_frozen_update.hpp",
        "native/virtual_frozen_walk.hpp", "native/virtual_frozen_game.hpp",
        "native/virtual_frozen_history.hpp", "native/virtual_frozen_policy.hpp",
        "native/virtual_frozen_proposal.hpp", "native/virtual_frozen_common_denominator.hpp",
        "native/full_deck_public_chance.hpp", "native/virtual_betting_template.hpp",
        "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "virtual-frozen-update": ("native-virtual-frozen-update-probe", (
        "native/virtual_frozen_update_probe.cpp", "native/virtual_frozen_update.hpp",
        "native/virtual_frozen_walk.hpp", "native/virtual_frozen_game.hpp",
        "native/virtual_frozen_history.hpp", "native/virtual_frozen_policy.hpp",
        "native/virtual_frozen_proposal.hpp", "native/virtual_frozen_common_denominator.hpp",
        "native/full_deck_public_chance.hpp", "native/virtual_betting_template.hpp",
        "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "virtual-betting-template-controls": ("native-virtual-betting-template-controls", (
        "tests/native/virtual_betting_template_controls.cpp", "native/virtual_betting_template.hpp",
        "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "virtual-betting-template": ("native-virtual-betting-template-probe", (
        "native/virtual_betting_template_probe.cpp", "native/virtual_betting_template.hpp",
        "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "virtual-dyadic-training": ("native-virtual-dyadic-training-probe", (
        "native/virtual_dyadic_training_probe.cpp", "native/virtual_dyadic_training.hpp",
        "native/prepared_public_chance.hpp", "native/virtual_dyadic_history.hpp", "native/virtual_dyadic_state.hpp",
        "native/virtual_dyadic_paged_image.hpp", "native/factored_dyadic.hpp", "native/factored_execution.hpp", "native/packed_signed_update.hpp",
        "native/dyadic_policy.hpp", "native/dyadic_policy_division.hpp", "native/virtual_betting_template.hpp", "native/full_deck_public_chance.hpp",
        "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "virtual-dyadic-history-controls": ("native-virtual-dyadic-history-controls", (
        "tests/native/virtual_dyadic_history_controls.cpp", "native/virtual_dyadic_history.hpp",
        "native/virtual_betting_template.hpp", "native/full_deck_public_chance.hpp",
        "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "virtual-dyadic-state-controls": ("native-virtual-dyadic-state-controls", (
        "tests/native/virtual_dyadic_state_controls.cpp", "native/virtual_dyadic_state.hpp",
        "native/virtual_dyadic_paged_image.hpp", "native/factored_dyadic.hpp", "native/factored_execution.hpp", "native/packed_signed_update.hpp",
        "native/dyadic_policy.hpp", "native/dyadic_policy_division.hpp", "native/virtual_dyadic_history.hpp", "native/virtual_betting_template.hpp",
        "native/full_deck_public_chance.hpp", "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "prepared-public-chance-controls": ("native-prepared-public-chance-controls", (
        "tests/native/prepared_public_chance_controls.cpp", "native/prepared_public_chance.hpp",
        "native/full_deck_public_chance.hpp", "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "dyadic-policy-controls": ("native-dyadic-policy-controls", (
        "tests/native/dyadic_policy_controls.cpp", "native/dyadic_policy.hpp", "native/dyadic_policy_division.hpp", "native/exact_binary64.hpp")),
    "full-deck-prefix-fold-controls": ("native-full-deck-prefix-fold-controls", (
        "tests/native/full_deck_prefix_fold_controls.cpp", "native/full_deck_public_chance.hpp",
        "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "full-deck-exact-reach-controls": ("native-full-deck-exact-reach-controls", (
        "tests/native/full_deck_exact_reach_controls.cpp", "native/full_deck_public_chance.hpp",
        "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp")),
    "full-deck-chance": ("native-full-deck-public-chance-probe", (
        "native/full_deck_public_chance_probe.cpp", "native/full_deck_public_chance.hpp",
        "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp",
        "scripts/build_native_full_deck_public_chance.py")),
    "full-deck-chance-preflight": ("native-full-deck-public-chance-preflight-controls", (
        "tests/native/full_deck_public_chance_preflight_controls.cpp",
        "native/full_deck_public_chance_probe.cpp", "native/full_deck_public_chance.hpp",
        "native/exact_selected_kernel.hpp", "native/exact_binary64.hpp",
        "scripts/build_native_full_deck_public_chance.py"))}


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
    compiler_sha256 = _hash(_bounded_read(Path(compiler),64 * 1024 * 1024))
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
    _need(_hash(_bounded_read(Path(compiler),64 * 1024 * 1024)) == compiler_sha256,
          "Native exact compiler changed during compilation")
    manifest = {"contract": "native-exact-build-v1", "target": target,
        "scope": ("Bounded exact policy-grid division controls."
                  if target == "dyadic-policy-division-controls" else "Bounded exact factored value arithmetic controls."
                  if target == "factored-dyadic-controls" else "Bounded packed signed limb updates."
                  if target == "packed-signed-update-controls" else "Converter boundary test helper only; not a poker kernel/trainer or accepted native solving backend."
                  if target == "converter" else "Exact selected vector test helper only; not a trainer or accepted native solving backend."
                  if target == "kernel" else "Graph-only public-history index conformance helper; no trainer integration or capacity admission."
                  if target == "history-index" else "Numeric Q/prefix routing conformance helper; no trainer or larger-capacity acceptance."
                  if target == "indexed-routing" else "Active traversal-frame conformance helper only; no native trainer or whole-game acceptance."
                  if target == "active-frame" else "Active-frame numeric routing conformance helper only; no trainer or whole-game acceptance."
                  if target == "active-routing" else "Exact fold-class callback/coupled trainer conformance helper; no public protocol or capacity acceptance."
                  if target == "fold-classes" else "Full-deck public-chance exact probability probe only; no sampler, trainer, or whole-game acceptance."
                  if target == "full-deck-chance" else "Full-deck public-chance preflight controls only; no numerical-kernel or solver acceptance."
                  if target == "full-deck-chance-preflight" else "Exact rational opponent-reach component controls only; no sampler, changing-policy trainer or whole-game acceptance."
                  if target == "full-deck-exact-reach-controls" else "Exact visible-prefix fold payoff controls only; changing-policy training and quality remain open."
                  if target == "full-deck-prefix-fold-controls" else "Prepared q=1 public-chance contraction controls only; no cumulative whole-game training or quality admission."
                  if target == "prepared-public-chance-controls" else "Compact literal-history cursor controls only; persistent policy/training/quality acceptance remains separate."
                  if target == "virtual-dyadic-history-controls" else "Persistent exact dyadic state and staged sweep controls only; whole poker training and quality remain open."
                  if target == "virtual-dyadic-state-controls" else "Explicit PROOF9 q=1 two-sweep training candidate; whole-game source acceptance and saved policy quality are separate gates."
                  if target == "virtual-dyadic-training" else "Finite dyadic policy allocation controls only; cumulative training admission and quality remain open."
                  if target == "dyadic-policy-controls" else "Card-free virtual betting template probe only; no chance, strategy, trainer or solver acceptance."
                  if target == "virtual-betting-template" else "Card-free template rounding and admission controls only; no solver acceptance."
                  if target == "virtual-betting-template-controls" else "PROOF9/v1 exact frozen-update preflight and value probe only; no RNG, training, generic solver backend or quality acceptance."
                  if target == "virtual-frozen-update" else "Frozen-update arithmetic, admission, ownership and bounded zero-target controls; no full-game acceptance."
                  if target == "virtual-frozen-update-controls" else "Explicit native exact four-street engine candidate; acceptance requires whole-game policy proof."),
        "source_sha256": {name: _hash(raw) for name, raw in raw_sources.items()},
        "source_lf_sha256": {name: _hash(raw.replace(b"\r\n", b"\n")) for name, raw in raw_sources.items() if not name.endswith(".zip")},
        "dependency_commit": dependency["commit"], "dependency_archive_sha256": HEADER_ARCHIVE_SHA256,
        "dependency_manifest_sha256": DEPENDENCY_MANIFEST_SHA256, "dependency_headers": len(headers),
        "license": "BSL-1.0", "compiler": compiler, "compiler_sha256": compiler_sha256,
        "system_build_inputs": "SDK/standard headers, linker/libraries/runtime are environmental inputs, not exhaustively byte-attested; bit reproducibility unproven",
        "toolchain_environment": {key: environment[key] for key in ("INCLUDE", "LIB", "LIBPATH", "VCINSTALLDIR", "VCToolsInstallDir", "WindowsSdkDir", "WindowsSDKVersion") if key in environment},
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
