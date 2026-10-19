# Explicit native training for prepared fixed-street games

The [prepared-call profile](fixed-street-profile.md) measured training at over
99.8% of complete call time in two existing games. This optional backend moves
only training into a separately built project-owned C11 executable. Python
retains prepared-table validation, betting rules, serialized private-information
policies, profile evaluation and exact own-hand best responses. Existing Python
paths, payloads and admission remain the default/reference.

## Supported calls and explicit build

From a source checkout with an installed compiler, build outside the checkout:

```text
python -m scripts.build_native_train --output-dir ../native-train
```

Windows requires an x64 MSVC developer environment; POSIX requires `cc`. No
compiler is installed, build started or fallback selected by a solve. Build
failures and stale source/executable identities fail explicitly. No compiled
binary is committed or distributed by this change. Toolchain/runtime packaging
clearance remains separate, as in [native equity preparation](native-preflop-equity.md).

```python
from pokerlab.preflop_checkdown_solver import solve_prepared_preflop_checkdown
from pokerlab.flop_checkdown_solver import solve_prepared_flop_checkdown

preflop = solve_prepared_preflop_checkdown(
    preflop_equities, world_indexing="pair-mean", resource_model="prepared-counts",
    training_backend="native", build_directory="../native-train")
flop = solve_prepared_flop_checkdown(
    flop_equities, training_backend="native", build_directory="../native-train")
```

The preflop API also supports its original categorical world indexing. Its
native result adds `training_backend` and `native_training`. A native fixed-flop
result changes `execution_backend` and adds `native_training`; its original
physical/category census remains intact. Native metadata records the separate
trainer world census. Both APIs retain their existing strategy/model versions,
physical counts, action descriptions and Python diagnostics. No later-street
betting, selected-outcome API, server route or frontend changes follow.

Fixed flop integrates category mass and signed mass per private pair in both
its Python trainer and the revised compiled public-batched trainer. It transports
signed mass directly, retains zero means and separate hidden opponent hands,
and aggregates hidden opponents before subtracting each own-hand regret.
Preflop retains the scalar traversal. Bitwise policy equality across compilers
and Python versions is not promised; declared finite tolerances remain required.

## Training and information boundary

The [C source](../native/fixed_street_train.c) receives a finite public tree,
affine terminal utility `constant + coefficient * sign`, and weighted hidden
private-pair worlds. At each decision it indexes a policy only by public node
and the acting player's own dense hand ID. It cannot index policy by opponent
hand or hidden sign. Python restores the original own-hand/public-history keys.
Fold constants and showdown coefficients use initial pot/2 plus matched wagers,
returning unmatched excess. Preflop uses an initial pot of zero.

Vanilla CFR and DCFR freeze the full start-of-sweep profile and aggregate world
deltas before updating regrets. Regrets use opponent reach; averaging uses own
reach. DCFR retains quadratic iteration weights and the existing positive and
nonpositive discount rules. CFR+ updates/clips player 0, rematches, updates/clips
player 1, rematches, then averages the completed profile once with linear weight.
Zero positive regret and zero cumulative average mass use the uniform policy.

## Admission and protocol

Historical solver admission is still mandatory. Preflop additionally forecasts
native work before tree construction. Fixed flop admits native work after its
bounded tree census and before pair collapse, flattening or process lookup.
Complete-solve admission retains every historical source/setup/diagnostic charge
and replaces only the Python training envelope with native training plus adapter
bookkeeping; its ceiling remains 500 million modeled loop entries.

The [adapter](../pokerlab/native_fixed_street.py) independently reserves all
flattened tree/world/policy buffers and the full requested training work before
launch. A rooted arborescence has exactly N-1 action edges. Scalar training
reserves eight world-state units per traversal. Public-batched training reserves
`8N + 4WN + 12(H0+H1)N` units per traversal, with N public states, W pair rows
and H0/H1 active hand counts. CFR+ reserves three traversals per sweep; vanilla
and DCFR reserve one. Twenty-four slot units per sweep cover profiles, resets
and regret updates. The public-batched heap envelope additionally reserves
`33 * (H0+H1) * 16 * 8 + 2 * (H0+H1) * 8` bytes for depth scratch and hand
vectors. Separate setup
and Python adapter reserves are included. These are explicit loop/element
models, excluding internal library/compiler/OS instructions, not bytecode,
runtime or RSS guarantees.

Native-specific ceilings are 250,000 public states, 384 world rows, 128 active
hands per player, 12 actions, depth 32, one million action slots, 8 MiB request,
24 MiB response and 64 MiB modeled native working allocation. The Python wire
and allocation forecasts are conservative and may reject smaller actual inputs.
Python poker terminal units and each native affine constant/coefficient are
at most 1e12 chips. Existing tighter poker
pair/ranking/tree caps remain. Native working allocation includes the full input
buffer, C structs, validation scratch, four double slot arrays and a margin;
Python allocations, linked runtime/library storage and process RSS are separate.

The ASCII `OPENPOKER_FIXED_TRAIN_V1` protocol uses strict decimal integer fields
and exactly sixteen lowercase hexadecimal IEEE binary64 bits per float. Records
cannot spill fields across lines. Children have larger IDs and exactly one
parent, except root; the complete tree, masses, signs and declared slot census
are validated before training/output. Full requested work and working storage
are checked before C heap allocation. Malformed, truncated, oversized, nonfinite,
NUL-containing or trailing input fails with nonzero status and no policy output.
Python checks output shape, finiteness, row normalization and source/executable/
manifest identities before returning a policy. Identities are not authentication
of untrusted binaries or physical counts.

## Evidence and provenance

The source is independently implemented for this repository from its existing
Python algorithms and published mathematical methods: [CFR+](https://arxiv.org/abs/1407.5042)
and [discounted regret minimization](https://ojs.aaai.org/index.php/AAAI/article/view/4007).
No third-party implementation or runtime dependency is incorporated. The
[builder](../scripts/build_native_train.py) records source raw/LF hashes, compiler
banner, exact flags, executable hash, protocol and work-model identity. It uses
strict floating-point settings and no fast-math option.

Focused MSVC validation passes all three algorithms at 10/100/1000 iterations
on weighted and refund trees, manual policy anchors, malformed protocol cases,
and independent physical-count replay through both prepared solvers. Default
omitted/explicit Python payloads match. The later sections retain the initial
failed experiment and the revised paired complete-call measurements. Python
allocation traces do not establish native child memory or RSS.

The frozen [benchmark specification](../benchmarks/native-fixed-street-v1.json)
compares three complete calls per backend on six profiles: preflop vanilla/DCFR
at 8k and CFR+ at 3k; fixed flop all three algorithms at 4k. It declares scalar
agreement 1e-8, policy agreement 1e-6, independent replay 1e-10 and an observed
median ratio threshold of 1.5. CFR+ NashConv must meet 0.005 plus 1e-10 padding;
other algorithms' quality targets are recorded, including any misses. Separate
1k preflop allocation traces are excluded from timing medians. The
[runner](../scripts/benchmark_native_fixed_street.py) retains raw observations
and requires all admissions before build lookup, clean committed source and
unchanged build/source identities. Initial and followup measurements are
recorded below.

Windows input hardening also applies to the existing native equity helper.
A reproduced text-mode Ctrl+Z request accepted a valid prefix while ignoring
trailing bytes. Both helpers now select binary stdin/stdout before parsing, and
regressions cover Ctrl+Z with trailing input and valid CRLF records. This changes
protocol byte handling; card ranking, physical counts and strategy rules remain
unchanged. Existing build manifests require an explicit rebuild after source
changes. Both refreshed helpers pass their focused conformance tests.

## Initial six-profile result: policy compatibility remains open

The [initial report](../benchmarks/results/native-fixed-street-v1-initial.json)
retains all 36 paired timed calls and two separate allocation calls from clean
source `59551ea5792d76fb7db1ba70b8d7d28c15ffb483`. Source and build snapshots
match before/after. Its overall status is **error**, with three repeated misses
of the frozen fixed-flop DCFR policy tolerance. The maximum probability difference
is 1.1611351929952107e-6 against a declared 1e-6 gate. Scalar differences for that
profile remain below 7.98e-11 chips and both independently replayed policies meet
the 0.005 NashConv target. The gate is unchanged; this experiment is not yet
qualified for merge as the proposed complete six-profile backend.

| Profile | Python median seconds | Native median seconds | Observed ratio |
| --- | --- | --- | --- |
| Preflop vanilla 8k | 3.379034 | 0.046638 | 72.45 |
| Preflop DCFR 8k | 3.474603 | 0.061344 | 56.64 |
| Preflop CFR+ 3k | 2.218749 | 0.056410 | 39.33 |
| Flop vanilla 4k | 15.173558 | 0.391529 | 38.75 |
| Flop DCFR 4k | 16.539162 | 0.396431 | 41.72 |
| Flop CFR+ 4k | 21.956447 | 0.648678 | 33.85 |

Every speed gate passes in this run, all repeated payloads are deterministic,
and both pinned Python CFR+ payloads exactly match the earlier profile report.
All independent policy replays pass. Five profiles meet the declared cross-backend
policy and scalar gates. Fixed-flop vanilla misses the 0.005 quality target in
both backends (NashConv approximately 0.03954255); this was retained under the
predeclared non-CFR+ reporting rule. The remaining five profiles meet that target.

Separate 1k preflop traces measured 62,767 Python bytes / 3.924454 seconds for
the Python backend and 318,330 Python bytes / 0.059786 seconds for the native
backend. Native child-process allocations and RSS are excluded. The native call
therefore uses more traced Python allocation in this fixture; no memory-saving
claim follows. These traced times are excluded from paired medians.

The complete initial artifact canonical SHA-256 is
`9a664e07658d79b649d0c161d11e9f659b0f33b3319ced4162bfa1a022ef7cac`.
The public-batched followup below keeps this initial report and its failed gate
intact. Independent replay of all 38 initial saved policies also passed.

## Public-batched reduction followup

The initial scalar flop experiment evaluated mathematically equivalent pair
updates in a different binary64 order. No equation or information-boundary defect
was found in source review. The revised C path follows the public Python
trainer's hand-vector reduction order, preserving represented signed masses
without dividing and multiplying them again. Pair/marginal accumulation and
average updates retain ordinary ordered additions; action expectations, positive
regret normalization and final average normalization use an independently written
compensated sum. This draws on
[Neumaier's summation analysis](https://doi.org/10.1002/zamm.19740540106) and the
[documented Python 3.12 floating sum change](https://docs.python.org/3.12/library/functions.html#sum).
No external implementation is copied or added as a dependency.

The wire/build protocol is `OPENPOKER_FIXED_TRAIN_V2`, with mode 0 for scalar
signed equity and mode 1 for public-batched signed mass. The manifest uses
`native-fixed-street-work-v2`. The stable engine family remains
`native-fixed-street-v1` in result metadata; `reduction`, the build protocol and
work model identify the actual execution. Old V1 builds require an explicit
rebuild and are rejected by the revised adapter.

The [followup plan](../benchmarks/native-fixed-street-vector-v1.json) and
[runner](../scripts/benchmark_native_fixed_street_vector.py) pin the initial
failed artifact's Git blob and canonical checksum before and after measurement.
They reuse every original profile, repeat, timing boundary, quality target and
agreement gate. All 18 native timed policies plus its separate allocation policy
must identify their declared reduction and V2 build. The original report remains
unchanged. Local strict MSVC conformance and all-algorithm shared-hand checkpoint
tests pass at 1/2/3/10/100/1000 iterations. In a separate untimed 100-iteration
check on the full 8x8 fixture, all policy probabilities and eight diagnostics
match Python exactly for vanilla, DCFR and CFR+. These checks are not the frozen
4k complete-call experiment. Native conformance also passes on Windows and
Linux in GitHub CI.

## Revised six-profile result

The [followup report](../benchmarks/results/native-fixed-street-vector-v1.json)
passes every original gate from clean freeze
`09c8ff93fd4621d5923586e82c3ef6b4adafef6a`. All 441 captured LF source hashes,
source/build snapshots, 36 timed payloads and two allocation payloads are retained.
All three fixed-flop profiles match every Python policy probability and all eight
diagnostics exactly, resolving the initial DCFR policy mismatch. The maximum
preflop cross-backend policy gap is 2.02e-14 and scalar gap 8.89e-16, below the
unchanged 1e-6 / 1e-8 gates. Both pinned Python CFR+ payload hashes still match
the earlier profiling artifact.

| Profile | Python median seconds | Native median seconds | Observed ratio |
| --- | --- | --- | --- |
| Preflop vanilla 8k | 3.331243 | 0.063823 | 52.19 |
| Preflop DCFR 8k | 3.683323 | 0.035739 | 103.06 |
| Preflop CFR+ 3k | 2.609389 | 0.065021 | 40.13 |
| Flop vanilla 4k | 18.211265 | 0.199623 | 91.23 |
| Flop DCFR 4k | 18.894332 | 0.275348 | 68.62 |
| Flop CFR+ 4k | 25.062828 | 0.359260 | 69.76 |

No observation was removed. These are complete-call ratios on two finite
prepared games using Python 3.12.14 and strict MSVC 19.44 on the measured Windows
host, including process launch, Python diagnostics and canonical serialization.
They do not establish general speedup, convergence improvement or broader game
coverage. The largest native complete-solve reservation is 378,109,520 logical
entries, below the retained 500-million ceiling.

Independent replay of all 38 saved payloads against pinned physical counts and
numeric betting/own-hand response rules reproduces the stored metrics; guarded
ranking remains zero. Both CFR+ quality targets pass: preflop NashConv about
0.0000450742 and flop about 0.0001049110. Vanilla flop still misses the reported
0.005 target in both backends at 0.0395425569, retained under the original
non-CFR+ reporting rule. DCFR flop is 0.0034382814. Faster fixed-iteration execution
does not improve those policies by itself.

Separate 1k preflop traces measure 62,767 Python bytes / 4.715325 seconds for
Python and 318,585 Python bytes / 0.038618 seconds for native. Traced calls are
excluded from medians; child-process allocation and RSS are excluded from the
memory numbers. Native uses more traced Python allocation in this fixture.

The followup canonical SHA-256 is
`99007280279d577e01ca6764ec6b680a9ff491ce5d20ab44134ce1455f779773`.
Source LF SHA-256 is
`6929c78d336217a65d6fca9ec1c0d433b5a17fea439ee31020d200bf83eee4fa`;
measured executable SHA-256 is
`6f5573a8d24f645a3689ee3aeae05d09626677e88c518a8c71cbb327586265ef`.

After measurement, one unit-test negative branch was corrected to mock historical
Git retrieval in shallow CI checkouts. Solver, C source, runner, specification,
build and measured artifact were unchanged. The initial failing CI run is retained
in [PR #142](https://github.com/ajpaulson18-design/openpoker-lab/pull/142).
