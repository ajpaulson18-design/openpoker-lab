# Two selected flops with complete future deals

`solve_preflop(..., traversal="public-batched", diagnostics="public-batched", resource_model="public-vector", tree_admission="vector")` explicitly admits larger aggregate preflop trees through structural vector budgets. Default admission and zero-delay solver paths are unchanged. Only the aggregate 10,000-decision guard is replaced. The 250,000-public-state ceiling, transient per-flop template guards, view-copy guard, 1,000,000 information-set action slots, 250,000 prefix edges, 2,000,000 dense slots and 500,000,000 modeled loop ceiling remain.

For positive averaging delay, the preflop-local CFR+ adapter caches its current profile and rematches only the player rows changed by each regret sweep. It skips zero-weight average traversals. Every row is matched once initially and once per completed sweep; training has `2T` regret traversals and `T-D` average traversals. The output preserves exact policy numbers and row order, including weighted asymmetric private ranges and dense index holes. The distinct delayed-v2 structural envelope covers this schedule; default zero-delay v1 admission remains unchanged.

The frozen [specification](../benchmarks/preflop-two-complete-flops-v1.json) and [harness](../scripts/benchmark_preflop_two_flops.py) define two canonical flops, `2c 3c 4d` and `5h 6s Jc`, each with all 2,352 ordered turn/river candidates. SB has `AsAd,QsQd` and BB `KsKd,JhJc`; the finite starting stack is two chips, preflop raises and explicit all-in actions disabled. The second flop blocks `JhJc`. Joint conditioning yields 11,880 physical worlds, four compatible private pairs, 18,354 public decisions and 30,128 information sets. Each BB-K pair has probability 1/3 and each BB-J pair 1/6, rather than a uniform flop mixture. This fixture is rejected by default aggregate decision admission.

Independent configured-numeric policy replay checks every serialized information set, hidden-card histories, physical posteriors, profile value and both complete legal visible-information best responses. Exact BR means exact enumeration for the configured binary64 finite game, with floating-point tolerances; it does not imply an exact-decimal or unrestricted Hold'em equilibrium.

The predeclared target is 0.005-chip NashConv, with `1e-10` padding in target checks. Both checkpoints are retained:

| Iterations / delay | Independent NashConv chips | Target met | Complete seconds |
| --- | ---: | --- | ---: |
| 50 / 25 | 0.0131656641915 | No | 65.428 |
| 90 / 45 | 0.00244660172582 | Yes | 115.791 |

The 90-iteration estimate is 442,826,722 modeled loop entries, below the unchanged 500-million limit. The historical complete first-flop 160/delay80 profile retains its independently replayed 0.000798537889384 gap; the new run compares historical accuracy only, not historical timing.

Three paired complete-call comparisons at fixed-flop 40/delay20 produced exactly equal serialized policies. Original times were 35.313, 40.348 and 38.193 seconds; optimized times were 30.874, 30.123 and 30.047 seconds. Observed medians are 38.193 versus 30.123 seconds, a 1.268 ratio (about 21% lower observed elapsed time) for this fixture. The separate ten-iteration two-flop complete-call peak was **76,511,888 traced Python bytes** (about 73.0 MiB), with the exclusions below. This is neither RSS nor a high-iteration guarantee.

The [frozen report](../benchmarks/results/preflop-two-complete-flops-v1.json) started clean at source `4f9f9c94e3fd53cd87f72cbcdf4c504a49419a97`, with 50 source hashes plus specification/prior-report hashes rechecked unchanged. Both measured profiles and the memory call were independently replayed; maximum reported scalar disagreement is 1.57e-14. The full local suite passed 549 tests. GitHub Python 3.11/3.12/3.13 passed 549 tests each; 3.11 has three expected instrumentation skips, while 3.12/3.13 exercise those bounds.

## Measurement and provenance boundaries

Three alternating pairs compare our frozen prior adapter with the optimized adapter at 40 iterations/delay20 on the complete fixed first-flop game. Both include complete solving, exact production diagnostics, their own applicable conservative admission and JSON serialization; pre-call garbage collection and independent replay are excluded. Policies must compare exactly. Medians on one shared host are observed timing evidence, not a statistical or universal speedup, equal-time convergence claim or unrestricted solver comparison.

A separate two-flop complete call at ten iterations/delay5 is measured under `tracemalloc`, including construction, training, diagnostics and JSON serialization. Runout arguments are preallocated; independent replay, native allocations and RSS are excluded. It supplies no higher-iteration memory guarantee. Source/specification/prior-report hashes are recorded from a clean frozen commit and rechecked after measurement.

The delay rule follows [Tammelin's CFR+ paper](https://arxiv.org/pdf/1407.5042), with this repository's established completed-alternating-sweep own-reach averaging. Selective rematching and omission of mathematically zero updates are independently implemented local optimizations; this is not a verbatim reproduction of Algorithm 1. The timing reference is our own earlier implementation preserved in tests. No third-party source, dependencies, commercial outputs or trained policies were incorporated. Luna implemented and tested the bounded adapter optimization and budget checks; lead integrated the admission, independent poker checks and measurements. Luna reviewed resource and measurement methodology, including correction of baseline work accounting.

Full-deck preflop, broad ranges, multiway and unrestricted no-limit solving remain outside this milestone. Shared postflop/turn/river kernels and the AI Coach workstream are unchanged.

```text
python -m unittest tests.test_preflop_tree_admission tests.test_preflop_delayed_cfrplus tests.test_preflop_vector_budget -v
python -m scripts.benchmark_preflop_two_flops
```
