# Preflop chance-sampled CFR with exact full-game diagnostics

`solve_preflop(..., traversal="chance-sampled", resource_model="chance-sampled",
diagnostics="public-batched", algorithm="vanilla")` adds opt-in joint-world
chance sampling. Existing recursive, planned and public-vector defaults and
payloads remain unchanged. CFR+, DCFR, recursive diagnostics and strategy locks
are unsupported on this new path. No shared CFR, postflop, turn/river,
public-diagnostic or AI Coach source is changed.

```python
from pokerlab.preflop_solver import solve_preflop

result = solve_preflop(
    "AsAd:1,AhAc:0.25", "KsKd:1,KcKh:0.5",
    config={"starting_stack": [4, 3], "max_raises": 0},
    runouts=["2c3c4d7h8h", "Kc2d3h7s8c", "Ac2d3h7s8c"],
    iterations=1000, algorithm="vanilla", traversal="chance-sampled",
    diagnostics="public-batched", resource_model="chance-sampled",
    sampling_seed=17, samples_per_iteration=8,
)
print(result["nash_conv"], result["sampling_statistics"])
```

## Method and provenance

The method is independently implemented from Lanctot, Waugh, Zinkevich and
Bowling, [Monte Carlo Sampling for Regret Minimization in Extensive Games
(2009), section 3, equation 6 and chance-block discussion](https://papers.nips.cc/paper/2009/file/00411460f7c92d2124a67ea0f4cb5f85-Paper.pdf).
One draw fixes a joint private-hand/five-card outcome independently of betting
actions. Every betting action remains enumerated on that draw. Opponent hands
and future cards never enter policy keys; keys remain own hand plus public
history. This is chance sampling, with neither opponent-action nor outcome
sampling. The implementation uses simultaneous vanilla regret matching, not
sampled CFR+ or a variance-reduction algorithm.

Let stored world mass be `p[w]`, total mass `P`, and draw probability
`q[w] = p[w]/P`. One-world counterfactual deltas use opponent reach and the
acting player's utility sign; average numerators use own reach. Each draw
contributes `P/batch_size` times those unweighted quantities. Thus the
unnormalized batch estimators match full-world weighted deltas and average
numerators in expectation, subject to binary floating arithmetic. The
normalized average policy is a ratio estimator; it is not claimed unbiased at
finite sample counts. The profile stays frozen throughout a batch, and both
players' regret rows update together afterward. Unvisited policy rows serialize
as uniform probabilities. Sparse batch maps and a lazy policy cache avoid
rematching all information sets each iteration.

Sampling uses `float.as_integer_ratio`, a common binary denominator, integer
cumulative weights and `random.Random(seed).randrange(total_integer_mass)`.
This preserves every positive represented float weight, including subnormals,
and skips zero-weight entries. It avoids floating CDF rounding that can erase
rare outcomes. Sampling support is exact for the represented weight law;
regret arithmetic and total-mass scaling remain binary floating operations.
Seeds must be exact integers in `[0, 2**64-1]`; batch sizes are exact integers
from 1 through 256. A SHA-256 digest of drawn canonical world indices, the RNG
name, counts, seed and Python version make observed runs reproducible.

Luna authored the sampling core, its initial tests and an independent sampler
storage census. Lead supplied integration, structural training admission,
additional hand-computed two-player/boundary/lifetime regressions and frozen
measurements. Luna reviewed integration, guards and measurement methodology.
No third-party source, dependencies, solver policies or commercial output were
incorporated. This research method is opt-in; endpoint evidence determines its
practical usefulness.

## Explicit admission and limits

Full-world iteration charges do not describe sampled training. This explicit
resource mode constructs the complete selected joint game once, retaining the
3-million absolute candidate-pair/world bounds, selected-outcome and 30-million
logical pair/runout preflight charges. It further caps sampled materialized
worlds at 250,000 **before ranking**, without admitting full-deck preflop.
Existing public-state, decision, temporary-template and copy-state bounds
remain. Information-set action slots reserve before insertion under the
1-million-slot cap.

An independent structural census counts a worst-case draw: decisions sum all
action subtrees, while chance nodes take the largest single branch. It caps
training node visits and action cells separately at 30 million, before sampling
allocation. Actual visit counts must fit the bound. These counters are
structural work measures, not instruction counts, elapsed-time or RSS bounds.

Sampler admission separately caps cumulative entries at 250,000 and logical
retained integer payload at 128 million bits. The latter uses a conservative
maximum cumulative-integer width derived from represented world weights and
positive-row count. It does not construct the CDF itself. Python headers,
container slots, temporary ratio/float arrays and query scratch are outside
this logical bit payload; their row counts are bounded, but no allocated-byte
or RSS guarantee follows.

Exact final diagnostics are separately admitted using the existing vector
census at **one vanilla iteration**. That conservative reference includes an
unused vector training allowance plus actual full-game diagnostic work and
prefix/dense/action caps. It is not an actual sampled-training work count.
Every final value and legal best response enumerates the full configured
world distribution; no sampled payoff or gap estimate is reported as exact.
No-information-set games skip sampling and retain exact refund diagnostics.

## Independent validation and measurements

Tests check hand-computed weighted expectations, both players' counterfactual
and own-reach factors, deterministic importance-scaled parity with vanilla CFR,
frozen batches, hidden public chance branches, zero/tiny probability support,
seed replay, constructor/storage/work guards, normal
and exceptional closure release, and known Kuhn legal best responses. Numeric
configured-policy replay independently checks actual weighted multi-flop poker
information sets, action amounts, probabilities and exact visible-information
best responses. Production evaluation is the candidate, never that oracle.

The frozen [specification](../benchmarks/preflop-chance-sampled-v1.json) records
all seeds and checkpoints before measurement. Complete fixed-flop runs retain
the existing four private pairs, all 7,920 worlds and all 17,620 policy rows
conditioned on `2c3c4d`; the unchanged accuracy target is 0.001 chips. Weighted
selected multi-flop runs use a separate 0.01-chip target. A known Kuhn fixture
uses independent rational-value anchors and exhaustive pure-policy responses.

At frozen source `b9ea214450bcedb677d2b72c20a43b3523ee5b42`, the worktree was clean at measurement start and all 52 source hashes plus specification/historical-report hashes stayed fixed. Maximum scalar disagreement with independent configured replay was `2.13e-14` chips. All 17,620 full-fixed-flop policy rows, 7,920 worlds and four private-pair posteriors were checked at each endpoint. Every predeclared full-flop and selected-game target **missed**.

| Game | Iterations / batch | Seed | Exact NashConv chips | Complete seconds | Target met |
| --- | ---: | ---: | ---: | ---: | --- |
| complete_fixed_flop | 1000 / 32 | 2 | 0.223998430 | 18.412 | no |
| complete_fixed_flop | 1000 / 32 | 17 | 0.226817371 | 19.721 | no |
| complete_fixed_flop | 1000 / 32 | 53 | 0.241784222 | 18.622 | no |
| complete_fixed_flop | 10000 / 32 | 2 | 0.038071173 | 156.067 | no |
| complete_fixed_flop | 10000 / 32 | 17 | 0.037045969 | 151.989 | no |
| complete_fixed_flop | 10000 / 32 | 53 | 0.038691167 | 153.226 | no |
| weighted_selected_flops | 1000 / 8 | 2 | 0.011532215 | 16.106 | no |
| weighted_selected_flops | 1000 / 8 | 17 | 0.012482086 | 15.218 | no |
| weighted_selected_flops | 1000 / 8 | 53 | 0.013390565 | 13.557 | no |

The separate 100-iteration full-call traced peak was **42,325,089 Python bytes**. Known Kuhn gaps at 3,000 samples range from 0.028656 to 0.042797; at 30,000 they range from 0.008395 to 0.014517. These passed their predeclared 0.08-chip gap and 0.04-chip value-error gates, which do not certify Hold'em accuracy.

The [complete report](../benchmarks/results/preflop-chance-sampled-v1.json) preserves every seed, posterior/replay check, resource census and padded value interval. Sampling is not promoted as the preferred accurate solver: the prior exact delayed-CFR+ endpoint remains 0.000798538 chips on this same configured game. The next optimization should target variance or public-chance batching before spending more budget on this unoptimized joint-world path.

Each timing is one uninstrumented complete call including JSON serialization;
pre-call GC and independent replay are excluded. Seed variation changes the
algorithmic path and is not repeated timing evidence. The previous delayed
CFR+160 report is a hashed historical accuracy reference, not a new controlled
runtime or equal-work comparison. Every failed target stays recorded.

Caller-supplied runout sequences are prepared before timing/tracing. A separate
100-iteration complete fixed-flop call measures traced Python peak
through final exact diagnostics and serialization. It excludes the independent
oracle, interpreter/native allocations and process RSS; it does not bound
10,000-iteration memory. Logical CDF payload and whole-call allocation tracing
are distinct evidence.

```text
python -m unittest tests.test_preflop_sampled_cfr tests.test_preflop_sampled_storage tests.test_preflop_sampled_budget tests.test_preflop_sampled_integration -v
python -m scripts.benchmark_preflop_chance_sampled
```

This samples training in a finite, conditioned heads-up betting abstraction.
It still materializes and ranks every admitted selected world and constructs
the full configured tree. It does not solve unrestricted NLHE, full-deck
preflop, wide unabstracted ranges or multiway equilibrium. Exact finite-game
BR validation is not an exact-decimal betting-equivalence or profitability
claim. More draws or a lower-cost update alone does not prove useful
convergence; compare measured legal deviation gaps at practical costs.
