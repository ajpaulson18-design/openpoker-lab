"""Capture accepted frozen fold-class evidence; archived sources are never run."""
import hashlib
import json
from pathlib import Path
import zipfile

work = Path(__file__).resolve().parent
repo = work / "native-fold-mask-repo"
study = work / "native-fold-classes-study-v1"
review = work / "native-fold-classes-independent-review-v1"
output = work / "native-fold-classes-evidence-v1.zip"
def sha(raw): return hashlib.sha256(raw).hexdigest()
def parse(path): return json.loads(path.read_bytes())
report = parse(study / "report.json")
source = parse(study / "source-before.json")
if output.exists() or report["failure"] is not None or any(report[k] != 34 for k in ("calls_planned", "calls_attempted", "calls_captured")):
    raise ValueError("require one complete fixed study and fresh archive")
if parse(study / "source-after.json") != source or parse(work / "native-fold-classes-study-process-v1/completion.json")["returncode"] != 0:
    raise ValueError("require stable frozen source and completed producer process")
accepted = [path for path in review.rglob("receipt.json") if parse(path).get("status") == "passed"]
if len(accepted) != 1:
    raise ValueError("one fresh independent acceptance is required")
receipt = parse(accepted[0])
if receipt["source_commit"] != source["commit"] or receipt["candidate_calls"] != 0 or receipt["manifest_sha256"] != sha((study / "manifest.json").read_bytes()) or receipt["report_sha256"] != sha((study / "report.json").read_bytes()):
    raise ValueError("independent receipt/source/study binding mismatch")
study_manifest = parse(study / "manifest.json")
study_bytes = {path.relative_to(study).as_posix(): path.read_bytes() for path in study.rglob("*") if path.is_file()}
if set(study_bytes) != set(study_manifest["files"]) | {"manifest.json"} or any(sha(study_bytes[name]) != digest for name, digest in study_manifest["files"].items()):
    raise ValueError("accepted inner study manifest/raw evidence drift")
members = {}
def add(name, path):
    if name in members or path.is_symlink() or not path.is_file():
        raise ValueError("duplicate or nonordinary archive input: " + name)
    members[name] = path.read_bytes()
directories = [study, review, work / "native-fold-classes-study-process-v1",
               work / "fold-mask-class-proof-v1", work / "native-fold-class-controls-v2-source",
               work / "native-fold-class-runner-tests-v1"]
for pattern in ("native-fold-*-build-v*", "native-fold-class-build-v*", "native-active-development-tests-fold-*", "native-fold-classes-runner-*"):
    directories.extend(path for path in work.glob(pattern) if path.is_dir())
for directory in sorted(set(directories)):
    if not directory.is_dir():
        raise ValueError("missing required evidence directory: " + str(directory))
    for path in sorted(directory.rglob("*")):
        if path.is_file() and not any(part in ("__pycache__", "boost-include") for part in path.parts) and path.suffix not in (".obj", ".pdb"):
            add("evidence/" + directory.name + "/" + path.relative_to(directory).as_posix(), path)
if any(members["evidence/" + study.name + "/" + name] != raw for name, raw in study_bytes.items()):
    raise ValueError("study changed during archive capture")
for pattern in ("*fold*.py", "native-fold-*.log"):
    for path in sorted(work.glob(pattern)):
        if path.is_file() and path != Path(__file__):
            add("development/" + path.name, path)
for name, digest in source["sha256"].items():
    path = repo / name
    if sha(path.read_bytes()) != digest:
        raise ValueError("full frozen raw source drift: " + name)
    selected = (name.startswith(("pokerlab/", "scripts/", "native/", "tests/")) and path.suffix in (".py", ".hpp", ".cpp")) or name.startswith("third_party/boost-multiprecision-") or name in (
        "AGENTS.md", ".gitattributes", ".github/workflows/native-exact-four-street.yml", "docs/native-fold-classes.md", "docs/decisions/DECISION_LOG.md", "docs/engineering/CURRENT_STATE.md", "docs/foundation-first-execution.md")
    if selected:
        add("source/" + name, path)
    if name.startswith("benchmarks/results/native-fold-class-development-v1/"):
        add("historical-development/" + name, path)
add("development/" + Path(__file__).name, Path(__file__))
add("development/exact-selected-independent-review.py", work / "exact-selected-independent-review.py")
manifest = {"contract": "native-fold-mask-classes-archive-v1", "producer_commit": source["commit"],
    "source_scope": "Full tracked raw/Git maps retained; current executable/math/test sources and pinned dependencies captured. Older historical evidence is referenced by the maps except the explicitly captured original fold-development archive. Archived sources are evidence only.",
    "files": {name: sha(raw) for name, raw in sorted(members.items())}}
manifest_raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for name, raw in sorted(members.items()): archive.writestr(name, raw)
    archive.writestr("manifest.json", manifest_raw)
result = {"archive": output.name, "bytes": output.stat().st_size, "entries": len(members) + 1,
          "sha256": sha(output.read_bytes()), "manifest_sha256": sha(manifest_raw), "source_commit": source["commit"]}
with (work / "native-fold-classes-package-v1.json").open("x") as stream:
    json.dump(result, stream, indent=2)
print(json.dumps(result), flush=True)
