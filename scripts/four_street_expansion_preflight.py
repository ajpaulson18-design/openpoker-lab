"""No-training admission preflight for the v2 selected-runout expansion."""
from __future__ import annotations

import argparse
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re

from scripts import benchmark_four_street_integration as runner
from scripts import four_street_certificate as certificate
from scripts import four_street_validation as numeric


EXPECTED_SOURCE_RE = re.compile(r"^[0-9a-f]{40}$")
JSON_LIMIT = 32 * 1024 * 1024
CASE_ID = "four-street-shared-river-expansion-v2"
ADDED_RUNOUT = "5c6d7s8cKc"


def _candidate_inputs():
    base_case = runner._literal_case()
    base_request = runner._literal_request()
    case = copy.deepcopy(base_case)
    case["id"] = CASE_ID
    case["runouts"] = [*case["runouts"], ADDED_RUNOUT]
    request = replace(base_request, runouts=tuple(case["runouts"]))

    if set(case) != set(base_case) or case.get("id") != CASE_ID:
        raise AssertionError("candidate case identity or fields differ from the fixed expansion")
    if case["runouts"] != [*base_case["runouts"], ADDED_RUNOUT]:
        raise AssertionError("candidate case did not append exactly the fixed runout")
    for key, value in base_case.items():
        if key not in {"id", "runouts"} and case[key] != value:
            raise AssertionError(f"candidate case changed fixed field {key}")

    base_public = base_request.to_dict()
    candidate_public = request.to_dict()
    if set(candidate_public) != set(base_public):
        raise AssertionError("candidate request changed the public request fields")
    if candidate_public["runouts"] != [*base_public["runouts"], ADDED_RUNOUT]:
        raise AssertionError("candidate request did not append exactly the fixed runout")
    for key, value in base_public.items():
        if key != "runouts" and candidate_public[key] != value:
            raise AssertionError(f"candidate request changed fixed field {key}")
    return case, request


def _world_receipt(model):
    sign_counts = {"sb_win": 0, "tie": 0, "bb_win": 0}
    for world in model.worlds:
        sign_counts[{1: "sb_win", 0: "tie", -1: "bb_win"}[world["sign"]]] += 1
    return {
        "world_sign_counts": sign_counts,
        "pair_probabilities": model.counts["pair_probabilities"],
        "world_support": [
            {"hands": ["".join(hand) for hand in world["hands"]],
             "board": list(world["board"]), "sign": world["sign"],
             "weight": str(world["weight"])}
            for world in model.worlds
        ],
    }


def _model_counts(model):
    return {
        "worlds": len(model.worlds),
        "public_states": model.counts["public_states"],
        "decisions": model.counts["decisions"],
        "information_rows": model.counts["infos"],
        "action_slots": model.counts["slots"],
    }


def _failure(stage, exc):
    return {"stage": stage, "error_type": type(exc).__name__, "message": str(exc)}


def _base_receipt(case, request, *, schema="four-street-expansion-preflight-v1", benchmark_id="four-street-shared-river-expansion-v2", independent_schema="four-street-expansion-independent-admission-v1"):
    return {
        "schema": schema,
        "benchmark_id": benchmark_id,
        "outcome": "rejected",
        "quality_gate": None,
        "production_calls_entered": 0,
        "attempted_training": False,
        "case": case,
        "request": request.to_dict() if hasattr(request, "to_dict") else request,
        "production_admission": None,
        "independent_admission": None,
        "support_comparison": None,
        "first_rejection": None,
    }


def _prepare_expansion(*, forecast_operator=None, schema="four-street-expansion-preflight-v1", benchmark_id="four-street-shared-river-expansion-v2", independent_schema="four-street-expansion-independent-admission-v1", expected_source_identity=None, expected_budget_schedule_version=None):
    """Build and cross-check the proposed game without entering any trainer."""
    if forecast_operator is None:
        forecast_operator = certificate.forecast_exact
    try:
        case, request = _candidate_inputs()
    except Exception as exc:
        receipt = _base_receipt({}, {}, schema=schema, benchmark_id=benchmark_id, independent_schema=independent_schema)
        receipt["first_rejection"] = _failure("candidate-inputs", exc)
        return receipt

    receipt = _base_receipt(case, request, schema=schema, benchmark_id=benchmark_id, independent_schema=independent_schema)
    try:
        receipt["production_admission"] = runner._production_admission(request)
    except Exception as exc:
        receipt["first_rejection"] = _failure("production-admission", exc)
        return receipt

    try:
        model = numeric.build_model(case)
        independent = {
            "schema": independent_schema,
            "counts": _model_counts(model),
            **_world_receipt(model),
            "attempted_training": False,
        }
        receipt["independent_admission"] = independent
    except Exception as exc:
        receipt["first_rejection"] = _failure("independent-model-build", exc)
        return receipt

    try:
        forecast = forecast_operator(case)
        independent["forecast"] = forecast
        admitted = forecast.get("admitted")
        if type(admitted) is not bool:
            raise ValueError("independent exact forecast admitted field must be a bool")
        independent["admitted"] = admitted
        expected_counts = {
            "worlds": forecast["worlds"],
            "public_states": forecast["tree_nodes"],
            "decisions": forecast["tree_decisions"],
            "information_rows": forecast["information_rows"],
            "action_slots": forecast["action_slots"],
        }
        if independent["counts"] != expected_counts:
            raise ValueError("independent model counts changed between fresh preparations")
    except Exception as exc:
        receipt["first_rejection"] = _failure("exact-work-forecast", exc)
        return receipt

    try:
        receipt["support_comparison"] = runner._compare_admission_support(
            receipt["production_admission"], independent)
    except Exception as exc:
        receipt["first_rejection"] = _failure("support-comparison", exc)
        return receipt

    if expected_source_identity is not None and forecast.get("source_identity") != expected_source_identity:
        receipt["first_rejection"] = _failure("exact-work-forecast-identity", ValueError("independent forecast source identity differs from the fixed v3 source"))
        return receipt
    if (expected_budget_schedule_version is not None and forecast.get("budget_schedule_version") != expected_budget_schedule_version):
        receipt["first_rejection"] = _failure("exact-work-forecast-identity", ValueError("independent forecast budget schedule differs from the fixed v3 schedule"))
        return receipt

    if not forecast.get("admitted"):
        receipt["first_rejection"] = {
            "stage": "exact-work-admission",
            "error_type": "AdmissionRejected",
            "message": "independent exact forecast exceeds its configured work limit",
        }
        return receipt

    receipt["outcome"] = "admitted"
    return receipt


def prepare_expansion():
    """Build and cross-check the v2 game without entering any trainer."""
    return _prepare_expansion()


def _json_bytes(value):
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(data) > JSON_LIMIT:
        raise ValueError("preflight receipt exceeds the 32 MiB artifact limit")
    return data


def _write_receipt_exclusive(directory: Path, receipt):
    data = _json_bytes(receipt)
    path = directory / "receipt.json"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {"path": str(path), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def _run_preflight(expected_source_commit: str, output_directory: str | os.PathLike, *, prepare=prepare_expansion, initial_receipt=None):
    if (type(expected_source_commit) is not str or
            not EXPECTED_SOURCE_RE.fullmatch(expected_source_commit)):
        raise ValueError("expected source commit must be a 40-character lowercase Git SHA")
    directory = runner._safe_output_directory(output_directory)
    directory.mkdir(exist_ok=False)
    receipt = initial_receipt() if initial_receipt is not None else _base_receipt({}, {})
    receipt.update({"source_commit": expected_source_commit,
                    "source_before": None, "source_after": None,
                    "source_matches": None})
    try:
        receipt["source_before"] = runner._capture_source_state(expected_source_commit)
    except Exception as exc:
        receipt["first_rejection"] = _failure("source-before", exc)
    if receipt["first_rejection"] is None:
        prepared = prepare()
        receipt.update(prepared)
        receipt["source_commit"] = expected_source_commit
        try:
            receipt["source_after"] = runner._capture_source_state(expected_source_commit)
            runner._same_source_state(receipt["source_before"], receipt["source_after"])
            receipt["source_matches"] = True
        except Exception as exc:
            receipt["source_matches"] = False
            if receipt["first_rejection"] is None:
                receipt["first_rejection"] = _failure("source-after", exc)
            receipt["outcome"] = "rejected"
            receipt["quality_gate"] = None
            receipt["production_calls_entered"] = 0
            receipt["attempted_training"] = False
    try:
        saved = _write_receipt_exclusive(directory, receipt)
    except Exception as exc:
        # Preserve the original first failure if receipt serialization is also blocked.
        if receipt.get("first_rejection") is None:
            receipt["first_rejection"] = _failure("receipt-write", exc)
        raise
    receipt["saved_receipt"] = saved
    return receipt


def run_preflight(expected_source_commit: str, output_directory: str | os.PathLike):
    return _run_preflight(expected_source_commit, output_directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--output-directory", required=True)
    args = parser.parse_args(argv)
    receipt = run_preflight(args.expected_source_commit, args.output_directory)
    print(json.dumps({key: receipt[key] for key in
                      ("outcome", "first_rejection", "saved_receipt")},
                     sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
