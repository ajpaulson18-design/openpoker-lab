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

Run `python -m scripts.census_virtual_dyadic_storage` to reproduce the counts.
[Raw census receipt](../benchmarks/results/native-dyadic-storage-census-v1/geometry.json)
