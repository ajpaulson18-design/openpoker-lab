"""Bounded verification of a completed fixed-flop range-reweight evidence batch.

This module reads saved evidence only. It does not prepare an oracle, build a
model, replay a policy, or train a solver. The two index pins are filled from
the completed immutable run before publication.
"""
import gzip
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import re
from fractions import Fraction

from scripts import benchmark_flop_class_cost as cost
from scripts import benchmark_flop_class_reweight as runner
from scripts import flop_class_reweight_plan as planning
from scripts import flop_public_classes as proof
from scripts import verify_flop_public_classes_publication as old_publication


ROOT = Path(__file__).resolve().parents[1]
PUBLICATION = ROOT / "benchmarks/results/flop-class-reweight-proof-v1"
INDEX_RAW_SHA256 = "4fe70ce71d09b5c41816917e2297ab8027e0f2b5c3e536ff6b473c3e695136f6"
INDEX_SHA256 = "166e877f68cc8ab7cf027ce6e80e18eb4ec952b5918aa26c85e4076bf6185dcb"
EXPECTED_REVISION = "b43bacbf2bd19b37ac6c7b0f8d4d5b115f9d2e13"
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_RAW_BYTES = 24 * 1024 * 1024
MAX_GZIP_BYTES = 8 * 1024 * 1024
METRICS = ("exploitability", "ip_best_response_gain", "ip_best_response_value",
           "nash_conv", "oop_best_response_gain", "oop_best_response_value",
           "value_ip", "value_oop")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _need(key not in result, "Duplicate JSON field")
        result[key] = value
    return result


def _canonical(value):
    return cost._canonical(value, newline=True)


def _index_canonical(value):
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"


def _read_index(path):
    _need(path.stat().st_size <= MAX_INDEX_BYTES, "Index exceeds size bound")
    with path.open("rb") as stream:
        raw = stream.read(MAX_INDEX_BYTES + 1)
    _need(len(raw) <= MAX_INDEX_BYTES, "Index exceeds size bound")
    _need(hashlib.sha256(raw).hexdigest() == INDEX_RAW_SHA256,
          "Index raw bytes differ from immutable pin")
    value = json.loads(raw, object_pairs_hook=_pairs,
                       parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    _need(type(value) is dict and value.get("index_sha256") == INDEX_SHA256,
          "Index identity differs from immutable pin")
    unsigned = {key: item for key, item in value.items() if key != "index_sha256"}
    _need(proof._digest(unsigned) == INDEX_SHA256, "Canonical index checksum differs")
    _need(_index_canonical(value) == raw, "Index is not canonical JSON")
    return raw, value


def _read_gzip(directory, row):
    _need(type(row) is dict and set(row) == {
        "path", "raw_bytes", "gzip_bytes", "raw_sha256", "gzip_sha256"},
        "Malformed evidence file record")
    name = row["path"]
    _need(type(name) is str and Path(name).name == name and name.endswith(".json.gz") and
          type(row["raw_bytes"]) is int and type(row["gzip_bytes"]) is int and
          0 <= row["raw_bytes"] <= MAX_RAW_BYTES and
          0 <= row["gzip_bytes"] <= MAX_GZIP_BYTES and
          type(row["raw_sha256"]) is str and HEX64.fullmatch(row["raw_sha256"]) and
          type(row["gzip_sha256"]) is str and HEX64.fullmatch(row["gzip_sha256"]),
          "Unsafe evidence filename")
    path = directory / name
    _need(not path.is_symlink(), "Evidence file cannot be a symlink")
    _need(path.stat().st_size <= MAX_GZIP_BYTES, "Compressed evidence exceeds size bound")
    with path.open("rb") as stream:
        compressed = stream.read(MAX_GZIP_BYTES + 1)
    _need(len(compressed) <= MAX_GZIP_BYTES and len(compressed) == row["gzip_bytes"] and
          hashlib.sha256(compressed).hexdigest() == row["gzip_sha256"],
          "Compressed evidence size or checksum differs")
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
        raw = stream.read(MAX_RAW_BYTES + 1)
    _need(len(raw) <= MAX_RAW_BYTES and len(raw) == row["raw_bytes"] and
          hashlib.sha256(raw).hexdigest() == row["raw_sha256"],
          "Raw evidence size or checksum differs")
    value = json.loads(raw, object_pairs_hook=_pairs,
                       parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    _need(_canonical(value) == raw, "Evidence is not canonical JSON")
    return raw, value


def _plan_records(spec):
    plans, _ = runner._preflight(spec)
    return {case_id: runner._plan_record(plan) for case_id, plan in plans}


def _check_source(source):
    _need(type(source) is dict and set(source) == {"revision", "status", "source_lf_sha256"} and
          type(source["revision"]) is str and HEX40.fullmatch(source["revision"]) and
          source["status"] == "" and type(source["source_lf_sha256"]) is dict and
          all(type(k) is str and type(v) is str and HEX64.fullmatch(v)
              for k, v in source["source_lf_sha256"].items()),
          "Malformed or dirty source snapshot")


def _timestamp(value):
    _need(type(value) is str, "Timestamp must be an ISO string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Malformed UTC timestamp") from None
    _need(parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed),
          "Timestamp must be timezone-aware UTC")
    return parsed


def _execution_and_runtime(index):
    runtime = index.get("runtime")
    _need(type(runtime) is dict and set(runtime) == {"python", "implementation", "platform"} and
          all(type(runtime[key]) is str and runtime[key] for key in runtime),
          "Malformed runtime metadata")
    state = index.get("execution_state")
    _need(type(state) is dict, "Malformed execution-state metadata")
    if state.get("mode") in ("direct-call", "ordinary-process"):
        _need(state == {"mode": state["mode"], "system_required": False},
              "Malformed ordinary execution-state metadata")
    else:
        _need(state.get("mode") == "windows-benchmark-thread" and
              state.get("system_required") is True and
              type(state.get("requested_flags")) is int and
              state["requested_flags"] == 0x80000001 and
              type(state.get("previous_flags")) is int and state["previous_flags"] > 0 and
              set(state) == {"mode", "system_required", "previous_flags", "requested_flags"},
              "Malformed Windows execution-state metadata")
    for key in ("wall_seconds", "process_seconds"):
        _need(type(index.get(key)) in (int, float) and math.isfinite(index[key]) and
              index[key] >= 0, "Malformed overall elapsed-time metadata")
    return _timestamp(index.get("created_at_utc")), _timestamp(index.get("finished_at_utc"))


def _check_plan(preparation, expected, case_id):
    _need(preparation.get("case_id") == case_id and
          proof._typed(preparation.get("plan")) == proof._typed(expected),
          "Preparation case or exact plan differs")
    plan = planning.plan_weights(
        tuple(__fraction(n, d) for n, d in expected["oop_weights"]),
        tuple(__fraction(n, d) for n, d in expected["ip_weights"]))
    _need(proof._typed(preparation.get("normalizer")) == proof._typed([
              plan.global_blocker_normalizer.numerator,
              plan.global_blocker_normalizer.denominator]) and
          type(preparation.get("worlds")) is int and preparation["worlds"] == 5940,
          "Preparation normalizer or world count differs")
    census = preparation.get("census")
    expected_base = runner.reweighted.EXPECTED_CENSUS
    expected_census_keys = set(expected_base) | {
        "compact_tree_sha256", "physical_branch_subtrees_compared", "physical_nodes_checked"}
    _need(type(census) is dict and set(census) == expected_census_keys and
          all(type(census.get(key)) is int and census[key] == value
              for key, value in expected_base.items()) and
          type(census["compact_tree_sha256"]) is str and
          HEX64.fullmatch(census["compact_tree_sha256"]) and
          type(census["physical_branch_subtrees_compared"]) is int and
          census["physical_branch_subtrees_compared"] == 11787 and
          type(census["physical_nodes_checked"]) is int and
          census["physical_nodes_checked"] == 30812,
          "Compact census differs from the fixed game")
    for key in ("weighted_worlds_sha256", "physical_tree_sha256",
                "baseline_world_sha256", "baseline_tree_sha256"):
        _need(type(preparation.get(key)) is str and HEX64.fullmatch(preparation[key]),
              "Malformed physical identity digest")
    return plan


def __fraction(numerator, denominator):
    from fractions import Fraction
    _need(type(numerator) is int and type(denominator) is int and denominator > 0,
          "Malformed exact plan fraction")
    return Fraction(numerator, denominator)


def _check_pair_metadata(preparation, plan):
    priors = {(runner.reweighted._canonical_hand(a),
               runner.reweighted._canonical_hand(b)): p
              for a, b, p in plan.exact_pair_priors}
    counts = preparation.get("pair_counts")
    _need(type(counts) is list and len(counts) == len(priors),
          "Physical pair-count inventory differs")
    observed = set()
    sign_census = {}
    for row in counts:
        _need(type(row) is dict, "Malformed physical pair-count row")
        pair = (runner.reweighted._canonical_hand(row.get("oop_hand", "")),
                runner.reweighted._canonical_hand(row.get("ip_hand", "")))
        _need(pair in priors and pair not in observed and
              type(row.get("ordered_outcomes")) is int and row["ordered_outcomes"] == 1980 and
              all(type(row.get(k)) is int and row[k] >= 0 for k in ("wins", "ties", "losses")) and
              sum(row[k] for k in ("wins", "ties", "losses")) == 1980 and
              row.get("pair_probability_fraction") ==
              f"{priors[pair].numerator}/{priors[pair].denominator}" and
              type(row.get("pair_probability")) is float and
              row["pair_probability"] == float(priors[pair]),
              "Physical pair count or exact prior differs")
        observed.add(pair)
        sign_census[pair] = tuple(row[k] for k in ("wins", "ties", "losses"))
    probs = preparation.get("pair_probabilities")
    _need(type(probs) is list and len(probs) == len(priors),
          "Pair probability inventory differs")
    got = {}
    for row in probs:
        _need(type(row) is list and len(row) == 3 and type(row[2]) is float,
              "Malformed pair probability")
        got[(row[0], row[1])] = row[2]
    _need(set(got) == set(priors) and
          all(got[pair] == float(value) for pair, value in priors.items()),
          "Pair probabilities differ from exact blocker-conditioned priors")
    return sign_census


def _check_control(case_id, mode, record, control_row, old_controls):
    _need(type(record) is dict and record.get("case_id") == case_id and
          record.get("control") == mode and type(record.get("payload")) is dict and
          type(record.get("audit")) is dict,
          "Control evidence identity or shape differs")
    payload, audit = record["payload"], record["audit"]
    _need(type(payload.get("worlds")) is int and payload["worlds"] == 5940 and
          type(payload.get("compatible_pairs")) is int and payload["compatible_pairs"] == 3 and
          type(payload.get("deals")) is int and payload["deals"] == 3 and
          payload.get("strategy_schema") == "postflop-strategy-v1" and
          type(payload.get("strategy")) is list and
          len(payload["strategy"]) == 16912,
          "Physical policy scope or row count differs")
    _need(type(audit.get("exact_metric_count")) is int and audit["exact_metric_count"] == 8 and
          set(audit.get("exact_metrics", {})) == set(METRICS) and
          set(audit.get("independent_numeric_metrics", {})) == set(METRICS) and
          type(audit.get("physical_rows_lifted")) is int and audit["physical_rows_lifted"] == 16912 and
          type(audit.get("class_rows")) is int and audit["class_rows"] == 466 and
          type(audit.get("class_policy")) is list and len(audit["class_policy"]) == 466,
          "Control audit metric or policy dimensions differ")
    _need(proof._digest(payload["strategy"]) == audit.get("physical_strategy_sha256"),
          "Physical strategy digest differs from audit")
    gaps = []
    exact_values = {}
    for key in METRICS:
        value = audit["independent_numeric_metrics"][key]
        _need(type(value) in (int, float) and math.isfinite(value),
              "Independent numeric metric is non-finite")
        exact_text = audit["exact_metrics"][key]
        _need(type(exact_text) is str and len(exact_text) <= 1024,
              "Malformed or oversized exact metric")
        try:
            exact_fraction = Fraction(exact_text)
            exact = float(exact_fraction)
        except (ValueError, TypeError, ZeroDivisionError, OverflowError):
            raise ValueError("Malformed exact metric") from None
        exact_values[key] = exact_fraction
        gaps.append(abs(exact - value))
    oop_value, ip_value = exact_values["value_oop"], exact_values["value_ip"]
    oop_br, ip_br = (exact_values["oop_best_response_value"],
                     exact_values["ip_best_response_value"])
    oop_gain, ip_gain = (exact_values["oop_best_response_gain"],
                         exact_values["ip_best_response_gain"])
    _need(ip_value == -oop_value and oop_br >= oop_value and ip_br >= ip_value and
          oop_gain == oop_br - oop_value and ip_gain == ip_br - ip_value and
          exact_values["nash_conv"] == oop_gain + ip_gain and
          exact_values["exploitability"] == exact_values["nash_conv"] / 2,
          "Eight exact metrics violate zero-sum best-response identities")
    maximum = max(gaps)
    _need(type(audit.get("maximum_numeric_gap")) in (int, float) and
          math.isfinite(audit["maximum_numeric_gap"]) and
          audit["maximum_numeric_gap"] <= 1e-10 and
          audit["maximum_numeric_gap"] == maximum,
          "Independent numeric metric gap exceeds bound or is misstated")
    _need(proof._typed(control_row.get("audit_summary")) ==
          proof._typed(runner._audit_summary(audit)),
          "Index audit summary differs from full saved audit")
    if case_id == "baseline":
        _need(all(proof._typed(audit[k]) == proof._typed(old_controls[mode][k])
                  for k in runner.BASELINE_FIELDS),
              "Baseline control differs from authenticated historical control")


def verify(directory=PUBLICATION):
    """Verify completed gzip evidence and return a compact authenticated summary."""
    original = Path(directory).absolute()
    _need(not original.is_symlink(), "Evidence directory cannot be a symlink")
    for ancestor in original.parents:
        _need(not ancestor.is_symlink(), "Evidence path cannot traverse a symlink")
    directory = original.resolve()
    _need(directory.is_dir(), "Evidence path must be a directory")
    index_path = directory / "index.json"
    _need(not index_path.is_symlink(), "Evidence index cannot be a symlink")
    raw_index, index = _read_index(index_path)
    _need(type(index.get("schema_version")) is int and index.get("schema_version") == 1 and
          index.get("protocol_id") == "fixed-flop-class-reweight-proof-v1" and
          index.get("status") == "complete" and index.get("errors") == [] and
          type(index.get("training_calls")) is int and index.get("training_calls") == 0,
          "Evidence batch is incomplete, errored, or trained")
    spec = runner._protocol()
    _need(proof._typed(index.get("protocol")) == proof._typed(spec),
          "Saved protocol differs from frozen protocol")
    plans = _plan_records(spec)
    _, expected_preflight = runner._preflight(spec)
    _need(proof._typed(index.get("preflight")) == proof._typed(expected_preflight),
          "Saved preflight forecast differs from fixed-game admission")
    cases = index.get("cases")
    _need(type(cases) is list and [row.get("case_id") for row in cases] ==
          list(runner.CASE_IDS), "Case inventory differs")
    source_before = index.get("source_before")
    source_after = index.get("source_after")
    _check_source(source_before)
    _check_source(source_after)
    _need(source_before["revision"] == source_after["revision"] == EXPECTED_REVISION,
          "Recorded revision differs from frozen source checkpoint")
    _need(proof._typed(source_before) == proof._typed(source_after),
          "Overall frozen source snapshots differ")
    for case in cases:
        _check_source(case.get("source_before"))
        _check_source(case.get("source_after"))
        _need(case["source_before"]["revision"] == EXPECTED_REVISION and
              proof._typed(case["source_before"]) == proof._typed(case["source_after"]) ==
              proof._typed(source_before) and
              case.get("status") == "complete",
              "Case source snapshots or completion state differ")
    current_before = runner._source_snapshot()
    _check_source(current_before)
    _need(current_before["status"] == "" and
          current_before["source_lf_sha256"] == source_before["source_lf_sha256"],
          "Current source identities differ from run")
    created, finished = _execution_and_runtime(index)
    _need(created <= finished, "Overall UTC timestamps are reversed")
    _need(runner._valid_guard_census(index.get("forbidden_production_calls")),
          "Authority guard census is incomplete or nonzero")
    _need(index.get("baseline_receipt", {}).get("training_calls") == 0,
          "Historical baseline receipt indicates training")
    old = old_publication.authenticate()
    expected_receipt = {
        "raw_sha256": old_publication.RAW_SHA256,
        "artifact_sha256": old_publication.ARTIFACT_SHA256,
        "interruption_sha256": old_publication.INTERRUPTION_SHA256,
        "physical_worlds_sha256": old["physical_worlds_sha256"],
        "physical_tree_sha256": old["physical_tree_sha256"],
        "source_lf_sha256": old["source_lf_sha256"],
        "training_calls": old["training_calls"],
        "forbidden_production_calls": old["forbidden_production_calls"]}
    _need(proof._typed(index.get("baseline_receipt")) == proof._typed(expected_receipt),
          "Historical baseline receipt differs from immutable publication")
    _need(set(index.get("forbidden_production_calls", {})) ==
          set(old.get("forbidden_production_calls", {})),
          "Authority guard keys differ from historical guard inventory")
    old_controls = old.get("controls")
    _need(type(old_controls) is dict and set(old_controls) == set(runner.CONTROLS),
          "Historical immutable controls unavailable")
    files = index.get("files")
    expected_names = {f"{case_id}-preparation.json.gz" for case_id in runner.CASE_IDS}
    expected_names |= {f"{case_id}-{mode}.json.gz" for case_id in runner.CASE_IDS
                       for mode in runner.CONTROLS}
    _need(type(files) is list and len(files) == 15 and
          [row.get("path") for row in files] and
          set(row.get("path") for row in files) == expected_names,
          "Evidence file inventory differs")
    _need({path.name for path in directory.iterdir()} == expected_names | {"index.json"},
          "Directory contains missing or unregistered evidence")
    shared_sign_census = None
    baseline_hashes = None
    for case in cases:
        case_id = case["case_id"]
        expected_plan = plans[case_id]
        _need(proof._typed(case.get("plan")) == proof._typed(expected_plan),
              "Index case plan differs from frozen protocol")
        prep_row = case.get("preparation_file")
        _need(type(prep_row) is dict and prep_row in files and
              prep_row["path"] == f"{case_id}-preparation.json.gz",
              "Case preparation file reference differs")
        prep_raw, prep = _read_gzip(directory, prep_row)
        plan = _check_plan(prep, expected_plan, case_id)
        sign_census = _check_pair_metadata(prep, plan)
        _need(shared_sign_census is None or sign_census == shared_sign_census,
              "Physical per-pair outcome signs changed across reweighted cases")
        shared_sign_census = sign_census
        _need(proof._typed(case.get("census")) == proof._typed(prep.get("census")),
              "Index census differs from preparation")
        receipt = index["baseline_receipt"]
        _need(prep["baseline_world_sha256"] == receipt["physical_worlds_sha256"] and
              prep["baseline_tree_sha256"] == receipt["physical_tree_sha256"] and
              prep["physical_tree_sha256"] == receipt["physical_tree_sha256"],
              "Preparation physical tree or baseline world differs from authenticated anchor")
        if case_id == "baseline":
            _need(prep["weighted_worlds_sha256"] == receipt["physical_worlds_sha256"],
                  "Baseline weighted world differs from authenticated old anchor")
        current_hashes = (prep["baseline_world_sha256"], prep["baseline_tree_sha256"],
                          prep["physical_tree_sha256"])
        _need(baseline_hashes is None or current_hashes == baseline_hashes,
              "Baseline or physical tree anchor changes across prior cases")
        baseline_hashes = current_hashes
        case_started = _timestamp(case.get("started_at_utc"))
        case_finished = _timestamp(case.get("finished_at_utc"))
        _need(created <= case_started <= case_finished <= finished,
              "Case UTC timestamps are outside run chronology")
        for elapsed in (case.get("wall_seconds"), case.get("process_seconds")):
            _need(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0,
                  "Malformed case elapsed-time metadata")
        controls = case.get("controls")
        _need(type(controls) is list and [r.get("control") for r in controls] ==
              list(runner.CONTROLS) and all(r.get("status") == "complete" for r in controls),
              "Control inventory or status differs")
        for control in controls:
            mode = control["control"]
            control_started = _timestamp(control.get("started_at_utc"))
            control_finished = _timestamp(control.get("finished_at_utc"))
            _need(case_started <= control_started <= control_finished <= case_finished,
                  "Control UTC timestamps are outside case chronology")
            for elapsed in (control.get("wall_seconds"), control.get("process_seconds")):
                _need(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0,
                      "Malformed control elapsed-time metadata")
            row = control.get("evidence_file")
            _need(type(row) is dict and row in files and
                  row["path"] == f"{case_id}-{mode}.json.gz",
                  "Control evidence file reference differs")
            control_raw, record = _read_gzip(directory, row)
            _check_control(case_id, mode, record, control, old_controls)
            del record, control_raw
        del prep, prep_raw
    for row in files:
        _read_gzip(directory, row)
    current_after = runner._source_snapshot()
    _check_source(current_after)
    _need(proof._typed(current_after) == proof._typed(current_before),
          "Full current source snapshot changed during verification")
    final_raw, _ = _read_index(index_path)
    _need(final_raw == raw_index, "Index changed during verification")
    return {"status": "saved-reweight-publication-authenticated", "cases": 3, "controls": 12,
            "files": 15, "training_calls": 0,
            "source_revision": source_before["revision"],
            "index_sha256": INDEX_SHA256}


def main():
    result = verify()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


