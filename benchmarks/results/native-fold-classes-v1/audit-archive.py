"""Audit exact saved archive paths/bytes; never execute archived sources."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

work = Path(__file__).resolve().parent
package = json.loads((work / "native-fold-classes-package-v1.json").read_bytes())
def sha(raw): return hashlib.sha256(raw).hexdigest()
def need(value, message):
    if not value: raise ValueError(message)
acceptance_pin = sys.argv[1]
archive_path = work / package["archive"]
raw = archive_path.read_bytes()
need(sha(raw) == package["sha256"] and len(raw) == package["bytes"], "outer archive pin")
with zipfile.ZipFile(archive_path) as archive:
    entries = archive.infolist()
    names = [item.filename for item in entries]
    need(len(names) == len(set(names)) == package["entries"] and len(names) < 5000, "unique bounded inventory")
    need(sum(item.file_size for item in entries) < 512 * 1024 * 1024, "expanded archive byte cap")
    for item in entries:
        path = PurePosixPath(item.filename)
        need(not path.is_absolute() and ".." not in path.parts and "\\" not in item.filename and ":" not in item.filename and not item.is_dir() and (item.external_attr >> 16) & 0o170000 != 0o120000, "unsafe member")
    manifest_raw = archive.read("manifest.json")
    need(sha(manifest_raw) == package["manifest_sha256"], "inner manifest pin")
    manifest = json.loads(manifest_raw)
    need(set(names) == set(manifest["files"]) | {"manifest.json"}, "exact internal inventory")
    for name, digest in manifest["files"].items():
        need(sha(archive.read(name)) == digest, "member digest: " + name)
    for directory in ("native-fold-classes-study-v1", "native-fold-classes-study-process-v1", "native-fold-classes-independent-review-v1", "native-fold-class-runner-tests-v1"):
        prefix = "evidence/" + directory + "/"
        expected = {prefix + path.relative_to(work / directory).as_posix(): sha(path.read_bytes()) for path in (work / directory).rglob("*") if path.is_file() and "__pycache__" not in path.parts}
        actual = {name: digest for name, digest in manifest["files"].items() if name.startswith(prefix)}
        need(actual == expected, "exact evidence path/byte equality: " + directory)
    candidates = [name for name in names if name.startswith("evidence/native-fold-classes-independent-review-v1/") and name.endswith("/receipt.json") and sha(archive.read(name)) == acceptance_pin]
    need(len(candidates) == 1, "unique externally pinned independent receipt")
    acceptance = json.loads(archive.read(candidates[0]))
    need(acceptance["status"] == "passed" and acceptance["candidate_calls"] == 0 and not any(acceptance["forbidden_calls"].values()) and acceptance["source_commit"] == package["source_commit"], "saved review identity")
    need(acceptance["helper_sha256"] == manifest["files"]["evidence/native-fold-classes-independent-review-v1/review.py"], "accepted review helper pin")
    study_prefix = "evidence/native-fold-classes-study-v1/"
    study_manifest_raw = archive.read(study_prefix + "manifest.json")
    need(sha(study_manifest_raw) == acceptance["manifest_sha256"] and sha(archive.read(study_prefix + "report.json")) == acceptance["report_sha256"], "accepted study/report pins")
    study_manifest = json.loads(study_manifest_raw)
    need({name[len(study_prefix):] for name in names if name.startswith(study_prefix)} == set(study_manifest["files"]) | {"manifest.json"}, "accepted exact inner study inventory")
    need(all(sha(archive.read(study_prefix + name)) == digest for name, digest in study_manifest["files"].items()), "accepted inner raw evidence digests")
    source = json.loads(archive.read("evidence/native-fold-classes-study-v1/source-before.json"))
    need(source["commit"] == package["source_commit"] == manifest["producer_commit"] and source == json.loads(archive.read("evidence/native-fold-classes-study-v1/source-after.json")), "source before/after")
    for name, digest in manifest["files"].items():
        if name.startswith("source/"):
            need(source["sha256"].get(name[len("source/"):]) == digest, "captured raw source closure")
    build = json.loads(archive.read("evidence/native-fold-v5-engine-build-v2/native-exact-build-manifest.json"))
    need(len(build["source_sha256"]) == 11 and all(manifest["files"].get("source/" + name) == digest for name, digest in build["source_sha256"].items()), "all eleven engine inputs captured")
    need(build["executable_sha256"] == manifest["files"]["evidence/native-fold-v5-engine-build-v2/native-exact-four-street-train.exe"] == acceptance["build"]["executable"] and manifest["files"]["evidence/native-fold-v5-engine-build-v2/native-exact-build-manifest.json"] == acceptance["build"]["manifest"], "accepted executable/build pins")
    process = json.loads(archive.read("evidence/native-fold-classes-study-process-v1/completion.json"))
    need(process["source_commit"] == source["commit"] and process["returncode"] == 0 and process["retry"] is False and process["producer_attempts_authorized"] == 1 and process["wrapper_sha256"] == manifest["files"]["development/run-native-fold-study-v1.py"], "one-attempt process provenance")
result = {"status": "passed", "archive_sha256": package["sha256"], "entries": len(names), "internal_manifest_sha256": package["manifest_sha256"], "review_receipt_sha256": acceptance_pin,
    "helper_sha256": sha(Path(__file__).read_bytes()), "scope": "Exact archive inventory, raw evidence/source/provenance bytes only; no archived source executed. Mathematical acceptance is the separately pinned review receipt."}
with (work / "native-fold-classes-archive-audit-v1.json").open("x") as stream:
    json.dump(result, stream, indent=2)
print(json.dumps(result), flush=True)
