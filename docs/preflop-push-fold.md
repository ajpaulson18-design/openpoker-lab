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

Prepared callers may explicitly select
[`resource_model="prepared-counts"`](preflop-prepared-budget.md) to budget only
compact-table validation/setup, training and diagnostics. The default still
charges source preparation, and the full convenience solve keeps its original
pre-enumeration guard.

## Reweighting a prepared table

Use [`reweight_preflop_equities`](preflop-equity-reweight.md) to apply new
private-hand weights to already-covered physical pair counts without ranking
boards again. It permits covered subsets and fully blocked added hands, and
rejects any newly compatible pair absent from the source table.
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

## Independently derived mixed-equilibrium anchor

Let `a=8/13`, `b=1/13`, `d=4/13` be the AA/KK, QQ/AK and QQ/KK priors.
For each independently counted pair, its expected showdown sign is
`(wins-losses)/1,712,304`; call those signs `u`, `v`, `z`. Let `s` and `B`
be the blinds and `m` the effective starting stack. In the checked regime where
AA always shoves, AK always calls, and QQ/KK mix, the indifference equations give:

```text
QQ shove frequency x = a*(m*u-B) / (d*(B-m*z))
KK call frequency  y = (b*m*v+d*B+s*(b+d)) / (d*(B-m*z))
SB equilibrium value = a*((1-y)*B+y*m*u)-s*(b+d)
```

The certificate requires `m*u>B`, `m*v<B`, and both frequencies strictly
between zero and one, then checks the entire constructed policy using legal
own-hand best responses. Arithmetic uses exact count/prior fractions. A regime
failure rejects this certificate instead of forcing it onto another game.
The unit suite's separately labeled synthetic signs `(3/4,1/4,-3/4)` at
`m=2`, `s=1/2`, `B=1` give `x=2/5`, `y=7/10` and value `83/130`.
Those synthetic signs are not claimed to be physical Hold'em equities.

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

## Measured acceptance result

The [verified report](../benchmarks/results/preflop-push-fold-v1.json) passed
all fixed gates at solver/harness source `4650d6591c88c25f1a04c28fcf4960efc6ec33de`
on Python 3.12.14 / Windows 10, Intel Core i7-7500U (two physical cores,
four logical processors). Three independent best-five workers matched every
production integer count across 5,136,912 boards; their complete per-pair
artifacts and the production report are retained beside the verified report.

| SB hand | BB hand | Wins | Ties | Losses | Exact pair prior |
| --- | --- | ---: | ---: | ---: | --- |
| AdAs | KdKs | 1,410,336 | 9,308 | 292,660 | 8/13 |
| QdQs | AsKh | 968,267 | 7,226 | 736,811 | 1/13 |
| QdQs | KdKs | 292,846 | 9,336 | 1,410,122 | 4/13 |

At 3,000 iterations, all three equal-effective-stack configurations met both
0.005-chip gates. Values below are independently replayed for equal two-BB
stacks; the asymmetric cases also passed the refund-invariance checks.
Exploitability is half NashConv; each player's gain is separately in the report.

| Algorithm | Exploitability (chips) | Error against known value (chips) | Prepared solve + diagnostics + JSON (seconds) |
| --- | ---: | ---: | ---: |
| vanilla | 0.00205974461 | 0.0002274736 | 0.724635 |
| dcfr | 0.000777680599 | 1.51611025e-06 | 0.758240 |
| cfrplus | 3.0191892e-05 | 1.40477496e-08 | 1.124098 |

The ideal rational certificate gives QQ shove frequency `130762/493357`,
KK call frequency `1449111/1973428`, and SB value
`256757651065/457587630786`. Every reported policy was independently
checked; maximum production/independent scalar difference was
`2.491e-16` chips.

Full preparation took 488.161 seconds; preparation plus the first 100-iteration
vanilla solve/serialization took 488.206 seconds. These are single observed
measurements, not speed comparisons or future runtime guarantees. A separate
3,000-iteration CFR+ prepared-call trace peaked at 19,437 Python bytes, excluding
the prebuilt table, equity preparation and RSS. No full-preparation allocation
peak is claimed. Independent oracle workers overlapped, taking about
3,468/3,485/3,468 seconds each; their summed worker times in the report are not
total wall time or a production benchmark.

The full local regression suite passed 773 tests in 358.547 seconds. Five final
evidence/replay helper checks passed after CLI-only provenance refinements; the
solver kernels were unchanged. GitHub validates the final published head on
Python 3.11/3.12/3.13 plus frontend/documentation checks. Luna reviewed the core,
independent replay, frozen harness and production artifact; the lead reviewed
and ran all measurement phases. This finite three-pair result does not certify
full-range preflop, missing actions or later-street equilibrium accuracy.
