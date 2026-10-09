# Optional CFR+ for conditioned preflop games

`solve_preflop(..., algorithm="cfrplus", traversal="recursive")` reuses the
repository's existing generic CFR+ trainer. It supports the same selected
physical outcomes, blind settlement, postflop action trees, serialized average
policy and exact legal best responses as the preflop adapter. No shared trainer,
turn/river solver or AI Coach implementation was changed. Vanilla remains the
default; vanilla/DCFR retain their original result fields and trainer paths.

This remains a bounded conditioned game, not a full-deck preflop solver. The
[preflop model limits](preflop-solver.md) still apply. Planned CFR+ is unsupported
and rejected before world ranking. A terminal all-in game with no information
sets bypasses training, returns exact settlement and reports zero actual passes.

## Method and independently implemented provenance

The unchanged repository trainer clips cumulative regrets at zero after
aggregating the weighted-world deltas for an information set. Each iteration
updates SB against a frozen profile, updates BB against SB's new policy, then
averages one completed profile using own-player reach and iteration weight
`t` (delay zero). This implementation uses three full world traversals per
iteration. The adapter multiplies its conservative world/decision work estimate
by three; it does not claim equal iteration counts imply equal compute budgets.

The method follows Oskari Tammelin's
[CFR+ paper (2014)](https://arxiv.org/abs/1407.5042); alternating updates have
separate theoretical treatment in Burch, Moravcik and Schmid's
[Revisiting CFR+ and Alternating Updates (2019)](https://arxiv.org/abs/1810.11542).
The precise post-sweep, own-reach averaging schedule above describes this
repository's reference implementation; it does not assert equivalence to every
published CFR+ averaging variant. Published speedups are not imported claims.
The integration, tests and benchmark were independently authored here, using
only existing repository code and Python's standard library. No third-party
source, dependencies, trained policies or commercial solver outputs were added.

## Reproducible correctness and comparison

```text
python -m unittest tests.test_preflop_cfrplus tests.test_preflop_solver tests.test_preflop_validation
python -m scripts.benchmark_preflop_cfrplus
```

The [specification](../benchmarks/preflop-cfrplus-v1.json) fixes three games,
three algorithms, 10/100 iterations and three timed repeats: 18 checkpoints.
The [report](../benchmarks/results/preflop-cfrplus-v1.json) records source revision
`ad432de8a69ab5d36e088cf9bacda43de2746d8d`, source/configuration hashes and the
Windows/Python 3.12.14 environment. The dirty flag reflects the untracked draft
report; the listed measured sources were committed and unchanged. Source hashes
include config normalization and the independent oracle.

Each checkpoint independently reconstructs world weights, enumerates best-five
showdowns, replays every serialized information-set row from numeric betting
rules and computes exact legal best responses. Production tree, ranking,
training, value and best-response helpers are not oracle inputs; only card/range
parsing is shared. Maximum scalar difference was `3.34e-16` chips; posterior
probabilities agreed within `1e-12`. Gates require endpoint gap improvement
(or equality at zero), final CFR+ NashConv below 0.1 chips for these fixtures and
the hidden-flop root's independently known value and legal BR gap of zero.
These endpoint checks do not establish monotonic convergence at every iteration.

| Game / method | NashConv at 10 | NashConv at 100 | Median seconds at 100 | Peak traced Python bytes at 10 |
| --- | ---: | ---: | ---: | ---: |
| Hidden-flop root / vanilla | 0.025 | 0.0025 | 0.0041 | 15,242 |
| Hidden-flop root / DCFR | 0.000649351 | 7.38880e-7 | 0.0037 | 14,554 |
| Hidden-flop root / CFR+ | 0 | 0 | 0.0116 | 13,274 |
| Shared flop/turn / vanilla | 0.708598 | 0.0745186 | 0.3104 | 299,852 |
| Shared flop/turn / DCFR | 0.454141 | 0.000516756 | 0.2940 | 298,068 |
| Shared flop/turn / CFR+ | 0.234217 | 0.00255088 | 0.5773 | 296,884 |
| Weighted blockers / vanilla | 1.18476 | 0.0970026 | 1.0196 | 637,842 |
| Weighted blockers / DCFR | 0.664795 | 0.000745496 | 0.9281 | 636,338 |
| Weighted blockers / CFR+ | 0.188520 | 0.00205319 | 1.8518 | 634,978 |

NashConv is the sum of both players' legal gains over the serialized average
profile, in whole-hand chips. Runtime measures a complete solve call including
tree/world construction, training, exact responses and serialization, excluding
independent replay. Separate tracemalloc calls cover **10 iterations only**;
there is no 100-iteration memory measurement, RSS measurement or process-memory
ceiling. These are small-game observations on a shared machine, not universal
performance or memory claims.

CFR+ achieves the smallest 10-iteration gaps in these fixtures. At 100 iterations
DCFR is faster and has smaller gaps in the two nontrivial multi-street games.
This evidence supports retaining CFR+ as an optional reference method and
keeping existing defaults. Broader practical flop ranges, complete-deck
scalability and equal-time comparisons remain separate milestones.

The five focused tests additionally cover deterministic weighted policies with
blocker-changing nonzero payoffs, a preflop decision hiding future flops,
unmatched-blind refunds with nonzero settlement, legacy terminal parity,
early unsupported-traversal rejection and three-pass work rejection before the
trainer runs. Luna implemented the bounded adapter and tests; lead review
supplied measurements and publication validation, with a separate Luna
provenance review.
