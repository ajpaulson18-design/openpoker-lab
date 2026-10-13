# Streamed physical-world construction experiment

The candidate failed its corrected predeclared runtime gate and was not adopted. Production source and AGENTS were restored to the prior main baseline; candidate-only integration tests were removed from the final tree. Its implementation and tests remain reproducible at the frozen ancestor revision below. The retained reports include both preliminary and corrected comparisons.

At that frozen revision, the experimental `world_storage="streamed-flop-sign"` path avoids retaining the raw and normalized seven-field physical-world lists. It applies to grouped flop-checkdown with original private indices, positive-delay CFR+ and public-vector training/exact diagnostics. The default materialized path and serialized payload remain unchanged.

A prepared source retains the bounded selected-runout blocker index, per-pair normalized masses, first-seen per-flop counts and legal private-hand summaries, plus selected-outcome reachability flags. Shape rows carry a placeholder sign exclusively for structural admission. They never reach training or evaluation. After all requested-iteration, checkpoint and extra construction work is admitted, the source ranks each physical outcome in original pair-major/ascending-selected order and sends it directly into the existing compensated first-seen sign groups. Rank and source construction inputs are released before training, including on ranking failure. Checkdown templates use flop counts without allocating unused local-world copies.

Normalization uses the exact original `fsum` sequence of repeated per-world pair masses. Pair probabilities keep the original mass-times-count/divide arithmetic. Categorical win/tie/loss groups retain their original order and arithmetic; no sign averaging or renormalization is introduced.

## Admission

Every existing candidate-pair, physical construction, selected input, tree/template, information-action, prefix-edge, dense-dimension and original-world vector/checkpoint guard remains. The complete original-world vector budget is computed from repeatable shape rows with the same estimator and exactly the same counters. It still charges hidden future prefixes and the full requested iteration ceiling.

The candidate v8 envelope (construction v2) adds `256 + 8W + 24P + 6R` logical source reference slots to the unchanged grouping envelope `128 + 22W`, with an 8,000,000-slot combined cap. Here W is physical worlds, P is compatible private pairs and R is selected runouts. This covers source summaries, pair-record/normalization overlap, selected-flop key lookup and fixed reference workspace. It separately adds `128 + 40W + 8R + 16P + 16P*ceil(R/8)` modeled loop entries for repeated shape construction and orchestration before training. Four packed blocker scans per private pair (summary, two structural censuses, ranking) visit `4P*ceil(R/8)` bytes, conservatively charged at four loop entries per visited byte. The construction estimator checks its own work ceiling before any summary scan; the later combined admission check also remains. Combined modeled work remains capped at 500,000,000. New storage can therefore reject an input admitted by the original mode; it cannot bypass an existing cap.

The 52 packed posting bitsets and reachable byte flags are reported as logical payloads under the unchanged 300,000-selected-outcome bound. Posting payload figures exclude masks, query/conversion scratch, integer padding, object headers and allocator overhead. Logical references, work and payload figures are not Python-byte or RSS guarantees.

## Frozen complete-call comparison

The [specification](../benchmarks/preflop-streamed-worlds-v2.json) fixes the independently verified four-hand-per-seat/four-flop, 10-chip game with 91,080 physical worlds, 108 sign groups and 1,744 information sets. It uses three alternating materialized/streamed pairs at 500 iterations/delay 250, plus separate 10/delay5 allocation arms. Complete solves plus raw JSON include all construction, requested training and exact diagnostics. Input preparation and GC precede measurement; normalization and independent replay follow it. No production policy objects or strings are retained between arms.

The primary gate requires at least 20% lower separate Python-traced peak allocation, no median runtime regression, every candidate pair within 1.05x baseline, exact normalized complete-payload parity and the unchanged independent quality target in all timing arms. Short allocation quality misses remain visible. Metadata normalization removes only explicit storage/version/additional-budget fields; policies, counts, outcomes, utilities, priors and exact diagnostics remain. Every timing payload must also match the exact full-payload hash from the earlier verified 500/250 report.

Each distinct complete normalized game payload is independently replayed once over every original physical world using independent numeric betting rules, card ranking and legal visible-information best responses. Later identical payloads may reuse only the metric/summary evidence, bound to both fixture and complete-payload SHA-256; production metric comparisons and rational posterior checks still run per arm. This avoids repeating an identical calculation and does not cache production policies.

The [preliminary v1 report](../benchmarks/results/preflop-streamed-worlds-v1.json), frozen at `f89a4547be0529f6cc018a569107f83752806c50`, passed its measurement gates but omitted repeated packed-byte scans from the construction work envelope. Review caught this before publication. V2 adds that charge and an early guard without changing storage/training arithmetic, and preserves v1 as preliminary evidence. Its thin wrapper requires the exact same timing, allocation, accuracy and parity gates. The new run evaluates corrected source; it is not a retry of identical source to select a better timing.

The [corrected v2 report](../benchmarks/results/preflop-streamed-worlds-v2.json) failed its promotion gate: the first pair's candidate/baseline ratio was 1.096570, above 1.05. There was no timing retry or gate relaxation. Median paired runtime reduction was only 0.0787%.

| Pair | Materialized seconds | Streamed seconds | Reduction |
|---|---:|---:|---:|
| 1 | 27.836693 | 30.524883 | -9.6570% |
| 2 | 30.909112 | 29.397781 | +4.8896% |
| 3 | 30.725806 | 30.701630 | +0.0787% |

All six 500/250 profiles matched each other exactly after the documented metadata normalization and matched the prior verified game's full payload hash. Independent NashConv was `0.0008733200818837883`, meeting the `0.005` target in every timing arm. The allocation profiles also matched each other exactly, but both 10/delay5 profiles missed the target with NashConv `0.664786689496687`.

Separate traced peaks were 36,504,962 bytes materialized and 17,079,999 bytes streamed, a 53.2118% reduction. These are Python-traced short-call allocations, not RSS or high-iteration memory. The baseline allocation arm recorded 2,902.777979 seconds during an observed host/approval clock jump; allocation elapsed times are retained but are not used as runtime evidence.

Corrected construction adds 4,001,072 modeled loop entries, including 70,560 blocker-byte visits charged as 282,240 loop entries. The full 500-iteration total is 123,938,054 versus 119,936,982 materialized; the 10-iteration total is 10,813,714 versus 6,812,642. Additional logical reference slots are 785,704, and combined grouping/source slots are 2,789,592. No admission limit was relaxed.

The preliminary v1 report passed its original gates (3.8793% median timing reduction and 53.2120% traced-peak reduction), but its incomplete construction work ledger makes it preliminary. It does not override the corrected comparison's failed gate. Production adoption is rejected despite the memory improvement.

## Validation and provenance

Luna implemented and tested the bounded repeatable-row budget adapter and integration regressions, then independently reviewed the lead's construction, orchestration and benchmark. Lead implemented streaming, separate admission and integration, reviewed the tests, froze and measured the comparison. All code was independently developed in this repository with the standard library; no third-party source or dependency was incorporated. Shared postflop/turn/river kernels and AI Coach were not edited.

The 14 focused streaming regressions passed, including sparse blocker scans with an early lowered work ceiling, a fully unreachable selected outcome, full requested convergence admission, complete-payload parity and independent legal best responses. Before the final ledger correction, the full local suite ran 627 tests: 626 passed and one unchanged Coach preview-expiry test failed across an observed host clock jump; that test passed immediately in isolation. Coach was not changed. The required Python 3.11/3.12/3.13 CI suites and presentation checks validate the final research-only publication commit; their outcome is recorded with the pull request. The candidate itself is not promoted by those final baseline checks.

The frozen revision is `ec12cba69f90df08c5c251678b45318e127cec12`. 78 source/specification hashes were checked at measurement start and end. The earlier verified source and main baseline are ancestors. Among prior recorded source files, only the intended preflop solver, grouping and budget files changed; the independent oracle, ranking and shared kernels were hash-checked unchanged. Hashes record working-tree bytes on the reported host and require matching checkout line endings for reproduction.

The current production tree deliberately has no streamed-world option. To reproduce, check out the frozen candidate `ec12cba69f90df08c5c251678b45318e127cec12` in a separate clean worktree and then run:

```powershell
python -m scripts.benchmark_preflop_streamed_worlds_v2
```

A failed comparison remains a failed comparison; the complete report is saved before exit status 1. Incremental metric-only checkpoints are written outside the checkout to preserve progress without invalidating its frozen state.

This evidence concerns one fixed conditioned heads-up preflop/flop betting game with forced future checkdown. It does not establish full-deck, multiway, broader-range, later-street betting or unrestricted NLHE convergence or general performance. The allocation trace is a separate short call, not RSS or high-iteration memory. The 1e-10 quality padding is conservative and is not a formal floating-point error bound.
