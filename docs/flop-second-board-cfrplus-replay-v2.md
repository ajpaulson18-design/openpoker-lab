# Second-board CFR+ replay boundary v2

This separate version corrects the result-schema integration error preserved in
the [stopped v1 pilot](flop-second-board-cfrplus.md). It preserves every v1
executable, protocol and artifact. The original T140 attempt remains failed,
T560 did not run and its quality-gate field remains null.

## Exact scope of the correction

The unchanged independent physical replay returns thirteen top-level fields:
eight numeric metrics, `scalar_absolute_gaps`, and four checked-count fields.
The v1 adapter incorrectly expects only the eight metric fields. The new
adapter wraps this boundary for one call, retains the complete original return
before validation, validates all thirteen fields and exposes an eight-metric
view to the preserved v1 adapter. It restores the original callable on every
exit. If a harness has already installed a counting wrapper, the new boundary
calls that captured wrapper exactly once; it does not invoke replay twice.

All eight metrics must be finite binary64 floats. The scalar-gap map must have
the exact eight metric names and finite nonnegative floats no greater than
`1e-10`. Checked counts must be strict integers: 16,912 own-hand information
rows, 5,940 physical worlds, 9,512 decisions and 30,812 public states. Missing,
extra, boolean, nonfinite or out-of-bound values reject. Invalid replay returns
and the first error remain available in the observation; the output fallback
must identify any inability to durably serialize a malformed return.

The shared trainer, recurrence, average weights, raw average policies, output
grid normalization, exact rational responses and physical replay algorithm
remain unchanged. The complete normalized physical output must still pass the
v1 adapter's exact compact/full response comparison, independent numeric gap
and final model validation. The correction changes the boundary schema only;
it does not itself establish quality or convergence.

## Provenance and admission

Admit the complete T140/T560 request before authentication or ranking. The
separate 110M per-call and 140M aggregate named logical-work envelopes, fixed
game, all world/path/row guards, six successful model proofs, two actual trainer
calls, four exact metric calls and two numeric replays remain the same as v1.
The protocol separately limits replay receipt checks and captures all metadata;
the logical training forecast still does not count all proof/adapter arithmetic,
runtime, allocation or RSS.

Authenticate both the saved stopped-v1 publication and D032 equivalence
publication before any fresh training. A clean 58-source snapshot extends v1's
54 sources with the failed-run verifier, new adapter, new harness and new
protocol. The v2 report retains the original 54-source subset and wrapped report
digest separately, and records the full raw numeric replay receipt. Both source
maps and every source hash must remain stable through the call and batch.

The new harness reuses immutable v1 output retention, per-case execution,
instrumentation and completion helpers. It owns its new protocol and batch
driver; it does not rewrite v1 globals. Each call uses a fresh model, and any
first execution error stops the batch without retry. Raw policies, all exact
metrics, numeric metadata, quality misses and cleanup/source failures remain
retained. Each completed output uses its own exact physical NashConv target
`1/200` chip. Two iteration budgets are observations, not a convergence theorem
or a controlled performance comparison.

## Completed frozen execution

Fourteen focused tests pass on bundled CPython 3.12, including real protocol
loading/admission with poker work forbidden, nested-wrapper exact-once behavior,
57/59-source rejection, full replay receipt persistence, per-case early rejection
and first-error/source-drift retention. Lead and bounded GPT-6 Luna reviews found
no remaining blocker after those independent batch checks were added.

The single batch at `7eed198bc6eb47a7a15b8fb8a84e0061f583ca48` ran from
2026-10-23 15:26:27.320330 to 15:28:38.561171 UTC on CPython 3.12.14 / Windows,
after the original failed attempt merged in PR #214. Both fresh calls completed
all exact/numeric/model checks without execution errors, retries or fallbacks.
The batch status is `verified-quality-miss`, preserving the T140 miss.

| Sweeps | Exact physical NashConv, decimal display | Target 0.005 | Maximum numeric gap |
| --- | ---: | --- | ---: |
| 140 | 0.014166984012911272 | Miss | 5.35162192338845e-16 |
| 560 | 0.0016464625267553663 | Pass | 6.557254739192331e-16 |

The lossless reports retain the full rational metric strings; decimals here are
display approximations. All eight compact/unrestricted physical metrics agree
exactly for each normalized output. Both independent replay returns retain all
thirteen fields and the exact expected checked counts. Each case used one replay
attempt/call; both preparation and diagnostic guards have all 41 zero counters.
Every final model check passed and clean 58-source snapshots matched before/after.

Actual batch counters are two fresh models, two shared training calls, six full
model proofs, four exact metric calls, two numeric replays, two projections,
20 expected row tables, 480,832 row/action slots and 8,268 attempted/actual ranks.
Each output retains 608 raw average rows, 608 normalized rows and all 16,912
physical rows/33,824 probabilities. Normalization changed 361/358 rows for
T140/T560 respectively, using two 304-row batches and zeroing no positive mass.
The earlier failed v1 attempt and its null gate remain separate and unchanged.

Total execution receipts are 131.02294160000747 wall seconds and 125.03125 process
CPU seconds, including proof/authentication, two calls, diagnostics and output.
These are one execution's receipts, not controlled timing, throughput, allocation
or RSS measurements. The two budgets establish two quality observations in this
finite game; they do not prove monotonic or general convergence.

The [complete index](../benchmarks/results/flop-second-board-cfrplus-replay-v2/index.json)
and both lossless reports are copied byte-for-byte from the original output.
The 46,200-byte index has raw SHA256
`f039c2667ac06db1b987643e4bfe17321a4b086e233b681da4041850c68039a5`
and self-digest
`d4ce99cbd3411f95664e828092c5634500d806c4db64ba78339b288d20315021`.
Both reports retain 51,125,237 raw bytes in 1,274,940 gzip bytes. Saved-data
authentication is available from a clean checkout with
`python -m scripts.verify_flop_second_board_cfrplus_replay_v2_publication`.
It validates raw file pins, both source maps, complete policies/normalization,
saved public-label transport, exact target outcomes and all replay receipts,
with zero live game builds, ranking, model projection, exact responses, numeric
replays or training. Eight focused publication tests cover the actual corpus,
source drift, file/schema tampering and bounded rational arithmetic.
Final-head CI and publication review are tracked in
[PR #215](https://github.com/ajpaulson18-design/openpoker-lab/pull/215).

The protocol LF SHA256 is
`efe8af15bec9fc9d45f2344c0583d7a3a538ba4f2ba9f05289798ed998e787be`.
This independently written compatibility layer uses project-owned components
and the Python standard library. It changes no production default, shared
turn/river implementation, Coach surface or third-party source/dependency.
