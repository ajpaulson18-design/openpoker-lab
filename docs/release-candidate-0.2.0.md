# OpenPoker Lab 0.2.0 release-candidate integration report

## Integrated work

1. Multidimensional Bayesian opponent model with explicit priors, evidence,
   contexts, uncertainty, migration, reset, and immutable snapshots.
2. Confidence-aware exploit adapter for the restricted river CFR game.
3. Deterministic, provenance-bearing explanation engine.
4. Live Coach, Blind Play, persistent decision events, and session review.
5. Grinder, Chronic Bluffer, Nit, Math Guy, and Old-School Pro presentation
   voices, plus a disabled-by-default provider-neutral optional AI boundary.
6. Browser-driven explanations for supported river decisions, including
   reference/exploitative strategies, action EVs, uncertainty, caveats, and
   replayable stable analysis IDs.

## Integration decisions and conflicts

The opponent model owns persistence and snapshot construction. The exploit layer
consumes snapshots and never queries SQLite. Explanation and personality layers
are downstream of `StrategyAnalysisResult`; neither can choose an action. Practice
records retain the calculation, model version, visible state, and sanitized model
snapshot used at decision time. UI visibility and personality selection are not
calculation inputs.

The river explanation form composes `/api/exploit` with `/api/explain`; replay uses
the same supplied scenario and unchanged opponent snapshot. The display keeps the
reference strategy, opponent-specific strategy, returned action EVs, and model
caveats distinct. Explanations remain scoped to the documented restricted river
game and do not claim unrestricted Hold'em GTO.

The release-candidate audit tightened this boundary further. Practice is now a
single-hero flow: only seat zero is exposed to the browser, non-hero seats use a
deterministic check/call policy, and only hero decisions are coached and stored.
Personality values are validated before game mutation. Practice analysis schema
`practice-ev-v3` hashes its complete calculation output and model evidence, while
each decision retains the legal amounts and versioned inputs required for exact
recalculation. The Explain disclosure consumes the deterministic structured
explanation payload, and malformed persisted sessions fail with a controlled
JSON error instead of a partial review.

A second audit found that multiway practice had retained a heads-up equity
assumption. The v3 replay contract now stores one range per live opponent and
the simulator includes all of them; a three-way regression guards that boundary.

Shared conflicts occurred in `pokerlab/models.py`, `pokerlab/contracts.py`, the
README, and architecture documentation. The v2 schema and model behavior were
kept while explanation and session interfaces were composed around them. No CFR
mathematics was rewritten during conflict resolution.

The final audit fixes overlapped in `pokerlab/practice.py`, `pokerlab/server.py`,
`pokerlab/web/app.js`, and `tests/test_practice.py`. Integration preserved both
the private single-hero flow and the replayable analysis record: automatic
opponent actions never enter the decision history, while every hero event retains
the exact pre-action state and opponent snapshot.

## Verification and adversarial coverage

The complete unit suite covers historical behavior plus zero/one observations,
extreme rates, contrary evidence overwhelming priors, invalid counts, card
blocking, ties, node locks, short all-ins, side pots, hidden cards, historical
review, repeated personality rendering, malformed data, and offline operation.
The final combined run passed all 87 tests in 24.820 seconds. The exhaustive
evaluator independently checked all 2,598,960 five-card hands against the known
category totals and passed.
On Python 3.14 for Windows, standard `TemporaryDirectory` may create unusable
owner-only ACLs in the sandbox; the release run uses an equivalent workspace-safe
temporary-directory fixture. This is a test-host issue, not a runtime dependency.

## Known limitations and technical debt

- Poker solving remains a heads-up, fixed-board river game with one bet size and
  no raises, rake, stack constraints, future streets, or multiway branches.
- Practice EV is an illustrative visible-information checkdown estimate, not the
  restricted river CFR exploit adapter and not full-game GTO. Showdown equity
  includes every live opponent; raise EV uses a documented simplified
  independent-fold, at-most-one-caller response model.
- Aggregated observations do not infer hidden-card ranges or conditional policies
  beyond documented translations.
- Showdown bluff evidence is selection-biased; uncertainty labels are heuristic.
- Sessions are local SQLite records and in-memory hands do not survive restart.
- Practice currently fixes the human hero at seat zero; automatic opponents use
  a deterministic check/call policy rather than a strategic playing agent.
- The optional conversational provider is interface-only and disabled by default.

## Suggested next phase

Unify practice decisions with the structured exploit-analysis contract, add
calibrated conditional models and hand-history import, benchmark strategies on
held-out samples, and expand solver abstractions only with corresponding
correctness and exploitability tests.

## Key files

- `pokerlab/contracts.py`: immutable cross-component contracts.
- `pokerlab/models.py`: Bayesian persistence and session history.
- `pokerlab/exploit.py`: confidence-aware river translation and analysis.
- `pokerlab/explanations.py`: deterministic fact extraction and provenance.
- `pokerlab/practice.py`: hidden-information-safe coaching and review records.
- `pokerlab/personalities.py`: invariant-preserving presentation voices.
- `pokerlab/server.py`: local HTTP composition boundary.
- `docs/human-aware-strategy.md`: meaning and ownership of strategy fields.
