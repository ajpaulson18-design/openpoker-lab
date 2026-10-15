# Weighted eight-hand fixed-flop checkdown coverage

This benchmark measures a finite heads-up betting game from one fixed flop. It
uses eight weighted private hands per player and every legal ordered turn/river
deal, then forces checkdown. It tests the fixed-flop API's blocker-sensitive
range uncertainty and deeper flop action tree. It does not model preflop,
turn/river betting, multiway play, or unrestricted no-limit Hold'em.

The board is `2c3c4d`. The OOP range is
`AsAd:1,QhJh:0.5,7s6s:0.25,Tc9c:0.75,KsQd:0.375,Ac5c:0.625,8h8d:0.875,ThTs:0.125`.
The IP range is
`KsKd:0.75,AhKh:1,8s7s:0.5,QcQd:0.25,AdJd:0.375,6h5h:0.625,9d8d:0.875,JcTc:0.125`.
The 64 candidate cross-products contain six card collisions, leaving 58
compatible private pairs. Their exact represented input-weight products have
common integer units `oop=[8,4,2,6,3,5,7,1]` and
`ip=[6,8,4,2,3,5,7,1]`; the compatible product total is `1185`. This gives
57,420 unordered final boards and 114,840 ordered physical worlds. Every pair
has 1,980 ordered outcomes. The independent test reconstructs the collisions
and joint prior from these range literals rather than trusting production
range expansion or benchmark counters.

Two action trees are fixed in the specification. Both use pot 6, half-pot and
pot bets, half-pot raises and explicit all-ins. The stack-12 game allows one
raise after the initial bet; the stack-24 game allows two. The latter must
expose a legal bet/raise/re-raise line and a check/bet/check-raise/re-raise
line. Coverage is checked from flop-street rows and complete public histories,
not from action names appearing elsewhere in the result. Eight own hands per
player are required. The independent replay checks serialized strategies,
full hidden-board values and both legal information-set best responses.

The frozen checkpoint matrix is CFR+ at 100, 1,000 and 4,000 iterations. The
100- and 1,000-iteration points have one timed complete call each; the final
point has three timed complete calls and a separate allocation trace at 4,000
iterations. All six fixture/checkpoint preflights must finish before any
ranking or training starts. The harness retains every admission rejection and
quality miss and does not fall back to a smaller game. The final quality gate
is independent NashConv plus `1e-10` at most `0.005` chips; scalar replay
agreement is within `1e-10` chips. Full-call timings include ranking, tree
construction, training, exact diagnostics and JSON serialization. The
separate `tracemalloc` result measures Python allocations, not RSS.

The raw versioned report at `benchmarks/results/flop-weighted-eight-hand-v1.json`
will record the frozen fixture, all preflights, source hashes, world and action
coverage, quality results and measurements. Reproduce from the recorded source
with:

```text
python -m scripts.benchmark_flop_weighted_eight_hand
```

For prior fixed-flop evidence, the [four-hand benchmark](direct-flop-checkdown.md)
covered 15 compatible pairs and 29,700 ordered worlds with two bet sizes, one
raise allowed and full future-board integration. A separate weighted asymmetric
fixture in that report exercised a two-raise tree with five compatible private
pairs. This new fixture uses more private hands and checks its additional action
branch; none of these results covers full ranges or later-street betting.

The command/configuration-file interface documented by
[TexasSolver's console branch](https://github.com/bupticybee/TexasSolver/tree/console)
is conceptual inspiration for explicit action-tree specifications only.
TexasSolver code, binaries, data and results are not reused, and its games and
metrics are not compared with this benchmark.
