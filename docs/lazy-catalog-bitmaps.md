# Exact first-holding-inline Catalog candidate

Status: local component gates pass normally and optimized at `0d14b07`;
whole-walk coupling and cross-platform acceptance remain pending. The shared Catalog keeps
its eager-bitmap default. An explicit `first_holding_inline` storage contract
keeps one original holding ID in the existing block descriptor, then creates
the exact bitmap when a second distinct holding is encountered. Duplicate
reads allocate nothing, promotion preserves both original indices, and all
later membership tests use the same bitmap semantics. RowId, full History,
actor, menu and owner identity contracts remain unchanged.

This follows the [uniform lifetime worksheet](joint-learning-lifetime.md).
The eager full52 Catalog allocates 21 words per public block regardless of
whether that block has seen only one holding. Removing that allocation in the
common sparse case improves representation without pruning information rows
or increasing resource ceilings. It does not solve the asymptotic growth in
encountered histories or admit longer learning.

## Peak reservation proof

Let B and R be the admitted public-block and seen-row maxima, with R>=B for
the opt-in contract. Let b be occupied blocks and d promoted bitmaps. Then
`b<=B`, `d<=b`, and `b+d<=R`: every block needs one row and every promotion
needs a second distinct row. Each bitmap has at most w=`ceil(H/64)<=21` words.
Since w<32, maximizing `32*b+w*d` under these inequalities chooses
`b=B`, `d=min(B,R-B)`. Fewer occupied blocks release more descriptor allowance
than they can consume in extra bitmaps. A bitmap may therefore be allocated
even when the forecast's `min(B,R-B)` is zero; the complete coupled bound,
rather than that isolated term, is the invariant.

The versioned logical metadata reservation is
`1024+320*M+32*B+w*min(B,R-B)`, compared with eager
`1024+320*M+32*B+w*B`. The first holding fits the existing 32-word descriptor
envelope; a compile-time size check guards the owned Block structure. As in
the original ledger, this is not exhaustive allocator/RSS accounting.
Promotion checks the complete occupied ledger before allocating its bitmap.
No old bitmap exists at promotion, so there is no overlapping bitmap copy.
Extra work is explicitly reserved as 256 setup units plus 32 per access.

For the existing T2 geometry B=R=868, M=434, H=1326, Catalog metadata changes
from 185,908 to 167,680 words. For the 100-world deterministic encounter upper
geometry B=42,806 and R=43,400, it changes from 2,408,622 to 1,522,170 words.
The latter is a metadata comparison, not a forecast for actual lifetime
lookups, Store state, epochs, whole-request work, RNG or learning quality.

## Frozen acceptance gates

Before compilation/execution, freeze the owner, controls and independent scalar
reference. Independently maximize every feasible small descriptor/bitmap state
for all bitmap widths 1..21. Reject invalid mode or R<B geometry, insufficient
work/metadata, and capacity violations before bitmap preparation.

The source-built component must preserve the entire original Catalog frame
and its 13 guards. New controls exercise an inline nonzero first index,
duplicate reads, all 1,326 original holding IDs after promotion, stable handles,
32 distinct visible public blocks without bitmaps, eager/lazy exact identity
and menu parity, descriptor/bitmap budget sharing, and eight typed rejection
guards. Normal/optimized independent replay checks the full frame and four
corruptions. Generic holding indices remain metadata controls rather than a
physical-support claim.

Only after these gates pass should the candidate be coupled to the existing
full52 T2 walk with a separate resource/version contract and all-row arithmetic
parity. Performance and actual retained-union evidence remain separate.

Local compilation passes unchanged `/O2 /W4 /WX` flags with MSVC19.44. The
independent scalar suite runs three tests per Python mode; the complete native
frame and four corruptions pass in each mode with one observed native call.
The entire original frame remains valid, with its original 96,000-work
receipt and 13 guards. Eight new guards check exact failure kinds.
Thirty-two one-holding public blocks allocate zero lazy bitmap words versus
672 eager words, with exact full-history/menu identities. One promoted block
preserves all1,326 generic original IDs in a single21-word bitmap. These are
logical storage and identity observations, not a speed or physical-game claim.
