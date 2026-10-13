# Matrix-free turn-to-river solving

The separate `pokerlab.matrix_free_turn.solve_matrix_free_turn` library entry
point solves a bounded configured heads-up turn/river game with full private
holdings and exact public river branches. It stores hand vectors and filtered
rank kernels, not private-pair/runout world lists. Existing postflop/flop,
preflop and Coach APIs retain their defaults and resource limits.

## Library use

```python
from pokerlab.matrix_free_turn import solve_matrix_free_turn
from pokerlab.river_config import RiverConfig

result = solve_matrix_free_turn(
    "2c5d9hJc", "AsAh:0.7,KsKh:0.3", "QcQd,TcTh",
    RiverConfig(30, (45, 22), (0.5,), (0.5,), 1, True),
    runouts=("3c", "4d", "7s"), iterations=100,
    target_exploitability=0.1, check_interval=20,
)
```

This explicitly solves the selected-river conditioned game. Omit `runouts` for
the full physical deck, subject to admission. A target is a stopping criterion,
not a promised result; inspect `convergence.stop_reason` and the reported gap.

## Physical chance law

A four-card board leaves 48 possible public river cards. Each physically
compatible pair of private two-card holdings removes four more cards and has
**44 legal rivers**. Confusing the two counts would distort the chance model.
For selected rivers R, let C_r sum original range-weight products over compatible
private pairs that do not contain r. The branch probability is
`C_r / sum(C_q for q in R)`, not `1 / len(R)`. Within each river branch the
compatible range products normalize conditionally. The ranked branch kernel's
values and own-hand marginals are multiplied by the global branch probability,
then scattered into original turn-range indices. Turn marginals sum those
branch marginals. Zero-support holdings retain their index but no policy row.

Selected rivers condition the **whole pair/runout game**. They are not sampling
or an unconditional approximation to full-deck solving. Positive physical
branches with unrepresentable binary64 mass are rejected rather than discarded.

At chance nodes, vector values sum over river outcomes. A turn action is then
maximized at its turn information set. Independently maximizing before summing
would let the turn player see the river. CFR+ likewise aggregates chance values
before updating/clipping turn regrets. River information sets include the
revealed river and full action history. Cumulative commitments, short-stack
refunds and fresh river OOP-first action use the established betting builder.

## Direct turn-fold integration

A turn fold occurs before the river is revealed, but still uses the globally
conditioned deal law. Enumerating every ranked river branch for a fold wastes
work. For a compatible pair i,j, its selected legal-river count is
`|R| - s(i) - s(j)`, where s counts selected cards contained in a holding.
Thus, against weighted opponent realization reaches q_j, an own holding i needs
`(|R| - s(i)) * compatible_sum(q) - compatible_sum(q * s)`.
Each compatible sum uses total/card inclusion-exclusion and identical-holding
add-back. Multiplying by the own range weight and dividing by the global
pair/runout normalizer gives the exact joint counterfactual mass. The fold
utility uses the usual signed initial half-pot plus matched contributions.
This is ordinary linear hand work, with bounded direct scans for ill-conditioned
cancellation. Joint mass is multiplied before normalization to preserve cases
where a valid selected branch has tiny original range mass.

The reference prototype instead sums globally weighted per-river fold vectors.
Its immutable source blob is `710b60b5070a4014eebfdbbd1cd04a7c2c15a76d` and is
retained in the engineering commit chain. This is a phase baseline, not a
commercial solver or an independent equilibrium oracle.

## Bounds and validation

The versioned `turn-hand-vectors-v1` envelope reserves global public states,
decision nodes, filtered kernel-hand slots, information/action slots and modeled
hand/state/pass work. It admits the entire requested iteration/checkpoint budget
before training allocations. Direct fallback scans share one cumulative budget
across every branch and the direct fold operator; failed calls still charge
consumed work. These counters do not promise elapsed time or resident memory.
Full random ranges across all 48 rivers can still exceed the information/action
budget. Coverage is reported by the configured admitted game, never inferred
from a two-river selected-subset probe.

An independently authored Fraction pair/runout enumerator checks branch mass,
root/river marginals, root/river folds and river showdowns, with blockers, weights,
ties, index holes and unequal contributions. An explicit two-river toy verifies
chance sums before turn best-response maximization: legal value zero versus
an invalid clairvoyant value of ten chips. Integration compares all three
algorithms with the existing physical-world turn solver, including full-deck
small ranges, selected subsets, raises, unequal stacks, all-ins, deterministic
output, targets and patched pre-training admission. The evaluator itself is
unchanged. Reported best responses are exact for the configured binary64 game;
finite training error is measured by NashConv/2, not assumed away.

A broader eight-hand full-deck probe exposed finite-iteration path sensitivity.
At iteration two, a mathematically tied row had legacy regrets `(0, 0)` versus
approximately `(6.94e-18, -6.94e-18)` under reordered arithmetic. Regret matching
then selected uniform versus pure play, which led to differing later policies
and a 0.452866-chip DCFR exploitability difference at 40 iterations (CFR+
difference 0.000372). Both paths describe the same chance/payoff law: direct
world terminal vectors differed by at most 7.64e-14, and marginals by 2.2e-16.
Replaying the candidate policy through materialized public-vector payoffs/BRs
reproduces its metrics. Arbitrary tie actions are permitted by CFR, but a claim
of identical finite trajectories would be false. No global absolute regret
cutoff is introduced: that could erase legitimate regrets of rare weighted hands.

The source-frozen [report](../benchmarks/results/matrix-free-turn-v1.json) is
reproduced by `python -m scripts.benchmark_matrix_free_turn`. Six small-range
comparisons use three interleaved complete-call timing repeats, plus separate
10-iteration traced-memory calls. All candidate policies pass materialized
public-vector metric replay; maximum separation is 1.5e-14 chips.

| Hands per player | Timed iterations | DCFR old / new seconds | CFR+ old / new seconds | Traced peak old / new |
|---:|---:|---:|---:|---:|
| 8 | 40 | 0.90 / 3.31 | 1.32 / 3.70 | 7.13 / 7.58 MB |
| 16 | 20 | 1.55 / 3.32 | 1.79 / 3.23 | See exact report |
| 32 | 10 | 2.45 / 3.39 | 3.09 / 3.79 | 29.53 / 26.09 MB |

These small full calls are slower under the new path. Keep the old backend for
small ordinary workloads; this opt-in representation advances coverage/storage,
not a universal performance win. Prepared root-fold calls alone improved
17.1x/18.6x/22.4x at 8/32/128 holdings, with vector errors below 3.6e-15 and
similar setup times. That phase gain is not a full-solver speedup.

The full random-range, **two-selected-river** probe uses 1,128 original turn
holdings per player, 1,081 legal holdings in each river branch, and 2,140,380
compatible pair/runout worlds. It materializes none of those worlds. Ten vanilla
iterations took 4.48 seconds, with traced peak 45.12 MB and exploitability
12.158 chips (pot 100). This is a coverage/resource probe, plainly unconverged,
and cannot represent full-deck strategic accuracy. The old API rejects even its
minimum ten iterations at the candidate-pair guard. The full 48-river/full-range
tree still exceeds the information/action-slot limit.

A separate [small terminal experiment](../benchmarks/results/small-river-kernels-v1.json)
found direct cached-rank pair sums 1.54x faster than sweeps at eight holdings per
side, but slower at 16/32/64. It adds no production dispatch rule; the evidence
does not justify a broad threshold. This records an investigated opportunity,
rather than building speculative complexity.

The full local suite passed **488 tests in 103.262 seconds**. Earlier focused
kernel/turn/preflop-envelope tests passed 25; the final kernel suite has nine
methods, and turn integration has ten including all algorithm/guard subcases.
No hand evaluator or earlier-street/Coach implementation was modified.
Commercial parity and unrestricted equilibrium accuracy remain unproven.
