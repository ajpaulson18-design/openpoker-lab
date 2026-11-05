# Prepared chance and persistent exact training state

The [fixed-profile proof](virtual-frozen-update-study.md) passed independent
saved review for PROOF9/v1. These components now support the
[verified two-sweep trainer](native-dyadic-two-sweep.md) for that finite game.

The earlier public-chance and history owners are useful component boundaries,
but their complete-game accounting cannot be multiplied across training. For
two exhaustive iterations with two target seats, the old exact terminal API
requires at least 500,838,144 logical units for river terminals alone. The
older history interner needs at least 456,225,792 logical units for the necessary
decision cursors alone. The [resource derivation and control archive](../benchmarks/results/native-dyadic-state-and-chance-v1/manifest.json)
retain both calculations and the exact source inputs. Neither ceiling was lifted.

`PreparedPublicChance` captures the validated immutable hand rows and normalized
integer prior. Exact powers of two cancel from both range factors and the shared
normalizer, preserving the global law. It returns unscaled integer contractions
and the chance divisor/reach exponent. Visible-prefix folds need no ranker. A
bounded cache holds up to 64 ordered-board rank planes with original holding
indices; it contains no private pair matrix, reach, payoff or world coefficients.
On a miss, rank all unblocked rows regardless of current reach. On a hit, reuse
the ranks and repeat only dynamic blocker/rank mass arithmetic. Validate every
opponent numerator, including blocked ones, against its common power of two.
Constructor, cache and arithmetic charges share one owner. The parent supplies
signed money and the fixed game scale, and admits any retained query outputs.

`History` snapshots 1,105 literal symbolic path occurrences for the reference
template. A key combines the literal occurrence ordinal with the complete ordered
visible prefix. Several histories may use the same numeric betting state, but
their keys stay distinct. The snapshot copies token and edge data once for each
symbolic path, independent of physical board count. Cursors validate a live
owner and generation. No hidden future card enters a key.

`State` owns packed legal menus, cumulative regrets and raw average masses for
one fixed denominator. It freezes one current policy across both target passes
of a simultaneous CFR+ sweep. Staging checks the exact mixed value on that
denominator, clips accumulated regrets at zero and accumulates nonnegative raw
average increments. It commits only after all registered rows are staged once.
Average export retains the raw masses and produces a distinct grid policy. The
enclosing trainer authenticates row menus and prior support, and admits the state
and its one cumulative quantizer together with all other work and storage.

The fixed trainer stores one ordered action menu per registered card-free
template node. The state owner copies each menu on first use and checks all
ordered token bytes on reuse. Every physical history and original holding
retains its own row and numerical offsets. The generic state interface still
owns a copy per row for callers that supply their own legal menus. Admission
continues to reserve the original conservative per-row storage and work.

The opt-in paired packed-average path stores a committed and staged limb array.
For an actor's `d` decisions through the current action, every average increment
has a factor `2^(625 - 52*d)` in this fixture. The reach exponent is at most
`52*(d - 1)` before that action. Each literal path carries its own depth across
reveals, and the sweep checks the shift against the registered row. Different
histories can share a menu and require different shifts. Registration admits
the full limb census before allocation. Staging rejects nondivisible inputs and
sum overflow before a sweep can commit.

Checkpoint output and final quantization decode exact numerators one row at a
time. The packed trainer exports policy units and uniform flags directly after
its full checkpoint, avoiding a third dense mass array. The generic State API
continues to return its dense raw masses. Packed admission counts the two limb
arrays, row metadata and bounded scratch, and precharges conversion work inside
the existing parent work cap.

The compact strategy profile packs both regrets and average masses. Let `H`
be the full decision horizon, `o` the number of opponent actions before a row,
and `t` the longest continuation measured in decisions including that row.
The fixed denominator carries `52*H` bits beyond the terminal money scale.
The opponent prefix and the continuation can consume at most `52*(o+t)` bits.
Action values and their mixed value therefore share the factor
`2^(52*(H-o-t))`. Subtraction, cumulative addition, and clipping at zero
preserve it. The trainer recomputes each row's shift during routing and checks
divisibility and width when staging the signed update.

The same quantizer can consume the compact values directly because a common
positive row factor preserves both the action ratios and zero support. The
checkpoint reconstructs the original numerators in the same order. Admission
reserves committed and staged limbs for each field and charges the compact
codec before training. This mode gives the parent the remainder after reserving
the other components under the existing 500-million-unit total. Earlier modes
retain their original 115-million-unit parent ceiling.

Strict MSVC builds and independent checks passed normally and optimized:
67,548 prepared contractions and cache/owner guards; 5,525 literal path records
over five ordered board variants and 14 rejection guards; and 24 synthetic
row updates over two sweeps and three widths, with 27 rejection guards. The
first state control build hit a test identifier collision under strict compiler
warnings. The archive retains that failure and the corrected build. These are
component results, including exact policy feedback on synthetic rows.

The first optimized Linux history build stopped at the deliberately invalid
edge-index control. Its compiler could not infer the constructor's array bound
from the stored menu count. The action path now checks the fixed array extent
explicitly before access, as well as phase and menu width. Both affected MSVC
control suites passed again normally and optimized. The
[portability receipt](../benchmarks/results/native-dyadic-history-guard-v1/manifest.json)
retains the Linux failure and fresh Windows evidence; final CI is separate.

## First whole-game plan

The [fixed two-sweep driver](native-dyadic-two-sweep.md) implements this
composition. Its corrected admission counts hidden all-in completions and has
passed; the design model below is retained as the earlier forecast, and does
not substitute for the executed admission or the saved training replay.

The rank-free source census gives 24,420 rows, 58,164 slots, 16,631 fold and
17,356 showdown occurrences per target pass on the same declared game. Its
maximum 12 decisions and reduced exact matched-payoff shift of one bit give
`D = 580 * 2^(52*12+1)`. The first uniform grid uses at most 420 effective
reach bits on a full path. Use per-literal-path bounds when reserving T2 current
quantization and final average quantization: own past reach is absent from
counterfactual values, and the raw average uses only own past and current reach.

The first work model with repeated map lookups and full history token exports
exceeded the existing 500-million-work ceiling. Deterministic traversal can
instead consume the pre-registered row array in order, comparing each exact
history/actor/holding key, and export compact path/prefix keys with a replayable
literal skeleton. A second model includes the observed earlier template/prior
setup, one final average export and bounded binary output. It projects
471,158,660 modeled work and 22,662,720 output bytes for T2. This is a design
census: the actual native driver, strict whole-request admission and accounting
must establish these bounds against the implemented operations before training.
Preserve any admission or quality misses; no savings are measured yet.
