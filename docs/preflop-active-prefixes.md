# Active legal hand prefixes for flop-checkdown solves

Flop-checkdown decisions can query only preflop and three-card flop histories. The previous setup decoded the same flop for every physical world and also built turn/river legal-hand sets. The solver now caches each canonical flop once and constructs only the active root/flop sets for this explicit model. The all-streets branch retains the literal original loop.

Root/flop legal hand sets are exactly the same unions over the same original world rows. Information rows still follow the original node order and sorted hand indices, so training arithmetic, policy identities/order, physical masses, utility and legal best responses are unchanged. No world coalescing, approximation, resource-limit change, new public option or shared kernel change is involved. The flop cache is bounded by the existing selected-outcome/world limits and does not copy worlds.

The [frozen specification](../benchmarks/preflop-active-prefixes-v1.json) reuses the [two-flop three-chip checkdown game](preflop-flop-checkdown.md), with all 4,704 future candidates and 11,880 compatible worlds. Before measurement it required three alternating complete90/delay45 comparisons, exact full serialized payload parity, and at least 5% observed median time reduction. The comparison changes only the legal-prefix helper; its reference is the literal prior loop preserved in [regression tests](../tests/test_preflop_active_prefixes.py).

| Pair | Original seconds | Optimized seconds | Exact full payload |
| --- | ---: | ---: | --- |
| 1 | 0.814914 | 0.554442 | Yes |
| 2 | 0.637592 | 0.535778 | Yes |
| 3 | 0.554816 | 0.519849 | Yes |

Observed medians are **0.637592 versus 0.535778 seconds**, a **15.97%** reduction that clears the predeclared 5% gate. Each arm includes physical enumeration/ranking, trees, legal hand setup, training, exact diagnostics and JSON serialization. Input runouts are preallocated; pre-call garbage collection and independent replay are excluded. No previous full result is retained during the next timed solve. Serialized text is compared exactly and independently replayed after both timing arms. These are observed one-host medians, not statistical/universal speed or cross-model claims.

Separate complete10/delay5 calls plus JSON peak at **13,874,527 versus 10,132,855 traced Python bytes**, **26.97% lower** for this fixture. No other complete policy is retained in either trace; replay and parity digest are outside the trace. Native allocations, process RSS and higher-iteration memory are excluded. Both complete serialized memory payloads have SHA-256 `b9a872706ac08a9c7c66b0e6a25df2ba9ff1d583347c95578049233b51a970e7`.

The equal 90/delay45 policy retains independent NashConv **0.00123906973909**, meeting the unchanged 0.005-chip target. The separate 10/delay5 memory policy retains NashConv **0.175182033386**, missing that target. All three equal timing policies and both memory policies were independently replayed; maximum scalar discrepancy is 2.34e-14. Exact full payload parity includes policies and row order, all diagnostics, physical priors, vector admission budgets and public counters.

The [report](../benchmarks/results/preflop-active-prefixes-v1.json) started clean at source `a60a6a7ef8f8c96c254a20a34ae1afcf2152277c`; all 56 source/specification hashes were rechecked unchanged. The [harness](../scripts/benchmark_preflop_active_prefixes.py) retains the raw pairs, quality misses, memory digests and model limits. Local validation passed **13 focused tests**, including five new legal-set/decoder/cap/full-payload parity regressions. Final-head CI must validate the full suite before merge.

Luna implemented/tested the bounded helper and independently reviewed the frozen harness/report. Lead reviewed integration, strengthened timing result cleanup, froze the workload and ran the measurements. Everything uses this repository's own standard-library code; no third-party source/dependencies, proprietary solver output, shared postflop/turn/river kernel or AI Coach changes.

All results remain limited to the finite conditioned preflop/flop game with forced checkdown and narrow ranges. They do not certify all-streets, full-deck preflop, unrestricted NLHE, multiway or broad-range accuracy.

```text
python -m unittest tests.test_preflop_active_prefixes tests.test_preflop_flop_checkdown -v
python -m scripts.benchmark_preflop_active_prefixes
```
