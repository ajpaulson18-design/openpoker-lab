# Fixed-support flop prior reweighting

This separate research path changes positive private-hand weights on the same
fixed flop card support and action tree. It is a **no-training** proof milestone;
no newly weighted equilibrium, convergence, speed or unrestricted NLHE claim
follows from the planner or synthetic tests.

## Model and early admission

The board is `2c3d4h`, OOP hands are `AsAd` / `QsQd`, and IP hands are `AsKh` /
`KsKd`. Pot 10, stack 5, half-pot betting, no raises and no optional all-in keep
the existing fixed numeric flop/turn/river tree. Existing street kernels and
Coach are unchanged. The overlapping `AsAd` / `AsKh` pair is removed before
one global normalization of the remaining hand-weight products.

The rank-free planner accepts two exact two-tuples of positive integers or
`Fraction` values; bools, floats, strings, zero, negatives and changed supports
are rejected. Input numerator/denominator components have at most 128 bits.
The common denominator of all normalized per-runout masses must fit the
unchanged 384-bit candidate envelope before any physical preparation. This
extra condition can reject otherwise valid 128-bit inputs. Planning establishes
neither card-ranking provenance nor quotient equivalence.

| Frozen case | OOP weights | IP weights | Global blocker normalizer | Compatible pair priors |
| --- | --- | --- | --- | --- |
| Baseline | 1, 1/2 | 1/4, 1 | 13/8 | 8/13, 1/13, 4/13 |
| Uniform | 1, 1 | 1, 1 | 3 | 1/3, 1/3, 1/3 |
| Skew | 4, 1 | 4, 1 | 9 | 4/9, 4/9, 1/9 |

Pair order is `AsAd`/`KsKd`, `QsQd`/`AsKh`, `QsQd`/`KsKd`. Physical records
canonicalize each hand's card order (for example `AsAd` becomes `AdAs`), while
retaining roles and physical identity. Every compatible pair has 45 x 44 =
1,980 ordered future reveals: 5,940 worlds in each full physical game.

## New-prior proof boundary

`WeightedClassModel` is distinct from the published old-prior `ClassModel`.
It holds a genuine authenticated old physical baseline and a separately built
weighted physical oracle. It checks exact world mass `pair_prior / 1980`,
normalizer, complete support, showdown signs, pair outcomes/probabilities,
source counters derived from support, numeric tree, node index and own-hand
visibility. The old world SHA authenticates the genuine baseline only; each
weighted oracle has its own reported world SHA.

A fresh candidate partition is independently checked against every weighted
physical row, per-pair river signature, turn posterior and reveal transport.
All 30,812 numeric public states are compared during collapse. Every model
consumption reauthenticates its physical data and rebuilds the quotient; it does
not rank the deck again. The admitted compact shape remains 126 worlds, 1,001
public states and 466 policy rows, versus 16,912 physical policy rows.

Four deterministic controls (`check-call`, `bet-fold`, `class-varying`,
`zero-reach`) exercise projection/lift and off-path responses. The audit requires
all eight exact compact metrics to equal unrestricted physical own-hand best
responses, independent numeric replay within 1e-10, and a bitwise policy lift
round trip. Hidden opponent hands and future cards are integrated before a
legal response maximizes. The old baseline controls must reproduce their
published exact metrics, class policy and physical strategy hash. Controls are
not trained strategies and have no equilibrium-quality target.

## Frozen execution and retention

The [protocol](../benchmarks/flop-class-reweight-proof-v1.json) admits all three
plans before any ranking, cheaply authenticates the immutable old proof and
preserves its interruption record. The single batch uses one baseline oracle
plus three independently prepared weighted oracles, for 23,760 enumerated
world rows and 12 control audits. At most the baseline and current case's
physical oracle are retained; references are released and GC runs between cases.
These are census/capacity admissions, not complete arithmetic/CPU, allocated
memory, elapsed-time or RSS bounds. Existing physical oracle caps remain intact.

The run requires clean committed source, with exact revision/status/LF manifests
before and after each case and overall. It reserves a new directory outside
source, saves active work before execution, and writes three preparation and
12 complete physical-policy/audit gzip files with raw/compressed hashes.
Failures retain partial files and tracebacks, stop later work and never retry.
The compact index omits duplicated policy rows but the complete rows remain in
the bounded gzip artifacts. All 41 forbidden production authorities must have
exact integer zero counters; no trainer is called. Wall/CPU/UTC/runtime and the
temporary Windows execution-state request are incidental receipts only.

No real new-prior proof experiment has run at this source checkpoint. The
planner, proof and harness have focused synthetic tests; execution and saved
verification remain separate evidence. No third-party source or dependency was
incorporated. See the [licensing boundary](research/LICENSING.md),
[old quotient proof](flop-public-classes.md),
[primary cost study](flop-class-call-cost.md) and
[phase attribution](flop-class-phase-profile.md).
