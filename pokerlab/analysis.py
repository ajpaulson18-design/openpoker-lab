"""Transparent one-decision EV estimates, distinct from equilibrium solving."""
import math
from .equity import simulate


def number(value, label, low=0, high=1_000_000):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number.")
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{label} must be between {low} and {high}.")
    return result


def analyze(data, opponent=None):
    pot = number(data.get("pot", 100), "Pot", 0.01)
    call = number(data.get("to_call", 0), "Amount to call")
    bet = number(data.get("bet", 50), "Bet size", 0.01)
    eq = simulate(data.get("hero", ""), data.get("board", ""),
                  [data.get("range", "random")], data.get("trials", 5000), data.get("seed", 42))
    equity = eq["equity"]
    warnings = ["Ranges are supplied by you; aggregate tendencies do not identify an opponent's hidden cards.",
                "EV assumes heads-up play, no rake, no raises, and no further betting after a call."]
    if not eq["exact"]:
        warnings.append("Before the river, these are checkdown EV estimates, not full-street strategy solutions.")
    if call:
        actions = {"fold": 0, "call": equity*(pot+call)-call}
        baseline = dict(actions)
        explanation = f"Calling needs {call/(pot+call):.1%} equity against the entered betting range. The current pot must include the opponent's bet."
        fold_rate = None
    else:
        baseline_fold = .45
        model = opponent["metrics"]["fold_to_bet"] if opponent else None
        fold_rate = number(data.get("fold_rate", model["mean"] if model else baseline_fold), "Fold rate", 0, 1)
        # Separate continuation range avoids assuming calls are a random subset.
        continuation = data.get("continue_range", "").strip()
        called = simulate(data["hero"], data.get("board", ""), [continuation],
                          data.get("trials", 5000), data.get("seed", 42)) if continuation else eq
        if not continuation:
            warnings.append("No calling range supplied: callers are assumed to have the same range as checkers. This can overvalue bets.")
        called_ev = called["equity"]*(pot+2*bet)-bet
        actions = {"check": equity*pot, "bet": fold_rate*pot+(1-fold_rate)*called_ev}
        baseline = {"check": equity*pot, "bet": baseline_fold*pot+(1-baseline_fold)*called_ev}
        explanation = f"The modeled fold rate is {fold_rate:.1%}; called equity is {called['equity']:.1%}. The baseline uses an illustrative 45% fold rate, not GTO."
        if model and "fold_rate" not in data:
            lo, hi = model["interval95"]
            sensitivity = sorted([f*pot+(1-f)*called_ev for f in (lo, hi)])
            warnings.append(f"Using the fold-rate interval alone puts bet EV between {sensitivity[0]:.2f} and {sensitivity[1]:.2f}; range uncertainty is additional.")
    return {"equity": eq, "actions": actions, "baseline_actions": baseline,
            "recommended": max(actions, key=actions.get), "fold_rate": fold_rate,
            "explanation": explanation, "warnings": warnings,
            "method": "one-decision EV model", "units": "same chips as input"}
