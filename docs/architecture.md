# Architecture and mathematical conventions

The contracts and layer boundaries for opponent-specific strategy are documented
in [human-aware-strategy.md](human-aware-strategy.md). This document describes
the currently implemented application and mathematical conventions.

## Flow

The browser sends JSON to a loopback-only Python HTTP server. The server delegates
to small modules and returns JSON. Opponent observations and decision analyses
are persisted in SQLite; equity and solver requests are stateless.

```text
Browser (pokerlab/web)
  └─ server.py
       ├─ cards.py      parsing, range expansion, exact hand comparison
       ├─ equity.py     sampled runouts or exact river enumeration
       ├─ models.py     opponent priors, observations, SQLite transactions
       ├─ contracts.py  immutable human-aware component boundaries
       ├─ analysis.py   one-decision EV calculation
       ├─ explanations.py deterministic facts, prose, and JSON round-trips
       ├─ personalities.py deterministic coaching voices and optional text adapter
       ├─ solver.py     restricted river CFR and best-response evaluation
       └─ game.py       full-hand betting mechanics and pot settlement
```

## Coaching presentation

`pokerlab.personalities` sits strictly after explanation and calculation. Its
five local voices (Grinder, Chronic Bluffer, Nit, Math Guy, and Old-School Pro)
work offline and retain the exact immutable `DecisionExplanation`. A SHA-256
fingerprint covers the protected recommendation, EVs, strategy frequencies,
confidence, uncertainty, opponent evidence, and caveats; a rendering with a
mismatched analysis ID or fingerprint is rejected.

The optional `ConversationalExplanationProvider` is disabled by default and
has no dependency or API-key requirement. If explicitly enabled, it receives a
serialized copy of an already-completed explanation and may return non-empty
prose only. It cannot return replacement structured result fields, and it never
participates in poker calculation.

## Expected value

Let `P` be the current pot and `C` the amount hero must call. The pot already
includes the opponent's outstanding bet. With showdown equity `e`:

```text
EV(fold) = 0
EV(call) = e × (P + C) − C
Required equity = C / (P + C)
```

With no outstanding bet, a proposed bet `B`, fold probability `f`, starting-range
equity `e0`, and calling-range equity `ec`:

```text
EV(check) = e0 × P
EV(bet) = f × P + (1 − f) × [ec × (P + 2B) − B]
```

These values are incremental from the decision point. Previous contributions are
sunk. If there is another betting decision, a raise, rake, or insufficient stacks,
the model needs extension; the displayed formula does not include those effects.

## Opponent posterior

For prior probability `p`, prior strength `k=10`, observed successes `s`, and
observed opportunities `n`:

```text
alpha = k × p + s
beta  = k × (1 − p) + n − s
posterior mean = alpha / (alpha + beta)
```

The opportunity denominator is recorded explicitly. Each observation has a stable
identifier for idempotence at the API level. Supplying the same ID and data twice
does not count twice; reusing the ID for different data is rejected. Separate
submissions without a supplied ID count as separate observations.

Archetypes initialize independent priors for each tendency and do not constrain
later estimates. The v2 store persists those priors in `opponent_priors` and
counted, contextual evidence in `opponent_observations`. Existing `opponents`
and single-event `observations` rows remain readable and are combined with v2
evidence. Malformed legacy evidence raises `OpponentDataError` instead of being
used silently. Snapshot creation is deterministic and contains no timestamps.

The public model boundary consists of `create_opponent()`,
`create_opponent_from_archetype()`,
`record_observation()`, `get_tendency_estimate()`,
`get_tendency_evidence()`, `opponent_snapshot()`, and
`reset_opponent_model()`/`reinitialize_opponent_model()`. The older
`add_opponent()`, `observe()`, and
`get_opponent()` shapes remain compatibility adapters.

Metric definitions: VPIP and PFR each use dealt hands; 3-bet uses opportunities
facing a preflop raise; fold-to-bet uses faced bets; aggression uses observed
postflop actions; showdown bluff uses classified shown aggressive hands. The
latter two are simple rates, not aggression factor or an unbiased bluff estimate.

## CFR

Four binary information-set families are maintained for each private hand:

- OOP opening: check / bet.
- OOP after check-bet: fold / call.
- IP after check: check / bet.
- IP facing a bet: fold / call.

Positive cumulative regrets determine each iteration's strategy. Full traversal
weights compatible deals by the product of the two input range weights, then
normalizes the joint distribution. Regret updates use the opponent's reach;
average-strategy accumulation uses the player's own reach. All regret updates in
an iteration are computed from the same strategy snapshot.

Utilities are `±P/2` for a fold or checked showdown and `±(P/2+B)` for a called
showdown; ties have zero utility. Best-response calculations retain private
information: values over indistinguishable opponent hands are summed before
maximizing. The resulting gap is exact for the reported average strategy in the
specified finite game, up to floating-point precision.

## Betting engine

Player names are unique, user-defined labels mapped to stable clockwise seat
numbers. Names appear in state, action history, and pot settlements; the numerical
seat remains the source of truth for positions and odd-chip order.

Chip amounts are integers. `raise` takes a street total, not a raise increment.
The engine tracks each player's street contribution, total contribution, remaining
stack, fold status, and last faced wager. Cumulative short all-ins reopen raising
when the total faced increase reaches a full raise. Side pots are built at distinct
contribution levels; unmatched excess is returned. Odd chips go clockwise from
the button among tied winners.

## API examples

`POST /api/equity`:

```json
{"hero":"As Ah","board":"","ranges":["random"],"trials":5000,"seed":42}
```

`POST /api/solve`:

```json
{"board":"Js 8d 4c 2h 2s","oop_range":"AsAh,KsKh,AsKs","ip_range":"AcAd,KcKd,AcKc","pot":100,"bet":50,"iterations":1000,"lock":{}}
```

`POST /api/exploit` accepts the same restricted river-game inputs plus
`hero_hand`, `opponent_id`, and optional `decision`. It loads an immutable river
snapshot and returns the shared strategy-analysis contract. This remains a
restricted river adapter, not a complete no-limit Hold'em solver.

`POST /api/explain` deterministically converts a serialized analysis contract
into traceable explanation facts. Practice `POST /api/act` accepts an optional
`personality`; the server renders that voice only after the calculation and
returns the unchanged analysis ID and a protected-facts fingerprint.

Other endpoints: `GET /api/health`, `GET /api/opponents`,
`POST /api/opponents`, `POST /api/observe`, `POST /api/analyze`,
`POST /api/exploit`, `POST /api/explain`, `POST /api/game`, `POST /api/act`,
`GET /api/session/{id}`, and `GET /api/export`.

All writes accept JSON. Errors return a JSON `error` with a non-2xx status.
The endpoint implementation is the current contract; there is no external API
compatibility promise before version 1.0.
