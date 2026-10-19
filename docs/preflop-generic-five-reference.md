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
the QQ/KK basis and protocol tests.

## Frozen physical QQ/KK observations

The [raw report](../benchmarks/results/preflop-qq-kk-basis-v1.json) passes from
clean source `b37939b01c3cbfe1c22f2d39cc06207078aaddfb`. All 489 normalized
source hashes independently match frozen Git blob contents; source and both
counter identities remain unchanged. Before the QQ/KK query, the current v2
build reproduces all 2,598,960 five-card tuples with zero mismatches, all nine
category totals and the exact same fixed dump SHA-256
`7dfd1ff4ed2761fef77db70b170fdae750cf7c162932087e30163037e4e78e52`.
The fixed full-board AA/KK basis also passes in that build.

| SB | BB | Shared suits | Wins | Ties | Losses |
| --- | --- | ---: | ---: | ---: | ---: |
| QdQs | KdKs | 2 | 292,846 | 9,336 | 1,410,122 |
| QdQs | KcKd | 1 | 305,351 | 7,960 | 1,398,993 |
| QdQs | KcKh | 0 | 317,856 | 6,584 | 1,387,864 |

Each row covers exactly 1,712,304 boards. All three rows match the separately
saved native-seven-card counts, and the shared-suits row exactly reproduces
the original independently enumerated anchor. Actual generic-reference counters
are 5,136,912 boards, 10,273,824 seven-card rankings and 215,750,304 five-card
subset calls. Fresh saved-file verification reconstructs the raw independent /
native count equality, old anchor, matching current-build conformance and all
source/build identities. Raw stdout/stderr and the binary dump remain outside
Git and were reopened for checksum/data verification.

The reference C source SHA-256 is
`68993c237e4092a9ddb8c0e2432a2cac8030486fd2b16904bf519fca024e6288`;
MSVC executable SHA-256 is
`a3037e43df3fe857fde62cd31d3caeeaf625e3605cc6332663d7d1b785f216e6`.
The QQ/KK reference/native calls took 11.869431 / 0.724779 seconds on the
recorded Python 3.12.14 / Windows runtime. These are distinct validation calls,
not paired performance or memory measurements.

Canonical report SHA-256:
`d47fcbdca9cb84275adb8902636d8331bca8b6089e1d62e83cc2160ff09503b8`.
Raw report SHA-256:
`44e750b135a97dc98dc8246c6c0881e5c775a697fdc9f4e1d803b995b6aa5118`.
A [publication regression](../tests/test_preflop_qq_kk_publication.py) freshly
rechecks the actual saved report and rejects re-signed raw-count tampering.
Final cross-platform CI and merge status are recorded on the PR. These extra
verified source rows support subsequent mixed strong/weak range work; they do
not themselves establish wider-range equilibrium accuracy.
