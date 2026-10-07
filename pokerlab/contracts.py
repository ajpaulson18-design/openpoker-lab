"""Shared, serializable contracts for human-aware strategy components.

The contracts deliberately keep observed/modelled opponent data, baseline
strategy, exploitative strategy, explanation facts, and presentation separate.
They contain no persistence, solver, network, or personality behaviour.
"""
from __future__ import annotations

from dataclasses import MISSING, dataclass, fields, is_dataclass
import hashlib
import json
import math
import re
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
class ObservationEvidence(SerializableContract):
    """One persisted evidence item contributing to a tendency estimate."""

    observation_id: str
    successes: int
    opportunities: int
    context: TendencyContext
    note: str = ""
    created_at: str | None = None
    legacy: bool = False

    def __post_init__(self) -> None:
        _require_text(self.observation_id, "Observation identifier")
        if type(self.successes) is not int or type(self.opportunities) is not int:
            raise ValueError("Successes and opportunities must be integers.")
        if self.opportunities <= 0 or not 0 <= self.successes <= self.opportunities:
            raise ValueError("Evidence counts must satisfy 0 <= successes <= opportunities.")
        if not isinstance(self.note, str):
            raise ValueError("Observation note must be a string.")
        if self.created_at is not None:
            _require_text(self.created_at, "Observation creation time")
        if type(self.legacy) is not bool:
            raise ValueError("Legacy evidence marker must be boolean.")


@dataclass(frozen=True, slots=True)
class TendencyEvidence(SerializableContract):
    """An estimate together with the immutable observations behind it."""

    estimate: OpponentTendencyEstimate
    observations: tuple[ObservationEvidence, ...]

    def __post_init__(self) -> None:
        successes = sum(item.successes for item in self.observations)
        opportunities = sum(item.opportunities for item in self.observations)
        if (successes, opportunities) != (self.estimate.successes,
                                           self.estimate.opportunities):
            raise ValueError("Evidence totals must match the tendency estimate.")


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
    node: str | None = None
    action: str | None = None
    baseline_frequency: float | None = None
    posterior_mean: float | None = None
    confidence_weight: float | None = None
    reason: str | None = None
    affected_hands: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.tendency_id, "Tendency identifier")
        _require_probability(self.value, "Assumption value")
        if type(self.evidence_count) is not int or self.evidence_count < 0:
            raise ValueError("Evidence count must be a non-negative integer.")
        for label, probability in (("Baseline frequency", self.baseline_frequency),
                                   ("Posterior mean", self.posterior_mean),
                                   ("Confidence weight", self.confidence_weight)):
            if probability is not None:
                _require_probability(probability, label)
        for label, text in (("Node", self.node), ("Action", self.action),
                            ("Assumption reason", self.reason)):
            if text is not None:
                _require_text(text, label)
        if any(not isinstance(hand, str) or not hand for hand in self.affected_hands):
            raise ValueError("Affected hands must be non-empty strings.")


@dataclass(frozen=True, slots=True)
class BestResponseInfo(SerializableContract):
    """Best-response facts for the reported hero decision."""

    action: str
    value: float
    policy_value: float
    gap: float
    unrestricted_profile_gap: float | None = None

    def __post_init__(self) -> None:
        _require_text(self.action, "Best-response action")
        for label, value in (("Best-response value", self.value),
                             ("Policy value", self.policy_value),
                             ("Best-response gap", self.gap),
                             ("Unrestricted profile gap", self.unrestricted_profile_gap)):
            if value is not None and (isinstance(value, bool)
                                      or not isinstance(value, (int, float))
                                      or not math.isfinite(value)):
                raise ValueError(f"{label} must be finite.")
        if self.gap < -1e-9:
            raise ValueError("Best-response gap cannot be negative.")


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
    best_response: BestResponseInfo | None = None

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
        if self.best_response and self.best_response.action not in self.legal_actions:
            raise ValueError("Best-response action must be legal for this analysis.")


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


# Coaching evidence is a versioned, privacy-conscious projection over existing
# analysis. It intentionally knows nothing about stores, solvers or providers.
_COACH_ERROR_CODES = {
    "unsupported_producer_version", "invalid_analysis",
    "unsupported_schema_version", "invalid_contract", "fingerprint_mismatch",
}


class CoachAnalysisError(ValueError):
    """Stable, safe error surface for the coaching-analysis boundary."""

    def __init__(self, code: str, message: str):
        if code not in _COACH_ERROR_CODES:
            raise ValueError("Unknown coaching analysis error code.")
        self.code = code
        super().__init__(message)


def _coach_error(code: str, message: str) -> None:
    raise CoachAnalysisError(code, message)


def _coach_text(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        _coach_error("invalid_contract", f"{label} must be non-empty text.")


def _coach_number(value: Any, label: str, minimum: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _coach_error("invalid_contract", f"{label} must be a finite number.")
    if minimum is not None and value < minimum:
        _coach_error("invalid_contract", f"{label} is outside its allowed range.")


def _coach_choice(value: Any, choices: tuple[str, ...], label: str) -> None:
    if value not in choices:
        _coach_error("invalid_contract", f"Unsupported {label}.")


def _coach_tuple(value: Any, label: str) -> None:
    if not isinstance(value, tuple):
        _coach_error("invalid_contract", f"{label} must be immutable.")


@dataclass(frozen=True, slots=True)
class CoachDecisionRef(SerializableContract):
    """Application-local decision identity, separate from analysis identity."""

    hand_id: str
    decision_id: str
    state_revision: int | None

    def __post_init__(self) -> None:
        _coach_text(self.hand_id, "Hand ID")
        _coach_text(self.decision_id, "Decision ID")
        if self.state_revision is not None and (
                type(self.state_revision) is not int or self.state_revision < 0):
            _coach_error("invalid_contract", "State revision must be a non-negative integer or null.")


@dataclass(frozen=True, slots=True)
class CoachAction(SerializableContract):
    """Legal or actually evaluated action, with explicit chip-size semantics."""

    action_id: str
    name: str
    amount: float | None
    amount_semantics: str
    minimum_total: float | None = None
    maximum_total: float | None = None

    def __post_init__(self) -> None:
        _coach_text(self.action_id, "Action ID")
        _coach_choice(self.name, ("fold", "check", "call", "bet", "raise"), "action name")
        _coach_choice(self.amount_semantics, ("chips_added", "street_total"), "amount semantics")
        if self.amount is not None:
            _coach_number(self.amount, "Action amount", 0)
        if self.name in ("fold", "check") and self.amount != 0:
            _coach_error("invalid_contract", "Fold and check actions must have a zero amount.")
        if self.name != "raise" and (self.minimum_total is not None or self.maximum_total is not None):
            _coach_error("invalid_contract", "Only raise actions may have size bounds.")
        bounds = (self.minimum_total, self.maximum_total)
        if self.name == "raise":
            if (bounds[0] is None) != (bounds[1] is None):
                _coach_error("invalid_contract", "Raise bounds must both be present or both be null.")
            if bounds[0] is not None:
                _coach_number(bounds[0], "Minimum raise total", 0)
                _coach_number(bounds[1], "Maximum raise total", 0)
                if bounds[0] > bounds[1]:
                    _coach_error("invalid_contract", "Minimum raise total cannot exceed its maximum.")
                if self.amount is not None and not bounds[0] <= self.amount <= bounds[1]:
                    _coach_error("invalid_contract", "Evaluated raise amount must fit its stated bounds.")
        elif self.amount is None:
            _coach_error("invalid_contract", "Non-raise actions require an explicit amount.")


@dataclass(frozen=True, slots=True)
class CoachDecisionContext(SerializableContract):
    """Visible decision state only; absent historical data stays absent."""

    street: str
    hero_cards: tuple[str, ...]
    board: tuple[str, ...]
    pot: float
    pot_basis: str
    actor_seat: int | None
    actor_role: str | None
    button_seat: int | None
    stacks: tuple[int, ...] | None
    street_bets: tuple[int, ...] | None
    committed: tuple[int, ...] | None
    current_bet: float | None
    min_raise: float | None

    def __post_init__(self) -> None:
        _coach_choice(self.street, ("preflop", "flop", "turn", "river"), "street")
        _coach_choice(self.pot_basis, ("current_committed", "solver_initial"), "pot basis")
        if self.actor_role is not None:
            _coach_choice(self.actor_role, ("oop", "ip"), "actor role")
        for label, value in (("hero cards", self.hero_cards), ("board", self.board)):
            _coach_tuple(value, label)
        if len(self.hero_cards) != 2 or len(self.board) not in (0, 3, 4, 5):
            _coach_error("invalid_contract", "Visible cards must contain two hero cards and a 0, 3, 4, or 5-card board.")
        if any(not isinstance(card, str) or not re.fullmatch(r"[2-9TJQKA][cdhs]", card)
               for card in self.hero_cards + self.board):
            _coach_error("invalid_contract", "Visible cards must use canonical rank and suit codes.")
        if len(set(self.hero_cards + self.board)) != len(self.hero_cards) + len(self.board):
            _coach_error("invalid_contract", "Visible cards must be unique.")
        expected_street = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(self.board)]
        if self.street != expected_street:
            _coach_error("invalid_contract", "Street must match the visible board length.")
        _coach_number(self.pot, "Pot", 0)
        for label, value in (("current bet", self.current_bet), ("minimum raise", self.min_raise)):
            if value is not None:
                _coach_number(value, label, 0 if label == "current bet" else 0.000000001)
        for label, seat in (("actor seat", self.actor_seat), ("button seat", self.button_seat)):
            if seat is not None and (type(seat) is not int or seat < 0):
                _coach_error("invalid_contract", f"{label.title()} must be a non-negative integer or null.")
        arrays = (self.stacks, self.street_bets, self.committed)
        for label, values in zip(("stacks", "street bets", "contributions"), arrays):
            if values is not None:
                _coach_tuple(values, label)
                if not 2 <= len(values) <= 6 or any(type(item) is not int or item < 0 for item in values):
                    _coach_error("invalid_contract", f"{label.title()} must contain 2–6 non-negative chip amounts.")
        present = [values for values in arrays if values is not None]
        if present and any(len(values) != len(present[0]) for values in present):
            _coach_error("invalid_contract", "Seat arrays must have matching lengths.")
        seat_count = len(present[0]) if present else None
        if seat_count is not None:
            for seat in (self.actor_seat, self.button_seat):
                if seat is not None and seat >= seat_count:
                    _coach_error("invalid_contract", "Seat index exceeds the available seat arrays.")
        if self.street_bets is not None and self.committed is not None:
            if any(street > total for street, total in zip(self.street_bets, self.committed)):
                _coach_error("invalid_contract", "Street contributions cannot exceed total contributions.")
        if self.pot_basis == "current_committed" and self.committed is not None:
            if not math.isclose(self.pot, sum(self.committed), rel_tol=0, abs_tol=1e-9):
                _coach_error("invalid_contract", "Current committed pot must equal total contributions.")


@dataclass(frozen=True, slots=True)
class CoachPolicy(SerializableContract):
    """A labeled policy; a one-hot argmax is not solver mixing."""

    kind: str
    frequencies: tuple[ActionFrequency, ...]

    def __post_init__(self) -> None:
        _coach_choice(self.kind, ("illustrative_argmax", "estimate_argmax",
                                  "equilibrium_mix", "modeled_opponent_mix"), "policy kind")
        _coach_tuple(self.frequencies, "policy frequencies")
        if any(not isinstance(item, ActionFrequency) for item in self.frequencies):
            _coach_error("invalid_contract", "Policy entries must use action-frequency contracts.")
        names = [item.action for item in self.frequencies]
        if not names or len(names) != len(set(names)):
            _coach_error("invalid_contract", "Policy action IDs must be unique and non-empty.")
        if not math.isclose(sum(item.frequency for item in self.frequencies), 1,
                            rel_tol=0, abs_tol=1e-9):
            _coach_error("invalid_contract", "Policy frequencies must sum to one.")


@dataclass(frozen=True, slots=True)
class CoachActionValue(SerializableContract):
    """An action EV; null explicitly means unavailable."""

    action_id: str
    value: float | None

    def __post_init__(self) -> None:
        _coach_text(self.action_id, "Action ID")
        if self.value is not None:
            _coach_number(self.value, "Action EV")


@dataclass(frozen=True, slots=True)
class CoachAnalysisQuality(SerializableContract):
    """Independent uncertainty and solver-diagnostic dimensions."""

    confidence_label: str
    opponent_uncertainty: Uncertainty | None
    equity_standard_error: float | None
    equity_exact: bool | None
    nash_conv: float | None
    exploitability: float | None
    iterations: int | None
    gap_semantics: str | None

    def __post_init__(self) -> None:
        _coach_text(self.confidence_label, "Confidence label")
        if self.opponent_uncertainty is not None and not isinstance(self.opponent_uncertainty, Uncertainty):
            _coach_error("invalid_contract", "Opponent uncertainty must use its shared contract type.")
        for label, value in (("equity standard error", self.equity_standard_error),
                             ("NashConv", self.nash_conv),
                             ("exploitability", self.exploitability)):
            if value is not None:
                _coach_number(value, label, 0)
        if self.equity_exact is not None and type(self.equity_exact) is not bool:
            _coach_error("invalid_contract", "Exact-equity marker must be boolean or null.")
        if self.iterations is not None and (type(self.iterations) is not int or self.iterations < 0):
            _coach_error("invalid_contract", "Iterations must be a non-negative integer or null.")
        if self.gap_semantics is not None:
            _coach_text(self.gap_semantics, "Gap semantics")
        if self.nash_conv is None and self.exploitability is not None:
            _coach_error("invalid_contract", "Exploitability requires a NashConv value.")
        if self.nash_conv is not None and self.exploitability is None:
            _coach_error("invalid_contract", "NashConv requires an exploitability value.")
        if self.gap_semantics is not None and self.nash_conv is None:
            _coach_error("invalid_contract", "Gap semantics require solver gap values.")


@dataclass(frozen=True, slots=True)
class CoachProvenance(SerializableContract):
    """Safe field-level source link for one fact in the envelope."""

    path: str
    origin: str
    source_path: str

    def __post_init__(self) -> None:
        _coach_text(self.path, "Provenance JSON Pointer")
        _coach_text(self.origin, "Provenance origin")
        _coach_choice(self.origin, ("game_state", "analysis_output", "solver_output",
                                    "opponent_model", "derived_application"), "provenance origin")
        _coach_text(self.source_path, "Provenance source path")
        if not self.path.startswith("/"):
            _coach_error("invalid_contract", "Provenance destination must be a JSON Pointer.")


def _coach_nested_keys(value: Any, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        _coach_error("invalid_contract", f"{label} has missing or unknown fields.")
    return value


def _coach_pointer_resolves(value: Any, pointer: str) -> bool:
    if not pointer.startswith("/"):
        return False
    try:
        for component in pointer[1:].split("/"):
            component = component.replace("~1", "/").replace("~0", "~")
            if isinstance(value, dict):
                value = value[component]
            elif isinstance(value, list):
                if not component.isdigit():
                    return False
                value = value[int(component)]
            else:
                return False
        return True
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def _coach_context_from_dict(data: Any) -> CoachDecisionContext:
    names = {item.name for item in fields(CoachDecisionContext)}
    value = _coach_nested_keys(data, names, "Decision context")
    for name in ("hero_cards", "board", "stacks", "street_bets", "committed"):
        if value[name] is not None:
            if not isinstance(value[name], list):
                _coach_error("invalid_contract", f"Context {name} must be a JSON array or null.")
            value = dict(value)
            value[name] = tuple(value[name])
    return CoachDecisionContext(**value)


def _coach_action_from_dict(data: Any) -> CoachAction:
    return CoachAction(**_coach_nested_keys(data, {item.name for item in fields(CoachAction)},
                                            "Action"))


def _coach_frequency_from_dict(data: Any) -> ActionFrequency:
    value = _coach_nested_keys(data, {"action", "frequency"}, "Action frequency")
    try:
        return ActionFrequency(**value)
    except (TypeError, ValueError):
        _coach_error("invalid_contract", "Action frequency contains invalid values.")


def _coach_policy_from_dict(data: Any) -> CoachPolicy | None:
    if data is None:
        return None
    value = _coach_nested_keys(data, {"kind", "frequencies"}, "Policy")
    if not isinstance(value["frequencies"], list):
        _coach_error("invalid_contract", "Policy frequencies must be a JSON array.")
    return CoachPolicy(value["kind"], tuple(_coach_frequency_from_dict(item)
                                             for item in value["frequencies"]))


def _coach_assumption_from_dict(data: Any) -> OpponentAssumption:
    names = {item.name for item in fields(OpponentAssumption)}
    value = dict(_coach_nested_keys(data, names, "Opponent assumption"))
    context = value["context"]
    context = _coach_nested_keys(context, {"street", "position", "action_context", "qualifiers"},
                                 "Tendency context")
    if not isinstance(context["qualifiers"], list):
        _coach_error("invalid_contract", "Tendency qualifiers must be a JSON array.")
    try:
        value["context"] = TendencyContext(context["street"], context["position"],
                                            context["action_context"],
                                            tuple(tuple(pair) for pair in context["qualifiers"]))
    except (TypeError, ValueError):
        _coach_error("invalid_contract", "Tendency context contains invalid values.")
    uncertainty = value["uncertainty"]
    if uncertainty is not None:
        value["uncertainty"] = Uncertainty(**_coach_nested_keys(
            uncertainty, {item.name for item in fields(Uncertainty)}, "Uncertainty"))
    if not isinstance(value["affected_hands"], list):
        _coach_error("invalid_contract", "Affected hands must be a JSON array.")
    value["affected_hands"] = tuple(value["affected_hands"])
    try:
        return OpponentAssumption(**value)
    except (TypeError, ValueError):
        _coach_error("invalid_contract", "Opponent assumption contains invalid values.")


def _coach_quality_from_dict(data: Any) -> CoachAnalysisQuality:
    value = _coach_nested_keys(data, {item.name for item in fields(CoachAnalysisQuality)},
                               "Analysis quality")
    result = dict(value)
    uncertainty = value["opponent_uncertainty"]
    if uncertainty is not None:
        result["opponent_uncertainty"] = Uncertainty(**_coach_nested_keys(
            uncertainty, {item.name for item in fields(Uncertainty)}, "Uncertainty"))
    try:
        return CoachAnalysisQuality(**result)
    except (TypeError, ValueError):
        _coach_error("invalid_contract", "Analysis quality contains invalid values.")


def _coach_provenance_from_dict(data: Any) -> CoachProvenance:
    return CoachProvenance(**_coach_nested_keys(
        data, {item.name for item in fields(CoachProvenance)}, "Provenance"))


@dataclass(frozen=True, slots=True)
class CoachDecisionAnalysis(SerializableContract):
    """Versioned calculation evidence, before any explanation or AI rendering."""

    ref: CoachDecisionRef
    analysis_id: str
    evidence_id: str
    adapter_version: str
    producer_version: str
    model_version: str
    source_kind: str
    context: CoachDecisionContext
    legal_actions: tuple[CoachAction, ...]
    modeled_actions: tuple[CoachAction, ...]
    reference_policy: CoachPolicy | None
    modeled_policy: CoachPolicy | None
    action_evs: tuple[CoachActionValue, ...]
    baseline_action_evs: tuple[CoachActionValue, ...]
    recommended_action_id: str | None
    baseline_recommended_action_id: str | None
    ev_basis: str
    opponent_ranges: tuple[str, ...]
    opponent_assumptions: tuple[OpponentAssumption, ...]
    quality: CoachAnalysisQuality
    limitations: tuple[str, ...]
    warnings: tuple[str, ...]
    unavailable_fields: tuple[str, ...]
    provenance: tuple[CoachProvenance, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        try:
            if not isinstance(self.ref, CoachDecisionRef) or not isinstance(self.context, CoachDecisionContext):
                _coach_error("invalid_contract", "Decision reference and context must use their shared contract types.")
            if not isinstance(self.quality, CoachAnalysisQuality):
                _coach_error("invalid_contract", "Analysis quality must use its shared contract type.")
            for label, value in (("Analysis ID", self.analysis_id),
                                 ("Evidence ID", self.evidence_id),
                                 ("Adapter version", self.adapter_version),
                                 ("Producer version", self.producer_version),
                                 ("Model version", self.model_version)):
                _coach_text(value, label)
            _coach_choice(self.source_kind, ("practice_estimate", "restricted_equilibrium",
                                             "restricted_exploit"), "analysis source")
            _coach_choice(self.ev_basis, ("incremental_decision_chips",
                                          "half_initial_pot_utility"), "EV basis")
            if type(self.schema_version) is not int or self.schema_version != 1:
                _coach_error("unsupported_schema_version", "Only coaching analysis schema version 1 is supported.")
            tuple_fields = (self.legal_actions, self.modeled_actions, self.action_evs,
                            self.baseline_action_evs, self.opponent_ranges,
                            self.opponent_assumptions, self.limitations, self.warnings,
                            self.unavailable_fields, self.provenance)
            for name, value in zip(("legal actions", "modeled actions", "action EVs",
                                    "baseline action EVs", "opponent ranges",
                                    "opponent assumptions", "limitations", "warnings",
                                    "unavailable fields", "provenance"), tuple_fields):
                _coach_tuple(value, name)
            if (any(not isinstance(item, CoachAction) for item in (*self.legal_actions, *self.modeled_actions))
                    or any(not isinstance(item, CoachActionValue)
                           for item in (*self.action_evs, *self.baseline_action_evs))
                    or any(not isinstance(item, CoachProvenance) for item in self.provenance)):
                _coach_error("invalid_contract", "Actions, values and provenance must use their shared contract types.")
            if not self.legal_actions or not self.modeled_actions:
                _coach_error("invalid_contract", "Legal and modeled action sets must be non-empty.")
            legal_ids = [item.action_id for item in self.legal_actions]
            modeled_ids = [item.action_id for item in self.modeled_actions]
            legal_names = [item.name for item in self.legal_actions]
            modeled_names = [item.name for item in self.modeled_actions]
            if (len(legal_ids) != len(set(legal_ids)) or len(modeled_ids) != len(set(modeled_ids))
                    or len(legal_names) != len(set(legal_names))):
                _coach_error("invalid_contract", "Legal action names and action IDs must be unique.")
            for modeled in self.modeled_actions:
                matches = [item for item in self.legal_actions if item.name == modeled.name]
                if not matches:
                    _coach_error("invalid_contract", "Modeled actions must match their legal action name.")
                legal = matches[0]
                if modeled.name == "raise":
                    if (modeled.amount_semantics != "street_total" or modeled.amount is None
                            or legal.minimum_total is None or legal.maximum_total is None
                            or not legal.minimum_total <= modeled.amount <= legal.maximum_total):
                        _coach_error("invalid_contract", "Modeled raise size must be legal under the raise bounds.")
                elif (modeled.action_id != legal.action_id or modeled.amount != legal.amount
                      or modeled.amount_semantics != legal.amount_semantics):
                    _coach_error("invalid_contract", "Modeled action amount must match its legal action.")
            for label, values in (("Action EVs", self.action_evs),
                                  ("Baseline action EVs", self.baseline_action_evs)):
                if len(values) != len(modeled_ids) or {item.action_id for item in values} != set(modeled_ids):
                    _coach_error("invalid_contract", f"{label} must cover every modeled action exactly once.")
            for label, policy in (("Reference policy", self.reference_policy),
                                  ("Modeled policy", self.modeled_policy)):
                if policy is not None and (not isinstance(policy, CoachPolicy)
                                           or {item.action for item in policy.frequencies} != set(modeled_ids)):
                    _coach_error("invalid_contract", f"{label} must cover every modeled action.")
            for label, action_id in (("Recommendation", self.recommended_action_id),
                                     ("Baseline recommendation", self.baseline_recommended_action_id)):
                if action_id is not None and action_id not in modeled_ids:
                    _coach_error("invalid_contract", f"{label} must refer to a modeled action.")
            for label, values in (("Opponent ranges", self.opponent_ranges),
                                  ("Limitations", self.limitations),
                                  ("Warnings", self.warnings),
                                  ("Unavailable fields", self.unavailable_fields)):
                if any(not isinstance(item, str) or not item.strip() for item in values):
                    _coach_error("invalid_contract", f"{label} entries must be non-empty text.")
            if len(self.unavailable_fields) != len(set(self.unavailable_fields)):
                _coach_error("invalid_contract", "Unavailable field names must be unique.")
            paths = [item.path for item in self.provenance]
            if len(paths) != len(set(paths)):
                _coach_error("invalid_contract", "Provenance destination pointers must be unique.")
            for item in self.opponent_assumptions:
                if not isinstance(item, OpponentAssumption):
                    _coach_error("invalid_contract", "Opponent assumptions must use their shared contract type.")
            if self.source_kind == "practice_estimate":
                if (self.ev_basis != "incremental_decision_chips"
                        or self.reference_policy is None or self.modeled_policy is None
                        or self.reference_policy.kind != "illustrative_argmax"
                        or self.modeled_policy.kind != "estimate_argmax"):
                    _coach_error("invalid_contract", "Practice estimates require incremental EVs and labeled argmax policies.")
                if any(value is not None for value in
                       (self.quality.nash_conv, self.quality.exploitability,
                        self.quality.iterations, self.quality.gap_semantics)):
                    _coach_error("invalid_contract", "Practice estimates cannot claim solver convergence diagnostics.")
                if any(item.origin == "solver_output" for item in self.provenance):
                    _coach_error("invalid_contract", "Practice estimates cannot claim solver-output provenance.")
            payload = _json_value(self)
            for item in self.provenance:
                if not _coach_pointer_resolves(payload, item.path):
                    _coach_error("invalid_contract", "Provenance points to an unavailable evidence field.")
            if not self.evidence_id.startswith("analysis-"):
                _coach_error("invalid_contract", "Evidence ID has an unsupported format.")
            if stable_analysis_id(self._protected_dict(), "coach-evidence-v1") != self.evidence_id:
                _coach_error("fingerprint_mismatch", "Evidence fingerprint does not match its protected facts.")
        except CoachAnalysisError:
            raise
        except (TypeError, ValueError, KeyError, OverflowError):
            _coach_error("invalid_contract", "Coaching analysis contains invalid structured data.")

    def _protected_dict(self) -> dict[str, Any]:
        value = _json_value(self)
        value.pop("ref", None)
        value.pop("evidence_id", None)
        return value

    @classmethod
    def build(cls, **values: Any) -> "CoachDecisionAnalysis":
        """Construct a validated instance with the deterministic evidence ID."""
        prepared = dict(values)
        if "evidence_id" in prepared:
            return cls(**prepared)
        provisional = object.__new__(cls)
        for name in cls.__dataclass_fields__:
            if name in prepared:
                object.__setattr__(provisional, name, prepared[name])
            elif name == "evidence_id":
                object.__setattr__(provisional, name, "")
            elif cls.__dataclass_fields__[name].default is not MISSING:
                object.__setattr__(provisional, name, cls.__dataclass_fields__[name].default)
        protected = _json_value(provisional)
        protected.pop("ref", None)
        protected.pop("evidence_id", None)
        prepared["evidence_id"] = stable_analysis_id(protected, "coach-evidence-v1")
        return cls(**prepared)

    def to_dict(self) -> dict[str, Any]:
        return _json_value(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CoachDecisionAnalysis":
        names = {item.name for item in fields(cls)}
        value = _coach_nested_keys(data, names, "Coaching analysis")
        if value.get("schema_version") != 1:
            _coach_error("unsupported_schema_version", "Only coaching analysis schema version 1 is supported.")
        result = dict(value)
        result["ref"] = CoachDecisionRef(**_coach_nested_keys(value["ref"],
            {item.name for item in fields(CoachDecisionRef)}, "Decision reference"))
        result["context"] = _coach_context_from_dict(value["context"])
        for field_name in ("legal_actions", "modeled_actions"):
            if not isinstance(value[field_name], list):
                _coach_error("invalid_contract", f"{field_name} must be a JSON array.")
            result[field_name] = tuple(_coach_action_from_dict(item) for item in value[field_name])
        for field_name in ("reference_policy", "modeled_policy"):
            result[field_name] = _coach_policy_from_dict(value[field_name])
        for field_name in ("action_evs", "baseline_action_evs"):
            if not isinstance(value[field_name], list):
                _coach_error("invalid_contract", f"{field_name} must be a JSON array.")
            result[field_name] = tuple(CoachActionValue(**_coach_nested_keys(
                item, {"action_id", "value"}, "Action value")) for item in value[field_name])
        for field_name in ("opponent_ranges", "limitations", "warnings", "unavailable_fields"):
            if not isinstance(value[field_name], list):
                _coach_error("invalid_contract", f"{field_name} must be a JSON array.")
            result[field_name] = tuple(value[field_name])
        for field_name in ("opponent_assumptions", "provenance"):
            if not isinstance(value[field_name], list):
                _coach_error("invalid_contract", f"{field_name} must be a JSON array.")
        result["opponent_assumptions"] = tuple(_coach_assumption_from_dict(item)
                                               for item in value["opponent_assumptions"])
        result["provenance"] = tuple(_coach_provenance_from_dict(item)
                                     for item in value["provenance"])
        result["quality"] = _coach_quality_from_dict(value["quality"])
        return cls(**result)

    @classmethod
    def from_json(cls, encoded: str) -> "CoachDecisionAnalysis":
        try:
            value = json.loads(encoded, parse_constant=lambda _: _coach_error(
                "invalid_contract", "JSON must contain only finite numbers."))
        except CoachAnalysisError:
            raise
        except (json.JSONDecodeError, TypeError):
            _coach_error("invalid_contract", "Coaching analysis must be valid JSON.")
        if not isinstance(value, dict):
            _coach_error("invalid_contract", "Coaching analysis JSON must be an object.")
        return cls.from_dict(value)


def stable_analysis_id(inputs: Mapping[str, Any], namespace: str = "strategy-v1") -> str:
    """Return a repeatable identifier for the same normalized analysis inputs."""

    _require_text(namespace, "Analysis namespace")
    encoded = json.dumps({"namespace": namespace, "inputs": inputs}, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode()
    return "analysis-" + hashlib.sha256(encoded).hexdigest()[:20]

