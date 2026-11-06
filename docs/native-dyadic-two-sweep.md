# Fixed PROOF9 two-sweep training path

The explicit `virtual-dyadic-training` target joins the accepted
[fixed-profile proof](virtual-frozen-update-study.md) with the
[prepared chance, compact history and persistent state](native-dyadic-training-foundation.md).
It accepts only the pinned reduced nine-card game, exhaustive physical reveals
with q=1, and two simultaneous CFR+ sweeps. The committed cohort at `aa38559`
completed one training invocation and passed the independent replay of its saved
binary output. [Accepted evidence manifest](../benchmarks/results/native-dyadic-two-sweep-accepted-v1/manifest.json)

The driver visits all legal actions and prunes only a visible prefix with zero
physical prior support. Each target pass consumes the same exact ordered row
catalog, checking full history, global actor, original holding, and menu extent
before using a policy row. A frozen policy stays in force across both targets.
After both passes, the owner commits one complete regret and average update.
Average increments use only own past reach, own current action probability and
prior visible-prefix mass. Both sweeps have equal weight in this profile.

Early all-ins settle with no future decisions. The payoff routine streams their
remaining physically supported boards, adds the exact unscaled rank contractions,
and applies the fixed money stake and scale once. Those hidden completions never
become history tokens or strategy rows. The first rank-free admission correctly
rejected the earlier terminal forecast because it omitted these completions.
The corrected census has 17,356 visible showdown occurrences per target pass,
18,180 full-board showdown contractions and 22,168 hidden completion candidates.
It plans 140 hand ranks across 60 ordered-board planes; some unblocked holdings
have no compatible opponent on that board. No ranks ran during admission.

The complete planned workload is 473,271,268 named work units, 1,132,473
entries, 255,006,160 integer payload bits and exactly 22,587,756 output bytes.
These caps cover the declared implementation and fixture, with every owner and
parent work family separately bounded. They do not measure wall time or process
memory. The 500-million work ceiling, two-million entry ceiling, 65,536-bit
integer ceiling and `2^30`-bit payload ceiling are unchanged. The build-only and
`ADMIT` CI controls never launch `TRAIN`. The
[development evidence](../benchmarks/results/native-dyadic-two-sweep-admission-development-v1/manifest.json)
retains the first rejected build and admission, the strict final MSVC build,
the normal/optimized controls and the independent reference preview.

The binary stream saves the literal skeleton, ordered visible row keys, both
frozen current grids, both complete regret/average arrays and root holding
values, and the separately quantized final average grid. The reader independently
reconstructs ordered legal histories and replays all updates with literal joint
worlds. It evaluates the saved grid and chooses each best response after summing
all worlds indistinguishable by visible history and own holding. The production
driver does not retain those literal worlds. The independent oracle agrees with
every clipped regret and average slot in the accepted saved fixed-profile study.

`scripts.run_virtual_dyadic_training_cohort` requires the trusted source-only
launcher and a clean expected commit. It binds the full committed source to
actual build inputs, vendored headers and executable, observes an admission-only
child, and enters a single native training child only with explicit `--train`.
The independent replay runs after that child exits and after source and output
identity checks. Observe the outer controller exit and final bootstrap too.
The accepted replay checked all 24,420 rows, 58,164 action slots per sweep,
four root holding values per sweep, and the exported average policy. All 24,420
current rows changed between sweeps. The independent best responses measured
exploitability of approximately 2.746696 big blinds for that exported policy.
This is an early training checkpoint, with convergence and larger games still
open.

The run consumed 344,067,616 modeled work units. The largest charges were
106,327,000 for the parent traversal and arithmetic, 73,455,536 for state,
and 54,311,964 for quantization. The isolated native process took 0.884 seconds
on the recorded MSVC fixture run, including binary output. The archive retains
the raw output, child exits, final verifier receipts, build identities, and
captured source inventory. Reuse saved output for any future replay.

The opt-in `ADMIT_PAIRED` and `TRAIN_PAIRED` modes carry both seats' values
through one public walk per sweep. Each decision stages the acting seat once.
The shared walk uses the same frozen policy, board support, action order, and
fixed-point arithmetic. Rank-free admission planned 443,428,568 modeled work
units. The paired cohort at `cc799a8` matched all 22,587,236 data bytes before
the receipt footer and passed independent replay, including best responses.
[Paired evidence manifest](../benchmarks/results/native-dyadic-paired-accepted-v1/manifest.json)

The paired run used 317,747,928 modeled units, down 26,319,688 or 7.65% from
the two-pass run. The isolated native process took 1.158 seconds, compared with
0.884 seconds for the saved two-pass run. These are single local samples. The
paired Windows child recorded a lifetime peak working set of 47,235,072 bytes
and peak commit of 45,768,704 bytes. Both policies have the same measured
exploitability of approximately 2.746696 big blinds on PROOF9.

The rank-free [storage census](native-dyadic-storage-census.md) keeps the
holdings and betting template fixed while expanding the deck. It identifies
dense river strategy storage as the first capacity barrier beyond PROOF9.

`ADMIT_PACKED` and `TRAIN_PACKED` select the paired walk with exact packed
average masses. The cohort controller selects this mode with
`--packed-averages`. The checkpoint still emits the full unscaled integer
values for independent replay. The receipt footer accounts for the packed
layout and conversion. See the [storage measurements](native-dyadic-storage-census.md#packed-exact-average-masses)
for the observed memory comparison and the remaining capacity limit.

`ADMIT_COMPACT` and `TRAIN_COMPACT` select both packed fields and direct
quantization of their compact values. Use `--compact-strategy` with the cohort
controller. The checkpoint format still carries the full numerators. See the
[compact strategy comparison](native-dyadic-storage-census.md#packing-both-strategy-fields)
for the frozen exact replay and measured tradeoff.

`ADMIT_SCALED` and `TRAIN_SCALED` use the compact strategy layout and construct
average increments directly in each row's scale. Select this profile with
`--scaled-averages`. The [measured comparison](native-dyadic-storage-census.md#constructing-averages-in-packed-units)
uses the same independently replayed game and full checkpoint format.

`ADMIT_SEALED` and `TRAIN_SEALED` use History-owned action tokens and release
the row lookup index before training. Select the profile with `--sealed-menus`.
The [sealed-menu comparison](native-dyadic-storage-census.md#reusing-history-owned-action-menus)
records the measured work, memory, and runtime on the same fixture.

`ADMIT_PAGED` and `TRAIN_PAGED` keep the compact strategy in two bounded
files under a fresh run directory. Select this profile with
`--paged-strategy`. The [paging comparison](native-dyadic-storage-census.md#paging-the-compact-strategy)
records exact parity, stream traffic, and the measured memory and runtime
tradeoff on the nine-card fixture.

`ADMIT_DIRECTORY` and `TRAIN_DIRECTORY` use the same paged strategy with
compact row records and a construction-only lookup array. Select this
profile with `--compact-directory`. The request still covers the frozen
nine-card, two-sweep fixture. See the
[directory measurements](native-dyadic-storage-census.md#compact-row-directory)
for the separate construction and training budgets.

`ADMIT_RANK_SETS` and `TRAIN_RANK_SETS` use the compact directory with
one rank cache entry per validated final board set. Select this profile
with `--rank-sets`. The training artifact retains the same ordered
histories, exact policy format, and two-sweep nine-card scope.

## Rank reuse by final board

The source-frozen run at `3d52ddb` used three rank planes for all 60 ordered
final boards. It observed seven hand ranks, three misses, 72,717 hits, and
zero evictions. An independent physical traversal predicted every cache
counter and the 150,872 charged lookup units. The previous ordered-cache
run used 140 ranks, 60 misses, and 1,265,970 lookup units.

The profile removed 28,490,684 planned chance units and 1,688,632 total
charged units after the extra board-set census. All 22,587,236 numerical
bytes and both backing files matched the compact-directory run. Saved-only
replay verified both updates and final best responses. The single Windows
process measurements were 3.365 seconds for the ordered cache and 2.660
seconds for the board-set cache.
[Rank-cache evidence](../benchmarks/results/native-dyadic-rank-sets-accepted-v1/manifest.json)

Component controls compared both seats with the independent literal
evaluator across every supported ordered river on both decks. The ten-card
component used 17 board-set planes and 42 hand ranks for 340 ordered rivers.
Whole-game ten-card admission still has separate work, payload, and
checkpoint gates.

A separate saved-data check reconstructed the prior 22,587,756-byte
checkpoint from 2,114,028 bytes of metadata and policy data plus its two
compact page files. The same split projects 9,833,076 stream bytes and
47,403,552 page bytes on the ten-card geometry. This is a format
feasibility result from saved data and a structural projection.
