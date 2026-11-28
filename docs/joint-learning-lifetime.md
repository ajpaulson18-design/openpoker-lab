# Uniform joint-world learning lifetime worksheet

Status: independent normal/optimized scalar validation passes. No longer native lifetime is
admitted. The Store still rejects more than two epochs, and every resource cap
remains unchanged.

The [scalar worksheet](../scripts/forecast_joint_learning_lifetime.py) separates
three scaling questions: encountered public Catalog blocks, encountered
own-hand/visible-history identities, and nonzero numerical Store rows. A full
selected-world walk encounters all 434 decision histories even through zero
policy branches. Numerical retention depends on the evolving policy and its
updates, so encounter lower bounds are not lower bounds on numerical retention.

For complete uniform ranges and iid uniform legal joint worlds, an individual
betting path has uniformly distributed public prefixes over
`P=(1,C(52,3),C(52,3)*49,C(52,3)*49*48)` cells. Its own-hand/visible-prefix
identity is uniform over
`K=C(52,2)*(1,C(50,3),C(50,3)*47,C(50,3)*47*46)` cells. Each equals the
public-prefix count times supported own hands at that street. The opponent's
hidden holding and hidden future board do not belong to the identity.

For T independent observations, expected distinct cells are exactly
`K*(1-(1-1/K)^T)`. Linearity of expectation permits summing over betting paths
despite dependence between paths within one world. No independence between
the two seats or different streets is assumed. The worksheet uses exact
rational Bonferroni and Cauchy bounds instead of constructing huge powers or
using floating-point exponentials. Its largest arithmetic components stay
within 256 bits for at most one billion observations. Expectations apply to
this uniform iid law, not arbitrary weighted ranges or a native RNG.

The same Catalog descriptor ledger reserves 32 words plus a 21-word holding
bitmap per public block, with fixed owner/menu allowances. Applying this
ledger to the encounter bounds exposes a capacity issue even with sparse
numerical updates. The worksheet reports logical words, not allocator bytes,
RSS, an information-theoretic lower bound, or whole-request work admission.
Hypothetical eight-byte units for every encountered slot are labelled as such;
the numerical Store can omit zero rows.

Fixed Q52, fixed path depth and q=P keep the regret/average denominators fixed
at `2^625` and `2^364`. The independent numeric rules bound terminal utilities
by eight in magnitude. A regret increment therefore has magnitude at most
`16*2^625`, and an average increment at most `2^364`. Summing T increments
increases numerator width logarithmically. These are conservative carrier
bounds, not observations of actual regret growth. Existing widths must be
re-admitted for a longer lifetime; passing a width bound does not admit work,
storage, epoch count, or quality.

Independent controls enumerate all 15,120 legal nine-card worlds and check
both seats' own-visible marginals. Small exact occupancy calculations check
the rational interval bounds. Separate controls preserve false training and
admission flags and expose the existing average-width boundary. This extends
the [dense full52 census](joint-chance-weighted-range-design.md), not the old
eleven-card exhaustive admission: that historical State/quantizer refusal
remains unchanged.

The next persistent-learning design must account for the complete requested
lifetime, measure policy-dependent retained unions, and bind any checkpoint
or storage compression to exact identity and update semantics. Splitting a
request into chunks is not permission to reset cumulative resource receipts.

## Executed worksheet

Source `856167c` passes four independent controls in normal and optimized Python,
including both-seat enumeration of all 15,120 nine-card worlds. The two scalar
outputs are byte-identical, SHA-256
`366a5bfc0375efe35f402ffac31713ab0e536f689841fdb95bbe3f24ff716e5a`.
The [saved observations](../benchmarks/results/joint-learning-lifetime-v1/result.json)
retain actual child exits, unchanged before/after raw source inventories, and
the complete rational intervals. No native process or learning run is entered.

| Uniform iid observations | Expected encountered information rows, outward rounded | Expected Catalog logical words, outward rounded |
| ---: | ---: | ---: |
| 2 | 867–868 | 185,589–185,590 |
| 100 | 43,378–43,379 | 2,408,213–2,408,214 |
| 1,000 | 432,199–432,307 | 22,783,482–22,783,489 |
| 1,000,000 | 427,350,174–427,350,261 | 18,716,364,332–18,918,901,915 |

The expectation lower bound already exceeds the Catalog's two-million-word
cap at 100 observations under its current representation. This is not a
guaranteed count for every deterministic sequence. The current native request
still has an earlier two-epoch limit. At 262,144 observations, the conservative
average-numerator envelope first requires 383 bits rather than the current
382; that means the existing width proof would no longer cover every allowed
sequence, not that every actual average reaches that width.

The Catalog currently allocates a 21-word holding bitmap even when a public
block has seen just one holding. This representation is a justified next
target: compare an exact lazy-bitmap design against the original, with source-
derived peak reservations, unchanged ownership/identity guards and complete
numerical parity. Measure numerical retention separately before designing any
longer-learning admission.
