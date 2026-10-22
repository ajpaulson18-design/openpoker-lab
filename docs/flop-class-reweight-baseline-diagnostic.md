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

## Completed frozen observation

The single admitted batch ran on source
`602a37eac96dfd146069e361f2501efff15b3576`, from
2026-10-22 16:17:17.739607 to 19:05:58.427508 UTC. Both samples completed,
with exactly one shared trainer invocation each and two total, no errors or
retries, and identical clean HEAD/status/35-source maps before and after every
sample and overall. Every returned byte equals the previously independently
replayed baseline pilot: raw SHA256
`902420ca04f52e1b64fda5127adc074357e41151e07565488d3d859399147cf9`, artifact
`a3f94b109cff3ce8e4b487b4a376160f152d4114ec39173a31f8db6e1a51983d`.
Its exact physical-response NashConv remains `0.0028924005277596834`, passing
0.005; these diagnostics add no new convergence result.

| Sample | Complete-call wall seconds | Process CPU seconds | Python traced peak bytes |
| --- | ---: | ---: | ---: |
| Phase instrumentation | 242.0216675 | 191.093750 | Not traced |
| Separate allocation trace | 9873.9262813 | 711.265625 | 401,901,644 |

The allocation sample spans a large wall/CPU gap that was observed while the
same authoritative process remained alive. That gap and tracing overhead are
retained; no cause is assumed, no run was replaced, and these timings are not
a controlled runtime comparison. The peak measures new traced Python
allocations in the stated window, not RSS, all live/native/preexisting memory,
a stable memory advantage or a byte bound. The two calls share a warm process.

All 13 phase events completed. The eight non-nested root intervals were:

| Root phase | Inclusive wall seconds | Inclusive CPU seconds |
| --- | ---: | ---: |
| No-training publication authentication | 30.5307875 | 21.468750 |
| Old compact-pilot read | 0.8112848 | 0.671875 |
| Weighted physical model construction | 27.2673736 | 22.796875 |
| Training input preparation | 22.8716521 | 17.921875 |
| Shared CFR+ training | 80.9469212 | 63.812500 |
| Output normalization | 0.1316145 | 0.078125 |
| Initial physical policy lift | 22.5740261 | 17.500000 |
| Independent physical audit | 55.8665427 | 46.046875 |

Four nested `weighted.validate_model` intervals total 79.6207668 wall seconds;
they are included within the relevant root intervals above. Audit also contains
a nested lift/validation. Do not add these nested measurements to the root
measurements. The observations motivate investigating privately owned prepared
state with complete integrity coverage; they establish no speed benefit,
general bottleneck or permission to skip model/policy/physical-response checks.

## Saved files and authentication

The [index](../benchmarks/results/flop-class-reweight-baseline-diagnostic-v1/index.json)
preserves every event, measurement, source snapshot and admission receipt.
The complete returned reports are retained separately for the
[phase sample](../benchmarks/results/flop-class-reweight-baseline-diagnostic-v1/phase-profile.json.gz)
and [allocation sample](../benchmarks/results/flop-class-reweight-baseline-diagnostic-v1/python-allocation.json.gz).
Each gzip has 138,363 bytes (6,163,274 raw bytes); both contain the exact
baseline report. Index raw SHA256 is
`aa18563a9f01c30faa52d8f2c72188892f3a838a9d25cb6c3bb663a28fda74d8`,
and canonical self-digest is
`919a16138442300a6125159fdc7a72767903896570c556396a0b8984a7a16a07`.

```text
python -m scripts.verify_flop_class_reweight_baseline_diagnostic_publication
```

This publication command authenticates bounded index/gzip bytes, the frozen
protocol, source identities, trainer counts, baseline parity, modes, UTC
chronology, nested event intervals and Python peak metadata. It rechecks files
and the current clean source map at the end. It performs no model construction,
training, ranking or physical replay. A later clean publication HEAD is allowed
only with the same 35 executable/specification hashes as the measured source.
No additional physical replay is claimed: byte-identical reports bind these
observations to the pilot's three fresh saved-policy reconstructions.

## Provenance and limits

The prerequisite pilot and fresh saved replays are published in merged
[PR #207](https://github.com/ajpaulson18-design/openpoker-lab/pull/207), merge
`08e3a339eadfcff706fa75f0851e8f9978361ce2`. Its reviewed head and the original
advance-solver commit were verified ancestors of fetched GitHub main before
this diagnostic. This publication is tracked in
[PR #209](https://github.com/ajpaulson18-design/openpoker-lab/pull/209).

Luna implemented the bounded diagnostic and saved-evidence verifier; lead
reviewed admission, per-sample trainer counts, report retention, wrapper
restoration and timestamp containment, requiring corrections before execution
or publication. Twenty-two focused harness/measurement/instrumentation tests
passed before source freeze; ten publication tamper/chronology tests passed
independently in scratch. All 32 integrated focused tests and the documentation checker passed.
Final-head CI and publication authentication are recorded in the PR. The actual two-sample batch had no failure/retry. All existing
mathematical and published measurement sources remain intact. No third-party
source or dependency is incorporated; see
[commercial boundary](research/LICENSING.md),
[prior phase profile](flop-class-phase-profile.md) and
[primary cost study](flop-class-call-cost.md).
