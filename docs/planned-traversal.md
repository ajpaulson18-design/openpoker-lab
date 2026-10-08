# Planned Python traversal experiment

The recursive full-traversal CFR kernel is the reference. The candidate
`pokerlab.planned_cfr.train` resolves each static world's chance transitions,
terminal payoffs and information-set indexes once per training call. It then
computes values in postorder and reaches in preorder using local arrays. It
preserves simultaneous vanilla/DCFR regret updates, own-reach averages and locks.

Use `solve_turn_river(..., traversal="planned")` to select this optional backend;
`traversal="recursive"` remains the default. Results identify the selected
`execution_backend` and retain the same `postflop-strategy-v1` policy schema.
The API reports solver version `configured-turn-river-v2` for both backends.

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

The preliminary training-only comparison on the full 176-world fixture showed
roughly 1.4–1.6 times faster training, including per-call planning, for 20/100/300
iterations under both algorithms. Every strategy frequency, expected value and
best-response value matched the recursive path exactly. Traced training peak
rose from approximately 902 KB to 1,436 KB. These are shared-machine scratch
measurements at ten iterations for memory, excluding the already-built public
tree. Final whole-API reports include construction, training, exact gaps and
serialization; their measurements supersede these preliminary timings.

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
