"""Shared, serializable contracts for human-aware strategy components.

The contracts deliberately keep observed/modelled opponent data, baseline
strategy, exploitative strategy, explanation facts, and presentation separate.
They contain no persistence, solver, network, or personality behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
import hashlib
import json
import math
from typing import Any, Mapping, Protocol, runtime_checkable


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string.")


def _require_probability(value: float, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number between 0 and 1.")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{label} must be between 0 and 1.")


def _json_value(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


class SerializableContract:
    """Mixin for stable JSON-ready representations without persistence coupling."""

    def to_dict(self) -> dict[str, Any]:
        return _json_value(self)


@dataclass(frozen=True, slots=True)
class TendencyContext(SerializableContract):
    """The observable situation to which a tendency estimate applies."""

    street: str | None = None
    position: str | None = None
    action_context: str | None = None
    qualifiers: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for label, value in (("street", self.street), ("position", self.position),
                             ("action_context", self.action_context)):
            if value is not None:
                _require_text(value, label)
        if any(not isinstance(pair, tuple) or len(pair) != 2
               or not all(isinstance(item, str) and item for item in pair)
               for pair in self.qualifiers):
            raise ValueError("Context qualifiers must be non-empty string pairs.")


@dataclass(frozen=True, slots=True)
class BetaPrior(SerializableContract):
    """Explicit prior inputs used by the current Beta-Bernoulli model."""

    mean: float
    strength: float
    source: str

    def __post_init__(self) -> None:
        _require_probability(self.mean, "Prior mean")
        if isinstance(self.strength, bool) or not isinstance(self.strength, (int, float)):
            raise ValueError("Prior strength must be a positive number.")
        if not math.isfinite(self.strength) or self.strength <= 0:
            raise ValueError("Prior strength must be a positive number.")
        _require_text(self.source, "Prior source")


@dataclass(frozen=True, slots=True)
class Uncertainty(SerializableContract):
    """A bounded interval and its stated interpretation."""

    lower: float
    upper: float
    level: float
    method: str
    confidence: str

    def __post_init__(self) -> None:
        _require_probability(self.lower, "Uncertainty lower bound")
        _require_probability(self.upper, "Uncertainty upper bound")
        _require_probability(self.level, "Uncertainty level")
        if self.lower > self.upper:
            raise ValueError("Uncertainty lower bound cannot exceed upper bound.")
        _require_text(self.method, "Uncertainty method")
        _require_text(self.confidence, "Confidence label")


@dataclass(frozen=True, slots=True)
class OpponentTendencyEstimate(SerializableContract):
    """One opportunity-defined estimate, never a global player score."""

    tendency_id: str
    context: TendencyContext
    successes: int
    opportunities: int
    prior: BetaPrior
    posterior_mean: float
    uncertainty: Uncertainty
    sample_size: int

    def __post_init__(self) -> None:
        _require_text(self.tendency_id, "Tendency identifier")
        if type(self.successes) is not int or type(self.opportunities) is not int:
            raise ValueError("Successes and opportunities must be integers.")
        if not 0 <= self.successes <= self.opportunities:
            raise ValueError("Successes must be between zero and opportunities.")
        if type(self.sample_size) is not int or self.sample_size != self.opportunities:
            raise ValueError("Sample size must equal the number of observed opportunities.")
        _require_probability(self.posterior_mean, "Posterior mean")


@dataclass(frozen=True, slots=True)
class OpponentModelSnapshot(SerializableContract):
    """Immutable solver input derived only from observations, priors, and math."""

    opponent_id: str
    prior_archetype: str
    model_version: str
    tendencies: tuple[OpponentTendencyEstimate, ...]

    def __post_init__(self) -> None:
        _require_text(self.opponent_id, "Opponent identifier")
        _require_text(self.prior_archetype, "Prior archetype")
        _require_text(self.model_version, "Opponent model version")
        if not self.tendencies:
            raise ValueError("An opponent snapshot must contain at least one tendency.")
        identifiers = [(item.tendency_id, item.context) for item in self.tendencies]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("A snapshot cannot contain duplicate tendency contexts.")

    def tendency(self, tendency_id: str) -> OpponentTendencyEstimate:
        matches = [item for item in self.tendencies if item.tendency_id == tendency_id]
        if len(matches) != 1:
            raise KeyError(f"Expected one tendency named {tendency_id!r}; found {len(matches)}.")
        return matches[0]


@runtime_checkable
class OpponentModelProvider(Protocol):
    """Boundary used by solvers instead of querying persistence themselves."""

    def opponent_snapshot(self, opponent_id: str, street: str = "all") -> OpponentModelSnapshot:
        ...


@dataclass(frozen=True, slots=True)
class ActionFrequency(SerializableContract):
    action: str
    frequency: float

    def __post_init__(self) -> None:
        _require_text(self.action, "Action")
        _require_probability(self.frequency, "Action frequency")


@dataclass(frozen=True, slots=True)
class ActionValue(SerializableContract):
    action: str
    value: float

    def __post_init__(self) -> None:
        _require_text(self.action, "Action")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)) or not math.isfinite(self.value):
            raise ValueError("Action value must be a finite number.")


@dataclass(frozen=True, slots=True)
class OpponentAssumption(SerializableContract):
    """A traceable model input consumed by an exploitative calculation."""

    tendency_id: str
    context: TendencyContext
    value: float
    evidence_count: int
    uncertainty: Uncertainty | None = None

    def __post_init__(self) -> None:
        _require_text(self.tendency_id, "Tendency identifier")
        _require_probability(self.value, "Assumption value")
        if type(self.evidence_count) is not int or self.evidence_count < 0:
            raise ValueError("Evidence count must be a non-negative integer.")


def _validate_strategy(items: tuple[ActionFrequency, ...], legal: tuple[str, ...], label: str) -> None:
    actions = tuple(item.action for item in items)
    if len(actions) != len(set(actions)) or set(actions) != set(legal):
        raise ValueError(f"{label} must contain every legal action exactly once.")
    if not math.isclose(sum(item.frequency for item in items), 1.0, abs_tol=1e-9):
        raise ValueError(f"{label} frequencies must sum to 1.")


@dataclass(frozen=True, slots=True)
class StrategyAnalysisResult(SerializableContract):
    """Calculation result with reference and exploitative policies kept distinct."""

    analysis_id: str
    legal_actions: tuple[str, ...]
    baseline_strategy: tuple[ActionFrequency, ...]
    exploitative_strategy: tuple[ActionFrequency, ...]
    action_evs: tuple[ActionValue, ...]
    ev_differences: tuple[ActionValue, ...]
    opponent_assumptions: tuple[OpponentAssumption, ...]
    confidence: str
    uncertainty: Uncertainty | None
    solver_version: str
    model_version: str
    limitations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.analysis_id, "Analysis identifier")
        if not self.legal_actions or any(not isinstance(action, str) or not action for action in self.legal_actions):
            raise ValueError("Legal actions must contain non-empty strings.")
        if len(self.legal_actions) != len(set(self.legal_actions)):
            raise ValueError("Legal actions must be unique.")
        _validate_strategy(self.baseline_strategy, self.legal_actions, "Baseline strategy")
        _validate_strategy(self.exploitative_strategy, self.legal_actions, "Exploitative strategy")
        for label, values in (("Action EVs", self.action_evs), ("EV differences", self.ev_differences)):
            actions = tuple(item.action for item in values)
            if len(actions) != len(set(actions)) or set(actions) != set(self.legal_actions):
                raise ValueError(f"{label} must contain every legal action exactly once.")
        for label, value in (("Confidence", self.confidence), ("Solver version", self.solver_version),
                             ("Model version", self.model_version)):
            _require_text(value, label)


@dataclass(frozen=True, slots=True)
class ExploitativeAdjustment(SerializableContract):
    action: str
    baseline_frequency: float
    exploitative_frequency: float

    def __post_init__(self) -> None:
        _require_text(self.action, "Adjustment action")
        _require_probability(self.baseline_frequency, "Baseline frequency")
        _require_probability(self.exploitative_frequency, "Exploitative frequency")


@dataclass(frozen=True, slots=True)
class MathematicalFact(SerializableContract):
    label: str
    value: float | str
    unit: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.label, "Mathematical fact label")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("Mathematical fact values must be finite.")


@dataclass(frozen=True, slots=True)
class ExplanationPayload(SerializableContract):
    """Facts for deterministic or optional AI explanation, not presentation style."""

    analysis_id: str
    recommended_action: str
    baseline_strategy: tuple[ActionFrequency, ...]
    exploitative_adjustment: ExploitativeAdjustment | None
    primary_reason: str
    relevant_tendency: OpponentAssumption | None
    evidence_count: int
    uncertainty: Uncertainty | None
    ev_difference: float | None
    mathematical_facts: tuple[MathematicalFact, ...] = ()
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.analysis_id, "Analysis identifier")
        _require_text(self.recommended_action, "Recommended action")
        _require_text(self.primary_reason, "Primary reason")
        baseline_actions = tuple(item.action for item in self.baseline_strategy)
        if not baseline_actions or len(baseline_actions) != len(set(baseline_actions)):
            raise ValueError("Baseline explanation strategy must contain unique actions.")
        if not math.isclose(sum(item.frequency for item in self.baseline_strategy), 1.0, abs_tol=1e-9):
            raise ValueError("Baseline explanation strategy frequencies must sum to 1.")
        if self.recommended_action not in baseline_actions:
            raise ValueError("Recommended action must appear in the baseline strategy action set.")
        if self.exploitative_adjustment and self.exploitative_adjustment.action not in baseline_actions:
            raise ValueError("Exploitative adjustment must refer to a legal strategy action.")
        if type(self.evidence_count) is not int or self.evidence_count < 0:
            raise ValueError("Evidence count must be a non-negative integer.")
        if self.relevant_tendency and self.evidence_count != self.relevant_tendency.evidence_count:
            raise ValueError("Evidence count must match the relevant tendency assumption.")
        if self.ev_difference is not None and (isinstance(self.ev_difference, bool)
                                                or not isinstance(self.ev_difference, (int, float))
                                                or not math.isfinite(self.ev_difference)):
            raise ValueError("EV difference must be finite when supplied.")


def stable_analysis_id(inputs: Mapping[str, Any], namespace: str = "strategy-v1") -> str:
    """Return a repeatable identifier for the same normalized analysis inputs."""

    _require_text(namespace, "Analysis namespace")
    encoded = json.dumps({"namespace": namespace, "inputs": inputs}, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode()
    return "analysis-" + hashlib.sha256(encoded).hexdigest()[:20]
