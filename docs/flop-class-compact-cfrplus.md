# Explicit compact-work fixed-flop CFR+

This separate research entry trains the same independently proved weighted
`2c3d4h` flop game under a new opt-in named-loop forecast. The
[140-sweep adapter and preserved miss](flop-class-cfrplus.md), all its measured
executable sources, production APIs and shared kernels remain unchanged.
Nothing here generalizes the quotient to another game.

## Why a separate envelope

The original adapter deliberately retains its 3-million physical-world and
30-million physical-decision/world proxies. Its 140-sweep pilot has NashConv
`0.012537880082162792`, missing `0.005`. Compact training actually traverses 126
class worlds and stores 466 private information sets. A separate envelope can
charge those loops explicitly while retaining bounded physical preparation and
unrestricted physical diagnostics. The old proxy is reported as informational
in this new mode; the legacy entry still enforces its original guards.

[scripts/flop_class_compact_budget.py](../scripts/flop_class_compact_budget.py)
authenticates both unchanged shared-kernel LF hashes before returning a
forecast. It rejects noninteger requests and bools, admits at most 560 sweeps,
and caps the named training plus setup/output work at 76,000,000 units. At the
ceiling it charges 75,046,160 training units plus 61,670 fixed units, totaling
75,107,830. This policy ceiling was selected before the 560-sweep pilot; it is
not a promise that the quality target will pass.

For each pass, `B = 126 * 33` bounds all visited nodes across the worlds.
Decision and terminal work use this conservative bound. Every sweep charges
three world loops and callbacks, node/key dispatch, action and deterministic
chance recursion (`2D+C <= 2S`), two regret traversals' utility/action work,
terminal contribution reads, owner regret action updates, own-reach average
updates, delta-key scans and zeroed slots, regret clipping, and three profile
matching passes. Fixed counters name input/array setup and final policy work.
The source lists each coefficient and its sum rather than treating a world
iteration as a uniform hardware operation.

The checked model retains 1,001 compact public states, 316 binary public
decisions, 632 public action edges and 1,000 total edges including chance.
Its private information sets have 932 action slots and an exact 232/234 player
row split. Validate these dimensions and the maximum 33-state world traversal
before training. Storage bookkeeping lists numeric slots and a temporary row
allowance; it excludes object headers, references, proof/rebuild objects and
other interpreter memory. It is not a total allocation or RSS bound.

Physical preparation/replay references remain separate: 5,940 physical worlds,
30,812 public states, 16,912 policy rows and 33,824 action slots. The new logical
sum does not count every proof or rational-arithmetic operation; unchanged
physical/model validation and exact-diagnostic guards still apply. Changes to
kernel loops, source pins, actions, chance structure, dimensions or numeric
recurrence require a new reviewed envelope; no wider model follows from this
fixed one.

## Policy and independent evidence boundary

[scripts/flop_class_compact_cfrplus.py](../scripts/flop_class_compact_cfrplus.py)
is a separate explicit entry. It authenticates the old pilot miss and freshly
replays the four quotient controls. Training uses the same joint masses,
own-hand/public-history keys, zero delay and unchanged alternating CFR+
recurrence. All raw compact averages are retained before the same audited
`2^-52` output-grid normalization. Lift and unrestricted physical own-hand
responses use the existing independent oracle under forbidden-production guards.

[scripts/verify_flop_class_compact_cfrplus.py](../scripts/verify_flop_class_compact_cfrplus.py)
reconstructs this request/model and all physical response metrics without
retraining. The lower-budget historical verifier remains literal and usable.
No external implementation or dependency is incorporated; this reuses the
project's independently implemented methods and existing proof. See
[commercial/provenance limits](research/LICENSING.md).

## Preregistered pilot

The [protocol](../benchmarks/flop-class-compact-cfrplus-pilot-v1.json) fixes one
560-sweep call, zero delay and exact `1/200` NashConv target. Keep every output,
including a miss. It makes no runtime or memory measurement; those need a
separate protocol with complete calls and separate allocation traces.

```powershell
python -B -m scripts.flop_class_compact_cfrplus --iterations 560 --output <new-report.json>
python -B -m scripts.verify_flop_class_compact_cfrplus <new-report.json>
```

## Completed finite-game quality pilot

The [complete policy](../benchmarks/results/flop-class-compact-cfrplus-pilot-v1.json)
retains all 466 raw compact averages and 16,912 physical policy rows. At 560
sweeps, exact NashConv is `0.0028924005277596834`, passing the preregistered
`0.005` gate. All eight class/unrestricted physical response metrics agree
exactly, and the maximum independent numeric gap is `1.1687699419393738e-15`.
Independent saved-policy replay completed with zero training calls, rebuilding
the four proof controls and checking the physical policy again.

Output normalization changes 256 rows by binary64 bits, with no positive
probability rounded to zero. Maximum exact-normalized distance is `2^-53`;
maximum raw-input distance is `2^-52`. The quality and exact response claims
apply to that normalized output. All old target misses, including the
140-sweep compact pilot, remain preserved. This one finite-game pass is not
a general convergence or unrestricted NLHE result.

The [execution receipt](../benchmarks/results/flop-class-compact-cfrplus-pilot-v1-execution.json)
records the clean source checkpoint `365b0136ea9a571e4303bdac156ba002d027cc0c`,
one completed training call, no restarted training, unchanged executable/protocol
hashes, the 75,107,830 admitted logical units and the zero-training saved replay.
No timing, allocation or RSS comparison was taken in that quality pilot.

The raw artifact has 6,160,106 bytes and SHA-256
`44e4e3a70713d0b7c69e8a20845c66478febe60db8dad854a43c8ecc302e3b4e`;
its unsigned canonical report SHA-256 is
`982e90ea073b1dfefa65662945c9b8178683bc4079ca5a9ae0af3a0d5f9c4334`.
Publication completed in [merged PR #202](https://github.com/ajpaulson18-design/openpoker-lab/pull/202).
Both push and pull-request full suites passed on Python 3.11, 3.12 and 3.13.
The separate [completed call-cost study](flop-class-call-cost.md) now records
runtime and Python allocation observations, with both budget outcomes retained.

The [immutable publication verifier](../scripts/verify_flop_class_compact_cfrplus_publication.py)
pins both raw and canonical report hashes, the passing result and older miss
before generic replay, then authenticates raw bytes again afterward. Its mocked
replay control and all compact-mode focused checks passed: 20 tests.

```powershell
python -B -m scripts.verify_flop_class_compact_cfrplus_publication
```
