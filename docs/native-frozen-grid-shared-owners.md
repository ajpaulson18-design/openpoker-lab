# Shared native contracts for the forthcoming raw-update walk

The next update owner must reuse the [immutable policy boundary](native-frozen-policy-state.md)
and [V2 resource envelope](frozen-grid-update-envelope.md). Their implementation
now lives in reusable native headers rather than test-only anonymous functions.
`virtual_frozen_policy_snapshot.hpp` owns the versioned bounded input decoder,
full visible-history reconstruction, complete State import/seal and output
boundary. History and State remain the identity and policy owners.
`virtual_frozen_grid_update_forecast.hpp` contains the same geometry, corrected
eight-prefix-query ledger and provisional feasibility checks.

The trainer's exact integer reach advancement is also a shared internal
primitive. Its original caller retains the same charge before calling it;
no operations, policy values, cancellations or supported game settings changed.
Inputs are State-validated Q52 units; no binary64 probability conversion occurs.

## Executed compatibility checks

At source `53370bfd67745e704ce03299b6eeae2123dfa449`, five complete snapshot
tests and two envelope tests passed. The refactored output is byte-identical
to the preserved original for both complete 24,420-row/58,164-slot profiles,
the small lifetime/directory controls and all 5,040 V2 forecasts.

| Output | Bytes | SHA256 |
| --- | ---: | --- |
| Uniform snapshot | 1,442,320 | `a0281877334a4e20faafe0a95757749e324ce108ebd3e187d3cb3c923d4b7ebb` |
| Zero/skew snapshot | 1,442,320 | `86be8ccd6a8ce458fa73e356ba78560bfc67d6769c292ec6afe147f3970af3f8` |
| Small controls | 1,009 | `b04cacdb82f7e71d6bbe9e192f921d197385ef9d91f3ba987ecf5d8e2c47125e` |
| V2 envelope | 752,190 | `5d789b186dc052c036a05d5d04fa84f99409ec72ca78295ee174fc382eaa1ab4` |

At source `d72aff458b9e115498d47bb176194e129a44a7f4`, the source-built default
trainer completed one existing `TRAIN_TEN_BOUNDED_DIVISION` regression. Its
entire 50,507,464-byte emitted wire matches the preserved SHA256
`7fde396c4c2e645087d9fd8abdc373a97a485265bf157e537e3cfd181c538945`.
Both 23,701,776-byte checkpoints and all nine stable owner sidecars match.
The controller observed an actual successful exit, retained the numerical
stream, authenticated source/executable before and after, and made no retry.
This is existing ten-card regression evidence, separate from the unimplemented
fixed-board update. It establishes no timing or larger-game benefit.

## Reproducible record and remaining gate

The [immutable packet](../benchmarks/results/native-frozen-grid-shared-owners-v1/manifest.json)
has 215 members and 5,938,835 bytes, SHA256
`e34d62021b526e0e52d3c291310b579f48c54b6cdc018e8c3564c8087803a2f9`.
All member hashes and CRCs passed. It contains exact source/build closure,
binaries, complete snapshot requests/responses, forecast output and observed
training receipts. Identical large checkpoints are referenced by exact hashes
to the existing immutable ten-card packet rather than duplicated.

`python -B -m scripts.replay_shared_grid_owners_packet` authenticates the
archive, replays the snapshot and envelope using their maintained independent
verifiers, checks the complete training observation and authenticates both
referenced canonical checkpoint byte streams. It makes zero candidate calls
and never executes archived code.

These are shared contracts and compatibility evidence. The native per-board
raw-update owner, its cumulative actual meters and independent raw-row replay
remain the next gate. Update admission, sampled learning, clipping correctness,
strategy quality, eleven-card admission and practical full-deck capacity remain
unresolved. No resource ceiling was increased.
