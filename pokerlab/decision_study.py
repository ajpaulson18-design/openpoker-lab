"""Deterministic, bounded study view over validated saved decision evidence."""
from __future__ import annotations

from .contracts import CoachDecisionAnalysis


_SOURCE_LABELS = {
    "practice_estimate": "Practice estimate",
    "restricted_equilibrium": "Restricted equilibrium result",
    "restricted_exploit": "Restricted exploit estimate",
}


def _amount(value: int | float | None) -> str:
    if value is None:
        return ""
    return str(int(value)) if int(value) == value else f"{value:g}"


def _action_label(action) -> str:
    if action.name == "raise" and action.amount is not None:
        return f"raise to {_amount(action.amount)}"
    return action.name


def _choice_label(choice: dict) -> str:
    if choice["name"] == "raise":
        return f"raise to {_amount(choice['amount'])}"
    return choice["name"]


def _bounded_text(value: str, limit: int = 500) -> str:
    return value if len(value) <= limit else value[:limit - 1].rstrip() + "…"


def build_decision_study(analysis: CoachDecisionAnalysis, choice: dict) -> dict:
    """Project validated facts into a small display model; never recalculate."""
    action_values = {item.action_id: item.value for item in analysis.action_evs}
    baseline_values = {item.action_id: item.value for item in analysis.baseline_action_evs}
    actions = []
    for action in analysis.modeled_actions:
        item = {
            "action_id": action.action_id,
            "name": action.name,
            "amount": action.amount,
            "amount_semantics": action.amount_semantics,
        }
        value_key = ("estimated_ev_chips" if analysis.ev_basis == "incremental_decision_chips"
                     else "estimated_ev")
        item[value_key] = action_values.get(action.action_id)
        actions.append(item)

    source_label = _SOURCE_LABELS[analysis.source_kind]
    recommendation = next((item for item in analysis.modeled_actions
                           if item.action_id == analysis.recommended_action_id), None)
    recommendation_label = (_action_label(recommendation)
                             if recommendation is not None else None)
    recommendation_ev = action_values.get(analysis.recommended_action_id)

    baseline = None
    baseline_id = analysis.baseline_recommended_action_id
    if baseline_id is not None and baseline_id in baseline_values:
        baseline_action = next((item for item in analysis.modeled_actions
                                if item.action_id == baseline_id), None)
        baseline_kind = (analysis.reference_policy.kind
                         if analysis.reference_policy is not None else "baseline")
        baseline_label = ("Illustrative baseline" if baseline_kind == "illustrative_argmax"
                          else "Saved baseline")
        baseline_value_key = ("estimated_ev_chips"
                              if analysis.ev_basis == "incremental_decision_chips"
                              else "estimated_ev")
        baseline = {
            "label": baseline_label,
            "recommended_action_id": baseline_id,
            "recommended_action": (_action_label(baseline_action)
                                   if baseline_action is not None else None),
            baseline_value_key: baseline_values[baseline_id],
            "ev_basis": analysis.ev_basis,
        }

    selected_ev = action_values.get(choice.get("assessed_modeled_action_id"))
    ev_gap = None
    if (choice.get("assessment_status") == "assessed"
            and choice.get("ev_loss") is not None
            and recommendation_ev is not None and selected_ev is not None
            and analysis.ev_basis in ("incremental_decision_chips", "half_initial_pot_utility")):
        ev_gap = {
            "selected_action_ev": selected_ev,
            "recommended_action_ev": recommendation_ev,
            "loss": choice["ev_loss"],
            "ev_basis": analysis.ev_basis,
        }

    if choice.get("assessment_status") == "unassessed_size":
        minimum_raise = next((item for item in analysis.modeled_actions
                              if item.name == "raise"), None)
        if minimum_raise is None:
            choice_answer = (f"The exact {_choice_label(choice)} size was not evaluated, "
                             "so no estimated loss is recorded for this choice.")
        else:
            choice_answer = (
                f"The exact {_choice_label(choice)} size was not evaluated. "
                f"The saved model includes {_action_label(minimum_raise)} as a separate alternative; "
                "that alternative's EV does not score the chosen size."
            )
    elif ev_gap is not None:
        choice_answer = (
            f"The saved estimate gives {_choice_label(choice)} an EV of "
            f"{ev_gap['selected_action_ev']:.2f} and its recommendation "
            f"{recommendation_label} an EV of {ev_gap['recommended_action_ev']:.2f}. "
            f"The recorded gap is {ev_gap['loss']:.2f} in {analysis.ev_basis}."
        )
    else:
        choice_answer = (f"The saved analysis assessed {_choice_label(choice)}, "
                         "but its compared EV values are unavailable.")

    if recommendation_label is None:
        estimate_answer = f"The saved {source_label.lower()} has no recommended action."
    else:
        estimate_answer = (f"The saved {source_label.lower()} recommends "
                           f"{recommendation_label}. Values use {analysis.ev_basis}.")

    assumptions = analysis.opponent_assumptions
    if assumptions:
        assumption_text = "; ".join(
            f"{item.tendency_id.replace('_', ' ')}: {item.value:.1%} from "
            f"{item.evidence_count} observed opportunities"
            for item in assumptions[:5]
        )
        if len(assumptions) > 5:
            assumption_text += "; additional saved assumptions omitted"
        assumption_answer = f"Saved opponent assumptions: {assumption_text}."
    else:
        assumption_answer = "No opponent assumption was captured for this decision."
    limit_parts = [f"Saved confidence label: {analysis.quality.confidence_label}.",
                   assumption_answer]
    uncertainty = analysis.quality.opponent_uncertainty
    if uncertainty is not None:
        limit_parts.append(
            f"Reported opponent uncertainty: {uncertainty.confidence} "
            f"({uncertainty.lower:.1%} to {uncertainty.upper:.1%}; {uncertainty.method})."
        )
    solver_quality = None
    if analysis.quality.nash_conv is not None:
        solver_quality = {
            "nash_conv": analysis.quality.nash_conv,
            "exploitability": analysis.quality.exploitability,
            "iterations": analysis.quality.iterations,
            "gap_semantics": analysis.quality.gap_semantics,
            "ev_basis": analysis.ev_basis,
        }
        limit_parts.append(
            f"Saved solver diagnostics: {analysis.quality.iterations} iterations; "
            f"NashConv {analysis.quality.nash_conv}; "
            f"exploitability {analysis.quality.exploitability} "
            f"({analysis.quality.gap_semantics})."
        )
    limitations = list(dict.fromkeys(
        _bounded_text(item) for item in (*analysis.limitations[:10], *analysis.warnings[:10])
    ))
    if limitations:
        limit_parts.extend(limitations)

    return {
        "schema_version": 1,
        "status": "ready",
        "binding": {
            "hand_id": analysis.ref.hand_id,
            "decision_id": analysis.ref.decision_id,
            "evidence_id": analysis.evidence_id,
            "state_revision": analysis.ref.state_revision,
        },
        "heading": f"{analysis.context.street.title()} decision",
        "source_label": source_label,
        "ev_basis": analysis.ev_basis,
        "solver_quality": solver_quality,
        "choice": {
            "name": choice["name"],
            "amount": choice["amount"],
            "amount_semantics": choice["amount_semantics"],
            "assessment_status": choice["assessment_status"],
            "ev_loss": choice["ev_loss"],
        },
        "modeled_actions": actions,
        "recommended_action_id": analysis.recommended_action_id,
        "baseline": baseline,
        "cards": [
            {"id": "estimate", "question": "What does this estimate prefer?",
             "answer": _bounded_text(estimate_answer)},
            {"id": "my_choice", "question": "How was my choice assessed?",
             "answer": _bounded_text(choice_answer)},
            {"id": "limits", "question": "How much should I trust it?",
             "answer": _bounded_text(" ".join(limit_parts), 2000)},
        ],
        "limitations": limitations,
    }
