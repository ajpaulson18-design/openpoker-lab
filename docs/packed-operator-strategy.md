# Contiguous strategy storage for the four-street operator

This implements the next storage step after the
[selected-runout operator](selected-operator-four-street.md) and
[bounded rank reuse](selected-board-rank-cache.md). The structural census
established that complete-world removal leaves public histories, per-hand
information sets and action slots explicit. This change targets numeric-row
object overhead; it does not compress away game histories or introduce an
abstraction.

## Chosen representation and reuse

`solve_four_street_operator(request, strategy_storage="packed")` explicitly
selects contiguous binary64 buffers for zero-delay alternating CFR+. The default
`"rows"` path and all legacy solver APIs remain. Other algorithms reject this
new mode before probability preparation rather than silently selecting a
different algorithm. Both rank-cache settings remain compatible.

Each original information-set key receives an action offset and count. A bounded
node/own-hand lookup stores offsets with `-1` for inactive own-hand indices.
Regrets, average sums, current strategy and one target's deltas occupy four
`array('d')` buffers. Original semantic keys and action order remain available
for complete output. A temporary key-to-offset map is released before training;
no numeric dictionary or row list is retained per information set during sweeps.
Complete compatibility policy rows are materialized after training. Missing
private-hand rows retain the same uniform traversal fallback and never become
new serialized information sets.

The public tree, chance/payoff operator, betting contracts, rank cache, result
schema and independent diagnostics are shared. The existing C++ trainer already
uses offsets/flat numeric storage, but requires materialized chance edges; its
wire format cannot directly consume the on-demand operator. This implementation
tests the flat strategy boundary with actual operator training, preserving the
Python row kernel as a separate reference. It is a storage implementation of
the same game, not four independently solved streets or a native migration.

The reference trainer allocates numeric row dictionaries internally in several
deep traversal/update functions. Replacing that internal storage globally would
change historical source closures before operator acceptance. The separate
opt-in packed kernel makes its algorithmic duplication explicit, retains the
original for regression, and requires exact complete-policy comparisons plus
independent replay. Consolidating/native reuse remains downstream of this gate.

## Mathematical and lifetime contracts

Preserve the initial regret match, player-zero regret pass/update/rematch,
player-one pass/update/rematch, then completed-sweep own-reach averaging with
weight T. Terminal vectors include joint chance and opponent reach; averaging
includes own reach and its prefix marginal. No additional chance multiplier is
applied at public reveals. Reduction order, binary64 clipping, multiplication,
policy fallback and average normalization match the row implementation.

No history or own hand is merged. Dense inactive indices are charged explicitly.
Layout validation checks complete semantic-key coverage and action menus,
rejecting cyclic/shared topology and orphaned or conflicting information sets.
The ordinary builders still define legal bets, chip quantization/refunds and
hidden information. No monetary, minimum-bet, reopening, rake or omitted-action
semantics are changed.

The enclosing original scan/rank/cache limits remain. Additional rank-free
layout admission caps one million action slots, two million decision/hand lookup
slots and 500 million requested layout-loop entries. The loop model separately
charges both players' vector dimensions, including asymmetric/unused hand
indices, resets, matching, updates and output. Array payload bytes exclude
headers, semantic keys, tree, index dictionaries, recursion scratch and complete
policy output. Buffers and recursive closures are released even on terminal
failure; rank-cache cleanup remains the enclosing solve's responsibility.

## Acceptance and fixed measurement

Controls require identical complete policy rows, numeric metrics, private-pair
probabilities and observed mass/rank work against row storage. Cases include the
existing 22-world four-street game, shared futures, weighted blockers, asymmetric
ranges, inactive index holes, short stacks, refunds, board ties and blind all-ins.
Separate numeric rules/physical rank and legal best responses replay complete
policies; an exact rational short-stack control compares independently certified
metrics. Rank-free cap tripwires, layout mismatch/cycle rejection and injected
terminal-failure cleanup are covered.

`python -B -m scripts.benchmark_packed_operator --output <fresh-external-dir>`
freezes source/protocol before three untraced T100 calls and one separate traced
call per storage mode, then one untraced T1000 call per mode. Both use rank-cache
capacity 64, the same game, requested sweeps and exact quality criterion. Each
cohort saves all raw policies before independent numeric/exact sample-zero
replay, pins every raw sample with an externally reportable manifest, preserves
all misses and never retries. A separate saved-only invocation reuses the
non-overwriting source/byte verifier. Timing includes preparation, training,
diagnostics and output; allocation instrumentation and process peaks remain
separate. No general speed/memory, full-deck or commercial readiness claim is
inferred from this bounded study.

Sol implemented this after worker usage limits. Existing independent oracles and
Terra's prior physical/cache controls remain in scope, but a final independent
agent engineering review is unavailable and is not claimed. Source-frozen
results and publication gates are recorded after execution.

## First frozen experiment and lifetime correction

The first fixed experiment at `3a0f9b114247e7fd92c0845b30268d4866f4049e`
produced identical complete policies, exact metrics and operator work in both
storage modes. T1000 passed the unchanged exact <=1/1000 BB target. Its complete
calls were about 75.21 s rows and 74.63 s packed, and the T100 untraced medians
were about 7.75 s and 7.65 s. These observations establish no meaningful speed
claim. T100 misses remain.

That experiment **missed the full-call memory objective**: traced peaks were
2,793,119 bytes rows and 3,021,397 bytes packed. The numeric buffers alone were
smaller, but their payload was not a valid proxy for whole-operation allocation.
The raw study and exact certificates are preserved before a distinct correction.

Separate T10 phase tracing identified two avoidable lifetime costs: layout
coverage validation retained fresh copies of all semantic-key tuples, and
complete JSON rows overlapped diagnostic policy, lookup dictionaries and the
original tree. The corrected layout consumes a set of original key references;
it still rejects duplicates, missing rows and cycles. After diagnostics, packed
serialization releases its obsolete dictionaries/root and consumes average and
metadata entries while creating the unchanged complete output. Default row
serialization remains unchanged in meaning and retains its dictionaries.

Diagnostic tracing then observed about 2.17 MB packed versus 2.77 MB rows at T10;
that is instrumented development evidence, not a frozen performance result.
Both original miss and phase evidence remain. A separately frozen full-call
study is required before accepting the correction; no cap or quality threshold
was changed to obtain the observed reduction.

## Corrected frozen result

The [receipt and both raw studies](../benchmarks/results/packed-operator-storage-v1/receipt.json)
retain the first miss and corrected source
`c6090c891f3bbede6107c2a549e283b208d3852c`. All compressed members were compared
byte-for-byte with the original files after compression. Both source-pinned
studies preserve identical complete policy rows, independent exact metric maps
and observed operator work across storage modes. T100 misses remain unchanged;
both T1000 policies meet the exact <=1/1000 BB target, with numeric NashConv
0.0003997388151442405 BB.

| Corrected experiment | Row storage | Packed storage |
| --- | ---: | ---: |
| T100 untraced median, three calls | 7.512110 s | 8.598265 s |
| T100 traced peak Python allocation, separate call | 2,793,147 bytes | 2,337,517 bytes |
| T100 traced process lifetime peak working set | 31,576,064 bytes | 30,375,936 bytes |
| T1000 untraced single call | 123.125387 s | 134.145210 s |
| T1000 process lifetime peak working set | 26,710,016 bytes | 26,476,544 bytes |
| T1000 independent exact quality target | pass | pass |

The measured allocation reduction is 455,630 bytes (about 16.3%) in the
separate T100 traced calls. The measured runtime cost is preserved; neither
the three-call medians nor the single T1000 observations establish a general
distribution or speed winner. Process peaks include interpreter/imports and do
not prove a general RSS reduction. No cross-study hardware-load comparison is
used to claim an improvement.

The 22-world layout has 1,200 information sets, 2,402 action slots and 1,256
dense decision/hand slots including inactive holes. Four numeric buffers hold
76,864 payload bytes; dense lookups hold 5,024 and row offset/count payloads
9,600 bytes. These payloads are not the total-memory measurements above.
The extra requested layout envelope is 237,550,088/500,000,000 entries at T1000;
all prior operator/cache caps remain unchanged. Actual ranking and pair/board
checks are identical across storage modes.

A separate process authenticated the corrected T1000 manifest and repeated
numeric/exact saved replay with zero training or native calls, comparing existing
audits without rewriting them. Corrected acceptance passes 65 tests normally
(15.058 s) and optimized (16.059 s), covering independent physical, numeric and
exact replay plus reference, cache, layout and contract controls. Documentation
links pass. Final-head CI and merge status remain separate live gates.

Corrected T100 manifest:
`33bc8087c50a6f1a484430db8065702ecabe8db39292807e5e80f2f40d4978bc`.
Corrected T1000 manifest:
`6c1606fc72910930e96a3ea86ad4295b0d790750fa187d8b3082f8b3ad10c513`.
Extract the chosen archive outside a clean checkout at that study's source
revision, preserving the source-byte/line-ending identities captured in
`source.json`, and invoke `--verify-saved` with the externally pinned manifest
digest on its cohort directory. Evolved source is intentionally rejected.

This step establishes a measured storage tradeoff in actual unified training.
It does not reduce the number of public histories or information/action entries.
The next structural work remains coherent native operator computation and
mathematically justified game/storage reduction or decomposition; the overall
foundation objective remains active.
