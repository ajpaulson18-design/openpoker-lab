# Configured turn-to-river solver

The additive `pokerlab.turn_solver.solve_turn_river` library entry point extends
the existing configured river action tree across two streets. It uses the same
full-traversal CFR/DCFR kernel and exact information-set best-response evaluator.
The browser river solver and AI Coach interfaces retain their existing behavior.

```python
from pokerlab.river_config import RiverConfig
from pokerlab.turn_solver import solve_turn_river

result = solve_turn_river(
    "2c 3d 4h 8s", "AsAd", "KhKd",
    RiverConfig(pot=100, effective_stack=100, include_all_in=False),
    iterations=100, algorithm="dcfr",
)
print(result["worlds"], result["nash_conv"])
```

## Physical chance and information

On a four-card board, each compatible pair of distinct two-card hands leaves
44 possible river cards. Its unnormalized physical world weight is the product
of the caller's private-hand weights divided by 44. The joint distribution is
normalized once across all compatible hand-pair/river worlds. Chance probability
is included exactly once in each world; traversals follow that world's latent
river when the public chance node is reached.

Turn policies share an information set across indistinguishable opponent hands
and unrevealed river cards. River policies include the revealed card and the
complete preceding turn action history, preserving perfect recall. Serialized
rows include street, public board, private hand, full history and sized actions
under `postflop-strategy-v1`. No row contains a public card also in its own hand.

`runouts="5c 9c"` optionally studies a conditional game. It filters the physical
joint worlds and normalizes globally. Private-pair priors change when pairs block
different numbers of selected cards. Renormalizing separately within each pair
would describe a different game and is deliberately avoided. The result reports
`runout_mode="conditioned-subset"`; it does not estimate an unconditional game.

Best responses group worlds by the responding player's private hand before
maximizing any decision. At a public chance node they sum revealed-card branches;
they may condition later decisions on that card. They cannot choose a turn action
using the unrevealed card or the opponent's private hand.

## Pot and stack accounting

Configuration pot is the original turn pot. Stack caps are each player's total
additional commitment across both streets. Settled turn calls refund unmatched
chips and carry equal matched commitments into the river. River opening fractions
use original pot plus both carried commitments. For example, a 100-chip turn pot
and a called 50-chip turn bet produce a 200-chip river pot; a half-pot river bet
adds 100 chips and has cumulative `raise_to=150`.

Payoffs remain relative to each player's half of the original pot, with total
matched contributions counted once. A winner after that called river bet earns
`100/2 + 150 = 200` chips; a turn fold earns only the original half pot. All-in
turn calls still enumerate legal river cards but have no river betting decisions.
The out-of-position player acts first on every new street.

An optional `river_config` may change the river bet/raise abstraction. Its original
pot and total stack caps must equal the turn configuration. Both reuse the existing
minimum-full-raise, short-all-in, capped-call and refund rules.

## Scope and bounded work

This entry point solves finite heads-up turn-to-river action abstractions. The
[shared postflop API](postflop-validation.md) also supports bounded flop starts;
preflop, unrestricted bet sizes, rake and multiway equilibrium remain unsupported. Exact
private worlds are retained; there is no card bucketing or chance sampling.
Default iteration averaging is vanilla CFR; DCFR(1.5,0,2) remains selectable.
`traversal="planned"` selects optional bounded Python traversal preparation;
recursive traversal remains the default. The planned path uses more retained
memory to avoid repeatedly resolving static worlds, payoffs and information-set
indexes. See [planned traversal](planned-traversal.md) for its independent checks,
measurements and 250,000-operation storage limit. Both expose the same policy
schema and exact best-response calculations, with the chosen execution backend
recorded in results under solver version `configured-turn-river-v3`. Version v3
delegates to the reusable postflop engine while retaining the turn strategy
schema and established fields. Historical v2 benchmarks retain their original
recorded implementation and source hashes.
The exact average-policy deviation gap is reported in chips as NashConv, with
exploitability equal to half that gap. Street coverage alone is not an accuracy
certificate; inspect the measured gap for the actual configured game.

Limits: 10–10,000 iterations, three million candidate-pair iterations, three
million chance-world iterations, 10,000 public decision nodes and 30 million
world-node traversals. The traversal bound counts all decision branches visited
for one world, selecting one branch at each chance node. Full public tree size
separately counts every reachable river card. These guards constrain broad ranges.

All solver code is independently implemented with Python's standard library.
See [research notes](turn-research-notes.md) for primary publications and reference
design inspiration, and [progress](solver-progress.md) for measured validation.
