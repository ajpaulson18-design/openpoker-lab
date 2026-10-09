# Turn and river quality initiative

Base: `65c9ba7`, isolated branch `solver/turn-river-quality-20261009`.
The unchanged base passed all 331 tests (65.244 seconds on this Linux host).
No coach, UI, contract, hand-evaluation or flop-tree construction changes are
part of this initiative. Shared dispatch changes are additive and reject the
new options on flop starts; existing vanilla/DCFR defaults remain unchanged.

## Build versus adopt

Primary algorithm sources checked before implementation:

- Tammelin, [Solving Large Imperfect Information Games Using CFR+](https://arxiv.org/abs/1407.5042).
- Burch, Moravcik and Schmid, [Revisiting CFR+ and Alternating Updates](https://arxiv.org/abs/1810.11542).
- Brown and Sandholm, [Solving Imperfect-Information Games via Discounted Regret Minimization](https://arxiv.org/abs/1809.04040).

OpenSpiel's [documented CFR variants](https://github.com/google-deepmind/open_spiel/blob/master/open_spiel/python/algorithms/cfr.py)
were checked as an interface/algorithm reference, without incorporating its
source. Its [license](https://github.com/google-deepmind/open_spiel/blob/master/LICENSE)
is Apache 2.0. Adopting its full game/runtime framework for this bounded change
would add integration and dependency costs; it remains a possible independent
development oracle. The Rust
[postflop-solver license](https://github.com/b-inary/postflop-solver/blob/main/LICENSE)
was fetched directly from GitHub and identifies AGPL v3. No code from that
project is integrated. Proprietary distribution without new copyleft obligations
is a requirement here, so that implementation is not an adoption candidate.
These are dependency decisions, not a legal freedom-to-operate conclusion.

All added algorithms use independently authored standard-library Python code
and this repository's existing game and range representations. Repository
license and visibility are unchanged; no external solver outputs are imported.

## Optional alternating CFR+

`solve_turn_river(..., algorithm="cfrplus", traversal="public-batched")` and
`solve_postflop` on four- or five-card boards add regret matching plus with
alternating OOP-then-IP updates. The generic `cfr_plus.py` callback trainer is
an independent recursive reference. Existing simultaneous algorithms are not
changed. The planned backend does not support the new algorithm.

One outer iteration does:

1. Freeze both policies; aggregate OOP counterfactual regrets across all
   hidden worlds, then clamp cumulative regrets at zero.
2. Recompute OOP's policy; aggregate IP counterfactual regrets against that
   updated OOP policy, then clamp IP's regrets at zero.
3. Recompute the completed profile and accumulate both players' average
   policies once with linear iteration weight and their own reach.

The precise averaging schedule is **post-sweep**, with no averaging delay in
the public API. It is explicit in optional result metadata; no claim that all
published CFR+ implementations choose identical averaging conventions is made.
Clipping per hidden world would change the update and depend on world ordering;
the implementation clips only after complete information-set aggregation.
Chance mass is included once; opponent reach weights regrets, own reach weights
averages. The existing exact information-set BR evaluator remains the reference
quality measure. CFR+ counts three passes in the conservative work guard, so an
equal iteration count is not an equal computational budget.

## Optional public-vector diagnostics

`diagnostics="public-batched"` computes profile value and both exact legal
best responses using sparse joint-hand edges per public prefix. At a responding
player node, maximize each own-hand value after summing compatible hidden
opponent holdings. At opponent nodes propagate that opponent's policy reach;
at public chance nodes sum card branches. The joint mass already includes
physical chance and blockers, so there is no extra marginal or conditional
chance factor. Missing policies for reachable hands are errors.

The option is separate from training backend selection and remains opt-in.
It uses the same 250,000 prefix-edge guard as public training. Default result
shapes remain unchanged; selected diagnostics identify their backend explicitly.
Microbenchmarks do not establish complete-call speedups. Profiling a full-deck
176-world, 100-iteration DCFR turn fixture showed training consuming about 94%
of profiled total time; both generic BRs about 2%. Training therefore remains
the main scaling target.

## Reproducible quality and cost measurements

`benchmarks/turn-river-quality-v1.json` fixes full-deck turn, conditional turn
with unequal stacks and raises, polarised river and weighted raised-river
fixtures. `scripts/benchmark_turn_river_quality.py` rotates algorithm call order,
times complete solves plus JSON serialization, traces separate untimed memory
calls once per fixture/algorithm at explicitly reported `memory_iterations`
(20 by default) and records source/config/harness hashes. Changed source during measurement
invalidates the run. It reports exact NashConv and pot-normalized gaps, rather
than treating a visible frequency match as proof of equilibrium accuracy.

```text
python -m scripts.benchmark_turn_river_quality --output benchmarks/results/turn-river-quality-v1.json
```

Results, final validation and follow-up priorities are appended after controlled
measurement. Small synthetic ranges do not establish full-range performance or
commercial-solver parity. Each reported gap applies only to its finite action
tree and its explicit full-deck or conditional runout game.

## Diagnostics phase measurements

`python -m scripts.benchmark_public_diagnostics --output benchmarks/results/public-diagnostics-v1.json`
completed against the source hashes in that report. Twenty interleaved calls
per backend evaluated the exact same fixed uniform policy; setup/training are
outside these intervals. Separate traced calls include diagnostic allocations.

| Fixture | Worlds | Generic median | Vector median | Generic/vector peak |
| --- | ---: | ---: | ---: | ---: |
| Weighted raised river | 4 | 0.0946 ms | 0.0736 ms | 3,920 / 5,216 bytes |
| Full physical turn, two by four combos | 352 | 17.005 ms | 7.839 ms | 16,176 / 312,896 bytes |

Profile and both BR values differed by at most `3.6e-15`. These phase speedups
(1.29x and 2.17x) trade increased memory for speed, especially on the turn.
They do not establish complete-solve speedups, and fixed uniform profiles are
not equilibrium results. Sparse joint edges are rebuilt for each diagnostic
call; sharing a bounded immutable prefix context with training remains a
possible follow-up if full-call profiling justifies it.

## Target-only CFR+ regret passes

The first CFR+ implementation computed utility vectors for both players in
each alternating pass. The optimized variant computes only the updating
player's vector, carrying only opponent reach. At own nodes use the current
policy's expected child value and action deviations; at opponent nodes sum
branches after multiplying opponent reach by that opponent's policy. The
separate average pass still tracks own reach. The simultaneous backend's
traversal remains intact. Comparison against actual pre-optimization source
`7553734` checks all serialized frequencies and exact value/BR metrics, not
only the final gap.

The initial long tracing experiment was stopped after repeated high-iteration
memory measurements proved costly. Its raw timed observations and source
hashes are retained in `turn-river-quality-initial-partial.json`; it is
explicitly marked incomplete and is not used as a completed benchmark report.

`python -m scripts.benchmark_cfrplus_target --skip-memory --output benchmarks/results/cfrplus-target-v1.json`
completed eight cases (four fixtures at 100/300 iterations), with three rotating
whole-call timed repeats each. Candidate implementation source is captured by
hashes in the report; the old module is loaded from the verified `7553734`
Git blob. The largest probability difference was `5.42e-13`; the largest
value/BR/gap difference was `7.11e-14`, comfortably below `1e-10`.

| Fixture | Iterations | Before | Target-only | Runtime reduction |
| --- | ---: | ---: | ---: | ---: |
| Full physical turn | 100 | 0.9671 s | 0.7195 s | 25.6% |
| Full physical turn | 300 | 2.8879 s | 2.0845 s | 27.8% |
| Conditional raised turn | 300 | 0.3589 s | 0.2697 s | 24.9% |
| Polarised river | 300 | 0.01464 s | 0.01156 s | 21.0% |
| Weighted raised river | 300 | 0.09622 s | 0.07148 s | 25.7% |

These are measured CFR+ execution improvements on synthetic fixtures, not a
change in its mathematical update or a general full-range speed claim. Memory
comparison was explicitly skipped in this controlled before/after report;
no optimization memory-reduction claim is made.

## Algorithm quality report

The completed `benchmarks/results/turn-river-quality-v1.json` contains all 36
rows (four fixtures, three checkpoints, three algorithms), with three timed
repeats per row. Separate whole-call traced peaks were measured once per
fixture/algorithm at **20 iterations**, explicitly distinguished from the
20/100/300-iteration quality and timing measurements.

| Fixture at 300 iterations | Vanilla NashConv | DCFR NashConv | CFR+ NashConv | DCFR / CFR+ time |
| --- | ---: | ---: | ---: | ---: |
| Full physical turn | 1.477155 | 0.021497 | 0.016111 | 1.423 / 2.176 s |
| Conditional raised turn | 3.234919 | 1.811793 | 0.046940 | 0.191 / 0.275 s |
| Polarised river | 2.873615 | 2.294658 | 0.207547 | 0.00737 / 0.01140 s |
| Weighted raised river | 2.919772 | 0.512741 | 0.042113 | 0.05087 / 0.08102 s |

All initial pots are 100 chips. CFR+ gives lower measured gaps in these
fixtures at this checkpoint but takes more time per iteration. DCFR remains
competitive on the full-deck fixture's quality/cost; this report does not
select a universal winner. The conditional turn is the explicitly conditioned
two-river game, not an approximation certificate for the unconditional deck.
Whole-call peaks at 20 iterations were approximately 2.108 MB for the full
turn, 298–300 KB for the conditional turn, 27–28 KB for the polarised river
and 90–91 KB for the raised river. Tracemalloc excludes RSS/native memory.

## Integrated validation

All **352** repository tests passed in **70.236 seconds** on this host:
`python -m unittest discover -s tests -v`. This includes the current Coach and
existing postflop regressions. New checks cover a closed-form Kuhn equilibrium
with exact value `-1/18` and zero best-response gap, independent 64-policy
enumeration per player, trained CFR+ convergence/determinism, hidden-world
regret cancellation before clipping, generator inputs/locks, numerical guards,
public-vector diagnostics against an independent pure-policy oracle, and
turn/river cross-backend integration through weighted raised games.

A separate source-based comparison loaded the original public trainer from
`65c9ba7` and compared it with the final simultaneous path on turn, river and
conditional flop starts for vanilla/DCFR (six cases, 20 iterations). All
serialized frequencies and values/BR/gaps differed by exactly zero. There is
no change to the hand evaluator, so its exhaustive card census was not rerun.

## Remaining priorities and delivery boundary

The existing exact-world/public-tree limits still constrain broad ranges;
this is a finite heads-up action abstraction without rake, preflop or multiway
equilibrium. The new algorithms are library options; the Coach and browser
interfaces were not redesigned. Before selecting a new default, compare
CFR+/DCFR against an equal wall-time budget across substantially broader
representative ranges and require appropriately small measured NashConv.
Prepared reusable prefix/tree contexts and convergence checkpoints are possible
next targets, but only if whole-call profiling demonstrates their value.

The isolated branch is committed locally. Automatic approval review blocked
publication even after the GitHub connector confirmed the repository is public,
the remote matches the user's project, and the account has push permission.
The final rejection requires explicit approval for public disclosure of this
new payload; no alternative publication path was used.
