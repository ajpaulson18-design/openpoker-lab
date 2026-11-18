# Native immutable policy State boundary

This explicit research target connects the [Q52 arithmetic contract](native-frozen-grid-arithmetic.md)
to the existing native History and State owners. It imports and reads a complete
immutable policy; it performs no update, ranking, quantization, training or quality
evaluation. It provides no eleven-card or full-deck capacity acceptance.

## Ownership and identity

`State::begin_frozen_policy_import` admits the complete import and all requested
reads before allocating grid units. Rows arrive in canonical directory order.
State validates the owned History cursor, actor, original holding, ordered legal
menu and exact Q52 partition, copies units, then advances its import count.
Reads become available only after all rows are sealed. Zero units and zero-reach
rows remain present. Numeric regret/average storage is absent, and training,
restaging, export and reopening reject in this phase.

This first boundary is resident and unpacked. It retains the existing conservative
dense storage forecast and grants no storage credit for the missing numeric
arrays. Paged import, immutable epochs, sparse updates and unvisited-row behavior
remain separate architecture work. The training defaults remain unchanged.

`History::decision_cursor` restores an already-owned directory key for readback.
It is not authentication of an external ordinal. Incoming rows reconstruct the
entire visible history from root using native legal actions and reveals.
The independent verifier maps every returned ordinal back to the original
holding and full history using its separate numeric rules.

## Versioned complete request

The fixed nine-card request has 24,420 rows and 58,164 action slots. Input starts
with `OPLFGS01` and six little-endian uint64 values: row count, slot count,
history-token count (249,662), history ASCII bytes (1,500,675), menu ASCII bytes
(294,353), and Q=2^52. Each row carries five uint64 values: actor, two original
card IDs, history length and action count. Length-prefixed ASCII history and
ordered menu tokens follow, then uint64 grid units. Tokens are 1–64 bytes.
The complete input is 3,545,022 bytes, within the existing 8 MiB input ceiling.

Output starts with `OPLFGV01`, then seven uint64 values: rows, slots, whole work,
entries, payload bits, History work and State work forecasts. Each row carries
actor, holding index, directory ordinal, slot offset, action count and grid units.
The 18-word footer reports rows, slots, actual composed work, History work, State
work, template work, parent work, chance work, input bytes, output bytes, rank
calls, contractions, quantizer work, completed sweeps, staged rows, imported rows,
read calls and ready flag. Exact output is 1,442,320 bytes; its 2,100,000-byte
reservation fits the existing child-output controller ceiling. The earlier text
format's oversized declaration was refused before any native child launched;
the controller limit was preserved.

## Whole-request admission

The request is admitted before template/catalog construction. The candidate builds
no physical world table or private-pair payoff matrix. Catalog mode reuses the
native public walk and State directory. The independent test oracle may enumerate
the sixty bounded literal worlds.

| Reservation | Forecast | Existing ceiling |
| --- | ---: | ---: |
| Whole modeled work | 309,602,837 | 500,000,000 |
| Logical entries | 1,168,201 | 2,000,000 |
| Payload bits | 256,883,688 | 1,073,741,824 |
| History work | 39,479,280 | 42,000,000 |
| State work | 54,125,756 | 75,000,000 |

Composition includes template preparation, chance setup, public catalog, input
validation, lifetime import/read work and serialization. I/O reserves 16 work
units per ceiling byte. These are modeled work and payload bounds, not CPU time,
process memory or a performance improvement. The independent oracle derives the
public-prefix census and equations without native forecast helpers. Final actual
counters must fit each component and sum to the composed actual total.

## Verification and next gate

The explicit build target is `virtual-frozen-policy-state-controls`. Conformance
compares every grid unit for uniform and zero/skew profiles, tests incomplete
imports, foreign identities, ordering, partitions, phase and lifetime violations,
and requires corrupt inputs to expose no partial output. The workflow runs normal
and optimized Python on Windows, Linux and sanitized Linux.

`scripts.replay_native_frozen_policy_state` authenticates captured introduced
source and build identity before importing the current independent oracle. It
replays saved inputs/outputs and actual process exits with zero candidate calls.
Archived source is never executed. Historical packets remain immutable. Executed
evidence is recorded separately from this contract.

The [retained packet](../benchmarks/results/native-frozen-policy-state-v1/manifest.json)
contains 408 members in a 7,733,361-byte archive, SHA256
`ecb72cd2bcbcdb1fb7089da6401ae558a4d71855daefdda86828b7c3817fbdd5`.
Native source `a776062138346a58e4703b46d8e606834d47d3de` and observation source
`5ae1757e560e249975a28c9f215cff47953eea9c` passed five complete conformance
tests normally and optimized. Each mode observed nine native cases with actual
exits; both complete profiles matched all rows and slots. Actual modeled work
was 209,671,033, History 31,606,488 and State 52,404,808 for each profile.
The 11 existing compiled State tests passed; their 48,753-byte output stayed
identical to the pre-change baseline, SHA256
`e939f1a865ac94fc791299a4c9b21fef19490a31fdc7615aa7d4954d3d47c26e`.
The packet retains exact source/build closure for both legacy binaries, the
new target, inputs/outputs, exits, original refusals and their repairs.

The [archive-only replay](../benchmarks/results/native-frozen-policy-state-v1/archive-replay.json)
passes for both extracted observations with zero native calls. Saved controls
can be reproduced with `python -B -m scripts.replay_native_policy_packet`;
the historical replay workflow runs that command normally and optimized on
Windows and Linux, authenticating every archive member before replay.
Saved controls
normally and optimized reject source bytes/membership/blob drift, false exits,
foreign commands, stream identity drift, an ordinal mutation with recomputed
transport hash, and an invalid input partition with recomputed transport hash.
The active entrypoint is trusted executed code checked against its current
committed bytes; the captured oracle/codec dependencies remain frozen. The two
historical mixed-ending native headers use exact raw/blob pins recovered from
the immutable PR325 packet. No arbitrary source normalization is accepted.

At PR329 source `ed5ee143bd4e1dda76c96621a16505def0c73374`, Windows job
[135223168130](https://github.com/ajpaulson18-design/openpoker-lab/actions/runs/44423763831/job/135223168130),
Linux job [135223168104](https://github.com/ajpaulson18-design/openpoker-lab/actions/runs/44423763831/job/135223168104)
and sanitizer job [135223167858](https://github.com/ajpaulson18-design/openpoker-lab/actions/runs/44423763831/job/135223167858)
passed both five-test import suites, saved replay and two saved-control tests.
Decoded logs are retained beside the immutable archive, with line endings
converted to LF for storage. This is executed cross-platform conformance,
not a runtime benchmark or a solved-quality result.

The next computation gate is a fully admitted per-board raw update through
existing prepared contractions and exact reach, followed by complete independent
row comparison. This read boundary alone cannot remove the eleven-card State,
quantizer or parent-work failures. Learning, clipping, sparse/paged lifetime
semantics and independently replayed policy quality remain unresolved.
