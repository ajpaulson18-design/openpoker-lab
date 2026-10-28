# Exact suit-orbit strategy storage in the selected four-street game

Status: integrated opt-in implementation with a [frozen 23-call result](suit-quotient-storage-result.md),
22 independently replayed policies/certificates and eleven independently
reconstructed row-orbit checks. Final publication CI remains an acceptance gate.
This page does not declare the storage backend accepted or commercially scalable.

The [storage frontier](exact-storage-frontier-result.md) established that own-hand
and full-history row growth survives public DAG sharing. It also showed that
many games have identity-only suit symmetry. The
[equivariant numerical reference](equivariant-selected-training.md) supplies the
required arithmetic contract for sharing rows without silently changing their
binary64 learning trajectory.

## Supported reduction

The explicit selection is
`training_reduction="suit-equivariant", strategy_storage="suit-quotient"` on
`solve_four_street_exact_selected`. The expanded default and ordinary training
reduction remain separate. Quotient selection requires the explicit new
numerical contract; it must never fall back to expanded training on a failure.

The group consists only of global S4 suit permutations preserving each seat's
exact parsed hand-weight map and the complete canonical-flop/ordered-turn/river
selected-outcome set. SB and BB do not exchange roles. This is a sufficient,
conservative group, not a claim to discover every possible game equivalence.

The graph verifier independently derives a topological order from unique edges,
rejecting cycles, invalid IDs and unreachable vertices. Bottom-up identity keys
contain terminal kind/winner and binary64 contribution hex values; decision
player, complete ordered action menu and child signatures; or chance street,
card position and sorted labeled child signatures. For each group element,
transformed keys are looked up in the identity interner without insertion. The
transformed root signature and initial history must match. This proves closure
of the supplied public graph, conditional on its construction; it does not
independently prove unrestricted betting legality or policy quality.

## Procedural row identity and member coverage

A row is `(global player, physical own-hand index, complete visible history)`.
`SuitQuotientPlan` streams actual positive physical support, transforms one row
under the group, deduplicates and sorts at most 24 images, and chooses the minimum
as its Q representative. The original row's ordinal among those distinct images
is its member bit. Deduplication handles row stabilizers: a group of size two can
give both one-member and two-member row orbits.

The plan retains Q semantic keys, immutable ordered menus, offsets/counts,
expected member masks, bounded G-by-H hand transformations and prefix support.
It retains no R-to-Q member-history dictionary. Full histories route through
actual unique graph labels before lookup, so a syntactically valid prefix alone
cannot authenticate a decision row. Plan construction verifies every expected
distinct member exactly once; duplicate or missing occurrences reject.

Maps and supported sets are immutable, plan attributes seal after construction,
and public admission/receipt access returns detached deep copies. The plan weakly
owns its exact kernel and binds its immutable input identities. Its iteration
count must equal the original admitted preparation, rather than a smaller
caller-selected count. This prevents a plan from borrowing admission from a
different requested run.

## Learning and output obligations

The quotient trainer allocates four Q-action binary64 arrays for
regrets, average sums, current probabilities and staged increments. During each
responder phase it captures the first member's action increment, compares every
other member's canonical binary64 bits, and validates complete member masks
before updating any persistent regrets. It applies one unchanged increment and
CFR+ clipping per Q row. Averaging separately stages the reference association
`marginal * own_reach * probability * iteration`, validates every member,
and commits once. Summing members and dividing by orbit size is not equivalent
binary64 arithmetic. Zero-reach rows still participate in coverage and bit checks.

All chance and action operations must match the unquotiented numerical reference,
including uniform absent-row probabilities. Any inconsistent menu, missing or
duplicate member, arithmetic mismatch or nonfinite result aborts without a
returned policy. A failed later phase discards the entire solve; it is not a
reusable checkpoint. Allocation and traversal failures must release actual
numeric buffers even with cyclic GC disabled and retained tracebacks.

Only after those buffers and recursive helper cells are released may a complete
R-row policy be reconstructed for unchanged diagnostics and independent physical
certificates. This output and diagnostic storage can still dominate the complete
call. Q payload reductions do not establish a smaller whole-process peak or a
faster solve. Identity-only games retain Q=R and pay overhead.

## Admission and current evidence

Every original game, R/S/dense layout, output, exact arithmetic and whole-request
cap remains. Additional admission reserves group search before its allocations,
graph validation before variable payload loops, and full signature work before
graph arrays/interner growth. It separately reserves Q history keys, procedural
lookup and sorting, masks, phase checks, prefix support and output reconstruction.
No projected savings lower an old admission bound. Work/entries and pure numeric
payload bytes are logical models; allocator and process observations are separate.

Initial independent adversarial controls found mutable internal maps, unbound
iterations, graph validation before a low-budget rejection, and uncontrolled
malformed-history errors. The first failed helper/log are preserved. After fixes,
the three original independent controls pass; malformed histories also reject
as `ValueError`. Ten plan controls plus eighteen graph controls pass with
assertions disabled, including partial-support setup cleanup with a retained
traceback. Nine trainer controls and nine whole-solver controls compare complete
policies, all eight metrics and exact-certificate fields for exchanged private
hands, identity-only weights, mixed orbit sizes, four-hand blocker holes, and
the no-decision blind-all-in boundary. Added controls preserve tiny positive
priors and verify both winning and losing independent hidden-world payoffs in
a private-flush game. The combined 71-test quotient/existing
solver/storage suite passes with assertions disabled (45.534 s). A later receipt
correction counts the actual Q semantic dictionary and separately reports zero
expanded lookup entries; all nine trainer controls pass again (3.039 s).

Nine independent external adversarial controls verify responder and average
phase failures before commit, menu corruption, actual Q array dimensions,
release before expanded output and partial-allocation cleanup. Initial
reviewer-only test errors remain preserved. A source-frozen paired study,
independent saved-policy replay and measured costs are recorded in the linked
frozen result; final publication CI remains. The
fixed study has 23 calls, including private-flush T10/T100 pairs. Twelve runner
controls pass, including actual child execution and protected independent replay.
