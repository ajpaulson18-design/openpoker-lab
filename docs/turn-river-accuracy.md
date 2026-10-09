# Turn and river accuracy-controlled solving

This follow-up starts at main `b7bf525` after preserving the parallel preflop
changes. The Coach, UI, evaluator, betting rules, and earlier-street APIs are
unchanged. New accuracy targets are restricted to turn/river starts using the
public-batched trainer; fixed-iteration behavior remains the default.

## What accuracy means

For the configured zero-sum game, profile value is `v` for OOP and `-v` for IP.
Exact legal best-response values `b0`, `b1` give unilateral gains `b0-v`,
`b1+v`. NashConv is their sum; exploitability is half that sum. We enumerate
the configured joint private hands and public chance outcomes, and maximize
only after aggregating hidden opponent hands at an information set.
"Exact" here means a full-game diagnostic computed with floating-point
arithmetic, not a formal interval-arithmetic proof.

```python
from pokerlab.postflop_solver import solve_postflop

result = solve_postflop(
    "2c7d9hJsKd", "AsAh,3c4c", "QsQh",
    {"pot": 100, "effective_stack": 100, "bet_sizes": [1.0],
     "include_all_in": False},
    iterations=1000, algorithm="cfrplus", traversal="public-batched",
    diagnostics="public-batched", target_exploitability=0.1,
    check_interval=20,
)
```

The target is absolute **chips**, so 0.1 at pot 100 is 0.1% of that pot.
`iterations` is the maximum budget; the result reports completed iterations.
The trainer keeps its regrets and average sums throughout the single solve.
Checkpoints observe independent snapshots after completed updates, at interval
multiples and at the final iteration. Solver checks before iteration ten are
ignored. The iteration cap always receives a final check, including when it
is not divisible by the interval. All existing admission guards still check
the entire requested budget before training; a hoped-for early stop cannot
circumvent them.

`convergence.achieved` is the measured final exploitability, not a boolean.
`stop_reason` is `target-reached` or `iteration-limit`. All checkpoint EV/BR/gap
measurements are retained. Nonfinite metrics or materially invalid BR bounds
raise errors rather than receiving a successful convergence label. Final
metrics reuse the final checkpoint; no extra identical BR calculation is
needed. A target miss returns the actual solution and explicitly reports the
miss. Convergence need not be monotone between checkpoints.

These bounds apply to the configured action tree, ranges, and chance game.
Selected rivers condition the whole joint game; reaching an accuracy target
there does not certify the full deck. Missing bet sizes, rake, multiway play,
and omitted actions are separate modeling errors, unaffected by training
convergence. A low finite-game gap is not unrestricted Hold'em accuracy.

## Independent poker analytical anchors

`scripts/river_analytical.py` independently enumerates the five terminal
histories of a one-bet river game. OOP has nuts with probability `n` and air
otherwise; IP has one bluffcatcher. Either player may bet, with no raises.
For starting pot `P` and bet `B`, in the unsaturated bluff region:

- OOP bets all nuts and air with probability `n/(1-n) * B/(P+B)`.
- IP calls an OOP bet with probability `P/(P+B)` and checks behind a check.
- OOP calls an IP bet with nuts and folds air, including off-path decisions.
- OOP's game value is `(2*n-1)*P/2 + n*B*P/(P+B)`.

The oracle uses exact rational arithmetic and enumerates all 16 OOP and four
IP pure visible-information policies for independent BR values. IP has one
shared policy across hidden OOP holdings. No production tree, terminal utility,
ranking, traversal, or BR function computes the oracle. Six rational anchors
use priors 1/4 and 1/2 and bets 50, 100, 200 into pot 100. Their profile EV,
both BR values, and zero deviation gaps agree with both production diagnostic
backends. Serialized trained Hold'em policies from vanilla, DCFR and CFR+ are
also replayed through the oracle. The equal-prior pot-bet game value is exactly
25 chips; mixed equilibria can have different off-path policies, so tests do
not demand arbitrary frequency identity.

## Measured target stopping

Run `python -m scripts.benchmark_turn_river_accuracy` to reproduce the report
at `benchmarks/results/turn-river-accuracy-v1.json`. It rotates complete-call
timing order, repeats three times, and separately checks policy identity against
a fixed solve at the actual stopped iteration count. Timing excludes JSON
serialization. All starting pots are 100; the target is 0.1 chips.

| Game | Algorithm | Iterations | Final exploitability | Stop result | Fixed-300 / target median time |
| --- | --- | ---: | ---: | --- | ---: |
| Full physical turn | DCFR | 160 | 0.070544 | Reached | 1.83x |
| Full physical turn | CFR+ | 100 | 0.072021 | Reached | 3.09x |
| Conditional raised turn | DCFR | 300 | 0.905897 | Budget miss | 1.00x |
| Conditional raised turn | CFR+ | 160 | 0.082273 | Reached | 1.84x |
| Polarised river | DCFR | 300 | 1.147329 | Budget miss | 0.88x |
| Polarised river | CFR+ | 240 | 0.093274 | Reached | 1.12x |
| Raised river | DCFR | 300 | 0.256370 | Budget miss | 0.96x |
| Raised river | CFR+ | 140 | 0.090889 | Reached | 1.94x |

All eight same-iteration comparisons have zero probability differences.
Target-zero overhead controls, which used the full 300 iterations, varied
from -5.0% to +21.1% versus fixed solving. Timing noise can make an overhead
control appear faster; checks are not a guaranteed speed improvement. Savings
come from avoiding unnecessary iterations when the measured target is reached.
These small synthetic ranges do not establish commercial scale or parity.

## Research and fair external comparison

Primary vendor references were checked on 2026-10-09:

- [PioSOLVER UPI](https://piofiles.com/docs/upi_documentation/) documents
  accuracy-based stopping in chips or pot fractions and reports EV and maximum
  exploitative strategy values. Our threshold feature addresses that practical
  capability; it is not an implementation of Pio's proprietary algorithm.
- [GTO Wizard's benchmark methodology](https://blog.gtowizard.com/gto-wizard-ai-benchmarks/)
  reports river re-solving to 0.1% Nash Distance and comparisons based on best
  counterstrategies. Its updated flop benchmarks are vendor reports, not an
  independent measurement of OpenPoker Lab.
- [GTO Wizard's sizing benchmark summary](https://help.gtowizard.com/accuracy-and-benchmarks/)
  distinguishes dynamic sizing EV retention from full-game exploitability.
  Matching visible frequencies or an EV-retention headline is insufficient.
- [Zhang, McAleer and Sandholm, Hyperparameter Schedules](https://arxiv.org/abs/2404.09097)
  is a possible next algorithm investigation. It is not implemented or validated
  here; schedules must be checked against exact reference updates and measured
  at equal runtime, not assumed superior from the paper's aggregate results.

A defensible comparison must match physical combo weights and blockers, the
whole betting tree with monetary rounding and raise conventions, original pot
and remaining stacks, rake, chance conditioning, and EV ownership conventions.
Our centered utilities add half the initial pot to each player's reported EV
under an initial-pot payout convention; unilateral gains are unchanged by
constant offsets. Compare both unilateral gains, normalized gaps, full-call
time to target, peak memory, and exact input/source/hardware provenance.
Use a legitimately licensed external executable or permitted user-owned export;
no commercial engine or proprietary strategy has been accessed in this session.
No external code or runtime dependency has been incorporated.

## Remaining priorities

`python -m scripts.benchmark_turn_river_scaling` additionally measured six range
sizes across DCFR/CFR+. All twelve calls were admitted. River ranges with
16/64/128 hands per player produced 165/2,627/10,300 compatible worlds and
about 0.18/1.22/4.43 MB traced peak allocation. Full-deck turn ranges with
4/8/16 hands produced 308/1,584/7,260 worlds; the public tree stayed at 2,271
states, while peak allocation increased from about 4.65 to 18.53 MB. These
are low-iteration resource probes, not converged large-range solutions. They
used at most 17.4% of the world-node budget. Full unit tests ran concurrently;
single-call timings are descriptive. The artifact retains exact ranges,
source hashes, counts and guard headroom. All 436 unit tests passed in
114.951 seconds; the analytical oracle also received independent Luna review.

The largest unproven area is commercially representative range/tree coverage.
Exact pair-world storage and repeated sparse-edge terminal scans still scale
poorly. Larger-range resource measurements should guide a blocker-aware ranked
terminal sweep or native kernel decision. A reusable prepared diagnostic context
may reduce checkpoint allocations. Broader randomized independent monetary and
chance replay would strengthen full-game validation. These improvements should
preserve exact full-deck turn chance and label conditioned subsets explicitly.
No current result demonstrates perfection or equivalence to a commercial solver.
