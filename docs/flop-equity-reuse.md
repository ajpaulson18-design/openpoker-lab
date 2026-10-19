# Reusable exact fixed-flop checkdown equity counts

The additive `pokerlab.flop_checkdown_equity` API prepares immutable ordered
win/tie/loss counts for a fixed three-card flop. Those counts can serve repeated
betting configurations, iterations and algorithms, or new weights and covered
private-pair subsets. The existing `solve_flop_checkdown` signature, default
behavior and result payload remain unchanged.

```python
from pokerlab.flop_checkdown_equity import (
    prepare_flop_checkdown_equities, reweight_flop_checkdown_equities,
)
from pokerlab.flop_checkdown_solver import solve_prepared_flop_checkdown

table = prepare_flop_checkdown_equities(
    "2c3c4d", "AsAd:1,QsQd:.5", "KsKd:1,AhKh:.25",
)
changed = reweight_flop_checkdown_equities(
    table, "QsQd:.75,AsAd:.25", "AhKh:.5,KsKd:1",
)
result = solve_prepared_flop_checkdown(
    changed, config={"pot": 6, "effective_stack": 12,
                     "bet_sizes": [.5, 1], "raise_sizes": [.5],
                     "max_raises": 1, "include_all_in": True},
    iterations=1000, algorithm="cfrplus",
)
```

Preparation uses the existing exact bounded ranking path: each compatible pair
has 990 unordered final boards, counted twice to represent all 1,980 ordered
future deals. The frozen table stores canonical board and hand tuples, exact
`Fraction` joint priors, integer outcome-count tuples and immutable budget
items. Its budget property and built worlds/count dictionaries are fresh copies.
Structural validation rejects malformed cards, board collisions, omitted or
duplicated compatible pairs, invalid counts, unsupported positive masses and
inconsistent resource metadata before a prepared solve allocates its action tree.
Validation cannot authenticate a fully consistent caller-supplied count table;
retain trusted preparation provenance.

Reweighting expands ranges with the existing grammar, removes board-blocked
hands, excludes private-card collisions and normalizes represented binary64
weight products globally with exact rational arithmetic. Every compatible target
pair must have literal source counts for the same OOP hand, IP hand and fixed
board. Reordering and subsets are supported. A new hand entirely blocked by the
board or all opposing hands can contribute no requested pair; a new compatible
pair is rejected. There is no suit transfer or player-role swap. Positive masses
that underflow binary64 are rejected rather than losing chance support.

The prepared solve reuses the same tree builder, trainer, diagnostics and result
schema. It adds `equity_preparation` metadata identifying zero current rank
calls and zero current board evaluations. Its work admission intentionally keeps
the same conservative source-inclusive bound as an ordinary solve; this slice
does not relax any candidate-pair, compatible-pair, board, tree, action-slot or
500-million modeled-work cap. The input table's original preparation is separate
work. Logical counts are not CPU time, allocation or RSS guarantees.

The benchmark specification fixes fresh-versus-prepared comparisons with the
[eight-hand matrix](flop-weighted-eight-hand.md), changed weights and a covered
subset. It compares the complete serialized numerical payload after removing
only the prepared-call metadata, forbids ranking and board enumeration in warm
calls, and independently replays physical chance, policy values and both legal
information-set best responses. Cold preparation, fresh complete calls and warm
reweight-plus-solve calls are measured separately. Final evidence is recorded
only after a clean source freeze; an implementation or test pass alone is not a
measured speedup.

## Frozen evidence

The [versioned report](../benchmarks/results/flop-equity-reuse-v1.json) records
source `9af1e75ae57f5bcf0c0e7b8d30e388bc2038e5bc`, Python 3.12.14 on Windows,
all four no-ranking preflights, 64 source hashes normalized to LF, and the
complete measurement matrix. Cold preparation took 5.002074 seconds for 58
compatible pairs, 57,420 unordered boards and 114,840 ordered future worlds.
Every integer W/T/L row matches both the independent oracle and the published
PR #130 report, pinned by Git blob `610ac4e8d272db495936119c60f731b7a1061032`.

Each row below has three complete fresh calls and three warm calls including
reweighting, tree construction, all 4,000 CFR+ iterations, exact diagnostics and
JSON serialization. The call order alternates between fresh/prepared and
prepared/fresh. Independent replay occurs outside the timed intervals. Source
preparation is excluded from warm calls and must be paid before reuse.

| Game | Fresh median seconds | Prepared median seconds | Median reduction | Independent NashConv (chips) |
| --- | ---: | ---: | ---: | ---: |
| Eight hands each, stack 12, one raise | 15.110667 | 10.212896 | 32.4% | 0.0000143935229765 |
| Eight hands each, stack 24, two raises | 20.208847 | 16.960834 | 16.1% | 0.000104911023367 |
| Reversed weights, stack 24, two raises | 22.473929 | 17.194747 | 23.5% | 0.0000422279060091 |
| Four-hand covered subset, stack 12, one raise | 5.926263 | 5.048768 | 14.8% | 0.0000168715935844 |

All 24 timed profiles meet independent NashConv plus `1e-9` at most `0.005`
chips. Their largest scalar disagreement is `4.440892098500626e-16` chips. Every
prepared call has exact complete numerical-payload equality with its fresh
counterpart after removing only `equity_preparation`; repeated payload hashes
are deterministic. Ranking, board-combination enumeration and source-plan build
guards all remain zero. Actual work budgets match their no-ranking preflights.
The reversed weights have exact compatible product total `1195/64`, rather than
the original `1185/64`; the covered subset has total `49/8` and 15 pairs.
These runtime reductions apply to these four measured games, not general solver
performance or full private ranges.

The separate full 4,000-iteration warm trace for the eight-hand stack-24 game
peaked at 418,997 Python allocation bytes. It includes reweighting, prepared
solving and complete JSON, excludes the already prepared source table, cold
preparation and independent oracle, and does not measure RSS. Its numerical
payload hash equals the independently verified timed profile. Its raw elapsed
17,910.517 seconds is retained in the report: the call spanned a Windows-recorded
host sleep from `2026-10-15T22:30:22.5058677Z` to
`2026-10-16T00:25:27.7100744Z`. This trace is allocation evidence, not an ordinary
runtime observation or a comparative fresh-call memory measurement. The timed
matrix above completed before the trace.

The canonical report checksum is
`963c2e0a2c39b2f64cbeb2b73713739f33b5b1b4bd2d419affa3c766ec2981f0`.
Reproduce from a clean checkout of the frozen source with:

```text
python -m scripts.benchmark_flop_equity_reuse
```

All 33 local focused flop tests and documentation validation pass. Default and
prepared results exactly match pre-change weighted vanilla/DCFR/CFR+ payloads,
with independent replay. Full-suite GitHub CI runs all 843 tests on Python 3.11,
3.12 and 3.13; all three pass at the frozen source. The final pull request
records checks for the evidence/documentation commit as well.

This API reuses exact chance marginalization in the existing independently
implemented fixed-flop solver. No external solver code, data or dependency is
incorporated. All decisions occur on the fixed flop, with later cards hidden and
forced to check down. Full private ranges, later-street betting, full-deck
preflop and multiway equilibrium remain outside this finite game. Pot-share
values retain the convention in the [direct solver](direct-flop-checkdown.md).

Explicit prepared calls may select `training_backend="native"` with a separately
source-built helper and `build_directory`. The Python default and its payload
remain unchanged. See [native training](native-fixed-street.md) for the distinct
work/storage admission, supported information boundary and actual evidence.
