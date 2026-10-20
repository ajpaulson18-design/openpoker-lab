# Exact mutual-response witness for mixed physical preflop ranges

The [frozen certificate experiment](../benchmarks/preflop-mixed-exact-witness-v1.json)
uses the same [72-pair weighted physical game](preflop-mixed-physical-range.md):
`AA:1,QQ:0.5` versus `KK`, blinds 0.5/1, stacks 3/3, two raise sizes and two
raises. All closed nonfolded lines force hidden full-board checkdown. This
certificate does not add later-street betting or unrestricted starting ranges.

## Candidate search and independent certificate

The project-owned [candidate producer](../scripts/preflop_mixed_sequence_candidate.py)
averages all 36 exact physical payoffs within each rank class using their
original joint priors. It solves a two-SB-type/one-BB-type sequence-form game
using the existing bounded Fraction simplex. It records the candidate reduced
matrix, flows, realization plans, duals, slacks and policies, then copies each
own-type policy onto the corresponding physical own hands. No private hands
are combined in the independent certificate.

Candidate shapes are 20 rows / 64 columns / 1,365 tableau cells for the SB
lower-bound problem and 28 / 80 / 2,349 for the BB upper-bound problem. All
existing caps remain: 96 rows, 256 columns, 25,000 cells, 512 pivots, ten million
updates and 4,096-bit rational components. These are candidate search limits,
not a new production backend or a general scalability claim.

The independent physical response checker reads only the serialized policy and
authenticated physical source reports. It rebuilds each rank pair's three suit
classes (six source classes total) directly from shared-suit counts and retains all 72 global priors. It
uses fourteen explicitly written terminal histories and exact chip transfers,
without the candidate producer, sequence-form LP, numeric tree, production
ranking, training or evaluation code. For each responding own hand it enumerates
all complete legal pure policies and sums every hidden opponent before choosing
its best response: 12 SB hands times 48 policies plus six BB hands times 36,
**792 legal own-hand responses**. Pair-conditioned clairvoyant controls, where
recorded, are separate invalid-information models, never the certificate.

Exact profile value and legal best-response values must agree and exact
NashConv must be zero. This full physical test is the proof authority; neither
candidate symmetry nor the producer's primal/dual bookkeeping is sufficient.
Zero-reach information sets still require complete normalized legal policies.
The [formal runner](../scripts/certify_preflop_mixed_sequence.py) requires clean
committed source, records before/after identities, forbids production
calculation, disables candidate/tree/LP calls during independent replay, saves
raw candidate and proof observations, and freshly replays the saved file.

## Research provenance

Sequence-form realization flows and their LP constraints follow published
mathematical ideas described by
[Koller, Megiddo and von Stengel](https://ai.stanford.edu/~koller/Papers/Koller%2Bal%3AGEB96.pdf).
Global suit invariance is conceptual context from
[Waugh's card isomorphism research](https://www.cs.cmu.edu/~waugh/publications/isomorphism13.pdf).
The implementation reuses the project's own Fraction LP and original numeric
rules in the candidate lane. The independent lane uses literal terminal paths.
No external implementation, evaluator, proprietary output or new dependency is
incorporated; this is not a commercial licensing clearance claim.

## Evidence status

The [formal certificate](../benchmarks/results/preflop-mixed-exact-witness-v1.json)
passes from clean source `009e4626b9a365b330b1b36ec1ea113113c7c20a` on Python
3.12.14 / Windows. All 557 LF-normalized source hashes independently match
frozen Git contents. Every forbidden production call counter is zero. Source
identities remain unchanged across the run and actual saved-file replays.

The exact SB game value is **`61612/75655` chips**, with exact SB best-response
value `61612/75655`, BB own-utility best-response value `-61612/75655`, both
unilateral gains zero and **exact NashConv `0`**. This is a mathematical
mutual-response certificate for the full 72-pair finite game. It does not
certify unrestricted Hold'em or identify every equilibrium policy.

The recorded candidate shoves each own AA hand. Each own QQ hand folds with
probability `28086/75655` and shoves with `47569/75655`. All 72 physical own-hand
rows, including off-path histories, are explicitly normalized and checked.
The independent oracle still permits arbitrary suit-dependent legal deviations;
it does not assume that an optimum response shares the candidate's symmetry.
Illegal pair-conditioned controls strictly improve both players' own utilities,
showing why conditioning on the hidden opponent would change the game.

The [initial report](../benchmarks/results/preflop-mixed-exact-witness-v1-initial.json)
is preserved with status `error`: its mathematical response check passed, but
saved-summary comparison failed when JSON converted integer suit-class keys to
strings. The followup uses explicit string keys and a roundtrip regression,
adds declared-game identity validation, and reproduces the identical candidate
artifact `e68870a26e6bfa5426edf9dd945293e4da2c369accba17a06c83dd8fe656fd05`.
No mathematical acceptance gate or LP cap changed.

Canonical passing report SHA-256:
`ed3512d35f03e2e7ed9e7440b73923670ca2412779a3e2dee97e79ad478d1ebb`.
Raw passing report SHA-256:
`1c5427b4cca145b4931913599ee244f044deac9fac5d0a94521902ec3371726f`.
[Publication tests](../tests/test_preflop_mixed_sequence_publication.py) freshly
replay the actual proof and reject re-signed false values, game labels and
missing guards. The source includes eight independent adversarial boundary
checks and three candidate/formal-source checks. A separate Luna read-only
review checked the physical response proof and found no blocking math issue;
its game-metadata hardening was integrated before the passing formal run.
GitHub checks and merge are verified separately at publication.

## Existing trained policies checked against the exact value

A separate [derived anchor report](../benchmarks/results/preflop-mixed-training-exact-anchor-v1.json)
freshly replays all ten unchanged policies from the prior mixed-range benchmark
and reauthenticates this exact physical witness. Every strict rational legal-BR
interval contains `61612/75655`, and every absolute profile-value error is no
greater than its independently computed NashConv. This is a new logical
comparison of immutable policies, not new training or a retroactive benchmark
gate. The ten-iteration quality miss remains a miss.

| CFR+ iterations | Python absolute error from exact value, chips |
| --- | ---: |
| 10 | 0.0505019135142 |
| 100 | 0.00101637336991 |
| 400 | 6.49277230399e-05 |

The [independent comparison script](../scripts/verify_preflop_mixed_anchor.py)
and [regression](../tests/test_preflop_mixed_exact_anchor.py) reconstruct all
rows, input identities and exact inequalities from published evidence.
