# Full-deck raised turn validation reference

This development reference combines two previously separate validation dimensions:
the full remaining river deck and finite raises on both turn and river. It runs
no production training and changes no production solver, earlier-street source,
default, payoff convention or admission limit. The later [fixed-budget experiment](full-deck-raised-turn-tail.md) records
finite-iteration quality; separately derived [exact witnesses](full-deck-raised-turn-clean-witness.md)
now establish the configured game value, with [independent full-physical replay](full-physical-audit-wrapper.md).

## Fixed game and physical evidence

Use turn `Js8d4c2h`, OOP `AsAh:0.5,KsKh:1`, IP
`AcAd:1,KcKd:0.75`, pot 100, original stack caps 220/220, half-pot opens and
raises, one raise per street and `include_all_in=False`. The same config applies
to both streets. Omit runouts: all 44 physically legal rivers follow each of four
compatible private pairs. The union has 48 public candidates/reachable rivers;
the complete joint game contains 176 globally weighted worlds.

| OOP / IP | Exact pair mass | Wins / ties / losses over 44 rivers |
| --- | --- | --- |
| AhAs / AcAd | 4/21 | 0 /44 /0 |
| AhAs / KcKd | 1/7 | 42 /0 /2 |
| KhKs / AcAd | 8/21 | 2 /0 /42 |
| KhKs / KcKd | 2/7 | 0 /44 /0 |

The independent numeric-rule constructor checks every exact world mass and
cross-checks every showdown sign using exhaustive best-five ranking. Global
physical mass is 1. Its public tree has 3,039 nodes, 1,254 decisions, 2,404 own-hand
policy rows and depth 9. The separate rank-free production-structure census
matches its complete tree projection, including histories, action amounts and
terminal contributions, at SHA256
`70d87064c6d7048b75784b6623a2dc6249f57ac61384a27d1724c3d53563bd61`.

The finite tree includes `raise@150` and stack-capped `all_in@220`. Disabling
optional all-ins does not remove an ordinary bet/raise clipped to the stack.
After turn bet 50, raise 150 and call, the river's remaining capped wager is 70,
its cumulative target is 220, and the called showdown has contributions 220/220.
The winning OOP transfer is 270, including half the original pot. This checks
carried investment and refunds separately from action labels.

## Hand-written policy and legal response anchors

The complete deterministic reference policy checks whenever available and calls
otherwise. Both players therefore check through on path. Its exact OOP profile
value is -2500/231. This is a policy value, not an equilibrium value.

Legal best responses to that particular policy have an independent closed form.
The opponent never bets or raises. A responder chooses turn investment t=0 or 50,
then river investment b=0 or(50+t); all such wagers stay below the stack cap.
For each own hand and visible river, sum the signed physical masses over hidden
opponent hands first. Call this sum s. OOP's river-optimized contribution is
`(50+t)*(s+max(0,s))`; IP minimizes using `min` instead. Sum every river before
choosing t, then sum the own-hand responses. Neither choice sees an opponent hand
or a future river unavailable at that decision.

| Quantity | Exact value |
| --- | --- |
| Profile OOP value | -2500/231 |
| OOP legal best response | 2350/231 |
| IP legal best response | 14975/231 |
| NashConv | 75 |
| Exploitability | 75/2 |

All eight independent numeric replay metrics agree with these exact anchors
within 1e-12 chips. Allowing the turn choice to see the river illegally increases
OOP's response to 2825/231 and IP's to 15325/231. A negative regression retains
both strict differences. The simple-policy formula does not audit arbitrary
trained policies and does not replace the existing generic exact auditor.

An exploratory uniform-policy call to the generic partition exact auditor
rejects at its unchanged 100,000-work limit. No partial result is an accepted
certificate. Broader exact trained-policy validation remains a separate task.

## Resource forecasts and frozen next experiment

The rank-free census counts 32 decision visits per materialized world and two
original hands per player. At T fixed CFR+ iterations, existing modeled work is
`176*32*3*T` for materialized training and `2*3039*(3*T+3)` for matrix-free
training plus final diagnostics.

| Iterations | Materialized work | Matrix-free work |
| ---: | ---: | ---: |
| 100 | 1689600 | 1841634 |
| 1000 | 16896000 | 18252234 |
| 1500 | 25344000 | 27369234 |

Each lies under the unchanged 30,000,000-work cap. The materialized formula first
exceeds it at 1,776 iterations (30,007,296); the matrix-free formula at 1,645
(30,013,164). These forecasts do not make production admission decisions or
authorize bypassing any other production guard. They are not CPU, byte or RSS
bounds.

The next experiment is fixed before training: iteration-major 100, 1,000, 1,500,
materialized then matrix-free, CFR+, full-deck chance, no stopping target.
Keep all six complete policies and every miss of 0.001-chip NashConv. This
reference itself contains zero training calls. The separate completed experiment
below retains the original grid and every quality miss.

## Completed fixed-budget experiment

The [immutable numeric report](../benchmarks/results/full-deck-raised-turn-benchmark-v1.json)
retains all six actual complete CFR+ calls and their full policies. Generation
ran from committed revision `6541f3da4bc1d71954febb4c0ad70d4a91e2f617`;
all 71 source pins match that Git revision. Report SHA256 is
`4381b2fbb7008572ff0993d005ee6d2d8dd00c6f9a38621d65b9621b469a9669`.
Each saved policy contains all 2,404 information rows and independently replays
all 176 physical worlds, four compatible pairs and 1,254 public decisions.

| Iterations | Materialized NashConv | Matrix-free NashConv | Target met |
| ---: | ---: | ---: | --- |
| 100 | 0.36976882289238944 | 0.3697688228924001 | Neither |
| 1000 | 0.0037309341770424 | 0.0037309341770424 | Neither |
| 1500 | 0.001658745330324507 | 0.001658745330324507 | Neither |

All six miss the unchanged 0.001-chip reporting target. No stopping target was
configured; every call completed its full requested budget. Independent replay
checks all eight profile/response metrics before and after serialization; maximum
production/replay disagreement is 1.4210854715202004e-14 chips. The source and
HEAD guards stayed fixed through training, conversion and final saved replay.
Staged and published report verification both passed. A separate Sol review
imports neither this candidate runner nor a production trainer, checks generation
pins against Git, replays every policy and retains every miss.

Complete call plus canonical JSON took 7.962 / 34.356 / 89.668 / 269.588 /
137.473 / 454.208 seconds in grid order on this shared host. Independent initial
and saved replay took 1.725–2.579 seconds per case. These are uncontrolled single
observations, with no RSS or general speed/convergence claim. The generic exact
auditor also rejects the saved materialized 100-iteration policy at its unchanged
100,000-work cap. Numeric replay is not an arbitrary-policy exact certificate;
the separate exact check/call anchors do not certify trained equilibria.

The later [checked chance-quotient audit](full-deck-raised-exact.md) separately
certifies all six explicitly normalized policies for this fixed full-deck game,
retaining all original physical mass and all six target misses. Its strict
information-equivalence and policy-equality requirements do not turn the numeric
report into a generic arbitrary-policy certificate or remove the unreduced
auditor's recorded work-limit rejection.

## Reproduction and verification

`python -m scripts.full_deck_raised_fixture` prints the advisory census.
`python -m scripts.full_deck_raised_reference --verify` reconstructs the saved
[reference](../benchmarks/results/full-deck-raised-turn-reference-v1.json) without
a production tree, trainer or candidate census. The bounded 200,000-byte envelope
pins proof sources and its historical generation commit; current source/HEAD
and accepted file bytes must stay unchanged across verification. Python source
pins normalize LF/CRLF only. Existing differing reference bytes cannot be
overwritten; failed new publication removes only its own newly created file.

Run `python -m unittest tests.test_full_deck_raised_fixture tests.test_full_deck_raised_reference -v`
and repeat with `python -O`. The tests cover rank-free census, original work
boundaries, independent physics/tree agreement, carried contributions, legal
information, changed source/data/HEAD and byte admission. Production defaults,
previous proofs, preflop/flop, Coach and frontend remain unchanged.

`python -m scripts.benchmark_full_deck_raised_turn --verify` checks the immutable
numeric report and all six saved policies without training. `--generate` returns
saved verification when the accepted report already exists and rejects a partial
immutable policy set before training. Each policy has a 2,000,000-byte admission
cap and the report a 1,000,000-byte cap, both checked before reads. Sources,
current HEAD, report and policy bytes must remain stable across verification.
The standalone `tests.test_full_deck_raised_saved_policy` replays the committed
experiment with production solver/trainer and exact-auditor entry points disabled.
