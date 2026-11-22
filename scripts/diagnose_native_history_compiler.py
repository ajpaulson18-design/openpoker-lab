"""Capture bounded MSVC front-end and optimization compile diagnostics.

This is a diagnostic, not a build or test. It never links or runs the control
program. Each phase reauthenticates the committed history-control source
closure in a fresh output directory; raw source snapshots are saved for evidence.
The compiler reads the checked-out files after their hashes are verified.

The phases use Microsoft's documented `/Zs` syntax-only, `/c` compile-only,
`/O2` optimized, and `/Od` unoptimized options:
https://learn.microsoft.com/en-us/cpp/build/reference/zs-syntax-check-only
https://learn.microsoft.com/en-us/cpp/build/reference/c-compile-without-linking
https://learn.microsoft.com/en-us/cpp/build/reference/o1-o2-minimize-size-maximize-speed
https://learn.microsoft.com/en-us/cpp/build/reference/od-disable-debug
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TARGET = "virtual-dyadic-history-controls"
TIMEOUT_SECONDS = 180
MAX_STREAM_BYTES = 4 * 1024 * 1024
PHASES = ("syntax-only", "compile-o2", "compile-od")
CLOSURE_NAMES = (
    "tests/native/virtual_dyadic_history_controls.cpp",
    "native/virtual_dyadic_history.hpp",
    "native/virtual_betting_template.hpp",
    "native/full_deck_public_chance.hpp",
    "native/exact_selected_kernel.hpp",
    "native/exact_binary64.hpp",
    "scripts/build_native_exact_four_street.py",
    "scripts/diagnose_native_history_compiler.py",
    ".github/workflows/history-compiler-diagnostic.yml",
    "third_party/boost-multiprecision-1.92.0/manifest.json",
    "third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt",
    "third_party/boost-multiprecision-1.92.0/headers.zip",
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _closure_names():
    return CLOSURE_NAMES


def _need(condition, message):
    if not condition:
        raise RuntimeError(message)


def _bounded_read(path, ceiling):
    path = Path(path)
    _need(path.is_file() and not path.is_symlink() and path.stat().st_size <= ceiling,
          "Missing, linked or oversized compiler diagnostic input: " + str(path))
    raw = path.read_bytes()
    _need(len(raw) <= ceiling, "Compiler diagnostic input grew while reading")
    return raw


def _git(*arguments, timeout=30):
    result = subprocess.run(
        ["git", *arguments], cwd=ROOT, capture_output=True, timeout=timeout, check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"git {' '.join(arguments)} failed ({result.returncode}): "
            f"{(result.stderr or result.stdout).decode(errors='replace')[:2000]}"
        )
    return result.stdout


def _git_text(raw, label):
    try:
        return raw.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"Non-ASCII Git {label}") from exc


def _normalize_uniform_text(raw, label):
    crlf = raw.count(b"\r\n")
    bare_lf = raw.count(b"\n") - crlf
    bare_cr = raw.count(b"\r") - crlf
    if bare_cr or (crlf and bare_lf):
        raise RuntimeError(f"Mixed or bare carriage return in tracked text source: {label}")
    return raw.replace(b"\r\n", b"\n")


def _source_identity():
    """Authenticate the compiler closure to a clean tracked HEAD snapshot."""
    names = _closure_names()
    head = _git_text(_git("rev-parse", "--verify", "HEAD^{commit}"), "HEAD")
    if len(head) != 40 or any(character not in "0123456789abcdef" for character in head.lower()):
        raise RuntimeError("Git HEAD is not a full 40-character commit ID")
    branch = _git_text(_git("branch", "--show-current"), "branch")
    tree = _git("ls-tree", "-r", "-z", "--full-tree", head, "--", *names)
    tracked = {}
    for item in tree.split(b"\0"):
        if not item:
            continue
        metadata, raw_name = item.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split()
        name = raw_name.decode("utf-8")
        if kind != "blob" or mode not in ("100644", "100755"):
            raise RuntimeError(f"Compiler closure entry is not a regular tracked blob: {name}")
        tracked[name] = {"mode": mode, "blob": object_id}
    if set(tracked) != set(names):
        missing = sorted(set(names) - set(tracked))
        extra = sorted(set(tracked) - set(names))
        raise RuntimeError(f"Git HEAD closure mismatch; missing={missing}, extra={extra}")
    status = _git("status", "--porcelain=v1", "-z", "--untracked-files=no", "--", *names)
    entries = []
    for name in names:
        raw = _bounded_read(ROOT / name, 2 * 1024 * 1024)
        blob_raw = _git("cat-file", "blob", tracked[name]["blob"])
        if len(blob_raw) > 2 * 1024 * 1024:
            raise RuntimeError(f"Tracked compiler source exceeds its bound: {name}")
        is_text = Path(name).suffix.lower() in {".cpp", ".hpp", ".py", ".yml", ".yaml", ".txt", ".json"}
        if is_text:
            matches = _normalize_uniform_text(raw, name) == _normalize_uniform_text(blob_raw, name + " Git blob")
            comparison = "uniform-line-endings"
        else:
            matches = raw == blob_raw
            comparison = "raw-bytes"
        entries.append({
            "path": name,
            "mode": tracked[name]["mode"],
            "git_blob_oid": tracked[name]["blob"],
            "git_blob_sha256": _sha(blob_raw),
            "worktree_raw_sha256": _sha(raw),
            "worktree_bytes": len(raw),
            "comparison": comparison,
            "matches_tracked_blob": matches,
        })
    identity = {
        "head": head,
        "branch": branch,
        "closure_paths": list(names),
        "limited_status_clean": not status,
        "limited_status_raw": status.decode("utf-8", errors="replace"),
        "files": entries,
    }
    identity["snapshot_sha256"] = _sha(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())
    return identity


def _require_trusted_identity(identity):
    _need(identity["limited_status_clean"], "Compiler source closure has tracked worktree changes")
    _need(all(item["matches_tracked_blob"] for item in identity["files"]),
          "Compiler source closure differs from its tracked HEAD blobs")


def _save_source_snapshot(output, label, identity):
    source_root = output / "source"
    raw_root = source_root / f"raw-{label}"
    raw_root.mkdir(parents=True, exist_ok=True)
    for item in identity["files"]:
        name = item["path"]
        raw = _bounded_read(ROOT / name, 2 * 1024 * 1024)
        _need(_sha(raw) == item["worktree_raw_sha256"],
              f"Source changed while saving evidence copy: {name}")
        destination = raw_root / Path(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    (source_root / f"HEAD-{label}.txt").write_text(identity["head"] + "\n", encoding="ascii")
    (source_root / f"tracked-blob-map-{label}.json").write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _compiler_hash(path):
    return _sha(_bounded_read(path, 64 * 1024 * 1024))


def _clean_environment(directory):
    environment = os.environ.copy()
    for key in ("CL", "_CL_", "LINK", "_LINK_", "CPATH", "CPLUS_INCLUDE_PATH", "C_INCLUDE_PATH"):
        environment.pop(key, None)
    environment["TEMP"] = environment["TMP"] = str(directory)
    return environment


def _capture(command, directory, environment, *, timeout_seconds):
    """Run one compiler command with bounded time and captured file streams."""
    stdout_path = directory / "stdout.bin"
    stderr_path = directory / "stderr.bin"
    started = time.monotonic()
    actual_exit_observed = False
    timed_out = False
    output_limited = False
    launch_error = None
    returncode = None
    killed_returncode = None
    with stdout_path.open("xb") as stdout_file, stderr_path.open("xb") as stderr_file:
        try:
            process = subprocess.Popen(
                command, cwd=directory, env=environment,
                stdout=stdout_file, stderr=stderr_file, shell=False,
            )
        except OSError as exc:
            launch_error = f"{type(exc).__name__}: {exc}"
        else:
            deadline = started + timeout_seconds
            while True:
                observed = process.poll()
                if observed is not None:
                    actual_exit_observed = True
                    returncode = observed
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    process.kill()
                    killed_returncode = process.wait()
                    break
                if stdout_path.stat().st_size > MAX_STREAM_BYTES or stderr_path.stat().st_size > MAX_STREAM_BYTES:
                    output_limited = True
                    process.kill()
                    killed_returncode = process.wait()
                    break
                time.sleep(0.025)
    duration = time.monotonic() - started
    stream_truncated = {}
    observed_bytes = {}
    for path in (stdout_path, stderr_path):
        size = path.stat().st_size
        observed_bytes[path.name] = size
        stream_truncated[path.name] = size > MAX_STREAM_BYTES
        if size > MAX_STREAM_BYTES:
            output_limited = True
            with path.open("r+b") as stream:
                stream.truncate(MAX_STREAM_BYTES)
    saved_hashes = {
        path.name: _sha(path.read_bytes())
        for path in (stdout_path, stderr_path)
    }
    status = "launch-error" if launch_error else "timed-out" if timed_out else \
             "output-limit" if output_limited else "exited" if actual_exit_observed else "unknown"
    return {
        "command": command,
        "status": status,
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "output_limited": output_limited,
        "actual_exit_observed": actual_exit_observed,
        "returncode": returncode,
        "returncode_after_termination": killed_returncode,
        "launch_error": launch_error,
        "duration_seconds": duration,
        "stdout_file": stdout_path.name,
        "stderr_file": stderr_path.name,
        "stdout_bytes_observed_before_truncate": observed_bytes[stdout_path.name],
        "stderr_bytes_observed_before_truncate": observed_bytes[stderr_path.name],
        "stdout_bytes_saved": stdout_path.stat().st_size,
        "stderr_bytes_saved": stderr_path.stat().st_size,
        "stdout_saved_sha256": saved_hashes[stdout_path.name],
        "stderr_saved_sha256": saved_hashes[stderr_path.name],
        "stream_truncated": stream_truncated,
    }


def _phase_flags(include_directory, optimization):
    # Keep the normal target's language, warning, exception, CRT, FP and
    # Boost options. Only the explicit optimization and phase options vary.
    return [
        "/nologo", "/std:c++20", optimization, "/W4", "/WX", "/EHsc", "/MT", "/fp:strict",
        "/DBOOST_MP_STANDALONE", "/I" + str(include_directory),
    ]


def _run_phase(name, output, compiler, compiler_sha256, source_path, headers, trusted_builder):
    directory = output / name
    directory.mkdir()
    include_directory = trusted_builder._extract(directory, headers)
    source_before = _source_identity()
    _require_trusted_identity(source_before)
    compiler_before = _compiler_hash(compiler)
    flags = _phase_flags(include_directory, "/O2" if name != "compile-od" else "/Od")
    if name == "syntax-only":
        phase_options = ["/Zs"]
        tail = [str(source_path)]
    else:
        phase_options = ["/c"]
        obj_path = directory / "native-virtual-dyadic-history-controls.obj"
        tail = [str(source_path), "/Fo" + str(obj_path)]
    command = [str(compiler), *flags, *phase_options, *tail]
    environment = _clean_environment(directory)
    result = _capture(command, directory, environment, timeout_seconds=TIMEOUT_SECONDS)
    source_after = _source_identity()
    compiler_after = _compiler_hash(compiler)
    result.update({
        "phase": name,
        "optimization_option": "/O2" if name != "compile-od" else "/Od",
        "source_head_before": source_before["head"],
        "source_head_after": source_after["head"],
        "source_snapshot_sha256_before": source_before["snapshot_sha256"],
        "source_snapshot_sha256_after": source_after["snapshot_sha256"],
        "source_closure_unchanged": source_before["snapshot_sha256"] == source_after["snapshot_sha256"],
        "compiler_sha256_expected": compiler_sha256,
        "compiler_sha256_before": compiler_before,
        "compiler_sha256_after": compiler_after,
        "compiler_unchanged": compiler_before == compiler_after == compiler_sha256,
    })
    (directory / "phase.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def diagnose(output_directory):
    if os.name != "nt":
        raise RuntimeError("This bounded diagnostic is Windows/MSVC-only")
    output = Path(output_directory).resolve()
    _need(output != ROOT and ROOT not in output.parents,
          "Diagnostic output must be outside the source checkout")
    _need(not output.exists() and not output.is_symlink(),
          "Diagnostic output must be a fresh, unlinked directory")

    # Authenticate the current tracked source closure and pinned headers before
    # extraction or compiler execution. Do not consume a stored build command.
    source_before = _source_identity()
    _require_trusted_identity(source_before)
    # Import the existing extractor only after independently confirming that
    # its bytes are the clean tracked source recorded above.
    from scripts import build_native_exact_four_street as trusted_builder
    source_after_import = _source_identity()
    _require_trusted_identity(source_after_import)
    _need(source_before["snapshot_sha256"] == source_after_import["snapshot_sha256"],
          "Compiler source closure changed while loading the pinned builder")
    dependency, headers = trusted_builder._dependency()
    output.mkdir(parents=True)
    _save_source_snapshot(output, "before", source_before)
    compiler_value = shutil.which("cl")
    _need(compiler_value is not None, "MSVC cl.exe is unavailable")
    compiler = Path(compiler_value).resolve()
    compiler_sha256 = _compiler_hash(compiler)

    environment = _clean_environment(output)
    version_result = subprocess.run(
        [str(compiler)], cwd=output, env=environment, capture_output=True,
        timeout=30, check=False,
    )
    version_bytes = version_result.stdout + version_result.stderr
    (output / "compiler-version.log").write_bytes(version_bytes[:MAX_STREAM_BYTES])
    version = {
        "command": [str(compiler)],
        "actual_exit_observed": True,
        "returncode": version_result.returncode,
        "stdout_bytes": len(version_result.stdout),
        "stderr_bytes": len(version_result.stderr),
        "compiler_sha256_before": compiler_sha256,
        "compiler_sha256_after_version": _compiler_hash(compiler),
        "version_output_sha256": _sha(version_bytes),
    }
    (output / "compiler-version.json").write_text(json.dumps(version, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Extract the already-pinned third-party closure separately into each
    # fresh phase directory using the existing builder's safe extractor.
    phase_results = []
    phase_source = Path("tests/native/virtual_dyadic_history_controls.cpp")
    for name in PHASES:
        result = _run_phase(name, output, compiler, compiler_sha256, ROOT / phase_source, headers,
                            trusted_builder)
        phase_results.append(result)
        if not result["source_closure_unchanged"] or not result["compiler_unchanged"]:
            break

    source_after = _source_identity()
    _save_source_snapshot(output, "after", source_after)
    complete = len(phase_results) == len(PHASES)
    record = {
        "contract": "native-history-compiler-diagnostic-v1",
        "scope": "Three non-linking compiler diagnostics for one authenticated test translation unit; no executable or native runtime is produced.",
        "source_closure_before": source_before,
        "source_closure_after": source_after,
        "source_closure_unchanged": source_before["snapshot_sha256"] == source_after["snapshot_sha256"],
        "dependency_commit": dependency["commit"],
        "dependency_manifest_sha256": trusted_builder.DEPENDENCY_MANIFEST_SHA256,
        "dependency_archive_sha256": trusted_builder.HEADER_ARCHIVE_SHA256,
        "dependency_header_count": len(headers),
        "compiler": str(compiler),
        "compiler_sha256": compiler_sha256,
        "compiler_version": version,
        "phases": phase_results,
        "all_phases_recorded": complete,
        "no_retries": True,
        "outcome": "observed" if complete else "incomplete-source-or-compiler-drift",
    }
    (output / "diagnostic.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    record = diagnose(args.output_dir)
    print(json.dumps(record, indent=2, sort_keys=True))
    if not record["all_phases_recorded"] or not record["source_closure_unchanged"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
