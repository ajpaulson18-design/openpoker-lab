# Fixed-flop complete-call cost experiment

This preregistered study compares the complete cost of the same fixed flop
game at two validated quality/work budgets: the original class entry at 140
sweeps (a preserved target miss), and the explicit compact-work entry at 560
sweeps (a finite-game target pass). Both already use the same 126 class worlds,
466 information sets, CFR+ recurrence and output normalization. This is not a
comparison of representations or a speedup at equal work.

## Frozen measurement boundary

The [protocol](../benchmarks/flop-class-call-cost-v1.json) fixes three paired
rounds, with order 140/560, 560/140, 140/560, followed by one separate allocation
call per entry. All eight requests must preflight before any solve/proof call.
The common benchmark-only named-work forecast totals 375,724,160 units under
a 400-million experiment ceiling; each actual entry retains its own admission.
The common forecast does not replace or weaken either solver entry's checks.

A timed sample includes the complete library function, including internal proof
reconstruction, preparation, training, normalization, physical policy lift and
exact/numeric diagnostics. It also includes canonical JSON serialization and
SHA-256. It excludes source snapshots, gzip/file I/O and additional saved
replay. Garbage collection runs before every call, outside its timing window.
Only the six untraced calls contribute to their per-entry medians.

The two separate `tracemalloc` calls cover the same solve/serialization/hash
boundary. Their peaks are Python traced allocations, not total process memory
or RSS; native/library/kernel allocations and prior interpreter memory can be
outside that trace. The helper rejects an already-active trace and always
stops its own trace on errors. Traced elapsed times are retained but excluded
from primary runtime medians.

Each call records UTC start/end, monotonic wall seconds, process CPU seconds
and Python/platform identity. The CLI uses the existing temporary Windows
execution-state request and restores the prior flags. That request does not
prove exclusive CPU access or rule out every interruption/suspend. Keep all
samples and elapsed gaps; qualify observations rather than dropping outliers.
No generic speed, unrestricted NLHE, convergence or RSS claim follows.

## Source, payloads and failure retention

Before measurement, require a clean committed source revision, authenticate
both published pilot artifacts and freeze executable/protocol LF identities.
Require the same revision, status and identities before and after each call.
Save the active request before starting it and preserve each completed row or
traceback immediately. The output directory must be new and outside source;
never restart a sample to select a better result.

Keep every complete report/policy in a bounded lossless gzip. Compare each
report with its independently replayed pinned pilot after removing only its
runtime field and artifact checksum; also validate its own checksum. Require
all four reports for each entry to match exactly within the measured runtime.
Thus the old miss and new pass remain separate outcomes. Saved verification
reads and authenticates every stored payload and recomputes summaries without
training or replaying the solver. Source or payload drift invalidates the study;
a failed/incomplete run remains retained as such.

The project-owned standard-library measurement helper changes no solver,
recurrence, oracle or Coach implementation. No third-party source/dependency
is incorporated. See the [quality milestone](flop-class-compact-cfrplus.md) and
[licensing boundary](research/LICENSING.md).

## Published observations

The single preregistered eight-call run completed on 2026-10-22, from clean
source `20a1f1dcf518895dd54ed5a9eb7ddc52fe1d89d4`, with no retries, discarded
samples, source drift or recorded errors. CPython 3.12.14 on Windows 10 ran
all calls in one process. Imports/startup are outside the library-call boundary;
allocation calls follow the six timing calls and GC, so prior retained objects
and caches may be outside the trace. These are not fresh-process measurements.

| Entry | Three untraced wall samples (s) | Median (s) | Python traced peak (bytes) | NashConv (decimal display) / 0.005 gate |
| --- | --- | --- | --- | --- |
| 140 sweeps | 133.061762, 150.169832, 148.360679 | 148.360679 | 96,955,723 | 0.012537880082162792 / miss |
| 560 sweeps | 179.545349, 168.325548, 175.079169 | 175.079169 | 96,959,799 | 0.0028924005277596834 / pass |

Both Python traced peaks are about 92.5 MiB. Each is one separate trace, not
RSS or evidence of a stable memory difference. The traced calls took
702.737329 s (140) and 554.453560 s (560), with CPU times 694.546875 s and
542.656250 s. Their reversed timing order is retained and excluded from the
primary medians. Timed-call CPU seconds are 132.593750, 177.625000,
166.875000, 148.859375, 147.203125 and 174.734375 in protocol order. All
elapsed variation remains evidence; CPU/wall agreement and the temporary
Windows request do not establish exclusive CPU access or a universal cost.

Every one of the four complete raw policies per method is byte-for-byte equal
to its published pilot. All eight internal physical-response audits therefore
retain their published exact class/physical agreement, including the miss.
The study changes neither policy, quality target, solver nor admission.

## Evidence and verification

The [complete saved index](../benchmarks/results/flop-class-call-cost-v1/index.json)
records all eight payload paths, raw/gzip hashes, UTC/wall/CPU observations,
source fingerprints and runtime/request metadata. The eight lossless gzip
reports total 1,091,724 bytes. Index identities are:

- Raw SHA-256: `15fa0dd9c90ecacee4337dca2649cdf771f0f46569bf24d1a2d6056e10ef3a7f`.
- Canonical index SHA-256: `80c95f4ec6f2af7d8797a7eb6de335c625332a75d0cc77e6993feac1c615bc49`.

The immutable publication verifier pins both identities and the frozen source
revision before checking all saved payloads, then authenticates the index again:

```sh
python -B -m scripts.verify_flop_class_cost_publication
```

The generic saved verifier was actually run on the complete external bundle
and passed all eight calls without training, proof reconstruction or physical
replay. Its payload check authenticates every report against the separately
replayed published pilots; it is not another independent replay of poker rules.
The publication wrapper has separate synthetic tamper and reauthentication tests.
All three retained Windows validation logs were also checked against the
compressed/uncompressed hashes and sizes in their qualification receipt.

Next, use a separate instrumented phase profile to locate time allocation before
choosing another performance architecture. Keep its instrumentation conditions
separate from these primary samples.

The [Windows validation qualification](flop-class-windows-validation.md)
preserves the preceding failed duplicate local run and unchanged-code reruns.
