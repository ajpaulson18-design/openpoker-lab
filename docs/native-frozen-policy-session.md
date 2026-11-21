# Persistent immutable policy session

The explicit `virtual-frozen-policy-session` target shares one catalog, History,
resident State policy import and Prepared Chance owner across two complete
[fixed-policy raw walks](native-frozen-grid-raw.md). Both results remain owned
until both walks finish. It echoes the complete policy once and publishes one
bounded response. It does not change policies, accumulate numerical State,
clip regrets, select random boards, train or evaluate quality.

This is a necessary setup-amortization gate for a future sampled architecture.
The existing exhaustive trainer and its [native walk profile](native-training-phase-profile.md)
remain separate: State staging/quantization and terminal work are still the
measured training bottlenecks. Sharing a frozen import does not resolve the
[eleven-card resource forecast](native-dyadic-storage-census.md).

## Lifetime and bounds

Both proposal/board selectors validate before shared owners are built. The
session imports/seals one complete Q52 image through the existing State owner.
Each raw walk borrows those same owners and independently evaluates both global
seats, including policy-zero actions and zero-full-target prefix averages.
Selectors may repeat; repeated selectors consume two complete raw lifetimes.
Prepared may reuse its existing bounded rank-plane cache across the walks;
the forecast still reserves each board's complete rank-fill/query allowance.
No per-board State, History or Chance meter resets.

The complete reservation is `C + V(B1) + V(B2)`: shared template/catalog,
input/import/seal, one policy echo and one Chance setup in C; each board's
raw traversal, policy reads, prefix/terminal contractions and retained stage
in V. State read lifetime is `24420 + 2*r1 + 2*r2`. Parent work includes the
catalog once, both six-family raw ledgers and 1,024 session metadata units.
Both retained stages and their scratch bounds count in peak entries/payload.
The 1,040,000-unit source/selector scanner fits inside the existing three-million
geometry family alongside the original 149,420-unit Forecast scanner.

The independent numeric-rule reference proves exact per-axis maxima over
25,401,600 ordered selector pairs (replacement allowed). Every axis separates
as C plus two board contributions, so `C + 2*max(V)` proves its maximum without
materializing the Cartesian product. Maxima need not occur on the same pair.

| Logical reservation | Pair maximum | Unchanged ceiling |
| --- | ---: | ---: |
| Whole work | 316,294,067 | 500,000,000 |
| History work | 39,784,400 | 42,000,000 |
| State work | 55,075,516 | 75,000,000 |
| Chance work | 2,579,498 | 110,000,000 |
| Parent work | 8,209,324 | 115,000,000 |
| Entries | 1,184,881 | 2,000,000 |
| Integer payload bits | 263,169,724 | 1,073,741,824 |
| Output bytes | 1,936,776 | 2,100,000 |

These are logical bounds, not allocator/RSS measurements or CPU shares.
The owner graph still materializes the complete 24,420-row/58,164-slot catalog.
Its conservative storage reservation is unchanged; no wider capacity credit
is taken for policy-only residency.

## Wire and validation

`OPLGEP01` introduces one 136-byte cumulative header, the complete 1,442,112-byte
policy body, two board records and a 208-byte global completion footer. Each
`OPLGBD01` record has a 256-byte reference-schedule header, 264-byte denominator
and roots, raw row/slot payload and a 208-byte delta footer. Its reference
schedule fields describe the existing single-board bound; cumulative admission
and actual totals live in the global frame. Total size is
`1,443,912 + 136*(r1+s1+r2+s2)`. Signed integers retain the existing 704-bit
two's-complement wire carrier and portable 32/64-bit Boost limb handling.

At source `677bf51`, local MSVC compilation and normal conformance pass.
Twelve independent requests cross two complete policy profiles with reversed
board order, repeated selectors, different compatible private pairs, a zero
full-target board with shared turn, a zero-at-flop board, and maximum retained
row/slot staging. All policies, regrets, prefix averages and roots match the
independent Fraction/rules/rank oracle. Per-board State/History read deltas and
all six raw family charges match independent equations; cumulative scope/work,
one import/echo and exact output bytes also match.

Seven further requests reject malformed second proposal/board, arity, extra
selector and late invalid policy partition with no stdout. Saved root-bit and
truncation corruptions reject independently of stream hashes. Maximum observed
modeled work is 223,700,123 and output is 1,936,776 bytes. Optimized conformance,
cross-platform CI, immutable packaging and matched elapsed comparison are
separate pending checks; no speed acceptance is claimed from these counts.

## Next architectural gate

Measure complete cold two-call versus shared-session work before accepting an
amortization benefit. Then replace repeated dense immutable import with a
validated changing-policy epoch and sparse/paged numerical ownership. Keep
raw importance-weighted regret estimation distinct from nonlinear CFR+
clipping: unbiased raw updates alone do not prove sampled CFR+ correctness.
Changing-policy quality needs independent saved-policy evaluation and legal
visible-information best responses. Realistic heads-up NLHE, full-deck
capacity, convergence and product readiness remain unresolved.
