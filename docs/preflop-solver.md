# Bounded preflop games with physical flop chance

`pokerlab.preflop_solver.solve_preflop` connects the existing blind-aware
preflop component to physical flop chance and the existing configured postflop
trees. This adds complete finite heads-up games starting before the flop.
It does not solve full-deck preflop or unrestricted no-limit Hold'em.
Existing postflop, turn/river, training-kernel and AI Coach source is unchanged.

```python
from pokerlab.preflop_solver import solve_preflop

result = solve_preflop(
    "AsAd", "KsKd",
    config={"starting_stack": 4, "max_raises": 0},
    runouts=["2c3c4d7h8h", "Kc2d3h7s8c"],
    iterations=1000,
    algorithm="dcfr", traversal="planned",
)
print(result["value_sb"], result["nash_conv"])
```

## Game and probability meanings

Global player 0 is the small blind/button and acts first preflop; player 1 is
the big blind and acts first on each live postflop street. Starting stacks
include blind posts. Settlement refunds unmatched chips, carries the matched
pot forward and derives remaining stacks. Fold and showdown payoffs are net
zero-sum chip transfers from the whole hand, including matched blinds exactly
once. All-in preflop leaves integrate latent runout payoffs with no later
decisions; later all-in leaves reuse the existing chance trees.

Each requested outcome is five distinct cards: an unordered first-three-card
flop, then ordered turn and river. Flops canonicalize by rank then suit.
Flop permutations are duplicates and rejected; swapping turn and river
produces a distinct outcome. Board/private and private/private collisions
are removed. For an unblocked private pair there are
`C(48,3) * 45 * 44 = 34,246,080` physical outcomes. Each selected compatible
world receives its product of range weights divided by this denominator,
and the entire joint distribution is normalized once.

Selected outcomes define a **conditioned game**. They can shift private-hand
priors through blockers. They are not samples estimating the unconditional
full-deck game. Returned `private_pair_probabilities` make the shift auditable.
For the weighted fixture, the first SB combination's conditional probability
is `4/4.625`, rather than its initial range proportion `0.8`.

Preflop uses `PreflopConfig` or its serialized mapping. `flop_config`,
`turn_config` and `river_config` accept action-only dictionaries containing
`bet_sizes`, `raise_sizes`, `max_raises` and `include_all_in`. Defaults are one
half-pot opening size, no raises and an optional shove. Turn and river inherit
the flop options independently, with explicit overrides. Pot/stack fields and
`RiverConfig` objects are rejected: those monetary values must be derived from
the settled preflop branch. Live branches outside the shared `RiverConfig`
pot/remaining-stack bounds are rejected instead of silently omitted.

Strategies expose `preflop-strategy-v1`: player `sb`/`bb`, own hand, current
street, `revealed_board`, complete public history and legal action probabilities.
Sized `history_key` tokens and `raise_to` use cumulative whole-hand contributions;
`amount` is the chips added by that action. No opponent hand or unrevealed card
enters an information-set key. Average-policy values and both exact legal best
responses accompany NashConv and exploitability (NashConv/2).

## Resource and model limits

Recursive and planned vanilla CFR/DCFR are supported. Optional
`algorithm="cfrplus"` uses the existing repository CFR+ trainer with recursive
traversal only; planned CFR+ is rejected before ranking worlds. It alternates
SB then BB regret updates and averages the completed profile with linear
iteration weights and own-player reach, with delay zero. Each iteration uses
three world passes, counted in the 30-million world/decision work guard and
reported in `training_passes_per_iteration` and `training_passes`. Terminal
games without information sets perform zero training passes. Legacy method
defaults and result fields are retained. See the
[CFR+ comparison and provenance](preflop-cfrplus.md).

Public batching is
not exposed through this adapter. The generic public-batched trainer assumes a
positive initial pot, whereas this hand starts with zero chips before blinds.

Requests are limited to 10–10,000 iterations, 300,000 selected outcomes,
three million candidate-pair iterations and three million world iterations.
Enumeration preflight is capped at 30 million pair/outcome checks. Complete
trees have aggregate caps of 250,000 public states and 10,000 decisions; work
is capped at 30 million world/node iterations and planned traversals at
250,000 operations. Outer outcome iterables and inner card iterables are bounded
before materialization. Full-deck requests fail before world/ranking allocation.

One temporary existing postflop template is built, cloned under aggregate caps,
and released at a time. Its separate limits are 250,000 states and 10,000
decisions. Temporary and final trees can coexist while cloning, so the state
cap is not a process-memory ceiling. Returned metadata records template peaks.

This remains a finite fractional betting abstraction: no full-deck preflop,
multiway equilibrium, rake, range inference, card abstraction or chance sampling.
The reused postflop builder has no blind-sized minimum opening bet. Convergence
and runtime evidence for tiny selected games does not certify broader games.

## Independent validation and provenance

Run from the repository root:

```text
python -m unittest tests.test_preflop_solver tests.test_preflop_validation -v
python -m scripts.benchmark_preflop_solver
```

The [fixture specification](../benchmarks/preflop-solver-v1.json) checks three
games at 100 and 1,000 iterations, both algorithms and both traversals. The
[report](../benchmarks/results/preflop-solver-v1.json) records three complete-call
timing repeats, a separate complete call under tracemalloc, source/configuration
hashes, revision/platform information and independently checked values and BRs.
Tracemalloc measures Python allocations, not RSS. Timing excludes the oracle.

All 24 checkpoints passed at source `7b5694f` on Windows/Python 3.12.14;
the largest scalar oracle difference was `3.34e-16` chips. At 1,000 iterations:

| Fixture / algorithm | Worlds / information sets | Recursive / planned seconds | Recursive / planned peak Python bytes |
| --- | ---: | ---: | ---: |
| Live four-street / vanilla | 2 / 86 | 2.888 / 1.181 | 194,446 / 198,084 |
| Live four-street / DCFR | 2 / 86 | 1.985 / 1.477 | 194,062 / 198,084 |
| Weighted asymmetric / vanilla | 8 / 338 | 9.532 / 5.562 | 694,010 / 670,672 |
| Weighted asymmetric / DCFR | 8 / 338 | 11.014 / 7.291 | 639,506 / 810,992 |

These are three-call medians on a shared machine, not universal speedups or
memory reductions. Final NashConv for these fixtures is respectively
0.0147832/5.99550e-7 and 0.00970026/7.55582e-7 chips (vanilla/DCFR).
The benchmark enforces independent scalar/backend agreement within `1e-10`,
private-pair probability agreement within `1e-12`, improvement from 100 iterations,
and final gaps below 0.02 vanilla / 0.001 DCFR. The report's dirty flag reflects
documentation/report and regression-test work during measurement; the listed
solver/oracle/harness/configuration sources were committed and unchanged.

`scripts/preflop_validation.py` independently enumerates physical worlds,
all 21 best-five candidates for each seven-card hand, numeric betting states,
chip transfers and legal actions. It replays serialized policies and computes
exact responses while grouping hidden worlds by the responder's own hand and
revealed history. It shares only card/range input parsing; production tree,
ranker, utility, trainer, evaluation and BR helpers are not oracle inputs.
It checks every reachable serialized row, including zero-probability branches.
Rational anchors cover blocker shifts, short-blind refunds and an adversarial
case where illegal future-flop peeking earns 0.25 chips versus the legal best
response's 0. Independent category anchors check the new oracle ranker; this
is not a new exhaustive certification of the unchanged production evaluator.

The separate [complete fixed-flop chance fixture](fixed-flop-complete-chance.md)
extends coverage to every one of the 1,980 legal ordered future-card outcomes
for one exact private pair. A constructive equilibrium supplies an independent
known value of SB +1 / BB -1 in that specific conditioned game.

Luna implemented the bounded solver and focused tests; lead review supplied
the independent checker, benchmark and publication gates. New implementation
and checker code were written in this repository using the standard library.
No external source, dependencies, solver outputs or trained values were imported.
The adapter reuses the repository's published CFR implementations and their
documented provenance. The information-set constraint follows the published
[CFR formulation](https://webdocs.cs.ualberta.ca/~bowling/papers/07nips-regretpoker.pdf)
by Zinkevich, Johanson, Bowling and Piccione (2007); this is an implementation
and validation of finite games, not a claim to reproduce a commercial solver.
