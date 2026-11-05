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

Run `python -m scripts.census_virtual_dyadic_storage` to reproduce the counts.
[Raw census receipt](../benchmarks/results/native-dyadic-storage-census-v1/geometry.json)
