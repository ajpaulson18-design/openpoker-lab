# Baseline positive-prior call diagnostic

This separate diagnostic follows the three independently replayed
[positive-prior quality passes](flop-class-reweight-cfrplus.md). It measures one
baseline 560-sweep call with reversible phase instrumentation, then one separate
call with Python allocation tracing. Both must reproduce the complete published
baseline report byte for byte. It changes no solver/proof/recurrence, default,
production API, AI Coach or shared street kernel.

## Frozen scope

The [protocol](../benchmarks/flop-class-reweight-baseline-diagnostic-v1.json)
admits both full baseline requests before prerequisite authentication or solver
work: 75,107,956 named units each, 150,215,912 total under a separate 153-million
reservation. Four physical builds / 23,760 world rows / at most two live physical
games are separate census references. These are not bounds on all arithmetic,
time, allocated bytes or RSS. The diagnostic requires CPython 3.12.14 before
measured work, because the complete pilot report contains that runtime identity.
This does not change the application's Python >=3.11 support.

The prerequisite check authenticates the immutable pilot index and baseline
report bytes, then releases the decoded report/raw bytes before measurement.
It performs no physical replay. The two samples execute sequentially in one
persistent process after imports/preflight, with GC before each. A reversible
shared-trainer counter delegates the unchanged function and requires exactly
one invocation per sample, two overall. One traced sample provides an allocation
observation, not a stable memory advantage or a fresh-process measurement.

The first sample wraps nine existing module boundaries: no-training publication
verification, old compact-pilot read, weighted model building, training inputs,
shared training, output normalization, lift, audit and weighted-model validation.
The immutable existing profiler supplies the reversible nested event ledger,
bounded at 1,000 events. Inclusive parent/child wall/CPU durations overlap and
must not be summed across nesting. Wrappers are removed before the allocation
sample; their overhead remains part of the profiled interval.

Both samples use the existing complete-call measurement helper. The measured
window includes library preparation/authentication/training/diagnostics plus
canonical JSON serialization and hashing. Outer source snapshots, prerequisite
byte authentication, gzip/file I/O and subsequent saved replay are excluded.
The second sample starts `tracemalloc` separately: the peak covers new Python
allocations in that call/serialization/hash window, excludes RSS/native/preexisting
allocations and is not a total memory bound. Counter overhead is included in both
calls; phase wrappers are included only in the first.

Clean committed revision/status/LF source snapshots must remain identical before
and after every sample and overall. Raw returned reports are retained before
acceptance with bounded gzip/raw hashes; full raw and artifact identities must
match the published baseline, preserving exact strategy, priors and quality.
The harness releases first-sample raw/compressed objects and collects before the
trace. It retains original failures/partial events and stops later samples on the
first error without retry or discarded runs. Single-call observations establish
no medians, throughput, speedup, RSS, general bottleneck or convergence-rate claim.

## Status and provenance

No actual diagnostic call has run at this source checkpoint. The preceding
training and three fresh saved replays are published in merged
[PR #207](https://github.com/ajpaulson18-design/openpoker-lab/pull/207), merge
`08e3a339eadfcff706fa75f0851e8f9978361ce2`. Both final Python 3.11/3.12/3.13
matrices passed; the reviewed pilot head and original advance-solver commit are
ancestors of fetched GitHub main. Actual diagnostic execution requires this
reviewed clean frozen source/protocol. Twenty-two focused harness, measurement
and wrapper tests passed on CPython 3.12.14. Synthetic tests do not provide
runtime or allocation evidence. All existing mathematical and published measurement
sources remain intact. No third-party source or dependency is incorporated; see
[commercial boundary](research/LICENSING.md),
[prior phase profile](flop-class-phase-profile.md) and
[primary cost study](flop-class-call-cost.md).
