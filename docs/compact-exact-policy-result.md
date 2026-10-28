# Compact exact-product output: frozen complete-call result

The explicit [compact output contract](compact-exact-policy.md) removes the
production private-pair diagnostic scan/table while preserving complete policies
and all eight diagnostics when both modes admit the request. It establishes no
general speed or total-memory gain. Source freeze
`3d9c8306b521c89fbc6c62f098355f28badfcf5e` completed the fixed ten fresh-process
schedule on its first run (terminal handle 16465, exit 0). The
[archive](../benchmarks/results/compact-exact-policy-v1/study.zip),
[protocol](../benchmarks/results/compact-exact-policy-v1/protocol.json),
[report](../benchmarks/results/compact-exact-policy-v1/report.json) and
[independent receipt](../benchmarks/results/compact-exact-policy-v1/receipt.json)
preserve source closure, raw streams, policies, counters, certificates and misses.
Final published-head CI/merge remain tracked in PR #259.

## Same-work measurements and structural change

All eight normal calls use the original 22-world four-street game, T10,
rank-cache capacity 64 and the same 1,200 rows/2,402 action slots. Three untraced
pairs alternate order; a fourth pair separately traces Python allocations.
Timing/tracing covers the complete solve under actual call spies, after request
parsing and instrumentation imports. Independent certification is outside timing.

| Observation | Expanded | Compact |
| --- | --- | --- |
| Untraced seconds, three fresh calls | 7.807418, 5.652645, 6.026043 | 6.703421, 6.894181, 6.548080 |
| Median seconds | 6.026043 | 6.703421 |
| Traced call seconds | 36.070454 | 34.669939 |
| Traced Python allocation peak, bytes | 2,218,238 | 2,218,095 |
| Traced child process lifetime peak, bytes | 35,786,752 | 35,823,616 |
| Actual pair queries per normal call | 4 | 0 |
| Pair-output modeled entries | 32 | 0 |
| Linear input snapshot modeled entries | 0 | 56 |
| Whole retained modeled peak entries | 365,750 | 365,774 |
| Actual kernel modeled work | 30,318,430 | 30,317,814 |
| Whole requested modeled work upper | 43,911,102 | 43,910,710 |

The compact median is higher in this small fixture, and the linear snapshot adds
24 modeled peak entries after replacing 32 pair-output slots. The structural
benefit is removal of quadratic diagnostic work/output as range sizes grow;
these observations do not establish lower total RAM, faster solving or scalable
strategy/history storage. Allocation traces and process lifetime peaks measure
different scopes and must never be added. Modeled entries/work are not bytes or
CPU time. This batch is independent of the earlier exact-product cost batch;
do not infer a cross-batch speed change.

All four complete expanded/compact policy pairs, game counts and eight metrics
are identical, and every normal sample matches sample zero. Separate unchanged
v3 exact certificates have the same ten rational metrics and normalized policy
hash `c8307412dec5e4ba8cb50e45f2719c2ed33ac15bb66dc755fb3db4842b816c22`.
Both T10 exact NashConv values remain about 0.6575302612 BB: both miss the
unchanged 0.001 BB target. Representation acceptance is not convergence acceptance.

## Full-range forced-game output contrast

Both final calls request 1,326 hands/seat and one selected board, with blinds
forcing an immediate all-in and no choices. Expanded output rejects its unchanged
serialized-output entry cap in 0.392432 s, before any pair query, rank or training.
Compact output completes in 0.842639 s with zero pair queries/training, 2,162
per-hand ranks and an empty strategy. It represents 1,070,190 compatible deals
without stored complete worlds and snapshots all 1,326 unit-weight holdings per
seat. Its modeled retained peak is 710,479 entries; combined requested work upper
is 6,735,172. This is a zero-decision control, not full-range choice-bearing
four-street training or full-deck solving.

All eight float values/BRs/gains satisfy identical-prior seat-swap symmetry within
1e-12. The independent compact certificate rejects these ranges under its
unchanged four-hands/seat cap before physical model construction. This control
has no exact quality certificate; no cap was increased to manufacture one.

## Independent replay, provenance and preserved repair

The external read-only reviewer authenticates all 1,771 tracked source files
against raw captured SHA256 and committed raw or attribute-normalized Git blobs
before importing repository mathematics. It authenticates every saved artifact
and the complete externally pinned archive, then performs eight fresh independent
physical numeric policy replays and two exact recomputations. Production solve,
training, exact kernel callbacks, native helpers and subprocess execution are
forbidden throughout replay. Source and artifact bytes are unchanged afterward.
Expanded results replay unchanged; compact verification reconstructs bounded
pair metadata from the independent physical oracle. Compact verification uses
three physical model builds, measured independently. The verifier remains
materialized and capped; this is not a scalable full-range certificate.

The first reviewer stopped because it compared pair-row order rather than unique
ordered-hand identities. The probabilities agreed. Its helper and error log are
preserved; the corrected reviewer compares unique hand keys, replays expanded
metadata unchanged and checks every repeated compact witness, report field and
certificate binding. The producer study was not rerun or modified. A separate
Sol reviewer scrutinized runner/reviewer controls while Terra/Luna were quota
unavailable; the lead performed the saved replay. Copilot quota availability is
separate from this independent evidence and is not claimed as completed review.

| External pin | SHA256 |
| --- | --- |
| Complete study archive, 890,749 bytes/29 entries | `146b25487e93c0f37d83fd92b67f1daca330d831725ae658aa49440e1bc9c4e6` |
| Producer manifest | `7e9696ce16aeefda459c6e06b0fa8241132d23b3b5f45b243fe47219bf051b2c` |
| Independent receipt | `61a9d079eaadaf695b2df9e1dc90ac350c0c0be37e3f1d0e0303dca6297d7097` |

Twenty-four compact/runner controls pass locally, including oversized/forged
witnesses, hidden future information, actual forbidden pair attempts, early
rejections, metadata/certificate tampering and first-failure preservation.
The runner's twelve controls also pass optimized Python. Legacy defaults,
probability guards, native protocols and all independent oracle limits remain.
The first full CI Python 3.11 job exposed a cross-version assumption in the
frozen-policy regression: it demanded bitwise equality with Python 3.12 output.
The [failure tail](../benchmarks/results/compact-exact-policy-v1/ci-python311-failure.txt)
is preserved. Python documents a float summation algorithm change in
[version 3.12](https://docs.python.org/3/library/functions.html#sum), consistent
with the observed final-digit trajectory differences; this is an explanation
supported by the version boundary, not a reconstructed causal trace. The
regression now requires exact row/history/menu/pair identity, at most 1e-12
probability drift and 1e-10 metric drift across versions, plus a fresh independent
physical policy replay within 1e-10 for its five profile/BR/NashConv fields.
It also caps per-row L1 drift at 1e-11, checks finite bounded probabilities and
prints observed maximum drift when nonzero. These tolerances do not establish
cross-version bitwise trajectory or exact zero-support identity. Same-runtime paired compact/expanded tests
and the frozen study still require bitwise complete policy/metric equality.
Production code and every archived study byte remain unchanged. Final repaired
head CI remains required before merge.
Strategy/history storage, exact computation cost, broader convergence and
scalable certification remain active foundation work.
