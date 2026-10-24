# Matrix-free river 16x16 accuracy study

The sole fixed four-call batch completed from published clean source
`db6cff583563072938c62e732078988b65e6e0d7` under claim
`a3738a714e284468b02fcc96daf3e25c`. All four saved policies meet the exact
normalized-binary64 NashConv <=1/1000 chip reporting target. The
[fixed protocol](matrix-free-river-range-quality-protocol.md),
[literal case manifest](../benchmarks/matrix-free-river-range-quality-v1.json),
[complete report](../benchmarks/results/matrix-free-river-range-quality-v1/report.json),
[claim](../benchmarks/results/matrix-free-river-range-quality-v1/claim.json),
[terminal status](../benchmarks/results/matrix-free-river-range-quality-v1/status.json)
and [byte index](../benchmarks/results/matrix-free-river-range-quality-v1/index.json)
retain every policy and complete audit ledger. No call was repeated.

| Frozen game | T / D | Numeric NashConv (chips) | Exact normalized-policy NashConv (decimal projection) | Exact target |
|---|---|---:|---:|---|
| Unpaired club, fractional short refund | 10000 / 0 | 0.0000220580944221283 | 0.0000220580944230326 | Met |
| Same game, original-weight tail | 20000 / 10000 | 0.000000341822952166 | 0.000000341822951705 | Met |
| Paired heart, rank extremes and short refund | 10000 / 0 | 0.000129765937375126 | 0.000129765937373756 | Met |
| Same game, original-weight tail | 20000 / 10000 | 0.0000569357901980538 | 0.0000569357901970302 | Met |

The cases were fixed before any trained call. Both have 16 unique unequal-weight
literal holdings per side; boards, ranges and action menus differ from the earlier
8x8 study. The unpaired game has 230 compatible deals, 26 blocked Cartesian pairs,
one tied-rank pair, 27 public states, 160 information rows and 416 action slots.
The paired game has 235 compatible deals, 21 blocked pairs, four tied-rank pairs,
24 states, 144 rows and 368 slots. Both retain complete legal raise/all-in menus,
unequal-stack refunds, global collision conditioning and hidden opponent cards.
These are configured finite heads-up river games.

## Source, averaging and admission

A [separate no-training preflight](../benchmarks/results/matrix-free-river-range-quality-v1/check-only-control.json)
authenticated all 84 source/study identities against committed Git blobs,
all four prior 8x8 policies and all 16 compiled controls. It freshly checked
all four full requested budgets, every physical pair and exact normalized input
mass, independent ranks, kernel marginals and ordered action/tree/terminal/refund
signatures. Source and baseline identities remained stable before and after all
calls, audits and comparisons. All four complete canonical raw returns were
saved, fsynced and reloaded before any policy validation. The original source
checkout remains frozen; evidence is published from a separate checkout.

The existing D0 API averages completed sweeps 1..10000 with original weights,
summing to 50005000. The new tail averages completed sweeps 10001..20000 with
original weights t, summing to 150005000. Own sequence reach and globally
conditioned hand marginals enter averaging. Regret/average traversals are
20000/10000 and 40000/10000, respectively. The tail therefore uses twice the
regret sweeps and a different averaging window. Comparisons are descriptive;
these observations do not isolate averaging effects or establish equal costs.

Full unchanged vector admission charges 3T+3 regardless of discard: unpaired
12961296/25921296 and paired 11521152/23041152 hand-state operations under 30m.
Action/state caps remain 1m/250k. Actual ranked fallback pair checks are
19952/20832 for the unpaired D0/tail and 11696 for both paired policies, all under
the original 30m dynamic fallback cap. Every solver returns zero materialized
worlds; the independent physical worlds belong only to validation.

The original materialized world-node caps reject these larger requests:
69m/138m for unpaired and 63.45m/126.9m for paired, above 30m. Native shape admission
also rejects the T10000 supports under its original 500m loop cap; T20000 exceeds
its separate 10000-iteration ceiling. Those rejection receipts are preserved.
No old cap, shared trainer, default or earlier-street behavior was changed.
Work counts are logical models, not runtime, actual allocations or RSS.

## Independent saved-policy validation

All information rows, action metadata and eight numeric metrics pass independent
physical-policy replay. Both unchanged physical exact modes, scan and partition,
agree on every Fraction metric, normalization ledger, legal response interval,
gain, zero-sum identity and target flag. Exact work for the four policies is
77,604, 58,945, 72,061 and 56,710; maximum Fraction bits are 6,327, 1,698, 5,668 and 974.
Every depth is 5 under the unchanged 100,000-work, 64-depth, 65,536-bit ceilings.
The report retains full rational rows and ledgers; table decimals are projections.
Numeric configured-model and exact normalized-policy rounding meanings remain
explicitly separate.

A [separate saved-only verifier](../benchmarks/results/matrix-free-river-range-quality-v1/replay-verifier.py)
and its [receipt](../benchmarks/results/matrix-free-river-range-quality-v1/independent-saved-replay.json)
reauthenticate the full frozen source, baselines and protected evidence, compare
complete deterministic audits, recompute exact Fraction identities and retain
separate descriptive differences. Production solving/training/native execution
are disabled; it records zero training and native calls. CI additionally checks
all primary artifact hashes, schedule/admission metadata, relevant immutable
mathematical sources, every physical/exact saved replay and both descriptive
comparisons. The separate experimental ranked certificate is not substituted
for this study's preregistered physical auditor.

## Scope and remaining quality work

The original [4x4 misses](river-heldout-quality-results.md) and
[shorter-tail misses](river-heldout-tail-results.md) remain unchanged. Larger
supports do not imply uniformly harder strategic games, and these four passes
do not supersede those failures. This study establishes the fixed reporting
threshold for these two finite games. Wider range/action-tree coverage, known
equilibrium anchors beyond bounded controls, broad turn quality, scaling and
commercial solver quality remain separate work. No speed, equal-cost method
advantage, general convergence or unrestricted Holdem claim follows.
