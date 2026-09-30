"""Deterministic, evidence-traceable explanations of strategy analysis.

This module only selects and renders facts already present in a
``StrategyAnalysisResult``.  The recommendation is supplied by the calculation
layer; explanation code never ranks actions or recomputes poker strategy.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any, Mapping

from .contracts import (ActionFrequency, ActionValue, ExploitativeAdjustment,
                        ExplanationPayload, MathematicalFact, OpponentAssumption,
                        StrategyAnalysisResult,
                        TendencyContext, Uncertainty)


SCHEMA_VERSION = 1


class ExplanationLevel(str, Enum):
    SHORT = "short"
    NORMAL = "normal"
    BEGINNER = "beginner"


@dataclass(frozen=True, slots=True)
class AlternativeAction:
    action: str
    ev: float
    ev_difference: float
    baseline_frequency: float
    exploitative_frequency: float

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "ev": self.ev,
                "ev_difference": self.ev_difference,
                "baseline_frequency": self.baseline_frequency,
                "exploitative_frequency": self.exploitative_frequency}


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    tendency_id: str
    value: float
    evidence_count: int
    context: TendencyContext
    uncertainty: Uncertainty | None

    def to_dict(self) -> dict[str, Any]:
        return {"tendency_id": self.tendency_id, "value": self.value,
                "evidence_count": self.evidence_count,
                "context": self.context.to_dict(),
                "uncertainty": self.uncertainty.to_dict() if self.uncertainty else None}


@dataclass(frozen=True, slots=True)
class TermDefinition:
    term: str
    definition: str

    def to_dict(self) -> dict[str, str]:
        return {"term": self.term, "definition": self.definition}


@dataclass(frozen=True, slots=True)
class ProvenanceItem:
    field: str
    source: str
    reference: str

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "source": self.source,
                "reference": self.reference}


@dataclass(frozen=True, slots=True)
class DecisionExplanation:
    """Serializable explanation facts plus deterministic prose."""

    analysis_id: str
    level: ExplanationLevel
    recommended_action: str
    facts: ExplanationPayload
    alternative_actions: tuple[AlternativeAction, ...]
    action_evs: tuple[ActionValue, ...]
    ev_differences: tuple[ActionValue, ...]
    baseline_strategy: tuple[ActionFrequency, ...]
    exploitative_strategy: tuple[ActionFrequency, ...]
    exploitative_adjustment: ExploitativeAdjustment
    evidence: tuple[EvidenceItem, ...]
    confidence: str
    uncertainty: Uncertainty | None
    mathematical_reason: str
    plain_language_reason: str
    summary: str
    caveats: tuple[str, ...]
    glossary: tuple[TermDefinition, ...]
    provenance: tuple[ProvenanceItem, ...]
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "analysis_id": self.analysis_id,
            "level": self.level.value,
            "recommended_action": self.recommended_action,
            "facts": self.facts.to_dict(),
            "alternative_actions": [item.to_dict() for item in self.alternative_actions],
            "action_evs": [item.to_dict() for item in self.action_evs],
            "ev_differences": [item.to_dict() for item in self.ev_differences],
            "baseline_strategy": [item.to_dict() for item in self.baseline_strategy],
            "exploitative_strategy": [item.to_dict() for item in self.exploitative_strategy],
            "exploitative_adjustment": self.exploitative_adjustment.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
            "confidence": self.confidence,
            "uncertainty": self.uncertainty.to_dict() if self.uncertainty else None,
            "mathematical_reason": self.mathematical_reason,
            "plain_language_reason": self.plain_language_reason,
            "summary": self.summary,
            "caveats": list(self.caveats),
            "glossary": [item.to_dict() for item in self.glossary],
            "provenance": [item.to_dict() for item in self.provenance],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"),
                          allow_nan=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DecisionExplanation":
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported explanation schema version.")
        return cls(
            analysis_id=data["analysis_id"], level=ExplanationLevel(data["level"]),
            recommended_action=data["recommended_action"],
            facts=_payload(data["facts"]),
            alternative_actions=tuple(AlternativeAction(**item) for item in data["alternative_actions"]),
            action_evs=_action_values(data["action_evs"]),
            ev_differences=_action_values(data["ev_differences"]),
            baseline_strategy=_frequencies(data["baseline_strategy"]),
            exploitative_strategy=_frequencies(data["exploitative_strategy"]),
            exploitative_adjustment=ExploitativeAdjustment(**data["exploitative_adjustment"]),
            evidence=tuple(EvidenceItem(
                tendency_id=item["tendency_id"], value=item["value"],
                evidence_count=item["evidence_count"],
                context=_context(item["context"]),
                uncertainty=_uncertainty(item.get("uncertainty"))) for item in data["evidence"]),
            confidence=data["confidence"], uncertainty=_uncertainty(data.get("uncertainty")),
            mathematical_reason=data["mathematical_reason"],
            plain_language_reason=data["plain_language_reason"], summary=data["summary"],
            caveats=tuple(data["caveats"]),
            glossary=tuple(TermDefinition(**item) for item in data["glossary"]),
            provenance=tuple(ProvenanceItem(**item) for item in data["provenance"]),
            schema_version=data["schema_version"],
        )

    @classmethod
    def from_json(cls, encoded: str) -> "DecisionExplanation":
        data = json.loads(encoded)
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON explanation object.")
        return cls.from_dict(data)


def _context(data: Mapping[str, Any]) -> TendencyContext:
    return TendencyContext(data.get("street"), data.get("position"),
                           data.get("action_context"),
                           tuple(tuple(pair) for pair in data.get("qualifiers", ())))


def _uncertainty(data: Mapping[str, Any] | None) -> Uncertainty | None:
    return Uncertainty(**data) if data is not None else None


def _frequencies(items: Any) -> tuple[ActionFrequency, ...]:
    return tuple(ActionFrequency(**item) for item in items)


def _action_values(items: Any) -> tuple[ActionValue, ...]:
    return tuple(ActionValue(**item) for item in items)


def _assumption(data: Mapping[str, Any] | None) -> OpponentAssumption | None:
    if data is None:
        return None
    return OpponentAssumption(
        tendency_id=data["tendency_id"], context=_context(data["context"]),
        value=data["value"], evidence_count=data["evidence_count"],
        uncertainty=_uncertainty(data.get("uncertainty")))


def _payload(data: Mapping[str, Any]) -> ExplanationPayload:
    adjustment = data.get("exploitative_adjustment")
    return ExplanationPayload(
        analysis_id=data["analysis_id"], recommended_action=data["recommended_action"],
        baseline_strategy=_frequencies(data["baseline_strategy"]),
        exploitative_adjustment=ExploitativeAdjustment(**adjustment) if adjustment else None,
        primary_reason=data["primary_reason"],
        relevant_tendency=_assumption(data.get("relevant_tendency")),
        evidence_count=data["evidence_count"],
        uncertainty=_uncertainty(data.get("uncertainty")),
        ev_difference=data.get("ev_difference"),
        mathematical_facts=tuple(MathematicalFact(**item)
                                 for item in data.get("mathematical_facts", ())),
        caveats=tuple(data.get("caveats", ())))


def analysis_from_dict(data: Mapping[str, Any]) -> StrategyAnalysisResult:
    """Deserialize the shared analysis contract at the server boundary."""
    assumptions = tuple(_assumption(item) for item in data.get("opponent_assumptions", ()))
    return StrategyAnalysisResult(
        analysis_id=data["analysis_id"], legal_actions=tuple(data["legal_actions"]),
        baseline_strategy=_frequencies(data["baseline_strategy"]),
        exploitative_strategy=_frequencies(data["exploitative_strategy"]),
        action_evs=_action_values(data["action_evs"]),
        ev_differences=_action_values(data["ev_differences"]),
        opponent_assumptions=assumptions, confidence=data["confidence"],
        uncertainty=_uncertainty(data.get("uncertainty")),
        solver_version=data["solver_version"], model_version=data["model_version"],
        limitations=tuple(data.get("limitations", ())), warnings=tuple(data.get("warnings", ())))


def _label(identifier: str) -> str:
    return identifier.replace("_", " ")


def _pct(value: float) -> str:
    return f"{value:.1%}"


def _chips(value: float) -> str:
    return f"{value:+.2f} chips"


def _glossary() -> tuple[TermDefinition, ...]:
    return (
        TermDefinition("expected value", "The average chip gain or loss if the same decision were repeated many times."),
        TermDefinition("range", "The set of hands a player could hold, often with different weights."),
        TermDefinition("pot odds", "The price of a call compared with the pot that can be won."),
        TermDefinition("action frequency", "How often a strategy takes an action across otherwise identical decisions."),
        TermDefinition("bluff-catching", "Calling with a hand that mainly wins when the opponent is bluffing."),
        TermDefinition("value betting", "Betting because worse hands are expected to continue often enough to make the bet profitable."),
        TermDefinition("opponent tendency", "A modeled action rate derived from a stated prior and recorded opportunities."),
        TermDefinition("uncertainty", "How imprecise an estimate is; limited evidence generally supports more caution."),
    )


def explain(analysis: StrategyAnalysisResult, recommended_action: str,
            level: ExplanationLevel | str = ExplanationLevel.NORMAL) -> DecisionExplanation:
    """Explain an upstream recommendation without choosing or checking it."""
    level = ExplanationLevel(level)
    if recommended_action not in analysis.legal_actions:
        raise ValueError("The calculation recommendation must be a legal action.")

    baseline = {item.action: item.frequency for item in analysis.baseline_strategy}
    exploit = {item.action: item.frequency for item in analysis.exploitative_strategy}
    evs = {item.action: item.value for item in analysis.action_evs}
    differences = {item.action: item.value for item in analysis.ev_differences}
    alternatives = tuple(AlternativeAction(
        action=action, ev=evs[action], ev_difference=differences[action],
        baseline_frequency=baseline[action], exploitative_frequency=exploit[action])
        for action in analysis.legal_actions if action != recommended_action)
    adjustment = ExploitativeAdjustment(recommended_action, baseline[recommended_action],
                                         exploit[recommended_action])
    evidence = tuple(EvidenceItem(item.tendency_id, item.value, item.evidence_count,
                                  item.context, item.uncertainty)
                     for item in analysis.opponent_assumptions)

    mathematical = (f"The supplied EV for {recommended_action} is {_chips(evs[recommended_action])}; "
                    f"its supplied EV difference is {_chips(differences[recommended_action])}.")
    if evidence:
        primary = evidence[0]
        evidence_sentence = (f"The calculation used a modeled {_label(primary.tendency_id)} rate of "
                             f"{_pct(primary.value)} from {primary.evidence_count} recorded opportunities "
                             "as the opponent input behind this adjustment.")
        adjustment_sentence = (f"Its frequency for {recommended_action} changes from "
                               f"{_pct(adjustment.baseline_frequency)} in the reference strategy to "
                               f"{_pct(adjustment.exploitative_frequency)} in the opponent-specific strategy.")
    else:
        evidence_sentence = "No opponent-specific tendency was supplied with this analysis."
        adjustment_sentence = (f"The supplied reference and opponent-specific frequencies for "
                               f"{recommended_action} are {_pct(adjustment.baseline_frequency)} and "
                               f"{_pct(adjustment.exploitative_frequency)}, respectively.")

    caution = ""
    if analysis.confidence.casefold() in {"low", "very low", "limited"}:
        caution = " Confidence is low, so treat the opponent-specific adjustment as tentative."
    elif analysis.uncertainty:
        caution = (f" The stated {_pct(analysis.uncertainty.level)} interval is "
                   f"{_pct(analysis.uncertainty.lower)} to {_pct(analysis.uncertainty.upper)}.")

    plain = (f"The poker engine recommends {recommended_action}. {adjustment_sentence} "
             f"{evidence_sentence}{caution}")
    if level is ExplanationLevel.SHORT:
        summary = f"Recommend {recommended_action}: {mathematical}"
    elif level is ExplanationLevel.NORMAL:
        summary = f"{plain} {mathematical}"
    else:
        summary = (f"{plain} {mathematical} Expected value means the average chip result over many "
                   "repetitions; action frequencies describe how often each option is used.")

    caveats = tuple(dict.fromkeys((*analysis.limitations, *analysis.warnings)))
    if not evidence:
        caveats += ("No opponent-model evidence was supplied; no tendency-based cause can be claimed.",)
    primary_assumption = analysis.opponent_assumptions[0] if analysis.opponent_assumptions else None
    facts = ExplanationPayload(
        analysis.analysis_id, recommended_action, analysis.baseline_strategy, adjustment,
        plain, primary_assumption,
        primary_assumption.evidence_count if primary_assumption else 0,
        analysis.uncertainty, differences[recommended_action],
        (MathematicalFact("Recommended action EV", evs[recommended_action], "chips"),
         MathematicalFact("Recommended action EV difference",
                          differences[recommended_action], "chips")), caveats)
    provenance = (
        ProvenanceItem("facts", "solver_output", "ExplanationPayload derived from StrategyAnalysisResult"),
        ProvenanceItem("analysis_id", "solver_output", "StrategyAnalysisResult.analysis_id"),
        ProvenanceItem("recommended_action", "solver_output", "explain() recommended_action argument"),
        ProvenanceItem("alternative_actions", "solver_output", "StrategyAnalysisResult.legal_actions"),
        ProvenanceItem("action_evs", "solver_output", "StrategyAnalysisResult.action_evs"),
        ProvenanceItem("ev_differences", "solver_output", "StrategyAnalysisResult.ev_differences"),
        ProvenanceItem("baseline_strategy", "solver_output", "StrategyAnalysisResult.baseline_strategy"),
        ProvenanceItem("exploitative_strategy", "solver_output", "StrategyAnalysisResult.exploitative_strategy"),
        ProvenanceItem("exploitative_adjustment", "deterministic_formula", "matching action frequencies from both supplied strategies"),
        ProvenanceItem("evidence", "opponent_model", "StrategyAnalysisResult.opponent_assumptions"),
        ProvenanceItem("confidence", "solver_output", "StrategyAnalysisResult.confidence"),
        ProvenanceItem("uncertainty", "opponent_model", "StrategyAnalysisResult.uncertainty"),
        ProvenanceItem("mathematical_reason", "deterministic_formula", "EV fact template v1"),
        ProvenanceItem("plain_language_reason", "deterministic_formula", "strategy comparison template v1"),
        ProvenanceItem("summary", "deterministic_formula", f"{level.value} explanation template v1"),
        ProvenanceItem("caveats", "solver_output", "StrategyAnalysisResult.limitations and warnings"),
        ProvenanceItem("glossary", "deterministic_formula", "beginner terminology definitions v1"),
    )
    return DecisionExplanation(
        analysis_id=analysis.analysis_id, level=level,
        recommended_action=recommended_action, facts=facts,
        alternative_actions=alternatives,
        action_evs=analysis.action_evs, ev_differences=analysis.ev_differences,
        baseline_strategy=analysis.baseline_strategy,
        exploitative_strategy=analysis.exploitative_strategy,
        exploitative_adjustment=adjustment, evidence=evidence,
        confidence=analysis.confidence, uncertainty=analysis.uncertainty,
        mathematical_reason=mathematical, plain_language_reason=plain, summary=summary,
        caveats=caveats, glossary=_glossary() if level is ExplanationLevel.BEGINNER else (),
        provenance=provenance)
