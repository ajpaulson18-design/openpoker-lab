# A suit-equivariant numerical reference for selected-game training

Status: opt-in, unquotiented four-street implementation. It is a prerequisite
for exact strategy-storage sharing; it does not merge information rows or reduce
the four packed numeric buffers. Frozen complete-call measurement, saved-only
independent replay and final CI are separate acceptance gates.

`solve_four_street_exact_selected(request, training_reduction="suit-equivariant")`
selects `suit-equivariant-sorted-chance-binary64-v1`. The default continues using
the previous packed trainer, payload and arithmetic. Either Fraction or dyadic
exact query arithmetic can feed this new reference. The
[exact-product chance law](exact-selected-kernel-contract.md), strict completed
query conversions, legal game, independent diagnostics and verifier caps remain
unchanged. This is one complete four-street training path, using the direct DAG
and non-materialized exact probability/payoff kernels.

## Why a distinct arithmetic contract is needed

A global suit permutation preserves an appropriate weighted mathematical game,
but can permute the order of chance children. Binary64 addition depends on that
order. Small differences can reach zero-regret boundaries and produce large
probability differences in rarely reached rows. Cross-runtime frozen policy bits
are also not a valid portable acceptance condition; the
[compact-output evidence](compact-exact-policy-result.md) preserves an actual
Python 3.11/3.12 reproduction. Neither small own reach nor matching diagnostics
alone establishes that an information row is irrelevant to opponent deviations.

At every chance occurrence, the new trainer gathers all child target-value
vectors, including zeros. It validates every component as finite binary64,
canonicalizes either zero encoding to positive zero, sorts each hand's values
numerically, and adds them explicitly left to right from positive zero. Every
action dot product, opponent action sum, reach product, regret-matching sum,
average product and output normalization also uses a specified ordered loop.
Local nonzero subnormal intermediate values are preserved; this does not relax
the adapter's rejection of nonzero completed exact queries that round to zero,
subnormal or nonfinite binary64. Nonfinite intermediates reject explicitly.

The schedule remains zero-delay, alternating CFR+: rematch, traverse one
responder under a frozen profile, commit and clip its regrets, rematch, traverse
the other responder, commit and clip, rematch, then average with the completed
iteration number. Own reach and exact global joint marginals weight averaging;
opponent reach enters terminal counterfactual values. Full own-hand and visible
betting/reveal history remain the information identity.

For a verified suit automorphism, exact completed callback components map to
equal rational numbers and therefore the same rounded binary64 values. From
uniform initialization, identical fixed action operations and sorted chance
multisets give identical mapped increments, regrets, current strategies and
average sums by induction. This reasoning requires the entire role-weighted
selected game and public action/money structure to be preserved. Equal DAG
vertices or row counts alone do not suffice. The implemented reference does not
assume a group, merge rows or infer an automorphism during training; separate
whole-game tests exercise a permutation exchanging actual private holdings.

## Admission and lifetime

Before legal-support information dictionaries, private-pair output or training
allocation, a pure additional census reserves sorted chance work, scalar
validation and simultaneous recursive vector scratch. Each of its three scans
charges the full copied history-token count as well as node/branch bookkeeping.
The whole solver adds this work to its existing 500-million envelope and adds
scratch entries to each existing retained-storage phase under the unchanged
25-million-entry ceiling. It does not reopen any request rejected previously.
The post-row layout receipt must exactly equal the earlier additional receipt;
the trainer repeats the layout validation before allocating its buffers.

These are modeled operations and logical entries, not complete CPU or allocator
bounds. Python object headers, allocator behavior and process memory require
separate measurements. Sorting can cost more time and temporary memory. A
successful symmetry control is not evidence of an overall performance gain.

Setup and all buffer allocation sit inside a cleanup guard. On normal return,
traversal failure or a later allocation failure, recursive helper cells and
numeric-buffer references are cleared. Tests disable cyclic garbage collection,
track the actual multiplied arrays, and retain error tracebacks. The initially
reproduced late-allocation retention is preserved in external review evidence.

## Next storage implementation: proposal, not shipped

The next backend should retain one record per orbit Q and generate mappings
procedurally from full row identities, without an expanded R-to-Q table or
pre-training R information/menu dictionaries. Its group must preserve both exact
role-specific priors, canonical flop plus ordered turn/river outcomes, complete
public action menus, global players, and terminal monetary values.

Each responder and average phase must stage one increment per Q row, compare
every distinct member's canonical binary64 action bits, and check complete
membership before committing once. Summing orbit deltas and dividing by orbit
size changes floating-point arithmetic and is not the proposed contract.
Stabilizers require deduplication of transformed row identities. Duplicate,
missing or inconsistent members must abort without returning partial state.

Admission must cover procedural transforms, group/graph closure, retained Q
history keys, phase masks, four Q buffers, nested chance scratch, and eventual
expanded output. Existing R/S/dense/game/work caps remain admission authority.
The independent small-game certificates still consume expanded policies; those
output and diagnostic phases can remain R-sized even after training storage is
reduced. Identity-only groups give no compression. No full-deck, commercial
accuracy or general storage/runtime improvement follows from this prerequisite.

## Executed controls

`tests.test_equivariant_packed_cfr` covers chance permutation/cancellation,
nonfinite rejection, signed zero, preserved subnormal intermediates, scan/scratch
admission, weighted scaling, mapped policy bits and buffer lifetime.
`tests.test_equivariant_selected_solver` covers complete exchanged-private-hand
policy bits, unchanged exact-certificate identity/threshold, Fraction/dyadic
agreement, early excessive-work rejection, receipt drift and unsupported modes.
Independent external controls separately exercise foreign/mutated views,
zero-own-reach rows, real multiplied-buffer lifetime and late allocation failure.
Their actual execution and frozen results belong in the execution record;
existence of a test or this argument is not a measured scaling claim.
