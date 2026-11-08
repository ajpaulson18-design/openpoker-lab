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

## Split checkpoint format

`ADMIT_SPLIT` and `TRAIN_SPLIT` select the bounded nine-card format
through `--split-checkpoint`. The stream begins with `OPLDSP01` and
uses an `OPLDSP02` footer. It carries the literal skeleton, row keys,
both current policy grids and root values, the final policy, and the work
ledger. The stream has a separate 2,114,028-byte transport ceiling.

After the two commits, `staged.bin` contains sweep 1 and
`committed.bin` contains sweep 2. Each file contains compact average
words followed by compact regret words. The controller records the
stream and image digests in `checkpoint-inputs.json`. Saved-only replay
authenticates all three inputs, derives row scales from the reference
tree, and checks both images exhaustively against independent updates.

The source-frozen run at `df04bcb` retained 11,821,708 numerical packet
bytes across the stream and two images. Restoring the wide stream from
those files matched all 22,587,236 numerical bytes of the rank-set
baseline. The verifier also rejected the two images in reversed sweep
order when given valid hashes for the supplied files.

The trainer read 17,785,312 page bytes, down from 27,558,528. The
independent access trace matched all 548 physical page loads. Both
planned and charged work fell by 9,771,552 units, covering the skipped
checkpoint emission and request charges. The single Windows process
times were 2.660 seconds for the rank-set run and 2.681 seconds for
the split run. The data supports the output and pager reductions at
this scope.
[Split checkpoint evidence](../benchmarks/results/native-dyadic-split-checkpoint-accepted-v1/manifest.json)

## Ten-card proof fixture

The separate `--ten-card` profile adds card 0 to the reduced deck and
keeps the same private ranges and betting template. `ADMIT_TEN` and
`TRAIN_TEN` select the two-sweep split format with `OPLDTP01` and
`OPLDTP02` framing. The denominator uses 120 ordered runouts per
compatible private pair. The full visible history still records each
ordered reveal and each holding.

The profile admits 644-bit values, a 9,833,076-byte stream, and two
23,701,776-byte images. The rank-free forecast reserves 2,102,190,180
work units inside a dedicated 2,150,000,000-unit allowance. State,
quantizer and pager enforce their own ten-card bounds. The earlier
nine-card modes retain their existing limits.

The frozen run at `bb46feb` trained 119,196 full-history rows and 281,066
action slots over two sweeps. The independent verifier enumerated 360
physical private-pair and runout combinations and checked both saved
updates, the final average policy, and both best responses. The native
trainer walked ordered chance and contracted reaches and payoffs on
demand. Its rank cache recorded 17 misses and 42 hand ranks.

The split packet retained 57,236,628 bytes across all three files.
The pager read 87,696,448 stream bytes and wrote 71,105,328, including
initialization. Its 2,679 page loads matched the independent schedule.
The run charged 1,575,076,849 work units. The Windows trainer process
took 14.0 seconds and reached a 13,660,160-byte working set in this
observation. The separate saved-only replay took 63.1 seconds.

The verified final exploitability was 2.9843 big blinds for the bounded
fixture after two sweeps. This is an exactness and capacity result for
the configured game. Longer-run convergence remains open.
[Ten-card run evidence](../benchmarks/results/native-dyadic-ten-card-accepted-v1/manifest.json)

### Buffered staging

The explicit `--ten-buffered` cohort uses `ADMIT_TEN_BUFFERED` and
`TRAIN_TEN_BUFFERED` on the same ten-card fixture. The pager retains one
dirty page per field. It flushes only contiguous marked runs on a page
change or commit. Average and regret extents can share a physical
page. The write-once bitmap covers the entire image and survives buffer
eviction. Reads continue to use the committed image until a successful
flush and sweep commit.

The independent rank-free traversal derives 19,560 stream write calls,
including initialization, and 8,888,166 written words. The direct
baseline used 1,124,988 calls for the same word count. Admission reserves
961,349 pager bytes, including 66,576 bytes for the two dirty buffers and
their metadata, and 2,126,173,102 work units within the ten-card cap.
The cohort checks the write schedule, unchanged read counts, both
checkpoint digests, and numerical stream bytes against the accepted
direct baseline. It then replays both sweeps and best responses from
the saved packet.

The frozen buffered run at `753b658` matched both checkpoint images and
all 9,832,556 numerical stream bytes. Saved-only replay reproduced both
sweeps and the final 2.9843-big-blind exploitability. The pager retained
the same 57,236,628-byte packet and transferred the same stream byte
counts. It reduced write calls by 98.3%.

The single Windows process observations were 14.00 seconds direct and
7.71 seconds buffered, with peak working sets of 13,660,160 and
13,742,080 bytes. These are observations for this fixture and toolchain.
The write counts measure calls made by the pager to its file stream.
[Buffered ten-card evidence](../benchmarks/results/native-dyadic-buffered-ten-card-accepted-v1/manifest.json)

## Packed checkpoint transport

The saved split images can be converted by
`python -m scripts.pack_virtual_dyadic_checkpoints`. The command
requires the original image directory, both published decoded hashes,
and a fresh output directory. Add `--ten-card` for the ten-card
fixture. It verifies the encoded round trip before emitting the packet
receipt.

Each `OPLPGZ01` file starts with an eight-byte magic and a little-endian
64-bit decoded byte count. An array of absolute 64-bit offsets follows,
with one offset per 32 KiB page and a final end offset. A frame with the
same length as its decoded page is raw. A shorter frame is raw DEFLATE.
The final page uses its actual decoded extent. The decoder checks the
directory before reading frames and bounds each decompression to one page.
Random page lookup uses the offset table and a single decoded-page cache.

Run the saved verifier with `--packed-page-images` and
`--packed-sweep-image-sha256` instead of the raw image directory flag.
Supply the original decoded hashes through `--sweep-image-sha256`.
Both sets are in the packed result manifest. Use the original numerical
stream and its existing hash. The buffered ten-card evidence archive
stores that stream at `cohort/train_ten_buffered/stdout.bin`; the raw
checkpoint images can stay in the archive.

The verifier authenticates the stored and decoded hashes before
mathematical replay, checks the decoded stream again as it compares every
checkpoint word, and rehashes the packed file before accepting the result.
The native trainer continues to use its existing mutable page store.

The frozen ten-card conversion at `0cde4ed` produced 2,189,329 bytes of
packed pages from 47,403,552 raw image bytes. Including the original
numerical stream, the replay packet fell from 57,236,628 to 12,022,405
bytes. Independent replay matched both sweep updates, the final policy,
and both best responses using only the packed images and that stream.
The study made zero native training calls. The byte comparison measures
files ready for replay. The historical ZIP remains the archival bundle.
[Packed ten-card evidence](../benchmarks/results/native-dyadic-packed-ten-card-accepted-v1/manifest.json)

## Virtual initial image

The explicit `--ten-virtual-zero` cohort uses `ADMIT_TEN_VIRTUAL_ZERO`
and `TRAIN_TEN_VIRTUAL_ZERO` with the ten-card buffered pager. Both
files start empty. Before the first commit, reads return zeros after
the same range, bank, and logical request checks. Those calls and
words are reported separately from cache and file traffic.

The first successful sweep commit switches the read view to the
materialized image. Subsequent reads require the full physical
extent. The write-once coverage, dirty-run flush, and commit checks
apply to both sweeps. A failed sweep preserves the previous read
view. The retained files still contain sweep 1 and sweep 2 in their
original order.

Admission keeps the 3,091,726 logical request cap and reserves
6,130,244 read words, 5,925,444 write words, and 18,836 write calls.
The work plan retains the per-word charge for synthesized reads and
removes the initialization and write-call allowances that this mode
does not need.

The frozen native run recorded 843,198 synthesized reads and matched
the independent schedule exactly. It used 1,498 page loads and 18,836
write calls, compared with 2,679 and 19,560 in the buffered baseline.
The difference was 62,356,272 bytes of file-stream traffic. The
single Windows process observations were 7.71 seconds buffered and
5.78 seconds with virtual initialization.

Both images and all 9,832,556 numerical payload bytes matched the
buffered baseline. The native run exited successfully. Its controller
then stopped at a baseline manifest-key error. The corrected
comparison has a regression test against the published manifest.
Separate saved-only recovery reauthenticated the original build and
packets and reproduced both exact updates and best responses without
rerunning the trainer.
[Virtual initial image evidence](../benchmarks/results/native-dyadic-virtual-zero-ten-card-accepted-v1/manifest.json)

## Ordered row registration and export reuse

The explicit `--ten-ordered-state` cohort uses the ten-card virtual
initial image. Its State accepts rows in canonical traversal order.
History reconstructs a bounded path of action-edge indices and
ordered reveal cards from each authenticated cursor. A fixed
17-digit path uses nonzero event digits and zero padding. This
places ancestors before descendants. Holding index breaks ties
between rows at one decision. A duplicate or backward row fails
before insertion. The stored full-history ordinal and the per-row
menu, holding and packed extents keep their existing meanings.

This profile skips the build hash. After the final commit, the
export takes ownership of the sweep policy and staging-mark arrays.
It overwrites every policy unit and fallback flag in the existing
wire order. All stage and row coverage checks still apply.

The ten-card admission removes the 524,288-slot hash and reserves
1,159,382 composed entries, down from 1,559,639. The History budget
adds 3,814,272 units for deriving paths. The per-row charge of 32
covers up to 15 occurrence visits and 17 digit or padding writes.
The existing State and quantizer work allowances stay in the plan.

The frozen run at `a249872` matched both prior sweep images and
all 9,832,556 numerical payload bytes. Independent replay reproduced
both updates, the final policy, and both best responses. The pager
traffic matched the virtual initial image baseline.

The single Windows observations measured a peak working set of
11,329,536 bytes with ordered State and 13,774,848 bytes in the
baseline. The corresponding process times were 8.22 and 5.78
seconds. These are paired-fixture observations from separate
runs. The admission ledger and measured working set describe
different quantities.
[Ordered State evidence](../benchmarks/results/native-dyadic-ordered-state-ten-card-accepted-v1/manifest.json)

## State-owned pager coverage

The explicit `--ten-row-coverage` profile uses a pager write
interface private to State. During registration, State lays out
consecutive, disjoint row extents in each of the packed average
and regret fields. The fields meet at the authenticated split.
Freeze verifies both complete limb counts.

Before staging any row, State checks that the row is still
unmarked and every action has its required input. It marks the
row only after both fields have been staged. A partial failure
poisons the owner. Commit verifies all row marks and the pager's
exact accepted and flushed word counts before switching the
committed image. Standalone pager calls keep their word overlap
check. Dirty-page marks still select the runs written to disk.

For ten cards, this removes 370,341 pager bytes and 46,293
composed entries. The work ledger removes 370,344 units of
bitmap reset allowance and retains the other paging charges.

The frozen run at `782d235` used 591,008 reserved pager bytes
and 1,113,089 composed entries. It matched both ordered-State
images, all 9,832,556 numerical payload bytes, and all pager
traffic counters. Independent replay reproduced the two
updates, final policy and best responses. The single Windows
observations measured 11.04 MB peak working set and 5.58 seconds
with row coverage, versus 11.33 MB and 8.22 seconds with the
word bitmap.
[State-owned coverage evidence](../benchmarks/results/native-dyadic-row-coverage-ten-card-accepted-v1/manifest.json)

## Shared policy rows

The explicit `--ten-shared-policy` profile keeps a one-byte tag in
each compact row record. Uniform and pure rows reconstruct their
exact grid values from the menu and tag. A mixed row writes its
first `menu_size - 1` units to a fixed address in a sweep-local
spill file. The last unit is the grid total minus the stored sum.

The spill build follows the registered row order and flushes before
the sweep opens. Every possible mixed row fits the admitted file
extent. The binary profile output, paired walk, and State staging
each read the same frozen policy once per row. Recursive decisions
hold their own copies. Final average export emits every policy unit
in wire order, then the fallback flags. A uniform grid and a
zero-mass fallback retain separate meanings.

Ten-card admission reserves 832,287 composed entries and a maximum
of 161,870 spill words per sweep. The work plan adds 15,056,976 units
for a build and three reads per row in both sweeps. It uses the
all-mixed case to set the bounds.

The frozen ten-card run at `154b40a` reproduced both previous
checkpoint images and all 9,832,556 numerical payload bytes.
Independent replay reproduced both updates, the final policy
and both best responses. Pager traffic retained the previous
counts. The spill receipt matched an independent scan of the
saved policy grids, including every retained mixed-policy word.

Sweep 1 used shared uniform rows throughout. Sweep 2 wrote
48,118 words for its mixed rows and read 144,354 words across
the three consumers. The final spill extent was 161,830 words
within the 161,870-word worst-case bound.

The single Windows observations measured 8.81 MB peak working
set and 3.88 seconds with shared policy, versus 11.04 MB and
5.58 seconds in the row-coverage baseline. The file-backed
mixed policy and streamed export removed the resident
slot-sized unit array.
[Shared policy evidence](../benchmarks/results/native-dyadic-shared-policy-ten-card-accepted-v1/manifest.json)

## Paged immutable row directory

The explicit `--ten-paged-directory` profile appends each row's
identity, source menu, offsets and exact scales to a private file.
Freeze flushes and checks the complete 32-byte-per-row extent.
Subsequent reads use eight direct-mapped pages of 128 records.
Callers receive value snapshots; action views refer to the sealed
menu catalog. The directory remains unchanged throughout training.

The existing byte per row holds the five-bit policy tag and a
staging mark. A successful row marks completion only after both
packed fields are staged. Final export replaces the byte with its
fallback flag after all policy units have been emitted. Directory
read failures poison State and prevent later sweep operations.

For ten cards, the composed reservation is 360,303 entries, down
from 832,287 with shared policy. The directory object reserves
4,608 eight-byte entries, including its 32 KiB cache; copied
decision descriptors add 192 frame entries. Sequential registration
also removes an obsolete per-row lookup allowance. Directory append,
lookup and page-read work remain separately charged. The resulting
plan is 2,129,413,526 modeled work units within the existing cap.

An independent physical-support traversal predicts 1,191,960 frozen
row reads, 7,656 page misses and 31,333,376 bytes read. Buffered
construction writes 3,814,272 bytes in 932 requests. These counts
describe application requests, not operating-system disk traffic.
The frozen run at `56a27a2` matched those traffic counts, both prior
checkpoint images and all 9,832,556 numerical payload bytes.
Independent saved-only replay reproduced both updates, the final
policy and both best responses. The native child, verifier and outer
controller exited zero, with all 2,515 captured source files unchanged.

The single Windows observations measured 5,038,080 bytes peak working
set and 6.81 seconds with the paged directory, versus 8,810,496 bytes
and 3.88 seconds with resident shared-policy rows. The memory gain
has a runtime cost on this fixture. These are separate single runs;
they do not establish a general speed or disk-I/O result.
[Paged directory evidence](../benchmarks/results/native-dyadic-paged-directory-ten-card-accepted-v1/manifest.json)

Longer recurrence is the next quality prerequisite. Fixed-two-sweep
assumptions remain in quantizer forecasts, policy-spill receipts,
checkpoint roles and replay. Keeping only a subset of the current
per-sweep charges adds at least 263,039,242 modeled units per extra
sweep, putting a conditional T3 lower bound at 2,392,452,768, above
the unchanged 2,150,000,000 cap. This omits extra chance, quantization,
value addition, averages and directory/paging work, plus any wider
integer costs. It is a capacity barrier, not an admitted forecast.
Versioned longer-run accounting and independent replay are required
before a convergence study; changing the sweep constant is insufficient.

## Sparse private-pair chance

The named `--ten-sparse-chance` profile keeps the ten-card game, two
simultaneous sweeps and streamed checkpoint format. Within the prepared
chance owner, it uses a fixed two-row scratch for live opponent weights
times reach. Each own row streams the compatible opposite rows. Fold
contractions sum positive mass. Showdown contractions use the sign of
the cached rank comparison and contribute zero on ties. The owner
preserves original row order, blocker masks, the common divisor and
the reach exponent.

The sparse kernel requires an explicit range limit of two holdings
per side. The bucket kernel remains the default for broader ranges.
Both share validation, rank-plane identity, cumulative admission and
failure handling. The sparse ledger covers the possible compatible
pair additions, weighted products and bounded live operands. It
retains neither a private-pair table nor complete worlds.

The independent ten-card forecast reduces the chance reservation from
447,066,576 to 127,793,144 modeled units. With checkpoint transport,
the complete reservation is 1,822,083,718 units. Independent verification
compares the numerical payload, both checkpoint digests, exported policy
and best responses to the streamed bucket profile.

The source-frozen study at `3c33c2f` matched all 9,832,556 bytes before
the work footer and both checkpoint images. Independent replay reproduced
the same policy and best responses with zero native calls. The observed
native chance charge fell from 209,133,313 to 68,478,558 modeled units.
Contraction work accounted for the entire difference. The two runs
recorded 797,344 contractions and 42 hand ranks each.

The single Windows native observations were 7.43 seconds and 5.10 MB
peak working set for buckets, and 6.41 seconds and 5.03 MB for sparse
pairs. These observations cover the named ten-card fixture and its
two-holding ranges.
[Sparse chance evidence](../benchmarks/results/native-dyadic-sparse-chance-ten-card-accepted-v1/manifest.json)

## Combined quotient and remainder

The named `--ten-single-division` profile keeps sparse chance, the
ten-card game and the two-sweep wire format. For each positive action
in a row with at least two positive weights, the quantizer requests
the exact quotient and remainder together from the bundled integer
backend. The existing power-of-two cancellation, action-order ties,
zero and pure shortcuts, and exact grid partition remain unchanged.

The proof10 quantizer keeps its width and scratch limits. The work
ledger charges one weighted division-helper invocation per qualifying
action. The helper can make several internal correction steps. These
units describe the invocation model rather than a count of backend
limb operations. The forecast reserves 433,472,328 quantizer units,
down from 513,301,416, and 1,742,254,630 total units including transport.
Saved-only replay counts qualifying actions from its own exact regrets
and average masses and checks the native invocation receipt.

The frozen run at `56dd735` reproduced both checkpoint images and all
9,832,556 numerical bytes before the work footer. Independent replay
reproduced the saved policy and both best responses with zero native
calls. The native counter, saved replay and a separate rank-free
checkpoint scan all counted 325,666 qualifying actions. The separate
path calls its division helper twice on those same actions, for 651,332
calls.

Charged quantizer work was 241,704,336 units with combined outputs,
compared with 255,655,680 with separate outputs. The single Windows
native observations were 5.92 seconds and 5.04 MB peak working set for
combined outputs, and 6.41 seconds and 5.03 MB for separate outputs.
The quality threshold was unset for this fixed fixture.
[Combined division evidence](../benchmarks/results/native-dyadic-single-division-ten-card-accepted-v1/manifest.json)
