"""Application-authored teaching notes for validated one-shot coach replies.

Notes are selected from the server-rendered facts for the same saved decision.
They do not use provider prose, the user's question, or new poker calculations.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .coach_grounding import (AnswerBlock, GroundFact, GroundingBinding,
                              GroundingBundle, RenderedCoachReply, ReplyFact)


_SOURCE_LABELS = {
    "practice_estimate": "Practice estimate",
    "restricted_equilibrium": "Restricted equilibrium result",
    "restricted_exploit": "Restricted exploit estimate",
}
_FACT_ID = re.compile(r"^f_[0-9a-f]{64}$")
_TEMPLATE_IDS = {
    "recommendation_scope_v1", "choice_assessed_v1", "choice_unassessed_raise_v1",
    "choice_loss_unavailable_v1", "comparison_shared_basis_v1", "limits_scope_v1",
    "unavailable_recommendation_v1", "unavailable_choice_v1",
    "unavailable_comparison_v1", "unavailable_request_v1",
}
@dataclass(frozen=True, slots=True)
class TeachingNote:
    """A short, immutable note tied to one exact saved decision."""

    template_id: str
    binding: GroundingBinding
    source_label: str
    text: str
    supporting_fact_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("Only teaching-note schema version 1 is supported.")
        if self.template_id not in _TEMPLATE_IDS:
            raise ValueError("Teaching-note template is unsupported.")
        if not isinstance(self.binding, GroundingBinding):
            raise ValueError("Teaching notes require a saved-decision binding.")
        if self.source_label not in _SOURCE_LABELS.values():
            raise ValueError("Teaching-note source is unsupported.")
        if not isinstance(self.text, str) or not self.text.strip() or len(self.text) > 600:
            raise ValueError("Teaching-note text is outside its allowed bounds.")
        if (not isinstance(self.supporting_fact_ids, tuple)
                or not 1 <= len(self.supporting_fact_ids) <= 16
                or any(not isinstance(item, str) or not _FACT_ID.fullmatch(item)
                       for item in self.supporting_fact_ids)
                or len(set(self.supporting_fact_ids)) != len(self.supporting_fact_ids)):
            raise ValueError("Teaching-note citations must be unique saved fact IDs.")

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "template_id": self.template_id,
                "binding": self.binding.to_dict(), "source_label": self.source_label,
                "text": self.text,
                "supporting_fact_ids": list(self.supporting_fact_ids)}


def _verified_visible_facts(bundle: GroundingBundle,
                            reply: RenderedCoachReply) -> dict[str, GroundFact] | None:
    if (not isinstance(bundle, GroundingBundle)
            or not isinstance(reply, RenderedCoachReply)
            or bundle.binding != reply.binding
            or bundle.source_kind != reply.source_kind
            or _SOURCE_LABELS[bundle.source_kind] != reply.source_label):
        return None
    saved = {fact.fact_id: fact for fact in bundle.facts}
    visible: dict[str, GroundFact] = {}
    if not isinstance(reply.blocks, tuple) or any(not isinstance(block, AnswerBlock)
                                                  for block in reply.blocks):
        return None
    for block in reply.blocks:
        if not isinstance(block.facts, tuple):
            return None
        for rendered in block.facts:
            if not isinstance(rendered, ReplyFact):
                return None
            fact = saved.get(rendered.fact_id)
            if (fact is None or rendered.kind != fact.kind or rendered.value != fact.value
                    or rendered.unit != fact.unit
                    or rendered.availability != fact.availability):
                return None
            visible[fact.fact_id] = fact
    return visible


def build_teaching_note(bundle: GroundingBundle,
                        reply: RenderedCoachReply) -> TeachingNote | None:
    """Select at most one local note using only exact facts visible in ``reply``."""
    visible = _verified_visible_facts(bundle, reply)
    if visible is None:
        return None
    by_id = {fact.fact_id: fact for fact in bundle.facts}
    block_kind = {"recommendation": "recommendation", "choice": "choice",
                  "compare": "comparison", "limits": "limits",
                  "unavailable": "unavailable"}.get(reply.intent)
    if block_kind is None:
        return None
    intent_block = next((block for block in reply.blocks if block.kind == block_kind), None)
    if intent_block is None:
        return None
    intent_visible = {fact.fact_id: visible[fact.fact_id]
                      for fact in intent_block.facts}
    by_kind: dict[str, list[GroundFact]] = {}
    for fact in intent_visible.values():
        by_kind.setdefault(fact.kind, []).append(fact)

    def one(kind: str) -> GroundFact | None:
        return next(iter(by_kind.get(kind, ())), None)

    def add(fact: GroundFact | None, supporting: list[GroundFact]) -> bool:
        if fact is None or fact.fact_id not in intent_visible:
            return False
        supporting.append(fact)
        return True

    def finish(template_id: str, text: str,
               supporting: list[GroundFact]) -> TeachingNote | None:
        ids = tuple(dict.fromkeys(fact.fact_id for fact in supporting))
        if (not ids or len(ids) > 16 or len(text) > 600
                or any(fact_id not in intent_visible for fact_id in ids)):
            return None
        return TeachingNote(template_id, bundle.binding, reply.source_label, text, ids)

    if reply.intent == "recommendation":
        recommendation = one("recommendation")
        action = next((fact for fact in by_kind.get("modeled_action", ())
                       if isinstance(fact.value, tuple)
                       and recommendation is not None
                       and fact.value[0] == recommendation.value), None)
        supporting: list[GroundFact] = []
        if not add(recommendation, supporting) or not add(action, supporting):
            return None
        text = ("The saved recommendation is limited to this decision's modeled action set; "
                "it does not cover unmodeled actions.")
        if bundle.source_kind == "practice_estimate":
            text += " This practice estimate is not equilibrium strategy or a guarantee of the best play."
        ev_facts = by_kind.get("action_ev", ())
        if ev_facts:
            text += " Any displayed action EV uses this analysis's saved EV basis."
            supporting.extend(ev_facts)
        return finish("recommendation_scope_v1", text, supporting)

    if reply.intent == "choice":
        choice = one("choice")
        loss = one("choice_loss")
        supporting = []
        if not add(choice, supporting) or not add(loss, supporting):
            return None
        if not isinstance(choice.value, tuple) or len(choice.value) != 6:
            return None
        if choice.value[3] == "unassessed_size":
            text = ("This larger raise size was not assessed. It has no saved EV or loss, "
                    "so an estimate for another raise size is not assigned to it.")
            template_id = "choice_unassessed_raise_v1"
        elif loss.availability == "available" and loss.value is not None:
            text = ("This recorded action was assessed. Its saved loss is relative to the "
                    "saved recommendation on this analysis's EV basis.")
            template_id = "choice_assessed_v1"
        else:
            text = ("The recorded action was assessed, but its saved loss is unavailable. "
                    "No loss is inferred.")
            template_id = "choice_loss_unavailable_v1"
        return finish(template_id, text, supporting)

    if reply.intent == "compare":
        block = next((item for item in reply.blocks if item.kind == "comparison"), None)
        if block is None:
            return None
        facts = list(block.facts)
        choices = [by_id[item.fact_id] for item in facts if item.kind == "choice"]
        action_facts = [by_id[item.fact_id] for item in facts if item.kind == "modeled_action"]
        ev_facts = [by_id[item.fact_id] for item in facts if item.kind == "action_ev"]
        if (len(choices) != 1 or len(action_facts) < 2 or len(ev_facts) != 2
                or any(item.availability != "available" or item.value[1] is None
                       or item.unit != bundle.ev_basis for item in ev_facts)):
            return None
        text = ("These displayed action EVs use the same saved basis and assumptions. "
                "This note does not calculate a new EV difference or compare another analysis.")
        return finish("comparison_shared_basis_v1", text,
                      [choices[0], *action_facts, *ev_facts])

    if reply.intent == "limits":
        source_fact = one("source_kind")
        if source_fact is None or source_fact.value != bundle.source_kind:
            return None
        supporting = [source_fact]
        if bundle.source_kind == "practice_estimate":
            text = ("This practice estimate summarizes the producer's saved actions. "
                    "It is not equilibrium strategy or a guaranteed best play.")
        elif bundle.source_kind == "restricted_equilibrium":
            text = ("This result applies to the producer's restricted equilibrium model "
                    "for this decision; it does not describe unrestricted Hold'em strategy.")
        else:
            text = "This is a restricted exploit estimate for the saved decision."

        opponent_facts = list(by_kind.get("opponent_assumption", ()))
        opponent_uncertainty = one("opponent_uncertainty")
        if opponent_facts:
            text += (" Recorded opponent assumptions are model inputs, not verified "
                     "facts about the opponent.")
            supporting.extend(opponent_facts)
        if opponent_uncertainty is not None and opponent_uncertainty.value is not None:
            text += (" Opponent-model uncertainty concerns the recorded behavior model, "
                     "not hidden cards.")
            supporting.append(opponent_uncertainty)

        equity_standard_error = one("equity_standard_error")
        if (equity_standard_error is not None
                and equity_standard_error.availability == "available"
                and equity_standard_error.value is not None):
            text += " The equity calculation reports a standard error for sampling uncertainty."
            supporting.append(equity_standard_error)
        equity_exact = one("equity_exact")
        if equity_exact is not None and type(equity_exact.value) is bool:
            text += (" The equity calculation is marked exact." if equity_exact.value
                     else " The equity calculation is marked non-exact.")
            supporting.append(equity_exact)

        solver_gap_facts = [fact for kind in ("solver_nash_conv", "solver_exploitability",
                                              "solver_gap_semantics")
                            for fact in by_kind.get(kind, ()) if fact.value is not None]
        solver_iteration_facts = [fact for fact in by_kind.get("solver_iterations", ())
                                  if fact.value is not None]
        if solver_gap_facts:
            text += " Solver-gap diagnostics describe the configured solve."
            supporting.extend(solver_gap_facts)
        if solver_iteration_facts:
            text += " Solver iteration count describes the configured solve."
            supporting.extend(solver_iteration_facts)

        categories = sum((bool(opponent_facts or (opponent_uncertainty is not None
                                                   and opponent_uncertainty.value is not None)),
                          bool((equity_standard_error is not None
                                and equity_standard_error.value is not None)
                               or (equity_exact is not None and type(equity_exact.value) is bool)),
                          bool(solver_gap_facts or solver_iteration_facts)))
        if categories >= 2:
            text += " These are separate measures, not one combined confidence score."
        return finish("limits_scope_v1", text, supporting)

    if reply.intent == "unavailable":
        supporting = []
        source_fact = one("source_kind")
        requested = reply.requested_intent
        if requested == "recommendation" and "recommendation" in reply.unavailable_fields:
            if not add(one("recommendation"), supporting):
                if not add(source_fact, supporting):
                    return None
            text = ("The saved recommendation was unavailable (marker: recommendation). "
                    "No substitute action or estimate is inferred.")
            return finish("unavailable_recommendation_v1", text, supporting)
        if requested == "choice" and "choice" in reply.unavailable_fields:
            if not add(source_fact, supporting):
                return None
            text = ("The saved choice was unavailable (marker: choice). "
                    "No loss or comparison is inferred.")
            return finish("unavailable_choice_v1", text, supporting)
        if requested == "compare":
            choice = one("choice")
            choice_status = (choice.value[3] if choice is not None
                             and isinstance(choice.value, tuple) and len(choice.value) == 6
                             else None)
            marker = ("choice_action_not_modeled" if choice_status != "assessed"
                      else "comparison_ev")
            if marker not in reply.unavailable_fields:
                return None
            if not add(choice, supporting) and not add(source_fact, supporting):
                return None
            if marker == "choice_action_not_modeled":
                text = ("The recorded choice could not be compared with a modeled action "
                        "(marker: choice_action_not_modeled). No substitute raise size or EV is inferred.")
                return finish("unavailable_choice_v1", text, supporting)
            text = ("The requested comparison was not measured (marker: comparison_ev). "
                    "No replacement action or EV is inferred.")
            return finish("unavailable_comparison_v1", text, supporting)
        if requested == "unavailable":
            if not add(source_fact, supporting):
                return None
            text = ("No recommendation or comparison was rendered for this request. "
                    "No substitute action or EV is inferred.")
            return finish("unavailable_request_v1", text, supporting)
    return None
