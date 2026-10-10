# Preflop and flop betting with an explicit checkdown continuation

`solve_preflop(..., postflop_scope="flop-checkdown")` solves a distinct finite game: heads-up preflop betting, selected physical flop chance, configured flop betting, then forced checking through showdown. Selected turn/river outcomes remain hidden throughout every decision and are integrated by their physical joint mass and final-board rank. This isolates flop/preflop decisions while the shared turn/river workstream remains separate. It does not solve the [blocked all-streets raised game](preflop-raised-coverage.md).

This opt-in currently requires positive-delay CFR+, `traversal="public-batched"`, `diagnostics="public-batched"`, and `resource_model="public-vector"`. Turn/river action configs are rejected before physical enumeration. The default `postflop_scope="all-streets"` path and payload are unchanged. Optional compact private indices and exact convergence stopping retain their existing constraints and full-ceiling admission.

```python
from pokerlab.preflop_solver import solve_preflop

result = solve_preflop(
    "AsAd,QsQd", "KsKd,JhJc",
    config={"starting_stack": 3, "raise_sizes": [0.5],
            "max_raises": 1, "include_all_in": False},
    runouts=["2c3c4d7h8h", "2c3c4dKc8s"],
    postflop_scope="flop-checkdown", iterations=90, averaging_delay=45,
    algorithm="cfrplus", traversal="public-batched",
    diagnostics="public-batched", resource_model="public-vector",
)
```

This example conditions on two selected complete outcomes; it does not enumerate every legal future. The separate frozen benchmark below uses complete future candidates for two selected flops.

The result identifies `solver_version="preflop-flop-checkdown-v1"` and `postflop_scope="flop-checkdown"`. The structural row schema remains `preflop-strategy-v1`; rows contain only preflop/flop histories, and `postflop_action_configs` contains only the active flop configuration. There are no turn/river strategies to export. Values and exact legal best responses describe the checkdown game; later-street betting deviations are outside its action set.

Implementation reuses the existing one-street configured betting builder with flop pot/stacks, then the existing preflop graft, trainer and diagnostics. No shared postflop/turn/river kernel changed. Full selected outcomes, blockers, global player identities, refunds, action sizing/rounding and physical priors remain. Every original candidate/world/public-state/transient-template/view/prefix/action-slot/work guard remains active. Removing future decisions is an explicit model restriction, not a resource-limit bypass.

Independent numeric replay settles after flop betting and sums the hidden complete-world outcomes. It checks every serialized information set, action/amount/target, profile value and both visible-information best responses without importing production tree, utility, rank or evaluation helpers. Replay requires a matching explicit scope. Regression coverage includes opposite hidden winners on the same flop, weighted blocked/asymmetric ranges and short-call refunds, unchanged default payloads, early mode rejection, guards before training/view allocation, and compact-index convergence checkpoints.

A cross-model regression copies the flop-checkdown policy into a tiny all-streets game and forces the future policy to check. Its independently replayed profile value agrees. All-streets best responses can deviate later and are bounded below by the checkdown best responses; the two equilibrium problems are not presented as equivalent.

## Frozen measurement

The [specification](../benchmarks/preflop-flop-checkdown-v1.json) fixes three-chip stacks, an open or limp-raise to two chips, default flop actions, SB `AsAd,QsQd`, BB `KsKd,JhJc`, and flops `2c3c4d` and `5h6sJc`. All 2,352 ordered turn/river candidates per flop are supplied. Blocking and joint conditioning create 11,880 physical worlds from 4,704 candidates. The second flop blocks BB `JhJc`, so private-pair priors are not uniform.

Before training, checkpoints were fixed at 20/delay10, 90/delay45 and 250/delay125 with a 0.005-chip NashConv target plus 1e-10 padding. The 250-iteration ceiling charges 2,970,000 world iterations, below the unchanged three-million guard. All checkpoints and target misses are retained. Three complete 90/delay45 calls plus serialization measure observed runtime on one host; a separate 10/delay5 call measures traced Python allocations. Input runouts are preallocated; pre-call GC and independent replay are excluded from timing. Native allocations/RSS and higher-iteration memory guarantees are excluded. No speed comparison to the rejected all-streets game is made.

The [frozen report](../benchmarks/results/preflop-flop-checkdown-v1.json) started clean at source `d0fee0277569a2606240fc29f33130ce6e8c68d2`. The [harness](../scripts/benchmark_preflop_flop_checkdown.py) rechecked all 52 source hashes and the specification hash unchanged. The game has 76 public states, 32 decisions and 57 information sets. Every unique accuracy/memory policy was independently replayed; maximum scalar discrepancy was 2.34e-14.

| Iterations / delay | Independent NashConv chips | 0.005 target met | Complete-call seconds |
| --- | ---: | --- | ---: |
| 20 / 10 | 0.0305124842686 | No | 0.836370 |
| 90 / 45 | 0.00123906973909 | Yes | 0.881667 |
| 250 / 125 | 0.000171726323754 | Yes | 1.111549 |

The three complete 90/delay45 calls took 0.881667, 1.433973, 1.000152 seconds; the median was **1.000152 seconds** and serialized policies were exactly equal. This is a single-host measurement, not a universal speed or statistical claim.

The separate 10/delay5 call peaked at **13,873,072 traced Python bytes**. Its independent NashConv was 0.175182033386, missing the quality target; memory measurement is not accuracy evidence for the higher-iteration policies. The largest requested vector envelope (250/delay125) was 2,100,587 modeled loop entries below the unchanged 500-million limit, with all original physical-world guards retained.

Local validation passed 23 focused tests, then the full **592-test** suite in 217.449 seconds with a verified writable isolated SQLite temporary directory. Eight new tests cover the scope, hidden outcomes, independent value/BR checks, cross-model profile value, weighted refunds, early guards, default parity and compact/convergence interactions.

## Provenance and limits

Luna implemented and tested the bounded production mode. Lead implemented the independent replay extension, cross-model/checkpoint regressions and frozen measurement. All work composes this repository's own standard-library code; no third-party source/dependencies, proprietary policies or commercial outputs were incorporated. Shared turn/river kernels, AI Coach and the visual interface are unchanged.

This is a conditioned finite heads-up preflop/flop game with narrow ranges and forced checkdown. It establishes no all-streets equilibrium, full-deck preflop, multiway, unrestricted NLHE, broad-range accuracy or general performance claim. Exact diagnostics mean complete enumeration of the configured binary64 finite game with numerical tolerances, not a formal floating-point or exact-decimal certificate.

```text
python -m unittest tests.test_preflop_flop_checkdown -v
python -m scripts.benchmark_preflop_flop_checkdown
```
