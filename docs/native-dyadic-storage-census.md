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
river strategy state the first storage target. A bounded page layout can
preserve each exact visible row key while limiting resident state. Paging still
incurs total storage and traversal work. Lossless per-row integer scaling and
exact equivalence classes need separate proofs and capacity measurements before
they can change the admission contract.

Run `python -m scripts.census_virtual_dyadic_storage` to reproduce the counts.
[Raw census receipt](../benchmarks/results/native-dyadic-storage-census-v1/geometry.json)
