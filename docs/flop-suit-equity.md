# Fixed-flop equity transfer through global suit symmetry

The opt-in `pokerlab.flop_suit_equity` API transfers prepared integer W/T/L
counts to a target flop and ordered private-hand pairs covered by the source's
joint suit orbits. A single four-suit bijection must map the source board and
both hands together for each target pair. Different target pairs can use
different valid mappings. This transfers counts; target range weights are
normalized afresh, so an arbitrary resulting game need not share the source
game's equilibrium strategy.

```python
from pokerlab.flop_checkdown_equity import prepare_flop_checkdown_equities
from pokerlab.flop_suit_equity import (
    remap_flop_checkdown_equities_by_suit, flop_suit_remap_provenance,
)
from pokerlab.flop_checkdown_solver import solve_prepared_flop_checkdown

source = prepare_flop_checkdown_equities("2c3c4d", "QhJh", "QcQd")
target = remap_flop_checkdown_equities_by_suit(
    source, "2d3d4c", "QsJs", "QcQd",
)
mapping = flop_suit_remap_provenance(source, "2d3d4c", "QsJs", "QcQd")
result = solve_prepared_flop_checkdown(
    target, config={"pot": 6, "effective_stack": 12,
                    "bet_sizes": [.5, 1], "raise_sizes": [.5],
                    "max_raises": 1, "include_all_in": True},
    iterations=1000, algorithm="cfrplus",
)
```

## Exact transfer boundary

A global suit-label bijection preserves card ranks, suit equality, blockers,
best-five hand comparisons and ties. It maps all 52 cards bijectively, hence
also the 45 cards remaining after the fixed flop and compatible private pair.
Each of the 1,980 ordered future deals has one corresponding target deal with
the same showdown result. Their integer counts therefore agree. The source
board, OOP hand and IP hand form one joint canonical key across the 24 possible
suit permutations. Player roles and board ranks stay fixed; independent
per-hand suit normalization would lose relative information and is rejected.

Suit isomorphism is established poker mathematics; see
[Waugh, A Fast and Optimal Hand Isomorphism Algorithm](https://www.cs.cmu.edu/~waugh/publications/isomorphism13.pdf).
This implementation uses a simple exhaustive 24-map joint canonicalization
written for this repository. No external code, binary, table or dependency is
incorporated.

Every target compatible pair must resolve to a covered source orbit. Multiple
source representatives of the same orbit must have identical W/T/L counts;
conflicts reject instead of selecting a count arbitrarily. The source table
remains immutable. Deterministic provenance records both canonical boards,
both role-ordered hand endpoints and the full four-suit bijection. Selection
uses the first matching source pair in table order and the first valid
permutation in the repository's suit order.

The target board and ranges use the existing no-ranking plan. It removes
board-blocked hands, excludes private collisions, computes exact globally
conditioned priors from represented binary64 weights, and retains every
candidate-pair, compatible-pair and board-work cap. Transfer performs no ranking
or future-board enumeration. The prepared solver retains its unchanged
source-inclusive admission and numerical behavior. Structural validation and
orbit consistency do not authenticate caller-supplied physical counts; trusted
source preparation remains required.

The [literal reweighting API](flop-equity-reuse.md) remains restricted to the
source's exact board and covered physical pairs. Suit transfer is separate and
explicit. It covers suit images of known joint configurations, not arbitrary
new flop ranks, suit textures or private hands. On `2c3c4d`, 24 global suit maps
produce 12 distinct board images; the combined board-and-hand images can still
be distinct. All games remain finite heads-up flop betting with hidden forced
future checkdown and the existing pot-share utility convention.

## Planned frozen evidence

The benchmark fixes all 24 suit images of one pair, two eight-hand whole-game
images with changed flop suits, and a two-hand mixed target assembled from one
source pair. It requires independent full-physical-chance policy/BR replay,
exact priors, full-deck mapping provenance, zero warm ranking guards and fixed
admission limits. Whole-game images additionally map serialized labels back to
the published source game and require exact complete numerical-payload parity.
Measurements and acceptance status will be recorded only after a clean source
freeze; unit coverage alone is not benchmark or general solver evidence.
