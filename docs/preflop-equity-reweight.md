# Reweighting full-board preflop equity counts

`reweight_preflop_equities(table, sb_range, bb_range)` is imported from
`pokerlab.preflop_push_fold`. It changes the private-hand distribution while
reusing an existing immutable `FullBoardEquities` table. It does not rank cards
or enumerate boards. The operation returns a new validated table and leaves the
source table and its hand-keyed win/tie/loss counts unchanged.

For explicit transfer to globally suit-permuted private pairs, see the separate
[suit-remap API](preflop-suit-remap.md). Literal reweighting keeps its existing
covered-pair requirement.

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

The [measured report](../benchmarks/results/preflop-equity-reweight-v1.json)
passed all six cases at frozen source
`55cdb2acc22c060fdce41922fd3779691cb7fa1d` on Python 3.12.14 / Windows 10.
The working tree was clean and all 16 source/config hashes stayed unchanged.
Each complete warm call includes reweighting, training, exact production
diagnostics and JSON serialization. Independent replay and witness checks sit
outside the timings; the table below gives medians of three calls.

| Case | Exploitability (chips) | Known-value error (chips) | Warm call (seconds) |
| --- | ---: | ---: | ---: |
| Original mixed | 3.0191892e-5 | 1.40477496e-8 | 0.834515 |
| AA-heavy | 0 | 0 | 0.808774 |
| AK-heavy | 0 | 0 | 0.854492 |
| Strong subset, inactive blocked hand | 0 | 0 | 0.331628 |
| Weak subset | 1.21160612e-7 | 2.42321223e-7 | 0.376495 |
| Reordered mixed | 3.0191892e-5 | 1.40477496e-8 | 0.907765 |

The exact AA-heavy witness shoves both SB hands and calls only AK; the AK-heavy
witness shoves both SB hands and calls both BB hands. The original and reordered
games retain the original rational mixed witness. Strong/weak single-pair values
are exactly +1 and -0.5 chips. Every returned matrix witness passes exact pure
unilateral-deviation inequalities and is independently replayed after conversion
to serialized frequencies; that conversion leaves at most 1.239e-17 chips of
replayed NashConv. Maximum production/replay scalar disagreement is 1.111e-16.
All trained results meet both predeclared 0.005-chip gates. Repeated payloads
are identical within each case, and the source table stays unchanged.

A separate complete warm-call allocation trace peaks at 22,621 Python bytes.
It excludes the prebuilt reference table, historical-file loading, original
full-board preparation and RSS. No cross-source speedup claim follows from
comparing these calls to the historical preparation run. Ranking and enumeration
are patched to fail throughout these calls, proving that this reuse path performs
neither operation. These timings and allocation observations are fixture-specific.

The local full suite passed 794 tests in 388.011 seconds; a subsequently added
fixture-mutation regression passed separately with the three other evidence
tests. GitHub checks the published source on Python 3.11/3.12/3.13 plus
frontend/documentation contracts. Luna implemented the bounded reweight and
independent witness slices and reviewed the integration; the lead ran the tests,
frozen benchmark and independent certificate replay.

Reweighting is independently implemented with the standard library and the
project's existing solver. It incorporates no third-party source, dependency or
solver output. This provenance statement is not legal advice or patent
clearance.
