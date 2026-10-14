# Longer-budget conditional turn-to-river accuracy

## Sol diagnosis and fixed experiment

The earlier source-frozen grid left the existing
`two-conditioned-runouts-asymmetric-multisize` fixture at approximately
0.0469402308876 NashConv after 300 matrix-free CFR+ sweeps. That row is
historical context, not a newly executed baseline. After the isolated
[river accuracy extension](river-long-budget.md), this slice measures strategy
quality across an actual turn decision and future river play without changing
production solvers, algorithms, admission or shared earlier-street code.

Freeze the existing fixture exactly: turn `Js8d4c2h`, OOP
`AsAh:0.5,KsKh:1`, IP `AcAd:1,KcKd:0.75`, and selected rivers `3c,5h`.
The starting pot is 100, stack caps are 220/120, turn opening sizes are
0.5/1.0 pot, river openings are 0.75/1.25 pot, raises use 0.5 pot with one
raise allowed, and all-ins are included. Keep the distinct river configuration
in both solving and independent replay.

Run CFR+ at fixed 1,000, 3,000 and 10,000 completed sweeps on each existing
materialized/public-batched and matrix-free backend. Save all six complete
policies and report every meet/miss of the predeclared 0.001-chip NashConv
benchmark threshold. These fixed calls configure no solver stopping target.
Selected rivers condition the entire joint pair/runout game; this is not a
full-deck or unconditional turn approximation.

## Admission and independent validation

The fixture has four compatible private pairs, eight physical pair/river
worlds, 138 information sets and 188 aggregate public states. Both backends
admit the fixed 10,000 ceiling under their existing limits. The matrix-free
path charges 11,281,128 modeled hand/state passes. The materialized path's
world-node charge is `8*41*10000*3 = 9,840,000`; its per-world traversal count
is 41. Multiplying by the 188 aggregate cross-world states would misstate that
model's existing guard.

Before the experiment, actual target-mode preflights requested 10,000 with a
very loose target and stopped at ten. Matrix-free reserved the full
12,409,128 conservative target-mode charge; materialized admission also
passed. Those preflights establish admission only. They are not long-training
quality evidence or evidence that the 0.001 benchmark threshold was met.

Every complete policy must independently replay from numeric betting rules,
original exact-Fraction binary64 input weights, physical card removal,
independent best-five ranks and legal visible-information best responses.
Compare all eight diagnostics, physical counts, complete rows/action metadata,
selected/reachable rivers and both street configurations. Future river cards
remain hidden at turn decisions. Save portable LF policy bytes with hashes,
reload and independently replay them again. Production, helper, fixture and
runner fingerprints must remain fixed throughout measurement.

There is no separately known closed-form value for this raised weighted turn
fixture. The one-bet river's 25-chip analytical witness does not apply. Exact
legal-policy BR replay supplies the measured finite-game quality evidence;
neither diagnostic agreement nor finite iterations prove unrestricted GTO.
Single complete-call timings are uncontrolled observations, not equal-cost
algorithm comparisons, speedups or allocation/RSS guarantees.

## Executed results and review

| Backend | 1,000-sweep independent NashConv | 3,000-sweep independent NashConv | 10,000-sweep independent NashConv |
| --- | ---: | ---: | ---: |
| Materialized/public-batched | 0.00423446838077 | 0.000470810046572 | 0.0000423827902161 |
| Matrix-free | 0.00423446838077 | 0.000470810046565 | 0.0000423827902161 |

Both 1,000-sweep profiles miss the unchanged 0.001 threshold. Both backends
meet it at 3,000 and 10,000 sweeps: four meets and two misses, all retained.
Every profile completes exactly its requested budget, with eight worlds,
four compatible pairs, 138 information sets and 188 public states independently
verified. Materialized policies report eight stored worlds and 41 per-world
traversal nodes; matrix-free policies report zero materialized worlds.
All fixed work charges match their backend-specific formulas and existing caps.

The [complete report](../benchmarks/results/turn-selected-accuracy-v1.json)
retains all eight metrics, differences, counts, work charges, uncontrolled
single-call timings and 53 protected source fingerprints. The
[policy folder](../benchmarks/results/turn-selected-accuracy-policies-v1)
contains all six complete LF JSON profiles and raw byte hashes. Every policy
passes independent replay before saving and again after reloading. Sol also
reloaded all six files in a separate process, checked LF bytes and hashes,
replayed with the correct two street configurations/runouts, and verified
all protected fingerprints. Maximum disagreement across **all eight** metrics
is `1.4210854715202004e-14` chips, at the matrix-free 3,000-sweep OOP gain.

All 21 focused tests passed: three harness regressions and eighteen independent
turn/river replay tests. Review caught and corrected a board-token comparison
and resource-field location error before long-run acceptance. Harness tests
now use cached actual ten-sweep results from both APIs and mutate copied
metadata to verify failed work/limit/river-config and counter gates. They
separately pin the two closed-form resource dimensions, including the distinction
between aggregate public states and per-world traversal nodes. After the final
test-only change the 21-test suite passed in 5.76 seconds; the frozen benchmark
runner and all measured production/oracle sources remained unchanged.

The [bounded runner](../scripts/benchmark_turn_selected_accuracy.py) pins the
fixture, both backends and all three budgets. Its gates reject inconsistent
metadata, incomplete sweeps, stop targets in fixed calls, wrong conditioning,
exceeded limits or replay disagreement. No production source differs from
baseline `182d6b6`; the slice adds development evidence and its tests/documents.

Reproduction:

```text
python -m unittest tests.test_benchmark_turn_selected_accuracy tests.test_turn_river_independent_validation
python -m scripts.benchmark_turn_selected_accuracy
python -m scripts.validate_docs
```

These measured policies are specific to the selected two-river game. Broader
full-deck turn accuracy, arbitrary extreme ranges and unrestricted Hold'em
remain separate. Independent float diagnostics still have numerical rounding.
The later [exact rational arithmetic audit](turn-rational-certificate.md) adds
response bounds for separately normalized versions of these complete policies,
without implying an exact raw-binary64 bound or changing this experiment.
