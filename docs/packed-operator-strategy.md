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
no numeric dictionary or row list is retained per information set. Missing
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
