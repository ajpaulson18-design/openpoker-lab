# Full-board preflop betting with forced checkdown

This separate prepared-table API models finite heads-up preflop betting followed by a hidden full-deck showdown. It supports a small blind/button, a big blind, finite configured raise sizes and a raise cap. Every non-folded closed betting line, including a limp or an all-in call, settles immediately using the prepared full-board win/tie/loss counts. No board card is revealed and no flop, turn or river decision is modeled. The existing shove/fold API and the selected-outcome all-streets solver keep their own scopes.

The solver entry point is `solve_prepared_preflop_checkdown` in `pokerlab.preflop_checkdown_solver`. Callers supply an immutable `FullBoardEquities` table; preparing that table is a separate operation and performs the expensive physical board ranking. The table supports at most four compatible private-hand pairs, each with exactly 1,712,304 unordered final boards and at most three nonzero showdown-sign categories. Its win/tie/loss counts are reused across every terminal line. The table is structurally validated, but that validation alone does not establish where caller-supplied counts came from; use trusted prepared counts and their provenance.

```python
from pokerlab.preflop_full_board_equity import prepare_preflop_equities
from pokerlab.preflop_checkdown_solver import solve_prepared_preflop_checkdown

# Prepare once; this enumerates and ranks full final boards.
table = prepare_preflop_equities("AsAd:1,QsQd:0.5", "AsKh:0.25,KsKd:1")

# Reuse the table for a finite preflop betting solve.
result = solve_prepared_preflop_checkdown(
    table,
    config={"small_blind": 0.5, "big_blind": 1,
            "starting_stack": [4, 3], "raise_sizes": [0.5, 1],
            "max_raises": 2, "include_all_in": True},
    iterations=1000, algorithm="cfrplus",
    resource_model="prepared-counts",
)
```

The button/SB acts first. A limp gives the BB its option to check or raise. Configured pot-fraction raises, reraises, the raise cap and the optional all-in action use the existing preflop betting builder. Short all-ins, effective-stack clipping, unmatched excess refunds and total-contribution action labels retain that builder's behavior. Each raise, including an incomplete all-in, consumes a raise in the cap. A fold settles the existing fold payoff; a call or check that closes betting goes directly to showdown at matched contributions. Histories contain public betting actions only. An information set is keyed by the acting player's own hand and public history, never the opponent's hand or the hidden final-board category.

## Admission and resource models

`solve_prepared_preflop_checkdown` accepts `resource_model="source-inclusive"` by default or the explicit `"prepared-counts"` option. Both validate the table and admit the full requested iteration count before building the betting tree. Both retain a 500,000,000 modeled-loop-entry ceiling, a 10,000 decision-node ceiling, a 250,000 public-state ceiling, a 1,000,000 information-action-slot ceiling, the four-compatible-pair limit and the existing equity-preparation limits. This new API consumes an already prepared table; it does not itself enumerate boards or expose a combined prepare-and-solve entry point.

`source-inclusive` conservatively charges historical source preparation/bookkeeping even if a caller already has a warm table. `prepared-counts` is for a caller that already prepared the table; it charges current validation/setup, training, diagnostics and result bookkeeping without charging the historical ranking preparation again. The work budget records zero current board combinations and rank calls, and preserves historical table-preparation metadata separately. Ranking instructions are excluded from these modeled loop units and are governed by the separate equity-table rank-call and board caps. Neither model is a CPU-time, bytecode-instruction, allocated-memory or RSS guarantee.

Before allocating the tree, the budget computes a conservative configuration-derived forecast. Let `B = len(raise_sizes) + int(include_all_in)` be the maximum number of raise branches per decision. Since each raise consumes one raise-cap level and only the initial SB call can create a same-depth BB option, the builder's decision count is bounded by two geometric roots:

```text
D = 2 * sum(B**k for k = 0..max_raises)
S = 1 + D * (B + 2)
I = compatible_pairs * D
A = I * (B + 2)
```

Here `D`, `S`, `I` and `A` forecast decision nodes, public states, information sets and information-action slots. The state bound allows up to `B + 2` outgoing branches at every decision. Deduplication, stack clipping, closed raise rights and terminal actions can only reduce the constructed tree. A request whose forecast exceeds a structural cap is rejected before tree construction, even if the realized tree might have been smaller. The solver also checks its actual tree and row census against the forecast before training.

The modeled-loop envelope charges `W = 3 * compatible_pairs` category worlds. Training is bounded by `iterations * (32 * W * S * passes + 32 * A)`, where `passes` is three for CFR+ and one for vanilla CFR or DCFR. Diagnostics charge `32 * W * S * 3` for profile evaluation and both exact own-hand best responses. A separate setup term covers bounded table/candidate validation, row and world setup, output normalization and serialization. Source-inclusive mode adds a historical preparation/bookkeeping term; prepared-counts sets that term to zero. These are conservative modeled loop/element envelopes, not counts of machine instructions or a prediction of elapsed time or memory.

## Payoffs, output and independent validation

The result uses `solver_version="preflop-full-checkdown-v1"` and the existing `preflop-strategy-v1` row shape. Strategy rows contain only preflop histories, own hand, legal actions and their probabilities; `revealed_board` is empty. The result includes the exact pair priors as represented fractions, physical-board and category-world counts, constructed-tree census, the selected resource budget, profile value, both best-response values, NashConv and exploitability. Exact diagnostics mean complete evaluation of this finite binary64 game within numeric tolerance; they do not certify exact-decimal arithmetic or an unrestricted Hold'em equilibrium.

The independent validation path reconstructs the legal numeric betting game and replays serialized strategies after exactly renormalizing each binary64 action row as a rational value. It computes profile value and maximizes over legal unilateral responses for each responding private hand, summing over hidden opponent hands and showdown categories before maximizing. It does not use the production betting tree, terminal utility, ranker or best-response implementation as the oracle. For weighted games, the two best responses give an equilibrium-value bracket `[-BR_BB, BR_SB]`; its width is NashConv. These bounds do not imply an exact game value when no separate certificate exists.

## Planned frozen benchmark — evidence pending

The planned specification is [`preflop-full-checkdown-v1.json`](../benchmarks/preflop-full-checkdown-v1.json), with the harness at [`benchmark_preflop_checkdown.py`](../scripts/benchmark_preflop_checkdown.py). The specification selects CFR+ at 100, 1,000 and 3,000 iterations, with three complete final repeats. Its four fixtures cover an AA/KK known-value game, two three-compatible-pair weighted games including a short BB stack, and a four-pair weighted game. The latter reuses three pinned physical count artifacts and derives its fourth pair through a recorded global suit bijection; this benchmark does not perform new physical board enumeration.

Each prepared-counts request must be admitted before any betting tree or training allocation; source-inclusive admission or rejection is recorded as a comparison. The final independent NashConv limit is 0.005 chips. The AA/KK fixture also has a known SB value of +1 chip and a separate 0.005-chip value-error limit. Weighted-game values are reported only as best-response brackets, not as exact value claims. Checkpoints that miss the target remain in the report. A separate Python allocation trace covers a complete prepared solve and JSON serialization; it is not process RSS, and it is not mixed into the timed samples.

For the AA/KK anchor, the signed conditional showdown value is
`u = (1,410,336 - 292,660) / 1,712,304`, with `u < 1 < 3*u`.
At total stacks `[3,3]`, the SB can guarantee +1 by jamming: a BB fold
pays +1, and a call pays `3*u > 1` in expectation. The BB can cap the SB
at +1 by checking after a limp and folding to every SB opening raise.
The SB fold pays -0.5 and the checked limp pays `u < 1`. These legal
strategies give matching lower and upper bounds of +1 for this finite game;
the counts and argument are independent of trained strategy probabilities.

The benchmark's source/spec freeze and execution have not yet been verified. Runtime, allocation, NashConv, value-error, repeated-payload and final-gate results are pending and must be filled from the eventual hash-verified report. No measured performance or convergence result is claimed here.

This is a bounded heads-up preflop betting abstraction with forced hidden full-board checkdown. It does not solve later-street betting, unrestricted no-limit Hold'em, multiway games, antes or rake, and it makes no profitability claim.
