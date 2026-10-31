# Exact fold payoff classes

Status: development V5 candidate connected to the same native indexed
four-street trainer through explicit Python/native selection and a checked
fold-operator receipt. Frozen measurement and saved-only acceptance are pending. This is the next
computation boundary after the [active-frame result](native-active-frames-result.md),
whose logical capacity gain comes with a scoped T10 timing regression.

The [development evidence manifest](../benchmarks/results/native-fold-class-development-v1/manifest.json)
retains the research helper/receipt, expanded native controls, exact compiled
source closure and the 82-control default-path regression. Public acceptance
and committed-source performance measurement are separate future gates. That
immutable archive describes the original map-based internal prototype, not the
revised V5 source closure or its later 91-control integration.

Repeated terminal callbacks remain a measured cost. For fold payoffs, each hand
has a bit mask identifying its legal complete selected boards. Group opponent
hands with the same mask. For a selected-prefix index mask Q, own-hand mask A
and opponent-class mask B, `popcount(Q & A & B)` is the exact number of admitted
boards for every member of that class. A card bucket over weighted opponent
reaches computes compatible mass by total minus the two own-card buckets plus
the exact identical-hand correction. Multiply by own weight, board count and
payoff, and sum exact integers before the existing single binary64 conversion.
Keep the original global joint normalizer and SB/BB payoff sign.

The grouping stores per-hand masks and membership only; no private-pair
coefficient matrix or complete-world table is constructed. Distinct masks can
approach the hand count, so the implementation chooses class application only
when its conservative static loop forecast fits the original board-loop
allowance. Otherwise it executes the declared literal-board crossover. The
original profile remains default. Showdown ordering/ranking is unchanged.

The new class table has an explicit constructor work/storage reservation in
Kernel and Plan, before allocation. The candidate retains the full original
per-query allowance and scratch/integer/conversion limits. It takes no new
training-capacity credit from the loop reduction. Any later admission change
requires independently checked full-request execution and proof counters.
Logical entries and work are not allocator-byte, RSS or CPU guarantees.

Choose `native_payoffs="fold-mask-classes-v1"` with explicit source-built native
execution, indexed routing/admission, active frames and the existing compact
dyadic/equivariant/Q/per-decision configuration. Incomplete combinations reject
before source lookup or preparation. The default `"board-sweep"` preserves V1–V4
protocols and payload shape. V5 uses fixed-indexed active frames and appends one
ordered 17-field `FOLD\tmask-classes-v1` record after FRAME. It independently binds
mask/member/class counts, per-player class/literal calls, bucket/own-loop counts,
setup ownership and the unchanged combined work/entry ledger. Entered-call
counters are completed callbacks only when the whole native run succeeds;
rejected native processes have unknown internal progress.

Review exposed map-comparison work missing from the initial class crossover
estimate. The revised class path uses no map: deterministic 64-pass radix
grouping and a separate temporary 4,096-slot holding-key lookup produce a linear
per-hand identical-opponent index for blocker correction. The radix buffers die
before the lookup is constructed. Neither structure stores compatible private
pair coefficients. The original map-based literal crossover keeps its previous
accounting; this change does not claim to repair that separate legacy model.

For total hands H, boards B, opponent classes C and own/opponent hand counts A/O,
the revised reservations are:

| Stage | Logical reservation |
| --- | --- |
| Class setup work | 2048 H + 8 B H + 65536 |
| Class retained entries | 10 H + 128 |
| Constructor scratch | max(12 H + 512, 4224) |
| Class query work | C (64 A + 256) + 64 O + 8 Bprefix + 128 |

The setup envelope covers bounded 64-pass scans, mask construction, member
grouping and both 4,096-entry initializations. Query groups partition opponent
IDs, initialize only one fixed 53-integer bucket at a time and perform constant
identical-hand correction. Integer arithmetic calls are logical primitives with
the separate operand/payload limits still enforced. The class query is selected
only when this envelope fits the old `Bprefix (48 H + 512)` allowance. All old
query charges remain; no new capacity credit is inferred. Host proof reservation
separately includes mask construction, all-occurrence prefix scans and actual
logical history-token/byte bounds before that independent proof executes.

An external exact-Fraction research check compares the class algebra with a
bounded direct pair/board oracle on 48 seeded fixtures. It records 282 exact
vector matches and one zero-support fixture rejection, with shared physical
holdings, zero reaches, extreme dyadic weights, and board subsets. The oracle
enumerates bounded pairs solely for independent research; the class operator
stores none. This is not native timing or quality evidence.

Strict native development controls compare 192 callback pairs bit for bit,
including normal/subnormal payoff conversion outcomes, zero reaches, blocked
hands, identical holdings across roles, board subsets and literal crossover.
They separately test constructor/query storage and work rejection and unknown
mode rejection. Coupled G1 and noncommuting G6 public-history trainers preserve
all quotient-policy bits, member checks and active-frame cleanup while actually
entering the new fold class operator. The 64-board fixture includes ordered
turn/river branching and reconvergent public vertices. These remain conditional
C++ controls. Public V5/V4 development tests now also preserve five established
physical T10 policies/eight metrics with protected independent replay, physical
G6 and blind-all-in behavior, reject forged/missing/wrong-mode FOLD records,
and forbid Python/legacy training fallback.

The revised integrated suite passes 91 controls with assertions disabled
(178.006 seconds). Terra's fresh read-only review accepts the algebra, native
scratch lifetime separation and revised host proof minimums, distinguishing
source inspection from executed validation. Earlier worker quota limits remain
part of the development history; workers resumed for this integration.

The fixed measurement runner is `scripts.benchmark_native_fold_classes`. Its
34 scheduled children pair V4 board sweep and V5 classes under the same active
indexed trainer: six physical T10 fixtures, two additional alternating original
T10 pairs, original T40/T60, private-flush T100, four larger-range T10 fixtures,
and original T100/T1000. It saves process/native bytes before validation and
allows no retries or replacement fixtures. Authentication covers the entire
clean committed source and native build before project mathematics; capture,
source, build and policy bytes are checked around independent replay. A fresh
saved-only review remains a separate acceptance gate. Failed gates and verifier
capacity limits remain evidence. Timing medians describe only three original
T10 pairs, and parent Python memory excludes the native heap.
Twelve runner controls pass both normally and with assertions disabled. They
exercise real V4/V5-shaped records through parent validation, inherited T1000
schedule admission, strict counters and replay-gap rejection. Preflight review
corrected a derived-count/schema mismatch and the inherited schedule gate before
any formal producer attempt. Terra's final source review finds no further
concrete runner blocker; that is not saved-data acceptance.

Next gates: freeze and execute that schedule,
retain misses/rejections and independently review the source and saved results.
Full-deck law, strategy storage,
unrestricted convergence and larger-game certification remain unresolved.
