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

This API reuses exact chance marginalization in the existing independently
implemented fixed-flop solver. No external solver code, data or dependency is
incorporated. All decisions occur on the fixed flop, with later cards hidden and
forced to check down. Full private ranges, later-street betting, full-deck
preflop and multiway equilibrium remain outside this finite game. Pot-share
values retain the convention in the [direct solver](direct-flop-checkdown.md).
