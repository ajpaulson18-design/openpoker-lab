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

The planned experiment uses the same four full-board checkdown cases and trusted count provenance described in [the solver benchmark](preflop-full-checkdown.md), with vanilla CFR, DCFR and CFR+ at 1,000 and 3,000 iterations. It compares categorical and pair-mean complete prepared calls, including production diagnostics and JSON serialization. The three 3,000-iteration final repeats are paired and alternate mode order. The final independent NashConv limit is 0.005 chips; the AA/KK known-value error limit is 0.005 chips. Independent serialized-policy replay has tolerance `1e-10`; corresponding categorical/pair-mean scalar metrics are compared at `1e-8`. Policy magnitudes are observed, not an acceptance gate.

Two separate complete Python allocation traces are planned for the weighted three-pair CFR+ case at 3,000 iterations, one per mode. The prepared input table and independent oracle work are excluded, and traced Python bytes are not process RSS. All timings and allocation observations are intended as fixture- and host-specific measurements, not universal speed or memory claims.

The source freeze and benchmark execution are pending. No accuracy, parity, runtime, memory or speedup result is claimed until the hash-verified paired report is available.

This optimization changes only the representation of hidden final-board chance inside the finite preflop forced-checkdown game. It does not solve postflop betting, unrestricted no-limit Hold'em, multiway play, antes or rake, and it makes no profitability claim.