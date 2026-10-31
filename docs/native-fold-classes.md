# Exact fold payoff classes

Status: development C++ candidate connected to the same native indexed
four-street trainer through an explicit internal Plan/Kernel parameter. The
public Python/native protocol does not select it yet. This is the next
computation boundary after the [active-frame result](native-active-frames-result.md),
whose logical capacity gain comes with a scoped T10 timing regression.

The [development evidence manifest](../benchmarks/results/native-fold-class-development-v1/manifest.json)
retains the research helper/receipt, expanded native controls, exact compiled
source closure and the 82-control default-path regression. Public acceptance
and committed-source performance measurement are separate future gates.

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
C++ controls, not the pending public API/whole-game physical acceptance.

Next gates: expose a versioned explicit whole-game selection and proof, bind
host/native ledgers, add physical-policy replay, freeze same-work measurements,
retain misses/rejections and independently review the source and saved results.
The team workers are usage-limited; root performs this development work and
does not imply fresh model-specific scrutiny. Full-deck law, strategy storage,
unrestricted convergence and larger-game certification remain unresolved.
