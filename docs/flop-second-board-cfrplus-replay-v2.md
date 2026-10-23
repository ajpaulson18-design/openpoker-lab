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

## Execution status

Fourteen focused tests pass on bundled CPython 3.12, including real protocol
loading/admission with poker work forbidden, nested-wrapper exact-once behavior,
57/59-source rejection, full replay receipt persistence, per-case early rejection
and first-error/source-drift retention. Lead and bounded GPT-6 Luna reviews found
no remaining blocker after those independent batch checks were added.

Only synthetic validation has run for this version. No v2 model preparation,
ranking, numeric replay or training experiment is claimed yet. Finish review,
prerequisite merge validation and a clean executable/protocol freeze before
running `python -m scripts.benchmark_flop_second_board_cfrplus_replay_v2
--output-dir PATH` with a new output directory outside the repository.

The protocol LF SHA256 is
`efe8af15bec9fc9d45f2344c0583d7a3a538ba4f2ba9f05289798ed998e787be`.
This independently written compatibility layer uses project-owned components
and the Python standard library. It changes no production default, shared
turn/river implementation, Coach surface or third-party source/dependency.
