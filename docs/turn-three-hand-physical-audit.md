# Fixed three-hand TURN physical audit

This separate research auditor extends independent validation to one weighted
three-hand-per-player turn/river game. It adds no solver entry point or training
result. The accepted two-hand proofs, generic exact cap, solver defaults and
earlier-street work retain their original scope.

## Physical model

The turn board is `Js8d4c2h`; OOP has `AsAh:0.5,KsKh:1,QsQh:0.75` and IP has
`AcAd:1,KcKd:0.75,QcQd:0.5`. Both streets use pot 100, stack 220, half-pot bets
and raises, one raise, and `include_all_in=False`. Stack-capped actions still
arise from the configured raise tree; cumulative contributions carry to river
utilities and unmatched wagers are refunded.

All nine private pairs are compatible. Each has 44 legal rivers, producing
396 physical worlds over a union of 48 river cards. Pair masses, in AA/KK/QQ
order for each player, are:

| OOP / IP | AA | KK | QQ |
| --- | ---: | ---: | ---: |
| AA | 8/81 | 6/81 | 4/81 |
| KK | 16/81 | 12/81 | 8/81 |
| QQ | 12/81 | 9/81 | 6/81 |

Each world's original mass is its pair mass divided by 44. Equal pocket pairs
tie on every legal river; a higher pair wins on 42 rivers and loses on two.
The independent numeric-rule ranker checks every physical showdown. A second
best-five implementation in the exact auditor independently checks all signs.
Neither uses production ranking, utilities, evaluation or best responses.

The independent public tree has 3,039 nodes, 1,254 decisions, 1,780 terminals,
five chance nodes with 240 edges, and depth nine. Its canonical structure hash
is `70d87064c6d7048b75784b6623a2dc6249f57ac61384a27d1724c3d53563bd61`.
There are 3,606 legal information rows and 8,046 information-action slots.
Reused models must match the complete physical support, exact masses, signs,
pair summaries, configuration and tree structure, rather than dimensions alone.

## Exact audit and limits

`scripts/turn_three_hand_reference.py` rebuilds this fixed model from independent
numeric rules and constructs the check/call control. Its preflight reserves
nine candidate pairs and 432 pair/river candidates before constructing the
396 legal worlds. Construction performs 792 independent seven-card rank calls.

`scripts/turn_three_hand_exact_oracle.py` audits a supplied complete policy.
It converts each finite binary64 probability to its exact rational value and
normalizes each row by its exact positive sum. Public history, board, actions,
amounts and hand support must match the independent legal tree, including
unreachable information rows. No probability cleanup is applied.

The profile is traversed once per OOP hand. Each response is traversed once per
responding own hand, yielding nine complete public-tree traversals. At a legal
choice, hidden opponent hands remain aggregated; at turn choices, future river
outcomes are integrated before maximizing or minimizing. Original joint masses
are never conditioned again. OOP and IP response gains are reported separately
without clipping, together with value, NashConv and half-gap exploitability.

The following limits are specific to this auditor:

| Resource | Fixed ceiling |
| --- | ---: |
| Full public-tree structural visits | 27,351 |
| Weighted policy-row operations, conservative | 3,610,332 |
| Checked Fraction constructions/arithmetic results | 1,000,000 |
| Fraction numerator or denominator bits | 65,536 |
| Distinct seven-card rank inputs | 276 |
| Independent five-card rank calls | 5,796 |
| Complete policy rows / action slots | 3,606 / 8,046 |

The local rank map is admitted before ranking. Six own hands each have 46
legal river cards; each seven-card input requires 21 five-card subsets. All
396 signs are checked once before terminal evaluation. Exact terminal
magnitudes come from the original pot and matched cumulative contributions.

For any one river, the active tree has 78 nodes, 32 decisions, 72 decision
edges and five chance nodes. Across profile and both responses, this bounds
active world/node visits by 92,664, weighted rows by 38,016, policy-edge
multiplications by 85,536 and terminal world contributions by 48,708.
The Fraction meter covers checked constructions and arithmetic results;
rational comparisons and integer ranking have separate structural bounds.
These are finite work counters, not elapsed-time or resident-memory guarantees.

The old 176-world oracle retains its 18,234 structural and 1,604,592 weighted-row
limits. The generic exact helper retains its 100,000-work cap, which rejected
this larger game's check/call control. Numeric replay retains its independent
8,000,000 work cap; its conservative estimate here is 4,813,776.

## Independent controls

The handwritten check/call policy has these exact metrics:

| Metric | Exact value |
| --- | ---: |
| OOP profile value | -9500/891 |
| IP profile value | 9500/891 |
| OOP best-response value | 6925/891 |
| IP best-response value | 57550/891 |
| OOP response gain | 16425/891 |
| IP response gain | 48050/891 |
| NashConv | 64475/891 |
| Exploitability | 64475/1782 |

A separate closed-form calculation first aggregates signed physical mass by
own hand and visible river. Against a passive opponent, a response can invest
zero or 50 on turn, then zero or `50 + turn investment` on river. It chooses
the river wager after observing that river, and the turn wager after summing
all rivers. This establishes the displayed control values without the generic
tree response engine. It supplies no equilibrium value for the game.

An illegal future-aware calculation instead yields OOP response `875/81` and
IP response `58775/891`, both exceeding the legal responses. Illegally exposing
the opponent's private hand before either choice instead yields `19325/891`
and `67300/891`. These controls distinguish the two information boundaries.
If only IP's
`KcKd` row at `[check,check,river@2c,check]` changes to bet 50, the legal
profile value becomes `-19075/1782`. The change is exactly `-25/594`, retaining
the original one-of-44 river mass and both hidden opposing pair weights.

## Executed validation

All eight integrated tests passed under Python 3.12.14 in normal mode
(32.126 seconds) and optimized mode (32.733 seconds). The tests separately
construct the literal physical law and closed-form legal and illegal responses;
they count the actual 792 reference rank calls and 5,796 exact best-five calls.
Production rank, tree, training, evaluation and response helpers are disabled
during exact checks. Reused-model validation performs no additional ranking.

The check/call, uniform and one-river-deviation controls agree on every exact
metric with independent numeric replay within 1.5e-14, below the unchanged
1e-9 comparison threshold. Their recorded exact-engine counters are:

| Control | Fraction results | Maximum bits | Weighted rows | Adjusted rows |
| --- | ---: | ---: | ---: | ---: |
| Check/call | 72,331 | 16 | 6,336 | 0 |
| Uniform | 232,315 | 55 | 25,344 | 834 |
| One-river deviation | 72,353 | 17 | 6,342 | 0 |

Every control completes 27,351 structural visits. The uniform control reaches
the declared 92,664 active world/node and 48,708 terminal-contribution bounds.
Additional tests reject balanced mass shifts, exchanged signs that preserve
aggregate win/loss totals, duplicate worlds, altered internal stacks/tree,
invalid metadata and policies, and attempts to exceed rank or Fraction work
before the corresponding unchecked operation. A near-unit binary64 root row
has an independently derived exact profile value after normalization.

Run `python -m unittest tests.test_turn_three_hand_physical -v` and repeat with
`python -O`. The preceding long-river, river and TURN saved direct-tail bundles
also replayed on current main with trainers disabled: three tests passed in
34.077 seconds. Documentation validation passed with 151 Markdown files,
763 local links and 12 required entry points. Full repository CI is separate.

No trained policy or quality-target attainment follows from these controls.
The later proposed T=750, discard=250 experiment must separately freeze its
sources, retain its raw policy and every miss of the unchanged 0.001-chip gap
target, and replay all eight metrics with this independently checked auditor.
