# Full physical AA-versus-KK preflop validation

This [frozen experiment](../benchmarks/preflop-aa-kk-physical-range-v1.json)
uses every AA private combination against every KK private combination: six
hands per player, 36 compatible pairs and 61,642,944 represented final boards.
The three [independently checked suit classes](preflop-five-card-reference.md)
cover every target pair through one joint global suit bijection. There is no
new ranking/enumeration and no independent rescaling of the two players' suits.
All private combinations and exact `1/36` pair priors remain separate.

The game has blinds 0.5/1, stacks 3/3, two configured raise sizes, a two-raise
cap, limps, the BB option, all-ins and refunds. Every closed nonfolded line
forces hidden full-board checkdown. This is not a general starting-range,
later-street or multiway result.

## Constructive exact value independent of training

[`preflop_aa_kk_reference.py`](../scripts/preflop_aa_kk_reference.py) first
rechecks the published full source report and raw candidate/reference count
agreement. It maps all 36 ordered pairs and checks the suit-class census
`6 / 24 / 6` for zero/one/two shared suits. For each physical pair the exact
conditional signed showdown mean `u` satisfies `1/3 < u < 1`.

A separate numeric legal-tree builder validates both complete-game bounds:

- SB shoves at the root for every own AA hand. BB can fold (SB earns +1) or
  call for three matched chips (SB earns `3u > 1`). This guarantees at least +1.
- BB checks after every limp and folds to every SB opening raise. SB can fold
  (earning -0.5), limp and check down (earning `u < 1`), or raise (earning +1).
  This caps SB at +1 against any unilateral strategy.

Both strategies use only own hand/public history. The bounds agree at exactly
**+1 chip SB net transfer** for this finite game. Unreached response branches
may use arbitrary normalized legal actions. These are explicit admissible
bounds, not a trained value, an LP search or a claim about other ranges/stacks.

## Frozen trainer comparison

The [runner](../scripts/benchmark_preflop_aa_kk_range.py) uses the existing
covered-table solver and explicit pair-mean indexing in Python/native modes.
It checks the constructive witness and all three full requested admissions
before native build lookup or training. Existing preparation, public-state,
action-slot, work and native limits remain unchanged. Direct ordinary
`prepare_preflop_equities('AA','KK')` still rejects its four-pair limit.

CFR+ checkpoints are 10, 100 and 500 iterations. The final checkpoint has three
alternating paired samples; earlier checkpoints have one sample each and no
reported medians. The final independently replayed NashConv and absolute value
error must both be at most 0.005 chips. Every serialized profile must strictly
contain the exact +1 value in its rational own-hand best-response bracket, and
its exact value error must be no greater than NashConv. Backend metric and
probability gates remain `1e-8` / `1e-6`, with independent scalar replay `1e-10`.
All raw policies, failed observations and early misses remain in the report.

Complete calls include canonical JSON serialization and payload hashing; input
loading, source checks and independent replay are outside timing. Runtime is
observed per fixture; no general speedup, allocation or RSS claim follows.

[Reference tests](../tests/test_preflop_aa_kk_reference.py) check physical pair
coverage, exact bounds and their failure cases, admission before lookup,
unchanged ordinary preparation rejection, dirty-source isolation and saved-file
checksums. Formal clean-source measurement and final publication are pending
at this source stage.
