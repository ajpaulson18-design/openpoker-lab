# Architecture and mathematical conventions

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
       ├─ analysis.py   one-decision EV and explanations
       ├─ solver.py     restricted river CFR and best-response evaluation
       └─ game.py       full-hand betting mechanics and pot settlement
```

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

Other endpoints: `GET /api/health`, `GET /api/opponents`,
`POST /api/opponents`, `POST /api/observe`, `POST /api/analyze`,
`POST /api/game`, `POST /api/act`, and `GET /api/export`.

All writes accept JSON. Errors return a JSON `error` with a non-2xx status.
The endpoint implementation is the current contract; there is no external API
compatibility promise before version 1.0.
