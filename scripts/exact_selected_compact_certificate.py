"""Bounded independent verification for compact exact-product policy output.

The production result has no pair table. This verifier uses the unchanged small
physical oracle and its limits to reconstruct verification-only metadata. It is
not a scalable/full-range certificate and never calls the production kernel.
"""
from fractions import Fraction
from math import isfinite

from scripts import four_street_validation as physical
from scripts import four_street_certificate_v3 as exact
from scripts import four_street_certificate as shared

MAX_COMPACT_RANGE_ROWS = physical.MAX_HANDS_PER_PLAYER


def evaluate_exact(case, payload):
    if type(payload) is not dict or payload.get("pair_diagnostics") != "compact-exact-product-inputs-v1":
        raise ValueError("A compact exact-product policy result is required")
    if ("private_pair_probabilities" in payload or "compatible_private_pairs" in payload or
            payload.get("chance_contract") != "exact-product-selected-v1" or
            payload.get("conversion_contract") != "exact-product-vectors-binary64-v1"):
        raise ValueError("Compact policy has incompatible chance/diagnostic metadata")
    if (len(payload) > 128 or type(payload.get("strategy")) is not list or
            len(payload["strategy"]) > physical.MAX_ROWS):
        raise ValueError("Compact payload exceeds unchanged exact policy-shape cap")
    shared._safe_json_value(payload, budget=[0])
    compact_hash = shared._canonical_hash(payload)
    # Snapshot/validate the complete case with the old exact oracle's caps before
    # constructing any physical model. Do not import production mass/rank code.
    safe = shared._snapshot_case(case)
    parsed = physical._case_inputs(safe)
    expected_ranges = parsed[-1]
    expected_selected = [list(board) for board in parsed[-2]]
    if payload.get("selected_runouts") != expected_selected:
        raise ValueError("Compact selected runouts differ from independent requested case")
    snapshot = payload.get("chance_input_snapshot")
    if type(snapshot) is not dict or set(snapshot) != {"contract", "ranges"} or snapshot["contract"] != "exact-product-selected-v1":
        raise ValueError("Malformed compact input snapshot")
    ranges = snapshot["ranges"]
    if type(ranges) is not list or len(ranges) != 2:
        raise ValueError("Compact ranges must contain exactly two bounded sides")
    for side, expected in zip(ranges, expected_ranges):
        if type(side) is not list or not 0 < len(side) <= MAX_COMPACT_RANGE_ROWS:
            raise ValueError("Compact range exceeds unchanged physical oracle hand cap")
        observed = {}
        for row in side:
            if type(row) is not dict or set(row) != {"hand", "weight_hex"}:
                raise ValueError("Malformed compact hand/weight row")
            hand, token = row["hand"], row["weight_hex"]
            if type(hand) is not str or len(hand) != 4 or hand in observed or type(token) is not str or len(token) > 64:
                raise ValueError("Duplicate or invalid compact hand/weight")
            try:
                value = float.fromhex(token)
            except (ValueError, OverflowError) as exc:
                raise ValueError("Invalid compact binary64 weight") from exc
            if not isfinite(value) or value <= 0 or value.hex() != token:
                raise ValueError("Compact weight must be canonical positive finite binary64")
            observed[hand] = value
        exact_expected = {"".join(hand): float(weight) for hand, weight in expected.items()}
        if observed != exact_expected:
            raise ValueError("Compact input weights/holdings differ from independent requested case")
    model = physical.build_model(safe)
    expanded = dict(payload)
    # Metadata is supplied only to the bounded verifier, derived from the
    # independent physical input model; it is never returned as solver output.
    expanded["compatible_private_pairs"] = model.counts["compatible_pairs"]
    expanded["private_pair_probabilities"] = [
        {"sb_hand": row["sb_hand"], "bb_hand": row["bb_hand"],
         "probability": float(Fraction(row["fraction"]))}
        for row in model.counts["pair_probabilities"]]
    result = exact.evaluate_exact(safe, expanded)
    return {"contract": "compact-exact-product-certificate-v1", "exact_certificate": result,
            "verification_only_reconstructed_pairs": len(expanded["private_pair_probabilities"]),
            "production_pair_rows": 0, "training_calls": 0, "native_calls": 0,
            "physical_model_builds": 3,
            "compact_input_canonical_sha256": compact_hash,
            "verification_expansion_canonical_sha256": result["input_policy_canonical_sha256"],
            "preparation_scope": "Wrapper physical model, exact evaluator model and exact evaluator floating-crosscheck model each retain the old independent oracle caps; repeated preparation is explicitly disclosed.",
            "scope": "Verification-only capped physical support reconstruction; old oracle limits unchanged. This does not certify larger/full-deck games or remove the verifier's world representation."}
