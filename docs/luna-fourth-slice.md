# Luna handoff: provider-safe grounding and reply plans

Architecture decision · 2026-10-07 · one implementation slice

## Objective

Establish the trust boundary for future conversational coaching. Build a pure, versioned projection of one validated saved decision into allowlisted facts, plus a strictly validated reply plan that can cite those facts without supplying new poker numbers or actions. A deterministic renderer turns a valid plan into answer blocks. This slice prepares a safe conversation/provider interface; it does **not** call a model, send data externally, add chat UI, or change gameplay.

## Starting point and decision

Start from the merged result of [PR #27](https://github.com/ajpaulson18-design/openpoker-lab/pull/27), `c4d1dfcf4b9f4e017557add5534dfcd0d138c514`. Its final head `a1e213d` passed the test and quality workflows after Sol's in-flight browser race findings were fixed. PR #27 adds `build_decision_study()` and a shared validated evidence/choice loader. `CoachDecisionAnalysis` remains authoritative for the saved calculation; the separately validated choice tells what the hero actually did. The study view is presentation, not a provider payload. Do not hand its complete JSON, the raw event, or the full coach envelope to an external model.

The architectural choice is a **fact selection and answer-plan boundary**. A future model may choose an intent, detail level, and known fact IDs; it may not write EVs, strategies, frequencies, or revised evidence. The application renders all strategic facts from the immutable grounding bundle. This is narrower than free-form AI prose, deliberately: semantic truth cannot be guaranteed by JSON shape alone. An evaluated interpretation layer can be considered later without changing the evidence contract.

## Files and contracts

Add a small pure module such as `pokerlab/coach_grounding.py` and focused tests. Reuse existing contract serialization/validation patterns where appropriate; do not modify schema-v1 `CoachDecisionAnalysis`, its evidence fingerprint, the practice producer, solver, storage tables, server routes, or browser in this slice.

Define immutable version-1 types with strict JSON round-trip readers:

```text
GroundingBundle {
  schema_version: 1,
  binding: {hand_id, decision_id, evidence_id, state_revision},
  source_kind, ev_basis,
  facts: tuple[GroundFact],
  limitations: tuple[str],
  unavailable_fields: tuple[str]
}
GroundFact {
  fact_id, kind, source_pointer, value, unit, availability
}
CoachReplyPlan {
  schema_version: 1,
  binding: same four IDs/revision,
  intent: recommendation | choice | compare | limits | unavailable,
  fact_ids: tuple[str],
  target_action_id: str | null,
  detail: short | normal | technical,
  audience: beginner | standard
}
```

`source_pointer` is a pointer under `/analysis` or `/choice` into the validated analysis or allowlisted choice, never into an arbitrary event. `fact_id` is `f_` plus the full SHA-256 hex digest of UTF-8 `decision_id + "\n" + evidence_id + "\n" + canonical_source_pointer`; including the decision ID prevents identical evidence in two hands from sharing choice-fact IDs. `value` is a copied JSON scalar or immutable tuple of at most 16 scalars, never an object reference into mutable input. Unit/availability are explicit; `null` remains unavailable rather than zero. Cap the bundle at 64 facts, each text scalar at 256 characters, limitations at 10 items of 500 characters, and plan citations at 16 IDs. Reject duplicate IDs, unknown keys, unsupported versions, non-finite numbers, booleans as numbers, oversized text/arrays, and mismatched bindings.

The bundle builder takes `CoachDecisionAnalysis` and the same **validated allowlisted choice** used by `/analysis` and `/study`. It includes only decision-local facts needed for the supported intents: street, hero cards, board, current pot and basis, modeled action names/amounts, action EVs and their basis, saved recommendation/baseline labels when present, exact choice/status/loss, consumed opponent assumptions/uncertainty, quality diagnostics when available, mandatory limitations and unavailable markers. Preserve source kind and `practice_estimate` semantics. No opponent hole cards, deck, names, notes, raw observations, database/export contents, local paths, seeds, provider secrets, or unrelated hand history. This pure projection is not consent to transmit it; external enablement belongs to a later slice.

`CoachReplyPlan` validation must bind to the exact bundle, use only known fact IDs, and cap count/length. Fact IDs in the plan are optional supporting selections, not permission to change an intent's required facts: the renderer chooses the mandatory recommendation/choice/limit facts from the bundle itself. `compare` requires a modeled `target_action_id` and EV facts with the same saved `ev_basis`; an unmodeled raise amount or changed board/range/size yields `unavailable`, never a substitute EV. `choice` may show loss only when the recorded choice is assessed. `limits` always carries the producer caveats and source label. A plan cannot cite a different hand or evidence ID. The renderer emits structured answer blocks with server-supplied labels, values, units, fact IDs and caveats; it accepts no provider-written numeric or strategic prose. Presentation detail may hide optional facts but cannot alter their values or suppress mandatory caveats.

Keep the reply-plan contract separate from the legacy `ConversationalExplanationProvider.explain(payload, personality) -> str` protocol in `personalities.py`; that text-only interface is insufficient for this boundary and remains for compatibility only. Do not widen it or treat its prose as certified evidence.

## Failure and tests

Malformed evidence or choice is rejected before bundle construction. Invalid plans fail with typed, safe errors and no partial answer. Missing recommendation/EV, weak or absent solver diagnostics, no opponent assumption, and unassessed raise size all produce narrower facts or an explicit unavailable plan; they never trigger calculation. A historical decision without versioned evidence cannot produce a bundle and remains explicitly unavailable at the existing read boundary. Unknown intents, cross-decision IDs, fabricated fact IDs, unsupported action sizes, duplicate citations, and non-finite values fail closed.

Test exact fact provenance and stable IDs, immutability, canonical serialization, allowlist/privacy exclusions, null-versus-zero, practice source/basis labels, assessed versus unassessed loss, same-basis comparisons, missing-value behavior, all five intents, optional detail/audience choices, binding mismatches, malformed JSON, and no solver/store/provider calls. Use synthetic decision fixtures; do not mirror the implementation by comparing whole rendered strings. Run focused tests and the full unit suite. No card evaluator sweep is needed because poker mechanics stay unchanged.

Done means a future coach request can be grounded in a small inspectable bundle and a proposed reply can be validated and rendered without trusting the proposer for poker facts. Publish this narrow change in a short-lived PR after required checks pass, then stop. Sol will inspect the result before specifying the runtime/provider integration.

