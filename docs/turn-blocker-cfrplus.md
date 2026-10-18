# Production CFR+ against the blocker-turn exact witness

This audit uses the unchanged [six-world blocker-conditioned turn game](turn-blocker-sequence-equilibrium.md)
and its independently certified exact value 115/7. It records full production
policies rather than treating finite iteration counts as equilibrium proofs.

## Experiment fixed before training

The materialized public-batched trainer and matrix-free trainer each run CFR+
for 1,000, 3,000 and 10,000 complete iterations. All six results remain in the
report. The declared target is exact normalized NashConv at most 1/1000 chip;
no iteration budget or threshold changes after observing a miss.

Both APIs receive the same turn/river configs, weighted ranges and selected
rivers. There are six compatible physical worlds, three private pairs and 56
own-hand/public-history policy rows. The public tree has 63 total nodes and
28 decision nodes; replay's `public_node_count` names the decision count.
Conditioning remains global over compatible private hands and selected futures.

## Replay and provenance

Each saved policy is the complete serialized binary64 API result. Independent
numeric replay validates its full legal action/public history structure and all
eight reported metrics. The exact certificate normalizes each serialized row
using rational arithmetic, retains a full per-action adjustment ledger and
computes both legal own-hand best responses. Every exact response interval must
contain 115/7, and every exact metric must agree with numeric replay within
1e-9. Exact bounds apply to these normalized serialized policies in the configured
numeric model; they do not assert exact arithmetic for the training process.

The primary producer and verifier pin all required proof inputs and accepted
witness bytes. Before and after training or replay they also snapshot current
source inputs, including every `pokerlab/*.py` file and the benchmark wrapper.
Extra historical training-source hashes remain context; required current proof
pins stay strict, with LF/CRLF equivalence for Python source only. Policy and
mathematical JSON bytes are exact. Saved verification never calls a trainer.

A separate checker imports no trainer, LP or exact-policy evaluator. It first
reconstructs the exact blocker witness, then independently normalizes all six
policies and recomputes their eight metrics, complete adjustment ledgers,
physical counts, known-value intervals and each target decision. It guards its
own source, proof dependencies, observed input bytes and Git HEAD across replay.

Policies are written exclusively and cannot overwrite differing accepted bytes.
A staged report must pass verification before and after atomic replacement.
A failed publication restores the previous report and removes only policy files
created by that attempt.

## Measurements and executed results

The [complete report](../benchmarks/results/turn-blocker-cfrplus-profiles-v1.json)
contains all six [full policies](../benchmarks/results/turn-blocker-cfrplus-policies-v1/turn-blocker-materialized-1000.json),
exact bounds and normalization ledgers. The primary saved-file verification and
separate arithmetic reconstruction both passed. All response intervals contain
115/7. Four target misses remain recorded, and both 10,000-iteration profiles
meet the unchanged target.

| Backend | Iterations | Exact normalized NashConv (float view) | Target met | Solve plus JSON seconds |
| --- | ---: | ---: | :---: | ---: |
| Materialized/public-batched | 1,000 | 0.0035295963922469683 | No | 1.7909163 |
| Materialized/public-batched | 3,000 | 0.0025569628165122856 | No | 5.8578099 |
| Materialized/public-batched | 10,000 | 0.00041359382389885384 | Yes | 17.4535906 |
| Matrix-free | 1,000 | 0.0035295963922472758 | No | 6.9107784 |
| Matrix-free | 3,000 | 0.0025569628165141825 | No | 20.9023873 |
| Matrix-free | 10,000 | 0.00041359382389848754 | Yes | 73.2550157 |

These are single complete-call observations on Python 3.12.14, Windows 10, with
replay timed separately. There is no comparative speed, memory or RSS claim.
All eight exact/float metric differences are at most 1.0855248991359367e-14.
Each certificate uses 3,156 charged exact work units at depth eight; maximum
fraction sizes range from 1,323 to 1,493 bits under unchanged 100,000-work,
64-depth and 65,536-bit limits.

The report is 730,283 bytes with SHA256
`5c5d4b60108af53256e9f58f21494967887fd91c8ac2871150c48f454f733e76`.
It records 74 generation source/input hashes. The separate checker is versioned
with the report in Git and guards its own bytes during reconstruction; its
digest is not part of that generator inventory.

This experiment leaves shared kernels, production payloads, prior proofs,
earlier streets, Coach and frontend unchanged. The selected river set defines
a finite conditional game; this is not unrestricted or full-deck Hold'em.

Executed regression checks passed 18 tests in normal Python (25.185 seconds)
and 18 with optimization (23.451 seconds). These include saved verification
with trainers disabled, exact-ledger/source/HEAD/policy drift, stale proof pins,
backend and threshold metadata, oversized inputs, forged metrics and atomic
publication rollback. The independent accepted-file test disables the exact
policy evaluator. Commands are `python -m unittest tests.test_turn_blocker_profiles tests.test_turn_blocker_profiles_independent -q`
and the same invocation with `-O`.
