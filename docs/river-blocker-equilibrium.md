# Blocker-correlated fixed river equilibrium and CFR+ audit

## Result and scope

This configured game has exact OOP equilibrium value **-43339/1751**
(about -24.7509994289 chips), with both exact unilateral gains and NashConv
equal to zero. The witness concerns one finite heads-up river abstraction.
Production solvers and earlier streets are unchanged. It establishes no
unrestricted Hold'em solution, decimal-intent equivalence or general speed/RSS
gain. Float projections are separately checked and need not have exactly zero
raw binary64 gap.

## Physical model and private information

Board: Js8d4c2h2s. OOP: AsAh:0.5,KsKh:1. IP: AsAd:1,KcKd:0.75.
Starting pot: 100 chips. Stacks: 220/120. Opening sizes: 0.33/0.75.
Raise sizes: 0.5/1.0. At most two raises; all-ins enabled.
The shared As forbids the AsAh/AsAd private pair.

| OOP / IP | Exact joint mass | Showdown sign |
| --- | ---: | ---: |
| AhAs / KcKd | 3/17 | +1 |
| KhKs / AdAs | 8/17 | -1 |
| KhKs / KcKd | 6/17 | 0 |

Raw compatible weights 3/8, 1, 3/4 total 17/8, then normalize globally.
OOP marginals are 3/17 and 14/17; IP marginals are 8/17 and 9/17.
Given IP KcKd, OOP is AhAs with probability 1/3 or KhKs with 2/3.
Given OOP KhKs, IP is AdAs with probability 4/7 or KcKd with 3/7.
Each ace hand forces the compatible opposing king hand. All joint, marginal
and conditional sums equal one.

Multiplying the conditioned marginals would put 24/289 on the impossible
shared-As pair; removing that pair afterward still gives the wrong joint
law. KK/KK ties: each player independently makes two pair, kings/deuces with
a jack kicker. Unknown opponent cards never create separate policy variables
or response choices. Each row uses only own hand and full public history.

## Independent reference and proof

Before candidate search, Sol froze a different sequence traversal and uniform
policy EV/legal responses in the [model reference](../benchmarks/results/river-blocker-model-v1.json).
Its 75,345 bytes have SHA256
f588431086eb0672985a58d52a4a01401db292526d4a88f0b97c56a3410e0f01.
Uniform V=-125149/8160, lower=-3475/51, upper=1755/136, NC=1945/24.

The confirmed census is 3 worlds, 51 public nodes, depth 6, 18 public decisions,
36 information sets, 49/53 sequence coordinates and 17/21 flow rows.
The [candidate](../scripts/river_blocker_equilibrium.py) specializes the
previous construction in a new file and reuses unchanged bounded LP and
policy helpers. The [independent verifier](../scripts/verify_river_blocker_equilibrium.py)
imports neither candidate/LP search nor the exact-policy evaluator.
It rebuilds every A/E/F coefficient with a different traversal, remaps
semantic labels, checks nonnegative realizations, all flows, dual slacks and
complementary slackness, then separately recurses own-hand legal responses.
Its checked objectives and profile satisfy L=V=U=-43339/1751.

The [previous two-game witnesses](river-sequence-equilibrium.md) and their
pinned sources/tests stay untouched. Source/input/HEAD guards remain active
under optimization. Historical generation commits need not exist in a shallow
verifying checkout; source pins tolerate ordinary LF/CRLF differences.
Unrelated historical training inventory does not replace pinned current
mathematical-source checks.

LP limits remain 96 rows, 256 columns, 25,000 tableau cells including RHS and
objective, 512 pivots, 10,000,000 logical updates and 4,096 accepted Fraction
bits. Exact policy replay retains 100,000 work, depth 64 and 65,536 Fraction
bits. These are logical search/admission bounds, not CPU, elapsed time,
allocation or RSS bounds. Lower/upper LPs used 161/173 pivots and
2,534,485/2,620,273 logical updates.

## Finite-iteration evidence

The separate [CFR+ audit](../scripts/river_blocker_profiles.py) preserves all six
predeclared complete profiles. It independently replays float diagnostics,
exactly normalizes the serialized binary64 rows, and checks the proved value
inside every exact legal-response interval. Every 0.001-chip target miss
remains recorded. Normalized exact gaps differ from raw binary64 diagnostics.

| Backend | Fixed sweeps | Exact normalized NC shown as float | NC <=0.001 |
| --- | ---: | ---: | --- |
| materialized | 1000 | 0.00745115803857 | False |
| materialized | 3000 | 0.000888199705168 | True |
| materialized | 10000 | 0.000200344289729 | True |
| matrix-free | 1000 | 0.00745115803857 | False |
| matrix-free | 3000 | 0.000888199705165 | True |
| matrix-free | 10000 | 0.000200344289722 | True |

Saved verification never trains. It freshly checks complete float-oracle data,
all eight exact metrics, normalization ledgers/rows, counters, threshold
outcomes and complete policy hashes. File limits and before/after source,
HEAD, witness, report and policy snapshots reject changed inputs.
Generation verifies a candidate before replacing its report and refuses
to overwrite a differing saved policy.

Timings are single complete solve-plus-JSON and separate replay observations
on a shared host. They establish no general speed, memory, RSS or convergence
improvement.

## Reproduction and executed evidence

    python -m scripts.river_blocker_equilibrium
    python -m scripts.river_blocker_profiles
    python -m scripts.verify_river_blocker_equilibrium
    python -m scripts.river_blocker_profiles --verify
    python -m unittest tests.test_river_blocker_equilibrium tests.test_river_blocker_profiles tests.test_river_sequence_form -v
    python -O -m unittest tests.test_river_blocker_equilibrium tests.test_river_blocker_profiles -v
    python -m scripts.validate_docs

Normal tests: 45 passed (38.335s complete process).
Optimized tests: 29 passed (26.407s complete process).
Untouched witnesses/profiles are positively verified before adversarial cases.
Tests cover chance law/factorization, A/E/F tampering, primal/dual/flow data,
hidden-opponent row splitting, false zero metrics, normalization, grid
completeness, source/threshold forgery, input drift and file limits.

The [equilibrium artifact](../benchmarks/results/river-blocker-equilibrium-v1.json)
has 332183 bytes, SHA256 98f8ec6a0a6c9ae08783dfbdc56758ff396af38fe21298d4090e4d5f6aa00f9f.
The [six-profile report](../benchmarks/results/river-blocker-profiles-v1.json)
has 616653 bytes, SHA256 d7e4eefc16e62da71f7606ee51fe277d5388536525fae3ff303c2ddfbf6751f9.

Sol specified/reviewed the chance law, independent reference and proof
acceptance, rejecting incorrect normalization and an early profile/witness
path collision. Luna drafted bounded chance-law tests and the profile
generator/replayer without tool execution. Sol integrated, corrected input
guards and executed the recorded checks. No Luna execution is implied.

Limits remain tiny synthetic private supports and a finite configured
binary64 tree. Broad-range/turn validation, generic convergence, rank changes,
production equilibrium APIs and earlier-street expansion are outside this slice.
