"""Exact-path, saved-byte-only archive audit; never executes archived sources."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

work = Path(__file__).resolve().parent
package = json.loads((work / "native-active-frames-package-v1.json").read_bytes())
archive_path = work / package["archive"]
def sha(raw): return hashlib.sha256(raw).hexdigest()
def need(value, message):
    if not value: raise ValueError(message)
raw = archive_path.read_bytes()
need(sha(raw) == package["sha256"] and len(raw) == package["bytes"], "outer archive pin differs")
with zipfile.ZipFile(archive_path) as archive:
    entries = archive.infolist()
    names = [item.filename for item in entries]
    need(len(names) == len(set(names)) == package["entries"] and len(names) < 5000, "duplicate/incomplete archive inventory")
    need(sum(item.file_size for item in entries) < 512 * 1024 * 1024, "archive expanded byte cap")
    for item in entries:
        p = PurePosixPath(item.filename)
        need(not p.is_absolute() and ".." not in p.parts and "\\" not in item.filename and
             ":" not in item.filename and not item.is_dir() and
             (item.external_attr >> 16) & 0o170000 != 0o120000, "unsafe archive member")
    manifest_raw = archive.read("manifest.json")
    need(sha(manifest_raw) == package["manifest_sha256"], "internal manifest pin differs")
    manifest = json.loads(manifest_raw)
    need(set(names) == set(manifest["files"]) | {"manifest.json"}, "internal inventory differs")
    for name, digest in manifest["files"].items():
        need(sha(archive.read(name)) == digest, "archive content differs: " + name)
    for directory in ("native-active-frames-study-v1", "native-active-frames-study-continuation-v1",
                      "native-active-frames-independent-review-v1"):
        prefix = "evidence/" + directory + "/"
        expected = {prefix + p.relative_to(work / directory).as_posix(): sha(p.read_bytes())
                    for p in (work / directory).rglob("*") if p.is_file()}
        actual = {name: digest for name, digest in manifest["files"].items() if name.startswith(prefix)}
        need(actual == expected, "exact evidence directory differs: " + directory)
    review_name = "evidence/native-active-frames-independent-review-v1/attempt1/receipt.json"
    need(sha(archive.read(review_name)) == "942587ce1c30707de190a3f78d46b79084c5e5817b93bd368bcdf0d06384e42c", "independent acceptance pin differs")
    acceptance = json.loads(archive.read(review_name))
    need(acceptance["status"] == "passed" and acceptance["independent_candidate_calls"] == 0 and
         acceptance["counts"] == {"complete":24,"native-resource-rejected":13}, "review outcome differs")
    source = json.loads(archive.read("evidence/native-active-frames-study-v1/source-before.json"))
    for name, digest in manifest["files"].items():
        if name.startswith("source/"):
            original = name[len("source/"):]
            need(source["sha256"].get(original) == digest, "captured source differs from frozen raw closure")
    build = json.loads(archive.read("evidence/native-active-engine-build-v1/engine/native-exact-build-manifest.json"))
    need(all(manifest["files"].get("source/" + name) == digest for name, digest in build["source_sha256"].items()),
         "engine source closure is not fully captured")
    protocol = json.loads(archive.read("development/native-active-frames-study-continuation-v1-protocol.json"))
    completion = json.loads(archive.read("development/native-active-frames-study-continuation-v1-completion.json"))
    need(protocol["helper_sha256"] == manifest["files"]["development/continue-native-active-study-v1.py"] and
         completion["counts"] == {"reused":2,"new_producers":35}, "continuation provenance differs")
receipt = {"status":"passed","archive_sha256":package["sha256"],"entries":len(names),
    "internal_manifest_sha256":package["manifest_sha256"],
    "review_receipt_sha256":"942587ce1c30707de190a3f78d46b79084c5e5817b93bd368bcdf0d06384e42c",
    "scope":"Exact archive/member/source/raw-directory/provenance equality only; independent mathematical acceptance is the separately pinned receipt. No archived source executed.",
    "helper_sha256":sha(Path(__file__).read_bytes())}
with (work / "native-active-frames-archive-audit-v1.json").open("x") as stream:
    json.dump(receipt, stream, indent=2)
print(json.dumps(receipt),flush=True)
