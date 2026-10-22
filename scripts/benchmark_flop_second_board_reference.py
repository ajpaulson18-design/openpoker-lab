"""One frozen no-training physical-reference batch for the 7c8d9h flop.

Full worlds, a rooted numeric tree view and a candidate-only partition are
retained. This preparation does not prove a quotient or permit training.
"""
from datetime import datetime, timezone
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import platform
import sys
import traceback

from scripts import benchmark_flop_class_owned_fingerprint as previous
from scripts import flop_second_board_plan as planning
from scripts import flop_second_board_reference as reference
from scripts import verify_flop_class_owned_fingerprint_publication as prerequisite


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "benchmarks/flop-second-board-reference-v1.json"
SPEC_SHA256 = "92bf84ed5d438b75accbfa2f40e541a2efb916dd0ee0708169024a8d7f7b9ed2"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
MAX_GZIP_BYTES = 16 * 1024 * 1024
SOURCE_COUNT = 44
proof = previous.proof


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def expected_protocol():
    return {
        "protocol_id": "fixed-flop-second-board-reference-v1",
        "request": {"board": ["7c", "8d", "9h"], "physical_oracle_builds": 1,
                    "candidate_partitions": 1, "training_calls": 0,
                    "best_response_calls": 0},
        "fixture": planning.admit_plan(),
        "limits": {"preparation_rank_calls": 11880, "recheck_rank_calls": 11880,
                   "best_five_combinations_per_rank": 21,
                   "total_rank_calls": 23760, "total_best_five_combinations": 498960,
                   "physical_worlds": 5940, "physical_decisions": 10000,
                   "physical_public_states": 250000, "tree_depth": 128,
                   "tree_stack": 8192, "actions_per_node": 64,
                   "source_files": SOURCE_COUNT, "source_file_bytes": MAX_SOURCE_BYTES,
                   "index_bytes": MAX_INDEX_BYTES, "payload_bytes": MAX_PAYLOAD_BYTES,
                   "gzip_bytes": MAX_GZIP_BYTES},
        "prerequisite": {"publication_pr": 211,
                         "raw_report_sha256": prerequisite.RAW_REPORT_SHA256,
                         "report_sha256": prerequisite.REPORT_SHA256},
        "acceptance": {
            "worlds": "All 5940 ordered worlds, three exact pair priors, full support, blockers, masses, sign metadata and source counters pass fresh checks.",
            "ranker": "Fresh-cache recheck uses the same established independent reference ranker; this is consistency, not a second independent ranking algorithm.",
            "tree": "Cycle-free rooted tree, decision-index aliases, public histories, explicit node/depth/stack limits and fresh views/hashes pass.",
            "candidate": "Explicit-board candidate output retains candidate_only=true and physical_provenance=false; measured class dimensions are not assumed.",
            "source": "Identical clean committed HEAD/status and all 44 named dependency LF hashes before/after the single batch.",
            "authority": "All 41 existing guarded production authorities stay zero; one admitted physical build and candidate partition, no training or best response.",
            "failure": "Retain first error, progress counters and partial output; stop without retry, replacement or discarded observations."},
        "scope": {
            "bounds": "Named rank, world, tree, source and output bounds only; not all arithmetic, allocation, elapsed time or RSS.",
            "claims": "Reference preparation and candidate partition only. No class/tree equivalence, policy projection/lift, best-response equality, convergence, speed or unrestricted NLHE claim.",
            "provenance": "Project-owned standard-library additions; unchanged existing independent physical oracle/ranker/candidate. No third-party source/dependency, shared street kernel, default or Coach change."}}


def _protocol():
    _need(SPEC.stat().st_size <= MAX_SOURCE_BYTES, "Protocol exceeds source bound")
    with SPEC.open("rb") as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    _need(len(raw) <= MAX_SOURCE_BYTES and hashlib.sha256(
        raw.replace(b"\r\n", b"\n")).hexdigest() == SPEC_SHA256,
        "Second-board protocol differs from frozen LF pin")
    spec = json.loads(raw, object_pairs_hook=previous._pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    _need(proof._typed(spec) == proof._typed(expected_protocol()),
          "Second-board protocol schema/admission differs")
    return raw, spec


def _preflight(spec):
    _need(proof._typed(spec) == proof._typed(expected_protocol()),
          "Full second-board request differs")
    limits = spec["limits"]
    _need(reference.MAX_PREPARATION_RANK_CALLS == limits["preparation_rank_calls"] and
          reference.MAX_RECHECK_RANK_CALLS == limits["recheck_rank_calls"] and
          reference.MAX_TREE_DEPTH == limits["tree_depth"] and
          reference.MAX_TREE_STACK == limits["tree_stack"] and
          reference.MAX_ACTIONS_PER_NODE == limits["actions_per_node"],
          "Reference traversal/ranking limits differ from full admission")
    _need(limits["total_rank_calls"] == 2 * 11880 and
          limits["total_best_five_combinations"] == 23760 * 21 and
          reference.physical.MAX_DECISIONS == limits["physical_decisions"] and
          reference.physical.MAX_PUBLIC_STATES == limits["physical_public_states"],
          "Named ranking/tree reservations differ")
    return {"request": spec["request"], "fixture": planning.admit_plan(),
            "limits": dict(limits), "interpretation": spec["scope"]["bounds"]}


def _snapshot():
    state = previous._snapshot()
    hashes = dict(state["source_lf_sha256"])
    additions = ((Path(__file__), "scripts/benchmark_flop_second_board_reference.py"),
                 (Path(planning.__file__), "scripts/flop_second_board_plan.py"),
                 (Path(reference.__file__), "scripts/flop_second_board_reference.py"),
                 (Path(prerequisite.__file__),
                  "scripts/verify_flop_class_owned_fingerprint_publication.py"),
                 (SPEC, "benchmarks/flop-second-board-reference-v1.json"))
    for path, relative in additions:
        _need(path.stat().st_size <= MAX_SOURCE_BYTES, "Named source exceeds bound")
        with path.open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        _need(len(raw) <= MAX_SOURCE_BYTES, "Named source changed beyond bound")
        hashes[relative] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    _need(len(hashes) == SOURCE_COUNT and state["status"] == "",
          "Named source inventory differs or checkout is dirty")
    return {**state, "source_lf_sha256": dict(sorted(hashes.items()))}


def _output_directory(path):
    original = Path(path).absolute()
    _need(not original.exists() and not original.is_symlink() and
          all(not parent.is_symlink() for parent in original.parents),
          "Output must be a new directory without symlink traversal")
    target, root = original.resolve(), ROOT.resolve()
    _need(not target.is_relative_to(root) and not root.is_relative_to(target),
          "Output must be outside and separate from the source checkout")
    target.mkdir(parents=True)
    return target


def _write_index(directory, report):
    unsigned = {key: value for key, value in report.items() if key != "index_sha256"}
    report["index_sha256"] = proof._digest(unsigned)
    raw = json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    _need(len(raw) <= MAX_INDEX_BYTES, "Index exceeds admitted bytes")
    target = directory / "index.json.tmp"
    with target.open("wb") as stream:
        stream.write(raw)
    target.replace(directory / "index.json")


class _BoundedWriter:
    def __init__(self, stream):
        self.stream, self.bytes = stream, 0

    def write(self, data):
        _need(self.bytes + len(data) <= MAX_GZIP_BYTES, "Compressed output exceeds bound")
        result = self.stream.write(data)
        self.bytes += result
        return result

    def flush(self):
        return self.stream.flush()


def _write_payload(directory, payload):
    target = directory / "reference.json.gz"
    temp = directory / "reference.json.gz.partial"
    digest, total = hashlib.sha256(), 0
    with temp.open("xb") as stream:
        bounded = _BoundedWriter(stream)
        with gzip.GzipFile(filename="", mode="wb", fileobj=bounded, mtime=0) as compressed:
            encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)
            for chunk in encoder.iterencode(payload):
                raw = chunk.encode("utf-8")
                _need(total + len(raw) <= MAX_PAYLOAD_BYTES, "Raw payload exceeds bound")
                digest.update(raw)
                total += len(raw)
                compressed.write(raw)
            _need(total + 1 <= MAX_PAYLOAD_BYTES, "Raw payload exceeds bound")
            compressed.write(b"\n")
            digest.update(b"\n")
            total += 1
    temp.replace(target)
    gzip_digest = hashlib.sha256()
    with target.open("rb") as stream:
        for raw in iter(lambda: stream.read(65536), b""):
            gzip_digest.update(raw)
    return {"path": target.name, "raw_bytes": total, "raw_sha256": digest.hexdigest(),
            "gzip_bytes": target.stat().st_size, "gzip_sha256": gzip_digest.hexdigest()}


def _completion(payload, progress):
    _need(type(progress) is dict and progress.get("phase") == "complete" and
          all(type(progress.get(key)) is int and progress[key] == value
              for key, value in {
                  "physical_builds_attempted": 1, "physical_builds_completed": 1,
                  "candidate_builds_attempted": 1, "candidate_builds_completed": 1,
                  "physical_world_rows": 5940, "world_rows_validated": 5940,
                  "candidate_world_rows": 5940}.items()),
          "Complete single-build support/progress receipt differs")
    for prefix in ("preparation", "recheck"):
        actual, attempts = progress.get(prefix + "_rank_calls"), progress.get(prefix + "_ranker_attempts")
        _need(type(actual) is int and type(attempts) is int and
              0 < actual == attempts <= 11880, "Complete rank-call receipt differs")
    _need(type(payload) is dict and payload.get("scope") ==
          "fresh-physical-reference-and-candidate-partition-only" and
          proof._typed(payload.get("claims")) == proof._typed({
              "class_or_tree_equivalence_proved": False,
              "policy_projection_or_lift_proved": False,
              "physical_best_response_equality_proved": False,
              "training_performed": False}), "Reference claim scope differs")
    candidate = payload["candidate_partition"]
    _need(candidate.get("candidate_only") is True and candidate.get("physical_provenance") is False
          and candidate.get("board") == ["7c", "8d", "9h"]
          and candidate.get("input_completeness") == "unverified-caller-supplied-records",
          "Candidate scope or board differs")
    physical = payload["physical"]
    _need(type(physical["worlds_view"]) is list and len(physical["worlds_view"]) == 5940 and
          type(physical["tree_view"]) is list and 0 < len(physical["tree_view"]) <= 250000 and
          type(progress.get("tree_nodes_validated")) is int and
          progress["tree_nodes_validated"] == len(physical["tree_view"]) ==
          physical["tree_census"]["public_states"], "Reference retained view sizes differ")


def run(output, *, execution_state=None):
    directory, first_error, guard_calls = None, None, None
    report = {"schema_version": 1, "protocol_id": "fixed-flop-second-board-reference-v1",
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "finished_at_utc": None, "status": "not-started", "admission": None,
              "protocol_sha256": None, "source_before": None, "source_after": None,
              "prerequisite": None, "progress": {}, "payload": None,
              "summary": None, "authority_calls": None, "errors": [],
              "runtime": {"python": sys.version, "implementation": platform.python_implementation(),
                          "platform": platform.platform()}, "execution_state": None,
              "index_sha256": None}
    try:
        raw, spec = _protocol()
        report["admission"] = _preflight(spec)  # before authentication, ranking or trees
        directory = _output_directory(output)
        report["protocol_sha256"] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
        report["execution_state"] = previous.diagnostic.evidence._execution_state(execution_state)
        report["source_before"] = _snapshot()
        report["status"] = "running"
        _write_index(directory, report)
        receipt = prerequisite.verify()
        _need(receipt.get("status") == "saved-owned-fingerprint-census-authenticated" and
              receipt.get("raw_sha256") == spec["prerequisite"]["raw_report_sha256"] and
              receipt.get("report_sha256") == spec["prerequisite"]["report_sha256"] and
              all(type(receipt.get(key)) is int and receipt[key] == 0
                  for key in ("fingerprint_calls", "full_validations", "training_calls")),
              "Saved prerequisite authentication differs")
        report["prerequisite"] = receipt
        _need(proof._typed(_snapshot()) == proof._typed(report["source_before"]),
              "Source changed during saved prerequisite authentication")
        _write_index(directory, report)
        with proof.independent_guard() as calls:
            guard_calls = calls
            try:
                payload = reference.prepare_reference(planning.plan_second_board(),
                                                      progress=report["progress"])
                _completion(payload, report["progress"])
                report["summary"] = {
                    "physical": {key: value for key, value in payload["physical"].items()
                                 if key not in ("worlds_view", "tree_view")},
                    "candidate": {key: payload["candidate_partition"][key] for key in (
                        "candidate_only", "physical_provenance", "input_completeness",
                        "physical_world_count", "compatible_pair_count", "turn_card_count",
                        "river_class_count", "turn_class_count")}, "claims": payload["claims"]}
                report["payload"] = _write_payload(directory, payload)
            except BaseException as exc:
                # The legacy authority guard merges its inventory on normal exit.
                first_error = {"message": f"{type(exc).__name__}: {exc}",
                               "traceback": traceback.format_exc()}
        report["authority_calls"] = previous._raw_guard_receipt(guard_calls)
        previous._guard_receipt(guard_calls)
    except BaseException as exc:
        error = {"message": f"{type(exc).__name__}: {exc}",
                 "traceback": traceback.format_exc()}
        if first_error is None:
            first_error = error
        else:
            report["errors"].append({"phase": "after-first-error", **error})
    finally:
        if guard_calls is not None:
            report["authority_calls"] = dict(sorted(guard_calls.items()))
        if report["source_before"] is not None:
            try:
                report["source_after"] = _snapshot()
                _need(proof._typed(report["source_before"]) == proof._typed(report["source_after"]),
                      "Source changed during the reference batch")
            except BaseException as exc:
                report["errors"].append({"phase": "source-finalization",
                                         "message": f"{type(exc).__name__}: {exc}"})
        if first_error is not None:
            report["errors"].insert(0, first_error)
        report["status"] = "error" if report["errors"] else "complete"
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        if directory is not None:
            _write_index(directory, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(args.output, execution_state={"mode": "ordinary-process", "system_required": False})
    print(json.dumps({"status": report["status"], "errors": report["errors"],
                      "progress": report["progress"], "index_sha256": report["index_sha256"]},
                     sort_keys=True))
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
