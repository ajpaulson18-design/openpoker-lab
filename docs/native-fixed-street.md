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

Fixed flop already integrates category mass and signed mass per private pair
in its Python vector trainer. The native scalar path integrates only that hidden
category, retaining full pair mass, zero means and separate hidden opponent
hands. Different scalar/vector summation orders may change binary64 policies;
bitwise cross-backend policy equality is not promised.

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
launch. A rooted arborescence has exactly N-1 action edges, so eight world-state
units per traversal conservatively cover node and action loops. Twenty-four
slot units per sweep cover profiles, resets and regret updates. Separate setup
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
omitted/explicit Python payloads match. Cross-platform CI and frozen paired
complete-call/runtime and Python-allocation measurements are pending. No native
speedup or memory saving has been established yet.
