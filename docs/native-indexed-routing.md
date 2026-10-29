# Explicit native indexed-history training

Status: implemented candidate with bounded development controls; committed-source
study, saved-only independent acceptance and final CI remain gates. This joins the
[public-history index](native-public-history-index-result.md) to numeric Q routing
and the exact native four-street trainer. The default full-history path remains.

## Explicit selection and contracts

Build the source-authenticated engine outside the checkout with
`python -m scripts.build_native_exact_four_street --target engine --output-dir <directory>`.
Select `solve_four_street_exact_selected(..., native_executable=..., native_routing="indexed")`
with the existing compact/dyadic/suit-equivariant/suit-quotient/per-decision options.
`native_routing="shadow"` runs the old path and checks numeric locations/prefixes
before use. The default `"full-history"` preserves V1. Missing executable,
unsupported combinations, drift and computation failures reject without fallback.

Routed requests/results use `OPENPOKER_NATIVE_EXACT_FOUR_STREET_ROUTED_V2` and
`OPENPOKER_NATIVE_EXACT_FOUR_STREET_ROUTED_RESULT_V2`. The request adds only an
explicit mode. The response retains complete physical policy rows and DONE13,
then a bounded named routing proof. Python checks exact complete-call schedules,
mode, Q/map layout, zero R cache, old-history retention, shared work/storage,
zero released router workspace and legacy-learning call counts. It rejects missing,
forged, duplicate or cross-mode proofs. V1 request/response grammar stays separate.

## What learning changes

The router retains one sorted `(actor, original own-hand index, path ordinal, old q)`
entry per existing Q representative. It verifies the original Q ordering and
borrows existing menus, action offsets and typed prefix support. Suit images are
sorted/deduplicated as complete keys, and the original key's position determines
the member bit. Physical hand-index holes remain null; missing image support fails.
No expanded R lookup table, G-by-Q membership cache or copied prefix cache appears.

Indexed learning branches before constructing child histories. Incremental cursors
advance in the original action/chance order; numeric decision locations and borrowed
ordered board-index vectors reach the same arithmetic body and exact callbacks.
Average/reach arithmetic, two responder phases, member validation, phase commit,
canonical zero and exact rational conversion remain unchanged. Old histories still
run during preflight, marginal-key setup and once-only Q-map construction; original
Q histories and expanded Python output/diagnostics remain retained costs.

Default and shadow paths continue as references. Shadow compares complete per-hand
Q index, offset, member bit, null holes and ordered prefix board vectors before
phase use. Indexed learning requires zero legacy history extensions, decision-row
lookups and prefix parses, with exact complete-call router counts. These counters
are complemented by external actual-call instrumentation on a bounded fixture.

## One whole-call admission

The index optionally receives a declared query schedule and external work/storage
reservation. Before its arrays grow, it admits Plan + index setup + future index
queries + external ownership together. Runtime consumes actual query charges under
the declared schedule, adding actual to the setup base rather than adding the
forecast again. Absent schedules preserve the graph-only dynamic behavior; strict
schedules reject unplanned token/inverse queries and exhausted operation counts.

The router derives Q setup routes and all 3T roots, 3T(L-1) edge advances, 3TD decision
lookups and T(2F+D) prefix calls from the immutable graph census. It charges all
fixed 24-image cursor and fixed 24-slot key/support arrays, even for G1, plus Q
metadata, token/comparison work, outputs and overlapping scratch. Typed support
borrows a stable existing vector key rather than copying it into the marginal map.

Trainer admission conservatively retains the old full-history work forecast and
the Plan's named kernel-setup overlap, while additionally charging fresh callbacks,
cursor copies, router/index work, numeric arrays, old comparison state and reports.
No capacity savings credit or ceiling increase is granted. Kernel state must still
match constructor admission before either routed run. Single use and floating
environment checks apply to all modes. Logical fields/characters exclude vector
capacity, allocator bytes and RSS. Plan must outlive its index/router; callers
must own it exclusively for a run.

## Development verification and remaining evidence

Sol implements shadow/indexed arithmetic integration; Luna implements numeric
routing and its fixed schedule/runner; Terra independently challenges support holes,
member masks, shared-budget boundaries, fixed-array accounting and actual calls.
Root integrates typed Plan access, scheduled index admission, V2 transport/API and
complete physical-policy verification. Sol's latest final review was usage-limited;
implemented-source evidence must not be relabeled as a completed final Sol review.

Three-mode native controls preserve complete Q-policy bits on identity, G2,
mixed-stabilizer, support-hole and terminal-only fixtures, with exact schedules,
phase/member gates, pre-learning limit-1 rejection, kernel freshness and floating
guards. These native controls share the kernel and are not an independent physical
game oracle. Separate API controls compare complete physical strategies and all
eight diagnostics across five games and invoke independent numeric/exact replay.

External exact-anchor instrumentation confirms learning-only calls to history
extension, old row lookup, prefix lookup, reveal parsing and history transformation:
legacy/shadow `[60,30,50,190,30]`, indexed `[0,0,0,0,0]` on its bounded hole fixture.
All three complete Q policies match. This establishes dependency removal there,
not performance or unrestricted correctness. First compile/harness failures and
development raw-capture gaps are retained separately from passing source pins.

The [new fixed study runner](../scripts/benchmark_native_indexed_routing.py) prescribes
20 fresh children: three alternating original T10 full-history/indexed pairs, a
separate traced pair, private-flush T100/blocker/asymmetric/mixed pairs, both original
T1000 rejections and two shadow checks. Complete API plus serialization/hash is
timed; build/replay is excluded. Raw policies and native streams precede validation,
with no retry; independent saved-policy replays and exact target misses remain.
Traced memory includes retained Python observer bytes and excludes native heap.

Until the committed-source study and saved-only review complete, no measured speed
or memory result is claimed. Larger original T1000 requests and full-deck solving
remain unsupported; exact terminal callbacks and conservative admission are separate
limits. The overall foundation goal remains active.
