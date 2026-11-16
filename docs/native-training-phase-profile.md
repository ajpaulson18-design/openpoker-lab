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

## CPU samples inside the walk

The [CPU evidence packet](../benchmarks/results/native-dyadic-walk-cpu-v1/manifest.json)
captures three complete calls of the standard bounded-division trainer at
`53a4072`, using the same Windows executable as the earlier code-layout
control. Each call reproduced the 50,507,464-byte training stream, both
checkpoint files, the policy spill, and the row directory byte for byte.
The collector requested 4,000 CPU samples per second and reported no lost
events or buffers.

The replay counts samples whose native stack contains `Walk::visit`.
Each row below counts a function entry anywhere in that stack. Nested
functions share samples, so the percentages cannot be added.

| Function on the walk stack | Capture 1 | Capture 2 | Capture 3 |
| --- | ---: | ---: | ---: |
| Walk samples | 16,327 | 16,407 | 14,054 |
| Terminal evaluation | 31.2% | 31.2% | 31.3% |
| State row staging | 30.7% | 28.7% | 28.9% |
| Prepared Chance contraction | 15.3% | 15.4% | 14.6% |
| Pager dirty-page flush | 13.4% | 12.6% | 12.3% |
| History visit action | 0.3% | 0.5% | 0.5% |
| History visit reveal | 0.1% | 0.1% | 0.1% |

Terminal evaluation or State row staging appears in 59.9–62.0% of the
walk samples. Dirty-page flushing belongs to the staging path and
prepared contraction belongs to the Chance path. These observations
prioritize reducing packed State staging and pager work, then separating
terminal contraction from the remaining payoff and parent arithmetic.
An owner-level change must reproduce the exact output and checkpoint
images and improve complete-call elapsed time in a matched comparison.
The eleven-card resource forecast still projects work above the current
State, quantizer, and composed ceilings.

To reproduce the capture, authenticate the source-built standard target
at the packet's source revision and attach the Visual Studio command-line
collector to the trainer before supplying the manifest's request, with
a fresh absolute `page-images` path. Use `CpuUsageHigh.json` and stop
the collector after the trainer exits. Extract the auxiliary ETL from
the diagnostic session and use `xperf -a dumper` on that ETL. Relink the
same object with MSVC `/MAP`, and compare the native `.text` bytes and
section address with the sampled executable before using the map. The
packet's `normalize.py` takes the xperf CSV, linker map, and a fresh output
path. `replay.py` recounts the three archived captures without running or
compiling the trainer.

The archive keeps only the trainer's relative instruction addresses,
relative timestamps, sample counts, and matched linker names. Symbol
attribution uses the preceding function entry and retains aliases at the
same address. Inlined work may belong to the surrounding named function.
CPU samples describe one host and one finite ten-card fixture. The
earlier elapsed measurements use different intervals, including time
waiting for I/O.
