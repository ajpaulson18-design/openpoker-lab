# Stable conditioned turn masses and fold utilities

## Diagnosis and scope

Sol identified two binary64 failures in the isolated matrix-free turn path at
baseline `bfae1fdfbd564500d662fe7e92459cbb4f1b5287` (PR #114). Luna implemented
the bounded correction; Sol reviewed the numerical law, admission order and
ordinary complete-result comparison. Shared ranked-river, CFR, postflop,
preflop/flop, explanation and UI code are outside this change.

On turn `2c5d9hJc`, select only river `As`. Give OOP `AhAs:1,KcKd:5e-324`
and IP `QhQs`. The selected river blocks the heavy OOP holding, so the sole
remaining physical deal has conditional probability one. With pot 20,
no matched additional wager and OOP winning a fold, opponent reach 1/4 must
produce the OOP vector `(0, 2.5)`; reach 3/4 must produce `(0, 7.5)`.
The old aggregate root operator returned `(0, 0)` and `(0, 10)` respectively.
Multiplying tiny unconditioned weights before dividing by tiny joint mass
lost information. Reversing the traversing player also exposed underflow in
the earlier opponent-weight-times-reach product.

A second selected game, turn `2c7d9hJs`, river `As`, OOP
`AsAh:1,3c4c:1e-200` and IP `AsKh:1,5c6c:1e-200`, has exactly one legal
conditional deal, `3c4c` versus `5c6c`. Its raw mass is near `1e-400`.
Rejecting this game because that unnormalized product rounds to zero is
unnecessary: the conditional probability is representable and equals one.
The implementation preserves original hand indexes and input ranges.

## Branch probability calculation

Ordinary branch masses retain the established arithmetic:

```text
mass(r) = filtered_mass_oop(r) * filtered_mass_ip(r) / kernel.factor(r)
P(r) = mass(r) / fsum(all branch masses)
```

If any raw branch mass is zero or subnormal, every branch instead retains a
mantissa/exponent representation `m(r) * 2**e(r)`, obtained by `frexp` on the
positive component factors. With `E = max(e(r))`, calculate:

```text
S = fsum(ldexp(m(r), e(r)-E) for r)
P(r) = ldexp(m(r)/S, e(r)-E)
```

Normalization precedes the final potentially subnormal `ldexp`. The original
mantissa/exponent stays available even if an intermediate common-scale term
rounds to zero. Tests require a minimum-positive conditional branch to stay
strictly positive; an absolute-tolerance comparison against zero is insufficient.
A genuinely unrepresentable positive final probability still rejects rather
than dropping support. The exceptional probabilities must also sum to one
within the existing numerical sanity scale. This is binary64 arithmetic,
not a general exact rational normalization implementation.

## Root fold operator and admission

Exceptional root folds integrate the existing branch-conditioned fold vectors,
weight each by `P(r)`, and scatter into original full-range indexes. This
avoids both demonstrated premature-underflow products. The normal aggregate
operator remains unchanged. Existing cumulative pair-fallback reservation and
`finally` charging apply to branch calls on success and error.

Before information-row allocation and training, the adapter adds a conservative
exceptional vector-work charge to the unchanged base envelope:

```text
extra = root_fold_terminals
      * (4 * max_original_hands * reachable_branches + 2 * filtered_hand_slots)
      * (requested_iterations * passes + 3 * planned_diagnostic_checks)
```

Passes are two for vanilla/DCFR and three for CFR+. Target mode reserves its
full requested ceiling and all planned checks even when training could stop
early. The same 30-million cap covers the total. These are modeled vector-slot
and pass counts, not literal Python instructions, elapsed-time bounds or RSS.
Existing construction, allocation and pair-fallback limits remain applicable.

Only exceptional results add `conditioning_mode` equal to
`scaled-branch-mass-and-conditioned-folds` and the resource field
`exceptional_root_fold_pass_work`. Ordinary complete payloads preserve their
prior fields and values.

## Accepted regression and ordinary parity evidence

The focused kernel tests include exact `Fraction` physical-world sums for both
players and fold winners, reaches 1/4 and 3/4, matched wagers, root/prefix
agreement, the newly admitted single-world game, unequal tiny branch masses,
and the representability boundary. The multi-river fixture has branch
probabilities 1/4 and 3/4 and independently verified full-range marginals.
The existing ranked-kernel rejection regression is retained.

The adapter tests compare original-range output to its pruned-equivalent game,
independently replay the complete policy against the original ranges, and
verify the closed-form full-ceiling charge. A cap between early-stop and
requested-ceiling work must reject before the trainer. Source review confirms
the guard also precedes information-row allocation.

Executed validation:

- All 13 turn-kernel tests passed after the final kernel test enhancement.
- All 16 matrix-free turn tests passed; the strengthened full-ceiling resource
  assertion was then separately rerun and passed.
- All 18 independent turn/river replay tests passed.
- The frozen old/new ordinary comparison completed all 12 cases: two existing
  turn fixtures, vanilla/DCFR/CFR+, fixed and zero-target modes, 20 sweeps.
  Complete payloads, including policies, resources and convergence records,
  are exactly equal. Every new complete policy passes independent replay of
  eight metrics, physical counts and metadata. Maximum scalar disagreement
  is `3.907985046680551e-14` chips; every unchanged 0.001-chip target misses.

See the [ordinary parity report](../benchmarks/results/turn-conditioned-mass-ordinary-parity-v1.json)
and [reproduction harness](../scripts/validate_turn_conditioning_parity.py).
Both changed historical production files are fingerprinted against the pinned
baseline; all unchanged production dependencies and the fixture specification
must match it. During historical calls only the shared trainer/evaluator class
references used by `isinstance` guards temporarily bind the archived kernel.
Their algorithms and kernel methods are unchanged; guards restore before new
calls, including error paths. Source fingerprints are checked before and after
measurement. Single-call timings are uncontrolled observations on a shared
host and establish no runtime, allocation or memory improvement.

## Complete exceptional-game policy evidence

The [acceptance harness](../scripts/benchmark_turn_conditioned_mass.py) freezes
the two demonstrated selected single-world cases above, with pot/stack 100/100
and 20/20 respectively, a single pot-sized wager, no raises and 20 sweeps for
each of vanilla, DCFR and CFR+. All six new original-range complete policies
pass independent physical-world, numeric-rule and legal visible-information
best-response replay. Each exactly matches the serialized strategy and all
eight scalar metrics of its pruned-equivalent single-world game.

The [acceptance report](../benchmarks/results/turn-conditioned-mass-acceptance-v1.json)
retains every metric, count, target miss and source fingerprint. All six
short-run original profiles miss the predeclared 0.001-chip NashConv target;
this is numerical correctness evidence, not an equilibrium claim. The six
pruned-equivalent controls miss too. Maximum independent replay disagreement
across the twelve new/control profiles is `1.4210854715202004e-14` chips.

The archived solver rejects the three `1e-400` case calls at branch-mass
admission. It admits the three subnormal-fold calls; their independent replay
mismatches are retained in the report rather than counted as successful
validation. The [policy folder](../benchmarks/results/turn-conditioned-mass-acceptance-policies-v1)
contains all six new originals, six controls and three admitted historical
complete results. Every file has a portable LF byte hash, is reread after
writing, and is independently replayed from saved bytes. Historical mismatches
are expected evidence; every new/control comparison must pass.

```text
python -m scripts.benchmark_turn_conditioned_mass --baseline-dir PATH
```

To reproduce ordinary parity, extract the two baseline files into a separate
directory using a byte-preserving Git/API tool, then run:

```text
python -m scripts.validate_turn_conditioning_parity --baseline-dir PATH --output benchmarks/results/turn-conditioned-mass-ordinary-parity-v1.json
python -m unittest discover -s tests -p test_turn_range_kernel.py -v
python -m unittest discover -s tests -p test_matrix_free_turn.py -v
python -m unittest discover -s tests -p test_turn_river_independent_validation.py -v
python -m scripts.validate_docs
```

## Remaining priorities and limits

This correction does not establish arbitrary ill-conditioned range support.
Some inputs still reject inside the unchanged ranked-river compatibility or
reciprocal normalization before turn branch masses can be formed. Existing
full-deck extreme-range rejection remains explicit. Broader physical-world
probability representability and branch-local orphan handling need separate
design and independent evidence; do not narrow accepted games merely to fit
an oracle's numeric limits.

Ordinary aggregate root arithmetic is preserved, so these finite regressions
do not prove it safe under every possible extreme combination of weights,
reaches and payoff scales. Exact conditional probabilities can also have
unrepresentable binary64 components. No general formal rounding bound or
unrestricted Hold'em equilibrium claim follows.

Sol's follow-up probe demonstrates that remaining boundary concretely:
use the first one-world fixture with OOP weight `1e-300` instead of `5e-324`
and opponent reach `1e-100`. Its raw branch mass is normal, so this change's
exceptional branch is inactive. Root OOP values still return `(0, 0)` while
the branch-conditioned operator and exact one-world calculation give
`(0, 1e-99)`; the reversed-player root loses `-1e-99` similarly. A subsequent
slice must address reach-product underflow at normal branch masses while
retaining bounded work and ordinary-game compatibility. This observation is
a measured residual, not a completed fix or a material-chip strategy claim.

The separate [river tail experiment](river-tail-realization.md) still misses
the 0.001-chip target on the bluff-catcher fixture. Its unresolved strategic
accuracy remains a priority alongside broader turn numerical coverage.
