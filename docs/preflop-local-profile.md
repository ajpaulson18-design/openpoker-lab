# Preflop local profile v1

This is a single-location profile of the weighted preflop/flop-checkdown fixture. It is diagnostic evidence for choosing a follow-up investigation, not a speed comparison or a claim that a proposed optimization will help.

## Frozen run

The profile was captured on source revision `62b6e9d0123456cdf73dfac9f59f866860ddba58` with Python 3.12.14 on Windows 10. All 68 source and specification hashes recorded in the report match. The capture began on a clean worktree and rechecked revision and all hashed inputs before saving. Publication commits advance HEAD while preserving the recorded measured source.

The harness ran one 500-iteration CFR+ solve with averaging delay 250. cProfile covered the solver call and JSON serialization. The measured wall time was 23.474 seconds and the profiler accumulated 23.457 seconds of function self time. It did not collect memory data, run paired timing arms, or measure RSS.

The solve passed the configured independent replay check: NashConv was `0.0005477015116682749`, below the unchanged `0.005` target. All 728 information sets were checked. The maximum posterior probability difference from the rational audit was `1.03e-14` for the independent oracle and zero for the solver output, both within `1e-12`.

## Where the profile spent time

Summing exclusive self time over the exact file `pokerlab/preflop_delayed_cfrplus.py` gives 3.55984 seconds out of 23.45698 seconds, or 15.176%. This exceeds the frozen 10% materiality marker. The marker only identifies a component for further review; it does not establish an optimization opportunity.

The largest individual self-time row was the shared `public_cfr.visit`: 8.547 seconds over 694,000 calls. Its 11.848-second cumulative time includes nested work. The shared `_cfrplus_target_deltas` wrapper accumulated 12.214 seconds over 1,000 calls, also inclusive of recursive visits. These cumulative values overlap and must not be added together.

Inside the preflop adapter, `train_delayed_public_cfrplus` used 1.795 seconds self time and 18.528 seconds cumulative time. Its average traversal's recursive `visit` used 1.763 seconds self and 2.302 seconds cumulative over 173,500 calls; this is a nested subset of the trainer's cumulative time. The shared `cfr.strategy` function used 1.049 seconds self and 1.717 seconds cumulative across 364,728 calls. Those figures likewise overlap with traversal totals.

Other notable exclusive costs were dictionary `get` calls (1.324 seconds), built-in `sum` (1.273 seconds), and built-in `max` (0.995 seconds). The profile therefore points to substantial recursive shared traversal work and some adapter-owned traversal/strategy setup. It does not justify changing the shared kernel or claim a whole-call speedup.

## Bounded next hypothesis

A possible adapter-only experiment is to check whether CFR+'s nonnegative regret rows can be normalized by direct summation in this adapter, avoiding repeated clamping in the shared `cfr.strategy` path. This is only a hypothesis: it must preserve output probabilities and arithmetic behavior exactly, including zero rows, and would require a frozen whole-call pair with an explicit improvement gate before adoption. No such change is included here.

## Scope limits

The game is finite and conditioned: three weighted exact private combinations per player, two selected flops, 4,704 ordered future candidates, 27,720 compatible physical worlds, a shared 10-chip stack, preflop raises/all-ins, rich flop actions, and forced checkdown after flop betting. It is not broad-range or full-deck preflop, all-streets, multiway, unrestricted no-limit Hold'em, or a general convergence result. The profile is one instrumented call; its runtime is not a performance benchmark.

## Reproduction artifacts

- [Frozen specification](../benchmarks/preflop-local-profile-v1.json)
- [Raw profile and replay](../benchmarks/results/preflop-local-profile-v1.json)
- [Harness](../scripts/profile_preflop_local_costs.py)

Run `python -m scripts.profile_preflop_local_costs` from a clean frozen checkout to reproduce the capture. Luna drafted and reviewed the isolated harness and audited the report; lead reviewed attribution/privacy, added auditable complete function records and measured the fixed case. Syntax/specification, path-sanitization and exclusive-attribution smoke checks passed, followed by the complete original-world replay and rational posterior checks. Final-head cross-version CI and presentation checks must pass before merge. No production, shared postflop/turn/river kernel, Coach, third-party source or dependency changes.
