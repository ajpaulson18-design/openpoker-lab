# Fixed-flop phase profile

This is one opt-in 560-sweep compact solve wrapped at existing module boundaries.
It leaves the published solver and CFR+ source bytes unchanged. The
[ordinary complete-call comparison](flop-class-call-cost.md) remains the primary
timing evidence.

Each wrapper records a unique event ID, parent event ID, phase name, UTC start
and finish, monotonic wall seconds, process CPU seconds, and error status. A
phase can be nested inside another phase; inclusive durations overlap and must
not be summed as separate costs. Wrappers are restored in `finally`, including
when a phase raises.

The profile includes the existing solve and canonical serialization/hash
boundary through `flop_class_call_measurement.measure_call`. Wrapper dispatch
adds overhead, so these phase timings are diagnostic only, not the preregistered
call medians or a same-work speed comparison. They do not measure RSS.

The run admits the full 560-sweep request before pilot authentication, then
requires clean source snapshots before and after. It retains the raw policy in
bounded gzip and limits the event ledger to 1,000 invocations. A failed profile
remains an error artifact with traceback; it is never retried. The protocol's
LF SHA-256 is pinned by the runner. The single preregistered call completed on 2026-10-22 without retries, source
drift or recorded errors. Its clean source checkpoint is
`369436002791813e3983104f63e8131b5d3aa0e1`.


## Retained observation

The complete call took 172.881961 wall seconds / 165.875000 process CPU seconds
on CPython 3.12.14 / Windows 10. Its full raw report is byte-identical to the
independently replayed 560-sweep pilot, including the passing quality result and
exact class/physical response metrics. The call includes its normal internal proof/audit work; no additional poker
replay or training call was run outside it. The temporary Windows execution-state request
and CPU/wall observations do not establish exclusive CPU access.

The following are the seven **root** intervals. Their nested children are kept
in the 21-event ledger and are not added again:

| Root phase | Inclusive wall seconds | Inclusive process CPU seconds |
| --- | --- | --- |
| `compact.publication.verify` | 89.552585 | 87.984375 |
| `proof.build_model` | 6.945471 | 6.171875 |
| `base._training_inputs` | 4.135290 | 3.921875 |
| `cfr_plus.train` | 46.553740 | 43.109375 |
| `policy.canonicalize_binary_rows` | 0.023548 | 0.015625 |
| `proof.lift_policy` | 4.344285 | 4.281250 |
| `proof.audit_policy` | 20.418856 | 19.484375 |

Root intervals total 171.973775 s; 0.908186 s of the whole
measurement lies outside those selected boundaries. Publication verification
occupies about 51.8% of this one observed call,
versus 26.9% for training. This locates cost in this research entry;
it does not establish a general solver bottleneck or imply that verification
can be removed from the correctness evidence.

The [complete index](../benchmarks/results/flop-class-phase-profile-v1/index.json)
pins source/protocol identities, all nested events, wall/CPU/UTC observations,
helper metadata and the losslessly saved policy. Its raw SHA-256 is
`ec839f707af9c03ec1247d4df25f8c6675901b0823f93b19fcb1390e31fea7a4` and canonical index SHA-256 is
`58a39f78e9f8f3e18ae91d9e5538369bd259ea962a742c860623b174641e8f8f`.

The next architecture decision should distinguish reusable verified preparation
from training and independent policy validation. Any proposed reuse path needs
separate admission, input/provenance validation, unchanged physical policy
checks and measured complete calls; this profile implements no such path.


## Saved publication verification

The immutable verifier authenticates the raw and canonical index identities,
frozen source revision, full request admission, parent/event structure, helper
metadata and the raw/gzip policy against the independently replayed compact
pilot. It reauthenticates payloads and the full current source snapshot afterward.
It reads saved evidence without training or physical replay:

```sh
python -B -m scripts.verify_flop_class_phase_profile_publication
```

Synthetic checks cover index tampering, malformed and closed-parent events,
wrong policy semantics, mutation during verification and current-source drift.
