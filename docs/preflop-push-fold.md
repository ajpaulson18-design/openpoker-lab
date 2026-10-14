# Exact full-board heads-up preflop shove/fold

This separate library API restricts the small blind/button to fold or shove,
then the big blind to fold or call. Both starting stacks include posted blinds
and must exceed the big blind. There are no limps, non-all-in raises, later-street
decisions, antes, rake or multiway equilibrium. Other preflop/postflop APIs and
the browser/Coach are unchanged. Full-deck chance coverage in this restricted
game does not establish unrestricted no-limit Hold'em solving.

```python
from pokerlab.preflop_push_fold import (
    prepare_preflop_equities, solve_prepared_push_fold,
)

# Expensive once: enumerate every legal final board for each private pair.
table = prepare_preflop_equities("AsAd:1,QsQd:0.5", "AsKh:0.25,KsKd:1")
result = solve_prepared_push_fold(
    table, config={"small_blind": 0.5, "big_blind": 1, "starting_stack": [3, 2]},
    iterations=1000, algorithm="cfrplus",
)
```

`solve_preflop_push_fold` combines preparation and solving, admitting the full
requested work before enumeration. The prepared API permits repeated stack,
algorithm and iteration experiments without ranking the same boards again.
Vanilla CFR, DCFR and alternating CFR+ reuse the existing independent kernels;
positive averaging delay is available only with CFR+. Finite-iteration output
includes value, information-set best responses and exploitability in this game.

## Chance, utility and trust boundaries

For each compatible private pair, exactly `C(48,5) = 1,712,304` equally likely
unordered final boards are ranked. Without later-street decisions, ordering the
same five cards cannot change utility or information. All boards remain hidden
from every decision. The implementation retains only negative/tied/positive
showdown counts, with at most three weighted terminal categories per pair.

Private weights are interpreted as exact fractions of represented binary64
inputs, multiplied and normalized after private collisions are removed. Each
category's exact prior times count/board-total becomes a positive float mass;
unrepresentable positive support rejects instead of silently disappearing.
No selected-board conditioning or chance sampling is used.

Values are whole-hand net transfers: SB fold loses its blind, BB fold loses its
blind, and a called shove wins/loses the smaller starting stack. Unmatched excess
returns to its owner. With blinds 0.5/1 and stacks `[3,2]`, SB shoves 2.5 more to
3, BB calls 1 more to 2, and SB's excess 1 is refunded at settlement. Histories
and serialized amounts retain the actual actions, even when effective stacks
produce the same strategic game.

`FullBoardEquities` is immutable and structurally validated: hands, compatible
pairs, exact prior total, count totals, categorical masses and budget metadata
must agree. This does **not** prove that arbitrary caller-supplied counts were
computed by ranking real boards. Use trusted preparation output; independent
physical enumeration supplies the benchmark evidence. Synthetic count tables in
unit tests are explicitly labeled numerical fixtures, not Hold'em equities.

## Admission and measurement

Preparation admits at most 4,096 candidate pairs, four compatible pairs,
6,849,216 board evaluations, 13,698,432 rank calls and 12 categorical rows before
enumeration. The solver separately admits the entire requested iteration count
under a conservative 500-million modeled bookkeeping-loop envelope, charging
source preparation even when a table is reused. The supported 10–10,000 input
interval does not mean every pair-count/iteration combination is admitted.
Internal rank instructions and caller progress callbacks are outside loop counts;
ranking has its own bounded call count. These counters are neither elapsed time
nor Python allocation/RSS guarantees.

The frozen [benchmark configuration](../benchmarks/preflop-push-fold-v1.json)
uses two hands per player, three compatible pairs and exact conditional priors
`8/13`, `1/13`, `4/13`. Equal stacks and both asymmetric directions share an
effective two-big-blind game. Checkpoints are 100/1,000/3,000 iterations for each
algorithm, with predeclared final exploitability and known-value error limits
of 0.005 chips. Misses must be reported; these are fixture-specific gates.

```sh
python -m scripts.benchmark_preflop_push_fold production
python -m scripts.benchmark_preflop_push_fold oracle
python -m scripts.benchmark_preflop_push_fold verify
```

The production phase measures one-time preparation separately from complete
prepared solves, including exact diagnostics and JSON serialization. A separate
prepared-solve allocation trace excludes equity preparation and is not RSS.
The oracle independently enumerates every board using the existing best-five
reference ranker, reconstructs blind/refund transfers, converts the serialized
binary64 action frequencies to fractions and exactly renormalizes each action
row, then maximizes only after
summing hidden-opponent alternatives for each responding own hand. Exact rational
indifference equations provide a candidate mixed equilibrium; independent replay
checks its value and legal response gaps. Production ranking/payoff/BR helpers
are candidates, never the oracle. Source hashes are checked before and after;
completed per-pair oracle checkpoints may be reused only with matching hashes,
fixture identities and priors. Artifact checksums detect accidental output edits;
they are not signatures or proof against deliberate coordinated tampering.

## Research and provenance

Published jam/fold research motivates a deliberately restricted preflop action
model: [Miltersen and Sørensen, AAMAS 2007](https://www.ifaamas.org/Proceedings/aamas2007/html/tec18_02.html).
Its results are not claimed as this implementation's accuracy certificate.
[Ganzfried and Sandholm, AAMAS 2008](https://www.ifaamas.org/Proceedings/aamas2008/proceedings/pdf/paper/AAMAS08_0313.pdf)
also discusses the restricted heads-up jam/fold precedent; its multiplayer
tournament method and payout model are not implemented here.
[CFR](https://papers.nips.cc/paper/3306-regret-minimization-in-games-with-incomplete-information.pdf)
supplies the established information-set/average-strategy framework. This code is
independently written using existing OpenPoker kernels and the standard library;
no external source, dependency or proprietary solver output is incorporated.
These references do not establish patent or legal clearance.
