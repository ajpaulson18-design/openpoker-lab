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

## Status and provenance

No real-model fingerprint experiment has run at this checkpoint. All 25 integrated helper/harness tests passed on the lead's CPython 3.12.14
runtime, including the real independent guard on a synthetic failure, exact
admitted limits, mutation restoration, primary/cleanup error retention and
pre-encoding bounds. The documentation checker passed as well. This synthetic
coverage is not evidence that the full model fits the caps. A reviewed clean
frozen source commit is required before the single admitted real run.

The prerequisite diagnostic is merged in
[PR #209](https://github.com/ajpaulson18-design/openpoker-lab/pull/209), merge
`2b0867acf65ff3eaeff8e52bac1b2f2acf9b896c`. Both final Python matrices and all
other checks passed; the published head and original advance-solver commit are
confirmed ancestors of fetched main, whose tree exactly matched that head.
All three evidence blobs matched GitHub hashes and sizes. The new branch builds
on that main merge.

Luna owns bounded helper/harness implementation and synthetic tests; lead owns
architecture, resource admission, review and any actual execution/publication.
The implementation uses the standard library and project-owned code, with no
third-party source or dependency. Frozen published executables, production APIs,
shared turn/river kernels and AI Coach remain unchanged. See the
[commercial boundary](research/LICENSING.md).
