# Prepared-table work budget

`solve_prepared_push_fold` accepts an opt-in `resource_model` keyword:

```python
result = solve_prepared_push_fold(
    table,
    iterations=3000,
    algorithm="cfrplus",
    resource_model="prepared-counts",
)
```

The default, `resource_model="source-inclusive"`, retains the existing
`preflop-push-fold-work-v1` envelope and payload exactly. It conservatively
charges source bookkeeping even when the immutable equity table is warm. The
new `prepared-counts` choice is only for a caller that already has a prepared
table and wants the preparation charge separated from the current solve. It
uses `preflop-push-fold-prepared-count-v1`; it does not change the convenience
`solve_preflop_push_fold` signature, path, or source-inclusive admission before
board enumeration.

## Prepared-counts envelope

Both models retain the same fixed 500,000,000 modeled-loop-entry ceiling,
pair/category/rank/world caps, full requested iteration count, training
formula, and diagnostic formula. Prepared-counts changes only the fixed setup
charge. For `C` candidate hand pairs, `P` compatible private pairs, `R = 3P` as a
categorical-row upper bound, and `S` information-action slots, it computes:

```text
setup       = 128 + 32*C + 256*P + 128*R + 128*S
training    = 1024 + 64*R + 128*S
              + iterations * (256 + 2048*R + 256*S)
diagnostics = 1024 + 512*R + 256*S
total       = setup + training + diagnostics
```

The setup term bounds the candidate-pair/table census, compatible-pair and
category-row validation/setup, information-slot setup, and serialized result
row bookkeeping in this fixed five-state game. The training and diagnostic
multipliers are unchanged conservative envelopes from the source-inclusive
model. CFR+ averaging delay does not reduce admission: the full requested
iteration count remains charged.

For illustration, a synthetic table with six candidate hand pairs, four
compatible private pairs, twelve category rows and ten information-action
slots yields a 54,800,960-entry prepared-counts envelope at 2,000 iterations,
82,192,960 at 3,000, and 273,936,960 at 10,000. Those are arithmetic results
from the stated model, not timing or memory measurements. The corresponding
source-inclusive model still rejects the 3,000-iteration case because it also
charges full-board preparation; the lower 2,000-iteration case remains within
that existing envelope.

Admission follows option validation and `FullBoardEquities.validate()`, then
runs before betting-tree construction, training, evaluation/best responses, or
result-row serialization. A request above the unchanged ceiling is rejected
there. The convenience full-solve API continues to apply its source-inclusive
plan admission before any full-board enumeration.

## Provenance and limits

The prepared-counts budget records `current_rank_calls: 0`,
`current_board_combinations: 0`, and `source_enumeration_charged: false`. The
historical table preparation metadata is retained separately as
`historical_equity_preparation` for provenance; its prior ranking work is not
charged a second time in this call. The estimate includes bounded logical
bookkeeping/setup, training, and diagnostics for this finite fold/shove game.
It is not a bound on bytecode instructions, elapsed time, Python allocation,
process memory, or RSS. Structural table validation does not authenticate
caller-supplied win/tie/loss counts; callers should use trusted preparation
output.

This is an explicit accounting option for repeated warm-table experiments,
not a change to the solver's poker model, accuracy, or supported action set.
See [the full-board push/fold specification](preflop-push-fold.md) for the
game scope and independent validation boundaries.