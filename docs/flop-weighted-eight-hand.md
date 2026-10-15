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

The [raw versioned report](../benchmarks/results/flop-weighted-eight-hand-v1.json)
records the frozen fixture, all preflights, source hashes, world and action
coverage, quality results and measurements. Its source revision is
`2c6c8584d007cd2a0d8db0dd916ec132fc95c1c0`, measured on Windows with Python
3.12.14. Reproduce from that recorded source with:

```text
python -m scripts.benchmark_flop_weighted_eight_hand
```

All six requests passed admission before ranking; both final accuracy gates
passed. The independent replay's largest scalar disagreement with production
across timed checkpoints was `3.885780586188048e-16` chips. The table reports
NashConv, which is twice the report's exploitability convention.

| Stack / maximum raises | Iterations | Independent NashConv (chips) | Complete call + JSON seconds | Accuracy gate |
| --- | ---: | ---: | ---: | --- |
| 12 / 1 | 100 | 0.00986943665481 | 4.718384 | Miss |
| 12 / 1 | 1,000 | 0.000195918491829 | 6.148047 | Pass |
| 12 / 1 | 4,000 | 0.0000143935229765 | 12.855162 median of three | Pass |
| 24 / 2 | 100 | 0.0490377242713 | 3.769938 | Miss |
| 24 / 2 | 1,000 | 0.00114882873683 | 6.751501 | Pass |
| 24 / 2 | 4,000 | 0.000104911023367 | 17.885450 median of three | Pass |

The separate full 4,000-iteration traces peaked at 294,858 and 418,715 Python
allocation bytes, respectively. They include the complete solve and JSON
serialization, exclude the independent replay, and do not measure process RSS.
The modeled total work bounds at 4,000 iterations are 80,878,592 and 129,020,256,
below the unchanged 500,000,000 cap. The trees contain 112/176 information sets,
39/63 public states and 25/41 terminal states. Both deeper-tree coverage
witnesses pass with non-all-in targets 3, 9 and 21 at stack 24; legal action
availability does not assert positive equilibrium probability on that line.

The first final serialized policy for each fixture is retained beside the
report, with its exact file SHA-256 recorded there. Repeated final calls and the
allocation call have identical compact policy hashes. The report's canonical
checksum is `4a4256b10949f479053cd03ff4d3ac5ace395de63cc84df6b109980e6b9f35c5`.
Generated policy files are staged outside the checkout until the final source
revision, hashes and clean-worktree check succeed.

After measurement, the publication-order unit test received a mock-isolation
fix: it replaces only the benchmark's subprocess reference, preserving Linux
system-information calls. The report retains the original measured test-file
hash at the frozen revision. Solver, oracle, specification and harness code did
not change after measurement. Six focused tests and documentation checks pass;
the pull request records the final cross-version full-suite CI results.

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
