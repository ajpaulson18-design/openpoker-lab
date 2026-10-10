# Preflop target-delta plan experiment

The [frozen specification](../benchmarks/preflop-target-plan-prototype-v1.json) evaluates a reusable preflop-owned description of the existing CFR+ target-delta traversal. The [prototype](../scripts/preflop_target_plan_prototype.py) is a research helper; production solvers do not select it. Shared postflop, turn and river kernels are unchanged.

A prior complete two-flop 10/delay5 cProfile run attributed 13.393 of 32.826 instrumented seconds to target-delta passes, with 9.297 seconds in visitor internals. Averaging accounted for 2.372 seconds. This profile motivated testing repeated node classification, prefix/key construction and terminal payoff setup. Instrumented times are selection evidence, not a speed comparison.

The prototype compiles node kinds, ordered children, dense information-set keys and terminal payoff/edge references once. Its executor retains recursive traversal, target/opponent reach semantics and the original binary64 arithmetic/accumulation order. It preflights cycles, types and record/key/child/information-row/terminal-edge reference caps before allocating the compiled plan. Per-player information rows are partitioned only after the census succeeds. No third-party source or dependencies are used.

The experiment compares the same complete two-selected-flop conditioned game in both arms: SB `AsAd,QsQd`, BB `KsKd,JhJc`, two-chip starting stacks, no preflop raises or explicit all-in actions, canonical flops `2c3c4d` and `5h6sJc`, and every ordered future deal for each flop. Joint conditioning/blockers remain unchanged. Three alternating timing pairs use 20 iterations/delay10. Every final policy is independently replayed from numeric poker rules and complete legal visible-information best responses; both arms must have exactly equal serialized policies, row order and diagnostic values.

The predeclared runtime gate requires at least 5% lower median complete-call time, including compilation/census, construction, training, final exact production diagnostics and JSON serialization. Runout arguments are preallocated; pre-call garbage collection and independent replay are excluded. One shared host and three pairs establish no universal speedup. The unchanged 0.005-chip target is recorded even if these short fixed schedules miss it. This experiment expects identical accuracy, not improved convergence.

Separate reference and planned ten-iteration/delay5 complete calls are traced with `tracemalloc`, including compilation and the prototype retained through final diagnostics/JSON. The earlier reference policy is held during the planned trace but was allocated before that trace starts. The reported peaks therefore concern new traced Python allocations, not all live memory, native allocations or RSS; no high-iteration guarantee follows.

The frozen source is `f055752f39c04c818873d08f19c09270102837ea`. All three paired policies and diagnostic values matched exactly. The observed median complete-call times were about 30.187 seconds for the reference and 29.615 for the plan, a reduction of about 1.9%. **The predeclared 5% runtime gate was not met. The plan is not integrated into production.** This negative result narrows future work: precomputing these tree details alone did not establish sufficient benefit on this workload.

The [frozen report](../benchmarks/results/preflop-target-plan-prototype-v1.json) records 52 source hashes and the specification hash, rechecked unchanged after measurement from a clean start. Pair times in reference/planned order were 30.187/29.615,32.030/29.648 and29.254/29.360 seconds. The third pair was slightly slower with the plan. Every final policy, row order and production diagnostic matched exactly; maximum reported disagreement with independent scalar replay was 2.95e-15.

The separate complete-call Python peaks were **76,510,056 bytes for reference** and **91,469,268 bytes for planned** (about 73.0 versus 87.2 MiB), under the allocation scope above. The experiment adds about 15.0 million traced peak bytes on this fixture, for insufficient measured timing benefit. This comparison is not RSS or a general memory bound.

The compiled plan recorded 59,448 records (18,354 decisions, 487 chance nodes, 40,607 terminals), 36,708 dense key references, 59,447 child references, 30,128 information rows and 107,476 repeated terminal-edge references. These are logical dimensions, not bytes. Both 20-iteration timing arms had independently replayed NashConv 0.0500238937425; both ten-iteration memory arms had 0.0947992878543. All miss the retained 0.005 target. This short workload tests performance and policy parity, not convergence improvement.

The frozen-source GitHub suite passed 567 tests on Python 3.11/3.12/3.13, with four instrumentation skips on 3.11 and none on 3.12/3.13; frontend checks passed. Five focused prototype tests and the weighted whole-solve smoke check passed locally. Luna implemented the prototype and focused tests, corrected preallocation partition accounting after lead review, and reviewed the frozen measurement methodology and report. Lead owned whole-solve replay, the frozen benchmark and the rejection decision.

The existing solver work budget excludes the prototype census, compilation and retained-plan storage. The helper's standalone caps do not substitute for production admission. Even a runtime-gate pass requires an independent versioned census before training-view/plan allocation, including temporary list-to-tuple overlap and information-row partition storage. Existing resource caps must remain in force.

Five focused tests cover both-player exact delta parity under weighted public chance, repeated terminal prefixes, dense private-hand holes and missing strategy rows; cap rejection before record/partition allocation; cyclic/unsupported trees; finite numeric validation; and prompt reference cleanup. An eight-world weighted asymmetric complete-solve smoke test also matched full policies/diagnostics exactly and passed independent replay.

Full-deck preflop, broad-range scalability, multiway and unrestricted no-limit Hold'em remain outside this experiment. Exact best responses refer to the configured finite binary64 game with numerical tolerances, not a formal floating-point or exact-decimal certificate. AI Coach is unchanged.

```text
python -m unittest tests.test_preflop_target_plan_prototype -v
python -m scripts.benchmark_preflop_target_plan_prototype
```
