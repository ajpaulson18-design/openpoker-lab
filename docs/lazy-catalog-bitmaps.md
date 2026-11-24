# Exact first-holding-inline Catalog candidate

Status: local component and whole-walk arithmetic/storage gates pass normally
and optimized. Component Windows/Linux/sanitizer gates pass at `962c8c8`;
whole-walk platform and timing acceptance remain pending. The shared Catalog keeps
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

Local compilation passes unchanged `/O2 /W4 /WX` flags with MSVC 19.44. The
independent scalar suite runs three tests per Python mode; the complete native
frame and four corruptions pass in each mode with one observed native call.
The entire original frame remains valid, with its original 96,000-work
receipt and 13 guards. Eight new guards check exact failure kinds.
Thirty-two one-holding public blocks allocate zero lazy bitmap words versus
672 eager words, with exact full-history/menu identities. One promoted block
preserves all 1,326 generic original IDs in a single 21-word bitmap. These are
logical storage and identity observations, not a speed or physical-game claim.

## Whole-walk integration candidate

The separate `virtual-weighted-joint-single-pass-lazy` target binds the
Catalog storage purpose to Store limits before quantizer construction. The
ordinary eager targets retain their versioned contracts. Three new typed
Store/Catalog mismatch guards supplement the original ten read/epoch guards.
No arithmetic mode, denominator, Q52 apportionment or epoch count changes.

The proposed `OPLLGP01`/`OPLLGB01` wire contract 3 adds two final observed words:
allocated bitmap words and peak occupied logical metadata. Its complete
forecast is 150,030,714 work, 953,663 entries, 52,393,006 payload bits and 502,768
output bytes under the existing ceilings. Extra Catalog work and the two new
serialized words are charged; the metadata/payload reservations decrease.

The independent reader first authenticates every new schema/resource field,
then normalizes only those fields to the eager version. The unchanged current
eager authority validates every mathematical byte, complete retained policy,
default and traversal counter. An independently derived promotion census uses
the 434 authenticated E0 descriptors, own-holding changes and visible-prefix
equality between the two worlds. It checks the new bitmap and occupied-ledger
observations exactly. No hidden future cards enter policy identity.

Before frame copying or numerical preparation, the reference composes its
law/source/raw reservations with two bounded frame copies and fixed metadata
checks: 499,930,720 modeled work under the unchanged 500-million reference cap.
A memoryview prevents an otherwise unaccounted preliminary slice copy.

Frozen acceptance requires twelve full52 requests covering both range profiles
and tie/loss/win worlds, eight parser rejections, five wire-corruption refusals,
and all-row arithmetic/storage checks normally and optimized. A fresh eager
baseline must also match all ten published single-pass wires byte for byte
and independently verify two additional shared-board/distinct-holding cases;
the new candidate's explicitly normalized wire must match that baseline.

After correctness, compare eight alternating pairs of sixteen complete calls,
with two warmups per target. Cycle weighted tie/loss/win tickets 0, 4, 1966603
at rank 0 and a shared-board/distinct-holding request using
index `(16*block+call)%4`, identically for both targets. The coverage revision
is frozen before any elapsed comparison is executed. Preserve all 260
observations without retries. For adoption, require median lazy/eager
elapsed ratio at most 1.05 and at most two pairs above 1.10. This is a one-host
nonregression gate for a storage optimization, not a required speedup or an
RSS claim. Do not change these gates after observing timing.

At `b5c0f97`, both Python modes pass twelve candidate requests, eight real
parser rejections, twelve fresh eager baseline calls and five corruption
refusals. Each matrix records32 actual native calls; the associated epoch
guard records one additional call. All ten applicable eager outputs equal the
published single-pass wires. Candidate normalization equals the eager wire
hash after independent arithmetic and storage verification. The complete
normal/optimized test module runs two tests per mode without skips.

The first attempt at `3464791` preserved successful native exits but the new
verifier refused its footer because it compared a Python list with a tuple.
That refusal occurred before the unchanged numerical authority was called.
The corrected representation check is separate from mathematical acceptance;
retain the first attempt's logs and process bytes. The additional shared-board
promotion cases and four-case timing coverage were frozen before any elapsed
comparison, rather than changing the meaning of that earlier attempt.

## First elapsed miss and revised membership path

The first complete elapsed comparison at `04e6c11` records all 260 native
exits and exact full wires, but misses the adoption gate. Its eight lazy/eager
ratios are 0.883524, 0.870562, 1.078457, 1.155831, 1.312665, 1.003771,
1.139889 and 0.927811. Median 1.041114 is below 1.05, while three pairs
exceed 1.10 instead of the allowed two. This is not accepted nonregression;
the variation does not identify a CPU cause.

The next source revision simplifies the membership predicate. Every published
block has at least one seen holding. With exactly one, its inline original
index identifies the sole member in both purposes. With more than one, both
purposes have a populated bitmap. Checking `seen_count==1` directly therefore
preserves membership, duplicate behavior and all ownership/menu guards while
avoiding a vector-empty test and a redundant singleton check. It also permits
the eager singleton to use its already recorded first index. This is a source-
based efficiency hypothesis, not a measured speedup. Freeze it before new
execution; keep the original observations and the unchanged timing gates.

At `67244f9`, all three focused component/epoch/whole tests pass in each Python
mode without skips, including the twelve-case arithmetic/storage matrix. The
second elapsed study again retains all 260 actual exits and exact wires, but
also misses the unchanged gate. Ratios are 1.095718, 1.094894, 1.072043,
1.174991, 0.965651, 0.886499, 0.964288 and 1.058200. Median 1.065121 exceeds
1.05, while only one pair exceeds 1.10. Both studies remain evidence; neither
is accepted runtime nonregression. The candidate remains explicit and opt-in.

Pause further kernel tuning until a [bounded own-thread CPU investigation](joint-thread-cycles.md)
distinguishes the cost families inside the walk. Neither logical metadata
savings nor source-level simplification substitutes for that measurement.
