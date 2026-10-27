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

Source-frozen complete-call runtime/allocation/process observations, saved T1000
policy/BR/exact replay, broader workload checks and final CI remain gates. No
total-memory improvement, native shared-topology support, full-deck capability or
overall scalable-foundation completion is claimed from these focused controls.
