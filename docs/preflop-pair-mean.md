# Pair-mean worlds for full-board preflop checkdown

`solve_prepared_preflop_checkdown(..., world_indexing="pair-mean")` is an opt-in indexing of the same finite heads-up preflop betting and hidden full-board forced-checkdown game documented in [the solver scope](preflop-full-checkdown.md). It compresses the hidden showdown categories within each compatible private-hand pair. It does not alter the actions, payoff rules, private-hand ranges, collision-conditioned priors, betting tree, or later-street scope.

The default remains `world_indexing="categorical"`. Omitting the argument and explicitly selecting `"categorical"` preserve the existing result payload and work-budget fields. At the top level, pair-mean adds only the result field `"world_indexing": "pair-mean"`; the existing solver version and strategy-row schema remain. The work-budget object uses a pair-mean-specific version and fields. The result's `training_world_rows` value is the number of compatible private pairs, `P`, rather than the original number of up-to-three nonzero category rows per pair.

```python
from pokerlab.preflop_checkdown_solver import solve_prepared_preflop_checkdown

result = solve_prepared_preflop_checkdown(
    prepared_equities,
    config={"small_blind": 0.5, "big_blind": 1,
            "starting_stack": [4, 3], "raise_sizes": [0.5],
            "max_raises": 2, "include_all_in": True},
    iterations=3000,
    algorithm="cfrplus",
    resource_model="prepared-counts",
    world_indexing="pair-mean",
)
```

## Why the category collapse preserves the game

For each ordered compatible SB/BB private pair `(i,j)`, let the prepared counts over `B = 1,712,304` legal unordered final boards be `W` wins, `T` ties and `L` losses for the SB. The exact conditional signed showdown mean is

```text
q(i,j) = (W - L) / B
```

Pair-mean supplies one weighted world for that pair: its unchanged collision-conditioned prior `p(i,j)` and signed mean `q(i,j)`. It computes the ratio as an exact `Fraction` before conversion to binary64. Ties stay in the denominator with sign zero. A zero signed mean still keeps the full pair prior: it contributes no showdown value but retains its probability mass for folds and for own-reach strategy averaging.

The final-board category is hidden at every decision. Every preflop action policy is keyed only by the acting player's own hand and public betting history. At a fold terminal, utility does not depend on the hidden final-board sign. At a showdown terminal, utility is the matched contribution multiplied by that sign, so expected utility is linear in the conditional sign distribution. Summing the category-weighted terminal values for a pair therefore gives the same game value as multiplying its prior by `q(i,j)`.

The same aggregation preserves training updates. For a fixed information set, all W/T/L worlds for one private pair use the same policy. Their counterfactual regret contributions sum linearly under the unchanged opponent reach, and their own-reach average contributions sum to the pair prior. Vanilla CFR and DCFR apply their updates only after the world contributions have been accumulated; CFR+ also aggregates each player's sweep before regret clipping. Thus replacing those category rows by one mean row preserves the real-valued regret and averaging updates for all three algorithms.

Best responses must retain distinct private-pair rows. The responder groups worlds by its own hand and must sum across the hidden opponent hands before choosing a response. Pair-mean combines W/T/L outcomes **within** a pair only; it does not average over opponent hands or allow a responder to condition on a hidden card or showdown category. This preserves the information available to both players.

The proof is exact over rational probabilities and payoffs. The implementation uses binary64 floats, and collapsing category rows changes summation order: a float conversion of one signed mean need not reproduce bit-for-bit the old sum of separately converted win, tie and loss masses. No bitwise payload or metric identity is promised. Independent replay and paired-mode comparisons use the benchmark's declared numeric tolerances.

## Admission and budget

Pair-mean retains the same table validation, compatible-pair ceiling, source-preparation fees, structural tree/action caps and 500,000,000 modeled-loop-entry limit. The source-inclusive default still charges historical ranking preparation; `prepared-counts` still excludes that prior preparation while charging the current solve. Neither mode performs ranking in this solve.

The pair-mean budget uses the same conservative prebuild tree and information-action forecasts. It retains the categorical table-validation/setup charge for up to `3P` category rows and adds `256P` modeled setup entries for the collapse. That component is included in `prepared_setup_loop_entries_upper_bound` and also disclosed as `pair_mean_setup_loop_entries_upper_bound` in the mean-only budget. The version is `preflop-full-checkdown-pair-mean-work-v1`; the separate `training_world_rows_upper_bound` is `P`, while `categorical_rows_upper_bound` remains `3P`.

Training and diagnostic traversal bounds substitute `P` pair worlds for the categorical upper bound `3P`. The structural tree, information sets and action slots do not shrink. These are modeled loop/element envelopes, not machine-instruction counts, elapsed-time predictions, memory bounds or RSS measurements. The ordinary categorical budget and its payload values remain unchanged.

## Planned paired validation â€” evidence pending

The frozen experiment uses the same four full-board checkdown cases and trusted count provenance described in [the solver benchmark](preflop-full-checkdown.md), with vanilla CFR, DCFR and CFR+ at 1,000 and 3,000 iterations. It compares categorical and pair-mean complete prepared calls, including production diagnostics and JSON serialization. The three 3,000-iteration final repeats are paired and alternate mode order. The final independent NashConv limit is 0.005 chips; the AA/KK known-value error limit is 0.005 chips. Independent serialized-policy replay has tolerance `1e-10`; corresponding categorical/pair-mean scalar metrics are compared at `1e-8`. Policy magnitudes are observed, not an acceptance gate.

Two separate complete Python allocation traces are planned for the weighted three-pair CFR+ case at 3,000 iterations, one per mode. The prepared input table and independent oracle work are excluded, and traced Python bytes are not process RSS. All timings and allocation observations are intended as fixture- and host-specific measurements, not universal speed or memory claims.

The [paired report](../benchmarks/results/preflop-pair-mean-v1.json) records
96 complete timed calls, 48 saved checkpoint payloads and two separate traces
at clean source `07a1c4d02a6926f733ef3adfdb32065c2eadab1b` on Python 3.12.14 /
Windows. All 278 recorded source identities match the frozen Git revision after
LF normalization. Canonical report SHA-256 is
`c5a8582e1ff47b7c21f6c2487cb13618b1788cc3892019fc35aefb1ca6bff7dd`;
specification SHA-256 is
`60f1f06de20022a7e673916b11c375d59767c7ed7d08757af6ef18ec60582ee9`.
Independent physical-count policy replay passes for every call, with maximum
scalar discrepancy `3.984e-16` chips. Every paired scalar comparison passes
(maximum `1.706e-13`); maximum policy-probability difference is `8.260e-12`.
All final three repeats per mode/profile have identical payloads.

The original report correctly retains **`all_final_gates_pass=false`**. At
3,000 sweeps, four algorithm/game profiles miss the 0.005-chip NashConv target
in both modes: three-pair vanilla `0.00730061`, three-pair DCFR `0.00501959`,
short-BB vanilla `0.00669817`, and four-pair vanilla `0.00765300`.
All CFR+ fixtures pass, with maximum final NashConv `0.0000921334`; the other
final profiles pass. These are finite-iteration convergence misses shared by
the two representations, not evidence that either solves unrestricted Hold'em.
No gate or observation was removed or adjusted.

The following are observed 3,000-iteration complete-call medians in seconds,
shown as categorical to pair-mean. Preparation and independent replay are
excluded; both paths include validation, admission, construction, training,
production diagnostics and UTF-8 JSON serialization.

| Fixture | Vanilla | DCFR | CFR+ |
| --- | --- | --- | --- |
| AA/KK | 1.24192 to 0.46620 | 1.21600 to 0.54295 | 2.11799 to 1.05251 |
| Three pairs | 2.91861 to 1.05522 | 3.44193 to 1.32338 | 6.55584 to 2.71771 |
| Short BB | 2.75171 to 0.97594 | 2.98445 to 1.39018 | 5.67617 to 2.26499 |
| Four pairs | 3.72463 to 1.39712 | 4.45012 to 1.43475 | 7.39757 to 2.90026 |

Observed median ratios range from 2.0123 to 3.1017 on this host. Raw samples
remain in the report, with alternating paired run order. These observations
are not a universal speed guarantee or a count-preparation speedup; timing
variability can give a median ratio above the threefold world-count reduction.

The separate complete three-pair CFR+ traces measure **61,504 categorical /
63,584 pair-mean Python bytes**: mean mode's observed peak is 2,080 bytes
higher. Traced times are 37.12465 / 14.25753 seconds and are excluded from timed
medians. Input tables, oracle work and RSS are excluded. This feature reduces
repeated world computation; it does not claim a Python-memory saving.

## Separately predeclared quality follow-up

The [8,000-sweep quality specification](../benchmarks/preflop-pair-mean-quality-v1.json)
and [runner](../scripts/benchmark_preflop_pair_mean_quality.py) respond to exactly
the four retained 3,000-sweep misses, using both representations with the same
quality and scalar-agreement gates. Both complete requested solves must fit
the unchanged 500-million work ceiling before any tree/training work. It is a
new experiment, not an alteration of the prior report. One complete call per
mode/request is for quality validation, with no new comparative median or
allocation claim. Its source freeze and results are pending.

CI initially caught a synthetic test demanding an exact floating-point sum of
1.0: Python 3.11 produced `0.9999999999999999`. The assertion now permits
`1e-15`, consistent with the documented binary64 model. Python documents the
[3.12 float-summation change](https://docs.python.org/3.12/library/functions.html#sum).
This test correction followed measurement; producer, budget, oracle, paired
harness and paired specification remain identical to the measured freeze.

This optimization changes only the representation of hidden final-board chance inside the finite preflop forced-checkdown game. It does not solve postflop betting, unrestricted no-limit Hold'em, multiway play, antes or rake, and it makes no profitability claim.