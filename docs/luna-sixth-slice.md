# Luna handoff: grounded teaching notes for one-shot answers

Architecture decision · 2026-10-07 · one implementation slice

## Objective

Make the merged one-shot coach answer explain what its saved facts mean. Add a small catalog of **application-authored teaching notes** selected from the validated reply intent and evidence. Each note names its source and cites the exact saved facts that support it. The model still selects only a `CoachReplyPlan`; it never writes the note, poker advice, numbers, or strategy. This slice improves a single question about a single saved decision. Multi-turn conversation, provider prose, automatic requests, and new calculations remain separate work.

## Starting point

Start from merged [PR #31](https://github.com/ajpaulson18-design/openpoker-lab/pull/31), `80940452620c6d82d9d9ea7b6957dbb5404d2f2b`. Its final head `4fa01320` passed 177 local tests and both GitHub workflows. Keep the existing off-by-default external opt-in, trusted `_validated_decision` load, `build_grounding_bundle`, `CoachReplyPlan` v1, OpenAI plan schema, separate coach admission gate, local fallback, and stale-response guards. Do not change gameplay, solver, persistence, or the legacy text-only personality provider.

## Teaching boundary

Add a pure module such as `pokerlab/coach_teaching.py`. Given a trusted `GroundingBundle` and `RenderedCoachReply` from the same binding, it returns at most one immutable, versioned `TeachingNote` with `{template_id, binding, text, supporting_fact_ids}`. The text is selected and assembled only from source-controlled templates and validated fact values; no provider-authored words, raw event fields, user question, or arbitrary fact IDs enter the note. Enforce a short text bound and exact supporting fact IDs. If prerequisites are missing, return no note and keep the existing structured reply. Do not introduce a second model call.

Provide a narrow catalog for the current intents:

- `recommendation`: explain that the saved recommendation applies only to the producer's modeled actions and EV basis. For `practice_estimate`, call it an estimate, never equilibrium strategy or a guaranteed best play.
- `choice`: distinguish an assessed recorded choice and its saved loss from an unassessed raise size. A larger raise cannot borrow the minimum-raise EV.
- `compare`: explain that the displayed actions and EVs share the same saved basis and assumptions; never compute a new delta or compare across analyses.
- `limits`: explain the producer's scope and differentiate opponent confidence, equity sampling error, and solver gap diagnostics when those facts are present. Do not convert any of them into a generic confidence score.
- `unavailable`: explain that the requested comparison or recommendation was not measured, naming only the server's unavailable marker. Do not offer a substitute size, EV, or action.

The catalog may use a few fixed glossary sentences for terms actually present in the rendered reply. It must avoid unsupported causal claims such as “the solver chose this because of blockers” or claims about an opponent's hidden cards. It may say that recorded opponent assumptions were used when those facts are present, but not that they are true of the opponent. Facts and mandatory limitations remain visible alongside every note. A `fact_ids` selection supplied by the model cannot alter template prerequisites or make unrelated facts authoritative.

Attach the note additively to the existing coach response as `teaching_note` for both AI-selected and local-fallback replies. In the study panel, show the note as a clearly labeled local explanation above the structured facts. Keep the source label, citation IDs, units, caveats, and external/local status visible. Escape text, preserve the current binding guard, and do not change the question or opt-in controls. A note for an old hand or decision must not appear in the current panel.

## Verification and stopping rule

Use synthetic fixtures to test every intent, practice source/basis wording, assessed versus unassessed raises, missing recommendations/EVs, opponent assumptions, weak or absent diagnostics, and cross-binding rejection. Assert semantic invariants and supporting fact IDs rather than whole paragraphs. Verify no new numeric arithmetic, solver/store/provider calls, user-supplied prose, or hidden-card claims. Test the endpoint with the fake provider and disabled-provider fallback, then inspect the rendered browser for a normal answer and an unavailable answer. Run focused and full tests and required checks. Publish one narrow PR; stop for Sol review before merging. Do not add conversation state, streaming, free-form model interpretations, lessons unrelated to the selected evidence, or a new provider prompt/schema in this slice.

