# Coach analysis evidence schema v1

`pokerlab.contracts.CoachDecisionAnalysis` is the versioned boundary between an existing calculation and any coach, renderer or provider. `pokerlab.coach_analysis.adapt_practice_analysis()` currently supports only saved `practice-ev-v3` estimates. It is an allowlist projection: it does not calculate poker values, query persistence, inspect a solver, call a model or copy the raw analysis object.

The envelope labels its source as `practice_estimate`, its EV unit/basis as incremental chips from the current committed pot, and its producer/adapter/model/schema versions separately. The original calculation's `analysis_id` remains intact. `evidence_id` hashes every protected evidence field except the hand/decision locator and the hash itself, under `coach-evidence-v1`; it identifies the normalized evidence but does not prove who supplied it.

## Actions and policies

`legal_actions` records what the game permits. A raise has a nullable amount and explicit legal street-total bounds. `modeled_actions` records what the calculation evaluated. Practice evaluates exactly the minimum legal raise, named `raise:min`; a larger size is legal when the game says so but has no EV in this analysis. Fold and check use zero chips added. Call uses the actual chips added. A raise size means the player's street-total contribution.

Action EVs and supplied recommendations copy directly from the producer. The adapter does not rank values again. One-hot policy maps are labeled `illustrative_argmax` and `estimate_argmax`: they encode the supplied baseline and opponent-informed recommendations. They are not solver frequencies. EV differences and chosen-action loss do not appear in this envelope.

## Quality and unavailable fields

Confidence, opponent-model uncertainty, and equity sampling error remain separate. Exact river equity does not mean exact action EV or solver convergence. Practice has no NashConv, exploitability or iteration facts; these remain null. Opponent assumptions include the fold-to-bet estimate only when a modeled raise uses it and a matching, complete model snapshot exists.

The adapter always declares the decision-time action-history prefix, folded-seat flags, effective stack, chosen action, solver convergence and conditional ranges unavailable. In particular, current persisted decisions do not preserve the chosen raise total, so they cannot establish which sized action was taken.

## Privacy, provenance and compatibility

The envelope retains only hero cards, public board, seat/chip/legal state, range inputs needed to describe the estimate, analysis facts, consumed model evidence and safe field provenance. It excludes other players' cards, deck, name/notes, opponent identity, timestamp, database, local path and deal seed. Unknown producer keys are ignored. A future external provider needs a narrower provider projection; callers must not send this entire local contract by default.

`to_dict()` returns fresh JSON-ready containers; the dataclasses store tuples. `to_json()` is canonical, compact, sorted and rejects non-finite values. Readers reject unknown fields and versions, validate nested types, resolve provenance pointers and verify the evidence fingerprint. Unsupported producer versions and malformed evidence return `CoachAnalysisError` with a stable code and a safe message. Future schema changes must use an explicit version and preserve old saved evidence.

The first producer's three mandatory limitations state that practice EVs are simplified estimates, its policies are recommendations rather than solver mixes, and only the minimum raise size is modeled. The separate restricted river CFR API can support a future adapter, with its heads-up fixed-board one-size scope and profile gap semantics preserved there.

