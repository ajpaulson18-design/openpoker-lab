# Next dependency: remove private-pair scans without silently changing the game

Architecture review by Sol and independent scrutiny by Terra, after native
selected-operator source 02982d145c7367f2919f577e1dbd40eb6bf87c8a.
This is a design boundary, not implementation or convergence evidence.

## Numerical obstacle

For weights [0.7,0.3] against [0.4,0.6], the old raw formula
fl(fl(wi*wj)/34246080), followed by global fsum and per-occurrence division,
produces [[0.28,0.42],[0.12000000000000001,0.18000000000000002]].
Its exact binary-rational determinant is
11168927075878831/1298074214633706907132624082305024, which is nonzero.
Thus an outer-product kernel cannot reproduce every legacy normalized pair
matrix exactly. Original per-pair board summation order is a second boundary.
Do not replace it with a factored formula under an equivalence claim.

## Candidate explicit new contract

Snapshot parsed binary64 weights as exact rationals. Give each compatible
private-pair/selected-board occurrence mass wi*wj/Z, with one common
Z=sum_board sum_compatible wi*wj. The identical physical-board chance divisor
cancels globally. Do not use full-deck prefix divisors or normalize per prefix.
Reaches and payoff scales need explicit exact snapshot/conversion boundaries.
Public histories and own-hand information-set identities remain shared.

For each selected board, filter board-blocked hands. Opponent compatible weight
for own hand {a,b} is T-C[a]-C[b]+same_hand. With rank-sorted opponent hands,
maintain lower/equal/higher total/card sums; signed compatible value is lower
minus higher, excluding ties. Same-hand add-back applies only to the bucket
containing that exact holding. Absolute marginals use priors without opponent
strategy; counterfactual terminal values use opponent reach exactly once.
Average strategy uses own sequence reach and absolute prior marginal.
Early all-in terminals sum all compatible unrevealed selected boards.

Exact rational arithmetic supplies a correctness reference and avoids
cancellation; integer-bit ceilings and modeled operations are independent
admission obligations. Any floating implementation needs rigorous error/fallback
or rejection rules, including admitted worst-case fallback work. No near-linear
complexity claim may hide quadratic fallback. Rank preparation is O(B H log H),
and reusable rank order permits O(B(H+52)) dynamic weighted sweeps in an intended
factored algorithm; retained groups, maps, ranks and output remain counted.

## Required next implementation evidence

1. Rank-free range/board/betting-growth census before choosing a storage remedy.
2. Independent tiny physical-pair enumeration for the new exact law; no reuse of
   the production factorization, rank groups or probability helpers as oracle.
3. Exact prefix/pair/marginal/fold/showdown vectors, shared futures, blockers,
   ties, identical holdings, inactive own indices, zero reach, asymmetric and
   extreme representable weights, root/all-in and early terminal controls.
4. Explicit demonstration of divergence from legacy rounded arithmetic rather
   than relabeling approximate equality as exact equivalence.
5. Connection through the existing four-street rule/history and CFR boundary,
   independently replayed policies and legal BR/accuracy targets.
6. Source-frozen complete calls, structural/work counters and storage receipts.

FullDeckPrefixMass offers exact inclusion-exclusion patterns, but a different
chance law and no terminal/training path. Ranked river operators offer useful
rank/card organization, but separate normalization and possible quadratic
fallback. Neither can be substituted unchanged into the selected whole game.
Explicit public-tree/information-action growth remains an independent F03 issue.
