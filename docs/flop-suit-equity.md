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

## Frozen measured evidence

At clean frozen source `e6af9e41f52eb9438881f9942609bbf593fd3542`, the
[specification](../benchmarks/flop-suit-equity-v1.json) fixes 27 cases: all 24
suit images of `QhJh` versus `QcQd`, two eight-hand whole-game images with
changed flop suits, and a two-pair mixed target assembled from one source pair.
Each trains 4,000 CFR+ iterations in three complete warm calls. All 81 profiles
pass independent ordered-future-deck, best-five numeric-rule policy and own-hand
best-response replay, exact globally conditioned priors, full-deck provenance,
deterministic payloads and zero ranking/enumeration/build guards. The independent
single-pair count anchor is 6 wins, 60 ties and 1,914 losses out of 1,980 ordered
future deals. Its 24 joint images cover 12 distinct flop boards.

| Cases | Compatible pairs per case | Ordered future worlds per case | Independent NashConv, chips | Complete warm-call median, seconds |
| --- | ---: | ---: | ---: | ---: |
| 24 single-pair images | 1 | 1,980 | 0.00000834966 | 1.47835–12.49474 |
| Eight-hand image A | 58 | 114,840 | 0.000104911 | 29.82636 |
| Eight-hand image B | 58 | 114,840 | 0.000104911 | 26.14521 |
| Mixed target | 2 | 3,960 | 0.00000834966 | 3.19387 |

Every profile meets the predeclared `NashConv + 1e-9 <= 0.005` gate and
`1e-10` scalar-agreement tolerance. Both whole-game images inverse-map to the
exact complete numerical payload of the published source game, with only the
prepared-count metadata removed. The mixed target uses priors `2/3` and `1/3`
and different valid source-to-target suit maps; whole-game strategy equivalence
is not asserted for arbitrary mixed transfers. All 27 no-ranking admission
checks finish before cold preparation; the largest modeled work charge remains
129,020,256 under the unchanged 500-million limit.

Timings include remap, provenance, prepared solve and JSON serialization. They
exclude independent verification and the 4.69336-second source preparation.
Single-pair image 13 retains all three observations: 2.46482, **493.74158** and
12.49474 seconds. The large elapsed-time variation is retained without trimming;
its cause was not established. No comparative speedup is claimed by this run.
A separate complete 4,000-iteration image-A call under `tracemalloc` peaks at
**523,805 Python bytes**, takes 251.17780 seconds, and matches the verified
timed payload exactly. This excludes the cached source table, cold preparation,
independent oracle and process RSS. Traced elapsed time is not ordinary runtime.

The [raw report](../benchmarks/results/flop-suit-equity-v1.json) records every
repeat, count, exact prior, mapping, preflight, replay scalar and allocation
guard. Its canonical artifact SHA-256 is
`6b52f050387e2024659025a907d054a65e215d7a429129ba13f18d17dfa2c745`.
It pins the prior source-count Git blob, specification hash and LF-normalized
frozen source hashes. All 854 tests pass in frozen-source GitHub CI on Python
3.11, 3.12 and 3.13. These results establish the stated finite model and suit
images; they do not add later-street betting or arbitrary full-range coverage.
