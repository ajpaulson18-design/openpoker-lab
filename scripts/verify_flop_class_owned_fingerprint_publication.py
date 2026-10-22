"""Authenticate the immutable saved D030 fingerprint census; no model replay."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from scripts import benchmark_flop_class_owned_fingerprint as evidence

ROOT = Path(__file__).resolve().parents[1]
PUBLICATION = ROOT / "benchmarks/results/flop-class-owned-fingerprint-v1.json"
MAX_REPORT_BYTES = 2 * 1024 * 1024
RAW_REPORT_SHA256 = "8ac7091a289a5e131348bd86fed58e769d1e1413b797a408435b1b8c2a4d56a5"
REPORT_SHA256 = "48cb08101cd1d9a1c9141572609e89cf2518a06afb7fb96b1bf0591467b76afb"
SOURCE_REVISION = "1b61d75f89c8960bf6aeca464611f899a2cbc841"

STABLE_DIGEST = "8eef279da8a2dd8998e86d805079cfe900cab2a8b959a681a1fff59c45053d73"
ACTION_DIGEST = "30ce8e4d7cfc0898def46bca7a9049ad2d1ab0102529b19475b6497d5309c974"
ALIAS_DIGEST = "c4eecf825b4adbb3197016619a2622a7933a076dde127f45ee053ccdb2253c26"
SAMPLE_IDS = ("stable", "stable-repeat", "root-action-amount",
              "root-action-restored", "node-index-alias", "node-index-restored")

AUTHORITY_KEYS = frozenset((
    "RiverConfig.__post_init__", "RiverConfig.from_dict",
    "pokerlab.alternating_public_cfr._aggregate_prefixes",
    "pokerlab.alternating_public_cfr._cfrplus_target_deltas",
    "pokerlab.alternating_public_cfr._train_alternating",
    "pokerlab.alternating_public_cfr._weighted_average_sweep",
    "pokerlab.alternating_public_cfr.train_public_alternating_dcfr",
    "pokerlab.alternating_public_cfr.train_public_lcfr",
    "pokerlab.cards.cards", "pokerlab.cards.expand_range", "pokerlab.cards.rank_hand",
    "pokerlab.cfr.best_response", "pokerlab.cfr.evaluate", "pokerlab.cfr.train",
    "pokerlab.cfr_plus.train", "pokerlab.planned_cfr.train",
    "pokerlab.postflop_solver._build_postflop_tree",
    "pokerlab.postflop_solver._build_public_tree", "pokerlab.postflop_solver._build_tree",
    "pokerlab.postflop_solver._enumerate_worlds", "pokerlab.postflop_solver._terminal_value",
    "pokerlab.postflop_solver.best_response", "pokerlab.postflop_solver.cards",
    "pokerlab.postflop_solver.evaluate", "pokerlab.postflop_solver.evaluate_profile",
    "pokerlab.postflop_solver.expand_range", "pokerlab.postflop_solver.rank_hand",
    "pokerlab.postflop_solver.solve_postflop", "pokerlab.postflop_solver.train",
    "pokerlab.postflop_solver.train_planned", "pokerlab.postflop_solver.train_plus",
    "pokerlab.postflop_solver.train_public_batched",
    "pokerlab.preflop_delayed_cfrplus.train_delayed_public_cfrplus",
    "pokerlab.public_cfr._aggregate_prefixes", "pokerlab.public_cfr._cfrplus_target_deltas",
    "pokerlab.public_cfr.train_public_batched", "pokerlab.public_diagnostics.evaluate_profile",
    "pokerlab.river_tree._build_tree", "pokerlab.river_tree._terminal_value",
    "scripts.preflop_validation.cards", "scripts.preflop_validation.expand_range",
))


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _need(key not in result, "Duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON constant: {value}")


def _finite_float(value):
    number = float(value)
    _need(math.isfinite(number), "Non-finite JSON number")
    return number


def _read(path):
    path = Path(path).absolute()
    _need(not path.is_symlink() and all(not parent.is_symlink() for parent in path.parents),
          "Saved census path cannot traverse symlinks")
    size = path.stat().st_size
    _need(size <= MAX_REPORT_BYTES, "Saved census exceeds its byte bound")
    with path.open("rb") as stream:
        raw = stream.read(MAX_REPORT_BYTES + 1)
    _need(len(raw) <= MAX_REPORT_BYTES and len(raw) == size,
          "Saved census changed size while being read")
    _need(hashlib.sha256(raw).hexdigest() == RAW_REPORT_SHA256,
          "Saved census bytes differ from immutable raw pin")
    report = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_reject_constant,
                        parse_float=_finite_float)
    _need(type(report) is dict, "Saved census must be a JSON object")
    unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
    computed = evidence.proof._digest(unsigned)
    _need(report.get("report_sha256") == REPORT_SHA256 == computed,
          "Saved census self-digest differs")
    return raw, report


def _utc(value):
    _need(type(value) is str, "Expected an aware UTC timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _need(parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed),
          "Timestamp must be UTC")
    return parsed


def _stable_census(limits):
    return {
        "objects": 318_280, "edges": 1_608_777, "max_depth": 22, "max_stack": 23,
        "stream_bytes": 50_383_627, "limits": limits,
        "token_counts": {"A": 297, "B": 38_747, "D": 62_627, "E": 318_280,
            "F64": 124_764, "I": 97_524, "L": 1_608_777, "M": 44_171,
            "N": 33_099, "Q": 12_019, "R": 85_558, "S": 910_806,
            "T": 189_654, "U": 9_512},
    }


def _alias_census(limits):
    row = _stable_census(limits)
    row.update(objects=318_281, edges=1_608_783, stream_bytes=50_383_839)
    row["token_counts"] = dict(row["token_counts"])
    for key, delta in {"D": 1, "E": 1, "I": 1, "L": 6, "R": 3, "S": 1}.items():
        row["token_counts"][key] += delta
    return row


def _source_ok(source, *, recorded):
    _need(type(source) is dict and source.get("status") == "" and
          type(source.get("revision")) is str and len(source["revision"]) == 40 and
          all(char in "0123456789abcdef" for char in source["revision"]) and
          type(source.get("source_lf_sha256")) is dict and
          len(source["source_lf_sha256"]) == 39 and
          all(type(name) is str and type(value) is str and len(value) == 64
              and all(char in "0123456789abcdef" for char in value)
              for name, value in source["source_lf_sha256"].items()),
          "Source snapshot is malformed or dirty")
    if recorded:
        _need(source["revision"] == SOURCE_REVISION,
              "Recorded census revision differs from frozen source checkpoint")


def _validate(report, spec, admission, current_source):
    p = evidence.proof
    _need(type(report.get("schema_version")) is int and report["schema_version"] == 1 and
          report.get("protocol_id") == "fixed-flop-owned-fingerprint-v1" and
          report.get("status") == "complete" and report.get("errors") == [],
          "Saved census status or schema differs")
    _need(report.get("protocol_sha256") == evidence.SPEC_SHA256 and
          p._typed(report.get("admission")) == p._typed(admission),
          "Protocol identity or admission differs")
    _need(type(report.get("fingerprint_calls")) is int and report["fingerprint_calls"] == 6 and
          type(report.get("full_validations")) is int and report["full_validations"] == 2 and
          type(report.get("training_calls")) is int and report["training_calls"] == 0,
          "Fingerprint, validation, or training call count differs")
    start, finish = _utc(report.get("created_at_utc")), _utc(report.get("finished_at_utc"))
    _need(start <= finish, "Saved census timestamps are reversed")

    runtime = report.get("runtime")
    _need(type(runtime) is dict and runtime == {
        "python": "3.12.14 (main, Aug 25 2026, 14:01:42) [MSC v.1944 64 bit (AMD64)]",
        "implementation": "CPython", "platform": "Windows-10-10.0.19045-SP0"},
        "Runtime identity differs from the captured experiment")
    _need(p._typed(report.get("execution_state")) == p._typed({
        "mode": "windows-benchmark-thread", "system_required": True,
        "requested_flags": 0x80000001, "previous_flags": 0x80000000}),
        "Windows execution-state receipt differs")

    before, after = report.get("source_before"), report.get("source_after")
    _source_ok(before, recorded=True)
    _source_ok(after, recorded=True)
    _need(p._typed(before) == p._typed(after), "Recorded source snapshots differ")
    _need(p._typed(before["source_lf_sha256"]) == p._typed(current_source["source_lf_sha256"]),
          "Current 39-source LF map differs from the experiment")

    prerequisite = report.get("prerequisite")
    _need(p._typed(prerequisite) == p._typed({
        "publication_pr": 209,
        "index_raw_sha256": spec["prerequisite"]["diagnostic_index_raw_sha256"],
        "index_sha256": spec["prerequisite"]["diagnostic_index_sha256"],
        "status": "saved-baseline-diagnostic-authenticated",
        "recorded_training_calls": 2, "verification_training_calls": 0,
        "phase_events": 13}), "Saved D029 prerequisite receipt differs")

    physical = report.get("physical_model_census")
    compact = {"compact_action_slots": 932, "compact_chance_nodes": 58,
        "compact_decisions": 316, "compact_policy_rows": 466,
        "compact_public_states": 1001, "compact_terminals": 627,
        "compact_tree_sha256": "55d75a6563ffb595c044d92d73c4f452880717a01f394dfd6c176e106b531dec",
        "compact_worlds": 126, "physical_action_slots": 33_824,
        "physical_branch_subtrees_compared": 11_787, "physical_nodes_checked": 30_812,
        "physical_policy_rows": 16_912, "river_signatures": 19, "turn_classes": 11}
    expected_physical = {"baseline_physical_worlds": 5940, "baseline_public_states": 30_812,
        "compact_census": compact, "maximum_live_physical_oracles_reference": 2,
        "physical_oracle_builds": 2, "physical_world_rows_reference": 11_880,
        "weighted_physical_worlds": 5940, "weighted_public_states": 30_812}
    _need(p._typed(physical) == p._typed(expected_physical),
          "Physical/compact model census differs")

    rows = report.get("fingerprints")
    _need(type(rows) is list and len(rows) == 6 and
          all(type(row) is dict for row in rows) and
          tuple(row.get("sample_id") for row in rows) == SAMPLE_IDS and
          all(row.get("status") == "complete" for row in rows),
          "Fingerprint sample inventory or status differs")
    limits = spec["limits"]
    stable = _stable_census(limits)
    alias = _alias_census(limits)
    expected_digests = (STABLE_DIGEST, STABLE_DIGEST, ACTION_DIGEST,
                        STABLE_DIGEST, ALIAS_DIGEST, STABLE_DIGEST)
    for index, row in enumerate(rows):
        _need(type(row.get("sha256")) is str and row["sha256"] == expected_digests[index],
              "Fingerprint digest differs from the recorded census")
        expected_census = alias if index == 4 else stable
        _need(p._typed(row.get("census")) == p._typed(expected_census),
              "Fingerprint census differs from its exact sample anchor")
        _need("partial_census" not in row and "error" not in row,
              "Completed fingerprint row contains a failure receipt")

    _need(type(report.get("authority_calls")) is dict and
          frozenset(report["authority_calls"]) == AUTHORITY_KEYS and
          all(type(value) is int and value == 0 for value in report["authority_calls"].values()),
          "Authority inventory is not the complete exact 41-entry all-zero set")


def verify(path=PUBLICATION):
    """Authenticate saved bytes and current source identity; performs no replay."""
    current_before = evidence._snapshot()
    _source_ok(current_before, recorded=False)
    raw, report = _read(path)
    _need(Path(path).stat().st_size == len(raw), "Saved report size changed during verification")
    _, spec = evidence._protocol()
    admission = evidence._preflight(spec)
    _validate(report, spec, admission, current_before)
    raw_after, report_after = _read(path)
    _need(raw_after == raw and evidence.proof._typed(report_after) ==
          evidence.proof._typed(report), "Saved report changed during verification")
    current_after = evidence._snapshot()
    _source_ok(current_after, recorded=False)
    _need(evidence.proof._typed(current_before) == evidence.proof._typed(current_after) and
          evidence.proof._typed(current_after["source_lf_sha256"]) ==
          evidence.proof._typed(report["source_before"]["source_lf_sha256"]),
          "Current source snapshot changed or differs from the recorded census")
    return {"status": "saved-owned-fingerprint-census-authenticated",
            "raw_sha256": RAW_REPORT_SHA256, "report_sha256": REPORT_SHA256,
            "source_revision": SOURCE_REVISION, "recorded_fingerprint_calls": 6,
            "recorded_full_validations": 2, "fingerprint_calls": 0,
            "full_validations": 0, "training_calls": 0}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=PUBLICATION)
    args = parser.parse_args(argv)
    print(json.dumps(verify(args.path), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
