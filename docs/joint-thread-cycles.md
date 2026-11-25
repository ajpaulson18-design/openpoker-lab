# Own-thread compute diagnostics

Status: the sampled frozen-policy-read diagnostic passes exact-wire and fixed
observer-overhead gates on the named local fixture. Finer arithmetic attribution
and any resulting kernel improvement remain open.

The [two lazy-Catalog elapsed misses](lazy-catalog-bitmaps.md) do not identify
whether the extra time comes from native computation, process observation,
host scheduling or other environmental effects. The earlier system profiler
refused collection under the current Windows policy. Keep that refusal and
the old accepted phase-wall observations distinct.

Microsoft documents [QueryThreadCycleTime](https://learn.microsoft.com/en-us/windows/win32/api/realtimeapiset/nf-realtimeapiset-querythreadcycletime)
as returning a thread's user- and kernel-mode CPU clock cycles. Its required
query rights can be exercised through the calling thread's own
[GetCurrentThread pseudo-handle](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getcurrentthread).
This is a narrower observation of the program's own thread, not system-wide
collection or a change to security policy. Microsoft explicitly says not to
convert these cycle values to elapsed time; hardware timer behavior varies.

A Python-only environment smoke check returned successful, monotone own-thread
values. That does not prove native availability, low overhead or solver timing.
The separate source-built `current-thread-cycle-probe` first measures capability
and observation cost without constructing any poker owner. It warms up with
32 queries, then records 1,024 adjacent query pairs, all raw deltas and the
surrounding wall interval. It caps queries at 4,096, output at 32,768 bytes,
entries at 65,536 and logical payload at 1,048,576 bits. Unsupported platforms
reject before build preparation; unsupported APIs and nonmonotone observations
fail instead of substituting another clock.

The wall interval covers 2,049 queries plus loop/storage overhead. Its per-query
ratio is an environment observation, not a pure API cost estimate. Adjacent
pair cycle deltas remain in cycles; never derive seconds from them. Every
original process exit, raw output, source/build identity and failure must be
retained before choosing instrumentation granularity.

Only if the probe supports sufficiently bounded observation should a separate
diagnostic target record coarse thread-cycle phases and a disjoint frozen-policy
read family inside the walk. Preserve standard preprocessor branches, numerical
wires and source provenance. Reserve metadata, clock calls, formatting and I/O
before preparation, and independently gate complete-call overhead against the
same standard target. These measurements must not replace or relax the lazy
storage candidate's existing elapsed acceptance gates.

The source-built probe at `d1b0fa0` succeeds in both Python modes, with one
observed native call each and all 1,024 raw pair deltas retained. Median pair
cycle deltas are 2,127 and 2,121; observed wall intervals average 835 and 753
nanoseconds per measured query, including loop/storage work. These are own-
thread environment observations, not a solver measurement or guaranteed query
cost. No system profiler is started.

The next experiment should sample one of every four frozen-policy reads.
Balancing offsets 0..3 across the same request covers all read positions over
four repetitions while bounding queries. Any extrapolation must distinguish
raw observed cycles, empirical clock overhead and estimated uninstrumented
shares. Preserve all raw calibration data and independently gate observer
overhead before using the result to select another optimization.

## First retained CPU result

Source `ab2c4e14c8eba4b7ff7b9a68e68f182692d59c9a`, MSVC 19.44,
Python 3.12.14: all four requests and four sampling offsets preserve the
complete independently checked numeric wire in both Python modes (40 native
processes). The actual recorder also passes four synthetic offsets, thirteen
native failure guards and sixteen independent parser mutations in both modes.
The first outer synthetic test failed only on Windows text newlines after its
cycle assertions passed; retain those original native outputs and failed logs.

The fixed 260-process comparison completes with median diagnostic / standard
elapsed ratio **1.0143528923875313**, with **two** pairs above 1.10. This passes
the predeclared observer gate. It is permission to use this diagnostic on the
named fixture, not evidence that a solver kernel became faster. Individual
paired ratios range from 0.834 to 1.246; retain every pair.

Across the 128 timed diagnostic calls, the median empirically corrected and
extrapolated frozen-policy-read share of walk cycles is **0.2031827313971546**
(individual-call range 0.1558..0.2793). Per-case median proxies are 0.2350
for tie, 0.2026 for loss, 0.2048 for win and 0.2000 for the shared-board case.
This family includes History, Catalog and Store work. It does not isolate
Catalog CPU or establish exact unobserved shares.

Median recorded phase cycles, summing both epochs within each call:

| Recorded interval | Median CPU clock cycles |
| --- | ---: |
| Template construction and geometry census | 11,869,081 |
| Both native walks, including observer | 25,779,445.5 |
| Raw validation, row joins and Store staging | 23,976,714 |
| Both committed snapshots | 6,558,661 |

These medians are separate observations, not additive percentages of a common
median call. Phase intervals exclude process startup/shutdown. Raw samples,
empty-query pairs and original wall observations are all retained; never
convert CPU clock cycles to time.

The result does **not** justify further speculative Catalog layout tuning.
Most walk cycles remain outside the observed read family. Next split exact
arithmetic/value construction inside the walk, while preserving source,
policy, zero-reach traversal and independent arithmetic. Staging also warrants
attribution before redesigning row identity or quantization. Any subsequent
optimization needs its own unchanged-cap correctness and elapsed gates.

The immutable [CPU packet](../benchmarks/results/joint-thread-cycles-v1/manifest.json)
contains 304 original process receipts, 81 exact shared byte objects and
5,081,563 stored expanded bytes. Its manifest SHA-256 is
`b5318e223def3f5230fb6435a2bee2c5ca9ed42338397c50e14352b46ad55c74`.
`python -B -m scripts.replay_joint_cycles_packet` authenticates the complete
source/build/process closure before importing current numerical modules, then
replays all-row math, every offset, raw cycle accounting and the fixed gate.
Changed manifest/object controls refuse before mathematical imports. Saved
replay makes zero native calls and no hardware queries.

## Frozen sampled-read experiment

The separate `virtual-weighted-joint-single-pass-cycles` target records the
existing 22 phase boundaries and one in four of the 868 frozen-policy reads.
Offsets 0..3 produce exactly 217 sampled reads each, with epoch counts
109/108 or 108/109. The recorder makes exactly 489 counter queries, including
16 empty calibration pairs. It admits 524,288 additional modeled work,
2,048 entries, 131,072 payload bits and at most 8,192 stderr bytes before
preparation. Original numeric stdout and its resource contract remain intact.
The recorder rejects missing/nested observers, cross-thread use, malformed
phase order, incomplete reads, abandoned scopes and unavailable/nonmonotone
clocks. A portable synthetic clock exercises the actual scope and recorder;
an independent Python census checks all four offsets and injected mutations.

`scripts/benchmark_joint_cycles.py` freezes eight alternating pairs of sixteen
calls per target, with two warmups each: 260 processes total. Each block uses
all four weighted request cases (tie, loss, win, changed holding on the same
board) at all four offsets. The observer passes only if median diagnostic /
standard elapsed time is at most 1.05 and at most two pairs exceed 1.10.
There are no automatic retries. Initial `--parity-only` execution checks all
case/offset combinations separately and does not constitute overhead acceptance.

Raw cycle counts are primary. Four times sampled read cycles is an extrapolation
across repeated requests, not an exact observation of every read in one call.
Subtracting the median empty-query-pair cost is only an empirical correction:
the clock cost varies, and observer checks, branching and compiler effects
remain. The read family includes History, Catalog and Store operations; it
does not isolate an individual owner. Sampled CPU data must not justify
another optimization unless the fixed observer-overhead gate passes.

## Frozen arithmetic helper experiment

The next separate diagnostic target is
`virtual-weighted-joint-single-pass-arithmetic-cycles`. It observes disjoint
reach updates, terminal-value construction, average-row construction and the
post-child value/regret mixing body. Scopes include local guards, modeled
ledgers and allocations; they are not pure multiprecision instruction latency.
The standard target's preprocessed numerical path stays unchanged.

The independent numeric betting rules derive the complete ordered helper
sequence: 1,039 reach, 606 terminal, 434 average and 434 mix calls per epoch.
Two epochs give 5,026 calls. One-in-32 observation makes 157 or 158 samples,
369 or 371 counter queries including calibration and 22 phases. Before any
preparation the diagnostic reserves 655,360 work, 2,048 entries, 131,072
payload bits and 8,192 stderr bytes within existing whole-request ceilings.
No game, Store, integer-width or global resource limit is raised.

The actual recorder's portable synthetic clock covers all 32 offsets and
four unequal known helper costs. Balanced extrapolation across those offsets
must recover each family's exact total; fourteen native guards and independent
parser mutations check failure behavior. Native parity must cover all four
requests at every offset, plus real argument rejections.

`scripts/benchmark_joint_arithmetic_cycles.py` then freezes eight alternating
pairs of sixteen calls, plus two warmups per target (260 processes). Case
index is `i%4`; offset is `(5*(4*block+i//4))%32`. Over eight blocks each
case sees every offset exactly once. Acceptance again requires median
diagnostic/standard elapsed ratio at most 1.05 and at most two pairs above
1.10, with no automatic retries. This is a new observer gate; the accepted
policy-read observer does not admit it. No arithmetic observations or solver
kernel improvement are claimed before execution.

### First arithmetic observer: overhead miss

At source `7d5401712a3f104628949e20a864db18bfe0a939`, both synthetic modes
pass all 32 offsets, fourteen native guards and 96 parser mutations. The
independent numeric betting rules agree on the complete ordered call sequence.
Both 135-process native parity matrices pass all four requests at every
offset and three real argument rejections, preserving all numeric bytes.

The separately frozen 260-process overhead comparison **fails** its unchanged
gate: median diagnostic / standard ratio **1.295510026587876**, with **six**
pairs above 1.10. Keep every original pair and raw CPU record. These helper
shares are **not admitted for kernel selection**. Comparison completion with
exit zero does not mean acceptance. Do not repeat unchanged until it passes.

The [immutable arithmetic packet](../benchmarks/results/joint-arithmetic-cycles-v1/manifest.json)
retains 532 original native processes, 85 shared byte objects and 7,117,897
stored expanded bytes. Manifest SHA-256:
`dc78a8c65b8be4e7f47ab8229fdd7c06611d259df4d52eb14b0e1f44a4db0233`.
`python -B -m scripts.replay_joint_arithmetic_cycles_packet` authenticates
source/build/process evidence before numerical imports and independently
replays arithmetic, offset accounting and the original observer miss. It
makes no native or hardware calls and returns `attribution_admitted=false`.

The next justified profiler change is to avoid virtual calls and thread-ID
queries on unsampled helper calls, preserving thread-local installation,
sampled ownership checks, exact counters and all failure guards. It needs
its own source freeze, exact-wire checks and the same fixed overhead gate.
No solver arithmetic change is justified by this failed observer.

On GitHub at `6ba9eea`, all CPU saved-replay, native-control and Windows
whole-wire checks pass, but all three jobs fail the artifact upload because
the action rejects `..` in patterns. The
[first upload failure](../benchmarks/results/joint-thread-cycles-ci-v1/first-upload-failure.txt)
is retained separately. A corrected workflow stages only named evidence
under an absolute runner-temp root; its complete result remains to be checked.

### Frozen typed-TLS observer revision

The separate `virtual-weighted-joint-single-pass-arithmetic-light-cycles`
target replaces type-erased virtual scope dispatch with a typed thread-local
recorder. Unsampled helper entry/exit checks use that installation and the
same exact census; they make no OS thread queries. Sampled clock calls and
phase boundaries retain actual-thread checks. Installation is one-at-a-time per
thread, nested contexts reject, scopes cannot be copied, abandoned scopes
poison the recorder, and a real foreign thread must fail before observing.
Mixed diagnostic build contracts reject at compilation.

The version-two stderr frame names `typed-tls-inline-v1`. An independent
wrapper requires that mode, then uses the unchanged numeric-rule sequence
and v1 sample/accounting authority. Four unequal synthetic costs, all 32
offsets and the added foreign-thread guard remain mandatory. The diagnostic
uses the same 655,360 work, 2,048 entries, 131,072 payload bits, 512-query and
8,192-byte reservations as the failed observer; no game ceiling changes.

`scripts/benchmark_joint_arithmetic_cycles.py --light` keeps the same four
requests, 32 offsets, eight alternating pairs, sixteen calls per block and
two warmups per target. Its fixed gate is still median ratio <=1.05 with at
most two pairs >1.10; no automatic retries. The v1 miss is immutable and
cannot be superseded by this observer. No revised CPU attribution or runtime
acceptance is claimed before execution.

### Typed-TLS result: second arithmetic-observer miss

At source `dea4f35458481f67eb427645a39080753211dd14`, the typed-TLS
recorder passes both synthetic modes, all 32 offsets, fifteen native guards
(including a real foreign thread), 96 parser mutations per mode, and both
135-process all-row parity/argument matrices.

Its separate 260-process comparison also **misses** the unchanged overhead
gate: median ratio **1.1987937230308239**, with **seven** pairs above 1.10.
Do not use its helper-cycle shares for kernel selection or treat the different
observer medians as a measured solver speedup. Raw data, all policies and every
pair remain preserved. Both arithmetic observers remain diagnostic experiments;
neither is an admitted source of fine CPU attribution.

The [typed-TLS packet](../benchmarks/results/joint-arithmetic-light-v1/manifest.json)
retains 532 original native processes, 87 shared objects and 7,176,927 stored
expanded bytes. Manifest SHA-256:
`1c7beace60d836d94ec015ec3b39c33c7a1a197b46674804d24f841a0dc4fcdb`.
`python -B -m scripts.replay_joint_arithmetic_cycles_packet --light` independently
replays complete arithmetic, offset census, foreign-thread guard and this
unchanged miss after evidence/source admission. Its output must keep
`attribution_admitted=false`, with zero native or hardware calls.

Stop tuning per-helper observers after these two distinct failures. The
accepted read/coarse-phase evidence is still useful: reads are a minority of
walk cost and staging is substantial. Next separate Store staging from public
row joins using a lower-frequency observation contract before a staging kernel
change. Broader branch-work reduction also needs an independent unbiasedness,
variance and lifetime-storage study; these profiler misses do not justify a
specific arithmetic rewrite or any larger solver cap.

The corrected CPU workflow is fully successful on Windows, Linux and
sanitizers at `48433ca`, including artifact publication and v1 arithmetic saved
replay. The same head's Python 3.13 regression job passes 3,356 tests with 171
skips. The new typed-TLS CI remains separate and must be checked at its own head.
