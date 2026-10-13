# Preflop raise and action coverage

This fixed experiment extends the bounded heads-up flop-checkdown game with two preflop raise sizes, up to three voluntary raises, and all-in actions. The six cases combine starting stacks of 6 and 10 chips with 250, 500, and 1,000 requested CFR+ iterations at half delay. Every case keeps the same two private hands per player, two selected flops, all 4,704 ordered future candidates, 11,880 compatible physical worlds, and the richer flop action set: half-pot and pot bets, half-pot raises, one raise, and all-in. Future streets remain forced checkdown.

The requested preflop sizing fractions produce distinct SB root raises to 2 and 3. The tree then permits the BB to 3-bet and the SB to 4-bet. At stack 10, the concrete sequence is SB raise-to-2, BB raise-to-4, SB raise-to-8. At stack 6, the SB's response after the same open and 3-bet is an all-in to 6. The serialized action coverage contains both opening sizes, BB 3-bets, SB 4-bets, regular SB 4-bets at stack 10, and preflop all-ins. After three voluntary raises, the report checked 72 serialized decision rows across checkpoints and private-hand rows; those are repeated row checks, not 72 unique public histories. No row after the cap offers another raise or all-in.

All six configurations were preflighted in both legacy and grouped-vector modes before training. Grouped mode admitted all six. Legacy mode admitted the 250-iteration cases and rejected the four higher-iteration cases at the existing world-iteration guard. All grouped cases retained the full requested iteration ceiling in the vector-work budget:

| Stack | Iterations / delay | Vector loop envelope | Independent NashConv | 0.005 target |
| ---: | ---: | ---: | ---: | --- |
| 6 | 250 / 125 | 7,333,195 | 0.00540492091679 | Miss |
| 6 | 500 / 250 | 14,068,195 | 0.00143979238733 | Met |
| 6 | 1,000 / 500 | 27,538,195 | 0.0000183142814747 | Met |
| 10 | 250 / 125 | 17,331,364 | 0.00139741139795 | Met |
| 10 | 500 / 250 | 34,008,864 | 0.000581248760732 | Met |
| 10 | 1,000 / 500 | 67,363,864 | 0.000140497566782 | Met |

The target is evaluated as `NashConv + 1e-10 <= 0.005` for each case. The stack-6 250-iteration miss remains visible. Every completed grouped policy was independently replayed over all original physical worlds using numeric betting rules and exact legal best responses by visible information set. The maximum production-to-oracle scalar discrepancy was **2.22e-16**. The stack-6/250 grouped result also exactly matched the legacy result's serialized policy, physical outputs, and scalar diagnostics.

The trees grew from **280 public states, 108 decisions, and 193 information sets** at stack 6 to **694 states, 262 decisions, and 466 information sets** at stack 10. Grouped training retained 16 world rows. No target miss or admission rejection was removed from the matrix.

One descriptive complete-call-plus-JSON time was recorded per grouped case: 3.465, 4.632, and 8.219 seconds at stack 6; 6.646, 12.141, and 22.851 seconds at stack 10. Each includes physical enumeration/ranking, tree construction, admission, grouping, training, exact diagnostics, and JSON serialization; preallocated runouts, pre-call garbage collection, and independent replay are excluded. This is a single timing per case, with no speed or memory comparison and no RSS claim.

The [raw report](../benchmarks/results/preflop-action-coverage-v1.json) records **61 source/spec hashes**, a clean source revision `120df696539891d6952ef1fe92c3fe75ecedbeb8`, full admission records, action exemplars with complete public histories, independent replay metrics, and payload digests. The harness rechecks source hashes and repository cleanliness before writing the report. The solver retains the existing tree, state, action, physical-world, and vector-work caps; this experiment does not raise limits or simplify rejected cases.

This is evidence for one narrow finite game with two narrow ranges and selected flops. It does not establish all-streets play, full-deck or broad-range solving, multiway play, unrestricted no-limit Hold'em, or a general convergence guarantee. It introduces no shared postflop/turn/river kernel, Coach, third-party source, or dependency changes.

The [frozen specification](../benchmarks/preflop-action-coverage-v1.json) and [harness](../scripts/benchmark_preflop_action_coverage.py) reproduce the full matrix with `python -m scripts.benchmark_preflop_action_coverage`. Luna drafted the isolated harness/spec and reviewed the frozen methodology and raw report; lead reviewed coverage/admission/timing, checked false-positive coverage cases and measured the unchanged matrix. Syntax/spec checks, coverage smoke checks and all six independently replayed solves passed. Final-head full Python CI and presentation checks must pass before merge.
