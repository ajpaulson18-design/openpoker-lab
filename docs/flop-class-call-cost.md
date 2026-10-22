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

No cost experiment has run at this source checkpoint. Implementation and its
frozen source revision must be validated before execution.

The [Windows validation qualification](flop-class-windows-validation.md)
preserves the preceding failed duplicate local run and unchanged-code reruns.
