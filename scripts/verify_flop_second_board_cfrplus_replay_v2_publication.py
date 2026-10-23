"""Authenticate the immutable saved second-board CFR+ replay-v2 batch."""
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import struct

from scripts import benchmark_flop_second_board_cfrplus_replay_v2 as harness
from scripts import verify_flop_second_board_equivalence_publication as equivalence
from scripts import verify_flop_second_board_cfrplus_failure_publication as failure
from scripts import flop_second_board_equivalence as proof
from scripts import flop_second_board_cfrplus as adapter


PUBLICATION = harness.ROOT / "benchmarks/results/flop-second-board-cfrplus-replay-v2"
SOURCE_REVISION = "7eed198bc6eb47a7a15b8fb8a84e0061f583ca48"
RAW_INDEX_BYTES = 46_200
RAW_INDEX_SHA256 = "f039c2667ac06db1b987643e4bfe17321a4b086e233b681da4041850c68039a5"
INDEX_SHA256 = "d4ce99cbd3411f95664e828092c5634500d806c4db64ba78339b288d20315021"
CASES = {
    140: {"path": "case-140/reference.json.gz", "gzip_bytes": 636_858,
          "gzip_sha256": "f71aa6b0014147ba5529b9498cccb19b094c5adca5b739293c5931ddc9dd9829",
          "raw_bytes": 25_555_060,
          "raw_sha256": "1e9413ef0c8f68b7acd2c4d4c508a2ba3153c1a0d0f09ec91a6cdd3a0a6bed72",
          "quality": False, "nash_conv_float": 0.014166984012911272},
    560: {"path": "case-560/reference.json.gz", "gzip_bytes": 638_082,
          "gzip_sha256": "5852aa2894af2d09d09405cad5e1032175689ab7417b822d8727ec187ef5e698",
          "raw_bytes": 25_570_177,
          "raw_sha256": "8017400f6456a65651bdf59d05c15bc0e0c9d7265d5b8fbe7f17a8ff0e1ad9ec",
          "quality": True, "nash_conv_float": 0.0016464625267553663},
}
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_GZIP_BYTES = 16 * 1024 * 1024
MAX_RAW_BYTES = 64 * 1024 * 1024
METRICS = tuple(proof.METRICS)
COUNTS = {"checked_information_sets": 16_912, "checked_physical_worlds": 5_940,
          "checked_public_nodes": 9_512, "checked_public_states": 30_812}


def _need(value, message):
    if not value:
        raise ValueError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(raw):
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
                      parse_float=_finite_float)


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite JSON number")
    return result


def _canonical_hash(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_bounded(path, limit):
    path = Path(path)
    _need(not path.is_symlink() and path.is_file() and path.stat().st_size <= limit,
          "Saved file is missing, symlinked, or exceeds its bound")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    _need(len(raw) <= limit, "Saved file exceeded bound while reading")
    return raw


def _inventory(directory):
    root = Path(directory)
    _need(not root.is_symlink() and root.is_dir(), "Publication directory missing or symlinked")
    names = set()
    for entry in root.iterdir():
        names.add(entry.name)
        _need(len(names) <= 3, "Publication contains too many entries")
    _need(names == {"index.json", "case-140", "case-560"}, "Publication inventory differs")
    for iterations in (140, 560):
        folder = root / f"case-{iterations}"
        _need(folder.is_dir() and not folder.is_symlink(), "Case directory missing or symlinked")
        items = []
        for item in folder.iterdir():
            items.append(item)
            _need(len(items) <= 1, "Case contains too many files")
        _need(len(items) == 1 and items[0].name == "reference.json.gz" and
              items[0].is_file() and not items[0].is_symlink(), "Case artifact inventory differs")


def _index(directory):
    raw = _read_bounded(Path(directory) / "index.json", MAX_INDEX_BYTES)
    _need(len(raw) == RAW_INDEX_BYTES and hashlib.sha256(raw).hexdigest() == RAW_INDEX_SHA256,
          "Raw replay-v2 index pin differs")
    report = _json(raw)
    _need(type(report) is dict and report.get("index_sha256") == INDEX_SHA256 and
          proof._digest({key: value for key, value in report.items() if key != "index_sha256"}) == INDEX_SHA256,
          "Replay-v2 index self-digest differs")
    return report


def _payload(directory, case):
    expected = CASES[case["iterations"]]
    receipt = case.get("payload")
    _need(type(receipt) is dict and set(receipt) ==
          {"path", "gzip_bytes", "gzip_sha256", "raw_bytes", "raw_sha256"} and
          receipt == {key: expected[key] for key in receipt}, "Case payload receipt differs")
    compressed = _read_bounded(Path(directory) / expected["path"], MAX_GZIP_BYTES)
    _need(len(compressed) == expected["gzip_bytes"] and
          hashlib.sha256(compressed).hexdigest() == expected["gzip_sha256"],
          "Case gzip pin differs")
    import io
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
        raw = stream.read(MAX_RAW_BYTES + 1)
    _need(len(raw) == expected["raw_bytes"] <= MAX_RAW_BYTES and
          hashlib.sha256(raw).hexdigest() == expected["raw_sha256"], "Case raw pin differs")
    return _json(raw)


def _int(value, expected):
    return type(value) is int and value == expected


def _policy_rows(rows, label, *, normalized):
    _need(type(rows) is list and len(rows) == 608, f"{label} row count differs")
    parsed, players = {}, [0, 0]
    hands = {0: {"AdAs", "QdQs"}, 1: {"AsKh", "KdKs"}}
    for row in rows:
        _need(type(row) is list and len(row) == 4 and type(row[0]) is int and
              row[0] in (0, 1) and type(row[1]) is str and row[1] in hands[row[0]] and
              type(row[2]) is list and len(row[2]) <= 32 and
              all(type(token) is str and len(token) <= 256 for token in row[2]) and
              type(row[3]) is list and len(row[3]) == 2 and
              all(type(p) is float and math.isfinite(p) and 0 <= p <= 1 for p in row[3]),
              f"{label} row is malformed")
        key = (row[0], row[1], tuple(row[2]))
        _need(key not in parsed, f"{label} repeats an information row")
        total = Fraction.from_float(row[3][0]) + Fraction.from_float(row[3][1])
        if normalized:
            _need(total == 1, f"{label} policy row does not exactly normalize")
        else:
            _need(abs(float(total) - 1.0) <= 1e-15, f"{label} raw row is not near-normalized")
        parsed[key] = tuple(row[3])
        players[row[0]] += 1
    _need(players == [304, 304], f"{label} player split differs")
    return parsed


def _source(state, *, recorded=False):
    _need(type(state) is dict and set(state) == {"revision", "status", "source_lf_sha256"} and
          type(state["revision"]) is str and re.fullmatch(r"[0-9a-f]{40}", state["revision"]) and
          state["status"] == "" and type(state["source_lf_sha256"]) is dict and
          len(state["source_lf_sha256"]) == harness.SOURCE_COUNT and
          all(type(path) is str and type(digest) is str and
              re.fullmatch(r"[0-9a-f]{64}", digest)
              for path, digest in state["source_lf_sha256"].items()), "Source snapshot malformed")
    if recorded:
        _need(state["revision"] == SOURCE_REVISION, "Recorded frozen source revision differs")


def _metrics(report, case):
    exact = report["audit"].get("exact_metrics")
    _need(type(exact) is dict and set(exact) == set(METRICS), "Exact metric inventory differs")
    fractions = {}
    for name, value in exact.items():
        _need(type(value) is str and len(value) <= 4096, "Exact fraction is malformed or too large")
        try:
            fraction = Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError("Exact fraction is invalid") from exc
        _need(str(fraction) == value and fraction.numerator.bit_length() <= 4096 and
              fraction.denominator.bit_length() <= 4096,
              "Exact fraction is noncanonical or too large")
        fractions[name] = fraction
    nash = fractions["nash_conv"]
    _need(nash >= 0 and fractions["exploitability"] == nash / 2 and
          fractions["value_ip"] == -fractions["value_oop"] and
          fractions["oop_best_response_gain"] == fractions["oop_best_response_value"] - fractions["value_oop"] and
          fractions["ip_best_response_gain"] == fractions["ip_best_response_value"] - fractions["value_ip"] and
          nash == fractions["oop_best_response_gain"] + fractions["ip_best_response_gain"] and
          fractions["oop_best_response_gain"] >= 0 and fractions["ip_best_response_gain"] >= 0,
          "Exact metric identities differ")
    physical = report["physical_policy"]
    _need(type(physical) is dict, "Physical policy is malformed")
    for name in METRICS:
        _need(type(physical.get(name)) is float and math.isfinite(physical[name]) and
              struct.pack(">d", physical[name]) == struct.pack(">d", float(fractions[name])),
              "Physical metric header differs bitwise from exact metrics")
    _need(float(nash) == CASES[case]["nash_conv_float"], "Saved exact NashConv differs from pinned value")
    return fractions


def _validate_case(index, case, payload):
    iterations = case["iterations"]
    expected = CASES[iterations]
    _need(_int(iterations, iterations) and case.get("status") ==
          ("quality-pass" if expected["quality"] else "quality-miss") and
          type(payload) is dict and set(payload) == {"adapter_report", "observation"},
          "Case completion identity differs")
    report, observation = payload["adapter_report"], payload["observation"]
    _need(type(report) is dict and type(observation) is dict and
          observation.get("status") == observation.get("phase") == "complete" and
          observation.get("primary_error") is None and observation.get("cleanup_error") is None and
          observation.get("final_model_validation") == "passed",
          "Case observation reports an incomplete or failed call")
    _need(report.get("schema_version") == "fixed-second-board-cfrplus-replay-v2" and
          report.get("status") == "trained-policy-physically-verified" and
          report.get("training_calls") == 1 and type(report.get("training_calls")) is int and
          report.get("quality_target") == 0.005 and
          report.get("quality_target_met") is expected["quality"], "Adapter status or quality receipt differs")
    unsigned = {key: value for key, value in report.items() if key != "artifact_sha256"}
    _need(report.get("artifact_sha256") == proof._digest(unsigned), "Adapter report self-digest differs")
    _need(_canonical_hash(observation.get("v2_report")) == _canonical_hash(report),
          "Observation v2 report does not duplicate the returned report")
    for key in ("admission", "audit", "census", "class_policy", "normalization",
                "physical_policy", "preparation_forbidden_calls", "preparation_progress",
                "diagnostic_forbidden_calls", "v1_failure_publication_receipt"):
        _need(_canonical_hash(observation.get(key)) == _canonical_hash(report.get(key)),
              f"Observation/report duplicate differs: {key}")
    obs_raw = observation.get("raw_class_policy")
    _need(type(obs_raw) is list and len(obs_raw) == 608 and
          all(type(row) is list and len(row) == 2 and type(row[0]) is list and len(row[0]) == 3
              for row in obs_raw), "Observation raw trainer policy shape differs")
    obs_raw_flat = sorted([*row[0], row[1]] for row in obs_raw)
    _need(_canonical_hash(obs_raw_flat) == _canonical_hash(report.get("raw_class_policy")),
          "Observation/report raw trainer policy differs")
    v1_report = observation.get("report")
    _need(type(v1_report) is dict and v1_report.get("artifact_sha256") == report.get("wrapped_v1_artifact_sha256") and
          v1_report.get("source_lf_sha256") == report.get("wrapped_v1_source_lf_sha256"),
          "Wrapped v1 report identity differs")
    projected = dict(report)
    v2_keys = ("schema_version", "wrapped_v1_artifact_sha256", "wrapped_v1_source_lf_sha256",
               "v1_failure_publication_receipt", "numeric_replay_raw_receipt", "numeric_replay_v2_receipt")
    for key in v2_keys:
        projected.pop(key, None)
    projected["schema_version"] = v1_report.get("schema_version")
    projected["artifact_sha256"] = report["wrapped_v1_artifact_sha256"]
    projected["source_lf_sha256"] = report["wrapped_v1_source_lf_sha256"]
    _need(_canonical_hash(projected) == _canonical_hash(v1_report), "Wrapped v1 report fields changed")
    failed_v1 = report.get("v1_failure_publication_receipt")
    wrapped_sources = report.get("wrapped_v1_source_lf_sha256")
    _need(report.get("source_revision") == SOURCE_REVISION and
          report.get("source_lf_sha256") == index["source_before"]["source_lf_sha256"] and
          type(wrapped_sources) is dict and len(wrapped_sources) == 54 and
          wrapped_sources == failed_v1.get("source_lf_sha256") and
          all(report["source_lf_sha256"].get(key) == digest for key, digest in wrapped_sources.items()),
          "Report source identities differ")
    _need(observation.get("v2_source_before") == observation.get("v2_source_after") and
          observation.get("v2_source_before").get("source_lf_sha256") == report["source_lf_sha256"] and
          observation.get("source_before") == observation.get("source_after"),
          "Per-case source snapshots differ")
    wrapper = observation.get("v2_wrapper")
    _need(type(wrapper) is dict and wrapper.get("version") == "fixed-second-board-cfrplus-replay-v2" and
          _int(wrapper.get("wrapped_v1_call_count"), 1) and
          _int(wrapper.get("numeric_replay_wrapper_calls"), 1) and
          type(wrapper.get("failure_publication_authenticated")) is bool and
          wrapper.get("failure_publication_authenticated") is True and
          type(wrapper.get("raw_numeric_result_retained")) is bool and
          wrapper.get("raw_numeric_result_retained") is True,
          "Per-case replay wrapper receipt differs")
    _need(report.get("v1_failure_publication_receipt") == observation.get("v1_failure_publication_receipt") and
          failed_v1["status"] == "saved-stopped-cfrplus-attempt-authenticated" and
          failed_v1["iteration_cases_attempted"] == [140] and
          failed_v1["iteration_cases_completed"] == [] and
          failed_v1["iteration_cases_not_run"] == [560] and
          failed_v1["numeric_replay_result"] == "not saved; no numeric validation claim" and
          failed_v1["quality_result"] == "not evaluated; the T140 case stopped before completion" and
          all(value == 0 for value in failed_v1["live_calls"].values()),
          "Frozen failed-v1 prerequisite receipt differs")
    proof_receipt = report.get("proof_receipt")
    _need(type(proof_receipt) is dict and
          proof_receipt.get("status") == "saved-second-board-equivalence-authenticated" and
          all(type(proof_receipt.get(key)) is int and proof_receipt[key] == 0 for key in
              ("physical_builds", "ranking_calls", "training_calls", "exact_response_calls",
               "numeric_replay_calls", "model_projection_calls")),
          "Current saved proof receipt claims live expensive work")
    _need(type(v1_report.get("artifact_sha256")) is str and len(v1_report["artifact_sha256"]) == 64 and
          proof._digest({key: value for key, value in v1_report.items() if key != "artifact_sha256"}) ==
          v1_report["artifact_sha256"] == report["wrapped_v1_artifact_sha256"],
          "Wrapped v1 artifact digest does not verify")
    census = report.get("census")
    wanted_census = {"compact_public_states": 1270, "compact_decisions": 400,
                     "compact_chance_nodes": 68, "compact_terminals": 802,
                     "compact_worlds": 170, "compact_policy_rows": 608,
                     "compact_action_slots": 1216, "physical_policy_rows": 16912,
                     "physical_action_slots": 33824}
    _need(type(census) is dict and all(_int(census.get(k), v) for k, v in wanted_census.items()) and
          census.get("compact_tree_sha256") == "5b8b6d504a35e0023c9150476ba9bb91d10615eae9ec6bb0305071745ab98152" and
          _int(report.get("maximum_world_path_states"), 33), "Saved dimension census differs")
    progress = report.get("preparation_progress")
    _need(type(progress) is dict and _int(progress.get("physical_builds_attempted"), 1) and
          _int(progress.get("physical_builds_completed"), 1) and
          _int(progress.get("preparation_ranker_attempts"), 4134) and
          _int(progress.get("preparation_rank_calls"), 4134), "Preparation receipts differ")
    for key in ("preparation_forbidden_calls", "diagnostic_forbidden_calls"):
        counters = report.get(key)
        _need(type(counters) is dict and set(counters) == set(failure.AUTHORITY_KEYS) and
              all(type(value) is int and value == 0 for value in counters.values()),
              "Saved forbidden-call receipt differs")
    raw = report.get("numeric_replay_raw_receipt")
    _need(type(raw) is dict and set(raw) == set(METRICS) | {"scalar_absolute_gaps"} | set(COUNTS) and
          len(raw) == 13 and all(type(raw[k]) is float and math.isfinite(raw[k]) for k in METRICS),
          "Raw numeric replay field inventory differs")
    _need(_canonical_hash(observation.get("numeric_replay_raw")) == _canonical_hash(raw) and
          _canonical_hash(observation.get("numeric_replay_receipt")) ==
          _canonical_hash(report.get("numeric_replay_v2_receipt")),
          "Observation raw/projected replay receipts differ from report")
    gaps = raw["scalar_absolute_gaps"]
    _need(type(gaps) is dict and set(gaps) == set(METRICS) and
          all(type(value) is float and math.isfinite(value) and 0 <= value <= 1e-10 for value in gaps.values()) and
          all(type(raw[k]) is int and raw[k] == value for k, value in COUNTS.items()),
          "Raw numeric replay gaps or counts differ")
    projection = {"numeric_metrics": {k: raw[k] for k in METRICS},
                  "scalar_absolute_gaps": gaps, "counts": COUNTS, "raw_result_key_count": 13}
    _need(_canonical_hash(report.get("numeric_replay_v2_receipt")) == _canonical_hash(projection),
          "Projected raw replay receipt differs")
    exact_metrics = report["audit"].get("exact_metrics")
    _need(observation.get("exact_compact_metrics") == exact_metrics and
          observation.get("exact_physical_metrics") == exact_metrics,
          "Compact, physical, and adapter exact metrics differ")
    numeric_metrics = report["audit"].get("numeric_metrics")
    _need(type(numeric_metrics) is dict and set(numeric_metrics) == set(METRICS) and
          all(type(numeric_metrics[k]) is float and
              struct.pack(">d", numeric_metrics[k]) == struct.pack(">d", raw[k]) for k in METRICS),
          "Raw replay metrics differ bitwise from saved audit metrics")
    fractions = _metrics(report, iterations)
    calculated_gaps = {key: abs(float(fractions[key]) - raw[key]) for key in METRICS}
    maximum_gap = max(calculated_gaps.values())
    _need(all(struct.pack(">d", calculated_gaps[k]) == struct.pack(">d", gaps[k]) for k in METRICS) and
          type(report["audit"].get("maximum_numeric_gap")) is float and
          struct.pack(">d", maximum_gap) == struct.pack(">d", report["audit"]["maximum_numeric_gap"]) and
          maximum_gap <= 1e-10, "Raw replay scalar gaps differ from exact audit metrics")
    quality_met = fractions["nash_conv"] <= Fraction(1, 200)
    _need(type(report.get("quality_target_met")) is bool and
          report["quality_target_met"] is quality_met is expected["quality"],
          "Quality outcome differs from exact rational target")
    raw_rows = _policy_rows(report.get("raw_class_policy"), "Raw trainer", normalized=False)
    normalized = _policy_rows(report.get("class_policy"), "Normalized class", normalized=True)
    _need(raw_rows.keys() == normalized.keys() and len(normalized) == 608,
          "Raw and normalized policy rows differ")
    _need(_canonical_hash(report["audit"].get("class_policy")) ==
          _canonical_hash(report.get("class_policy")), "Audit and report class policies differ")
    keyed_raw = {(player, hand, history): values for (player, hand, history), values in raw_rows.items()}
    rebuilt, normalization_receipt = adapter.canonicalize_binary_rows(keyed_raw)
    def policy_records(rows):
        return [[player, hand, list(history), list(rows[(player, hand, history)])]
                for player, hand, history in sorted(rows)]
    _need(_canonical_hash(policy_records(rebuilt)) == _canonical_hash(policy_records(normalized)) and
          _canonical_hash(normalization_receipt) == _canonical_hash(report.get("normalization")),
          "Saved class-policy normalization does not reproduce")
    physical_for_validation = dict(report.get("physical_policy", {}))
    physical_for_validation["iterations"] = 140  # helper validates fixed shape; iteration is checked below.
    physical_hash, _ = failure._validate_physical_policy(physical_for_validation)
    _need(_int(report["physical_policy"].get("iterations"), iterations) and
          type(report.get("physical_worlds_sha256")) is str and
          re.fullmatch(r"[0-9a-f]{64}", report["physical_worlds_sha256"]),
          "Saved physical policy or world digest differs")
    # Load only the pinned predecessor's saved class partition. These helpers
    # map public labels; they do not construct/project a poker model.
    _, predecessor = equivalence._read_index(equivalence.PUBLICATION)
    turns, rivers = proof.shared._maps(predecessor["partition"])
    class_bits = {key: tuple(struct.pack(">d", value) for value in values)
                  for key, values in normalized.items()}
    equivalence._mapped_groups(report["physical_policy"], turns, rivers, class_bits)
    _need(report.get("normalization", {}).get("rows_per_batch") == [304, 304] and
          _int(report["normalization"].get("normalizer_batches"), 2),
          "Normalization batch receipt differs")
    _need(str(fractions["nash_conv"]) == report["audit"].get("exact_metrics", {}).get("nash_conv") and
          fractions["nash_conv"] >= 0, "Exact quality metric differs")
    _need(report["physical_worlds_sha256"] ==
          "4ea9c186e4ba524da66b3363ad2a0d8a6851081ca41275a92d2c576a038879ab",
          "Physical-world identity differs from the saved corpus")
    audit = report["audit"]
    _need(_int(audit.get("exact_metric_count"), 8) and _int(audit.get("class_rows"), 608) and
          _int(audit.get("physical_rows_lifted"), 16_912) and
          audit.get("physical_strategy_sha256") == physical_hash,
          "Saved exact-metric or policy-row audit receipt differs")
    case_position = 0 if iterations == 140 else 1
    _need(_int(case.get("training_calls_before"), case_position) and
          _int(case.get("training_calls_after"), case_position + 1) and
          _int(case.get("numeric_replay_calls_before"), case_position) and
          _int(case.get("numeric_replay_calls_after"), case_position + 1) and
          _int(case.get("numeric_replay_calls_in_case"), 1) and
          _int(case.get("numeric_replay_attempts_in_case"), 1) and
          type(case.get("quality_target_met")) is bool and
          case["quality_target_met"] is quality_met and case.get("serialization_error") is None,
          "Per-case replay/training counter or quality receipt differs")
    for key in ("preparation_forbidden_calls", "diagnostic_forbidden_calls"):
        _need(_canonical_hash(case.get(key)) == _canonical_hash(report.get(key)),
              f"Index/report authority receipt differs: {key}")
    return {"iterations": iterations, "quality_target_met": expected["quality"],
            "exact_nash_conv": str(fractions["nash_conv"]), "physical_policy_sha256": physical_hash}


def _validate_index(report):
    _need(report.get("schema_version") == 2 and report.get("protocol_id") == harness.PROTOCOL and
          report.get("protocol_sha256") == harness.SPEC_SHA256 and report.get("status") == "verified-quality-miss" and
          report.get("errors") == [] and report.get("execution_state") ==
          {"mode": "ordinary-process", "system_required": False}, "Batch identity/status differs")
    _need([case.get("iterations") for case in report.get("cases", [])] == [140, 560] and
          all(case.get("status") == ("quality-miss" if case["iterations"] == 140 else "quality-pass")
              for case in report["cases"]), "Batch case inventory or outcomes differ")
    boundaries = report.get("boundaries")
    expected = {"training_calls": 2, "model_build_attempts": 2, "model_proof_calls": 6,
                "exact_metric_calls": 4, "numeric_replay_calls": 2, "projection_calls": 2,
                "row_tables": 20, "row_action_slots": 480_832,
                "preparation_ranker_attempts": 8_268, "preparation_rank_calls": 8_268}
    _need(type(boundaries) is dict and all(_int(boundaries.get(k), v) for k, v in expected.items()),
          "Recorded expensive-call boundaries differ")
    _need(_int(report["admission"].get("aggregate_logical_work"), 126_289_636) and
          _int(report["admission"].get("aggregate_logical_work_cap"), 140_000_000),
          "Aggregate logical-work admission differs")
    _source(report.get("source_before"), recorded=True)
    _source(report.get("source_after"), recorded=True)
    _need(report["source_before"] == report["source_after"], "Frozen source snapshots differ")
    return report["source_before"]


def verify(directory=PUBLICATION):
    """Authenticate saved bytes and recorded receipts; never run a solver or replay."""
    _inventory(directory)
    index = _index(directory)
    frozen_source = _validate_index(index)
    # The current repository may have a later HEAD, but its clean named LF map must match.
    current_before = harness._snapshot()
    _source(current_before)
    _need(current_before["status"] == "" and
          current_before["source_lf_sha256"] == frozen_source["source_lf_sha256"],
          "Current clean source map differs from frozen batch")
    summaries = []
    for case in index["cases"]:
        payload = _payload(directory, case)
        summaries.append(_validate_case(index, case, payload))
    # Re-read all pinned bytes and source after semantic validation to close TOCTOU gaps.
    index_again = _index(directory)
    _need(_canonical_hash(index_again) == _canonical_hash(index), "Index changed during authentication")
    for case in index["cases"]:
        _payload(directory, case)
    _inventory(directory)
    current_after = harness._snapshot()
    _need(current_after == current_before, "Current source changed during authentication")
    return {"schema_version": 1, "status": "saved-second-board-replay-v2-batch-authenticated",
            "index_sha256": INDEX_SHA256, "source_revision": SOURCE_REVISION,
            "live_calls": {"model_builds": 0, "model_proofs": 0, "rank_calls": 0,
                           "training_calls": 0, "exact_metric_calls": 0,
                           "numeric_replay_calls": 0, "projection_calls": 0},
            "recorded_training_calls": 2, "recorded_model_build_attempts": 2,
            "recorded_model_proofs": 6, "recorded_exact_metric_calls": 4,
            "recorded_numeric_replays": 2, "recorded_projection_calls": 2,
            "recorded_row_tables": 20, "recorded_row_action_slots": 480_832,
            "iteration_cases_attempted": [140, 560],
            "iteration_cases_completed": [140, 560], "iteration_cases_not_run": [],
            "case_results": summaries,
            "quality_scope": "Exact finite-game threshold outcomes as recorded; no broader-game claim.",
            "quality_outcomes": {"140": "miss", "560": "pass"},
            "source_lf_sha256": dict(frozen_source["source_lf_sha256"])}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
