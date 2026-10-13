# Bounded vector work and complete fixed-flop convergence

`solve_preflop(..., resource_model="public-vector")` optionally admits a game
using a structural private-hand-vector workload model instead of the legacy
world-times-decision traversal estimate. It requires both
`traversal="public-batched"` and `diagnostics="public-batched"`. The default
`resource_model="world"`, its result shape and its admission rules are unchanged.
This is a resource-accounting change; it does not change policies, utilities,
chance probabilities, betting rules, training algorithms or legal responses.

```python
from itertools import permutations
from pokerlab.preflop_solver import solve_preflop

flop = ("2c", "3c", "4d")
deck = [rank + suit for rank in "23456789TJQKA" for suit in "cdhs"
        if rank + suit not in flop]
result = solve_preflop(
    "AsAd,QsQd", "KsKd,JhJc",
    config={"starting_stack": 2, "max_raises": 0, "include_all_in": False},
    runouts=[flop + future for future in permutations(deck, 2)],
    iterations=350, algorithm="dcfr", traversal="public-batched",
    diagnostics="public-batched", resource_model="public-vector",
)
print(result["nash_conv"], result["vector_work_budget"])
```

## Admission model and remaining bounds

The legacy guard charges every hidden physical world at every decision on its
path for each iteration. Public vectors share public traversal and fold/showdown
work across private hands, so that estimate can reject useful bounded requests.
The new estimator independently walks the original public tree and counts dense
hand dimensions, repeated terminal-prefix edges, actions, chance branches and
information-set rows. It never invokes the trainer or evaluator to estimate work.

The versioned envelope charges aggregation, row setup and normalization,
regret matching/updates, training and three diagnostic traversals. CFR+ charges
two target-player sweeps, an average-only sweep, rematches and positive-regret
updates. A terminal game without information sets has zero training work and
one diagnostic aggregation. Missing diagnostic policy rows include dense fallback
and uniform-policy construction. Dense dimensions use maximum hand index plus
one, including holes and asymmetric ranges.

New mode caps are 250,000 prefix/private-pair edges, 2,000,000 dense prefix slots,
1,000,000 information-set action slots and 500,000,000 modeled loop entries.
Prefix and dense-slot capacity is reserved before a new census row is inserted;
action capacity is checked before new information-set metadata is inserted.
The final workload check runs before a positive-pot view or vector trainer is
allocated. Temporary recursive census references are released on success/error.
The fixed ceilings bound this opt-in model; they are not fitted accuracy targets.

The per-node full-visitor envelope uses `H` own hands, `J` opponent hands,
`Hsum=H+J`, `A` actions, `B` chance branches and `E` terminal-prefix edges:

| Node | Modeled full-visitor entries |
| --- | ---: |
| Chance | `8 + Hsum + B*(Hsum+4)` |
| Terminal | `8 + Hsum + 2*E` |
| Decision | `8 + 6*H + 3*J + A*(4*H+J+4)` |

Average-only envelopes are `4+2*B`, `4`, and `4+2*H+A*(2*H+4)` respectively.
The source records the remaining row and aggregation terms separately. These
are conservative structural loop/allocation envelopes for the current vector
implementations, not exact bytecode counts, timing predictions or RSS bounds.
Changes to those implementations require reviewing this versioned model.

Candidate/world/iteration, selected-outcome, ranking preflight, public-state,
decision, transient-template and positive-pot-copy guards remain enforced.
World enumeration and tree construction use those independent guards, outside
the new traversal envelope. No full-deck preflop request becomes supported.
The result retains `world_decision_work` as reference evidence, marks
`world_decision_work_enforced=false`, and puts its old ceiling under
`limits.reference_world_decision_work`; `limits.world_decision_work` is null.

## Independent checks and measurement scope

Eight estimator tests exercise known counts, repeated prefixes, dense index
holes, asymmetric dimensions, caps, terminal games, invalid inputs and prompt
closure release. One observes actual backend `FOR_ITER` entries on an asymmetric
synthetic tree for all three algorithms using Python 3.12+ `sys.monitoring`;
Python 3.11 skips that observation only. The observed work stays inside the
modeled envelope on that fixture. This is a regression audit, not an exhaustive
proof for arbitrary programs or an instruction-count benchmark.

Six integration tests check unchanged default output and learned policies,
independent configured replay for all three algorithms, explicit replacement
of the legacy guard, early new-cap failures, unsupported combinations, retained
original guards and no-training blind refunds. The final focused run including
existing vector integration tests passed 28 tests.

The [specification](../benchmarks/preflop-vector-resources-v1.json) fixes the
accuracy target at 0.001 chips before measuring DCFR at 100/350 iterations and
CFR+ at 120. The fixture has four equally weighted compatible private pairs,
2,352 requested public future deals, 2,336 reachable future deals and all 7,920
physical worlds after the fixed flop. It contains 30,920 public states, 9,546
decisions and 17,620 information sets. Future cards and opponent hands remain
hidden until the appropriate public reveal or showdown. This is conditioned on
one fixed flop, not every possible preflop flop.

The legacy model admits DCFR100 but rejects DCFR350 and CFR+120 before training.
The new estimates for the latter are 455,782,662 and 369,074,932 entries under
the unchanged 500-million ceiling. The harness confirms both old rejections,
independently replays every serialized information set and both exact legal
best responses, checks private-pair posteriors, and records a numerically padded
zero-sum value interval `[-BR_BB, BR_SB]`. That interval bounds the finite-game
value; it does not import the earlier single-private-pair game's +1/-1 value.

The versioned report records the frozen source revision, source/configuration
hashes, historical ten-iteration report hash, measured calls and target booleans.
The historical report is a frozen prior accuracy checkpoint, not a new timing
or memory comparison. Source/configuration/baseline hashes are checked again
before the report is written.

All three checkpoints in the
[report](../benchmarks/results/preflop-vector-resources-v1.json) passed independent
configured replay at frozen source `b8fe3028ea22012e9bc809fb4502f26e88ffc6bf`
on Windows/Python 3.12.14. The worktree was clean when measurement began;
all 18 source hashes, configuration and historical report hashes stayed fixed.
The maximum scalar disagreement was `1.67e-14` chips. All 17,620 policy rows
and all four private-pair probabilities were checked at each checkpoint.

| Method / iterations | Independent NashConv chips | Padded SB game-value interval | Observed complete seconds | Preflight traced peak bytes |
| --- | ---: | --- | ---: | ---: |
| DCFR / 100 | 0.0254527752 | [0.5104706903, 0.5359234657] | 78.348 | 2,020,471 |
| DCFR / 350 | 0.0079080216 | [0.5141574960, 0.5220655178] | 283.792 | 2,019,576 |
| CFR+ / 120 | 0.0024791135 | [0.5176154594, 0.5200945731] | 135.961 | 2,019,576 |

The intervals include `1e-10` outward numerical padding at each end; table
rounding is for display, while the report preserves the computed endpoints.
Preflight tracing took 2.187, 2.788 and 2.347 seconds respectively. The fixed
0.001-chip target is **unmet at every checkpoint**. CFR+ has the smallest
observed endpoint gap on this game, unlike the earlier selected-outcome examples
where DCFR won at 100 iterations. These sparse endpoints and single-call costs
do not establish monotonic convergence, universal method superiority or an
equal-time comparison. The next accuracy work must use measured legal gaps
rather than infer convergence from full chance coverage or higher iteration counts.

Each timing is one complete call including JSON serialization and **preflight
allocation tracing**. Independent replay and pre-call garbage collection are
excluded. These are observed costs, not uninstrumented medians, statistical
speedup evidence or a controlled backend comparison. Memory tracing covers
only the estimator after worlds/tree/infos exist; it excludes their allocation,
subsequent training/diagnostics/serialization and RSS. It establishes neither
a high-iteration whole-call peak nor a process-memory guarantee.

```text
python -m unittest tests.test_preflop_vector_budget tests.test_preflop_vector_resources tests.test_preflop_public_diagnostics tests.test_preflop_public_batched -v
python -m scripts.benchmark_preflop_vector_resources
```

## Provenance and limits

Luna authored the bounded census and estimator regressions. Lead review derived
the per-node envelope, corrected reservation/fallback details, integrated the
opt-in mode and supplied independent replay tests and the frozen benchmark.
Luna completed a read-only review of the final integration and measurement
claims. No third-party source, dependencies, solver policies or commercial
outputs were incorporated. The shared training/diagnostic kernels, postflop,
turn/river and AI Coach production source remain unchanged.

This milestone measures convergence in a finite conditioned heads-up game with
restricted ranges and actions. A low legal deviation gap does not certify an
unrestricted NLHE strategy, wider ranges, other flops or exact-decimal betting
equivalence. An unmet target remains recorded as unmet.
