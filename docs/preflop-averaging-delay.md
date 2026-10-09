# Delayed CFR+ averaging for preflop games

`solve_preflop(..., algorithm="cfrplus", averaging_delay=d)` optionally delays
strategy averaging while training every sweep. Positive delays work with
recursive or public-batched training; planned CFR+ remains unsupported. Omitted
or explicit `averaging_delay=0` preserves the existing trainer path, learned
policy, admission rules and payload shape. Betting actions, chance mass,
terminal utilities and legal response calculations remain unchanged.

```python
from pokerlab.preflop_solver import solve_preflop

result = solve_preflop(
    "AsAd:1,AhAc:0.25", "KsKd:1,KcKh:0.5",
    config={"starting_stack": [4, 3], "raise_sizes": [0.5],
            "max_raises": 1, "include_all_in": False},
    runouts=["2c3c4d7h8h", "Kc2d3h7s8c", "Ac2d3h7s8c"],
    iterations=20, algorithm="cfrplus", averaging_delay=8,
    traversal="public-batched", diagnostics="public-batched",
    resource_model="public-vector",
)
print(result["nash_conv"], result["averaging_positive_sweeps"])
```

## Method and information boundaries

The weight `max(t-d, 0)` follows section 2 of
[Tammelin's CFR+ paper (2014)](https://arxiv.org/pdf/1407.5042).
The first `d` sweeps receive zero average mass; sweep `d+1` gets weight one.
Regret updates still run through all sweeps. Delay is a parameter, not an
accuracy certificate or guarantee of faster convergence.

The adapter retains its established convention: update player 0, rematch,
update player 1, rematch, then average the completed profile once. It uses the
published delay sequence with that convention, not a verbatim reproduction
of Algorithm 1. Average mass is the row's public-prefix/own-hand physical
marginal times **own action reach**, action probability and iteration weight.
Opponent action reach does not enter average-policy accumulation. Hidden future
cards and opponent hands do not become policy keys.

Recursive requests reuse existing `cfr_plus.train(delay=d)`. Public-vector
requests use a preflop-local orchestration module with unchanged repository
validation, prefix aggregation and target-player delta helpers. Its independent
average-only traversal preserves operation order, dense index holes and missing
rows. Each vector sweep keeps two regret traversals and one average traversal
even when its weight is zero. The recursive average visitor is cleared in
`finally` on success/failure.

`d` must be an exact integer with `0 <= d < iterations`. Booleans, negative,
noninteger, `None` and no-positive-average schedules reject before enumeration.
Positive delays require CFR+. All existing caps remain, including the opt-in
vector resource model's unchanged conservative CFR+ envelope.

Positive results add `averaging_delay`, `averaging_positive_sweeps` and the
delayed schedule description. The vector adapter performs `3*iterations`
traversals; the generic reference skips zero-weight average passes and performs
`3*iterations-d`. Its variable `training_passes_per_iteration` is null. Regret
and average pass counts are separate. No-information-set games report zero
training passes and zero contributing averaging sweeps, preserving blind refunds.

## Independent checks and measured scope

Thirteen new tests cover exact zero-delay vector parity, positive-delay generic
reference parity, weighted hidden chance, hand-derived average chronology,
early rejection, unchanged defaults, independent configured replay, a hidden
future known-value root, terminal refunds and retained guards. The lifetime
test uses plain replacements and clears the captured exception traceback before
requiring immediate weak-reference release **without garbage collection**.
The Python 3.12+ monitoring audit observes actual backend `FOR_ITER` entries
inside the existing structural envelope on a tiny fixture; Python 3.11 skips
that observation. This is a regression audit, not a universal loop/RSS proof.

The known Kuhn anchor uses independent literal terminal-history payoffs and
exhaustive pure-policy best responses. At 2,000 iterations, delays 0/100/500
have NashConv 0.000103724/0.000111013/0.000150283 chips and known-value errors
1.11e-7/1.60e-9/1.20e-8 against exact -1/18. Gates require gap below 0.001 and
value error below 1e-5. These examples show that a longer delay need not reduce
the deviation gap; Kuhn quality does not certify Hold'em equilibrium accuracy.

The [specification](../benchmarks/preflop-averaging-delay-v1.json) fixes 120
iterations and delays 0/20/60 before measurement on the complete four-private-pair
fixed-flop game, with the same 0.001-chip target. All 7,920 worlds, 17,620 policy
rows, both legal best responses and private-pair posteriors are checked
independently. After `2c3c4d`, 2,352 requested public future deals yield 2,336
reachable outcomes. This is conditioned on one fixed flop, not unconditional
preflop. Padded `[-BR_BB, BR_SB]` intervals bound its configured numeric game
value; they are not a universal exact-decimal betting proof.

The [120-iteration report](../benchmarks/results/preflop-averaging-delay-v1.json)
passed every check at source `1240dd0f2635ec0625b1f188bb01349be3121ab8` on
Windows/Python 3.12.14. The worktree began clean; all 19 source hashes, the
configuration hash and prior report hash remained fixed. Maximum scalar disagreement was
`1.61e-14` chips. All 120-iteration targets remain **unmet**:

| Delay / iterations | Independent NashConv chips | Observed complete seconds |
| --- | ---: | ---: |
| 0 / 120 | 0.0024791135 | 171.888 |
| 20 / 120 | 0.0013714425 | 133.444 |
| 60 / 120 | 0.0011859762 | 118.852 |

The endpoint gaps improve with delay on this particular fixture, unlike the
Kuhn examples. Single-call timing differences on the shared host do not
establish a speedup: the vector algorithm still performs 360 traversals.
The separate eight-world/308-information-set selected game's 20-iteration
traced peaks were 721,101 bytes with delay zero and 714,429 with delay eight.
That small difference establishes no general memory reduction.

An [evidence-guided extension](../benchmarks/preflop-averaging-delay-160-v1.json)
then freezes 160 iterations with delays 0/80. It keeps the half-run delay
fraction that improved the earlier gap, the same poker game and 0.001 target,
and every unchanged resource ceiling. Its conservative workload is 490,881,772
entries, below 500 million. This second stage was selected **after** observing
the 120-iteration results; it is not represented as part of the initial
predeclared set. The 120-iteration prior stays an accuracy reference, not a
same-iteration parity assertion or timing/memory comparison at 160.

The report records one complete **uninstrumented** solve plus JSON serialization
per full-flop delay, including resource preflight. Pre-call GC and independent
replay are excluded. Source/configuration/prior report hashes are frozen and
rechecked. The earlier zero-delay report supplies an accuracy cross-check,
not timing/memory comparison. Single observed calls on a shared host are not
medians, equal-time trials, statistical speedup or universal delay superiority.

Separate complete traced calls cover only the small weighted selected-outcome
game at 20 iterations and delays 0/8, including world/tree construction,
training, diagnostics and serialization. Python allocation peaks exclude the
oracle; they do not measure RSS or the full fixed-flop 120-iteration game's
memory. No full-game memory reduction is inferred.

```text
python -m unittest tests.test_preflop_delayed_cfrplus tests.test_preflop_averaging_delay -v
python -m scripts.benchmark_preflop_averaging_delay
python -m scripts.benchmark_preflop_averaging_delay --config benchmarks/preflop-averaging-delay-160-v1.json --output benchmarks/results/preflop-averaging-delay-160-v1.json
```

## Provenance and remaining scope

Luna independently authored the local orchestration/average traversal and
module tests from the published rule and repository interfaces. Lead review
isolated test-owned lifetime retention, strengthened prompt-release testing,
supplied integration, independent replay/Kuhn checks and the frozen benchmark.
Luna reviewed integration and measurement methodology. No third-party source,
dependencies, trained policies, commercial outputs or external implementations
were incorporated. Shared CFR, postflop, turn/river, public-diagnostic and
AI Coach production source remain unchanged.

This remains a finite conditioned heads-up action abstraction. Delayed averages
do not add sampling, wider ranges, all preflop flops, multiway or unrestricted
NLHE solving. Target failures remain failures. The default delay stays zero.
