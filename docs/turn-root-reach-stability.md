# Stable turn root folds at tiny opponent reach

## Confirmed defect and chosen correction

The [previous conditioned-mass correction](turn-conditioned-mass.md) fixed
zero/subnormal raw branch masses. Sol then reproduced a distinct remaining
failure on merged baseline `f934f4a`: a normal raw branch mass can still lose
a terminal numerator when opponent reach is tiny.

On turn `2c5d9hJc`, select only `As`, with OOP `AhAs:1,KcKd:1e-300` and IP
`QhQs`. Only `KcKd` versus `QhQs` survives the selection. At pot 20 and reach
`1e-100`, a fold won by OOP must return `(0, 1e-99)` for the OOP traverser.
The old root returned `(0, 0)`, while its conditioned prefix was nonzero.
Traversing IP similarly lost the negative value through the earlier
opponent-weight-times-reach product. With pot `2e100`, the same premature
rounding loses a full unit: both independent binary-rational arithmetic and
the conditioned prefix give 1.0, while the old root gives zero.

Luna implemented Sol's bounded rare-path design. Keep the ordinary aggregate
operator and its arithmetic unless a product with positive operands becomes
zero or subnormal at weighted opponent reach, own-hand joint mass, or
normalized joint mass. Test the first condition before treating total weighted
reach as zero. A detected risk recomputes the full root vector, preserving
original hand indexes, fold signs and matched wager scale. True zero reach
stays on the ordinary path.

The rare path sums compatible original private pairs directly. For disjoint
holdings, their number of selected legal rivers is the selected set size minus
the selected cards held by either player. It accumulates positive products of
the original normalized binary64 weights, opponent reach and this count using
`Fraction`. Multiply by the validated binary64 terminal scale and divide by
the established binary64 root mass before the final float conversion.

This arithmetic is exact **on those binary64 operands**. Its denominator is
the existing root normalizer represented as a Fraction; it is not a newly
computed exact rational physical-law denominator. Independent physical-world
checks and root/prefix comparisons therefore use a stated tolerance for
multiworld rounding. Exactly representable one-world anchors must agree
exactly. Final overflow remains a representability error. A final value below
binary64 representability can round to zero; intermediate zero products no
longer substitute for a representable final answer on this path.

## Admission, accounting and integer width

Before any stable-path Fraction conversion or pair scan, reserve the full
original own-hand count times opponent-hand count against both:

- the existing cumulative 30-million fallback-pair limit;
- a separate cumulative 100,000 stable-root pair limit.

Count physically blocked and zero-reach pairs that are inspected. Preflight
both limits atomically; insufficient budget starts no stable work. Once
accepted, charge both before execution and retain the charges on errors.
Earlier ordinary fallback work is also retained if a late trigger restarts
the vector. The kernel's optional `stable_root_pair_limit` accepts an exact
nonnegative integer for explicit bounded use and deterministic small-cap tests.

There are at most `C(48,2)=1128` unique holdings per player outside the turn
board. No pair/world table or per-pair Fraction list is created. At most one
own-row accumulator and the full own-hand answer vector are retained. Since
both hand counts are positive, row setup and accepted-call counts are bounded
by the admitted pair count too.

A conservative mathematical width bound follows from the accepted float
domains. Each binary64 denominator is a power of two with exponent at most
1074 (integer bit length at most 1075). Four dyadic factors have denominator
exponent at most 4296. Normalized weights are at most one, reach and finite
terminal scale are below `2**1024`, selected-card count is below `2**6`, and
the opponent-hand count is below `2**11`. Thus the positive sum before division
is below `2**2065`; aligning denominators needs fewer than 6362 numerator bits.
Dividing by the finite root mass adds at most 1074 numerator bits and, using
even the loose general float bound, at most 1024 denominator bits. The resulting
mathematical integers fit within 7500 bits. Accumulator/result width checks
guard this assumption against future changes.

Integer width and inspected-pair caps do not count Fraction gcds, aggregate
limbs touched, Python instructions, implementation temporaries, runtime or
RSS. A proposed width-times-pairs "bit work" label was rejected during review
because width alone does not establish an operation count. No such work
estimate is reported.

All existing tree, construction, information/action and full requested
hand-vector/checkpoint admission remains in place. The new allowance is a
dynamic cumulative cap, like the existing pair fallback cap: a solve can reject
during training when actual reaches require too much stable work. It does not
promise that pre-admitted training will finish within this dynamic allowance.

Only results that actually use the rare path add `root_fold_mode` equal to
`exact-normalized-binary64-pairs`, its call/pair counters, the stable-pair
limit and integer-width bound. Ordinary complete outputs and the prior
exceptional branch-conditioning path keep their previous fields and values.

## Scope and remaining work

This changes the isolated turn root-fold operator and its adapter metadata.
Shared ranked-river/CFR, postflop, preflop/flop, Coach and UI remain outside
the slice. It neither broadens the ranked-kernel extreme-range admission
domain nor proves arbitrary floating-point payoff accuracy. The prior
zero/subnormal branch-mass normalization and its resource envelope remain
separate. See [the previous numerical limits](turn-conditioned-mass.md#remaining-priorities-and-limits)
and [unmet river accuracy targets](river-tail-realization.md).

## Executed acceptance evidence

All 55 focused tests passed in 83.342 seconds across turn kernel, matrix-free
turn adapter and independent turn/river oracle. They cover tiny positive
reaches, nonzero subnormal intermediates, normalized-mass underflow, both
traversers/winners, matched wagers, multiple selected cards, true-zero reach,
invalid pair limits, atomic preflight and retained charges after injected
conversion failure. The adapter metadata test performs one explicitly injected
risky-reach observation during an actual solve; the actual strategy and all
eight diagnostics remain exactly equal to an unwrapped solve. It does not
claim that the observation arose naturally in that CFR trajectory.

Sol's separate [witness harness](../scripts/benchmark_turn_root_reach.py)
enumerates physical private pairs and selected rivers directly with exact
`Fraction` raw binary64 input weights, without production probability, tree,
payoff, evaluation or best-response helpers. Six frozen fixtures yield 48
fold vectors across both traversers, both winners and matched contributions
0/4. They include the nonzero subnormal product, unequal river masses,
normalized-product trigger, one-unit scale anchor and true-zero control.

Every new vector exactly equals the independently calculated binary64 answer
in these fixtures. The gate also requires the exact zero/nonzero classification
and at most `1e-12` relative error for nonzero components; an absolute-only
gate could miss the original tiny-value failure. Maximum root versus summed
prefix relative difference is `1.8503717077085936e-16`. The frozen old kernel
differs in 32 vectors, with maximum absolute error 1.0. Full parameters,
rational answers, old/new vectors, differences and source hashes are retained
in the [witness report](../benchmarks/results/turn-root-reach-witnesses-v1.json).
These are numerical payoff checks, not learned-policy quality results.

The [ordinary parity harness](../scripts/validate_turn_reach_parity.py) freezes
both changed production modules at `f934f4a` and checks every unchanged
production dependency and fixture specification against that commit. Across
the two existing turn fixtures, three algorithms and fixed/zero-target modes
at 20 sweeps, all 12 complete payloads are exactly equal, including strategies,
resource records and convergence. Each complete new policy passes independent
numeric-rule and legal information-set best-response replay. All unchanged
0.001-chip benchmark thresholds miss; see the [full report](../benchmarks/results/turn-root-reach-ordinary-parity-v1.json).
This comparison threshold is distinct from the solver stopping setting:
fixed calls configure no target and zero-target calls configure
`target_exploitability=0.0`.
The archived class temporarily binds only shared runtime type guards during
old calls, restoring them before new calls; algorithms remain untouched.
Source fingerprints must stay fixed throughout measurement. Single old/new
timings are uncontrolled observations, with no speed/RSS claim.

Sol also regenerated all six original-range exceptional profiles saved by the
previous slice, using their saved configurations and algorithms. Every complete
payload remains exactly equal and passes independent replay. The separate
zero/subnormal branch-conditioning path is preserved.

Reproduction requires a byte-preserving extraction of the baseline's two
production files into `PATH`, then:

```text
python -m unittest tests.test_turn_range_kernel tests.test_matrix_free_turn tests.test_turn_river_independent_validation
python -m scripts.benchmark_turn_root_reach --baseline-dir PATH --output benchmarks/results/turn-root-reach-witnesses-v1.json
python -m scripts.validate_turn_reach_parity --baseline-dir PATH --output benchmarks/results/turn-root-reach-ordinary-parity-v1.json
python -m scripts.validate_docs
```
