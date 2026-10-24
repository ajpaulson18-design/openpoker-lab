# Native river 8x8 accuracy study

The single fixed four-call batch completed from published clean source
`7371b450976a8b904afb7c7583070db4d5b84595` under claim
`9399dbdbf6de4d7397295c05269140de`. All four policies meet the exact
normalized-policy NashConv <= 1/1000 chip reporting target. The
[protocol](native-river-range-quality-protocol.md),
[case manifest](../benchmarks/native-river-range-quality-v1.json),
[complete report](../benchmarks/results/native-river-range-quality-v1/report.json),
[claim](../benchmarks/results/native-river-range-quality-v1/claim.json),
[terminal status](../benchmarks/results/native-river-range-quality-v1/status.json)
and [artifact index](../benchmarks/results/native-river-range-quality-v1/index.json)
retain every raw policy and provenance receipt.

| Fixed game | Backend | Independent numeric NashConv (chips) | Exact normalized-policy NashConv (decimal projection) | Exact target |
|---|---|---:|---:|---|
| Unpaired weighted 8x8, fractional short refund | Python materialized | 0.000036652381053770 | 0.000036652381053410 | Met |
| Same game | Native | 0.000036652381053770 | 0.000036652381053410 | Met |
| Paired weighted 8x8, short refund | Python materialized | 0.000009238254012445 | 0.000009238254014126 | Met |
| Same game | Native | 0.000009238254012445 | 0.000009238254014126 | Met |

All calls use CFR+ T=10,000, D=0, original completed-sweep own-reach averaging,
window 1..10,000 and weight sum 50,005,000. There are 20,000 regret and 10,000
averaging traversals per returned policy. The fixed threshold never controls
training length. The unpaired game reuses the prior compiled T10/T100 control;
it is not newly held out. The paired 8x8 game is the frozen complement. Both
are finite literal-support abstractions with predeclared bet/raise menus.

## Provenance and full-request admission

Before claim creation, a separate
[check-only preflight](../benchmarks/results/native-river-range-quality-v1/check-only-control.json)
authenticated the explicit MSVC build, all sixteen retained
[compiled control policies](native-river-solver.md#retained-paired-compiled-controls),
77 historical source files and three new committed study files. It compared
actual working LF bytes with expected Git blobs, including the installed runner,
protocol and manifest. Source/build/control identities were checked again before
and after every real call, audit and parity phase. All four complete canonical
JSON returns were saved, fsynced and reloaded before any policy validation.
The original generation checkout remains frozen; publication uses a separate
checkout. No training call was repeated.

Independent preflight found 59/60 compatible physical pairs, 4/2 rank-tie pairs,
9/10 decisions, 15/17 terminals, 24/27 public states, 72/80 information rows and
184/208 information-action slots. It verified a bijection of physical pairs,
normalized joint masses, independent ranks, complete action/tree/utility
signatures and unequal-stack refunds. Fresh full-request historical world-node
work is 15,930,000/18,000,000 and dense hand-state work 5,760,576/6,480,648,
under the original 30m limits. Candidate-hand-pair iterations are 640,000;
compatible-world iterations are 590,000/600,000 under the original 3m guards.

The separate native logical-loop bounds are 358,163,824/406,411,888 under
500,000,000. Native heap reservations are 8,534,769/8,535,991 bytes under
64 MiB, and wire reservations are 7,104/7,552 bytes under 8 MiB. These source
models cover their stated historical and native envelopes separately. They
are not measured runtime, actual Python allocations, process RSS or a unified
complete-solve performance bound. No executable is committed.

## Independent physical replay

All eight serialized metrics agree with independent numeric physical-policy
replay. Both exact scan and partition modes admit every policy and agree on
all Fraction metrics, legal own-hand response bounds, zero-sum value, gains,
exploitability and target flags. Exact work is 17,149/19,374, depth 5 and at
most 3,127 Fraction bits, below the unchanged 100,000-work, 64-depth and
65,536-bit caps. The complete rational rows and normalization ledgers remain
in the report; displayed decimals are projections. Exact normalized-binary64
certificates and numeric configured-model metrics retain their separate
rounding semantics.

Each native/Python pair has maximum serialized action-probability difference
zero and zero difference on all eight independently replayed numeric metrics
on the recorded MSVC build. The predeclared tolerances remain 1e-9 for policy
probabilities and 1e-8 for metrics; this observation promises no bitwise
cross-compiler identity. Backend parity is a separate result from accuracy.

A [separate saved-only verifier](../benchmarks/results/native-river-range-quality-v1/replay-verifier.py),
its [completed receipt](../benchmarks/results/native-river-range-quality-v1/independent-saved-replay.json)
and CI regression reload the immutable
policies with production solving/training/evaluation helpers disabled. They
recheck raw receipts, source/build identity, exact Fraction identities and all
four target outcomes without training or native execution. The verifier SHA-256
is `1f9ae42c78494db0d04a55090d15f6bae941889a368516cd44fbd9a1d618be9a`.
All 28 focused lifecycle and retained-evidence tests pass in normal and optimized
Python; documentation validation covers 184 files, 1,021 local links and 12 entry
points.

## Scope and remaining work

These observations establish the fixed target for these two configured river
games. The [four earlier 4x4 misses](river-heldout-quality-results.md) and
[two shorter-tail misses](river-heldout-tail-results.md) remain unchanged.
Larger support alone does not make these games uniformly harder, and the
results do not supersede those misses. Full-range/action-tree accuracy,
independent known equilibrium anchors beyond the existing zero-value control,
broader turn coverage, scalability and commercial solver quality remain open.
No speed, equal-cost method advantage or general convergence claim follows.
