"""Authenticate the saved second-board equivalence corpus without replaying it."""
from datetime import datetime, timedelta
from fractions import Fraction
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import struct

from scripts import benchmark_flop_second_board_equivalence as evidence
from scripts.verify_flop_class_owned_fingerprint_publication import AUTHORITY_KEYS

PUBLICATION = evidence.ROOT / "benchmarks/results/flop-second-board-equivalence-v1"
SOURCE_REVISION = "8c093c9af650e53ddf1a98457d0cad69382eb5d1"
RAW_INDEX_SHA256 = "06b60eada9aa6465e63138525060b0891f3d66d00e2364dd42e047e2b060880a"
INDEX_SHA256 = "29ff51b127a393d484262d788835324ac76c44fd0f2c5b2ee76e7ee375bd8691"
INDEX_BYTES = 1423452
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_GZIP_BYTES = 16 * 1024 * 1024
MAX_RAW_BYTES = 64 * 1024 * 1024
proof = evidence.proof
_need = evidence._need
MODES = ("check-call", "bet-fold", "class-varying", "zero-reach")
NEGATIVES = ("within-class-card-variation", "near-normalized")
METRICS = ("exploitability", "ip_best_response_gain", "ip_best_response_value",
           "nash_conv", "oop_best_response_gain", "oop_best_response_value",
           "value_ip", "value_oop")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(raw):
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def _read_bounded(path, limit):
    path = Path(path)
    _need(not path.is_symlink() and path.stat().st_size <= limit, "Saved file is a symlink or exceeds bound")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    _need(len(data) <= limit, "Saved file exceeded bound while reading")
    return data


def _safe_inventory(directory):
    root = Path(directory)
    _need(not root.is_symlink() and root.is_dir(), "Publication directory is missing or symlinked")
    expected_dirs = set(MODES + NEGATIVES)
    names = set()
    for entry in root.iterdir():
        names.add(entry.name)
        _need(len(names) <= 7, "Publication contains too many entries")
    _need(names == expected_dirs | {"index.json"}, "Publication inventory differs")
    index = root / "index.json"
    _need(index.is_file() and not index.is_symlink(), "Index is missing or symlinked")
    for mode in MODES + NEGATIVES:
        folder = root / mode
        _need(folder.is_dir() and not folder.is_symlink(), "Payload directory is missing or symlinked")
        items = []
        for entry in folder.iterdir():
            items.append(entry)
            _need(len(items) <= 1, "Payload directory contains extra entries")
        _need(len(items) == 1 and items[0].name == "reference.json.gz" and
              items[0].is_file() and not items[0].is_symlink(), "Payload inventory differs")


def _source(state, *, recorded):
    _need(type(state) is dict and set(state) == {"revision", "status", "source_lf_sha256"}
          and type(state["revision"]) is str and len(state["revision"]) == 40
          and all(c in "0123456789abcdef" for c in state["revision"])
          and state["status"] == "" and type(state["source_lf_sha256"]) is dict
          and len(state["source_lf_sha256"]) == evidence.SOURCE_COUNT,
          "Source snapshot shape/status differs")
    if recorded:
        _need(state["revision"] == SOURCE_REVISION, "Recorded source checkpoint differs")
    _need(all(type(p) is str and type(h) is str and len(h) == 64 and
              all(c in "0123456789abcdef" for c in h)
              for p, h in state["source_lf_sha256"].items()), "Source LF map is malformed")


def _read_index(directory):
    raw = _read_bounded(Path(directory) / "index.json", MAX_INDEX_BYTES)
    _need(len(raw) == INDEX_BYTES and hashlib.sha256(raw).hexdigest() == RAW_INDEX_SHA256,
          "Raw saved index pin differs")
    report = _json(raw)
    unsigned = {k: v for k, v in report.items() if k != "index_sha256"}
    _need(type(report) is dict and report.get("index_sha256") == INDEX_SHA256 == proof._digest(unsigned),
          "Saved index self-digest differs")
    return raw, report


def _read_payload(directory, receipt, expected_path):
    _need(type(receipt) is dict and set(receipt) == {"path", "raw_bytes", "raw_sha256",
          "gzip_bytes", "gzip_sha256"} and receipt["path"] == expected_path,
          "Payload receipt/path differs")
    for field, upper in (("raw_bytes", MAX_RAW_BYTES), ("gzip_bytes", MAX_GZIP_BYTES)):
        value = receipt[field]
        _need(type(value) is int and 0 <= value <= upper, "Payload size receipt is invalid")
    for field in ("raw_sha256", "gzip_sha256"):
        value = receipt[field]
        _need(type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value),
              "Payload digest receipt is invalid")
    gzip_raw = _read_bounded(Path(directory) / expected_path, MAX_GZIP_BYTES)
    _need(len(gzip_raw) == receipt["gzip_bytes"] and
          hashlib.sha256(gzip_raw).hexdigest() == receipt["gzip_sha256"], "Payload gzip receipt differs")
    with gzip.GzipFile(fileobj=io.BytesIO(gzip_raw), mode="rb") as stream:
        raw = stream.read(MAX_RAW_BYTES + 1)
    _need(len(raw) == receipt["raw_bytes"] <= MAX_RAW_BYTES and
          hashlib.sha256(raw).hexdigest() == receipt["raw_sha256"], "Payload raw receipt differs")
    return gzip_raw, raw, _json(raw)


def _fraction_text(value):
    _need(type(value) is str and len(value) <= 128, "Exact metric fraction is malformed")
    try:
        fraction = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("Exact metric fraction is invalid") from exc
    _need(str(fraction) == value, "Exact metric fraction is not canonical")
    return fraction


def _metric_checks(exact, numeric, gap):
    _need(type(exact) is dict and set(exact) == set(METRICS) and
          all(type(v) is str for v in exact.values()), "Exact metric inventory differs")
    fractions = {k: _fraction_text(v) for k, v in exact.items()}
    _need(type(numeric) is dict and set(numeric) == set(METRICS) and
          all(type(v) is float and math.isfinite(v) for v in numeric.values()),
          "Numeric metric inventory differs")
    _need(type(gap) is float and math.isfinite(gap) and 0 <= gap <= 1e-10,
          "Numeric replay gap exceeds tolerance")
    _need(fractions["value_ip"] == -fractions["value_oop"] and
          fractions["oop_best_response_gain"] == fractions["oop_best_response_value"] - fractions["value_oop"] and
          fractions["ip_best_response_gain"] == fractions["ip_best_response_value"] - fractions["value_ip"] and
          fractions["nash_conv"] == fractions["oop_best_response_gain"] + fractions["ip_best_response_gain"] and
          fractions["exploitability"] == fractions["nash_conv"] / 2 and
          fractions["oop_best_response_gain"] >= 0 and fractions["ip_best_response_gain"] >= 0,
          "Exact own-hand metric identities differ")
    actual = max(abs(float(fractions[k]) - numeric[k]) for k in METRICS)
    _need(actual <= 1e-10 and actual == gap, "Numeric replay receipt is inconsistent")
    return fractions


def _probabilities(values, *, normalized=True):
    _need(type(values) is list and len(values) == 2 and
          all(type(v) is float and math.isfinite(v) and 0.0 <= v <= 1.0 for v in values),
          "Binary policy probabilities are malformed")
    total = Fraction(values[0]) + Fraction(values[1])
    if normalized:
        _need(total == 1, "Policy is not exactly normalized")
    return tuple(struct.pack(">d", v) for v in values), total


def _strategy_maps(payload, *, normalized=True):
    rows = payload.get("strategy")
    _need(type(rows) is list and len(rows) == 16912, "Physical strategy row count differs")
    result = {}
    for row in rows:
        _need(type(row) is dict and set(row) == {"actions", "board", "hand", "history", "player", "street"} and
              row["player"] in ("oop", "ip") and type(row["hand"]) is str and
              type(row["board"]) is list and len(row["board"]) in (3, 4, 5) and
              row["board"][:3] == ["7c", "8d", "9h"] and type(row["street"]) is str and
              type(row["history"]) is list and len(row["history"]) <= 20 and
              all(type(x) is str and len(x) <= 64 for x in row["history"]),
              "Physical policy row key differs")
        actions = row["actions"]
        _need(type(actions) is list and len(actions) == 2, "Physical row action count differs")
        _need(row["street"] == {3: "flop", 4: "turn", 5: "river"}[len(row["board"])],
              "Policy street/board visibility differs")
        for action in actions:
            _need(type(action) is dict and set(action) == {"amount", "history_key", "name", "probability", "raise_to"}
                  and type(action["name"]) is str and type(action["history_key"]) is str and
                  type(action["amount"]) is float and math.isfinite(action["amount"]) and
                  type(action["raise_to"]) is float and math.isfinite(action["raise_to"]),
                  "Physical action record is malformed")
        bits, _ = _probabilities([a.get("probability") for a in actions], normalized=normalized)
        key = (0 if row["player"] == "oop" else 1, row["hand"], tuple(row["history"]))
        _need(key not in result, "Duplicate physical policy key")
        result[key] = (bits, row)
    return result


def _mapped_groups(payload, turns, rivers, class_rows):
    physical = _strategy_maps(payload)
    projected = {}
    for (player, hand, history), (bits, _) in physical.items():
        key = (player, hand, evidence.proof.shared._mapped_history(history, turns, rivers))
        prior = projected.setdefault(key, bits)
        _need(prior == bits, "Physical rows are not class-constant")
    _need(len(projected) == len(class_rows) == 608 and set(projected) == set(class_rows),
          "Physical and compact information rows differ")
    _need(all(projected[k] == class_rows[k] for k in projected), "Projected policy differs from saved class policy")


def _class_rows(control):
    rows = control.get("class_policy")
    _need(type(rows) is list and len(rows) == 608 and type(control.get("class_rows")) is int
          and control["class_rows"] == 608, "Class policy row count differs")
    _need(proof._digest(rows) == control.get("class_policy_sha256"), "Class policy digest differs")
    result = {}
    for row in rows:
        _need(type(row) is list and len(row) == 4 and type(row[0]) is int and row[0] in (0, 1)
              and type(row[1]) is str and type(row[2]) is list and
              all(type(x) is str and len(x) <= 64 for x in row[2]), "Class policy key is malformed")
        bits, _ = _probabilities(row[3])
        key = (row[0], row[1], tuple(row[2]))
        _need(key not in result, "Duplicate class policy key")
        result[key] = bits
    return result


def _validate_payload(payload, control, mode, turns, rivers):
    fixed_config = {"bet_sizes": [0.5], "effective_stack": [5.0, 5.0],
                    "include_all_in": False, "max_raises": 0, "pot": 10.0, "raise_sizes": []}
    fixed_configs = {street: fixed_config for street in ("flop", "turn", "river")}
    _need(type(payload) is dict and payload.get("strategy_schema") == "postflop-strategy-v1" and
          payload.get("algorithm") == "no-training-second-board-control" and
          payload.get("solver_version") == "configured-postflop-v1" and
          proof._typed(payload.get("board")) == proof._typed(["7c", "8d", "9h"]) and
          type(payload.get("pot")) is float and payload["pot"] == 10.0 and
          proof._typed(payload.get("config")) == proof._typed(fixed_config) and
          proof._typed(payload.get("street_configs")) == proof._typed(fixed_configs) and
          proof._typed(payload.get("effective_stack")) == proof._typed([5.0, 5.0]) and
          all(type(payload.get(field)) is int and payload[field] == value for field, value in (
              ("deals", 3), ("compatible_pairs", 3), ("worlds", 5940), ("info_sets", 16912),
              ("public_states", 30812), ("public_nodes", 9512), ("chance_nodes", 248),
              ("terminal_nodes", 21052))) and payload.get("runout_mode") == "full-deck",
          "Saved physical policy header differs")
    deck = evidence.proof.physical.DECK
    board = ("7c", "8d", "9h")
    expected_all = [[turn, river] for turn in deck if turn not in board
                    for river in deck if river not in board and river != turn]
    pairs = (("AdAs", "KdKs"), ("QdQs", "AsKh"), ("QdQs", "KdKs"))
    expected_reachable = set()
    for oop, ip in pairs:
        blocked = set(board) | {oop[:2], oop[2:], ip[:2], ip[2:]}
        remain = [card for card in deck if card not in blocked]
        expected_reachable.update((turn, river) for turn in remain for river in remain if turn != river)
    _need(proof._typed(payload.get("runouts")) == proof._typed(expected_all) and
          proof._typed(payload.get("reachable_runouts")) == proof._typed(
              [list(pair) for pair in expected_all if tuple(pair) in expected_reachable]),
          "Saved full-deck or blocker-conditioned runout header differs")
    exact = control.get("exact_physical_metrics")
    numeric = control.get("numeric_metrics")
    fractions = _metric_checks(exact, numeric, control.get("maximum_numeric_gap"))
    for metric in METRICS:
        _need(type(payload.get(metric)) is float and math.isfinite(payload[metric]) and
              proof._typed(payload[metric]) == proof._typed(float(fractions[metric])),
              "Policy metric header differs from exact audited metrics")
    strategy = payload.get("strategy")
    _need(type(strategy) is list and proof._digest(payload) == control.get("physical_policy_sha256"),
          "Physical policy digest differs")
    class_rows = _class_rows(control)
    _mapped_groups(payload, turns, rivers, class_rows)
    return fractions, class_rows


def _validate_negative(neg, payload, zero_payload, turns, rivers, kind):
    _need(type(neg) is dict and neg.get("mode") == kind and neg.get("status") == "expected-rejection" and
          type(neg.get("physical_row_index")) is int and neg.get("qualification") and neg.get("rejection"),
          "Negative projection control receipt differs")
    _need(type(payload) is dict and type(payload.get("strategy")) is list and
          len(payload["strategy"]) == 16912, "Negative policy row inventory differs")
    idx = neg["physical_row_index"]
    _need(0 <= idx < 16912, "Negative row index out of range")
    _need(type(neg.get("hand")) is str and type(neg.get("history")) is list and
          type(neg.get("player")) is str and neg["player"] in ("oop", "ip"),
          "Negative row identity metadata is malformed")
    before_expected = [1.0, 0.0]
    after_expected = ([0.75, 0.25] if kind == NEGATIVES[0] else [1.0, 2 ** -54])
    base_rows = zero_payload["strategy"]
    _need(proof._typed({k: v for k, v in payload.items() if k != "strategy"}) ==
          proof._typed({k: v for k, v in zero_payload.items() if k != "strategy"}),
          "Negative control changed the zero-reach policy header")
    for i, (actual, base) in enumerate(zip(payload["strategy"], base_rows)):
        if i != idx:
            _need(proof._typed(actual) == proof._typed(base),
                  "Negative control changed more than its one admitted row")
        else:
            _need(actual.get("hand") == neg["hand"] and actual.get("history") == neg["history"] and
                  actual.get("player") == neg["player"],
                  "Negative row index does not match its recorded key")
            _need(proof._typed({k: v for k, v in actual.items() if k != "actions"}) ==
                  proof._typed({k: v for k, v in base.items() if k != "actions"}),
                  "Negative row identity changed")
            _need(type(actual.get("actions")) is list and len(actual["actions"]) == 2 and
                  type(base.get("actions")) is list and len(base["actions"]) == 2,
                  "Negative row actions malformed")
            _need(all(proof._typed({k: v for k, v in action.items() if k != "probability"}) ==
                      proof._typed({k: v for k, v in original.items() if k != "probability"})
                      for action, original in zip(actual["actions"], base["actions"])),
                  "Negative mutation changed a selected action outside probabilities")
            _need(proof._typed([a.get("probability") for a in base["actions"]]) ==
                  proof._typed(before_expected) and
                  proof._typed([a.get("probability") for a in actual["actions"]]) ==
                  proof._typed(after_expected), "Negative before/after probabilities differ")
    _strategy_maps(payload, normalized=False)  # preserve exact row identities while admitting the intended near-normalized rejection
    expected_qualification = "Intentionally invalid projection control; metric headers remain from the original zero-reach policy."
    expected_rejection = ("ValueError: Within-class physical-card probabilities differ bitwise"
                          if kind == NEGATIVES[0] else
                          "ValueError: Exact audit requires binary64 probabilities summing exactly to one")
    _need(neg.get("qualification") == expected_qualification and neg.get("rejection") == expected_rejection,
          "Negative-control qualification/rejection text differs")
    _need(proof._typed(neg.get("before_probabilities")) == proof._typed(before_expected) and
          proof._typed(neg.get("after_probabilities")) == proof._typed(after_expected),
          "Negative control probability mutation differs")
    if kind == NEGATIVES[0]:
        physical = _strategy_maps(payload, normalized=False)
        group_counts = {}
        for (player, hand, history), (bits, _) in physical.items():
            key = (player, hand, evidence.proof.shared._mapped_history(history, turns, rivers))
            prior = group_counts.setdefault(key, bits)
            if prior != bits:
                group_counts[key] = None
        _need(sum(value is None for value in group_counts.values()) == 1,
              "Within-class negative did not create exactly one invalid class")
    else:
        actions = payload["strategy"][idx]["actions"]
        _, total = _probabilities([a["probability"] for a in actions], normalized=False)
        _need(total != 1, "Near-normalized negative unexpectedly sums exactly to one")


def _validate(report, payloads, current, spec):
    _need(type(report) is dict and type(report.get("schema_version")) is int and
          report["schema_version"] == 1 and report.get("status") == "no-training-equivalence-verified" and
          report.get("errors") == [] and type(report.get("training_calls")) is int and report["training_calls"] == 0,
          "Saved batch status/error/training receipt differs")
    _need(report.get("protocol_id") == spec["protocol_id"] and
          report.get("protocol_sha256") == evidence.SPEC_SHA256 and
          proof._typed(report.get("admission")) == proof._typed(evidence._preflight(spec)),
          "Protocol/admission differs")
    unsigned = {k: v for k, v in report.items() if k != "index_sha256"}
    _need(report.get("index_sha256") == INDEX_SHA256 == proof._digest(unsigned), "Index self-digest differs")
    before, after = report.get("source_before"), report.get("source_after")
    _source(before, recorded=True); _source(after, recorded=True); _source(current, recorded=False)
    _need(proof._typed(before) == proof._typed(after) and
          proof._typed(current["source_lf_sha256"]) == proof._typed(before["source_lf_sha256"]),
          "Recorded/current source maps differ")
    _need(type(report.get("runtime")) is dict and report["runtime"].get("implementation") == "CPython" and
          type(report["runtime"].get("python")) is str and report["runtime"]["python"].startswith("3.12.14 ") and
          type(report["runtime"].get("platform")) is str and report["runtime"]["platform"].startswith("Windows-"),
          "Runtime metadata differs")
    _need(proof._typed(report.get("execution_state")) == proof._typed({
        "mode": "ordinary-process", "system_required": False}), "Execution state differs")
    try:
        start = datetime.fromisoformat(report["created_at_utc"])
        finish = datetime.fromisoformat(report["finished_at_utc"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Index UTC interval malformed") from exc
    _need(start.utcoffset() == finish.utcoffset() == timedelta(0) and finish >= start,
          "Index UTC interval invalid")
    _need(proof._typed(report.get("boundaries")) == proof._typed({
        "full_model_proofs": 10, "exact_metric_calls": 8, "numeric_replays": 4,
        "projection_attempts": 6, "expected_row_tables": 26, "row_action_slots": 879424,
        "exact_world_node_terms": 2419560, "numeric_world_node_terms": 2352240}),
        "Recorded work counts differ")
    _need(proof._typed(report.get("census")) == proof._typed({
        "compact_action_slots": 1216, "compact_chance_nodes": 68, "compact_decisions": 400,
        "compact_policy_rows": 608, "compact_public_states": 1270, "compact_terminals": 802,
        "compact_tree_sha256": "5b8b6d504a35e0023c9150476ba9bb91d10615eae9ec6bb0305071745ab98152",
        "compact_world_path_visits": 5610, "compact_worlds": 170,
        "maximum_compact_world_path": 33, "maximum_physical_world_path": 33,
        "partition_proof": {"board": ["7c", "8d", "9h"], "class_worlds": 170,
            "compatible_pairs": 3, "joint_mass": "1/1", "ordered_runouts": 2328,
            "pair_marginals": [{"ip_hand": "KdKs", "mass": "8/13", "oop_hand": "AdAs"},
                {"ip_hand": "AsKh", "mass": "1/13", "oop_hand": "QdQs"},
                {"ip_hand": "KdKs", "mass": "4/13", "oop_hand": "QdQs"}],
            "physical_worlds": 5940, "river_signatures": 17, "river_transports_checked": 2328,
            "turn_cards": 49, "turn_classes": 13},
        "physical_action_slots": 33824, "physical_branch_subtrees_compared": 11787,
        "physical_nodes_checked": 30812, "physical_policy_rows": 16912,
        "physical_world_path_visits": 196020, "river_signatures": 17, "turn_classes": 13}),
        "Recorded model census differs")
    preparation = report.get("preparation")
    _need(type(preparation) is dict and set(preparation) == {"candidate_dimensions", "phase",
          "physical_builds_attempted", "physical_builds_completed", "preparation_rank_calls",
          "preparation_ranker_attempts", "prerequisite"} and
          proof._typed(preparation["candidate_dimensions"]) == proof._typed({
              "class_worlds": 170, "physical_world_count": 5940,
              "river_class_count": 17, "turn_class_count": 13}) and
          preparation.get("phase") == "complete" and
          all(type(preparation.get(field)) is int and preparation[field] == value for field, value in (
              ("physical_builds_attempted", 1), ("physical_builds_completed", 1),
              ("preparation_rank_calls", 4134), ("preparation_ranker_attempts", 4134))),
          "Preparation census/count types differ")
    # Authenticate the predecessor's saved receipt, never invoke its model/replay verifier.
    expected_prereq = {"status": "saved-second-board-reference-authenticated",
        "index_raw_sha256": evidence.proof.prerequisite.RAW_INDEX_SHA256,
        "index_sha256": evidence.proof.prerequisite.INDEX_SHA256,
        "source_revision": evidence.proof.prerequisite.SOURCE_REVISION,
        "recorded_physical_builds": 1, "recorded_preparation_rank_calls": 4134,
        "recorded_recheck_rank_calls": 4134, "physical_builds": 0, "ranking_calls": 0,
        "training_calls": 0, "best_response_calls": 0, "full_equivalence_proved": False,
        "worlds_sha256": evidence.proof.prerequisite.WORLDS_SHA256,
        "tree_sha256": evidence.proof.prerequisite.TREE_SHA256}
    _need(proof._typed(report["preparation"].get("prerequisite")) == proof._typed(expected_prereq),
          "Saved prerequisite receipt differs")
    auth_keys = AUTHORITY_KEYS
    authorities = report.get("authority_calls")
    _need(type(authorities) is dict and frozenset(authorities) == auth_keys and
          all(type(v) is int and v == 0 for v in authorities.values()), "41 authority counters differ")
    _need(type(report.get("partition")) is dict and report["partition"].get("candidate_only") is True and
          report["partition"].get("physical_provenance") is False and
          report["partition"].get("board") == ["7c", "8d", "9h"] and
          len(report["partition"].get("class_worlds", [])) == 170,
          "Candidate partition scope/dimensions differ")
    turns, rivers = evidence.proof.shared._maps(report["partition"])
    _need(type(report.get("compact_worlds")) is list and len(report["compact_worlds"]) == 170,
          "Compact-world inventory differs")
    for world, row in zip(report["partition"]["class_worlds"], report["compact_worlds"]):
        mass = world.get("mass")
        _need(type(mass) is list and len(mass) == 2 and all(type(x) is int for x in mass),
              "Class world mass malformed")
        _need(proof._typed(row) == proof._typed([world["oop_hand"], world["ip_hand"],
              f"{mass[0]}/{mass[1]}", world["sign"], ["7c", "8d", "9h",
              f"T{world['turn_class_id']:02d}", f"R{world['river_class_id']:02d}"]]),
              "Compact-world linkage differs")
    controls = report.get("controls")
    _need(type(controls) is list and [r.get("mode") for r in controls] == list(MODES),
          "Positive control inventory/order differs")
    loaded = {}
    for control in controls:
        mode = control["mode"]
        _need(control.get("status") == "complete" and control.get("phase") == "complete" and
              control.get("final_model_validation") == "passed" and
              type(control.get("physical_rows")) is int and control["physical_rows"] == 16912,
              "Positive control completion/rows differ")
        receipt = control.get("payload")
        gz, raw, payload = payloads[receipt["path"]]
        _need(control.get("physical_policy_sha256") == proof._digest(payload), "Physical policy digest differs")
        exact_compact = control.get("exact_compact_metrics")
        exact_physical = control.get("exact_physical_metrics")
        _need(proof._typed(exact_compact) == proof._typed(exact_physical), "Compact/physical exact metrics differ")
        _metric_checks(exact_compact, control.get("numeric_metrics"), control.get("maximum_numeric_gap"))
        _validate_payload(payload, control, mode, turns, rivers)
        loaded[mode] = payload
    zero = loaded["zero-reach"]
    negatives = report.get("negative_controls")
    _need(type(negatives) is list and [r.get("mode") for r in negatives] == list(NEGATIVES),
          "Negative control inventory/order differs")
    for neg in negatives:
        receipt = neg.get("payload")
        _, _, payload = payloads[receipt["path"]]
        _validate_negative(neg, payload, zero, turns, rivers, neg["mode"])
    return loaded


def _load_payloads(directory, report):
    receipts = []
    for control in report["controls"]:
        receipts.append((control["payload"], control["payload"]["path"]))
    for neg in report["negative_controls"]:
        receipts.append((neg["payload"], neg["payload"]["path"]))
    expected = [f"{mode}/reference.json.gz" for mode in MODES + NEGATIVES]
    _need([path for _, path in receipts] == expected, "Payload receipt order/path differs")
    result = {}
    for receipt, path in receipts:
        result[path] = _read_payload(directory, receipt, path)
    return result


def verify(directory=PUBLICATION):
    before = evidence._snapshot()
    _safe_inventory(directory)
    index_raw, report = _read_index(directory)
    _, spec = evidence._protocol()
    payloads = _load_payloads(directory, report)
    _validate(report, payloads, before, spec)
    # Reauthenticate all seven files after semantic checks, then take final source snapshot.
    _need(_read_bounded(Path(directory) / "index.json", MAX_INDEX_BYTES) == index_raw,
          "Saved index changed during authentication")
    for control in report["controls"]:
        receipt = control["payload"]
        raw = _read_bounded(Path(directory) / receipt["path"], MAX_GZIP_BYTES)
        _need(len(raw) == receipt["gzip_bytes"] and hashlib.sha256(raw).hexdigest() == receipt["gzip_sha256"],
              "Saved positive payload changed during authentication")
    for neg in report["negative_controls"]:
        receipt = neg["payload"]
        raw = _read_bounded(Path(directory) / receipt["path"], MAX_GZIP_BYTES)
        _need(len(raw) == receipt["gzip_bytes"] and hashlib.sha256(raw).hexdigest() == receipt["gzip_sha256"],
              "Saved negative payload changed during authentication")
    _safe_inventory(directory)
    after = evidence._snapshot()
    _source(after, recorded=False)
    _need(before["status"] == after["status"] == "" and
          proof._typed(before["source_lf_sha256"]) == proof._typed(after["source_lf_sha256"]),
          "Current source map/status changed during authentication")
    return {"status": "saved-second-board-equivalence-authenticated",
            "index_raw_sha256": RAW_INDEX_SHA256, "index_sha256": INDEX_SHA256,
            "source_revision": SOURCE_REVISION, "physical_builds": 0, "ranking_calls": 0,
            "model_projection_calls": 0, "exact_response_calls": 0,
            "numeric_replay_calls": 0, "training_calls": 0,
            "recorded_physical_builds": 1, "recorded_preparation_rank_calls": 4134,
            "recorded_full_model_proofs": 10, "recorded_exact_metric_calls": 8,
            "recorded_projection_attempts": 6, "recorded_numeric_replays": 4,
            "saved_policy_rows_authenticated": 101472,
            "quality_claim": False}


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=PUBLICATION)
    args = parser.parse_args(argv)
    print(json.dumps(verify(args.directory), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
