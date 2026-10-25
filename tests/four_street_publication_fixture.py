"""Small committed source checkout for saved-publication integration tests.

The fixture copies the real Python source closure and three pinned data/docs
files into an isolated temporary Git repository. It contains no solver output
or generated policy artifact, and its consumers must use a synthetic policy.
"""
from contextlib import ExitStack, contextmanager
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch


PINNED_FILES = (
    "benchmarks/four-street-integration-v1.json",
    "docs/four-street-integration-protocol.md",
    "docs/river-heldout-quality-protocol.md",
)


def _copy_python_tree(source_root: Path, destination_root: Path, relative: str) -> None:
    source = source_root / relative
    for path in source.rglob("*.py"):
        target = destination_root / path.relative_to(source_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


@contextmanager
def committed_source_fixture(runner, verifier):
    """Yield ``(checkout, commit)`` with source modules pointed at the fixture.

    Source files are copied as bytes from the real checkout, then committed so
    the production runner and publication verifier can authenticate the full
    closure through Git blob identities. No training or actual solver run is
    part of fixture setup.
    """
    source_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="four-street-source-") as temporary:
        checkout = Path(temporary) / "repo"
        checkout.mkdir()
        for relative in ("pokerlab", "scripts"):
            _copy_python_tree(source_root, checkout, relative)
        for relative in PINNED_FILES:
            target = checkout / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_root / relative, target)

        subprocess.run(["git", "init", "-q", str(checkout)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "-C", str(checkout), "add", "--all"], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "-C", str(checkout), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit", "-q",
                        "-m", "synthetic publication source fixture"], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        commit = subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True,
            stderr=subprocess.PIPE).strip()

        with ExitStack() as stack:
            stack.enter_context(patch.object(runner, "REPO_ROOT", checkout))
            stack.enter_context(patch.object(runner.source_helper, "REPO_ROOT", checkout))
            stack.enter_context(patch.object(verifier, "REPO_ROOT", checkout))
            yield checkout, commit
