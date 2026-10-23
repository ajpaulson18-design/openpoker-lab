"""Authenticate the saved stopped T140 CFR+ attempt without rerunning it."""
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import struct

from scripts import benchmark_flop_second_board_cfrplus as benchmark
from scripts import flop_second_board_equivalence as proof
from scripts.verify_flop_class_owned_fingerprint_publication import AUTHORITY_KEYS


PUBLICATION = benchmark.ROOT / "benchmarks/results/flop-second-board-cfrplus-pilot-v1"
SOURCE_REVISION = "0106c521fffffdb407f193b4295da6ff2e35759d"
RAW_INDEX_BYTES = 36_372
RAW_INDEX_SHA256 = "6923789f8847b79326c37906875ae3f658d15762e52c8d6fb37ae89f46ba9afd"
INDEX_SHA256 = "237d9f30d80b13d9e89fee71121ca750438dcd8e34c330a0276dfdbd4b2a5fba"
PROTOCOL_SHA256 = "75c0e30819a0632594b93bc29994ef764559eac33245b44d321dcef6eb261f87"
GZIP_BYTES = 152_863
GZIP_SHA256 = "16c12e67e622c90ad5e0461c1bf370fe2ea265e7f053221666f8499fbf74e2cd"
RAW_BYTES = 6_319_719
RAW_SHA256 = "7f43e60f86bd67cdd47efc80a12b8a17771f5864360afcefaef232d08ca04831"
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_GZIP_BYTES = 16 * 1024 * 1024
MAX_RAW_BYTES = 64 * 1024 * 1024
METRICS = ("exploitability", "ip_best_response_gain", "ip_best_response_value",
           "nash_conv", "oop_best_response_gain", "oop_best_response_value",
           "value_ip", "value_oop")
HANDS = {0: {"AdAs", "QdQs"}, 1: {"AsKh", "KdKs"}}


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _is_int(value, expected):
    return type(value) is int and value == expected


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
    _need(not path.is_symlink() and path.is_file() and path.stat().st_size <= limit,
          "Saved file is missing, symlinked, or exceeds its bound")
    with path.open("rb") as stream:
        value = stream.read(limit + 1)
    _need(len(value) <= limit, "Saved file exceeded its bound while reading")
    return value


def _inflate_bounded(compressed):
    import io
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
        raw = stream.read(MAX_RAW_BYTES + 1)
    _need(len(raw) <= MAX_RAW_BYTES, "Saved gzip expands beyond the raw bound")
    return raw


def _index(directory):
    root = Path(directory)
    _need(not root.is_symlink() and root.is_dir(), "Saved publication directory is missing or symlinked")
    entries = []
    for entry in root.iterdir():
        entries.append(entry)
        _need(len(entries) <= 2, "Stopped-run publication contains too many entries")
    _need(len(entries) == 2 and {item.name for item in entries} == {"index.json", "case-140"},
          "Stopped-at-140 publication inventory differs")
    case = root / "case-140"
    _need(case.is_dir() and not case.is_symlink(), "T140 case directory is missing or symlinked")
    case_entries = []
    for entry in case.iterdir():
        case_entries.append(entry)
        _need(len(case_entries) <= 1, "T140 case contains too many files")
    _need(len(case_entries) == 1 and case_entries[0].name == "reference.json.gz" and
          case_entries[0].is_file() and not case_entries[0].is_symlink(),
          "T140 payload inventory differs")
    raw = _read_bounded(root / "index.json", MAX_INDEX_BYTES)
    _need(len(raw) == RAW_INDEX_BYTES and hashlib.sha256(raw).hexdigest() == RAW_INDEX_SHA256,
          "Raw stopped-run index pin differs")
    report = _json(raw)
    _need(type(report) is dict and report.get("index_sha256") == INDEX_SHA256 and
          proof._digest({key: value for key, value in report.items() if key != "index_sha256"}) == INDEX_SHA256,
          "Stopped-run index self-digest differs")
    compressed = _read_bounded(case_entries[0], MAX_GZIP_BYTES)
    _need(len(compressed) == GZIP_BYTES and hashlib.sha256(compressed).hexdigest() == GZIP_SHA256,
          "T140 gzip receipt differs")
    raw_payload = _inflate_bounded(compressed)
    _need(len(raw_payload) == RAW_BYTES and hashlib.sha256(raw_payload).hexdigest() == RAW_SHA256,
          "T140 uncompressed payload receipt differs")
    return report, _json(raw_payload)


def _source_snapshot():
    """Read the present 54-file source inventory without running solver code."""
    return benchmark._snapshot()


def _validate_source(before, after, current):
    for state, recorded in ((before, True), (after, True), (current, False)):
        _need(type(state) is dict and set(state) == {"revision", "status", "source_lf_sha256"} and
              type(state["revision"]) is str and re.fullmatch(r"[0-9a-f]{40}", state["revision"]) and
              state["status"] == "" and type(state["source_lf_sha256"]) is dict and
              len(state["source_lf_sha256"]) == 54,
              "Source snapshot shape/status differs")
        if recorded:
            _need(state["revision"] == SOURCE_REVISION, "Frozen source revision differs")
        _need(all(type(path) is str and type(digest) is str and
                  re.fullmatch(r"[0-9a-f]{64}", digest)
                  for path, digest in state["source_lf_sha256"].items()),
              "Source LF inventory is malformed")
    _need(before == after and current["source_lf_sha256"] == before["source_lf_sha256"],
          "Recorded/current source maps are not identical and clean")


def _metric_fractions(value, name):
    _need(type(value) is dict and set(value) == set(METRICS), f"{name} metric inventory differs")
    result = {}
    for key, text in value.items():
        _need(type(text) is str and len(text) <= 2_048, f"{name} metric is malformed")
        try:
            fraction = Fraction(text)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"{name} metric is not a rational string") from exc
        _need(fraction.numerator.bit_length() <= 4_096 and
              fraction.denominator.bit_length() <= 4_096 and str(fraction) == text,
              f"{name} metric is not a bounded canonical rational")
        result[key] = fraction
    _need(result["nash_conv"] >= 0, f"{name} NashConv is negative")
    _need(result["nash_conv"] == result["ip_best_response_gain"] +
          result["oop_best_response_gain"] and
          result["exploitability"] * 2 == result["nash_conv"] and
          result["value_ip"] + result["value_oop"] == 0 and
          result["ip_best_response_gain"] ==
          result["ip_best_response_value"] - result["value_ip"] and
          result["oop_best_response_gain"] ==
          result["oop_best_response_value"] - result["value_oop"],
          f"{name} exact metric identities differ")
    return result


def _policy_rows(rows, label, normalized):
    _need(type(rows) is list and len(rows) == 608, f"{label} row count differs")
    identities, players = set(), [0, 0]
    parsed = {}
    for row in rows:
        expected_length = 4 if normalized else 2
        _need(type(row) is list and len(row) == expected_length, f"{label} row schema differs")
        key, probabilities = (row[:3], row[3]) if normalized else (row[0], row[1])
        _need(type(key) is list and len(key) == 3 and type(key[0]) is int and key[0] in (0, 1) and
              type(key[1]) is str and key[1] in HANDS[key[0]] and type(key[2]) is list and
              len(key[2]) <= 32 and all(type(token) is str and len(token) <= 256 for token in key[2]),
              f"{label} own-hand information key is malformed or repeated")
        identity = (key[0], key[1], tuple(key[2]))
        _need(identity not in identities, f"{label} own-hand information key is repeated")
        _need(type(probabilities) is list and len(probabilities) == 2 and
              all(type(probability) is float and math.isfinite(probability) and
                  0.0 <= probability <= 1.0 for probability in probabilities),
              f"{label} action probabilities are malformed")
        total = sum((Fraction.from_float(probability) for probability in probabilities), Fraction())
        _need(total == 1 if normalized else abs(float(total) - 1.0) <= 1e-15,
              f"{label} action probabilities do not normalize")
        identities.add(identity)
        players[key[0]] += 1
        parsed[identity] = tuple(probabilities)
    _need(players == [304, 304], f"{label} player row split differs")
    return parsed


def _validate_physical_policy(payload):
    _need(type(payload) is dict and payload.get("algorithm") == "cfrplus" and
          _is_int(payload.get("iterations"), 140) and _is_int(payload.get("averaging_delay"), 0) and
          payload.get("research_adapter") == "fixed-second-board-cfrplus-v1" and
          payload.get("board") == ["7c", "8d", "9h"] and
          payload.get("pot") == 10.0 and payload.get("effective_stack") == [5.0, 5.0],
          "Saved physical-policy fixed-game identity differs")
    _need(payload.get("config") == {"bet_sizes": [0.5], "effective_stack": [5.0, 5.0],
          "include_all_in": False, "max_raises": 0, "pot": 10.0, "raise_sizes": []} and
          _is_int(payload.get("public_states"), 30_812) and
          _is_int(payload.get("public_nodes"), 9_512) and
          _is_int(payload.get("chance_nodes"), 248) and
          _is_int(payload.get("terminal_nodes"), 21_052) and
          _is_int(payload.get("info_sets"), 16_912) and _is_int(payload.get("worlds"), 5_940) and
          _is_int(payload.get("deals"), 3) and _is_int(payload.get("compatible_pairs"), 3),
          "Saved physical policy configuration/census differs")
    embedded_nash = payload.get("nash_conv")
    _need(type(embedded_nash) is float and math.isfinite(embedded_nash) and embedded_nash >= 0 and
          all(type(payload.get(key)) is float and math.isfinite(payload[key]) for key in METRICS),
          "Saved physical metric headers are malformed")
    strategy = payload.get("strategy")
    _need(type(strategy) is list and len(strategy) == 16_912,
          "Saved physical policy row count differs")
    seen, actions_count, players = set(), 0, {"oop": 0, "ip": 0}
    for row in strategy:
        _need(type(row) is dict and row.get("player") in ("oop", "ip") and
              row.get("hand") in (HANDS[0] if row["player"] == "oop" else HANDS[1]) and
              row.get("street") in ("flop", "turn", "river") and
              type(row.get("board")) is list and row["board"][:3] == ["7c", "8d", "9h"] and
              len(row["board"]) == {"flop": 3, "turn": 4, "river": 5}[row["street"]] and
              type(row.get("history")) is list and len(row["history"]) <= 32 and
              all(type(token) is str and len(token) <= 256 for token in row["history"]) and
              type(row.get("actions")) is list and len(row["actions"]) == 2,
              "Saved physical strategy row shape differs")
        ident = (row["player"], row["hand"], tuple(row["history"]))
        _need(ident not in seen, "Saved physical strategy repeats an information row")
        seen.add(ident)
        players[row["player"]] += 1
        for action in row["actions"]:
            _need(type(action) is dict and type(action.get("probability")) is float and
                  math.isfinite(action["probability"]) and 0 <= action["probability"] <= 1,
                  "Saved physical action probability is malformed")
        _need(sum((Fraction.from_float(action["probability"]) for action in row["actions"]),
                  Fraction()) == 1,
              "Saved physical action probabilities do not normalize")
        actions_count += len(row["actions"])
    _need(actions_count == 33_824 and players == {"oop": 8_456, "ip": 8_456},
          "Saved physical action-slot/player count differs")
    return (hashlib.sha256(json.dumps(strategy, sort_keys=True, separators=(",", ":"),
                                      allow_nan=False).encode("utf-8")).hexdigest(),
            embedded_nash)


def _validate_observation(index, payload):
    _need(type(payload) is dict and set(payload) == {"adapter_report", "harness_error", "observation"} and
          payload["adapter_report"] is None,
          "T140 failure payload envelope differs")
    observation = payload["observation"]
    error = payload["harness_error"]
    expected_error = "ValueError: Numeric replay metric inventory differs"
    _need(type(observation) is dict and observation.get("status") == "error" and
          observation.get("phase") == "final-model-validation" and
          _is_int(observation.get("training_calls"), 1) and
          _is_int(observation.get("validation_attempts"), 2) and
          observation.get("primary_error") == expected_error and
          observation.get("final_model_validation") == "passed" and
          observation.get("cleanup_error") is None and
          type(error) is dict and error.get("message") == expected_error,
          "Recorded T140 execution/cleanup failure differs")
    trace = error.get("traceback")
    _need(type(trace) is str and len(trace) <= 32_768 and
          "flop_second_board_cfrplus.py" in trace and
          "Numeric replay metric inventory differs" in trace,
          "Saved failure traceback does not identify the stopped numeric-replay boundary")
    _need(index.get("status") == "error" and type(index.get("errors")) is list and
          index["errors"] and index["errors"][0].get("phase") == "case-execution" and
          index["errors"][0].get("message") == expected_error,
          "Index does not preserve the primary stopped-run error")
    _need(_is_int(index.get("schema_version"), 1) and
          index.get("protocol_id") == "fixed-flop-second-board-cfrplus-pilot-v1" and
          index.get("protocol_sha256") == PROTOCOL_SHA256 and
          [row.get("iterations") for row in index.get("cases", [])] == [140] and
          index["cases"][0].get("status") == "error" and
          index["cases"][0].get("quality_target_met") is None and
          _is_int(index["cases"][0].get("training_calls_after"), 1),
          "Stopped-run case inventory or quality scope differs")
    _need(type(index.get("case_admissions")) is list and
          len(index["case_admissions"]) == 2 and
          all(type(case) is dict for case in index["case_admissions"]) and
          [(_is_int(case.get("requested_iterations"), expected_iterations),
            _is_int(case.get("total_admitted_work"), expected_work))
           for case, expected_iterations, expected_work in zip(
               index["case_admissions"], (140, 560), (25_297_148, 100_992_488))] ==
          [(True, True), (True, True)] and
          type(index.get("admission")) is dict and
          _is_int(index["admission"].get("aggregate_logical_work"), 126_289_636) and
          _is_int(index["admission"].get("aggregate_logical_work_cap"), 140_000_000),
          "Pre-admitted fixed two-case request differs")
    admission = observation.get("admission")
    _need(type(admission) is dict and _is_int(admission.get("requested_iterations"), 140) and
          _is_int(admission.get("total_admitted_work"), 25_297_148) and
          admission.get("version") == "fixed-flop-second-board-cfrplus-logical-work-v1",
          "Stopped T140 admission receipt differs")
    before, after = observation.get("source_before"), observation.get("source_after")
    _validate_source(before, after, {"revision": SOURCE_REVISION, "status": "",
                                     "source_lf_sha256": before.get("source_lf_sha256", {})})
    _need(before == index.get("source_before") and after == index.get("source_after"),
          "Case source snapshots differ from the batch index")
    expected_saved = {
        "status": "saved-second-board-equivalence-authenticated",
        "index_raw_sha256": "06b60eada9aa6465e63138525060b0891f3d66d00e2364dd42e047e2b060880a",
        "index_sha256": "29ff51b127a393d484262d788835324ac76c44fd0f2c5b2ee76e7ee375bd8691",
        "source_revision": "8c093c9af650e53ddf1a98457d0cad69382eb5d1",
        "recorded_exact_metric_calls": 8, "recorded_full_model_proofs": 10,
        "recorded_numeric_replays": 4, "recorded_physical_builds": 1,
        "recorded_preparation_rank_calls": 4134, "recorded_projection_attempts": 6,
        "saved_policy_rows_authenticated": 101472, "physical_builds": 0,
        "ranking_calls": 0, "training_calls": 0, "exact_response_calls": 0,
        "numeric_replay_calls": 0, "model_projection_calls": 0,
        "quality_claim": False,
    }
    _need(proof._typed(observation.get("saved_equivalence_receipt")) == proof._typed(expected_saved),
          "Saved predecessor receipt differs")
    progress = observation.get("preparation_progress")
    _need(type(progress) is dict and progress.get("phase") == "complete" and
          _is_int(progress.get("physical_builds_attempted"), 1) and
          _is_int(progress.get("physical_builds_completed"), 1) and
          _is_int(progress.get("preparation_ranker_attempts"), 4134) and
          _is_int(progress.get("preparation_rank_calls"), 4134) and
          type(progress.get("candidate_dimensions")) is dict and
          all(_is_int(progress["candidate_dimensions"].get(key), value) for key, value in {
              "class_worlds": 170, "physical_world_count": 5940,
              "river_class_count": 17, "turn_class_count": 13}.items()),
          "Saved physical-preparation receipt differs")
    counters = observation.get("preparation_forbidden_calls")
    diag = observation.get("diagnostic_forbidden_calls")
    _need(type(counters) is dict and set(counters) == set(AUTHORITY_KEYS) and
          all(type(value) is int and value == 0 for value in counters.values()) and
          type(diag) is dict and set(diag) == set(AUTHORITY_KEYS) and
          all(type(value) is int and value == 0 for value in diag.values()),
          "Saved 41-counter authority receipts differ")
    census = observation.get("census")
    expected_counts = {
        "compact_public_states": 1270, "compact_decisions": 400,
        "compact_chance_nodes": 68, "compact_terminals": 802,
        "compact_worlds": 170, "compact_policy_rows": 608,
        "compact_action_slots": 1216, "physical_policy_rows": 16912,
        "physical_action_slots": 33824, "compact_world_path_visits": 5610,
        "physical_world_path_visits": 196020, "physical_nodes_checked": 30812,
        "physical_branch_subtrees_compared": 11787,
        "turn_classes": 13, "river_signatures": 17,
    }
    _need(type(census) is dict and all(_is_int(census.get(key), value)
          for key, value in expected_counts.items()) and
          census.get("compact_tree_sha256") == "5b8b6d504a35e0023c9150476ba9bb91d10615eae9ec6bb0305071745ab98152" and
          _is_int(observation.get("maximum_world_path_states"), 33) and
          _is_int(observation.get("training_worlds"), 170) and
          _is_int(observation.get("information_rows"), 608),
          "Saved compact/physical census differs")
    raw_rows = _policy_rows(observation.get("raw_class_policy"), "Raw trainer", normalized=False)
    normalized = _policy_rows(observation.get("class_policy"), "Normalized class", normalized=True)
    _need(raw_rows.keys() == normalized.keys(), "Raw/normalized policy information rows differ")
    norm = observation.get("normalization")
    _need(type(norm) is dict and _is_int(norm.get("normalizer_batches"), 2) and
          norm.get("rows_per_batch") == [304, 304] and _is_int(norm.get("grid_bits"), 52) and
          _is_int(norm.get("rows_changed"), 361) and
          _is_int(norm.get("zeroed_positive_probabilities"), 0) and
          norm.get("max_normalized_probability_distance") == "1/9007199254740992" and
          norm.get("max_raw_distance") == "1/4503599627370496",
          "Saved normalization receipt differs")
    physical_hash, embedded_nash = _validate_physical_policy(observation.get("physical_policy"))
    exact_compact = _metric_fractions(observation.get("exact_compact_metrics"), "Compact exact")
    exact_physical = _metric_fractions(observation.get("exact_physical_metrics"), "Physical exact")
    _need(exact_compact == exact_physical, "Saved compact and physical exact metrics differ")
    _need(float(exact_physical["nash_conv"]) == embedded_nash and
          all(struct.pack(">d", observation["physical_policy"][key]) ==
              struct.pack(">d", float(exact_physical[key])) for key in METRICS),
          "Saved physical-policy metric headers differ bitwise from exact fractions")
    _need("numeric_metrics" not in observation and "audit" not in observation and
          index["cases"][0].get("payload") == {
              "path": "case-140/reference.json.gz", "raw_bytes": RAW_BYTES,
              "raw_sha256": RAW_SHA256, "gzip_bytes": GZIP_BYTES,
              "gzip_sha256": GZIP_SHA256},
          "Stopped run falsely contains numeric replay or payload receipt differs")
    boundaries = index.get("boundaries")
    _need(type(boundaries) is dict and _is_int(boundaries.get("training_calls"), 1) and
          _is_int(boundaries.get("model_build_attempts"), 1) and
          _is_int(boundaries.get("model_proof_calls"), 3) and
          _is_int(boundaries.get("exact_metric_calls"), 2) and
          _is_int(boundaries.get("numeric_replay_calls"), 1) and
          _is_int(boundaries.get("exact_world_node_terms"), 604_890) and
          _is_int(boundaries.get("numeric_world_node_terms"), 588_060) and
          _is_int(boundaries.get("projection_calls"), 1) and
          _is_int(boundaries.get("row_tables"), 10) and
          _is_int(boundaries.get("row_action_slots"), 240_416) and
          _is_int(boundaries.get("preparation_ranker_attempts"), 4134) and
          _is_int(boundaries.get("preparation_rank_calls"), 4134),
          "Recorded expensive-call boundaries differ")
    return {"physical_policy_strategy_sha256": physical_hash,
            "saved_exact_nash_conv": str(exact_physical["nash_conv"]),
            "saved_exact_nash_conv_float": embedded_nash,
            "exact_metric_inventory": list(METRICS),
            "numeric_replay_result": "not saved; no numeric validation claim",
            "quality_result": "not evaluated; the T140 case stopped before completion",
            "iteration_cases_attempted": [140], "iteration_cases_completed": [],
            "iteration_cases_not_run": [560]}


def verify(directory=PUBLICATION):
    """Authenticate only frozen saved bytes and a read-only source snapshot."""
    index, payload = _index(directory)
    current_before = _source_snapshot()
    _validate_source(index.get("source_before"), index.get("source_after"), current_before)
    result = _validate_observation(index, payload)
    index_after, payload_after = _index(directory)
    _need(index_after == index and payload_after == payload,
          "Saved failure artifacts changed during authentication")
    current_after = _source_snapshot()
    _need(current_before == current_after,
          "Current source changed during saved failure authentication")
    return {"schema_version": 1, "status": "saved-stopped-cfrplus-attempt-authenticated",
            "index_sha256": INDEX_SHA256, "source_revision": SOURCE_REVISION,
            "error": "ValueError: Numeric replay metric inventory differs",
            "live_calls": {"model_builds": 0, "model_proofs": 0, "rank_calls": 0,
                           "training_calls": 0, "exact_metric_calls": 0,
                           "numeric_replay_calls": 0, "projection_calls": 0},
            "recorded_training_calls": 1, "recorded_physical_builds": 1,
            "recorded_preparation_rank_calls": 4134,
            "recorded_exact_metric_calls": 2, "recorded_numeric_replay_calls": 1,
            "recorded_projection_calls": 1,
            "numeric_replay_result": result["numeric_replay_result"],
            "quality_result": result["quality_result"],
            "iteration_cases_attempted": result["iteration_cases_attempted"],
            "iteration_cases_completed": result["iteration_cases_completed"],
            "iteration_cases_not_run": result["iteration_cases_not_run"],
            "physical_policy_strategy_sha256": result["physical_policy_strategy_sha256"],
            "saved_exact_nash_conv": result["saved_exact_nash_conv"],
            "saved_exact_nash_conv_float": result["saved_exact_nash_conv_float"],
            "exact_metric_inventory": result["exact_metric_inventory"],
            "source_lf_sha256": dict(index["source_before"]["source_lf_sha256"])}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
