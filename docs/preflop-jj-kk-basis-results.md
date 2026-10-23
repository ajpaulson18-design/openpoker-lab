# JJ/KK physical source-count observation

The single frozen [JJ/KK study](preflop-jj-kk-basis.md) passed on
2026-10-23 UTC. The project-owned best-five reference and separate native
seven-card counter produced identical full-board counts for all three fixed
ordered private pairs. Each pair covers all 1,712,304 unordered five-card boards.

| SB | BB | Wins | Ties | Losses |
| --- | --- | ---: | ---: | ---: |
| JdJs | KdKs | 300,064 | 8,850 | 1,403,390 |
| JdJs | KcKd | 312,425 | 7,476 | 1,392,403 |
| JdJs | KcKh | 324,786 | 6,102 | 1,381,416 |

The reference and native APIs return these pairs in different orders. The
observation retains both raw orders and compares by exact ordered SB/BB hands;
neither count stream is silently reordered or replaced. The existing AA/KK and
QQ/KK publications authenticated before computation. Current-build conformance
checked all 2,598,960 five-card tuples against the project-owned independent
Python rules and reproduced the complete published three-class AA/KK basis.

## Frozen execution and publication

The executable/protocol/test freeze is
[`cfe53c8e9a96993f32740dea1bf3f03405f3701b`](https://github.com/ajpaulson18-design/openpoker-lab/commit/cfe53c8e9a96993f32740dea1bf3f03405f3701b).
The protocol's canonical SHA256 is
`303594b6782b111c2c132a61c42bfda551379cb5400f3b2ec34f239ff71ee4e3`.
The batch ran once from 16:19:33.5724545 to 16:21:00.5303658 UTC on bundled
CPython 3.12.14 / Windows. There were no errors, retries, numerical fallbacks or
strategy-training calls. All five numerical subprocesses returned zero, both
build identities stayed unchanged, and all 746 clean source identities matched
before and after. Recorded elapsed time is an execution receipt, without a
controlled runtime, allocation or RSS comparison.

The [publication index](../benchmarks/results/preflop-jj-kk-basis-v1/index.json)
maps 11 copied original JSON/text files plus itself, totaling 1,118,976 bytes.
The original [complete report](../benchmarks/results/preflop-jj-kk-basis-v1/report.json)
is 753,320 bytes, with raw SHA256
`f276da203ce73de024b1e2ae79558e78c8fe589cf82f2032f3aae4910cacadc5`
and canonical self-digest
`1f80d95da14890be036c72772f6a88228beff936d05355875384dcc34d6d5156`.
Its separate conformance report and nine small raw stdout/stderr receipts are
copied byte-for-byte. The publication index records their original paths rather
than editing the measured report. Git preserves every archived byte.

Repository instructions keep binary dumps and build products outside Git. The
original exhaustive dump and captured copy remain external: each is 15,593,760
bytes with SHA256
`7dfd1ff4ed2761fef77db70b170fdae750cf7c162932087e30163037e4e78e52`.
The publication records their identities and exhaustive-check receipt; it does
not distribute an encoded substitute. Saved-data authentication can recheck
raw JSON counts, sources, builds, operation censuses and receipt consistency.
It does not repeat the five-card tuple comparison or enumerate physical boards.

Authenticate a clean checkout with:

```text
python -m scripts.verify_preflop_jj_kk_basis_publication
```

The [saved-data verifier](../scripts/verify_preflop_jj_kk_basis_publication.py)
pins the index and every raw file before parsing, freshly authenticates the
published AA/QQ and current-build conformance receipts, links the raw outputs
to all physical rows and build identities, and authenticates the generation-time
746-file source map. Four explicit non-computational context files use their
pinned original archives; their current LF hashes are recorded separately.
The other sources retain strict LF checks, with the one exact archived test
cleanup transition below. This does not attest arbitrary later calculation code.
Its [20 publication tests](../tests/test_verify_preflop_jj_kk_basis_publication.py)
include actual and copied-corpus authentication with live computation forbidden,
byte/source/build/count tampering, metadata linkage and strict scalar types.
Together with the 23 admission/orchestration checks, all 43 focused checks
passed on bundled CPython 3.12.14. Earlier 39-check and 41-check validations
preceded the two parallel-main integrations; added checks cover historical
archives, separate current context, mathematical-source rejection and
source/context changes during verification.

## CI test isolation correction

The first publication-head CI failed ten later saved-evidence tests because a
benchmark test left its fake `subprocess.run` installed globally. The standalone
benchmark module passed all 16 tests while leaking that callable; the combined
suite exposed it. Test teardown now restores the process-wide delegate even
when a test deliberately replaces the capture instance's internal delegate.
A regression executes that test and asserts exact callable restoration.

The original measured test is retained
[byte-for-byte](../benchmarks/sources/preflop-jj-kk-basis-benchmark-test-frozen-v1.py),
with raw/LF SHA256
`b19712a80f2ff89070db5027b9f5339d57b6d21e3abaa159b21239a49b61cad2`.
The corrected test's LF SHA256 is
`8348222151a715eedb834f2fef5c6344311a742465c7ad573276b02173173abd`.
Saved authentication admits only this exact historical-to-current pair and
requires the original archive. The
measured batch, executable, protocol, count rows, source snapshots, corpus
digests and original failure observation remain untouched. No physical study
was repeated. The separate failing CI log is retained outside Git.

## Parallel-main context integration

The later main revision
[`de569fe`](https://github.com/ajpaulson18-design/openpoker-lab/commit/de569fe)
published the separate turn workstream, followed by
[`745b72e`](https://github.com/ajpaulson18-design/openpoker-lab/commit/745b72e).
This branch preserves their complete
implementation and evidence, and resolves the attribute/progress conflicts by
retaining both sets of rules and sections. No turn executable or policy was
changed. Current capability/progress summaries also link this completed JJ
observation separately from the original frozen planning record.

Four generation-time context documents are retained as exact source text:
[agent instructions](../benchmarks/sources/preflop-jj-kk-context-freeze-v1/AGENTS.md.txt),
[current state](../benchmarks/sources/preflop-jj-kk-context-freeze-v1/CURRENT_STATE.md.txt),
[solver progress](../benchmarks/sources/preflop-jj-kk-context-freeze-v1/solver-progress.md.txt)
and [turn context](../benchmarks/sources/preflop-jj-kk-context-freeze-v1/turn-class-tail.md.txt).
The verifier authenticates each original archive against its immutable
generation LF hash on every check. It separately records current context hashes
and the current subset digest, requiring source/context stability across the
entire saved verification. Current narrative updates are not claims that run-time
context matched later documentation. The four paths are explicit; none is read
as mathematical input by the counter or proof. The original run's source maps
remain byte-for-byte unchanged. The other 741 sources remain strictly pinned,
alongside the one exact benchmark-test cleanup transition. Unlisted paths,
calculation-source changes and altered archives reject. No physical study was
repeated, and no protocol, cap or mathematical-source allowance is introduced.

## Scope and next evidence

The observed schedule includes two three-pair physical requests per method:
AA calibration and new JJ counts. Each method counted 10,273,824 boards and
20,547,648 seven-card rankings; the best-five reference also performed
431,500,608 subset calls, in addition to the exhaustive five-card check. These
are recorded named operations, without a process-memory or time bound.

The 23 focused pre-measurement tests and lead/Luna reviews checked admission,
raw stream retention, ordering, timeout handling, original-error preservation
and a complete simulated five-stage success. They are distinct from the actual
physical count evidence. This publication adds no strategy, exact equilibrium
value, best-response certificate or convergence result. The future 108-pair
AA/QQ/JJ-versus-KK game still needs independently checked joint suit transport,
global priors and its own legal own-hand response verification. Shared
turn/river work, production defaults and Coach remain unchanged.

Publication review and CI are tracked in
[PR #216](https://github.com/ajpaulson18-design/openpoker-lab/pull/216).
