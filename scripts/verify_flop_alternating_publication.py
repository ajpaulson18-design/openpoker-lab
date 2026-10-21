"""Authenticate and independently replay the immutable three-method flop study.

Pins retain the completed quality miss, exact measured Git sources and
the incident receipt that qualifies the complete-call timing observations. A separate
scratch-incident receipt records transient non-input worktree dirt. The source
was clean at both captured input snapshots, but timing observations carry the
receipt's incidental-I/O qualification; do not claim the checkout was clean
throughout the run.
"""
import argparse
import hashlib
import json
from pathlib import Path

from scripts import benchmark_flop_alternating as study
from scripts.benchmark_preflop_covered_counts import checksum


PUBLICATION = study.ROOT / "benchmarks/results/weighted-full-deck-flop-alternating-v1"
BASELINE_PUBLICATION = study.ROOT / "benchmarks/results/weighted-full-deck-flop-cfrplus-v1"
SOURCE_SIDECAR = study.ROOT / "benchmarks/results/weighted-full-deck-flop-alternating-v1-git-source.json"
INCIDENT_SIDECAR = study.ROOT / "benchmarks/results/weighted-full-deck-flop-alternating-v1-scratch-incident.json"
INDEX_SHA256 = "32b549df30ce3ac13a12b1fdd32c2cefda795feb7ed0364f6eb1960bfd5c1088"
ARTIFACT_SHA256 = "aee1a69f9e88fe2b35a3bb7ea85df045958fc315087daef4df0e14b21d7c5e90"
SOURCE_SIDECAR_SHA256 = "7585828fed5cb4b34173852b23ca1800e989cb4815b7d420ad915e2299fa0d5e"
INCIDENT_SHA256 = "eca613ce1667872e63b4632a2c5a553c281ab5b0eab268a09df4c3094ad42ab1"
SOURCE_REVISION = "481e7ec508724be5012a895f6e53b5b3d375034a"
SOURCE_FILES = 626
SOURCE_HASHES_SHA256 = "0d77d79d310231833ff25414205df12c845de1261b7c583c9c7f801e67920b81"
SOURCE_GIT_LF_MANIFEST_SHA256 = "dc48bb7a6c7335549788988b82169adfcc40e7a1da8a699610415fc1b98cc866"
SPEC_SHA256 = "738e8f123a3bdb844efdfe78638ce4954dfcb65fd0979e351e28ff853d72192d"
MAX_INDEX_BYTES = 4 * 1024 * 1024
MAX_SIDECAR_BYTES = 2 * 1024 * 1024
MAX_INCIDENT_BYTES = 64 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _is_sha256(value):
    return (type(value) is str and len(value) == 64
            and all(char in "0123456789abcdef" for char in value))


def _require_frozen_pin(value, label):
    if not _is_sha256(value) or value.startswith("__"):
        raise ValueError("Publication pin is not finalized: " + label)


def _read_bounded_json(path, limit, label):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Invalid bounded " + label)
    raw = path.read_bytes()
    if len(raw) > limit:
        raise ValueError(label + " grew beyond its byte limit")
    try:
        parsed = json.loads(raw, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Invalid " + label + " JSON") from exc
    return raw, parsed


def _validate_source_record(before, after, sidecar_raw, sidecar):
    if type(before) is not dict or type(after) is not dict or before != after:
        raise ValueError("Published source snapshot changed during measurement")
    if (before.get("revision") != SOURCE_REVISION or type(before.get("revision")) is not str
            or before.get("status") != [] or type(before.get("status")) is not list):
        raise ValueError("Published measured source revision or clean status changed")
    source_hashes = before.get("source_hashes")
    if (type(source_hashes) is not dict or len(source_hashes) != SOURCE_FILES
            or checksum(source_hashes) != SOURCE_HASHES_SHA256):
        raise ValueError("Published measured source map changed")
    lf_hashes = {}
    for path, entry in source_hashes.items():
        if (type(path) is not str or not path or path.startswith(("/", "\\"))
                or ".." in Path(path).parts or "\\" in path
                or type(entry) is not dict or set(entry) != {"raw_sha256", "lf_sha256"}
                or not _is_sha256(entry.get("raw_sha256"))
                or not _is_sha256(entry.get("lf_sha256"))):
            raise ValueError("Published source map entry is malformed")
        lf_hashes[path] = entry["lf_sha256"]
    if checksum(lf_hashes) != SOURCE_GIT_LF_MANIFEST_SHA256:
        raise ValueError("Published Git-LF source manifest changed")

    expected_keys = {
        "captured_files", "captured_source_hashes_sha256", "git_lf_manifest_sha256",
        "git_lf_source_hashes", "matched_git_lf_files", "method", "mismatches",
        "source_revision",
    }
    if type(sidecar) is not dict or set(sidecar) != expected_keys:
        raise ValueError("Git-LF sidecar schema changed")
    if (type(sidecar.get("captured_files")) is not int
            or sidecar["captured_files"] != SOURCE_FILES
            or type(sidecar.get("matched_git_lf_files")) is not int
            or sidecar["matched_git_lf_files"] != SOURCE_FILES
            or sidecar.get("source_revision") != SOURCE_REVISION
            or sidecar.get("captured_source_hashes_sha256") != SOURCE_HASHES_SHA256
            or sidecar.get("git_lf_manifest_sha256") != SOURCE_GIT_LF_MANIFEST_SHA256
            or sidecar.get("mismatches") != [] or type(sidecar.get("mismatches")) is not list
            or sidecar.get("git_lf_source_hashes") != lf_hashes):
        raise ValueError("Git-LF sidecar does not attest the measured source snapshot")
    if type(sidecar.get("method")) is not str or not sidecar["method"]:
        raise ValueError("Git-LF sidecar method is missing")
    if len(sidecar_raw) > MAX_SIDECAR_BYTES:
        raise ValueError("Git-LF sidecar exceeds its byte limit")
    return checksum(source_hashes), checksum(lf_hashes)


def _validate_incident(raw, incident):
    expected_keys = {
        "action", "corrected_at_utc", "destination_directory", "detected_at_utc",
        "draft_creation_time_utc", "draft_last_write_time_utc", "draft_sha256",
        "last_observed_active_request_before_correction", "scope", "source_files",
        "source_git_status", "source_git_status_after", "source_hashes_sha256",
        "source_map_identical_to_prelaunch", "source_path", "source_revision",
        "timing_limit",
    }
    if type(incident) is not dict or set(incident) != expected_keys:
        raise ValueError("Scratch-incident receipt schema changed")
    if (type(incident.get("source_revision")) is not str
            or incident["source_revision"] != SOURCE_REVISION
            or type(incident.get("source_files")) is not int
            or incident["source_files"] != SOURCE_FILES
            or type(incident.get("source_hashes_sha256")) is not str
            or incident["source_hashes_sha256"] != SOURCE_HASHES_SHA256
            or incident.get("source_map_identical_to_prelaunch") is not True
            or type(incident.get("source_git_status_after")) is not list
            or incident["source_git_status_after"] != []):
        raise ValueError("Scratch-incident receipt does not match clean captured source identity")
    if (type(incident.get("source_git_status")) is not list
            or not incident["source_git_status"]
            or any(type(line) is not str for line in incident["source_git_status"])):
        raise ValueError("Scratch-incident initial status is malformed")
    for field in ("action", "corrected_at_utc", "destination_directory", "detected_at_utc",
                  "draft_creation_time_utc", "draft_last_write_time_utc", "scope",
                  "source_path", "timing_limit"):
        if type(incident.get(field)) is not str or not incident[field]:
            raise ValueError("Scratch-incident field is malformed: " + field)
    if not _is_sha256(incident.get("draft_sha256")):
        raise ValueError("Scratch-incident draft digest is malformed")
    request = incident.get("last_observed_active_request_before_correction")
    if (type(request) is not dict
            or set(request) != {"completed_samples", "method", "repeat"}
            or type(request.get("completed_samples")) is not int
            or request["completed_samples"] < 0
            or type(request.get("repeat")) is not int or request["repeat"] < 1
            or type(request.get("method")) is not str or not request["method"]):
        raise ValueError("Scratch-incident active-request receipt is malformed")
    if len(raw) > MAX_INCIDENT_BYTES:
        raise ValueError("Scratch-incident receipt exceeds its byte limit")
    return hashlib.sha256(raw).hexdigest(), incident["timing_limit"]


def verify_saved(directory=PUBLICATION, *, baseline_directory=BASELINE_PUBLICATION,
                 source_sidecar=SOURCE_SIDECAR, incident_sidecar=INCIDENT_SIDECAR,
                 require_quality=False):
    _require_frozen_pin(INDEX_SHA256, "raw report index")
    _require_frozen_pin(ARTIFACT_SHA256, "canonical report artifact")
    _require_frozen_pin(SOURCE_SIDECAR_SHA256, "Git-LF source sidecar")
    _require_frozen_pin(INCIDENT_SHA256, "scratch-incident sidecar")
    raw, report = _read_bounded_json(Path(directory) / "index.json", MAX_INDEX_BYTES,
                                     "published alternating index")
    if hashlib.sha256(raw).hexdigest() != INDEX_SHA256:
        raise ValueError("Immutable published alternating index changed")
    if type(report) is not dict:
        raise ValueError("Published alternating index must be an object")
    unsigned = dict(report)
    artifact = unsigned.pop("artifact_sha256", None)
    if (artifact != ARTIFACT_SHA256 or checksum(unsigned) != ARTIFACT_SHA256):
        raise ValueError("Published canonical alternating artifact changed")
    spec = study.load_spec()
    if (report.get("benchmark_id") != spec["benchmark_id"]
            or report.get("spec_sha256") != SPEC_SHA256
            or checksum(report.get("specification")) != SPEC_SHA256):
        raise ValueError("Published alternating benchmark specification changed")

    sidecar_raw, sidecar = _read_bounded_json(source_sidecar, MAX_SIDECAR_BYTES,
                                              "Git-LF source sidecar")
    if hashlib.sha256(sidecar_raw).hexdigest() != SOURCE_SIDECAR_SHA256:
        raise ValueError("Immutable Git-LF source sidecar changed")
    source_map_sha, git_lf_sha = _validate_source_record(
        report.get("source_before"), report.get("source_after"), sidecar_raw, sidecar)
    if source_map_sha != SOURCE_HASHES_SHA256 or git_lf_sha != SOURCE_GIT_LF_MANIFEST_SHA256:
        raise ValueError("Measured source manifest identity changed")

    incident_raw, incident = _read_bounded_json(
        incident_sidecar, MAX_INCIDENT_BYTES, "scratch-incident sidecar")
    incident_sha, timing_qualification = _validate_incident(incident_raw, incident)
    if incident_sha != INCIDENT_SHA256:
        raise ValueError("Immutable scratch-incident sidecar changed")

    if require_quality and report.get("quality_gate_met") is not True:
        raise ValueError("One or more per-method final quality gates remain unmet")
    checked = study.verify_saved(directory, baseline_directory)
    if Path(directory, "index.json").read_bytes() != raw:
        raise ValueError("Published alternating index changed during reconstruction")
    if Path(source_sidecar).read_bytes() != sidecar_raw:
        raise ValueError("Git-LF sidecar changed during reconstruction")
    if Path(incident_sidecar).read_bytes() != incident_raw:
        raise ValueError("Scratch-incident sidecar changed during reconstruction")
    return dict(
        checked,
        source_revision=SOURCE_REVISION,
        source_files=SOURCE_FILES,
        source_hashes_sha256=source_map_sha,
        git_lf_manifest_sha256=git_lf_sha,
        raw_index_sha256=INDEX_SHA256,
        canonical_artifact_sha256=ARTIFACT_SHA256,
        source_sidecar_sha256=SOURCE_SIDECAR_SHA256,
        scratch_incident_sha256=incident_sha,
        timing_qualification=timing_qualification,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=PUBLICATION)
    parser.add_argument("--baseline-directory", type=Path, default=BASELINE_PUBLICATION)
    parser.add_argument("--source-sidecar", type=Path, default=SOURCE_SIDECAR)
    parser.add_argument("--incident-sidecar", type=Path, default=INCIDENT_SIDECAR)
    parser.add_argument("--require-quality", action="store_true")
    args = parser.parse_args(argv)
    result = verify_saved(args.directory, baseline_directory=args.baseline_directory,
                          source_sidecar=args.source_sidecar,
                          incident_sidecar=args.incident_sidecar,
                          require_quality=args.require_quality)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
