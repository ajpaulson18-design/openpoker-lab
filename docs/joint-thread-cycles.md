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
