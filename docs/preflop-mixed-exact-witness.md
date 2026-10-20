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

The exploratory candidate has a rational value and fits the unchanged LP caps.
Independent physical response verification, a clean formal report and GitHub
publication are still pending at this source revision. Do not present the
candidate value as an exact game value until those checks pass.
