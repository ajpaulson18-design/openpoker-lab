# Optional terminal cache for matrix-free turn solving

`solve_matrix_free_turn(..., terminal_cache="ranked-lru")` reuses exact terminal
vectors within one solve. The default remains `terminal_cache="none"`. Every
legacy result field, including strategy rows, metrics and resource accounting,
must match the default exactly; the opt-in result adds only `terminal_cache`
metadata. This mode applies to the existing configured heads-up turn/river game.

## Supported calls and ownership

The initial mode supports fixed CFR+ calls with 10 through 10,000 requested
sweeps, at most two original hands per player, at most 48 reachable river
branches, ordinary conditioning, and both the original solver admission and
the additional cache admission described below. Target-based stopping and
exceptional conditioning reject before training. An otherwise valid default
call can exceed the optional cache budget. Selected runouts still define the
same conditioned joint game; omitting runouts still retains the remaining deck.

The original outer `TurnRangePayoffs` object remains in use. A private context
temporarily replaces its own branch evaluators with composition proxies, then
restores the original objects. No shared class or module is patched. Separate
solves own separate caches and can overlap. Success, training errors, diagnostic
errors and partial installation restore branch references and clear entries.
Closed contexts and runtimes reject reuse.

## Reuse invariants

Each lookup first performs the original player, terminal and reach validation.
The key contains the private branch identity, terminal kind, matched wager,
fold winner, player and complete opponent reach. Numeric keys preserve exact
binary64 bits, including signed zero. There is no rounding or reuse across
rivers. Successful calls are cached only when they add zero fallback-pair work;
fallback calls and errors execute the original evaluator each time. Proxy limit
writes reach the original evaluator, preserving cumulative fallback limits.
Stored vectors are immutable tuples and hits return fresh lists.

Original root-fold paths bypass the branch cache and retain their original
arithmetic, including exact stabilization at very small positive reach. The
cache changes neither the public information available to best responses nor
the order of chance integration and maximization.

## Resource admission

All original tree, hand, action, state, fallback and requested-iteration guards
remain enforced. Before allocating information rows or the cache, the adapter
counts all terminal leaves, including uncached root folds, and reserves:

```text
calls = all_terminal_leaves * (2 * requested_iterations + 4)
setup_slots = 16 * reachable_branches + 64
reserved_slots = 20 * calls + setup_slots <= 30,000,000
```

The two passes per sweep and four reserved final diagnostic passes conservatively
cover training and diagnostics. The setup model covers bounded restoration,
proxy, runtime and control references. These are declared logical accounting
units, not Python instructions, CPU time, allocator work or memory usage.
Admissions are revalidated before allocation. Actual calls charge twenty units
before lookup and cannot exceed the original full-request reservation.

The global LRU for one solve retains at most 16,384 entries, evicting before
insertion. At most two reach floats, two output floats and one matched-wager
float per entry give a numeric payload upper bound of 655,360 logical bytes.
Fixed key fields, Python representations, references, LRU overhead, temporaries
and allocator overhead are excluded. This is not an RSS measurement or bound.

| Frozen fixture | All terminal leaves | Branches | Sweeps | Reserved cache slots |
| --- | ---: | ---: | ---: | ---: |
| Selected two rivers | 107 | 2 | 1,000 | 4,288,656 |
| Full remaining deck | 722 | 48 | 1,000 | 28,938,592 |
| Selected two rivers | 107 | 2 | 3,000 | 12,848,656 |

Under this additional cap the full-deck fixture fits 1,036 sweeps and rejects
1,037; selected rivers fit 7,007 and reject 7,008. These are fixture-specific
admission boundaries, not new global iteration limits.

## Validation and measurement

Independent review checks known terminal vectors, actual cumulative fallback
failure, tiny-reach exact root-fold behavior, overlapping public solver calls,
and cleanup after final diagnostics fail. Eighteen captured pre-change complete
outputs cover all three algorithms, fixed and target modes, and exceptional
conditioning. Both omitted and explicit default cache options preserve them.

The benchmark compares the current default with the opt-in mode after short
warmups. It retains both 1,000-sweep candidates, the selected 3,000-sweep
candidate, and both 300-sweep modes for each fixture: seven complete policies.
Each saved policy is byte-hashed, reloaded and independently replayed across
all eight metrics. The 1k and selected 3k candidates must match their pinned
archived complete legacy payloads exactly. The selected 3k policy additionally
recomputes its [exact normalized certificate](turn-rational-certificate.md).

Both 1,000-sweep candidates passed exact archived legacy-payload parity and
independent replay. Their NashConv values remain approximately 0.00423446838
for selected rivers and 0.00145336964 for the full remaining deck; both miss
the unchanged 0.001 reporting threshold. The selected 3,000-sweep candidate
also passed exact archived parity and recomputation of its normalized
Fraction certificate: exact NashConv is approximately 0.000470810046557,
meeting exact `1/1000`. No solver stopping target was configured.

Three paired complete 300-sweep calls run in baseline/candidate,
candidate/baseline, baseline/candidate order. Construction, training, final
diagnostics, cleanup and serialization are timed; hashing and independent
replay occur outside each timer. The predeclared research gate requires a
median baseline/candidate ratio of at least 1.10 for both fixtures. Every raw
sample and miss remains evidence. Shared-host timing gives no general speed
guarantee. Faster evaluation does not itself improve a fixed-sweep strategy.

Reproduce the short checks with
`python -m scripts.benchmark_turn_terminal_cache --phase preflight`, or the
complete pinned comparison with `--phase measure`. Sources and inputs must
remain unchanged throughout a run. The earlier
[research class-patching experiment](turn-terminal-memoization.md) has its own
historical source pins and is separate from this per-solve integration.

## Executed evidence

The run froze current baseline `c57591b43707c8f26c5997f5fba45479958f615c` and
78 source/input fingerprints before and after measurement. Sol's separate
artifact audit reloaded all seven policies, verified byte hashes and LF
encoding, replayed all eight metrics, checked archived complete-payload parity,
reconstructed call/slot and timing arithmetic, checked exact certificate
identities, and rehashed every frozen input. Maximum scalar disagreement was
`1.4210854715202004e-14` chips. Eighteen captured old complete outputs also
matched both omitted and explicit default options across 36 solver calls.

| Fixture | Pair/order | Default seconds | Cached seconds |
| --- | --- | ---: | ---: |
| Selected rivers | 1, default/cache | 5.614765 | 4.541497 |
| Selected rivers | 2, cache/default | 5.729749 | 4.393205 |
| Selected rivers | 3, default/cache | 5.383152 | 4.507972 |
| Full remaining deck | 1, default/cache | 37.307357 | 26.907661 |
| Full remaining deck | 2, cache/default | 36.027667 | 27.691073 |
| Full remaining deck | 3, default/cache | 36.961268 | 26.429225 |

Selected medians were 5.614765 / 4.507972 seconds, a ratio of 1.245519.
Full-deck medians were 36.961268 / 26.907661 seconds, a ratio of 1.373634.
Both meet the predeclared 1.10 gate. The gate divides the two medians; it is
distinct from taking the median of the three individual pair ratios.

| Fixture/profile | Independently replayed NashConv | Meets 0.001 |
| --- | ---: | --- |
| Selected rivers, both 300-sweep modes | 0.046940230887631884 | No |
| Full deck, both 300-sweep modes | 0.01611099682434869 | No |
| Selected rivers, cached 1k | 0.00423446838076913 | No |
| Full deck, cached 1k | 0.0014533696436025423 | No |
| Selected rivers, cached 3k | 0.00047081004656490677 | Yes |

The selected 300-sweep cache made 57,888 calls: 54,714 hits, 3,174 misses,
3,172 maximum entries and no evictions. Two successful fallback calls were
deliberately uncached; the original four fallback-pair checks remain identical.
Full deck made 434,160 calls: 415,343 hits, 18,817 misses, 16,384 maximum entries
and 2,433 evictions. Actual 1k calls were 192,288 selected and 1,442,160 full
deck; selected 3k used 576,288. All caches were empty after cleanup and all
actual work stayed below the separate full-request reservation.

The broader ranked/turn/adapter/independent-oracle/cache regression passed
92 tests in 121.844 seconds. The final focused cache/API/independent-review/
benchmark/legacy-maintenance suite passed 32 tests in 20.168 seconds and the
same 32 passed with `python -O` in 19.347 seconds. These are scoped runs;
full final-head CI remains a separate publication gate.

The [complete report](../benchmarks/results/turn-terminal-cache-v1.json) retains
all raw samples, counters, misses, metrics and frozen fingerprints. The
[saved complete policies](../benchmarks/results/turn-terminal-cache-policies-v1)
retain both 300-sweep modes and all three archived-parity candidates.
