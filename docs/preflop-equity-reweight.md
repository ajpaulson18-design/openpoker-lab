# Reweighting full-board preflop equity counts

`reweight_preflop_equities(table, sb_range, bb_range)` is imported from
`pokerlab.preflop_push_fold`. It changes the private-hand distribution while
reusing an existing immutable `FullBoardEquities` table. It does not rank cards
or enumerate boards. The operation returns a new validated table and leaves the
source table and its hand-keyed win/tie/loss counts unchanged.

```python
from pokerlab.preflop_push_fold import (
    prepare_preflop_equities,
    reweight_preflop_equities,
    solve_prepared_push_fold,
)

source = prepare_preflop_equities("AsAd:1,QsQd:0.5", "AsKh:0.25,KsKd:1")
changed = reweight_preflop_equities(
    source, "QsQd:0.0625,AsAd:1", "KsKd:1,AsKh:0.25"
)
result = solve_prepared_push_fold(changed, config={
    "small_blind": 0.5, "big_blind": 1, "starting_stack": 2,
}, iterations=1000, algorithm="cfrplus")
```

Weights are interpreted as the exact rational values represented by the input
binary64 numbers. The API multiplies the two players' weights for each private
pair, removes pairs that share a card, and then normalizes globally across all
remaining pairs. Thus collisions change the prior; weights are not normalized
independently by player before dealing. A positive exact category mass that
cannot be represented as a positive float is rejected rather than silently
removed.

The supplied ranges may select a subset of source pairs, reorder hands, or list
new hands that are fully blocked by the opponent's range. Every compatible pair
that the requested ranges actually produce must already have a count in the
source table. If any such pair is missing, reweighting raises `ValueError`
before constructing the output category rows. It makes no claim about pairs
outside the source table's coverage.

The reweight plan uses the existing preparation limits: at most 4,096 candidate
pairs, four compatible private pairs, 6,849,216 board evaluations,
13,698,432 rank calls and 12 categorical rows. These are admission bounds, not
runtime or memory guarantees. Structural validation checks that counts, priors,
category masses and budget metadata agree internally; it does not prove that
caller-supplied counts came from real board enumeration. Use a trusted prepared
table when relying on the physical equity counts.

## Verification and benchmark provenance

The focused reweight tests use synthetic counts where appropriate and check
that ranking and board-enumeration functions are never called. They include
same-weight and exact power-of-two scaling invariance, changed weights, subsets,
reordering, fully blocked hands, uncovered-pair rejection, and numeric support
boundaries. The benchmark separately reuses the three physical win/tie/loss
counts from the original equity source revision
`4650d6591c88c25f1a04c28fcf4960efc6ec33de`.

The frozen benchmark configuration is
[`preflop-equity-reweight-v1.json`](../benchmarks/preflop-equity-reweight-v1.json).
Its harness pins the PR #125 merge commit
`a5e1b75ab424c97673f5126796b9d7eae14b0706` and verifies five immutable Git
blobs for the historical report, production evidence and three per-pair oracle
artifacts before using the counts. It then runs six warm cases at 3,000 CFR+
iterations, with three repeats per case. Ranking and board-enumeration functions
are patched to fail during the measured calls. Separate from timing, each case
is checked with a small exact normal-form equilibrium witness (up to two active
hands per player) and independent policy replay. This is a bounded fixture; it
is not a full-range equilibrium or general linear-programming result.

Numeric reweight benchmark results are pending the lead's final report. No
cross-source speedup or RSS claim is made. The benchmark excludes original
full-board table preparation and loading the historical evidence files.

Reweighting is independently implemented with the standard library and the
project's existing solver. It incorporates no third-party source, dependency or
solver output. This provenance statement is not legal advice or patent
clearance.
