# Prepared trainers against an exact preflop value

This experiment measures finite-iteration strategies in precisely the weighted
one-raise game certified by the [independent exact witness](preflop-weighted-sequence.md).
The [frozen specification](../benchmarks/preflop-exact-anchor-v1.json) pins the
ranges, 19 public states, physical counts and rational equilibrium value
`100107990869/130471452826` SB net-transfer chips. Production defaults, shared
kernels and later-street work remain unchanged.

## Questions and fixed checks

The runner will compare Python and explicitly source-built native training for
vanilla CFR, DCFR and CFR+ at 10, 100, 1,000 and 8,000 iterations. Both use the
existing prepared-counts admission and explicit pair-mean world indexing. The
three compatible private pairs retain their globally conditioned priors; all
5,136,912 physical final boards remain hidden and integrated through their
previously enumerated W/T/L counts. No new card ranking or enumeration is allowed.

The saved rational certificate is independently reverified before using its
value as an anchor. A separate numeric-rule replay validates every serialized
trained strategy against pinned physical counts. It constructs legal own-hand
best responses and exact rational profile values from the binary64 probabilities,
normalizing each row exactly. The strict best-response interval
`[-BR_BB, BR_SB]` must contain the exact game value. Here `BR_BB` is BB's own
utility. The absolute profile-value error must be at most NashConv. These
mathematical checks use Fractions without numeric padding.

Every strategy must also agree with its independently replayed metrics within
`1e-10` chips. Python/native metric and probability agreement use the existing
`1e-8` and `1e-6` tolerances. A policy is never required to equal the particular
LP equilibrium: alternate equilibrium policies and unreachable rows can differ.
No monotonic convergence requirement is imposed across checkpoints.

The 8,000-iteration CFR+ profiles must meet the existing 0.005-chip NashConv
target. Earlier and non-CFR+ misses remain visible observations. All requested
work is admitted before native build lookup or training; no caps, quality gates
or iteration counts are relaxed after observation.

## Measurement and publication status

Early checkpoints have one paired call each, reported as individual samples.
The final checkpoint has three paired calls with alternating backend order;
only those final calls supply medians. Complete calls include solver execution,
canonical JSON serialization and SHA-256. Independent replay, input loading,
garbage collection and source/build checks stay outside the timed interval.
All raw policies, failures, hashes, phase counts and forbidden ranking counters
are retained.

Separate 1,000-iteration CFR+ calls trace Python allocations for each backend.
They do not contribute to timing medians. These traces exclude native subprocess
allocations and process RSS. Timings and allocator peaks are observations for
this fixture and runtime; there is no speed or memory-saving acceptance gate.

Implementation and clean-source saved-report measurement are pending. The
specification was committed before the formal comparison; passing reference
certificates do not establish finite-iteration convergence for the trainers.
