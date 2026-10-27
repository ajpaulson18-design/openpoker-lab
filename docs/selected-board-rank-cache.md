# Bounded board-rank reuse in the selected-game operator

This follow-up to the [non-materialized four-street milestone](selected-operator-four-street.md)
targets a measured cost. At T1000 the one-board operator made 991,485 ranking
calls on six boards and four private hands. A T100 cProfile recorded 100,485
rank calls, about 10.9 seconds cumulative ranking inside a 31.9-second
instrumented call. Profiling is not a benchmark or an accuracy certificate.

## Exact computational boundary

`solve_four_street_operator(request, rank_cache_boards=64)` explicitly selects
a solve-local LRU of immutable per-player rank vectors. Default capacity one
preserves the existing one-board path and payload. Capacities two through 64
use selected runout indices as keys. No suit/board-equivalence claim, pair/world
storage, abstraction, changed chance law, or changed trainer is introduced.
Only the result of independently ranking each private hand on a complete board
is reused. Blocked hands retain a sentinel; lookup occurs only after physical
pair/board compatibility has passed. Pair/mass reduction, payoff arithmetic,
sequence reaches, information-set identity and averaging order remain intact.

The provider reserves `(capacity+1)*(H0+H1)` logical rank/reference slots,
limited to 8,192 before rank work. This includes conservative construction
references during list-to-tuple conversion. The oldest vector is evicted before
building a replacement. A failed build never publishes a partial vector. The
cache belongs to one operator; solver cleanup releases it after diagnostics on
success or failure. No shared/global patch or fallback occurs.

The original full-request scan/rank ceilings stay fixed. An additional model
charges at most `(2*T+3)*terminal_count*H0*H1*selected_count` lookups, four
bookkeeping entries per lookup and at most `H0+H1` vector-build scans per miss.
The combined additional bookkeeping envelope is limited to one billion logical
entries. It is conservative and independent of observed hits. Metadata records
keys, per-player vector references, retained slots and construction capacity.
These are logical limits, not allocator-byte, CPU or process-RSS bounds.

## Acceptance and measurement

Tests compare capacities one, two and 64 through forced eviction/revisits,
weighted/blocker/tie payoffs and early all-ins. They require identical complete
policies/metrics and independent numeric legal best-response replay. Exact
rational replay covers the short-stack control. Failure injection checks partial
build rejection, cleanup after diagnostic failure, cross-solve isolation and
pre-ranking capacity/work rejection. Existing one-board tests remain in scope.

Terra drafted independent physical/policy tests. Both worker agents subsequently
hit usage limits; Sol completed implementation, corrected retained/construction
slot accounting, preserved the original one-board branch, and ran acceptance.
This substitution is recorded rather than claiming a final independent agent
review of changes made after the workers stopped.

`python -B -m scripts.benchmark_selected_rank_cache --output <fresh-external-dir>`
freezes source and protocol before child calls. T100 uses three alternating
untraced calls and one separate traced call per mode. T1000 uses one call per
mode. Both modes solve the same original 22-world finite game. All policies are
saved before numeric/exact replay; T100 accuracy misses are retained. The
manifest/source gate and non-overwriting saved-only verifier are reused from
the previous milestone. Timing includes all preparation, training, diagnostics
and payload construction; process lifetime RSS and Python allocation remain
separate. No general speedup or full-deck capability follows from these cases.

## Retained source-frozen result

Source revision: `3ba64b386fad3ed5852182915220625232dee1bc`. The
[receipt and raw compressed study](../benchmarks/results/selected-board-rank-cache-v1/receipt.json)
retain all policies, manifests, exact certificates, traces, process peaks and
intermediate failures. Archive members were compared with original bytes.

| Measurement | Capacity one | Capacity 64 |
| --- | ---: | ---: |
| T100 untraced median, three calls | 21.812964 s | 13.061669 s |
| T100 traced Python peak allocation, separate call | 2,772,623 bytes | 2,793,119 bytes |
| T100 traced process lifetime peak working set | 31,703,040 bytes | 31,379,456 bytes |
| T100 independent exact accuracy target | miss | miss |
| T1000 single complete call | 118.992255 s | 80.770475 s |
| T1000 ranking calls | 991,485 | 23 |
| T1000 observed post-constructor pair/board checks | 7,547,036 | 7,547,036 |
| T1000 independent exact target <= 1/1000 BB | pass | pass |

Both experiments produced identical complete strategy rows and independent
exact metric maps. T1000 numeric NashConv is 0.0003997388151442405 BB. The
one-board default also reproduces the predecessor's frozen T1000 strategy and
operator statistics. A separate saved-only process authenticated the T1000
manifest, repeated independent numeric/exact replay with zero training/native
calls, and compared existing certificates without overwriting them.

The measured T100 median ratio is about 1.67 and T1000 single-call ratio about
1.47, relative to the non-materialized one-board operator. This is not a ratio
against the existing C++ or materialized backends. Only the stated fixture and
hardware/runtime observations are established. Allocation rose by 20,496 bytes
in the separate traced calls; mixed process peaks do not establish an RSS gain.
The T1000 process peaks were 26,804,224 bytes and 27,070,464 bytes respectively.

The capacity-64 cache had six misses and 2,864,284 hits without eviction at
T1000. It retained 24 rank slots and reserved a measured conservative peak of
28 retained-plus-construction reference slots. Requested capacity admission was
256 retained and 260 construction-inclusive slots, below 8,192. Forced-eviction
tests independently exercise the two-board path. Old requested scan/rank caps
remain unchanged; additional modeled bookkeeping was 271,126,080/1,000,000,000
entries. No admission was widened in response to observed performance.

Normal and optimized acceptance pass 56 tests (18.009 s and 17.338 s). Earlier
restricted runs passed the numerical controls but hit three temporary-folder
permission errors each; these logs are retained and all three file-evidence
tests pass with normal Windows file access. Documentation validates 205
Markdown files and 1,179 local links before this results update. Final-head
CI and publication are separate live checks.

T100 manifest:
`1c2ed31d9343f23dc85cbf9c56c5cb3533a47b965f98e1a761efff2b5b42af36`.
T1000 manifest:
`256abf6ffa17f54a5d39ca217321730b35bb8022fb05af2adc919bfbb60a2ad9`.
Extract the study archive outside a clean checkout at the measurement revision,
with captured source bytes/line endings, then use `--verify-saved` and
`--expected-manifest-sha256` on the named cohort directory. Evolved source is
intentionally rejected. The root protocol and summary are separate from the
per-cohort hash manifests and pinned by the outer study archive hash.

The next structural limits remain the unchanged pair/board scans and explicit
public-tree/information-action storage. This controlled reuse improves measured
cost without resolving those limits or completing the foundation phase.
