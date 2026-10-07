"""Safe adapter from saved practice estimates to versioned coach evidence."""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .cards import cards
from .contracts import (ActionFrequency, CoachAction, CoachActionValue,
                       CoachAnalysisError, CoachAnalysisQuality,
                       CoachDecisionAnalysis, CoachDecisionContext,
                       CoachDecisionRef, CoachPolicy, CoachProvenance,
                       OpponentAssumption, TendencyContext, Uncertainty)


COACH_PRACTICE_ADAPTER_VERSION = "coach-practice-adapter-v1"
_PRODUCER_VERSION = "practice-ev-v3"
_ACTION_ORDER = ("fold", "check", "call", "raise")
_LIMITATIONS = (
    "Practice action EVs are simplified estimates, not equilibrium solver output.",
    "Practice policies encode supplied argmax recommendations, not equilibrium mixing frequencies.",
    "The modeled raise evaluates only the minimum legal street total; other raise sizes are unassessed.",
)
_UNAVAILABLE = (
    "action_history", "folded_flags", "effective_stack", "chosen_action",
    "solver_convergence", "conditional_ranges",
)


def _fail(message: str) -> None:
    raise CoachAnalysisError("invalid_analysis", message)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label} must be an object.")
    return value


def _field(value: Mapping[str, Any], name: str, label: str | None = None) -> Any:
    if name not in value:
        _fail(f"Missing {label or name}.")
    return value[name]


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label} must be non-empty text.")
    return value


def _finite(value: Any, label: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail(f"{label} must be a finite number.")
    if minimum is not None and value < minimum:
        _fail(f"{label} is outside its allowed range.")
    return float(value)


def _int(value: Any, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail(f"{label} must be a non-negative integer.")
    return value


def _sequence(value: Any, label: str) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        _fail(f"{label} must be an array.")
    return tuple(value)


def _json_pointer(path: str) -> str:
    return "/" + "/".join(part.replace("~", "~0").replace("/", "~1")
                             for part in path.split("/"))


class _ProvenanceBuilder:
    def __init__(self) -> None:
        self.rows: dict[str, CoachProvenance] = {}

    def add(self, path: str, origin: str, source: str) -> None:
        pointer = _json_pointer(path)
        self.rows[pointer] = CoachProvenance(pointer, origin, source)

    def leaves(self, prefix: str, value: Any, origin: str, source: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                self.leaves(f"{prefix}/{key}", child, origin, source)
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                self.leaves(f"{prefix}/{index}", child, origin, source)
        else:
            self.add(prefix, origin, source)

    def build(self) -> tuple[CoachProvenance, ...]:
        return tuple(self.rows[key] for key in sorted(self.rows))


def _validate_context(inputs: Mapping[str, Any]) -> CoachDecisionContext:
    street = _text(_field(inputs, "street"), "Street")
    if street not in ("preflop", "flop", "turn", "river"):
        _fail("Street is unsupported.")
    try:
        hero = cards(_sequence(_field(inputs, "known_cards"), "Hero cards"), 2)
        board = cards(_sequence(_field(inputs, "public_cards"), "Board"))
    except (ValueError, TypeError):
        _fail("Visible cards are malformed.")
    if len(board) not in (0, 3, 4, 5):
        _fail("Board must contain 0, 3, 4, or 5 cards.")
    expected = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(board)]
    if street != expected:
        _fail("Street must match the visible board length.")
    pot = _finite(_field(inputs, "pot"), "Pot", 0)
    committed = tuple(_int(item, "Contribution") for item in _sequence(
        _field(inputs, "committed"), "Contributions"))
    stacks = tuple(_int(item, "Stack") for item in _sequence(
        _field(inputs, "stacks"), "Stacks"))
    street_bets = tuple(_int(item, "Street contribution") for item in _sequence(
        _field(inputs, "street_bets"), "Street contributions"))
    if not 2 <= len(stacks) <= 6 or len(committed) != len(stacks) or len(street_bets) != len(stacks):
        _fail("Seat arrays must contain 2–6 entries with matching lengths.")
    if any(bet > total for bet, total in zip(street_bets, committed)):
        _fail("Street contributions cannot exceed total contributions.")
    if not math.isclose(pot, sum(committed), rel_tol=0, abs_tol=1e-9):
        _fail("Pot must equal the total recorded contributions.")
    actor = _int(_field(inputs, "actor"), "Actor seat")
    button = _int(_field(inputs, "button"), "Button seat")
    if actor >= len(stacks) or button >= len(stacks):
        _fail("Actor and button seats must exist in the hand.")
    current_bet = _finite(_field(inputs, "current_bet"), "Current bet", 0)
    min_raise = _finite(_field(inputs, "min_raise"), "Minimum raise", 0.000000001)
    return CoachDecisionContext(
        street, tuple(hero), tuple(board), pot, "current_committed", actor, None,
        button, stacks, street_bets, committed, current_bet, min_raise)


def _action_sets(analysis: Mapping[str, Any], inputs: Mapping[str, Any]
                 ) -> tuple[tuple[CoachAction, ...], tuple[CoachAction, ...],
                            dict[str, str], tuple[CoachActionValue, ...],
                            tuple[CoachActionValue, ...]]:
    legal = _mapping(_field(inputs, "legal"), "Legal action details")
    for flag in ("fold", "check", "raise"):
        if type(_field(legal, flag)) is not bool:
            _fail("Legal action flags must be boolean.")
    call_amount = _int(_field(legal, "call"), "Call amount")
    minimum_total = _int(_field(legal, "raise_min"), "Minimum raise total")
    maximum_total = _int(_field(legal, "raise_max"), "Maximum raise total")
    if minimum_total > maximum_total:
        _fail("Minimum raise total cannot exceed maximum total.")
    if call_amount:
        if legal["check"] or not legal["fold"]:
            _fail("Call, check and fold legality are inconsistent.")
    elif not legal["check"]:
        _fail("A zero call amount must permit checking.")

    names = tuple(name for name in _ACTION_ORDER
                  if name != "call" and legal.get(name))
    if call_amount:
        names = tuple(name for name in _ACTION_ORDER if name in (*names, "call"))
    supplied = _sequence(_field(inputs, "legal_actions"), "Legal action names")
    if any(not isinstance(item, str) for item in supplied) or len(supplied) != len(set(supplied)):
        _fail("Legal action names must be unique strings.")
    if tuple(supplied) != names:
        _fail("Analysis legal actions must match the game action details in canonical order.")

    legal_actions: list[CoachAction] = []
    modeled_actions: list[CoachAction] = []
    action_ids: dict[str, str] = {}
    for name in names:
        if name == "raise":
            legal_action = CoachAction("raise", "raise", None, "street_total",
                                       minimum_total, maximum_total)
            modeled = CoachAction("raise:min", "raise", minimum_total, "street_total")
        else:
            amount = 0 if name in ("fold", "check") else call_amount
            legal_action = CoachAction(name, name, amount, "chips_added")
            modeled = legal_action
        legal_actions.append(legal_action)
        modeled_actions.append(modeled)
        action_ids[name] = modeled.action_id

    def values_for(key: str) -> tuple[CoachActionValue, ...]:
        raw = _mapping(_field(analysis, key), key)
        if set(raw) != set(names):
            _fail(f"{key} must cover every legal action exactly once.")
        return tuple(CoachActionValue(action_ids[name], _finite(raw[name], f"{key} value"))
                     for name in names)

    action_values = values_for("actions")
    baseline_values = values_for("baseline_actions")
    return (tuple(legal_actions), tuple(modeled_actions), action_ids,
            action_values, baseline_values)


def _read_assumption(analysis: Mapping[str, Any], inputs: Mapping[str, Any],
                     action_ids: Mapping[str, str]) -> tuple[tuple[OpponentAssumption, ...],
                                                             Uncertainty | None, Mapping[str, Any] | None]:
    if "raise" not in action_ids:
        return (), None, None
    snapshot = inputs.get("opponent_model_snapshot")
    if snapshot is None:
        if inputs.get("opponent_id") is not None:
            _fail("Opponent analysis snapshot is unavailable.")
        return (), None, None
    snapshot = _mapping(snapshot, "Opponent analysis snapshot")
    if snapshot.get("street") != inputs["street"]:
        _fail("Opponent snapshot street does not match the analyzed decision.")
    snapshot_version = _text(snapshot.get("model_version"), "Opponent model version")
    metrics = _mapping(snapshot.get("metrics"), "Opponent metrics")
    metric = _mapping(metrics.get("fold_to_bet"), "Fold-to-bet estimate")
    mean = _finite(metric.get("mean"), "Modeled fold-to-bet rate", 0)
    if mean > 1 or not math.isclose(mean, _finite(inputs.get("fold_to_bet"),
                                                  "Calculation fold-to-bet rate", 0),
                                     rel_tol=0, abs_tol=1e-12):
        _fail("Consumed fold-to-bet value does not match its opponent-model source.")
    observations = _int(metric.get("observations"), "Opponent evidence count")
    interval = _sequence(metric.get("interval95"), "Opponent uncertainty interval")
    if len(interval) != 2:
        _fail("Opponent uncertainty interval must have two bounds.")
    method = _text(metric.get("interval_method"), "Opponent interval method")
    confidence = _text(metric.get("confidence"), "Opponent confidence")
    try:
        uncertainty = Uncertainty(_finite(interval[0], "Lower uncertainty bound", 0),
                                 _finite(interval[1], "Upper uncertainty bound", 0),
                                 .95, method, confidence)
        assumption = OpponentAssumption("fold_to_bet", TendencyContext(street=inputs["street"]),
                                        mean, observations, uncertainty)
    except (TypeError, ValueError):
        _fail("Opponent model uncertainty is malformed.")
    if snapshot_version != _text(inputs.get("opponent_model_version"), "Opponent model version"):
        _fail("Opponent model version does not match the decision analysis.")
    return (assumption,), uncertainty, metric


def _provenance(context: CoachDecisionContext, legal: tuple[CoachAction, ...],
                modeled: tuple[CoachAction, ...], reference: CoachPolicy,
                policy: CoachPolicy, action_evs: tuple[CoachActionValue, ...],
                baseline_evs: tuple[CoachActionValue, ...],
                assumptions: tuple[OpponentAssumption, ...], quality: CoachAnalysisQuality,
                limitations: tuple[str, ...], warnings: tuple[str, ...],
                inputs: Mapping[str, Any], metric: Mapping[str, Any] | None
                ) -> tuple[CoachProvenance, ...]:
    out = _ProvenanceBuilder()
    context_values = context.to_dict()
    for path, value in context_values.items():
        if path in ("pot_basis", "actor_role"):
            out.add(f"context/{path}", "derived_application", "practice adapter context normalization")
        else:
            out.leaves(f"context/{path}", value, "game_state",
                       f"analysis_inputs/{'known_cards' if path == 'hero_cards' else 'public_cards' if path == 'board' else path}")
    for index, action in enumerate(legal):
        value = action.to_dict()
        for key in value:
            synthesized_amount = key == "amount" and action.name in ("fold", "check")
            origin = ("derived_application" if key in ("action_id", "amount_semantics")
                      or synthesized_amount else "game_state")
            source = ("practice adapter legality normalization" if origin == "derived_application"
                      else f"analysis_inputs/legal/{action.name}/{key}")
            out.add(f"legal_actions/{index}/{key}", origin, source)
    for index, action in enumerate(modeled):
        for key, value in action.to_dict().items():
            if key in ("action_id", "amount_semantics") or (action.name == "raise" and key == "amount"):
                origin, source = "derived_application", "practice adapter modeled-action projection"
            else:
                origin, source = "game_state", f"analysis_inputs/legal/{action.name}/{key}"
            out.add(f"modeled_actions/{index}/{key}", origin, source)
    for prefix, value in (("reference_policy", reference.to_dict()),
                          ("modeled_policy", policy.to_dict())):
        for index, frequency in enumerate(value["frequencies"]):
            out.add(f"{prefix}/frequencies/{index}/action", "derived_application",
                    "upstream recommendation mapped to modeled action ID")
            out.add(f"{prefix}/frequencies/{index}/frequency", "derived_application",
                    "one-hot encoding of supplied upstream recommendation")
        out.add(f"{prefix}/kind", "derived_application", "practice policy semantics")
    for prefix, entries, producer_key in (("action_evs", action_evs, "actions"),
                                          ("baseline_action_evs", baseline_evs, "baseline_actions")):
        for index, entry in enumerate(entries):
            out.add(f"{prefix}/{index}/action_id", "derived_application",
                    "practice action name mapped to modeled action ID")
            source_name = "raise" if entry.action_id == "raise:min" else entry.action_id
            out.add(f"{prefix}/{index}/value", "analysis_output",
                    f"analysis_output/{producer_key}/{source_name}")
    out.add("recommended_action_id", "derived_application", "practice recommended action mapping")
    out.add("baseline_recommended_action_id", "derived_application", "practice baseline recommendation mapping")
    out.add("ev_basis", "derived_application", "practice EV basis declaration")
    for index, value in enumerate(inputs["opponent_ranges"]):
        out.add(f"opponent_ranges/{index}", "analysis_output", f"analysis_inputs/opponent_ranges/{index}")
    if assumptions:
        for key, value in assumptions[0].to_dict().items():
            out.leaves(f"opponent_assumptions/0/{key}", value, "opponent_model",
                       "analysis_inputs/opponent_model_snapshot/metrics/fold_to_bet")
        if metric is not None:
            out.add("opponent_assumptions/0/value", "opponent_model",
                    "analysis_inputs/opponent_model_snapshot/metrics/fold_to_bet/mean")
    for key, value in quality.to_dict().items():
        source = ("analysis_inputs/opponent_model_snapshot/metrics/fold_to_bet" if key == "opponent_uncertainty"
                  else "equity" if key.startswith("equity_") else "analysis_output/confidence")
        origin = "opponent_model" if key == "opponent_uncertainty" else "analysis_output"
        out.leaves(f"quality/{key}", value, origin, source)
    for index, value in enumerate(limitations):
        out.add(f"limitations/{index}", "derived_application" if value in _LIMITATIONS else "analysis_output",
                "practice adapter limitation set" if value in _LIMITATIONS else f"analysis_output/warnings/{index}")
    for index, _ in enumerate(warnings):
        out.add(f"warnings/{index}", "analysis_output", f"analysis_output/warnings/{index}")
    for index, value in enumerate(_UNAVAILABLE):
        out.add(f"unavailable_fields/{index}", "derived_application", "practice adapter availability declaration")
    return out.build()


def adapt_practice_analysis(analysis: Mapping[str, Any], *,
                            ref: CoachDecisionRef) -> CoachDecisionAnalysis:
    """Project one already calculated practice result; never run poker logic."""
    if not isinstance(ref, CoachDecisionRef):
        raise CoachAnalysisError("invalid_analysis", "A validated decision reference is required.")
    value = _mapping(analysis, "Practice analysis")
    producer = value.get("analysis_version")
    if producer != _PRODUCER_VERSION:
        raise CoachAnalysisError("unsupported_producer_version",
                                 "Practice analysis version is unsupported.")
    try:
        inputs = _mapping(_field(value, "analysis_inputs"), "Practice analysis inputs")
        analysis_id = _text(_field(value, "analysis_id"), "Analysis ID")
        model_version = _text(_field(value, "opponent_model_version"), "Model version")
        context = _validate_context(inputs)
        legal, modeled, action_ids, action_evs, baseline_evs = _action_sets(value, inputs)
        recommendation = _text(_field(value, "recommended"), "Recommendation")
        baseline_recommendation = _text(_field(value, "baseline_recommended"),
                                        "Baseline recommendation")
        if recommendation not in action_ids or baseline_recommendation not in action_ids:
            _fail("Upstream recommendations must name legal modeled actions.")
        ranges = _sequence(_field(inputs, "opponent_ranges"), "Opponent ranges")
        if not 1 <= len(ranges) <= 5:
            _fail("Practice analysis must contain one to five opponent ranges.")
        ranges = tuple(_text(item, "Opponent range") for item in ranges)
        confidence = _text(_field(value, "confidence"), "Confidence label")
        equity = _mapping(_field(value, "equity"), "Practice equity")
        equity_se = _finite(_field(equity, "standard_error"), "Equity standard error", 0)
        equity_exact = _field(equity, "exact")
        if type(equity_exact) is not bool:
            _fail("Equity exactness marker must be boolean.")
        assumptions, uncertainty, metric = _read_assumption(value, inputs, action_ids)
        reference = CoachPolicy("illustrative_argmax", tuple(
            ActionFrequency(action_ids[name], float(name == baseline_recommendation))
            for name in action_ids))
        policy = CoachPolicy("estimate_argmax", tuple(
            ActionFrequency(action_ids[name], float(name == recommendation))
            for name in action_ids))
        quality = CoachAnalysisQuality(confidence, uncertainty, equity_se,
                                      equity_exact, None, None, None, None)
        producer_warnings = _sequence(_field(value, "warnings"), "Analysis warnings")
        warnings = tuple(_text(item, "Analysis warning") for item in producer_warnings)
        limitations = _LIMITATIONS
        prov = _provenance(context, legal, modeled, reference, policy, action_evs,
                           baseline_evs, assumptions, quality, limitations,
                           warnings, inputs, metric)
        return CoachDecisionAnalysis.build(
            ref=ref, analysis_id=analysis_id, adapter_version=COACH_PRACTICE_ADAPTER_VERSION,
            producer_version=producer, model_version=model_version,
            source_kind="practice_estimate", context=context,
            legal_actions=legal, modeled_actions=modeled,
            reference_policy=reference, modeled_policy=policy,
            action_evs=action_evs, baseline_action_evs=baseline_evs,
            recommended_action_id=action_ids[recommendation],
            baseline_recommended_action_id=action_ids[baseline_recommendation],
            ev_basis="incremental_decision_chips", opponent_ranges=ranges,
            opponent_assumptions=assumptions, quality=quality,
            limitations=limitations, warnings=warnings,
            unavailable_fields=_UNAVAILABLE, provenance=prov)
    except CoachAnalysisError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        _fail("Practice analysis contains malformed evidence.")

