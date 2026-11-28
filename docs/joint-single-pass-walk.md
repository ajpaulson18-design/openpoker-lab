# Single global-value joint walk candidate

Status: exact-conformance, paired-performance, saved-replay and Windows/Linux/
sanitizer gates pass. The two-target path remains the
explicit baseline. This opt-in candidate changes computation and its versioned read/census
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
These source-ledger predictions agree with the local executed admission and
counters. They are not CPU/RSS measurements.

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

## Local executed result

At source `70f5209`, ten named requests and eight real parser rejections pass
normally and with optimized Python. Each mode observes 18 candidate calls and
four fresh baseline calls for the added win/loss cases; the original six
baseline wires remain authenticated historical inputs. Both corruption controls
reject. The unchanged independent Fraction authority verifies every retained
R/A/policy coordinate, both roots, implicit defaults and full-history identities.
The independent law/ranker confirms tie/loss/win witnesses for both profiles.
Ten typed one-read/two-read ownership and completion guards also pass, and
the legacy N9 whole path plus epoch controls pass normally and optimized.

The frozen paired comparison observes 132 actual complete calls. Its eight
candidate/baseline elapsed ratios are 0.984696, 0.696474, 1.025201, 0.891761,
0.801919, 0.751796, 0.922430 and 0.744129. Median 0.846840 and seven faster
pairs pass the predeclared 0.95/six-pair gate. Every mode's full wire remains
exact and both modes share the same numeric projection. This is a one-host
result for the specified three-world mix, including construction, training,
serialization and process overhead; no inner-walk CPU attribution is inferred.

The first candidate compilation at `fdf33d7` failed MSVC C4127 under `/WX`
because a template constant appeared in an ordinary conditional. The fix uses
an explicit `if constexpr` assignment without weakening warning flags. Keep
that first failure and the original six-case matrices with the expanded result.

Windows, Linux and sanitizer jobs, including both Python modes and artifact
uploads, pass at `f660712`. The [immutable packet](../benchmarks/results/joint-single-pass-v1/manifest.json)
retains 53,666,088 expanded bytes under the unchanged 80-MiB archive budget.
All 132 timing receipts remain distinct; exact stdout objects are deduplicated.
The [maintained saved-only reader](../scripts/replay_single_pass_packet.py)
authenticates the flat inventory, every source/build/process closure, historical
checkout hashes, current independent math and frozen protocol before replay.
Normal/optimized reports are byte-identical and run zero native or archived
source calls. [Replay observations](../benchmarks/results/joint-single-pass-replay-v1/post-run-index.json)
also preserve the initial source-form refusals and the subsequent tuple/list
report-encoding refusal; none changes the raw mathematical authority or wires.

The [longer-lifetime worksheet](joint-learning-lifetime.md) makes the next
storage gate explicit. A faster T2 walk does not admit a persistent learner.
