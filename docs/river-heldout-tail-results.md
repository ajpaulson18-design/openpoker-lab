# River original-weight tail study: two exact passes and two retained misses

The single preregistered four-call batch completed from published clean source
`74b8fa8adb13838401b06d203d597476eada4274` under claim
`99a99ba342ee3935b0879a7d471a5b6a`. Both 50,000-sweep materialized tails meet
the fixed exact normalized-policy NashConv <= 1/1000 chip reporting target.
Both 10,000-sweep tails remain misses. The [protocol](river-heldout-tail-protocol.md),
[complete report](../benchmarks/results/river-heldout-tail-v1/report.json),
[claim](../benchmarks/results/river-heldout-tail-v1/run-claim.json) and
[terminal status](../benchmarks/results/river-heldout-tail-v1/run-status.json)
are retained with every complete raw policy. The four
[original v1 misses](river-heldout-quality-results.md) remain unchanged.

| Configured game | T | D | Independent numeric NashConv (chips) | Exact target |
|---|---:|---:|---:|---|
| Unpaired blocker/tie/raise | 10,000 | 5,000 | 0.002730245806441989 | Miss |
| Unpaired blocker/tie/raise | 50,000 | 25,000 | 0.0004472558809105465 | Met |
| Paired short-SPR/rank extremes | 10,000 | 5,000 | 0.002072706828926130 | Miss |
| Paired short-SPR/rank extremes | 50,000 | 25,000 | 0.0006567595797726256 | Met |

These are the same weighted 4x4 literal-support games used in v1. This is an
evidence-guided follow-up; they are no longer held out for study selection.
T=50,000 uses five times the full regret sweeps of the old T=10,000 baseline,
so it does not isolate the effect of tail averaging or compare equal costs.
At equal T=10,000, the unpaired tail is worse than its old approximately
0.00174251 gap; the paired tail improves on approximately 0.00232499 but still
misses. No uniform benefit from discard follows from these observations.

## Source, schedule and unchanged admission

All 74 source/protocol identities remained stable before/after each real call,
audit and saved reload. The source freeze authenticates every production Python
module and unchanged original numeric/exact helpers, plus the new wrapper and
protocol. Full original baseline report/claim/status/policy byte hashes and all
four historical policies were authenticated and independently replayed before
the first new trainer. All four fresh full-request admissions passed first.

The existing research adapter averages completed sweeps t>D with original
weight t and own sequence reach. The returned windows are 5,001..10,000 and
25,001..50,000; triangular weight sums are 37,502,500 and 937,512,500. Actual
training uses 2T regret traversals plus T-D averaging traversals, or 25,000 and
125,000 passes. Admission reserves the original full request, including the
3T+3 dense-work envelope, without subtracting D. No production/shared cap,
solver default, earlier-street code or existing adapter changed.

At T=50,000, candidate hand-pair work is 800,000; compatible-world iterations
are 700,000/750,000; world-node work is 21,000,000/22,500,000; dense-hand-state
work is 16,200,324. The unchanged 3m/30m, action-slot, prefix and public-tree
limits all admit these values. These are source-derived logical budgets, not
measured runtime or memory results.

## Independent saved-policy evidence

Each complete canonical LF policy was saved before audit, then reloaded and
replayed. Numeric betting rules, physical compatible pairs, independent ranks,
all own-hand information rows and legal visible-information responses agree
with all eight serialized metrics within 1e-9. Exact normalized-binary64 scan
and partition audits agree on every metric, response interval and target flag.
Their work is 4,226 for the unpaired and 4,223 for the paired game; all have
depth 5 and at most 598 Fraction bits, under the unchanged 100,000-work,
64-depth and 65,536-bit limits.

A [separate saved verifier](../benchmarks/results/river-heldout-tail-v1/replay-verifier.py)
rechecked the full frozen source, baseline and raw byte identities; recomputed
the no-training admissions; disabled production solving/tree/training/evaluation
helpers during saved replay; and independently checked Fraction value bounds,
response gains, zero-sum value, exploitability and the 1/1000 target. Its
[receipt](../benchmarks/results/river-heldout-tail-v1/independent-saved-replay.json)
records all four profiles, zero blocked production calls and zero training.
Verifier SHA-256 is
`9f9ee39259507477550cfa15b2a8a7f4671f31bae6dbc1238279d8d6e671026c`.

The first external verifier run stopped before policy replay because it compared
a fresh Python tuple against its JSON list encoding in the stored preflight.
The [original verifier](../benchmarks/results/river-heldout-tail-v1/verification-history/first-verifier.py)
and [failure log](../benchmarks/results/river-heldout-tail-v1/verification-history/first-verifier-failure.log)
are preserved. Comparing the complete canonical JSON forms corrected that
verification-only type mismatch; the next saved replay passed. No training,
policy, report, claim, frozen wrapper or protocol was changed or retried.

## Scope and remaining quality work

The source-linked policies establish this accuracy threshold for two finite
configured river games. They do not establish an independently known exact
equilibrium value, accuracy for broader ranges/action trees, general convergence,
controlled performance gains or GTO Wizard quality. Those remain separate
validation milestones. Full source authentication is reproducible from the
original frozen checkout; future CI replays the immutable artifacts under
explicit relevant mathematical source pins without requiring unrelated future
production files to remain unchanged.
