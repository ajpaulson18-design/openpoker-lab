# Human-aware strategy architecture

## Purpose and invariant

OpenPoker Lab is evolving from reference poker analysis toward decisions against
a particular observed opponent. The governing invariant is that poker
calculation and presentation remain independent. A personality may change how a
recommendation is worded; it must never change the cards, assumptions,
frequencies, EVs, or recommended action.

The free core owns all deterministic modeling and explanation facts. It must run
locally without an API key, subscription, network connection, or external AI
service. An optional AI explainer is a consumer of structured facts, not a solver.

This document supplements [architecture.md](architecture.md). The executable
shared types are in `pokerlab/contracts.py`.

## Data flow and ownership

```text
recorded observations + explicitly selected prior/archetype
                         │
                         ▼
              opponent model calculator
                         │
              OpponentModelSnapshot (immutable)
                         │
           ┌─────────────┴─────────────┐
           ▼                           ▼
 reference strategy              exploit calculator
           │                           │
           └─────────────┬─────────────┘
                         ▼
             StrategyAnalysisResult
                         │
                         ▼
               ExplanationPayload
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
 deterministic renderer       optional AI explainer
            └────────────┬────────────┘
                         ▼
                 personality/style
```

Persistence is upstream of the snapshot boundary. `Store.opponent_snapshot()` is
the current adapter from SQLite-backed observations and profile priors. Solvers
and analysis engines receive an `OpponentModelSnapshot`; they must not query
SQLite for individual statistics. This keeps a calculation reproducible and
makes alternate stores possible.

The current `analyze()` and `solve()` dictionaries remain supported. New work
should use the shared contracts at component boundaries and add adapters rather
than removing legacy fields before an explicit API migration.

## Layer rules

### A. Reference/baseline strategy

May calculate a strategy under a documented reference model and publish legal
actions, frequencies, EVs, solver version, and limitations.

Must not read opponent observations, call an opponent-profile store, or label the
current restricted river CFR game as a complete no-limit Hold'em GTO solver. The
decision lab's present 45% fold comparison is illustrative, not GTO.

### B. Human opponent observations

May record an actual opportunity, outcome, street, action context, position, and
source identifier. Observations are evidence, not estimates.

Must not synthesize a failed opportunity when none was observed, infer hidden
cards, or turn a profile label into a fact about a person.

### C. Opponent model estimates

May combine recorded observations with an explicitly selected prior/archetype by
a deterministic, versioned calculation. Each `OpponentTendencyEstimate` names
one tendency and its context, prior, successes, opportunities, posterior mean,
sample size, and uncertainty.

Must not produce one global "fish score." It must not infer a hidden-card range
from VPIP, PFR, fold, aggression, or other aggregate rates unless a future,
explicitly versioned range model is implemented and validated.

### D. Opponent-model uncertainty

May expose an interval, level, method, and human-readable confidence label.

Must stay attached to the estimate it describes. A sample-size label is not a
claim of predictive calibration. The current interval is a clipped normal
approximation to a Beta posterior and must retain that method label.

### E. Exploitative strategy

May consume a reference strategy and an immutable opponent snapshot, document
which tendency assumptions were used, and calculate a distinct adjusted policy.

Must not overwrite the reference policy, silently convert aggregate tendencies
into hand-specific ranges, or reach back into persistence during a solve.

### F. Explanation data

May deterministically select relevant mathematical facts, evidence counts,
uncertainty, caveats, and the EV difference supporting the recommendation.

Must not recalculate poker strategy. `ExplanationPayload.analysis_id` must match
the `StrategyAnalysisResult` it explains. Any optional LLM receives this payload
and returns prose only; its prose is not calculation output.

### G. Presentation and personality

May change vocabulary, tone, examples, and visual treatment after calculation.

Must not change an action, frequency, EV, assumption, caveat, analysis ID, or
mathematical fact. Presentation code should be testable with a fixed explanation
payload.

## Shared contracts

All shared contracts are frozen dataclasses and contain tuples rather than
mutable collections. `to_dict()` returns a JSON-ready copy; serialization does
not grant mutation of the source object.

- `TendencyContext` identifies street, position, action context, and optional
  explicit qualifiers.
- `BetaPrior` records prior mean, effective strength, and source. A source such
  as `profile:balanced` makes an archetype selection visible.
- `Uncertainty` carries bounds, interval level, method, and confidence label.
- `OpponentTendencyEstimate` is one opportunity-based posterior estimate.
- `ObservationEvidence` and `TendencyEvidence` expose the immutable observations
  underlying an estimate without exposing persistence internals.
- `OpponentModelSnapshot` is the immutable collection passed into calculation.
- `OpponentModelProvider` is the storage/model boundary implemented by `Store`.
- `ActionFrequency` and `ActionValue` make strategy and EV entries explicit.
- `OpponentAssumption` records exactly which model value a calculation consumed.
- `StrategyAnalysisResult` keeps legal actions, baseline frequencies,
  exploitative frequencies, action EVs, EV deltas, assumptions, uncertainty,
  versions, limitations, and warnings in separate fields.
- `ExplanationPayload` carries recommendation facts without presentation style.
- `stable_analysis_id()` hashes canonical inputs under a versioned namespace.
  Callers must exclude timestamps and other nondeterministic values.

`StrategyAnalysisResult` requires both strategies to cover every legal action and
sum to one. This prevents consumers from confusing missing data with a zero
frequency. `action_evs` and `ev_differences` likewise cover every legal action.
The meaning and comparison point for each EV difference must be documented by
the producer in its method/version documentation.

## Baseline versus exploitative results

Baseline and exploitative policies are siblings, never aliases. A component may
produce equal policies when no supported adjustment exists, but it must still
populate both fields and state that no adjustment was applied. UI labels should
say which policy they display. A baseline may be equilibrium-derived,
rule-derived, or illustrative; the solver/method version and limitations must say
which. "Baseline" alone does not mean GTO.

Opponent assumptions belong only to the exploitative calculation. Reference
results must remain reproducible without a profile or snapshot.

## Restricted-river exploit implementation

`pokerlab.exploit.solve_exploitative_river()` is the first executable bridge
from `OpponentModelSnapshot` to strategy. It solves the existing restricted
river game once for a reference CFR policy, translates only supported river
estimates into inspectable IP node locks, and solves the same game against those
locks. It can report either the OOP root decision (`check`/`bet`) or the OOP
response after checking and facing a bet (`fold`/`call`). The two policies remain
separate in `StrategyAnalysisResult`; neither is described as full-game GTO.

The currently supported mappings are deliberately narrow:

- `fold_to_bet` maps to IP's fold/call response when OOP bets. A single common
  log-odds shift changes private-hand call frequencies while preserving their
  reference ordering.
- `showdown_bluff` maps to the bluff share when IP bets after an OOP check. Only
  IP hands with negative showdown value against the supplied OOP range are
  adjusted. Value-hand betting remains at its reference frequency. An
  unattainable requested bluff share is clipped to the feasible range and
  produces a warning.

No other aggregate tendency changes a solver node. In particular, the
`prior_archetype` string is retained for provenance but is never consumed as a
solver instruction. The explicit tendency posterior, context, prior strength,
and observed opportunity count are the mathematical inputs.

### Confidence treatment

For an estimate with `n` observed opportunities and Beta prior effective
strength `k`, the exploit adapter uses the evidence share

```text
w = n / (n + k)
modeled frequency = reference frequency + w × (posterior mean - reference frequency)
```

This has no arbitrary sample threshold: zero evidence gives `w = 0`, and the
influence of evidence grows smoothly toward one. The resulting aggregate target
is projected onto hand-specific node frequencies using a common log-odds shift,
the minimum-discrimination-information update under one mean constraint. The
reported hero policy is also blended between the reference policy and the raw
best response by the largest applicable `w`. That second conservative step
prevents tiny samples from causing a large strategy jump at an equilibrium
indifference point.

Every applied mapping produces an `OpponentAssumption` containing the tendency,
context, reference frequency, posterior mean, modeled frequency, exact
confidence weight, uncertainty, affected node and action, affected private
hands, and a reason. Action EV differences mean modeled-opponent action EV minus
the corresponding reference-opponent action EV. `BestResponseInfo` reports the
decision best response, policy value and residual gap, while also retaining the
restricted solver's unrestricted profile gap.

### Mathematical limitations

The bridge does not infer ranges from population statistics. Both private ranges
remain explicit scenario inputs, and blocker removal is still performed by the
restricted river solver. `showdown_bluff` is treated as a conditional bluff
share at the IP-after-check node even though real showdown samples are
selection-biased. The model has one bet size, no raises, no rake, no stack
constraints, no future streets and no multiway play. Finite-iteration CFR and
the behavioral translation are research approximations, not a claim of a full
no-limit Hold'em solution.

## Calculation, explanation, and personality

Calculation chooses frequencies and EVs. Explanation selection converts those
results into a bounded set of relevant facts. Rendering turns facts into prose.
Personality is a final rendering option. Keeping these steps separate provides a
deterministic explanation path when AI is disabled and makes it possible to
verify that two personalities communicate the same recommendation.

The stable analysis ID joins persisted calculation results, explanation payloads,
UI events, and future session review. It is not a database primary key by itself;
the current store may continue assigning its own saved-record ID.

## Guidance for parallel implementation agents

1. Import contracts from `pokerlab.contracts`; do not create competing payload
   shapes inside feature modules.
2. Add fields compatibly. Changing a field's meaning requires a new model or
   solver version and migration notes.
3. Request one immutable snapshot at the start of a calculation and retain the
   assumptions used in the result. Do not hold a live `Store` inside a solver.
4. Keep observation ingestion separate from model calculation. An imported hand
   can generate observations only through documented opportunity definitions.
5. Preserve baseline output when adding exploit logic. Never relabel the current
   restricted CFR output as unrestricted NLHE GTO.
6. Build deterministic explanation payloads before adding renderers or optional
   AI. AI and personalities may consume results but cannot amend them.
7. Session coaching should persist analysis IDs and the inputs/model versions
   needed for replay; it should not copy mutable profile dictionaries into a
   running hand.
8. Add contract-boundary tests for serialization, immutability, model versioning,
   and baseline/exploit separation alongside poker-correctness tests.

## Current compatibility adapter

`Store.opponent_snapshot(opponent_id, street)` converts the existing
opportunity-based Beta model to these contracts. It intentionally includes only
the opponent ID, selected prior archetype, model version, and modeled tendencies.
The opponent's display name, notes, raw observation records, database connection,
and timestamps do not enter a solver snapshot.

The existing `Store.get_opponent()` response remains unchanged. JSON exports are
schema version 2 and include persisted priors plus both legacy and v2 observation
rows. Existing browser flows continue to work while new strategy components can
depend on an explicit immutable boundary.
