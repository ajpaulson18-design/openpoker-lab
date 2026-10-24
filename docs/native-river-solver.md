# Explicit native CFR+ for configured river games

The separate research API `pokerlab.native_river_solver.solve_native_river`
uses the existing source-built fixed-street trainer for a complete five-card
board. Python retains range parsing, blockers, rank signs, the public betting
tree, physical information rows, serialization and visible-information best
responses. Existing solver entry points and defaults are unchanged.

`solve_native_river(board, oop_range, ip_range, config=None, *, iterations=1000,
build_directory=...)` requires an explicit build directory and integer T from
10 through 10,000. It neither compiles nor selects a fallback. Build explicitly
outside the checkout with `python -m scripts.build_native_train --output-dir
../native-train`, as described in [native training](native-fixed-street.md).
The builder records C source, compiler/flags and executable hashes; stale source,
changed executables and subprocess errors fail explicitly.

## Training and information boundary

For each original physical world `(h0,h1,mass,sign)`, the adapter sends
`(h0,h1,mass,mass*sign)` to public-batched native training. Original physical
worlds remain intact for Python diagnostics. Native information keys use actor,
own hand and public history. The returned `postflop-strategy-v1` rows retain
every literal hand, board, public action amount, raise-to value and history token.
The distinct solver version is `research-native-river-cfrplus-v1`.

Each CFR+ sweep updates/clips/rematches OOP, then IP, then averages the completed
profile once with original weight t, own sequence reach and joint hand marginal.
This API has D=0, source window 1..T, average weight T(T+1)/2, 2T regret passes
and T average passes. It offers no target stopping or tail/discard option. The
native trainer's 10,000-sweep cap remains; the separately published
[50,000-sweep Python tails](river-heldout-tail-results.md) are unchanged.

## Admission

Every historical river guard still charges the full requested T: 3,000,000
candidate-hand products and world iterations; 30,000,000 world-node and dense
hand-state-pass work; 1,000,000 action slots; 250,000 prefix edges and public
states; 10,000 public decisions. Dense admission retains 3T+3 including the
three diagnostic passes. Counts and resource usage are disclosed in the result.

The existing native admission applies additionally: at most 384 worlds, 128
active hands per player, depth 32, 12 actions per decision, 8 MiB input, 24 MiB
output, 64 MiB modeled native heap and 500,000,000 modeled native loop entries.
Tree/terminal shape, complete information rows, full training admission and
source-built identities are checked before process launch. Neither historical
nor native caps are raised. This first adapter therefore does not expand the
historically admitted games or iteration budgets.

Native and historical admissions remain separate; no new combined complete-call
work bound is claimed. Native loop/heap reservations are structural models,
not measured runtime, Python allocation or process RSS bounds. Actual Python
value and best-response diagnostics follow training and remain outside the
native training envelope.

## Executed validation and scope

With an explicitly rebuilt x64 MSVC executable, seven admission/serialization
tests and three compiled control tests passed (10 tests, 2.394s). The controls
compare complete policies at 1e-9 and all eight metrics at 1e-8 against Python
D=0 for T10/T100 on both original weighted 4x4 river games, a weighted 8x8 game,
and an all-tied royal-flush board. Each saved/reloaded native policy is replayed
using independent physical cards, numeric rules and exact normalized-binary64
scan/partition audits under unchanged caps. All eight independent metrics agree
within 1e-9; production solve/tree/trainer/evaluator entry points are disabled
during that replay.

The royal-flush board has separately known equilibrium value zero: either
player guarantees zero by checking/calling and never folding. Its independent
exact response intervals contain zero at both tested budgets. This does not
claim the finite trained policies have zero gap. Weighted blockers, ties, raises,
short unequal-stack all-ins and unmatched refunds are included. The direct
native trainer/client's 11 existing conformance checks also passed (3.461s).
Compiled river tests run only with `OPENPOKER_NATIVE_TRAIN_BUILD_DIR` set to an
explicit build and are included in the Linux/Windows native conformance job.

These bounded controls establish integration correctness for the tested games;
they establish no accuracy target for new ranges, general convergence, controlled
speed or memory gain, TURN support or GTO Wizard quality. Wider range coverage
and a source-derived scaling model remain separate work.


## Retained paired compiled controls

A separate fixed control batch completed once from clean published source
`e537ec82b756b3e69d87a3b4f574d7eda8becc4f` under claim
`29f643a2201dd16cf93a6fbba487a362`. Its
[complete report](../benchmarks/results/native-river-controls-v1/report.json),
[exclusive claim](../benchmarks/results/native-river-controls-v1/claim.json),
[terminal status](../benchmarks/results/native-river-controls-v1/status.json),
[byte index](../benchmarks/results/native-river-controls-v1/index.json) and
[runner](../benchmarks/results/native-river-controls-v1/validate_compiled_river.py)
retain all 16 complete Python/native policy returns. All 77 committed
Python/C/helper identities, the external runner bytes, compiler/build manifest
and executable hashes stayed stable. No compiled binary is distributed.

The eight paired profiles cover both original 4x4 games, a separate weighted
8x8 game on `AhKdQcJs2d` with pot 17.3, stacks 29.1/11.2 and 0.33 bet/raise
fractions, and a royal-flush tied-board anchor, each at T10 and T100. On this
recorded MSVC build, every native/Python policy probability and all eight
independent numeric metric deltas are exactly zero in the serialized binary64
values. This observation does not promise bitwise agreement on other compilers
or at larger budgets; the declared 1e-9 policy and 1e-8 metric tolerances remain.

All 16 saved policies pass independent physical numeric and exact scan/partition
audits. Fatal production solve/tree/training/evaluation/rank tripwires observed
zero calls during each independent replay. Both trained tied-board profiles
retain exact response intervals containing the separately known game value zero.
The complete raw rows and audit fractions, including every finite-budget gap,
are preserved. This is correctness evidence; no target attainment, runtime ratio
or memory claim is inferred from these short controls.
