# Exact audit through a checked full-deck chance quotient

This development auditor is restricted to the [fixed raised turn/river
game](full-deck-raised-turn.md). It executes no training and changes neither
production solvers nor the generic exact auditor. Certificate publication and
the complete six-policy audit are pending at this source-preparation checkpoint.

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

## Reproduction

Run `python -m unittest tests.test_full_deck_raised_exact -v` and repeat with
`python -O`. `python -m scripts.audit_full_deck_raised_exact --generate` creates
the separate immutable audit; later calls return saved verification. Without
`--generate`, the command reconstructs and verifies an existing audit without
training. The report is bounded to 8,000,000 bytes and policies to 2,000,000 bytes
before reading. Sources, current HEAD and accepted bytes must stay stable during
verification; a historical generation commit remains valid after publication.
