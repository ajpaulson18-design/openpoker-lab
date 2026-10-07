# Practice decision capture v1

Each accepted hero action now has a server-generated decision ID, a hand-local
pre-action revision, the exact choice made, and the validated coach evidence
produced from the original practice analysis. The evidence stays separate from
the chosen action: it describes the decision before the action was accepted.

## Capture and retries

`POST /api/game` returns `revision: 0`. Each successful `POST /api/act` may
include `expected_revision` and `client_action_id`; the browser sends both.
The expected revision must match the hand's current revision. A repeated client
action ID with the same meaningful request returns its original response,
including after the hand revision advances. Reusing the ID for a different
action returns HTTP 409. Older clients may omit both fields.

The server calculates and applies an action to a copy of the hand. It saves the
decision event, versioned evidence, and optional hand completion in one SQLite
transaction. The copied hand and next revision become live only after that
transaction succeeds. A failed calculation, presentation step, or save leaves
the current hand available for retry.

Decision events retain a safe pre-action history prefix and folded flags. The
prefix contains seat, street, action, and raise total; it never stores player
names. `chosen_action_detail` records chips added for fold/check/call and the
exact street total for a raise. Only a raise at the modeled minimum size has an
estimated EV loss. Other legal raise sizes are marked `unassessed_size`, with
loss and recommendation-match fields null.

## Retrieve evidence

`GET /api/v1/decisions/{decision_id}/analysis` returns one of:

- `200 {"status":"ready","analysis":...,"choice":...}` for validated saved
  evidence and an allowlisted choice summary;
- `200 {"status":"unavailable",...}` for a known legacy decision without
  versioned evidence;
- `404` for an unknown decision;
- `500 {"status":"failed",...}` when saved evidence or its binding is invalid.

The endpoint reads the saved envelope. It does not recalculate or adapt an
analysis and never returns the arbitrary persisted event. Responses use the
existing local-access checks and `Cache-Control: no-store` header.

Session review counts every recorded decision, but excludes unassessed choices
from EV-loss, recommendation-match, and exploit totals. Historical raises that
have no recorded amount are treated as unassessed without rewriting their
saved events.
