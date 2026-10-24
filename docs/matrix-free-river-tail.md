# Matrix-free original-weight river tail

`pokerlab.matrix_free_river_tail.solve_matrix_free_river_tail` is a separate
research API for a configured heads-up game on a complete five-card board.
It uses the existing [ranked river payoff kernel](ranked-river.md) and public
CFR+ regret traversals. Private hands remain vectors; compatible joint private
pairs are not materialized as worlds. Existing solver APIs, default choices and
saved quality experiments remain unchanged.

```python
from pokerlab.matrix_free_river_tail import solve_matrix_free_river_tail
from pokerlab.river_config import RiverConfig

result = solve_matrix_free_river_tail(
    "AhKdQcJs2d",
    "AsTc:1,3c4c:0.25,9c9d:0.75,5c6c:0.5",
    "AsKh:0.5,QhTh:0.75,8c8d:0.25,6c7d:1",
    RiverConfig(pot=100, effective_stack=(120, 80), bet_sizes=(0.33,),
                raise_sizes=(0.25,), max_raises=1, include_all_in=True),
    iterations=20,
    discard=5,
)
```

The result uses `research-matrix-free-river-tail-v1` and the established
`postflop-strategy-v1` row schema. The API accepts fixed CFR+ budgets from 10
through 100,000 and an exact integer `0 <= discard < iterations`. It has no
target stopping, alternative training algorithm or implicit change to defaults.

## Averaging contract

Every original sweep `t=1..T` performs OOP then IP regret updates, with clipping
and rematching after each player. After both updates, the completed profile
enters the average only when `t > D`. Its weight is the original `t`.
Each action's numerator is `t * joint_own_hand_marginal * own_sequence_reach *
action_probability`. Opponent reach remains in regret and value traversal.
One globally normalized compatible range-product distribution supplies the
joint hand marginals at every betting node.

Information keys remain `(actor, own_hand_index, public_history)`. They reveal
no opponent holding. Zero-marginal hands have no policy rows; a retained row
with zero total own average reach keeps the existing uniform fallback. Fold,
showdown, tie, all-in and unmatched-contribution refund rules come from the
unchanged configured river tree and ranked terminal kernel.

The result records the source window `[D+1,T]`, `T-D` averaged sweeps, original
weight sum `(T*(T+1)-D*(D+1))//2`, `2*T` executed regret passes, `T-D` executed
averaging passes and `3*T-D` total training traversals. No subtraction of two
independently trained cumulative profiles is used.

## Admission

The original river limits remain: at most 100,000 requested iterations,
30,000,000 modeled hand-state pass operations, 1,000,000 information-set action
slots, 250,000 public states and 30,000,000 ranked fallback pair checks.
Information/action and full-work admission precede strategy-row allocation
and training. The full vector charge is
`max(hand_counts) * public_states * (3*T+3)` regardless of discard. The final
three passes cover profile value and both visible-information best responses.
An input within the iteration ceiling can still exceed another guard.

Rank/card groups supply ordinary terminal payoffs. When cancellation requires
direct compatible-pair scans, the unchanged ranked kernel reserves their work
against its separate dynamic fallback limit before scanning. The result
discloses the actual fallback counter. A cancellation scan is not a retained
joint-world table. Passing the vector guard alone does not guarantee that a
later fallback fits its cap, and these modeled counts are not memory or runtime
bounds.

## Bounded correctness controls

[The dedicated tests](../tests/test_matrix_free_river_tail.py) cover literal
serialized-policy and metric equality with the existing matrix-free CFR+ API
at `D=0`, positive tails against the materialized
[original-weight river adapter](../pokerlab/river_tail_adapter.py), and numeric
physical-world replay plus exact normalized-binary64 response audits in scan
and partition modes. Replay runs while production solve, trainer, tree,
rank and evaluation aliases are disabled. Exact audit caps remain 100,000 work,
depth 64 and 65,536 Fraction bits.

Controls use bounded T=10/20/40 games with blockers, ties, unequal short stacks,
raises, dead hands, identical holdings, both ordinary and cancellation-fallback
payoffs, and a final-sweep-only average. Separate tests reject invalid schedules
before parsing and preserve full requested admission before training, including
the distinction between the 100,000 input ceiling and the vector-work cap.
Concurrent repeated calls retain private state and do not rebind shared trainers.

These controls establish the averaging contract on finite fixtures. They do not
establish improved convergence, speed, allocations, RSS, commercial solver
parity or unrestricted Hold'em quality. No larger-budget quality study is part
of this API change; such a study needs its own frozen protocol, full preflight,
exclusive attempt, raw policy retention and independent replay. Earlier
[held-out misses and tail results](river-heldout-tail-results.md) remain evidence
of their original games and schedules.
