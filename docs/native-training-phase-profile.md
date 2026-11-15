# Bounded native training phase diagnostics

The ten-card bounded-division T2 fixture has a separate diagnostic build.
The standard trainer compiles without phase hooks. This is a measurement
tool for the existing finite game, with no additional capacity or quality claim.

## Build and request boundary

Build the standard executable with target `virtual-dyadic-training`
and the diagnostic executable with target `virtual-dyadic-training-profile`
using `scripts.build_native_exact_four_street`.
Only the latter target defines `OPENPOKER_TRAINING_PHASE_DIAGNOSTICS`.
Its manifest names the target, flags, compiler, executable and source closure.

The diagnostic executable accepts the existing bounded-division training
request, an absolute fresh `page-images` scratch path and the third argument
`--profile-phases`. The host cohort selects the diagnostic target only when
`--profile-phases` accompanies `--train --ten-bounded-division`.
Other requests and unknown flags are rejected before scratch preparation.
The standard executable rejects the profiling argument.

An independent comparison against source `927e4a3` found the normal
Driver header and probe main token-identical after selecting the normal
preprocessor branches. The normal constructor and train signatures are
restored; compile-time assertions guard the differing signatures. This
is source-level hook separation, not proof of identical machine code.

## Bounded measurement contract

The recorder has 64 fixed event slots and permits at most 80 clock reads.
This fixture uses 36 events and 43 reads, including the origin and six
outer timestamps. The object occupies 1,064 bytes on the measured Windows
build; the resource bridge reserves 2,048 bytes, 256 logical entries and
8,192 work units. It adds those diagnostics to the inherited composed
budgets before admission and leaves the solver's ledgers unchanged.

The phases cover Plan preflight; Chance and other owner setup; row
registration; freeze; prelude; per-sweep policy construction, policy
emission, inclusive walk, commit and checkpoint streaming; average
export; and footer extraction. Checkpoint intervals include stream
flushing. There are no per-row, per-contract or arithmetic clock calls.

Driver includes Plan. The verifier reports Plan and the remaining
Driver interval without counting Plan twice. It partitions the training
interval into non-overlapping leaf phases and a nonnegative residual,
and reports outer output work separately. State/Chance/History cleanup
after the last phase remains in the training residual.

The measurement excludes startup and request parsing, sidecar writing,
Driver destruction and process exit. The independent complete-call
timing includes process execution and streamed transport. These are
different intervals and should not be compared as equal durations.

The strict independent verifier checks the bounded sidecar's schema,
finite integer types, exact event order/sweeps, clock census, monotonic
and hierarchical timestamps, nonnegative residuals, and resource
derivation. It makes no native producer calls.

## Frozen studies and limits

The [immutable packet](../benchmarks/results/native-dyadic-phase-profile-v1/manifest.json)
retains both source-frozen studies and all timing observations.

The first study used one executable with hooks disabled or enabled.
Instrumentation's median paired ratio was 0.99002, while the disabled
hooked executable versus the pristine baseline measured 1.01857.
The latter missed the predeclared 1.01 limit. Its phase ranking was
provisional and the study was not accepted. A separate diagnostic build
was then introduced; the limit was unchanged.

The revised study at `53a4072` uses eight alternating pairs for each
comparison. Diagnostic instrumentation measured a median paired ratio
of 1.00327 (0.33 percent overhead). The standard trainer versus the pristine
baseline measured 0.99392; this passes the overhead limit and is not
claimed as a causal speedup. Both comparisons passed the unchanged
1.01 limit, and every one of the 32 complete training calls reproduced
the reference artifacts. Walk ranked first in all eight enabled runs.
Its median fraction of the measured interval was 69.05 percent, followed
by checkpoint streaming at 12.88 percent and policy construction at
8.40 percent. These are wall-time observations on one Windows host;
other host load was uncontrolled.

Both studies reproduce the pristine baseline's complete compact and
expanded outputs, policy spill, row directory, checkpoint images and
visible-information best responses. Enabled and disabled saved-only
replays enter no native producer. The second study archives one raw
checkpoint pair; duplicate timed outputs are represented by their exact
identities against the archived reference.

All 89 focused controls pass in normal and optimized Python, with no
skips. Native deterministic vectors verify all 26 fake-clock events and
failure guards. The packet preserves the initial temporary-directory test
failure and its test-only correction, the first auxiliary vector-operator
failure and correction, and a timing-operator syntax failure before any
timed calls. These are distinct from the completed timing studies.

Walk timing includes Chance, State, History and parent computation.
It cannot attribute costs among those owners. The next step is bounded
external sampling on the standard trainer, followed by one measured
owner-level change. Eleven-card training, broader-deck quality,
convergence, and commercial-scale performance remain unproven.

