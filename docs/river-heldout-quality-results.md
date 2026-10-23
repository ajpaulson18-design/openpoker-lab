# Held-out river quality v1: four retained target misses

The [preregistered two-case protocol](river-heldout-quality-protocol.md) completed exactly four fixed CFR+10000 API calls on source df02381625ce72d7922461b97d7c7d238258523e. Every complete physical policy passed independent numeric rules replay and exact normalized-binary64 scan/partition audit. All four missed the unchanged 1/1000-chip NashConv threshold.

| Fixed game | Backend | NashConv (chips, numeric replay) | Exact target met |
| --- | --- | ---: | --- |
| Unpaired blocker/tie/raise | materialized | 0.0017425086114033483 | no |
| Unpaired blocker/tie/raise | matrix-free | 0.0017425086114579713 | no |
| Paired short-SPR/rank-extremes | materialized | 0.0023249852685438555 | no |
| Paired short-SPR/rank-extremes | matrix-free | 0.0023249852685900407 | no |

The [complete report](../benchmarks/results/river-heldout-quality-v1/report.json), [exclusive claim](../benchmarks/results/river-heldout-quality-v1/run-claim.json), [terminal status](../benchmarks/results/river-heldout-quality-v1/run-status.json), and every referenced policy are saved unchanged. The report SHA-256 is 5b26d6e9275b4962df4c67be1822594caa3d46291d196f863fe3b65f4353b578. No source drift, execution error or retry occurred. The target is reporting only; successful execution does not turn these misses into passes.

Both unpaired profiles have 14 compatible physical pairs, 40 own-hand information rows and 10 public decisions. Both paired profiles have 15 pairs and the same row/decision counts. Exact scan/partition maps agree on all eight metrics. Their work counts are 4,848 for the unpaired game and 5,115 for the paired game, at depth 5 and maximum observed Fraction size 1,863 bits, within unchanged limits of 100,000 work, depth 64 and 65,536 bits. Exact value intervals equal [-BR_IP,BR_OOP], contain the profile value, and have width NashConv; no separately known exact equilibrium value is asserted.

All 72 production/helper/protocol/runner sources match the clean frozen commit before and after the batch. Raw policies were saved before validation, then reloaded and replayed. A separate [saved-file replay receipt](../benchmarks/results/river-heldout-quality-v1/independent-saved-replay.json) records all four policies rechecked in another process with eight production solving/tree/evaluation helpers disabled, zero intercepted helper calls and zero training. Independent review also rehashed and replayed every profile and checked the Fraction interval/gain identities.

Complete API-plus-serialization observations were 11.229/39.721 seconds for the unpaired materialized/matrix-free calls and 11.129/34.010 seconds for the paired calls. These are single shared-host observations, with no controlled runtime, throughput or memory comparison. The agreement between backends is consistency evidence; the independent physical replay and exact arithmetic provide the mathematical checks.

These are two finite synthetic games with four weighted holdings per player. They broaden blocker, tie, decimal sizing, raise/all-in, short-stack and rank coverage while exposing an accuracy limit at T10000. They do not establish arbitrary-range equilibrium accuracy or commercial solver parity. Keep this complete v1 corpus and all earlier river/turn misses immutable. Any higher-budget or averaging-window study needs a separate preregistered version and unchanged applicable resource limits.

Twelve integrated runner and saved-policy regressions passed in normal Python (2.973 seconds) and optimized Python (2.787 seconds), with no training. Documentation validation passed (175 Markdown files, 947 links, 12 entry points). Run python -B -m unittest tests.test_benchmark_river_heldout_quality tests.test_river_heldout_quality_saved -v to reconstruct the saved checks; add -O for optimized Python. Full hosted publication CI remains pending at this revision.
