# Native training over selected probability/payoff queries

This page describes the literal-tree selected-operator helper. Explicit
`public_topology="direct"` instead requires the distinct [native DAG helper](native-selected-dag-protocol.md);
its [separate measured result](native-selected-dag-result.md) preserves this
backend and all of its original evidence.

This connects C++ computation to the
[non-materialized four-street operator](selected-operator-four-street.md), with
[flat strategy buffers](packed-operator-strategy.md). The original
[native edge-table backend](native-four-street-architecture.md) remains unchanged
and independently replayable. This is one shared whole-game/rule/strategy
boundary with an explicit computational backend, not separately solved streets.

## Input and retained representation

`solve_four_street_operator(request, strategy_storage="packed",
native_executable=<source-built-helper>)` explicitly selects zero-delay CFR+.
Other combinations reject before probability preparation. Native failures,
timeouts, provenance changes and malformed output propagate without Python
training fallback. A no-information-set game authenticates the helper identity
but records zero native training calls; Python still performs independent numeric
diagnostics for the same configured game.

The new protocol sends per-seat private-hand masks/weights, selected public
flop/turn/river masks, bounded per-hand board ranks and the flat public tree,
action offsets and complete own-hand information-set map. It does not send or
construct complete private-pair/board worlds or prefix/private-pair edge tables.
Private pairs and compatible selected boards are streamed within each terminal
or marginal query. Only one prefix's own-hand marginals survive a query.

Per-board ranks are an explicitly bounded O(B*(H0+H1)) table, not an unbounded
linear-storage claim: at most 64 selected boards, 128 hands per seat and 8,192
rank entries. Blocked hands use zero; valid category/tiebreak tuples receive
order-preserving six-nibble integer codes. The native parser validates rank
shape and blocker sentinels; it does not establish physical provenance of
arbitrary caller-supplied ranks. The production adapter computes them with the
unchanged project ranker, tested against independent best-five/physical replay.
No third-party evaluator, solver output or source is imported.

Tree/history/information-action storage remains explicit. The selected-board
and rank-table limits are declared workload boundaries, not full-deck solving.
No sampling, delayed averaging, decomposition, abstraction or implicit native
selection is added.

## Numerical and information contracts

The raw world mass is the reference's rounded binary64 range product divided
by 34,246,080. A common normalizer is rounded once after summing those raw masses
over all physically compatible pairs and selected boards. Each occurrence then
divides by that normalizer and passes the original positive-normal guard. Each
pair's prefix mass/signed mass is accumulated in the same selected-board order
before opponent-reach/payoff multiplication. There is no local renormalization.

The native parser independently verifies the global normalizer exactly. It
decomposes each positive normal binary64 raw mass into an integer mantissa
shifted in units of 2^-1074, accumulates into 36 fixed 64-bit limbs, then rounds
once with nearest/ties-to-even before bitwise-value comparison. Addition carries
and truncation/sticky/half bits are explicit. The positive-input invariant avoids
signed cancellation and subnormal output: a supported raw input is already at
least the minimum normal value. Capacity includes all finite input exponents
and bounded candidate-count headroom; overflow is rejected. A one-ulp changed
normalizer is rejected. Independent rational controls cover midpoint ties,
cross-limb carry and seeded positive masses. This verifies the configured raw
binary64 law, not equivalence to unrounded decimal or rational priors.

Regret matching, expected-action and final average reductions preserve the
existing native backend's versioned arithmetic: left-to-right for Python 3.11
and compensated for 3.12/3.13. Pair mass and payoff additions retain their literal
order. Strict compilation disables unsafe reassociation and contraction. Compile
success alone is not numerical equivalence.

Terminal values include joint chance mass and opponent reach once. Strategy
averaging uses own sequence reach, its absolute prefix marginal and completed
sweep weight. Early all-in terminals integrate unrevealed selected boards.
Rows depend only on acting own hand and the full visible history provided by the
shared betting builder; future boards and opponent cards do not select policies.
Player-zero update/rematch, player-one update/rematch, then own-reach averaging
remain unchanged. Existing configured monetary quantization, refund and finite
menu/reopening rules remain authoritative; this adds no real-world action rules.

## Admission, memory and provenance

The original Python candidate/world/scan, rank-cache, tree and packed-layout
ceilings remain. Before ranking, transport or process entry, an additional
native census charges complete requested terminal pair/board scans, marginal
queries, vector/action operations, rematching, parsing/support validation,
normalizer integer arithmetic, depth arenas and output. It caps logical work at
500 million and modeled native storage at 256 MiB. The model includes a separate
128 MiB parser/input reserve, tree/map/row/array storage, bounded ranks and
depth scratch. This is a conservative logical storage model, not allocator or
process RSS measurement. Input/output byte caps and process timeout are separate.
Captured output lengths are checked after process completion; they bound
accepted data, not parent capture allocation for arbitrary executables. Only the
explicitly built, source/binary-identity-matching helper is supported. Its own
process peak is measured separately from Python's process/traced peaks; those
measurements are not summed as simultaneous memory.

The native parser reserves from the declared census, recomputes all six
structural counters before training and requires equality. It checks physical
card masks, global chance normalization, rank/blocker shape, unique prefixes,
tree indegrees/reachability/depth, reveal extensions, row/action spans and a
complete per-prefix private support map. Reused/orphaned rows and hidden/public
transition mismatches reject. Parser structure is not proof of all poker rules;
the shared Python builder and independent numeric/rational replay supply that
separate acceptance.

Chance children must additionally form a distinct, complete partition of the
next reveals under all globally compatible selected deals. This support is
independent of strategy reach, so zero-reach histories retain their branches.
Terra independently reproduced a pre-fix parser gap: duplicate and missing
branches were accepted with internally consistent census counters. Both now
reject specifically at the partition guard, while the valid control passes
normally and optimized. The before source is retained as inert text whose
hash exactly matches its captured bytes; original raw inputs/output, exit codes,
binary hash and build manifest are retained. The old binary bytes were not
captured. No archived source was executed or old evidence re-signed.

The helper owns four contiguous strategy arrays, depth scratch and one prefix
marginal cache. Training iterations allocate no new game/world tables. Python
retains setup, complete output and independent diagnostics. Native counters are
reported separately from Python preparation/diagnostic checks rather than
mislabeling either as whole-operation counts. Compiler flags, source and binary
hashes are authenticated before/after execution; builds are explicit and external
to the checkout, with no installation or silent rebuild.

## Verification and remaining gates

Compiled controls require identical complete policies and numeric diagnostics
against packed Python on the original 22-world game and weighted, asymmetric,
inactive-index, shared-future, tie, refund, short-all-in and fractional-blind
controls. Independent numeric visible-information BR and exact small-game replay
remain the authorities. The parser has malformed protocol, census, normalizer,
rank/card, row-support and trailing-data controls; failure injection prohibits
fallback. Python 3.11/3.12/3.13 compiled controls and POSIX address/undefined
behavior sanitizer jobs are required separately from local MSVC controls.

After the account usage window reset, Luna resumed benchmark integration and
Terra independently scrutinized chance/reach semantics, exact accumulation,
rank/row boundaries and arena/resource logic. Terra found the partition issue
above, confirmed its correction and reported no additional concrete arithmetic
or buffer blocker for the supported source-authenticated path. He explicitly
retained the modeled-memory and trusted-rank boundaries rather than accepting
them as hard process-memory or physical-rank proof.

## Frozen bounded comparison

The [receipt and complete raw archives](../benchmarks/results/native-selected-operator-v1/receipt.json)
pin clean source `02982d145c7367f2919f577e1dbd40eb6bf87c8a`, its native build,
ten fresh-process complete calls, manifests, complete policies and numeric/exact
certificates. Both paths use packed strategy storage and rank-cache capacity 64
on the original weighted, shared-future 22-world selected game. All five paired
complete policies are identical. T100 misses remain (numeric NashConv
0.011805990010147288 BB); both T1000 exact <=1/1000 BB targets pass, with numeric
NashConv 0.0003997388151442405 BB and identical exact metric maps.

| Complete-call observation | Python | Native training path |
| --- | ---: | ---: |
| T100 median, three untraced calls | 9.99134 s | 0.251108 s |
| T1000, one untraced call | 63.96154 s | 0.604050 s |
| T100 traced Python peak, separate call | 2,322,062 bytes | 2,346,214 bytes |

These are about 39.79x and 105.89x observed runtime ratios on this fixture,
including preparation/transport, native launch, independent Python diagnostics
and full output. T1000 has no runtime distribution. Python process lifetime peaks
remain roughly 25–26 MB untraced, slightly higher for the native path; its native
child separately peaks around 3.24 MB. There is no established overall memory
gain. Traced and untraced timings are kept separate, and peaks are not summed.

The T1000 native request contains 1,462 public nodes, 1,200 information rows,
2,402 action slots, 6 selected boards, 24 per-hand rank entries and 13 prefixes;
stored worlds and prefix/pair edges remain zero. Native training performs
6,240,000 terminal and 1,296,000 marginal pair/board checks. This accelerates the
existing streamed computation without removing its pair/board scan complexity.

A fresh saved-only process replays both budgets with zero training/native calls,
externally pinned manifests and a maximum numeric discrepancy of about 1.11e-16.
Terra independently verified all manifest entries, five policy pairs, both exact
metric maps/targets and separate memory scope. The complete before-fix partition
failure and initial Linux test-fixture failure are preserved. The latter arose
because a mocked child runner intercepted the Linux platform-name query;
`1c22a71` isolates synthetic metadata without changing runner or solver code.
Ninety-seven local controls pass normally and with assertions disabled.

Broader held-out complexity, compiled/sanitized CI, explicit history/strategy
growth and full-deck integration remain separate gates. This bounded runtime
improvement establishes neither large-range quality nor commercial readiness.
The overall scalable-foundation objective stays active.
