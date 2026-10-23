# Proposed three-rank physical preflop transport audit

This separate no-enumeration milestone reuses the authenticated AA/KK, QQ/KK
and [JJ/KK source counts](preflop-jj-kk-basis-results.md). It checks prepared
counts for SB `AA:1,QQ:0.5,JJ:0.25` against BB `KK`: 18 SB hands, six BB hands
and 108 compatible physical private pairs. It adds no strategy, betting
decision, training call, equilibrium certificate or later-street continuation.
The [JJ publication](https://github.com/ajpaulson18-design/openpoker-lab/pull/216)
must merge and pass its final checks before a formal dependent observation.

## Candidate and independent authority

The [candidate producer](../scripts/preflop_three_rank_transport.py) uses the
existing bounded prepared-count pool with three ordinary source tables. Each
contains the three authenticated relative-suit classes. The original four-pair
enumeration cap and the separate 128-pair prepared-pool cap remain unchanged.
The producer admits the complete literal request and exact target priors before
source authentication or pooling. Its serialized output remains candidate-only.

One global suit bijection must map both ordered private hands from an exact
source row to each physical target. It also maps the entire unused deck, so
there is a bijection between the source and target five-card board sets. This
preserves W/T/L counts without enumerating those target boards again. The
independent checker must authenticate the saved bases, independently reconstruct
all physical target combinations and verify both endpoints and source count
values. It must allow no production pool, range planner, ranker or trainer as
its proof authority. Each rank has six two-shared-suit, 24 one-shared-suit and
six zero-shared-suit pairs.

The 184,928,832 represented board outcomes are coverage information. They do not
authorize a new 108-pair enumeration or an aggregate series of four-pair count
requests. This milestone performs no new physical board counts or rank calls.

## Joint weights and limits

Each target pair receives the product of its literal private-range weights,
conditioned once over the complete compatible joint support. Here the total
unnormalized weight is `36 * (1 + 1/2 + 1/4) = 63`, yielding:

| SB rank | Physical pairs | Exact prior per pair | Total rank mass |
| --- | ---: | --- | --- |
| AA | 36 | 1/63 | 4/7 |
| QQ | 36 | 1/126 | 2/7 |
| JJ | 36 | 1/252 | 1/7 |

The priors sum exactly to one. Row-local normalization and conditioning on a
hidden opponent hand would change the game. Every physical hand retains its
own identity, source map and exact prior, with no strategy sharing imposed.
Structural table validation alone cannot authenticate source counts.

This audit is preparation evidence only. A subsequent finite preflop game must
have a separate action/configuration specification and legal own-hand response
check. The existing 72-pair mixed-game witness does not certify 108 pairs or
these new priors. For the old three-chip betting tree, 18 SB hands times 48
complete pure policies and six BB hands times 36 would require 1,080 own-hand
response candidates; that forecast is not an executed response certificate.
Runtime, allocation/RSS and solver convergence remain separate evidence.

## Formal observation boundary

The [audit runner](../scripts/certify_preflop_three_rank_transport.py) requires
a clean committed source snapshot and a fresh external output directory. It
calls the candidate once, retains its entire serialized report, runs the
[independent checker](../scripts/preflop_three_rank_transport_validation.py)
in memory and freshly from that saved file, and requires identical results.
The saved-file verifier re-reads the candidate after authentication and rejects
any byte change during the check.
Reversible guards forbid ranking, native/reference counting, building and
training throughout; the independent phase additionally disables the candidate
and production pool. Saved-source authentication retains its existing rank-free
metadata admission checks, without using them to reconstruct target transport.
First errors and later source-check failures are retained without a retry.

The [candidate checks](../tests/test_preflop_three_rank_transport.py),
[independent adversarial checks](../tests/test_preflop_three_rank_transport_validation.py)
and [orchestration checks](../tests/test_certify_preflop_three_rank_transport.py)
are separate from an actual clean frozen observation. Formal saved evidence,
publication checks and merge status remain pending.
