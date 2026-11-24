# Joint chance sampling: the next architecture gate

This records a mathematical design and its independent deterministic gate. It
does not establish native admission or a training result. It
continues the [sparse epoch foundation](sparse-policy-epochs.md) toward realistic
heads-up ranges. The existing eleven-card resource rejection remains binding.

## Why storage compression alone is insufficient

For the existing fixed betting template and one full-deck public board, the
per-seat decision counts by street are 3, 16, 58 and 140. The corresponding
action-slot counts are 8/7 preflop, then 42, 144 and 326 per seat. The supported
own-holding counts are 1,326, 1,176, 1,128 and 1,081. Multiplying gives 479,116
rows and 1,148,350 slots for that one board. This is a structural census, not
execution or an allocation measurement.

The current two-bank numeric forecast would require
`2 * 1,148,350 * (649 + 382 + 64) = 2,514,886,500` payload bits before all
metadata. The current entry model requires 41,371,168 entries. Both exceed the
unchanged component limits. Those widths are the current PROOF9 owner contract;
they are not a proved full-deck numeric bound. Even a hypothetical packed
factorization that fits the numeric payload would leave row validation and
quantization costs, plus the growing union of histories from different boards.

## Estimator and information boundary

Let a world `w = (SB holding, BB holding, complete board)` have the globally
blocker-conditioned physical probability `P(w)`. Freeze the entire Q52 policy,
sample `w` with `q(w) = P(w)`, and expand every betting action for that world.
An information row still contains only actor, own holding and complete visible
history. Opponent cards and hidden future cards never enter its policy key.

For the selected own holding at row I, use these raw increments:

```
R[I,a] = opponent_past_reach * (action_value[a] - policy_value)
A[I,a] = own_past_reach * policy[I,a]
root   = frozen_policy_value_for_this_world
```

Other own holdings receive zero in that observation. The usual importance
factor `P(w)/q(w)` is one. There is no additional prior, board probability or
prefix-marginal multiplier. Both seats share the same world and frozen policy.
Zero-policy branches remain expanded.

Taking expectation sums physical probabilities over every world compatible
with the information row. This gives the literal joint raw regret. For
averages, perfect recall makes own reach and policy constant over those worlds,
so their summed probability supplies exactly the physical own-hand/prefix
marginal. The root expectation is the literal frozen-policy value.

This is different from the public-board estimator's prefix correction. Carrying
its `1/q(prefix)` factor into this estimator would be incorrect. Unbiased raw
increments also do not make quantized next policies or normalized average
policies unbiased, and do not establish convergence.

## Exact sampling without a quadratic retained pair table

For opponent integer weights `b[g]`, form total weight T, per-card weights C,
and exact same-holding weight E. For own holding `h={c1,c2}`:

```
compatible_mass[h] = T - C[c1] - C[c2] + E[h]
Z = sum(own_weight[h] * compatible_mass[h])
```

The inclusion-exclusion identity already underlies
[`full_deck_public_chance.hpp`](../native/full_deck_public_chance.hpp).
These summaries take linear preparation work in the range sizes. A uniform
integer ticket in `[0,Z)` first selects the own holding interval; divide its
local offset by that holding's weight to select the compatible opponent
cumulative interval. Zero-compatible intervals are never selected. This avoids
a second bounded random draw with holding-dependent failure probability.

After excluding four private cards, the number of canonical-flop and ordered
turn/river boards is `choose(N-4,3) * (N-7) * (N-8)`: 20 at N9 and 34,246,080
at N52. Exact ticket generation, board unranking and all resource bounds need
their own controls before a sampler is admitted. There is no RNG implementation
or full-range admission in this design record.

## Fixed N9 gate before native changes

The existing priors give three compatible private pairs with integer weights
3, 8 and 18, normalized by 29. Each has 20 boards, so there are 60 positive
worlds and 580 equally weighted pair/board tickets. Uniform selection among the
60 worlds would change the game.

For one sampled world the unchanged betting skeleton has 434 decision rows and
1,039 slots, independent of the number of supported private holdings. Under
the existing route/stake proof, sufficient sample denominators are `2^625` for
R and `2^364` for A. Two observations require at most 631 regret magnitude bits
and 366 average bits. The executed reference checks the corresponding one-sample
bounds; these do not describe a native implementation. The retained
union still grows with newly sampled holdings and visible histories.

The first acceptance gate is a deterministic full expectation over all 60 worlds
for complete frozen Q52 profiles, including zero-policy branches. It must
compare every raw R/A slot and both roots with the separate literal joint
reference, verify all 580 tickets, and group prefix marginals independently.
Tests must preserve identical policy lookup for identical visible information
despite different opponent holdings or future cards. Source must be frozen
before execution, with complete policies, failures and resource receipts kept.
Native coupling, a longer bounded lifecycle, RNG and independently replayed
saved-policy quality follow as separate gates. No resource limit is raised.

## Executed independent gate

Reference source `d11fc29` was committed before execution. At execution head
`4e54249e4d02190539b156503a3a9175e190abe5`, all seven controls pass normally
and with optimized Python. Each complete expectation checks 60 worlds and
all 580 tickets for both uniform and zero-skew full Q52 profiles. Every one of
the 24,420 rows and 58,164 slots, and the root, matches the separate literal
joint update. A separate grouping of literal worlds verifies physical
own-hand/prefix marginals against ticket counts. Shared visible flop rows retain
identical policy and average increments when hidden opponents or future cards
change. Zero-own-reach and zero-policy branches can still have nonzero regrets.

The complete request preflight reserves 250-million modeled work, seven-million
logical entries and 15,405,760,000 cumulatively created bits under the unchanged
500-million/eight-million/sixteen-billion limits. Its 2,048-bit intermediate
forecast is below the unchanged 4,096-bit ceiling. The explicit entry partition
totals 6,909,632 and covers up to 64 retained scalar results; the full expectation
streams one at a time. These are conservative source-derived logical bounds,
not allocation/RSS or throughput measurements. Concurrent test durations are
not performance comparisons.

The [source and check receipts](../benchmarks/results/joint-chance-sample-v1/manifest.json)
retain all 24 source files, both original test logs, and the normal/optimized
published target-proposal packet replay reports. This is a post-run raw-source
capture matched to the previously frozen commit, with that timing disclosed.
Per-world sample tables are not retained in this check packet; the tests
recompute and compare them internally. The complete input policies remain in
the separately authenticated target-board packet. The next section records the
subsequent native coupling. Longer learning, an admitted RNG and independent
saved-policy quality remain separate gates.

## Executed native coupling

Native source was frozen at `b033782` before compilation. A signed/unsigned
comparison warning stopped the first whole-game build under `/WX`; `ae88da4`
corrected the selector constants. Independent controller source `8c42ee1`
was committed before the six-request matrix ran. This path remains explicitly
fixed to the N9 ranges and betting template; it adds no production default.

The existing Prepared owner now supplies a scoped joint-ticket certificate.
It preserves original holding indices, constructs compatible masses with a
linear card-bucket inclusion/exclusion sum, un-ranks the board, and ranks only
the two selected holdings. Its callback lifetime and poison guards reject
nested or conflicting queries. All 580 ticket/board/sign records match the
independent Python law and ranker, normally and optimized. The existing
Prepared constructor still has broader storage and cross-range costs; this
component result does not establish full-deck preparation.

The existing sparse Store has a constructor-bound true-joint arithmetic mode.
It requires exactly `2^625` regret and `2^364` average denominators and rejects
mixed public-board laws or scales. The legacy mode retains its original
denominators and behavior. Sixteen native guards and three independent component
controls pass normally and optimized. Two earlier duplicate-stage fixtures
failed before reaching the intended predicate: one hit its row capacity, and
the next had inconsistent per-epoch/union reservations. Both failures remain
preserved. The corrected fixture changes no Store arithmetic or resource cap.

The new scalar walk reuses Template, full History, Catalog and frozen EpochLease.
It performs two genuine target passes, with 434 staged rows, 1,039 slots and
868 policy reads per observation. Every betting action remains expanded.
Conditional values use the fixed `2^625` grid. Before multiplying by opposite
past reach, the walk checks and removes the exact corresponding power of two;
this avoids constructing an approximately 995-bit intermediate. The current
walk's checked peak bound is 683 bits. No weighted marginal or terminal
contractions are used by this estimator.

The whole-request forecast covers all 336,400 ordered pairs of the 580 tickets
before Template or private preparation. It reserves 117,690,568 modeled work,
954,355 logical entries, 52,441,006 payload bits and 502,720 output bytes under
unchanged caps. Source allocation allowances remain logical reservations,
not a complete allocator census or RSS measurement.

Six complete requests pass normally and optimized: different private pairs,
reversed order, repeated world, equivalent tickets, shared flop with changed
future cards, and boundary tickets. Seven real CLI rejections exit 2 with empty
stdout. Two saved-image corruption controls reject. Independent replay checks
every cumulative signed regret, exact average, both roots and all 24,420 policy
rows including implicit defaults. E2 uses E1's committed policy. One detached
raw image is live at a time, and neither snapshot is published until both
observations and final cumulative checks succeed. Normal/optimized native
streams match exactly. Saved-only replay passes in both modes with zero
candidate calls and no archived-source execution.

For tickets `(0,0)` then `(11,0)`, E1 retains 434 numerical rows/1,039 slots;
E2 retains 865/2,071. There are 1,736 policy reads, 868 staged rows, 702 changed
regret rows quantized, four selected-hand ranks and zero weighted contractions.
The named request charges 105,483,197 modeled work and writes 501,592 bytes.
These are logical counters, not a measured speedup or CPU bottleneck profile.

The changed shared owners also pass the legacy Prepared controls (17 tests),
sparse Store controls (four tests), and complete public-board epoch matrix,
normally and optimized. All thirteen historical public-board native streams
and the original 3,130-byte synthetic Store stream remain byte-identical.
The independent full unit suite at the earlier isolated `f127f09` revision
passes 3,259 tests with 174 skips and observed exit 0. It does not certify the
later native changes. Dedicated Windows/Linux/sanitizer checks for the new
joint path pass at `2920bdc`, including complete current-math saved replay
([hosted run](https://github.com/ajpaulson18-design/openpoker-lab/actions/runs/45295713233)).
The older standalone Windows History compiler failure remains separate and
unresolved; the repository is not presented as globally green.

The [immutable native joint evidence](../benchmarks/results/joint-two-epoch-v1/manifest.json)
retains both full matrices, component streams, legacy regressions, build and
source identities, and the original compile/test-fixture failures. Eight
archives each stay below the existing eight-MiB compressed/member ceilings.
The first packaging attempt refused an oversized combined legacy archive
before creating output. Splitting the legacy evidence retained all data and
kept those ceilings unchanged. Reconstructed Git source is explicitly labelled
where original raw checkout capture was unavailable. The packet also keeps
the earlier full-suite result under its own revision scope.

Realistic weighted-range preparation, longer bounded learning, RNG and saved
policy quality remain open. The older eleven-card rejection is unchanged.
