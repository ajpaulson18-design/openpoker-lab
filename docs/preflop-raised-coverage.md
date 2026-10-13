# Non-all-in preflop raise coverage: structural admission evidence

The frozen [grid](../benchmarks/preflop-raise-admission-grid-v1.json) measures structural admission for SB `AsAd,QsQd` and BB `KsKd,JhJc`, starting stacks 2.25, 2.5, 2.75 and 3 chips, and one or two selected flops (`2c3c4d`, then `5h6sJc`). Preflop has one half-pot raise increment, no explicit all-in action, and blinds 0.5/1. Both an SB open and a BB raise after a limp target two chips. Calling leaves positive chips in every listed configuration. The BB option after a limp and the one-raise ceiling are preserved.

Postflop retains the solver defaults: half-pot bets, no raises, explicit all-in enabled on all three streets. Each selected flop includes all 2,352 ordered turn/river candidates. One flop creates 7,920 compatible private-pair/outcome worlds; two create 11,880. The second flop blocks BB `JhJc`, so these are conditioned joint games rather than equal-weight independent flop samples.

**All eight configurations are rejected** by the unchanged per-flop 10,000-decision template limit, before independent vector admission, vector-view allocation or training. Reducing stacks across this grid does not remove the bottleneck. No policy, convergence, runtime or memory result follows from these probes. The predeclared 0.005-chip quality target was not tested or relaxed. No production guard or shared kernel changed.

The authoritative [grid report](../benchmarks/results/preflop-raise-admission-grid-v1.json) started clean at source `dddc5605a02b7b7b465ef99382316ff92c5c7754`, with source/specification hashes checked before and after all eight cases. Its [runner](../scripts/probe_preflop_raise_grid.py) retains every failure and forbids training/view allocation. The separate [original three-chip report](../benchmarks/results/preflop-raise-admission-probe-v1.json) records base `9071038` and distinguishes its later dirty-worktree reproduction from that base. It is supporting history, not the clean frozen grid.

```text
python -m scripts.probe_preflop_raise_grid
python -m scripts.probe_preflop_raise_admission
python -m scripts.probe_preflop_raise_admission --starting-stack 2.5 --output ../preflop-raise-2p5.json
```

The grid runner requires the frozen source/spec in a clean checkout. A rerun at a later commit records that later revision; compare source hashes as well as results. The single-stack runner records dirty status honestly and retains the exact three-chip rejection assertion only for its original fixture. A tiny single-future smoke exercised the admitted branch and the additional iteration censuses without training; it is not complete-future quality evidence.

Luna implemented the single-stack probe and checked both admitted/rejected interception paths. Lead reviewed error classification and provenance, froze the grid and selection rule, and ran all eight cases. These scripts compose this repository's existing code using only the standard library. No third-party source, dependencies, commercial output, shared postflop/turn/river kernel changes or AI Coach changes were incorporated.

The next flop/preflop milestone must explicitly distinguish its action model from this blocked all-streets game. A checkdown continuation can be useful for isolating flop decisions, but it would not resolve this three-chip all-streets admission failure or establish unrestricted Hold'em accuracy.
