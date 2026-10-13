# Direct flop betting with a complete hidden future deck

`pokerlab.flop_checkdown_solver.solve_flop_checkdown` starts directly on a fixed three-card flop. It optimizes the configured heads-up flop betting tree and integrates every legal turn/river deal under forced checkdown. Future cards never become decision information because there are no later-street decisions. This is a distinct finite game, not a solution to later-street betting or full-deck preflop.

```python
from pokerlab.flop_checkdown_solver import solve_flop_checkdown

result = solve_flop_checkdown(
    "2c3c4d", "AsAd:1,QhJh:.5,7s6s:.25,Tc9c:.75",
    "KsKd:.75,AhKh:1,8s7s:.5,QcQd:.25",
    config={"pot": 6, "effective_stack": 12,
            "bet_sizes": [.5, 1], "raise_sizes": [.5],
            "max_raises": 1, "include_all_in": True},
    iterations=1000, algorithm="cfrplus",
)
print(result["nash_conv"], result["pair_equities"])
```

The config accepts the existing `RiverConfig` value object or its mapping as a reusable single-street betting abstraction. Its name does not imply river cards or river decisions here. Effective stacks are the chips remaining after the existing pot. Values use the existing symmetric pot-share convention: half the initial pot plus matched additional wagers; unmatched excess is refunded. These are zero-sum pot-share values, not whole-hand profit measured from unknown preflop investments. The builder retains its fractional sizes, legal raises, short all-ins and reopening rules; it does not impose a blind-sized minimum opening bet.

The new API supports 10–10,000 fixed iterations of vanilla CFR, DCFR(1.5,0,2), or alternating CFR+. It uses the unchanged public-vector trainer and exact visible-information diagnostics. CFR+ averages completed alternating sweeps with linear own-reach weights and no averaging delay; vanilla/DCFR retain their existing simultaneous update and uniform/quadratic own-reach schedules. No convergence stopping, node locks, sampled estimates, later-street action configs or range inference are exposed by this initial API.

Returned strategies use `postflop-strategy-v1`: own hand, OOP/IP identity, fixed flop board, public action history and legal action probabilities. `pair_equities` exposes the exact integer win/tie/loss counts and each compatible pair's normalized joint prior. `physical_worlds` reports original ordered outcomes, while `training_world_rows` reports categorical sign rows. Both exact legal best responses, profile values, NashConv and exploitability accompany the average strategy.

## Exact chance integration

Range expansion removes flop-blocked hands. Private/private collisions are excluded, and the remaining products of represented binary64 range weights are normalized jointly using `Fraction`. This avoids raw-product underflow; any positive final pair or categorical mass that cannot be represented as a nonzero binary64 value is rejected rather than silently discarded. The meaning is exact arithmetic on the input floats, not exact decimal input semantics.

Each compatible private pair leaves 45 possible turn cards and then 44 rivers: 1,980 ordered deals. Because all future play is checkdown, swapping turn and river cannot change terminal utilities or information. The chance helper evaluates each of 990 unordered final boards once per player and adds two to the corresponding integer sign count. It keeps at most three rows per pair, with mass equal to the exact pair prior times that sign's count/1,980. Signs remain categorical -1/0/+1; no average sign is passed to the shared kernels. Chance groups can replace the original physical worlds exactly for this decision model because all available decisions precede both hidden future cards and terminal utilities are linear in showdown sign.

The AA/KK `2c3c4d` anchor has 1,782 OOP wins, 48 ties and 150 losses. With pot two and one remaining chip per player, OOP shoving and IP folding is a constructive equilibrium with pot-share value +1/-1: the called-showdown OOP expectation exceeds +1, so IP prefers folding. Independent numeric replay verifies a completed legal certificate with zero NashConv as well as learned profiles. This certificate is specific to that single-pair action game.

## Admission

Before ranking, the helper bounds expanded candidate pairs at 4,096, compatible pairs at 128 and unordered board evaluations at 126,720. This admits at most 253,440 ordered physical worlds and 253,440 seven-card rank calls. It retains only range/pair summaries and categorical counts, with no physical-world row list or rank cache.

The solver reserves every tree decision/terminal before expansion under a separate 25,000-state cap and the builder's unchanged 10,000-decision cap. Information-action slots retain the existing 1,000,000 cap, including sparse hand-index holes. Before ranking, it runs the existing independent vector census on a three-row-per-pair structural upper bound. Placeholder rows are for admission exclusively. Full requested iterations and exact final diagnostics are charged, then source bookkeeping is added before the combined 500,000,000 logical loop-entry cap. Source bookkeeping is `128 + 4C + 128P + 64B`, where C is candidate pairs, P compatible pairs and B unordered final boards. Internal ranking instructions are outside that bookkeeping count and are separately bounded by the rank-call ceiling. Logical counts are not bytecode, elapsed time, allocated bytes or RSS guarantees. Other solver APIs and all their old guards remain unchanged.

## Frozen evidence

The [specification](../benchmarks/direct-flop-checkdown-v1.json) fixes three games: the known one-pair anchor, five weighted compatible pairs with asymmetric stacks and two raise levels, and four hands per player with a colliding pair. It requires three complete calls plus JSON at each of 100/1,000/4,000 CFR+ iterations, a separate 10-iteration allocation call, independent scalar agreement within 1e-10, complete deterministic payload equality per checkpoint and final target/improvement gates. The known anchor has an additional fixed 0.0001-chip value-error requirement. Every earlier or short-call target miss remains visible.

The [raw report](../benchmarks/results/direct-flop-checkdown-v1.json) passes every predeclared final acceptance gate. All three independent complete payloads are identical at each checkpoint, and every learned profile agrees with independent full-future values and legal best responses. Maximum scalar disagreement is `8.881784197001252e-16` chips.

| Game | Iterations | Median complete-call + JSON seconds | Independent NashConv | Target |
|---|---:|---:|---:|---|
| known-aa-kk | 100 | 0.110550 | 5.03976865194e-05 | met |
| known-aa-kk | 1,000 | 0.233704 | 5.08508125718e-07 | met |
| known-aa-kk | 4,000 | 0.673939 | 3.18055881632e-08 | met |
| weighted-asymmetric-raises | 100 | 0.637403 | 0.0020221552408 | met |
| weighted-asymmetric-raises | 1,000 | 1.690567 | 6.1791747874e-06 | met |
| weighted-asymmetric-raises | 4,000 | 5.400135 | 3.8648800027e-07 | met |
| four-hands-colliding | 100 | 1.766474 | 0.0104029724251 | miss |
| four-hands-colliding | 1,000 | 3.337453 | 0.000230623571881 | met |
| four-hands-colliding | 4,000 | 9.454790 | 1.68715935844e-05 | met |

The broadest fixture has 15 compatible pairs, 29,700 ordered physical worlds, 42 categorical training rows, 56 information sets and 39 public states. Its 100-iteration target miss remains visible; the 1,000 and 4,000 checkpoints meet the unchanged 0.005-chip target. The final known-AA/KK value error is `3.180557883730728e-08`, within its fixed 0.0001 requirement.

Separate 10-iteration complete-call traced peaks are 23,036 bytes (known anchor), 106,618 bytes (weighted/asymmetric) and 138,872 bytes (four-hand ranges). Their independent NashConv values are 0.004627423944051023,0.04495225041373496 and0.31042287997320694 respectively: all three short allocation profiles miss their targets. These traces do not establish 4,000-iteration memory or RSS bounds.


Input preparation and GC precede measurement. Full calls include ranking, tree construction, all requested training, exact diagnostics and raw JSON. An independent oracle enumerates ordered future deals from its own spelled deck and best-five ranks once per fixture, then independently rebuilds numeric betting rules and replays every measured profile and legal best response. Reusing immutable chance counts avoids identical rank work; no production strategy objects are retained between measured calls. Independent replay follows timing/tracing. Separate 10-iteration Python-traced peaks are not RSS or high-iteration memory evidence. These are measurements of this API on fixed games, not a comparative or general speedup claim.

## Validation and provenance

The 13 focused tests pass: known equity and equilibrium anchors, full-deck numeric replay across all three algorithms, weighted blocker priors, asymmetric raises, refunds, sparse inactive hand indices, hidden future information, invalid options, pre-ranking caps, subnormal normalization, positive-support underflow rejection, and deliberate policy/chance tampering. The complete local suite passed all 629 tests in 350.036 seconds with a unique project-local temporary directory and a successful SQLite probe. Required Python 3.11/3.12/3.13 and presentation CI outcomes are recorded on the final pull request.

Luna independently implemented the bounded chance helper and six tests, and reviewed the lead's solver, numeric oracle and benchmark. Lead implemented orchestration, independent ordered-deck/rule/BR replay, seven integration regressions and the frozen evidence harness, and reviewed the helper. The implementation uses probability marginalization and the repository's existing CFR/action kernels, independently developed without third-party source, dependencies or proprietary solver output. No card-evaluator logic, shared postflop/turn/river kernel, browser presentation or AI Coach source changed.

Frozen source revision: `1db6a6eb1a5c085072e9aa7ef037023fb0bd4146`. 56 source/specification hashes are checked at start/end of measurement. To reproduce from a clean checkout of that revision:

```text
python -m scripts.benchmark_direct_flop_checkdown
```

A failed quality gate saves its full report before returning failure. The finite fixed-flop/checkdown model does not establish unrestricted no-limit Hold'em, later-street betting, full-deck preflop, multiway equilibrium, rake or profitability. The 1e-10 target padding is conservative; it is not a formal floating-point error bound.
