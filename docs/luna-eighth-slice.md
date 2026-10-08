# Luna handoff: current-decision study preview

Architecture decision · 2026-10-07 · one implementation slice

## Objective

Let a player explicitly study the **current hero decision before acting**. Return a short, truthful practice-estimate preview with the modeled legal actions, recommendation, assumptions, and limitations. This is the evidence foundation for a later live question; it is not yet a live AI conversation. The preview must never mutate the hand, record a choice, or claim that the simplified practice estimate is a solved strategy.

## Starting point

Start from merged [PR #36](https://github.com/ajpaulson18-design/openpoker-lab/pull/36), `40864fd732edaff62a1b8a57b47a840b76069385`, which follows the bounded conversation work in PR #35. Existing saved-decision conversations, the one-shot route, post-action capture, and Blind Play behavior remain intact. `practice.analyze_decision` computes from a `Game` snapshot and optional opponent model; `adapt_practice_analysis` converts that result to `CoachDecisionAnalysis`. Saved-decision `build_decision_study` and `build_grounding_bundle` require an actual chosen action, so do not invent a choice to reuse them. The server currently calculates accepted actions under `game_lock`; this preview calculation must not hold that lock or a SQLite transaction while running.

## Contract and server boundary

Add `POST /api/v1/hands/{hand_id}/current-study` with an exact JSON body `{expected_revision: nonnegative integer, opponent_id: string|null}`. The selected opponent ID is only an input to the existing local model lookup; it is not evidence supplied by the browser. Unknown/expired hands return 404, malformed inputs 400, stale revisions or a hand that advances during calculation 409, and a busy preview admission gate 429. Existing Host/Origin, JSON, loopback, and no-store protections apply. No provider or network call is allowed.

Under `game_lock`, verify the hand exists, is not complete, the hero is awaiting a decision, and its revision equals `expected_revision`; deep-copy the game and release the lock. Resolve the optional opponent model through the existing store method, with a safe error for unknown IDs. Calculate on the copy using `analyze_decision`, then adapt to `CoachDecisionAnalysis` with a server-generated, unpredictable preview ID as `decision_id` and the captured revision. Before publishing or caching the result, reacquire `game_lock` briefly and reject it if the hand/revision/hero turn changed. No `Game.act`, `save_decision`, session write, observation, or decision event occurs.

Use one bounded preview admission slot separate from the coach and general gameplay slots; a preview must not occupy the ordinary `work_lock` for its calculation. Keep only a small, expiring in-memory cache of successful preview evidence and its safe view, keyed by exact hand/revision and the **resolved opponent snapshot identity** (or explicit illustrative default). Repeated identical requests may return the same binding without recalculation while current; a changed opponent model cannot reuse old evidence. Cap entries and idle lifetime; never cache a stale result or return cached evidence after the hand advances. A process restart may discard previews. Avoid a new persistence schema or long-lived cache service.

The response is a bounded, versioned view, for example:

```json
{
  "schema_version": 1,
  "status": "ready",
  "binding": {
    "hand_id": "...", "decision_id": "preview-generated-id",
    "evidence_id": "...", "state_revision": 2
  },
  "source_label": "Practice estimate · current decision preview",
  "heading": "Current turn decision",
  "recommended_action_id": "raise:min",
  "modeled_actions": [
    {"action_id": "raise:min", "name": "raise", "amount": 4,
     "amount_semantics": "street_total", "estimated_ev_chips": 1.2}
  ],
  "assumptions": ["..."],
  "limitations": ["..."]
}
```

Example values show shape only. Build the view in a small pure module from the validated contract, not from raw `Game` or browser data. Include only current hero/board/public context needed for study. Distinguish exact evaluated minimum raise from other legal raises. Show null for unavailable values; never include a chosen action, mistake score, choice loss, opponent hole cards, deck, names, raw observations, or backend paths. Clearly state simplified practice EV semantics, random opponent ranges where used, illustrative fold assumption when no model exists, and sampling/uncertainty limits. Do not derive causal reasons from an EV ranking. Keep the contract immutable so later live coaching can reuse the preview binding, but do not expose a live coach endpoint in this slice.

## Browser behavior

When a hand is active and the hero can act, show a **Study current decision** button only if the existing coaching visibility rules allow it. Never show a live preview during Blind Play while coaching is hidden. Clicking the button sends the current hand ID, displayed revision, and selected opponent ID; there is no automatic calculation when a hand opens or advances. Show loading, a safe error/retry state, the source label, modeled options, assumptions and limitations. Keep action controls usable while it calculates. Clear the preview when an action is submitted, a new hand starts, Blind Play hides coaching, the revision changes, or the selected opponent changes. Check hand ID, revision, local request generation, and coaching visibility before rendering a late response. Render text safely.

Do not connect the existing saved-decision conversation to a preview ID. Once the action succeeds, the normal recorded decision and its evidence become the study target; the earlier preview remains labeled as a preview, not as a scored choice.

## Verification and stopping rule

Test a ready pre-action preview, modeled minimum raise versus other legal sizes, no-opponent illustrative assumptions, optional modeled opponent, hidden-card/name exclusion, unknown hand, malformed and stale revision, hand advancing during calculation, concurrent/busy requests, cache identity/invalidation, and absence of decision/hand mutation or external calls. Verify that a preview calculation does not hold `game_lock` or consume a gameplay request slot. Exercise rendered browser flow for a visible preview, an action during a pending preview, new hand, opponent change, and Blind Play. Run focused and full tests, publish one narrow PR, and stop for Sol review before merging. Do not add live AI questions, streaming, cancellation, auto-generated coaching, solver changes, or persistent previews in this slice.

