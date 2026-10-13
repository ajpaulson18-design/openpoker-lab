# Grouped preflop target-plan reassessment

This research experiment reuses the unchanged [target-plan helper](../scripts/preflop_target_plan_prototype.py) on the independently verified [expanded weighted game](preflop-expanded-range.md). It does not integrate a new production backend.

The [earlier experiment](preflop-target-plan-prototype.md) used 20 sweeps on an all-streets tree with 59,448 plan records, missed the quality target and failed its 5% runtime gate. Its negative report is preserved. This new fixture has 1,300 public states, 108 grouped physical-world rows and 1,744 information sets, with 1,000 sweeps already independently meeting quality. The changed setup and training proportions justify a separately frozen experiment; they do not establish a speedup.

## Fixed comparison

The [specification](../benchmarks/preflop-grouped-target-plan-v1.json) declares three alternating baseline/candidate pairs at 1,000 iterations and delay 500. The same four weighted private hands per seat, four selected flops, 10-chip stack and rich preflop/flop action tree apply to both arms. All 91,080 original physical worlds govern the independent replay. Futures remain hidden and betting ends at the flop, followed by forced checkdown.

Both arms enter their patch context before garbage collection and timing. The candidate compiles once on the first target-delta pass, verifies stable root/edge/info identity and performs exactly 2,000 target passes. Compilation, the complete solve, final exact diagnostics, JSON serialization and plan release count toward timing. The plan remains alive through JSON. Input preparation and independent replay are outside timing, and no prior policy is retained between arms.

Promotion to further production-admission work requires exact full-payload parity across all six timing arms, independent accuracy success in every timing arm, a faster candidate in every pair and at least 5% median paired reduction. A separate allocation pair at 10 iterations/delay 5 requires exact payload parity and candidate Python-traced peak no greater than 1.01 times baseline. This is a bounded allocation nonregression gate, not an RSS or general memory-saving claim.

## Results

| Pair | Baseline seconds | Candidate seconds | Reduction |
|---|---:|---:|---:|
| 1 | 52.183673 | 53.763880 | -3.0282% |
| 2 | 52.091079 | 47.920809 | 8.0057% |
| 3 | 51.719916 | 47.796194 | 7.5865% |

The median paired reduction was **7.5865%**, but pair 1 was slower. The frozen requirement that every pair improve failed, so **the experiment gate is false**. The candidate remains a research helper and is not adopted. No retry or replacement of the negative result was performed.

All six timing arms had exactly the same complete serialized payload hash. Each independently replayed all 91,080 physical worlds and checked all 1,744 information sets. Every arm had NashConv 0.0002388792222732805, meeting the unchanged 0.005 target with 1e-10 padding. The maximum production/oracle metric difference was 1.1102230246251565e-16.

At 10 iterations/delay 5, baseline and candidate Python-traced peaks were 36,504,962 and 36,504,938 bytes. The 24-byte difference is not evidence of a memory saving. The separate 1.01x nonregression gate passed and the two full payload hashes matched. Both short arms missed quality with NashConv 0.664786689496687; their maximum production/oracle metric difference was 3.3306690738754696e-16. Traced-arm runtimes are not used in the timing comparison.

## Admission and limits

The helper retains its standalone census-before-compilation caps for records, information rows, keys, children and terminal-edge references. Each candidate used 1,300 records (494 decisions, 15 chance nodes, 791 terminals), 1,744 information-row references, 1,976 key references, 1,299 child references and 9,247 terminal-edge references. Candidate target-pass counts were exactly 2,000 for timing and 20 for allocation. The unchanged original-world plus grouping envelopes were 235,369,982 modeled loop entries for timing and 6,812,642 for allocation. These are logical dimensions, not bytes. Both timing and allocation solver cases are preflighted, and each actual original-world vector budget must match its full-requested-iteration preflight.

The production vector budget does **not** charge the prototype census, compilation, retained records, information-row partitions or temporary conversion overlap. Even a passing experiment requires a separate independent versioned workload/allocation envelope before production integration. No production or shared postflop/turn/river code, Coach work or dependency changed here; no third-party source was incorporated.

This is one fixed conditioned heads-up preflop/flop game on one host. Neither these timings nor successful finite-game replay establishes broad-range, full-deck, multiway, later-street betting or unrestricted NLHE performance or convergence. The 1e-10 quality padding is conservative, not a formal floating-point error bound.

## Provenance and reproduction

The frozen source is `fc4edfb54e6deb5181967891d4ef0c72cef771f8`; 74 source/specification hashes were checked unchanged at start and end. The previous verified-game source is an ancestor, and its complete source manifest was rechecked. The [raw report](../benchmarks/results/preflop-grouped-target-plan-v1.json) retains all timings, replay metrics, target results, hashes, preflights, plan counts and gate failures.

Luna reviewed the bounded comparison design. Lead reused the existing helper, checked benchmark wiring, froze and measured the experiment. The five existing plan regression tests passed before measurement. Luna and lead independently rechecked the saved report, all 74 hashes, paired gates, posterior/accuracy results, plan dimensions and original-world budgets. Both reviews were clear and retained the failed gate. Full CI results are recorded in the pull request.

After checking out the frozen revision with a clean worktree:

```powershell
python -m scripts.benchmark_preflop_grouped_target_plan
```

A failed gate is saved before the harness exits with status 1. It must remain visible; it is not a request to retry the same fixture.
