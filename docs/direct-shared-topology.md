# Direct shared construction for the selected four-street game

`public_topology="direct", strategy_storage="packed"` selects direct public DAG
construction and the existing shared-cursor packed Python CFR+ path. Literal and
compiler-bridge modes remain available. The selected probability operator is
unchanged; no native fallback or new probability law is inferred. Native plus
direct rejects before preparation.

## Representation and rule boundaries

The builder uses the bounded original preflop skeleton and directly constructs
immutable postflop vertices. It does not construct a literal postflop tree, call
the literal template merger/clone, or run the topology compiler. Memoized betting
states contain the full relevant local state: player, contribution bit patterns,
previous full raise, raise count, reopening flag, check count, stage, public-prefix
and support context, exact stage configs and the preflop translation offset.
Config/support context identities are shared rather than copied into every state.

History is absent from physical vertices and reconstructed by the existing
bounded cursor. Distinct public histories retain distinct information rows, and
the same own hand/history retains one row across hidden future worlds. Global
support determines chance branches independently of strategy reach. Chance order,
global seats, action tokens, both terminal contributions and fold winner match
the original builders. Complete policy output is still materialized.

Monetary operations preserve the original local ledger and translation order.
Starting a fresh postflop street cleans carried contributions at entry. Settlement
and all-in reveals carry raw matched binary64 values through the all-in decision;
they do not round those values prematurely. Only global translation cleans the
preflop matched offset plus local target/contribution, with the original seat
swap. The previous full raise and reopening state are updated from the original
increment/epsilon comparison. Reusing a real-arithmetic-equivalent global ledger
would not establish parity with these local rounding boundaries.

## Admission obligations

Original candidate/world, scan, information-action, cache and packed-loop guards
remain. Compression must not bypass literal logical state/decision, per-template
or whole-game limits. Direct construction separately reserves unique state/edge,
memo, context, transition, branch and temporary key/summary work before growth.
Subtree summaries count each logical child occurrence, including repeated child
identifiers. Partial sums are checked while children are composed, so final
receipt assembly is not the first logical admission check.

The receipt separates materialized preflop source states from zero materialized
postflop source nodes and zero compiler snapshots. DAG vertices/edges, memoized
betting work, expanded logical visits, row/action counts, histories and temporary
scratch remain separate quantities. These modeled counts do not establish a hard
allocator, process RSS or CPU bound.

The original public topology is still allowed to be exponentially larger than the
shared DAG. The solver's full history keys, strategy rows and complete serialized
output remain explicit and may dominate memory. Private-pair/selected-board scans
are unchanged. Direct shared construction alone is not full-deck solving or a
solution to strategy-storage growth.

## Verification status

Initial complete path and solver controls match the literal reference on the
22-world fixture and weighted, shared-future, inactive-index, fractional-blind,
refund, tie, all-in and re-raise cases. Tests prohibit entry into the old literal
postflop builders, compiler, node collector and expanded training-view copier.
Independent numeric replay and a bounded early-all-in exact certificate agree.

Review identified two pre-acceptance issues: an early cleanup operation on carried
amounts and late logical admission after construction. The cleanup order differed
from source; no reachable output counterexample was established. Corrections and
the revised pre-growth ledger have now received independent review. Terra's new
controls prove cached templates are charged per logical occurrence and a small
scratch cap stops parser input consumption before allocation grows. The receipt
has an explicit version and snapshots every direct logical limit; these are
entry/work limits, not allocator-byte guarantees. The original logical caps
still apply even when the physical DAG is small.

The 22-world rank-free receipt has 10 materialized preflop states (including
three continuation records), zero materialized postflop nodes and zero compiler
snapshots, 200 memoized betting states and 234 recurrence transitions. Its DAG
has 99 vertices/173 edges, with 1,462 logical visits/628 decisions and 1,200
information rows/2,402 action slots. Logical reservation totals equal those
expanded counts. These are structural entry counts and establish no memory gain.

Source-frozen complete-call cost/memory, saved-policy exact replay and final CI
are separate gates. The compiler bridge's measured memory/runtime misses remain
preserved in its [original evidence](shared-public-topology.md).
