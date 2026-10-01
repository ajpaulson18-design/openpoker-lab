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


PRACTICE_ANALYSIS_VERSION = "practice-ev-v1"


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


def analyze_decision(game, opponent: dict[str, Any] | None = None) -> dict[str, Any]:
    """Estimate legal-action EVs without consulting any opponent hole cards."""
    seat = game.actor
    legal = game.legal()
    actions = _legal_actions(legal)
    pot = float(sum(game.committed))
    hero = "".join(game.hands[seat])
    board = "".join(game.board)
    equity = simulate(hero, board, ["random"], trials=600, seed=7919 + len(game.log))
    eq = equity["equity"]
    call = float(legal.get("call") or 0)
    fold_model = .45
    confidence = "illustrative"
    model_version = "no-opponent-model"
    opponent_id = None
    if opponent:
        metric = opponent["metrics"]["fold_to_bet"]
        fold_model = metric["mean"]
        confidence = metric["confidence"]
        model_version = opponent.get("model_version", "beta-opportunity-v1")
        opponent_id = opponent["id"]

    baseline, modeled = {}, {}
    for action in actions:
        if action == "fold":
            baseline[action] = modeled[action] = 0.0
        elif action == "check":
            baseline[action] = modeled[action] = eq * pot
        elif action == "call":
            baseline[action] = modeled[action] = eq * (pot + call) - call
        else:
            investment = max(float(legal["raise_min"] - game.street_bets[seat]), 1.0)
            called_ev = eq * (pot + 2 * investment) - investment
            baseline[action] = .45 * pot + .55 * called_ev
            modeled[action] = fold_model * pot + (1 - fold_model) * called_ev

    recommended = max(actions, key=lambda action: modeled[action])
    baseline_recommended = max(actions, key=lambda action: baseline[action])
    normalized = {
        "street": game.street, "public_cards": list(game.board), "known_cards": list(game.hands[seat]),
        "pot": pot, "stacks": list(game.stacks), "legal_actions": actions,
        "legal": legal, "committed": list(game.committed),
        "street_bets": list(game.street_bets),
        "baseline_actions": baseline, "actions": modeled, "opponent_id": opponent_id,
        "model_version": model_version, "analysis_version": PRACTICE_ANALYSIS_VERSION,
        "equity_seed": equity["seed"], "equity_trials": equity["trials"],
    }
    model_snapshot = None
    if opponent:
        model_snapshot = {
            "opponent_id": opponent["id"], "model_version": model_version,
            "prior_archetype": opponent["profile"], "street": opponent["street"],
            "metrics": opponent["metrics"],
        }
    return {
        "analysis_id": stable_analysis_id(normalized, PRACTICE_ANALYSIS_VERSION),
        "analysis_version": PRACTICE_ANALYSIS_VERSION,
        "recommended": recommended,
        "baseline_recommended": baseline_recommended,
        "actions": modeled,
        "baseline_actions": baseline,
        "equity": equity,
        "confidence": confidence,
        "opponent_id": opponent_id,
        "opponent_model_version": model_version,
        "opponent_model_snapshot": model_snapshot,
        "street": game.street,
        "explanation": (f"{recommended.title()} has the highest estimated EV in this simplified "
                        "checkdown model. The estimate uses only visible board cards and the acting player's cards."),
        "warnings": ["Practice EVs are simplified estimates, not a complete no-limit Hold'em solution."],
    }


def decision_event(game, analysis: dict[str, Any], chosen_action: str,
                   opponent: dict[str, Any] | None = None) -> dict[str, Any]:
    best = analysis["actions"][analysis["recommended"]]
    chosen = analysis["actions"][chosen_action]
    return {
        "street": game.street,
        "public_cards": list(game.board),
        "known_cards": list(game.hands[game.actor]),
        "pot": sum(game.committed),
        "stacks": list(game.stacks),
        "legal_actions": _legal_actions(game.legal()),
        "chosen_action": chosen_action,
        "opponent_id": opponent["id"] if opponent else None,
        "opponent_model_snapshot": analysis.get("opponent_model_snapshot"),
        "ranges_settings": {"opponent_range": "random", "trials": analysis["equity"]["trials"],
                            "seed": analysis["equity"]["seed"]},
        "analysis_at_time": analysis,
        "ev_loss": max(0.0, best - chosen),
        "matched_recommendation": chosen_action == analysis["recommended"],
        "successful_exploit": (chosen_action == analysis["recommended"] and
                               analysis["recommended"] != analysis["baseline_recommended"]),
        "exploit_gain": max(
            0.0, analysis["actions"][analysis["recommended"]]
            - analysis["actions"][analysis["baseline_recommended"]]),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def render_coach_personality(analysis: dict[str, Any],
                             personality: CoachPersonality | str) -> dict[str, Any]:
    """Render a voice strictly downstream of the saved practice calculation."""
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
    rendered = render_personality(explain(contract, recommended), personality)
    return {"personality": rendered.personality.value,
            "analysis_id": rendered.analysis_id,
            "facts_fingerprint": rendered.facts_fingerprint,
            "text": rendered.text, "source": rendered.source}


def summarize(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(decisions, key=lambda item: item["decision_order"])
    losses = [item for item in ordered if item["ev_loss"] > .01]
    exploits = [item for item in ordered if item["successful_exploit"]]
    return {
        "analyzed_decisions": len(ordered),
        "matched_recommendation": sum(item["matched_recommendation"] for item in ordered),
        "meaningful_ev_losses": len(losses),
        "total_ev_loss": sum(item["ev_loss"] for item in ordered),
        "missed_exploitative_opportunities": sum(
            item["analysis_at_time"]["recommended"] != item["analysis_at_time"]["baseline_recommended"]
            and not item["matched_recommendation"] for item in ordered),
        "successful_exploits": len(exploits),
        "biggest_errors": sorted(losses, key=lambda item: item["ev_loss"], reverse=True)[:3],
        "biggest_successful_exploits": sorted(
            exploits, key=lambda item: item.get("exploit_gain", 0), reverse=True)[:3],
    }
