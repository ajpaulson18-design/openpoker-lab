# Richer flop betting: fixed accuracy and admission matrix

The [frozen matrix](../benchmarks/preflop-flop-raise-coverage-v1.json) extends the explicit preflop/flop game with flop half-pot and pot-sized bets, half-pot raises, one allowed raise and explicit all-in actions. Preflop retains the half-pot opening/limp-raise model with one raise and no explicit preflop all-in action. Stacks are fixed at **3, 4 and 6 chips**, with **20/delay10, 90/delay45 and 250/delay125** sweeps each. All nine cases were chosen before training. This is additional measured coverage of the existing engine, with no production code or action-rule change.

Ranges remain SB `AsAd,QsQd` and BB `KsKd,JhJc`, with flops `2c3c4d` and `5h6sJc`. All 4,704 ordered future candidates yield 11,880 compatible joint physical worlds. `JhJc` is blocked on the second flop, so the selected joint game has unequal pair priors. Future indexing is opt-in `flop-sign`, with 16 grouped training rows, while independent numeric replay uses every original physical world and exact legal visible-information best responses. Turn and river betting remain outside this explicitly forced-checkdown game.

The [harness](../scripts/benchmark_preflop_flop_raise_coverage.py) first preflights **all nine cases before training any case**. It intercepts the solver immediately before grouped-world allocation, forbids vector-view/trainer entry, and records original-world vector admission, separate grouping charges and actual tree/template counts. All nine passed unchanged limits. Each subsequent complete solve checks that its total admission equals its preflight total; no rejected case is simplified or retried. Known cap rejections would remain in the report, and unexpected failures propagate. Even an all-rejected result is saved before intended action-coverage failure is raised.

| Stack | Public states | Decisions | Information sets | Maximum live template states / decisions |
| ---: | ---: | ---: | ---: | ---: |
| 3 | 88 | 36 | 64 | 21 / 8 |
| 4 | 112 | 44 | 78 | 33 / 12 |
| 6 | 172 | 64 | 113 | 39 / 14 |

At 250 sweeps the combined original-world vector plus grouping loop envelopes are **2,674,854**, **3,253,088** and **4,698,667**, below the unchanged 500,000,000 modeled-loop ceiling. Physical world-iteration admission is **11,880 × 250 = 2,970,000**, below the unchanged 3,000,000 ceiling. All other candidate, selected-outcome, prefix, dense/reference, public-state and template caps remain in force. Counts are structural admission evidence, not runtime or RSS predictions.

Every trained policy is independently replayed using numeric poker rules, independently evaluated card ranks, hidden-future integration and exact legal best responses. Every reachable information set and serialized action/amount/target is checked. The maximum production-versus-oracle scalar discrepancy is **3.34e-16**. The target remains **NashConv + 1e-10 <= 0.005 chips** for every case.

| Stack | 20 / delay 10 | 90 / delay 45 | 250 / delay 125 |
| ---: | ---: | ---: | ---: |
| 3 | 0.095603432391 — miss | 0.018321185257 — miss | **0.002544600621 — met** |
| 4 | 0.180089018155 — miss | 0.022872178616 — miss | **0.002490648379 — met** |
| 6 | 0.184886280469 — miss | 0.019844802674 — miss | **0.011632249016 — miss** |

Seven of nine checkpoints miss the target. The six-chip case remains a miss at the highest predeclared checkpoint; it is not promoted as target-accurate. All measured gaps decrease across these three checkpoints, which is finite-run evidence for these fixtures rather than a broad convergence guarantee. In particular, adding flop actions makes the earlier single-bet 90-sweep success insufficient evidence for these richer games.

Action coverage is checked from independently validated **flop rows only**, so a preflop raise cannot certify a flop raise. The admitted matrix contains check, call, bet, raise and all-in flop actions. At the BB flop root after limp/check, the matched preflop contributions are one chip each and pot is two chips; the distinct one- and two-chip opening bets verify that both configured flop sizes are live. Per-case coverage remains visible: caps and duplicate targets can eliminate some named actions at a particular stack. This proves availability of legal actions, not positive equilibrium use of every action.

The [raw report](../benchmarks/results/preflop-flop-raise-coverage-v1.json) records clean frozen source `ebab6da3a5cdcc9f4f5d93d81979613ce5a72b40`, all 58 source/specification hashes, every admission, case-specific coverage, complete numeric replay, target misses and one descriptive complete-call-plus-JSON time per case. Preallocated inputs, pre-call garbage collection and independent replay are excluded from timing; previous full policies are released before the next solve. Single timings are not a speedup comparison or statistical performance claim, and no memory experiment is made in this slice.

The full matrix was rerun after a trailing blank line was removed from the harness. All independent replay results exactly match the pre-format run; fixture/action/specification/numerical code were unchanged, and no case or target was selected from the results. The committed report uses the final clean source above, with hashes/revision rechecked before saving.

Validation includes successful syntax compilation and all nine actual preflights and independently verified solves. The unchanged production source already passed 607 local tests plus Python 3.11/3.12/3.13 and presentation CI in the preceding grouped-future release; final-head applicable checks must pass before this report merges. Luna drafted the bounded script/spec and reviewed the measurement plan; lead reviewed integration, tightened flop-specific coverage/rejection reporting, froze and measured the complete matrix. No third-party source/dependencies, proprietary outputs, shared postflop/turn/river kernel or AI Coach changes.

All evidence remains limited to the finite conditioned heads-up preflop/flop game, narrow ranges and forced future checkdown. It does not establish full-deck/broad-range preflop, unrestricted NLHE, all-streets or multiway accuracy. The earlier raised all-streets per-flop template rejection remains unresolved in its separate workstream.

```text
python -m scripts.benchmark_preflop_flop_raise_coverage
```
