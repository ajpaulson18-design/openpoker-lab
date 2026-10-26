# Fixed flop public-chance equivalence audit

Historical-record inspection after later verifier changes: use
`scripts.verify_flop_public_classes_publication.authenticate_record()` to
authenticate the unchanged published bytes, source manifest and policy records.
This performs no proof execution or current-source attestation. The existing
`authenticate()`, `verify()` and CLI retain the exact original six-source guard
before reconstruction. The October 26 preflop-validator hardening changes that
old source closure, so current-source reconstruction deliberately rejects; use
the pinned historical source revision for a full historical replay. No original
artifact, hash, miss or execution-admission rule is replaced. See
[the foundation execution record](foundation-first-execution.md).

This is a no-training audit for the same weighted full-future flop game used by
[the completed alternating study](flop-alternating-study.md). Its three original
0.005-chip quality misses remain unchanged. The class audit establishes a
bounded mathematical representation for class-constant policies; it adds no
compact trainer, API path, changed resource cap or convergence result.

## Physical game and candidate partition

The independent oracle starts from `2c3d4h`, OOP `AsAd:1,QsQd:1/2`, IP
`AsKh:1/4,KsKd:1`, pot 10 and effective stack 5. Every street allows a half-pot
bet, no raises and no explicit all-in option. A half-pot bet can exhaust the
stack. Global blocker conditioning retains three private pairs with exact
priors 8/13, 1/13 and 4/13, normalizer 13/8, and 1,980 ordered turn/river
outcomes per pair: 5,940 physical worlds in total.

The [candidate builder](../scripts/flop_public_classes_candidate.py) only
partitions supplied structural records. It accepts a bounded incomplete input
as an explicitly unverified candidate; it does not rank cards or certify
physical provenance. It uses full ordered private-pair support, original joint
mass and showdown sign, including absent pairs. Win/tie/loss totals or a suit
heuristic cannot replace those signatures.

On the complete fixed game, the candidate has 11 turn classes, 19 global river
signatures and 126 aggregated private-pair/turn-class/river-class worlds. Turn
class membership is deliberately stronger than proportional-mass equivalence:
all original exact joint masses must agree. The largest turn class contains the
remaining 2/3/4 cards and all 7-through-J cards. Five and six each form another
class; Q/K/A classes retain the relevant private-card blockers.

## Two reveal layers and exact mass proof

For each physical ordered runout `(t,r)`, form the vector over the three ordered
private pairs of `(present, original joint mass, showdown sign)`. Two river
observations can share a signature only when these full vectors agree exactly.
For a turn card, retain its per-pair marginal-mass vector and the multiset of
river signatures with their multiplicities. Turn cards merge only when both
objects agree. Each turn member has a complete deterministic river bijection to
its representative that preserves every original signature.

The [auditor](../scripts/flop_public_classes.py) independently checks these
conditions from freshly enumerated and independently ranked physical worlds.
It verifies every transport, aggregates the original Fraction masses without
per-pair renormalization, preserves each private-pair marginal and showdown
payoff, and covers each original world exactly once. The candidate's reported
signatures, mass summaries and scope fields are also authenticated against the
original records.

At each public chance node, the audit compares the complete descendant betting
subtree after replacing revealed cards by their class IDs. This includes every
public history, acting player, street, numeric action and action order, public
board, terminal kind, winner and contribution/refund amount. Both reveal layers
are checked across every betting history, including zero-reach branches.
All 30,812 physical public nodes and 11,787 physical chance-branch subtrees are
checked. The collapsed tree has 1,001 public states: 316 decisions, 58 chance
nodes and 627 terminals. It has 466 policy rows and 932 action slots, compared
with 16,912 physical policy rows and 33,824 action slots.

These conditions preserve the posterior and future signature distribution at
each merged observation. Against a class-constant opponent, distinguishing two
physical members of a class gives a responder the same continuation decision
problem. Maximizing separately on physical members therefore agrees with the
class response. Own private hands remain distinct; hidden opponent hands and
unrevealed outcomes must be summed before each maximization.

## Policy projection, lift and independent response checks

Projection first validates the entire physical policy against independent
numeric rules. It requires every row and both legal actions, then checks
bit-exact binary64 probability equality within each class. It rejects
card-specific differences, including zero-reach rows and signed-zero
differences, rather than averaging them. The rational lane requires finite
binary64 probabilities in [0,1] whose exact Fraction sum is one. Arbitrary
rounded or near-normalized policies need separate handling and are outside
this audit's accepted policy domain.

Lifting restores every physical information-set row and probability without
changing its bits. The audit compares all eight exact profile/response metrics
between the class game and the unrestricted physical game, and compares those
values with the existing separate physical numeric oracle. Both exact response
lanes separate own hands and retain all hidden worlds until a legal public
reveal. The numeric lane is independently implemented; backend parity alone is
not the evidence.

Four deterministic controls exercise check/call, bet/fold, varying own-hand and
class/history probabilities, and branches with zero reach. They are synthetic
policies, with no training or equilibrium claim. The check/call profile has the
closed-form value `5 * sum(original_mass * showdown_sign) = 602/429`; the
bet/fold profile has value 5. Complete compact probability rows, physical policy
and strategy digests, all exact metrics and numeric gaps are retained in the
audit record. Every full physical row can be reconstructed from the saved
compact rows and checked lift.

## Resource and provenance boundaries

Fresh physical enumeration uses the existing independent oracle's limits. The
fixed audit adds bounded public traversal, candidate record sizes, exact-input
integer sizes and exact metric bit lengths. Complete physical world and numeric
tree digests anchor the fixed game; model revalidation checks its policy-node
index, visibility tables, metadata and census. Mutation of physical mass/sign,
class mass, transports, actions, terminal contributions or visibility rejects.
The CLI disables production parsers, rankers, tree builders, trainers and
profile/response helpers while preparing and auditing. It records zero forbidden
calls and unchanged normalized hashes of the six executable validation sources.

This foundation does not authorize compact training by itself. A later trainer
requires its own complete request admission, numerical recurrence controls,
physical policy lift, independent responses and a frozen quality study. This
fixed class result does not apply to other ranges, boards, betting trees,
conditioned runouts, earlier streets or the separate TURN/RIVER class work.

## Reproduction

Run from the repository root. The output must not already exist:

```powershell
python -B -m scripts.flop_public_classes --output <new-audit-json>
python -B -m unittest tests.test_flop_public_classes_candidate tests.test_flop_public_classes -v
```

The first command performs the fresh physical and full exact/numeric audit.
It performs no training and does not measure solver runtime or memory.

## Completed proof record

The [saved proof](../benchmarks/results/flop-public-classes-v1.json) retains all
four controls and their 466 complete compact rows each. All eight exact metrics
agree between class and unrestricted physical calculations; the maximum
independent numeric gap is 8.881784197001252e-16. All 41 production-authority
counters remain zero, and all six executable validation source hashes match
before and after the run. The proof's raw SHA-256 is
`c661a01a579b59053e93f7200d68dcda595df858dc5592cf9921e8f7a692e66a`;
its canonical unsigned artifact SHA-256 is
`996cd561cac42c63df41052df7e32168cfe5b1bb194c08bcc5b427c1fec6792d`.

The first CLI attempt lost its tool process during a runtime refresh and
produced no final output. Its [interruption receipt](../benchmarks/results/flop-public-classes-initial-interruption-v1.json)
is retained separately; no success is claimed for that attempt. The subsequent
complete audit used a persistent log. This was a no-training mathematical
audit; no completed solver measurement was restarted or changed.

The [publication verifier](../scripts/verify_flop_public_classes_publication.py)
pins both raw records, then freshly rebuilds all physical worlds and replays the
four complete controls. It has independently completed with zero training:

```powershell
python -B -m scripts.verify_flop_public_classes_publication
```

The measured validation sources are required to match their normalized source
pins; adapting this proof to changed validation code requires a new audit.

The focused suite passed all **26 tests in 239.533 seconds**, covering candidate
structure, all four physical/class controls, the strict hidden-information
control, zero-reach/card-specific rejection, exact input/probability/resource
bounds, mutated masses/signs/transports/subtrees/metadata and publication pins.
The first test selection assumed later decisions after a flop all-in; it was
corrected to a class-duplicated turn/river facing-bet row, without changing the
audit implementation or saved proof.

A separate [fixed-game CFR+ research adapter](flop-class-cfrplus.md) adds its own
admission, raw-policy retention and physical replay. The proof above remains
a no-training record and makes no claim about convergence or performance.
