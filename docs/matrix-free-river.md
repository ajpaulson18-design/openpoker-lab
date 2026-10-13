# Matrix-free configured river solving

This opt-in library path removes the private-pair world and prefix-edge lists
from fixed-board river solving. It retains the configured heads-up action tree,
full private holdings, physical blockers, weighted ranges, and exact visible
information best responses. It introduces no hand buckets, sampling, rake,
third-party implementation, or runtime dependency. It does not certify
commercial solver parity or unrestricted no-limit Hold'em accuracy.

## Library use

```python
from pokerlab.matrix_free_river import solve_matrix_free_river
from pokerlab.river_config import RiverConfig

result = solve_matrix_free_river(
    "2c7d9hJsKd", "random", "random",
    RiverConfig(100, 200, (0.75,), (), 0, False),
    iterations=500, target_exploitability=0.01, check_interval=50,
)
```

The action tree in this example matches the benchmark abstraction; it has no
raises. Inspect `convergence.stop_reason` rather than assuming the requested
target was achieved. Larger trees and iteration caps can be refused by the
separate admission model.

## Mathematical boundary

For compatible holdings i,j, the joint chance weight is
`w0[i] * w1[j] / Z`, where Z sums products over physically compatible pairs.
For an own hand containing cards a,b, compatible opponent mass is total mass
minus mass containing a minus mass containing b plus the mass of the identical
holding. The last term corrects the double subtraction. Multiplying this mass
by the own normalized weight and `1/Z` produces the **joint hand marginal**.
Independently normalizing each player's unblocked range would be wrong.

The existing prepared public-vector CFR traversal uses opponent realization
reach for counterfactual values and own realization reach with these chance
marginals for average strategies. Vanilla/DCFR remain simultaneous; CFR+
remains alternating OOP/IP with post-sweep linear averaging. Exact BRs maximize
by the responder's private hand and public history, without seeing opponent
cards. Rank-ordered terminal sweeps are reused from the preceding backend.

Research basis: Johanson, Waugh, Bowling and Zinkevich,
[Accelerating Best Response Calculation in Large Extensive Games](https://johanson.ca/publications/poker/2011-ijcai-abr/2011-ijcai-abr.pdf),
IJCAI 2011, especially the public-tree and rank-ordered terminal computation.
This is an independently implemented standard-library specialization. No
external solver source is incorporated; commercial licensing obligations are
unchanged.

## Admission and numerical limits

A separate versioned `river-hand-vectors-v1` admission model bounds information
set/action slots, allocated public states, and modeled hand/state/pass work.
It does not relax the existing world-based postflop or preflop guards. The full
requested iteration/checkpoint budget is admitted before training, regardless
of hoped-for early stopping. Counters model work/allocation slots, not elapsed
time or resident memory guarantees.

Inclusion-exclusion may suffer cancellation when nearly all opponent mass is
blocked. The ranked kernel retains direct compensated compatible-pair scans
for these rare cases. This means **matrix-free storage**, not an unconditional
linear runtime guarantee. A separate cumulative candidate pair-check cap is
reserved before each fallback scan, including constructor normalization and
marginal computation. Exhaustion rejects the solve rather than skipping terms
or certifying an incomplete result. Ordinary callers retain their previous
uncapped fallback behavior.

Range normalization and calculations use binary64. Excessive weight dynamic
range or an unrepresentable normalizer is rejected. A convergence target is
NashConv/2 in chips for this finite configured game; a missed target is reported
as an iteration limit. Small numerical agreement with another backend does not
establish an unrestricted equilibrium proof.

## Validation and measurements

The source-frozen report is [matrix-free-river-v1.json](../benchmarks/results/matrix-free-river-v1.json),
reproduced by `python -m scripts.benchmark_matrix_free_river`. Three interleaved
complete-call timing repeats include setup, training, exact BRs and strategy
construction, excluding JSON encoding. Separate 10-iteration tracemalloc calls
measure peak traced Python allocation, not resident memory.

| Hands per player | Iterations timed | DCFR speedup | CFR+ speedup | Materialized peak | Matrix-free peak |
|---|---:|---:|---:|---:|---:|
| 128 | 50 | 1.54x | 1.60x | 6.55 MB | 0.89 MB |
| 256 | 40 | 2.43x | 2.34x | 25.59 MB | 1.75 MB |

Both backends use the same ranked terminal computation. Maximum metric
separation was 8.9e-16 chips; maximum policy separation was 3.4e-16. These are
synthetic finite-tree measurements, not universal performance guarantees.

Full uniform random/random ranges contain 1,081 legal holdings per player and
1,070,190 compatible pairs. The new path materializes zero worlds and admits
10/50/100 CFR+ iterations, taking 0.49/2.26/4.49 seconds in single descriptive
calls, with exact exploitability 0.811/0.107/0.0404 chips for pot 100. The
10-iteration traced peak was 6.83 MB. The old API rejects even 10 iterations at
its existing candidate-pair guard; there is no invented old full-range runtime.

Independent Fraction pair-loop marginals, an analytical nuts/air game with
exhaustive visible-information BRs, all three algorithms, weighted blockers,
orphan hands, multiple bet/raise sizes, unequal stacks, deterministic repetition,
accuracy checkpoints and patched pre-allocation guards are tested. An extreme
positive compatible product of 1e-400 is explicitly rejected as unrepresentable
in binary64 rather than mislabeled as a physically empty range. Existing default
complete results matched base `3ee96fb` exactly on fourteen flop/turn/river
cases. The existing training-loop AST was preserved by the prepared extraction,
except for river-only defensive chance rejection. Focused tests passed 46. The full local suite passed 467 tests in 88.826
seconds before the subsequent analytical-boundary tests. The independent oracle
now also covers saturated bluffing, the exact threshold `(P+B)/(P+2B)`, and
pure nut-prior endpoints. Exhaustive rational BRs certify those anchors exactly;
three trained high-nut cases at 1,500 CFR+ iterations have NashConv and value
error below 0.001 chips.


## Integration boundary and next opportunities

The new entry point is separate from server/UI and Coach code. Existing
world-based API defaults and resource envelopes remain unchanged. The prepared
CFR/diagnostic extraction preserves the existing traversal arithmetic; default
flop, turn and preflop regression checks are required before merge.

Turn still materializes private-pair/runout worlds. Extending this representation
to turn requires correctly conditioned per-river range products, global chance
normalization, public histories, hidden future cards, and turn regret aggregation.
Independent river solves cannot simply be averaged: their equilibrium responses
must be consistent with the turn strategy's reach. That is the next substantial
architectural problem, separate from this fixed-board storage improvement.
