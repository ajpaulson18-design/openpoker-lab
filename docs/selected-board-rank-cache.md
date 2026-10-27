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

Executed results and remaining gates will be recorded after source-frozen runs.
