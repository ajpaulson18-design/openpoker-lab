# Proposed exact physical witness for three preflop ranks

This separate candidate study extends the [mixed-range exact witness](preflop-mixed-exact-witness.md)
to SB `AA:1,QQ:0.5,JJ:0.25` against BB `KK`. It retains blinds 0.5/1,
stacks 3/3, raise sizes 0.5 and 1, two raises and all-ins. Every closed
nonfolded line forces hidden full-board checkdown. There are no later-street
decisions. Neither source count coverage nor a reduced candidate LP proves
equilibrium in this physical game.

The [three-rank transport study](preflop-three-rank-transport.md) supplies
108 physical pairs from nine independently authenticated source classes. Its
exact global weight is 63: each AA pair has prior 1/63, each QQ pair 1/126,
and each JJ pair 1/252. The represented 184,928,832 board outcomes require
no new board enumeration. The source publication and transport proof must
pass and merge before a dependent formal witness is recorded.

## Candidate and proof authority

The [candidate producer](../scripts/preflop_three_rank_sequence_candidate.py)
averages physical showdown means with their exact joint priors within each
rank. It uses the project's existing Fraction sequence-form LP, with three
SB types and one BB type, then lifts complete own-type behavior onto each
physical own hand. It retains reduced matrices, realization flows, duals,
slacks and off-path policies as candidate diagnostics.

The fixed sequence counts are 34 and 11; flow counts are 13 and 5. The two
tableaux have 24 rows / 79 columns / 2,000 cells and 39 rows / 110 columns /
4,440 cells. All existing LP limits remain unchanged: 96 rows, 256 columns,
25,000 cells, 512 pivots, ten million updates and 4,096-bit fractions. These
limits admit a bounded candidate search and establish no runtime or RSS bound.

The [independent physical response checker](../scripts/preflop_three_rank_pure_response.py)
authenticates saved source counts, rebuilds literal private combinations and
relative-suit classes, and uses the prior witness's fourteen explicitly written
terminal histories. It retains 18 SB hands, six BB hands and all 108 pair
priors. It accepts exactly 96 own-hand/public-history policy rows, including
off-path histories. The candidate producer, numeric tree, LP and production
evaluation routines cannot serve as its proof authority.

For each responding own hand, the checker evaluates every complete legal
pure policy against all hidden opponent hands before choosing the best one:
18 times 48 SB policies plus six times 36 BB policies, or 1,080 candidates.
It permits arbitrary suit-dependent deviations. An exact mutual-response
witness requires agreement with the claimed rational profile value and exact
NashConv zero. An arbitrary non-equilibrium policy remains a measured miss.

The [formal runner](../scripts/certify_preflop_three_rank_sequence.py) requires
clean committed source, an ancestor baseline commit and a fresh external
directory. Its operator separately verifies the transport publication's actual
GitHub checks and merge before selecting that baseline. It records one candidate attempt and exactly two prescribed LP
calls, saves the complete candidate, and independently checks it in memory and
from the saved file. Candidate construction, numeric tree and LP calls are
disabled during replay. Source identities must remain stable on every exit;
a mathematical pass followed by source drift is an overall error. First
failures and later cleanup errors remain recorded without a retry.

## Status and provenance

Implementation and adversarial checks are preparatory evidence. A clean frozen
candidate search, physical mutual-response certificate, saved-file replay,
GitHub validation and merge have not been recorded for this study. No candidate
policy or game value is asserted here.

This reuses the project's original sequence-form and literal-response methods
and the research provenance recorded in the [prior witness](preflop-mixed-exact-witness.md#research-provenance).
No third-party implementation or new dependency is added. The result, if it
passes, will concern only this finite preflop/checkdown model; unrestricted
Hold'em, later-street betting, multiway play, general starting ranges, runtime,
memory and trained-solver convergence remain separate questions.
