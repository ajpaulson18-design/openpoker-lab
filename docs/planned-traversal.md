# Planned Python traversal experiment

The recursive full-traversal CFR kernel is the reference. The candidate
`pokerlab.planned_cfr.train` resolves each static world's chance transitions,
terminal payoffs and information-set indexes once per training call. It then
computes values in postorder and reaches in preorder using local arrays. It
preserves simultaneous vanilla/DCFR regret updates, own-reach averages and locks.

Use `solve_turn_river(..., traversal="planned")` to select this optional backend;
`traversal="recursive"` remains the default. Results identify the selected
`execution_backend` and retain the same `postflop-strategy-v1` policy schema.
The historical comparisons below report `configured-turn-river-v2` for both
backends. The current compatible turn facade reports v3 over the shared
postflop engine; its generic API reports `configured-postflop-v1`.

This is Python traversal preparation, not native compilation or chance sampling.
It retains exact worlds and action branches. Terminal callbacks must return
deterministic utilities constant throughout training; chance and key callbacks
must also be deterministic. Plans are never reused across independent calls.
The operation budget defaults to 250,000 decision/terminal plan entries and is
checked during construction. Retained storage scales with worlds times traversed
tree size, so planning can trade memory for runtime rather than improve both.

Adoption requires independent recursive-profile/value/best-response parity,
callback and lock tests, bounded-memory tests, and repeated timings that include
planning cost. The recursive path remains available as a comparison. Reusing an
already-built plan in scratch timing is not the cost of a normal one-shot solve.
Measure traced memory separately, starting before plan construction.

## Whole-API measurements

Four versioned `benchmarks/results/turn-river-v2-*.json` reports use the same
two-fixture configuration, 20/100/300 iterations, three timed calls per row and
a separate traced-memory call. All 24 rows record source revision `f6f46a2` and
six module checksums. These checksums match the committed implementation and
are identical across reports. Uncommitted documentation/reports/scratch files
account for the recorded dirty-worktree flag. Timings include tree construction,
per-call planning, training, exact value/BR calculations and strategy serialization.
Every paired numerical value/gap matched within 1e-12; tree counts matched exactly.

| Fixture, 300 iterations | Algorithm | Recursive seconds | Planned seconds | Runtime ratio |
| --- | --- | ---: | ---: | ---: |
| Full deck, 176 worlds | Vanilla | 5.921 | 4.440 | 1.33x |
| Full deck, 176 worlds | DCFR | 7.332 | 4.295 | 1.71x |
| Conditioned subset, 8 worlds | Vanilla | 0.748 | 0.517 | 1.45x |
| Conditioned subset, 8 worlds | DCFR | 0.802 | 0.877 | 0.91x |

The full-deck vanilla case was also slower with planning at 20 and 100 iterations
(0.783 vs 0.542 seconds; 2.246 vs 2.104 seconds). The conditioned DCFR case was
slower at 300. These shared-machine measurements are noisy, particularly on tiny
cases, and do not establish a universal speedup or production full-range speed.
Recursive traversal therefore remains the default.

Whole-API traced peaks at 300 iterations were about 2.34/2.09 MiB
(recursive/planned) on the full fixture and 296/233 KiB on the conditioned fixture.
A separate preliminary training-only scratch comparison measured higher planned
peak (about 902 to 1,436 KB at ten iterations, excluding the already-built public
tree). Retained plan storage and whole-call peak are different measures; allocation
lifetimes and cyclic GC can affect the latter. Report the mixed, fixture-specific
memory results rather than a general memory-reduction or increase claim.
Tracemalloc excludes process RSS and native allocations.

```text
python -m scripts.benchmark_turn_solver --traversal recursive --algorithm vanilla
python -m scripts.benchmark_turn_solver --traversal planned --algorithm vanilla
python -m scripts.benchmark_turn_solver --traversal recursive --algorithm dcfr
python -m scripts.benchmark_turn_solver --traversal planned --algorithm dcfr
```

Six additional differential tests exercise weighted blocker-conditioned worlds,
both CFR variants at 20/100 iterations, custom chance/key callbacks, nonuniform
locked policies, early operation-budget failure and public API parity. The exact
recursive kernel remains validated against the original independent river and
turn-game mathematical oracles.
The full local suite passed 304 tests, including application/AI Coach regressions,
in 81.433 seconds. GitHub's Python-version matrix validates the final pushed head.

## Design inspiration and subsequent work

Johanson's [2016 thesis](https://poker.cs.ualberta.ca/publications/2016-johanson-phd-thesis.pdf),
sections 2.4 and 3.3, describes walking public states with vectors of private-hand
reaches and values to reuse strategy queries across private worlds. Its best
response maximizes separately for each own information set and sums opponent and
chance branches. This motivates reducing repeated work, while preserving the
information available at each decision. The candidate here still traverses
individual physical worlds; it does not implement that vector algorithm or claim
the paper's measured speedups. Broader ranges and flop solving may require a
public-state/vector representation after this smaller experiment is measured.

No external code, dependency or trained solver output is incorporated. The code
and validation are independently implemented for OpenPoker Lab.
