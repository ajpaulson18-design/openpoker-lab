# Active traversal frames for native indexed learning

Status: implemented with [committed-source measurement and independent saved-policy
acceptance](native-active-frames-result.md). Final publication-head checks pass;
[PR #274](https://github.com/ajpaulson18-design/openpoker-lab/pull/274) merged as
`df7e3968c776498600ae96b596b2bc23e0f285b6` with the tested tree unchanged.
The [indexed admission result](native-indexed-admission-result.md)
is prior evidence; it does not measure this change.

Select `native_traversal="active-frames"` with an explicit source-built
`native_executable`, `native_routing="indexed"`, `native_admission="indexed-v1"`,
compact diagnostics, dyadic arithmetic, suit-equivariant reduction,
suit-quotient storage and per-decision lookup. Unsupported combinations reject
before preparation or build lookup. The default `"value-cursor"` preserves the
previous V1/V2/V3 protocols and reference path. No automatic fallback occurs.

## Ownership and numerical contract

The previous learning cursor holds a fixed 24-image array even when the actual
symmetry group has one member. Each recursive edge copies that value cursor.
The new Router owns one noncopyable traversal workspace sized by maximum public
edge depth and actual group size. Each depth slot stores only its active suit
images. A move-only lease releases the slot; a small borrowed view carries
workspace identity, slot and epoch. Recursive learning retains a child's lease
until the child returns. Success and exception paths release the workspace.

The Router checks exact workspace ownership before accepting a view; matching
Index ownership alone is insufficient. Epochs reject stale/reused slots. Parent
release invalidates its active suffix, and subsequent child destruction is safe.
Foreign views, invalid depths, duplicate roots and mixed traversal modes reject.
Workspace/Index/Plan owners must outlive their borrowed views and leases. This
internal lifetime requirement is not a memory-safe external capability API.

Both paths use the same edge-image update and templated numeric training body.
Private ranges, compatible support, ordered reveals, hidden future information,
joint normalization, payoff callbacks, CFR+ phase order, action order and float
reduction order remain unchanged. Q setup still uses the original value cursor.
The Router still reserves fixed 24-element key/view scratch and retained Q
histories; expanded output, callback computation and Python diagnostics remain.
This change targets traversal metadata, not those independent limits.

## Independent resource receipt

V4 uses fixed-indexed headers
`OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_V4` and
`OPENPOKER_NATIVE_EXACT_FOUR_STREET_ACTIVE_FRAMES_RESULT_V4`. It retains existing
ROW/DONE/ROUTE/ADMISSION records and adds one ordered 22-field
`FRAME\tactive-v1` record. All values are bounded unsigned decimal integers.
The host reserves the extra proof scan and output bytes before transport.

Frozen producer `0be1a858fb5983df21698d97b2a1f8e5e7295505` emits V4's
`training_backend` and `native_traversal` markers but omits top-level
`native_routing`/`native_admission`. Native ROUTE/ADMISSION proofs remain explicit.
The initial parent expected those optional top-level fields and stopped after
two preserved solves. An external continuation validates the actual frozen
schema and reuses both observations, launching only unattempted schedule entries.
A separate host correction makes both markers explicit in future V4 payloads;
it changes no native wire, policy or numerical computation. Keep the initial
failure and the original schema in the evidence record.

For maximum edge depth D, actual group size G, full logical visit count L and
iterations T, independent host occurrence counts bind these formulas:

| Quantity | Logical reservation or required count |
| --- | --- |
| Workspace depth slots F | D + 1 |
| Image slots | F G |
| Header entries | 3 F |
| Workspace entries and setup work | 64 + 3 F + 8 F G |
| Borrowed view and lease fields | 3 each |
| Borrowed frame entries | 24 (D + 4) |
| Flow work per visit | 88 + 8 G |
| Total flow work | workspace setup + 3 T L (88 + 8 G) |
| Activations, released frames and release calls | roots + edges = 3 T L |
| Frame validation work | decisions 32 (1 + G + Hmax (1 + G)) + prefixes 64 |

Caller work includes workspace setup/flow. Router query work includes frame
validation exactly once. The host checks their lower bounds separately and
binds FRAME's combined work/entries to ROUTE, ADMISSION and DONE. Actual learning
value-cursor calls, final active frames and final workspace entries must be zero;
the workspace must be Router-owned. All old callback, Index, numeric, Plan,
integer-payload and whole-request checks remain. Neither the 500-million work
ceiling nor the native two-million-entry ceiling increases.

The old cursor has 196 logical fields and a conservative 848-field per-visit
flow allowance. For D=14 and G=1, the new traversal-only reservation is 229
workspace plus 432 borrowed entries, versus 14,112 old cursor-frame entries.
These are modeled fields, not allocator bytes or measured process memory.
Additional validation work offsets part of the flow reduction. No CPU, RSS,
whole-trainer memory or wider-game quality claim follows from this ledger.

## Development evidence and fixed measurement plan

Normal and optimized native controls cover G1/G2 and noncommuting G6 reveals,
reconvergent paths, original histories, terminal-only games, stale/foreign views,
exception unwinding, single use and exact work/storage boundary rejection.
Physical end-to-end controls compare five established games and a separate G6
game against indexed value-cursor learning, including full policies, all eight
metrics, member checks and protected independent replay. G6's nine compatible
deals have three distinct members per hand orbit; its board-flush showdown ties.
The payoff-varied private-flush case separately tests differing private payoffs.
These are development checks, not the formal study or a quality-target result.

One external control command initially omitted the native include directory
after successfully building the engine. That failed command/log is preserved;
the control compiled separately with the correct include path. Initial test-only
fixture/import errors and the receipt-owner correction also remain in development
records. No formal producer was repeated to repair these helpers.

The planned schedule contains exactly 37 distinct complete-call attempts:

1. Six T10 physical cases, each with one value-cursor/active-frame pair (12).
2. Two further alternating original-T10 pairs (4); only these three same-game
   pairs support a scoped complete-call median.
3. Original T40/T60/T100 pairs (6).
4. Payoff-varied T100 pair (2).
5. Five fixed range shapes at T10/T100/T1000, active-only, reusing the original
   T10 and T100 observations through explicit aliases (13 new attempts).

The six T10 pairs and payoff-varied T100 pair must complete for regression
acceptance. Higher-iteration original and matrix outcomes remain measurements,
including rejection. No Python-traced pair is planned: it would not measure the
native workspace. Authenticate committed raw/Git source and build/dependency
closure before mathematics, preserve every raw result and failure, and never
repeat a producer because a verifier or parent classifier fails. Replay every
completed numeric policy and exact certificate within unchanged limits; retain
target misses and verifier-cap unknowns. A rejected half-pair provides no paired
speed or quality inference. Full-deck strategy storage and scalable certification
remain unresolved.
