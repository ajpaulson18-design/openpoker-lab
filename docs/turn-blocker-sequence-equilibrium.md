# Compact exact turn sequence-form witness

This isolated research lane keeps the production turn/river APIs and the
[legacy exact sequence-form solver](river-sequence-equilibrium.md) unchanged.
It fixes each player's empty realization coordinate to one and removes its
corresponding equality before constructing a bounded exact LP.

## Fixed conditional game

The board is `2c7d9hJs`, with selected rivers `8d` and `Kd`.
OOP has `AsAh:0.25,Th6h:0.75`; IP has `QhQs:1,AdAs:1`.
The pot is 100, added contribution caps are 100 per player, opens are half-pot,
raises are absent, and no additional all-in size is included. The existing
size may still be capped by a stack and labeled all-in.

The shared ace makes OOP AA versus IP AA impossible. The compatible pair
probabilities are AA/QQ 1/7, draw/QQ 3/7, draw/AA 3/7. Each selected river
has half that pair's mass. These are globally conditioned joint probabilities;
products of the conditioned marginal ranges give the wrong game.

The physical public tree has 63 nodes, eight depth levels and 28 decisions.
Each player has 28 information sets, 57 sequences and 29 flow rows. The policy
has 56 own-hand/public-history rows. Future rivers remain hidden until reveal.

The [frozen physical model](../benchmarks/results/turn-blocker-sequence-model-v1.json)
was independently built before candidate search. Uniform policies have exact
value 4175/224, lower response bound -200/7 and upper response bound 400/7.
Its NashConv is 600/7. Independent best-five enumeration checks every showdown.

## Admission and affine reduction

The original LP construction requires 86 rows, 258 columns and 22,533 cells per
side. Its 256-column limit rejects the requested model before dense payoff
allocation or search. The [failure receipt](../benchmarks/results/turn-blocker-sequence-legacy-preflight.json)
and [raw failure](../benchmarks/results/turn-blocker-sequence-legacy-preflight.log)
are retained. None of the legacy admission or arithmetic caps changes.

For the lower LP, fix x0=1 and drop its root equation from Ex=e. The remaining
flow right-hand sides become e[r]-E[r,0]. Each payoff cover uses right-hand
side -A[0,j]. Retain every free opponent-flow coordinate q, including q0.
For the upper LP, fix y0=1, use f[r]-F[r,0], and give each cover right-hand
side A[i,0]. Retain every p coordinate, including p0.

Normalize a negative right-hand side by negating all existing coefficients
before adding a positive artificial basis entry. Both affine payoff shifts
matter even though this poker fixture has a zero empty payoff row/column.
An independently anchored matching-pennies example with nonzero empty terms
checks both signs, value zero, half-half realization plans and full dual
vectors [0,-5/2]. A redundant-flow example checks valid phase-I row removal.

The compact forecast is 85 rows, 256 columns and 22,102 cells per side. Limits
remain 96 rows, 256 columns, 25,000 cells, 512 pivots, 10 million logical cell
updates and 4,096 fraction bits. Cleaned final tableaus may have fewer rows;
initial allocation is reported separately. These counts are not memory or
runtime guarantees.

Acceptance reconstructs the original full realization vectors, both full
flow systems, every original payoff inequality, retained free duals, exact
objectives and complementary slackness. A separate physical tree checker
reconstructs every matrix cell and exact legal best response without importing
the LP candidate, compact helper or exact-policy evaluator.

## Hidden-information controls

The [frozen negative controls](../benchmarks/results/turn-blocker-sequence-hidden-information-v1.json)
show why the information boundary matters. Against uniform policies, legal IP
response gives OOP -200/7; illegally revealing the opponent's hand before its
decisions changes that lower value to -1725/56, an illicit IP gain of 125/56.
Against IP check/call, legal OOP response is 300/7 and illegal future-river
knowledge raises it to 450/7. Factorized conditioned marginals assign 3/49
mass to the impossible AA/AA pair; removing that pair afterward still yields
incorrect compatible probabilities 9/23, 12/23 and 2/23.

## Validation status

The first bounded candidate passed the separate saved-file verifier at exact
value **115/7** and zero NashConv. Both original primal/dual bounds and legal
own-hand physical responses equal 115/7. The complete rational policy, original
full payoff/flow matrices, duals, slacks and 102 terminal entries are saved in
[the witness](../benchmarks/results/turn-blocker-sequence-equilibrium-v1.json).

The lower LP used 185 pivots, 4,196,839 logical cell updates and at most 16
fraction bits; the upper used 245 pivots, 5,543,419 updates and 18 bits. Each
allocated the forecast 85 by 256 tableau (22,102 cells including objective and
RHS). Exact profile replay used 2,485 charged work units at depth eight. All
eight float projection metrics agreed within 7.105427357601002e-15. These
counters describe this fixture only; there is no runtime or memory comparison.

The separate verifier rebuilds the frozen model and hidden-information controls,
checks every original matrix cell and full flow equation, reconstructs both
realizations from the policy, verifies all original inequalities and
complementarity, and computes both legal responses by rational tree recursion.
Saved-file verification never invokes candidate search or the exact-policy
helper. The saved equilibrium reaches river decisions with probability one:
19/35 through turn bet/call and 16/35 through check/bet/call.

Executed validation passed 22 targeted tests in normal Python (9.786 seconds)
and 22 with optimization (9.309 seconds), all five existing/new witness
verifiers and documentation links (119 Markdown files, 513 local links, 12
required entry points). Tests include forged matrices, full realizations,
retained root duals, affine signs, terminal entries, admission metadata,
private/future identities, source drift and publication rollback. The accepted
saved-file test disables candidate LP and exact-evaluator entry points.
Commands: `python -m unittest tests.test_turn_sequence_compact_lp tests.test_turn_blocker_sequence tests.test_verify_turn_blocker_sequence tests.test_turn_blocker_sequence_publication -v`,
the same command with `-O`, the five witness verification modules and
`python -m scripts.validate_docs`.

The initial structural test assumed the independent and candidate flow equations
had identical row ordering. It failed while their full payoff matrices agreed;
comparison was corrected to require the exact same unique equations regardless
of ordering. The model, frozen reference and limits were preserved.

The game remains a finite configured selected-runout abstraction. It does not
solve full-deck turn, unrestricted Hold'em, earlier-street games or multiway
poker. Production CFR, Coach and frontend contracts remain separate.
