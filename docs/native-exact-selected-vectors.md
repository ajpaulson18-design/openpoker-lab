# Bounded native exact selected vectors

Status: implemented query-kernel candidate with a
[completed frozen vector record](native-exact-selected-vectors-result.md).
Final publication-head CI remains a gate. This is the next [native exact four-street prerequisite](native-exact-four-street.md),
following the [conversion boundary](native-exact-conversion-result.md). There is
no native training loop or public solver backend in this change.

[`exact_selected_kernel.hpp`](../native/exact_selected_kernel.hpp) accepts original
binary64 prior bits, role-ordered physical hands and selected complete boards.
It decodes exact integer significands and seat powers of two, computes its own
global integer Z through card/holding buckets, and exposes rank-free prefix
support, completed marginal vectors and fold/showdown vectors. Board subsets
identify selected future outcomes; they never renormalize Z locally. Duplicate
hands, repeated board outcomes, invalid cards/bits/limits/indexes and incompatible
deal sets reject. Ordered turn and river remain distinct. Same-holding addback
corrects two-card inclusion/exclusion, including ties and overlapping ranges.

Terminal reach vectors are exact images of finite binary64 values in [0,1]. Fold
payoff is signed global-SB payoff, inverted for BB. Showdown payoff is nonnegative
matched contribution; comparison is own versus opponent rank for either seat.
Signed integer sums are completed before the strict once-rounded binary64
boundary. Exact zero becomes positive zero; a nonzero subnormal/zero/nonfinite
rounded callback rejects. Rank-free support still includes a positive physical
hand whose numerical marginal would be too tiny to return. Current reach zero
does not remove a supported information row.

The project-owned seven-card ranker uses counts, rank/suit masks and category
logic. It sends no rank vectors from Python. Per-board ranks are requested on
demand through a bounded solve-local LRU. Sorted own/opponent rank sweeps and
card/holding buckets compute signed payoff masses. There is no complete-world,
cross-seat pair-probability or pair-rank table and no nested private-pair loop.
The independent test oracle enumerates physical pairs and best-five subsets;
it is deliberately separate from the native implementation.

## Admission and boundary scope

Reduce-only caps are 1,326 hands per seat, 64 selected boards, 65,536 integer
value bits, 500 million versioned modeled-work units, two million combined
retained/scratch logical entries and 2^30 modeled aggregate integer-value bits.
Setup and each query reserve dimensions/work/storage before their large vectors,
integer alignment or ranking. Every integer shift/product/addition forecasts
value width before allocation. The converter has its separate extra 53 scratch
bits. No old Python whole-solve, row/output or exact-certification cap is relaxed.

Setup payload is `(8H+128)*Wsetup`; query payload is that retained setup reservation
plus `(140H+800)*Wquery+(Wquery+53)`. H is total hands. Wsetup admits seat weights
and Z; Wquery admits aligned reach, completed numerator and denominator bounds.
The generous logical slot coefficients cover simultaneous vectors, card/holding
buckets and arithmetic values. These modeled mathematical value bits are not
Boost limb/allocator bytes, process memory or a CPU guarantee. Likewise, the
named H-log-H sort/map allowance is a modeled reservation; the C++ standard does
not promise the model's constant as a portable actual-comparison bound.

[`exact_selected_kernel_probe.cpp`](../native/exact_selected_kernel_probe.cpp)
implements `OPENPOKER_EXACT_SELECTED_VECTORS_V1` for conformance. Input is bounded
ASCII with exact sixteen-digit binary64 bit fields, at most 256 queries, eight
MiB request bytes and two million declared output components. All query syntax
is parsed before kernel construction. Cumulative query admission remains inside
the kernel; this helper does not establish whole-training admission. It emits
Z/seat exponents, raw result bits and counters. Errors reject explicitly and may
leave a partial diagnostic stream. It is not registered with the solver, and
the integer conversion probe's wire format is unchanged.

## Executed development controls

Five optimized controls pass (5.768 seconds): weighted 3x3 blockers across shared
future boards and empty/subset prefixes, both global seats, exact normalizer,
fold/showdown values, meaningful private-flush outcomes, ties/same-holding addback,
cache sizes one/64, 32 seeded independent best-five games, malformed inputs and
tiny-output rejection. A direct API control authored by Terra proves work,
integer-width, aggregate-payload, NaN-reach and negative-reach failures occur
with zero rank calls and empty rank cache. The first integration attempt to
compile that API test lacked the Visual Studio environment and could not find
the standard `<bit>` header; its failure is retained externally. Running in the
installed compiler environment passes without a source change.

Terra independently extends the root-authored physical/Fraction test harness with
64 more seeded blocker/rank games, zero payoff/reach, both seats, invalid reaches
and payoff/index controls; seven tests pass against authenticated development
source. This is separate engineering scrutiny using the same independent
physical oracle, not a claim of a second separately implemented mathematical oracle.

Review finds and fixes a missing aggregate integer-payload bound before
acceptance. A scalar `all-lower-equal` compatible-mass computation also replaces
two fixed 52-card bucket subtractions per own row. The original path was already
linear in the fixed card domain; an initial review suspicion of a quadratic
private-pair scan was incorrect and is not a performance claim. Development
normalizer formatting changes and first harness compile failures remain distinct
from the eventual frozen record. No elapsed-time or memory gain is inferred.

The [dedicated CI](../.github/workflows/native-exact-vectors.yml) requires actual
Windows/Linux builds and Linux ASan/UBSan physical controls. Full native query
evidence, whole-process Q training, complete policies/eight metrics, independent
saved-policy/exact-BR certification and complete-call performance remain separate
acceptance stages. Broader convergence and full-deck scalability remain unresolved.
