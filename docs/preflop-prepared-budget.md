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

## Measured prepared-table acceptance

The [fixed specification](../benchmarks/preflop-prepared-budget-v1.json) and
[verified report](../benchmarks/results/preflop-prepared-budget-v1.json) cover
three algorithms at six checkpoints on the four-pair split-AK game from
[suit-remap validation](preflop-suit-remap.md). The counts retain their five
pinned historical Git-blob proofs; no boards are ranked again. Frozen source
`e8e70bcb7d71661fb50cf6e4786c58d1c46f1ec1` ran with a clean working tree on
Python 3.12.14 / Windows 10; all 22 source/config hashes stayed unchanged.

Independent own-hand best-response replay gives these exploitabilities in chips:

| Iterations | Vanilla | DCFR | CFR+ |
| ---: | ---: | ---: | ---: |
| 100 | 0.0131273845 | 0.00867809761 | 0.000856085243 |
| 1,000 | 0.00357060779 | 0.00093857024 | 0.0000611536153 |
| 2,000 | 0.00260247553 | 0.00101325472 | 0.0000146360565 |
| 3,000 | 0.00205974461 | 0.000777680599 | 0.0000301918920 |
| 5,000 | 0.00158910559 | 0.000903472954 | 0.0000269814616 |
| 10,000 | 0.00109287998 | 0.000366289086 | 0.00000688172621 |

Every final policy meets both predeclared 0.005-chip accuracy gates; CFR+ also
meets its stronger 0.00005-chip exploitability gate. The 100-iteration vanilla
and DCFR policies exceed the final target, and intermediate DCFR/CFR+ increases
remain visible. No monotone convergence claim follows. Every exact matrix
witness retains the known value `256757651065/457587630786`; its serialized
policy is separately replayed. Maximum production/replay scalar disagreement
is 2.512e-16 chips.

| Algorithm, 10,000 iterations | Known-value error (chips) | Median complete prepared call (seconds) |
| --- | ---: | ---: |
| Vanilla | 0.0000458009571 | 1.866398 |
| DCFR | 1.88956980e-7 | 2.409724 |
| CFR+ | 9.37444011e-10 | 4.060158 |

Final times are medians of three complete solve/production-diagnostic/JSON
calls. Intermediate checkpoints have one descriptive timing each. Legacy calls
at 100/1,000/2,000 iterations have exact non-budget payload agreement; their
3,000/5,000/10,000 requests remain rejected. Every 10,000-iteration prepared
request charges 273,936,960 entries under the unchanged 500-million cap.
Repeated final payloads are identical, source tables stay unchanged, and ranking
and enumeration functions are patched to fail throughout the experiment.

A separate complete 10,000-iteration CFR+ trace peaks at 24,251 Python bytes,
excluding the caller's input table, its construction, historical loading,
original enumeration and RSS. Independent replay and witness checks run outside
the timings and trace. This is admission for an already prepared table, not
kernel acceleration or a cold-call speedup.

The local full suite passed 823 tests in 403.566 seconds; nine focused admission
and fixture checks passed. The golden regression matches the complete default
2,000-iteration result against the previously merged frozen JSON. GitHub checks
the final head on Python 3.11/3.12/3.13 plus frontend/docs. Luna implemented,
independently tested and reviewed the bounded admission slice; the lead reviewed
integration and ran all regression and benchmark phases.
