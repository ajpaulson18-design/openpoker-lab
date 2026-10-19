# Exact audit through a checked full-deck chance quotient

This development auditor is restricted to the [fixed raised turn/river
game](full-deck-raised-turn.md). It executes no training and changes neither
production solvers nor the generic exact auditor. The complete six-policy audit
below certifies explicitly normalized policies for this fixed model.

## Physical and information equivalence

The 48 candidate river cards partition into five classes for this particular
board and four private pairs:

| Class representative | Original physical rivers |
| --- | --- |
| 3c | All 40 remaining cards other than aces and kings |
| As | As, Ah |
| Ac | Ac, Ad |
| Ks | Ks, Kh |
| Kc | Kc, Kd |

This is a fixture-specific partition. The auditor reconstructs all 176 original
worlds, checks each exact pair mass divided by 44, verifies every showdown sign
with exhaustive best-five ranking, and checks each class's full card set across
all private pairs that support that class. Equal counts alone are insufficient:
the sets must agree. Each individual card within a class consequently has the
same likelihood under every supported hidden private pair.

Every original public action and terminal branch is checked, including off-path
branches. Mapping river history tokens and public boards to representatives must
produce identical subtrees within each class and match a separately constructed
quotient tree. Legal actions, wager amounts, refunds and cumulative contributions
must all agree. The reduction sums exact physical masses; it does not condition
the game on five selected physical rivers.

The complete original 2,404-row policy first passes full-deck numeric-rule
validation. Every raw binary64 probability and mapped row/action metadata must
then agree exactly within its class. A tolerance, averaging step or repair is
not allowed. The projected policy must cover all 220 legal quotient rows. The
quotient contains 12 weighted worlds, 330 public nodes and depth nine.

For a class-constant opponent, an individual river card within the class gives
the responder the same hidden-hand posterior, legal subtree and payoff
objective. The responder may choose a different action for each physical card;
each of those conditional optimization problems still has the same optimum.
Summing their maxima equals the optimum multiplied by the class mass. Turn
choices integrate all classes before maximizing, so they cannot see a future
card. This establishes equality of profile value and both legal best-response
values between the full game and its quotient without restricting the full
game's deviations to class-constant strategies.

## Exact arithmetic and limits

The unchanged generic Fraction evaluator runs on the checked quotient. It
explicitly normalizes each binary64 input row as exact Fractions and retains
the complete normalization ledger and canonical normalized rows. Its certificate
therefore applies to that explicitly normalized policy. It is not a proof that
raw floating-point sums are exact or that the policy is equilibrium.

The original limits remain 100,000 modeled exact-work units, depth 64 and
65,536 fraction bits. The exact helper's work counters exclude full physical
validation, quotient preparation and full-deck numeric replay; those steps have
separate fixed envelopes of 176 worlds, 2,404 rows, 3,039 public nodes and depth
nine. These counts are not CPU, byte or RSS bounds. The generic unreduced audit's
recorded work-limit rejection remains valid and unchanged.

The audit pins the accepted numeric report, all six complete policy hashes,
the physical reference and proof sources. All target misses must remain in the
new exact report. The original numeric policies and report are immutable.

## Recorded exact audit

The [immutable audit](../benchmarks/results/full-deck-raised-turn-exact-audit-v1.json)
is 3,195,784 bytes with SHA256
`6a2b1b66631bdb892856cae38b9378b16bfb702ed84d8563cf56a90dc6f9f1ed`.
Generation was frozen at `25fe7a5be7900acdef25f9f8ada45134823f6521`;
all ten proof/source pins match committed Git bytes. Every policy retains all
eight exact metrics, legal-response bounds, Fraction normalization adjustments,
canonical normalized quotient rows and detailed work counters.

| Iterations | Materialized exact NashConv, rounded | Matrix-free exact NashConv, rounded |
| ---: | ---: | ---: |
| 100 | 0.3697688228923919 | 0.3697688228923921 |
| 1000 | 0.0037309341770361214 | 0.003730934177036123 |
| 1500 | 0.0016587453303189687 | 0.0016587453303189693 |

All six exact Fractions miss the unchanged 1/1000-chip target. All use 13,708
modeled exact-work units. Maximum observed fraction size is 6,423 bits; largest
input-row probability adjustment is 1.4236712691430153e-16. Maximum difference
between an exact normalized metric converted to binary64 and full physical
numeric replay is 8.256850064780608e-15 chips. Numeric observations replay with
1e-12 tolerance across supported platforms; Fraction certificates and ledgers
must reconstruct exactly.

Staged and published verification passed without training. Separate Sol review
used another projection constructor and a literal 12-world mass table, checked
all ten generation pins against Git, and matched all eight exact metrics for
every profile. That review shares the generic Fraction evaluator; the original
full physical numeric-rule replay and independent closed-form check/call anchors
provide separate diagnostic checks. The 12 focused tests passed in normal and
optimized Python, including physical-law, information, policy, tree and immutable
artifact failure cases. This establishes fixed-policy accuracy evidence, not
convergence to an exact equilibrium or a broader-game certificate.

## Reproduction

Run `python -m unittest tests.test_full_deck_raised_exact -v` and repeat with
`python -O`. `python -m scripts.audit_full_deck_raised_exact --generate` creates
the separate immutable audit; later calls return saved verification. Without
`--generate`, the command reconstructs and verifies an existing audit without
training. The report is bounded to 8,000,000 bytes and policies to 2,000,000 bytes
before reading. Sources, current HEAD and accepted bytes must stay stable during
verification; a historical generation commit remains valid after publication.
