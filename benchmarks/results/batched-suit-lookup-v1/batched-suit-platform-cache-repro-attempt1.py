"""Reproduce the CI platform-cache defect in a fresh process using live source."""
import json
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent/'batched-suit-lookup-repo'))
from scripts import benchmark_batched_suit_lookup as study

platform._uname_cache = None
platform._platform_cache.clear()
source = {"commit":"reproduction-only", "status":"", "sha256":{}}
failed = SimpleNamespace(returncode=1,stdout=b"partial child",stderr=b"failure")
first = None
with TemporaryDirectory() as folder:
    # Select the processor lookup used on Linux while keeping the reproduction
    # on the installed Windows Python. No system or runtime files are changed.
    with patch.object(platform._Processor, "get", new=lambda: platform._Processor.from_subprocess()), \
         patch.object(study,"_identity",return_value=source), \
         patch.object(study.subprocess,"run",return_value=failed):
        try:
            study.run(Path(folder)/'study')
        except Exception as exc:
            first={"type":type(exc).__name__,"message":str(exc)}
    later=None
    try:
        platform.platform()
    except Exception as exc:
        later={"type":type(exc).__name__,"message":str(exc)}
print(json.dumps({"python":sys.version,"initial_failure":first,"later_platform_failure":later,
    "cached_processor_type":type(platform.uname().processor).__name__,
    "scope":"Fresh-process exact metadata path reproduction; no solver invocation or source changes."}))
if first is None or later is None:
    raise SystemExit(1)
