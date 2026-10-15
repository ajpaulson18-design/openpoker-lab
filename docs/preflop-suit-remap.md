# Preflop suit-orbit equity remapping

`remap_preflop_equities_by_suit(table, sb_range, bb_range)` is an explicit,
opt-in API re-exported by `pokerlab.preflop_push_fold`. It constructs a new
`FullBoardEquities` table for requested ranges by transferring already covered
ordered private-pair win/tie/loss counts through a global suit permutation. It
does not change the default literal-pair behavior of
`reweight_preflop_equities`; callers must select suit remapping deliberately.

```python
from pokerlab.preflop_push_fold import (
    prepare_preflop_equities,
    remap_preflop_equities_by_suit,
    solve_prepared_push_fold,
)

source = prepare_preflop_equities("AsAd:1,QsQd:0.5", "AsKh:0.25,KsKd:1")
remapped = remap_preflop_equities_by_suit(
    source, "AcAd:1,QcQd:0.5", "AcKh:0.25,KcKd:1"
)
result = solve_prepared_push_fold(remapped, config={"starting_stack": 2},
                                 iterations=2000, algorithm="cfrplus")
```

The helper `preflop_suit_remap_provenance` in
`pokerlab.preflop_suit_equity` reports each requested SB/BB pair, the source
pair, and the full four-suit mapping used. A remap is accepted only when one
permutation bijects all four suit labels and maps both private hands in order;
SB and BB roles are never exchanged. A source table may contain several
representatives from the same suit orbit only if their W/T/L counts agree.
Every requested compatible pair must resolve to a covered source orbit, or the
operation raises before constructing output rows. The source table is immutable.
Weights retain the exact rational values represented by their input binary64
numbers. The two hand weights are multiplied for each compatible pair, then
all compatible joint masses are normalized together after card collisions are
removed; each player's range is not normalized independently first.

The existing admission ceilings still apply: at most four compatible private
pairs, 6,849,216 physical board evaluations, 13,698,432 rank calls and 12
categorical rows. Suit remapping creates no new ranking work and does not relax
any cap. Those are work-admission bounds, not runtime or memory guarantees.

## Why the transfer preserves counts

A global suit permutation is a bijection of the 52-card deck. It maps the four
private cards to four distinct private cards and induces a one-to-one mapping
between legal five-card boards remaining after those private cards are removed.
Because hand comparison is invariant to suit relabeling, each mapped board has
the same win/tie/loss result as its source board. Thus the ordered pair's exact
integer W/T/L counts and board count are preserved. The implementation checks
that one whole-deck suit bijection maps both source endpoints to the requested
endpoints; it does not independently relabel just one hand or infer similarity
from rank classes.

This is a direct finite symmetry argument. Structural validation and orbit
consistency do not authenticate the source counts or prove they came from
physical board enumeration. The provenance helper records which source row and
bijection were used; it does not establish who produced those counts. The
benchmark obtains its source counts from pinned historical evidence and adds
independent checks. The suit-isomorphism and poker abstraction work of [Waugh (2015)](https://www.cs.cmu.edu/~waugh/publications/isomorphism13.pdf)
and [Gilpin, Sandholm, and Sorensen (2007)](https://cdn.aaai.org/AAAI/2007/AAAI07-008.pdf)
provide conceptual background only. This implementation does not copy their
canonical indexing, abstraction, or solver code: it enumerates the 24 suit
permutations, verifies the ordered pair mapping, and reuses an existing count
row.

## Split-AK example

The frozen split fixture uses SB `AsAd:1,QsQd:0.5` and BB
`AsKh:0.125,AsKc:0.125,KsKd:1`. Swapping hearts and clubs fixes `AsAd`,
`QsQd`, and `KsKd`, and maps the complete ordered pair `QsQd|AsKh` to
`QsQd|AsKc`. The two AK pair rows therefore have identical verified counts.

After removing card collisions, the four compatible prior masses before
normalization are:

| SB hand | BB hand | Joint mass | Normalized prior |
| --- | --- | ---: | ---: |
| `AsAd` | `KsKd` | 1 | 8/13 |
| `QsQd` | `AsKh` | 1/16 | 1/26 |
| `QsQd` | `AsKc` | 1/16 | 1/26 |
| `QsQd` | `KsKd` | 1/2 | 4/13 |

The total compatible mass is 13/8. `AsAd` collides with both AK hands, so those
deals are omitted before the global normalization. The split game has four
compatible private pairs and three active BB hands. Its 4-by-8 complete
pure-policy matrix has the same exact game value as the original fixture; the
certified policy retains the same QQ shove and KK call frequencies and calls
with each AK hand. The known SB value is `256757651065/457587630786` chips for
the configured matched effective stack.

The separate bounded witness helper in
`scripts/preflop_push_fold_equilibrium.py` supports at most three active hands
on one side and two on the other. It searches equal-cardinality supports in a
4-by-8 or 8-by-4 matrix, at most 494 support pairs. This is not a complete
linear-programming algorithm: it may report no witness for a game whose
equilibrium requires unequal support sizes or a singular support representation.
A returned witness is exact and is checked against every pure complete
hand-contingent policy deviation, so the limitation can cause a missed
certificate but not an unchecked one.

## Validation scope and benchmark

The frozen configuration is
[`preflop-suit-remap-v1.json`](../benchmarks/preflop-suit-remap-v1.json). The
benchmark harness uses the historical physical count evidence pinned to source
revision `4650d6591c88c25f1a04c28fcf4960efc6ec33de` and the reweight benchmark's
five pinned historical Git blobs. It checks 25 cases: all 24 global suit images
of the original fixture and the split-AK game. Each case runs three complete
warm solve calls at 2,000 CFR+ iterations; the harness also checks the reported
source-to-target mappings, independent serialized-policy replay and exact
normal-form witness. Production rank and board-enumeration entry points are
patched to fail during measured calls.

The four-pair game is refused at 3,000 iterations by the existing 500-million
modeled-loop guard. The declared 2,000-iteration fixture fits that unchanged
guard; it keeps the same accuracy gates. Admission is a conservative requested
work model that still charges source preparation when counts are reused.

Separately, an independent 16-card toy-deck check enumerates all 792 legal
boards for one private-pair deal and verifies all 24 suit images, for 19,008
mapped-board comparisons. It uses the separate numeric-rule oracle in
`scripts/preflop_validation.py`. This exhaustive toy check demonstrates the
bijection on its declared toy deck; it is not a fresh 52-card enumeration or a
replacement for the historical physical full-board counts.

The [verified report](../benchmarks/results/preflop-suit-remap-v1.json) passes
both fixed 0.005-chip gates for all 25 fixtures at frozen source
`695dd35eec4439efec214afb3d15ce9578f37295` on Python 3.12.14 / Windows 10.
Its working tree was clean; all 20 source/config hashes stayed unchanged.
The 24 images check 72 ordered pair transfers, and the split game checks four,
for 76 checked source/target mappings in total. The toy oracle gives
W/T/L `(540, 4, 248)` on every image of its 792-board deal. These toy counts
are distinct from the reused physical 52-card counts.

| Fixture | Exploitability (chips) | Known-value error (chips) | Median complete warm call (seconds) |
| --- | ---: | ---: | ---: |
| Each of 24 global suit images | 1.46360565e-5 | 4.20180701e-9 | 0.653009–1.104554 |
| Four pairs, three BB hands | 1.46360565e-5 | 4.20180701e-9 | 1.214929 |

Every exact matrix witness has the known rational value and passes all pure
unilateral-deviation inequalities. Independent replay of the serialized witness
leaves at most 1.239e-17 chips of NashConv due to frequency conversion.
Maximum production/replay scalar disagreement is 1.324e-16 chips. All three
repeated payloads are identical within each fixture, and the source table is
unchanged. The four-pair 2,000-iteration request charges 493,147,312 modeled
loop entries under the unchanged 500-million cap.

A separate complete split-game warm allocation trace peaks at 32,758 Python
bytes. Timings include remapping, training, production exact diagnostics and
JSON; independent toy enumeration, witness search and replay run outside them.
The trace excludes the prebuilt source table, original full-board preparation,
historical-file loading and RSS. The cases reuse historical source counts and
are fixture-specific; they establish no cold-call speedup, full-range result
or accuracy for missing betting actions.

The local full suite passed 814 tests in 536.646 seconds. A metadata-only
orientation correction was also checked with all 13 witness tests; it does not
change the calculation. GitHub runs the final source on Python 3.11/3.12/3.13
plus frontend/documentation contracts. Luna implemented and reviewed the
bounded core, independent witness and toy proof; the lead reviewed integration
and ran focused tests, the full suite and the frozen benchmark.

Suit remapping is standard-library code in this repository. The source papers
are cited as background only; no third-party implementation or solver output is
incorporated. This provenance statement is not legal advice or patent
clearance.
