# Explicit native fixed-flop equity preparation

`prepare_native_flop_checkdown_equities` in
[`native_flop_equity.py`](../pokerlab/native_flop_equity.py) adds a separate
source-built cold preparer. It returns an ordinary immutable
`FlopCheckdownEquities` table and detached build/raw-count metadata. The existing
Python preparation and solver defaults remain unchanged. Callers can pass the
table to `solve_prepared_flop_checkdown`, including its explicit native trainer.
This finite heads-up model optimizes flop betting and forces hidden future
turn/river checkdown; it does not add later-street decisions.

The [existing no-ranking plan](../pokerlab/flop_checkdown_worlds.py) first
expands/blocks ranges, computes exact represented-binary64 joint priors and
admits every pair under the existing 4,096-candidate, 128-compatible and
126,720-unordered-board limits. No binary lookup or fallback precedes those
checks. Each private pair leaves 45 unseen cards and 990 unordered final
boards. The C helper evaluates both hands once per board and adds two to its
W/T/L category, representing 1,980 ordered future outcomes. It reports actual
990-per-pair board and 1,980-per-pair rank-call counters separately.

## Protocol and source build

The project's existing [C evaluator](../native/preflop_equity.c) adds only an
explicit `FLOP` request mode. Existing `COUNT` and `RANK` formats, limits and
rank-classification code are preserved. The whole request must parse before
any ranking/output: a three-card shared board, one-to-128 ordered OOP/IP hand
pairs, distinct board/private cards, no duplicate ordered hand pairs even
under within-hand reversal, and no trailing tokens. Reversing player roles
remains a distinct legal query and swaps wins/losses. Windows binary stdin
preserves complete-input checks in the presence of Ctrl+Z.

Use the existing [explicit build command](../scripts/build_native_preflop.py)
with a new external build directory. Historical executables are preserved;
source-identity checks intentionally reject them after this extension until an
explicit rebuild is requested. The wrapper never compiles or silently falls
back. It verifies source/manifest/executable before and after execution, binds
all board/pair echoes, requires even integer W/T/L counts totaling 1,980, and
validates every returned work unit before constructing the ordinary table.
Build hashes identify local bytes; they do not authenticate untrusted binaries.
No evaluator or third-party code was imported.

## Frozen full-call experiment

The [specification](../benchmarks/native-flop-preparation-v1.json) fixes two
weighted eight-by-eight range games on `2c3c4d`, with 58 compatible pairs each,
stack 24, two raise levels and 4,000 CFR+ iterations. Both complete admissions
finish before lookup/ranking. Native modeled complete work is 378,109,520 for
each game under the unchanged 500-million cap. All preparation-only oracle
checks are admitted first as well.

The [runner](../scripts/benchmark_native_flop_preparation.py) compares three
alternating paired cold preparations and three alternating paired complete
calls per game: 24 raw observations in total. Complete calls use the same
qualified native trainer and Python diagnostics on both sides, isolating cold
Python versus native preparation. Timings include return construction and
canonical JSON/hash; independent checks follow outside timing. Python rank-call
census wrappers add per-call counter overhead inside timing. Any reported ratio
therefore describes these instrumented calls, not a general performance claim.
There is no allocation or RSS measurement in this experiment.

All 58 physical W/T/L rows are checked against the complete checksum-pinned
independent PR130 report. Two small independent ordered-board/best-five counts
on different flops are freshly repeated during saved-file replay. Every full
policy receives independent numeric-rule/value/own-hand-BR checks and must meet
the original 0.005-chip NashConv target. Both preparers must produce exactly
identical table and complete-policy payloads, with all repeats deterministic.
Historical and new helpers also receive identical bounded `COUNT`/`RANK`
requests, with raw byte agreement and all build identities retained.

## Current validation status

The strict MSVC build and eight new boundary/benchmark checks pass locally,
including actual full-capacity 128-pair input, role reversal, one-pair full
policy identity, original caps, weighted blockers and admission before lookup.
Original native preflop protocol/count checks also pass on the extended build.
The [Windows/Linux conformance workflow](../.github/workflows/native-preflop.yml)
now builds both explicit helpers and exercises complete-call integration.
Formal frozen measurements and GitHub publication are pending at this source
revision. Keep observations and planned performance benefits distinct.
