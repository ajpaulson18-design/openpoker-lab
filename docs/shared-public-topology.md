# Shared public topology with distinct strategy histories

The selected four-street solver can explicitly use
`public_topology="shared", strategy_storage="packed"` for Python zero-delay CFR+.
The literal/default path and original betting builders remain available.
Native plus shared topology rejects before preparation: the existing native
protocol still requires a literal tree, and no fallback is inferred.

## What is shared

The compiler snapshots the already-built public tree into immutable local
vertices. It interns decisions by global player, all four action fields, action
tokens and ordered child identifiers; chance vertices by street, card index and
ordered reveal/child pairs; terminals by kind, both ordered contributions and
winner. Binary64 numeric keys include their bits, including signed zero. Nonfinite
values reject. Source histories must equal each reconstructed path, cycles reject,
and source snapshots are rechecked before return because source nodes are mutable.

No full history is stored in a shared vertex. A bounded iterator or lazy traversal
cursor reconstructs the complete observable action/reveal path. Equal vertex
identifiers do not imply equal information sets. The same full history and own
hand select the same row across hidden future worlds; distinct visible histories
keep distinct rows even if their pots, stacks or menus match. No off-path branch
is removed. Chance order is retained because it participates in floating sums.

Structural controls find 99 vertices and 173 edges for the original 1,462-node
22-world tree. Its 628 decision occurrences and 1,200 information rows/2,402 action
slots remain. The 96-world held-out tree has 56 vertices/92 edges versus 1,300
logical nodes, while retaining 2,224 information rows/4,452 action slots. These
are entry counts, not memory measurements or universal compression ratios.

## Connection to training and diagnostics

The existing packed trainer keeps its four binary64 buffers and alternating
player updates, rematches and weighted own-reach averaging. Shared mode looks up
row offsets by `(global player, own hand index, full visible history)` rather
than cursor object identity. It retains a semantic lookup with O(information
rows) entries and their existing history keys; it does not allocate an expanded
node-to-private-hand map. Inactive private-hand indices retain uniform fallback
under zero physical support. Coverage checks reject orphan rows, menu mismatch
and reuse of a policy row at duplicate logical occurrences.

Lazy child sequences and chance mappings construct cursors on demand. They do
not cache expanded nodes or histories. The unchanged vector diagnostics consume
the same lazy transitions through an explicit chance type. Terminal copies are
cached per unique terminal, with the exact original power-of-two anchor and
binary64 contribution subtraction. Global seat mapping, refunds, monetary
quantization, card probabilities and blocker conditioning remain those of the
shared original builders and selected operator.

Before training, serialization metadata retains immutable action menus instead
of references to expanded nodes, and the literal root is released. A weak-reference
test checks this at actual trainer entry and after an injected training error.
No second expanded positive-pot training tree is built in shared mode. Policies,
metadata/history keys, numeric buffers and complete result rows remain materialized.

## Admission and memory boundaries

All previous selected operator, tree, packed-array, scan and rank-cache guards
remain. The compiler separately bounds source nodes/edges, logical visits/depth,
unique DAG vertices/edges, history token work/bytes and node/map/frame scratch.
Edges reserve capacity before publication; postorder chance traversal indexes
the existing snapshot instead of repeatedly copying its whole child list.
Source-edge storage and keys are counted separately from node/map/frame scratch;
these logical limits are not a hard allocator or RSS bound.

The shared layout validates complete logical coverage and bounds requested array,
vector and history-key lookup work before training. Its lookup envelope includes
three traversals per sweep, action-dependent diagnostics and setup/metadata work.
Logical dense holes are counted even though their physical lookup array is absent.
Setup and coverage stream occurrence records using a depth stack. The receipt
distinguishes setup walks from the lazy training/diagnostic cursor bound. Compiler
and source preparation work have already occurred before this final admission.

This is a compiler bridge: it first constructs the old literal tree, then
temporarily retains that source alongside compiler snapshots and the DAG.
It therefore does not eliminate initial construction or demonstrate lower
full-call peak memory. Removing literal construction requires a direct shared
builder and independent history/action/chance parity, not a relabeled tree copy.
Distinct information-action storage and repeated private-pair scans remain open.

## Executed controls and remaining gates

Sol integrated the existing trainer and diagnostics; Luna implemented the
compiler/structural controls; Terra independently challenged the identity and
resource boundaries and supplied alias/orphan/shifted-payoff controls. Complete
policies, pair probabilities, monetary anchor and all numeric diagnostics match
the literal packed path on the original selected game and weighted shared-future,
asymmetric-index, fractional-blind, refund, tie and short-all-in controls.
Independent numeric replay and a bounded exact short-all-in certificate agree.
Rank-free shared admission and rejection before training are separately tested.

## Frozen complete-call result: correct policies, higher measured cost

The [receipt and raw archives](../benchmarks/results/shared-public-topology-v1/receipt.json)
pin clean source `e0e50a60264fe995074570ea4a72f666cec9c017`. All five paired
complete policies, pair probabilities, numeric diagnostics and operator counters
match. Independent exact metric maps match; both T1000 <=1/1000 BB targets pass
with numeric NashConv 0.0003997388151442405 BB. T100 target misses remain.

| Complete-call observation | Literal packed | Shared packed |
| --- | ---: | ---: |
| T100 median, three fresh untraced calls | 5.317529 s | 6.703550 s |
| T1000, one fresh untraced call each | 54.050178 s | 69.816158 s |
| T100 traced Python peak, separate call each | 2,362,920 bytes | 2,906,499 bytes |

This bridge is slower and has about 23% higher traced peak on this fixture. It
is not a successful full-call memory optimization. Process peaks are separate
descriptive lifetime observations and establish no general RSS result. T1000
has no runtime distribution; traced calls are excluded from runtime medians.

A fresh saved-only process repeats both budgets' numeric/exact replay with zero
training/native calls and maximum numeric discrepancy about 1.11e-16. Terra
independently authenticates both manifests, every listed artifact, all 1,668
captured source hashes, five complete policy pairs and exact threshold flags.
The first batch was interrupted after six untraced calls; its raw samples and
source identity are preserved. The old handle was missing and no matching OS
process existed before starting a distinct full second batch. Termination cause
is unknown; no completed sample was silently selected or replaced.

A separate instrumented T10 phase profile records current traced allocation at
trainer entry of 953,544 bytes literal versus 804,478 shared. The shared call's
cumulative peak of 2,773,601 bytes was already reached before trainer entry and
remains its full-call peak, versus 2,141,728 literal in those instrumentation
calls. This places the peak in the broad pre-training interval; it does not
identify the compiler as its sole cause. Current snapshots include imports and
instrumentation and do not prove retained-object savings. These calls are
separate from the formal T100 measurements and do not replace their memory miss.

The next storage dependency is direct shared construction, independently matched
against the literal builders' complete action/history/monetary/chance behavior.
Native shared-topology support, broader workload quality, strategy-history growth
and full-deck solving remain unresolved. Final evidence-head CI and merge state
are separate live checks; the overall scalable-foundation objective stays active.
