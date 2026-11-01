"""Saved-only matrix-free exact certificate pass over the frozen fold study.

This runner authenticates both source checkouts and every old study artifact
before importing candidate code. It certifies only the 28 already-complete
policies; the six producer resource rejections remain separate unknown inputs.
No solver or training call is made here.
"""
from argparse import ArgumentParser
import hashlib
import json
import math
import base64
from pathlib import Path
import re
import subprocess
import sys
import time
import platform
import zipfile
from types import SimpleNamespace
from contextlib import ExitStack
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent
DEFAULT_STUDY = WORK / "native-fold-classes-study-v1"
DEFAULT_REVIEW = WORK / "native-fold-classes-independent-review-v1"
PRODUCER_COMMIT = "946671d8da38102aff4c7d901d02d58158888a68"
STUDY_MANIFEST_SHA256 = "e520dbeb8011b247041e13d63eeddf1423bba0dc340ebb8072250af664ef19ac"
STUDY_REPORT_SHA256 = "41096b7db81e62111bec209905c35c04f99542473313b0d29d5458986fa3b1ef"
OLD_REVIEW_RECEIPT_SHA256 = "88e5a8cc68dae468338ba854158bc4f1c0467e0e364e059b5917acab76664e33"
OLD_REVIEW_OBSERVATION_SHA256 = "798a0f906f180a284a1b25932e575d7c1656bbfd2069bc3be4b11bffdb5dd078"
OLD_BUILD_MANIFEST_SHA256 = "40c75343ae7c6d3b9f5d0010f0da977ecea096e6aadeb9afb13535492abf6412"
OLD_BUILD_EXE_SHA256 = "065217920a79e9d4b6378e09a3ad4371332eb863b363e911f20dd18ac64475d9"
BOOST_ARCHIVE_SHA256 = "33c422ab3ebfa9e86c62f41f372ec2b9c2cefa303f1885391aa4d8250ef2f831"
BOOST_MANIFEST_SHA256 = "4d6f33341887e35a0c29e9dc5da2a326d546427940c2b16b485db0c61b042555"
BOOST_LICENSE_SHA256 = "c9bff75738922193e67fa726fa225535870d2aa1059f91452c411736284ad566"
OLD_EXACT_UNKNOWN = frozenset(
    f"{case}-t10-{mode}-p0"
    for case in ("balanced-4x4-unit", "balanced-8x8-unit", "asymmetric-2x16-unit")
    for mode in ("board-sweep", "fold-mask-classes-v1"))
PRODUCER_REJECTIONS = frozenset(
    f"{case}-t{iterations}-{mode}-p0"
    for case, iterations in (("balanced-16x16-unit", 10), ("original-22-t10", 100),
                             ("original-22-t10", 1000))
    for mode in ("board-sweep", "fold-mask-classes-v1"))
_MODES = ("board-sweep", "fold-mask-classes-v1")
_BASELINES = ("original-22-t10", "payoff-varied-t10", "blocker-18",
              "asymmetric-weighted", "mixed-stabilizer", "physical-g6")
_MATRIX = ("balanced-4x4-unit", "balanced-8x8-unit", "balanced-16x16-unit",
           "asymmetric-2x16-unit")
_FIXED_ENTRIES = tuple(
    [(case, 10, mode, 0) for case in _BASELINES for mode in _MODES] +
    [("original-22-t10", 10, mode, sample) for sample, modes in (
        (1, ("fold-mask-classes-v1", "board-sweep")),
        (2, ("board-sweep", "fold-mask-classes-v1"))) for mode in modes] +
    [("original-22-t10", iterations, mode, 0) for iterations in (40, 60) for mode in _MODES] +
    [("payoff-varied-t100", 100, mode, 0) for mode in _MODES] +
    [(case, 10, mode, 0) for case in _MATRIX for mode in _MODES] +
    [("original-22-t10", iterations, mode, 0) for iterations in (100, 1000) for mode in _MODES])
FIXED_LABELS = frozenset(f"{case}-t{iterations}-{mode}-p{sample}"
                         for case, iterations, mode, sample in _FIXED_ENTRIES)
METRICS = ("value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value",
           "sb_gain", "bb_gain", "nash_conv", "exploitability")
EXACT_TO_NUMERIC = {"value_sb": "value_sb", "value_bb": "value_bb",
    "sb_best_response_value": "sb_best_response_value",
    "bb_best_response_value": "bb_best_response_value",
    "sb_best_response_gain": "sb_gain", "bb_best_response_gain": "bb_gain",
    "nash_conv": "nash_conv", "exploitability": "exploitability"}
NUMERIC_TOLERANCE = 1e-9
OLD_NUMERIC_TOLERANCE = 1e-10
RECORD_SCHEMA = "matrix-free-saved-certificate-record-v1"
MANIFEST_SCHEMA = "matrix-free-saved-certificate-manifest-v1"
CERTIFICATE_LIMITS = {"work": 500_000_000, "entries": 8_000_000,
                      "integer_bits": 65_536, "created_bits": 16_000_000_000}
_RESOURCE_ERRORS = (
    re.compile(r"^(?:[^\n:]{1,80}: )?certificate work limit exceeded$"),
    re.compile(r"^(?:[^\n:]{1,80}: )?certificate integer bit limit exceeded$"),
    re.compile(r"^(?:[^\n:]{1,80}: )?certificate cumulative integer bit limit exceeded$"),
    re.compile(r"^.+: certificate entry limit exceeded$"),
    re.compile(r"^certificate JSON node/depth limit exceeded$"),
    re.compile(r"^(?:[^\n:]{1,80}: )?certificate JSON (?:integer width|input string length|sequence|mapping) exceeded$"),
    re.compile(r"^certificate canonical JSON byte limit exceeded$"),
    re.compile(r"^certificate whole-request walk forecast exceeds (?:work|entry) limit$"),
    re.compile(r"^certificate public traversal depth exceeded$"),
    re.compile(r"^certificate final Fraction text forecast exceeds byte limit$"),
    re.compile(r"^(?:[^\n:]{1,80}: )?Fraction text integer bit limit exceeded$"),
    re.compile(r"^(?:[^\n:]{1,80}: )?cumulative Fraction text byte limit exceeded$"),
    re.compile(r"^(?:[^\n:]{1,80}: )?certificate policy-row limit exceeded$"),
    re.compile(r"^(?:[^\n:]{1,80}: )?certificate action-slot limit exceeded$"),
    re.compile(r"^public graph exceeds (?:\d+ nodes|depth \d+)$"),
    re.compile(r"^.+ exceeds the \d+-holding research cap$"),
    re.compile(r"^public action menu exceeds bounded per-decision width$"),
    re.compile(r"^certificate public occurrence census exceeded$"),
)


def _need(value, message):
    if not value:
        raise ValueError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True,
                      allow_nan=False).encode("ascii") + b"\n"


def _write(path, value):
    Path(path).write_bytes(_json_bytes(value))


def _decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _need(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON value")))


def _git(root, *args, data=None):
    return subprocess.check_output(["git", "-C", str(root), *args], input=data)


def _tree_identity(root, *, require_clean=True):
    root = Path(root).resolve()
    commit = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    status = _git(root, "status", "--porcelain", "--untracked-files=all").decode("utf-8").strip()
    _need(not require_clean or not status, "source checkout must be clean before saved certification")
    names = _git(root, "ls-files", "-z").decode("utf-8").split("\0")[:-1]
    _need(bool(names) and len(names) == len(set(names)), "tracked source closure is empty or duplicated")
    raw_hashes = {name: _sha((root / name).read_bytes()) for name in names}
    entries = _git(root, "ls-tree", "-rz", "--full-tree", commit).split(b"\0")[:-1]
    tree = {}
    for entry in entries:
        metadata, name = entry.split(b"\t", 1)
        mode, kind, oid = metadata.split()
        _need(kind == b"blob" and mode in (b"100644", b"100755"),
              "source tree contains a nonordinary file")
        tree[name.decode("utf-8")] = oid.decode("ascii")
    _need(set(names) == set(tree), "tracked source keyset differs from committed tree")
    normalized_lines = _git(root, "hash-object", "--stdin-paths",
                             data=("\n".join(names) + "\n").encode("utf-8")).decode("ascii").splitlines()
    _need(len(normalized_lines) == len(names), "Git source normalization closure is incomplete")
    normalized = dict(zip(names, normalized_lines))
    for name in names:
        raw = (root / name).read_bytes()
        raw_oid = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        _need(raw_oid == tree[name] or normalized[name] == tree[name],
              "raw/normalized committed blob mismatch: " + name)
    result = {"root": str(root), "commit": commit, "status": status,
              "sha256": raw_hashes, "tree_blob_oid": tree,
              "git_normalized_blob_oid": normalized, "closure_count": len(names)}
    if require_clean:
        _need(_tree_identity_shallow(root) == (commit, status, raw_hashes),
              "source changed during tree authentication")
    return result


def _tree_identity_shallow(root):
    root = Path(root).resolve()
    commit = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    status = _git(root, "status", "--porcelain", "--untracked-files=all").decode("utf-8").strip()
    names = _git(root, "ls-files", "-z").decode("utf-8").split("\0")[:-1]
    return commit, status, {name: _sha((root / name).read_bytes()) for name in names}


def _safe_artifact_path(root, relative):
    _need(type(relative) is str and relative and "\\" not in relative,
          "artifact manifest path must be a normalized relative path")
    path = Path(relative)
    _need(not path.is_absolute() and all(part not in ("", ".", "..") for part in path.parts),
          "artifact manifest path escapes the saved study")
    full = (root / path).resolve()
    _need(root.resolve() in full.parents, "artifact path resolves outside the saved study")
    return full


def _artifact_hashes(study):
    study = Path(study).resolve()
    manifest_raw = (study / "manifest.json").read_bytes()
    report_raw = (study / "report.json").read_bytes()
    _need(_sha(manifest_raw) == STUDY_MANIFEST_SHA256 and
          _sha(report_raw) == STUDY_REPORT_SHA256,
          "frozen producer manifest/report pins differ")
    manifest = _decode(manifest_raw)
    _need(type(manifest) is dict and manifest.get("version") == "native-fold-mask-classes-evidence-manifest-v1" and
          type(manifest.get("files")) is dict and len(manifest["files"]) == 322,
          "frozen producer artifact manifest schema/count changed")
    observed = {}
    for name, expected in manifest["files"].items():
        path = _safe_artifact_path(study, name)
        digest = _sha(path.read_bytes())
        _need(digest == expected, "frozen producer artifact hash mismatch: " + name)
        observed[name] = digest
    _need("capture-time-sha256.json" in observed, "capture-time artifact pins are missing")
    capture_time = _decode((study / "capture-time-sha256.json").read_bytes())
    _need(type(capture_time) is dict and bool(capture_time), "capture-time pin schema is malformed")
    for name, expected in capture_time.items():
        _need(name in observed and observed[name] == expected,
              "capture-time artifact pin mismatch: " + str(name))
    report = _decode(report_raw)
    return manifest, report, observed


def _label(sample):
    artifact = sample.get("artifact")
    _need(type(artifact) is str and artifact.endswith(".raw.json"), "sample artifact label malformed")
    return artifact[:-len(".raw.json")]


def _partition_inventory(report):
    _need(type(report) is dict and report.get("source_commit") == PRODUCER_COMMIT and
          report.get("calls_planned") == report.get("calls_attempted") ==
          report.get("calls_captured") == 34 and report.get("failure") is None and
          type(report.get("samples")) is list and len(report["samples"]) == 34,
          "fixed 34-call producer report identity/status changed")
    samples = {}
    for row in report["samples"]:
        identifier = _label(row)
        _need(identifier not in samples, "duplicate producer sample label")
        samples[identifier] = row
    _need(set(samples) == FIXED_LABELS, "frozen producer fixed 34-label schedule changed")
    complete = {label for label, row in samples.items() if row.get("status") == "complete"}
    rejected = {label for label, row in samples.items() if row.get("status") == "native-resource-rejected"}
    _need(complete == FIXED_LABELS - PRODUCER_REJECTIONS and len(complete) == 28 and
          len(rejected) == 6 and rejected == PRODUCER_REJECTIONS,
          "fixed producer complete/rejection inventory changed")
    return samples, sorted(complete), sorted(rejected)


def _authenticate_build(producer_repo, study, artifacts, receipt):
    """Bind the old executable and the complete pinned Boost header closure; never execute it."""
    producer_repo = Path(producer_repo).resolve()
    study = Path(study).resolve()
    build_before_path = study / "build-before.json"
    build_after_path = study / "build-after.json"
    before_raw = build_before_path.read_bytes()
    after_raw = build_after_path.read_bytes()
    _need(_sha(before_raw) == artifacts.get("build-before.json") and
          _sha(after_raw) == artifacts.get("build-after.json") and before_raw == after_raw,
          "saved native build snapshots are missing or differ")
    build = _decode(before_raw)
    review_build = receipt.get("build")
    _need(type(build) is dict and type(review_build) is dict and
          build.get("manifest_sha256") == OLD_BUILD_MANIFEST_SHA256 and
          build.get("executable_sha256") == OLD_BUILD_EXE_SHA256 and
          review_build.get("manifest") == OLD_BUILD_MANIFEST_SHA256 and
          review_build.get("executable") == OLD_BUILD_EXE_SHA256 and
          build.get("source_sha256") == review_build.get("sources"),
          "saved executable/build source pins differ from the independent receipt")
    manifest_path = producer_repo.parent / "native-fold-v5-engine-build-v2" / "native-exact-build-manifest.json"
    exe_path = Path(build.get("executable", ""))
    _need(manifest_path.is_file() and exe_path.is_file(),
          "pinned old native build manifest or executable is unavailable")
    manifest_raw = manifest_path.read_bytes()
    _need(_sha(manifest_raw) == OLD_BUILD_MANIFEST_SHA256,
          "old native build manifest hash differs")
    native_manifest = _decode(manifest_raw)
    _need(type(native_manifest) is dict and native_manifest.get("contract") == "native-exact-build-v1" and
          native_manifest.get("target") == "engine" and
          native_manifest.get("source_sha256") == build["source_sha256"] and
          native_manifest.get("executable_sha256") == OLD_BUILD_EXE_SHA256 and
          native_manifest.get("flags") == build.get("flags") and
          _sha(exe_path.read_bytes()) == OLD_BUILD_EXE_SHA256,
          "old native build manifest/executable identity differs")
    expected_sources = review_build.get("sources")
    expected_source_names = {
        "native/exact_binary64.hpp", "native/exact_four_street_train.cpp",
        "native/exact_indexed_routing.hpp", "native/exact_public_graph.hpp",
        "native/exact_public_history_index.hpp", "native/exact_selected_cfr.hpp",
        "native/exact_selected_kernel.hpp", "scripts/build_native_exact_four_street.py",
        "third_party/boost-multiprecision-1.92.0/LICENSE_1_0.txt",
        "third_party/boost-multiprecision-1.92.0/headers.zip",
        "third_party/boost-multiprecision-1.92.0/manifest.json"}
    _need(type(expected_sources) is dict and len(expected_sources) == 11 and
          set(expected_sources) == expected_source_names and
          expected_sources == build.get("source_sha256"),
          "pinned native build must contain its exact eleven-source closure")
    for relative, digest in expected_sources.items():
        _need(type(relative) is str and type(digest) is str and
              _sha((producer_repo / relative).read_bytes()) == digest,
              "native executable source closure differs from producer checkout: " + str(relative))
    dep = producer_repo / "third_party" / "boost-multiprecision-1.92.0"
    dep_paths = {"headers.zip": dep / "headers.zip", "manifest.json": dep / "manifest.json",
                 "LICENSE_1_0.txt": dep / "LICENSE_1_0.txt"}
    expected_dep = {"headers.zip": BOOST_ARCHIVE_SHA256, "manifest.json": BOOST_MANIFEST_SHA256,
                    "LICENSE_1_0.txt": BOOST_LICENSE_SHA256}
    _need(all(path.is_file() and _sha(path.read_bytes()) == expected_dep[name]
              for name, path in dep_paths.items()), "pinned Boost archive/license/manifest bytes differ")
    dep_manifest = _decode(dep_paths["manifest.json"].read_bytes())
    with zipfile.ZipFile(dep_paths["headers.zip"]) as archive:
        entries = [item for item in archive.infolist() if not item.is_dir()]
        _need(len(entries) == 198 and len({item.filename for item in entries}) == 198,
              "pinned Boost archive header count or paths differ")
        packaged_headers = {item.filename: _sha(archive.read(item)) for item in entries}
    _need(dep_manifest.get("header_count") == 198 and
          dep_manifest.get("headers_sha256") == packaged_headers and
          review_build.get("headers") == packaged_headers,
          "packaged 198-header closure differs from pinned manifest/review receipt")
    actual_include = exe_path.parent / "boost-include"
    _need(actual_include.is_dir(), "actual old compiler include tree is missing")
    actual_headers = {}
    for path in actual_include.rglob("*"):
        if path.is_file():
            actual_headers[path.relative_to(actual_include).as_posix()] = _sha(path.read_bytes())
    _need(actual_headers == packaged_headers,
          "actual compiler include tree differs from the authenticated 198 packaged headers")
    return {"schema": "frozen-native-build-identity-v1",
        "manifest_sha256": OLD_BUILD_MANIFEST_SHA256, "executable_sha256": OLD_BUILD_EXE_SHA256,
        "executable_path": str(exe_path), "target": "engine",
        "source_sha256": expected_sources, "source_count": len(expected_sources),
        "dependency": {"archive_sha256": BOOST_ARCHIVE_SHA256,
            "manifest_sha256": BOOST_MANIFEST_SHA256, "license_sha256": BOOST_LICENSE_SHA256,
            "dependency_commit": dep_manifest.get("commit"), "header_count": len(packaged_headers),
            "headers_sha256": packaged_headers},
        "actual_include_headers_sha256": actual_headers,
        "flags": build.get("flags"), "executable_invoked": False}


def _validate_inventory(report, artifacts, study):
    samples, complete_labels, rejected_labels = _partition_inventory(report)
    complete, rejected = set(complete_labels), set(rejected_labels)
    for row in samples.values():
        _need(row.get("artifact") in artifacts, "producer raw sample missing from authenticated manifest")
    _need(OLD_EXACT_UNKNOWN <= complete and len(OLD_EXACT_UNKNOWN) == 6,
          "fixed historical exact-unknown set differs")
    previous = {}

    def validate_streams(label, sample, raw):
        streams = raw.get("native_streams")
        _need(type(streams) is list and len(streams) == 1,
              "frozen producer sample must contain one raw native invocation")
        stream = streams[0]
        _need(type(stream) is dict and type(stream.get("request")) is str and
              type(stream.get("stdout")) is str and type(stream.get("stderr")) is str,
              "frozen native stream shape is malformed")
        decoded = {key: base64.b64decode(stream[key], validate=True)
                   for key in ("request", "stdout", "stderr")}
        stem = label + "-native-0-"
        for key, raw_bytes in decoded.items():
            name = stem + key + ".bin"
            _need(name in artifacts and artifacts[name] == _sha(raw_bytes) and
                  _safe_artifact_path(study, name).read_bytes() == raw_bytes,
                  "raw native stream differs from its pinned sidecar: " + name)
        status_name = label + "-native-0-status.json"
        process_name = label + "-process-status.json"
        _need(status_name in artifacts and process_name in artifacts,
              "frozen native process status sidecar is missing")
        expected_status = {"returncode": stream.get("returncode"),
            "request_sha256": _sha(decoded["request"]),
            "stdout_sha256": _sha(decoded["stdout"]),
            "stderr_sha256": _sha(decoded["stderr"])}
        _need(_decode(_safe_artifact_path(study, status_name).read_bytes()) == expected_status,
              "native stream process-status sidecar differs")
        top_status = _decode(_safe_artifact_path(study, process_name).read_bytes())
        _need(type(top_status) is dict and top_status.get("returncode") == 0 and
              top_status.get("stdout_sha256") == artifacts[label + ".stdout.bin"] and
              top_status.get("stderr_sha256") == artifacts[label + ".stderr.bin"],
              "outer producer child capture status differs")
        return stream

    for label in sorted(complete):
        row = samples[label]
        raw_bytes = _safe_artifact_path(study, row["artifact"]).read_bytes()
        raw = _decode(raw_bytes)
        _need(type(raw.get("payload")) is dict and raw.get("status") == "complete" and
              _sha(_canonical(raw["payload"])) == row.get("payload_sha256"),
              "frozen raw policy canonical hash/status differs from report: " + label)
        _need(raw.get("payload_sha256") == row.get("payload_sha256") and
              raw.get("counts") == row.get("counts") and
              raw.get("native_observations") == row.get("native_observations"),
              "frozen raw child metadata differs from producer report: " + label)
        stream = validate_streams(label, row, raw)
        _need(stream.get("returncode") == 0 and raw["counts"].get("native_invoke") == 1 and
              type(raw["counts"].get("native_invoke")) is int and
              type(raw["counts"].get("rank_before_native")) is int and raw["counts"].get("rank_before_native") == 0 and
              type(raw["counts"].get("python_trainer")) is int and raw["counts"].get("python_trainer") == 0 and
              type(raw["counts"].get("world")) is int and raw["counts"].get("world") == 0 and
              type(raw["counts"].get("pair")) is int and raw["counts"].get("pair") == 0 and
              raw.get("native_observations") == row.get("native_observations"),
              "complete frozen producer sample entered an unexpected path")
        verification_name = label + "-verification.json"
        _need(verification_name in artifacts, "complete producer sample lacks saved verification")
        verification = _decode(_safe_artifact_path(study, verification_name).read_bytes())
        exact_status = verification.get("exact", {}).get("status")
        numeric = verification.get("numeric", {})
        _need(exact_status in ("complete", "resource-unverified") and
              numeric.get("status") == "complete",
              "saved exact/numeric verification status changed")
        expected = "resource-unverified" if label in OLD_EXACT_UNKNOWN else "complete"
        _need(exact_status == expected, "historical exact verification classification changed: " + label)
        if expected == "resource-unverified":
            error = verification["exact"].get("error", {})
            _need(error.get("type") == "ValueError" and
                  error.get("message") == "Compact payload exceeds unchanged exact policy-shape cap",
                  "historical exact unknown is not the pinned shape-cap outcome")
        else:
            _validate_old_exact_binding(verification, row, raw)
        previous[label] = {"status": exact_status, "verification": verification,
                           "artifact": verification_name,
                           "artifact_sha256": _sha(_safe_artifact_path(study, verification_name).read_bytes()),
                           "source_raw_sha256": _sha(raw_bytes)}
    for label in sorted(rejected):
        _need((label + "-verification.json") not in artifacts,
              "producer rejection unexpectedly has a policy verification")
        row = samples[label]
        raw = _decode(_safe_artifact_path(study, row["artifact"]).read_bytes())
        _need(raw.get("status") == "native-resource-rejected" and raw.get("payload") is None and
              raw.get("failure", {}).get("type") == "NativeFailure" and
              raw.get("native_observations") == {"learning_completed": None, "rank_calls": None} and
              all(raw.get("counts", {}).get(key) == 0 for key in ("python_rank", "python_trainer", "rank_before_native", "world", "pair")),
              "frozen producer rejection record is malformed")
        stream = validate_streams(label, row, raw)
        _need(stream.get("returncode") == 2 and not base64.b64decode(stream["stdout"], validate=True),
              "frozen native rejection did not preserve its native failure stream")
    return samples, previous, sorted(complete), sorted(rejected)


def _validate_old_exact_binding(verification, sample, raw):
    """The compact wrapper and expanded literal certificate have distinct hashes."""
    wrapper = verification.get("exact", {}).get("result")
    _need(type(wrapper) is dict and wrapper.get("contract") == "compact-exact-product-certificate-v1",
          "old compact verification wrapper is absent")
    cert = wrapper.get("exact_certificate")
    _need(type(cert) is dict and
          wrapper.get("compact_input_canonical_sha256") == sample.get("payload_sha256") and
          wrapper.get("verification_expansion_canonical_sha256") == cert.get("input_policy_canonical_sha256") and
          type(cert.get("input_case_canonical_sha256")) is str and
          re.fullmatch(r"[0-9a-f]{64}", cert["input_case_canonical_sha256"]) is not None,
          "old compact/expanded certificate provenance differs")
    _need(all(type(wrapper.get(key)) is int and wrapper[key] == 0
              for key in ("production_pair_rows", "training_calls", "native_calls")),
          "old compact verifier entered a production path")


def _authenticate_saved(study, review, producer):
    study = Path(study).resolve()
    review = Path(review).resolve()
    manifest, report, observed = _artifact_hashes(study)
    source_before = _decode((study / "source-before.json").read_bytes())
    source_after = _decode((study / "source-after.json").read_bytes())
    proof = _decode((study / "source-auth-proof.json").read_bytes())
    for source in (source_before, source_after):
        _need(source.get("commit") == PRODUCER_COMMIT and source.get("status") == "" and
              source.get("sha256") == producer["sha256"],
              "saved producer source map differs from the explicit clean producer checkout")
    _need(source_before == source_after and proof.get("commit") == PRODUCER_COMMIT and
          proof.get("raw_or_normalized_blob_match") is True and
          proof.get("closure_count") == len(producer["sha256"]) and
          proof.get("committed_tree_blob_oid") == producer["tree_blob_oid"] and
          proof.get("git_normalized_blob_oid") == producer["git_normalized_blob_oid"],
          "saved source before/after/authentication proof is incomplete")
    process_path = Path(review) / "process-observation.json"
    receipt_path = Path(review) / "attempt1" / "receipt.json"
    process_raw = process_path.read_bytes()
    receipt_raw = receipt_path.read_bytes()
    _need(_sha(process_raw) == OLD_REVIEW_OBSERVATION_SHA256 and
          _sha(receipt_raw) == OLD_REVIEW_RECEIPT_SHA256,
          "old independent review receipt/process pins differ")
    process = _decode(process_raw); receipt = _decode(receipt_raw)
    _need(process.get("receipt_sha256") == OLD_REVIEW_RECEIPT_SHA256 and
          receipt.get("status") == "passed" and receipt.get("source_commit") == PRODUCER_COMMIT and
          receipt.get("manifest_sha256") == STUDY_MANIFEST_SHA256 and
          receipt.get("report_sha256") == STUDY_REPORT_SHA256 and
          receipt.get("counts") == {"complete": 28, "native-resource-rejected": 6},
          "old independent review receipt does not bind the frozen 34-call study")
    samples, previous, complete_labels, rejected_labels = _validate_inventory(report, observed, study)
    build_identity = _authenticate_build(producer["root"], study, observed, receipt)
    proof_out = {"study_manifest_sha256": STUDY_MANIFEST_SHA256,
        "study_report_sha256": STUDY_REPORT_SHA256,
        "study_file_count": len(observed), "study_files": observed,
        "capture_time_file_sha256": observed["capture-time-sha256.json"],
        "producer_source_before": source_before, "producer_source_after": source_after,
        "producer_source_auth_proof_sha256": observed["source-auth-proof.json"],
        "old_review_receipt_sha256": OLD_REVIEW_RECEIPT_SHA256,
        "old_review_process_observation_sha256": OLD_REVIEW_OBSERVATION_SHA256,
        "old_exact_complete_count": 22, "old_exact_unknown_count": 6,
        "producer_policy_complete_count": len(complete_labels),
        "producer_resource_rejected_count": len(rejected_labels),
        "complete_labels": complete_labels, "producer_rejection_labels": rejected_labels,
        "old_exact_unknown_labels": sorted(OLD_EXACT_UNKNOWN),
        "producer_build_identity": build_identity}
    return {"manifest": manifest, "report": report, "samples": samples,
            "previous": previous, "complete": complete_labels, "rejected": rejected_labels,
            "build_identity": build_identity,
            "review_receipt": receipt, "proof": proof_out, "study": study, "review": review}


def _dependencies():
    from scripts import exact_selected_matrix_free_certificate as certificate
    from scripts import preflop_validation as numeric
    from pokerlab import exact_selected_solver as solver
    from pokerlab import exact_selected_kernel as kernel
    from pokerlab import native_exact_four_street as native
    from pokerlab import packed_operator_cfr as packed
    from pokerlab import cards
    return SimpleNamespace(certificate=certificate, numeric=numeric, solver=solver,
        kernel=kernel, native=native, packed=packed, cards=cards)


def _forbidden(counter, label, calls):
    def reject(*_args, **_kwargs):
        calls[counter] += 1
        raise AssertionError("forbidden production path entered: " + label)
    return reject


def _protected(deps, calls):
    stack = ExitStack()
    for obj, name, key in (
        (deps.solver, "solve_four_street_exact_selected", "solver"),
        (deps.solver, "_prepare_exact_selected", "prepare"),
        (deps.solver, "train_packed", "trainer"),
        (deps.packed, "train_packed", "packed_trainer"),
        (deps.kernel.ExactSelectedRunoutKernel, "__init__", "production_kernel"),
        (deps.native, "_invoke", "native"),
        (deps.native, "train", "native_train"),
        (deps.cards, "rank_hand", "production_rank"),
    ):
        if hasattr(obj, name):
            stack.enter_context(patch.object(obj, name, new=_forbidden(key, name, calls)))
    return stack


def _payload_from(raw, sample):
    _need(type(raw) is dict and raw.get("status") == "complete" and
          raw.get("failure") is None and type(raw.get("payload")) is dict,
          "complete saved child payload schema is malformed")
    fields = ("case", "iterations", "native_payoffs", "native_traversal", "routing",
              "sample", "traced", "request_case", "native_admission", "counts",
              "native_observations", "payload_sha256", "payload_bytes")
    _need(all(raw.get(key) == sample.get(key) for key in fields),
          "saved raw child selectors/input differ from the frozen report row")
    payload = raw["payload"]
    _need(_sha(_canonical(payload)) == sample["payload_sha256"],
          "canonical saved policy hash differs from the producer report")
    return payload


def _known_resource_error(exc):
    if type(exc) is not ValueError:
        return False
    message = str(exc)
    return any(pattern.fullmatch(message) for pattern in _RESOURCE_ERRORS)


def _old_numeric_binding(verification, payload):
    numeric = verification.get("numeric")
    gaps = verification.get("numeric_metric_gaps")
    _need(type(numeric) is dict and numeric.get("status") == "complete" and
          type(numeric.get("result")) is dict and type(gaps) is dict and set(gaps) == set(METRICS),
          "saved numeric replay receipt is incomplete")
    _need(numeric["result"].get("checked_information_sets") == payload.get("info_sets"),
          "saved numeric replay checked-row count differs")
    _need(all(type(value) in (int, float) and not isinstance(value, bool) and
              math.isfinite(value) and 0 <= value <= OLD_NUMERIC_TOLERANCE
              for value in gaps.values()), "saved numeric replay receipt failed its old tolerance")
    return {"status": "complete", "artifact_hash_bound": True,
            "metric_gaps": gaps, "tolerance": OLD_NUMERIC_TOLERANCE,
            "checked_information_sets": numeric["result"]["checked_information_sets"]}


def _fresh_numeric(case, payload, deps):
    replay = deps.numeric.replay_policy(payload, case["sb_range"], case["bb_range"],
        config=case["config"], runouts=case["runouts"],
        flop_config=case["flop_config"], turn_config=case["turn_config"],
        river_config=case["river_config"])
    metrics = {key: replay[key] for key in (
        "value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value")}
    metrics["sb_gain"] = max(0.0, metrics["sb_best_response_value"] - metrics["value_sb"])
    metrics["bb_gain"] = max(0.0, metrics["bb_best_response_value"] + metrics["value_sb"])
    metrics["nash_conv"] = metrics["sb_gain"] + metrics["bb_gain"]
    metrics["exploitability"] = metrics["nash_conv"] / 2.0
    _need(type(replay.get("checked_information_sets")) is int and
          replay["checked_information_sets"] == payload.get("info_sets"),
          "fresh physical replay did not check every serialized row")
    _need(all(type(value) in (int, float) and not isinstance(value, bool) and math.isfinite(value)
              for value in metrics.values()), "fresh physical replay returned nonfinite metrics")
    return {"status": "complete", "metrics": metrics,
            "checked_information_sets": replay["checked_information_sets"],
            "worlds": replay.get("worlds"), "monetary_mode": replay.get("monetary_mode")}


def _metric_gaps(exact_result, numeric_metrics):
    exact_metrics = exact_result.get("metrics")
    _need(type(exact_metrics) is dict and set(exact_metrics) == {
        "value_sb", "value_bb", "sb_best_response_value", "bb_best_response_value",
        "sb_best_response_gain", "bb_best_response_gain", "nash_conv", "exploitability",
        "lower_value_bound", "upper_value_bound"}, "new exact metric schema changed")
    gaps = {}
    for exact_key, numeric_key in EXACT_TO_NUMERIC.items():
        value = float(_parse_bounded_fraction(exact_metrics[exact_key]))
        gap = abs(value - numeric_metrics[numeric_key])
        _need(math.isfinite(gap), "fresh numeric/exact metric comparison is nonfinite")
        gaps[exact_key] = gap
    return gaps


_EXACT_FRACTION = re.compile(r"(-?(?:0|[1-9][0-9]*))(?:/([1-9][0-9]*))?\Z", re.ASCII)
_MAX_EXACT_BITS = 65536
_MAX_DECIMAL_DIGITS = 19729


def _bounded_decimal_integer(text, *, signed):
    _need(type(text) is str and text.isascii(), "exact metric integer must be ASCII text")
    negative = text.startswith("-") if signed else False
    digits = text[1:] if negative else text
    _need(bool(digits) and len(digits) <= _MAX_DECIMAL_DIGITS and digits.isdigit(),
          "exact metric integer text exceeds its bounded canonical form")
    _need(not (len(digits) > 1 and digits[0] == "0"),
          "exact metric integer text has a leading zero")
    value = 0
    first = len(digits) % 9 or 9
    value = int(digits[:first])
    for offset in range(first, len(digits), 9):
        value = value * 1_000_000_000 + int(digits[offset:offset + 9])
    _need(value.bit_length() <= _MAX_EXACT_BITS,
          "exact metric integer exceeds the 65536-bit comparison bound")
    return -value if negative and value else value


def _parse_bounded_fraction(value):
    _need(type(value) is str and len(value) <= 2 * _MAX_DECIMAL_DIGITS + 2,
          "exact metric fraction text exceeds its bounded input length")
    match = _EXACT_FRACTION.fullmatch(value)
    _need(match is not None, "exact metric fraction text is malformed")
    _need(match.group(1) != "-0", "exact metric integer text has negative zero")
    numerator = _bounded_decimal_integer(match.group(1), signed=True)
    denominator = (1 if match.group(2) is None else
                   _bounded_decimal_integer(match.group(2), signed=False))
    _need(denominator > 0, "exact metric denominator must be positive")
    from fractions import Fraction
    return Fraction(numerator, denominator)


def _compare_old_exact(new, old):
    _need(type(old) is dict, "old exact certificate is unavailable for a historically complete row")
    _need(new.get("legacy_model_case_canonical_sha256") == old.get("input_case_canonical_sha256"),
          "new/old exact certificate input-case canonical hashes differ")
    _need(new.get("normalized_policy_sha256") == old.get("normalized_policy_sha256") and
          _canonical(new.get("normalized_policy_rows")) == _canonical(old.get("normalized_policy_rows")),
          "new/old exact normalized full policy rows or hash differ")
    _need(new.get("metrics") == old.get("metrics") and
          new.get("threshold") == old.get("threshold") == "1/1000" and
          type(new.get("threshold_met")) is bool and
          new.get("threshold_met") == old.get("threshold_met"),
          "new/old exact metrics or threshold flag differ")
    return {"verified": True, "normalized_policy_sha256": new["normalized_policy_sha256"],
            "normalized_policy_rows_identical": True, "all_exact_metrics_identical": True,
            "threshold": new["threshold"], "threshold_met": new["threshold_met"]}


def _record(label, sample, source_raw_hash, payload_hash, prior, new_status,
            result_name=None, result_hash=None, error_name=None, error_hash=None,
            fresh_name=None, fresh_hash=None, old_numeric_binding=None,
            numeric_gaps=None, comparison=None, build_identity_sha256=None,
            certificate_wall_seconds=None):
    old_exact_path = label + "-verification.json"
    return {"schema": RECORD_SCHEMA, "label": label,
        "producer_commit": PRODUCER_COMMIT, "producer_label": label,
        "source_raw_artifact": sample["artifact"], "source_raw_sha256": source_raw_hash,
        "source_counts": sample.get("counts"),
        "source_native_observations": sample.get("native_observations"),
        "payload_sha256": payload_hash, "previous_exact_status": prior["status"],
        "status": new_status, "result_artifact": result_name, "result_sha256": result_hash,
        "error_artifact": error_name, "error_sha256": error_hash,
        "old_exact_artifact": old_exact_path,
        "old_exact_sha256": prior["artifact_sha256"],
        "producer_build_identity_artifact": "producer-build-identity.json",
        "producer_build_identity_sha256": build_identity_sha256,
        "old_numeric_artifact": old_exact_path,
        "old_numeric_sha256": prior["artifact_sha256"],
        "old_numeric_binding": old_numeric_binding,
        "numeric_replay_artifact": fresh_name, "numeric_replay_sha256": fresh_hash,
        "numeric_metric_gaps": numeric_gaps, "numeric_metric_tolerance": NUMERIC_TOLERANCE,
        "old_exact_comparison": comparison,
        "certificate_wall_seconds": certificate_wall_seconds}


def _check_raw_inputs(study, sample, prior, raw_bytes, verification_bytes):
    _need(_sha(raw_bytes) == sample["source_raw_sha256"], "frozen raw policy bytes drifted")
    _need(_sha(verification_bytes) == prior["artifact_sha256"], "frozen prior verification bytes drifted")
    _need(_sha((Path(study) / sample["artifact"]).read_bytes()) == sample["source_raw_sha256"] and
          _sha((Path(study) / prior["artifact"]).read_bytes()) == prior["artifact_sha256"],
          "frozen input artifacts changed during certification")


def _check_captured(output, captured):
    for name, digest in captured.items():
        path = _safe_artifact_path(Path(output), name)
        _need(path.is_file() and not path.is_symlink() and _sha(path.read_bytes()) == digest,
              "capture-time certificate evidence drifted: " + name)


def _validate_candidate_result(result, sample, payload_hash):
    _need(type(result) is dict and result.get("contract") == "matrix-free-selected-certificate-v1" and
          result.get("source_identity") == "four-street-independent-matrix-free-exact-v1" and
          result.get("input_policy_canonical_sha256") == payload_hash and
          result.get("input_case_canonical_sha256") == _sha(_canonical(sample["request_case"])),
          "new certificate raw input identity or contract differs")
    _need(all(type(result.get(key)) is int and result[key] == 0 for key in
              ("production_pair_rows", "training_calls", "native_calls")),
          "new certificate reports a production/training path")
    operator = result.get("operator", {})
    _need(type(operator) is dict and all(type(operator.get(key)) is int and operator[key] == 0
              for key in ("stored_pairs", "stored_worlds")), "new verifier retained forbidden world/pair records")
    _need(type(result.get("normalized_policy_rows")) is list and
          _sha(_canonical(result["normalized_policy_rows"])) == result.get("normalized_policy_sha256"),
          "new normalized policy hash differs from its rows")
    _need(result.get("threshold") == "1/1000" and type(result.get("threshold_met")) is bool,
          "new exact quality threshold or flag changed")
    budget, forecast = result.get("budget"), result.get("forecast")
    _need(type(budget) is dict and type(forecast) is dict and budget.get("limits") == CERTIFICATE_LIMITS,
          "new exact logical resource model/limits changed")
    for field, upper, ceiling in (("work", "whole_work_upper", CERTIFICATE_LIMITS["work"]),
                                  ("entries", "whole_entries_upper", CERTIFICATE_LIMITS["entries"])):
        _need(type(budget.get(field)) is int and type(forecast.get(upper)) is int and
              0 < budget[field] <= forecast[upper] <= ceiling,
              "new exact work/entry receipt exceeded its admitted envelope")
    _need(type(budget.get("created_bits")) is int and 0 <= budget["created_bits"] <= CERTIFICATE_LIMITS["created_bits"] and
          type(budget.get("max_forecast_bits")) is int and 0 < budget["max_forecast_bits"] <= CERTIFICATE_LIMITS["integer_bits"],
          "new exact Fraction forecast receipt exceeded its limit")


def _dependencies_after_auth():
    return _dependencies()


def _run_one(label, sample, previous, study, output, deps, protected_calls, capture,
             build_identity_sha256, check_captured):
    raw_path = Path(study) / sample["artifact"]
    verification_path = Path(study) / previous["artifact"]
    raw_bytes = raw_path.read_bytes()
    verification_bytes = verification_path.read_bytes()
    source_raw_hash = _sha(raw_bytes)
    _need(source_raw_hash == sample["source_raw_sha256"],
          "raw source SHA differs from authenticated original manifest")
    _need(_sha(verification_bytes) == previous["artifact_sha256"],
          "saved old verification SHA differs from authenticated manifest")
    _check_raw_inputs(study, {**sample, "source_raw_sha256": source_raw_hash},
                      previous, raw_bytes, verification_bytes)
    raw = _decode(raw_bytes)
    payload = _payload_from(raw, sample)
    payload_hash = _sha(_canonical(payload))
    old_numeric = _old_numeric_binding(previous["verification"], payload)
    result_name = f"results/{label}-result.json"
    error_name = f"errors/{label}-error.json"
    validation_error_name = f"errors/{label}-validation-error.json"
    numeric_name = f"numeric/{label}-replay.json"
    old_exact = None
    if previous["status"] == "complete":
        old_exact = previous["verification"]["exact"]["result"]["exact_certificate"]
    result = None
    result_hash = None
    fresh_hash = None
    comparison = None
    gaps = None
    certificate_wall_seconds = None

    def fresh_replay():
        check_captured()
        try:
            value = _fresh_numeric(sample["request_case"], payload, deps)
        finally:
            _need(_sha(_canonical(payload)) == payload_before,
                  "fresh numeric replay mutated the saved policy")
            _check_raw_inputs(study, sample, previous, raw_bytes, verification_bytes)
            check_captured()
        return value, capture(numeric_name, _json_bytes(value))

    try:
        check_captured()
        payload_before = _sha(_canonical(payload))
        certificate_started = time.perf_counter()
        try:
            result = deps.certificate.evaluate_exact(sample["request_case"], payload)
        except Exception as exc:
            certificate_wall_seconds = time.perf_counter() - certificate_started
            error_raw = _json_bytes({"type": type(exc).__name__, "message": str(exc)})
            error_hash = capture(error_name, error_raw)
            _need(_sha(_canonical(payload)) == payload_before,
                  "candidate certificate mutated the saved policy before failure")
            _check_raw_inputs(study, sample, previous, raw_bytes, verification_bytes)
            check_captured()
            status = "resource-unverified" if _known_resource_error(exc) else "failed"
            if status == "resource-unverified":
                _fresh, fresh_hash = fresh_replay()
            row = _record(label, sample, source_raw_hash, payload_hash, previous, status,
                error_name=error_name, error_hash=error_hash,
                fresh_name=numeric_name if fresh_hash is not None else None, fresh_hash=fresh_hash,
                old_numeric_binding=old_numeric, comparison=None,
                build_identity_sha256=build_identity_sha256,
                certificate_wall_seconds=certificate_wall_seconds)
            capture(f"records/{label}-certificate.json", _json_bytes(row))
            return row, None, None if status == "resource-unverified" else {
                "stage": "candidate-certificate", "label": label,
                "type": type(exc).__name__, "message": str(exc)}
        certificate_wall_seconds = time.perf_counter() - certificate_started
        result_raw = _json_bytes(result)
        result_hash = capture(result_name, result_raw)
        _need(_sha(_canonical(payload)) == payload_before,
              "candidate certificate mutated the saved policy object")
        _validate_candidate_result(result, sample, payload_hash)
        comparison = _compare_old_exact(result, old_exact) if old_exact is not None else None
        fresh, fresh_hash = fresh_replay()
        gaps = _metric_gaps(result, fresh["metrics"])
        _need(all(0 <= value <= NUMERIC_TOLERANCE for value in gaps.values()),
              "fresh independent numeric replay differs from exact certificate by more than 1e-9")
        _check_raw_inputs(study, {**sample, "source_raw_sha256": source_raw_hash},
                          previous, raw_bytes, verification_bytes)
        row = _record(label, sample, source_raw_hash, payload_hash, previous, "complete",
            result_name, result_hash, fresh_name=numeric_name, fresh_hash=fresh_hash,
            old_numeric_binding=old_numeric, numeric_gaps=gaps, comparison=comparison,
            build_identity_sha256=build_identity_sha256,
            certificate_wall_seconds=certificate_wall_seconds)
        capture(f"records/{label}-certificate.json", _json_bytes(row))
        return row, {"result": result, "gaps": gaps}, None
    except Exception as exc:
        error_raw = _json_bytes({"type": type(exc).__name__, "message": str(exc)})
        error_hash = capture(validation_error_name, error_raw)
        status = "failed"
        row = _record(label, sample, source_raw_hash, payload_hash, previous, status,
            result_name=result_name if result_hash is not None else None,
            result_hash=result_hash, error_name=validation_error_name,
            error_hash=error_hash, fresh_name=numeric_name if fresh_hash is not None else None,
            fresh_hash=fresh_hash, old_numeric_binding=old_numeric,
            numeric_gaps=gaps, comparison=comparison,
            build_identity_sha256=build_identity_sha256,
            certificate_wall_seconds=certificate_wall_seconds)
        capture(f"records/{label}-certificate.json", _json_bytes(row))
        return row, None, {"stage": "post-certificate-validation", "label": label,
            "type": type(exc).__name__, "message": str(exc)}


def run(output, *, producer_repo, study=DEFAULT_STUDY, review=DEFAULT_REVIEW):
    output = Path(output).resolve()
    study = Path(study).resolve()
    review = Path(review).resolve()
    producer_repo = Path(producer_repo).resolve()
    _need(output != ROOT and ROOT not in output.parents and not output.exists(),
          "use a new external saved-certificate output directory")
    _need(output != study and study not in output.parents and output != producer_repo and
          producer_repo not in output.parents and output != review and review not in output.parents,
          "output directory must be outside source/artifact inputs")
    output.mkdir(parents=True)
    captured = {}
    rows = []
    labels_entered = 0
    first_failure = None
    current_before = producer_before = None
    deps = None
    protected_calls = {key: 0 for key in ("solver", "prepare", "trainer", "packed_trainer",
        "production_kernel", "native", "native_train", "production_rank")}

    def capture(name, raw):
        _check_captured(output, captured)
        path = _safe_artifact_path(output, name)
        _need(name not in captured and not path.exists(), "duplicate saved-certificate evidence path")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        digest = _sha(raw)
        captured[name] = digest
        return digest

    try:
        # Both source checkouts and all external inputs are authenticated using
        # only the standard library before any project/certificate import.
        current_before = _tree_identity(ROOT)
        capture("source-before.json", _json_bytes(current_before))
        producer_before = _tree_identity(producer_repo)
        capture("producer-source-before.json", _json_bytes(producer_before))
        _need(producer_before["commit"] == PRODUCER_COMMIT,
              "explicit producer checkout is not the frozen 946671d8 source")
        saved = _authenticate_saved(study, review, producer_before)
        capture("producer-artifact-auth.json", _json_bytes(saved["proof"]))
        capture("producer-build-identity.json", _json_bytes(saved["build_identity"]))
        capture("protocol.json", _json_bytes({"version": MANIFEST_SCHEMA,
            "current_source_commit": current_before["commit"], "current_source_sha256": current_before["sha256"],
            "producer_commit": producer_before["commit"], "producer_source_sha256": producer_before["sha256"],
            "producer_manifest_sha256": STUDY_MANIFEST_SHA256,
            "producer_report_sha256": STUDY_REPORT_SHA256,
            "old_review_receipt_sha256": OLD_REVIEW_RECEIPT_SHA256,
            "schedule_counts": {"producer_complete": 28, "producer_rejected": 6,
                "old_exact_complete": 22, "old_exact_unknown": 6},
            "old_exact_unknown_labels": sorted(OLD_EXACT_UNKNOWN),
            "producer_rejection_labels": sorted(PRODUCER_REJECTIONS),
            "numeric_replay": "fresh scripts.preflop_validation.replay_policy for every complete payload; prior numeric verification separately hash-bound",
            "numeric_metric_tolerance": NUMERIC_TOLERANCE,
            "certificate_limits": CERTIFICATE_LIMITS,
            "source_authentication_precedes_project_imports": True,
            "runtime": {"python_version": sys.version, "executable": sys.executable,
                        "implementation": platform.python_implementation(), "platform": sys.platform},
            "candidate_training_calls": 0, "production_pair_tables": 0,
            "scope": "Saved complete policies from the fixed 34-child finite selected-runout study. Six producer rejections are not certified and remain unknown."}))
        deps = _dependencies_after_auth()
        # Snapshot the complete saved input corpus so later drift checks cover
        # every raw/native capture, manifest, report and capture-time pin.
        input_manifest, _input_report, input_hashes = _artifact_hashes(study)
        for label in saved["complete"]:
            if first_failure is not None:
                break
            sample = {**saved["samples"][label],
                      "source_raw_sha256": saved["proof"]["study_files"][saved["samples"][label]["artifact"]]}
            previous = dict(saved["previous"][label])
            # Re-read the verification after copying its status so records bind
            # exact raw bytes, not just the decoded prior certificate values.
            ver_path = study / previous["artifact"]
            previous["artifact_sha256"] = _sha(ver_path.read_bytes())
            _need(_tree_identity_shallow(ROOT) ==
                  (current_before["commit"], current_before["status"], current_before["sha256"]),
                  "candidate source changed before saved policy certification")
            _need(_tree_identity_shallow(producer_repo) ==
                  (producer_before["commit"], producer_before["status"], producer_before["sha256"]),
                  "producer source changed before saved policy certification")
            try:
                labels_entered += 1
                with _protected(deps, protected_calls):
                    row, outcome, failure = _run_one(label, sample, previous,
                        study, output, deps, protected_calls, capture,
                        _sha(_json_bytes(saved["build_identity"])),
                        lambda: _check_captured(output, captured))
                rows.append(row)
                _check_captured(output, captured)
                _need(_tree_identity_shallow(ROOT) ==
                      (current_before["commit"], current_before["status"], current_before["sha256"]),
                      "candidate source changed during saved policy mathematics")
                _need(_tree_identity_shallow(producer_repo) ==
                      (producer_before["commit"], producer_before["status"], producer_before["sha256"]),
                      "producer source changed during saved policy mathematics")
                print(label, row["status"], flush=True)
                if failure is not None:
                    first_failure = failure
                    _write(output / "first-failure.json", failure)
                elif outcome is not None:
                    pass
            except Exception as exc:
                failure = {"stage": "saved-policy", "label": label,
                    "type": type(exc).__name__, "message": str(exc)}
                first_failure = failure
                _write(output / "first-failure.json", failure)

        _need(all(value == 0 for value in protected_calls.values()),
              "a forbidden training/production path was entered")
        _need(len(rows) == len(saved["complete"]) or first_failure is not None,
              "saved-certificate pass ended without a complete inventory or first failure")
    except Exception as exc:
        if first_failure is None:
            first_failure = {"stage": "preflight", "type": type(exc).__name__, "message": str(exc)}
            _write(output / "first-failure.json", first_failure)
    finally:
        try:
            _check_captured(output, captured)
        except Exception as exc:
            drift = {"stage": "captured-output-after", "type": type(exc).__name__, "message": str(exc)}
            _write(output / "capture-drift.json", drift)
            if first_failure is None:
                first_failure = drift
        _write(output / "capture-time-sha256.json", captured)
        try:
            if current_before is not None:
                current_after = _tree_identity(ROOT, require_clean=False)
                _write(output / "source-after.json", current_after)
                _need(current_after == current_before, "candidate source changed during saved certification")
        except Exception as exc:
            drift = {"stage": "source-after", "type": type(exc).__name__, "message": str(exc)}
            _write(output / "source-after-error.json", drift)
            if first_failure is None:
                first_failure = drift
        try:
            if producer_before is not None:
                producer_after = _tree_identity(producer_repo, require_clean=False)
                _write(output / "producer-source-after.json", producer_after)
                _need(producer_after == producer_before, "producer source changed during saved certification")
        except Exception as exc:
            drift = {"stage": "producer-source-after", "type": type(exc).__name__, "message": str(exc)}
            _write(output / "producer-source-after-error.json", drift)
            if first_failure is None:
                first_failure = drift
        try:
            if "saved" in locals():
                after_hashes = _artifact_hashes(study)[2]
                _need(after_hashes == input_hashes, "frozen producer study artifacts changed during certification")
                _write(output / "producer-artifact-after.json", {"files": after_hashes,
                    "stable": True, "manifest_sha256": STUDY_MANIFEST_SHA256,
                    "report_sha256": STUDY_REPORT_SHA256})
                build_after = _authenticate_build(producer_repo, study, after_hashes,
                                                   saved["review_receipt"])
                _need(build_after == saved["build_identity"],
                      "frozen producer executable/build/header identity changed during certification")
                _write(output / "producer-build-identity-after.json", build_after)
                _need(_sha((review / "attempt1" / "receipt.json").read_bytes()) == OLD_REVIEW_RECEIPT_SHA256 and
                      _sha((review / "process-observation.json").read_bytes()) == OLD_REVIEW_OBSERVATION_SHA256,
                      "old independent review receipt/provenance changed during certification")
        except Exception as exc:
            drift = {"stage": "producer-artifacts-after", "type": type(exc).__name__, "message": str(exc)}
            _write(output / "producer-artifact-after-error.json", drift)
            if first_failure is None:
                first_failure = drift

    report = {"schema": MANIFEST_SCHEMA, "current_source_commit": current_before.get("commit") if current_before else None,
        "producer_commit": producer_before.get("commit") if producer_before else None,
        "records": rows, "records_attempted": labels_entered, "records_captured": len(rows), "records_planned": 28,
        "candidate_complete": sum(row.get("status") == "complete" for row in rows),
        "candidate_resource_unverified": sum(row.get("status") == "resource-unverified" for row in rows),
        "historical_exact_unknowns_retained": 6, "producer_rejections_not_certified": 6,
        "forbidden_calls": protected_calls, "failure": first_failure,
        "scope": "Independent exact certificates for saved finite selected-runout policies only. No producer reruns, training, production kernel calls, full-deck or unrestricted quality claim."}
    _write(output / "report.json", report)
    files = {str(path.relative_to(output)).replace("\\", "/"): _sha(path.read_bytes())
             for path in sorted(output.rglob("*")) if path.is_file() and path.name != "manifest.json"}
    _write(output / "manifest.json", {"version": MANIFEST_SCHEMA,
        "current_source_commit": report["current_source_commit"],
        "producer_commit": report["producer_commit"], "records": [
            {"label": row["label"], "record_artifact": f"records/{row['label']}-certificate.json",
             "record_sha256": files.get(f"records/{row['label']}-certificate.json"),
             "source_raw_artifact": row["source_raw_artifact"],
             "source_raw_sha256": row["source_raw_sha256"], "status": row["status"],
             "previous_exact_status": row["previous_exact_status"]} for row in rows],
        "files": files})
    return {"outcome": "complete" if first_failure is None and len(rows) == 28 else "failed",
            "records_attempted": len(rows), "failure": first_failure}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--producer-repo", type=Path, required=True)
    parser.add_argument("--study-dir", type=Path, default=DEFAULT_STUDY)
    parser.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW)
    args = parser.parse_args()
    result = run(args.output, producer_repo=args.producer_repo,
                 study=args.study_dir, review=args.review_dir)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    raise SystemExit(0 if result["outcome"] == "complete" else 1)


if __name__ == "__main__":
    main()
