# Unified bounded four-street solving interface

`pokerlab.four_street_solver.solve_four_street` exposes the existing coupled
preflop-to-river engine through an immutable request and complete-result envelope.
It delegates exactly once to `solve_preflop(postflop_scope="all-streets")`.
Preflop, flop, turn and river decisions belong to one game and one trained policy;
there are no independent street-equilibrium calls or fixed continuation policies.

The explicit `native_executable=` call option selects the
[C++ public-chance CFR+ backend](native-four-street-architecture.md) for zero-delay
public-batched training/diagnostics with public-vector admission. It migrates
training across the same coupled game. Preparation, numeric diagnostics and the
immutable mathematical request retain their existing boundaries; native source
and build identity appear in the returned payload.

```python
from pokerlab.four_street_solver import solve_four_street
from pokerlab.preflop_tree import PreflopConfig
from pokerlab.solver_contracts import FourStreetSolveRequest, PostflopActions

request = FourStreetSolveRequest(
    sb_range="AsAd",
    bb_range="KsKd",
    runouts=("2c3c4d7h8h", "2c3c4d7hKc", "2c3c4dKc8h"),
    preflop_config=PreflopConfig(starting_stack=4, max_raises=0),
    flop_actions=PostflopActions(include_all_in=False),
    iterations=100,
)
result = solve_four_street(request)
envelope = result.to_dict()
print(envelope["payload"]["nash_conv"])
```

## Game and history contract

Global player 0 is SB/button and acts first preflop; player 1 is BB and acts
first on live postflop streets. Starting stacks include blinds. Net values are
whole-hand chip transfers from before posting; unmatched contributions are
refunded. Action `amount` is chips added now; sized `raise_to` and history keys
refer to cumulative whole-hand commitments. The existing binary64/local
nine-decimal action quantization and whole-hand translation order are retained.

Each information set contains actor, own physical hand and complete public
history. Reveal tokens expose only the canonical flop and then ordered turn and
river. Opponent hands and future cards are hidden. Blockers apply to one joint
private-hand/runout law, globally conditioned on the selected outcomes. Betting
updates retain separate player sequence reaches; posterior marginals cannot be
multiplied and substituted for the correlated joint game.

The complete underlying `preflop-strategy-v1` rows, values, legal best responses,
resource receipts and other fields remain in `payload`. There is no new state
machine or diagnostic pass in the reference facade. The optional native trainer
has separately tested binary64 recurrence and normalization; it does not change
the game, money rules or independent diagnostics.
See [the underlying solver](preflop-solver.md) and
[monetary replay](preflop-monetary-replay.md) for precise existing semantics.

## Inputs and supported options

`FourStreetSolveRequest` accepts the two original range strings, an actual
nonempty tuple of up to 300,000 runout strings, a `PreflopConfig`, action contracts
and the fixed solve options. It freezes the input structure; card/range parsing,
iteration bounds, option compatibility and complete resource admission remain
owned by the existing engine. Lists and generators are not request runout inputs.

`PostflopActions` is a complete specification with `bet_sizes`, `raise_sizes`,
`max_raises` and `include_all_in`. Its defaults match the existing engine. A
`None` turn or river specification independently inherits the entire flop
specification. An explicit later specification replaces all four fields.

| Option | Supported values |
| --- | --- |
| `algorithm` | `vanilla`, `dcfr`, `cfrplus` |
| `traversal` | `recursive`, `planned`, `public-batched` |
| `diagnostics` | `recursive`, `public-batched` |
| `resource_model` | `world`, `public-vector` |

Existing compatibility restrictions still apply: planned CFR+ rejects, and the
public-vector model requires public-batched training and diagnostics. There is
no arbitrary option passthrough. Sampling, delay, early stopping, grouping,
compaction and expanded tree admission remain outside this initial interface.

## Result and evidence boundary

`FourStreetSolveResult.to_dict()` returns a fresh detached envelope with schema
`four-street-solve-v1`, the submitted request, explicit semantic identities,
source-identity fields and the complete engine payload. `to_json()` returns
deterministic finite JSON. Mutating an input action-size list, a detached request
receipt or a detached output cannot change the retained request/result.

Ordinary calls report `source_revision: null` and
`source_verification: "not-recorded"`. A semantic identifier or solver version is
not authenticated source provenance or a new mathematical certificate. A frozen
integration runner must independently establish its source map and complete-game
quality evidence. Exact-normalized policy certification remains a subsequent
integration milestone; current floating diagnostics retain their existing scope.

The immutable output snapshot adds JSON serialization and retained-string cost.
That cost is not included in the old trainer's logical-loop model. No runtime,
memory/RSS improvement or broader admission is claimed.

Selected outcomes define a conditioned finite heads-up game. This interface does
not add full-deck preflop with live later-street betting, unrestricted NLHE, rake,
multiway equilibrium, simulator migration or a browser endpoint. All-in/short-blind
games can legitimately have no later-street decision rows.

## Validation

The new tests compare complete underlying payloads for shared-future, weighted,
fractional-money, zero-decision and public-vector controls, retain independent
numeric replay, check exact single-call delegation and exercise defensive
immutability and source-unknown serialization. Run:

```text
python -B -m unittest tests.test_solver_contracts tests.test_four_street_solver -v
```

The [integration architecture](unified-solver-integration.md) separates this
interface milestone from the frozen four-street corpus and independent exact
whole-game accuracy gate that follow it.

At this implementation boundary, the lead's combined new/legacy run passed 50
tests, including configured independent replay, shared public futures, weighted
blockers, fractional monetary boundaries and public-vector paths. All ten new
contract-only tests also passed under optimized Python. These finite controls
establish adapter behavior; they do not replace the upcoming frozen quality gate.
