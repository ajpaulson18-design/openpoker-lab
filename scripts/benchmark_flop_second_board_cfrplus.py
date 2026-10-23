"""Run one bounded, two-case second-board CFR+ pilot and retain full receipts.

The harness executes exactly one fresh adapter call at 140 sweeps and one at
560 sweeps, stopping at the first error. It is an execution receipt, not a
runtime, memory, convergence, or unrestricted Hold'em claim.
"""
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import gzip
import hashlib
import importlib
import json
from pathlib import Path
import platform
import sys
import time
import traceback
from unittest.mock import patch

from scripts import benchmark_flop_second_board_equivalence as previous
from scripts import flop_second_board_cfrplus_budget as budget
from scripts import flop_second_board_equivalence as proof
from scripts import verify_flop_second_board_equivalence_publication as publication


ROOT = previous.ROOT
SPEC = ROOT / "benchmarks/flop-second-board-cfrplus-pilot-v1.json"
SPEC_SHA256 = "75c0e30819a0632594b93bc29994ef764559eac33245b44d321dcef6eb261f87"
SOURCE_COUNT = 54
MAX_SOURCE_BYTES = previous.previous.MAX_SOURCE_BYTES
MAX_INDEX_BYTES = previous.previous.MAX_INDEX_BYTES
MAX_RAW_BYTES = previous.previous.MAX_PAYLOAD_BYTES
MAX_GZIP_BYTES = previous.previous.MAX_GZIP_BYTES
ITERATIONS = (140, 560)
AGGREGATE_LOGICAL_CAP = 140_000_000
AGGREGATE_LOGICAL_RESERVATION = 126_289_636
MAX_MODEL_BUILDS = 2
MAX_MODEL_PROOFS = 10
PROOF_PASS_RESERVATION_EACH = 807_740
AGGREGATE_PROOF_PASS_RESERVATION = 8_077_400
MAX_EXACT_METRIC_CALLS = 4
EXACT_WORLD_NODE_TERM_RESERVATION = 1_209_780
MAX_NUMERIC_REPLAYS = 2
NUMERIC_WORLD_NODE_TERM_RESERVATION = 1_176_120
MAX_PROJECTION_CALLS = 2
MAX_ROW_TABLES = 100
MAX_ROW_ACTION_SLOTS = 4_000_000
MAX_PREPARATION_RANK_CALLS_PER_MODEL = 11_880
MAX_PREPARATION_RANK_CALLS_TOTAL = 23_760
FAILURE_FALLBACK_COUNT = 1
_need = previous._need


def expected_protocol():
    """Return a fresh, JSONable copy of the complete fixed pilot request."""
    return {
        "protocol_id": "fixed-flop-second-board-cfrplus-pilot-v1",
        "request": {
            "board": ["7c", "8d", "9h"],
            "iterations": list(ITERATIONS),
            "algorithm": "cfrplus",
            "averaging_delay": 0,
            "independent_fresh_model_per_case": True,
            "stop_after_first_error": True,
            "retry_count": 0,
            "target_nash_conv": "1/200",
            "retain_quality_misses": True,
            "normalization_batch_rows_by_player": {"player_0": 304, "player_1": 304},
        },
        "limits": {
            "aggregate_logical_work_cap": AGGREGATE_LOGICAL_CAP,
            "aggregate_logical_work_reservation": AGGREGATE_LOGICAL_RESERVATION,
            "maximum_model_builds": MAX_MODEL_BUILDS,
            "maximum_model_proofs": MAX_MODEL_PROOFS,
            "proof_pass_reservation_each": PROOF_PASS_RESERVATION_EACH,
            "aggregate_proof_pass_reservation": AGGREGATE_PROOF_PASS_RESERVATION,
            "maximum_exact_metric_calls": MAX_EXACT_METRIC_CALLS,
            "exact_world_node_term_reservation": EXACT_WORLD_NODE_TERM_RESERVATION,
            "maximum_numeric_replays": MAX_NUMERIC_REPLAYS,
            "numeric_world_node_term_reservation": NUMERIC_WORLD_NODE_TERM_RESERVATION,
            "maximum_projection_calls": MAX_PROJECTION_CALLS,
            "maximum_row_tables": MAX_ROW_TABLES,
            "maximum_row_action_slots": MAX_ROW_ACTION_SLOTS,
            "preparation_rank_calls_per_model": MAX_PREPARATION_RANK_CALLS_PER_MODEL,
            "aggregate_preparation_rank_calls": MAX_PREPARATION_RANK_CALLS_TOTAL,
            "source_files": SOURCE_COUNT,
            "source_file_bytes": MAX_SOURCE_BYTES,
            "case_payload_files": 2,
            "raw_payload_bytes_each": MAX_RAW_BYTES,
            "gzip_bytes_each": MAX_GZIP_BYTES,
            "aggregate_raw_payload_bytes": 2 * MAX_RAW_BYTES,
            "aggregate_gzip_bytes": 2 * MAX_GZIP_BYTES,
            "failure_fallback_raw_files": FAILURE_FALLBACK_COUNT,
            "failure_fallback_raw_bytes": MAX_RAW_BYTES,
            "index_bytes": MAX_INDEX_BYTES,
        },
        "case_admission": [
            {"iterations": 140, "logical_work_per_sweep": 180_227,
             "total_training_work": 25_231_780, "fixed_setup_and_output_work": 65_368,
             "total_admitted_work": 25_297_148},
            {"iterations": 560, "logical_work_per_sweep": 180_227,
             "total_training_work": 100_927_120, "fixed_setup_and_output_work": 65_368,
             "total_admitted_work": 100_992_488},
        ],
        "prerequisite": {
            "source_revision": publication.SOURCE_REVISION,
            "raw_index_sha256": publication.RAW_INDEX_SHA256,
            "index_sha256": publication.INDEX_SHA256,
            "compact_tree_sha256": "5b8b6d504a35e0023c9150476ba9bb91d10615eae9ec6bb0305071745ab98152",
        },
        "model_admission": proof.admission(),
        "acceptance": {
            "admission": "Pre-admit both complete iteration requests and validate the new output location before source authentication or either solve.",
            "models_and_training": "Exactly one fresh model and at most one shared CFR+ training call per case; two cases total. No retries; stop after the first execution error.",
            "normalization": "Record the explicit per-player 304-row normalization batches and their bounded row-family counts.",
            "quality": "Retain exact NashConv and an explicit <=1/200 target result for each completed case; a miss is recorded without rerunning.",
            "artifacts": "Preserve each complete adapter report, raw rows, normalized policy and any partial observation in a lossless bounded case/reference.json.gz artifact; retain one bounded raw fallback if gzip output fails.",
            "source": "Clean identical committed HEAD/status and all 54 named dependency LF hashes before and after the batch.",
            "runtime": "Record CPython/OS metadata and wall/CPU elapsed receipts; elapsed values are not performance claims.",
            "failure": "Keep first error, then record source/index/cleanup errors as secondary; preserve available reports in the returned API with an explicit not-durable marker when both artifact paths fail.",
        },
        "scope": {
            "bounds": "Named logical work, proof/diagnostic families, preparation ranks, source and output bytes only; not all arithmetic, allocation, wall time or RSS.",
            "claims": "One finite fixed-board, fixed-stack, fixed-action-size game. No unrestricted Hold'em, convergence, speed, or memory claim follows.",
            "provenance": "Project-owned implementation and standard library; shared CFR+ recurrence remains authenticated by the separate versioned budget.",
        },
    }


def _protocol():
    _need(SPEC.stat().st_size <= MAX_SOURCE_BYTES, "Pilot protocol exceeds source bound")
    with SPEC.open("rb") as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    _need(len(raw) <= MAX_SOURCE_BYTES, "Pilot protocol exceeds source bound while reading")
    lf_digest = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    _need(SPEC_SHA256 != "PENDING_ROOT_FREEZE" and lf_digest == SPEC_SHA256,
          "Pilot protocol differs from frozen LF pin")
    spec = publication._json(raw)
    _need(proof._typed(spec) == proof._typed(expected_protocol()),
          "Pilot protocol schema/admission differs")
    return raw, spec


def _adapter():
    return importlib.import_module("scripts.flop_second_board_cfrplus")


def _preflight(spec, adapter_module=None):
    _need(proof._typed(spec) == proof._typed(expected_protocol()),
          "Full two-case pilot request differs")
    adapter_module = adapter_module or _adapter()
    _need(MAX_MODEL_BUILDS == 2 and
          MAX_MODEL_PROOFS * PROOF_PASS_RESERVATION_EACH == AGGREGATE_PROOF_PASS_RESERVATION and
          EXACT_WORLD_NODE_TERM_RESERVATION == 2 * 3 * (170 + 5940) * 33 and
          NUMERIC_WORLD_NODE_TERM_RESERVATION == 2 * 3 * 5940 * 33 and
          MAX_ROW_ACTION_SLOTS == MAX_ROW_TABLES * 20_000 * 2 and
          MAX_PREPARATION_RANK_CALLS_TOTAL == MAX_MODEL_BUILDS * MAX_PREPARATION_RANK_CALLS_PER_MODEL,
          "Named proof/diagnostic reservation arithmetic differs")
    forecasts = []
    for iterations, expected in zip(ITERATIONS, spec["case_admission"]):
        forecast = budget.admit_second_board_request(iterations)
        adapter_forecast = adapter_module.admit_request(iterations)
        _need(type(forecast) is dict and type(adapter_forecast) is dict,
              "Case admission must return dictionaries")
        for key in ("logical_work_per_sweep", "total_training_work",
                    "fixed_setup_and_output_work", "total_admitted_work"):
            _need(type(forecast.get(key)) is int and forecast[key] == expected[key] and
                  type(adapter_forecast.get(key)) is int and adapter_forecast[key] == expected[key],
                  f"Full case admission differs for {iterations} sweeps: {key}")
        _need(forecast["version"] == budget.VERSION and
              forecast["total_admitted_work"] <= budget.LOGICAL_WORK_CAP,
              "Second-board rank-free budget admission differs")
        forecasts.append(forecast)
    total = sum(item["total_admitted_work"] for item in forecasts)
    _need(total == AGGREGATE_LOGICAL_RESERVATION and total <= AGGREGATE_LOGICAL_CAP,
          "Aggregate two-case logical-work admission differs")
    _need(sum(item["requested_iterations"] for item in forecasts) == sum(ITERATIONS),
          "Full iteration request is incomplete")
    return {"cases": forecasts, "aggregate_logical_work": total,
            "aggregate_logical_work_cap": AGGREGATE_LOGICAL_CAP}


def _snapshot():
    """Extend the authenticated 49-file equivalence snapshot by five exact paths."""
    state = previous._snapshot()
    hashes = dict(state["source_lf_sha256"])
    adapter_module = _adapter()
    verifier = importlib.import_module("scripts.verify_flop_second_board_equivalence_publication")
    additions = (
        (Path(verifier.__file__), "scripts/verify_flop_second_board_equivalence_publication.py"),
        (Path(budget.__file__), "scripts/flop_second_board_cfrplus_budget.py"),
        (Path(adapter_module.__file__), "scripts/flop_second_board_cfrplus.py"),
        (Path(__file__), "scripts/benchmark_flop_second_board_cfrplus.py"),
        (SPEC, "benchmarks/flop-second-board-cfrplus-pilot-v1.json"),
    )
    for path, relative in additions:
        _need(relative not in hashes, "Source inventory contains a duplicate path")
        _need(not path.is_symlink() and path.stat().st_size <= MAX_SOURCE_BYTES,
              f"Named source exceeds bound or is symlinked: {relative}")
        with path.open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        _need(len(raw) <= MAX_SOURCE_BYTES, f"Named source exceeds read bound: {relative}")
        hashes[relative] = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    _need(state["status"] == "" and len(hashes) == SOURCE_COUNT,
          "Pilot source inventory differs or checkout is dirty")
    return {**state, "source_lf_sha256": dict(sorted(hashes.items()))}


def _write_index(directory, report):
    saved = {key: value for key, value in report.items()
             if key not in ("unserialized_reports", "index_sha256")}
    if report.get("unserialized_reports"):
        marker = {"available_in_returned_api_report": True, "durably_saved": False,
                  "case_names": [row["case"] for row in report["unserialized_reports"]],
                  "reason": "Both admitted report output paths failed; reports remain available in memory only."}
        saved["unserialized_report_retention"] = marker
        report["unserialized_report_retention"] = marker
    previous.previous._write_index(directory, saved)
    report["index_sha256"] = saved["index_sha256"]


def _write_case(directory, case_name, payload):
    case_directory = directory / case_name
    case_directory.mkdir()
    receipt = previous.previous._write_payload(case_directory, payload)
    return {**receipt, "path": case_name + "/" + receipt["path"]}


def _raw_fallback(directory, case_name, payload):
    return previous._raw_fallback(directory, case_name, payload)


@contextmanager
def _instrument(observed, adapter_module):
    """Bound proof families and the shared train entry, restoring all wrappers."""
    observed.update(model_build_attempts=0, model_proof_calls=0, exact_metric_calls=0,
                    exact_world_node_terms=0, numeric_replay_calls=0,
                    numeric_world_node_terms=0, projection_calls=0,
                    row_tables=0, row_action_slots=0, training_calls=0)

    def counted(module, name, counter, limit, *, family=None):
        original = getattr(module, name)

        def wrapper(*args, **kwargs):
            observed[counter] += 1
            _need(observed[counter] <= limit, f"Boundary allowance exceeded: {counter}")
            if family == "exact":
                worlds = args[1]
                _need(type(worlds) is tuple and len(worlds) in (170, 5940),
                      "Exact-metric world support is unadmitted")
                observed["exact_world_node_terms"] += 3 * len(worlds) * 33
                _need(observed["exact_world_node_terms"] <= EXACT_WORLD_NODE_TERM_RESERVATION,
                      "Exact world-node reservation exceeded")
            elif family == "numeric":
                observed["numeric_world_node_terms"] += 3 * 5940 * 33
                _need(observed["numeric_world_node_terms"] <= NUMERIC_WORLD_NODE_TERM_RESERVATION,
                      "Numeric world-node reservation exceeded")
            result = original(*args, **kwargs)
            if family == "rows":
                _need(type(result) in (dict, list, tuple) and len(result) <= 20_000,
                      "Observed row table exceeds per-table bound")
                observed["row_action_slots"] += 2 * len(result)
                _need(observed["row_action_slots"] <= MAX_ROW_ACTION_SLOTS,
                      "Row-action reservation exceeded")
            return result
        return patch.object(module, name, wrapper)

    with ExitStack() as stack:
        stack.enter_context(counted(proof, "build_model", "model_build_attempts", MAX_MODEL_BUILDS))
        stack.enter_context(counted(proof, "_make_model", "model_proof_calls", MAX_MODEL_PROOFS))
        stack.enter_context(counted(proof.shared, "_exact_metrics", "exact_metric_calls",
                                    MAX_EXACT_METRIC_CALLS, family="exact"))
        stack.enter_context(counted(proof.physical, "replay", "numeric_replay_calls",
                                    MAX_NUMERIC_REPLAYS, family="numeric"))
        stack.enter_context(counted(proof, "_project", "projection_calls", MAX_PROJECTION_CALLS))
        stack.enter_context(counted(proof, "_expected_rows", "row_tables", MAX_ROW_TABLES,
                                    family="rows"))
        for name in ("_class_rows",):
            if hasattr(proof, name):
                stack.enter_context(counted(proof, name, "row_tables", MAX_ROW_TABLES,
                                            family="rows"))
        cfr_plus = importlib.import_module("pokerlab.cfr_plus")
        original_train = cfr_plus.train
        original_guard = proof.shared.independent_guard
        active_guard_depth = [0]

        @contextmanager
        def tracked_guard(*args, **kwargs):
            with original_guard(*args, **kwargs) as calls:
                active_guard_depth[0] += 1
                try:
                    yield calls
                finally:
                    active_guard_depth[0] -= 1

        def counted_train(*args, **kwargs):
            _need(active_guard_depth[0] == 0,
                  "Shared CFR+ training occurred inside a forbidden-call guard")
            observed["training_calls"] += 1
            _need(observed["training_calls"] <= MAX_MODEL_BUILDS,
                  "Shared CFR+ training-call ceiling exceeded")
            return original_train(*args, **kwargs)

        stack.enter_context(patch.object(proof.shared, "independent_guard", tracked_guard))
        stack.enter_context(patch.object(cfr_plus, "train", counted_train))
        yield observed


def _time_receipt(start_wall, start_cpu):
    return {"wall_seconds": max(0.0, time.perf_counter() - start_wall),
            "process_cpu_seconds": max(0.0, time.process_time() - start_cpu)}


def _case_payload(adapter_report, observation, error=None):
    result = {"adapter_report": adapter_report, "observation": observation}
    if error is not None:
        result["harness_error"] = error
    return result


def _case_record(iterations):
    return {"iterations": iterations, "status": "not-started", "phase": "admission",
            "training_calls_before": 0, "training_calls_after": 0,
            "quality_target_met": None, "payload": None, "serialization_error": None,
            "preparation_forbidden_calls": None, "diagnostic_forbidden_calls": None}


def _record_preparation_rank_calls(report, record, progress):
    """Retain and bound the adapter's explicit preparation ranker receipt."""
    _need(type(progress) is dict, "Adapter omitted preparation progress")
    attempts = progress.get("preparation_ranker_attempts")
    calls = progress.get("preparation_rank_calls")
    _need(type(attempts) is int and type(calls) is int and calls <= attempts and
          0 <= attempts <= MAX_PREPARATION_RANK_CALLS_PER_MODEL and
          0 <= calls <= MAX_PREPARATION_RANK_CALLS_PER_MODEL,
          "Per-model preparation ranker reservation exceeded or malformed")
    prior = record.get("preparation_ranker_attempts")
    if prior is not None:
        _need(prior == attempts and record.get("preparation_rank_calls") == calls,
              "Preparation ranker receipt changed within one case")
        return
    record["preparation_ranker_attempts"] = attempts
    record["preparation_rank_calls"] = calls
    attempts_total = report["boundaries"].get("preparation_ranker_attempts", 0) + attempts
    calls_total = report["boundaries"].get("preparation_rank_calls", 0) + calls
    _need(attempts_total <= MAX_PREPARATION_RANK_CALLS_TOTAL and
          calls_total <= MAX_PREPARATION_RANK_CALLS_TOTAL,
          "Aggregate preparation ranker reservation exceeded")
    report["boundaries"]["preparation_ranker_attempts"] = attempts_total
    report["boundaries"]["preparation_rank_calls"] = calls_total


def _run_case(adapter_module, iterations, directory, report):
    record = _case_record(iterations)
    report["cases"].append(record)
    case_name = f"case-{iterations}"
    observation = {}
    record.update(status="running", phase="solve",
                  training_calls_before=report["boundaries"].get("training_calls", 0))
    wall_start, cpu_start = time.perf_counter(), time.process_time()
    adapter_report, error, error_object = None, None, None
    try:
        adapter_report = adapter_module.solve_second_board(iterations, observation=observation)
        record["phase"] = "solved"
        record["adapter_observation_phase"] = observation.get("phase")
        record["adapter_progress"] = observation.get("progress")
        record["adapter_status"] = adapter_report.get("status") if type(adapter_report) is dict else None
        if type(adapter_report) is dict:
            quality = adapter_report.get("quality_target_met")
            _need(type(quality) is bool and adapter_report.get("quality_target") == 0.005,
                  "Adapter report omitted the exact convergence target result")
            record["quality_target_met"] = quality
            _record_preparation_rank_calls(
                report, record, adapter_report.get("preparation_progress"))
            _need(record["preparation_ranker_attempts"] == 4_134 and
                  record["preparation_rank_calls"] == 4_134,
                  "Completed preparation ranker receipt differs")
            record["preparation_forbidden_calls"] = adapter_report.get("preparation_forbidden_calls")
            record["diagnostic_forbidden_calls"] = adapter_report.get("diagnostic_forbidden_calls")
        else:
            _need(False, "Adapter returned a non-dict report")
        _need(adapter_report.get("status") == "trained-policy-physically-verified",
              "Adapter case did not complete physical verification")
        _validate_guard_receipt(record["preparation_forbidden_calls"], "preparation")
        _validate_guard_receipt(record["diagnostic_forbidden_calls"], "diagnostic")
        if type(adapter_report.get("source_lf_sha256")) is not dict:
            _need(False, "Adapter report omitted its source LF hash map")
        _need(proof._typed(adapter_report["source_lf_sha256"]) ==
              proof._typed(report["source_before"]["source_lf_sha256"]),
              "Adapter source LF map differs from the authenticated batch source")
    except BaseException as exc:
        error_object = exc
        error = {"message": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
        record.update(status="error", error=error["message"], phase="solve-error")
        record["adapter_observation_phase"] = observation.get("phase")
        record["adapter_progress"] = observation.get("progress")
        prep_progress = observation.get("preparation_progress")
        if type(prep_progress) is dict:
            try:
                _record_preparation_rank_calls(report, record, prep_progress)
            except BaseException as rank_exc:
                report["errors"].append({"phase": "preparation-rank-receipt",
                                         "message": f"{type(rank_exc).__name__}: {rank_exc}"})
    finally:
        record["elapsed"] = _time_receipt(wall_start, cpu_start)
        record["training_calls_after"] = report["boundaries"].get("training_calls", 0)
    payload = _case_payload(adapter_report, observation, error)
    try:
        record["payload"] = _write_case(directory, case_name, payload)
        record["phase"] = "serialized"
    except BaseException as exc:
        record["serialization_error"] = f"{type(exc).__name__}: {exc}"
        try:
            record["fallback_payload"] = _raw_fallback(directory, case_name, payload)
            record["phase"] = "serialized-raw-fallback"
        except BaseException as fallback_exc:
            record["fallback_error"] = f"{type(fallback_exc).__name__}: {fallback_exc}"
            record["retained_partial_paths"] = [
                f"{case_name}/reference.json.gz.partial",
                f"{case_name}/physical-policy.raw.json.partial",
            ]
            report.setdefault("unserialized_reports", []).append(
                {"case": case_name, "payload": payload})
            if error is None:
                error_object = fallback_exc
                error = {"message": record["fallback_error"],
                         "traceback": traceback.format_exc()}
    if error is not None:
        record["status"] = "error"
        raise error_object
    record["status"] = "quality-pass" if record["quality_target_met"] is True else "quality-miss"
    return adapter_report


def _validate_guard_receipt(value, phase):
    from scripts.verify_flop_class_owned_fingerprint_publication import AUTHORITY_KEYS
    _need(type(value) is dict and frozenset(value) == AUTHORITY_KEYS and
          all(type(count) is int and count == 0 for count in value.values()),
          f"{phase.capitalize()} authority receipt differs")


def _validate_completion(report):
    counts = report["boundaries"]
    _need(type(counts["training_calls"]) is int and counts["training_calls"] == MAX_MODEL_BUILDS,
          "Two-case shared training-call count differs")
    _need(type(counts["model_build_attempts"]) is int and
          counts["model_build_attempts"] == MAX_MODEL_BUILDS and
          counts["model_proof_calls"] == 6 and counts["model_proof_calls"] <= MAX_MODEL_PROOFS,
          "Fresh model / proof call count differs")
    _need(counts["exact_metric_calls"] == MAX_EXACT_METRIC_CALLS and
          counts["exact_world_node_terms"] == EXACT_WORLD_NODE_TERM_RESERVATION and
          counts["numeric_replay_calls"] == MAX_NUMERIC_REPLAYS and
          counts["numeric_world_node_terms"] == NUMERIC_WORLD_NODE_TERM_RESERVATION and
          counts["projection_calls"] == MAX_PROJECTION_CALLS,
          "Completed exact/numeric/projection family counts differ")
    for key, maximum in (("exact_metric_calls", MAX_EXACT_METRIC_CALLS),
                         ("exact_world_node_terms", EXACT_WORLD_NODE_TERM_RESERVATION),
                         ("numeric_replay_calls", MAX_NUMERIC_REPLAYS),
                         ("numeric_world_node_terms", NUMERIC_WORLD_NODE_TERM_RESERVATION),
                         ("projection_calls", MAX_PROJECTION_CALLS),
                         ("row_tables", MAX_ROW_TABLES),
                         ("row_action_slots", MAX_ROW_ACTION_SLOTS)):
        _need(type(counts[key]) is int and 0 <= counts[key] <= maximum,
              f"Completed boundary count exceeds admission: {key}")
    _need([row["iterations"] for row in report["cases"]] == list(ITERATIONS) and
          all(row["status"] in ("quality-pass", "quality-miss") and
              type(row.get("preparation_forbidden_calls")) is dict and
              type(row.get("diagnostic_forbidden_calls")) is dict
              for row in report["cases"]),
          "Complete two-case inventory differs")
    for row in report["cases"]:
        _validate_guard_receipt(row["preparation_forbidden_calls"], "preparation")
        _validate_guard_receipt(row["diagnostic_forbidden_calls"], "diagnostic")
    receipts = [row.get("payload") or row.get("fallback_payload") for row in report["cases"]]
    _need(all(type(row) is dict for row in receipts) and len({row["path"] for row in receipts}) == 2 and
          sum(row["raw_bytes"] for row in receipts) <= 2 * MAX_RAW_BYTES and
          sum(row.get("gzip_bytes", 0) for row in receipts) <= 2 * MAX_GZIP_BYTES,
          "Complete adapter-report payload inventory differs")
    _need(report["boundaries"].get("preparation_ranker_attempts") ==
          sum(row.get("preparation_ranker_attempts", -1) for row in report["cases"]) and
          report["boundaries"].get("preparation_rank_calls") ==
          sum(row.get("preparation_rank_calls", -1) for row in report["cases"]) and
          report["boundaries"]["preparation_ranker_attempts"] == 8_268 and
          report["boundaries"]["preparation_rank_calls"] == 8_268 and
          0 <= report["boundaries"]["preparation_ranker_attempts"] <= MAX_PREPARATION_RANK_CALLS_TOTAL,
          "Aggregate preparation ranker receipt differs")


def run(output_dir):
    """Run the frozen pilot once, preserving complete case reports and errors."""
    report = {
        "schema_version": 1,
        "protocol_id": "fixed-flop-second-board-cfrplus-pilot-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "finished_at_utc": None,
        "status": "not-started",
        "protocol_sha256": None,
        "admission": None,
        "source_before": None,
        "source_after": None,
        "boundaries": {},
        "cases": [],
        "case_admissions": None,
        "errors": [],
        "index_sha256": None,
        "runtime": {"python": sys.version, "implementation": platform.python_implementation(),
                    "platform": platform.platform()},
        "execution_receipts": {"wall_seconds": None, "process_cpu_seconds": None,
                               "interpretation": "Execution timing receipt only; no performance claim."},
    }
    directory = None
    first_error = None
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    adapter_module = None
    try:
        raw_spec, spec = _protocol()
        report["admission"] = _preflight(spec)
        directory = previous.previous._output_directory(output_dir)
        report["protocol_sha256"] = hashlib.sha256(raw_spec.replace(b"\r\n", b"\n")).hexdigest()
        report["case_admissions"] = report["admission"]["cases"]
        report["source_before"] = _snapshot()
        report["status"] = "running"
        adapter_module = _adapter()
        _write_index(directory, report)
        with _instrument(report["boundaries"], adapter_module):
            for iterations in ITERATIONS:
                try:
                    case = _run_case(adapter_module, iterations, directory, report)
                    _write_index(directory, report)
                except BaseException as exc:
                    first_error = {"phase": "case-execution", "message": f"{type(exc).__name__}: {exc}",
                                   "traceback": traceback.format_exc()}
                    break
            if first_error is None:
                try:
                    _validate_completion(report)
                except BaseException as exc:
                    first_error = {"phase": "completion-check", "message": f"{type(exc).__name__}: {exc}",
                                   "traceback": traceback.format_exc()}
    except BaseException as exc:
        if first_error is None:
            first_error = {"phase": "preflight-or-setup", "message": f"{type(exc).__name__}: {exc}",
                           "traceback": traceback.format_exc()}
        else:
            report["errors"].append({"phase": "after-first-error", "message": f"{type(exc).__name__}: {exc}",
                                     "traceback": traceback.format_exc()})
    finally:
        report["execution_receipts"]["wall_seconds"] = max(0.0, time.perf_counter() - started_wall)
        report["execution_receipts"]["process_cpu_seconds"] = max(0.0, time.process_time() - started_cpu)
        if report["source_before"] is not None:
            try:
                report["source_after"] = _snapshot()
                _need(proof._typed(report["source_before"]) == proof._typed(report["source_after"]),
                      "Source map/status changed during pilot")
            except BaseException as exc:
                report["errors"].append({"phase": "source-finalization",
                                         "message": f"{type(exc).__name__}: {exc}"})
        if first_error is not None:
            report["errors"].insert(0, first_error)
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["status"] = "error" if report["errors"] else (
            "verified-quality-pass" if all(row.get("quality_target_met") is True for row in report["cases"])
            else "verified-quality-miss")
        if directory is not None:
            try:
                _write_index(directory, report)
            except BaseException as exc:
                report["errors"].append({"phase": "final-index-write",
                                         "message": f"{type(exc).__name__}: {exc}"})
                report.update(status="error", index_sha256=None)
    return report


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(args.output_dir)
    print(json.dumps({"status": report["status"], "errors": report["errors"],
                      "boundaries": report.get("boundaries"),
                      "index_sha256": report.get("index_sha256")}, sort_keys=True))
    return 0 if report["status"].startswith("verified-") else 1


if __name__ == "__main__":
    raise SystemExit(main())
