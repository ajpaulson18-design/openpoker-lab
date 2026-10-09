# Exact finite postflop games

`pokerlab.postflop_solver.solve_postflop` solves configured heads-up action
abstractions from flop, turn or river, using the same betting builder and CFR
kernels. This adds three-street coverage, with explicit computational limits.
It does not establish unrestricted NLHE equilibrium accuracy.

```python
from pokerlab.postflop_solver import solve_postflop
from pokerlab.river_config import RiverConfig

# A small full physical flop game: 1,980 ordered future worlds per private pair.
result = solve_postflop(
    "2c3d4h", "AsKd", "JsJd",
    RiverConfig(pot=10, effective_stack=5, bet_sizes=(0.5,),
                include_all_in=False),
    iterations=30, algorithm="vanilla", traversal="recursive",
)

# A conditional deeper-stack study game, with weighted private uncertainty.
study = solve_postflop(
    "2c3d4h", "AsKd:0.5,QhQc:1", "JsJd:1,9s9d:0.75",
    RiverConfig(pot=10, effective_stack=(35, 25), bet_sizes=(0.5,)),
    runouts=[("As", "8c"), ("6c", "9s"), ("6c", "8c")],
    iterations=30, algorithm="dcfr", traversal="planned",
)
```

The initial config applies to the starting street. For a flop start,
`turn_config` and `river_config` can override later sizing; for a turn start,
only `river_config` applies. Configs accept `RiverConfig` or dictionaries, all
preserving the original pot and total additional stack caps. Minimum raises,
short all-ins, reopening and returned uncalled excess retain the river builder's
semantics. A complete five-card board uses only `config` and rejects runouts.

Each compatible private pair has 45 unseen turn cards and 44 subsequent rivers
on a flop, 44 rivers on a turn, and one world on a complete board. Worlds retain
ordered future cards even when reversed reveals have the same final showdown
rank. Rank caching shares that evaluation, not the earlier decisions.

Selected flop runouts must be nonempty, unique ordered `(turn, river)` pairs;
turn selections retain the existing card-string format. Both filter the entire
joint physical distribution and normalize once. Blockers can change private
pair priors under this conditioning. They are explicit conditional games rather
than approximations of the full-deck game. `runouts` records requested outcomes
before private removal; `reachable_runouts` records those with at least one
compatible world, in the same format and deterministic order.

Information sets contain own private hand and full public action/reveal history.
A flop policy has no future cards; a turn policy sees its revealed turn but not
its future river. OOP starts each postflop street. Matched cumulative commitments
carry between streets, original pot is counted once, and all-in branches reveal
remaining cards without new betting decisions. Compatible own hands are indexed
by revealed-card prefix before information-set construction.

Results expose `configured-postflop-v1` and `postflop-strategy-v1`, with street,
visible board and full history in each policy row. Exact information-set best
responses integrate unrevealed worlds before selecting an action. NashConv is
the sum of both unilateral improvements in chips; exploitability is half that
gap for this two-player zero-sum configured game. Inspect it separately from
street coverage. No rake, preflop blinds/BB option, multiway certificate, card
bucketing or chance sampling is introduced.

## Independent validation

Tests independently enumerate physical worlds and replay serialized policies
and best responses on weighted, blocker-conditioned three-street games. An
adversarial two-reveal tree has legal response value zero versus a clairvoyant
value two. Planned and recursive policies match under vanilla and DCFR. Tests
also execute a full physical short-stack flop game, check normalized policies,
verify cumulative street sizing, reject invalid selections/configs, and compare
complete-board results with the established configurable river API.

The established turn entry point is a thin facade, preserving its signature,
strategy schema and result fields, while reporting `configured-turn-river-v3`.
A separate before/after check loads the actual prior turn implementation from
GitHub main `95f0928`, rather than comparing two facades. It compares all policy
rows, actions, values, both BRs, gaps and counts on two versioned fixtures, both
algorithms/backends and 10/30 iterations: 16 comparisons, maximum difference zero.
The recorded source hashes are in `benchmarks/results/turn-refactor-parity-v1.json`.

## Limits and measurements

The solver accepts 10–10,000 iterations, at most three million candidate-pair
iterations and three million world iterations, 10,000 public decision nodes,
and 30 million world-node iterations. Chance selects one branch for each static
world in the work bound; the public-tree bound counts all reachable reveals.
An additional 250,000-public-state cap counts decisions, chance nodes and terminal
leaves before their expansion/allocation. The betting builder accepts a private
allocation hook so the initial street is charged before building its child
continuations. Decision counts alone would miss large all-in reveal trees.
Reported `public_states`, `terminal_nodes` and `public_state_limit` make this
separate bound visible. Tree-walking closures are cleared after use so the tree
does not depend on cyclic collection for release.
Planned traversal additionally bounds retained operations at 250,000, using a
conservative per-world maximum before compilation and the actual compiler guard.

With pot 10, stack 5 and a half-pot bet, a one-pair full flop has 1,980 worlds,
8,104 public decision nodes, 12 decision visits per world and 49,500 planned
operations, plus 228 chance nodes and 17,912 terminal leaves (26,244 public
states total). A stack-10 half-pot/all-in full flop exceeds the public-node cap,
because called partial bets leave later betting decisions. Larger practical
flop ranges and deeper full-deck trees require further performance work.

Run reproducible whole-call measurements with:

```sh
python -m scripts.benchmark_postflop_solver --algorithm vanilla --traversal recursive --output benchmarks/results/postflop-v1-recursive-vanilla.json
python -m scripts.benchmark_postflop_solver --algorithm dcfr --traversal recursive --output benchmarks/results/postflop-v1-recursive-dcfr.json
python -m scripts.benchmark_postflop_solver --algorithm vanilla --traversal planned --output benchmarks/results/postflop-v1-planned-vanilla.json
python -m scripts.benchmark_postflop_solver --algorithm dcfr --traversal planned --output benchmarks/results/postflop-v1-planned-dcfr.json
```

The versioned config includes a small full-deck game and a weighted conditional
game. Timings include world/tree construction, training and exact BRs; memory
uses a separate traced call. Reports record source/config/harness hashes and
reject source changes during measurement. Timing is shared-machine evidence,
not a general speed guarantee. Research/provenance is tracked separately in
[postflop research](postflop-research.md).

Committed records include the initial recursive vanilla report at source
`3a8a78a` and the current planned vanilla report at guarded source `bac5e47`.
They agree on game counts, values, exact BRs and gaps within 1e-12, but their
different source revisions prevent a controlled backend speed/memory comparison.
All 317 repository tests passed after the allocation guard, including the
coaching regression suite. No evaluator or coaching source changed.
