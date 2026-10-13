# Preflop private-index compaction

`solve_preflop(..., private_indexing="compact")` is an opt-in preflop optimization for positive-delay CFR+ with `traversal="public-batched"`, `diagnostics="public-batched"` and `resource_model="public-vector"`. The default remains `"original"`, with its previous result fields and budget versions. Other combinations are rejected before physical-world enumeration.

Expanded ranges can contain hands that are incompatible with every opponent hand or every selected physical outcome. Original indices retain those holes, making dense vectors larger than the actual game. Compaction sorts each player's globally active original indices and maps them to consecutive indices. It preserves world order, physical joint masses, signs, future-card fields, public histories, information-row insertion order and all arithmetic accumulation order. Training, exact diagnostics and convergence checkpoints use the compact view. Policy keys are restored to their original identities and order before serialization; returned hand labels and posterior pair probabilities stay unchanged.

This removes globally inactive slots only. A hand that is inactive under one public prefix but possible elsewhere stays in the global compact dimension. It changes no ranges, continuation values, action sizes or selected-outcome conditioning. It is independently implemented using this repository's data structures, with no third-party source or new dependencies. Shared postflop/turn/river kernels and AI Coach are untouched.

Before copying, the independent `preflop-public-vector-private-compact-budget-v4` census reserves actual compact dense dimensions, the existing work/prefix/action limits, additional copy/restoration loop entries and at most 8,000,000 logical compact-copy reference slots. The reference allowance is `128 + 4F + 4W + 12I + 16H`, with world-field count F, world rows W, information rows I and active hand-count sum H. It includes temporary copy overlap, mapping and ordering storage and policy restoration; object headers, allocator behavior and process RSS are excluded. The helper separately caps 3,000,000 world rows, 25,000,000 fields, 500,000 information rows, 1,000,000 action slots and 1,326 active hands per player. Original tree, world, candidate, copy-view and iteration guards remain in force. Admission reserves a requested convergence ceiling and every possible checkpoint before any early stopping.

Compact copies are local to one solve and released after diagnostics/restoration, including error paths. Output includes `private_indexing="compact"` and `private_indexing_metadata` recording original/compact dimensions, active original indices and logical copy counts. Budget fields separately record copy/reference allowances; they are not byte counts, timings or memory guarantees.

The [frozen specification](../benchmarks/preflop-private-compaction-v1.json) compares complete calls on a conditioned two-selected-flop game with all ordered future deals. SB has twelve leading As-containing hands blocked by both BB hands, then `QsQd,JcJd`; BB is `AsAd,As2d`. The original dimensions [14,2] become [2,2]. Selected flops `2c3c4d` and `5h6sJc` preserve nonuniform joint pair masses due to the Jc blocker. Starting stacks are two chips with no preflop raises or explicit all-in action.

Three alternating 20-iteration/delay10 timing pairs require exact serialized policies, row order, diagnostics and physical priors, plus independent configured-model numeric replay and complete legal visible-information best responses for every final policy. The predeclared runtime gate is at least 5% lower median complete-call time, including both censuses, copies, exact diagnostics, restoration and JSON serialization. Preallocated runout arguments, pre-call garbage collection and independent replay are excluded. A separate compact90/delay45 checkpoint records accuracy against the unchanged 0.005-chip NashConv target. It provides no runtime comparison to original90.

Separate original/compact10/delay5 calls measure new Python allocation peaks under tracemalloc. Each arm runs without retaining the other result. An exact serialized-policy/diagnostic/physical-prior digest, computed after tracing, verifies equality across separate memory phases. Native allocations, RSS, all live process memory and higher-iteration guarantees are outside that measurement. Report all target misses. A benefit on this deliberately hole-heavy shape does not imply improvement on hole-free ranges, broad ranges or other configurations.

The harness saves six completed phases atomically outside the worktree: three timing pairs, accuracy, and each memory arm. `--resume` validates the exact frozen commit, source/specification hashes, Python/platform identity and phase payload checksum before reusing work. It refuses a dirty or unverifiable source state and writes the final report only when every required phase is complete. Each phase rechecks provenance before and after measurement and records its execution timestamps. A new source revision requires a fresh state directory or checkout of the original frozen revision.

An [initial interrupted attempt](../benchmarks/results/preflop-private-compaction-interrupted-attempt.json) reached three timing pairs but lost its process before accuracy/memory completion and final hash rechecks. Its rounded console observations are explicitly incomplete and excluded from the adoption decision. The resumable harness preserves completed evidence if a later process is interrupted.

The [completed report](../benchmarks/results/preflop-private-compaction-v1.json) is frozen at source `5fd68f59c364b1dd887f537e05e17c9118f3ce97`, with 52 source hashes plus the specification hash checked before and after every saved phase. All nine final policies passed independent numeric replay and exact legal best-response evaluation. Maximum reported scalar disagreement was 1.06e-15. Every timing pair preserved exact policy numbers, row order, diagnostics and physical priors; the separate memory arms had identical serialized parity digests.

Original/compact complete-call pair times were 22.498/15.703, 26.425/19.411 and 20.607/13.176 seconds. Medians were **22.4978 versus 15.7033 seconds**, a **30.20% observed reduction**, clearing the predeclared 5% gate. This is a result for this globally blocked-hand shape on one shared host, not a universal improvement or a comparison to the interrupted attempt.

| Checkpoint | Independent NashConv chips | 0.005 target |
| --- | ---: | --- |
| Timing20 / delay10, both modes | 0.0110366448493684 | Miss |
| Memory10 / delay5, both modes | 0.0201335398398814 | Miss |
| Accuracy90 / delay45, compact | 0.00377567047243843 | Met |

The 90-iteration accuracy call took 48.858 seconds, with 11,880 physical worlds, 29,606 information sets, 17,642 decisions and 57,138 public states. Its v4 census reserved 429,568,352 modeled loop entries against the unchanged 500-million cap, plus 735,624 logical compaction reference slots against the 8-million cap. These are admission counters, not performance or RSS predictions. No original90 speed comparison was made.

Separate complete-call ten-iteration Python peaks were **74,364,817 bytes original** and **74,366,857 bytes compact**: compact was 2,040 bytes higher, essentially equal in this single trace per mode. No memory saving is claimed. Both memory phases include their own complete solving and serialization, release the other result, and compute parity digests and independent replay after tracing.

The approved local full suite passed **584 tests** in 283.649 seconds. The initial default-sandbox full run had 14 SQLite temporary-directory errors (including cleanup access errors); default-sandbox focused persistence retries also failed. All 14 affected tests passed through the approved command path, and the complete approved run used a fresh writable project-local temporary root. No persistence or Coach code was changed. Frozen-source GitHub suites passed Python3.11/3.12/3.13 and frontend checks; Python3.11 has five expected instruction-monitoring skips, while 3.12/3.13 exercise them. Lightweight harness checks verified saved-phase reuse, altered-payload/revision rejection and rejection of unavailable Git cleanliness evidence.

Luna implemented the compact view and solver integration, added independent budget tests, reviewed the admission and measurement methodology, implemented phase durability, and reviewed the final report and raw phase provenance/checksums. Lead owned admission, independent integration checks, complete-call measurement, validation and adoption. The optimization is accepted as an opt-in feature within the stated shape/model limits. Final report prose explicitly distinguishes target outcomes; numeric phase evidence is unchanged.

Tests cover weighted chance with holes in both players, independent monetary replay, physical pair conditioning, exact fixed/checkpoint policy parity, no-information-set refund diagnostics, invalid modes, cap rejection before copying/view allocation and cleanup without forced collection. Instruction monitoring checks helper copy/restoration loop entries against the modeled allowance where Python supports it. Exact best responses are within the configured finite binary64 model and numerical tolerances; they are not a formal floating-point certificate.

```text
python -m unittest tests.test_preflop_private_indices tests.test_preflop_private_index_budget tests.test_preflop_private_index_integration -v
python -m scripts.benchmark_preflop_private_compaction --phase pair1
python -m scripts.benchmark_preflop_private_compaction --resume
```

Full-deck preflop, unrestricted no-limit Hold'em, multiway and commercial solver parity remain future work.
