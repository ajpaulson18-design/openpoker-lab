# OpenPoker Lab 0.2.0 release-candidate integration report

## Integrated work

1. Multidimensional Bayesian opponent model with explicit priors, evidence,
   contexts, uncertainty, migration, reset, and immutable snapshots.
2. Confidence-aware exploit adapter for the restricted river CFR game.
3. Deterministic, provenance-bearing explanation engine.
4. Live Coach, Blind Play, persistent decision events, and session review.
5. Grinder, Chronic Bluffer, Nit, Math Guy, and Old-School Pro presentation
   voices, plus a disabled-by-default provider-neutral optional AI boundary.

## Integration decisions and conflicts

The opponent model owns persistence and snapshot construction. The exploit layer
consumes snapshots and never queries SQLite. Explanation and personality layers
are downstream of `StrategyAnalysisResult`; neither can choose an action. Practice
records retain the calculation, model version, visible state, and sanitized model
snapshot used at decision time. UI visibility and personality selection are not
calculation inputs.

Shared conflicts occurred in `pokerlab/models.py`, `pokerlab/contracts.py`, the
README, and architecture documentation. The v2 schema and model behavior were
kept while explanation and session interfaces were composed around them. No CFR
mathematics was rewritten during conflict resolution.

## Verification and adversarial coverage

The complete unit suite covers historical behavior plus zero/one observations,
extreme rates, contrary evidence overwhelming priors, invalid counts, card
blocking, ties, node locks, short all-ins, side pots, hidden cards, historical
review, repeated personality rendering, malformed data, and offline operation.
On Python 3.14 for Windows, standard `TemporaryDirectory` may create unusable
owner-only ACLs in the sandbox; the release run uses an equivalent workspace-safe
temporary-directory fixture. This is a test-host issue, not a runtime dependency.

## Known limitations and technical debt

- Poker solving remains a heads-up, fixed-board river game with one bet size and
  no raises, rake, stack constraints, future streets, or multiway branches.
- Practice EV is an illustrative visible-information checkdown estimate, not the
  restricted river CFR exploit adapter and not full-game GTO.
- Aggregated observations do not infer hidden-card ranges or conditional policies
  beyond documented translations.
- Showdown bluff evidence is selection-biased; uncertainty labels are heuristic.
- Sessions are local SQLite records and in-memory hands do not survive restart.
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
