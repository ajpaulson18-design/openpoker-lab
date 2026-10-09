# Exact private-hand-vector diagnostics for conditioned preflop games

`solve_preflop(..., diagnostics="public-batched")` optionally computes profile
value and both legal best responses with the repository's existing public-tree
private-hand-vector evaluator. Generic recursive diagnostics remain the default
and reference. Training algorithm, learned policy, physical chance mass,
configured monetary rules and `preflop-strategy-v1` action meanings are preserved.

```python
from pokerlab.preflop_solver import solve_preflop

result = solve_preflop(
    "AA,KK,QQ", "JJ,TT,99",
    config={"starting_stack": [4, 3], "raise_sizes": [0.5],
            "max_raises": 1, "include_all_in": False},
    runouts=["2c3c4d7h8h", "Kc2d3h7s8c", "Ac2d3h7s8c"],
    iterations=100, algorithm="dcfr", traversal="public-batched",
    diagnostics="public-batched",
)
print(result["value_sb"], result["nash_conv"])
```

## Information and utility boundaries

Global player identity remains SB=0 and BB=1 through every street. At a
responder's decision, the vector maximum is chosen separately for each own hand
after integrating hidden opponent hands and future outcomes. Public chance
branches reveal only the configured flop, turn or river prefix. This is an exact
legal information-set response to the learned profile in the finite conditioned
game, not a response that knows the opponent's hand or unrevealed cards.

The existing vector evaluator requires a positive initial pot. The adapter
reuses the [positive-pot view](preflop-public-batched.md) with binary anchor `a`,
terminal contributions `c-a`, and evaluator pot `2*a`:

```text
pot/2 + min(c_sb-a, c_bb-a) = min(c_sb, c_bb)
```

It preserves net whole-hand fold/showdown utility, including blind refunds.
No second SB/BB position swap or extra marginal probability factor is applied.
The identity is algebraic; measured binary64 comparisons have explicit
tolerances and do not prove universal exact-decimal equivalence.

When training also uses public vectors, diagnostics reuse its existing view
before that view is released. Other training backends create a separate bounded
view after training. Explicit vector diagnostics on a terminal root create a
one-state view; default terminal handling remains copy-free. Copies are released
in `finally` even if evaluation fails. The original tree remains intact.

The existing 250,000-state copy ceiling and 250,000 prefix/private-pair edge
ceiling still apply. The original tree and one view can coexist; these are
separate bounds, not an aggregate process-memory guarantee. A recursive training
request may fit its own bounds yet fail the optional vector diagnostic edge
guard. All original candidate/world/iteration/work guards remain enforced;
this milestone does not admit full-deck preflop or loosen those limits.
The later explicit [vector resource model](preflop-vector-resources.md) can
replace only the legacy world-decision traversal estimate when both training
and diagnostics use public vectors. Its separate workload and allocation caps
are opt-in; the default admission rules described here remain unchanged.

Optional metadata records `diagnostics_backend="public-batched-python"`, the
view's anchor/state count, its reuse source and the prefix-edge limit. Default
calls retain their previous payload shape. Training-view metadata remains
separate from diagnostic-view metadata.

## Verification and measured scope

Nine integration tests cover all three algorithms, public-view reuse, planned
DCFR with a separate view, weighted asymmetric multi-flop worlds, the configured
fractional monetary boundary, short-blind terminal refunds, invalid choices,
prefix-edge rejection and release after evaluator failure. The hidden-future
anchor has one preflop fold/call choice: legal SB best-response value is zero;
choosing differently after seeing the latent outcome would illegally earn
0.25 chips. That anchor has no live flop decision. Other tests exercise live
flop and later public reveals.

```text
python -m unittest tests.test_preflop_public_diagnostics -v
python -m scripts.benchmark_preflop_public_diagnostics
```

The [specification](../benchmarks/preflop-public-diagnostics-v1.json) compares
recursive and vector diagnostics with identical public-batched DCFR training.
It includes 18 combinations on each side over selected outcomes at 10/100
iterations, and four private pairs with every legal future deal on a fixed flop
at 10 iterations. Every serialized row, independent profile value, both exact
legal responses and joint private-pair probabilities are checked.

All six checkpoints in the [report](../benchmarks/results/preflop-public-diagnostics-v1.json)
passed at frozen source `f9f7bdad5ec4fa9d45a27d149a3b42dbef849b7e` on
Windows/Python 3.12.14. The measured worktree was clean at the start, and all
17 source/configuration hashes remained unchanged through completion. Learned
policy probabilities matched exactly; the largest scalar difference against
independent numeric replay or between diagnostic backends was `7.33e-15` chips.

| Game / iterations | Recursive / vector whole-call median seconds | Recursive / vector traced peak bytes at 10 |
| --- | ---: | ---: |
| 18 vs 18 combinations / 10 | 2.576 / 1.620 | 7,027,963 / 7,028,649 |
| 18 vs 18 combinations / 100 | 15.107 / 14.132 | Not measured at 100 |
| Four private pairs, complete fixed-flop future deck / 10 | 14.179 / 12.036 | 42,883,204 / 42,883,964 |

The selected-outcome range game has 324 compatible private pairs, 864 physical
worlds and 3,438 information sets. Its diagnostic phase medians at 10 iterations
were 1.110/0.209 seconds, with whole-call medians about 1.59 times faster with
vectors. At 100 iterations, training dominated: diagnostic medians were
1.084/0.230 seconds but the whole-call ratio was only 1.07. Raw whole-call samples
vary and overlap at 100 iterations; these observations do not establish a
universal speedup or statistical significance. Its independently checked
NashConv fell from 0.546966 to 0.000622379 chips between the two endpoints.

The complete fixed-flop game has all 7,920 worlds and 17,620 information sets.
Diagnostic phase medians were 2.330/0.960 seconds, with a whole-call ratio of
1.18. Its ten-iteration NashConv remains 0.467452 chips, so full chance coverage
does not certify equilibrium accuracy. It is conditioned on the fixed flop;
it does not enumerate every possible preflop flop.

Timings use three complete calls per backend in alternating order, including
JSON serialization and fixed phase-wrapper overhead. Explicit pre-call garbage
collection and independent replay are excluded. Phase medians need not sum to
the total median. Separate complete, uninstrumented solves plus serialization
under tracemalloc measure Python allocation peaks at **10 iterations only**,
not RSS or hundred-iteration memory. The near-equal peaks do not support a
memory-reduction claim. The shared Windows host and finite fixtures limit
performance conclusions; defaults remain unchanged.

## Implementation provenance

Luna implemented the bounded adapter and regression tests; lead review supplied
the measurement harness, independent replay comparisons and publication checks.
The adapter reuses the independently authored shared `public_diagnostics.py`
without modifying it or the turn/river, training-kernel or AI Coach source.
No third-party source, dependencies, trained policies or commercial solver
outputs were incorporated. The new integration applies the repository's
existing finite-game CFR and exact information-set response formulations;
it does not add chance sampling, abstraction, full-deck preflop or unrestricted
Hold'em equilibrium solving.
