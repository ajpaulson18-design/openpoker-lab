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

## Single-call native solving

`solve_native_flop_checkdown` in
[`flop_checkdown_solver.py`](../pokerlab/flop_checkdown_solver.py) composes the
explicit count helper and native trainer in one cold call. Supply both build
directories, which must have been built explicitly from the current source:

```python
from pokerlab.flop_checkdown_solver import solve_native_flop_checkdown

result = solve_native_flop_checkdown(
    "2c3c4d", "AsAd", "KsKd",
    count_build_directory="../native-counts-local",
    training_build_directory="../native-training-local",
    config={"pot": 2, "effective_stack": 1, "bet_sizes": [1],
            "raise_sizes": [], "max_raises": 0, "include_all_in": True},
    iterations=1000, algorithm="cfrplus",
)
```

This entry point first validates options and chip limits, expands/blocks ranges,
reserves the entire public tree and information-action slots, and admits both
historical source-inclusive work and the native trainer/combined work envelope.
Only then does it look up either executable or count future cards. The same
admitted no-ranking plan feeds the count producer; ranges are not expanded a
second time. The two-step preparation API remains useful for reuse, but cannot
admit a future solve whose config and iterations it has not received.

The output has the existing policy, exact diagnostic fields and native
training metadata, plus `equity_preparation.mode="native-cold-counts"`. This
section reports current count/rank work and detached count build/response
metadata. The source charge remains in complete admission even though counting
is accelerated. Missing/stale helpers, malformed responses and training failures
propagate; there is no compilation or Python fallback. This composition adds no
new timing or memory claim to the frozen experiment below.

[Integration regressions](../tests/test_native_flop_solver.py) use real oversized
requests to isolate historical, native-shape and combined-work rejection before
both build lookups. The combined case separately admits 179,341,952 historical
units and 499,643,488 native units, then rejects the 503,772,568 combined total.
Small accepted calls match the same-process two-step payload exactly across all
three algorithms after removing preparation metadata. The 58-pair/4,000-sweep
case also matches that composition exactly and passes independent physical-count
policy replay and the unchanged 0.005 NashConv target. Comparison to the frozen
historical build ignores host-specific build identity and allows at most 1e-8
binary64 drift; same-process parity remains exact. Invalid options/ranges and
count failures are covered without lookup or Python fallback.

Sixteen focused native preparation, full-call, benchmark and saved-publication
tests passed locally with explicit builds; documentation checks passed. The
unchanged default solver was separately compared with its pre-API source on
one-pair ten-sweep games across vanilla, DCFR and CFR+: all three complete
payloads were identical. Final cross-platform and full Python matrix status is
recorded on the publication PR. These checks establish guarded composition,
not a new performance measurement.

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
The [formal report](../benchmarks/results/native-flop-preparation-v1.json)
passes at clean source `1cee10d63dc7abc39139d38fee7a23cdd1fe56c3` on Windows /
Python 3.12.14 with the recorded MSVC count helper and qualified native V2
trainer. All 571 LF-normalized source hashes independently match frozen Git
contents. Source plus count/training/historical build identities are unchanged.
All 24 raw calls pass exact table/policy parity and deterministic repeat checks;
all 12 full policies pass independent numeric-rule and legal response replay.

| Weighted range case | Python/native cold preparation median, seconds | Python/native complete-call median, seconds | Complete-call observed ratio |
| --- | --- | --- | ---: |
| Base eight-by-eight | 7.482584 / 0.049970 | 8.158832 / 0.597332 | 13.66 |
| Reversed weights | 7.717378 / 0.063052 | 7.847729 / 0.796039 | 9.86 |

Ratios include instrumentation and apply only to these paired fixtures. Complete
calls use native training on both sides. Cold-preparation ratios are 149.74 /
122.40, respectively; source-validation/independent checks outside measurement
are not hidden inside those boundaries. There is no RSS/allocation claim.
Independent final NashConv is 0.0001049110234 / 0.0000422279060 chips, below
the unchanged 0.005 target. Every complete policy is exactly the same between
preparers, including all returned training metadata and diagnostics.

Both fresh independent physical checks match every count: dry AA/KK returns
`1782 / 48 / 150`; the wet `TsJs2s`, `AsKd` versus `AhAd` case returns
`914 / 12 / 1054`. Old/new bounded `COUNT` and `RANK` outputs are byte-identical.
The source-built evaluator classification code itself remains unchanged.

A Luna code/harness review found no blocking admission or count issue. Its
narrow fresh-check metadata recommendation was integrated after the frozen
measurement: saved verification now checks every echoed board/private pair,
raw counter, top-level count field and source/build correspondence, with
re-signed tampering regressions. The original raw observations remain unchanged
and pass that stronger verifier; no performance sample, quality gate or work
limit was changed.

Canonical report SHA-256:
`86d0215733529b20a174506ccd7ca41c78f4734d43aa49a48d0a07c8b31691b4`.
Raw report SHA-256:
`9fee8bf0162d60e16f3f53a6ec93e585ea8b55cc8f271738961a92b834385dab`.
[Publication regressions](../tests/test_native_flop_preparation_publication.py)
reconstruct all 24 observations, median summaries, full policy replays, fresh
physical counts and provenance checks. GitHub matrix checks and merge are
verified separately at publication.
