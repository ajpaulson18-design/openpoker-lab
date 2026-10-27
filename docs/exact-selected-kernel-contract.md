# Exact-product selected chance/payoff kernel: implementation contract

Status: explicit research integration with [frozen complete-call and independent
saved-policy evidence](exact-selected-kernel-result.md). Final PR-head CI and
publication remain separate gates. The existing legacy-binary64 selected operator, native DAG, old limits
and all frozen evidence remain unchanged. The new contract is explicit research
work for removing private-pair scans; actual four-street training integration and
independent policy/BR acceptance are required before calling it a solver path.

## Mathematical game and boundaries

Contract ID: `exact-product-selected-v1`. Snapshot each positive parsed binary64
range weight as its exact rational image wi. For each compatible SB hand i, BB
hand j and ordered selected complete board b, define unnormalized mass wi*wj.
Let Z be the sum over compatible pair/board occurrences. One joint global Z
normalizes all queries, including early folds/all-ins and partially revealed
prefixes. The common physical selected-board divisor cancels. Never normalize
locally per board, private pair or public prefix. Zero strategy reach does not
remove physical support. Prefixes reveal exactly flop, turn and river tokens.

This differs from the old rounded raw-product/divisor/per-occurrence-normalized
binary64 law. A separately tested nonzero determinant witnesses why factoring
that old matrix is not exact. Preserve that divergence explicitly. New exact
queries do not claim bitwise legacy policies or alter defaults. The finite
betting/money model remains separately identified; exact prior arithmetic does
not make its legal-action coverage unrestricted NLHE or its money exact-decimal.

For every selected board, exclude board-blocked hands first. Build total/card
buckets and exact-holding lookup for the opponent. For own hand {a,b}, compatible
opponent weight is T-C[a]-C[b]+same_hand. Same-hand add-back is necessary because
that holding occurs in both card buckets. Apply the same operation to unit hand
counts to obtain world/support counts without private-pair enumeration.

For showdown, sort per-hand physical ranks, then sweep lower/equal/higher buckets
containing exact weight*opponent-reach and per-card sums. Own signed expectation
is compatible lower minus compatible higher; ties contribute zero. Query all
matching selected boards in configured order and sum exactly. Marginals use
prior weights alone; terminal counterfactual vectors include opponent reach once;
averaging later uses own sequence reach and absolute prior marginal separately.
No subtraction-error heuristic or quadratic fallback is necessary in this exact
reference: integer/rational operations must obey explicit bit/work admission.

## Owned initial implementation API

New `pokerlab/exact_selected_kernel.py`, class `ExactSelectedRunoutKernel`:

- Constructor `(sb_range, bb_range, runouts, *, rank_cache_boards=1, limits=None)`.
  Reuse range/card and selected-runout parsing semantics, but do not instantiate
  SelectedRunoutOperator or enumerate its worlds. Preserve input hand order.
- Immutable hands/weights/selected boards, exact `normalizer`, rank-free support
  counts, and versioned structural/work/bit receipts. No private-pair/world table.
- `joint_marginals_exact(prefix=()) -> (tuple[Fraction], tuple[Fraction])`, every
  input hand retained, board/pair-blocked holes zero, globally normalized.
- `prefix_mass_exact(prefix=()) -> Fraction` and
  `pair_probability_exact(i, j, prefix=()) -> Fraction`; explicit pair queries
  may scan boards, but no pair scan may be hidden in batched marginal/payoff APIs.
- `terminal_values_exact(prefix, *, kind, payoff, player, opponent_reach)` returns
  globally normalized own-hand counterfactual Fractions. `payoff` is a signed
  SB-oriented fold scale or nonnegative showdown scale; global player 1 negates.
  Reach vector length is the opponent dimension; exact dyadic snapshots for
  float entries, finite nonnegative entries<=1, Fraction values explicitly bounded.
- `legal_hands(prefix=())` and `reachable_selected()` use rank-free global support.
  A diagnostic `statistics()`/`receipt()` distinguishes logical operations,
  rank/cache work, storage entries and unsupported requests from CPU/RSS bounds.

Canonical prefixes are empty or `(six-character flop,)`, then turn, then river.
Validate prefix tokens/collisions/support shape before cache access. Unknown
physical prefixes may have exact zero mass; malformed prefixes reject. Full
future cards never select an information key. Cache ranks only after successful
validation; cache size and transient rank vectors must be separately reserved.

## Admission and retained work

Use explicit initial research limits, immutable validated dataclass: at most
1,326 hands/seat,64 selected boards,65,536 integer bits and500million modeled
work units. Do not raise any existing solver/native limit. Reserve every
hand/board/card/rank/cache/summary entry before its allocation. Charge requested
rank sorting/sweep work, prior setup and query operation/bit bounds before loops;
include all counts, zero-mass prefixes and errors. A separate retained+scratch
entry cap must prevent a small logical-work result from permitting unbounded
Fraction storage. Document that entry/bit accounting is not hard allocator/RSS.
No cardinality-based pair loop or fallback is admitted in the batched kernel.
Small physical-pair enumeration belongs only to the independent test oracle.

## Acceptance and integration dependency

Independent tests enumerate physical deals with their own Fraction products,
blocker masks and physical best-five ranks. Compare all marginal, prefix, fold,
showdown and pair queries exactly for shared futures, identical holdings, ties,
asymmetric/index-hole support, zero reaches, unknown prefixes and extreme tiny
positive weights. Prove old/new chance-law divergence and no legacy cap change.
Patch legacy world/pair producers forbidden, instrument candidate scans, and
exercise boundary admission before rank/sort/cache/bucket growth on success/error.

After the exact kernel passes independent scrutiny, integrate an explicitly
selected conversion contract through the existing directly built four-street
root, sequence-reach CFR+ and policy serialization. Conversion boundaries and
new-game independent physical policy/BR/exact replay must be specified before
training acceptance. Native migration and full-call measurements follow proof;
this kernel alone is not full-deck probability, training or scalable verification.

## Planned shared-trainer conversion boundary

Root's new `exact_selected_float_adapter.py` is an unintegrated callback adapter,
not a solver selector. It binds one immutable shared view and retains an admitted
O(unique terminals) identity-to-original-scale map with strong references. Only
terminal membership uses object identity; policy identity remains full visible
history and own hand. Each terminal payoff is the original vertex's final
binary64 matched contribution, snapshotted exactly, with global fold sign. It
never reconstructs money by adding an anchor to a rounded shifted amount and
never applies an extra root correction. Foreign/stale terminals or replaced
views/inputs reject before callbacks.

Each completed exact marginal/terminal component rounds once to binary64. Exact
zero from blockers, zero reach or cancellation is valid; a nonzero signed value
that becomes zero, subnormal or nonfinite rejects. This defines an approximate
binary64 CFR trajectory over the exact prior game; it does not prove exact
training updates or prevent all downstream float underflow. Final policy rows
must be independently validated/normalized as exact images of serialized floats,
then replayed with legal exact-product physical best responses.

Current source `scripts/four_street_validation.py::_physical_support` already
independently enumerates exact products of parsed binary64 range weights with a
single global Fraction normalizer. The unchanged v3 certificate consumes those
priors and snapshots original matched contributions as binary64 images. It can
therefore serve as the bounded independent new-law oracle; do not change its
limits or silently reinterpret the legacy training arithmetic. Full shared-root
CFR+ integration, whole-request admission, final policy/BR quality and measured
cost remain open gates after the kernel/adapter controls.

## Executed reference controls before solver integration

The revised exact kernel and strict float adapter passed 23 focused controls,
including 16 independent Terra controls. Review found and corrected player 1 sign,
rank-threshold, duplicate/mutable input, prefix/range/runout bound and scratch
accounting defects before acceptance. The reviewed kernel SHA-256 is
`57775bd1feb6fe032eb1c2f531fcf8ce0b3bb257775303e8db7b40d871245678`;
no legacy solver/source/limit changed. This is scoped reference-component review,
not exhaustive resource-bound proof or trained-policy acceptance.

A separate rank-free combinatorial control admits all 1,326 hands per seat for
one selected five-card board. It represents 1,070,190 compatible pair/board
occurrences using zero stored worlds and no legacy world producer. Exactly 1,081
hands per seat remain active with exact marginal 1/1,081, and both sides sum to 1.
This is one selected-board probability census, not full-deck solving or training.
The separate regression tests its combinatorial counts with ranking forbidden.

The range string parser is bounded to 16,384 characters with conservative hand-
expansion work admitted before parsing; direct mappings remain separately bounded.
Public input snapshots are immutable; sized mapping/runout inputs cannot yield
beyond admitted declared cardinality plus one rejection sentinel. Fraction reach
LCM/product/sum bounds and all matching-board accumulation are checked before
rank or bucket work. Cumulative operation and scratch entry receipts remain
logical models, not actual allocator/CPU bounds. Whole-request solver admission,
training, policy serialization, certificate quality and measured cost remain open.

## Four-street integration and requested-work admission

`solve_four_street_exact_selected(request, rank_cache_boards=1, kernel_limits=None)`
in `pokerlab/exact_selected_solver.py` explicitly selects this new law. It requires
CFR+, public-batched training/diagnostics, public-vector resources and 10..10000
requested iterations. It constructs one direct four-street DAG and trains one
root with the existing packed CFR+ implementation. Legacy API defaults/native
protocols and their probability guards remain unchanged.

Before information/pair-output/training allocation, a streamed logical occurrence
census charges every public occurrence with its selected-prefix board multiplicity.
Two complete terminal traversals per sweep plus six diagnostic terminal passes
are reserved. Average marginal queries are bounded per decision/sweep and missing-
policy diagnostic fallbacks by three times action/acting-hand entries. A one-
prefix marginal cache does not excuse worst-case call accounting. Original direct,
packed action/dense/history/loop limits remain. New exact-kernel, adapter,
phase-overlap storage and output limits are separate, versioned logical models.

For B selected boards, H total private hands and Bp matching a prefix, the kernel
lookup charge is 64+8B; legal/marginal charges add Bp*(24H+104)/(20H+260).
Terminal charges reserve 16+lookup+Bp*(200H+520+H*(ceil(log2(max(2,H)))+1))+4*Hopp.
This covers rank/card bucket sweeps and sorting in logical units; one bounded
seven-card rank evaluation is one unit, not an instruction/CPU-time estimate.
The exact kernel uses a merged rank sweep and retains all/lower/equal card sums,
not a card-vector snapshot for every rank. The bit forecast reserves all possible
binary64 reach images, original payoff images, dyadic denominator LCMs, sums over
hands/boards and global normalization before training. The receipt records actual
forecast bit maxima and the unchanged 65,536-bit ceiling.

The existing independent policy validator still requires explicit positive
private-pair probability rows. This integration therefore has a separately billed
O(H0*H1*B) setup/output stage, capped before training (30 million candidate-board
scans and 2 million modeled output entries). Every positive pair mass must convert
to normal binary64 before training starts. This is not hidden in the batched
payoff/marginal kernel, but remains an end-to-end scalability limitation.

Storage accounting includes all selected prefixes (including terminal-only
prefixes), support lists, history-key references, infos/menus, four numeric
strategy buffers and lookup maps, average/normalized policies, depth/action/hand
scratch, terminal-view snapshots, pair rows and complete strategy/history output.
A separate 25 million retained+scratch slot ceiling applies across overlapping
phases. Entries are neither Python object bytes nor an allocator/RSS guarantee.
Support tables are dropped before training; cache cleanup is in a finally path;
callback/view and obsolete policy state is dropped before row serialization.

The old candidate/world*iterations work caps describe a materialized pair/world
training path. They are unchanged for those APIs. This separately selected exact
kernel bills its actual rank/card operations with a new full-request envelope;
it does not infer legacy support or raise the old limits. Native exact-product
training, larger-policy independent verification and compact pair-free output
remain separate dependencies.

Initial complete controls independently certify the original 22-world T10 policy
under the unchanged v3 exact-game oracle; all four streets, profile and both BRs
agree within 1e-9. Exact T10 NashConv is approximately 0.6575302611616735 BB, a retained
quality miss. A common 1e-200 input scale that makes legacy products underflow
normalizes exactly: complete new-law policy/metrics equal the unit-weight control
and the actual tiny-weight case independently certifies. These are bounded
correctness controls, not source-frozen performance or convergence evidence.

## Frozen study

The fixed runner `python -m scripts.benchmark_exact_selected_solver --output
<new-external-directory>` requires a clean committed source. Its
[retained result](exact-selected-kernel-result.md) authenticates the original
source closure, complete raw outputs, manifests and separate saved review.
It preserves all four finite-iteration target misses, original 22-world T1000
pretraining admission rejection, and the small one-world T1000 target pass.
No universal accuracy, speed, memory or full-deck claim follows.
