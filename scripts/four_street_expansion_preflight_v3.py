"""Fixed no-training preflight for the corrected four-street certificate."""
from __future__ import annotations

import argparse
import json

from scripts import four_street_certificate_v3 as certificate
from scripts import four_street_expansion_preflight as shared


SCHEMA = "four-street-expansion-preflight-v2"
BENCHMARK_ID = "four-street-shared-river-expansion-v2"
INDEPENDENT_SCHEMA = "four-street-expansion-independent-admission-v2"
CASE_ID = shared.CASE_ID


def _forecast(case):
    return certificate.forecast_exact(case)


def _base_receipt(case, request):
    receipt = shared._base_receipt(
        case, request, schema=SCHEMA, benchmark_id=BENCHMARK_ID,
        independent_schema=INDEPENDENT_SCHEMA)
    receipt["validator_entrypoint"] = "scripts.four_street_certificate_v3.forecast_exact"
    receipt["source_identity"] = certificate.SOURCE_IDENTITY
    receipt["budget_schedule_version"] = certificate.BUDGET_SCHEDULE_VERSION
    receipt["preparation_accounting"] = None
    return receipt


def prepare_expansion():
    """Prepare the single fixed candidate through the v3 exact forecaster."""
    receipt = shared._prepare_expansion(
        forecast_operator=_forecast, schema=SCHEMA, benchmark_id=BENCHMARK_ID,
        independent_schema=INDEPENDENT_SCHEMA,
        expected_source_identity=certificate.SOURCE_IDENTITY,
        expected_budget_schedule_version=certificate.BUDGET_SCHEDULE_VERSION)
    receipt["validator_entrypoint"] = "scripts.four_street_certificate_v3.forecast_exact"
    receipt["source_identity"] = certificate.SOURCE_IDENTITY
    receipt["budget_schedule_version"] = certificate.BUDGET_SCHEDULE_VERSION
    forecast = ((receipt.get("independent_admission") or {}).get("forecast"))
    if forecast is not None:
        receipt["preparation_accounting"] = {
            "production_preparation": {
                "counts": (receipt.get("production_admission") or {}).get("counts"),
                "preparation_is_separate_from_forecaster_census": True,
            },
            "independent_model_build_paths": [
                "explicit numeric.build_model support and count build",
                "fresh v3 exact forecaster graph and census build",
            ],
            "forecaster_preparation_receipts": forecast.get("preparation_receipts"),
            "forecaster_preparation_cap_is_not_whole_preflight_cap": True,
        }
    return receipt


def run_preflight(expected_source_commit: str, output_directory):
    """Capture clean source, run the fixed no-training preflight, save receipt."""
    return shared._run_preflight(
        expected_source_commit, output_directory, prepare=prepare_expansion,
        initial_receipt=lambda: _base_receipt({}, {}))


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
