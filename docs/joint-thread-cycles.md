# Own-thread compute diagnostics

Status: native own-thread capability is observed. No solver CPU attribution
or profiling acceptance yet.

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
