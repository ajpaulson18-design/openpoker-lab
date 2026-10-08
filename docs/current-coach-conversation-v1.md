# Current-preview coach turns v1

`POST /api/v1/hands/{hand_id}/current-coach/turns` accepts a `client_turn_id` UUID v4, an optional `conversation_id`, the exact retained preview `target` binding, `question`, `detail`, and `audience`. External AI requires the existing per-request opt-in header. The response adds `conversation_id`, `client_turn_id`, and one-based `turn_index` to the existing current-coach reply. The one-shot `/current-coach` route remains available.

Each conversation contains at most four turns for one unplayed decision and uses a separate in-memory ledger from saved-decision conversations. Identical turn retries return the cached response without another provider call. Conflicting IDs, concurrent turns, cross-preview reuse, and expired conversations return controlled errors. The current hand, revision, and retained immutable preview are checked before and after a provider wait, including for cached retries. Refreshing a preview creates a new binding and starts a new conversation.

When explicitly opted in, the provider receives the current allowlisted preview facts, this question, and at most two preceding questions with validated plan metadata. It never receives a recorded choice or choice loss for an unplayed decision. Local fallback remains available without external AI. No turn recalculates poker strategy or persists conversation text in SQLite.
