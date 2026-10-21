# Fixed-game flop class CFR+ research adapter

This opt-in research script trains only the exact weighted `2c3d4h` flop game
from the [public-chance proof](flop-public-classes.md). It uses the unchanged
project-owned alternating CFR+ kernel over 126 class worlds and 466 policy rows,
then restores all 16,912 physical rows. This is not a production solver API.

## Admission and numerical boundary

The complete request is admitted before source/proof reconstruction, ranking,
tree or training allocation. Exact integer iterations must be in `[1, 140]`.
Both historical physical reference guards remain: 3,000,000 world iterations
and 30,000,000 decision/world iterations, charging three passes per sweep and
12 physical decisions per world. At 140 sweeps these charges are 2,494,800 and
29,937,600. Compact training reserves 52,920 world iterations and at most
3,386,880 visited states (64 per world/pass); actual path sizes are checked
before training. These are logical counts, not runtime, byte or RSS bounds.
The independently validated model must retain every fixed census dimension.
No wider iteration cap follows from the smaller representation.

The kernel receives the original rational joint mass rounded once to binary64;
every positive class world must remain positive. It uses own-hand/public-history
keys and selects each public chance child from that world's class label. Hidden
opponent hands and future reveals are not information-set keys. Two alternating
regret passes precede one completed-profile own-reach linear average. This
adapter supports zero averaging delay only; the kernel remains unchanged.

The raw two-action average need not sum to exactly one as rational binary64
values. All 466 raw rows are retained. At the output boundary, divide by the
exact raw row sum, round the first probability to the nearest multiple of
`2^-52` with ties to even, then use its exact complement. Distance from the
exact normalized raw probability is at most `2^-53`. Report exact rational
maximum distances from both normalized and raw inputs, every changed row by
binary64 bits, and positive probabilities rounded to zero. This is an explicit
policy change; raw policies are not claimed bitwise identical or physically
audited before normalization. Chance masses are never normalized this way.

## Independent checks and provenance

Every complete call first reconstructs all four published proof controls. The
model is freshly built and validated under the existing forbidden-production
call guard; training runs outside that guard. Final lift and diagnostics run
under a fresh guard. The existing exact auditor requires equality of all eight
class and unrestricted physical own-hand response metrics and independently
replays numeric physical policies within `1e-10`. No pinned proof source or
shared training implementation is changed.

The [saved-policy verifier](../scripts/verify_flop_class_cfrplus.py) checks the
bounded JSON, duplicate fields and raw rows, checksum, executable source hashes,
full proof receipt, request, census, binary64 normalization/lift, physical
metrics and quality gate without retraining. It validates the saved policy and
its diagnostics; a saved policy alone cannot prove how training was executed.

No external source, dependency, proprietary output or new method implementation
is incorporated. The adapter reuses this repository's independently implemented
CFR+ kernel; the quotient and physical oracle remain the project-owned proof.
Source LF hashes and Python runtime identify each result. These facts do not
constitute patent or commercial clearance; see [licensing](research/LICENSING.md).
AI Coach/explanation and the independently owned turn workstream are separate.

## First pilot protocol and status

The [frozen pilot protocol](../benchmarks/flop-class-cfrplus-pilot-v1.json) fixes
140 sweeps, zero delay and an exact `1/200` NashConv gate before execution.
Retain every result and raw row, including a miss. It deliberately makes no
runtime, memory or old-policy parity comparison. All three historical
[alternating-study misses](flop-alternating-study.md) remain unchanged.
A later performance or higher-budget convergence study needs its own frozen
protocol and independent admission; this pilot does not authorize either.

Run from the repository root with a new output path:

```powershell
python -B -m scripts.flop_class_cfrplus --iterations 140 --output <new-report.json>
python -B -m scripts.verify_flop_class_cfrplus <new-report.json>
python -B -m unittest tests.test_flop_class_policy tests.test_flop_class_cfrplus -v
```

Pilot execution and publication are pending at the initial source checkpoint.
