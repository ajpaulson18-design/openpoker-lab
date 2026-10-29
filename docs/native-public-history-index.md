# Exact public-history index: graph-only prerequisite

Status: graph-only implementation passes scoped development conformance and
independent retained-ledger review; committed-source evidence and final CI remain
publication gates. This module is not yet
selected by the native trainer, solver API or wire protocol. It changes no
learning trajectory or admission result. The accepted [native four-street
integration](native-exact-whole-game-result.md) remains the reference.

## Purpose and identity

The [index](../native/exact_public_history_index.hpp) assigns an exact ordinal to
each unfolded public path without storing a table of those paths. A shared DAG
vertex can occur after many different histories; those occurrences retain
different ordinals. This prepares a replacement for repeated history copying,
root routing, suit transformation and string-key comparisons during learning.
It does not reduce the number of strategic information sets.

For each canonical continuation, `C(v) = 1 + sum(C(child))`. Outgoing edges get
separate metadata sorted by complete history-token byte order. Their offsets
are one plus preceding sibling subtree counts. Advancing adds the appropriate
offset to the current occurrence ordinal. Consequently numeric order equals
lexicographic full token-tuple order, including a history before its extensions.
The original action/chance traversal order is retained separately.

Exact bottom-up signatures identify equivalent continuations, including different
raw objects and reordered equivalent chance branches. Raw edge positions map by
the complete token and child continuation, not by an assumed object bijection.
Each suit image carries its own continuation and parent ordinal and follows its
transformed token. A flop reveal is one token containing three canonical cards.
Unique sibling tokens and the existing fixed initial history are prerequisites.

The typed visible-prefix identifier includes only cards revealed so far. Fixed
subtree sizes are public game constants; an ordinal never selects an opponent
holding or unrevealed runout. The same visible path always has the same identity
for every compatible hidden world. Future Q keys must still include actor and
original own-hand index, with distinct transformed keys sorted and deduplicated
before deriving orbit member masks.

## Ownership and resource contract

`HistoryIndex` references an existing immutable `Plan`; **the Plan must outlive
the index**. This is an internal C++ lifetime precondition, not a checked promise
after destroying the Plan. Cursor construction is private, cursors are bound to
their index and generation, and cross-index use rejects. Numeric ordinals alone
are not persistent/public handles or permission to bypass validated history APIs.

Index metadata is bounded by the graph, edges and suit group, without an expanded
history/R-row/R-to-Q table. Constructor admission adds the existing Plan receipt
to new retained and simultaneous scratch reservations. It charges exact signature
keys, token payloads, comparison/sorting and transformed-edge matching before
dependent growth. Query work uses remaining combined capacity, and inverse
queries include the returned history's string/vector payload. Counters describe
logical work, populated fields and characters, not vector capacity, allocator
bytes, CPU time or process memory. The receipt exposes the named per-array upper
and populated ledgers, including vertex-to-class and raw-vertex records, both
token copies and a fixed 512-entry bookkeeping reserve. It checks their sum
against the retained upper before returning the index.

The prerequisite exposes counts and reservations, but does not establish that a
later integrated trainer needs less total memory. Existing Q histories, policy
arrays, Python preparation/output and independent diagnostics remain unchanged.

## Conformance and build

Build the test-only target outside the checkout:

```text
python -m scripts.build_native_exact_four_street --target history-index --output-dir <external-directory>
python -m unittest tests.test_native_public_history_index -v
```

The Python harness builds locally when a compiler is available, or authenticates
an explicitly provided `OPENPOKER_NATIVE_HISTORY_INDEX_EXE`. It verifies complete
current source/dependency and executable identities before/after running the
[C++ controls](../tests/native/exact_public_history_index_controls.cpp).
The [dedicated workflow](../.github/workflows/native-public-history-index.yml)
requires actual Windows/Linux builds and Linux ASan/UBSan controls.

Acceptance requires literal full-history ordering/inverse checks, reconvergence,
duplicate/reordered signatures, nontrivial reveal-path suit composition, fixed
initial histories, malformed handles and reduced-capacity rejection. Independent
adversarial review and final source/build pins remain separate gates. Passing
this graph-only test does not provide a new poker quality certificate.

The final development header/control pins are respectively
`6ec930089c4339e64b772d984e2830c4a8711df06eccff7ba692e5d7d30646bc`
and `812f9e6d644ec49194ff72adf1c344c16ebabb13f4dd28d9ec1c36ebfe14f12f`.
Root's authenticated strict MSVC target passes normally and with Python `-O`;
the C++ checks use explicit exceptions rather than elidable assertions. The
controls include noncommuting S3 reveal composition and a 49-vertex/48-edge chain.
Terra's separate 41-way reconvergent/UTF-8 control independently recomputes the
wide/tall per-array ledger and verifies one-entry-below combined-limit rejection.
The Plan lifetime precondition remains explicit.

Draft review corrected child-signature construction order, missing query costs,
generation wraparound and a retained ledger that omitted three per-vertex fields.
Earlier passing ordering tests did not accept that older storage ledger. The
first local C2065 control compile error was transcribed after the fact; its raw
streams and pre-fix source hash were not captured. Preserve that gap separately
from the retained root builds and independent harness failures.

## Why broader admission remains open

A rank-free diagnostic of the unchanged original T1000 request finds the first
production rejection at 2,614,761,482 kernel modeled units versus the 500-million
cap. Of that forecast, terminals require 2,276,489,040 and marginals 335,446,384.
Removing the entire marginal allowance would still exceed the cap. The same
saved graph substituted into existing native formulas has a counterfactual
12,570,661,340 whole-native upper, including 2,981,361,856 trainer history-key
units. Those are formula evaluations, not admitted execution or measured CPU.

The native trainer already computes its marginal map once, whereas inherited
Python admission conservatively reserves repeated marginal queries. A future
versioned model must describe work that actually runs; simply deleting an old
guard or increasing its ceiling is not an accepted improvement.

Before integrating the index into Q lookup or training, obtain scoped phase
profiles that distinguish history processing, exact callbacks, preparation and
diagnostics. Forecast shares are not timing shares. Then compare complete keys,
orbit masks and phase/policy bits against the reference and independently replay
saved policies/visible-information best responses. The overall foundation goal
remains active; this prerequisite alone does not admit T1000 or full-deck solving.
