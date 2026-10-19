# Bounded generic best-five source-count reference

This extends the isolated [five-card reference](preflop-five-card-reference.md)
with explicit one-to-four-private-pair count requests. It prepares reference
**physical source rows**, not strategies or a production evaluator/backend.
The original production preparation limits remain mandatory and unchanged.
No third-party code, dependency or compiled binary is distributed.

## Explicit inputs and current-build conformance

The source-built reference protocol is `PREFLOP_FIVE_REFERENCE_V2`. The original
`--all-five` and fixed `--count-basis` numerical modes remain; a new
`--count-pairs` mode takes four decimal card ids per ordered SB/BB pair. Its
complete argv is validated before any output or enumeration: one to four
pairs, ids 0..51, four distinct cards per pair and no duplicate ordered pair
even if either private hand is internally reordered. Signed/noninteger,
trailing and oversized requests reject. A role reversal is a distinct query
and reverses W/L. No stdin, shell command, board stream or arbitrary bytecode
is accepted by this research interface.

The [Python reference adapter](../scripts/preflop_five_count_reference.py)
admits the original candidate/four-pair/board/rank limits before resolving a
binary or conformance file. It separately reconstructs every compatible pair
from range grammar and checks the planner's pair set. Source weights do not
alter physical W/T/L counts. It bounds grammar text, output size and subprocess
time, checks exact integer counters and ordered endpoints, and records complete
raw stdout/stderr in a caller-selected new external observation directory,
including failed process/protocol observations.

A count request requires a passing exhaustive conformance report for that exact
current source/executable identity. A source change requires an explicit new
build and conformance run. Counts preserve exact ordered hands; no suit class or
opponent hand is guessed. The immutable result returns detached count rows and
metadata, with compiler/source/binary identities and actual operation censuses.
Fingerprints are consistency evidence, not cryptographic attestation.

Each request still has at most 6,849,216 boards and 13,698,432 seven-card rank
calls. The best-five reference charges its own 21-subset units explicitly, at
most 287,667,072 five-card calls. These are distinct work units; no elapsed-time,
allocation or RSS bound follows. Source-count pooling never authorizes a larger
production enumeration request.

## Frozen QQ-versus-KK source basis

The [specification](../benchmarks/preflop-qq-kk-basis-v1.json) fixes SB `QdQs`
against `KdKs,KcKd,KcKh`: three relative-suit classes and 5,136,912 boards.
The [runner](../scripts/benchmark_preflop_qq_kk_basis.py) first admits both the
separate conformance query and QQ/KK query. It requires the current build to
pass every 2,598,960 five-card rank tuple and the previous full AA/KK source
basis, then enumerates QQ/KK through the generic argv interface. Every QQ/KK
W/T/L count must agree with the separate production seven-card counter. The
shared-suits pair must also reproduce the earlier pinned independent Python
full-board QQ/KK artifact. All raw independent/native values are saved and
freshly compared after serialization; source and both counter identities must
remain unchanged.

These are separate bounded validation queries with their individual complete
work censuses. The conformance and QQ/KK reference stages each count 5,136,912
boards and 215,750,304 five-card subsets; both production comparison stages
retain ordinary three-pair limits. The separate five-card conformance stage
checks 2,598,960 tuples. No query is split to bypass an original cap, and these
validation totals are not a solver work-budget or speed claim.

[Boundary/protocol tests](../tests/test_preflop_generic_five_reference.py)
cover admission before lookup, blockers, exact raw counters, rejected input,
current-build mismatch, detached metadata, complete raw-failure retention and
actual native role reversal. Dedicated Windows/Linux CI runs full conformance,
the QQ/KK basis and protocol tests. Formal clean-source observations and
publication are pending at this source stage. Additional verified rows will
support mixed strong/weak covered ranges; they alone do not establish wider
range equilibrium accuracy.
