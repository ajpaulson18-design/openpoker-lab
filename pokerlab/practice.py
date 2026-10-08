"""Deterministic, hidden-information-safe analysis for practice decisions."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .contracts import (ActionFrequency, ActionValue, OpponentAssumption,
                        StrategyAnalysisResult, TendencyContext, Uncertainty,
                        stable_analysis_id)
from .equity import simulate
from .explanations import explain
from .personalities import CoachPersonality, render_personality


PRACTICE_ANALYSIS_VERSION = "practice-ev-v3"


def visible_state(game, hero_seat: int = 0) -> dict[str, Any]:
    """Return a single-user view that never serializes opponents' hole cards."""
    state = game.state()
    state["hands"] = [list(hand) if seat == hero_seat else None
                      for seat, hand in enumerate(game.hands)]
    return state


def advance_to_hero(game, hero_seat: int = 0) -> None:
    """Deterministically check/call non-hero seats until the hero acts or the hand ends."""
    while not game.done and game.actor != hero_seat:
        legal = game.legal()
        action = "check" if legal.get("check") else "call" if legal.get("call") else "fold"
        game.act(action)


def _legal_actions(legal: dict[str, Any]) -> list[str]:
    return [name for name in ("fold", "check", "call", "raise") if legal.get(name)]


def _calculate_analysis(inputs: dict[str, Any]) -> dict[str, Any]:
    """Calculate from a complete, persisted, hidden-information-safe input set."""
    legal = inputs["legal"]
    actions = list(inputs["legal_actions"])
    pot = float(inputs["pot"])
    hero = "".join(inputs["known_cards"])
    board = "".join(inputs["public_cards"])
    equity = simulate(hero, board, inputs["opponent_ranges"],
                      trials=inputs["equity_trials"], seed=inputs["equity_seed"])
    eq = equity["equity"]
    call = float(legal.get("call") or 0)
    fold_model = inputs["fold_to_bet"]
    confidence = inputs["confidence"]
    model_version = inputs["opponent_model_version"]
    opponent_id = inputs["opponent_id"]

    baseline, modeled = {}, {}
    for action in actions:
        if action == "fold":
            baseline[action] = modeled[action] = 0.0
        elif action == "check":
            baseline[action] = modeled[action] = eq * pot
        elif action == "call":
            baseline[action] = modeled[action] = eq * (pot + call) - call
        else:
            investment = max(float(legal["raise_min"] - inputs["actor_street_bet"]), 1.0)
            called_ev = eq * (pot + 2 * investment) - investment
            baseline[action] = .45 * pot + .55 * called_ev
            modeled[action] = fold_model * pot + (1 - fold_model) * called_ev

    recommended = max(actions, key=lambda action: modeled[action])
    baseline_recommended = max(actions, key=lambda action: baseline[action])
    warnings = [
        "Practice EVs are simplified estimates, not a complete no-limit Hold'em solution.",
        ("Showdown equity includes every live opponent. Raise EV still uses a simplified "
         "independent-fold, at-most-one-caller response model."),
    ]
    protected_facts = {
        "analysis_inputs": inputs,
        "baseline_actions": baseline, "actions": modeled, "opponent_id": opponent_id,
        "recommended": recommended, "baseline_recommended": baseline_recommended,
        "confidence": confidence, "opponent_model_snapshot": inputs["opponent_model_snapshot"],
        "equity": equity, "warnings": warnings,
    }
    return {
        "analysis_id": stable_analysis_id(protected_facts, PRACTICE_ANALYSIS_VERSION),
        "analysis_version": PRACTICE_ANALYSIS_VERSION,
        "analysis_inputs": inputs,
        "recommended": recommended,
        "baseline_recommended": baseline_recommended,
        "actions": modeled,
        "baseline_actions": baseline,
        "equity": equity,
        "confidence": confidence,
        "opponent_id": opponent_id,
        "opponent_model_version": model_version,
        "opponent_model_snapshot": inputs["opponent_model_snapshot"],
        "street": inputs["street"],
        "explanation": (f"{recommended.title()} has the highest estimated EV in this simplified "
                        "checkdown model. The estimate uses only visible board cards and the acting player's cards."),
        "warnings": warnings,
    }


def decision_event(game, analysis: dict[str, Any], chosen_action: str,
                   opponent: dict[str, Any] | None = None,
                   amount: int | None = None) -> dict[str, Any]:
    legal = game.legal()
    if chosen_action == "raise":
        if type(amount) is not int or not legal["raise_min"] <= amount <= legal["raise_max"]:
            raise ValueError("Raise to a legal integer street total.")
        choice_amount = amount
        amount_semantics = "street_total"
        assessed = amount == legal["raise_min"]
        modeled_action_id = "raise:min" if assessed else None
    elif chosen_action in ("fold", "check"):
        choice_amount = 0
        amount_semantics = "chips_added"
        assessed = True
        modeled_action_id = chosen_action
    elif chosen_action == "call" and legal.get("call"):
        choice_amount = legal["call"]
        amount_semantics = "chips_added"
        assessed = True
        modeled_action_id = chosen_action
    else:
        raise ValueError("That action is not legal here.")
    best = analysis["actions"][analysis["recommended"]]
    chosen_name = "raise" if chosen_action == "raise" else chosen_action
    chosen = analysis["actions"].get(chosen_name) if assessed else None
    loss = max(0.0, best - chosen) if assessed else None
    matched = (chosen_name == analysis["recommended"]) if assessed else None
    successful_exploit = (matched and
                          analysis["recommended"] != analysis["baseline_recommended"]
                          if assessed else None)
    exploit_gain = (max(0.0, analysis["actions"][analysis["recommended"]]
                        - analysis["actions"][analysis["baseline_recommended"]])
                    if assessed else None)
    return {
        "street": game.street,
        "actor": game.actor,
        "button": game.button,
        "public_cards": list(game.board),
        "known_cards": list(game.hands[game.actor]),
        "pot": sum(game.committed),
        "stacks": list(game.stacks),
        "legal_actions": _legal_actions(game.legal()),
        "legal_action_details": dict(game.legal()),
        "committed": list(game.committed),
        "street_bets": list(game.street_bets),
        "current_bet": game.current_bet,
        "min_raise": game.min_raise,
        "chosen_action": chosen_action,
        "chosen_action_detail": {"name": chosen_action, "amount": choice_amount,
                                 "amount_semantics": amount_semantics},
        "assessed_modeled_action_id": modeled_action_id,
        "assessment_status": "assessed" if assessed else "unassessed_size",
        "opponent_id": opponent["id"] if opponent else None,
        "opponent_model_snapshot": analysis.get("opponent_model_snapshot"),
        "ranges_settings": {"opponent_ranges": list(analysis["analysis_inputs"]["opponent_ranges"]),
                            "trials": analysis["equity"]["trials"],
                            "seed": analysis["equity"]["seed"]},
        "analysis_at_time": analysis,
        "analysis_inputs": analysis["analysis_inputs"],
        "ev_loss": loss,
        "matched_recommendation": matched,
        "successful_exploit": successful_exploit,
        "exploit_gain": exploit_gain,
        "pre_action_history": [
            {"seat": item["seat"], "street": item["street"],
             "action": item["action"],
             "raise_total": item.get("amount") if item["action"] == "raise" else None}
            for item in game.log
        ],
        "folded_flags": list(game.folded),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def analyze_recorded_decision(inputs: dict[str, Any]) -> dict[str, Any]:
    """Recalculate a historical decision from its versioned saved inputs."""
    if not isinstance(inputs, dict) or inputs.get("analysis_version") != PRACTICE_ANALYSIS_VERSION:
        raise ValueError("Unsupported or malformed practice-analysis inputs.")
    required = {
        "street", "public_cards", "known_cards", "pot", "stacks", "legal_actions",
        "legal", "committed", "street_bets", "actor", "button", "current_bet",
        "min_raise", "actor_street_bet", "opponent_ranges", "equity_seed",
        "equity_trials", "fold_to_bet", "confidence", "opponent_id",
        "opponent_model_version", "opponent_model_snapshot",
    }
    if required - inputs.keys():
        raise ValueError("Practice-analysis inputs are incomplete.")
    return _calculate_analysis(inputs)


def analyze_decision(game, opponent: dict[str, Any] | None = None) -> dict[str, Any]:
    """Estimate legal-action EVs without consulting any opponent hole cards."""
    seat = game.actor
    legal = game.legal()
    metric = opponent["metrics"]["fold_to_bet"] if opponent else None
    model_version = (opponent.get("model_version", "beta-opportunity-v1")
                     if opponent else "no-opponent-model")
    model_snapshot = None
    if opponent:
        model_snapshot = {
            "opponent_id": opponent["id"], "model_version": model_version,
            "prior_archetype": opponent["profile"], "street": opponent["street"],
            "metrics": opponent["metrics"],
        }
    inputs = {
        "analysis_version": PRACTICE_ANALYSIS_VERSION,
        "street": game.street,
        "public_cards": list(game.board),
        "known_cards": list(game.hands[seat]),
        "pot": float(sum(game.committed)),
        "stacks": list(game.stacks),
        "legal_actions": _legal_actions(legal),
        "legal": dict(legal),
        "committed": list(game.committed),
        "street_bets": list(game.street_bets),
        "actor": seat,
        "button": game.button,
        "current_bet": game.current_bet,
        "min_raise": game.min_raise,
        "actor_street_bet": game.street_bets[seat],
        "opponent_ranges": ["random" for other_seat, folded in enumerate(game.folded)
                            if other_seat != seat and not folded],
        "equity_seed": 7919 + len(game.log),
        "equity_trials": 600,
        "fold_to_bet": metric["mean"] if metric else .45,
        "confidence": metric["confidence"] if metric else "illustrative",
        "opponent_id": opponent["id"] if opponent else None,
        "opponent_model_version": model_version,
        "opponent_model_snapshot": model_snapshot,
    }
    return _calculate_analysis(inputs)


def build_coach_explanation(analysis: dict[str, Any]):
    """Build the structured deterministic explanation used by the coach UI."""
    legal = tuple(analysis["actions"])
    baseline = analysis["baseline_recommended"]
    recommended = analysis["recommended"]
    best = analysis["actions"][recommended]
    uncertainty = None
    assumptions = ()
    snapshot = analysis.get("opponent_model_snapshot")
    if snapshot:
        modeled = snapshot["metrics"]["fold_to_bet"]
        uncertainty = Uncertainty(
            modeled["interval95"][0], modeled["interval95"][1], .95,
            modeled["interval_method"], modeled["confidence"])
        assumptions = (OpponentAssumption(
            "fold_to_bet", TendencyContext(analysis["street"]), modeled["mean"],
            modeled["observations"], uncertainty),)
    contract = StrategyAnalysisResult(
        analysis_id=analysis["analysis_id"], legal_actions=legal,
        baseline_strategy=tuple(ActionFrequency(action, float(action == baseline))
                                for action in legal),
        exploitative_strategy=tuple(ActionFrequency(action, float(action == recommended))
                                    for action in legal),
        action_evs=tuple(ActionValue(action, analysis["actions"][action]) for action in legal),
        ev_differences=tuple(ActionValue(action, analysis["actions"][action] - best)
                             for action in legal),
        opponent_assumptions=assumptions, confidence=analysis["confidence"],
        uncertainty=uncertainty, solver_version=analysis["analysis_version"],
        model_version=analysis["opponent_model_version"],
        limitations=tuple(analysis["warnings"]),
    )
    return explain(contract, recommended)


def render_coach_personality(analysis: dict[str, Any],
                             personality: CoachPersonality | str) -> dict[str, Any]:
    """Render a voice strictly downstream of the saved practice calculation."""
    rendered = render_personality(build_coach_explanation(analysis), personality)
    return {"personality": rendered.personality.value,
            "analysis_id": rendered.analysis_id,
            "facts_fingerprint": rendered.facts_fingerprint,
            "text": rendered.text, "source": rendered.source}


def summarize(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(decisions, key=lambda item: item["decision_order"])
    def unassessed(item):
        if item.get("assessment_status") == "unassessed_size":
            return True
        return item.get("chosen_action") == "raise" and not isinstance(
            item.get("chosen_action_detail"), dict)

    assessed = [item for item in ordered if not unassessed(item)]
    losses = [item for item in assessed if item.get("ev_loss") is not None
              and item["ev_loss"] > .01]
    exploits = [item for item in assessed if item.get("successful_exploit")]
    return {
        "analyzed_decisions": len(ordered),
        "assessed_decisions": len(assessed),
        "unassessed_decisions": len(ordered) - len(assessed),
        "matched_recommendation": sum(bool(item.get("matched_recommendation")) for item in assessed),
        "meaningful_ev_losses": len(losses),
        "total_ev_loss": sum(item["ev_loss"] or 0 for item in assessed),
        "missed_exploitative_opportunities": sum(
            item["analysis_at_time"]["recommended"] != item["analysis_at_time"]["baseline_recommended"]
            and not item.get("matched_recommendation") for item in assessed),
        "successful_exploits": len(exploits),
        "biggest_errors": sorted(losses, key=lambda item: item["ev_loss"], reverse=True)[:3],
        "biggest_successful_exploits": sorted(
            exploits, key=lambda item: item.get("exploit_gain", 0), reverse=True)[:3],
    }
