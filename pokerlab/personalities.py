"""Deterministic coaching voices over an immutable explanation result.

Personality rendering is deliberately downstream of poker calculation.  A
renderer can only add prose: the complete ``DecisionExplanation`` is retained
unchanged and guarded by a stable fingerprint.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Protocol, runtime_checkable

from .explanations import DecisionExplanation


class CoachPersonality(str, Enum):
    GRINDER = "grinder"
    CHRONIC_BLUFFER = "chronic_bluffer"
    NIT = "nit"
    MATH_GUY = "math_guy"
    OLD_SCHOOL_PRO = "old_school_pro"


@dataclass(frozen=True, slots=True)
class PersonalityRendering:
    """Presentation text paired with the exact facts that produced it."""

    personality: CoachPersonality
    analysis_id: str
    facts_fingerprint: str
    explanation: DecisionExplanation
    text: str
    source: str = "deterministic"

    def __post_init__(self) -> None:
        if self.analysis_id != self.explanation.analysis_id:
            raise ValueError("A personality rendering cannot change the analysis ID.")
        if self.facts_fingerprint != explanation_fingerprint(self.explanation):
            raise ValueError("A personality rendering cannot change analysis facts.")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Personality text must be a non-empty string.")


def explanation_fingerprint(explanation: DecisionExplanation) -> str:
    """Fingerprint all upstream facts, excluding presentation prose and level."""
    protected = {
        "analysis_id": explanation.analysis_id,
        "recommended_action": explanation.recommended_action,
        "facts": explanation.facts.to_dict(),
        "alternative_actions": [item.to_dict() for item in explanation.alternative_actions],
        "action_evs": [item.to_dict() for item in explanation.action_evs],
        "ev_differences": [item.to_dict() for item in explanation.ev_differences],
        "baseline_strategy": [item.to_dict() for item in explanation.baseline_strategy],
        "exploitative_strategy": [item.to_dict() for item in explanation.exploitative_strategy],
        "exploitative_adjustment": explanation.exploitative_adjustment.to_dict(),
        "evidence": [item.to_dict() for item in explanation.evidence],
        "confidence": explanation.confidence,
        "uncertainty": (explanation.uncertainty.to_dict()
                        if explanation.uncertainty else None),
        "caveats": list(explanation.caveats),
    }
    encoded = json.dumps(protected, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _pct(value: float) -> str:
    return f"{value:.1%}"


def _common_facts(explanation: DecisionExplanation) -> str:
    adjustment = explanation.exploitative_adjustment
    return (f"Recommendation: {explanation.recommended_action}. "
            f"{explanation.mathematical_reason} "
            f"Reference frequency {_pct(adjustment.baseline_frequency)}; "
            f"opponent-specific frequency {_pct(adjustment.exploitative_frequency)}. "
            f"Confidence: {explanation.confidence}.")


def _voice(personality: CoachPersonality, explanation: DecisionExplanation) -> str:
    action = explanation.recommended_action.casefold()
    if personality is CoachPersonality.GRINDER:
        return "Stay disciplined and take the supplied edge without chasing variance."
    if personality is CoachPersonality.CHRONIC_BLUFFER:
        if action in {"fold", "check", "call"}:
            return ("I'd love to turn up the pressure, but the numbers do not support "
                    f"forcing aggression here. Take the {action}.")
        return "Now we can apply pressure—the engine supports the aggressive action."
    if personality is CoachPersonality.NIT:
        if action in {"bet", "raise", "all-in", "all_in", "shove"}:
            return ("My cautious instinct wants another look, but the calculated result "
                    "supports aggression, so follow it.")
        return "Protect the stack and avoid paying off a marginal spot."
    if personality is CoachPersonality.MATH_GUY:
        frequencies = ", ".join(
            f"{item.action} {_pct(item.frequency)}"
            for item in explanation.exploitative_strategy)
        return f"The opponent-specific mix is {frequencies}; keep the decision tied to those inputs."
    return "That's the table read: play the recommended action and don't embroider the evidence."


def render_personality(explanation: DecisionExplanation,
                       personality: CoachPersonality | str) -> PersonalityRendering:
    """Render a local voice without modifying or recalculating analysis facts."""
    personality = CoachPersonality(personality)
    text = f"{_voice(personality, explanation)} {_common_facts(explanation)}"
    return PersonalityRendering(personality, explanation.analysis_id,
                                explanation_fingerprint(explanation), explanation, text)


@runtime_checkable
class ConversationalExplanationProvider(Protocol):
    """Provider-neutral, text-only boundary for an optional future model."""

    def explain(self, payload: dict[str, object], personality: str) -> str:
        """Return presentation prose only; structured facts cannot be returned."""
        ...


@dataclass(frozen=True, slots=True)
class OptionalAIAdapter:
    """Opt-in adapter. Disabled adapters never invoke their provider."""

    provider: ConversationalExplanationProvider | None = None
    enabled: bool = False

    def render(self, explanation: DecisionExplanation,
               personality: CoachPersonality | str) -> PersonalityRendering:
        personality = CoachPersonality(personality)
        fallback = render_personality(explanation, personality)
        if not self.enabled:
            return fallback
        if self.provider is None:
            raise RuntimeError("Optional AI rendering is enabled but no provider was supplied.")
        text = self.provider.explain(explanation.to_dict(), personality.value)
        if not isinstance(text, str) or not text.strip():
            raise TypeError("A conversational provider may return non-empty text only.")
        return PersonalityRendering(personality, explanation.analysis_id,
                                    explanation_fingerprint(explanation), explanation,
                                    text, source="optional_provider")
