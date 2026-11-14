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

## Paged State payload by phase

The named `--ten-phase-payload` profile keeps the same training and
checkpoint transport. It bounds the integer and text payload of the
sealed, ordered, row-covered State with a paged directory and streamed
export. The forecast includes the directory object, borrowed menu views,
resident pager, row overlay, policy spill metadata, codec buffer and
bounded live arithmetic. Borrowed action text remains charged to History.

The peak State payload reservation is 6,398,880 bits and the composed
reservation is 20,036,160 bits before stream scratch. The previous
composed reservation was 1,182,148,028 bits, including dense strategy
allowances carried forward from earlier layouts. These are modeled
payload bounds. Allocator capacity, filesystem buffering and working
set are measured separately. The named profile leaves entry and work
limits unchanged.

The frozen run at `bab69e2` matched the combined-division baseline's
numerical payload, checkpoint images, work receipts and independently
replayed policy and best responses. The one-bit-short State control
rejected before creating scratch files. The two Windows runs recorded
about 5.04 MB and 5.03 MB of peak working set for the legacy and phase
ledgers, respectively.
[Phase payload evidence](../benchmarks/results/native-dyadic-phase-payload-ten-card-accepted-v1/manifest.json)

## Contiguous row requests

The opt-in `--ten-row-batched` profile uses the same ten-card T2
training and streamed checkpoints. Policy construction reads the compact
regret extent once per row. Each sweep stages two complete field extents per
row. Final policy export reads the compact average extent once per row.
Each field keeps its original packed offsets, per-action scales and order.
The pager splits a request when it crosses a page boundary. The staged image
becomes committed only after the complete row coverage check and flush.

The request bound is seven reads and four writes per row across both
sweeps, including virtual zero reads. For the 119,196 rows and 281,066
action slots in this fixture, that gives 1,311,156 logical requests
instead of 3,091,726. The forecast preserves physical word, dirty-run,
and read-miss ceilings. It reserves 264 extra bytes for one reusable
44-word codec buffer. The request and fragment bookkeeping charge falls
by 33,668,960 modeled work units. Both checkpoint digests, the numerical
stream prefix, exact policy feedback and visible-information best responses
are required to match the phase-payload baseline.

The frozen run at `7a85266` passed native execution, independent replay
and the outer source check. All 2,536 tracked files retained their captured
raw bytes. Both checkpoint images and 9,832,556 numerical bytes matched
the phase-payload baseline. The observed pager counts matched every field
of the independent trace, including 1,498 read misses and 18,836 dirty
write runs. Fifty focused controls passed normally and optimized.

The composed reservation is 20,038,272 bits before stream scratch, with
360,336 reserved entries. The modeled total work falls from 1,730,311,006
to 1,696,642,046 before transport. The two separate Windows observations
recorded 7.29 seconds for row batching and 3.59 seconds for the phase
baseline, with about 5.03 MB of peak working set each. This study
establishes a request-count reduction. The fixture still uses two sweeps
and has an unset quality threshold.
[Row batching evidence](../benchmarks/results/native-dyadic-row-batched-ten-card-accepted-v1/manifest.json)

A separate comparison used the same authenticated executable for four
alternating pairs of complete native calls and streamed output. The
order was phase/row, row/phase, phase/row, row/phase. All eight calls
matched their accepted numerical stream, complete wire and checkpoint
images exactly, with the source inventory unchanged. Every observation
is retained. Row batching was faster in three pairs and slower in one.

Median times were 6.523 seconds for the phase profile and 6.001 seconds
for row batching. The median within-pair row/phase ratio was 0.9455,
about 5.45 percent less elapsed time. These measurements cover this
Windows host and finite ten-card T2 fixture. The numerical acceptance
study still contains its one training invocation. The timing experiment
records its eight additional calls separately.
[Alternating timing evidence](../benchmarks/results/native-dyadic-row-batched-ten-card-timing-v1/manifest.json)

## Sorted board-set rank index

The explicit `--ten-indexed-cache` profile uses row batching and a
sorted index of full board masks to stable rank-plane slots. A recent
match retains the existing fast path. Other lookups use a fixed-capacity
binary search. The index is allocated and admitted before use. On a
miss, the complete update bound is reserved before ranking, and the new
mapping is published only after the rank plane has been filled.
Exceptions poison the private owner.

The scalar ledger reserves two units for a recent comparison, eight per
binary-search step and four for the final key and slot checks. At
capacity `n`, a query is bounded by `6 + 8 * bit_width(n)`. The
erase/insert reservation is `8*n + 16*bit_width(n) + 32`, including two
searches and two possible record shifts. Initialization reserves
`4*n + 16`. Each index record holds a full mask and slot, with 32
additional logical entries for metadata, diagnostics and bounded scratch.
The existing linear profile retains its original receipts.

For the ten-card fixture, the new index reserves 66 entries within the
existing chance-owner allowance. Its conservative chance forecast rises
from 127,793,144 to 132,742,404 modeled work units, with the additional
search and maintenance charges included. An independent rank-free
traversal derives 79,560 nonrecent searches across 412,080 queries and
pins the complete expected index ledger before training.

The same independent traversal derives 262,080 nonrecent searches for
the prospective eleven-card T2 workload. Its 56-plane chance forecast
is 448,157,615 units, compared with 526,856,639 for linear lookup, under
the existing 500-million chance-owner ceiling. This is a rank-free
forecast. Eleven-card precision, storage, transport, whole-request
admission, training and saved-policy verification remain separate gates.

The frozen run at `0122ce9` passed native execution, independent
saved-policy replay and the outer source check. All 2,542 tracked files
retained their captured bytes. The independent structural trace matched
all eight index fields, including 79,560 nonrecent searches and 17
successful publications. Both checkpoint images and the numerical
stream outside its work footer matched the row-batched baseline.
Sixty-six focused controls passed normally and optimized. Terra supplied
the independent source review, complete Chance forecast and search trace.

The new Chance reservation is 132,742,404 units on ten cards. Its actual
metered work is 70,637,650, versus 68,478,558 in the row-batched baseline.
The broader scalar bookkeeping is explicit in the new model. The
separate native observations were 8.50 and 7.29 seconds, with about
5.03 MB peak working set each. They establish no timing improvement.
Exploitability remains approximately 2.9843 big blinds after two sweeps,
with an unset quality threshold. The packet also preserves the complete
rank-free ten- and eleven-card forecasts with authenticated source closure.
[Indexed-cache evidence](../benchmarks/results/native-dyadic-indexed-cache-ten-card-accepted-v1/manifest.json)

## Named 32-sweep quality lifecycle

The [N9 quality study](native-dyadic-quality32.md) extends the exact changing-policy
path to a separately admitted 32-sweep lifecycle. Recovered independent replay
passes every update and the complete wire hash. Exploitability is 0.3969424
big blinds in this fixed game, above the predeclared 0.1 target. The miss and
original controller interruption remain preserved.

## Exact terminal payoff scaling

The paired trainer precomputes one unsigned scale for each terminal
from the exact money significand and the integer chance-divisor ratio.
Admission checks that the full divisor bounds every scale product.
The lane then applies one wide multiplication and the original exact
shift and sign.

A frozen build at `704fea6` reproduced the complete wire, every
checkpoint digest, and the independent saved-policy replay for both the
indexed ten-card T2 and linear-weight nine-card T32 fixtures. Both
source audits passed, as did 38 focused controls in normal and optimized
Python. The source-level wide multiplication count falls by 1,329,176
on T2 and 4,350,336 on T32. These counts describe the named fixtures.
The conservative work meter uses the original equation. The observed
times came from concurrent runs and supply no speed estimate.
[Terminal scaling evidence](../benchmarks/results/native-dyadic-terminal-scaling-v1/manifest.json)

## Complement quantization on the fixed ten-card profile

The opt-in `--ten-complement` cohort uses the indexed ten-card trainer
and computes the last positive action's quotient and remainder from
the total grid mass. It divides for each earlier positive weight.
The prior remainders accumulate modulo the sum of the positive weights,
with a carry for each subtraction. The last quotient is the grid total
minus the prior quotients, the carry, and one more unit if the residual
is nonzero. The final remainder is the denominator minus that residual,
or zero when the residual is zero. Largest-remainder ordering and
action-order tie breaking follow the existing path.

The new kernel admits up to four actions in the named ten-card profile.
One-positive and zero-positive rows follow the existing pure and uniform
rules. The combined-division admission formula remains conservative.
The receipt counts actual wide quotient/remainder operations.
Other named profiles continue to use their prior kernels.

The frozen run at `4ec2929` executed 186,152 wide divisions versus 325,666
in the indexed baseline, a 42.8 percent reduction. Its complete output
stream, both checkpoint digests, independently replayed policies and best
responses, and work receipts match the baseline. Six quantizer tests and
25 training and admission controls passed with normal and optimized Python.
The initial pretraining attempt lacked the compiler environment. The
evidence retains that zero-training exit and the successful source audit
over all 2,555 tracked files.

The same executable ran four alternating timing pairs with identical
complete output and checkpoints. The complement was faster in all
four. Median elapsed times were 6.245 seconds for indexed division and
5.822 seconds for the complement. The median within-pair ratio was
0.9541, about 4.6 percent less elapsed time. Peak working sets ranged
from 4,317,184 to 4,321,280 bytes. These observations cover one Windows
host and the fixed ten-card, two-sweep fixture. Exploitability remains
about 2.9843 big blinds, with an unset quality threshold.
[Complement evidence](../benchmarks/results/native-dyadic-quantizer-complement-v1/manifest.json)


## Compact exact numerical transport

The opt-in `--ten-compact-wire` cohort retains every ordered row identity
in a six-byte record, reconstructs cumulative slot offsets, and omits
the first sweep's canonical uniform policy units after checking them.
Subsequent policies retain seven bytes for each action except the last,
whose exact unit count follows from the fixed grid total. Fallback
flags use one bit per row. Roots, the literal skeleton, denominator,
receipt footer and all checkpoint frames remain present.

The compact format uses a separate magic and declared length. Its bounded
decoder reconstructs the existing numerical stream for independent policy,
update and best-response replay. The cohort authenticates both streams,
checks compact frame epochs and image hashes, and compares the expanded
bytes against the accepted indexed result. The verification workflow keeps
the compact stream and an expanded disk copy, and reports both extents.
The native output bound and host verification disk usage are distinct.

The rank-free eleven-card geometry gives 9,614,478 compact numerical bytes,
below the existing 9,833,076-byte native profile ceiling by 218,598 bytes.
The full proposed wire remains 165,201,774 bytes including checkpoint
images and headers. This output representation leaves the eleven-card
work and quality gates open.

The encoder has a separate conservative scalar-operation reservation of
`208 * rows + 64 * slots + 16 * ceil(rows / 8)`. It reserves 64 units
before each packed row, 64 plus 32 per action before each of the two
encoded policies, and 16 per flag plus 16 per packed flag byte. These
constants cover packing, partition checks and loop/control primitives.
The earlier output ledger retains common stream I/O, policy access and
the first uniform-policy check. The extra encoder counter and packed
scalar scratch reserve 32 logical entries and 2,048 payload bits.
Admission composes these terms with learning and checkpoint-copy work
under the existing caps. They measure the declared source-level model.
The native sidecar records the extra work before acceptance.

Independent reconstruction interleaves saved compact numerical sections,
canonical epoch headers and both authenticated image files, then compares
its complete wire length and SHA-256 to the captured native stream.

For ten cards, the additional encoding reservation is 43,019,392 work
units. Composed learning, checkpoint-copy and encoding work reserve
1,756,554,322 units within the existing 2.15-billion cap. Encoder scratch
brings the composed reservation to 364,468 entries and 20,302,720
payload bits. The earlier learning/footer receipts retain their scope.

Extending the encoder equation to eleven cards adds 136,982,368
units. The current whole-request projection becomes 5,496,134,543
units, above the unchanged work ceiling. The output reduction therefore
resolves a projected representation constraint while compute admission
remains unfinished.

The final frozen study at `cf5d480` passed native execution, exact
expansion, independent full policy/update/best-response replay, wire
reconstruction and both source audits. All 2,560 tracked files retained
their captured bytes. Numerical output fell from 9,833,076 to 3,103,848
bytes, a 68.4 percent reduction. The full wire fell from 57,236,692 to
50,507,464 bytes, including both checkpoint frames. All 38 focused
controls passed with normal and optimized Python.

Four alternating pairs on the same executable preserved every output
and checkpoint identity. Compact calls were faster in two pairs and
slower in two. Median native-call times were 4.367 seconds for legacy
emission and 4.277 seconds for compact emission. The median within-pair
compact/legacy ratio was 0.9796. These measurements cover one Windows
host, complete native calls and streamed transport. Host expansion and
independent replay follow the captured call. Exploitability remains
about 2.9843 big blinds, with an unset quality threshold.

The packet preserves the earlier format-only run before separate
encoding-work accounting, the intermediate metered run, and the final
compatibility adjustment.
[Compact transport evidence](../benchmarks/results/native-dyadic-compact-wire-v1/manifest.json)

## Factored payoff arithmetic and direct packed updates

The opt-in `TEN_FACTORED` profile uses the same ten-card game and two
completed CFR+ sweeps as compact transport. Each traversal value stores a
signed integer coefficient and an implicit power of two. Terminal scaling
multiplies by the exact stake and street-divisor ratio. Addition aligns only
the coefficient with the larger shift. A row mix factors out the common
power of two in the nonzero policy units before applying the exact
`2^52` denominator. Pure rows return the selected value after validating
the partition. The driver expands four numerators at each sweep boundary.

State subtracts each mixed value from its action values and converts the
delta to the certified regret row scale. If this conversion requires a
right shift, the low magnitude bits must be zero. The packed update reads
the shifted sign and magnitude directly, checks overflow, and clips
negative regrets at zero. Average increments already arrive in the
certified row units. The update writes a field's staged words only after
all actions in that field succeed. If average staging fails after regret
staging, State marks the owner failed and prevents committing the sweep.
The packed arithmetic controls cover separate update failure atomicity.
The fixed full-game replay covers successful State staging and commit.
Synthetic nondivisible factored deltas and a forced average failure after
regret staging are still uncovered at the State boundary.

The existing Parent work reservations still cover wide arithmetic.
At eleven words, each of the 1,329,176 terminal scaling calls frees 60
units inside that reservation by avoiding the second multiply and
expanded shift. The 1,420,012 additions need at most 46 extra units each
for one coefficient copy, one in-place alignment and signed addition.
The resulting 14,430,008-unit balance stays within Parent. The old footer
charges are preserved. State's mixed-value allowance covers bounded
products, alignment, addition and exact division. Its regret arithmetic
and codec allowance cover the aligned difference and checked quotient.
The retained per-slot and per-word codec reservation covers packed word
extraction, comparison, carry or borrow, and scratch copies.

A shared execution counter charges 64 units for each conversion,
addition, subtraction, terminal scale and root expansion, and 320 per
policy mix. The native driver and independent host check each realized
event count. The added metadata reservation is 380,819,456 units.
Composed work is 2,137,373,778 against the existing 2.15-billion cap.
With 65,536 bytes of additional scratch reserved, the composed counts are
372,660 entries and 20,827,008 payload bits. The work and storage
reservations are modeled. Packed word receipt counts describe the
target words touched.

The frozen run at `e455b94` verified both checkpoint images and all policy,
root and compact-wire bytes against the existing exact result. The
saved-only replay reproduced the updates and best responses. Maximum
observed coefficient width was 430 bits and maximum implicit shift was
628 bits, across different values. The two-sweep exploitability was
2.9843178536 big blinds with no quality threshold set. Eleven-card
compute admission remains open.

In four alternating pairs on one Windows host, the factored profile
was faster in three pairs. The median within-pair time ratio was 0.947,
with medians of 6.464 seconds for the baseline and 5.986 seconds for
factored execution. Peak working set was 5.04–5.05 MB in both modes.
Each complete native call and capture reproduced the same bytes. The
timing excludes host expansion and independent replay.

All 54 controls passed normally and with optimized Python. The evidence
archive preserves both logs, the initial controller count mismatch,
source and binary identities, the saved policy, independent replay, and
all eight timing observations.
[Factored training evidence](../benchmarks/results/native-dyadic-factored-training-v1/manifest.json)

## Checked History cursor

The opt-in ten-card checked History profile uses the factored trainer.
A private cursor carries the physical board code and card mask. The flop
establishes their values after verifying sorted, distinct deck members.
Turn and river each verify the existing prefix and append one checked
physical card. Betting edges preserve the board bits. The literal path
ordinal still distinguishes different action histories through a shared
template node, and the board code still distinguishes turn and river order.

A single checked lookup verifies the expected source node and visible
street at each visit. Owner, generation, cursor extent and phase guards
remain in the transition path. The cursor fits the 48-byte bound without
growing the resident occurrence array. The action, reveal, ordinal and
ordered registration charges retain their previous rates.

The exact History reservation counts construction, one root acquisition,
all three public walks, the learning decision ordinals, ordered catalog
rows and one read per distinct sealed menu. For the fixed two-sweep
schedule, with action edges A, reveal edges Q, visits V, public decision
occurrences D, rows R, menu sources M and menu tokens T, this is
4096 × 1105 + 1288 + 3 × (40A + 72Q + 8V) + 64D + 64R + 24M + 16T.
The new profile requires the complete History receipt to match the
reservation. Its 62,890,960 units are 6,934,704 below the earlier realized
charge and 36,863,656 below the earlier conservative forecast. Composed
factored admission is 2,100,510,122 units against the 2.15-billion cap.

The frozen run at 8bd8274 reproduced both checkpoints and every numerical
section. The expanded artifact differed in the two History work words.
The independent verifier checked both work words, all saved policies
and updates, and the two best responses. The initial MSVC freeze
failed on the narrowing of a backwalk index before training. The
successful freeze explicitly retains occurrence-width backwalk indices.

The independent rank-free schedule projects 185,692,384 History units
for eleven cards against its 100-million cap. Other owner limits and
the composed work cap also need separate changes. The forecast script
counts 355,446 literal decision visits per walk from the physical prefix
geometry and reconstructs the earlier ten-card ledger as a calibration.

Four alternating pairs on one Windows host reproduced both complete
streams and both image hashes against their respective frozen receipts.
Median full native call times were 7.161 seconds for factored training
and 6.583 seconds for checked traversal. The median paired ratio was
0.9077. Three checked calls were faster and one was slower. The
4,096-byte peak working-set difference was one memory page. Host
expansion and independent replay followed the measured native calls.

The focused controls cover the exact ordinal on 5,525 records and
reject a changed prefix, a foreign card and a repeated card at the
turn boundary. The archive preserves the first control failure, caused
by counting two mismatch checks in the single-call work measurement.
The test-only correction was checked against the original trainer and
State build source closures.
[Checked History evidence](../benchmarks/results/native-dyadic-checked-history-v1/manifest.json)
[Rank-free projection](../scripts/project_virtual_dyadic_history.py)

## Reusing a validated public visit

The ten-card visit profile authenticates the cursor once when it enters
a traversal frame. The checked occurrence supplies the decision ordinal
from the already packed board code. Child edges take that same visit
value. It retains owner and generation identity, and each edge rejects
a failed or foreign owner before reading the occurrence. The parent can
use its visit again after returning from a child. Sealed row catalog
registration still checks each holding and reconstructs its strict
traversal order.

The History model retains 8 units for the cursor validation at visit
entry. The existing parent visit reservation covers matching the
source and street and forming the key from the checked occurrence and
board code. Action descent reserves 16 units for the bounded owner,
phase and menu checks, child index read and fixed cursor copy. Reveal
descent reserves 48 for its guards and the checked three-card flop pack,
or the short prior-prefix comparison and one checked physical card append.
Both edge paths charge before running those operations. The separate
learning ordinal charge disappears because the visit supplies it.
These are modeled operation units. They do not predict elapsed time.

The complete ten-card schedule reserves 34,741,384 History units, down
from 62,890,960, and 2,072,360,546 units across the factored profile.
The rank-free eleven-card History projection is 98,688,160 against
100,000,000, leaving 1,311,840 units of projected headroom. The State,
quantizer and composed work gates remain open. The projection uses
the same three traversal schedule and unchanged catalog charges.

The frozen run at 9a9f48f matched both checkpoint images and every
numerical section. Only the two History work words differed in the
expanded artifact. All 55 focused controls passed with normal and
optimized Python. Across four alternating pairs on one Windows host,
the median complete native call took 8.241 seconds for checked History
and 8.282 seconds for visit reuse. The median paired ratio was 1.0050,
with two faster and two slower pairs. The comparison established
no elapsed-time improvement.
[Visit reuse evidence](../benchmarks/results/native-dyadic-history-visit-v1/manifest.json)

## Equal positive weights in the policy quantizer

The opt-in ten-card equal quantizer inherits the visit profile. After
validating the entire input, it checks whether all positive weights
are equal. For k equal positive weights, each receives floor(2^52/k)
grid units and the first 2^52 mod k positive actions in legal order
receive one extra unit. Zero and negative regret entries receive
zero units, and negative average masses are rejected. This rule is
the same largest-remainder allocation because all positive
remainders tie. A positive equal row has no uniform fallback flag.
Unequal rows use the existing complement division path.

The two potentially mixed row phases each reserve 16 plus four times
the menu size times (maximum limb words plus one) for the equality
check. Each phase keeps the existing full generic reservation. The
first sweep starts with zero regrets and never enters the equality
check. With 119,196 rows and 281,066 action slots, the total additional
reservation is 30,796,608 units. The quantizer reserves 464,268,936
units and composed factored admission reserves 2,103,157,154. The
rank-free eleven-card projection would add 97,884,864 units under
the same conservative scheme. Equality frequency at eleven cards
must be measured separately.

The first strict native build rejected two obsolete local declarations.
The corrected build and exact replay use frozen source 53a2f7b.

Independent saved replay verified every numerical section and both
checkpoint images. The expected change from the visit profile is in
the two quantizer work words. It rebuilt the realized quantizer charge
from exact packed row masses and matched all three figures. The shortcut
handled 94,164 rows, avoided 113,224 multiprecision divisions, and left
72,928 such divisions. Realized quantizer work fell to 206,392,024
from 241,704,336 units. All 61 focused controls passed in both modes.

On a Windows host, the shortcut was faster in all four matched pairs.
The median within-pair time ratio was 0.9749, and median complete
native calls took 3.475 seconds versus 3.649 seconds for the preceding
visit profile. The timing excludes host replay and covers only this
fixed game and budget.
[Equal-weight quantizer evidence](../benchmarks/results/native-dyadic-equal-quantizer-v1/manifest.json)

## Reusing an owned frozen row during staging

The opt-in ten-card snapshot profile copies the four policy slots into
an internal State-issued object before visiting children. It retains the
authenticated descriptor by value, with menu views that borrow immutable
catalog storage. Staging checks State ownership, the active sweep and
its generation, and rejects a duplicate row before applying the exact
regret and average updates. No directory or policy cache pointer is
retained across recursion. Public copy APIs keep their current behavior.

The two-sweep directory schedule falls from ten to eight reads per row.
The independent direct-mapped trace predicts 953,568 logical row
lookups, down from 1,191,960. The modeled
page-read count falls from 7,656 to 7,456, or 819,200 fewer requested
bytes. Policy spill loads fall from three passes per sweep to two.
Packed regret and average traffic is accounted separately. State retains
the prior conservative work reservations, and the composed entry and
payload allowances include 16 KiB for the snapshot frames.

The independent eleven-card trace projects 760,344 fewer directory
lookups across two sweeps and 582 fewer page reads, saving 2,383,872
requested directory bytes. The policy spill schedule removes one
logical load per row per sweep. Eleven-card physical mixed reads still
depend on its policy. The eleven-card training path remains outside
the current State and quantizer work limits.

The first build caught that the snapshot object exceeded the proposed
MSVC size bound. The corrected source at 617919c raised the per-object
ceiling to 160 bytes and reserved 16 KiB for the recursive frame scratch.
The frozen run and replay reproduced the complete compact output,
checkpoints and best responses byte for byte. The independent directory
trace matched all observed logical and physical counters. Both test
modes passed 61 controls.

Four matched native-call pairs on one Windows host all verified the
same compact wire and both checkpoints. The snapshot mode was faster
in two pairs and slower in two. Median full-call time was 5.746 seconds
versus 5.646 seconds for the preceding path. Median paired time was
2.0 percent higher. Measured I/O reductions establish no elapsed-time
gain on this fixture.
[Owned snapshot evidence](../benchmarks/results/native-dyadic-owned-snapshot-v1/manifest.json)

## Initial policy from virtual zero

The opt-in ten-card initial-policy profile uses State's fresh virtual-zero
image to register the uniform policy tag for each first-sweep row. State
validates the row menu and spill order. Reading a tag reconstructs the
same 52-bit policy units in legal-action order, including the extra unit
for the first action in a three-action menu. The second sweep and average
export retain the equal-weight quantizer.

The first-sweep build uses 119,196 fewer synthetic regret reads and skips
1,666,910 synthetic words. The physical read count and requested words
stay at 1,498 and 6,130,244. Net reserved work across State, quantizer and
parent falls by 49,726,752 units, from 2,103,157,154 to 2,053,430,402
including transport and factored execution. The independent byte
comparison permits eight changed work counters in the expanded footer.

The rank-free eleven-card schedule projects 380,172 fewer synthetic
reads, 5,536,052 fewer synthetic words and 158,431,968 fewer net work
units. State and quantizer are still projected above their respective
caps. The projection uses the same two-sweep lifecycle and contains
zero native training or hand-ranking calls.
[Initial policy evidence](../benchmarks/results/native-dyadic-initial-policy-v1/manifest.json)


## First-sweep regret support and packed widths

Starting at zero, a row's first CFR+ update clips the difference between
each action value and their policy-weighted mean. At least one action
value is at or below that mean. Its clipped regret is zero, so a menu
of size m has at most m minus one positive regrets for the next policy.
A two-action menu therefore takes the zero-or-single-positive path.
The named ten-card profile enforces this support bound at quantization.

The forecast also uses each packed column's certified bit width for
equality and trailing-zero scans. The width used for ratio arithmetic
continues to follow the separate bound on normalized masses. The export
receives a narrower scan reservation from its packed layout and may
still have positive mass on every action.

The ten-card quantizer reservation falls from 412,635,048 to 317,853,256
work units. The saved-only replay verifies both sweeps and best responses.
Against the initial-policy profile, the expanded stream changes only
the quantizer forecast word, and realized work charges match. The
eleven-card structural projection reduces the quantizer forecast
by 303,431,928 units to 1,014,146,272. The eleven-card State and quantizer
forecasts remain above their caps.
[Regret support evidence](../benchmarks/results/native-dyadic-first-regret-bound-v1/manifest.json)


## Direct first-sweep packed updates

The opt-in ten-card profile constructs first-sweep packed regret and
average rows from the owned virtual-zero image. It validates signed
regret divisibility before clipping and checks the retained width and
extent before staging. The packed writer records every word, including
required zero padding. Later sweeps continue to update committed rows.

Compared with the first-regret-bound profile, the ten-card schedule
removes 238,392 synthetic requests and 2,962,722 synthetic words.
Physical reads, physical writes and checkpoint coverage keep their
previous counts. The paging reservation falls by 3,814,272 units while
the State arithmetic and codec reservations remain conservative.
Eleven-card geometry projects 760,344 fewer synthetic requests and
9,724,202 fewer synthetic words. Its State and quantizer admission
caps still prevent training.
The independent replay reproduced both policies, checkpoints and best
responses. The expanded file differs in four paging-work words. All 65
focused controls passed in both modes. In four alternating same-binary
pairs on one Windows host, the direct mode was slower in every pair.
Median native-call times were 4.833 versus 4.337 seconds, a 13.6 percent
median paired slowdown. The broader local test run was active on the
host during timing.
[Direct staging evidence](../benchmarks/results/native-dyadic-initial-packed-stage-v1/manifest.json)


## Factored staging width by row

The opt-in ten-card profile charges factored regret arithmetic at the
row's certified scale. A terminal numerator carries one factor of
2^52 for every decision absent from the opponent reach or the remaining
continuation. Reveal sums preserve the common factor. At a decision,
the child values have at least one additional factor of 2^52 over the
stored regret shift. State checks the factored scale of each nonzero
child value before charging the reduced width.

The policy units partition the 52-bit grid, which bounds every prefix
of the normalized weighted sum. The first uniform policy uses one
fractional bit for two actions, two for four actions, and up to 52 for
three actions. The second policy reserves all 52 bits. The calculation
keeps two extra bits for signed differences and scratch. Fixed checks,
packed codec and pager charges still use their previous formulas.

The ten-card State forecast and realized work both fall from 264,839,656
to 208,451,944 units. The independent byte comparison changes only the
two State work words. The eleven-card projection falls by 179,604,504
units to 662,607,040, above the 300,000,000 cap.
[Factored width evidence](../benchmarks/results/native-dyadic-bounded-stage-width-v1/manifest.json)


## Exact two-positive policy allocation

For two positive weights, the complement kernel computes the first
weight's quotient and remainder on the policy grid. A nonzero remainder
leaves one grid unit to assign. The earlier action gets it if its
remainder is at least the complementary remainder. The opt-in kernel
implements this directly, preserving tie order, sparse rows, equal rows
and the generic path for wider positive support.

The ten-card comparison uses the row-specific State work profile as its
baseline. Both versions perform the same number of divisions and carry
the same work reservations. The complete native output and both
checkpoints match.
Independent replay counted 15,794 eligible second-policy rows and
2,820 eligible average-export rows. Four alternating same-binary pairs
on one Windows host produced three slower runs and one faster run for
the shortcut. Median native call time was 4.711 versus 4.505 seconds,
a 4.1 percent median paired slowdown. The broader local suite was active
on that host during timing.
[Two-positive policy evidence](../benchmarks/results/native-dyadic-pair-complement-v1/manifest.json)
