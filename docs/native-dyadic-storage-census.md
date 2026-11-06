# Strategy storage census for nested decks

The rank-free census keeps the PROOF9 private holdings and betting template
fixed and adds the lowest unused card IDs. The template has 388 numeric states,
410 edges, and 1,105 literal occurrences at every size. The census counts each
acting holding's visible prefixes by inclusion-exclusion over its compatible
opponent holdings. It counts a canonical flop and ordered turn and river. A
separate enumeration checks the formula at all four streets of the nine-card
game and recovers the accepted 24,420 strategy rows and 58,164 action slots.

| Deck cards | Literal joint worlds | Strategy rows | Action slots | Packed checkpoint fields |
| ---: | ---: | ---: | ---: | ---: |
| 9 | 60 | 24,420 | 58,164 | 11,312,676 bytes |
| 10 | 360 | 119,196 | 281,066 | 54,696,044 bytes |
| 13 | 7,560 | 2,058,852 | 4,819,432 | 938,246,788 bytes |
| 26 | 1,580,040 | 349,801,052 | 815,751,450 | 158,843,293,100 bytes |
| 52 | 102,738,240 | 20,826,340,668 | 48,525,509,832 | 9,449,352,325,788 bytes |

Packed checkpoint fields use the current wire widths of 25 bytes per row and
184 bytes per slot. These are format-specific byte counts. The modeled state
reservation is a different measure, and the native process working set is a
separate observation. The 10-card row and slot counts already imply 4,718,820
entries and 1,165,699,576 integer payload bits under the current reservation
formula. Both exceed the trainer's limits before adding chance or history.
Only the nine-card case has a verified training result.

The river contains 98,000 of the 119,196 rows in the 10-card case. This makes
river strategy state the largest remaining storage target. A bounded page layout can
preserve each exact visible row key while limiting resident state. Paging still
incurs total storage and traversal work. Lossless per-row integer scaling and
exact equivalence classes need separate proofs and capacity measurements before
they can change the admission contract.

## Measured action-menu sharing

The fixed trainer reuses owned immutable legal-action menus by card-free
template node. The Windows x64 allocation controls measured 4,653,120 bytes of
action-token and view arrays before sharing and 39,008 bytes including the new
catalog spans. The 4,614,112-byte saving applies to those arrays. The existing
conservative admission and charged work are still used.

The source-frozen paired run at `aaba040` produced all 22,587,756 bytes of the
accepted `cc799a8` artifact exactly, including the receipt footer. Independent
replay verified both sweeps and the exported policy's best responses again.
Observed lifetime peak working set fell from 47,235,072 to 42,631,168 bytes.
Peak commit fell from 45,768,704 to 41,164,800 bytes. The corresponding native
wall-clock samples were 1.158 and 0.744 seconds. These are single observations
on the same bounded nine-card fixture. [Shared-menu evidence](../benchmarks/results/native-dyadic-shared-menu-accepted-v1/manifest.json)

The archive includes an offline width census of the saved integer arrays.
Factoring the common power of two from each final row leaves 48,708 of 58,164
regret slots and 47,442 average slots at 128 bits or fewer, counting zeros.
The largest residual widths are 423 and 253 bits respectively. A lossless
storage layout would need to handle both common small values and wider values,
with space for each row's scale and indexing. This census measures the saved
checkpoint, and a future layout will need its own bounds and replay.

## Packed exact average masses

The fixed paired trainer's opt-in packed mode uses the guaranteed common
power of two for each full-history row. It reserves 258,694 64-bit words per
array, or 4,139,104 bytes for the committed and staged arrays together before
metadata. The independent rank-free census agrees. The ten-card projection
needs 1,295,812 words per array. Under the current accounting its state alone
would reserve 5,864,478 entries, above the two-million entry cap.

The source-frozen run at `584b0eb` matched all 22,587,236 numerical bytes from
the shared-menu run. Independent replay matched both updates and the saved
best responses. The receipt footer records the different admission and work
charges. On Windows, the two single-run observations measured peak working
sets of 42,631,168 and 25,251,840 bytes, and peak commit of 41,164,800 and
22,761,472 bytes. Native wall-clock samples were 0.744 and 0.645 seconds.
[Packed-average evidence](../benchmarks/results/native-dyadic-packed-averages-accepted-v1/manifest.json)

The packed mode reserves and charges 23,123,160 additional modeled units for
layout and conversion. Total modeled work was 340,871,088 units. Logical
storage admission rose from 1,132,473 to 1,351,755 entries because each retained
packed word is counted separately. The conservative payload cap and reservation
are retained. The measured memory gain applies to this exact nine-card
profile and its two sweeps.

## Packing both strategy fields

The compact profile also stores regrets with a certified row-specific binary
shift. The four committed and staged arrays contain 9,707,680 bytes of limbs
before metadata. The full nine-card profile admits 1,980,339 entries and
498,002,048 modeled work units under the existing total ceilings.

The source-frozen run at `528bc32` matched all 22,587,236 numerical bytes from
the packed-average run. Independent replay verified both sweeps and the final
policy's best responses. The saved-only quantizer census predicted a reduction
of 1,516,512 charged units from scanning the compact values directly, which
matched the native receipt. The codec and suffix census add 31,453,424 units,
bringing total charged work to 370,808,000.
[Compact strategy evidence](../benchmarks/results/native-dyadic-compact-strategy-accepted-v1/manifest.json)

In single Windows observations, peak working set fell from 25,251,840 to
18,878,464 bytes. Peak commit fell from 22,761,472 to 16,031,744 bytes. Native
wall-clock time rose from 0.645 to 0.879 seconds. These measurements cover the
same bounded game and two sweeps.

The rank-free ten-card projection needs 47,403,552 bytes in the four limb
arrays and 8,874,558 modeled state entries before chance and history. Further
growth needs a different resident storage model and a separate work forecast.

## Constructing averages in packed units

The scaled-average profile builds one weighted own-reach value per row and
multiplies by each frozen action unit. The packed state accepts the resulting
compact increments directly. The saved-row census predicts 12,177,724 fewer
units for average construction and 5,118,432 fewer units for the average codec.
The observed receipts match both reductions, lowering planned total work from
498,002,048 to 480,705,892 units and charged work from 370,808,000 to 353,511,844.

The source-frozen run at `a6f2a14` matched all 22,587,236 numerical bytes from
the compact-strategy run. Independent replay verified both sweeps and the final
policy's best responses. The Windows observations measured 0.879 and 0.671
seconds and peak working sets of 18,878,464 and 18,898,944 bytes respectively.
Each variant has one observation on this bounded fixture.
[Scaled-average evidence](../benchmarks/results/native-dyadic-scaled-averages-accepted-v1/manifest.json)

With the same word widths and current accounting equations, the ten-card
state and two codec reservations alone would require 599,711,120 work units.
The projection also retains the 8,874,558-entry state requirement.

## Reusing History-owned action menus

The sealed profile authenticates 146 source menus with 371 action tokens and
reuses their immutable views across 24,420 independent strategy rows. It clears
the construction index before allocating the strategy arrays. The independent
census and native receipts agree on 14,483,984 fewer State units, 185,920 fewer
History units, and 3,104 additional parent census units. Charged work fell to
338,845,044, a reduction of 14,666,800 units. Planned work was 466,035,988.

The source-frozen run at `3663096` matched all 22,587,236 numerical bytes from
the scaled-average run. Independent replay verified both sweeps and the final
policy's best responses. The Windows observations measured peak working sets of
18,898,944 and 17,010,688 bytes, and native times of 0.671 and 1.254 seconds.
Each version has one observation on this bounded fixture.
[Sealed-menu evidence](../benchmarks/results/native-dyadic-sealed-menus-accepted-v1/manifest.json)

With the same widths and current accounting, the ten-card State and codec
reservations project 529,680,640 work units before traversal. The rank-free
page census also partitions the ten-card geometry into 543 visible-board pages.
The largest page holds 165,872 bytes of limb payload across all four images.
With a 4 MiB page budget, a cold sweep that loads all four images per miss
projects 284,426,144 read bytes. Keeping the frozen policy resident and reading
committed images separately projects 111,110,688 read bytes and 23,701,776
staged write bytes, plus 2,248,528 bytes for the resident frozen policy. These
are payload projections for the current traversal order. The archived census
records their phase, metadata, checkpoint, and filesystem assumptions.

## Paging the compact strategy

The paged profile reserves 600,274 bytes for cache payload, cache tags, and
staging coverage, plus 88 bytes of strategy codec scratch. Each of the two
backing files holds 4,853,840 bytes. Composed admission fell from 1,980,339
to 841,925 entries. The admission ledger charges 30,508,644 additional work
units for paging, for 369,353,688 charged units across the run.

The two-sweep run at `28e4171` matched all 22,587,236 numerical bytes from
the sealed profile. Saved-only replay independently checked both sweeps
and the final policy's best responses. A second verifier reconstructed
both backing files byte-for-byte from the full-width checkpoints. The
rank-free trace matched all 848 page loads and 27,558,528 bytes read by the
pager. The two files received 14,561,520 stream bytes, including initialization.
The single-bank layout at the same cache size projects 726,655,456 read
bytes. Stream counts describe application I/O, with filesystem caching
left to the operating system.

In one Windows run per profile, paging reduced peak working set from
17,010,688 to 8,151,040 bytes and peak commit from 14,249,984 to 5,312,512
bytes. Native process time increased from 1.254 to 3.235 seconds.
[Paged strategy evidence](../benchmarks/results/native-dyadic-paged-strategy-accepted-v1/manifest.json)

With the nine-card width and two-sweep schedule held fixed, the separate
rank-free ten-card projection covers 119,196 rows and 281,066 slots.
At the same cache size, the layout projects 135,165,536 stream bytes read
and 71,105,328 written, including initialization and checkpoint reads in
the schedule. Substituting the projected page reservation into the existing
State ledger leaves 3,060,972 entries. Ten-card training and convergence
remain open.

## Compact row directory

The source-frozen directory run at `36806b4` kept all 24,420 rows in their
original order. The independent census matched each saved history, actor,
holding, menu extent, and slot offset. It found a maximum of ten probes
against the 30-probe construction limit. The State reserves 231,814
entries during construction and 340,956 after releasing the lookup array,
including policy export. Composed admission fell from 841,925 to 500,045
entries. The directory added 2,344,320 charged work units.

Saved-only replay verified both sweeps and the final best responses. All
22,587,236 numerical bytes, both compact backing files, and the pager
counters matched the prior paged run. In one Windows observation per
profile, peak working set fell from 8,151,040 to 6,598,656 bytes, and
peak commit fell from 5,312,512 to 3,579,904 bytes. Native process time
was 3.235 and 3.365 seconds respectively.
[Compact directory evidence](../benchmarks/results/native-dyadic-compact-directory-accepted-v1/manifest.json)

At the derived 644-bit width, the rank-free ten-card census projects
1,392,228 State entries under the two-million-entry cap. Current formulas
already reserve at least 735,665,344 work units across State, History,
and paging and strategy bookkeeping. This subtotal excludes chance,
quantization, and other traversal work. The full-width checkpoint projects
108,768,308 bytes, and the integer and text payload reservation is
1,182,148,028 bits. Those estimates exceed their current limits. The
current rank cache would also see 340 ordered river prefixes. Grouping
those prefixes by final board yields 17 potential rank-only keys while
leaving ordered public histories distinct. The census does no hand ranking
or training.

Run `python -m scripts.census_virtual_dyadic_storage` to reproduce the counts.
[Raw census receipt](../benchmarks/results/native-dyadic-storage-census-v1/geometry.json)
