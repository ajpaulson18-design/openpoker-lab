"""Research-only pure argmax control for the fixed raised-turn witness inputs."""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
import math

from scripts.full_physical_exact_oracle import audit_policy


IDENTITY_SCHEMA = "full-deck-raised-turn-clean-witness-v1"
MAX_SOURCE_BYTES = 2_000_000
ACCEPTED_INPUT_SHA256 = {
    "materialized": "879263a910ae3a06eca2b4a95aa02aa61d1e40cd572f5ff4875ebe03ce7a9514",
    "matrix-free": "0bd8ba79cf3924894bab552c904e1bfb858003c97d83a47259028cd72b9e76ff",
}
METRICS = (
    "value_oop", "value_ip", "oop_best_response_value", "ip_best_response_value",
    "oop_best_response_gain", "ip_best_response_gain", "nash_conv", "exploitability",
)
ROOT_METADATA = (
    "board", "runouts", "runout_mode", "reachable_runouts", "strategy",
    "info_sets", "compatible_world_count", "worlds", "compatible_pairs",
    "deals", "config", "river_config", "turn_config", "street_configs",
    "pot", "effective_stack", "strategy_schema",
)
OPTIONAL_ROOT_METADATA = {"compatible_world_count", "worlds", "compatible_pairs", "deals"}


def _first_argmax_index(probabilities):
    if not probabilities:
        raise ValueError("argmax requires at least one legal action")
    return max(range(len(probabilities)), key=probabilities.__getitem__)


def derive_argmax_control(source, source_bytes, *, expected_backend, model):
    """Derive a pinned first-action-tie-break control and independently replay it."""
    if expected_backend not in ACCEPTED_INPUT_SHA256:
        raise ValueError("unknown accepted witness backend")
    if (not isinstance(source_bytes, bytes) or not source_bytes or
            len(source_bytes) > MAX_SOURCE_BYTES):
        raise ValueError("source bytes are missing or exceed the 2 MB limit")
    source_sha256 = sha256(source_bytes).hexdigest()
    if source_sha256 != ACCEPTED_INPUT_SHA256[expected_backend]:
        raise ValueError("source bytes do not match the accepted backend pin")
    if type(source) is not dict:
        raise ValueError("source policy must be a JSON object")
    try:
        decoded = json.loads(source_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("source bytes are not valid JSON") from exc
    if decoded != source:
        raise ValueError("source mapping does not match the supplied source bytes")
    source_provenance = source.get("derived_provenance")
    if (not isinstance(source_provenance, dict) or
            source_provenance.get("schema") != IDENTITY_SCHEMA or
            source_provenance.get("backend") != expected_backend or
            source.get("research_profile") != "clean-witness"):
        raise ValueError("source is not the expected saved clean witness")
    rows = source.get("strategy")
    if type(rows) is not list or len(rows) != 2404:
        raise ValueError("source must contain all 2,404 strategy rows")
    derived = {key: deepcopy(source[key]) for key in ROOT_METADATA if key in source}
    if set(ROOT_METADATA) - OPTIONAL_ROOT_METADATA - set(derived):
        raise ValueError("source is missing required fixed-game metadata")

    changed_actions = 0
    for row in derived["strategy"]:
        actions = row.get("actions")
        if type(actions) is not list or not actions:
            raise ValueError("every row must contain legal actions")
        probabilities = []
        for action in actions:
            p = action.get("probability")
            if type(p) is not float or not math.isfinite(p) or not 0 <= p <= 1:
                raise ValueError("action probabilities must be finite binary64 values")
            probabilities.append(p)
        selected = _first_argmax_index(probabilities)
        for index, action in enumerate(actions):
            probability = float(index == selected)
            changed_actions += probability != action["probability"]
            action["probability"] = probability

    derived.update({
        "solver_version": "research-raised-turn-argmax-control-v1",
        "source_solver_version": source.get("solver_version"),
        "method": "Deterministic first-action argmax control of a pinned clean witness",
        "scope": "Research negative control for the fixed full-deck raised turn game",
        "diagnostic_provenance": (
            "Research-only pure argmax control; all eight numeric metrics are recomputed "
            "by full_physical_exact_oracle.audit_policy; not an equilibrium witness."
        ),
        "training_calls": 0,
    })
    result = audit_policy(derived, model)
    exact_metrics = result["metrics"]
    if set(exact_metrics) != set(METRICS):
        raise ValueError("independent audit did not return all eight metrics")
    for key in METRICS:
        value = exact_metrics[key]
        if not isinstance(value, Fraction):
            raise ValueError("independent audit metrics must be exact Fractions")
        derived[key] = float(value)
    derived["derived_provenance"] = {
        "schema": "full-deck-raised-turn-argmax-control-v1",
        "source_backend": expected_backend,
        "source_policy_sha256": source_sha256,
        "source_clean_witness_solver_version": source.get("solver_version"),
        "exact_zero_required": False,
        "tie_break": "first action in original legal-action order",
        "training_calls": 0,
        "metrics_recomputed_by": "full_physical_exact_oracle.audit_policy",
        "changed_action_probabilities": changed_actions,
        "scope": "research negative control; fixed full-deck raised turn game",
    }
    return derived, result
