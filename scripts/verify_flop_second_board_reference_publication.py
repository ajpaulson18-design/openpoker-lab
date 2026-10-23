"""Authenticate saved second-board reference bytes without preparing a game."""
from datetime import datetime, timedelta
import gzip
import hashlib
import json
from pathlib import Path

from scripts import benchmark_flop_second_board_reference as evidence


PUBLICATION = evidence.ROOT / "benchmarks/results/flop-second-board-reference-v1"
SOURCE_REVISION = "a373c6e874b962ebf3d673ee4a95d8f301ae7ca5"
RAW_INDEX_SHA256 = "46236f56d92c0b546c52b00339f84d202b51b5913031c0fdafedb4b43eb3d01c"
INDEX_SHA256 = "17be8d509916853b7e24ec2cf73f86567b5b8029083432fd04a2bed0e096d583"
RAW_PAYLOAD_SHA256 = "4435d50308efbbe21203f166e6c4f2ccc185bae9dc54578eef56169b0e18b3fe"
GZIP_SHA256 = "6e9690e649815aa315ef1fff6e8cf1aca3ccc40a54e178a8fbf7a9acea874e9f"
WORLDS_SHA256 = "4ea9c186e4ba524da66b3363ad2a0d8a6851081ca41275a92d2c576a038879ab"
TREE_SHA256 = "1b327471df5591e48d50a1db305e0ea32ad3b45c2ff0354df2ddbe4025684173"
INDEX_BYTES, PAYLOAD_BYTES, GZIP_BYTES = 19914, 7978451, 373923
proof = evidence.proof
_need = evidence._need


def _json(raw):
    return json.loads(raw, object_pairs_hook=evidence.previous._pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def _read_exact(path, size, digest):
    path = Path(path)
    _need(path.stat().st_size == size, "Saved file size differs")
    with path.open("rb") as stream:
        raw = stream.read(size + 1)
    _need(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest,
          "Saved file raw hash differs")
    return raw


def _read(directory):
    directory = Path(directory)
    index_raw = _read_exact(directory / "index.json", INDEX_BYTES, RAW_INDEX_SHA256)
    gzip_raw = _read_exact(directory / "reference.json.gz", GZIP_BYTES, GZIP_SHA256)
    import io
    with gzip.GzipFile(fileobj=io.BytesIO(gzip_raw), mode="rb") as stream:
        payload_raw = stream.read(PAYLOAD_BYTES + 1)
    _need(len(payload_raw) == PAYLOAD_BYTES and
          hashlib.sha256(payload_raw).hexdigest() == RAW_PAYLOAD_SHA256,
          "Saved decompressed payload size/hash differs")
    return index_raw, gzip_raw, _json(index_raw), _json(payload_raw)


def _source(state, *, recorded):
    _need(type(state) is dict and set(state) == {"revision", "status", "source_lf_sha256"}
          and type(state["revision"]) is str and len(state["revision"]) == 40
          and all(ch in "0123456789abcdef" for ch in state["revision"])
          and state["status"] == "" and type(state["source_lf_sha256"]) is dict
          and len(state["source_lf_sha256"]) == evidence.SOURCE_COUNT,
          "Source inventory/status/revision differs")
    if recorded:
        _need(state["revision"] == SOURCE_REVISION, "Recorded source checkpoint differs")
    _need(all(type(path) is str and type(digest) is str and len(digest) == 64
              and all(ch in "0123456789abcdef" for ch in digest)
              for path, digest in state["source_lf_sha256"].items()),
          "Source LF inventory is malformed")


def _flat_structure(view):
    """Reconstruct the saved typed structure as JSON data, never numeric nodes."""
    _need(type(view) is list and len(view) == 30812 and
          all(type(row) is dict and type(row.get("id")) is int and row["id"] == index
              for index, row in enumerate(view)), "Saved rooted-view inventory differs")
    root = view[0]
    _need(root.get("kind") == "decision" and type(root.get("player")) is int
          and root["player"] == 0 and root.get("street") == "flop"
          and root.get("history") == [] and root.get("board") == ["7c", "8d", "9h"],
          "Saved rooted view is not the complete flop-start game")
    seen, counts = set(), {"decision": 0, "chance": 0, "terminal": 0}

    def visit(index, depth):
        _need(type(index) is int and 0 <= index < len(view) and index not in seen
              and depth <= 128, "Saved tree child/cycle/depth differs")
        seen.add(index)
        row = view[index]
        kind = row.get("kind")
        _need(kind in counts, "Saved view has an unknown node kind")
        counts[kind] += 1
        if kind == "terminal":
            return ["terminal", row["history"], row["terminal_kind"], row["winner"],
                    proof._typed(tuple(row["contributions"]))]
        if kind == "decision":
            _need(type(row["children"]) is list and len(row["children"]) == len(row["actions"]) == 2,
                  "Saved decision choices differ")
            return ["decision", row["history"], row["player"], row["street"], row["board"],
                    proof._typed(tuple(row["actions"])),
                    [visit(child, depth + 1) for child in row["children"]]]
        branches = row["branches"]
        _need(type(branches) is list and 0 < len(branches) <= 49 and
              len({branch[0] for branch in branches}) == len(branches),
              "Saved chance branch inventory differs")
        return ["chance", row["history"], row["card_index"], row["street"],
                [[card, visit(child, depth + 1)] for card, child in sorted(branches)]]

    structure = visit(0, 1)
    _need(len(seen) == len(view) and counts == {
        "decision": 9512, "chance": 248, "terminal": 21052},
        "Saved tree does not cover every retained numeric node")
    return structure


def _validate(report, payload, current, spec):
    _need(type(report) is dict and type(report.get("schema_version")) is int
          and report["schema_version"] == 1 and report.get("protocol_id") == spec["protocol_id"]
          and report.get("status") == "complete" and report.get("errors") == [],
          "Saved reference batch did not complete cleanly")
    unsigned = {key: value for key, value in report.items() if key != "index_sha256"}
    _need(report.get("index_sha256") == INDEX_SHA256 == proof._digest(unsigned),
          "Saved index self-digest differs")
    _need(report.get("protocol_sha256") == evidence.SPEC_SHA256 and
          proof._typed(report.get("admission")) == proof._typed(evidence._preflight(spec)),
          "Saved protocol/admission differs")
    before, after = report.get("source_before"), report.get("source_after")
    _source(before, recorded=True)
    _source(after, recorded=True)
    _source(current, recorded=False)
    _need(proof._typed(before) == proof._typed(after) and
          proof._typed(current["source_lf_sha256"]) == proof._typed(before["source_lf_sha256"]),
          "Saved or current named source identities differ")
    expected_progress = {"phase": "complete", "physical_builds_attempted": 1,
                         "physical_builds_completed": 1, "candidate_builds_attempted": 1,
                         "candidate_builds_completed": 1, "physical_world_rows": 5940,
                         "world_rows_validated": 5940, "candidate_world_rows": 5940,
                         "tree_nodes_validated": 30812, "preparation_rank_calls": 4134,
                         "preparation_ranker_attempts": 4134, "recheck_rank_calls": 4134,
                         "recheck_ranker_attempts": 4134}
    _need(proof._typed(report.get("progress")) == proof._typed(expected_progress),
          "Saved attempted/completed rank/build counts differ")
    expected_receipt = {
        "path": "reference.json.gz", "raw_bytes": PAYLOAD_BYTES,
        "raw_sha256": RAW_PAYLOAD_SHA256, "gzip_bytes": GZIP_BYTES,
        "gzip_sha256": GZIP_SHA256}
    _need(proof._typed(report.get("payload")) == proof._typed(expected_receipt),
          "Saved payload linkage differs")
    _need(proof._typed(report.get("execution_state")) == proof._typed({
        "mode": "ordinary-process", "system_required": False}), "Saved execution state differs")
    runtime = report.get("runtime")
    _need(type(runtime) is dict and runtime.get("implementation") == "CPython" and
          type(runtime.get("python")) is str and runtime["python"].startswith("3.12.14 ")
          and type(runtime.get("platform")) is str and runtime["platform"].startswith("Windows-"),
          "Recorded interpreter/platform differs")
    try:
        start, finish = (datetime.fromisoformat(report[key])
                         for key in ("created_at_utc", "finished_at_utc"))
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("Saved UTC interval is malformed") from exc
    _need(start.utcoffset() == finish.utcoffset() == timedelta(0) and finish >= start,
          "Saved UTC interval differs")
    prereq = report.get("prerequisite")
    expected_prereq = {"status": "saved-owned-fingerprint-census-authenticated",
                       "raw_sha256": evidence.prerequisite.RAW_REPORT_SHA256,
                       "report_sha256": evidence.prerequisite.REPORT_SHA256,
                       "source_revision": evidence.prerequisite.SOURCE_REVISION,
                       "recorded_fingerprint_calls": 6, "recorded_full_validations": 2,
                       "fingerprint_calls": 0, "full_validations": 0, "training_calls": 0}
    _need(proof._typed(prereq) == proof._typed(expected_prereq),
          "Saved prerequisite linkage differs")
    authorities = report.get("authority_calls")
    _need(type(authorities) is dict and frozenset(authorities) == evidence.prerequisite.AUTHORITY_KEYS
          and all(type(value) is int and value == 0 for value in authorities.values()),
          "Saved complete 41-entry authority inventory differs")
    evidence._completion(payload, report["progress"])
    _need(proof._typed(payload.get("admission")) == proof._typed(spec["fixture"]) and
          proof._typed(payload.get("plan")) == proof._typed(evidence.reference._plan_record(
              evidence.planning.plan_second_board())), "Saved plan/admission differs")
    physical, candidate = payload["physical"], payload["candidate_partition"]
    _need(physical.get("worlds_sha256") == WORLDS_SHA256 == proof._digest(physical["worlds_view"])
          and physical.get("tree_sha256") == TREE_SHA256 ==
          proof._digest(_flat_structure(physical["tree_view"])), "Saved world/tree identity differs")
    _need(type(candidate.get("turn_class_count")) is int and candidate["turn_class_count"] == 13
          and type(candidate.get("river_class_count")) is int and candidate["river_class_count"] == 17
          and type(candidate.get("class_worlds")) is list and len(candidate["class_worlds"]) == 170,
          "Saved measured candidate dimensions differ")
    summary = {"physical": {key: value for key, value in physical.items()
                            if key not in ("worlds_view", "tree_view")},
               "candidate": {key: candidate[key] for key in (
                   "candidate_only", "physical_provenance", "input_completeness",
                   "physical_world_count", "compatible_pair_count", "turn_card_count",
                   "river_class_count", "turn_class_count")}, "claims": payload["claims"]}
    _need(proof._typed(report.get("summary")) == proof._typed(summary),
          "Saved index and full payload summaries differ")


def verify(directory=PUBLICATION):
    before = evidence._snapshot()
    index_raw, gzip_raw, report, payload = _read(directory)
    _, spec = evidence._protocol()
    _validate(report, payload, before, spec)
    _need(_read_exact(Path(directory) / "index.json", INDEX_BYTES, RAW_INDEX_SHA256) == index_raw
          and _read_exact(Path(directory) / "reference.json.gz", GZIP_BYTES, GZIP_SHA256) == gzip_raw,
          "Saved publication changed during authentication")
    after = evidence._snapshot()
    _need(proof._typed(before) == proof._typed(after), "Current source changed during authentication")
    return {"status": "saved-second-board-reference-authenticated",
            "index_raw_sha256": RAW_INDEX_SHA256, "index_sha256": INDEX_SHA256,
            "source_revision": SOURCE_REVISION, "worlds_sha256": WORLDS_SHA256,
            "tree_sha256": TREE_SHA256, "recorded_physical_builds": 1,
            "recorded_preparation_rank_calls": 4134, "recorded_recheck_rank_calls": 4134,
            "physical_builds": 0, "ranking_calls": 0, "training_calls": 0,
            "best_response_calls": 0, "full_equivalence_proved": False}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=PUBLICATION)
    args = parser.parse_args(argv)
    print(json.dumps(verify(args.directory), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
