"""Replay a saved reweighted flop CFR+ policy without retraining it."""
import argparse
import gzip
import hashlib
import io
import json
import math
from fractions import Fraction
from pathlib import Path
import struct

from scripts import flop_class_policy as policy
from scripts import flop_class_reweight_cfrplus as trainer
from scripts import flop_class_reweight_proof as reweighted
from scripts import flop_public_classes as proof
from scripts import verify_flop_class_compact_cfrplus_publication as compact_publication
from scripts import verify_flop_class_cfrplus as legacy_replay
from scripts import verify_flop_class_reweight_publication as publication
from scripts import benchmark_flop_class_reweight as evidence


MAX_REPORT_BYTES = 24 * 1024 * 1024
MAX_GZIP_BYTES = 8 * 1024 * 1024


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _read_bounded(path):
    path = Path(path)
    absolute = path.absolute()
    _need(not absolute.is_symlink() and absolute.is_file(),
          "Saved reweighted report must be a regular non-symlink file")
    _need(all(not ancestor.is_symlink() for ancestor in absolute.parents),
          "Saved report path cannot traverse a symlink")
    size = path.stat().st_size
    with path.open("rb") as stream:
        if path.suffix == ".gz" or size >= 2 and stream.peek(2)[:2] == b"\x1f\x8b":
            _need(size <= MAX_GZIP_BYTES, "Compressed report exceeds size bound")
            compressed = stream.read(MAX_GZIP_BYTES + 1)
            _need(len(compressed) <= MAX_GZIP_BYTES,
                  "Compressed report exceeds size bound")
            with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as decoded:
                raw = decoded.read(MAX_REPORT_BYTES + 1)
            _need(len(raw) <= MAX_REPORT_BYTES, "Decompressed report exceeds size bound")
        else:
            _need(size <= MAX_REPORT_BYTES, "Report exceeds size bound")
            raw = stream.read(MAX_REPORT_BYTES + 1)
            _need(len(raw) <= MAX_REPORT_BYTES, "Report exceeds size bound")
    return path, raw


def _raw_rows(value):
    _need(type(value) is list and len(value) == 466,
          "Report must retain all 466 raw compact policy rows")
    rows = {}
    for row in value:
        _need(type(row) is list and len(row) == 4 and type(row[2]) is list and
              type(row[3]) is list and len(row[3]) == 2,
              "Malformed raw compact policy row")
        player, hand, history, values = row
        _need(type(player) is int and player in (0, 1) and type(hand) is str and
              len(hand) == 4 and len(history) <= policy.MAX_HISTORY_ITEMS and
              all(type(token) is str and len(token) <= policy.MAX_HISTORY_TOKEN_CHARS
                  for token in history),
              "Malformed or oversized raw compact policy key")
        key = (player, hand, tuple(history))
        _need(key not in rows, "Duplicate raw compact information set")
        rows[key] = values
    return rows


def _guard_census(calls, expected):
    _need(type(calls) is dict and type(expected) is dict and len(expected) == 41 and
          set(calls) == set(expected) and
          all(type(key) is str and type(value) is int and value == 0
              for key, value in calls.items()),
          "Saved no-training authority guard inventory differs")


def _audit_shape(audit, payload, rows):
    _need(type(audit) is dict and
          set(audit) >= {"exact_metrics", "independent_numeric_metrics", "maximum_numeric_gap",
                         "exact_metric_count", "physical_rows_lifted", "class_rows",
                         "physical_strategy_sha256", "class_policy"},
          "Saved physical audit is incomplete")
    exact, numeric = audit["exact_metrics"], audit["independent_numeric_metrics"]
    _need(type(exact) is dict and set(exact) == set(proof.METRICS) and
          type(numeric) is dict and set(numeric) == set(proof.METRICS) and
          type(audit["exact_metric_count"]) is int and audit["exact_metric_count"] == 8 and
          type(audit["physical_rows_lifted"]) is int and audit["physical_rows_lifted"] == 16912 and
          type(audit["class_rows"]) is int and audit["class_rows"] == 466,
          "Physical audit metric keys or dimensions differ")
    parsed = {}
    try:
        for key in proof.METRICS:
            value = exact[key]
            _need(type(value) is str and len(value) <= 1024,
                  "Exact audit metric is malformed")
            parsed[key] = Fraction(value)
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError("Exact audit metric is malformed") from exc
    _need(parsed["value_ip"] == -parsed["value_oop"] and
          parsed["oop_best_response_gain"] ==
          parsed["oop_best_response_value"] - parsed["value_oop"] and
          parsed["ip_best_response_gain"] ==
          parsed["ip_best_response_value"] - parsed["value_ip"] and
          parsed["nash_conv"] == parsed["oop_best_response_gain"] +
          parsed["ip_best_response_gain"] and
          parsed["exploitability"] == parsed["nash_conv"] / 2,
          "Exact audit metric identities differ")
    _need(type(audit["physical_strategy_sha256"]) is str and
          audit["physical_strategy_sha256"] == proof._digest(payload["strategy"]),
          "Physical strategy digest differs from saved payload")
    expected_policy = [[p, hand, list(history), list(values)]
                       for (p, hand, history), values in sorted(rows.items())]
    _need(proof._typed(audit["class_policy"]) == proof._typed(expected_policy),
          "Audited full class policy differs from normalized raw rows")
    gaps = {}
    for key in proof.METRICS:
        value = numeric[key]
        _need(type(value) in (int, float) and math.isfinite(value),
              "Numeric audit metric is nonfinite or malformed")
        gaps[key] = abs(float(parsed[key]) - value)
    actual_gap = max(gaps.values())
    stated_gap = audit["maximum_numeric_gap"]
    _need(type(stated_gap) in (int, float) and math.isfinite(stated_gap) and
          stated_gap >= 0 and stated_gap == actual_gap and actual_gap <= 1e-10,
          "Physical audit numeric gap is inconsistent or exceeds tolerance")
    return parsed, numeric


def _read_report(path):
    path, raw = _read_bounded(path)
    report = json.loads(raw, object_pairs_hook=legacy_replay._pairs,
                        parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    _need(type(report) is dict and report.get("schema_version") == trainer.ADAPTER and
          report.get("status") == "trained-policy-physically-verified",
          "Saved reweighted report scope or status differs")
    unsigned = {key: value for key, value in report.items() if key != "artifact_sha256"}
    digest = proof._digest(unsigned)
    _need(type(report.get("artifact_sha256")) is str and
          report["artifact_sha256"] == digest,
          "Saved reweighted report checksum differs")
    return path, raw, report


def verify_saved(path):
    """Authenticate bounded bytes, then independently replay physical policy."""
    path, original_raw, report = _read_report(path)
    case_id = report.get("case_id")
    _need(type(case_id) is str and case_id in trainer.CASE_WEIGHTS,
          "Saved reweighted case is outside the fixed three-case scope")
    payload = report.get("physical_policy")
    _need(type(payload) is dict and type(payload.get("iterations")) is int and
          1 <= payload["iterations"] <= trainer.MAX_ITERATIONS,
          "Saved requested iteration count is malformed")
    iterations = payload["iterations"]
    admission = trainer.admit_request(case_id, iterations)
    plan = trainer.case_plan(case_id)
    expected_plan = trainer._plan_record(plan)
    _need(proof._typed(report.get("admission")) == proof._typed(admission) and
          proof._typed(report.get("plan")) == proof._typed(expected_plan),
          "Saved full-request admission or exact weighted plan differs")
    _need(type(report.get("training_calls")) is int and report["training_calls"] == 1 and
          type(payload.get("algorithm")) is str and payload["algorithm"] == "cfrplus" and
          type(payload.get("averaging_delay")) is int and payload["averaging_delay"] == 0 and
          payload.get("research_adapter") == trainer.ADAPTER and
          payload.get("prior_case") == case_id and
          payload.get("compact_resource_model") ==
          admission["compact_logical_admission"]["version"],
          "Saved recurrence, delay, or call count differs")
    _need(type(payload.get("worlds")) is int and payload["worlds"] == 5940 and
          type(payload.get("compatible_pairs")) is int and payload["compatible_pairs"] == 3 and
          type(payload.get("deals")) is int and payload["deals"] == 3 and
          payload.get("strategy_schema") == "postflop-strategy-v1" and
          type(payload.get("strategy")) is list and len(payload["strategy"]) == 16_912,
          "Saved physical policy scope or row count differs")
    sources = trainer.source_hashes()
    _need(type(report.get("source_lf_sha256")) is dict and
          proof._typed(report["source_lf_sha256"]) == proof._typed(sources),
          "Saved executable source map differs")

    _, compact_raw, compact_report = compact_publication._read(
        compact_publication.PUBLICATION)
    baseline_expected = {
        "raw_sha256": compact_publication.RAW_SHA256,
        "artifact_sha256": compact_publication.ARTIFACT_SHA256,
        "iterations": compact_report["physical_policy"]["iterations"],
        "nash_conv": compact_report["physical_policy"]["nash_conv"],
        "quality_target_met": compact_report["quality_target_met"],
    }
    del compact_raw, compact_report
    _need(proof._typed(report.get("compact_historical_baseline")) ==
          proof._typed(baseline_expected), "Historical compact pilot receipt differs")

    raw_rows = _raw_rows(report.get("raw_class_policy"))
    rows, normalization = policy.canonicalize_binary_rows(raw_rows)
    _need(proof._typed(report.get("normalization")) == proof._typed(normalization),
          "Saved raw-policy normalization audit differs")
    saved_exact, saved_numeric = _audit_shape(report.get("audit"), payload, rows)
    saved_met = saved_exact["nash_conv"] <= Fraction(1, 200)
    _need(type(report.get("quality_target")) is float and report["quality_target"] == 0.005 and
          type(report.get("quality_target_met")) is bool and
          report["quality_target_met"] is saved_met,
          "Saved exact quality gate differs from saved audit")
    historical = publication.old_publication.authenticate()
    expected_guards = historical.get("forbidden_production_calls")
    _guard_census(report.get("preparation_forbidden_calls"), expected_guards)
    _guard_census(report.get("diagnostic_forbidden_calls"), expected_guards)
    source_before = evidence._source_snapshot()
    _need(type(source_before) is dict and source_before.get("status") == "" and
          type(source_before.get("revision")) is str and len(source_before["revision"]) == 40 and
          type(source_before.get("source_lf_sha256")) is dict and
          all(type(key) is str and type(value) is str and len(value) == 64
              for key, value in source_before["source_lf_sha256"].items()),
          "Current clean source snapshot differs before replay")
    receipt = publication.verify()
    _need(proof._typed(report.get("proof_receipt")) == proof._typed(receipt),
          "Saved no-training reweight proof receipt differs")

    with proof.independent_guard() as calls:
        model = reweighted.build_model(plan)
        worlds, infos, max_visits = trainer._training_inputs(model)
        _need(set(rows) == set(infos) and
              proof._typed(report.get("census")) == proof._typed(model.census) and
              type(report.get("maximum_world_path_states")) is int and
              report["maximum_world_path_states"] == max_visits,
              "Saved weighted quotient census or information sets differ")
        weighted_world_sha = proof._digest(reweighted._world_rows(model.physical["worlds"]))
        baseline_world_sha = proof._digest(reweighted._world_rows(model.baseline["worlds"]))
        _need(report.get("physical_worlds_sha256") == weighted_world_sha and
              report.get("baseline_worlds_sha256") == baseline_world_sha,
              "Saved weighted or baseline physical-world identity differs")
        projected = reweighted.project_policy(payload, model)
        _need(all(tuple(struct.pack(">d", value) for value in rows[key]) ==
                  tuple(struct.pack(">d", value) for value in projected[key])
                  for key in rows),
              "Saved physical policy does not project to all normalized raw rows")
        actual = reweighted.audit_policy(payload, model)
    fresh_exact, fresh_numeric = _audit_shape(actual, payload, rows)
    for key in ("exact_metrics", "exact_metric_count", "physical_rows_lifted", "class_rows",
                "physical_strategy_sha256", "class_policy"):
        _need(proof._typed(actual[key]) == proof._typed(report["audit"][key]),
              "Fresh weighted physical exact audit differs from saved audit")
    _need(all(abs(saved_numeric[key] - fresh_numeric[key]) <= 1e-10
              for key in proof.METRICS),
          "Saved and fresh numeric metrics differ beyond tolerance")
    actual_gap = actual.get("maximum_numeric_gap")
    _need(type(actual.get("exact_metric_count")) is int and
          actual["exact_metric_count"] == 8 and
          type(actual.get("physical_rows_lifted")) is int and
          actual["physical_rows_lifted"] == 16_912 and
          type(actual.get("class_rows")) is int and actual["class_rows"] == 466 and
          type(actual_gap) in (int, float) and actual_gap >= 0 and
          actual_gap <= 1e-10,
          "Fresh physical audit dimensions or numeric gap differ")
    _guard_census(calls, expected_guards)
    met = fresh_exact["nash_conv"] <= Fraction(1, 200)
    source_after = evidence._source_snapshot()
    _need(proof._typed(source_after) == proof._typed(source_before),
          "Clean source snapshot changed during replay")
    _need(trainer.source_hashes() == sources, "Executable source changed during saved replay")
    _, final_raw, _ = _read_report(path)
    _need(final_raw == original_raw, "Saved reweighted report changed during replay")
    return {"status": "saved-reweighted-policy-physically-verified", "training_calls": 0,
            "case_id": case_id, "iterations": iterations, "class_rows": len(rows),
            "physical_rows": actual["physical_rows_lifted"],
            "nash_conv": float(Fraction(actual["exact_metrics"]["nash_conv"])),
            "quality_target_met": met, "artifact_sha256": report["artifact_sha256"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(verify_saved(args.path), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
