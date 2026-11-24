# Single global-value joint walk candidate

Status: source-only next experiment. The accepted two-target path remains the
baseline. This proposal changes computation and its versioned read/census
contract, not chance law, information identity, cumulative signed regret,
average weighting, policy quantization or update timing.

## Exact equivalence argument

For one certified private pair and complete board, freeze both players' Q52
policies. Express every continuation in global SB utility units. The two
existing target walks traverse the same actions in the same order with the
same policies and terminal utilities; target identity only selects which
actor's rows are retained and negates the second root after traversal.
Their conditional global-SB values are therefore identical exact integers.
Preserve distinct full histories while reusing each history's conditional value
across seats; the shared numeric DAG does not define policy-row identity.

One complete traversal can compute
`v(h)=sum_a pi_actor(a|own,visible_history)*v(ha)` once and retain every actor's
rows. Its regret contribution is
`sign(actor)*opponent_past_reach*(v(ha)-v(h))`, with signs +1 for SB and -1 for
BB. Its average contribution remains `own_past_reach*pi_actor(a|row)`.
Keep the same exact factor cancellation and denominators `2^625`/`2^364`.
Return the global SB root and its exact negation. The independent Fraction
reference already uses this global-value algebra and remains unchanged.

All actions, including zero-policy and zero-own-reach branches, must still be
visited. Policy lookup uses only original own holding and visible history.
Both seats' rows are staged against the same immutable input policy, then
committed together. Row staging order may differ, but each row's exact
cumulative R/A and independent stable Q52 apportionment must be identical.
This is an exact per-observation equivalence, not a new stochastic-convergence
or CFR+ clipping argument.

## Explicit contract and unchanged caps

Use a new weighted single-pass arithmetic/read contract. An epoch expects one
read per complete row, while every existing constructor/mode retains two.
Reject mixed read/arithmetic modes before numerical preparation. Seal exactly
434 rows, 1,039 slots and 434 reads after 1,105 visits, 1,039 actions, 65 reveals
and 606 terminals. Duplicate reads, incomplete seals and foreign identities
still fail closed. The existing two-epoch numeric union remains at most
868 rows/2,078 slots. No capacity ceiling is increased.

The proposed scalar raw families per observation are reach 61,301, scale 32,118,
mix 377,932, average 112,382, stage 45,424 and walk 283,392: total 912,549.
They replace two identical continuation calculations with one; regret and
average row work remain. For the named full52 T2 request, prospective composed
work is 149,877,434, including Catalog 29,228,320, History 5,443,024,
Store/quantizer 17,132,608, parent 3,313,610 and unchanged Chance 43,715,840.
These are source-ledger predictions to verify before execution, not CPU/RSS
measurements or an admission result.

## Frozen acceptance gates

1. Freeze candidate, independent census/framing references and source closure
   before compilation or execution. Keep the baseline mode explicit.
2. Recheck all ten full52 named requests and real parser rejections in normal
   and optimized Python, including every retained R/A/policy coordinate,
   untouched-default contract, signed negatives, zero-reach cases and both
   root signs. Explicit independent tie/loss/win witnesses supplement the
   earlier six endpoint requests, whose selected showdowns tied. Preserve
   baseline N9 conformance and error bytes. Retain the original six-case
   matrices separately instead of expanding their historical scope.
3. Compare canonical numeric byte projections (roots, row descriptors and
   every R/A/policy unit) against baseline. Header/resource/read/visit fields
   may differ only by the independently derived single-pass contract.
4. After correctness, freeze eight alternating pairs of eight complete
   standard/candidate calls, with two warmups each, on the named weighted
   full52 T2 request mix. Cycle tie, SB-loss and SB-win worlds with index
   `(8*block+call)%3`, identically for both modes. This coverage revision is
   frozen before any timed single-pass comparison; no timing has been observed
   for the earlier proposed tie-only comparison. Every actual exit and exact numeric projection
   must match. Require median candidate/baseline elapsed ratio at most 0.95
   and candidate faster in at least six of eight pairs. Keep all misses.

The [accepted coarse profile](joint-walk-cpu-protocol.md) places about 34% of
phase wall time in the walk on its frozen source/host/request. That motivates
this measured experiment; it does not identify an inner-walk CPU family or
promise the proposed speedup. Longer learning, retained-union scaling and
saved-policy quality remain separate architecture gates.
