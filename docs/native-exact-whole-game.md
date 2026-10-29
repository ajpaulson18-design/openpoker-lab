# Native exact-product four-street training

Status: implemented opt-in whole-game backend with [two frozen studies and
independent saved-only acceptance](native-exact-whole-game-result.md). Corrected
source passes Windows/Linux/sanitizer controls; final publication CI is separate.
This connects the [native exact kernel](native-exact-selected-vectors-result.md)
to one public graph/Q plan and alternating training loop. It is distinct from
the [older rounded-chance native DAG](native-selected-dag-protocol.md) protocol.

## Explicit use

Build from current committed sources outside the checkout:

```text
python -m scripts.build_native_exact_four_street --target engine --output-dir <external-build-directory>
```

Call `solve_four_street_exact_selected` with the protocol-specific
`native_executable=` plus all of `pair_diagnostics="compact"`,
`exact_arithmetic="dyadic"`, `training_reduction="suit-equivariant"`,
`strategy_storage="suit-quotient"`, and `quotient_lookup="per-decision"`.
Unsupported combinations and stale/missing/foreign source builds reject before
preparation. There is no fallback. Defaults retain the established Python path.

Python still prepares the legal four-street betting DAG, API and conservative
old admission, including its own rank-free exact prior preparation. It separately
evaluates the returned complete policy and serializes the established strategy
contract. That preparation/diagnostic cost is part of complete-call measurement;
this boundary does not remove all Python or duplicate setup. Native performs its
own global normalization, physical support, on-demand ranking, exact payoff
vectors, row planning and complete Q learning. No Python normalizer, rank vector,
terminal vector, pair/world table, policy or trusted Q witness enters the wire.

## One native owner and numerical trajectory

[`exact_public_graph.hpp`](../native/exact_public_graph.hpp) owns immutable
role priors/ordered selected boards, public DAG and its exact kernel. It derives
the full weighted S4 stabilizer, verifies exact bottom-up public-signature closure
and fixed initial history, then streams full visible-history/own-hand rows into
Q representatives. Distinct-image ordinals handle stabilizers. Prefix support
and board-index caches are bounded by selected outcomes; no R-to-Q member table
is retained. Inactive contradictory vertex fields, cycles/unreachable vertices,
invalid ordered menus, reveals and direct-builder chance indices 4/5/6 reject.
Every chance occurrence must cover exactly the next reveals with positive
compatible selected mass; a zero-mass outcome may be absent. Otherwise a graph
could discard mass that remains in global Z.

[`exact_selected_cfr.hpp`](../native/exact_selected_cfr.hpp) performs the whole
root traversal with explicitly ordered finite binary64 arithmetic, canonical
positive zero and sorted per-hand chance reductions. Each iteration rematches,
updates SB, rematches, updates BB, rematches, then averages with the original
iteration weight and own sequence reach/marginal. Every distinct supported
member participates at zero reach too. It stages the first orbit increment,
checks every member's exact bits and complete mask, prevalidates all prospective
persistent values, then commits once. It neither sums nor divides orbit updates.

The trainer retains four Q-action arrays. It normalizes the existing average
array in place, releases regrets/current/deltas and member masks, then transfers
the remaining compact Q policy. The [process driver](../native/exact_four_street_train.cpp)
streams full R rows only afterward; it does not retain an expanded policy table.
Python output and diagnostics remain expanded. A single-use trainer rechecks
nearest rounding, preservation of subnormals and fresh cumulative kernel work
at run entry. Callers must use the plan/kernel exclusively during that run.
Local binary64 subnormals are permitted; completed exact callbacks keep their
separate strict finite-normal conversion boundary.

## Whole-request admission and transport

All old expanded R geometry, sorted-chance, Q-plan, integer and output guards
remain binding. No native/Q storage credit can reopen a rejected old request.
Python additionally reserves wire/parsed-output logical entries and new native
work from the remaining whole-request budget. Native separately derives its
own structural/group/Q census, complete callback work, nested vectors, marginal
keys, kernel retained-plus-scratch and worst binary64-reach integer/payload
bounds before allocating learning state. Unified work removes the plan's named
kernel-setup forecast before adding fresh actual setup/support, all future
callbacks and trainer/history-key work, avoiding both omission and double count.

Marginal key/value capacity is checked before insertion. A reduced kernel storage
limit must cover retained setup plus the larger constructor/support scratch;
the graph plan rejects before constructing an under-admitted kernel. Every query
also has the kernel's reduce-only width, aggregate value-payload and cumulative
work guard. Standard-library sort/map constants are modeled units, not portable
actual-comparison, allocator-byte, CPU or RSS guarantees.

`OPENPOKER_NATIVE_EXACT_FOUR_STREET_V1` is a separate bounded ASCII protocol,
with exact sixteen-digit binary64 fields and complete original terminal money.
The Python transport authenticates the full pinned build/source/dependency closure
before and after one process. It enforces live stdout/stderr byte caps and a
timeout, kills failures without retry, and retains bounded first streams in a
`NativeFailure`. Complete returned row support, menus/counts, normalization, zero
encoding and phase counters are checked against original admitted Python rules.
The outer result identifies `training_backend="native-exact-four-street-v1"`.

The mathematical prior remains `exact-product-selected-v1`, with one global Z
and ordered hidden future reveals. Native compiles/ranks physical holdings itself.
No old rounded native protocol is relabeled, and no pot-anchor/root correction
enters the exact callback trajectory. The old fixture-specific 66.615x result
is unrelated evidence and is not a result for this implementation.

## Development verification and retained findings

Complete physical policies and all eight diagnostic values match bitwise across
private-flush, weighted asymmetric, blocker-18, mixed-stabilizer and original
22-world T10 fixtures. Existing independent physical numeric and exact compact
certificates pass their replay checks; target misses remain target misses.
The private-flush T100 real child also passes independent replay and the unchanged
1/1000-BB exact quality gate. These development observations are not a frozen
performance study or broad quality claim.

Eight optimized integrated controls pass (44.025 seconds), including reviewers'
direct graph/CFR tests, no Python/legacy training in native mode, original T1000
rejection before native launch, malformed/forged output and real pipe cap/timeout
termination. A later focused three-test run (42.526 seconds) additionally covers
14 exact seven-card best-five anchors and early low-kernel-scratch rejection.
The unchanged Python evaluator's exhaustive 2,598,960 five-card category census
passes; it is a Python baseline check, not exhaustive native seven-card proof.
Forty optimized legacy exact/quotient/equivariant controls also pass (79.425 seconds).

Terra's draft review found the omitted chance mass, inactive-field and chance-index
defects and the combined kernel scratch gap. Luna fixes the graph, Sol fixes
trainer admission/buffer accounting, and root integrates the protocol/API and
full-game tests. Terra's original witnesses and corrected graph retest are retained
externally. Her final second CFR audit was usage-limited; root must not claim a
completed second Terra acceptance. The manual literal-R comparator shares the
native callback kernel; the separate physical Fraction/best-five and policy
certificate paths provide independent mathematics. Early harness environment,
quoting and expectation errors remain distinct from implementation failures;
not all early Luna raw streams were captured, and gaps must stay explicit.

## Frozen study and remaining gates

The [fixed runner](../scripts/benchmark_native_exact_four_street.py) prescribes
18 fresh children: three alternating original-22 T10 pairs, a separate traced
pair, paired private-flush T100/blocker/asymmetric/mixed games, and both original
T1000 rejections. It retains complete policies, raw native requests/results,
source/build pins, first failures and exact replay flags without retry.
Complete API plus canonical result serialization/hash is timed; compilation and
independent replay are excluded. The observer retains native wire bytes through
diagnostics. Traced Python peak includes those observer bytes and excludes native
heap; Python child lifetime peak is a separate scope. Neither is whole-solve RSS.

Both source-frozen batches and saved-only physical/exact replays are now retained
in the [result record](native-exact-whole-game-result.md), including all misses,
the original strict graph mismatch and the narrower exact terminal-tail proof.
The [dedicated CI](../.github/workflows/native-exact-four-street.yml)
requires actual Windows/Linux builds, Linux ASan/UBSan, complete policy comparisons
and malformed/phase controls. Full-deck solving, unrestricted NLHE, wider convergence,
asymmetric strategy growth, expanded Python output and scalable independent
certification remain unresolved. The foundation goal remains active.
