# Saved decision study v1

`GET /api/v1/decisions/{decision_id}/study` returns a fixed, deterministic
view of a captured decision. It reads the saved coach envelope and the
allowlisted choice validated by the decision evidence boundary. It does not
call analysis, adaptation, solver, or provider code.

The response binds the view to the saved hand, decision, evidence fingerprint,
and pre-action revision. It includes the exact choice, every modeled action and
its saved EV (or `null` when unavailable), the saved recommendation, three
fixed study prompts, and bounded caveats. Practice action values are labeled in
chips. Other evidence uses its declared EV basis. A baseline is included only
when the saved envelope contains a baseline recommendation and matching EV
value under the same declared basis.

For an assessed choice, the choice card may describe the saved EV gap only when
the validated loss and both compared action values are available under the same
basis. A legal raise above the modeled minimum is described as unevaluated; the
modeled minimum appears only as a separate alternative and never scores that
larger raise. The limits card reports the saved confidence label, any captured
opponent assumption and uncertainty, plus the producer's limitations and
warnings. No opponent read is implied when no assumption was captured.

Known decisions without versioned evidence return the existing `unavailable`
status. Unknown IDs return `404`; invalid saved evidence or choices return the
same controlled `500` shape as the `/analysis` route. The route does not return
arbitrary event fields, player names, hidden cards, or database errors.

In the browser, each accepted decision is selectable while Live Coach is on.
Blind Play hides the study until the player turns coaching on or the hand
finishes. Completed-hand review keeps a chronological list and can reopen
legacy rows as unavailable. A hand ID, selected decision ID, and incrementing
selection generation guard every asynchronous response so stale requests cannot
replace the current study. All saved text is rendered as escaped text.
