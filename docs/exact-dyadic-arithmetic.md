# Exact integer arithmetic in the unified selected-game solver

Status: integrated opt-in implementation with independently replayed
[source-frozen results](exact-dyadic-result.md); final CI/publication remain
acceptance gates. This extends the [exact-product four-street contract](exact-selected-kernel-contract.md)
and [compact output](compact-exact-policy.md). It does not change legacy rounded
chance, defaults, native protocols, legal game coverage or oracle limits.

`solve_four_street_exact_selected(request, exact_arithmetic="dyadic")` uses an
integer bucket/rank-sweep core for completed exact marginals and terminal vectors
inside the existing direct-DAG, packed CFR+ trainer and public diagnostics.
`exact_arithmetic="fraction"` remains the reference/default. Both accept either
expanded or compact diagnostic output; compact avoids production private-pair
queries. The arithmetic choice does not remove explicit policies/histories or
perform abstraction. All own-hand and visible-history rows remain distinct.

## Same-game arithmetic identity

For seat p, write each parsed binary64 weight as `A[p,i] / 2^e[p]`, choosing the
common exponent from every input hand, including board-blocked hands. The integers
are exact. The existing reference setup computes global mass Z; the integer plan
authenticates `Zint = Z * 2^(e[0]+e[1])` without private-pair enumeration. Setup
retains the reference Fraction normalization; it is not yet an all-integer parser
or probability implementation.

For one complete opponent reach vector, write `r[j] = R[j] / 2^d` with one common
exponent across its entire dimension. For original terminal scale `P / 2^f`, each
completed own-hand value is

`sum_B A[own,i] * sum_compatible_j(A[opp,j]*R[j]*sign(i,j,B)) * P / (Zint * 2^(d+f))`.

Fold scale carries the global SB payoff sign, inverted for BB. Showdown sign is
own rank minus opponent rank; BB receives no additional sign inversion. Prefixes
filter selected boards but never locally renormalize global Z. Marginals use
reach/payoff one. Per-card exclusion uses `total-card[a]-card[b]+same_holding` for
compatible mass; strict lower/higher rank sweeps give same-holding ties zero.
Exact signed integer sums preserve cancellation, and a Fraction is constructed
only after each query component is complete. The unchanged adapter then converts
that completed rational once, preserving ties-to-even and strict nonzero
zero/subnormal/nonfinite rejection after rounding. No intermediate float or
epsilon repair is introduced.

The explicit integer path rejects non-dyadic Fraction reach/payoff inputs before
rank/cache work. Its production callbacks are binary64 dyadics. The Fraction
reference continues accepting its existing general rational inputs. There is no
fallback when integer admission or input checks reject. Rank vectors retain the
existing bounded solve-local LRU; ranks are sorted per query. No new rank-order
cache or prefix terminal-value cache is claimed.

## Admission, storage and lifetime

The kernel reserves `20H+128` additional setup work and `8H+128` retained entries
before constructing its plan. The current plan reports `6H+84` logical entries.
Its owner is a weak reference: attaching the plan to the kernel creates no
kernel/plan cycle. Immutable input snapshots are checked on each query. Existing
bounded hostile-iterator snapshots, rank-cache cleanup and foreign-view adapter
checks remain in force.

Each shift/product/signed bucket/board sum/final denominator is forecast before
large integer/vector allocation or ranking. Whole-request admission additionally
forecasts all possible binary64 callbacks before information rows/training:
common reach exponent at most 1,074, aligned reach integer at most 1,075 bits,
opponent/own weight maxima, hand/board carries, original payoff scales and global
normalizer. The identity denominator `1 << (e[0]+e[1])` is included in setup size.
The aggregate logical integer-payload ceiling is `1<<30` bits (128 MiB of value
payload, excluding object headers/allocator). Its conservative envelope includes
`(8H+128)*setup_bits + (140H+800)*query_bits`; reference Fraction inputs, packed
strategy/history and other solve phases remain separately charged.

All previous bit, logical work, output, topology, history, array and whole-request
limits remain. The original 22-world T1000 request still rejects before ranking
or training. Faster arithmetic does not reopen that request. A future capacity
model needs a separate justified version and independent acceptance.

Receipts count integer adds/products/shifts, completed rational outputs, peak
operand/forecast widths and logical payload. A secondary subset model multiplies
counted integer operations plus four abstract operations per completed Fraction
by squared 64-bit limb width. It excludes Fraction GCD/LCM validation/bit
preflights, setup normalization/identity, reference queries, adapter conversion,
library/runtime costs and rank evaluation. It is not a complete arithmetic or
CPU bound and cannot replace whole-request logical admission. Actual counted
subset, operand and payload receipts must remain below admitted envelopes.

## Executed controls and next gates

The combined exact-product/dyadic/adapter/compact regression selection passes 60
tests. Five integration controls compare complete four-street policy rows and all
eight metrics, independently certify both results, forbid Fraction add/multiply
fallback inside integer query cores, preserve T1000 early rejection, reject
unsupported arithmetic before preparation, and prove no owner cycle with GC
disabled. Six helper controls compare literal pair/board Fraction queries across
prefixes, both seats, folds/showdowns, identical holdings, ties and tiny weights.

Terra independently executed seven adversarial controls, including 288 seeded
physical-deal/Fraction comparisons using the independent rank implementation,
signed win/loss cancellation, zero reaches, near-normal rounding midpoints,
subnormal input weights, non-dyadic rejection, a 65,530-bit reach and aggregate
payload rejection before rank/train work. Sol separately inspected formula,
allocation and lifetime boundaries; receipt scope was narrowed after that review.
The linked frozen result now records paired complete calls, retained misses and
saved-only numeric/exact replay: T10 median improves, T100 single call does not,
and traced allocation is higher. No general speed/RAM or broader convergence
claim follows. Eighteen new controls also pass optimized Python. Final CI remains.
Native integration, strategy/history compression and scalable certification stay
separate foundation work.
