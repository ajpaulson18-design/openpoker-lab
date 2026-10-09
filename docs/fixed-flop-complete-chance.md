# Complete future-card coverage after a fixed flop

This fixture covers every legal future turn/river card pair after `2c3c4d`,
with SB `AsAd` and BB `KsKd`. Removing both hands and the flop leaves 45 cards:
45 possible turns, then 44 rivers, or **1,980 ordered outcomes**. Reversed
turn/river order remains distinct. The preflop adapter builds a complete hand
conditioned on this particular flop, with two-chip starting stacks, no preflop
raises, and the default half-pot/no-raise postflop abstraction. A half-pot flop
wager reaches the remaining one-chip stack, so there is one shove size.

This is complete **future-deck coverage for one fixed flop and private pair**.
It does not enumerate all flops, represent full private ranges, or solve
unconditional full-deck preflop. Conditioning fixes the modeled flop before
preflop play; future turn/river cards remain hidden until their public reveal.
All-in payoffs integrate those same physical worlds.

## A constructive exact equilibrium anchor

Independent best-five enumeration finds 1,782 SB wins, 150 BB wins and 48 ties.
The signed showdown expectation is `(1782-150)/1980 = 136/165`.
After a called flop shove, the SB net payoff is `2 * 136/165 = 272/165` chips.

SB can guarantee at least one chip by completing preflop, then shoving after
a flop check or calling a flop shove: BB folding pays SB +1; either called
shove pays SB `272/165`, exceeding +1 in expectation. BB can cap SB at one
chip by always checking when possible and folding to wagers, adding no chips
beyond the posted one-chip blind. These bounds prove game value **SB +1,
BB -1**. They are fixture-specific, with exact known ranges and this action set.

`known_equilibrium_profile` serializes those rules, including arbitrary legal
check/fold completions for unreachable later rows. Independent numeric-state
replay verifies all rows, both exact legal best responses and zero NashConv.
It also evaluates the learned average profile against this known game value.
No proprietary solver output is a reference.

## Reproduction, measurements and limits

```text
python -m unittest tests.test_preflop_full_flop -v
python -m scripts.benchmark_preflop_full_flop
```

The focused regression passed, including complete physical outcome coverage,
canonical duplicate rejection, visible information-set rows, resource guards,
independent policy/value/BR replay and the constructive equilibrium certificate.
Luna implemented that bounded test and reviewed the fixture-specific proof;
lead work supplied the benchmark, numerical gates, report and merge review.

The [specification](../benchmarks/preflop-full-flop-v1.json) fixes DCFR/planned
training at 10 and 30 iterations, three complete timed calls per checkpoint,
and one separate traced-memory call at **10 iterations**. The
[report](../benchmarks/results/preflop-full-flop-v1.json) records all source and
configuration hashes, exact outcome counts and the constructive-policy replay.
Timing includes construction, training, exact best responses and returned
policy serialization, excluding the oracle. Tracemalloc measures Python
allocations, not RSS; the 10-iteration allocation measurement is not a
30-iteration memory measurement or a memory-scaling claim.

The report freezes source `b77a08f` on Windows/Python 3.12.14. There are
8,106 decisions/information sets and 26,248 public states. Results:

| DCFR / planned checkpoint | Median complete-call seconds | SB value | NashConv | Error from known SB value |
| --- | ---: | ---: | ---: | ---: |
| 10 iterations | 5.896 | 1.005665 | 0.185208 | 0.005665 |
| 30 iterations | 9.562 | 0.992838 | 0.008309 | 0.007162 |

The learned gap decreases; value error need not decrease at each checkpoint.
Every learned scalar agrees with independent replay within `2.23e-16` chips.
The constructive reference profile replays to values/BRs exactly +1/-1 and
zero NashConv. The separate 10-iteration traced peak is **26,226,183 bytes**.
These are shared-machine observations for this fixture. The dirty flag reflects
documentation/report work; measured source/configuration bytes were committed
and unchanged throughout the run.

The final learned gap must improve from 10 iterations and stay below 0.1 chips;
known-value error must also stay below 0.1. These are finite-iteration acceptance
gates for a tiny game, not a general equilibrium guarantee. Scalar replay
agreement remains within 1e-10. Production solver, shared kernel, turn/river,
Coach and browser source are unchanged by this validation milestone. New test
and benchmark code use the standard library; no outside source, dependencies
or trained values were incorporated.
