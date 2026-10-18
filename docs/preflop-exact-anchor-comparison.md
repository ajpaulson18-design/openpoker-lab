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

## Formal saved observations

The [raw report](../benchmarks/results/preflop-exact-anchor-v1.json) passes from
clean source `a818a0658eca7dbee9029967b81d66eed2e7e381` on Python 3.12.14 /
Windows with the explicitly identified MSVC native V2 build. All 464 LF-normalized
source hashes match the normalized Git blob contents at that freeze. Source
snapshots and native executable/manifest identities remain unchanged; all rank
and board-enumeration guards are zero. All 14 full-request admissions pass.
The largest Python/native complete modeled-loop envelopes are respectively
125,221,024 and 46,747,424, below the unchanged 500-million ceiling.

All 36 timed policies and two separately traced policies pass independent
physical-count replay, strict exact value containment and the profile-error
bound. Fresh saved-file verification reconstructs all 38 assessments and 19
paired comparisons. Final repeated payloads are deterministic within each
backend/algorithm. Maximum cross-backend metric and policy gaps are respectively
`1.256e-13` chips and `3.773e-12`, passing the unchanged `1e-8`/`1e-6` gates.

| Algorithm | Python NashConv at 10 / 100 / 1,000 / 8,000 iterations, chips | Final absolute value error, chips | Final Python / native median seconds |
| --- | --- | ---: | ---: |
| Vanilla CFR | 0.241456 / 0.0454830 / 0.0122414 / 0.00384792 | 0.000362004 | 1.120660 / 0.028964 |
| DCFR | 0.296018 / 0.0306912 / 0.00820542 / 0.00363563 | 0.00114132 | 1.448469 / 0.027993 |
| CFR+ | 0.0301236 / 0.00237206 / 0.000257046 / 0.0000401948 | 0.0000000311993 | 2.555989 / 0.042950 |

The exact rational values and both backend results remain in the report. All
10-iteration profiles miss 0.005 chips; vanilla/DCFR also miss at 100 and 1,000.
These preregistered nonfatal observations are retained. Both final CFR+ profiles
pass the mandatory target, and all other final profiles also pass. A small
equilibrium-value error alone would not establish low exploitability.

Final native complete calls are faster on this measured game. At ten iterations
its process/adapter overhead makes it slower than Python; no general speedup
claim follows. The separate 1,000-iteration Python/native allocation peaks are
52,929 / 313,328 Python bytes, taking 1.980895 / 0.035974 seconds. Native uses
more traced Python allocation here. Child-process allocation and RSS remain
unmeasured. Neither result implies native memory savings.

Canonical report SHA-256 (excluding its checksum field):
`0b6076e0f6248810c3fc2b3348d912c4fd92f14cd8b584a0805f493a7b6d6d8f`.
Raw saved-file SHA-256:
`465f9cac5aeddcd911bc97f84a30d4baaa41b82ff515bc238788f56bb4e2828e`.
The specification and numerical source were frozen before measurement. Publishing
this report adds only evidence, documentation and an actual-artifact regression.
Final CI and merge evidence are recorded on the associated pull request.
