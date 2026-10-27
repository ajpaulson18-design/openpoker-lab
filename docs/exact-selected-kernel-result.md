# Exact-product selected four-street integration: frozen result

This explicit research solver connects exact blocker/card/rank queries to one
direct shared four-street root and the existing packed CFR+ trainer. It eliminates
private-pair scans from batched marginal/terminal queries without storing complete
worlds or prefix/pair edges. Its exact-product chance law differs from the legacy
rounded per-occurrence law; the old operators, native protocols and guards remain
unchanged. Once-rounded binary64 query vectors define an approximate training
trajectory, with final policy quality checked independently.

## Evidence and scope

Measured source: `66788d4a27b549a5cd1788649bae3e1dea047ac6`.
The [receipt](../benchmarks/results/exact-product-selected-v1/receipt.json) pins the
[complete archive](../benchmarks/results/exact-product-selected-v1/exact-selected-study-v1.zip),
raw policies, certificates, rejected request, source closures, process/allocation
observations and full logs. Archive SHA-256:
`9f14a749dab150dc1f676ea3c88eab66faa951c91386b289ab0152df9da702e6`.
Study manifest SHA-256:
`1d265cdb6bbbcb913aa2945e6b18598121bdc54b8142f2b9f0722240bda48bf1`.

The [separate independent saved review](../benchmarks/results/exact-product-selected-v1/exact-selected-independent-receipt.json)
authenticated 1,755 source files against captured raw SHA-256 and raw-or-normalized
frozen Git blobs before mathematical replay. It checks every raw artifact and
archive entry, all eight saved numeric policies and all five fresh exact certificates with
solver/trainer/native/exact-kernel callbacks and process launches forbidden.
Source/artifact inventory and raw bytes remain unchanged afterward. Largest
numeric discrepancy is `1.1102230246251565e-16`. Receipt SHA-256:
`e19c3376b661f2fd000fdd01d5600c3feca612b4fffc0ced98aa9a15351c85db`.

Review found and corrected sign/rank-threshold, duplicate/mutable input,
bounded-iterator, whole-request work/bit/storage and release defects before source
freeze. After Terra/Luna usage limits, a separate Sol reviewer completed independent
integration and measurement-runner scrutiny. This is scoped engineering review,
not exhaustive proof of all resource or floating-point behavior. Seventy-one
combined new/legacy controls passed, 43 focused controls passed optimized and nine
independent runner controls passed. Final PR-head CI and merge state are separate
in [PR #257](https://github.com/ajpaulson18-design/openpoker-lab/pull/257).

## Fixed calls and retained quality limits

The schedule contains ten fresh processes: three untraced original 22-world T10
calls, one traced T10 call, original T100/T1000 requests, unit/tiny common-scale
T10 controls, one-world T1000 and a full-range selected-board mass census.
Eight actual training calls complete; original 22-world T1000 rejects admission
before rank/training, and the census does not train. There are zero native calls.
All four repeated T10 policies are identical. The original game retains 1,200
full own-hand/visible-history information rows across all four streets.

| Complete-call observation | Recorded result |
| --- | ---: |
| Original 22-world T10 median, three calls | 6.378994 s |
| Original 22-world T100, one call | 47.216008 s |
| Original 22-world T1000 | Rejected before rank/training |
| One-world four-street T1000, one call | 59.452411 s |
| Traced original T10 Python allocation peak | 2,307,873 bytes |
| Traced original T10 process lifetime peak | 35,794,944 bytes |

The traced call took 32.122762 seconds. These are complete calls including admission,
exact queries, explicit pair output, training, diagnostics and serialization.
Allocation and process peaks remain separate. This unpaired study establishes
no speed or memory advantage over the legacy rounded/native studies, whose
arithmetic and frozen sources differ.

| Independently recomputed exact policy | NashConv in BB | Unchanged 0.001-BB target |
| --- | ---: | --- |
| Original 22-world T10 | 0.6575302611616735 | Miss |
| Original 22-world T100 | 0.007965523314703803 | Miss |
| Unit common-scale T10 | 0.3378652430181167 | Miss |
| Tiny common-scale T10 | 0.3378652430181167 | Miss |
| One-world T1000 | 0.00001668816797967092 | Pass |

Full rational metrics, normalized-policy ledgers and threshold comparisons are
retained. Original 22-world T1000 rejects the 500 million whole-request exact-kernel
work envelope with zero rank/training/native calls. It has no policy or quality
result. The one-world pass does not certify larger-game accuracy, unrestricted
Hold'em or commercial convergence. No failure, cap or target was removed.

## Exact normalization and structural scaling controls

Common 1e-200 weights on both ranges cause the old raw-product operator to reject.
Under the explicitly selected exact-product law, the common positive exact scale
cancels in one global normalizer. The complete unit/tiny policies, all eight
reported metrics and private-pair probabilities are identical; both actual input
cases independently replay and certify. The legacy underflow guard remains.

The separate rank-free full-range census has 1,326 hands per seat on one selected
five-card board and represents 1,070,190 compatible private-pair/board occurrences.
Exactly 1,081 hands per seat remain active with exact marginal 1/1,081; both sums
are exactly 1. It stores no worlds and performs no ranking/training. The observed
call is 0.364308 seconds; its modeled storage peak is 85,979 logical entries. This
is one selected-board probability control, not full-deck solving or full-range
four-street training. The full solver has additional strategy/output/admission
and quality constraints not discharged by this census.

## Remaining barriers

Complete information histories, regrets/averages and serialized policies remain
explicit. The unchanged independent policy schema requires positive private-pair
probability rows, so the solver retains a separately admitted quadratic setup/
output stage; only its batched mass/payoff kernels remove pair scans. The
[contract](exact-selected-kernel-contract.md) describes prefix-weighted callback
work, dyadic bit forecasts, phase-overlap entry limits and strict nonzero-to-normal
float conversion. These modeled bounds are not hard allocator/RSS or CPU limits.

Next dependencies include measured exact-query computation improvement and native
integration, compact pair-free diagnostic/certification interfaces, information-
history/strategy growth, scalable exact validation and broader convergence. This
result moves the unified foundation forward without resolving full-deck reach/
payoff integration, general NLHE rules or commercial accuracy.
