# Weighted private-range coverage for flop checkdown

This experiment checks weighted private-hand blockers and a broader preflop/flop action menu in a finite heads-up game. It reports approximate-equilibrium checkpoints for this configured game, not a general solver-accuracy claim.

## Fixed fixture

The small blind range is `AsAd:1,QhJh:0.5,7s6s:0.25`; the big blind range is `KsKd:0.75,AhKh:1,8s7s:0.5`. The 3-by-3 combo cross product has nine candidate pairs. `7s6s` and `8s7s` overlap on `7s`, leaving eight compatible pairs. The `6s` on flop `5h6sJc` blocks the small blind's `7s6s` hand. The selected flops are `2c3c4d` and `5h6sJc`; all ordered turn/river candidates under both flops are included.

The independent rational audit counted 4,704 selected runout candidates and 27,720 physically compatible worlds. Six private-pair combinations have 3,960 worlds each. The two combinations containing `7s6s` have 1,980 each because that hand is blocked on one flop. Conditioning the explicit rational range weights on compatible private cards and blocker counts gives:

| Small blind | Big blind | Worlds | Posterior |
|---|---|---:|---:|
| AsAd | KsKd | 3,960 | 24/115 |
| AsAd | AhKh | 3,960 | 32/115 |
| AsAd | 8s7s | 3,960 | 16/115 |
| QhJh | KsKd | 3,960 | 12/115 |
| QhJh | AhKh | 3,960 | 16/115 |
| QhJh | 8s7s | 3,960 | 8/115 |
| 7s6s | KsKd | 1,980 | 3/115 |
| 7s6s | AhKh | 1,980 | 4/115 |

The harness independently parses the exact combo strings and rational weights, checks the private-card overlap and the `6s` flop blocker, and derives the posterior without using production range expansion or ranking as its oracle. Solver and independent replay probabilities are compared against those fractions with tolerance `1e-12`, after canonicalizing card order. The solver delta was 0; the replay delta was at most `1.021405182655144e-14`.

Both players start with 10 chips. Preflop uses small blind 0.5, big blind 1, raise fractions 0.5 and 1, a three-raise cap, and all-in actions. Flop uses bet fractions 0.5 and 1, raise fraction 0.5, a one-raise cap, and all-in actions. After flop betting, the game forces checkdown while the selected turn and river remain hidden until terminal utility evaluation. Training uses public-batched CFR+ and grouped future rows; independent verification uses all 27,720 original physical worlds.

## Admission and results

Both cases passed grouped-vector preflight before training. The preflight retained each requested iteration ceiling in the vector-work estimate and included the separate grouped-world charge. Combined modeled work was 49,064,575 loop entries at 500 iterations and 96,715,575 at 1,000 iterations. Both cases had 694 public states, 262 decision nodes, and 728 information sets. The 27,720 physical worlds formed 34 grouped rows by private pair, public flop, and final showdown sign. Training and public-batched diagnostics used that grouped view; physical counts and private-pair priors remained tied to the original worlds, and the independent replay used all original worlds.

Grouped-vector admission replaces the old physical-world-count times requested-iterations guard with a construction-only charge of 10 iterations per physical world. This changes that one admission rule for the explicit opt-in mode. The candidate-pair charge still uses requested T, the full requested T remains in the vector-work estimate and checkpoint training, and the tree, information-set, vector, grouping, and copy limits remain enforced.

| Iterations | Averaging delay | Independent NashConv | 0.005-chip target | Combined modeled work | Complete solve + JSON |
|---:|---:|---:|:---:|---:|---:|
| 500 | 250 | 0.0005477015116682749 | Met | 49,064,575 | 11.258 s |
| 1,000 | 500 | 0.00007499768949426056 | Met | 96,715,575 | 19.404 s |

The unchanged checkpoint target is `NashConv + 1e-10 <= 0.005`. Both policies were replayed over original physical worlds with numeric poker rules and exact visible-information best responses. Candidate and replay metrics for value, both players' best responses, and NashConv matched exactly in the recorded comparisons. Both measured gaps met the target; this is evidence only for these finite cases.

Serialized preflop actions included SB opening raises to 2 and 3, BB three-bets, a regular SB four-bet to 8, and all-ins. Across the two checkpoint policies there were 60 checks of histories at the three-raise cap with no raise or all-in beyond it. Those are repeated row checks across checkpoints, not 60 unique public histories. Flop rows included check, call, bet, raise, and all-in actions. After the SB limped and BB checked, the BB flop root exposed bets of 1 and 2 chips. Coverage assertions occur after the report is written, preserving admissions and results if a later run misses coverage.

## Repeat, provenance, and limits

The initial metadata wording was corrected in source revision `f62369e52007a2e6da34b499bb479f038c07f0f1`. The correction clarifies that grouped-vector mode replaces only the old world-count-by-requested-iterations guard; the full-T vector estimate and remaining caps stay enforced. Numerical solve, grouping, and validation paths did not change. The original pre-correction report is preserved outside the repository at `../preflop-weighted-range-coverage-before-scope-report.json`; the corrected run repeated the same fixture and both checkpoints, with no selection based on the initial outcomes. The lead compared the old and corrected verification, rational posterior, and both action-coverage dictionaries and found them exactly equal.

The corrected report records a clean worktree at run start and 65 SHA-256 entries for source, imported harness/oracle dependencies, and configuration. All 65 hashes were verified after the rerun. The measured source revision is recorded in the report; repository HEAD may advance after publication. Fourteen focused tests passed; final cross-version CI was pending when this document was drafted.

Each checkpoint has one descriptive complete-solve-plus-JSON timing. The timer includes physical enumeration/ranking, tree construction, admission, grouping, training, and exact diagnostics; preallocated runouts, pre-call garbage collection, and independent replay are excluded. These are single-run timings, not a speed comparison. No memory measurement was made.

This result covers one weighted three-combo-per-player fixture, one 10-chip stack, two selected flops, 4,704 ordered future candidates, 27,720 compatible physical worlds, and forced checkdown after flop betting. It does not establish broad-range or full-deck coverage, all-streets behavior, multiway correctness, unrestricted no-limit hold'em performance, or a universal equilibrium/convergence guarantee.

## Artifacts

- [Benchmark harness](../scripts/benchmark_preflop_weighted_range_coverage.py)
- [Frozen specification](../benchmarks/preflop-weighted-range-coverage-v1.json)
- [Corrected result report](../benchmarks/results/preflop-weighted-range-coverage-v1.json)
