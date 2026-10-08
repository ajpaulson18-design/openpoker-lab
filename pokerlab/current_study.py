"""Safe, bounded presentation view for a pre-action practice estimate."""


SCHEMA_VERSION = 1
SOURCE_LABEL = "Practice estimate · current decision preview"


def build_current_study_view(analysis):
    """Project validated immutable evidence into a small browser-safe shape."""
    if getattr(analysis, "source_kind", None) != "practice_estimate":
        raise ValueError("Current study requires a practice estimate.")

    context = analysis.context
    evs = {item.action_id: item.value for item in analysis.action_evs}
    modeled_actions = []
    for action in analysis.modeled_actions:
        row = {
            "action_id": action.action_id,
            "name": action.name,
            "amount": action.amount,
            "amount_semantics": action.amount_semantics,
            "estimated_ev_chips": evs.get(action.action_id),
        }
        if action.name == "raise":
            legal = next((item for item in analysis.legal_actions
                          if item.name == "raise"), None)
            row["size_note"] = "EV evaluates the minimum legal raise only."
            row["minimum_legal_total"] = legal.minimum_total if legal else None
            row["maximum_legal_total"] = legal.maximum_total if legal else None
        modeled_actions.append(row)

    assumptions = ["Live opponents use random card ranges in the practice estimate."]
    if analysis.opponent_assumptions:
        for assumption in analysis.opponent_assumptions:
            assumptions.append(
                f"Fold-to-bet estimate: {assumption.value:.1%} "
                f"({assumption.evidence_count} observed opportunities; uncertainty remains)."
            )
    else:
        assumptions.append("Without a selected model, fold-to-bet is an illustrative 45% assumption.")

    limitations = list(analysis.limitations)
    limitations.extend(analysis.warnings)
    limitations.append("Equity is sampled; results are estimates, not a solved strategy.")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready",
        "binding": {
            "hand_id": analysis.ref.hand_id,
            "decision_id": analysis.ref.decision_id,
            "evidence_id": analysis.evidence_id,
            "state_revision": analysis.ref.state_revision,
        },
        "source_label": SOURCE_LABEL,
        "heading": "Current turn decision",
        "context": {
            "street": context.street,
            "hero_cards": list(context.hero_cards),
            "board": list(context.board),
            "pot_chips": context.pot,
        },
        "recommended_action_id": analysis.recommended_action_id,
        "modeled_actions": modeled_actions,
        "assumptions": assumptions,
        "limitations": list(dict.fromkeys(limitations)),
    }
