"""Independent finite-strategy audit against the pinned exact preflop witness.

This module validates saved reference data and replays a production strategy
through the separate numeric oracle. It never trains or constructs a solver.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from fractions import Fraction
from math import isfinite
from pathlib import Path

from scripts import preflop_checkdown_validation as checkdown
from scripts import verify_preflop_sequence as exact_checker


ROOT = Path(__file__).resolve().parents[1]
REPORT_RELATIVE_PATH = "benchmarks/results/preflop-weighted-sequence-v1.json"
REPORT_PATH = ROOT / REPORT_RELATIVE_PATH
SPEC_PATH = ROOT / "benchmarks/preflop-weighted-sequence-v1.json"
REPORT_SHA256 = "7bdffdf73df5950d73f9fab54e27b364babb4e00718249a44cafdf47c62415c6"
SPEC_SHA256 = "5b4a79d0239a42c3911928b0ca5d0f53a54be228e68c62ad9a5f8a2925719fb3"
WITNESS_SHA256 = "59d294d41114756053419e0a69e4d3b043be9a900ec678a0668a0f9cf48300ed"
EXACT_VALUE = Fraction(100107990869, 130471452826)
MAX_REPORT_BYTES = 1_000_000

_FIXTURE = {
    "id": "preflop-weighted-three-pair-sequence-equilibrium",
    "sb_range": "AsAd:1,QsQd:0.5",
    "bb_range": "AsKh:0.25,KsKd:1",
    "config": {
        "small_blind": 0.5,
        "big_blind": 1.0,
        "starting_stack": [4, 3],
        "raise_sizes": [0.5, 1.0],
        "max_raises": 1,
        "include_all_in": True,
    },
}
_COUNTS = (
    {"sb_hand": "AdAs", "bb_hand": "KdKs", "wins": 1_410_336,
     "ties": 9_308, "losses": 292_660, "boards": 1_712_304},
    {"sb_hand": "QdQs", "bb_hand": "AsKh", "wins": 968_267,
     "ties": 7_226, "losses": 736_811, "boards": 1_712_304},
    {"sb_hand": "QdQs", "bb_hand": "KdKs", "wins": 292_846,
     "ties": 9_336, "losses": 1_410_122, "boards": 1_712_304},
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _read_bounded_json(path: Path):
    if path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError("Saved exact-anchor report exceeds the input limit")
    with path.open("rb") as source:
        raw = source.read(MAX_REPORT_BYTES + 1)
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError("Saved exact-anchor report exceeds the input limit")
    try:
        return json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Saved exact-anchor report is not valid JSON") from exc


def _check_counts(counts):
    if type(counts) not in (list, tuple) or len(counts) != len(_COUNTS):
        raise ValueError("Pinned physical count table shape changed")
    for actual, expected in zip(counts, _COUNTS):
        if (type(actual) is not dict or set(actual) != set(expected)
                or any(type(actual[key]) is not type(value) or actual[key] != value
                       for key, value in expected.items())):
            raise ValueError("Pinned physical count rows differ from the fixed reference")
    # Recheck arithmetic locally as well as through the verifier's loader.
    if any(sum(row[k] for k in ("wins", "ties", "losses")) != row["boards"]
           for row in counts):
        raise ValueError("Pinned physical count total is invalid")


def load_reference(report_path=None):
    """Load and independently reverify the one frozen exact reference.

    The report and witness hashes are pinned constants. Physical counts are
    loaded and fully hash/provenance-checked by the exact verifier's separate
    pinned-artifact reader, then checked against this adapter's fixed rows.
    """
    path = Path(report_path) if report_path is not None else REPORT_PATH
    report = _read_bounded_json(path)
    if type(report) is not dict or "artifact_sha256" not in report:
        raise ValueError("Malformed saved exact-anchor report")
    report_digest = report.get("artifact_sha256")
    unsigned_report = {key: value for key, value in report.items()
                       if key != "artifact_sha256"}
    if (type(report_digest) is not str or report_digest != REPORT_SHA256
            or hashlib.sha256(_canonical(unsigned_report)).hexdigest() != REPORT_SHA256):
        raise ValueError("Saved exact-anchor report checksum mismatch")

    spec = _read_bounded_json(SPEC_PATH)
    if (hashlib.sha256(_canonical(spec)).hexdigest() != SPEC_SHA256
            or report.get("spec_sha256") != SPEC_SHA256
            or report.get("specification") != spec
            or spec.get("fixture") != _FIXTURE):
        raise ValueError("Frozen exact-anchor specification mismatch")
    if (report.get("schema_version") != 1
            or report.get("benchmark_id") != "preflop-weighted-sequence-v1"
            or report.get("phase") != "formal-exact-equilibrium-witness"
            or report.get("status") != "passed"
            or report.get("source_unchanged") is not True
            or report.get("errors") != []):
        raise ValueError("Saved exact-anchor report did not pass its frozen run")

    witness = report.get("candidate_witness")
    if type(witness) is not dict or witness.get("artifact_sha256") != WITNESS_SHA256:
        raise ValueError("Saved exact witness identity mismatch")
    witness_unsigned = {key: value for key, value in witness.items()
                        if key != "artifact_sha256"}
    if hashlib.sha256(_canonical(witness_unsigned)).hexdigest() != WITNESS_SHA256:
        raise ValueError("Saved exact witness checksum mismatch")
    verification = exact_checker.verify_certificate(witness)
    if verification.get("status") != "passed" or verification.get("value_fraction") != str(EXACT_VALUE):
        raise ValueError("Independent exact-certificate verification failed")
    if (report.get("independent_verification") != verification
            or report.get("serialized_witness_verification") != verification):
        raise ValueError("Saved report verification summaries differ from fresh verification")

    counts, _provenance = exact_checker._pinned_counts()
    _check_counts(counts)
    fixture = deepcopy(_FIXTURE)
    identity = {
        "benchmark_id": "preflop-weighted-sequence-v1",
        "report_path": REPORT_RELATIVE_PATH,
        "report_sha256": REPORT_SHA256,
        "spec_sha256": SPEC_SHA256,
        "witness_sha256": WITNESS_SHA256,
    }
    return {
        "fixture": fixture,
        "counts": [dict(row) for row in counts],
        "exact_value_fraction": [EXACT_VALUE.numerator, EXACT_VALUE.denominator],
        "identity": identity,
        "verification": verification,
    }


def _validated_reference(reference):
    expected_keys = {"fixture", "counts", "exact_value_fraction", "identity", "verification"}
    if type(reference) is not dict or set(reference) != expected_keys:
        raise ValueError("Malformed exact-anchor reference")
    def same_types(left, right):
        if type(left) is not type(right):
            return False
        if type(left) is dict:
            return (left.keys() == right.keys()
                    and all(same_types(left[key], right[key]) for key in right))
        if type(left) is list:
            return len(left) == len(right) and all(same_types(a, b) for a, b in zip(left, right))
        return left == right

    if not same_types(reference["fixture"], _FIXTURE):
        raise ValueError("Exact-anchor fixture was changed")
    _check_counts(reference["counts"])
    if (type(reference["exact_value_fraction"]) is not list
            or reference["exact_value_fraction"] != [EXACT_VALUE.numerator, EXACT_VALUE.denominator]):
        raise ValueError("Exact-anchor value was changed")
    # Re-load and reverify the tracked report, then compare every field using
    # canonical JSON bytes so bool/int and nested type substitutions cannot
    # pass through Python's permissive equality rules.
    trusted = load_reference()
    try:
        matches = _canonical(reference) == _canonical(trusted)
    except (TypeError, ValueError):
        matches = False
    if not matches:
        raise ValueError("Exact-anchor reference was changed or is not authenticated")
    return trusted


def _fraction(pair, field):
    if (type(pair) is not list or len(pair) != 2
            or any(type(value) is not int for value in pair) or pair[1] <= 0):
        raise ValueError(f"Invalid exact replay fraction: {field}")
    return Fraction(pair[0], pair[1])


def _decimal_fraction(value, field):
    if type(value) not in (int, float) or value < 0:
        raise ValueError(f"Invalid {field}")
    try:
        if not isfinite(float(value)):
            raise ValueError(f"Invalid {field}")
    except OverflowError as exc:
        raise ValueError(f"Invalid {field}") from exc
    # Interpret the user's decimal spelling (0.005 -> 1/200), rather than the
    # incidental binary approximation of the Python float.
    return Fraction(str(value))


def assess(result, reference, *, tolerance=1e-10, target_nash_conv=0.005):
    """Replay one finite-iteration result and compare its exact rational bounds.

    The quality flag is solely the exact NashConv threshold. Structural replay,
    exact-anchor containment, and the profile-error/NashConv bound are required
    invariants and raise ``ValueError`` if violated.
    """
    ref = _validated_reference(reference)
    if type(tolerance) not in (int, float) or tolerance < 0:
        raise ValueError("Invalid replay tolerance")
    try:
        if not isfinite(float(tolerance)):
            raise ValueError("Invalid replay tolerance")
    except OverflowError as exc:
        raise ValueError("Invalid replay tolerance") from exc
    target = _decimal_fraction(target_nash_conv, "target NashConv")

    replay = checkdown.replay(
        result,
        ref["fixture"]["sb_range"],
        ref["fixture"]["bb_range"],
        ref["fixture"]["config"],
        ref["counts"],
        tolerance=tolerance,
    )
    exact = replay.get("exact_fraction_replay")
    if type(exact) is not dict:
        raise ValueError("Independent replay omitted exact rational metrics")
    value = _fraction(exact.get("value_sb"), "value_sb")
    sb_br = _fraction(exact.get("sb_best_response_value"), "sb_best_response_value")
    bb_br = _fraction(exact.get("bb_best_response_value"), "bb_best_response_value")
    sb_gain = _fraction(exact.get("sb_best_response_gain"), "sb_best_response_gain")
    bb_gain = _fraction(exact.get("bb_best_response_gain"), "bb_best_response_gain")
    nash_conv = _fraction(exact.get("nash_conv"), "nash_conv")
    exploitability = _fraction(exact.get("exploitability"), "exploitability")
    anchor = Fraction(*ref["exact_value_fraction"])
    lower = -bb_br  # convert BB's own-utility BR into SB net-transfer units
    upper = sb_br
    if (sb_gain < 0 or bb_gain < 0 or sb_br - value != sb_gain
            or bb_br + value != bb_gain or sb_gain + bb_gain != nash_conv):
        raise ValueError("Independent replay returned inconsistent best-response gains")
    if not lower <= anchor <= upper:
        raise ValueError("Exact equilibrium value is outside the policy's best-response bracket")
    profile_error = abs(value - anchor)
    if profile_error > nash_conv:
        raise ValueError("Profile-value error exceeds exact NashConv")
    if nash_conv < 0 or exploitability != nash_conv / 2:
        raise ValueError("Independent replay returned inconsistent NashConv/exploitability")

    return {
        "status": "passed",
        "quality_pass": nash_conv <= target,
        "target_nash_conv_fraction": [target.numerator, target.denominator],
        "exact_replay": replay,
        "profile_value_fraction": [value.numerator, value.denominator],
        "profile_value_error_fraction": [profile_error.numerator, profile_error.denominator],
        "sb_best_response_fraction": [sb_br.numerator, sb_br.denominator],
        "bb_best_response_fraction": [bb_br.numerator, bb_br.denominator],
        "sb_best_response_gain_fraction": [sb_gain.numerator, sb_gain.denominator],
        "bb_best_response_gain_fraction": [bb_gain.numerator, bb_gain.denominator],
        "lower_bound_sb_fraction": [lower.numerator, lower.denominator],
        "upper_bound_sb_fraction": [upper.numerator, upper.denominator],
        "exact_anchor_fraction": [anchor.numerator, anchor.denominator],
        "exact_anchor_contained": True,
        "profile_error_within_nash_conv": True,
        "nash_conv_fraction": [nash_conv.numerator, nash_conv.denominator],
        "exploitability_fraction": [exploitability.numerator, exploitability.denominator],
    }
