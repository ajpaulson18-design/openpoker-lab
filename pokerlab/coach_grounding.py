"""Provider-safe facts and deterministic coach reply plans.

This module projects validated saved evidence into small immutable values. It
has no provider, persistence, solver, server, or gameplay dependencies.

Fact IDs are stable provenance locators, not signatures or authenticity proofs.
A bundle loaded from JSON must be rebound with trusted saved analysis and the
validated choice via :func:`rebind_grounding_bundle` before its facts are treated
as authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Mapping

from .contracts import CoachDecisionAnalysis


_SOURCE_LABELS = {
    "practice_estimate": "Practice estimate",
    "restricted_equilibrium": "Restricted equilibrium result",
    "restricted_exploit": "Restricted exploit estimate",
}
_FACT_KINDS = {
    "street", "hero_cards", "board", "current_pot", "pot_basis",
    "source_kind", "ev_basis", "modeled_action", "action_ev",
    "baseline_action_ev", "recommendation", "baseline_recommendation",
    "baseline_label", "choice", "choice_loss", "opponent_assumption",
    "opponent_uncertainty", "confidence_label", "equity_standard_error",
    "equity_exact", "solver_nash_conv", "solver_exploitability",
    "solver_iterations", "solver_gap_semantics",
}
_AVAILABILITY = {"available", "unavailable"}
_INTENTS = {"recommendation", "choice", "compare", "limits", "unavailable"}
_DETAILS = {"short", "normal", "technical"}
_AUDIENCES = {"beginner", "standard"}
_SOURCE_POINTER = re.compile(r"^/(analysis|choice)(?:/(?:[^~/]|~[01])*)*$")
_FACT_ID = re.compile(r"^f_[0-9a-f]{64}$")


class CoachGroundingError(ValueError):
    """Typed, safe failure for grounding and reply-plan contracts."""

    def __init__(self, code: str, message: str):
        if code not in {"invalid_grounding", "invalid_reply_plan"}:
            raise ValueError("Unknown coach grounding error code.")
        self.code = code
        super().__init__(message)


def _fail(code: str, message: str) -> None:
    raise CoachGroundingError(code, message)


def _strict_object(value: Any, keys: set[str], code: str, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        _fail(code, f"{label} has missing or unknown fields.")
    return value


def _text(value: Any, label: str, code: str, limit: int = 256) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        _fail(code, f"{label} is outside its allowed text bounds.")


def _enum(value: Any, values: set[str], label: str, code: str) -> None:
    if not isinstance(value, str) or value not in values:
        _fail(code, f"{label} is unsupported.")


def _finite_number(value: Any) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _optional_number(value: Any) -> bool:
    return value is None or _finite_number(value)


def _probability(value: Any) -> bool:
    return _finite_number(value) and 0 <= value <= 1


def _check_fact_shape(kind: str, value: Any) -> None:
    if kind in {"street", "pot_basis", "source_kind", "ev_basis", "baseline_label",
                "confidence_label"}:
        if not isinstance(value, str):
            _fail("invalid_grounding", "Text facts must contain bounded strings.")
    elif kind in {"hero_cards", "board"}:
        if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
            _fail("invalid_grounding", "Card facts must contain immutable text arrays.")
    elif kind in {"recommendation", "baseline_recommendation"}:
        if value is not None and not isinstance(value, str):
            _fail("invalid_grounding", "Recommendation facts must contain an action ID or null.")
    elif kind == "current_pot":
        if not _finite_number(value):
            _fail("invalid_grounding", "Pot facts must be finite numbers, not booleans.")
    elif kind == "modeled_action":
        if (not isinstance(value, tuple) or len(value) != 4
                or not isinstance(value[0], str)
                or value[1] not in {"fold", "check", "call", "bet", "raise"}
                or not _optional_number(value[2])
                or value[3] not in {"chips_added", "street_total"}):
            _fail("invalid_grounding", "Modeled action facts have invalid fields.")
    elif kind in {"action_ev", "baseline_action_ev"}:
        if (not isinstance(value, tuple) or len(value) != 2
                or not isinstance(value[0], str) or not _optional_number(value[1])):
            _fail("invalid_grounding", "Action EV facts must preserve a finite value or null.")
    elif kind in {"choice", "choice_loss"}:
        if kind == "choice_loss":
            if not _optional_number(value):
                _fail("invalid_grounding", "Choice loss must be finite or null, not a boolean.")
        elif (not isinstance(value, tuple) or len(value) != 6
              or value[0] not in {"fold", "check", "call", "raise"}
              or not _finite_number(value[1])
              or value[2] not in {"chips_added", "street_total"}
              or value[3] not in {"assessed", "unassessed_size"}
              or not _optional_number(value[4])
              or (value[5] is not None and not isinstance(value[5], str))):
            _fail("invalid_grounding", "Choice facts have invalid fields.")
    elif kind == "opponent_assumption":
        if (not isinstance(value, tuple) or len(value) != 13
                or not isinstance(value[0], str)
                or any(item is not None and not isinstance(item, str) for item in value[1:4])
                or not _probability(value[4])
                or type(value[5]) is not int or value[5] < 0
                or any(not (item is None or _probability(item)) for item in value[6:9])
                or (value[9] is not None and not _probability(value[9]))
                or (value[10] is not None and not _probability(value[10]))
                or any(item is not None and not isinstance(item, str) for item in value[11:13])):
            _fail("invalid_grounding", "Opponent assumption facts have invalid fields.")
    elif kind == "opponent_uncertainty":
        if (value is not None and (not isinstance(value, tuple) or len(value) != 5
                or any(not _probability(item) for item in value[:3])
                or any(not isinstance(item, str) for item in value[3:]))):
            _fail("invalid_grounding", "Opponent uncertainty facts have invalid fields.")
    elif kind in {"equity_standard_error", "solver_nash_conv", "solver_exploitability"}:
        if not _optional_number(value):
            _fail("invalid_grounding", "Quality metrics must be finite numbers or null.")
    elif kind == "equity_exact":
        if value is not None and type(value) is not bool:
            _fail("invalid_grounding", "Equity exactness must be boolean or null.")
    elif kind == "solver_iterations":
        if value is not None and (type(value) is not int or value < 0):
            _fail("invalid_grounding", "Solver iterations must be a non-negative integer or null.")
    elif kind == "solver_gap_semantics":
        if value is not None and not isinstance(value, str):
            _fail("invalid_grounding", "Solver gap semantics must be text or null.")


def _scalar(value: Any, code: str) -> None:
    if value is None or type(value) is bool or type(value) is int:
        return
    if type(value) is float:
        if math.isfinite(value):
            return
        _fail(code, "Numeric fact values must be finite.")
    if isinstance(value, str):
        _text(value, "Fact text", code)
        return
    _fail(code, "Fact values must be JSON scalars.")


def _value(value: Any, code: str) -> None:
    if isinstance(value, tuple):
        if len(value) > 16:
            _fail(code, "Fact arrays exceed their allowed length.")
        for item in value:
            _scalar(item, code)
        return
    _scalar(value, code)


def _value_from_json(value: Any, code: str) -> Any:
    if isinstance(value, list):
        if len(value) > 16:
            _fail(code, "Fact arrays exceed their allowed length.")
        result = tuple(value)
        _value(result, code)
        return result
    _scalar(value, code)
    return value


def _value_to_json(value: Any) -> Any:
    return list(value) if isinstance(value, tuple) else value


def _canonical_pointer(pointer: str, code: str) -> str:
    _text(pointer, "Source pointer", code, 512)
    if not _SOURCE_POINTER.fullmatch(pointer):
        _fail(code, "Source pointer must be canonical and remain under analysis or choice.")
    components = pointer.split("/")[1:]
    for component in components:
        decoded = component.replace("~1", "/").replace("~0", "~")
        encoded = decoded.replace("~", "~0").replace("/", "~1")
        if encoded != component:
            _fail(code, "Source pointer must use canonical JSON Pointer escaping.")
    return pointer


def _fact_id(decision_id: str, evidence_id: str, pointer: str) -> str:
    payload = f"{decision_id}\n{evidence_id}\n{pointer}".encode("utf-8")
    return "f_" + hashlib.sha256(payload).hexdigest()


def _resolve_pointer(root: Any, pointer: str) -> Any:
    value = root
    for component in pointer[1:].split("/"):
        component = component.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            value = value[component]
        elif isinstance(value, list) and component.isdigit():
            value = value[int(component)]
        else:
            raise KeyError(pointer)
    return value


def _json_loads(encoded: str, code: str, label: str) -> Any:
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _fail(code, f"{label} JSON contains duplicate object keys.")
            result[key] = value
        return result

    try:
        return json.loads(encoded, object_pairs_hook=object_pairs,
                          parse_constant=lambda _: _fail(code, "JSON numeric values must be finite."))
    except CoachGroundingError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError):
        _fail(code, f"{label} must be valid JSON.")


@dataclass(frozen=True, slots=True)
class GroundingBinding:
    hand_id: str
    decision_id: str
    evidence_id: str
    state_revision: int | None

    def __post_init__(self) -> None:
        for label, value in (("Hand ID", self.hand_id), ("Decision ID", self.decision_id),
                             ("Evidence ID", self.evidence_id)):
            _text(value, label, "invalid_grounding")
        if self.state_revision is not None and (type(self.state_revision) is not int
                                                or self.state_revision < 0):
            _fail("invalid_grounding", "State revision must be a non-negative integer or null.")

    def to_dict(self) -> dict[str, Any]:
        return {"hand_id": self.hand_id, "decision_id": self.decision_id,
                "evidence_id": self.evidence_id, "state_revision": self.state_revision}

    @classmethod
    def from_dict(cls, value: Any, code: str) -> "GroundingBinding":
        data = _strict_object(value, {"hand_id", "decision_id", "evidence_id", "state_revision"},
                              code, "Binding")
        try:
            return cls(**data)
        except CoachGroundingError as exc:
            if exc.code != code:
                _fail(code, "Binding contains invalid values.")
            raise
        except TypeError:
            _fail(code, "Binding contains invalid values.")


@dataclass(frozen=True, slots=True)
class GroundFact:
    fact_id: str
    kind: str
    source_pointer: str
    value: Any
    unit: str
    availability: str

    def __post_init__(self) -> None:
        _text(self.fact_id, "Fact ID", "invalid_grounding", 66)
        if not _FACT_ID.fullmatch(self.fact_id):
            _fail("invalid_grounding", "Fact ID has an invalid format.")
        _enum(self.kind, _FACT_KINDS, "Fact kind", "invalid_grounding")
        _canonical_pointer(self.source_pointer, "invalid_grounding")
        _value(self.value, "invalid_grounding")
        _text(self.unit, "Fact unit", "invalid_grounding", 64)
        _enum(self.availability, _AVAILABILITY, "Fact availability", "invalid_grounding")
        _check_fact_shape(self.kind, self.value)

    def to_dict(self) -> dict[str, Any]:
        return {"fact_id": self.fact_id, "kind": self.kind,
                "source_pointer": self.source_pointer,
                "value": _value_to_json(self.value), "unit": self.unit,
                "availability": self.availability}

    @classmethod
    def from_dict(cls, value: Any) -> "GroundFact":
        data = _strict_object(value, {"fact_id", "kind", "source_pointer", "value",
                                      "unit", "availability"},
                              "invalid_grounding", "Ground fact")
        result = dict(data)
        result["value"] = _value_from_json(data["value"], "invalid_grounding")
        try:
            return cls(**result)
        except TypeError:
            _fail("invalid_grounding", "Ground fact contains invalid values.")


@dataclass(frozen=True, slots=True)
class GroundingBundle:
    binding: GroundingBinding
    source_kind: str
    ev_basis: str
    facts: tuple[GroundFact, ...]
    limitations: tuple[str, ...]
    unavailable_fields: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            _fail("invalid_grounding", "Only grounding schema version 1 is supported.")
        if not isinstance(self.binding, GroundingBinding):
            _fail("invalid_grounding", "Grounding bundle requires an immutable binding.")
        _enum(self.source_kind, set(_SOURCE_LABELS), "Grounding source kind", "invalid_grounding")
        _enum(self.ev_basis, {"incremental_decision_chips", "half_initial_pot_utility"},
              "Grounding EV basis", "invalid_grounding")
        if not isinstance(self.facts, tuple) or len(self.facts) > 64:
            _fail("invalid_grounding", "Grounding facts must be an immutable array of at most 64 items.")
        if any(not isinstance(item, GroundFact) for item in self.facts):
            _fail("invalid_grounding", "Grounding facts must use the shared fact type.")
        ids = [item.fact_id for item in self.facts]
        pointers = [item.source_pointer for item in self.facts]
        if len(ids) != len(set(ids)) or len(pointers) != len(set(pointers)):
            _fail("invalid_grounding", "Fact IDs and source pointers must be unique.")
        for fact in self.facts:
            if fact.fact_id != _fact_id(self.binding.decision_id, self.binding.evidence_id,
                                        fact.source_pointer):
                _fail("invalid_grounding", "Fact ID does not match its decision-bound provenance.")
            if (fact.kind in {"action_ev", "baseline_action_ev", "choice_loss"}
                    and fact.unit != self.ev_basis):
                _fail("invalid_grounding", "EV facts must use the bundle's saved basis.")
        if not isinstance(self.limitations, tuple) or len(self.limitations) > 10:
            _fail("invalid_grounding", "Limitations must be an immutable array of at most 10 items.")
        for item in self.limitations:
            _text(item, "Limitation", "invalid_grounding", 500)
        if (not isinstance(self.unavailable_fields, tuple)
                or len(self.unavailable_fields) > 64
                or len(set(self.unavailable_fields)) != len(self.unavailable_fields)):
            _fail("invalid_grounding", "Unavailable fields must be unique and bounded.")
        for item in self.unavailable_fields:
            _text(item, "Unavailable field", "invalid_grounding")

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "binding": self.binding.to_dict(),
                "source_kind": self.source_kind, "ev_basis": self.ev_basis,
                "facts": [item.to_dict() for item in self.facts],
                "limitations": list(self.limitations),
                "unavailable_fields": list(self.unavailable_fields)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_dict(cls, value: Any) -> "GroundingBundle":
        data = _strict_object(value, {"schema_version", "binding", "source_kind", "ev_basis",
                                      "facts", "limitations", "unavailable_fields"},
                              "invalid_grounding", "Grounding bundle")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            _fail("invalid_grounding", "Only grounding schema version 1 is supported.")
        for name in ("facts", "limitations", "unavailable_fields"):
            if not isinstance(data[name], list):
                _fail("invalid_grounding", f"{name} must be a JSON array.")
        try:
            return cls(GroundingBinding.from_dict(data["binding"], "invalid_grounding"),
                       data["source_kind"], data["ev_basis"],
                       tuple(GroundFact.from_dict(item) for item in data["facts"]),
                       tuple(data["limitations"]), tuple(data["unavailable_fields"]),
                       data["schema_version"])
        except TypeError:
            _fail("invalid_grounding", "Grounding bundle contains invalid values.")

    @classmethod
    def from_json(cls, encoded: str) -> "GroundingBundle":
        value = _json_loads(encoded, "invalid_grounding", "Grounding bundle")
        return cls.from_dict(value)


@dataclass(frozen=True, slots=True)
class CoachReplyPlan:
    binding: GroundingBinding
    intent: str
    fact_ids: tuple[str, ...]
    target_action_id: str | None
    detail: str
    audience: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            _fail("invalid_reply_plan", "Only reply-plan schema version 1 is supported.")
        if not isinstance(self.binding, GroundingBinding):
            _fail("invalid_reply_plan", "Reply plan requires an immutable binding.")
        _enum(self.intent, _INTENTS, "Reply-plan intent", "invalid_reply_plan")
        if not isinstance(self.fact_ids, tuple) or len(self.fact_ids) > 16:
            _fail("invalid_reply_plan", "Reply-plan citations must be an immutable array of at most 16 IDs.")
        for fact_id in self.fact_ids:
            _text(fact_id, "Fact citation", "invalid_reply_plan", 66)
            if not _FACT_ID.fullmatch(fact_id):
                _fail("invalid_reply_plan", "Reply-plan citation has an invalid format.")
        if len(set(self.fact_ids)) != len(self.fact_ids):
            _fail("invalid_reply_plan", "Duplicate fact citations are not allowed.")
        if self.target_action_id is not None:
            _text(self.target_action_id, "Target action ID", "invalid_reply_plan")
        if self.intent == "compare" and self.target_action_id is None:
            _fail("invalid_reply_plan", "Compare plans require a modeled target action ID.")
        if self.intent != "compare" and self.target_action_id is not None:
            _fail("invalid_reply_plan", "Only compare plans may name a target action ID.")
        _enum(self.detail, _DETAILS, "Reply-plan detail", "invalid_reply_plan")
        _enum(self.audience, _AUDIENCES, "Reply-plan audience", "invalid_reply_plan")

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "binding": self.binding.to_dict(),
                "intent": self.intent, "fact_ids": list(self.fact_ids),
                "target_action_id": self.target_action_id,
                "detail": self.detail, "audience": self.audience}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_dict(cls, value: Any) -> "CoachReplyPlan":
        data = _strict_object(value, {"schema_version", "binding", "intent", "fact_ids",
                                      "target_action_id", "detail", "audience"},
                              "invalid_reply_plan", "Reply plan")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            _fail("invalid_reply_plan", "Only reply-plan schema version 1 is supported.")
        if not isinstance(data["fact_ids"], list):
            _fail("invalid_reply_plan", "Reply-plan citations must be a JSON array.")
        try:
            return cls(GroundingBinding.from_dict(data["binding"], "invalid_reply_plan"),
                       data["intent"], tuple(data["fact_ids"]), data["target_action_id"],
                       data["detail"], data["audience"], data["schema_version"])
        except TypeError:
            _fail("invalid_reply_plan", "Reply plan contains invalid values.")

    @classmethod
    def from_json(cls, encoded: str) -> "CoachReplyPlan":
        value = _json_loads(encoded, "invalid_reply_plan", "Reply plan")
        return cls.from_dict(value)


def _choice_from_input(analysis: CoachDecisionAnalysis, choice: Any) -> dict[str, Any]:
    keys = {"name", "amount", "amount_semantics", "assessed_modeled_action_id",
            "assessment_status", "ev_loss"}
    data = _strict_object(choice, keys, "invalid_grounding", "Validated choice")
    name, amount = data["name"], data["amount"]
    _enum(name, {"fold", "check", "call", "raise"}, "Choice action", "invalid_grounding")
    if type(amount) is not int or amount < 0:
        _fail("invalid_grounding", "Validated choice is malformed.")
    expected_semantics = "street_total" if name == "raise" else "chips_added"
    legal = next((action for action in analysis.legal_actions if action.name == name), None)
    status = data["assessment_status"]
    _enum(status, {"assessed", "unassessed_size"}, "Choice assessment status",
          "invalid_grounding")
    if (legal is None or data["amount_semantics"] != expected_semantics):
        _fail("invalid_grounding", "Validated choice is malformed.")
    if name == "raise":
        if (legal.minimum_total is None or legal.maximum_total is None
                or not legal.minimum_total <= amount <= legal.maximum_total):
            _fail("invalid_grounding", "Validated choice is malformed.")
        assessed = amount == legal.minimum_total
    else:
        if amount != legal.amount:
            _fail("invalid_grounding", "Validated choice is malformed.")
        assessed = True
    expected_id = "raise:min" if name == "raise" else name
    if ((status == "assessed") != assessed
            or (status == "assessed" and data["assessed_modeled_action_id"] != expected_id)
            or (status == "unassessed_size"
                and (name != "raise" or data["assessed_modeled_action_id"] is not None))):
        _fail("invalid_grounding", "Validated choice is malformed.")
    loss = data["ev_loss"]
    if loss is not None and (type(loss) not in (int, float) or not math.isfinite(loss) or loss < 0):
        _fail("invalid_grounding", "Validated choice is malformed.")
    if ((status == "unassessed_size" and loss is not None)
            or (status == "assessed" and loss is None)):
        _fail("invalid_grounding", "Validated choice is malformed.")
    if status == "assessed":
        action_values = {item.action_id: item.value for item in analysis.action_evs}
        recommended = analysis.recommended_action_id
        selected = data["assessed_modeled_action_id"]
        if (recommended not in action_values or selected not in action_values
                or action_values[recommended] is None or action_values[selected] is None):
            _fail("invalid_grounding", "Validated choice is malformed.")
        expected_loss = max(0.0, action_values[recommended] - action_values[selected])
        if loss != expected_loss:
            _fail("invalid_grounding", "Validated choice is malformed.")
    return dict(data)


def build_grounding_bundle(analysis: CoachDecisionAnalysis, choice: Mapping[str, Any]) -> GroundingBundle:
    """Project only the approved decision-local facts from validated inputs."""
    if not isinstance(analysis, CoachDecisionAnalysis):
        _fail("invalid_grounding", "Grounding requires validated coach decision evidence.")
    selected = _choice_from_input(analysis, choice)
    binding = GroundingBinding(analysis.ref.hand_id, analysis.ref.decision_id,
                               analysis.evidence_id, analysis.ref.state_revision)
    facts: list[GroundFact] = []
    pointer_source = {"analysis": analysis.to_dict(), "choice": selected}

    def add(kind: str, pointer: str, value: Any, unit: str,
            available: bool | None = None) -> GroundFact:
        pointer = _canonical_pointer(pointer, "invalid_grounding")
        try:
            _resolve_pointer(pointer_source, pointer)
        except (KeyError, IndexError, TypeError, ValueError):
            _fail("invalid_grounding", "Fact provenance does not resolve in validated evidence.")
        if available is None:
            available = value is not None
        fact = GroundFact(_fact_id(binding.decision_id, binding.evidence_id, pointer),
                          kind, pointer, value, unit,
                          "available" if available else "unavailable")
        facts.append(fact)
        return fact

    add("street", "/analysis/context/street", analysis.context.street, "street", True)
    add("hero_cards", "/analysis/context/hero_cards", analysis.context.hero_cards,
        "cards", True)
    add("board", "/analysis/context/board", analysis.context.board, "cards", True)
    add("current_pot", "/analysis/context/pot", analysis.context.pot, "chips", True)
    add("pot_basis", "/analysis/context/pot_basis", analysis.context.pot_basis,
        "basis", True)
    add("source_kind", "/analysis/source_kind", analysis.source_kind, "source", True)
    add("ev_basis", "/analysis/ev_basis", analysis.ev_basis, "basis", True)

    for index, action in enumerate(analysis.modeled_actions):
        add("modeled_action", f"/analysis/modeled_actions/{index}",
            (action.action_id, action.name, action.amount, action.amount_semantics),
            "action", True)
    for index, item in enumerate(analysis.action_evs):
        add("action_ev", f"/analysis/action_evs/{index}",
            (item.action_id, item.value), analysis.ev_basis, item.value is not None)
    for index, item in enumerate(analysis.baseline_action_evs):
        add("baseline_action_ev", f"/analysis/baseline_action_evs/{index}",
            (item.action_id, item.value), analysis.ev_basis, item.value is not None)
    add("recommendation", "/analysis/recommended_action_id",
        analysis.recommended_action_id, "action_id", analysis.recommended_action_id is not None)
    add("baseline_recommendation", "/analysis/baseline_recommended_action_id",
        analysis.baseline_recommended_action_id, "action_id",
        analysis.baseline_recommended_action_id is not None)
    if analysis.reference_policy is not None:
        add("baseline_label", "/analysis/reference_policy/kind",
            analysis.reference_policy.kind, "policy", True)

    choice_value = (selected["name"], selected["amount"], selected["amount_semantics"],
                    selected["assessment_status"], selected["ev_loss"],
                    selected["assessed_modeled_action_id"])
    add("choice", "/choice", choice_value, "choice", True)
    add("choice_loss", "/choice/ev_loss", selected["ev_loss"], analysis.ev_basis,
        selected["assessment_status"] == "assessed" and selected["ev_loss"] is not None)

    for index, assumption in enumerate(analysis.opponent_assumptions):
        uncertainty = assumption.uncertainty
        assumption_value = (
            assumption.tendency_id, assumption.context.street,
            assumption.context.position, assumption.context.action_context,
            assumption.value, assumption.evidence_count,
            assumption.baseline_frequency, assumption.posterior_mean,
            assumption.confidence_weight,
            uncertainty.lower if uncertainty else None,
            uncertainty.upper if uncertainty else None,
            uncertainty.confidence if uncertainty else None,
            uncertainty.method if uncertainty else None,
        )
        add("opponent_assumption", f"/analysis/opponent_assumptions/{index}",
            assumption_value, "assumption", True)
    quality = analysis.quality
    add("confidence_label", "/analysis/quality/confidence_label",
        quality.confidence_label, "label", True)
    add("equity_standard_error", "/analysis/quality/equity_standard_error",
        quality.equity_standard_error, "standard_error")
    add("equity_exact", "/analysis/quality/equity_exact", quality.equity_exact, "boolean")
    add("solver_nash_conv", "/analysis/quality/nash_conv", quality.nash_conv, "ev")
    add("solver_exploitability", "/analysis/quality/exploitability",
        quality.exploitability, "ev")
    add("solver_iterations", "/analysis/quality/iterations", quality.iterations, "iterations")
    add("solver_gap_semantics", "/analysis/quality/gap_semantics",
        quality.gap_semantics, "semantics")
    opponent_uncertainty = quality.opponent_uncertainty
    uncertainty_value = ((opponent_uncertainty.lower, opponent_uncertainty.upper,
                          opponent_uncertainty.level, opponent_uncertainty.method,
                          opponent_uncertainty.confidence)
                         if opponent_uncertainty is not None else None)
    add("opponent_uncertainty", "/analysis/quality/opponent_uncertainty",
        uncertainty_value, "interval", opponent_uncertainty is not None)

    limitations = tuple(dict.fromkeys((*analysis.limitations, *analysis.warnings)))
    if len(limitations) > 10 or any(not isinstance(item, str) or len(item) > 500
                                    for item in limitations):
        _fail("invalid_grounding", "Producer caveats exceed the grounding bundle limits.")
    unavailable = list(analysis.unavailable_fields)
    action_values = {item.action_id: item.value for item in analysis.action_evs}
    baseline_values = {item.action_id: item.value for item in analysis.baseline_action_evs}
    if analysis.recommended_action_id is None:
        unavailable.append("recommendation")
    for action_id, value in action_values.items():
        if value is None:
            unavailable.append(f"action_ev:{action_id}")
    for action_id, value in baseline_values.items():
        if value is None:
            unavailable.append(f"baseline_action_ev:{action_id}")
    if analysis.baseline_recommended_action_id is None:
        unavailable.append("baseline_recommendation")
    if (quality.nash_conv is None or quality.exploitability is None
            or quality.iterations is None or quality.gap_semantics is None):
        unavailable.append("solver_quality")
    if not analysis.opponent_assumptions:
        unavailable.append("opponent_assumptions")
    if selected["ev_loss"] is None:
        unavailable.append("choice.ev_loss")
    unavailable_fields = tuple(dict.fromkeys(unavailable))
    if len(facts) > 64 or len(unavailable_fields) > 64:
        _fail("invalid_grounding", "Grounding bundle exceeds its bounded field limits.")
    return GroundingBundle(binding, analysis.source_kind, analysis.ev_basis,
                           tuple(facts), limitations, unavailable_fields)


def rebind_grounding_bundle(bundle: GroundingBundle, analysis: CoachDecisionAnalysis,
                            choice: Mapping[str, Any]) -> GroundingBundle:
    """Rebuild a loaded bundle against trusted saved evidence before using it.

    The provenance hash detects accidental ID drift; it does not authenticate a
    serialized value. Equality with this fresh allowlisted projection is the
    trust check callers must perform before treating loaded facts as authoritative.
    """
    if not isinstance(bundle, GroundingBundle):
        _fail("invalid_grounding", "Only a validated grounding bundle can be rebound.")
    expected = build_grounding_bundle(analysis, choice)
    if bundle != expected:
        _fail("invalid_grounding", "Grounding bundle does not match trusted saved evidence.")
    return expected


def validate_coach_reply_plan(plan: CoachReplyPlan, bundle: GroundingBundle) -> CoachReplyPlan:
    """Validate an answer proposal against one exact bundle and action set."""
    if not isinstance(bundle, GroundingBundle):
        _fail("invalid_reply_plan", "Reply plan requires a validated grounding bundle.")
    if not isinstance(plan, CoachReplyPlan):
        if isinstance(plan, Mapping):
            plan = CoachReplyPlan.from_dict(plan)
        else:
            _fail("invalid_reply_plan", "Reply plan has an invalid shape.")
    if plan.binding != bundle.binding:
        _fail("invalid_reply_plan", "Reply plan binding does not match the grounding bundle.")
    fact_ids = {fact.fact_id for fact in bundle.facts}
    if any(fact_id not in fact_ids for fact_id in plan.fact_ids):
        _fail("invalid_reply_plan", "Reply plan cites a fact outside the grounding bundle.")
    action_ids = {fact.value[0] for fact in bundle.facts
                  if fact.kind == "modeled_action" and isinstance(fact.value, tuple)}
    if plan.intent == "compare" and plan.target_action_id not in action_ids:
        _fail("invalid_reply_plan", "Compare target must identify a modeled action.")
    return plan


@dataclass(frozen=True, slots=True)
class ReplyFact:
    fact_id: str
    kind: str
    value: Any
    unit: str
    availability: str

    def to_dict(self) -> dict[str, Any]:
        return {"fact_id": self.fact_id, "kind": self.kind,
                "value": _value_to_json(self.value), "unit": self.unit,
                "availability": self.availability}


@dataclass(frozen=True, slots=True)
class AnswerBlock:
    kind: str
    label: str
    facts: tuple[ReplyFact, ...]
    caveats: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "label": self.label,
                "facts": [item.to_dict() for item in self.facts],
                "caveats": list(self.caveats)}


@dataclass(frozen=True, slots=True)
class RenderedCoachReply:
    binding: GroundingBinding
    intent: str
    requested_intent: str
    detail: str
    audience: str
    source_kind: str
    source_label: str
    blocks: tuple[AnswerBlock, ...]
    caveats: tuple[str, ...]
    unavailable_fields: tuple[str, ...]
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "binding": self.binding.to_dict(),
                "intent": self.intent, "requested_intent": self.requested_intent,
                "detail": self.detail, "audience": self.audience,
                "source_kind": self.source_kind, "source_label": self.source_label,
                "blocks": [item.to_dict() for item in self.blocks],
                "caveats": list(self.caveats),
                "unavailable_fields": list(self.unavailable_fields)}


def render_coach_reply(bundle: GroundingBundle, plan: CoachReplyPlan) -> RenderedCoachReply:
    """Render structured answer blocks; never accept provider-authored strategy text."""
    plan = validate_coach_reply_plan(plan, bundle)
    by_id = {fact.fact_id: fact for fact in bundle.facts}
    by_kind: dict[str, list[GroundFact]] = {}
    for fact in bundle.facts:
        by_kind.setdefault(fact.kind, []).append(fact)

    def cited(facts) -> tuple[ReplyFact, ...]:
        return tuple(ReplyFact(item.fact_id, item.kind, item.value, item.unit,
                               item.availability) for item in facts)

    def one(kind: str) -> GroundFact | None:
        return next(iter(by_kind.get(kind, ())), None)

    def action(action_id: str) -> GroundFact | None:
        return next((item for item in by_kind.get("modeled_action", ())
                     if item.value[0] == action_id), None)

    def ev(action_id: str, kind: str = "action_ev") -> GroundFact | None:
        return next((item for item in by_kind.get(kind, ())
                     if item.value[0] == action_id), None)

    source_label = _SOURCE_LABELS[bundle.source_kind]
    selected_ids: set[str] = set()
    blocks: list[AnswerBlock] = []
    rendered_intent = plan.intent
    unavailable = list(bundle.unavailable_fields)

    def include(block_kind: str, label: str, facts, caveats=()):
        facts = tuple(fact for fact in facts if fact is not None)
        selected_ids.update(fact.fact_id for fact in facts)
        blocks.append(AnswerBlock(block_kind, label, cited(facts), tuple(caveats)))

    if plan.intent == "recommendation":
        recommendation = one("recommendation")
        recommendation_id = recommendation.value if recommendation else None
        selected_action = action(recommendation_id) if isinstance(recommendation_id, str) else None
        if recommendation_id is None or selected_action is None:
            rendered_intent = "unavailable"
            if "recommendation" not in unavailable:
                unavailable.append("recommendation")
            include("unavailable", "Recommendation unavailable", (recommendation,))
        else:
            facts = [recommendation, selected_action]
            if plan.detail != "short":
                facts.append(ev(recommendation_id))
            if plan.detail == "technical":
                facts.extend((one("confidence_label"),
                              *by_kind.get("solver_nash_conv", ()),
                              *by_kind.get("solver_exploitability", ()),
                              *by_kind.get("solver_iterations", ()),
                              *by_kind.get("solver_gap_semantics", ()),
                              one("opponent_uncertainty")))
            label = ("Saved action" if plan.audience == "beginner"
                     else "Saved recommendation")
            include("recommendation", label, facts)
    elif plan.intent == "choice":
        choice = one("choice")
        loss = one("choice_loss")
        choice_status = choice.value[3] if choice and isinstance(choice.value, tuple) else None
        if choice is None:
            rendered_intent = "unavailable"
            unavailable.append("choice")
            include("unavailable", "Choice unavailable", (one("source_kind"),))
        elif choice_status == "assessed" and loss is not None and loss.availability == "available":
            include("choice", "Recorded choice", (choice, loss))
        else:
            if "choice.ev_loss" not in unavailable:
                unavailable.append("choice.ev_loss")
            include("choice", "Choice recorded; loss unavailable", (choice, loss))
    elif plan.intent == "compare":
        choice = one("choice")
        choice_status = choice.value[3] if choice and isinstance(choice.value, tuple) else None
        choice_action_id = choice.value[5] if choice and isinstance(choice.value, tuple) else None
        choice_action = action(choice_action_id) if isinstance(choice_action_id, str) else None
        target_action = action(plan.target_action_id)
        choice_ev = ev(choice_action_id) if isinstance(choice_action_id, str) else None
        target_ev = ev(plan.target_action_id)
        choice_amount = choice.value[1] if choice and isinstance(choice.value, tuple) else None
        if (choice is None or choice_status != "assessed" or choice_action is None
                or choice_ev is None or target_action is None or target_ev is None
                or choice_ev.availability != "available"
                or target_ev.availability != "available"
                or choice_ev.unit != bundle.ev_basis or target_ev.unit != bundle.ev_basis
                or (choice_action.value[1] == "raise" and choice_action.value[2] != choice_amount)):
            rendered_intent = "unavailable"
            marker = "choice_action_not_modeled" if choice_status != "assessed" else "comparison_ev"
            if marker not in unavailable:
                unavailable.append(marker)
            # Keep the recorded choice visible to explain why an unassessed
            # size cannot be compared, while withholding every substitute EV.
            include("unavailable", "Comparison unavailable", (choice,))
        else:
            include("comparison", "Saved estimates in the same EV basis",
                    (choice, choice_action, choice_ev, target_action, target_ev))
    elif plan.intent == "limits":
        facts = [one("source_kind"), one("confidence_label"), one("opponent_uncertainty"),
                 one("equity_standard_error"), one("equity_exact"),
                 *by_kind.get("solver_nash_conv", ()),
                 *by_kind.get("solver_exploitability", ()),
                 *by_kind.get("solver_iterations", ()),
                 *by_kind.get("solver_gap_semantics", ()),
                 *by_kind.get("opponent_assumption", ())]
        if plan.detail == "short":
            facts = [one("source_kind"), one("confidence_label")]
        include("limits", "Model limits and saved assumptions", facts, bundle.limitations)
    else:
        include("unavailable", "Unavailable facts", (one("source_kind"),))

    # Citations support an answer but cannot select or replace its required facts.
    # An unavailable comparison intentionally omits optional EV facts so none can
    # be mistaken for a substitute estimate of an unmodeled choice.
    choice_fact = one("choice")
    unassessed_choice = (choice_fact is not None and isinstance(choice_fact.value, tuple)
                         and choice_fact.value[3] == "unassessed_size")
    if rendered_intent != "unavailable" and not unassessed_choice:
        for fact_id in plan.fact_ids:
            fact = by_id[fact_id]
            if fact_id not in selected_ids:
                include("supporting", f"Saved {fact.kind.replace('_', ' ')}", (fact,))

    return RenderedCoachReply(
        bundle.binding, rendered_intent, plan.intent, plan.detail, plan.audience,
        bundle.source_kind, source_label, tuple(blocks), bundle.limitations,
        tuple(dict.fromkeys(unavailable)),
    )
