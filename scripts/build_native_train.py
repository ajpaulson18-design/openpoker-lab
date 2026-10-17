"""Build the bounded project-owned finite-tree CFR trainer explicitly.

Windows requires an installed x64 MSVC developer environment. POSIX uses an
installed C compiler. No compiler is installed implicitly and output stays in
the caller-selected build directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'native' / 'fixed_street_train.c'
PROTOCOL = 'OPENPOKER_FIXED_TRAIN_V1'
WORK_MODEL = 'native-fixed-street-work-v1'


def _source_hashes():
    raw = SOURCE.read_bytes()
    return (hashlib.sha256(raw).hexdigest(),
            hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest())


def build(output_directory):
    compiler_name = 'cl' if os.name == 'nt' else 'cc'
    compiler = shutil.which(compiler_name)
    if compiler is None:
        raise RuntimeError('Native compiler unavailable. Use installed x64 MSVC on Windows or cc on POSIX; no automatic install.')
    compiler = str(Path(compiler).resolve())
    directory = Path(output_directory).resolve()
    if directory == ROOT or ROOT in directory.parents:
        raise ValueError('Use a separate local build directory outside the source tree.')
    directory.mkdir(parents=True, exist_ok=True)
    executable = directory / ('native-fixed-street-train.exe' if os.name == 'nt'
                              else 'native-fixed-street-train')
    if executable.is_symlink():
        raise ValueError('Refusing to replace a symlink output.')

    if os.name == 'nt':
        flags = ['/nologo', '/std:c11', '/O2', '/W4', '/WX', '/MT',
                 '/D_CRT_SECURE_NO_WARNINGS', '/fp:strict']
        object_path = directory / 'fixed_street_train.obj'
        command = [compiler, *flags, str(SOURCE), '/Fo' + str(object_path),
                   '/Fe' + str(executable)]
        version_command = [compiler]
    else:
        flags = ['-std=c11', '-O3', '-Wall', '-Wextra', '-Werror', '-pedantic',
                 '-ffp-contract=off']
        command = [compiler, *flags, str(SOURCE), '-lm', '-o', str(executable)]
        version_command = [compiler, '--version']

    build_environment = os.environ.copy()
    for key in ('CL', '_CL_', 'LINK', '_LINK_'):
        build_environment.pop(key, None)
    version = subprocess.run(version_command, capture_output=True, timeout=30,
                             check=False, env=build_environment)
    banner = (version.stdout + version.stderr).decode(errors='replace').strip()[:4096]
    source_before = _source_hashes()
    completed = subprocess.run(command, capture_output=True, timeout=120,
                               check=False, cwd=directory, env=build_environment)
    if completed.returncode:
        raise RuntimeError('Native compilation failed: '
                           + (completed.stdout + completed.stderr).decode(errors='replace')[:8192])
    if _source_hashes() != source_before:
        raise RuntimeError('Native source changed during compilation; rebuild explicitly.')

    manifest = {
        'schema_version': 1,
        'protocol': PROTOCOL,
        'work_model': WORK_MODEL,
        'source_sha256': source_before[0],
        'source_lf_sha256': source_before[1],
        'executable': executable.name,
        'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
        'compiler': compiler,
        'compiler_version': banner,
        'flags': flags,
        'platform': platform.platform(),
    }
    manifest_path = directory / 'native-train-manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True,
                                        allow_nan=False) + '\n', encoding='utf-8')
    return manifest_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    print(build(args.output_dir))


if __name__ == '__main__':
    main()
