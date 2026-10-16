# Optional native full-board preflop equity preparation

The separate native entry point accelerates bounded full-board counting. The
ordinary Python preparation and solver remain the default/reference. This is a
source-checkout development feature: explicitly build the project-owned C helper
with an installed compiler, then choose it. Compilation, installation and
fallback are never automatic.

```sh
python -m scripts.build_native_preflop --output-dir build/native-preflop
```

POSIX requires `cc`; Windows requires an installed x64 MSVC developer environment.
See Microsoft's [command-line setup](https://learn.microsoft.com/en-us/cpp/build/building-on-the-command-line?view=msvc-170).
The builder uses argument arrays, fixed recorded flags and explicit failures.
There is no new Python dependency.

```python
from pokerlab.native_preflop_equity import prepare_native_preflop_equities
from pokerlab.preflop_push_fold import solve_prepared_push_fold

prepared = prepare_native_preflop_equities(
    "AsAd:1,QsQd:.5", "AsKh:.25,KsKd:1",
    build_directory="build/native-preflop",
)
result = solve_prepared_push_fold(
    prepared.equities, config={"starting_stack": [3, 2]},
    iterations=2000, algorithm="cfrplus",
)
provenance = prepared.metadata
```

Normal expansion, exact binary64-weight fractions, collision conditioning and
all fixed caps run before binary lookup/execution: 4,096 candidate pairs, four
compatible pairs, 6,849,216 unordered boards and 13,698,432 logical hand-rank
evaluations. Each pair still counts all 1,712,304 final boards. Native output
supplies only integer W/T/L counts; Python constructs and validates the same
immutable `FullBoardEquities`, exact category masses and world ordering.
Downstream source-inclusive solver admission is unchanged. Preparation alone
does not admit an arbitrary training request.

This separate API has no progress callback; existing Python callbacks retain
their established behavior. Native preparation has a 120-second process timeout,
rejects changed source/binary identities and malformed output, and never silently
substitutes Python. The bounded ASCII protocol validates all input before work,
caps COUNT at four pairs and conformance RANK at 4,096 hands, and rejects invalid
cards, duplicate cards and trailing input. Invalid requests emit no partial
result. Python caps response reads; temporary files are not a hard storage cap
against a faulty or untrusted executable.

Build provenance records compiler path/version, flags, platform, raw and
LF-normalized C-source SHA-256 and executable SHA-256. Preparation returns it
separately from the ordinary solver payload, with actual logical board and rank
counts, and checks current source/executable bytes before and after execution.
These identities and structural checks are reproducibility information, not
authentication of arbitrary local binaries or caller-supplied counts.

## Implementation and distribution

`native/preflop_equity.c` implements this repository's own category/kicker rules
with small rank-count/suit-mask arrays and ascending board loops. No imported
evaluator, lookup table, third-party source or binary is used. No executable or
object file is committed, and the repository license remains unchanged.

Local MSVC builds use `/MT`; see Microsoft's [runtime linkage documentation](https://learn.microsoft.com/en-us/cpp/build/reference/md-mt-ld-use-run-time-library?view=msvc-170).
This slice distributes source. Shipping compiled applications would require a
separate packaging/runtime-notice review under the applicable toolchain terms;
these build facts are not legal clearance.

## Validation and measured status

At frozen `ee87737cccc34fd3ed47782f90ecb8b17f5bf5d2`, all fifteen measured
complete calls pass: twelve native calls across four fixtures and three fresh
Python calls on the paired base fixture. Every native table, work budget and
complete solver dictionary exactly matches the reference assembled from the
three pinned independently enumerated PR #125 physical-count artifacts. The
fourth split-pair count uses a documented global suit bijection of the independent
source count. Native preparation itself re-enumerates every physical board in
each measured call; the independent oracle enumeration is reused.

All fixtures train 2,000 CFR+ iterations, including exact diagnostics and JSON.
Numeric-rule own-hand best-response replay agrees within `1.324e-16` chips.
Maximum exploitability is `0.0000146361` and known equilibrium-value error is
`4.202e-9` chips; every profile passes both predeclared 0.005-chip gates with
`1e-10` padding. Three-pair games charge 370,245,216 modeled entries; the
four-pair split game charges 493,147,312. The original 500-million limit holds.

| Fixture | Native complete-call samples, seconds | Native median, seconds |
| --- | --- | ---: |
| Three pairs, stacks 3/2 | 1.20543, 1.62903, 1.57198 | 1.57198 |
| Three pairs, stacks 2/2 | 1.83905, 1.27280, 1.71972 | 1.71972 |
| Three pairs, stacks 2/3 | 1.72948, 1.53367, 1.57731 | 1.57731 |
| Four split pairs, stacks 3/2 | 2.31961, 1.80004, 2.22368 | 2.22368 |

The paired fresh Python samples are **483.02199, 431.19727 and 664.05387**
seconds, with median **483.02199**. Against the native median of **1.57198**,
the recorded median ratio is **307.27× for this fixture and machine/build**.
The selected [Windows Power-Troubleshooter event](../benchmarks/results/native-preflop-host-events-v1.json) records a sleep from `2026-10-16T15:04:42.0273515Z`
to `2026-10-16T15:08:05.6345202Z` during the third Python call. Its entire raw
664.05387-second observation is retained; no time is removed or sample discarded.
The median is the first Python observation. These are observed wall times, not
a universal solver or pure evaluator speed claim.

Both intervals include preparation, training, diagnostics and serialization;
compilation and independent verification are outside timing. Python uses no
progress callback, and stage-level progress writes occur outside both intervals.
Native calls additionally include Python ranking guards and preparation metadata
serialization. A separate complete native call under `tracemalloc` takes 7.01317
seconds and peaks at **347,984 Python bytes**, with payload identity matching the
timed call. This excludes compiler work, native-process allocations and RSS;
native memory and any memory saving are unmeasured.

The [raw benchmark](../benchmarks/results/native-preflop-v1.json) retains every
sample, exact prior, physical-count identity, witness/replay, work census and
frozen source/build identity. Its canonical artifact SHA-256 is
`f808a4a37c69c2511c514e23afeaad436ef055e1ae978bc178d38b2c3f89db10`.
The [exhaustive native report](../benchmarks/results/native-preflop-evaluator-v1.json)
checks all **2,598,960 five-card rank tuples** against the independent best-five
oracle with **zero mismatches** and all nine known category totals. It took
119.68088 seconds including validation; this is not native-only ranking time.
Its canonical checksum is
`bb2940c0eee02ea8743f3097bedcb627f2ee51e0186dbbebd1dd9ee07c699053`.
This does not exhaust six- or seven-card hands; focused vectors and 1,000
deterministic seven-card hands cover those paths.

All 17 focused local tests pass, including real native full counts, role reversal,
three stack configurations, malformed protocol responses and benchmark failure
retention. Dedicated CI builds with installed MSVC on Windows and `cc` on Linux;
ordinary Python-only CI requires no compiler. After measurement, test-only fixes
remove a shallow-Git-history assumption and compare Windows file identity across
temporary-path aliases. Evaluator, adapter, build, benchmark and fixture source
remain identical to the measurement freeze. Final publication CI is recorded
on [PR #135](https://github.com/ajpaulson18-design/openpoker-lab/pull/135).

The game remains heads-up SB fold/shove and BB fold/call with forced showdown.
Calculation speed adds no betting branches, multiway support or equilibrium
guarantee.
