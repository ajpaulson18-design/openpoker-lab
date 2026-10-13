# Blocker-aware ranked river terminals

The follow-up to merged PR #78 investigates repeated quadratic terminal scans
on a complete river board. The optional specialization retains the existing
physical-world representation, betting builder, CFR schedules, average
strategies, exact information-set best responses and admission guards.
It does not expand the supported range/tree budgets or earlier streets.

## Research and independently authored implementation

[Johanson, Waugh, Bowling and Zinkevich (IJCAI 2011), Accelerating Best Response
Calculation in Large Extensive Games](https://johanson.ca/publications/poker/2011-ijcai-abr/2011-ijcai-abr.pdf),
section 4, describes rank ordering and card inclusion-exclusion for efficient
poker terminal evaluation. The paper distinguishes genuine worst-case
evaluation from head-to-head success and warns that abstraction refinement
does not guarantee less real-game exploitability. These distinctions remain
important for OpenPoker Lab's finite action trees.

`pokerlab/ranked_river.py` is independently authored standard-library Python.
No external implementation, commercial output, dependency or license-bearing
source code was adopted. This is an algorithm implementation from a primary
research description, not an adoption of a solver framework.

## Mathematical boundary

Given nonnegative independent combo weights `w0`, `w1`, the joint distribution
is `w0[i]*w1[j]/Z` for physically compatible holdings and zero otherwise.
`Z` sums those compatible products. The kernel normalizes each side by its
own scale before joint normalization; this does not change the distribution.
The opponent's action reach is separate from their initial range weight.

At folds, compatible opponent reach mass for a hand containing cards `a,b`
is total mass minus the mass containing `a` minus the mass containing `b`,
plus the exact matching two-card holding's mass. The matching holding is
otherwise subtracted twice, although it is only one blocked opponent holding.
Multiply by own range weight, `1/Z`, and the signed fold utility.

At showdown, sorted ranks permit lower and higher opponent-rank sweeps.
Subtract blocked lower/higher masses for each private card; equal ranks have
zero utility. An identical holding has equal rank, so its signed correction
is zero. The net compatible win-minus-loss mass multiplies own range weight,
`1/Z`, and `pot/2 + min(contributions)`. Using the minimum commitment returns
unmatched excess for short-stack all-ins and folds.

Ranks and rank groups are cached per board. Ordinary terminal work is linear
in the two ranges and rank groups, using sparse compensated card accumulators.
The kernel uses integer card counts to establish physical pair existence.
Ill-conditioned normalization and near-canceling utility calculations fall
back to direct compatible-pair/holding sums. These rare paths may be quadratic;
there is no unconditional linear-time claim. They preserve small valid mass
rather than silently clamping it away. The integration accepts only complete
fixed-board, factorized range-product worlds with matching ranks and weights;
arbitrary correlated worlds must use the original sparse backend.

## Independent validation

`tests/test_ranked_river.py` uses a rational pair-loop oracle for normalized
joint mass and utilities, with the established evaluator supplying hand ranks.
It covers both player perspectives, identical and one-card blockers, weighted
sparse and dense random ranges, zero reach, all-board ties, folds, unequal
commitments/refunds, all 1,081 board-compatible holdings, and malformed inputs.

The oracle caught a real precision defect: large opposing win/loss masses
initially erased a small valid signed residual. Compensated rank/card sweeps
and cancellation fallback fixed it. Tests preserve a small residual even with
action reaches bounded by one and range weights differing by `10**16`, and
retain the only surviving compatible hand behind dominant blocked weight.

## Terminal-only measurement

`python -m scripts.benchmark_ranked_river` prepares cached sparse pair edges
`(i,j,mass,signed_mass)` before timing. Its timed reference matches the existing
production terminal arithmetic; blockers and rank comparisons are not
recomputed per terminal. An additional independent pair oracle is untimed.
An initial slower pair-loop baseline was rejected during senior review and
replaced before recording the final report.

The report `benchmarks/results/ranked-river-v1.json` records ten interleaved
samples per method, exact inputs, source hashes, preparation cost and separate
traced working allocation. Each values sample covers fold and showdown
utilities for both players.

| Hands per player | Cached sparse median | Ranked median | Phase speedup |
| --- | ---: | ---: | ---: |
| 64 | 1.22 ms | 1.00 ms | 1.22x |
| 128 | 5.12 ms | 1.85 ms | 2.77x |
| 256 | 20.37 ms | 3.10 ms | 6.57x |
| 512 | 93.80 ms | 6.18 ms | 15.19x |

Maximum utility difference was below `5.6e-17` chips. Ranked working allocation
was higher (about 84–264 KB versus 9–66 KB); cached pair storage/preparation
is separate. These are terminal phase timings, not complete-solver speedups.
They exclude adversarial numerical fallback cases. The exact measured source
is recoverable with `git cat-file blob 85b81a6e8edddaa55d1b6080aff01cbad7f9d216`;
the prototype file remains reachable in the published history. Integration
adds world validation after that checkpoint.

## Optional production integration

Use `solve_postflop(..., traversal="public-batched", terminal_backend="ranked")`
on a five-card board. `diagnostics="public-batched"` accelerates diagnostics as
well; recursive diagnostics remain an independent reference. Accuracy targets
from PR #78 can be combined with this option. The result identifies
`terminal_backend="ranked-river-python"`; default sparse solves have no new
field. Ranked mode rejects turn/flop starts and recursive/planned training.

Before using factorized arithmetic, the kernel validates all complete river
worlds: compatible pair coverage, unique indices, no future-card suffix,
matching pot, expected joint masses and cached showdown rank signs. The
trainer and evaluator preserve full range indexing even for orphan hands with
no compatible opponent; those hands receive zero mass and are not serialized
as reachable information sets. Chance-conditioned or correlated generic worlds
cannot be supplied as if they were independent river ranges.

Senior review found a second cancellation boundary during integration: with
only a `1e-8` or `1e-10` weighted hand surviving dominant card blockers,
normalization could disagree with physical worlds despite valid ranges. Direct
compatible-mass summation now handles ill-conditioned constructor and terminal
mass, including when only one hand is ill-conditioned. Regressions compare
the resulting solves across all three algorithms and test relative accuracy
for tiny surviving opponent reach. This trades speed for correctness on those
rare paths.

## Complete-call measurement

`python -m scripts.benchmark_ranked_river_solver --skip-memory` compares the
same algorithm, game and iteration count with only terminal payoff arithmetic
changed in training and public diagnostics. It includes enumeration, setup,
training, exact BR diagnostics and result assembly, without JSON serialization.
Three interleaved calls produce each median. All guards remain in place.

| Hands per player | Iterations | DCFR sparse/ranked time | CFR+ sparse/ranked time |
| --- | ---: | ---: | ---: |
| 64 | 50 | 0.66x | 0.70x |
| 128 | 50 | 1.51x | 1.32x |
| 256 | 10 | 0.82x | 0.97x |
| 256 | 40 | 1.40x | 1.72x |

Ratios above one favor ranked solving. Small and low-iteration workloads can
be slower because sorting, validation, numerical safeguards and additional
working arrays outweigh reduced terminal scans. The sparse backend stays the
default; no automatic performance crossover is asserted. Complete-call metric
differences were at most `7.1e-14` chips and policy differences below `1e-13`.
These are finite-iteration correctness/performance comparisons, not converged
commercial reference results. The final complete-call report skips repeated
memory tracing explicitly; its peak-memory values are null.

The 256-hand/40-iteration row is a separate, focused probe recorded by
`python -m scripts.benchmark_ranked_river_budget`. Both algorithms fit the
unchanged guards: candidate-pair work used 87% of its budget and CFR+ used
96% of the world-node budget. It tests the larger admitted iteration workload
without repeating smaller cases. Its metric differences were below
`1.42e-14` chips. Higher iteration counts amortize setup more effectively;
this does not justify choosing ranked arithmetic for every river solve.

The earlier complete-call report retains its measured harness hash and
explicitly records a post-measurement terminology correction: the selected
payoff backend changes both training and diagnostics, and every configured
case was admitted. Numerical measurements and solver source hashes are
unchanged by that report-text correction.

The full local suite passed 453 tests in 109.583 seconds before the final
near-total-blocker regression. After that numerical fix, all 48 focused kernel,
integration, postflop, public traversal/diagnostic and accuracy tests passed
in 11.809 seconds. Source-based default
result comparisons against merged main `5c712f8` matched exactly on eight
flop, turn and river algorithm cases. Final CI results are recorded separately.

## Next architectural step

Repeated world enumeration, sparse prefix preparation and validation still
limit complete-call gains and retain quadratic pair storage. A future immutable
prepared-game interface could safely reuse validated distributions and provide
linear-size river range metadata directly to training/diagnostics. Extending
ranked arithmetic to turn river-prefix terminals requires global physical
chance mass and blocked-hand index maps; normalizing each river independently
without its root chance mass would be incorrect. These are architectural
follow-ups, not implemented features or claimed full-range capacity increases.
