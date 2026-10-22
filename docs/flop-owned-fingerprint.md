# Fixed-flop owned-model integrity investigation

The [baseline diagnostic](flop-class-reweight-baseline-diagnostic.md) recorded
four full model validations within one complete call. Before testing any reuse,
this separate no-training experiment checks bounded structural coverage on a
fresh baseline model. It changes no solver path and skips no validator.
The current full model validation is required before and after all probes.

## Frozen request and admission

The [protocol](../benchmarks/flop-class-owned-fingerprint-v1.json) fixes one
baseline positive-prior game on the existing card/action support. Two physical
oracles enumerate 11,880 world rows in total, with at most two live oracles.
These are separate census references. Both exact model validations and six
fingerprint traversals are admitted before saved diagnostic authentication or
model construction. Shared training and all other guarded poker authorities
remain forbidden throughout the real-model block.

Each fingerprint has explicit limits: 2,000,000 distinct graph objects,
6,000,000 edges, depth 256, stack 1,024, strings at most 16,384 UTF-8 bytes,
integers at most 4,096 bits, a 256-MiB streamed encoding cap and a 64-KiB
atomic set-encoding reservation. Six object-plus-edge reservations total
48,000,000 under a separate 50-million cap. Source/report files are bounded at
2 MiB each. These named counts do not bound all arithmetic, elapsed time,
Python allocations, native memory or RSS; the encoding is hashed incrementally.
Default helper limits are not assumed to fit the real model.

## What the fingerprint means

The project-owned helper accepts exact whitelisted model, plan and numeric-tree
classes and exact built-in data types. It includes every declared model/plan/node
field, nested containers, action metadata, worlds/masses/signs, partition maps,
census and rooted node index. Tags preserve bool/int, list/tuple and signed-float
bits. Traversal-local reference ordinals distinguish shared objects from equal
copies; process object IDs never enter the digest. Mapping insertion order is
significant, and sets admit only bounded supported atomic encodings.

A fingerprint detects changes between traversals. It does not prove a graph is
poker-correct or prevent concurrent mutation or mutation followed by restoration.
Existing independent model validation remains mandatory. No cache, prepared
solver context or path that bypasses validation is implemented here.

## Six probes and evidence rules

The first two traversals must match exactly. A root action amount then changes;
its digest must differ. The amount restores in `finally`, and the next digest
and census must match the original. A rooted physical node-index entry then
changes to a distinct shallow node with identical field values; its broken alias
relationship must change the digest. That entry also restores in `finally`, and
the last digest/census must match the original. Final unchanged model validation
checks the restored genuine game.

The single run must preserve clean committed HEAD/status and 39 LF source hashes
before and after: the existing diagnostic manifest plus this helper, harness,
protocol and saved-diagnostic verifier. Retain the first original failure and
available partial/completed census; stop later work without retry or discarded
runs. The saved D029 prerequisite is authenticated only after admission. No
training, policy, numeric replay, allocation trace or comparative timing study
is part of this request.

## Completed frozen census

The one admitted batch completed at source
`1b61d75f89c8960bf6aeca464611f899a2cbc841`, from
2026-10-22 20:33:40.513991 to 20:37:24.497845 UTC. It retained six fingerprint
calls, two unchanged full model validations, all 41 authority counters at zero,
no training, no errors/retries, and identical clean HEAD/status/39-source maps
before and after. The baseline and fresh weighted physical oracles each retain
5,940 worlds; this investigation adds no policy or convergence result.

| Observation | Stable / repeated / restored graph | Node-index alias mutation |
| --- | ---: | ---: |
| Tracked graph objects | 318,280 | 318,281 |
| Traversed edges | 1,608,777 | 1,608,783 |
| Maximum graph depth | 22 | 22 |
| Maximum traversal stack | 23 | 23 |
| Hashed stream bytes | 50,383,627 | 50,383,839 |

Both action-value and node-index alias mutations changed the digest. Both
restorations and the unmodified repeat returned exactly to the original digest
and census. The action mutation keeps the same census while changing its value
encoding. The stable digest is
`8eef279da8a2dd8998e86d805079cfe900cab2a8b959a681a1fff59c45053d73`.
Aggregate observed tracked-object-plus-edge counts are 11,562,349 across the six
passes, below the admitted 48,000,000 reservation. These are this traversal's
named counters, not all Python objects, all work or allocated memory. Stream
bytes were hashed incrementally; their count is not an allocated buffer or RSS.
The recorded batch interval is incidental provenance, not a timing benchmark.

The [complete report](../benchmarks/results/flop-class-owned-fingerprint-v1.json)
preserves every digest/census, model dimensions, actual source/authority counts,
runtime, admission and prerequisite receipt. Its raw SHA256 is
`8ac7091a289a5e131348bd86fed58e769d1e1413b797a408435b1b8c2a4d56a5`;
canonical self-digest is
`48cb08101cd1d9a1c9141572609e89cf2518a06afb7fb96b1bf0591467b76afb`.
No comparative runtime, memory advantage, broader support or validation-reuse
claim follows. Existing validators remain in force.

```text
python -m scripts.verify_flop_class_owned_fingerprint_publication
```

The saved-file command authenticates bounded raw/self digests, source identities,
protocol/admission, exact counts/digests/censuses, authority inventory and runtime
metadata, then rechecks bytes and current clean sources. It performs zero
fingerprints, full model validations, ranking, training or replay. Its separately
labelled recorded counters refer to the saved experiment. A later clean HEAD
is accepted only with the same 39 executable/specification hashes.

## Provenance and publication

All 25 integrated helper/harness tests passed on the lead's CPython 3.12.14
runtime before freezing the source, including the real independent guard on a
synthetic failure, exact admitted limits, mutation restoration, primary/cleanup
error retention, guard finalization and pre-encoding bounds. The documentation
and staged whitespace checks passed. The actual single census subsequently
completed without failure or retry. Eleven publication tamper tests also passed,
including blocked model/fingerprint/training execution during authentication.
This publication is tracked in
[PR #211](https://github.com/ajpaulson18-design/openpoker-lab/pull/211).

The prerequisite diagnostic is merged in
[PR #209](https://github.com/ajpaulson18-design/openpoker-lab/pull/209), merge
`2b0867acf65ff3eaeff8e52bac1b2f2acf9b896c`. Both final Python matrices and all
other checks passed; the published head and original advance-solver commit were
confirmed ancestors of fetched main, whose tree exactly matched that head.
All three evidence blobs matched GitHub hashes and sizes. This experiment's
source checkpoint builds on that main merge.

Luna implemented the bounded helper/harness and synthetic tests; lead owned
architecture, resource admission, review, actual execution and publication.
Review required fixes to exact admitted limits, early encoding reservations,
guard-exit ordering and original/cleanup error retention before the real run.
The implementation uses the standard library and project-owned code, with no
third-party source or dependency. Frozen published executables, production APIs,
shared turn/river kernels and AI Coach remain unchanged. See the
[commercial boundary](research/LICENSING.md).
