"""Explicitly build the project-owned helper; no installation or binary vendoring.

Windows: run in an installed x64 Visual C++ developer environment.
POSIX: an installed cc compiler is required. Outputs stay in the chosen build dir.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

from pokerlab.native_preflop_equity import PROTOCOL, SOURCE, _source_hashes


def build(output_directory):
    compiler_name = 'cl' if os.name == 'nt' else 'cc'
    compiler = shutil.which(compiler_name)
    if compiler is None:
        raise RuntimeError('Native compiler unavailable. Use an installed x64 MSVC '
                           'developer environment on Windows or cc on POSIX; no automatic install.')
    compiler = str(Path(compiler).resolve())
    directory = Path(output_directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    executable = directory / ('native-preflop-equity.exe' if os.name == 'nt' else 'native-preflop-equity')
    if directory == SOURCE.parent or executable.is_symlink():
        raise ValueError('Use a separate local build directory and regular output file.')
    if os.name == 'nt':
        flags = ['/nologo', '/std:c11', '/O2', '/W4', '/WX', '/MT', '/D_CRT_SECURE_NO_WARNINGS']
        command = [compiler, *flags, str(SOURCE), '/Fo' + str(directory / 'preflop_equity.obj'),
                   '/Fe' + str(executable)]
        version_command = [compiler]
    else:
        flags = ['-std=c11', '-O3', '-Wall', '-Wextra', '-Werror', '-pedantic']
        command = [compiler, *flags, str(SOURCE), '-o', str(executable)]
        version_command = [compiler, '--version']
    # MSVC accepts hidden extra options through these variables; use only the
    # recorded flags. Keep SDK/include/library setup from the developer shell.
    build_environment = os.environ.copy()
    for key in ('CL', '_CL_', 'LINK', '_LINK_'):
        build_environment.pop(key, None)
    version = subprocess.run(version_command, capture_output=True, timeout=30,
                             check=False, env=build_environment)
    banner = (version.stdout + version.stderr).decode(errors='replace').strip()[:4096]
    raw_hash, lf_hash = _source_hashes()
    completed = subprocess.run(command, capture_output=True, timeout=120,
                               check=False, cwd=directory, env=build_environment)
    if completed.returncode:
        raise RuntimeError('Native compilation failed: '
                           + (completed.stdout + completed.stderr).decode(errors='replace')[:8192])
    if _source_hashes() != (raw_hash, lf_hash):
        raise RuntimeError('Native source changed during compilation; rebuild explicitly.')
    manifest = {'schema_version': 1, 'protocol': PROTOCOL, 'source_sha256': raw_hash,
                'source_lf_sha256': lf_hash, 'executable': executable.name,
                'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
                'compiler': compiler, 'compiler_version': banner,
                'flags': flags, 'platform': platform.platform()}
    manifest_path = directory / 'native-preflop-manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return manifest_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    print(build(args.output_dir))


if __name__ == '__main__':
    main()
